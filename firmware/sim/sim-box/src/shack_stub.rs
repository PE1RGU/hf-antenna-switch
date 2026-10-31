//! Scripted shack: the master end of the link, and the shack end of the SAFE loop.
//! Stands in for the real shack until P6.
//!
//! The stub uses the real link code of `link-proto` ([`ShackLink`], [`Decoder`]):
//! Hello until the box answers, then one command at a time, Polls every 50 ms,
//! resends and the link time-out. Only the decisions are a script: the test queues
//! the commands.
//!
//! The shack end of the SAFE loop closes while the KILL switch is not pressed. The
//! SAFE latch (D-75) is not in the loop (system-verification.md section 1): it sets
//! when the loop current stops, only [`ShackStub::press_reset`] clears it, and it
//! only blocks TX at the shack. It is set at power-up.

use link_proto::frame::MAX_WIRE;
use link_proto::shack_link::{Event, ShackLink};
use link_proto::{Command, Decoder, Frame, Ms, Reply, Status};
use sim_models::box_board::BoxBoard;
use std::collections::VecDeque;

/// The scripted shack. [`BoxSim`](crate::BoxSim) calls [`ShackStub::step`] once
/// per ms. A test may change the public fields.
pub struct ShackStub {
    link: ShackLink,
    decoder: Decoder,
    /// Commands to send, oldest first. One goes out after each answer.
    pub queue: VecDeque<Command>,
    /// Every answer: time, the answered command, the Status.
    pub replies: Vec<(Ms, Command, Status)>,
    /// Link events other than answers (up, version, lost), with their time.
    pub events: Vec<(Ms, Event)>,
    /// The shack MCU sends nothing (hang, or pair 1 broken).
    pub mute: bool,
    /// The SAFE latch: set = TX blocked at the shack. Not in the loop.
    pub latched: bool,
    /// The KILL switch is pressed.
    pub kill_pressed: bool,
}

impl Default for ShackStub {
    fn default() -> Self {
        Self::new()
    }
}

impl ShackStub {
    /// A shack at power-up: link down, SAFE latch set.
    pub fn new() -> Self {
        ShackStub {
            link: ShackLink::new(),
            decoder: Decoder::new(),
            queue: VecDeque::new(),
            replies: Vec::new(),
            events: Vec::new(),
            mute: false,
            latched: true,
            kill_pressed: false,
        }
    }

    /// The link is up (Hello answered, no time-out since).
    pub fn link_up(&self) -> bool {
        self.link.is_up()
    }

    /// The last Status from the box.
    pub fn status(&self) -> Option<Status> {
        self.replies.last().map(|r| r.2)
    }

    /// Press the RESET button: clears the SAFE latch. If the loop has no current,
    /// the latch sets again at the next step.
    pub fn press_reset(&mut self) {
        self.latched = false;
    }

    /// One frame straight onto the line, outside the link state machine: for
    /// tests that need a chosen seq.
    pub fn send_raw(board: &mut BoxBoard, seq: u8, cmd: Command) {
        let mut buf = [0u8; MAX_WIRE];
        let n = Frame { seq, msg: cmd }.encode(&mut buf);
        for &b in &buf[..n] {
            board.shack_send(b);
        }
    }

    /// One ms of shack time at `now`: answers in, link time-out, next frame out,
    /// then the SAFE loop.
    pub fn step(&mut self, now: Ms, board: &mut BoxBoard) {
        while let Some(b) = board.shack_recv() {
            if let Some(Ok(f)) = self.decoder.push::<Reply>(b)
                && let Some(e) = self.link.receive(now, f)
            {
                self.on_event(now, e);
            }
        }
        if let Some(e) = self.link.check_timeout(now) {
            self.on_event(now, e);
        }
        if !self.mute {
            if self.link.is_up()
                && !self.link.busy()
                && let Some(c) = self.queue.pop_front()
            {
                let _ = self.link.submit(c);
            }
            if let Some(f) = self.link.transmit(now) {
                let mut buf = [0u8; MAX_WIRE];
                let n = f.encode(&mut buf);
                for &b in &buf[..n] {
                    board.shack_send(b);
                }
            }
        }
        self.safe_loop(board);
    }

    fn on_event(&mut self, now: Ms, e: Event) {
        match e {
            Event::Reply { cmd, status } => self.replies.push((now, cmd, status)),
            e => self.events.push((now, e)),
        }
    }

    fn safe_loop(&mut self, board: &mut BoxBoard) {
        let closed = !self.kill_pressed;
        if board.env().shack_loop != closed {
            board.set_env(|e| e.shack_loop = closed);
        }
        if !board.signals().safe_current {
            self.latched = true;
        }
    }
}
