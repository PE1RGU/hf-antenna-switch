//! Shack interface logic. Call `tick` every TICK ms from the main loop.
//!
//! Rules implemented here (design-log.md, hardware/unit/verify):
//! - F1: expander outputs written before its configuration, at start-up and after every expander reset.
//! - LATCH_CLR: one edge, once, after the start-up self-test. Not again after a later fault (cause unknown).
//! - WDI: toggled from the main loop only (system-verification rule 6), every tick.
//! - Handshake for R2 and R3 (D-63, link-protocol.md 5.1): PERMIT only while the box reports the permit.
//! - F14: at TX end, inhibit first, then wait for TX sense inactive and at least 100 ms, then TxEnd.
//! - Link lost: drop every permit and key at once; the box keeps K0 (F13); TxEnd after the link returns.

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
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TxState {
    Idle,
    /// TxRequest sent, no permit yet.
    Requesting,
    /// Box reports the permit; PERMIT is on.
    Permitted,
    /// Inhibited at `since`; waiting for the F14 conditions before TxEnd.
    Ending {
        since: Ms,
    },
    /// TxEnd sent; waiting for the box to drop the permit.
    Releasing,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Event {
    ExpanderReady,
    /// Expander did not answer or was reset: all outputs off, set up again.
    ExpanderLost,
    LinkUp,
    LinkLost,
    VersionMismatch,
    Refused {
        cmd: Command,
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

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Refusal {
    LinkDown,
    /// R1 has no handshake; R2 and R3 only.
    NotForR1,
    /// The radio is transmitting or ending (F13 on the shack side).
    TxBusy,
    QueueFull,
}

/// Expander inputs, decoded.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Inputs {
    pub tx_sense: [bool; 3],
    /// Bit 0 = BAND A ... bit 3 = BAND D.
    pub band: u8,
    pub kill: bool,
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
    pub fn set_key(&mut self, radio: Radio, on: bool) {
        self.want_key[radio.index()] = on;
    }

    pub fn set_bias(&mut self, mask: link_proto::ColMask) -> Result<(), Refusal> {
        self.queue(Command::SetBias(mask))
    }

    /// Software stop: opens the SAFE loop (SW_STOP_N low). Release does not clear the latch.
    pub fn software_stop(&mut self, on: bool) {
        self.sw_stop = on;
    }

    // ---------------------------------------------------------------- state

    pub fn link_up(&self) -> bool {
        self.link.is_up()
    }

    pub fn box_status(&self) -> Option<&Status> {
        self.status.as_ref()
    }

    pub fn inputs(&self) -> Option<&Inputs> {
        self.inputs.as_ref()
    }

    pub fn safe_lost(&self) -> bool {
        self.safe_lost
    }

    pub fn tx_state(&self, radio: Radio) -> TxState {
        self.tx[radio.index()]
    }

    pub fn permit(&self, radio: Radio) -> bool {
        self.permit_out[radio.index()]
    }

    pub fn take_event(&mut self) -> Option<Event> {
        self.events.pop_front()
    }

    // ---------------------------------------------------------------- main loop

    pub fn tick<H: ShackHw>(&mut self, now: Ms, hw: &mut H) {
        self.wdi = !self.wdi;
        hw.set_wdi(self.wdi);
        self.safe_lost = hw.safe_lost();
        self.load_config(hw);

        if !self.expander_ready {
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

    /// The stored settings in use.
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
    pub fn fault_known(&self) -> bool {
        self.fault_known
    }
}
