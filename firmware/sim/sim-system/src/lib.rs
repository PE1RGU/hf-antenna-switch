//! The whole system in the emulator: both firmwares on both boards, joined by the
//! Cat6 cable (phase P6).
//!
//! [`SystemSim`] lives in `sim-shack` (module `system`), so the terminal UI of the
//! `sim-shack` program can run it. This crate re-exports it and holds the system
//! scenario tests (`tests/scenarios.rs`).
//!
//! ```
//! use sim_system::SystemSim;
//!
//! let mut s = SystemSim::new();
//! s.start();
//! assert!(s.shack.shack.link_up());
//! ```

pub use sim_shack::system::*;
