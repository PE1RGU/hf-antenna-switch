//! Shack interface logic. Call [`Shack::tick`] every [`TICK`] ms from the main loop.
//!
//! [`Shack`] is the state machine of the interface. The host port
//! (host-protocol.md) and the display are submodules; they add methods to the same
//! `Shack` type.
//!
//! Rules implemented here (design-log.md, hardware/unit/verify):
//! - F1: expander outputs written before its configuration, at start-up and after every expander reset.
//! - LATCH_CLR: one edge, once, after the start-up self-test. Not again after a later fault (cause unknown).
//! - WDI: toggled from the main loop only (system-verification rule 6), every tick.
//! - Handshake for R2 and R3 (D-63, link-protocol.md 5.1): PERMIT only while the box reports the permit.
//! - F14: at TX end, inhibit first, then wait for TX sense inactive and at least 100 ms, then TxEnd.
//! - Link lost: drop every permit and key at once; the box keeps K0 (F13); TxEnd after the link returns.
//!
//! # TX handshake of R2 and R3
//!
//! Each of R2 and R3 has a [`TxState`]. The moves are:
//!
//! | From | To | When |
//! |---|---|---|
//! | Idle | Requesting | `set_tx(on)` with the link up: TxRequest queued |
//! | Requesting | Permitted | The box Status shows permit bit k: PERMIT_Rk on in the same tick |
//! | Requesting, Permitted | Ending | `set_tx(off)`, host time-out, TxRequest refused, permit lost or link lost: PERMIT_Rk and KEY_Rk off in the same tick |
//! | Ending | Releasing | Link up, TX sense inactive, at least 100 ms since the inhibit (F14): TxEnd queued |
//! | Releasing | Idle | The box Status shows permit bit k = 0 |
//! | Releasing | Ending | Link lost or TxEnd refused: TxEnd again after the F14 wait |
//!
//! PERMIT_Rk is on only in `Permitted`, and only while the box reports permit bit k.
//! R1 has no handshake: K0 of R1 follows the PTT loop in hardware, and PERMIT_R1
//! follows the box status (C-1).

mod display;
pub use display::{AUTO_CARDS_MS, AUTO_FLOW_MS, ROWS_PER_TICK};
mod host;

use crate::board::{EXPANDER_ADDR, ExpPin, exp, expander_config};
use crate::config::{CONFIG_MAX, Config};
use crate::hw::ShackHw;
use heapless::Deque;
use link_proto::frame::MAX_WIRE;
use link_proto::shack_link::{Event as LinkEvent, ShackLink};
use link_proto::{Command, Decoder, Ms, Radio, Reply, ResultCode, Route, Status};
use pca9539::Pca9539;

/// Main loop period. Inputs are polled at this rate (D-83).
pub const TICK: Ms = 10;
/// F14: minimum time from the inhibit to 'end'.
pub const TX_END_MIN_WAIT: Ms = 100;
/// Stored settings are saved this long after the last change.
pub const CONFIG_SAVE_DELAY: Ms = 2000;
/// F14 plausibility: keyed this long without TX sense flags the port.
pub const TX_SENSE_PLAUSIBLE: Ms = 500;

const EXPANDER: Pca9539 = Pca9539::new(EXPANDER_ADDR);
const KEYS: [ExpPin; 3] = [exp::KEY_R1, exp::KEY_R2, exp::KEY_R3];
const TX_SENSE: [ExpPin; 3] = [exp::R1_TX, exp::R2_TX, exp::R3_TX];

/// TX state of R2 and R3 (R1 uses the hardware PTT loop).
///
/// The handshake follows link-protocol.md 5.1 (D-63). See the module docs for the
/// diagram.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TxState {
    /// No TX wanted. K0 released, no permit.
    Idle,
    /// TxRequest sent, no permit yet.
    Requesting,
    /// Box reports the permit; PERMIT is on.
    Permitted,
    /// Inhibited at `since`; waiting for the F14 conditions before TxEnd.
    Ending {
        /// Time of the inhibit, in ms. TxEnd goes no earlier than
        /// `since + TX_END_MIN_WAIT`.
        since: Ms,
    },
    /// TxEnd sent; waiting for the box to drop the permit.
    Releasing,
}

