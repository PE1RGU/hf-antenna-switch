//! Shack end of the link: the master (link-protocol.md sections 5 and 6).
//!
//! One frame in flight at a time. A lost answer resends the same seq every
//! ANSWER_TIMEOUT. No valid answer for LINK_TIMEOUT: link lost, back to Hello.

use crate::frame::Frame;
use crate::msg::{Command, HelloInfo, Reply, Status};
use crate::{ANSWER_TIMEOUT, LINK_TIMEOUT, Ms, POLL_PERIOD, VERSION};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Event {
    /// HelloReply with our version: commands can go.
    Up(HelloInfo),
    /// HelloReply with another version. The link stays in Hello; no commands go.
    VersionMismatch(HelloInfo),
    /// Answer to a command (Poll included).
    Reply { cmd: Command, status: Status },
    /// No valid answer for LINK_TIMEOUT. The caller drops all permits and keys.
    /// `unanswered` was in flight (it may or may not have run in the box);
    /// `unsent` never left the shack.
    Lost {
        unanswered: Option<Command>,
        unsent: Option<Command>,
    },
}

#[derive(Clone, Copy, Debug)]
struct InFlight {
    seq: u8,
    cmd: Command,
    sent: Ms,
}

#[derive(Debug, Default)]
pub struct ShackLink {
    up: bool,
    mismatch_reported: bool,
    seq: u8,
    queued: Option<Command>,
    in_flight: Option<InFlight>,
    last_tx: Option<Ms>,
    last_rx: Ms,
}

impl ShackLink {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn is_up(&self) -> bool {
        self.up
    }

    /// Queue one command. Refused (returned) while the link is down or a command waits.
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
    pub fn transmit(&mut self, now: Ms) -> Option<Frame<Command>> {
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
    pub fn receive(&mut self, now: Ms, frame: Frame<Reply>) -> Option<Event> {
        let f = self.in_flight.filter(|f| f.seq == frame.seq)?;
        self.in_flight = None;
        match (f.cmd, frame.msg) {
            (Command::Hello { .. }, Reply::Hello(info)) => {
                self.last_rx = now;
                if info.version == VERSION {
                    self.up = true;
                    self.mismatch_reported = false;
                    Some(Event::Up(info))
                } else if !self.mismatch_reported {
                    self.mismatch_reported = true;
                    Some(Event::VersionMismatch(info))
                } else {
                    None
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
