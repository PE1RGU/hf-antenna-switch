//! Shack and box link state machines over a lossy channel, in virtual time (1 ms steps).
//! Frames go through encode and the streaming decoder, as on the wire.

use link_proto::box_link::{BoxLink, Incoming};
use link_proto::frame::MAX_WIRE;
use link_proto::shack_link::{Event, ShackLink};
use link_proto::*;

/// Minimal box application: counts runs per command and answers with a Status.
#[derive(Default)]
struct BoxApp {
    link: BoxLink,
    decoder: Decoder,
    runs: Vec<Command>,
    hello_version: u8,
    lost_events: u32,
}

impl BoxApp {
    fn new() -> Self {
        BoxApp {
            hello_version: VERSION,
            ..Default::default()
        }
    }

    fn rx(&mut self, now: Ms, bytes: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        for &b in bytes {
            let Some(r) = self.decoder.push::<Command>(b) else {
                continue;
            };
            let reply = match self.link.receive(now, r) {
                Some(Incoming::Execute(f)) => {
                    self.runs.push(f.msg);
                    if let Command::Hello { .. } = f.msg {
                        let info = HelloInfo {
                            version: self.hello_version,
                            ..Default::default()
                        };
                        (f.seq, Reply::Hello(info))
                    } else {
                        self.link.complete(f.seq, ResultCode::Ok);
                        (f.seq, status(ResultCode::Ok))
                    }
                }
                Some(Incoming::Repeat { seq, result }) => (seq, status(result)),
                Some(Incoming::BadArg { seq }) => {
                    self.link.complete(seq, ResultCode::BadArg);
                    (seq, status(ResultCode::BadArg))
                }
                None => continue,
            };
            out.extend(encode(reply.0, reply.1));
        }
        out
    }

    fn tick(&mut self, now: Ms) {
        if self.link.check_timeout(now) {
            self.lost_events += 1;
        }
    }
}

fn status(result: ResultCode) -> Reply {
    Reply::Status(Status {
        result,
        ..Default::default()
    })
}

fn encode<M: Message>(seq: u8, msg: M) -> Vec<u8> {
    let mut out = [0u8; MAX_WIRE];
    let n = Frame { seq, msg }.encode(&mut out);
    out[..n].to_vec()
}

/// Shack, box and two channels. `drop_down` / `drop_up` decide per frame number whether it is lost.
struct Bench {
    now: Ms,
    shack: ShackLink,
    shack_dec: Decoder,
    boxa: BoxApp,
    sent_down: Vec<Frame<Command>>,
    n_down: usize,
    n_up: usize,
    drop_down: Box<dyn Fn(usize, Ms) -> bool>,
    drop_up: Box<dyn Fn(usize, Ms) -> bool>,
    events: Vec<(Ms, Event)>,
}

impl Bench {
    fn new() -> Self {
        Bench {
            now: 0,
            shack: ShackLink::new(),
            shack_dec: Decoder::new(),
            boxa: BoxApp::new(),
            sent_down: Vec::new(),
            n_down: 0,
            n_up: 0,
            drop_down: Box::new(|_, _| false),
            drop_up: Box::new(|_, _| false),
            events: Vec::new(),
        }
    }

    fn step(&mut self) {
        let now = self.now;
        if let Some(e) = self.shack.check_timeout(now) {
            self.events.push((now, e));
        }
        self.boxa.tick(now);
        if let Some(f) = self.shack.transmit(now) {
            self.sent_down.push(f);
            self.n_down += 1;
            if !(self.drop_down)(self.n_down, now) {
                let answer = self.boxa.rx(now, &encode(f.seq, f.msg));
                if !answer.is_empty() {
                    self.n_up += 1;
                    if !(self.drop_up)(self.n_up, now) {
                        for b in answer {
                            if let Some(Ok(r)) = self.shack_dec.push::<Reply>(b)
                                && let Some(e) = self.shack.receive(now, r)
                            {
                                self.events.push((now, e));
                            }
                        }
                    }
                }
            }
        }
        self.now += 1;
    }

    fn run(&mut self, ms: Ms) {
        for _ in 0..ms {
            self.step();
        }
    }

    fn replies(&self) -> Vec<Command> {
        self.events
            .iter()
            .filter_map(|(_, e)| match e {
                Event::Reply { cmd, .. } => Some(*cmd),
                _ => None,
            })
            .collect()
    }

    fn up(&mut self) {
        self.run(5);
        assert!(self.shack.is_up());
        assert!(matches!(self.events[0], (_, Event::Up(_))));
    }
}

#[test]
fn hello_then_poll_every_50_ms() {
    let mut b = Bench::new();
    b.up();
    b.run(1000);
    let polls = b
        .sent_down
        .iter()
        .filter(|f| f.msg == Command::Poll)
        .count();
    assert_eq!(polls, 20);
    assert_eq!(b.boxa.lost_events, 0);
}

#[test]
fn command_goes_out_and_is_answered_once() {
    let mut b = Bench::new();
    b.up();
    let cmd = Command::TxRequest(Radio::R2);
    b.shack.submit(cmd).unwrap();
    assert!(b.shack.busy());
    assert_eq!(b.shack.submit(Command::Poll), Err(Command::Poll));
    b.run(100);
    assert!(!b.shack.busy());
    assert_eq!(b.replies().iter().filter(|c| **c == cmd).count(), 1);
    assert_eq!(b.boxa.runs.iter().filter(|c| **c == cmd).count(), 1);
}

