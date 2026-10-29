//! Shack to box data link (spec: `docs/design/link-protocol.md`).
//!
//! The shack interface (ESP32-C3) and the outdoor relay box talk over two
//! opto current loops in the Cat6 cable (pairs 1 and 4, D-56, D-58). The
//! line is a plain UART: 9600 baud, 8N1. This crate holds everything both
//! ends need to use that line. Both ends use the same code, so they cannot
//! disagree on the format.
//!
//! ```text
//!  Mac or Pi --USB text--> shack interface ==Cat6, 9600 baud==> relay box
//!                          ShackLink (master)                   BoxLink (answers)
//!                          Frame::encode  ---- frame bytes ---> Decoder
//!                          Decoder        <--- frame bytes ---- Frame::encode
//! ```
//!
//! The link carries routes, the TX handshake for R2 and R3 (D-63, F13, F14),
//! bias-T commands (D-54) and the box status. It does not carry the safety
//! lines: PTT (pair 2) and the SAFE loop (pair 3) stay in hardware. Nothing
//! in this crate can clear a latch or close a safety line.
//!
//! # Main parts
//!
//! - [`msg`]: the messages. [`Command`] goes from the shack to the box,
//!   [`Reply`] goes back. [`Status`] is the box state in each answer.
//! - [`frame`]: one message on the wire. [`Frame::encode`] makes the bytes;
//!   [`Decoder`] takes the received bytes one at a time and gives frames back.
//! - [`shack_link`]: [`ShackLink`](shack_link::ShackLink), the shack state
//!   machine. It sends Hello, commands and Polls, resends lost frames and
//!   finds a lost link.
//! - [`box_link`]: [`BoxLink`](box_link::BoxLink), the box state machine. It
//!   finds repeated frames, so a command never runs twice, and finds a lost
//!   link.
//!
//! # Rules
//!
//! The crate is `no_std`: it does not use the Rust standard library, so it
//! runs on the ESP32-C3 without an operating system. It does not allocate
//! memory and does not panic on any input bytes. It makes no hardware calls.
//! Time comes in from the caller as milliseconds ([`Ms`]), so the simulator
//! can drive the state machines with virtual time.
//!
//! # Example
//!
//! Encode a SetRoute command and decode it again, byte by byte, as the box
//! does with the UART bytes:
//!
//! ```
//! use link_proto::frame::MAX_WIRE;
//! use link_proto::{Col, Command, Decoder, Frame, Radio, Route};
//!
//! // Shack: route R2 to A3 for TX and RX.
//! let frame = Frame {
//!     seq: 7,
//!     msg: Command::SetRoute {
//!         radio: Radio::R2,
//!         route: Route { tx: Col::A3, rx: Col::A3 },
//!     },
//! };
//! let mut wire = [0u8; MAX_WIRE];
//! let n = frame.encode(&mut wire);
//! assert_eq!(n, 9); // link-protocol.md section 4: 9 bytes on the wire.
//! assert_eq!(wire[n - 1], 0x00); // The delimiter ends the frame.
//!
//! // Box: feed the bytes to the decoder. A result comes at the delimiter.
//! let mut decoder = Decoder::new();
//! let mut got = None;
//! for &b in &wire[..n] {
//!     if let Some(result) = decoder.push::<Command>(b) {
//!         got = Some(result);
//!     }
//! }
//! assert_eq!(got, Some(Ok(frame)));
//! ```
#![no_std]

pub mod box_link;
mod cobs;
pub mod frame;
pub mod msg;
pub mod shack_link;

pub use frame::{DecodeError, Decoder, Frame};
pub use msg::*;

/// Protocol version, sent in Hello and HelloReply. The shack sends commands
/// only when the box reports the same version (link-protocol.md section 5).
pub const VERSION: u8 = 1;

/// Time in milliseconds, from any fixed start (for example power-up).
///
/// The caller gives the time to each call. The firmware uses its timer; the
/// simulator uses virtual time.
pub type Ms = u64;

/// Shack: send a Poll when no frame went out for this long, in ms
/// (link-protocol.md section 5). The Poll gets the box status.
pub const POLL_PERIOD: Ms = 50;
/// Shack: resend the frame in flight when no answer came for this long, in ms
/// (section 6). The resend keeps the same seq.
pub const ANSWER_TIMEOUT: Ms = 60;
/// Both ends: the link is lost when no valid frame came for this long, in ms
/// (section 6). This is 6 poll periods, well below the box watchdog minimum
/// of 0.9 s (C-19), so the firmware acts before the watchdog does.
pub const LINK_TIMEOUT: Ms = 300;
