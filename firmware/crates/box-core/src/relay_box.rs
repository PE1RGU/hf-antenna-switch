//! Box logic. Call [`RelayBox::tick`] every [`TICK`] ms from the main loop.
//!
//! Rules implemented here (hardware/unit/verify, link-protocol.md):
//! - F11 start-up: MCU_EN_N high, after [`BOOT_DELAY`] one LATCH_CLR edge, then
//!   MCU_EN_N low, then wait for KILL = 0 (fault 5 after [`SAFE_TIMEOUT`]), then set up.
//! - F1: each expander gets its outputs (all 0) before its configuration.
//! - F5: KILL = 1 puts the expanders in reset in hardware; after KILL = 0 the box sets
//!   them up again. The relays come back off. MCU_EN_N stays low.
//! - F6: every new state is checked with [`crossbar::check`] before a relay moves.
//! - F10 and the sequence of logic-verification.md section 8: open rows, 12 ms, K1
//!   on, 12 ms, close rows, 12 ms, read back, K1 off, 12 ms. One register write only
//!   opens or only closes. Each step waits while TX_ANY = 1.
//! - F13: no K0 or row change of a radio with a permit out. On a link time-out
//!   with a permit out, the box opens SAFE (MCU_EN_N = 1) and does not write K0.
//! - WDI: toggled from the main loop, every [`POLL`] ms.
//! - D-191: FAULT = 1 after the self-test is a supervisor trip (fault 11). The
//!   latch keeps READY open until the host sends ClearFault (operator request,
//!   one LATCH_CLR edge). If the edge does not clear FAULT, the answer is NotReady.
//!
//! # Power-up self-test
//!
//! The first time the SAFE loop closes after power-up, the box tests its safety
//! hardware before any relay can move. No relay moves during the test.
//!
//! 1. Gate: MCU_EN_N = 1 must open READY (KILL = 1) and drop RLY_EN (the
//!    expanders stop answering). Then MCU_EN_N = 0 must close the loop again.
//! 2. Expanders: F1 set-up and read-back of all four.
//! 3. Inputs, a warning only (fault 10): TX_ANY = 0, R1 K0 read-back equal to
//!    TX_ANY (F3), no RF on any detector, no bias-T OK while its feed is off.
//! 4. Watchdog: the WDI kicks stop. The supervisor must trip (KILL = 1 through
//!    FAULT and READY) between [`WDT_MIN`] and [`WDT_MAX`] after the last kick.
//! 5. The kicks resume; after [`WDT_RECOVER`] (RESET_N high again) one more
//!    LATCH_CLR edge (the cause is known: rule 2), and the loop must close again.
//!
//! A failed step 1, 2, 4 or 5 sets the fault code (7, 1, 2, 8 or 9), keeps
//! MCU_EN_N high and stops in [`Phase::Failed`] until a power cycle. The box
//! keeps answering the shack, with READY = 0. With R64 open (watchdog off, D-123)
//! the box therefore does not start.
//!
//! # Phases
//!
//! | From | To | When |
//! |---|---|---|
//! | Boot | WaitSafe | [`BOOT_DELAY`] after power-up: LATCH_CLR edge, MCU_EN_N = 0 |
//! | WaitSafe | SelfTest | KILL = 0 for the first time after power-up |
//! | SelfTest | Run | All steps passed, expanders set up again (F1, F5) |
//! | SelfTest | Failed | A step failed: MCU_EN_N = 1, until a power cycle |
//! | WaitSafe | Run | KILL = 0 again later and all four expanders set up (F1) |
//! | Run | WaitSafe | KILL = 1, or an expander reset or NACK with no permit out |
//! | Run | Stopped | Link time-out or expander lost, with a permit out: MCU_EN_N = 1 |
//! | Stopped | WaitSafe | A Hello, or a TxEnd for each radio that had a permit: MCU_EN_N = 0 |
//!
//! The stop exit was decided by Prins (2026-10-31). The SAFE latch in the shack
//! still needs RESET after a stop, so an operator is in the loop.
//!
//! # TX handshake of R2 and R3 (link-protocol.md 5.1)
//!
//! TxRequest sets K0 and answers Ok at once. The permit bit comes when K0 is
//! settled ([`RELAY_WAIT`]) and read back. TxEnd releases K0 at once (the shack
//! sends it after the F14 wait). A Hello ends every permit: the shack that sends
//! it has all PERMIT lines off (boot or link loss). The box then releases K0
//! [`HELLO_RELEASE`] ms later, the F14 wait, unless a TxRequest or TxEnd comes first,
//! and only once no RF is on that radio's TX column (a radio without TX INH, or a
//! long RF tail, keeps K0 on its TX row).

