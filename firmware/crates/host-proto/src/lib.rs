//! Host protocol: Mac or Pi to the shack interface (spec: `docs/design/host-protocol.md`).
//!
//! Text lines. Parsing is not case sensitive. Formatting writes one line without
//! its line end through `core::fmt`, so the caller picks the buffer.
//!
//! ```text
//!  Mac or Pi ==USB serial, text lines==> shack interface --link-proto--> relay box
//!            "route R2 A3 A3"  -> parse() -> HostCommand
//!            "ok" / "err ..."  <- ErrorLine, StatusLine, NamesLine
//!            "!tx R2 permitted" <- HostEvent
//! ```
//!
//! The host asks; the shack interface decides. Nothing in this protocol can
//! clear the SAFE latch, give a permit the box did not report, or key a radio
//! without its permit (D-63, D-71). One protocol serves the Mac and the Pi (D-68).
//!
//! # Line types
//!
//! The first characters of a shack line give its type (section 3):
//! `ok` answer, `err` refused, `!` event, `#` log text. A host ignores all
//! other lines, so boot ROM text on the same USB port does no harm. Every
//! command gets exactly one `ok` or `err` line, in order.
//!
//! # Main parts
//!
//! - [`parse`] turns a host line into a [`HostCommand`], or an [`ErrorCode`].
//! - [`ErrorLine`], [`StatusLine`], [`NamesLine`] and [`HostEvent`] format
//!   the shack lines. They implement `Display`, so `write!` puts them into
//!   any buffer. The caller adds CR LF.
//! - [`HELP`] is the text for `help`.
//!
//! This crate only reads and writes lines. The shack-core crate decides what
//! a command does.
//!
//! The crate is `no_std`: it does not use the Rust standard library, so it
//! runs on the ESP32-C3 without an operating system. It does not allocate
//! memory and does not panic on any input line.
//!
//! # Example
//!
//! ```
//! use host_proto::{parse, ErrorCode, ErrorLine, HostCommand, HostEvent, TxPhase};
//! use link_proto::{Col, Radio, Route};
//!
//! // A host line, as typed in a terminal (Enter sends CR).
//! let cmd = parse("route r2 a3 A3\r").unwrap();
//! assert_eq!(
//!     cmd,
//!     HostCommand::Route {
//!         radio: Radio::R2,
//!         route: Route { tx: Col::A3, rx: Col::A3 },
//!     }
//! );
//!
//! // R1 has no TX handshake: the answer is an error line.
//! let err = parse("tx R1 on").unwrap_err();
//! assert_eq!(err, ErrorCode::NotForR1);
//! assert_eq!(
//!     ErrorLine(err).to_string(),
//!     "err notforr1 R1 uses the hardware PTT loop"
//! );
//!
//! // An event line, sent when the box gives the permit.
//! let ev = HostEvent::Tx(Radio::R2, TxPhase::Permitted);
//! assert_eq!(ev.to_string(), "!tx R2 permitted");
//! ```
#![no_std]

use core::fmt;
use link_proto::{Col, ColMask, Command, Radio, ResultCode, Route};

/// Host protocol version, sent in the `hello` answer (`ok shack fw <x.y.z> proto 1`).
pub const PROTO_VERSION: u8 = 1;
/// Longest host line in characters, without the line end (section 3).
/// Shack lines (the status line) can be longer.
pub const MAX_LINE: usize = 120;
/// Host keep-alive (section 8): default time-out in seconds. It goes back to
/// this value at every power-up. A host app leaves it at 2 s.
pub const KEEP_ALIVE_DEFAULT_S: u8 = 2;
/// Shortest keep-alive time-out allowed by `keepalive`, in seconds.
pub const KEEP_ALIVE_MIN_S: u8 = 2;
/// Longest keep-alive time-out allowed by `keepalive`, in seconds (for typing by hand).
pub const KEEP_ALIVE_MAX_S: u8 = 60;
/// Longest antenna or radio name in characters (fits an antenna box on page B).
pub const NAME_MAX: usize = 8;

/// A name: 1 to NAME_MAX characters from letters, digits and `-._/`.
///
/// Set with the `name` command and stored in flash (section 8a). The value
/// is kept in a fixed array, so it needs no memory allocation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Name {
    len: u8,
    bytes: [u8; NAME_MAX],
}

impl Name {
    /// A name from text. Gives `None` for an empty text, more than
    /// [`NAME_MAX`] characters, or a character that is not allowed.
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

    /// The name as text.
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
    /// R1 to R3.
    Radio(Radio),
}

