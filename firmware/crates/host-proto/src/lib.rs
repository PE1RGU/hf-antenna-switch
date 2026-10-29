//! Host protocol: Mac or Pi to the shack interface (docs/design/host-protocol.md).
//!
//! Text lines. Parsing is not case sensitive. Formatting writes one line without
//! its line end through `core::fmt`, so the caller picks the buffer.
#![no_std]

use core::fmt;
use link_proto::{Col, ColMask, Command, Radio, ResultCode, Route};

pub const PROTO_VERSION: u8 = 1;
/// Longest host line, without the line end.
pub const MAX_LINE: usize = 120;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HostCommand {
    Hello,
    Status,
    Route { radio: Radio, route: Route },
    Tx { radio: Radio, on: bool },
    Key { radio: Radio, on: bool },
    Bias(ColMask),
    Stop(bool),
    ClearFault,
    Events(bool),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ErrorCode {
    Syntax,
    Arg,
    LinkDown,
    NotForR1,
    TxBusy,
    QueueFull,
    TooLong,
    NoFault,
}

impl ErrorCode {
    pub fn as_str(self) -> &'static str {
        match self {
            ErrorCode::Syntax => "syntax",
            ErrorCode::Arg => "arg",
            ErrorCode::LinkDown => "linkdown",
            ErrorCode::NotForR1 => "notforr1",
            ErrorCode::TxBusy => "txbusy",
            ErrorCode::QueueFull => "queuefull",
            ErrorCode::TooLong => "toolong",
            ErrorCode::NoFault => "nofault",
        }
    }

    fn text(self) -> &'static str {
        match self {
            ErrorCode::Syntax => "unknown command or wrong number of words",
            ErrorCode::Arg => "value out of range",
            ErrorCode::LinkDown => "box link is down",
            ErrorCode::NotForR1 => "R1 uses the hardware PTT loop",
            ErrorCode::TxBusy => "radio transmits or ends TX",
            ErrorCode::QueueFull => "too many commands wait for the box",
            ErrorCode::TooLong => "line longer than 120 characters",
            ErrorCode::NoFault => "no fault known",
        }
    }
}

/// `err <code> <text>`.
pub struct ErrorLine(pub ErrorCode);

impl fmt::Display for ErrorLine {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "err {} {}", self.0.as_str(), self.0.text())
    }
}

// ---------------------------------------------------------------- parsing

fn eq(a: &str, b: &str) -> bool {
    a.eq_ignore_ascii_case(b)
}

fn radio(w: &str) -> Result<Radio, ErrorCode> {
    Radio::ALL
        .into_iter()
        .find(|r| eq(w, radio_name(*r)))
        .ok_or(ErrorCode::Arg)
}

fn col(w: &str) -> Result<Col, ErrorCode> {
    Col::ALL
        .into_iter()
        .find(|c| eq(w, col_name(*c)))
        .ok_or(ErrorCode::Arg)
}

fn col_list(w: &str) -> Result<ColMask, ErrorCode> {
    if w == "-" {
        return Ok(ColMask::EMPTY);
    }
    w.split(',')
        .try_fold(ColMask::EMPTY, |m, part| match col(part)? {
            Col::None => Err(ErrorCode::Arg),
            c => Ok(m.with(c)),
        })
}

fn on_off(w: &str) -> Result<bool, ErrorCode> {
    if eq(w, "on") {
        Ok(true)
    } else if eq(w, "off") {
        Ok(false)
    } else {
        Err(ErrorCode::Arg)
    }
}

