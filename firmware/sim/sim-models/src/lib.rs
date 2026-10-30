//! Part and board models. Each part follows its datasheet; each board follows
//! its KiCad netlist and the logic in hardware/unit/verify.
//!
//! # Where this crate sits
//!
//! This crate is the middle layer of the emulator. It uses the plumbing of
//! `sim-core` (virtual time, trace, I2C runner, UART line) and gives models of real
//! parts. The harness in `sim-shack` runs the firmware logic on the board model.
//!
//! The models work at the HAL boundary (PLAN.md section 2): they see what the MCU
//! pins see, as register writes, pin levels and bytes. They do not model analogue
//! voltages, rise times or bit timing on I2C and SPI.
//!
//! # Models
//!
//! | Module | Part | Interface | Source |
//! |---|---|---|---|
//! | [`pca9539`] | PCA9539 16-bit I/O expander, with INT | [`I2cDevice`](sim_core::i2c::I2cDevice) | Datasheet, rule F1 |
//! | [`tps3823`] | TPS3823A-33 supervisor and watchdog | `update(now, vdd_ok, wdi)` | SLVS165O, C-19 |
//! | [`lvc1g74`] | 74LVC1G74 D flip-flop | `update(pre_n, clr_n, clk, d)` | Datasheet, D-59, D-75 |
//! | [`st7789`] | ST7789 display controller | `spi(dc, bytes)` | Datasheet, D-187 |
//! | [`rt1`] | TE RT1 power relay | `update(now, coil)` | RT1pb rev 4 (timing), verify_logic.py section 8 |
//! | [`shack`] | The shack interface board | [`Board`](sim_core::hal::Board) | verify_system.py sections 1, 3, 4 |
//! | [`box_board`] | The box: RF board and controller board | [`Board`](sim_core::hal::Board) | verify_logic.py, verify_system.py section 1 |
//!
//! # How the board model works
//!
//! [`shack::ShackBoard`] owns one instance of each part. The test changes the
//! outside world with [`shack::ShackBoard::set_env`] (power, KILL, cable, radios)
//! and moves time with [`shack::ShackBoard::step_to`] or [`shack::ShackBoard::run`].
//! After each change the board calls its private `settle` function. `settle`
//! updates every part from the present levels, works out the derived
//! [`shack::Signals`] (TX_EN, INH, keying), and records each change in the trace.
//!
//! # How to add a part model
//!
//! 1. Make a new module with a struct for the part. Put the datasheet facts in the
//!    module header: part number, document, the values the model uses.
//! 2. Give the struct its interface. For an I2C part, implement
//!    [`sim_core::i2c::I2cDevice`]. For a logic or timing part, write an `update`
//!    function that takes the input levels (and `now` if it has timing) and returns
//!    the output level, as [`lvc1g74::Lvc1g74::update`] does.
//! 3. Add the part as a field of the board struct, and wire it in the board's
//!    `settle` function: feed it the board signals, and use its outputs. For an I2C
//!    part, also add its address in the board's `i2c` function.
//! 4. Add unit tests in the module for the datasheet behaviour (reset values, edges,
//!    time-outs), and a board test in `tests/` for the wiring.
//!
//! # Example
//!
//! The PCA9539 after reset: all pins are inputs, the output register is 0xFFFF.
//!
//! ```
//! use sim_core::i2c::I2cDevice;
//! use sim_models::pca9539::Pca9539;
//!
//! let mut exp = Pca9539::new();
//! assert_eq!(exp.output_reg(), 0xFFFF);
//! assert_eq!(exp.config_reg(), 0xFFFF); // 1 = input
//!
//! // Read the configuration pair (registers 6, 7) over I2C.
//! exp.write(&[6]).unwrap();
//! let mut buf = [0u8; 2];
//! exp.read(&mut buf).unwrap();
//! assert_eq!(buf, [0xFF, 0xFF]);
//! ```

pub mod box_board;
pub mod lvc1g74;
pub mod pca9539;
pub mod rt1;
pub mod shack;
pub mod st7789;
pub mod tps3823;
