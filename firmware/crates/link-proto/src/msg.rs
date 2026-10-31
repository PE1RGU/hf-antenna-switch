//! Message types and payload layout (link-protocol.md section 4).
//!
//! [`Command`] goes from the shack to the box. [`Reply`] goes from the box to
//! the shack: a [`HelloInfo`] for Hello, a [`Status`] for every other command.
//! Both implement [`Message`], which [`Frame`](crate::Frame) uses to write and
//! read the payload.
//!
//! Parsing is strict: every value out of range and every reserved bit set is an error.

/// Largest payload in bytes (Status, 12 bytes).
pub const MAX_PAYLOAD: usize = 12;

/// One of the three radio ports of the box. The number is the value on the wire.
///
/// R1 is the FT-710. It keys through the hardware PTT loop (pair 2), so it has
/// no TX handshake on the link. R2 and R3 use the handshake (D-63).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Radio {
    /// Radio port 1 (FT-710, hardware PTT loop).
    R1 = 1,
    /// Radio port 2 (TX by handshake).
    R2 = 2,
    /// Radio port 3 (TX by handshake).
    R3 = 3,
}

impl Radio {
    /// All radios in port order. Useful to loop over the ports.
    pub const ALL: [Radio; 3] = [Radio::R1, Radio::R2, Radio::R3];

    /// The radio for a wire value 1 to 3. Other values give `None`.
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            1 => Some(Radio::R1),
            2 => Some(Radio::R2),
            3 => Some(Radio::R3),
            _ => None,
        }
    }

    /// Array index: 0 for R1, 1 for R2, 2 for R3.
    pub fn index(self) -> usize {
        self as usize - 1
    }
}

/// Antenna column of the relay crossbar. `None` = no column.
///
/// The number is the value on the wire: 0 = none, 1 to 4 = A1 to A4,
/// 5 = EXP (the column to the expansion unit, unit 2).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(u8)]
pub enum Col {
    /// No column: the radio row is not connected.
    #[default]
    None = 0,
    /// Antenna port A1.
    A1 = 1,
    /// Antenna port A2. On unit 1 this is receive-only (D-103).
    A2 = 2,
    /// Antenna port A3.
    A3 = 3,
    /// Antenna port A4.
    A4 = 4,
    /// Expansion column to unit 2.
    Exp = 5,
}

impl Col {
    /// All values in wire order, `None` first. `ALL[1..]` gives the real columns.
    pub const ALL: [Col; 6] = [Col::None, Col::A1, Col::A2, Col::A3, Col::A4, Col::Exp];

    /// The column for a wire value 0 to 5. Other values give `None` (the
    /// `Option`, not [`Col::None`]).
    pub fn from_u8(v: u8) -> Option<Self> {
        Col::ALL.get(v as usize).copied()
    }
}

/// A set of columns, one bit per column: bit 0 = A1 ... bit 3 = A4, bit 4 = EXP.
///
/// Used for the bias-T feeds, the K1 relays, the RF detectors and the
/// receive-only columns. Bits 5 to 7 are reserved and always 0.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ColMask(u8);

impl ColMask {
    /// No column.
    pub const EMPTY: ColMask = ColMask(0);
    const VALID: u8 = 0x1F;

    /// The mask for a wire byte. A reserved bit (5 to 7) set gives `None`.
    pub fn from_bits(bits: u8) -> Option<Self> {
        (bits & !Self::VALID == 0).then_some(ColMask(bits))
    }

    /// The wire byte.
    pub fn bits(self) -> u8 {
        self.0
    }

    /// True if the column is in the set. Always false for [`Col::None`].
    pub fn contains(self, col: Col) -> bool {
        col != Col::None && self.0 & (1 << (col as u8 - 1)) != 0
    }

    /// The set with this column added. [`Col::None`] adds nothing.
    pub fn with(self, col: Col) -> Self {
        match col {
            Col::None => self,
            c => ColMask(self.0 | 1 << (c as u8 - 1)),
        }
    }
}

