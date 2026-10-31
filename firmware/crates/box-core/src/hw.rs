//! What the box logic needs from the hardware. The ESP32-C3 target and the
//! simulator each give one implementation.
//!
//! [`RelayBox::tick`](crate::relay_box::RelayBox::tick) calls these functions;
//! nothing else in the crate touches the hardware. Each function must return at
//! once: the main loop runs every 1 ms, so no function may block or wait.

/// The hardware boundary of the box controller.
///
/// The pin numbers are in [`board::gpio`](crate::board::gpio).
pub trait BoxHw {
    /// The I2C bus type (any `embedded-hal` 1.0 I2C driver).
    type I2c: embedded_hal::i2c::I2c;

    /// The I2C bus to the RF board: the four PCA9539 at 0x74 to 0x77.
    fn i2c(&mut self) -> &mut Self::I2c;
    /// WDI of the supervisor (IO1). The logic toggles it from the main loop
    /// only, never from a timer (verify_logic.py section 10, rule 1).
    fn set_wdi(&mut self, high: bool);
    /// LATCH_CLR of the fault latch (IO3). The logic gives one rising edge after
    /// the boot delay, and never again (rule 2).
    fn set_latch_clr(&mut self, high: bool);
    /// MCU_EN_N (IO4), active low. Low asks for RLY_EN and closes READY; high
    /// opens the SAFE loop (F13).
    fn set_mcu_en_n(&mut self, high: bool);
    /// KILL (IO5): `true` = no SAFE loop current, so the relays are off in hardware.
    fn kill(&mut self) -> bool;
    /// Data link to the shack (UART, 9600 8N1): send these bytes.
    fn uart_write(&mut self, bytes: &[u8]);
    /// Data link to the shack: the next received byte, or `None` when there is none.
    fn uart_read(&mut self) -> Option<u8>;
}
