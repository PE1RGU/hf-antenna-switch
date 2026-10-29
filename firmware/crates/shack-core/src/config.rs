//! Stored settings (host-protocol.md section 8a): names, routes, bias-T columns, page.
//! Never TX requests or keys.
//!
//! Record: `S K` | version | 5 antenna names | 3 radio names | 3 routes (tx, rx) |
//! bias mask | page | CRC-16/CCITT-FALSE (high byte first). A name is a length byte
//! and its characters.
//!
//! | Bytes | Content |
//! |---|---|
//! | 2 | Magic `SK` |
//! | 1 | Version, now 1 |
//! | 8 x (1 + 1..=8) | A1, A2, A3, A4, EXP names, then R1, R2, R3 names |
//! | 6 | Route per radio: TX column, RX column (0 = none, 1 = A1 ... 5 = EXP) |
//! | 1 | Bias-T column mask |
//! | 1 | Page: 0 = flow (B), 1 = cards (C), 2 = auto |
//! | 2 | CRC-16 over all bytes before it |
//!
//! The names have a variable length, so the record length varies too; the
//! largest is [`CONFIG_MAX`] bytes. The CRC, the magic and the version together
//! refuse erased flash (all 0xFF), a half-written record and a record from another
//! firmware version. Then the logic uses [`Config::default`].
//!
//! The logic loads the record once, on the first tick. It saves the record
//! [`CONFIG_SAVE_DELAY`](crate::shack::CONFIG_SAVE_DELAY) after the last change.

use host_proto::{NAME_MAX, Name, PageSel};
use link_proto::{Col, ColMask, Route};

const MAGIC: [u8; 2] = *b"SK";
const VERSION: u8 = 1;
/// Largest record in bytes: 3 + 8 names of 1 + NAME_MAX + 6 + 1 + 1 + 2 = 85.
/// Use it as the buffer size for [`Config::encode`] and for the flash slot.
pub const CONFIG_MAX: usize = 3 + 8 * (1 + NAME_MAX) + 6 + 1 + 1 + 2;

const CRC: crc::Crc<u16> = crc::Crc::<u16>::new(&crc::CRC_16_IBM_3740);

/// The stored settings of the shack interface.
///
/// The logic keeps one copy in [`Shack`](crate::shack::Shack). The host changes the
/// names and the page directly (`name`, `page`). Routes and bias change only when
/// the box accepts a command: the logic copies what the box reports, so the stored
/// values are always values the box allowed.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Config {
    /// Names of A1, A2, A3, A4 and EXP, shown on the display (1 to 8 characters).
    pub antenna_names: [Name; 5],
    /// Names of R1, R2 and R3, shown on the display.
    pub radio_names: [Name; 3],
    /// Last accepted route per radio (index 0 = R1). Sent to the box again after
    /// each link up (host-protocol.md 8a, restore).
    pub routes: [Route; 3],
    /// Columns with the bias-T on (only RX-only columns have one, A-10).
    pub bias: ColMask,
    /// Display page choice: flow, cards or auto.
    pub page: PageSel,
}

fn name(s: &str) -> Name {
    Name::new(s).unwrap_or(Name::new("-").unwrap_or_else(|| unreachable!()))
}

impl Default for Config {
    /// Station as in requirements.md: A1 G5RV, A2 RX loop, A3 and A4 spare; R1 FT-710.
    fn default() -> Self {
        Config {
            antenna_names: ["G5RV", "Loop", "spare", "spare", "unit2"].map(name),
            radio_names: ["FT-710", "WSPR", "spare"].map(name),
            routes: [Route::default(); 3],
            bias: ColMask::EMPTY,
            page: PageSel::Flow,
        }
    }
}

