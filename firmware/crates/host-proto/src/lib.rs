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
/// Host keep-alive (section 8): default and allowed range in seconds.
pub const KEEP_ALIVE_DEFAULT_S: u8 = 2;
pub const KEEP_ALIVE_MIN_S: u8 = 2;
pub const KEEP_ALIVE_MAX_S: u8 = 60;
/// Longest antenna or radio name (fits an antenna box on page B).
pub const NAME_MAX: usize = 8;

/// A name: 1 to NAME_MAX characters from letters, digits and `-._/`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Name {
    len: u8,
    bytes: [u8; NAME_MAX],
}

impl Name {
    pub fn new(s: &str) -> Option<Self> {
        let ok = |c: u8| c.is_ascii_alphanumeric() || b"-._/".contains(&c);
        if s.is_empty() || s.len() > NAME_MAX || !s.bytes().all(ok) {
            return None;
        }
        let mut bytes = [0; NAME_MAX];
        bytes[..s.len()].copy_from_slice(s.as_bytes());
        Some(Name {
            len: s.len() as u8,
            bytes,
        })
    }

    pub fn as_str(&self) -> &str {
        // Only ASCII is accepted by `new`.
        core::str::from_utf8(&self.bytes[..self.len as usize]).unwrap_or("?")
    }
}

/// `-` (no name).
impl Default for Name {
    fn default() -> Self {
        let mut bytes = [0; NAME_MAX];
        bytes[0] = b'-';
        Name { len: 1, bytes }
    }
}

impl fmt::Display for Name {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// What a `name` command names.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NameTarget {
    /// A1 to A4 or EXP (never `Col::None`).
    Antenna(Col),
    Radio(Radio),
}

/// `ok A1=... EXP=... R1=... R3=...` (answer to `names`).
pub struct NamesLine<'a> {
    pub antennas: &'a [Name; 5],
    pub radios: &'a [Name; 3],
}

impl fmt::Display for NamesLine<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("ok")?;
        for (c, n) in Col::ALL[1..].iter().zip(self.antennas) {
            write!(f, " {}={n}", col_name(*c))?;
        }
        for (r, n) in Radio::ALL.iter().zip(self.radios) {
            write!(f, " {}={n}", radio_name(*r))?;
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HostCommand {
    Hello,
    Status,
    Route {
        radio: Radio,
        route: Route,
    },
    Tx {
        radio: Radio,
        on: bool,
    },
    Key {
        radio: Radio,
        on: bool,
    },
    Bias(ColMask),
    Stop(bool),
    ClearFault,
    Events(bool),
    /// Keep-alive time-out in seconds, KEEP_ALIVE_MIN_S to KEEP_ALIVE_MAX_S.
    KeepAlive(u8),
    Page(PageSel),
    Name {
        target: NameTarget,
        name: Name,
    },
    Names,
    /// `help` or `?`.
    Help,
}

/// Display page selection (`page` command).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum PageSel {
    /// B: flow.
    #[default]
    Flow,
    /// C: cards.
    Cards,
    /// B 10 s, C 5 s.
    Auto,
}

impl PageSel {
    pub fn as_str(self) -> &'static str {
        match self {
            PageSel::Flow => "b",
            PageSel::Cards => "c",
            PageSel::Auto => "auto",
        }
    }
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
    } else if is("help", 1) || is("?", 1) {
        Ok(HostCommand::Help)
    } else if is("names", 1) {
        Ok(HostCommand::Names)
    } else if is("name", 3) {
        let target = match col(w[1]) {
            Ok(Col::None) => return Err(ErrorCode::Arg),
            Ok(c) => NameTarget::Antenna(c),
            Err(_) => NameTarget::Radio(radio(w[1])?),
        };
        let name = Name::new(w[2]).ok_or(ErrorCode::Arg)?;
        Ok(HostCommand::Name { target, name })
    } else if is("page", 2) {
        [PageSel::Flow, PageSel::Cards, PageSel::Auto]
            .into_iter()
            .find(|p| eq(w[1], p.as_str()))
            .map(HostCommand::Page)
            .ok_or(ErrorCode::Arg)
    } else if is("keepalive", 2) {
        let s: u8 = w[1].parse().map_err(|_| ErrorCode::Arg)?;
        if !(KEEP_ALIVE_MIN_S..=KEEP_ALIVE_MAX_S).contains(&s) {
            return Err(ErrorCode::Arg);
        }
        Ok(HostCommand::KeepAlive(s))
    } else if is("events", 2) {
        Ok(HostCommand::Events(on_off(w[1])?))
    } else {
        Err(ErrorCode::Syntax)
    }
}

/// Answer to `help`: one `#` line each, then `ok`.
pub const HELP: [&str; 14] = [
    "hello                      identify",
    "status                     full state, one line",
    "route R1-R3 <tx> <rx>      route a radio; columns A1-A4, EXP, - (none)",
    "tx R2|R3 on|off            ask for the TX permit, or end TX",
    "key R1-R3 on|off           key a radio (only with its permit)",
    "bias <A2,A3 | ->           bias-T feeds on these columns",
    "stop on|off                software stop: opens the SAFE loop",
    "clearfault                 clear the fault latch after a supervisor reset",
    "page b|c|auto              display page: flow, cards, or both in turn",
    "name A1-A4|EXP|R1-R3 <x>   set a name, 1-8 characters",
    "names                      show all names",
    "keepalive 2-60             host keep-alive time-out in seconds",
    "events on|off              events on or off",
    "help | ?                   this list",
];

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
            HostCommand::KeepAlive(s) => write!(f, "keepalive {s}"),
            HostCommand::Page(p) => write!(f, "page {}", p.as_str()),
            HostCommand::Names => f.write_str("names"),
            HostCommand::Help => f.write_str("help"),
            HostCommand::Name { target, name } => match target {
                NameTarget::Antenna(c) => write!(f, "name {} {name}", col_name(c)),
                NameTarget::Radio(r) => write!(f, "name {} {name}", radio_name(r)),
            },
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
    /// Keep-alive time-out in seconds.
    pub keepalive: u8,
    pub page: PageSel,
    pub band: u8,
    pub boxs: Option<BoxPart>,
    pub radios: [RadioStatus; 3],
}

impl fmt::Display for StatusLine {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let b = |v: bool| v as u8;
        write!(
            f,
            "ok link={} safe={} latched={} kill={} fault={} stop={} keepalive={} page={} band={} box={}",
            if self.link { "up" } else { "down" },
            if self.safe_ok { "ok" } else { "lost" },
            b(self.latched),
            b(self.kill),
            b(self.fault),
            b(self.stop),
            self.keepalive,
            self.page.as_str(),
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