/// Something that happened in a tick, for the log or the host.
///
/// [`Shack::tick`] queues events; [`Shack::take_event`] takes them out, oldest
/// first. The queue holds 16; when it is full, the oldest event is dropped. The
/// host also gets each event as a `!` line (host-protocol.md section 6), except
/// [`Event::VersionMismatch`], which comes as a `#` log line.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Event {
    /// The expander answered and is set up (F1 order). Inputs are valid from now on.
    ExpanderReady,
    /// Expander did not answer or was reset: all outputs off, set up again.
    ExpanderLost,
    /// The box answered Hello with the same protocol version.
    LinkUp,
    /// No valid answer from the box for 300 ms (link-protocol.md 6). All permits
    /// and keys are off.
    LinkLost,
    /// The box speaks another link protocol version: no commands are sent.
    VersionMismatch,
    /// The box refused a command (Poll and Hello not included).
    Refused {
        /// The refused command.
        cmd: Command,
        /// The result code from the box (link-protocol.md 4.1).
        result: ResultCode,
    },
    /// The box dropped a permit that the shack still used.
    PermitLost(Radio),
    /// F14 plausibility: keyed with the permit, but TX sense stays inactive.
    TxSenseFault(Radio),
    /// Expander lost after start-up: the fault latch is likely set. TX blocked until cleared (C-2).
    Fault,
    /// Host keep-alive missed: TX ended, keys released (host-protocol.md section 8).
    HostTimeout,
}

/// Why a request from the host or the main loop was refused at once.
///
/// These are local checks. The box still checks every command it gets, and a
/// refusal from the box comes later as [`Event::Refused`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Refusal {
    /// The box link is down, so the request cannot go to the box.
    LinkDown,
    /// R1 has no handshake; R2 and R3 only.
    NotForR1,
    /// The radio is transmitting or ending (F13 on the shack side).
    TxBusy,
    /// The command queue to the box (8 commands) is full. Try again later.
    QueueFull,
}

/// Expander inputs, decoded.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Inputs {
    /// TX sense per radio (index 0 = R1): `true` = the radio transmits.
    pub tx_sense: [bool; 3],
    /// Bit 0 = BAND A ... bit 3 = BAND D.
    pub band: u8,
    /// KILL switch pressed.
    pub kill: bool,
    /// SAFE latch set: TX blocked in hardware until the RESET button.
    pub latched: bool,
}

impl Inputs {
    fn from_word(w: u16) -> Self {
        let b = |p: ExpPin| w & (1 << p.bit) != 0;
        Inputs {
            tx_sense: TX_SENSE.map(b),
            band: [exp::BAND_A, exp::BAND_B, exp::BAND_C, exp::BAND_D]
                .iter()
                .enumerate()
                .fold(0, |acc, (i, p)| acc | (b(*p) as u8) << i),
            kill: b(exp::KILL_S),
            latched: b(exp::LATCHED),
        }
    }
}

/// The shack interface state machine.
///
/// Make one with [`Shack::new`] and call [`Shack::tick`] every 10 ms. Requests
/// (`set_route`, `set_tx`, `set_key`...) only record what is wanted. The next tick
/// checks the conditions and sets the outputs. The host port calls the same
/// requests from its text commands.
pub struct Shack {
    expander_ready: bool,
    latch_cleared: bool,
    wdi: bool,
    exp_written: Option<u16>,
    inputs: Option<Inputs>,
    safe_lost: bool,
    link: ShackLink,
    decoder: Decoder,
    status: Option<Status>,
    tx: [TxState; 3],
    want_tx: [bool; 3],
    want_key: [bool; 3],
    permit_out: [bool; 3],
    keyed_since: [Option<Ms>; 3],
    sense_fault: [bool; 3],
    route_r1_pending: bool,
    sw_stop: bool,
    pending: Deque<Command, 8>,
    events: Deque<Event, 16>,
    fault_known: bool,
    host: host::HostPort,
    /// The SAFE latch was clear at least once since power-up (Safe stop cause).
    ever_unlatched: bool,
    /// Stored settings (host-protocol.md 8a).
    config: Config,
    config_loaded: bool,
    /// Time of the last unsaved change.
    config_dirty: Option<Ms>,
    /// Send the stored routes and bias once the box is ready (after each link up).
    restore_pending: bool,
    display: display::Display,
}

impl Default for Shack {
    fn default() -> Self {
        Self::new()
    }
}