impl Config {
    /// Write the record into `out` and return its length in bytes.
    ///
    /// ```
    /// use shack_core::config::{CONFIG_MAX, Config};
    ///
    /// let mut c = Config::default();
    /// c.page = host_proto::PageSel::Cards;
    ///
    /// let mut buf = [0u8; CONFIG_MAX];
    /// let n = c.encode(&mut buf);
    /// assert_eq!(&buf[..2], b"SK");
    /// assert_eq!(Config::decode(&buf[..n]), Some(c));
    ///
    /// // One changed bit and the CRC refuses the record.
    /// buf[5] ^= 0x01;
    /// assert_eq!(Config::decode(&buf[..n]), None);
    /// ```
    pub fn encode(&self, out: &mut [u8; CONFIG_MAX]) -> usize {
        let mut n = 0;
        let mut put = |b: &[u8]| {
            out[n..n + b.len()].copy_from_slice(b);
            n += b.len();
        };
        put(&MAGIC);
        put(&[VERSION]);
        for nm in self.antenna_names.iter().chain(&self.radio_names) {
            put(&[nm.as_str().len() as u8]);
            put(nm.as_str().as_bytes());
        }
        for r in &self.routes {
            put(&[r.tx as u8, r.rx as u8]);
        }
        let page = match self.page {
            PageSel::Flow => 0,
            PageSel::Cards => 1,
            PageSel::Auto => 2,
        };
        put(&[self.bias.bits(), page]);
        let crc = CRC.checksum(&out[..n]).to_be_bytes();
        out[n..n + 2].copy_from_slice(&crc);
        n + 2
    }

    /// Read a record. `b` must be exactly the record, with nothing after the CRC.
    ///
    /// None for a missing, damaged or unknown record: wrong CRC, wrong magic, other
    /// version, a bad name, an unknown column, or a wrong length.
    pub fn decode(b: &[u8]) -> Option<Self> {
        let (body, crc) = b.split_at_checked(b.len().checked_sub(2)?)?;
        if CRC.checksum(body).to_be_bytes() != crc
            || body.get(..2)? != MAGIC
            || *body.get(2)? != VERSION
        {
            return None;
        }
        let mut i = 3;
        let mut next_name = || -> Option<Name> {
            let len = *body.get(i)? as usize;
            let s = core::str::from_utf8(body.get(i + 1..i + 1 + len)?).ok()?;
            i += 1 + len;
            Name::new(s)
        };
        // Start from the defaults; every field is overwritten below.
        let mut c = Config::default();
        for nm in c.antenna_names.iter_mut().chain(c.radio_names.iter_mut()) {
            *nm = next_name()?;
        }
        // After the names: 6 route bytes, the bias mask and the page.
        let rest = body.get(i..)?;
        if rest.len() != 8 {
            return None;
        }
        for (k, r) in c.routes.iter_mut().enumerate() {
            *r = Route {
                tx: Col::from_u8(rest[2 * k])?,
                rx: Col::from_u8(rest[2 * k + 1])?,
            };
        }
        c.bias = ColMask::from_bits(rest[6])?;
        c.page = [PageSel::Flow, PageSel::Cards, PageSel::Auto]
            .get(rest[7] as usize)
            .copied()?;
        Some(c)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> Config {
        let mut c = Config::default();
        c.antenna_names[2] = Name::new("Hexbeam").unwrap();
        c.radio_names[1] = Name::new("IC-7300").unwrap();
        c.routes[0] = Route {
            tx: Col::A1,
            rx: Col::A2,
        };
        c.bias = ColMask::EMPTY.with(Col::A2);
        c.page = PageSel::Auto;
        c
    }

    #[test]
    fn round_trip() {
        let c = sample();
        let mut buf = [0u8; CONFIG_MAX];
        let n = c.encode(&mut buf);
        assert!(n <= CONFIG_MAX);
        assert_eq!(Config::decode(&buf[..n]), Some(c));
    }

    #[test]
    fn full_length_names_fit() {
        let mut c = sample();
        c.antenna_names = [Name::new("12345678").unwrap(); 5];
        c.radio_names = [Name::new("abcdefgh").unwrap(); 3];
        let mut buf = [0u8; CONFIG_MAX];
        let n = c.encode(&mut buf);
        assert_eq!(n, CONFIG_MAX);
        assert_eq!(Config::decode(&buf[..n]), Some(c));
    }

    #[test]
    fn damaged_records_are_refused() {
        let mut buf = [0u8; CONFIG_MAX];
        let n = sample().encode(&mut buf);
        for i in 0..n {
            for bit in 0..8 {
                let mut b = buf;
                b[i] ^= 1 << bit;
                assert_eq!(Config::decode(&b[..n]), None, "byte {i} bit {bit}");
            }
        }
        assert_eq!(Config::decode(&[]), None);
        assert_eq!(Config::decode(&buf[..n - 1]), None);
        assert_eq!(Config::decode(&[0xFF; CONFIG_MAX]), None, "erased flash");
    }
}
