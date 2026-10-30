//! Box logic: the firmware brain of the relay matrix at the antenna end.
//!
//! # Where this crate sits
//!
//! The box (Shack Relay Matrix, unit 1) holds the RF board with 37 relay
//! positions and the controller board with the ESP32-C3 and the safety gate. The
//! shack interface drives it over the data link (docs/design/link-protocol.md).
//!
//! The crate is `no_std`, as `shack-core`: the same code runs on the ESP32-C3 and
//! in the simulator.
//!
//! # Status
//!
//! Phase P4 (firmware/PLAN.md) gives only the pin map, [`board`]. The emulator's
//! box board model (`sim-models`) uses it, so the model and the firmware cannot
//! disagree about a pin. The state machine (start-up F11, crossbar check F6,
//! switching sequence F10, the box side of the TX handshake) follows in P5.

#![no_std]

pub mod board;
