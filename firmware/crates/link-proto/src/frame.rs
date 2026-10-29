//! Frame layout (link-protocol.md section 3):
//! `COBS( seq | type | payload | crc16 ) | 0x00`, CRC-16/CCITT-FALSE high byte first.

use crate::cobs;
use crate::msg::{MAX_PAYLOAD, Message, ParseError};

/// seq + type + payload + crc.
pub const MAX_RAW: usize = 2 + MAX_PAYLOAD + 2;
/// COBS adds one byte below 254 bytes.
const MAX_COBS: usize = MAX_RAW + 1;
/// Largest frame on the wire, with the delimiter.
pub const MAX_WIRE: usize = MAX_COBS + 1;

/// CRC-16/CCITT-FALSE is named CRC-16/IBM-3740 in the CRC catalogue.
const CRC: crc::Crc<u16> = crc::Crc::<u16>::new(&crc::CRC_16_IBM_3740);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Frame<M> {
    pub seq: u8,
    pub msg: M,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DecodeError {
    TooLong,
    Cobs,
    TooShort,
    Crc,
    UnknownType,
    Length,
    /// CRC good, but a value is out of range. The box answers BadArg to this seq.
    BadValue {
        seq: u8,
    },
}

impl<M: Message> Frame<M> {
    /// Write the frame with its delimiter, return the number of bytes.
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

    /// Check and parse one frame after COBS decoding.
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
#[derive(Debug, Default)]
pub struct Decoder {
    buf: [u8; MAX_COBS],
    len: usize,
    overflow: bool,
}

impl Decoder {
    pub fn new() -> Self {
        Self::default()
    }

    /// Returns a result at each delimiter. Empty frames (a break reads as zero bytes) give nothing.
    pub fn push<M: Message>(&mut self, byte: u8) -> Option<Result<Frame<M>, DecodeError>> {
        if byte != 0 {
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