impl Shack {
    /// A new interface at power-up: expander not set up, link down, every permit
    /// and key off, SAFE assumed lost until the first tick reads it.
    pub fn new() -> Self {
        Shack {
            expander_ready: false,
            latch_cleared: false,
            wdi: false,
            exp_written: None,
            inputs: None,
            safe_lost: true,
            link: ShackLink::new(),
            decoder: Decoder::new(),
            status: None,
            tx: [TxState::Idle; 3],
            want_tx: [false; 3],
            want_key: [false; 3],
            permit_out: [false; 3],
            keyed_since: [None; 3],
            sense_fault: [false; 3],
            route_r1_pending: false,
            sw_stop: false,
            pending: Deque::new(),
            events: Deque::new(),
            fault_known: false,
            host: host::HostPort::new(),
            ever_unlatched: false,
            config: Config::default(),
            config_loaded: false,
            config_dirty: None,
            restore_pending: false,
            display: display::Display::new(),
        }
    }

    // ---------------------------------------------------------------- requests

    /// Queue a route change for `radio` to the box.
    ///
    /// Refused while that radio is not [`TxState::Idle`] (F13 on the shack side).
    /// For R1, PERMIT_R1 stays off from now until the box answers (C-1). The box
    /// checks the route (H1 to H4) and the result comes as a reply.
    pub fn set_route(&mut self, radio: Radio, route: Route) -> Result<(), Refusal> {
        if self.tx[radio.index()] != TxState::Idle {
            return Err(Refusal::TxBusy);
        }
        self.queue(Command::SetRoute { radio, route })?;
        if radio == Radio::R1 {
            self.route_r1_pending = true;
        }
        Ok(())
    }

    /// Ask for (or end) TX on R2 or R3.
    ///
    /// `on = true` starts the handshake on the next tick (D-63). `on = false` ends
    /// TX the F14 way and also releases the key. Ending is always allowed, also
    /// with the link down.
    pub fn set_tx(&mut self, radio: Radio, on: bool) -> Result<(), Refusal> {
        if radio == Radio::R1 {
            return Err(Refusal::NotForR1);
        }
        if on && !self.link.is_up() {
            return Err(Refusal::LinkDown);
        }
        self.want_tx[radio.index()] = on;
        if !on {
            self.want_key[radio.index()] = false;
        }
        Ok(())
    }

    /// Key the radio through the interface. Takes effect only while its permit is out.
    ///
    /// The key is a wish: KEY_Rk goes high on the expander only when PERMIT_Rk is
    /// out, and the hardware gates it by the permit as well.
    pub fn set_key(&mut self, radio: Radio, on: bool) {
        self.want_key[radio.index()] = on;
    }

    /// Queue a bias-T change to the box: `mask` is the set of columns with the
    /// bias-T on.
    pub fn set_bias(&mut self, mask: link_proto::ColMask) -> Result<(), Refusal> {
        self.queue(Command::SetBias(mask))
    }

    /// Software stop: opens the SAFE loop (SW_STOP_N low). Release does not clear the latch.
    pub fn software_stop(&mut self, on: bool) {
        self.sw_stop = on;
    }

    // ---------------------------------------------------------------- state

    /// The box link is up (Hello answered, no time-out).
    pub fn link_up(&self) -> bool {
        self.link.is_up()
    }

    /// The last Status from the box. `None` before the first one and after a link loss.
    pub fn box_status(&self) -> Option<&Status> {
        self.status.as_ref()
    }

    /// The expander inputs of the last tick. `None` while the expander is not ready.
    pub fn inputs(&self) -> Option<&Inputs> {
        self.inputs.as_ref()
    }

    /// No SAFE loop current at the last tick (GPIO21 high).
    pub fn safe_lost(&self) -> bool {
        self.safe_lost
    }

    /// TX state of `radio`. Always [`TxState::Idle`] for R1 (no handshake).
    pub fn tx_state(&self, radio: Radio) -> TxState {
        self.tx[radio.index()]
    }

    /// PERMIT line of `radio` as driven now.
    pub fn permit(&self, radio: Radio) -> bool {
        self.permit_out[radio.index()]
    }

    /// Take the oldest queued [`Event`], or `None` when there is none.
    pub fn take_event(&mut self) -> Option<Event> {
        self.events.pop_front()
    }

    // ---------------------------------------------------------------- main loop

    /// Run one pass of the main loop. Call it every [`TICK`] ms with the present
    /// time `now` in ms (from power-up; it must not go back).
    ///
    /// The order of the steps is in the crate docs. The call never blocks: the
    /// display, the link and the flash each do a short step per tick.
    pub fn tick<H: ShackHw>(&mut self, now: Ms, hw: &mut H) {
        self.pass(now, hw);
        // Kick the supervisor from the main loop only, after the checks of the pass
        // (D-59 rule 1). A pass that hangs or panics gives no kick, so the
        // supervisor sets the fault latch and every radio is inhibited in hardware.
        self.wdi = !self.wdi;
        hw.set_wdi(self.wdi);
    }

