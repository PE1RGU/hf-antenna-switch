//! PCA9539 driver. Rule F1 (logic-verification.md): after a reset the output
//! register is 0xFFFF, so the output register is written before the configuration.
//!
//! The PCA9539 is a 16-bit I2C I/O expander (D-49). The box uses them to
//! drive the relay coils and read back the relay and detector states; the
//! shack interface uses one for its own I/O. Addresses 0x74 to 0x77 (A1 A0).
//!
//! Why F1 matters (`hardware/unit/verify/logic-verification.md`): after a
//! reset every pin is an input and the output register is all ones. If the
//! firmware makes a pin an output (configuration 0) before it writes the
//! output register, that pin goes high at once, and its relay coil switches
//! on. So [`Pca9539::init`] always writes the outputs first.
//!
//! A 16-bit value holds both ports: bit 0 to 7 = port 0 (IO0_0 to IO0_7),
//! bit 8 to 15 = port 1 (IO1_0 to IO1_7). The driver writes and reads the two
//! registers of a pair in one I2C transfer, low port first.
//!
//! The driver uses the `embedded-hal` 1.0 [`I2c`] trait, so it works with the
//! ESP32-C3 I2C peripheral and with the simulated bus. The crate is `no_std`:
//! it does not use the Rust standard library, so it runs on the ESP32-C3
//! without an operating system.
//!
//! ```text
//!  let x = Pca9539::new(0x74);
//!  x.init(&mut i2c, 0x0000, config)?;   // F1 order, with read-back
//!  x.write_outputs(&mut i2c, coils)?;   // switch relays
//!  let pins = x.read_inputs(&mut i2c)?; // read back
//! ```
#![no_std]

use embedded_hal::i2c::I2c;

// Register pairs (port 0, port 1). The chip steps to the second register of
// the pair by itself, so one transfer covers 16 bits. The polarity register
// pair (4, 5) is not used: it stays at its reset value 0 (no inversion).
const REG_INPUT: u8 = 0;
const REG_OUTPUT: u8 = 2;
const REG_CONFIG: u8 = 6;

/// Driver error. `E` is the error type of the I2C bus.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error<E> {
    /// The I2C transfer failed, for example a NACK (no chip at the address).
    Bus(E),
    /// Read-back differs from what was written.
    Verify,
}

/// Lets `?` turn a bus error into [`Error::Bus`].
impl<E> From<E> for Error<E> {
    fn from(e: E) -> Self {
        Error::Bus(e)
    }
}

/// One PCA9539 on the bus.
///
/// It holds only the address. The caller passes the I2C bus to each call, so
/// one bus can serve several expanders.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Pca9539 {
    addr: u8,
}

impl Pca9539 {
    /// An expander at this 7-bit I2C address (0x74 to 0x77). No bus traffic.
    pub const fn new(addr: u8) -> Self {
        Pca9539 { addr }
    }

    /// Set up after power-up or reset, in the F1 order: outputs, then configuration
    /// (1 = input), then read both back.
    ///
    /// `out` is the output level per pin (normally 0x0000: all coils off).
    /// `config` sets each pin: 1 = input, 0 = output. Gives
    /// [`Error::Verify`] if the read-back differs. Call it again after any
    /// expander reset (F5: after KILL returns to 0).
    pub fn init<I: I2c>(&self, i2c: &mut I, out: u16, config: u16) -> Result<(), Error<I::Error>> {
        self.write_outputs(i2c, out)?;
        self.write16(i2c, REG_CONFIG, config)?;
        if self.read16(i2c, REG_OUTPUT)? != out || self.read16(i2c, REG_CONFIG)? != config {
            return Err(Error::Verify);
        }
        Ok(())
    }

    /// Write the output register pair: the level of each output pin
    /// (1 = high). Bits of input pins have no effect on the pins.
    pub fn write_outputs<I: I2c>(&self, i2c: &mut I, out: u16) -> Result<(), Error<I::Error>> {
        self.write16(i2c, REG_OUTPUT, out)
    }

    /// Pin levels (input register, polarity 0). Gives the real level of
    /// every pin, outputs included, so it also reads back the outputs.
    pub fn read_inputs<I: I2c>(&self, i2c: &mut I) -> Result<u16, Error<I::Error>> {
        self.read16(i2c, REG_INPUT)
    }

    /// Configuration register. 0xFFFF after a reset: use it to find an expander reset.
    ///
    /// If it reads 0xFFFF but [`init`](Self::init) wrote another value, the
    /// chip was reset (for example RLY_EN low, F5) and needs `init` again.
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
