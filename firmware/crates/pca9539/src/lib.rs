//! PCA9539 driver. Rule F1 (logic-verification.md): after a reset the output
//! register is 0xFFFF, so the output register is written before the configuration.
#![no_std]

use embedded_hal::i2c::I2c;

const REG_INPUT: u8 = 0;
const REG_OUTPUT: u8 = 2;
const REG_CONFIG: u8 = 6;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error<E> {
    Bus(E),
    /// Read-back differs from what was written.
    Verify,
}

impl<E> From<E> for Error<E> {
    fn from(e: E) -> Self {
        Error::Bus(e)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Pca9539 {
    addr: u8,
}

impl Pca9539 {
    pub const fn new(addr: u8) -> Self {
        Pca9539 { addr }
    }

    /// Set up after power-up or reset, in the F1 order: outputs, then configuration
    /// (1 = input), then read both back.
    pub fn init<I: I2c>(&self, i2c: &mut I, out: u16, config: u16) -> Result<(), Error<I::Error>> {
        self.write_outputs(i2c, out)?;
        self.write16(i2c, REG_CONFIG, config)?;
        if self.read16(i2c, REG_OUTPUT)? != out || self.read16(i2c, REG_CONFIG)? != config {
            return Err(Error::Verify);
        }
        Ok(())
    }

    pub fn write_outputs<I: I2c>(&self, i2c: &mut I, out: u16) -> Result<(), Error<I::Error>> {
        self.write16(i2c, REG_OUTPUT, out)
    }

    /// Pin levels (input register, polarity 0).
    pub fn read_inputs<I: I2c>(&self, i2c: &mut I) -> Result<u16, Error<I::Error>> {
        self.read16(i2c, REG_INPUT)
    }

    /// Configuration register. 0xFFFF after a reset: use it to find an expander reset.
    pub fn read_config<I: I2c>(&self, i2c: &mut I) -> Result<u16, Error<I::Error>> {
        self.read16(i2c, REG_CONFIG)
    }

    fn write16<I: I2c>(&self, i2c: &mut I, reg: u8, v: u16) -> Result<(), Error<I::Error>> {
        let [lo, hi] = v.to_le_bytes();
        Ok(i2c.write(self.addr, &[reg, lo, hi])?)
    }

    fn read16<I: I2c>(&self, i2c: &mut I, reg: u8) -> Result<u16, Error<I::Error>> {
        let mut b = [0u8; 2];
        i2c.write_read(self.addr, &[reg], &mut b)?;
        Ok(u16::from_le_bytes(b))
    }
}