    /// The work of one tick, before the watchdog kick. Returns early when the
    /// expander is not ready.
    fn pass<H: ShackHw>(&mut self, now: Ms, hw: &mut H) {
        self.safe_lost = hw.safe_lost();
        self.load_config(hw);

        if !self.expander_ready {
            // F1: `init` writes the output word before the configuration.
            if EXPANDER
                .init(hw.i2c(), self.exp_word(), expander_config())
                .is_err()
            {
                // No expander: TX stays off; the host still gets answers.
                self.host_rx(now, hw);
                self.host_tx(hw);
                return;
            }
            self.expander_ready = true;
            self.exp_written = Some(self.exp_word());
            self.event(Event::ExpanderReady);
            // Self-test passed (expander answers): one LATCH_CLR edge, only at
            // start-up (D-59 rule 2). After a later reset the host must use
            // `clearfault` (C-2).
            if !self.latch_cleared {
                hw.set_latch_clr(true);
                hw.set_latch_clr(false);
                self.latch_cleared = true;
            }
        }
        match self.read_expander(hw) {
            Some(i) => {
                self.ever_unlatched |= !i.latched;
                self.inputs = Some(i);
            }
            None => {
                self.expander_ready = false;
                self.exp_written = None;
                self.inputs = None;
                self.drop_all(hw);
                self.display.lost();
                self.event(Event::ExpanderLost);
                if self.latch_cleared && !self.fault_known {
                    self.fault_known = true;
                    self.event(Event::Fault);
                }
                self.host_rx(now, hw);
                self.host_tx(hw);
                return;
            }
        }

        // Box link: decode replies, then check the 300 ms link time-out.
        while let Some(b) = hw.uart_read() {
            if let Some(Ok(f)) = self.decoder.push::<Reply>(b)
                && let Some(e) = self.link.receive(now, f)
            {
                self.on_link(now, e);
            }
        }
        if let Some(e) = self.link.check_timeout(now) {
            self.on_link(now, e);
        }

        self.host_rx(now, hw);
        self.host_keep_alive(now);
        self.restore_step();
        for r in [Radio::R2, Radio::R3] {
            self.step_tx(now, r);
        }
        // One command at a time: the next one waits for the answer to the last.
        if self.link.is_up()
            && !self.link.busy()
            && let Some(c) = self.pending.pop_front()
        {
            let _ = self.link.submit(c);
        }
        if let Some(f) = self.link.transmit(now) {
            let mut buf = [0u8; MAX_WIRE];
            let n = f.encode(&mut buf);
            hw.uart_write(&buf[..n]);
        }
        self.apply_outputs(now, hw);
        self.host_tx(hw);
        self.display_step(now, hw);
        self.save_config(now, hw);
    }

    fn load_config<H: ShackHw>(&mut self, hw: &mut H) {
        if self.config_loaded {
            return;
        }
        self.config_loaded = true;
        let mut buf = [0u8; CONFIG_MAX];
        let n = hw.config_load(&mut buf).min(CONFIG_MAX);
        match Config::decode(&buf[..n]) {
            Some(c) => self.config = c,
            None => self.host.log("stored settings not found, defaults used"),
        }
        self.display.sel = self.config.page;
    }

    pub(super) fn config_changed(&mut self, now: Ms) {
        self.config_dirty = Some(now);
    }

    /// Save 2 s after the last change: a burst of commands gives one flash write.
    fn save_config<H: ShackHw>(&mut self, now: Ms, hw: &mut H) {
        if self
            .config_dirty
            .is_some_and(|t| now.saturating_sub(t) >= CONFIG_SAVE_DELAY)
        {
            let mut buf = [0u8; CONFIG_MAX];
            let n = self.config.encode(&mut buf);
            hw.config_save(&buf[..n]);
            self.config_dirty = None;
        }
    }