use crate::board::{EXPANDERS, ExpPin, RX_ONLY, exp, expander_config, k0, k1, rf_det, row_relay};
use crate::crossbar::{self, ANTENNAS, used_columns};
use crate::hw::BoxHw;
use link_proto::box_link::{BoxLink, Incoming};
use link_proto::frame::MAX_WIRE;
use link_proto::{
    Col, ColMask, Command, Decoder, FaultCode, Flags, Frame, HelloInfo, Ms, Radio, Reply,
    ResultCode, Route, Status, VERSION,
};
use pca9539::Pca9539;

/// Main loop period.
pub const TICK: Ms = 1;
/// Expander poll and WDI kick period.
pub const POLL: Ms = 10;
/// From power-up to the LATCH_CLR edge. The supervisor holds RESET_N low for td
/// (300 ms at most), and the latch ignores an edge in that time (S4).
pub const BOOT_DELAY: Ms = 500;
/// Fault 5 when KILL stays 1 this long after MCU_EN_N = 0 at start-up.
pub const SAFE_TIMEOUT: Ms = 2000;
/// RT1 operate plus bounce, and release plus NC bounce (section 8).
pub const RELAY_WAIT: Ms = 12;
/// Added to [`RELAY_WAIT`] between two switching steps. The step time is the
/// tick start, but the write comes after the I2C reads of that tick: up to two
/// full reads of the four expanders, about 7.6 ms at 100 kHz. Without the margin
/// open-to-close could shrink to about 8 ms (review 2026-10-31, F-4).
pub const IO_MARGIN: Ms = 8;
/// An I2C NACK is retried this many times (one per poll) before the box treats
/// the expander as lost (review 2026-10-31, F-3). An expander found reset acts at once.
pub const IO_RETRIES: u8 = 2;
/// Unit 2 (the expansion unit on EXP) is fitted. Not on unit 1: no TX on EXP,
/// so no radio transmits into an open SMA (review 2026-10-31, F-2).
pub const UNIT2: bool = false;
/// A bias-T feed is checked this long after it was switched on.
pub const BIAS_SETTLE: Ms = 10;
/// After a Hello, K0 of a radio with a permit is released this late (F14 wait).
pub const HELLO_RELEASE: Ms = 100;
/// Self-test: the supervisor trip must not come earlier than this after the last
/// kick (TPS3823 time-out 0.9 s at least, C-19).
pub const WDT_MIN: Ms = 500;
/// Self-test: the supervisor must trip within this time after the last kick
/// (time-out 2.5 s at most).
pub const WDT_MAX: Ms = 3000;
/// Self-test: wait after the trip before the LATCH_CLR edge. RESET_N stays low for
/// td (300 ms at most), and the latch ignores an edge in that time (S4).
pub const WDT_RECOVER: Ms = 400;
/// Self-test: the SAFE loop must open or close within this time after a
/// MCU_EN_N or LATCH_CLR change.
pub const LOOP_WAIT: Ms = 100;
/// Firmware version in HelloReply: major, minor, patch.
pub const FW_VERSION: [u8; 3] = [0, 1, 0];

/// Row bits of a radio expander: TX on bits 0 to 4, RX on bits 5 to 9.
const ROWS: u16 = 0x03FF;
/// Bias-T enable bits of U1001.
const BIAS_EN: u16 = 0x000F;

/// Where the box is. See the module docs for the moves.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    /// After power-up: MCU_EN_N high, waiting for [`BOOT_DELAY`].
    Boot,
    /// MCU_EN_N low, waiting for KILL = 0, then the expander set-up.
    WaitSafe {
        /// When the wait started.
        since: Ms,
        /// First wait after power-up: fault 5 after [`SAFE_TIMEOUT`].
        startup: bool,
    },
    /// Power-up self-test (module docs). No relay moves.
    SelfTest(SelfTest),
    /// Expanders set up; commands can switch relays.
    Run,
    /// SAFE opened with a permit out (MCU_EN_N high, F13).
    Stopped,
    /// The self-test failed: MCU_EN_N high until a power cycle. The fault code
    /// says which step.
    Failed,
}

/// A step of the power-up self-test, with its start time.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SelfTest {
    /// MCU_EN_N = 1 since `at`: KILL must go to 1 and the expanders must stop answering.
    GateOpen {
        /// Start of the step.
        at: Ms,
    },
    /// MCU_EN_N = 0 since `at`: KILL must go to 0.
    GateClose {
        /// Start of the step.
        at: Ms,
    },
    /// No WDI kicks since `since`: the supervisor must trip.
    Watchdog {
        /// Time of the last kick.
        since: Ms,
    },
    /// Tripped; kicks again. LATCH_CLR edge at `at`.
    Recover {
        /// Time of the LATCH_CLR edge.
        at: Ms,
    },
    /// LATCH_CLR edge given at `at`: KILL must go to 0.
    LatchClear {
        /// Time of the edge.
        at: Ms,
    },
}

/// State of K0 of one radio (R2 and R3; R1 follows the PTT loop in hardware).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum K0 {
    Off,
    /// Written on at this time; permit after [`RELAY_WAIT`] and the read-back.
    Settling(Ms),
    /// Permit out.
    On,
    /// After a Hello: release at this time.
    Releasing(Ms),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Step {
    Open,
    K1On,
    Close,
    ReadBack,
    K1Off,
    Done,
}

