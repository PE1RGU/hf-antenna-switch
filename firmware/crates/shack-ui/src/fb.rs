//! Frame buffer in the ST7789 pixel format: RGB565, big-endian, row by row.
//! 320 x 240 x 2 = 153 600 bytes. The caller owns the memory (a static on the target).

use crate::{HEIGHT, WIDTH};
use core::convert::Infallible;
use embedded_graphics::pixelcolor::Rgb565;
use embedded_graphics::pixelcolor::raw::RawU16;
use embedded_graphics::prelude::*;
use embedded_graphics::primitives::Rectangle;

pub const BYTES: usize = (WIDTH * HEIGHT * 2) as usize;
pub const ROW_BYTES: usize = (WIDTH * 2) as usize;

pub struct FrameBuffer<'a> {
    buf: &'a mut [u8],
}

impl<'a> FrameBuffer<'a> {
    /// `buf` must hold at least `BYTES`.
    pub fn new(buf: &'a mut [u8]) -> Self {
        assert!(buf.len() >= BYTES, "frame buffer too small");
        FrameBuffer { buf }
    }
}

/// Pixel at (x, y) of a frame buffer, as RGB565.
pub fn pixel(buf: &[u8], x: u32, y: u32) -> u16 {
    let i = ((y * WIDTH + x) * 2) as usize;
    u16::from_be_bytes([buf[i], buf[i + 1]])
}

impl OriginDimensions for FrameBuffer<'_> {
    fn size(&self) -> Size {
        Size::new(WIDTH, HEIGHT)
    }
}

impl DrawTarget for FrameBuffer<'_> {
    type Color = Rgb565;
    type Error = Infallible;

    fn draw_iter<I: IntoIterator<Item = Pixel<Rgb565>>>(
        &mut self,
        pixels: I,
    ) -> Result<(), Infallible> {
        for Pixel(p, c) in pixels {
            if (0..WIDTH as i32).contains(&p.x) && (0..HEIGHT as i32).contains(&p.y) {
                let i = ((p.y as u32 * WIDTH + p.x as u32) * 2) as usize;
                self.buf[i..i + 2].copy_from_slice(&RawU16::from(c).into_inner().to_be_bytes());
            }
        }
        Ok(())
    }

    fn fill_solid(&mut self, area: &Rectangle, color: Rgb565) -> Result<(), Infallible> {
        let area = area.intersection(&self.bounding_box());
        let Some(br) = area.bottom_right() else {
            return Ok(());
        };
        let px = RawU16::from(color).into_inner().to_be_bytes();
        for y in area.top_left.y..=br.y {
            let row = (y as u32 * WIDTH) as usize * 2;
            for x in area.top_left.x..=br.x {
                let i = row + x as usize * 2;
                self.buf[i..i + 2].copy_from_slice(&px);
            }
        }
        Ok(())
    }
}
