//! ST7789VW commands for the 2inch module (D-187), write-only SPI, CS tied low.
//! Sequence: RST low, RST high, wait 120 ms, SLPOUT, wait 120 ms, then `INIT`.

pub const SLPOUT: u8 = 0x11;
pub const INVON: u8 = 0x21;
pub const DISPON: u8 = 0x29;
pub const CASET: u8 = 0x2A;
pub const RASET: u8 = 0x2B;
pub const RAMWR: u8 = 0x2C;
pub const MADCTL: u8 = 0x36;
pub const COLMOD: u8 = 0x3A;

/// Wait after the reset and after SLPOUT.
pub const WAIT_MS: u64 = 120;

/// MV and MX: landscape, 320 x 240. To confirm with the module as mounted on front plate a8.
pub const MADCTL_LANDSCAPE: u8 = 0x60;

/// After SLPOUT: landscape, 16-bit colour, inversion on (IPS panel), display on.
pub const INIT: [(u8, &[u8]); 4] = [
    (MADCTL, &[MADCTL_LANDSCAPE]),
    (COLMOD, &[0x55]),
    (INVON, &[]),
    (DISPON, &[]),
];

/// CASET and RASET for the window (x0, y0) to (x1, y1), inclusive.
pub fn window(x0: u16, y0: u16, x1: u16, y1: u16) -> [(u8, [u8; 4]); 2] {
    let [a, b] = x0.to_be_bytes();
    let [c, d] = x1.to_be_bytes();
    let [e, f] = y0.to_be_bytes();
    let [g, h] = y1.to_be_bytes();
    [(CASET, [a, b, c, d]), (RASET, [e, f, g, h])]
}