/// The switching sequence in progress: the next step and its earliest time.
#[derive(Clone, Copy, Debug)]
struct Switching {
    step: Step,
    at: Ms,
}

/// An expander did not answer (NACK) or was found reset.
#[derive(Clone, Copy, Debug)]
struct Lost {
    nack: bool,
}

/// The box state machine.
///
/// Make one with [`RelayBox::new`] at power-up and call [`RelayBox::tick`] every
/// [`TICK`] ms. The box speaks only to answer the shack.
pub struct RelayBox {
    boot_at: Option<Ms>,
    phase: Phase,
    link: BoxLink,
    decoder: Decoder,
    /// Accepted routes: the target of the switching sequence.
    routes: [Route; 3],
    /// Accepted bias-T feeds.
    bias: ColMask,
    /// Output words as written, per expander (address order).
    out: [u16; 4],
    /// Pin levels at the last read. `None` while the expanders are not set up.
    inputs: Option<[u16; 4]>,
    next_poll: Ms,
    wdi: bool,
    kill: bool,
    switching: Option<Switching>,
    k0: [K0; 3],
    /// Stopped: the radios that had a permit out at the stop.
    held: [bool; 3],
    bias_since: Ms,
    fault: FaultCode,
    link_lost_stop: bool,
    /// The power-up self-test passed.
    tested: bool,
    /// WDI kicks on (off only in the watchdog step of the self-test).
    kick: bool,
    /// I2C errors in a row (F-3).
    io_errors: u8,
    /// The supervisor tripped after the self-test (fault 11, D-191). Cleared only
    /// by [`Command::ClearFault`].
    tripped: bool,
}

impl Default for RelayBox {
    fn default() -> Self {
        Self::new()
    }
}

impl RelayBox {
    /// The box at power-up: MCU_EN_N high, no routes, link not heard yet.
    pub fn new() -> Self {
        RelayBox {
            boot_at: None,
            phase: Phase::Boot,
            link: BoxLink::new(),
            decoder: Decoder::new(),
            routes: [Route::default(); 3],
            bias: ColMask::EMPTY,
            out: [0; 4],
            inputs: None,
            next_poll: 0,
            wdi: false,
            kill: true,
            switching: None,
            k0: [K0::Off; 3],
            held: [false; 3],
            bias_since: 0,
            fault: FaultCode::NONE,
            link_lost_stop: false,
            tested: false,
            kick: true,
            io_errors: 0,
            tripped: false,
        }
    }

    // ---------------------------------------------------------------- state

    /// The present phase.
    pub fn phase(&self) -> Phase {
        self.phase
    }

    /// The accepted routes (the target of a running switching sequence).
    pub fn routes(&self) -> [Route; 3] {
        self.routes
    }

    /// The last fault since power-up.
    pub fn fault(&self) -> FaultCode {
        self.fault
    }

    /// True while a switching sequence runs.
    pub fn switching(&self) -> bool {
        self.switching.is_some()
    }

    /// The Status the box would send now, with result Ok.
    pub fn status(&self) -> Status {
        self.status_with(ResultCode::Ok)
    }

    // ---------------------------------------------------------------- main loop

    /// Run one pass of the main loop at `now` (ms from power-up; it must not go back).
    pub fn tick<H: BoxHw>(&mut self, now: Ms, hw: &mut H) {
        let boot_at = *self.boot_at.get_or_insert_with(|| {
            hw.set_mcu_en_n(true);
            hw.set_latch_clr(false);
            now
        });
        self.kill = hw.kill();
        // D-191: after the self-test FAULT is low, unless the supervisor tripped
        // while this loop ran on. The latch stays set: wait for ClearFault.
        if self.tested && !self.tripped && hw.fault() {
            self.tripped = true;
        }
        if self.tripped {
            self.fault = FaultCode::SUPERVISOR_TRIP;
        }
        self.link_rx(now, hw);
        if self.link.check_timeout(now) {
            self.on_link_lost(hw);
        }
        let poll = now >= self.next_poll;
        if poll {
            self.next_poll = now + POLL;
        }
        match self.phase {
            Phase::Boot if now - boot_at >= BOOT_DELAY => {
                // One edge, once (rule 2), then ask for RLY_EN (F11).
                hw.set_latch_clr(true);
                hw.set_latch_clr(false);
                hw.set_mcu_en_n(false);
                self.phase = Phase::WaitSafe {
                    since: now,
                    startup: true,
                };
            }
            Phase::Boot | Phase::Stopped | Phase::Failed => {}
            Phase::WaitSafe { since, startup } => {
                if startup && now - since >= SAFE_TIMEOUT {
                    self.fault = FaultCode::SAFE_NOT_CLOSED;
                    self.phase = Phase::WaitSafe {
                        since,
                        startup: false,
                    };
                }
                if !self.kill && poll {
                    if !self.tested {
                        hw.set_mcu_en_n(true);
                        self.phase = Phase::SelfTest(SelfTest::GateOpen { at: now });
                    } else if self.set_up(hw) {
                        self.phase = Phase::Run;
                    }
                }
            }
            Phase::SelfTest(t) => self.self_test(now, t, hw),
            Phase::Run => self.run(now, poll, hw),
        }
        if poll && self.kick {
            // After the checks of the pass (rule 1): a hung loop stops the kicks.
            self.wdi = !self.wdi;
            hw.set_wdi(self.wdi);
        }
    }

