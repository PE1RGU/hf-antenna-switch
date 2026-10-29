//! What the shack logic needs from the hardware. The ESP32-C3 target and the
//! simulator each give one implementation.
//!
//! [`Shack::tick`](crate::shack::Shack::tick) calls these functions; nothing else in
//! the crate touches the hardware. Each function must return at once: the main loop
//! has a 10 ms rhythm (WDI, link, permits), so no function may block or wait.

use link_proto::Radio;

/// The hardware boundary of the shack interface.
///
/// Implement it once per platform: the ESP32-C3 glue drives the real pins and
/// peripherals, the simulator drives its models. The pin numbers are in
/// [`board`](crate::board).
pub trait ShackHw {
    /// The I2C bus type (any `embedded-hal` 1.0 I2C driver).
    type I2c: embedded_hal::i2c::I2c;

    /// The board I2C bus (PCA9539 at 0x74).
    fn i2c(&mut self) -> &mut Self::I2c;
    /// PERMIT_R1..R3 (direct GPIO, D-83). `true` = permit out: the TX INH of that
    /// radio may release. The logic sets a permit only when the box reports it
    /// (R2, R3) or the R1 conditions hold (C-1).
    fn set_permit(&mut self, radio: Radio, on: bool);
    /// WDI of the supervisor (GPIO1, D-59). The logic toggles it once per tick from
    /// the main loop, never from a timer, so a hung loop stops the kicks.
    fn set_wdi(&mut self, high: bool);
    /// LATCH_CLR of the fault latch (GPIO3, D-59). The logic gives a rising edge
    /// (`true` then `false`) once after start-up, and again only on `clearfault`.
    /// The latch ignores the edge while RESET_N is low.
    fn set_latch_clr(&mut self, high: bool);
    /// GPIO21: high = no SAFE loop current. Read once per tick; `true` means the
    /// SAFE loop is open.
    fn safe_lost(&mut self) -> bool;
    /// Data link to the box (UART, 9600 8N1): send these bytes.
    fn uart_write(&mut self, bytes: &[u8]);
    /// Data link to the box: the next received byte, or `None` when there is none.
    fn uart_read(&mut self) -> Option<u8>;
    /// Host port (USB Serial/JTAG, host-protocol.md): send these bytes.
    fn usb_write(&mut self, bytes: &[u8]);
    /// Host port: the next received byte, or `None` when there is none.
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
    /// Stored settings: write this record to flash, in place of the old one. The
    /// logic calls it 2 s after the last change, so a burst of changes gives one write.
    fn config_save(&mut self, record: &[u8]);
}
