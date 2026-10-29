//! Sitronix ST7789 display controller, write-only SPI, 240 x 320 panel (Waveshare 2inch, D-187).
//!
//! Supports the commands a driver needs to draw: SWRESET, SLPIN/SLPOUT, INVOFF/INVON,
//! DISPOFF/DISPON, CASET, RASET, RAMWR, MADCTL (MY, MX, MV), COLMOD (16 bit only).
//! Other commands are kept in `unknown` so a test can see them.
//! Simplification: MADCTL swaps (MV) before it mirrors (MX, MY), on panel coordinates.

pub const WIDTH: usize = 240;
pub const HEIGHT: usize = 320;

#[derive(Clone, Debug)]
pub struct St7789 {
    fb: Vec<u16>,
    cmd: Option<u8>,
    args: Vec<u8>,
    col: (u16, u16),
    row: (u16, u16),
    cur: (u16, u16),
    pixel_hi: Option<u8>,
    madctl: u8,
    colmod: u8,
    sleeping: bool,
    on: bool,
    inverted: bool,
    in_reset: bool,
    /// Commands the model does not handle, in order received.
    pub unknown: Vec<u8>,
}

impl Default for St7789 {
    fn default() -> Self {
        Self::new()
    }
}

impl St7789 {
    pub fn new() -> Self {
        St7789 {
            fb: vec![0; WIDTH * HEIGHT],
            cmd: None,
            args: Vec::new(),
            col: (0, WIDTH as u16 - 1),
            row: (0, HEIGHT as u16 - 1),
            cur: (0, 0),
            pixel_hi: None,
            madctl: 0,
            colmod: 0x66,
            sleeping: true,
            on: false,
            inverted: false,
            in_reset: false,
            unknown: Vec::new(),
        }
    }

    /// Registers to their reset values. The frame memory keeps its content.
    fn reset_registers(&mut self) {
        let (fb, unknown) = (
            std::mem::take(&mut self.fb),
            std::mem::take(&mut self.unknown),
        );
        *self = St7789 {
            fb,
            unknown,
            ..St7789::new()
        };
    }

    /// RESX pin: low holds the controller in reset.
    pub fn set_reset(&mut self, low: bool) {
        if low {
            self.reset_registers();
        }
        self.in_reset = low;
    }

    /// Bytes on SPI with the D/C level: false = command, true = data.
    pub fn spi(&mut self, dc: bool, data: &[u8]) {
        if self.in_reset {
            return;
        }
        for &b in data {
            if dc {
                self.data(b);
            } else {
                self.command(b);
            }
        }
    }

    fn command(&mut self, c: u8) {
        self.cmd = Some(c);
        self.args.clear();
        self.pixel_hi = None;
        match c {
            0x00 => {}
            0x01 => self.reset_registers(),
            0x10 => self.sleeping = true,
            0x11 => self.sleeping = false,
            0x20 => self.inverted = false,
            0x21 => self.inverted = true,
            0x28 => self.on = false,
            0x29 => self.on = true,
            0x2C => self.cur = (self.col.0, self.row.0),
            0x2A | 0x2B | 0x36 | 0x3A => {}
            _ => self.unknown.push(c),
        }
    }

    fn data(&mut self, b: u8) {
        let Some(c) = self.cmd else { return };
        if c == 0x2C {
            match self.pixel_hi.take() {
                None => self.pixel_hi = Some(b),
                Some(hi) => self.put_pixel(u16::from_be_bytes([hi, b])),
            }
            return;
        }
        self.args.push(b);
        let a = &self.args;
        match (c, a.len()) {
            (0x2A, 4) => {
                self.col = (
                    u16::from_be_bytes([a[0], a[1]]),
                    u16::from_be_bytes([a[2], a[3]]),
                )
            }
            (0x2B, 4) => {
                self.row = (
                    u16::from_be_bytes([a[0], a[1]]),
                    u16::from_be_bytes([a[2], a[3]]),
                )
            }
            (0x36, 1) => self.madctl = a[0],
            (0x3A, 1) => self.colmod = a[0],
            _ => {}
        }
    }

