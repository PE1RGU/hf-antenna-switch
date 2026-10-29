//! Message types and payload layout (link-protocol.md section 4).
//! Parsing is strict: every value out of range and every reserved bit set is an error.

/// Largest payload (Status).
pub const MAX_PAYLOAD: usize = 12;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Radio {
    R1 = 1,
    R2 = 2,
    R3 = 3,
}

impl Radio {
    pub const ALL: [Radio; 3] = [Radio::R1, Radio::R2, Radio::R3];

    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            1 => Some(Radio::R1),
            2 => Some(Radio::R2),
            3 => Some(Radio::R3),
            _ => None,
        }
    }

    /// 0 for R1, 1 for R2, 2 for R3.
    pub fn index(self) -> usize {
        self as usize - 1
    }
}

/// Antenna column. `None` = no column.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(u8)]
pub enum Col {
    #[default]
    None = 0,
    A1 = 1,
    A2 = 2,
    A3 = 3,
    A4 = 4,
    Exp = 5,
}

impl Col {
    pub const ALL: [Col; 6] = [Col::None, Col::A1, Col::A2, Col::A3, Col::A4, Col::Exp];

    pub fn from_u8(v: u8) -> Option<Self> {
        Col::ALL.get(v as usize).copied()
    }
}

/// One bit per column: bit 0 = A1 ... bit 3 = A4, bit 4 = EXP.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ColMask(u8);

impl ColMask {
    pub const EMPTY: ColMask = ColMask(0);
    const VALID: u8 = 0x1F;

    pub fn from_bits(bits: u8) -> Option<Self> {
        (bits & !Self::VALID == 0).then_some(ColMask(bits))
    }

    pub fn bits(self) -> u8 {
        self.0
    }

    pub fn contains(self, col: Col) -> bool {
        col != Col::None && self.0 & (1 << (col as u8 - 1)) != 0
    }

    pub fn with(self, col: Col) -> Self {
        match col {
            Col::None => self,
            c => ColMask(self.0 | 1 << (c as u8 - 1)),
        }
    }
}

/// TX and RX column of one radio.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Route {
    pub tx: Col,
    pub rx: Col,
}

impl Route {
    fn to_byte(self) -> u8 {
        self.tx as u8 | (self.rx as u8) << 4
    }

    fn from_byte(b: u8) -> Option<Self> {
        Some(Route {
            tx: Col::from_u8(b & 0x0F)?,
            rx: Col::from_u8(b >> 4)?,
        })
    }
}

/// Result of a command (section 4.1).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(u8)]
pub enum ResultCode {
    #[default]
    Ok = 0,
    NotReady = 1,
    PermitOut = 2,
    TxActive = 3,
    Hazard = 4,
    NoTxRoute = 5,
    BadArg = 6,
    Busy = 7,
    ReadBack = 8,
    Version = 9,
}

impl ResultCode {
    pub fn from_u8(v: u8) -> Option<Self> {
        use ResultCode::*;
        [
            Ok, NotReady, PermitOut, TxActive, Hazard, NoTxRoute, BadArg, Busy, ReadBack, Version,
        ]
        .get(v as usize)
        .copied()
    }
}

/// Box fault code (section 4.2). Open list, so a plain number.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct FaultCode(pub u8);

impl FaultCode {
    pub const NONE: FaultCode = FaultCode(0);
    pub const EXPANDER_NACK: FaultCode = FaultCode(1);
    pub const READ_BACK: FaultCode = FaultCode(2);
    pub const BIAS_T: FaultCode = FaultCode(3);
    pub const LINK_TIMEOUT_PERMIT: FaultCode = FaultCode(4);
    pub const SAFE_NOT_CLOSED: FaultCode = FaultCode(5);
}

/// Status byte 1.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Flags {
    pub ready: bool,
    pub kill: bool,
    pub tx_any: bool,
    pub switching: bool,
    pub link_lost_stop: bool,
    pub unit2: bool,
}