    fn run<H: BoxHw>(&mut self, now: Ms, poll: bool, hw: &mut H) {
        if self.kill {
            // The expanders are in reset: the relays are off in hardware (F5).
            self.drop_to_wait(now);
            return;
        }
        let r = if poll { self.read(hw) } else { Ok(()) };
        let r = r
            .and_then(|()| self.k0_step(now, hw))
            .and_then(|()| self.switch_step(now, hw))
            .and_then(|()| {
                if poll {
                    self.bias_check(now, hw)
                } else {
                    Ok(())
                }
            });
        if let Err(l) = r {
            self.io_error(now, l, hw);
        }
    }

    /// An I2C error. A NACK may be a single disturbed transfer: retry it at the next
    /// poll, up to [`IO_RETRIES`] times, before the expander counts as lost. Nothing
    /// moves meanwhile: a switching step and a K0 write are repeated when due.
    fn io_error<H: BoxHw>(&mut self, now: Ms, l: Lost, hw: &mut H) {
        if l.nack && self.io_errors < IO_RETRIES {
            self.io_errors += 1;
            self.fault = FaultCode::EXPANDER_NACK;
            return;
        }
        self.io_errors = 0;
        self.on_lost(now, l, hw);
    }

    /// F1 set-up of all four expanders, all outputs 0. True on success; the
    /// fault code says why not.
    fn set_up<H: BoxHw>(&mut self, hw: &mut H) -> bool {
        for addr in EXPANDERS {
            match Pca9539::new(addr).init(hw.i2c(), 0, expander_config(addr)) {
                Ok(()) => {}
                Err(pca9539::Error::Bus(_)) => {
                    self.fault = FaultCode::EXPANDER_NACK;
                    return false;
                }
                Err(pca9539::Error::Verify) => {
                    self.fault = FaultCode::READ_BACK;
                    return false;
                }
            }
        }
        self.out = [0; 4];
        self.clear_state();
        self.read(hw).is_ok()
    }

    /// One pass of the power-up self-test (module docs).
    fn self_test<H: BoxHw>(&mut self, now: Ms, step: SelfTest, hw: &mut H) {
        match step {
            SelfTest::GateOpen { at } if now >= at + 2 => {
                // RLY_EN low holds the expanders in reset: they must not answer.
                let answers = EXPANDERS
                    .into_iter()
                    .any(|a| Pca9539::new(a).read_config(hw.i2c()).is_ok());
                if !self.kill || answers {
                    return self.fail(FaultCode::SELFTEST_GATE, hw);
                }
                hw.set_mcu_en_n(false);
                self.phase = Phase::SelfTest(SelfTest::GateClose { at: now });
            }
            SelfTest::GateClose { .. } if !self.kill => {
                if !self.set_up(hw) {
                    let code = self.fault;
                    return self.fail(code, hw);
                }
                self.check_inputs();
                self.kick = false;
                self.phase = Phase::SelfTest(SelfTest::Watchdog { since: now });
            }
            SelfTest::GateClose { at } if now >= at + LOOP_WAIT => {
                self.fail(FaultCode::SELFTEST_GATE, hw);
            }
            SelfTest::Watchdog { since } if self.kill => {
                self.kick = true;
                if now - since < WDT_MIN {
                    return self.fail(FaultCode::SELFTEST_WATCHDOG, hw);
                }
                self.inputs = None;
                self.phase = Phase::SelfTest(SelfTest::Recover {
                    at: now + WDT_RECOVER,
                });
            }
            SelfTest::Watchdog { since } if now - since > WDT_MAX => {
                self.kick = true;
                self.fail(FaultCode::SELFTEST_WATCHDOG, hw);
            }
            SelfTest::Recover { at } if now >= at => {
                // The cause of this fault is known (the test): one more edge (rule 2).
                hw.set_latch_clr(true);
                hw.set_latch_clr(false);
                self.phase = Phase::SelfTest(SelfTest::LatchClear { at: now });
            }
            SelfTest::LatchClear { .. } if !self.kill => {
                // The expanders were reset by RLY_EN: set them up again (F5).
                if !self.set_up(hw) {
                    let code = self.fault;
                    return self.fail(code, hw);
                }
                self.tested = true;
                self.phase = Phase::Run;
            }
            SelfTest::LatchClear { at } if now >= at + LOOP_WAIT => {
                self.fail(FaultCode::SELFTEST_LATCH, hw);
            }
            _ => {}
        }
    }