    fn put_pixel(&mut self, color: u16) {
        let (x, y) = self.cur;
        if let Some(i) = self.panel_index(x, y) {
            self.fb[i] = color;
        }
        // Advance inside the window, wrap to the start.
        self.cur = if x < self.col.1 {
            (x + 1, y)
        } else if y < self.row.1 {
            (self.col.0, y + 1)
        } else {
            (self.col.0, self.row.0)
        };
    }

    fn panel_index(&self, x: u16, y: u16) -> Option<usize> {
        let (mut px, mut py) = (x as usize, y as usize);
        if self.madctl & 0x20 != 0 {
            (px, py) = (py, px);
        }
        if px >= WIDTH || py >= HEIGHT {
            return None;
        }
        if self.madctl & 0x40 != 0 {
            px = WIDTH - 1 - px;
        }
        if self.madctl & 0x80 != 0 {
            py = HEIGHT - 1 - py;
        }
        Some(py * WIDTH + px)
    }

    /// RGB565 at panel coordinates (x 0..240, y 0..320).
    pub fn pixel(&self, x: usize, y: usize) -> u16 {
        self.fb[y * WIDTH + x]
    }

    pub fn framebuffer(&self) -> &[u16] {
        &self.fb
    }

    /// The picture as the driver addressed it: `w` x `h` in window coordinates,
    /// through the present MADCTL (landscape 320 x 240 with MV set).
    pub fn logical(&self, w: usize, h: usize) -> Vec<u16> {
        let mut out = Vec::with_capacity(w * h);
        for y in 0..h {
            for x in 0..w {
                let i = self.panel_index(x as u16, y as u16);
                out.push(i.map_or(0, |i| self.fb[i]));
            }
        }
        out
    }

    pub fn madctl(&self) -> u8 {
        self.madctl
    }

    /// The picture is visible: awake, display on, 16-bit colour set.
    pub fn showing(&self) -> bool {
        !self.in_reset && !self.sleeping && self.on && self.colmod & 0x07 == 0x05
    }

    pub fn inverted(&self) -> bool {
        self.inverted
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cmd(d: &mut St7789, c: u8, args: &[u8]) {
        d.spi(false, &[c]);
        d.spi(true, args);
    }

    fn fill(d: &mut St7789, x0: u16, y0: u16, x1: u16, y1: u16, color: u16) {
        let [a, b] = x0.to_be_bytes();
        let [c, e] = x1.to_be_bytes();
        cmd(d, 0x2A, &[a, b, c, e]);
        let [a, b] = y0.to_be_bytes();
        let [c, e] = y1.to_be_bytes();
        cmd(d, 0x2B, &[a, b, c, e]);
        let n = ((x1 - x0 + 1) * (y1 - y0 + 1)) as usize;
        let px: Vec<u8> = (0..n).flat_map(|_| color.to_be_bytes()).collect();
        cmd(d, 0x2C, &px);
    }

    #[test]
    fn init_and_fill_window() {
        let mut d = St7789::new();
        cmd(&mut d, 0x11, &[]);
        cmd(&mut d, 0x3A, &[0x55]);
        cmd(&mut d, 0x21, &[]);
        cmd(&mut d, 0x29, &[]);
        assert!(d.showing());
        fill(&mut d, 10, 20, 12, 21, 0xF800);
        assert_eq!(d.pixel(10, 20), 0xF800);
        assert_eq!(d.pixel(12, 21), 0xF800);
        assert_eq!(d.pixel(13, 21), 0);
        assert_eq!(d.pixel(10, 22), 0);
        assert!(d.unknown.is_empty());
    }

    #[test]
    fn landscape_with_mv() {
        let mut d = St7789::new();
        cmd(&mut d, 0x36, &[0x20]);
        // Logical (300, 5) in a 320 x 240 picture lands on panel (5, 300).
        fill(&mut d, 300, 5, 300, 5, 0x07E0);
        assert_eq!(d.pixel(5, 300), 0x07E0);
    }

    #[test]
    fn reset_pin_keeps_frame_memory_and_ignores_spi() {
        let mut d = St7789::new();
        fill(&mut d, 0, 0, 0, 0, 0x001F);
        d.set_reset(true);
        fill(&mut d, 1, 0, 1, 0, 0x001F);
        d.set_reset(false);
        assert_eq!(d.pixel(0, 0), 0x001F);
        assert_eq!(d.pixel(1, 0), 0);
        assert!(!d.showing());
    }
}