impl Flags {
    fn to_byte(self) -> u8 {
        self.ready as u8
            | (self.kill as u8) << 1
            | (self.tx_any as u8) << 2
            | (self.switching as u8) << 3
            | (self.link_lost_stop as u8) << 4
            | (self.unit2 as u8) << 5
    }

    fn from_byte(b: u8) -> Option<Self> {
        (b & 0xC0 == 0).then_some(Flags {
            ready: b & 1 != 0,
            kill: b & 2 != 0,
            tx_any: b & 4 != 0,
            switching: b & 8 != 0,
            link_lost_stop: b & 16 != 0,
            unit2: b & 32 != 0,
        })
    }
}

/// Box state, the answer to every command except Hello.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Status {
    pub result: ResultCode,
    pub flags: Flags,
    pub permit_r2: bool,
    pub permit_r3: bool,
    /// Index with `Radio::index()`.
    pub routes: [Route; 3],
    pub k1: ColMask,
    pub rfdet: ColMask,
    pub bias_en: ColMask,
    pub bias_ok: ColMask,
    pub fault: FaultCode,
}

impl Status {
    pub fn permit(&self, radio: Radio) -> bool {
        match radio {
            Radio::R1 => false,
            Radio::R2 => self.permit_r2,
            Radio::R3 => self.permit_r3,
        }
    }
}

/// HelloReply payload.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct HelloInfo {
    pub version: u8,
    pub fw: [u8; 3],
    pub rx_only: ColMask,
    pub unit2: bool,
}

/// Shack to box.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Command {
    Hello { version: u8 },
    Poll,
    SetRoute { radio: Radio, route: Route },
    TxRequest(Radio),
    TxEnd(Radio),
    SetBias(ColMask),
}

/// Box to shack.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Reply {
    Hello(HelloInfo),
    Status(Status),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ParseError {
    UnknownType,
    Length,
    BadValue,
}

/// A message that fits in one frame.
pub trait Message: Sized {
    /// Write the payload, return the type byte and the payload length.
    fn write(&self, payload: &mut [u8; MAX_PAYLOAD]) -> (u8, usize);
    fn parse(ty: u8, payload: &[u8]) -> Result<Self, ParseError>;
}

mod ty {
    pub const HELLO: u8 = 0x01;
    pub const POLL: u8 = 0x02;
    pub const SET_ROUTE: u8 = 0x10;
    pub const TX_REQUEST: u8 = 0x11;
    pub const TX_END: u8 = 0x12;
    pub const SET_BIAS: u8 = 0x20;
    pub const HELLO_REPLY: u8 = 0x81;
    pub const STATUS: u8 = 0x82;
}

/// Payload length for a type, `None` if the type is unknown.
fn expected_len(t: u8) -> Option<usize> {
    Some(match t {
        ty::POLL => 0,
        ty::HELLO | ty::TX_REQUEST | ty::TX_END | ty::SET_BIAS => 1,
        ty::SET_ROUTE => 3,
        ty::HELLO_REPLY => 6,
        ty::STATUS => 12,
        _ => return None,
    })
}

fn check_len(t: u8, payload: &[u8], allowed: &[u8]) -> Result<(), ParseError> {
    match expected_len(t) {
        Some(n) if allowed.contains(&t) => {
            if payload.len() == n {
                Ok(())
            } else {
                Err(ParseError::Length)
            }
        }
        _ => Err(ParseError::UnknownType),
    }
}

fn radio(b: u8) -> Result<Radio, ParseError> {
    Radio::from_u8(b).ok_or(ParseError::BadValue)
}

fn mask(b: u8) -> Result<ColMask, ParseError> {
    ColMask::from_bits(b).ok_or(ParseError::BadValue)
}

fn col(b: u8) -> Result<Col, ParseError> {
    Col::from_u8(b).ok_or(ParseError::BadValue)
}

