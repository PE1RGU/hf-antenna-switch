//! Simulator core: virtual time, trace, I2C and UART plumbing, and the
//! embedded-hal adapters that stand where the ESP32-C3 HAL stands on the target.
//!
//! The models are plain Rust structs. Time only moves when the test moves it.
//!
//! # Where this crate sits
//!
//! The emulator has three layers:
//!
//! 1. `sim-core` (this crate): the parts that every board model needs. It knows
//!    nothing about the shack interface.
//! 2. `sim-models`: the part models (PCA9539, TPS3823, 74LVC1G74, ST7789) and the
//!    shack board model. The board model uses the types of this crate.
//! 3. `sim-shack`: the harness that runs the firmware logic on the board model.
//!
//! The emulator works at the HAL boundary (PLAN.md section 2). The firmware logic
//! calls the hardware through traits. On the ESP32-C3, `esp-hal` gives these
//! traits. In the emulator, a board model gives them. The emulator does not run
//! RISC-V instructions.
//!
//! # Main types
//!
//! - [`SimTime`]: virtual time in microseconds. It is an instant and a duration.
//! - [`Trace`]: a time-stamped record of signal changes, I2C transfers, UART bytes
//!   and notes. Tests read it after a run.
//! - [`i2c::I2cDevice`] and [`i2c::transact`]: a bus target, and the function that
//!   runs one I2C transaction on it and records it in the trace.
//! - [`uart::UartLine`]: one direction of a UART link with real byte timing, a cut
//!   switch and a fault filter.
//! - [`hal::Board`]: what the MCU sees of a board. The adapters in [`hal`]
//!   ([`hal::SimI2c`], [`hal::SimOutput`], [`hal::SimInput`], [`hal::SimSpi`])
//!   implement the `embedded-hal` 1.0 traits on top of it.
//!
//! A trait in Rust is a set of functions that a type promises to have. The firmware
//! asks for "something that implements `I2c`"; it does not know if that is the
//! real peripheral or a model.
//!
//! # How the parts work together
//!
//! A board model (for example `sim_models::shack::ShackBoard`) implements
//! [`hal::Board`]. It owns a [`Trace`], its part models and its [`uart::UartLine`]s.
//! The harness puts the board in a [`hal::Shared`] value, so the firmware glue and
//! the test can both reach it. Each I2C call goes through [`i2c::transact`], which
//! calls the part model and records the transfer. The test moves time forward and
//! then reads the trace.
//!
//! # Example
//!
//! Virtual time, and the byte time of a 9600 baud line (8N1: 10 bits per byte):
//!
//! ```
//! use sim_core::SimTime;
//! use sim_core::uart::UartLine;
//!
//! assert_eq!(SimTime::ms(2) + SimTime::us(500), SimTime::us(2_500));
//! // Subtraction saturates: an earlier minus a later time is zero.
//! assert_eq!(SimTime::ms(1) - SimTime::ms(5), SimTime::ZERO);
//!
//! let mut line = UartLine::new(9600);
//! assert_eq!(line.byte_time(), SimTime::us(1041));
//! line.send(SimTime::ZERO, b'A');
//! assert_eq!(line.recv(SimTime::us(1040)), None); // still on the wire
//! assert_eq!(line.recv(SimTime::us(1041)), Some(b'A'));
//! ```

pub mod hal;
pub mod i2c;
pub mod time;
pub mod trace;
pub mod uart;

pub use time::SimTime;
pub use trace::{Trace, TraceEvent, TraceKind};
