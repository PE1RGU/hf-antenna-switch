//! Box end of the link: answers only (link-protocol.md sections 5 and 6).
//!
//! Keeps the last seq and its result, so a repeated frame is not run twice.
//! Hello clears that store, so a restarted shack cannot hit an old seq.

use crate::frame::{DecodeError, Frame};
use crate::msg::{Command, ResultCode};
use crate::{LINK_TIMEOUT, Ms};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Incoming {
    /// New command: run it, answer, then call `complete` with its result.
    Execute(Frame<Command>),
    /// Same seq as the last command: do not run it; answer the present state with `result`.
    Repeat { seq: u8, result: ResultCode },
    /// Good CRC, value out of range: answer BadArg with this seq, then call `complete`.
    BadArg { seq: u8 },
}

#[derive(Debug, Default)]
pub struct BoxLink {
    last: Option<(u8, ResultCode)>,
    last_rx: Option<Ms>,
    lost: bool,
}

impl BoxLink {
    pub fn new() -> Self {
        Self::default()
    }

    /// A decoder result. Frames that fail COBS, CRC, type or length give `None`.
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

    /// True once when the link is lost: no valid frame for LINK_TIMEOUT
    /// after at least one valid frame. The caller applies F13 and P-02.
    pub fn check_timeout(&mut self, now: Ms) -> bool {
        let Some(t) = self.last_rx else { return false };
        if self.lost || now.saturating_sub(t) < LINK_TIMEOUT {
            return false;
        }
        self.lost = true;
        true
    }

    pub fn is_lost(&self) -> bool {
        self.lost
    }
}