    /// Start-up input plausibility (self-test step 3). A warning only: fault 10.
    fn check_inputs(&mut self) {
        let Some(w) = self.inputs else { return };
        let bit = |p: ExpPin| w[usize::from(p.addr - EXPANDERS[0])] & (1 << p.bit) != 0;
        let tx_any = bit(exp::TX_ANY);
        let rf = ANTENNAS
            .into_iter()
            .any(|c| rf_det(c).is_some_and(|p| !bit(p)));
        let bias_ok = (w[3] >> 4) & BIAS_EN != 0;
        if tx_any || bit(exp::R1_K0) != tx_any || rf || bias_ok {
            self.fault = FaultCode::SELFTEST_INPUT;
        }
    }

    /// Self-test failed: open SAFE and stay stopped until a power cycle.
    fn fail<H: BoxHw>(&mut self, code: FaultCode, hw: &mut H) {
        hw.set_mcu_en_n(true);
        self.kick = true;
        self.fault = code;
        self.clear_state();
        self.inputs = None;
        self.phase = Phase::Failed;
    }

    /// Forget the relay state: the relays are off (expanders reset or set up).
    fn clear_state(&mut self) {
        self.routes = [Route::default(); 3];
        self.bias = ColMask::EMPTY;
        self.k0 = [K0::Off; 3];
        self.switching = None;
    }

    fn drop_to_wait(&mut self, now: Ms) {
        self.clear_state();
        self.inputs = None;
        self.phase = Phase::WaitSafe {
            since: now,
            startup: false,
        };
    }

    fn permit_out(&self) -> bool {
        self.k0.iter().any(|&k| k != K0::Off)
    }

    /// An expander is lost in Run. With a permit out the box must not touch K0
    /// (F13): it opens SAFE. Without, it sets the expanders up again.
    fn on_lost<H: BoxHw>(&mut self, now: Ms, l: Lost, hw: &mut H) {
        if l.nack {
            self.fault = FaultCode::EXPANDER_NACK;
        }
        if self.permit_out() {
            self.stop(false, hw);
        } else {
            self.drop_to_wait(now);
        }
    }

    fn on_link_lost<H: BoxHw>(&mut self, hw: &mut H) {
        if self.phase == Phase::Failed {
            return; // keep the self-test fault code
        }
        if self.phase == Phase::Run && self.permit_out() {
            self.fault = FaultCode::LINK_TIMEOUT_PERMIT;
            self.stop(true, hw);
        } else {
            // P-02: hold the routes, flag the fault, wait for the link.
            self.fault = FaultCode::LINK_TIMEOUT;
        }
    }

    /// Open SAFE (MCU_EN_N = 1). K0 is not written: RLY_EN low resets U903 in
    /// hardware, and the shack inhibits every radio (F12, F13).
    fn stop<H: BoxHw>(&mut self, link: bool, hw: &mut H) {
        hw.set_mcu_en_n(true);
        self.held = self.k0.map(|k| k != K0::Off);
        self.clear_state();
        self.inputs = None;
        self.link_lost_stop = link;
        self.phase = Phase::Stopped;
    }

    fn exit_stop<H: BoxHw>(&mut self, now: Ms, hw: &mut H) {
        self.held = [false; 3];
        self.link_lost_stop = false;
        hw.set_mcu_en_n(false);
        self.phase = Phase::WaitSafe {
            since: now,
            startup: false,
        };
    }

    // ---------------------------------------------------------------- expanders

    /// Read configuration and pins of all four expanders. A configuration at
    /// its reset value means the expander was reset.
    fn read<H: BoxHw>(&mut self, hw: &mut H) -> Result<(), Lost> {
        let mut inputs = [0; 4];
        for (i, addr) in EXPANDERS.into_iter().enumerate() {
            let x = Pca9539::new(addr);
            let cfg = x.read_config(hw.i2c()).map_err(|_| Lost { nack: true })?;
            if cfg != expander_config(addr) {
                return Err(Lost { nack: false });
            }
            inputs[i] = x.read_inputs(hw.i2c()).map_err(|_| Lost { nack: true })?;
            let outs = !cfg;
            if inputs[i] & outs != self.out[i] & outs {
                // Write the commanded state again: a disturbed output register
                // goes back to the checked state (F-3). A stuck pin stays wrong
                // and keeps the fault.
                self.fault = FaultCode::READ_BACK;
                let _ = x.write_outputs(hw.i2c(), self.out[i]);
            }
        }
        self.inputs = Some(inputs);
        self.io_errors = 0; // the bus works again
        Ok(())
    }

    /// Write the output words that differ from `self.out`. True if any was written.
    fn write<H: BoxHw>(&mut self, hw: &mut H, new: [u16; 4]) -> Result<bool, Lost> {
        let mut any = false;
        for (i, addr) in EXPANDERS.into_iter().enumerate() {
            if new[i] != self.out[i] {
                Pca9539::new(addr)
                    .write_outputs(hw.i2c(), new[i])
                    .map_err(|_| Lost { nack: true })?;
                self.out[i] = new[i];
                any = true;
            }
        }
        Ok(any)
    }

