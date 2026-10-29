//! Stored settings (host-protocol.md section 8a): names, routes, bias-T columns, page.
//! Never TX requests or keys.
//!
//! Record: `S K` | version | 5 antenna names | 3 radio names | 3 routes (tx, rx) |
//! bias mask | page | CRC-16/CCITT-FALSE (high byte first). A name is a length byte
//! and its characters.

use host_proto::{NAME_MAX, Name, PageSel};
use link_proto::{Col, ColMask, Route};

const MAGIC: [u8; 2] = *b"SK";
const VERSION: u8 = 1;
/// Largest record: 3 + 8 names of 1 + NAME_MAX + 6 + 1 + 1 + 2.
pub const CONFIG_MAX: usize = 3 + 8 * (1 + NAME_MAX) + 6 + 1 + 1 + 2;

const CRC: crc::Crc<u16> = crc::Crc::<u16>::new(&crc::CRC_16_IBM_3740);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Config {
    pub antenna_names: [Name; 5],
    pub radio_names: [Name; 3],
    pub routes: [Route; 3],
    pub bias: ColMask,
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

    /// None for a missing, damaged or unknown record.
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
        let mut c = Config::default();
        for nm in c.antenna_names.iter_mut().chain(c.radio_names.iter_mut()) {
            *nm = next_name()?;
        }
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
