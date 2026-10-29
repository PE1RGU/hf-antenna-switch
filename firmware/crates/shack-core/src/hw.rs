//! What the shack logic needs from the hardware. The ESP32-C3 target and the
//! simulator each give one implementation.

use link_proto::Radio;

pub trait ShackHw {
    type I2c: embedded_hal::i2c::I2c;

    /// The board I2C bus (PCA9539 at 0x74).
    fn i2c(&mut self) -> &mut Self::I2c;
    /// PERMIT_R1..R3 (direct GPIO, D-83).
    fn set_permit(&mut self, radio: Radio, on: bool);
    fn set_wdi(&mut self, high: bool);
    fn set_latch_clr(&mut self, high: bool);
    /// GPIO21: high = no SAFE loop current.
    fn safe_lost(&mut self) -> bool;
    /// Data link to the box (UART, 9600 8N1).
    fn uart_write(&mut self, bytes: &[u8]);
    fn uart_read(&mut self) -> Option<u8>;
}
