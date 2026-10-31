//! Box logic: the firmware brain of the relay matrix at the antenna end.
//!
//! # Where this crate sits
//!
//! The box (Shack Relay Matrix, unit 1) holds the RF board with 37 relay
//! positions and the controller board with the ESP32-C3 and the safety gate. The
//! shack interface drives it over the data link (docs/design/link-protocol.md).
//!
//! The crate is `no_std`, as `shack-core`: the same code runs on the ESP32-C3 and
//! in the simulator (`sim/sim-box`).
//!
//! # Main parts
//!
//! - [`relay_box::RelayBox`]: the state machine. Start-up (F11, F1), the switching
//!   sequence (F10), the box side of the TX handshake and the link time-out (F13).
//! - [`crossbar`]: the state check H1 to H4 (F6).
//! - [`hw::BoxHw`]: the boundary between the logic and the hardware.
//! - [`board`]: the pin map. The emulator's box board model (`sim-models`) uses
//!   it too, so the model and the firmware cannot disagree about a pin.
//!
//! # Safety idea
//!
//! The hardware decides; the firmware can only make things safer. The safety
//! gate, the fault latch, the supervisor and the SAFE loop stop the relays in
//! hardware. The firmware never moves a relay under RF, never closes a state
//! that breaks H1 to H4, and opens SAFE when it loses control with a permit out.

#![no_std]

pub mod board;
pub mod crossbar;
pub mod hw;
pub mod relay_box;