/// Parse one host line (without or with its CR).
pub fn parse(line: &str) -> Result<HostCommand, ErrorCode> {
    let line = line.strip_suffix('\r').unwrap_or(line);
    if line.len() > MAX_LINE {
        return Err(ErrorCode::TooLong);
    }
    let mut w = ["", "", "", ""];
    let mut n = 0;
    for word in line.split_ascii_whitespace() {
        if n == w.len() {
            return Err(ErrorCode::Syntax);
        }
        w[n] = word;
        n += 1;
    }
    let cmd = w[0];
    let is = |k: &str, words: usize| eq(cmd, k) && n == words;
    if is("hello", 1) {
        Ok(HostCommand::Hello)
    } else if is("status", 1) {
        Ok(HostCommand::Status)
    } else if is("clearfault", 1) {
        Ok(HostCommand::ClearFault)
    } else if is("route", 4) {
        Ok(HostCommand::Route {
            radio: radio(w[1])?,
            route: Route {
                tx: col(w[2])?,
                rx: col(w[3])?,
            },
        })
    } else if is("tx", 3) {
        let radio = radio(w[1])?;
        let on = on_off(w[2])?;
        if radio == Radio::R1 {
            return Err(ErrorCode::NotForR1);
        }
        Ok(HostCommand::Tx { radio, on })
    } else if is("key", 3) {
        Ok(HostCommand::Key {
            radio: radio(w[1])?,
            on: on_off(w[2])?,
        })
    } else if is("bias", 2) {
        Ok(HostCommand::Bias(col_list(w[1])?))
    } else if is("stop", 2) {
        Ok(HostCommand::Stop(on_off(w[1])?))
    } else if is("events", 2) {
        Ok(HostCommand::Events(on_off(w[1])?))
    } else {
        Err(ErrorCode::Syntax)
    }
}

// ---------------------------------------------------------------- names

pub fn radio_name(r: Radio) -> &'static str {
    ["R1", "R2", "R3"][r.index()]
}

pub fn col_name(c: Col) -> &'static str {
    ["-", "A1", "A2", "A3", "A4", "EXP"][c as usize]
}

fn on_name(on: bool) -> &'static str {
    if on { "on" } else { "off" }
}

/// Column list: `A2,A3` or `-`.
pub struct ColList(pub ColMask);

impl fmt::Display for ColList {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let mut first = true;
        for c in &Col::ALL[1..] {
            if self.0.contains(*c) {
                if !first {
                    f.write_str(",")?;
                }
                f.write_str(col_name(*c))?;
                first = false;
            }
        }
        if first {
            f.write_str("-")?;
        }
        Ok(())
    }
}

/// The command as a host would type it (for host tools and tests).
impl fmt::Display for HostCommand {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match *self {
            HostCommand::Hello => f.write_str("hello"),
            HostCommand::Status => f.write_str("status"),
            HostCommand::ClearFault => f.write_str("clearfault"),
            HostCommand::Route { radio, route } => write!(
                f,
                "route {} {} {}",
                radio_name(radio),
                col_name(route.tx),
                col_name(route.rx)
            ),
            HostCommand::Tx { radio, on } => write!(f, "tx {} {}", radio_name(radio), on_name(on)),
            HostCommand::Key { radio, on } => {
                write!(f, "key {} {}", radio_name(radio), on_name(on))
            }
            HostCommand::Bias(m) => write!(f, "bias {}", ColList(m)),
            HostCommand::Stop(on) => write!(f, "stop {}", on_name(on)),
            HostCommand::Events(on) => write!(f, "events {}", on_name(on)),
        }
    }
}

/// A box link command in host words, for `!refused`.
struct LinkCommand(Command);

impl fmt::Display for LinkCommand {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self.0 {
            Command::Hello { .. } => f.write_str("hello"),
            Command::Poll => f.write_str("poll"),
            Command::SetRoute { radio, route } => HostCommand::Route { radio, route }.fmt(f),
            Command::TxRequest(radio) => HostCommand::Tx { radio, on: true }.fmt(f),
            Command::TxEnd(radio) => HostCommand::Tx { radio, on: false }.fmt(f),
            Command::SetBias(m) => HostCommand::Bias(m).fmt(f),
        }
    }
}

pub fn result_name(r: ResultCode) -> &'static str {
    match r {
        ResultCode::Ok => "ok",
        ResultCode::NotReady => "notready",
        ResultCode::PermitOut => "permitout",
        ResultCode::TxActive => "txactive",
        ResultCode::Hazard => "hazard",
        ResultCode::NoTxRoute => "notxroute",
        ResultCode::BadArg => "badarg",
        ResultCode::Busy => "busy",
        ResultCode::ReadBack => "readback",
        ResultCode::Version => "version",
    }
}

// ---------------------------------------------------------------- events

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TxPhase {
    Idle,
    Requesting,
    Permitted,
    Ending,
    Releasing,
}

