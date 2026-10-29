//! Box end of the link: answers only (link-protocol.md sections 5 and 6).
//!
//! Keeps the last seq and its result, so a repeated frame is not run twice.
//! Hello clears that store, so a restarted shack cannot hit an old seq.
//!
//! Use per received frame:
//!
//! 1. Give the [`Decoder`](crate::Decoder) result to [`BoxLink::receive`].
//! 2. On [`Incoming::Execute`], run the command, answer, then call
//!    [`BoxLink::complete`] with the result. On [`Incoming::Repeat`], answer
//!    the present Status with the stored result. On [`Incoming::BadArg`],
//!    answer BadArg and call `complete`.
//!
//! Call [`BoxLink::check_timeout`] often (each main loop pass). When it gives
//! true, apply F13 and P-02: with a permit out, open SAFE (MCU_EN_N = 1) and
//! keep K0; with no permit out, hold the routes and flag the fault.

use crate::frame::{DecodeError, Frame};
use crate::msg::{Command, ResultCode};
use crate::{LINK_TIMEOUT, Ms};

/// What the box must do with a received frame.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Incoming {
    /// New command: run it, answer, then call `complete` with its result.
    Execute(Frame<Command>),
    /// Same seq as the last command: do not run it; answer the present state with `result`.
    Repeat {
        /// The seq to answer with.
        seq: u8,
        /// The stored result of the first run.
        result: ResultCode,
    },
    /// Good CRC, value out of range: answer BadArg with this seq, then call `complete`.
    BadArg {
        /// The seq to answer with.
        seq: u8,
    },
}

/// Box end of the link. Holds the seq store and the link time-out.
///
/// The box never sends on its own; it only answers. So this state machine has
/// no transmit side.
#[derive(Debug, Default)]
pub struct BoxLink {
    /// Seq and result of the last completed command.
    last: Option<(u8, ResultCode)>,
    /// Time of the last valid frame. `None` until the first one, so a box that
    /// never heard the shack does not report a lost link.
    last_rx: Option<Ms>,
    /// The loss is reported; stays true until the next valid frame.
    lost: bool,
}

impl BoxLink {
    /// A box link that has not received a frame yet.
    pub fn new() -> Self {
        Self::default()
    }

    /// Handle a decoder result at time `now`.
    ///
    /// Frames that fail COBS, CRC, type or length give `None`: drop them and
    /// send nothing. Every other frame counts as a valid frame for the link
    /// time-out, a BadArg frame too (its CRC is good).
    pub fn receive(
        &mut self,
        now: Ms,
        frame: Result<Frame<Command>, DecodeError>,
    ) -> Option<Incoming> {
        let incoming = match frame {
            Ok(f) if matches!(f.msg, Command::Hello { .. }) => {
                self.last = None;
                Incoming::Execute(f)
            }
            // The shack gives each new command a new seq, so the same seq
            // means a resend after a lost answer: do not run it again.
            Ok(f) => match self.last {
                Some((seq, result)) if seq == f.seq => Incoming::Repeat { seq, result },
                _ => Incoming::Execute(f),
            },
            Err(DecodeError::BadValue { seq }) => Incoming::BadArg { seq },
            Err(_) => return None,
        };
        self.last_rx = Some(now);
        self.lost = false;
        Some(incoming)
    }

    /// Store the result of the command with this seq. Not needed for Hello.
    pub fn complete(&mut self, seq: u8, result: ResultCode) {
        self.last = Some((seq, result));
    }

    /// True once when the link is lost: no valid frame for
    /// [`LINK_TIMEOUT`] (300 ms) after at least one valid frame. The caller
    /// applies F13 and P-02. The next valid frame clears the loss.
    pub fn check_timeout(&mut self, now: Ms) -> bool {
        let Some(t) = self.last_rx else { return false };
        if self.lost || now.saturating_sub(t) < LINK_TIMEOUT {
            return false;
        }
        self.lost = true;
        true
    }

    /// True from a reported loss until the next valid frame.
    pub fn is_lost(&self) -> bool {
        self.lost
    }
}
