//! Shack interface logic: the firmware brain of the shack interface, without any
//! direct hardware access.
//!
//! # Where this crate sits
//!
//! The shack interface sits between the radios, the host (Mac or Pi) and the box
//! at the antenna end. This crate holds all of its decisions: the TX handshake with
//! the box, the permits, the keys, the host commands, the stored settings and the
//! display pages. Two programs use it:
//!
//! - the ESP32-C3 firmware (`targets/shack-esp32c3`), on the real board;
//! - the simulator (`sim/sim-shack`), on the Mac, with models of the box and the radios.
//!
//! The crate is `no_std`: it does not use the Rust standard library, only `core`.
//! So it runs on the ESP32-C3 without an operating system, and the same code runs
//! in the simulator.
//!
//! # Main types
//!
//! - [`shack::Shack`]: the state machine. It holds every state of the interface.
//! - [`hw::ShackHw`]: the boundary between the logic and the hardware.
//! - [`board`]: the pin map (GPIO numbers, PCA9539 pins).
//! - [`config::Config`]: the stored settings (names, routes, bias-T, page).
//!
//! # The `ShackHw` trait
//!
//! A trait is a list of functions that a type promises to supply. [`hw::ShackHw`]
//! lists everything the logic needs from the board: the I2C bus, the PERMIT lines,
//! WDI, LATCH_CLR, the SAFE sense, the box UART, the USB host port, the display SPI
//! and the flash for the stored settings. The ESP32-C3 glue implements it with real
//! peripherals. The simulator implements it with models. The logic never touches a
//! register itself, so it can be tested on the Mac before the board exists.
//!
//! # The tick model
//!
//! The main loop calls [`Shack::tick`](shack::Shack::tick) once every
//! [`TICK`](shack::TICK) (10 ms) with the present time in ms. Nothing in the crate
//! blocks or waits: each tick does a short step of work and returns. A state machine
//! is a value that remembers where it is (for example "TX requested, no permit yet")
//! and moves to the next state when an input changes. One tick does this, in order:
//!
//! 1. Toggle WDI (the supervisor watchdog) and read the SAFE sense.
//! 2. Load the stored settings (first tick only).
//! 3. Set up the PCA9539 expander if it is not ready (F1 order), then give the
//!    one LATCH_CLR edge after start-up. If the expander does not answer, answer
//!    the host and stop the tick here: TX stays off.
//! 4. Read the expander inputs (TX sense, band data, KILL, LATCHED). A failed read
//!    or a changed configuration means the expander was reset: drop all permits,
//!    answer the host and stop the tick here.
//! 5. Read the box link replies and check the link time-out.
//! 6. Read and answer the host lines; check the host keep-alive.
//! 7. Restore the stored routes and bias after a link up.
//! 8. Step the TX handshake of R2 and R3.
//! 9. Send the next queued command (or a Poll) to the box.
//! 10. Set the outputs: permits that go off, the expander, permits that go on.
//! 11. Send events to the host, send one display chunk, save the settings when due.
//!
//! # Safety idea
//!
//! The firmware asks; the hardware decides. The SAFE latch, the fault latch, the
//! supervisor and the box gate TX in hardware. The firmware can only make things
//! safer: it never clears the SAFE latch, and it never gives a permit that the box
//! did not report (D-63). When a TX must end, it inhibits first (PERMIT and KEY off)
//! and only then tells the box (F14).
//!
//! # Example
//!
//! ```ignore
//! let mut shack = Shack::new();
//! loop {
//!     shack.tick(now_ms(), &mut hw); // hw implements ShackHw
//!     while let Some(e) = shack.take_event() {
//!         log(e);
//!     }
//!     wait_until_next_tick();
//! }
//! ```
#![no_std]

pub mod board;
pub mod config;
pub mod hw;
pub mod shack;