impl TxPhase {
    pub fn as_str(self) -> &'static str {
        match self {
            TxPhase::Idle => "idle",
            TxPhase::Requesting => "requesting",
            TxPhase::Permitted => "permitted",
            TxPhase::Ending => "ending",
            TxPhase::Releasing => "releasing",
        }
    }
}

/// Event lines (section 6).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HostEvent {
    Link(bool),
    Expander(bool),
    Fault,
    Safe(bool),
    Latched(bool),
    Kill(bool),
    Band(u8),
    Tx(Radio, TxPhase),
    Permit(Radio, bool),
    Refused(Command, ResultCode),
    PermitLost(Radio),
    TxSenseFault(Radio),
    Route(Radio, Route),
    HostTimeout,
}

impl fmt::Display for HostEvent {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match *self {
            HostEvent::Link(up) => write!(f, "!link {}", if up { "up" } else { "down" }),
            HostEvent::Expander(ok) => {
                write!(f, "!expander {}", if ok { "ready" } else { "lost" })
            }
            HostEvent::Fault => f.write_str("!fault"),
            HostEvent::Safe(ok) => write!(f, "!safe {}", if ok { "ok" } else { "lost" }),
            HostEvent::Latched(v) => write!(f, "!latched {}", v as u8),
            HostEvent::Kill(v) => write!(f, "!kill {}", v as u8),
            HostEvent::Band(b) => write!(f, "!band {b}"),
            HostEvent::Tx(r, p) => write!(f, "!tx {} {}", radio_name(r), p.as_str()),
            HostEvent::Permit(r, on) => write!(f, "!permit {} {}", radio_name(r), on_name(on)),
            HostEvent::Refused(c, r) => write!(f, "!refused {} {}", LinkCommand(c), result_name(r)),
            HostEvent::PermitLost(r) => write!(f, "!permitlost {}", radio_name(r)),
            HostEvent::TxSenseFault(r) => write!(f, "!txsense {} fault", radio_name(r)),
            HostEvent::Route(r, route) => write!(
                f,
                "!route {} {} {}",
                radio_name(r),
                col_name(route.tx),
                col_name(route.rx)
            ),
            HostEvent::HostTimeout => f.write_str("!host timeout"),
        }
    }
}

// ---------------------------------------------------------------- status line

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct RadioStatus {
    /// None: no box status yet.
    pub route: Option<Route>,
    /// None for R1 (no handshake).
    pub tx: Option<TxPhase>,
    pub permit: bool,
    pub key: bool,
}

/// Box part of the status. None: no box status since the link came up.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct BoxPart {
    pub ready: bool,
    pub k1: ColMask,
    pub rfdet: ColMask,
    pub bias: ColMask,
    pub fault: u8,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct StatusLine {
    pub link: bool,
    pub safe_ok: bool,
    pub latched: bool,
    pub kill: bool,
    pub fault: bool,
    pub stop: bool,
    pub band: u8,
    pub boxs: Option<BoxPart>,
    pub radios: [RadioStatus; 3],
}

impl fmt::Display for StatusLine {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let b = |v: bool| v as u8;
        write!(
            f,
            "ok link={} safe={} latched={} kill={} fault={} stop={} band={} box={}",
            if self.link { "up" } else { "down" },
            if self.safe_ok { "ok" } else { "lost" },
            b(self.latched),
            b(self.kill),
            b(self.fault),
            b(self.stop),
            self.band,
            match self.boxs {
                Some(x) if x.ready => "ready",
                Some(_) => "notready",
                None => "?",
            }
        )?;
        for r in Radio::ALL {
            let s = self.radios[r.index()];
            write!(f, " {}=", ["r1", "r2", "r3"][r.index()])?;
            match s.route {
                Some(rt) => write!(f, "{}/{}", col_name(rt.tx), col_name(rt.rx))?,
                None => f.write_str("?/?")?,
            }
            if let Some(p) = s.tx {
                write!(f, ",tx={}", p.as_str())?;
            }
            write!(f, ",permit={},key={}", b(s.permit), b(s.key))?;
        }
        match self.boxs {
            Some(x) => write!(
                f,
                " k1={} rfdet={} bias={} boxfault={}",
                ColList(x.k1),
                ColList(x.rfdet),
                ColList(x.bias),
                x.fault
            ),
            None => f.write_str(" k1=? rfdet=? bias=? boxfault=?"),
        }
    }
}
