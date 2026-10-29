//! Colours and fonts. M+ fonts, anti-aliased (4-bit), printable ASCII plus the middle dot.

use embedded_graphics::pixelcolor::{Gray4, Rgb565};
use mplusfonts::{BitmapFont, mplus};

pub type Font = BitmapFont<'static, Gray4, 1>;

pub static HUGE: Font = mplus!(1, 800, line_height(30), true, 1, 4, ' '..='~');
pub static BIG: Font = mplus!(1, 700, line_height(24), true, 1, 4, ' '..='~');
pub static NUM: Font = mplus!(1, 300, line_height(28), true, 1, 4, ' '..='~');
pub static TITLE: Font = mplus!(1, 700, line_height(17), true, 1, 4, ' '..='~');
pub static BODY: Font = mplus!(1, 500, line_height(15), true, 1, 4, ' '..='~', ["·"]);
pub static SMALL: Font = mplus!(1, 500, line_height(12), true, 1, 4, ' '..='~', ["·"]);

/// 24-bit colour (0xRRGGBB) to RGB565.
const fn rgb(h: u32) -> Rgb565 {
    Rgb565::new(
        ((h >> 19) & 0x1F) as u8,
        ((h >> 10) & 0x3F) as u8,
        ((h >> 3) & 0x1F) as u8,
    )
}

pub const BG: Rgb565 = rgb(0x0E1116);
pub const CARD: Rgb565 = rgb(0x1A1F27);
pub const CARD_DIM: Rgb565 = rgb(0x151920);
pub const TEXT: Rgb565 = rgb(0xF1F3F6);
pub const SEC: Rgb565 = rgb(0x8A94A3);
pub const FAINT: Rgb565 = rgb(0x4A5361);
pub const TX: Rgb565 = rgb(0xFF4D4F);
pub const TX_GLOW: Rgb565 = rgb(0x4A1A1D);
pub const TX_IDLE: Rgb565 = rgb(0x6A2A2D);
pub const RX: Rgb565 = rgb(0x2BD07B);
pub const RX_TINT: Rgb565 = rgb(0x123326);
pub const AMBER: Rgb565 = rgb(0xF5A524);
pub const AMBER_TINT: Rgb565 = rgb(0x33260C);