/// `ok A1=... EXP=... R1=... R3=...` (answer to `names`).
///
/// Example: `ok A1=G5RV A2=Loop A3=spare A4=spare EXP=unit2 R1=FT-710 R2=WSPR R3=spare`.
pub struct NamesLine<'a> {
    /// Names of A1 to A4 and EXP, in that order.
    pub antennas: &'a [Name; 5],
    /// Names of R1 to R3, in that order.
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

/// One host command (host-protocol.md section 5), the result of [`parse`].
///
/// The shack answers each command with one `ok` or `err` line. Commands for
/// the box (`route`, `tx on`, `bias`) answer `ok` when queued; the box result
/// comes later as an event.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HostCommand {
    /// `hello`: identify. Answer `ok shack fw <x.y.z> proto 1`.
    Hello,
    /// `status`: the full state in one line ([`StatusLine`]).
    Status,
    /// `route <radio> <tx col> <rx col>`: route a radio. Sent to the box.
    Route {
        /// The radio to route.
        radio: Radio,
        /// The new TX and RX column; [`Col::None`] for `-`.
        route: Route,
    },
    /// `tx R2|R3 on|off`: ask for the TX permit (handshake, D-63) or end TX.
    /// Never R1: [`parse`] refuses it with [`ErrorCode::NotForR1`].
    Tx {
        /// R2 or R3.
        radio: Radio,
        /// True: ask for the permit. False: end TX (inhibit first, F14).
        on: bool,
    },
    /// `key <radio> on|off`: key a radio through the interface. Works only
    /// while its permit is out; the hardware gates it too (D-71).
    Key {
        /// R1 to R3.
        radio: Radio,
        /// True: key. False: release.
        on: bool,
    },
    /// `bias <column list>`: bias-T feeds on for these columns, off for the rest (D-54).
    Bias(ColMask),
    /// `stop on|off`: software stop. On opens the SAFE loop. Off closes it
    /// again; the SAFE latch still needs RESET.
    Stop(bool),
    /// `clearfault`: clear the shack fault latch after a supervisor reset (P3b-04).
    ClearFault,
    /// `events on|off`: event lines on (default) or off.
    Events(bool),
    /// Keep-alive time-out in seconds, KEEP_ALIVE_MIN_S to KEEP_ALIVE_MAX_S.
    KeepAlive(u8),
    /// `page b|c|auto`: display page.
    Page(PageSel),
    /// `name <column or radio> <text>`: set and store a name.
    Name {
        /// The antenna or radio to name.
        target: NameTarget,
        /// The new name.
        name: Name,
    },
    /// `names`: all names in one line ([`NamesLine`]).
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
    /// The word in commands and in the status line: `b`, `c` or `auto`.
    pub fn as_str(self) -> &'static str {
        match self {
            PageSel::Flow => "b",
            PageSel::Cards => "c",
            PageSel::Auto => "auto",
        }
    }
}

/// Why a command was refused: the code in an `err` line (section 5).
///
/// [`parse`] gives `Syntax`, `Arg`, `NotForR1` and `TooLong`. The shack
/// gives the others when it runs the command.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ErrorCode {
    /// Unknown command or wrong number of words.
    Syntax,
    /// A value out of range (radio, column, on/off, number, name).
    Arg,
    /// The box link is down (`tx on`, `route`, `bias`).
    LinkDown,
    /// `tx` for R1; R1 uses the hardware PTT loop.
    NotForR1,
    /// Route change for a radio that transmits or ends TX (F13).
    TxBusy,
    /// Too many commands wait for the box; try again.
    QueueFull,
    /// Line longer than [`MAX_LINE`] characters.
    TooLong,
    /// `clearfault` while no fault is known.
    NoFault,
}

impl ErrorCode {
    /// The code word in the `err` line, for example `linkdown`.
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

/// `err <code> <text>`, for example `err arg value out of range`.
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
///
/// Words are split at spaces. Keywords and names of radios and columns are
/// not case sensitive. A line with too many words gives
/// [`ErrorCode::Syntax`].
///
/// An empty line gives [`ErrorCode::Syntax`] too. The spec says an empty line
/// gets no answer but counts for the keep-alive, so the caller must handle
/// empty lines before it calls `parse`.
pub fn parse(line: &str) -> Result<HostCommand, ErrorCode> {
    let line = line.strip_suffix('\r').unwrap_or(line);
    if line.len() > MAX_LINE {
        return Err(ErrorCode::TooLong);
    }
    // No command has more than 4 words, so a fixed array is enough.
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
        // The first word is a column (A1 to A4, EXP) or a radio (R1 to R3).
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
///
/// Each entry is the text after `# `.
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

/// Radio name as used in lines: `R1`, `R2`, `R3`.
pub fn radio_name(r: Radio) -> &'static str {
    ["R1", "R2", "R3"][r.index()]
}

/// Column name as used in lines: `A1` to `A4`, `EXP`, or `-` for [`Col::None`].
pub fn col_name(c: Col) -> &'static str {
    ["-", "A1", "A2", "A3", "A4", "EXP"][c as usize]
}