/// TX and RX column of one radio.
///
/// The TX column is the antenna that K0 connects in TX (the TX row); the RX
/// column is the antenna in receive (the RX row, K0 off). On the wire in a
/// Status, one byte: low nibble TX, high nibble RX.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Route {
    /// Column for transmit.
    pub tx: Col,
    /// Column for receive.
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

/// Result of a command, byte 0 of the Status (section 4.1).
///
/// The box sends the result of the command with the same seq. For a Poll the
/// result is normally `Ok`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(u8)]
pub enum ResultCode {
    /// Done, or accepted and running (see the SWITCHING flag and the permits).
    #[default]
    Ok = 0,
    /// The box is not READY, or KILL is 1.
    NotReady = 1,
    /// The radio has a permit out; its K0 and rows do not change (F13).
    PermitOut = 2,
    /// TX_ANY is 1; no relay moves under RF.
    TxActive = 3,
    /// The new state breaks one of the hazard rules H1 to H4 (F6).
    Hazard = 4,
    /// TxRequest for a radio without a TX column, or with its K1 off (H4).
    NoTxRoute = 5,
    /// A value out of range, or TxRequest / TxEnd for R1 (R1 uses the PTT loop).
    BadArg = 6,
    /// A switching sequence is running.
    Busy = 7,
    /// The read-back from the expanders differs from the written state.
    ReadBack = 8,
    /// The box does not support the Hello version.
    Version = 9,
}

impl ResultCode {
    /// The result for a wire value 0 to 9. Other values give `None`.
    pub fn from_u8(v: u8) -> Option<Self> {
        use ResultCode::*;
        [
            Ok, NotReady, PermitOut, TxActive, Hazard, NoTxRoute, BadArg, Busy, ReadBack, Version,
        ]
        .get(v as usize)
        .copied()
    }
}

/// Box fault code, byte 10 of the Status (section 4.2). The last fault the box saw.
///
/// The list stays open: the box firmware adds codes. So this is a plain
/// number with named constants, not an enum, and every value parses.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct FaultCode(pub u8);

impl FaultCode {
    /// No fault.
    pub const NONE: FaultCode = FaultCode(0);
    /// An I/O expander did not acknowledge on I2C.
    pub const EXPANDER_NACK: FaultCode = FaultCode(1);
    /// The expander read-back differs from the written state.
    pub const READ_BACK: FaultCode = FaultCode(2);
    /// Bias-T fault: a feed has EN = 1 and OK = 0 (D-54).
    pub const BIAS_T: FaultCode = FaultCode(3);
    /// Link time-out while a permit was out: the box opened SAFE (F13).
    pub const LINK_TIMEOUT_PERMIT: FaultCode = FaultCode(4);
    /// The SAFE loop did not close at start-up (F11).
    pub const SAFE_NOT_CLOSED: FaultCode = FaultCode(5);
    /// Link time-out with no permit out: the box holds the routes (P-02).
    pub const LINK_TIMEOUT: FaultCode = FaultCode(6);
}

/// Status byte 1: the box state flags. Bits 6 and 7 are reserved and always 0.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Flags {
    /// Bit 0, READY: MCU_EN_N = 0 and FAULT = 0. The box may switch relays.
    pub ready: bool,
    /// Bit 1, KILL: the SAFE loop is open, so the relays are off in hardware.
    pub kill: bool,
    /// Bit 2, TX_ANY: a radio transmits (read back on U903 IO1_5).
    pub tx_any: bool,
    /// Bit 3, SWITCHING: a switching sequence is running.
    pub switching: bool,
    /// Bit 4, LINK_LOST_STOP: the box opened SAFE after a link time-out (F13).
    pub link_lost_stop: bool,
    /// Bit 5: unit 2 (the expansion unit) is present.
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