    /// After a link up, once the box is ready: send the stored routes and bias that
    /// differ from what the box reports. The box checks them like any command.
    fn restore_step(&mut self) {
        let Some(s) = self.status.filter(|s| s.flags.ready) else {
            return;
        };
        if !self.restore_pending || !self.link.is_up() {
            return;
        }
        self.restore_pending = false;
        for r in Radio::ALL {
            let want = self.config.routes[r.index()];
            if want != Route::default() && s.routes[r.index()] != want {
                let _ = self.set_route(r, want);
            }
        }
        if self.config.bias != s.bias_en {
            let _ = self.set_bias(self.config.bias);
        }
    }

    /// The stored settings in use (names, routes, bias, page).
    pub fn config(&self) -> &Config {
        &self.config
    }

    fn read_expander<H: ShackHw>(&mut self, hw: &mut H) -> Option<Inputs> {
        let cfg = EXPANDER.read_config(hw.i2c()).ok()?;
        if cfg != expander_config() {
            return None; // expander was reset: registers at their defaults
        }
        EXPANDER.read_inputs(hw.i2c()).ok().map(Inputs::from_word)
    }

    fn on_link(&mut self, now: Ms, e: LinkEvent) {
        match e {
            LinkEvent::Up(_) => {
                self.restore_pending = true;
                self.event(Event::LinkUp);
            }
            LinkEvent::VersionMismatch(_) => self.event(Event::VersionMismatch),
            LinkEvent::Lost { .. } => {
                // Without a status, permit_wanted() is false for all radios, so
                // apply_outputs() drops every permit in this tick. Each radio that
                // was in the handshake goes to Ending: TxEnd after the link is back.
                self.status = None;
                self.pending.clear();
                self.route_r1_pending = false;
                for i in 0..3 {
                    self.want_tx[i] = false;
                    self.want_key[i] = false;
                    if !matches!(self.tx[i], TxState::Idle | TxState::Ending { .. }) {
                        self.tx[i] = TxState::Ending { since: now };
                    }
                }
                self.event(Event::LinkLost);
            }
            LinkEvent::Reply { cmd, status } => self.on_reply(now, cmd, status),
        }
    }

    fn on_reply(&mut self, now: Ms, cmd: Command, status: Status) {
        self.status = Some(status);
        let ok = status.result == ResultCode::Ok;
        // Keep the stored settings equal to what the box accepted.
        match cmd {
            Command::SetRoute { radio, .. } if ok => {
                let i = radio.index();
                if self.config.routes[i] != status.routes[i] {
                    self.config.routes[i] = status.routes[i];
                    self.config_changed(now);
                }
            }
            Command::SetBias(_) if ok && self.config.bias != status.bias_en => {
                self.config.bias = status.bias_en;
                self.config_changed(now);
            }
            _ => {}
        }
        match cmd {
            Command::SetRoute {
                radio: Radio::R1, ..
            } => self.route_r1_pending = false,
            Command::TxRequest(r) if !ok => {
                self.tx[r.index()] = TxState::Ending { since: now };
                self.want_tx[r.index()] = false;
            }
            Command::TxEnd(r) if !ok => self.tx[r.index()] = TxState::Ending { since: now },
            _ => {}
        }
        if !ok && !matches!(cmd, Command::Poll | Command::Hello { .. }) {
            self.event(Event::Refused {
                cmd,
                result: status.result,
            });
        }
        // Follow the permit bits in the Status (link-protocol.md 5.1).
        for r in [Radio::R2, Radio::R3] {
            let i = r.index();
            match self.tx[i] {
                TxState::Requesting if status.permit(r) => self.tx[i] = TxState::Permitted,
                TxState::Permitted if !status.permit(r) => {
                    self.tx[i] = TxState::Ending { since: now };
                    self.want_tx[i] = false;
                    self.event(Event::PermitLost(r));
                }
                TxState::Releasing if !status.permit(r) => self.tx[i] = TxState::Idle,
                _ => {}
            }
        }
    }

    /// Move the handshake of `r` on by local conditions (request, end, F14 wait).
    /// Moves caused by the box reply are in `on_reply`.
    fn step_tx(&mut self, now: Ms, r: Radio) {
        let i = r.index();
        let up = self.link.is_up();
        match self.tx[i] {
            TxState::Idle if self.want_tx[i] && up => {
                if self.queue(Command::TxRequest(r)).is_ok() {
                    self.tx[i] = TxState::Requesting;
                }
            }
            TxState::Requesting | TxState::Permitted if !self.want_tx[i] => {
                self.tx[i] = TxState::Ending { since: now };
            }
            TxState::Ending { since } => {
                let sense = self.inputs.is_some_and(|x| x.tx_sense[i]);
                if up
                    && !sense
                    && now.saturating_sub(since) >= TX_END_MIN_WAIT
                    && self.queue(Command::TxEnd(r)).is_ok()
                {
                    self.tx[i] = TxState::Releasing;
                }
            }
            _ => {}
        }
    }

