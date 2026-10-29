//! embedded-hal adapters. On the target, esp-hal gives these traits; in the
//! simulator, these adapters forward each call to the board model.

use crate::SimTime;
use embedded_hal::digital::{ErrorType as PinErrorType, InputPin, OutputPin};
use embedded_hal::i2c::{self, I2c, Operation, SevenBitAddress};
use embedded_hal::spi::{self, SpiBus};
use std::cell::RefCell;
use std::convert::Infallible;
use std::rc::Rc;

/// What the MCU sees of a board: its pins, its I2C bus, its SPI bus, its UART.
/// Pin numbers are ESP32-C3 GPIO numbers.
pub trait Board {
    fn now(&self) -> SimTime;
    fn i2c(&mut self, addr: u8, ops: &mut [Operation<'_>]) -> Result<(), i2c::ErrorKind>;
    fn gpio_write(&mut self, pin: u8, high: bool);
    fn gpio_read(&mut self, pin: u8) -> bool;
    fn spi_write(&mut self, data: &[u8]);
    fn uart_write(&mut self, byte: u8);
    fn uart_read(&mut self) -> Option<u8>;
    /// Host port (USB). Bytes arrive at once: USB is fast against the 10 ms tick.
    fn usb_write(&mut self, byte: u8);
    fn usb_read(&mut self) -> Option<u8>;
}

pub type Shared<B> = Rc<RefCell<B>>;

pub fn shared<B>(board: B) -> Shared<B> {
    Rc::new(RefCell::new(board))
}

pub struct SimI2c<B>(pub Shared<B>);

impl<B> i2c::ErrorType for SimI2c<B> {
    type Error = i2c::ErrorKind;
}

impl<B: Board> I2c<SevenBitAddress> for SimI2c<B> {
    fn transaction(&mut self, addr: u8, ops: &mut [Operation<'_>]) -> Result<(), Self::Error> {
        self.0.borrow_mut().i2c(addr, ops)
    }
}

pub struct SimOutput<B> {
    pub board: Shared<B>,
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

pub struct SimInput<B> {
    pub board: Shared<B>,
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
