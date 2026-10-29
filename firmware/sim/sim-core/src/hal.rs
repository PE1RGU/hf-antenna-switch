//! embedded-hal adapters. On the target, esp-hal gives these traits; in the
//! simulator, these adapters forward each call to the board model.
//!
//! The board model implements [`Board`]. Each adapter holds a [`Shared`] handle to
//! the same board, so a write on [`SimOutput`] and a read on [`SimInput`] see one
//! board state. The adapters are thin: they add no timing and no faults. Faults
//! belong in the board or part models.

use crate::SimTime;
use embedded_hal::digital::{ErrorType as PinErrorType, InputPin, OutputPin};
use embedded_hal::i2c::{self, I2c, Operation, SevenBitAddress};
use embedded_hal::spi::{self, SpiBus};
use std::cell::RefCell;
use std::convert::Infallible;
use std::rc::Rc;

/// What the MCU sees of a board: its pins, its I2C bus, its SPI bus, its UART.
/// Pin numbers are ESP32-C3 GPIO numbers.
///
/// A board model implements this trait. The adapters in this module and the
/// firmware glue (`SimShackHw` in `sim-shack`) call it. Every call happens at the
/// board's present virtual time, [`Board::now`].
pub trait Board {
    /// Present virtual time of the board.
    fn now(&self) -> SimTime;
    /// One I2C transaction to the 7-bit address `addr`: the write and read
    /// segments in `ops`, with repeated starts between them. Returns
    /// `NoAcknowledge` when no device answers.
    fn i2c(&mut self, addr: u8, ops: &mut [Operation<'_>]) -> Result<(), i2c::ErrorKind>;
    /// Drive output `pin` high or low.
    fn gpio_write(&mut self, pin: u8, high: bool);
    /// Read the level on input `pin`.
    fn gpio_read(&mut self, pin: u8) -> bool;
    /// Bytes on the SPI bus (write only). The board decides what the bytes mean,
    /// for example from a D/C pin.
    fn spi_write(&mut self, data: &[u8]);
    /// Put one byte in the UART transmitter.
    fn uart_write(&mut self, byte: u8);
    /// Next byte that the UART received by now, if any.
    fn uart_read(&mut self) -> Option<u8>;
    /// Host port (USB). Bytes arrive at once: USB is fast against the 10 ms tick.
    fn usb_write(&mut self, byte: u8);
    /// Host port (USB): next byte from the host, if any.
    fn usb_read(&mut self) -> Option<u8>;
}

/// A board that more than one owner can use: the firmware glue, the adapters
/// and the test.
///
/// `Rc` lets several owners hold the same value. `RefCell` lets each of them
/// change it, one at a time: `borrow_mut()` panics if another borrow is still
/// active. The simulator runs on one thread, so this is enough.
pub type Shared<B> = Rc<RefCell<B>>;

/// Wrap a board in a [`Shared`] handle. Clone the handle to give it to a
/// second owner; both clones point to the same board.
pub fn shared<B>(board: B) -> Shared<B> {
    Rc::new(RefCell::new(board))
}

/// I2C bus master: forwards each `embedded-hal` transaction to [`Board::i2c`].
pub struct SimI2c<B>(pub Shared<B>);

impl<B> i2c::ErrorType for SimI2c<B> {
    type Error = i2c::ErrorKind;
}

impl<B: Board> I2c<SevenBitAddress> for SimI2c<B> {
    fn transaction(&mut self, addr: u8, ops: &mut [Operation<'_>]) -> Result<(), Self::Error> {
        self.0.borrow_mut().i2c(addr, ops)
    }
}

/// One push-pull output pin: `set_high` and `set_low` go to [`Board::gpio_write`].
pub struct SimOutput<B> {
    /// The board that owns the pin.
    pub board: Shared<B>,
    /// ESP32-C3 GPIO number.
    pub pin: u8,
}

impl<B> PinErrorType for SimOutput<B> {
    type Error = Infallible;
}

impl<B: Board> OutputPin for SimOutput<B> {
    fn set_low(&mut self) -> Result<(), Infallible> {
        self.board.borrow_mut().gpio_write(self.pin, false);
        Ok(())
    }
    fn set_high(&mut self) -> Result<(), Infallible> {
        self.board.borrow_mut().gpio_write(self.pin, true);
        Ok(())
    }
}

/// One input pin: `is_high` and `is_low` come from [`Board::gpio_read`].
pub struct SimInput<B> {
    /// The board that owns the pin.
    pub board: Shared<B>,
    /// ESP32-C3 GPIO number.
    pub pin: u8,
}

impl<B> PinErrorType for SimInput<B> {
    type Error = Infallible;
}

impl<B: Board> InputPin for SimInput<B> {
    fn is_high(&mut self) -> Result<bool, Infallible> {
        Ok(self.board.borrow_mut().gpio_read(self.pin))
    }
    fn is_low(&mut self) -> Result<bool, Infallible> {
        Ok(!self.board.borrow_mut().gpio_read(self.pin))
    }
}

/// Write-only SPI (the display has no MISO). Reads give zeros.
pub struct SimSpi<B>(pub Shared<B>);

impl<B> spi::ErrorType for SimSpi<B> {
    type Error = Infallible;
}

impl<B: Board> SpiBus<u8> for SimSpi<B> {
    fn read(&mut self, words: &mut [u8]) -> Result<(), Infallible> {
        words.fill(0);
        Ok(())
    }
    fn write(&mut self, words: &[u8]) -> Result<(), Infallible> {
        self.0.borrow_mut().spi_write(words);
        Ok(())
    }
    fn transfer(&mut self, read: &mut [u8], write: &[u8]) -> Result<(), Infallible> {
        self.write(write)?;
        read.fill(0);
        Ok(())
    }
    fn transfer_in_place(&mut self, words: &mut [u8]) -> Result<(), Infallible> {
        self.write(words)?;
        words.fill(0);
        Ok(())
    }
    fn flush(&mut self) -> Result<(), Infallible> {
        Ok(())
    }
}