fn on_name(on: bool) -> &'static str {
    if on { "on" } else { "off" }
}

/// Column list: `A2,A3` or `-`. Formats a [`ColMask`] for lines.
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
            Command::ClearFault => HostCommand::ClearFault.fmt(f),
        }
    }
}

/// Box result code in lower case, as in `!refused` (link-protocol.md section 4.1).
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

/// TX handshake state of R2 or R3 (link-protocol.md section 5.1), as in
/// `!tx <radio> <state>` and in the status line.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TxPhase {
    /// No TX. TX INH is on.
    Idle,
    /// TxRequest sent; waiting for the permit bit from the box.
    Requesting,
    /// The box reported the permit; PERMIT is on and the radio may transmit.
    Permitted,
    /// TX end: PERMIT and KEY are off (inhibit first); waiting for TX sense
    /// inactive and at least 100 ms (F14).
    Ending,
    /// TxEnd sent; waiting for the box to release K0.
    Releasing,
}

impl TxPhase {
    /// The state word, for example `permitted`.
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

/// Event lines (section 6). Sent on every change, when events are on.
///
/// `Display` writes the line, for example `!link up`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HostEvent {
    /// `!link up` / `!link down`: box link state (link-protocol.md section 6).
    Link(bool),
    /// `!expander ready` / `!expander lost`: shack expander set up, or lost
    /// (all permits dropped).
    Expander(bool),
    /// `!fault`: a supervisor reset was seen after start-up. TX stays blocked
    /// until `clearfault`.
    Fault,
    /// `!safe ok` / `!safe lost`: SAFE loop current (GPIO21).
    Safe(bool),
    /// `!latched 1` / `!latched 0`: SAFE latch (expander input).
    Latched(bool),
    /// `!kill 1` / `!kill 0`: KILL switch pressed or released.
    Kill(bool),
    /// `!band <n>`: R1 band data changed. 0 to 15, FT-710 BAND D C B A as a
    /// 4-bit number (D-86). The host decodes it to metres.
    Band(u8),
    /// `!tx <radio> <state>`: TX handshake state of R2 or R3 changed.
    Tx(Radio, TxPhase),
    /// `!permit <radio> on|off`: a PERMIT line changed (all radios, R1 included).
    Permit(Radio, bool),
    /// `!refused <command words> <result>`: the box refused a command.
    Refused(Command, ResultCode),
    /// `!permitlost <radio>`: the box dropped a permit in use.
    PermitLost(Radio),
    /// `!txsense <radio> fault`: keyed with permit for 500 ms without TX sense (F14, C-3).
    TxSenseFault(Radio),
    /// `!txsense <radio> nopermit`: the radio transmits without its permit (F15).
    TxWithoutPermit(Radio),
    /// `!route <radio> <tx col> <rx col>`: route as read back from the box.
    Route(Radio, Route),
    /// `!host timeout`: host keep-alive missed; every TX ended and every key
    /// released (section 8).
    HostTimeout,
    /// `!selftest pass` / `!selftest fail <item>`: the power-up self-test ended.
    /// After a fail the shack never gives its LATCH_CLR edge: TX stays blocked
    /// until a power cycle.
    SelfTest(SelfTestState),
    /// `!selftest warn <item>`: something unexpected at start-up; TX is not blocked.
    SelfTestWarn(SelfTestItem),
}

/// What the power-up self-test checks (host-protocol.md section 6).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SelfTestItem {
    /// `expander`: the PCA9539 did not answer, or did not come back after the
    /// watchdog test.
    Expander,
    /// `latch`: the SAFE latch was not set at power-up.
    Latch,
    /// `watchdog`: the supervisor did not trip when the WDI kicks stopped, or
    /// tripped too early.
    Watchdog,
    /// `txsense <radio>`: TX sense active at start-up (warning).
    TxSense(Radio),
    /// `i2c <address>`: a DevKit part (SHTC3 0x70, IMU 0x68) did not answer (warning).
    I2c(u8),
}

