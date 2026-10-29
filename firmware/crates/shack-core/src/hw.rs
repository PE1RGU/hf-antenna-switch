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
    /// Host port (USB Serial/JTAG, host-protocol.md).
    fn usb_write(&mut self, bytes: &[u8]);
    fn usb_read(&mut self) -> Option<u8>;
    /// Display SPI (SCK IO2, MOSI IO9, D-180). D/C and RST are on the expander.
    fn spi_write(&mut self, bytes: &[u8]);
    /// Display frame buffer, `shack_ui::fb::BYTES` long (a static on the target).
    fn framebuffer(&mut self) -> &mut [u8];
    /// Send `framebuffer()[start..end]` over the display SPI.
    fn spi_write_framebuffer(&mut self, start: usize, end: usize);
    /// Stored settings (host-protocol.md 8a): copy the stored record into `buf`,
    /// return its length; 0 when there is none. Flash on the target.
    fn config_load(&mut self, buf: &mut [u8]) -> usize;
    fn config_save(&mut self, record: &[u8]);
}