    fn pin(&self, p: ExpPin) -> bool {
        let i = usize::from(p.addr - EXPANDERS[0]);
        self.inputs.is_some_and(|w| w[i] & (1 << p.bit) != 0)
    }

    fn tx_any(&self) -> bool {
        self.pin(exp::TX_ANY)
    }

    /// RF detected on the column (detector low). False while the pins are unknown.
    fn rf(&self, col: Col) -> bool {
        self.inputs.is_some() && rf_det(col).is_some_and(|p| !self.pin(p))
    }

    /// K1 bits of these columns, per expander.
    fn k1_bits(cols: ColMask) -> [u16; 4] {
        let mut w = [0; 4];
        for c in ANTENNAS.into_iter().filter(|&c| cols.contains(c)) {
            let p = k1(c).expect("antenna column");
            w[usize::from(p.addr - EXPANDERS[0])] |= 1 << p.bit;
        }
        w
    }

    /// Row bits of each radio's accepted route, on its own expander.
    fn row_bits(&self) -> [u16; 4] {
        let mut w = [0; 4];
        for r in Radio::ALL {
            let route = self.routes[r.index()];
            for (tx, col) in [(true, route.tx), (false, route.rx)] {
                if let Some(p) = row_relay(r, tx, col) {
                    w[r.index()] |= 1 << p.bit;
                }
            }
        }
        w
    }

    // ---------------------------------------------------------------- switching

    /// One step of the section 8 sequence, if due. Each write only opens or only
    /// closes (F10).
    fn switch_step<H: BoxHw>(&mut self, now: Ms, hw: &mut H) -> Result<(), Lost> {
        let Some(mut sw) = self.switching else {
            return Ok(());
        };
        if now < sw.at {
            return Ok(());
        }
        // No relay moves under RF: read TX_ANY now, and wait while it is 1.
        self.read(hw)?;
        if self.tx_any() {
            return Ok(());
        }
        let rows = self.row_bits();
        let k1_need = Self::k1_bits(used_columns(&self.routes));
        let mut next = self.out;
        let (then, writes) = match sw.step {
            Step::Open => {
                for i in 0..3 {
                    next[i] &= !(ROWS & !rows[i]);
                }
                (Step::K1On, true)
            }
            Step::K1On => {
                for i in 0..4 {
                    next[i] |= k1_need[i];
                }
                (Step::Close, true)
            }
            Step::Close => {
                for i in 0..3 {
                    next[i] |= rows[i];
                }
                (Step::ReadBack, true)
            }
            Step::ReadBack => {
                // `read` above compared every output pin with `out`.
                (Step::K1Off, false)
            }
            Step::K1Off => {
                let all = Self::k1_bits(ColMask::from_bits(0x0F).expect("A1..A4"));
                for i in 0..4 {
                    next[i] &= !(all[i] & !k1_need[i]);
                }
                (Step::Done, true)
            }
            Step::Done => {
                self.switching = None;
                return Ok(());
            }
        };
        let wrote = writes && self.write(hw, next)?;
        sw.step = then;
        sw.at = if wrote {
            now + RELAY_WAIT + IO_MARGIN
        } else {
            now
        };
        self.switching = Some(sw);
        if !wrote {
            // Nothing moved: go on with the next step in this pass.
            return self.switch_step(now, hw);
        }
        Ok(())
    }

    fn k0_step<H: BoxHw>(&mut self, now: Ms, hw: &mut H) -> Result<(), Lost> {
        for r in [Radio::R2, Radio::R3] {
            match self.k0[r.index()] {
                K0::Settling(t) if now >= t + RELAY_WAIT => {
                    self.read(hw)?;
                    if self.pin(k0(r)) {
                        self.k0[r.index()] = K0::On;
                    } else {
                        // `read` set fault 2 already; no permit, K0 off.
                        self.k0_off(r, hw)?;
                    }
                }
                // After a Hello: release only when no RF is on the radio's TX
                // column any more, so K0 never breaks under an RF tail (F-1).
                K0::Releasing(t) if now >= t && !self.rf(self.routes[r.index()].tx) => {
                    self.read(hw)?;
                    if !self.rf(self.routes[r.index()].tx) {
                        self.k0_off(r, hw)?;
                    }
                }
                _ => {}
            }
        }
        Ok(())
    }

    fn k0_off<H: BoxHw>(&mut self, r: Radio, hw: &mut H) -> Result<(), Lost> {
        let mut next = self.out;
        next[2] &= !(1 << k0(r).bit);
        self.write(hw, next)?;
        self.k0[r.index()] = K0::Off;
        Ok(())
    }