impl fmt::Display for SelfTestItem {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match *self {
            SelfTestItem::Expander => f.write_str("expander"),
            SelfTestItem::Latch => f.write_str("latch"),
            SelfTestItem::Watchdog => f.write_str("watchdog"),
            SelfTestItem::TxSense(r) => write!(f, "txsense {}", radio_name(r)),
            SelfTestItem::I2c(a) => write!(f, "i2c {a:#04x}"),
        }
    }
}

/// State of the power-up self-test (`selftest=` in the status line).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum SelfTestState {
    /// `running`: not done yet. TX stays blocked.
    #[default]
    Running,
    /// `pass`.
    Pass,
    /// `fail <item>` (`fail-<item>` in the status line). TX stays blocked until a
    /// power cycle.
    Fail(SelfTestItem),
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
            HostEvent::TxWithoutPermit(r) => write!(f, "!txsense {} nopermit", radio_name(r)),
            HostEvent::Route(r, route) => write!(
                f,
                "!route {} {} {}",
                radio_name(r),
                col_name(route.tx),
                col_name(route.rx)
            ),
            HostEvent::HostTimeout => f.write_str("!host timeout"),
            HostEvent::SelfTest(SelfTestState::Fail(i)) => write!(f, "!selftest fail {i}"),
            HostEvent::SelfTest(SelfTestState::Pass) => f.write_str("!selftest pass"),
            HostEvent::SelfTest(SelfTestState::Running) => f.write_str("!selftest running"),
            HostEvent::SelfTestWarn(i) => write!(f, "!selftest warn {i}"),
        }
    }
}

// ---------------------------------------------------------------- status line

/// One radio in the status line: `r2=A3/A3,tx=permitted,permit=1,key=1`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct RadioStatus {
    /// None: no box status yet (written `?/?`).
    pub route: Option<Route>,
    /// None for R1 (no handshake).
    pub tx: Option<TxPhase>,
    /// The PERMIT line of this radio is on.
    pub permit: bool,
    /// The interface keys this radio.
    pub key: bool,
}

/// Box part of the status: values from the last box [`Status`](link_proto::Status).
/// [`StatusLine::boxs`] is `None` when no box status came since the link came up.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct BoxPart {
    /// The box READY flag (`box=ready` or `box=notready`).
    pub ready: bool,
    /// Columns with K1 on (`k1=`).
    pub k1: ColMask,
    /// Columns with RF detected (`rfdet=`).
    pub rfdet: ColMask,
    /// Columns with the bias-T feed on (`bias=`).
    pub bias: ColMask,
    /// Last box fault code (`boxfault=`), link-protocol.md section 4.2. 0 = none.
    pub fault: u8,
}

/// The answer to `status`: one line of `key=value` pairs (section 7).
///
/// ```text
/// ok link=up safe=ok latched=0 kill=0 fault=0 stop=0 keepalive=2 page=b band=5 box=ready
///    r1=A1/A1,permit=1,key=0 r2=A3/A3,tx=permitted,permit=1,key=1 r3=-/-,tx=idle,permit=0,key=0
///    k1=A1,A3 rfdet=- bias=- boxfault=0
/// ```
///
/// One line on the wire (wrapped here), about 200 characters. Unknown values
/// read `?`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct StatusLine {
    /// Box link up (`link=up`).
    pub link: bool,
    /// SAFE loop current present (`safe=ok`).
    pub safe_ok: bool,
    /// SAFE latch set: TX inhibited until RESET (`latched=1`).
    pub latched: bool,
    /// KILL switch pressed (`kill=1`).
    pub kill: bool,
    /// Shack fault latch: a supervisor reset was seen (`fault=1`, see `clearfault`).
    pub fault: bool,
    /// Software stop on (`stop=1`).
    pub stop: bool,
    /// Keep-alive time-out in seconds.
    pub keepalive: u8,
    /// Display page (`page=`).
    pub page: PageSel,
    /// R1 band data, 0 to 15 (D-86).
    pub band: u8,
    /// Box values. None: no box status since the link came up (`box=?`).
    pub boxs: Option<BoxPart>,
    /// R1, R2, R3. Index with [`Radio::index`].
    pub radios: [RadioStatus; 3],
    /// Power-up self-test (`selftest=running`, `pass` or `fail-<item>`).
    pub selftest: SelfTestState,
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
        }?;
        match self.selftest {
            SelfTestState::Running => f.write_str(" selftest=running"),
            SelfTestState::Pass => f.write_str(" selftest=pass"),
            SelfTestState::Fail(i) => write!(f, " selftest=fail-{i}"),
        }
    }
}
