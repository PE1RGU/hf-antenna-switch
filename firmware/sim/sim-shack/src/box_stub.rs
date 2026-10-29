//! Scripted box: answers the link like the box firmware will, with simple rules.
//! Stands in for the real box until P4 to P6. Rules from link-protocol.md and D-63:
//! - TxRequest: K0 set at once, permit reported 12 ms later.
//! - SetRoute: refused while the radio has K0, while TX_ANY, or for a TX row on A2 or a shared TX column.
//! - Link lost with K0 out: open SAFE (READY off), keep K0 (F13). Without K0: hold (P-02).

use link_proto::box_link::{BoxLink, Incoming};
use link_proto::frame::MAX_WIRE;
use link_proto::*;
use sim_models::shack::ShackBoard;

/// K0 operate plus bounce (verify_logic.py section 8).
pub const K0_SETTLE: Ms = 12;
/// Length of a route change sequence (three 12 ms steps).
pub const SWITCH_TIME: Ms = 36;

pub struct BoxStub {
    link: BoxLink,
    decoder: Decoder,
    pub routes: [Route; 3],
    pub bias: ColMask,
    k0_since: [Option<Ms>; 3],
    switching_until: Ms,
    /// READY switch closed (MCU_EN_N = 0 and no fault).
    pub ready: bool,
    /// Time from K0 set to the permit bit; K0_SETTLE unless a test makes the box slow.
    pub k0_settle: Ms,
    pub link_lost_stop: bool,
    /// Box MCU answers nothing (hang, or pair 4 broken).
    pub mute: bool,
    /// Every executed or repeated command with its result.
    pub log: Vec<(Ms, Command, ResultCode)>,
    /// K0 changes: (time, radio, on).
    pub k0_log: Vec<(Ms, Radio, bool)>,
}

impl Default for BoxStub {
    fn default() -> Self {
        Self::new()
    }
}

impl BoxStub {
    pub fn new() -> Self {
        BoxStub {
            link: BoxLink::new(),
            decoder: Decoder::new(),
            routes: [Route::default(); 3],
            bias: ColMask::EMPTY,
            k0_since: [None; 3],
            switching_until: 0,
            ready: true,
            k0_settle: K0_SETTLE,
            link_lost_stop: false,
            mute: false,
            log: Vec::new(),
            k0_log: Vec::new(),
        }
    }

    pub fn k0(&self, r: Radio) -> bool {
        self.k0_since[r.index()].is_some()
    }

    fn permit(&self, now: Ms, r: Radio) -> bool {
        self.k0_since[r.index()].is_some_and(|t| now >= t + self.k0_settle)
    }

    fn k1(&self) -> ColMask {
        self.routes
            .iter()
            .fold(ColMask::EMPTY, |m, r| m.with(r.tx).with(r.rx))
    }

    pub fn step(&mut self, now: Ms, board: &mut ShackBoard) {
        while let Some(b) = board.box_recv() {
            let Some(frame) = self.decoder.push::<Command>(b) else {
                continue;
            };
            if self.mute {
                continue;
            }
            if let Some(reply) = self.receive(now, board, frame) {
                let mut buf = [0u8; MAX_WIRE];
                let n = reply.encode(&mut buf);
                for &b in &buf[..n] {
                    board.box_send(b);
                }
            }
        }
        if self.link.check_timeout(now) && self.k0_since.iter().any(Option::is_some) {
            self.link_lost_stop = true;
            self.ready = false;
        }
        if board.env().box_ready != self.ready {
            let ready = self.ready;
            board.set_env(|e| e.box_ready = ready);
        }
    }

    fn receive(
        &mut self,
        now: Ms,
        board: &ShackBoard,
        frame: Result<Frame<Command>, DecodeError>,
    ) -> Option<Frame<Reply>> {
        let (seq, result, cmd) = match self.link.receive(now, frame)? {
            Incoming::Execute(f) => {
                if let Command::Hello { .. } = f.msg {
                    let info = HelloInfo {
                        version: VERSION,
                        fw: [0, 1, 0],
                        rx_only: ColMask::EMPTY.with(Col::A2),
                        unit2: false,
                    };
                    return Some(Frame {
                        seq: f.seq,
                        msg: Reply::Hello(info),
                    });
                }
                let r = self.execute(now, board, f.msg);
                self.link.complete(f.seq, r);
                (f.seq, r, Some(f.msg))
            }
            Incoming::Repeat { seq, result } => (seq, result, None),
            Incoming::BadArg { seq } => {
                self.link.complete(seq, ResultCode::BadArg);
                (seq, ResultCode::BadArg, None)
            }
        };
        if let Some(c) = cmd {
            self.log.push((now, c, result));
        }
        Some(Frame {
            seq,
            msg: Reply::Status(self.status(now, board, result)),
        })
    }

    fn execute(&mut self, now: Ms, board: &ShackBoard, cmd: Command) -> ResultCode {
        let tx_any = board.signals().ptt_loop;
        match cmd {
            Command::Hello { .. } | Command::Poll => ResultCode::Ok,
            Command::SetRoute { radio, route } => {
                let i = radio.index();
                let others_use = |c: Col| {
                    c != Col::None
                        && self
                            .routes
                            .iter()
                            .enumerate()
                            .any(|(j, r)| j != i && (r.tx == c || r.rx == c))
                };
                if !self.ready {
                    ResultCode::NotReady
                } else if self.k0(radio) {
                    ResultCode::PermitOut
                } else if tx_any {
                    ResultCode::TxActive
                } else if route.tx == Col::A2 || others_use(route.tx) {
                    ResultCode::Hazard
                } else {
                    self.routes[i] = route;
                    self.switching_until = now + SWITCH_TIME;
                    ResultCode::Ok
                }
            }
            Command::TxRequest(r) => {
                let tx = self.routes[r.index()].tx;
                if r == Radio::R1 {
                    ResultCode::BadArg
                } else if self.k0(r) {
                    ResultCode::Ok
                } else if !self.ready {
                    ResultCode::NotReady
                } else if tx_any {
                    ResultCode::TxActive
                } else if tx == Col::None || !self.k1().contains(tx) {
                    ResultCode::NoTxRoute
                } else {
                    self.k0_since[r.index()] = Some(now);
                    self.k0_log.push((now, r, true));
                    ResultCode::Ok
                }
            }
            Command::TxEnd(r) => {
                if r == Radio::R1 {
                    return ResultCode::BadArg;
                }
                if self.k0_since[r.index()].take().is_some() {
                    self.k0_log.push((now, r, false));
                }
                ResultCode::Ok
            }
            Command::SetBias(m) => {
                self.bias = m;
                ResultCode::Ok
            }
        }
    }

    fn status(&self, now: Ms, board: &ShackBoard, result: ResultCode) -> Status {
        Status {
            result,
            flags: Flags {
                ready: self.ready,
                kill: !board.signals().safe_current,
                tx_any: board.signals().ptt_loop,
                switching: now < self.switching_until,
                link_lost_stop: self.link_lost_stop,
                unit2: false,
            },
            permit_r2: self.permit(now, Radio::R2),
            permit_r3: self.permit(now, Radio::R3),
            routes: self.routes,
            k1: self.k1(),
            rfdet: ColMask::EMPTY,
            bias_en: self.bias,
            bias_ok: self.bias,
            fault: FaultCode::NONE,
        }
    }
}