#[test]
fn lost_answer_is_retried_with_same_seq_and_not_run_twice() {
    let mut b = Bench::new();
    // Lose the first answer to the command (answer number 2: number 1 is the HelloReply).
    b.drop_up = Box::new(|n, _| n == 2);
    b.up();
    let cmd = Command::SetRoute {
        radio: Radio::R1,
        route: Route {
            tx: Col::A1,
            rx: Col::A1,
        },
    };
    b.shack.submit(cmd).unwrap();
    b.run(200);
    let sends: Vec<_> = b.sent_down.iter().filter(|f| f.msg == cmd).collect();
    assert_eq!(sends.len(), 2, "one send, one retry");
    assert_eq!(sends[0].seq, sends[1].seq);
    assert_eq!(b.boxa.runs.iter().filter(|c| **c == cmd).count(), 1);
    assert_eq!(b.replies().iter().filter(|c| **c == cmd).count(), 1);
}

#[test]
fn retry_after_answer_timeout() {
    let mut b = Bench::new();
    b.up();
    b.drop_down = Box::new(|_, t| (100..130).contains(&t));
    b.run(95);
    b.shack.submit(Command::TxEnd(Radio::R3)).unwrap();
    b.run(200);
    let sends: Vec<_> = b
        .sent_down
        .iter()
        .filter(|f| f.msg == Command::TxEnd(Radio::R3))
        .collect();
    assert_eq!(sends.len(), 2, "send at 100 lost, retry at 160 answered");
    assert_eq!(sends[0].seq, sends[1].seq);
    assert!(b.shack.is_up());
}

#[test]
fn link_lost_after_300_ms_at_both_ends() {
    let mut b = Bench::new();
    b.up();
    b.run(200);
    let cut = b.now;
    b.drop_down = Box::new(move |_, t| t >= cut);
    b.shack.submit(Command::TxRequest(Radio::R2)).unwrap();
    b.run(400);
    let lost: Vec<_> = b
        .events
        .iter()
        .filter_map(|(t, e)| match e {
            Event::Lost { unanswered, unsent } => Some((*t, *unanswered, *unsent)),
            _ => None,
        })
        .collect();
    assert_eq!(lost.len(), 1);
    let (t, unanswered, unsent) = lost[0];
    // Last answer came just before the cut; lost 300 ms after it.
    assert!(
        t >= cut + 250 && t <= cut + 300,
        "lost at {t}, cut at {cut}"
    );
    assert_eq!(unanswered, Some(Command::TxRequest(Radio::R2)));
    assert_eq!(unsent, None);
    assert!(!b.shack.is_up());
    assert_eq!(b.boxa.lost_events, 1, "box reports the loss once");
    assert!(b.boxa.link.is_lost());
    // Commands are refused while down; Hello goes out instead.
    assert!(b.shack.submit(Command::Poll).is_err());
    assert!(matches!(
        b.sent_down.last().unwrap().msg,
        Command::Hello { .. }
    ));
}

#[test]
fn link_comes_back_after_cut() {
    let mut b = Bench::new();
    b.up();
    b.drop_down = Box::new(|_, t| (100..600).contains(&t));
    b.run(800);
    let ups = b
        .events
        .iter()
        .filter(|(_, e)| matches!(e, Event::Up(_)))
        .count();
    assert_eq!(ups, 2);
    assert!(b.shack.is_up());
    assert!(!b.boxa.link.is_lost());
}

#[test]
fn box_without_shack_reports_no_loss() {
    let mut boxa = BoxApp::new();
    for t in 0..2000 {
        boxa.tick(t);
    }
    assert_eq!(boxa.lost_events, 0);
}

#[test]
fn restarted_shack_cannot_hit_an_old_seq() {
    let mut b = Bench::new();
    b.up();
    let cmd = Command::TxEnd(Radio::R2);
    b.shack.submit(cmd).unwrap();
    b.run(10);
    // Shack restarts: Hello gets seq 1, then the same command gets seq 2, as before.
    b.shack = ShackLink::new();
    b.shack_dec = Decoder::new();
    b.events.clear();
    b.up();
    b.shack.submit(cmd).unwrap();
    b.run(10);
    assert_eq!(b.boxa.runs.iter().filter(|c| **c == cmd).count(), 2);
}

#[test]
fn version_mismatch_reported_once_and_no_commands() {
    let mut b = Bench::new();
    b.boxa.hello_version = VERSION + 1;
    b.run(500);
    let mism = b
        .events
        .iter()
        .filter(|(_, e)| matches!(e, Event::VersionMismatch(_)))
        .count();
    assert_eq!(mism, 1);
    assert!(!b.shack.is_up());
    // Hello at the answer time-out pace (60 ms), not back to back.
    assert!(
        b.sent_down.len() <= 500 / ANSWER_TIMEOUT as usize + 1,
        "{} Hello frames in 500 ms",
        b.sent_down.len()
    );
    assert!(
        b.sent_down
            .iter()
            .all(|f| matches!(f.msg, Command::Hello { .. }))
    );
}

#[test]
fn bad_value_gets_bad_arg() {
    let mut boxa = BoxApp::new();
    // TxRequest for radio 9, valid CRC: built from raw bytes.
    let body = [4u8, 0x11, 9];
    let crc = crc::Crc::<u16>::new(&crc::CRC_16_IBM_3740).checksum(&body);
    let mut raw = body.to_vec();
    raw.extend(crc.to_be_bytes());
    let mut wire = vec![raw.len() as u8 + 1];
    wire.extend(&raw);
    wire.push(0);
    let answer = boxa.rx(0, &wire);
    let mut d = Decoder::new();
    let got: Vec<_> = answer.iter().filter_map(|&b| d.push::<Reply>(b)).collect();
    assert_eq!(
        got,
        vec![Ok(Frame {
            seq: 4,
            msg: status(ResultCode::BadArg)
        })]
    );
    assert!(boxa.runs.is_empty());
}