    /// Permit per radio from the present state.
    fn permit_wanted(&self, r: Radio) -> bool {
        let Some(s) = self.status.filter(|_| self.link.is_up()) else {
            return false;
        };
        match r {
            // R1 keys K0 by the PTT loop. Permit while the box is ready, R1 has a terminated
            // TX column, and no R1 route change is pending or running.
            Radio::R1 => {
                let tx = s.routes[0].tx;
                s.flags.ready
                    && !s.flags.switching
                    && !self.route_r1_pending
                    && tx != link_proto::Col::None
                    && s.k1.contains(tx)
            }
            _ => self.tx[r.index()] == TxState::Permitted && s.permit(r),
        }
    }

    /// The expander output word for the present state: software stop, keys (only
    /// with the permit out) and the display pins.
    fn exp_word(&self) -> u16 {
        let mut w = 0u16;
        if !self.sw_stop {
            w |= 1 << exp::SW_STOP_N.bit;
        }
        for (i, k) in KEYS.iter().enumerate() {
            if self.permit_out[i] && self.want_key[i] {
                w |= 1 << k.bit;
            }
        }
        w | self.display.exp_bits()
    }

    fn apply_outputs<H: ShackHw>(&mut self, now: Ms, hw: &mut H) {
        let want = Radio::ALL.map(|r| self.permit_wanted(r));
        // Inhibit first: permits that go off, then the expander, then permits that go on.
        // So a radio is inhibited before anything else changes, and a key never
        // goes high before its permit is out.
        for r in Radio::ALL {
            if self.permit_out[r.index()] && !want[r.index()] {
                hw.set_permit(r, false);
                self.permit_out[r.index()] = false;
            }
        }
        let w = self.exp_word();
        if self.exp_written != Some(w) && EXPANDER.write_outputs(hw.i2c(), w).is_ok() {
            self.exp_written = Some(w);
        }
        for r in Radio::ALL {
            if !self.permit_out[r.index()] && want[r.index()] {
                hw.set_permit(r, true);
                self.permit_out[r.index()] = true;
            }
        }
        // Keys follow on the next write once the permit is out.
        let w = self.exp_word();
        if self.exp_written != Some(w) && EXPANDER.write_outputs(hw.i2c(), w).is_ok() {
            self.exp_written = Some(w);
        }
        self.check_tx_sense(now);
    }

    /// F14 plausibility (C-3): keyed with the permit for 500 ms without TX sense
    /// flags the port once. TX is not blocked.
    fn check_tx_sense(&mut self, now: Ms) {
        for r in Radio::ALL {
            let i = r.index();
            let keyed = self.permit_out[i] && self.want_key[i];
            if !keyed {
                self.keyed_since[i] = None;
                self.sense_fault[i] = false;
                continue;
            }
            let since = *self.keyed_since[i].get_or_insert(now);
            let sense = self.inputs.is_some_and(|x| x.tx_sense[i]);
            if !sense && !self.sense_fault[i] && now.saturating_sub(since) >= TX_SENSE_PLAUSIBLE {
                self.sense_fault[i] = true;
                self.event(Event::TxSenseFault(r));
            }
        }
    }

    fn drop_all<H: ShackHw>(&mut self, hw: &mut H) {
        for r in Radio::ALL {
            hw.set_permit(r, false);
            self.permit_out[r.index()] = false;
        }
    }

    /// Add a command for the box. A command that is already queued is not added
    /// twice (all commands set a state, link-protocol.md 5).
    fn queue(&mut self, cmd: Command) -> Result<(), Refusal> {
        if self.pending.iter().any(|c| *c == cmd) {
            return Ok(());
        }
        self.pending.push_back(cmd).map_err(|_| Refusal::QueueFull)
    }

    fn event(&mut self, e: Event) {
        if self.events.is_full() {
            self.events.pop_front();
        }
        let _ = self.events.push_back(e);
        self.host_event(e);
    }

    /// True after a supervisor reset during operation, until `clearfault`.
    ///
    /// The firmware cannot read FAULT itself. It knows a fault when the expander
    /// was reset after start-up (the expander RESET is RESET_N, C-2).
    pub fn fault_known(&self) -> bool {
        self.fault_known
    }
}
