//! Simulator core: virtual time, trace, I2C and UART plumbing, and the
//! embedded-hal adapters that stand where the ESP32-C3 HAL stands on the target.
//!
//! The models are plain Rust structs. Time only moves when the test moves it.

pub mod hal;
pub mod i2c;
pub mod time;
pub mod trace;
pub mod uart;

pub use time::SimTime;
pub use trace::{Trace, TraceEvent, TraceKind};
