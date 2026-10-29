//! Shack to box data link (docs/design/link-protocol.md).
//!
//! Pure code: no hardware calls, no allocation, no panics on any input.
//! Time comes in as milliseconds from the caller, so the simulator can drive it.
#![no_std]

pub mod box_link;
mod cobs;
pub mod frame;
pub mod msg;
pub mod shack_link;

pub use frame::{DecodeError, Decoder, Frame};
pub use msg::*;

/// Protocol version, sent in Hello and HelloReply.
pub const VERSION: u8 = 1;

/// Time in milliseconds, from any fixed start.
pub type Ms = u64;

/// Shack: send a Poll when no frame went out for this long (section 5).
pub const POLL_PERIOD: Ms = 50;
/// Shack: resend the frame in flight when no answer came for this long (section 6).
pub const ANSWER_TIMEOUT: Ms = 60;
/// Both ends: link lost when no valid frame came for this long (section 6).
pub const LINK_TIMEOUT: Ms = 300;
