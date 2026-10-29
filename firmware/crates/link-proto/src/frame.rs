//! Frame layout (link-protocol.md section 3):
//! `COBS( seq | type | payload | crc16 ) | 0x00`, CRC-16/CCITT-FALSE high byte first.
//!
//! - **seq**: sequence number. The shack sets it; the box copies it into the answer.
//! - **type**: message type (section 4).
//! - **payload**: 0 to 12 bytes, fixed length per type.
//! - **crc16**: CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection,
//!   no final XOR) over seq, type and payload.
//!
//! COBS (Consistent Overhead Byte Stuffing) removes every 0x00 from the frame,
//! for a cost of one byte. So a 0x00 on the line can only be the delimiter at
//! the end of a frame. After any error, the receiver starts again at the next
//! 0x00. A break (cable cut, box dead) reads as 0x00 bytes, so it also only
//! ends a frame.
//!
//! The CRC-16 finds all 1, 2 and 3 bit errors and all bursts up to 16 bits in
//! these short frames. The cable is unshielded and buried (D-57).

use crate::cobs;
use crate::msg::{MAX_PAYLOAD, Message, ParseError};

/// Largest frame before COBS, in bytes: seq + type + payload + crc (16).
pub const MAX_RAW: usize = 2 + MAX_PAYLOAD + 2;
/// COBS adds one byte below 254 bytes.
const MAX_COBS: usize = MAX_RAW + 1;
/// Largest frame on the wire, with the delimiter, in bytes (18: a Status).
/// Use it as the size of the buffer for [`Frame::encode`].
pub const MAX_WIRE: usize = MAX_COBS + 1;

/// CRC-16/CCITT-FALSE is named CRC-16/IBM-3740 in the CRC catalogue.
const CRC: crc::Crc<u16> = crc::Crc::<u16>::new(&crc::CRC_16_IBM_3740);

/// One message with its sequence number.
///
/// `M` is the message type: [`Command`](crate::Command) from the shack, or
/// [`Reply`](crate::Reply) from the box. Rust calls this a generic type: the
/// same code works for both.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Frame<M> {
    /// Sequence number. The shack adds 1 for each new command (it wraps after
    /// 255); a resend keeps the seq. The box answers with the same seq.
    pub seq: u8,
    /// The message.
    pub msg: M,
}

/// Why a received frame was not accepted.
///
/// The checks run in the order of section 3. On every error except
/// [`BadValue`](DecodeError::BadValue) the receiver drops the frame and says
/// nothing; the time-outs catch a lost link.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DecodeError {
    /// More bytes than [`MAX_WIRE`] before the delimiter.
    TooLong,
    /// The COBS encoding is not valid.
    Cobs,
    /// Fewer than 4 bytes after COBS: no room for seq, type and CRC.
    TooShort,
    /// The CRC does not match: the frame was damaged on the line.
    Crc,
    /// The type byte is not known in this direction.
    UnknownType,
    /// The payload length does not match the type.
    Length,
    /// CRC good, but a value is out of range. The box answers BadArg to this seq.
    BadValue {
        /// The seq of the frame, for the BadArg answer.
        seq: u8,
    },
}

impl<M: Message> Frame<M> {
    /// Write the frame with its delimiter into `out`, return the number of bytes.
    ///
    /// Send `out[..n]` on the UART. A frame is 6 (Poll) to 18 (Status) bytes.
    pub fn encode(&self, out: &mut [u8; MAX_WIRE]) -> usize {
        let mut payload = [0u8; MAX_PAYLOAD];
        let (ty, n) = self.msg.write(&mut payload);
        let mut raw = [0u8; MAX_RAW];
        raw[0] = self.seq;
        raw[1] = ty;
        raw[2..2 + n].copy_from_slice(&payload[..n]);
        let crc = CRC.checksum(&raw[..2 + n]);
        raw[2 + n..4 + n].copy_from_slice(&crc.to_be_bytes());
        let len = cobs::encode(&raw[..4 + n], &mut out[..MAX_COBS]);
        out[len] = 0;
        len + 1
    }

    /// Check and parse one frame after COBS decoding (without the delimiter).
    ///
    /// Checks the length, the CRC, the type and the payload. Normally you do
    /// not call this yourself: [`Decoder::push`] does it.
    pub fn decode_raw(raw: &[u8]) -> Result<Self, DecodeError> {
        if raw.len() < 4 {
            return Err(DecodeError::TooShort);
        }
        let (body, crc) = raw.split_at(raw.len() - 2);
        if CRC.checksum(body).to_be_bytes() != crc {
            return Err(DecodeError::Crc);
        }
        let seq = body[0];
        M::parse(body[1], &body[2..])
            .map(|msg| Frame { seq, msg })
            .map_err(|e| match e {
                ParseError::UnknownType => DecodeError::UnknownType,
                ParseError::Length => DecodeError::Length,
                ParseError::BadValue => DecodeError::BadValue { seq },
            })
    }
}

/// Streaming decoder: feed it the UART bytes one at a time.
///
/// It collects bytes until a 0x00 delimiter, then decodes the frame. It needs
/// no time-out of its own: a frame cut short by a break ends at the next 0x00
/// and fails the COBS, length or CRC check.
#[derive(Debug, Default)]
pub struct Decoder {
    buf: [u8; MAX_COBS],
    len: usize,
    overflow: bool,
}

impl Decoder {
    /// An empty decoder.
    pub fn new() -> Self {
        Self::default()
    }

    /// Add one received byte.
    ///
    /// Returns a result at each delimiter, `None` for all other bytes. Empty
    /// frames (a break reads as zero bytes) give nothing. `M` is the message
    /// type to expect: the box uses `push::<Command>`, the shack
    /// `push::<Reply>`.
    pub fn push<M: Message>(&mut self, byte: u8) -> Option<Result<Frame<M>, DecodeError>> {
        if byte != 0 {
            // Keep the byte. On overflow, drop the rest of the frame and
            // report TooLong at the delimiter.
            if self.len < self.buf.len() {
                self.buf[self.len] = byte;
                self.len += 1;
            } else {
                self.overflow = true;
            }
            return None;
        }
        let len = core::mem::take(&mut self.len);
        if core::mem::take(&mut self.overflow) {
            return Some(Err(DecodeError::TooLong));
        }
        if len == 0 {
            return None;
        }
        let mut raw = [0u8; MAX_RAW];
        Some(match cobs::decode(&self.buf[..len], &mut raw) {
            Ok(n) => Frame::decode_raw(&raw[..n]),
            Err(()) => Err(DecodeError::Cobs),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::msg::Command;

    #[test]
    fn crc_check_value() {
        assert_eq!(CRC.checksum(b"123456789"), 0x29B1);
    }

    #[test]
    fn poll_on_the_wire() {
        // seq 0x05, type 0x02, CRC over [05 02], COBS, delimiter: 6 bytes (section 4).
        let mut out = [0u8; MAX_WIRE];
        let n = Frame {
            seq: 5,
            msg: Command::Poll,
        }
        .encode(&mut out);
        let crc = CRC.checksum(&[5, 2]).to_be_bytes();
        assert_eq!(n, 6);
        assert_eq!(out[..n], [5, 5, 2, crc[0], crc[1], 0]);
    }
}
