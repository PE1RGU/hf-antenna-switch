//! ST7789VW commands for the 2inch module (D-187), write-only SPI, CS tied low.
//! Sequence: RST low, RST high, wait 120 ms, SLPOUT, wait 120 ms, then `INIT`.
//!
//! A command is one byte sent with D/C low. Its arguments follow with D/C high.
//! This module only lists the bytes; the shack logic sends them.

/// Sleep out: the panel leaves sleep mode. Wait [`WAIT_MS`] before the next command.
pub const SLPOUT: u8 = 0x11;
/// Display inversion on. The IPS panel needs it for correct colours.
pub const INVON: u8 = 0x21;
/// Display on: the panel shows its memory.
pub const DISPON: u8 = 0x29;
/// Column address set: first and last column of the write window.
pub const CASET: u8 = 0x2A;
/// Row address set: first and last row of the write window.
pub const RASET: u8 = 0x2B;
/// Memory write: all pixel data after it goes into the window, row by row.
pub const RAMWR: u8 = 0x2C;
/// Memory data access control: rotation and mirroring.
pub const MADCTL: u8 = 0x36;
/// Interface pixel format. Argument 0x55 = 16 bits per pixel (RGB565).
pub const COLMOD: u8 = 0x3A;

/// Wait after the reset and after SLPOUT, in ms.
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
///
/// Each argument is sent as two bytes, high byte first.
///
/// ```
/// use shack_ui::st7789::{CASET, RASET, window};
///
/// let [(c, cols), (r, rows)] = window(0, 0, 319, 239);
/// assert_eq!((c, cols), (CASET, [0, 0, 0x01, 0x3F]));
/// assert_eq!((r, rows), (RASET, [0, 0, 0, 0xEF]));
/// ```
pub fn window(x0: u16, y0: u16, x1: u16, y1: u16) -> [(u8, [u8; 4]); 2] {
    let [a, b] = x0.to_be_bytes();
    let [c, d] = x1.to_be_bytes();
    let [e, f] = y0.to_be_bytes();
    let [g, h] = y1.to_be_bytes();
    [(CASET, [a, b, c, d]), (RASET, [e, f, g, h])]
}
