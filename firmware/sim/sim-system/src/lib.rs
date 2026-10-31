//! The whole system in the emulator: the shack firmware on the shack board, the
//! box firmware on the box board, and Cat6 #1 between them (phase P6).
//!
//! # Where this crate sits
//!
//! It joins the two harnesses of the lower layers. [`ShackSim`] (`sim-shack`) runs
//! `shack-core` on the shack board model; [`BoxSim`] (`sim-box`) runs `box-core` on
//! the box board model. Here both run with their stubs off, and [`SystemSim`]
//! carries the four pairs of the cable between the two boards:
//!
//! | Pair | Signal | Joined as |
//! |---|---|---|
//! | 1 | Data, shack to box (opto current loop, 9600 baud) | bytes from the shack UART to the box UART |
//! | 2 | PTT loop: R1 TX GND to K0 of R1 and TX_ANY | shack `ptt_loop` to box `ptt_loop` |
//! | 3 | SAFE loop, one series loop through both ends | shack switches (power, SW_STOP source, KILL) to the box; box READY to the shack |
//! | 4 | Data, box to shack | bytes from the box UART to the shack UART |
//!
//! The radios' RF follows their TX: a radio feeds RF into its box port
//! (`radio_rf`) from [`SystemSim::rf_delay`] after its TX GND goes active (the
//! radio TX delay of finding F7) until TX ends. [`SystemSim::cable`] cuts or
//! restores all pairs at once.
//!
//! Each step also checks one rule across both ends (D-63): R2 or R3 is released
//! (TX INH open) only while its K0 in the box is settled on the TX row. A break goes
//! to [`SystemSim::violations`]. The box harness keeps the relay hazards
//! ([`BoxSim::hazards`]) and the board keeps the hot switches.
//!
//! Simplifications: each board models its own UART line, so a byte crosses two
//! line models and arrives one byte time (1.04 ms) later than on the real cable.
//! The SAFE loop and the PTT loop are joined once per ms, so a change crosses the
//! cable in at most 1 ms; the opto and gate delays are microseconds.
//!
//! # One step
//!
//! 1. The shack harness steps 1 ms (board, firmware tick, host lines).
//! 2. The box harness steps 1 ms (board, firmware tick, hazard check).
//! 3. The cable: bytes move both ways, then the loop states.
//!
//! # Example
//!
//! ```
//! use sim_system::SystemSim;
//!
//! let mut s = SystemSim::new();
//! s.start();
//! assert_eq!(s.host("route R1 A1 A1"), "ok");
//! s.run(200);
//! let st = s.shack.shack.box_status().unwrap();
//! assert_eq!(st.routes[0].tx, link_proto::Col::A1);
//! assert!(s.boxs.hazards.is_empty());
//! ```

use box_core::relay_box::Phase;
use link_proto::{Ms, Radio};
use sim_box::BoxSim;
use sim_core::hal::Board;
use sim_models::rt1::Contact;
use sim_shack::ShackSim;

/// Radio TX delay: TX GND to RF out, at least 15 ms (finding F7, a station setting).
pub const RF_DELAY: Ms = 15;

/// Both firmwares, both boards and the cable, moved together in 1 ms steps.
pub struct SystemSim {
    /// The shack side: board, firmware, host port. Its scripted box is off.
    pub shack: ShackSim,
    /// The box side: board, firmware, hazard record. Its scripted shack is off.
    pub boxs: BoxSim,
    /// TX GND to RF at the box port, per radio. [`RF_DELAY`] by default.
    pub rf_delay: [Ms; 3],
    /// Breaks of the cross-end rules, with their time.
    pub violations: Vec<(Ms, String)>,
    tx_since: [Option<Ms>; 3],
}

impl Default for SystemSim {
    fn default() -> Self {
        Self::new()
    }
}

impl SystemSim {
    /// Both boards powered at t = 0, cable intact, no stored settings, relays at
    /// the datasheet maximum timing.
    pub fn new() -> Self {
        let mut shack = ShackSim::new();
        shack.external_box = true;
        let mut boxs = BoxSim::new();
        boxs.external_shack = true;
        let mut s = SystemSim {
            shack,
            boxs,
            rf_delay: [RF_DELAY; 3],
            violations: Vec::new(),
            tx_since: [None; 3],
        };
        s.join();
        s
    }

    /// Present virtual time in ms.
    pub fn now(&self) -> Ms {
        self.shack.now()
    }

