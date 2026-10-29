//! Host port: text lines from the Mac or Pi (docs/design/host-protocol.md).
//!
//! The host asks; the shack logic decides. No command here clears the SAFE latch
//! or gives a permit: commands only set what the host wants, as the API does.
//!
//! Each tick reads the received bytes and answers every complete line in the same
//! tick (`ok`, `err ...` or a text answer). Commands for the box answer `ok` when
//! queued; the box result comes later as an event. Events are not sent at once:
//! they are queued and sent at the end of the tick, after the change detection,
//! so the host sees the new state in a fixed order.

use super::*;
use core::fmt::{self, Write as _};
use heapless::{String, Vec};
use host_proto::{
    BoxPart, ErrorCode, ErrorLine, HostCommand, HostEvent, KEEP_ALIVE_DEFAULT_S, MAX_LINE,
    NameTarget, NamesLine, PROTO_VERSION, RadioStatus, StatusLine, TxPhase, parse,
};

/// Longest line the shack sends (the status line is about 200 characters).
const OUT_LINE: usize = 256;

/// Last value sent to the host per item; `None` = not sent yet.
#[derive(Default)]
struct Seen {
    safe_ok: Option<bool>,
    latched: Option<bool>,
    kill: Option<bool>,
    band: Option<u8>,
    permit: [Option<bool>; 3],
    tx: [Option<TxPhase>; 3],
    routes: [Option<Route>; 3],
}

pub(super) struct HostPort {
    buf: Vec<u8, MAX_LINE>,
    overflow: bool,
    events_on: bool,
    /// Keep-alive time-out in seconds (`keepalive`, section 8).
    keep_alive_s: u8,
    /// Time of the last line from the host; None until the host speaks (keep-alive off).
    last_line: Option<Ms>,
    queued: Deque<HostEvent, 32>,
    logs: Deque<&'static str, 4>,
    seen: Seen,
}

impl HostPort {
    pub(super) fn new() -> Self {
        HostPort {
            buf: Vec::new(),
            overflow: false,
            events_on: true,
            keep_alive_s: KEEP_ALIVE_DEFAULT_S,
            last_line: None,
            queued: Deque::new(),
            logs: Deque::new(),
            seen: Seen::default(),
        }
    }

    fn push(&mut self, e: HostEvent) {
        if self.queued.is_full() {
            self.queued.pop_front();
        }
        let _ = self.queued.push_back(e);
    }

    pub(super) fn log(&mut self, text: &'static str) {
        if self.logs.is_full() {
            self.logs.pop_front();
        }
        let _ = self.logs.push_back(text);
    }
}

fn phase(s: TxState) -> TxPhase {
    match s {
        TxState::Idle => TxPhase::Idle,
        TxState::Requesting => TxPhase::Requesting,
        TxState::Permitted => TxPhase::Permitted,
        TxState::Ending { .. } => TxPhase::Ending,
        TxState::Releasing => TxPhase::Releasing,
    }
}

fn write_line<H: ShackHw>(hw: &mut H, args: fmt::Arguments<'_>) {
    let mut s: String<OUT_LINE> = String::new();
    let _ = s.write_fmt(args);
    hw.usb_write(s.as_bytes());
    hw.usb_write(b"\r\n");
}

/// Mark a change and remember the new value.
fn changed<T: PartialEq + Copy>(seen: &mut Option<T>, now: T) -> bool {
    let c = *seen != Some(now);
    *seen = Some(now);
    c
}

impl Shack {
    /// Read host bytes; answer each complete line.
    pub(super) fn host_rx<H: ShackHw>(&mut self, now: Ms, hw: &mut H) {
        while let Some(b) = hw.usb_read() {
            if b != b'\n' && b != b'\r' {
                if self.host.buf.push(b).is_err() {
                    self.host.overflow = true;
                }
                continue;
            }
            let line = core::mem::take(&mut self.host.buf);
            self.host.last_line = Some(now);
            let answer = if core::mem::take(&mut self.host.overflow) {
                Err(ErrorCode::TooLong)
            } else {
                match core::str::from_utf8(&line) {
                    Ok(l) if l.trim().is_empty() => continue,
                    Ok(l) => parse(l).and_then(|cmd| self.host_command(now, cmd, hw)),
                    Err(_) => Err(ErrorCode::Syntax),
                }
            };
            match answer {
                Ok(Some(text)) => write_line(hw, format_args!("{text}")),
                Ok(None) => write_line(hw, format_args!("ok")),
                Err(e) => write_line(hw, format_args!("{}", ErrorLine(e))),
            }
        }
    }