/// Box state, the answer to every command except Hello (12 bytes, section 4).
///
/// All values are read back from the hardware, not copied from the commands.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Status {
    /// Result of the command with this seq.
    pub result: ResultCode,
    /// State flags (byte 1).
    pub flags: Flags,
    /// R2 permit: K0 of R2 is in TX, settled and read back (D-63).
    /// Only then may the shack release TX INH of R2.
    pub permit_r2: bool,
    /// R3 permit, as for R2.
    pub permit_r3: bool,
    /// Route of R1, R2, R3 as read back from the expanders.
    /// Index with [`Radio::index`].
    pub routes: [Route; 3],
    /// Columns with K1 on (antenna connected to the crossbar).
    pub k1: ColMask,
    /// Columns where the RF detector sees RF (D-47).
    pub rfdet: ColMask,
    /// Columns with the bias-T feed switched on (D-54).
    pub bias_en: ColMask,
    /// Columns with the bias-T output good. A feed with EN = 1 and OK = 0 is a fault (D-54).
    pub bias_ok: ColMask,
    /// Last box fault, [`FaultCode::NONE`] if none.
    pub fault: FaultCode,
}

impl Status {
    /// The permit bit of a radio. Always false for R1: R1 has no handshake
    /// and no permit bit on the link.
    pub fn permit(&self, radio: Radio) -> bool {
        match radio {
            Radio::R1 => false,
            Radio::R2 => self.permit_r2,
            Radio::R3 => self.permit_r3,
        }
    }
}

/// HelloReply payload (6 bytes): who the box is.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct HelloInfo {
    /// Protocol version of the box. Must equal [`VERSION`](crate::VERSION).
    pub version: u8,
    /// Box firmware version: major, minor, patch.
    pub fw: [u8; 3],
    /// Receive-only columns of this box. Must match the shack table
    /// (unit 1: A2, D-103).
    pub rx_only: ColMask,
    /// Unit 2 (the expansion unit) is present.
    pub unit2: bool,
}

/// Shack to box. Every command sets a state, not a step, so a command sent
/// twice gives the same result (section 5).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Command {
    /// Start the link. Also clears the box seq store (section 5).
    Hello {
        /// Protocol version of the shack, [`VERSION`](crate::VERSION).
        version: u8,
    },
    /// No command: ask for the box status. The shack sends it every
    /// [`POLL_PERIOD`](crate::POLL_PERIOD) when it has nothing else to send.
    Poll,
    /// Set the TX and RX column of a radio.
    SetRoute {
        /// The radio to route.
        radio: Radio,
        /// The new TX and RX column.
        route: Route,
    },
    /// Ask for the TX permit of R2 or R3 (D-63, section 5.1). The box sets K0,
    /// waits 12 ms, reads back, then sets the permit bit.
    TxRequest(Radio),
    /// End TX of R2 or R3: the box releases K0 and clears the permit bit.
    /// The shack sends it only after the inhibit and the F14 wait.
    TxEnd(Radio),
    /// Bias-T feeds on for these columns, off for the rest (D-54).
    SetBias(ColMask),
}

/// Box to shack.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Reply {
    /// HelloReply: the answer to Hello.
    Hello(HelloInfo),
    /// The answer to every other command.
    Status(Status),
}

/// Why a payload did not parse. [`Frame::decode_raw`](crate::Frame::decode_raw)
/// turns it into a [`DecodeError`](crate::DecodeError).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ParseError {
    /// The type byte is not a known type for this direction.
    UnknownType,
    /// The payload length does not match the type.
    Length,
    /// A value is out of range or a reserved bit is set.
    BadValue,
}

/// A message that fits in one frame. [`Command`] and [`Reply`] implement it.
///
/// A trait is a set of functions that more than one type can have. Here it
/// lets one [`Frame`](crate::Frame) and one [`Decoder`](crate::Decoder) work
/// for both directions.
pub trait Message: Sized {
    /// Write the payload, return the type byte and the payload length.
    fn write(&self, payload: &mut [u8; MAX_PAYLOAD]) -> (u8, usize);
    /// Read a message from its type byte and payload. Strict: see [`ParseError`].
    fn parse(ty: u8, payload: &[u8]) -> Result<Self, ParseError>;
}

/// Type bytes (section 4). 0x30 to 0x3F are reserved for a firmware update
/// over the link (P-04, not in v1).
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

/// Check the type against the types `allowed` in this direction, then the
/// length. A known type from the other direction counts as unknown here.
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
        // Type and length are good from here, so the indexes below are safe.
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
            // Unit 2 byte: 0 or 1 only.
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
        // Permits byte: only bits 1 (R2) and 2 (R3). Byte 11 is reserved.
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