    /// One millisecond on both sides, then the cable.
    pub fn step(&mut self) {
        self.shack.step();
        self.boxs.step();
        self.join();
        self.check();
    }

    /// D-63: R2 and R3 are released only with K0 settled on the TX row.
    fn check(&mut self) {
        let t = self.now();
        let inhibit = self.shack.board.borrow().signals().inhibit;
        for r in [Radio::R2, Radio::R3] {
            let k0 = self.boxs.board.borrow().k0(r);
            if !inhibit[r.index()] && k0 != Contact::No {
                self.violations
                    .push((t, format!("{r:?} released with K0 {k0:?}")));
            }
        }
    }

    /// Run for `ms` milliseconds.
    pub fn run(&mut self, ms: Ms) {
        for _ in 0..ms {
            self.step();
        }
    }

    /// Step until `cond` holds, at most `max` ms. The time it held, or `None`.
    pub fn run_until(&mut self, max: Ms, cond: impl Fn(&Self) -> bool) -> Option<Ms> {
        for _ in 0..max {
            if cond(self) {
                return Some(self.now());
            }
            self.step();
        }
        cond(self).then(|| self.now())
    }

    /// Send one line to the shack host port and return the answer.
    ///
    /// # Panics
    ///
    /// If no answer comes within 100 ms.
    pub fn host(&mut self, line: &str) -> String {
        let from = self.shack.host_lines.len();
        self.shack
            .board
            .borrow_mut()
            .host_send(&format!("{line}\n"));
        for _ in 0..100 {
            self.step();
            if let Some((_, l)) = self.shack.host_lines[from..]
                .iter()
                .find(|(_, l)| l.starts_with("ok") || l.starts_with("err"))
            {
                return l.clone();
            }
        }
        panic!("no answer to {line:?}");
    }

    /// Press the shack RESET button for 5 ms (clears the SAFE latch).
    pub fn press_reset(&mut self) {
        self.shack
            .board
            .borrow_mut()
            .set_env(|e| e.reset_pressed = true);
        self.run(5);
        self.shack
            .board
            .borrow_mut()
            .set_env(|e| e.reset_pressed = false);
    }

    /// Cut (`false`) or restore Cat6 #1: all four pairs.
    pub fn cable(&mut self, ok: bool) {
        self.shack.board.borrow_mut().set_env(|e| e.cable_ok = ok);
        self.boxs.board.borrow_mut().set_env(|e| e.cable_ok = ok);
        self.join();
    }

    /// Bring the system up: both boot, the link comes up, the box sets up its
    /// expanders, the operator presses RESET.
    ///
    /// # Panics
    ///
    /// If this does not end with the link up, the box running and TX_EN high
    /// within 3 s.
    pub fn start(&mut self) {
        self.run_until(3000, |s| {
            s.shack.shack.link_up() && s.boxs.fw.phase() == Phase::Run
        })
        .expect("link up and box running");
        self.press_reset();
        self.run(100);
        assert!(
            self.shack.board.borrow().signals().tx_en,
            "TX_EN after start"
        );
    }

    /// The cable: data bytes both ways, then the SAFE loop, the PTT loop and RF.
    fn join(&mut self) {
        let mut sb = self.shack.board.borrow_mut();
        let mut bb = self.boxs.board.borrow_mut();
        while let Some(b) = sb.box_recv() {
            bb.shack_send(b);
        }
        while let Some(b) = bb.shack_recv() {
            sb.box_send(b);
        }
        let (ss, se) = (sb.signals(), sb.env());
        let (bs, be) = (bb.signals(), bb.env());
        let box_ready = bs.ready || (be.power && be.ready_stuck_closed);
        if se.box_ready != box_ready {
            sb.set_env(|e| e.box_ready = box_ready);
        }
        let shack_loop = se.power && ss.safe_source && !se.kill_pressed;
        let ptt = ss.ptt_loop;
        let now = sb.now().as_ms();
        let rf: [bool; 3] = std::array::from_fn(|n| {
            let on = ss.radio_tx_active[n];
            let since = *self.tx_since[n].get_or_insert(now);
            if !on {
                self.tx_since[n] = None;
            }
            on && now >= since + self.rf_delay[n]
        });
        if (be.shack_loop, be.ptt_loop, be.radio_rf) != (shack_loop, ptt, rf) {
            bb.set_env(|e| {
                e.shack_loop = shack_loop;
                e.ptt_loop = ptt;
                e.radio_rf = rf;
            });
        }
    }
}