    fn host_command<H: ShackHw>(
        &mut self,
        now: Ms,
        cmd: HostCommand,
        hw: &mut H,
    ) -> Result<Option<String<OUT_LINE>>, ErrorCode> {
        let refusal = |r: Refusal| match r {
            Refusal::LinkDown => ErrorCode::LinkDown,
            Refusal::NotForR1 => ErrorCode::NotForR1,
            Refusal::TxBusy => ErrorCode::TxBusy,
            Refusal::QueueFull => ErrorCode::QueueFull,
        };
        let link_up = |s: &Self| {
            if s.link.is_up() {
                Ok(())
            } else {
                Err(ErrorCode::LinkDown)
            }
        };
        match cmd {
            HostCommand::Hello => {
                let mut s = String::new();
                let _ = write!(
                    s,
                    "ok shack fw {} proto {}",
                    env!("CARGO_PKG_VERSION"),
                    PROTO_VERSION
                );
                return Ok(Some(s));
            }
            HostCommand::Status => {
                let mut s = String::new();
                let _ = write!(s, "{}", self.status_line());
                return Ok(Some(s));
            }
            HostCommand::Route { radio, route } => {
                link_up(self)?;
                self.set_route(radio, route).map_err(refusal)?;
            }
            HostCommand::Tx { radio, on } => self.set_tx(radio, on).map_err(refusal)?,
            HostCommand::Key { radio, on } => self.set_key(radio, on),
            HostCommand::Bias(m) => {
                link_up(self)?;
                self.set_bias(m).map_err(refusal)?;
            }
            HostCommand::Stop(on) => self.software_stop(on),
            HostCommand::ClearFault => {
                if !self.fault_known {
                    return Err(ErrorCode::NoFault);
                }
                // Same edge as at start-up; the latch ignores it while RESET_N is low.
                hw.set_latch_clr(true);
                hw.set_latch_clr(false);
                // With the expander down, RESET_N may still be low and the latch then
                // ignores the edge: keep the fault and say so, never claim a clear.
                if self.expander_ready {
                    self.fault_known = false;
                    self.host.log("fault latch cleared by host");
                } else {
                    self.host.log(
                        "LATCH_CLR sent, but the expander is not ready: fault kept, try again",
                    );
                }
            }
            HostCommand::Events(on) => self.host.events_on = on,
            HostCommand::KeepAlive(s) => self.host.keep_alive_s = s,
            HostCommand::Page(p) => {
                self.set_page(p);
                self.config.page = p;
                self.config_changed(now);
            }
            HostCommand::Name { target, name } => {
                match target {
                    NameTarget::Antenna(c) => self.config.antenna_names[c as usize - 1] = name,
                    NameTarget::Radio(r) => self.config.radio_names[r.index()] = name,
                }
                self.config_changed(now);
            }
            HostCommand::Help => {
                for l in host_proto::HELP {
                    write_line(hw, format_args!("# {l}"));
                }
            }
            HostCommand::Names => {
                let mut s = String::new();
                let c = &self.config;
                let _ = write!(
                    s,
                    "{}",
                    NamesLine {
                        antennas: &c.antenna_names,
                        radios: &c.radio_names
                    }
                );
                return Ok(Some(s));
            }
        }
        Ok(None)
    }

    /// Host silent for the keep-alive time-out while TX or a key is on: end it all (section 8).
    /// Routes, bias and the software stop stay as they are. The timer restarts, so
    /// one time-out gives one `!host timeout`.
    pub(super) fn host_keep_alive(&mut self, now: Ms) {
        let Some(last) = self.host.last_line else {
            return;
        };
        let active = self.want_tx.iter().chain(&self.want_key).any(|x| *x);
        if active && now.saturating_sub(last) >= Ms::from(self.host.keep_alive_s) * 1000 {
            self.want_tx = [false; 3];
            self.want_key = [false; 3];
            self.host.last_line = Some(now);
            self.event(Event::HostTimeout);
        }
    }