    fn bias_check<H: BoxHw>(&mut self, now: Ms, hw: &mut H) -> Result<(), Lost> {
        let Some(w) = self.inputs else { return Ok(()) };
        if now < self.bias_since + BIAS_SETTLE {
            return Ok(());
        }
        let en = self.out[3] & BIAS_EN;
        let bad = en & !(w[3] >> 4);
        if bad != 0 {
            // D-54: EN = 1 and OK = 0 is a fault. Switch that feed off and report.
            let mut next = self.out;
            next[3] &= !bad;
            self.write(hw, next)?;
            self.bias = ColMask::from_bits((en & !bad) as u8).unwrap_or(ColMask::EMPTY);
            self.fault = FaultCode::BIAS_T;
        }
        Ok(())
    }

    // ---------------------------------------------------------------- link

    fn link_rx<H: BoxHw>(&mut self, now: Ms, hw: &mut H) {
        while let Some(b) = hw.uart_read() {
            let Some(frame) = self.decoder.push::<Command>(b) else {
                continue;
            };
            let Some(incoming) = self.link.receive(now, frame) else {
                continue;
            };
            let reply = match incoming {
                Incoming::Execute(Frame {
                    seq,
                    msg: Command::Hello { .. },
                }) => {
                    self.on_hello(now, hw);
                    Frame {
                        seq,
                        msg: Reply::Hello(HelloInfo {
                            version: VERSION,
                            fw: FW_VERSION,
                            rx_only: ColMask::EMPTY.with(RX_ONLY),
                            unit2: UNIT2,
                        }),
                    }
                }
                Incoming::Execute(f) => {
                    let result = self.execute(now, f.msg, hw);
                    self.link.complete(f.seq, result);
                    self.status_frame(f.seq, result)
                }
                Incoming::Repeat { seq, result } => self.status_frame(seq, result),
                Incoming::BadArg { seq } => {
                    self.link.complete(seq, ResultCode::BadArg);
                    self.status_frame(seq, ResultCode::BadArg)
                }
            };
            let mut buf = [0u8; MAX_WIRE];
            let n = reply.encode(&mut buf);
            hw.uart_write(&buf[..n]);
        }
    }

    fn on_hello<H: BoxHw>(&mut self, now: Ms, hw: &mut H) {
        if self.phase == Phase::Stopped {
            self.exit_stop(now, hw);
            return;
        }
        for k in &mut self.k0 {
            if matches!(*k, K0::Settling(_) | K0::On) {
                *k = K0::Releasing(now + HELLO_RELEASE);
            }
        }
    }

    fn execute<H: BoxHw>(&mut self, now: Ms, cmd: Command, hw: &mut H) -> ResultCode {
        let r = match cmd {
            Command::Hello { .. } | Command::Poll => Ok(ResultCode::Ok),
            Command::ClearFault => Ok(self.clear_fault(hw)),
            Command::SetRoute { radio, route } => self.set_route(now, radio, route, hw),
            Command::TxRequest(r) => self.tx_request(now, r, hw),
            Command::TxEnd(r) => self.tx_end(now, r, hw),
            Command::SetBias(m) => self.set_bias(now, m, hw),
        };
        r.unwrap_or_else(|l| {
            self.io_error(now, l, hw);
            ResultCode::NotReady
        })
    }

    /// ClearFault (D-191): after a supervisor trip, one LATCH_CLR edge on operator
    /// request. This is the only edge outside the start-up (rule 2): the host
    /// asks for it and logs it. Without a trip, nothing happens.
    fn clear_fault<H: BoxHw>(&mut self, hw: &mut H) -> ResultCode {
        if !self.tripped {
            return ResultCode::Ok;
        }
        hw.set_latch_clr(true);
        hw.set_latch_clr(false);
        if hw.fault() {
            // RESET_N is still low (3V3 low, or no WDI edge): the latch ignored the edge.
            return ResultCode::NotReady;
        }
        self.tripped = false;
        self.fault = FaultCode::NONE;
        ResultCode::Ok
    }

    fn ready(&self) -> bool {
        self.phase == Phase::Run && !self.kill
    }

    fn set_route<H: BoxHw>(
        &mut self,
        now: Ms,
        radio: Radio,
        route: Route,
        hw: &mut H,
    ) -> Result<ResultCode, Lost> {
        let i = radio.index();
        if !self.ready() {
            return Ok(ResultCode::NotReady);
        }
        if self.k0[i] != K0::Off {
            return Ok(ResultCode::PermitOut);
        }
        if self.switching.is_some() {
            return Ok(ResultCode::Busy);
        }
        if route == self.routes[i] {
            return Ok(ResultCode::Ok);
        }
        if route.tx == Col::Exp && !UNIT2 {
            return Ok(ResultCode::Hazard);
        }
        self.read(hw)?;
        let old = self.routes[i];
        let touched = [old.tx, old.rx, route.tx, route.rx];
        if self.tx_any() || touched.into_iter().any(|c| self.rf(c)) {
            return Ok(ResultCode::TxActive);
        }
        let new = crossbar::with_route(&self.routes, radio, route);
        if crossbar::check(&new, used_columns(&new), self.bias).is_err() {
            return Ok(ResultCode::Hazard);
        }
        self.routes = new;
        self.switching = Some(Switching {
            step: Step::Open,
            at: now,
        });
        Ok(ResultCode::Ok)
    }