impl Message for Command {
    fn write(&self, p: &mut [u8; MAX_PAYLOAD]) -> (u8, usize) {
        match *self {
            Command::Hello { version } => {
                p[0] = version;
                (ty::HELLO, 1)
            }
            Command::Poll => (ty::POLL, 0),
            Command::SetRoute { radio, route } => {
                p[..3].copy_from_slice(&[radio as u8, route.tx as u8, route.rx as u8]);
                (ty::SET_ROUTE, 3)
            }
            Command::TxRequest(r) => {
                p[0] = r as u8;
                (ty::TX_REQUEST, 1)
            }
            Command::TxEnd(r) => {
                p[0] = r as u8;
                (ty::TX_END, 1)
            }
            Command::SetBias(m) => {
                p[0] = m.bits();
                (ty::SET_BIAS, 1)
            }
        }
    }

    fn parse(t: u8, p: &[u8]) -> Result<Self, ParseError> {
        use ty::*;
        check_len(
            t,
            p,
            &[HELLO, POLL, SET_ROUTE, TX_REQUEST, TX_END, SET_BIAS],
        )?;
        Ok(match t {
            HELLO => Command::Hello { version: p[0] },
            POLL => Command::Poll,
            SET_ROUTE => Command::SetRoute {
                radio: radio(p[0])?,
                route: Route {
                    tx: col(p[1])?,
                    rx: col(p[2])?,
                },
            },
            TX_REQUEST => Command::TxRequest(radio(p[0])?),
            TX_END => Command::TxEnd(radio(p[0])?),
            _ => Command::SetBias(mask(p[0])?),
        })
    }
}

impl Message for Reply {
    fn write(&self, p: &mut [u8; MAX_PAYLOAD]) -> (u8, usize) {
        match self {
            Reply::Hello(h) => {
                p[..6].copy_from_slice(&[
                    h.version,
                    h.fw[0],
                    h.fw[1],
                    h.fw[2],
                    h.rx_only.bits(),
                    h.unit2 as u8,
                ]);
                (ty::HELLO_REPLY, 6)
            }
            Reply::Status(s) => {
                *p = [
                    s.result as u8,
                    s.flags.to_byte(),
                    (s.permit_r2 as u8) << 1 | (s.permit_r3 as u8) << 2,
                    s.routes[0].to_byte(),
                    s.routes[1].to_byte(),
                    s.routes[2].to_byte(),
                    s.k1.bits(),
                    s.rfdet.bits(),
                    s.bias_en.bits(),
                    s.bias_ok.bits(),
                    s.fault.0,
                    0,
                ];
                (ty::STATUS, 12)
            }
        }
    }

    fn parse(t: u8, p: &[u8]) -> Result<Self, ParseError> {
        check_len(t, p, &[ty::HELLO_REPLY, ty::STATUS])?;
        let bad = ParseError::BadValue;
        if t == ty::HELLO_REPLY {
            if p[5] > 1 {
                return Err(bad);
            }
            return Ok(Reply::Hello(HelloInfo {
                version: p[0],
                fw: [p[1], p[2], p[3]],
                rx_only: mask(p[4])?,
                unit2: p[5] == 1,
            }));
        }
        if p[2] & !0x06 != 0 || p[11] != 0 {
            return Err(bad);
        }
        let route = |b| Route::from_byte(b).ok_or(bad);
        Ok(Reply::Status(Status {
            result: ResultCode::from_u8(p[0]).ok_or(bad)?,
            flags: Flags::from_byte(p[1]).ok_or(bad)?,
            permit_r2: p[2] & 0x02 != 0,
            permit_r3: p[2] & 0x04 != 0,
            routes: [route(p[3])?, route(p[4])?, route(p[5])?],
            k1: mask(p[6])?,
            rfdet: mask(p[7])?,
            bias_en: mask(p[8])?,
            bias_ok: mask(p[9])?,
            fault: FaultCode(p[10]),
        }))
    }
}