    pub(super) fn host_event(&mut self, e: Event) {
        let h = match e {
            Event::ExpanderReady => HostEvent::Expander(true),
            Event::ExpanderLost => HostEvent::Expander(false),
            Event::LinkUp => HostEvent::Link(true),
            Event::LinkLost => HostEvent::Link(false),
            Event::VersionMismatch => {
                self.host
                    .log("box link protocol version differs: no commands sent");
                return;
            }
            Event::Refused { cmd, result } => HostEvent::Refused(cmd, result),
            Event::PermitLost(r) => HostEvent::PermitLost(r),
            Event::TxSenseFault(r) => HostEvent::TxSenseFault(r),
            Event::Fault => HostEvent::Fault,
            Event::HostTimeout => HostEvent::HostTimeout,
        };
        self.host.push(h);
    }

    /// Queue change events, then send logs and events.
    pub(super) fn host_tx<H: ShackHw>(&mut self, hw: &mut H) {
        self.detect_changes();
        while let Some(text) = self.host.logs.pop_front() {
            write_line(hw, format_args!("# {text}"));
        }
        while let Some(e) = self.host.queued.pop_front() {
            if self.host.events_on {
                write_line(hw, format_args!("{e}"));
            }
        }
    }

    /// Compare the present state with the last values sent and queue an event for
    /// each change. The first call after start-up sends each known value once.
    fn detect_changes(&mut self) {
        let mut out: Vec<HostEvent, 16> = Vec::new();
        let seen = &mut self.host.seen;
        if changed(&mut seen.safe_ok, !self.safe_lost) {
            let _ = out.push(HostEvent::Safe(!self.safe_lost));
        }
        if let Some(i) = self.inputs {
            if changed(&mut seen.latched, i.latched) {
                let _ = out.push(HostEvent::Latched(i.latched));
            }
            if changed(&mut seen.kill, i.kill) {
                let _ = out.push(HostEvent::Kill(i.kill));
            }
            if changed(&mut seen.band, i.band) {
                let _ = out.push(HostEvent::Band(i.band));
            }
        }
        for r in Radio::ALL {
            let n = r.index();
            // State first, then its effect on the PERMIT line.
            if r != Radio::R1 && changed(&mut seen.tx[n], phase(self.tx[n])) {
                let _ = out.push(HostEvent::Tx(r, phase(self.tx[n])));
            }
            if changed(&mut seen.permit[n], self.permit_out[n]) {
                let _ = out.push(HostEvent::Permit(r, self.permit_out[n]));
            }
            if let Some(s) = self.status
                && changed(&mut seen.routes[n], s.routes[n])
            {
                let _ = out.push(HostEvent::Route(r, s.routes[n]));
            }
        }
        for e in out {
            self.host.push(e);
        }
    }

    fn status_line(&self) -> StatusLine {
        // Expander unknown: show the safe values (latched).
        let inp = self.inputs.unwrap_or(Inputs {
            latched: true,
            ..Default::default()
        });
        StatusLine {
            link: self.link.is_up(),
            safe_ok: !self.safe_lost,
            latched: inp.latched,
            kill: inp.kill,
            fault: self.fault_known,
            stop: self.sw_stop,
            keepalive: self.host.keep_alive_s,
            page: self.page(),
            band: inp.band,
            boxs: self.status.map(|s| BoxPart {
                ready: s.flags.ready,
                k1: s.k1,
                rfdet: s.rfdet,
                bias: s.bias_en,
                fault: s.fault.0,
            }),
            radios: Radio::ALL.map(|r| RadioStatus {
                route: self.status.map(|s| s.routes[r.index()]),
                tx: (r != Radio::R1).then(|| phase(self.tx[r.index()])),
                permit: self.permit_out[r.index()],
                key: self.want_key[r.index()],
            }),
        }
    }
}