    fn tx_request<H: BoxHw>(&mut self, now: Ms, r: Radio, hw: &mut H) -> Result<ResultCode, Lost> {
        let i = r.index();
        if r == Radio::R1 {
            return Ok(ResultCode::BadArg);
        }
        match self.k0[i] {
            K0::On | K0::Settling(_) => return Ok(ResultCode::Ok),
            K0::Releasing(_) if self.ready() => {
                self.k0[i] = K0::On;
                return Ok(ResultCode::Ok);
            }
            _ => {}
        }
        if !self.ready() {
            return Ok(ResultCode::NotReady);
        }
        if self.switching.is_some() {
            return Ok(ResultCode::Busy);
        }
        self.read(hw)?;
        if self.tx_any() {
            return Ok(ResultCode::TxActive);
        }
        let tx = self.routes[i].tx;
        let k1_on = |c: Col| k1(c).is_none_or(|p| self.pin(p));
        if tx == Col::None || !k1_on(tx) || (tx == Col::Exp && !UNIT2) {
            return Ok(ResultCode::NoTxRoute);
        }
        if crossbar::check(&self.routes, used_columns(&self.routes), self.bias).is_err() {
            return Ok(ResultCode::Hazard);
        }
        let mut next = self.out;
        next[2] |= 1 << k0(r).bit;
        self.write(hw, next)?;
        self.k0[i] = K0::Settling(now);
        Ok(ResultCode::Ok)
    }

    fn tx_end<H: BoxHw>(&mut self, now: Ms, r: Radio, hw: &mut H) -> Result<ResultCode, Lost> {
        if r == Radio::R1 {
            return Ok(ResultCode::BadArg);
        }
        if self.phase == Phase::Stopped {
            self.held[r.index()] = false;
            if !self.held.iter().any(|&h| h) {
                self.exit_stop(now, hw);
            }
        } else if self.phase == Phase::Run && self.k0[r.index()] != K0::Off {
            self.k0_off(r, hw)?;
        }
        Ok(ResultCode::Ok)
    }

    fn set_bias<H: BoxHw>(&mut self, now: Ms, m: ColMask, hw: &mut H) -> Result<ResultCode, Lost> {
        if !self.ready() {
            return Ok(ResultCode::NotReady);
        }
        // Rule 8: the feed only on the receive-only port, never with a TX row.
        let only_rx = m.bits() & !ColMask::EMPTY.with(RX_ONLY).bits() == 0;
        if !only_rx || crossbar::check(&self.routes, used_columns(&self.routes), m).is_err() {
            return Ok(ResultCode::Hazard);
        }
        let mut next = self.out;
        next[3] = (next[3] & !BIAS_EN) | u16::from(m.bits()) & BIAS_EN;
        if self.write(hw, next)? {
            self.bias_since = now;
        }
        self.bias = m;
        Ok(ResultCode::Ok)
    }

    // ---------------------------------------------------------------- status

    fn status_frame(&self, seq: u8, result: ResultCode) -> Frame<Reply> {
        Frame {
            seq,
            msg: Reply::Status(self.status_with(result)),
        }
    }

    /// The box state, read back from the expanders (link-protocol.md section 4).
    fn status_with(&self, result: ResultCode) -> Status {
        let w = self.inputs.unwrap_or([0; 4]);
        let first = |word: u16, from: u8| {
            (0..5)
                .find(|b| word & (1 << (from + b)) != 0)
                .map_or(Col::None, |b| Col::ALL[usize::from(b) + 1])
        };
        let routes = Radio::ALL.map(|r| Route {
            tx: first(w[r.index()], 0),
            rx: first(w[r.index()], 5),
        });
        let mask = |f: &dyn Fn(Col) -> bool| {
            ANTENNAS
                .into_iter()
                .filter(|&c| f(c))
                .fold(ColMask::EMPTY, ColMask::with)
        };
        let bias_ok = (w[3] >> 4) as u8 & 0x0F;
        Status {
            result,
            flags: Flags {
                ready: self.ready(),
                kill: self.kill,
                tx_any: self.tx_any(),
                switching: self.switching.is_some(),
                link_lost_stop: self.link_lost_stop,
                unit2: UNIT2,
            },
            permit_r2: self.k0[1] == K0::On,
            permit_r3: self.k0[2] == K0::On,
            routes,
            k1: mask(&|c| k1(c).is_some_and(|p| self.pin(p))),
            rfdet: mask(&|c| self.rf(c)),
            bias_en: ColMask::from_bits(w[3] as u8 & 0x0F).unwrap_or(ColMask::EMPTY),
            bias_ok: ColMask::from_bits(bias_ok).unwrap_or(ColMask::EMPTY),
            fault: self.fault,
        }
    }
}
