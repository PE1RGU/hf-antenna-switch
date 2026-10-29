//! Shack end of the link: the master (link-protocol.md sections 5 and 6).
//!
//! One frame in flight at a time. A lost answer resends the same seq every
//! ANSWER_TIMEOUT. No valid answer for LINK_TIMEOUT: link lost, back to Hello.
//!
//! States, in short:
//!
//! ```text
//!  down: send Hello ----HelloReply, same version----> up: send commands and Polls
//!    ^                                                  |
//!    +------------- no valid answer for 300 ms ---------+   (Event::Lost)
//! ```
//!
//! Use in the main loop, at time `now`:
//!
//! 1. [`ShackLink::transmit`]: encode and send the frame it gives, if any.
//! 2. For each frame from the [`Decoder`](crate::Decoder):
//!    [`ShackLink::receive`].
//! 3. [`ShackLink::check_timeout`].
//!
//! Give a command with [`ShackLink::submit`]. Its answer comes back as
//! [`Event::Reply`].

use crate::frame::Frame;
use crate::msg::{Command, HelloInfo, Reply, Status};
use crate::{ANSWER_TIMEOUT, LINK_TIMEOUT, Ms, POLL_PERIOD, VERSION};

/// Something the shack application must know about the link.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Event {
    /// HelloReply with our version: commands can go.
    Up(HelloInfo),
    /// HelloReply with another version. The link stays in Hello; no commands go.
    VersionMismatch(HelloInfo),
    /// Answer to a command (Poll included).
    Reply {
        /// The command that was answered.
        cmd: Command,
        /// The box state in the answer, with the result of `cmd`.
        status: Status,
    },
    /// No valid answer for LINK_TIMEOUT. The caller drops all permits and keys.
    /// `unanswered` was in flight (it may or may not have run in the box);
    /// `unsent` never left the shack.
    /// After the link is back, the shack sends TxEnd for each radio that
    /// had a permit, after the F14 wait (link-protocol.md section 6).
    Lost {
        /// The command in flight (never a Poll), if any.
        unanswered: Option<Command>,
        /// The queued command that was not sent, if any.
        unsent: Option<Command>,
    },
}

/// The frame sent and not answered yet.
#[derive(Clone, Copy, Debug)]
struct InFlight {
    seq: u8,
    cmd: Command,
    /// Time of the last send, for the answer time-out.
    sent: Ms,
}

/// Shack end of the link: the master. Sends Hello, commands and Polls.
///
/// It holds at most one queued command and one frame in flight. The shack
/// application keeps its own queue in front of it.
#[derive(Debug, Default)]
pub struct ShackLink {
    /// HelloReply with our version seen, no time-out since.
    up: bool,
    /// A version mismatch is reported once, not at every Hello.
    mismatch_reported: bool,
    /// Seq of the last new frame. +1 for each new frame, wraps after 255.
    seq: u8,
    /// Submitted command, waiting for the frame in flight to be answered.
    queued: Option<Command>,
    in_flight: Option<InFlight>,
    /// Time of the last send, for the Poll period.
    last_tx: Option<Ms>,
    /// Time of the last valid answer, for the link time-out.
    last_rx: Ms,
}

impl ShackLink {
    /// A link that is down. The first [`transmit`](Self::transmit) sends Hello.
    pub fn new() -> Self {
        Self::default()
    }

    /// True while the link is up: Hello done with the same version, no time-out since.
    pub fn is_up(&self) -> bool {
        self.up
    }

    /// Queue one command. Refused (returned) while the link is down or a command waits.
    ///
    /// The command goes out at the next [`transmit`](Self::transmit) after
    /// the frame in flight is answered. The link sends Hello and Poll by itself.
    pub fn submit(&mut self, cmd: Command) -> Result<(), Command> {
        if !self.up || self.queued.is_some() {
            return Err(cmd);
        }
        self.queued = Some(cmd);
        Ok(())
    }

    /// True while a submitted command has not been answered yet.
    pub fn busy(&self) -> bool {
        self.queued.is_some()
            || self
                .in_flight
                .is_some_and(|f| !matches!(f.cmd, Command::Poll))
    }

    /// The next frame to send, if any. Call often; it sends at most one frame per answer.
    ///
    /// In this order: a resend of the frame in flight after
    /// [`ANSWER_TIMEOUT`] (same seq); Hello while the link is down; the queued
    /// command; a Poll when nothing went out for [`POLL_PERIOD`].
    pub fn transmit(&mut self, now: Ms) -> Option<Frame<Command>> {
        // One frame in flight: wait for its answer, or resend it with the same
        // seq, so the box can see that it is a repeat.
        if let Some(f) = &mut self.in_flight {
            if now.saturating_sub(f.sent) < ANSWER_TIMEOUT {
                return None;
            }
            f.sent = now;
            self.last_tx = Some(now);
            return Some(Frame {
                seq: f.seq,
                msg: f.cmd,
            });
        }
        let cmd = if !self.up {
            Command::Hello { version: VERSION }
        } else if let Some(c) = self.queued.take() {
            c
        } else if self
            .last_tx
            .is_none_or(|t| now.saturating_sub(t) >= POLL_PERIOD)
        {
            Command::Poll
        } else {
            return None;
        };
        self.seq = self.seq.wrapping_add(1);
        self.in_flight = Some(InFlight {
            seq: self.seq,
            cmd,
            sent: now,
        });
        self.last_tx = Some(now);
        Some(Frame {
            seq: self.seq,
            msg: cmd,
        })
    }

    /// A valid frame from the box. Answers that do not match the frame in flight are ignored.
    ///
    /// Give only frames that decoded without error. An old answer with
    /// another seq (for example a late answer to an earlier frame) is ignored.
    pub fn receive(&mut self, now: Ms, frame: Frame<Reply>) -> Option<Event> {
        let f = self.in_flight.filter(|f| f.seq == frame.seq)?;
        self.in_flight = None;
        match (f.cmd, frame.msg) {
            (Command::Hello { .. }, Reply::Hello(info)) => {
                self.last_rx = now;
                if info.version == VERSION {
                    self.up = true;
                    self.mismatch_reported = false;
                    return Some(Event::Up(info));
                }
                // Wrong version: keep asking, but at the answer time-out pace, not
                // back to back. The Hello stays in flight from now, so `transmit`
                // sends the next one ANSWER_TIMEOUT later (link-protocol.md 5).
                self.in_flight = Some(InFlight { sent: now, ..f });
                if self.mismatch_reported {
                    None
                } else {
                    self.mismatch_reported = true;
                    Some(Event::VersionMismatch(info))
                }
            }
            (cmd, Reply::Status(status)) if self.up => {
                self.last_rx = now;
                Some(Event::Reply { cmd, status })
            }
            // Wrong reply type for the command: treat as no answer.
            (_, _) => {
                self.in_flight = Some(f);
                None
            }
        }
    }

    /// Check the link time-out. Call often.
    ///
    /// Gives [`Event::Lost`] once when no valid answer came for
    /// [`LINK_TIMEOUT`] (300 ms). The link then goes back to Hello. The caller
    /// drops all PERMIT and KEY lines at once.
    pub fn check_timeout(&mut self, now: Ms) -> Option<Event> {
        if !self.up || now.saturating_sub(self.last_rx) < LINK_TIMEOUT {
            return None;
        }
        self.up = false;
        let unanswered = self
            .in_flight
            .take()
            .map(|f| f.cmd)
            .filter(|c| !matches!(c, Command::Poll));
        Some(Event::Lost {
            unanswered,
            unsent: self.queued.take(),
        })
    }
}
