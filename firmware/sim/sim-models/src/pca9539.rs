//! NXP/TI PCA9539 16-bit I2C I/O expander, register level.
//!
//! Registers: 0, 1 input; 2, 3 output; 4, 5 polarity; 6, 7 configuration (1 = input).
//! After reset: output 0xFFFF, polarity 0, configuration 0xFFFF (all inputs).
//! The register pointer toggles inside its pair after each byte.
//! While RESET is low the device holds the defaults and does not acknowledge.
//!
//! On the shack board, RESET comes from the supervisor RESET_N (TPS3823). The
//! default output register of 0xFFFF matters: a pin that the firmware makes an
//! output before it writes the output register goes high at once (rule F1). So the
//! firmware writes the outputs first, then the configuration.

use sim_core::i2c::{I2cDevice, Nack};

/// One PCA9539 at register level. Use it as an [`I2cDevice`] on the board bus.
///
/// The board sets the levels on the input pins with [`Pca9539::set_external`] and
/// reads the pin levels with [`Pca9539::pins`].
#[derive(Clone, Debug)]
pub struct Pca9539 {
    output: u16,
    polarity: u16,
    config: u16,
    ptr: u8,
    in_reset: bool,
    ext: u16,
    /// Fault injection: refuse every transfer.
    pub force_nack: bool,
}

impl Default for Pca9539 {
    fn default() -> Self {
        Self::new()
    }
}

impl Pca9539 {
    /// A device in its power-on state: outputs 0xFFFF, polarity 0, all pins inputs,
    /// not in reset.
    pub fn new() -> Self {
        Pca9539 {
            output: 0xFFFF,
            polarity: 0,
            config: 0xFFFF,
            ptr: 0,
            in_reset: false,
            ext: 0xFFFF,
            force_nack: false,
        }
    }

    /// RESET pin. Active: registers to defaults, no acknowledge.
    pub fn set_reset(&mut self, active: bool) {
        if active {
            let (nack, ext) = (self.force_nack, self.ext);
            *self = Pca9539::new();
            self.force_nack = nack;
            self.ext = ext;
        }
        self.in_reset = active;
    }

    /// True while the RESET pin is active.
    pub fn in_reset(&self) -> bool {
        self.in_reset
    }

    /// Levels the board puts on the pins (pull resistors and drivers).
    /// Used for pins configured as inputs.
    pub fn set_external(&mut self, levels: u16) {
        self.ext = levels;
    }

    /// Pin levels: the output register on outputs, the board level on inputs.
    pub fn pins(&self) -> u16 {
        (self.output & !self.config) | (self.ext & self.config)
    }

    /// Level of one pin (`bit` 0 to 15: port 0 is bits 0 to 7, port 1 is bits 8 to 15).
    pub fn pin(&self, bit: u8) -> bool {
        self.pins() & (1 << bit) != 0
    }

    /// Output registers 2 and 3 as one word (register 3 in the high byte).
    pub fn output_reg(&self) -> u16 {
        self.output
    }

    /// Configuration registers 6 and 7 as one word. A 1 bit is an input.
    pub fn config_reg(&self) -> u16 {
        self.config
    }

    fn reg(&self, r: u8) -> u8 {
        let word = match r >> 1 {
            0 => self.pins() ^ self.polarity,
            1 => self.output,
            2 => self.polarity,
            _ => self.config,
        };
        word.to_le_bytes()[(r & 1) as usize]
    }

    fn set_reg(&mut self, r: u8, v: u8) {
        let word = match r >> 1 {
            0 => return, // input registers are read-only
            1 => &mut self.output,
            2 => &mut self.polarity,
            _ => &mut self.config,
        };
        let mut b = word.to_le_bytes();
        b[(r & 1) as usize] = v;
        *word = u16::from_le_bytes(b);
    }
}

impl I2cDevice for Pca9539 {
    fn write(&mut self, data: &[u8]) -> Result<(), Nack> {
        if self.in_reset || self.force_nack {
            return Err(Nack);
        }
        let Some((&cmd, rest)) = data.split_first() else {
            return Ok(());
        };
        if cmd > 7 {
            return Err(Nack);
        }
        self.ptr = cmd;
        for &v in rest {
            self.set_reg(self.ptr, v);
            self.ptr ^= 1;
        }
        Ok(())
    }

    fn read(&mut self, buf: &mut [u8]) -> Result<(), Nack> {
        if self.in_reset || self.force_nack {
            return Err(Nack);
        }
        for b in buf {
            *b = self.reg(self.ptr);
            self.ptr ^= 1;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_after_reset() {
        let mut e = Pca9539::new();
        e.write(&[2, 0x00, 0x00]).unwrap();
        e.write(&[6, 0x00, 0x00]).unwrap();
        e.set_reset(true);
        assert!(e.write(&[2, 0]).is_err());
        e.set_reset(false);
        assert_eq!(e.output_reg(), 0xFFFF);
        assert_eq!(e.config_reg(), 0xFFFF);
    }

    /// F1: configuring a pin as output before writing its output register drives it high.
    #[test]
    fn config_before_output_drives_high() {
        let mut e = Pca9539::new();
        e.set_external(0x0000);
        e.write(&[6, 0xFE]).unwrap();
        assert!(e.pin(0), "pin 0 jumps high: output register default 1");
        let mut e = Pca9539::new();
        e.set_external(0x0000);
        e.write(&[2, 0x00, 0x00]).unwrap();
        e.write(&[6, 0xFE]).unwrap();
        assert!(!e.pin(0));
    }

    #[test]
    fn pointer_toggles_in_pair_and_polarity_inverts_input() {
        let mut e = Pca9539::new();
        e.set_external(0x1234);
        e.write(&[4, 0xFF, 0x00, 0x0F]).unwrap(); // 4, 5, then back to 4
        let mut b = [0u8; 2];
        e.write(&[0]).unwrap();
        e.read(&mut b).unwrap();
        assert_eq!(u16::from_le_bytes(b), 0x1234 ^ 0x000F);
        e.write(&[1]).unwrap();
        e.read(&mut b).unwrap();
        assert_eq!(b, [0x12, 0x3B]);
    }

    #[test]
    fn input_register_is_read_only() {
        let mut e = Pca9539::new();
        e.set_external(0xAAAA);
        e.write(&[0, 0x00, 0x00]).unwrap();
        let mut b = [0u8; 2];
        e.write(&[0]).unwrap();
        e.read(&mut b).unwrap();
        assert_eq!(u16::from_le_bytes(b), 0xAAAA);
    }
}
