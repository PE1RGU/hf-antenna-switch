//! The box, unit 1: the RF board (hardware/unit/rf-board, docs/design/rf-board.md)
//! with the controller board on top (hardware/unit/controller-board,
//! docs/design/controller-board.md).
//!
//! Logic as in verify_logic.py and the SAFE loop of verify_system.py:
//! - Fault latch (D-59): PRE_N = RESET_N of the supervisor, CLK = LATCH_CLR, D = 0.
//!   Q = FAULT. The supervisor does not reset the MCU: a hung MCU keeps running.
//! - READY (D-62, D-104): U15 = NOR(MCU_EN_N, FAULT), U16 = AND(U15, RF_A2_N). READY
//!   closes the box end of the SAFE loop; KILL = no loop current.
//! - Safety gate U14 (D-59): RLY_EN = NOR(KILL, MCU_EN_N, FAULT). RLY_EN is the
//!   RESET of all four expanders and switches +12V_SW for the row relays and K1.
//! - K0 (D-27, D-63): on +12V_RLY, not switched by RLY_EN. R1 K0 follows TX_ANY,
//!   the PTT loop (pair 2), in hardware; R2 and R3 K0 come from U903.
//! - Coil gate = expander pin level if the pin is an output, else 0 (100k pull-down).
//! - RF: a radio's RF follows the closed contacts (K0, the row relays, K1). The
//!   detectors see RF on a column; RF on A2 opens READY (D-104).
//!
//! Simplifications: the RF detectors have no hold time; RF follows the contacts as
//! they were at the start of the step, so a contact change shows in the RF signals
//! one step later (1 ms with [`BoxBoard::run`]). The I2C SDA select (JP11) and the
//! unit 2 EXP header are not modelled.
//!
//! # Use
//!
//! As the shack board: [`BoxBoard::set_env`] changes the outside world,
//! [`BoxBoard::step_to`] and [`BoxBoard::run`] move time, the firmware side uses the
//! [`Board`] trait. The trace names are the net names (`RLY_EN`, `KILL`, `TX_ANY`,
//! the expander pins as `R1_TX1_DRV`) and the relay references (`K102`: high = COM
//! on NO). [`BoxBoard::hazards`] checks the contacts against H1 to H4, and
//! [`BoxBoard::hot_switches`] lists every contact that moved under RF.
//!
//! The shack end of the data link is open to the test: [`BoxBoard::shack_send`] and
//! [`BoxBoard::shack_recv`].

use crate::lvc1g74::Lvc1g74;
use crate::pca9539::Pca9539;
use crate::rt1::{Contact, Rt1, Rt1Timing};
use crate::tps3823::{Corner, Tps3823};
use box_core::board::{EXPANDERS, ExpPin, RX_ONLY, gpio};
use embedded_hal::i2c::{ErrorKind, Operation};
use link_proto::{Col, Radio};
use sim_core::hal::Board;
use sim_core::i2c::{self, I2cDevice};
use sim_core::uart::UartLine;
use sim_core::{SimTime, Trace, TraceKind};

/// Relay references: K0 per radio.
const K0_NAMES: [&str; 3] = ["K101", "K201", "K301"];
/// Relay references: row relays per radio, TX then RX, columns A1..A4 and EXP.
const ROW_NAMES: [[[&str; 5]; 2]; 3] = [
    [
        ["K102", "K103", "K104", "K105", "K106"],
        ["K107", "K108", "K109", "K110", "K111"],
    ],
    [
        ["K202", "K203", "K204", "K205", "K206"],
        ["K207", "K208", "K209", "K210", "K211"],
    ],
    [
        ["K302", "K303", "K304", "K305", "K306"],
        ["K307", "K308", "K309", "K310", "K311"],
    ],
];
/// Relay references: K1 per antenna column.
const K1_NAMES: [&str; 4] = ["K401", "K501", "K601", "K701"];
/// Index of the receive-only column in a row.
const A2: usize = RX_ONLY as usize - 1;

/// Everything outside the box the test can change.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Env {
    /// +5V present: the logic of both boards (3V3 from the LP2985 on each).
    pub power: bool,
    /// +12V_RLY present: the coil supply (K0 direct, the rest through +12V_SW).
    pub rly_supply: bool,
    /// +12V_AUX present: the bias-T supply.
    pub aux_supply: bool,
    /// Controller board on J14. Unplugged: RLY_EN, TX_ANY and RF_A2_N are pulled low.
    pub j14_plugged: bool,
    /// R64 fitted: WDI reaches the supervisor (D-123). Open: the watchdog is off.
    pub wdi_link: bool,
    /// Cat6 #1 intact.
    pub cable_ok: bool,
    /// The shack closes its part of the SAFE loop (pair 3): power, source on, KILL
    /// not pressed. The loop current also needs the box READY switch.
    pub shack_loop: bool,
    /// Current in the PTT loop (pair 2): R1 transmits (TX GND), D-56.
    pub ptt_loop: bool,
    /// Radio sends RF into its port, per radio R1..R3.
    pub radio_rf: [bool; 3],
    /// RF coupled onto an antenna column from outside the matrix paths, for
    /// example from another antenna (A-20). Per column A1..A4.
    pub rf_coupled: [bool; 4],
    /// Short circuit on a bias-T output, per column A1..A4 (D-54).
    pub bias_short: [bool; 4],
    /// Fault injection: the READY photorelay U6 stuck closed. The SAFE loop then
    /// carries current without READY, and only the gate's own MCU_EN_N and FAULT
    /// inputs stop the relays.
    pub ready_stuck_closed: bool,
}

impl Default for Env {
    fn default() -> Self {
        Env {
            power: false,
            rly_supply: true,
            aux_supply: true,
            j14_plugged: true,
            wdi_link: true,
            cable_ok: true,
            shack_loop: true,
            ptt_loop: false,
            radio_rf: [false; 3],
            rf_coupled: [false; 4],
            bias_short: [false; 4],
            ready_stuck_closed: false,
        }
    }
}

/// Derived board signals, traced on every change (net names in brackets).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Signals {
    /// Supervisor output (`RESET_N`). Low: fault latch set.
    pub reset_n: bool,
    /// Fault latch Q (`FAULT`).
    pub fault: bool,
    /// MCU_EN_N line (`MCU_EN_N`): the MCU output, or the R63 pull-up while the pin
    /// floats.
    pub mcu_en_n: bool,
    /// A2 detector output at the controller (`RF_A2_N`). Low = RF on A2, or the
    /// controller unplugged (R36).
    pub rf_a2_n: bool,
    /// READY switch U6 closed (`READY`) = NOR(MCU_EN_N, FAULT) AND RF_A2_N.
    pub ready: bool,
    /// Current in the SAFE loop (`SAFE_CURRENT`).
    pub safe_current: bool,
    /// KILL (`KILL`) = no SAFE loop current. Not latched in the box (S6).
    pub kill: bool,
    /// Safety gate output (`RLY_EN`) = NOR(KILL, MCU_EN_N, FAULT) at the RF board.
    pub rly_en: bool,
    /// Switched coil supply (`12V_SW`) for the row relays and K1.
    pub sw12: bool,
    /// PTT loop at the RF board (`TX_ANY`), also the R1 K0 gate.
    pub tx_any: bool,
    /// Expander interrupt line (`EXP_INT`), active low.
    pub exp_int_n: bool,
    /// U903 IO1_2 or IO1_5 set as an output against the U5 output (`CONTENTION`, F3).
    pub contention: bool,
    /// RF on an antenna column, as the detector sees it (`RF_A1` .. `RF_A4`).
    pub rf_column: [bool; 4],
    /// RF reaches an antenna (`RF_ANT1` .. `RF_ANT4`): column RF and K1 on NO.
    pub rf_antenna: [bool; 4],
    /// RF from another radio reaches this radio's port (`RF_INTO_R1` .. `R3`), H2.
    pub rf_into_radio: [bool; 3],
    /// A transmitting radio finds no antenna and no EXP port (`RF_OPEN_R1` ..
    /// `R3`): it sees an open line (finding F2).
    pub rf_open: [bool; 3],
    /// Bias-T output on (`BIAS_A1` .. `BIAS_A4`).
    pub bias_out: [bool; 4],
}

impl Signals {
    fn list(&self) -> Vec<(&'static str, bool)> {
        const RF_COL: [&str; 4] = ["RF_A1", "RF_A2", "RF_A3", "RF_A4"];
        const RF_ANT: [&str; 4] = ["RF_ANT1", "RF_ANT2", "RF_ANT3", "RF_ANT4"];
        const INTO: [&str; 3] = ["RF_INTO_R1", "RF_INTO_R2", "RF_INTO_R3"];
        const OPEN: [&str; 3] = ["RF_OPEN_R1", "RF_OPEN_R2", "RF_OPEN_R3"];
        const BIAS: [&str; 4] = ["BIAS_A1", "BIAS_A2", "BIAS_A3", "BIAS_A4"];
        let mut v = vec![
            ("RESET_N", self.reset_n),
            ("FAULT", self.fault),
            ("MCU_EN_N", self.mcu_en_n),
            ("RF_A2_N", self.rf_a2_n),
            ("READY", self.ready),
            ("SAFE_CURRENT", self.safe_current),
            ("KILL", self.kill),
            ("RLY_EN", self.rly_en),
            ("12V_SW", self.sw12),
            ("TX_ANY", self.tx_any),
            ("EXP_INT", self.exp_int_n),
            ("CONTENTION", self.contention),
        ];
        v.extend(RF_COL.into_iter().zip(self.rf_column));
        v.extend(RF_ANT.into_iter().zip(self.rf_antenna));
        v.extend(INTO.into_iter().zip(self.rf_into_radio));
        v.extend(OPEN.into_iter().zip(self.rf_open));
        v.extend(BIAS.into_iter().zip(self.bias_out));
        v
    }
}

/// A breach of the crossbar rules, found in the contact positions
/// (verify_logic.py section 7). A bouncing contact counts as closed.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Hazard {
    /// H1: two TX rows on one column.
    TwoTx(Col),
    /// H2: a TX row and a row of another radio on one column.
    TxIntoRadio(Col),
    /// H3: a TX row on the receive-only column.
    TxOnRxOnly(Col),
    /// H4: a TX row on a column whose K1 is not settled on NO (open line).
    TxOpenLine(Col),
    /// More than one TX row (`true`) or RX row (`false`) of one radio closed.
    TwoRows(Radio, bool),
}

/// Levels the MCU drives on its direct GPIO. `None` = floating (after power-up,
/// before the firmware drives the pin).
#[derive(Clone, Copy, Debug, Default)]
struct Gpio {
    wdi: Option<bool>,
    latch_clr: Option<bool>,
    mcu_en_n: Option<bool>,
}

/// All 37 relay positions (34 fitted on unit 1).
#[derive(Clone, Debug)]
struct Relays {
    k0: [Rt1; 3],
    /// `row[radio][0 = TX, 1 = RX][column A1..A4, EXP]`.
    row: [[[Rt1; 5]; 2]; 3],
    k1: [Rt1; 4],
}

/// Where RF is, from the contact positions.
#[derive(Clone, Copy, Debug, Default)]
struct Rf {
    bus: [[bool; 2]; 3],
    column: [bool; 4],
    exp: [bool; 3],
}

/// The box board pair: parts, wiring, relays and the board end of the data link.
///
/// Make one with [`BoxBoard::new`]. It starts unpowered at t = 0.
pub struct BoxBoard {
    now: SimTime,
    env: Env,
    gpio: Gpio,
    sup: Tps3823,
    fault_ff: Lvc1g74,
    /// The expanders U901, U902, U903, U1001 (addresses 0x74 to 0x77). Public so a
    /// test can inject faults (`force_nack`) or read registers.
    pub exp: [Pca9539; 4],
    relays: Relays,
    from_shack: UartLine,
    to_shack: UartLine,
    sig: Signals,
    exp_pins: [u16; 4],
    contacts: Vec<bool>,
    hot: Vec<(SimTime, &'static str)>,
    /// Record of every signal change, relay contact change, I2C transfer and UART
    /// byte to the shack.
    pub trace: Trace,
}

impl BoxBoard {
    /// Board at t = 0, unpowered. `corner` sets the supervisor timing, `relays`
    /// the RT1 timing of all relays.
    pub fn new(corner: Corner, relays: Rt1Timing) -> Self {
        let k = Rt1::new(relays);
        let mut b = BoxBoard {
            now: SimTime::ZERO,
            env: Env::default(),
            gpio: Gpio::default(),
            sup: Tps3823::new(corner),
            fault_ff: Lvc1g74::new(),
            exp: Default::default(),
            relays: Relays {
                k0: [(); 3].map(|_| k.clone()),
                row: [(); 3].map(|_| [(); 2].map(|_| [(); 5].map(|_| k.clone()))),
                k1: [(); 4].map(|_| k.clone()),
            },
            from_shack: UartLine::new(9600),
            to_shack: UartLine::new(9600),
            sig: Signals::default(),
            exp_pins: [0; 4],
            contacts: Vec::new(),
            hot: Vec::new(),
            trace: Trace::new(),
        };
        b.settle();
        b
    }

    /// The present outside world.
    pub fn env(&self) -> Env {
        self.env
    }

    /// Change the outside world at the present time.
    pub fn set_env(&mut self, f: impl FnOnce(&mut Env)) {
        f(&mut self.env);
        self.settle();
    }

    /// The derived board signals after the last settle.
    pub fn signals(&self) -> Signals {
        self.sig
    }

    /// Level of one expander pin.
    pub fn exp_pin(&self, p: ExpPin) -> bool {
        self.expander(p.addr).pin(p.bit)
    }

    fn expander(&self, addr: u8) -> &Pca9539 {
        &self.exp[usize::from(addr - EXPANDERS[0])]
    }

    /// Contact of K0 of radio `r`. On NO = the radio on its TX row.
    pub fn k0(&self, r: Radio) -> Contact {
        self.relays.k0[r.index()].contact()
    }

    /// Contact of the row relay of radio `r`, TX row (`tx`) or RX row, column
    /// `col`. On NO = the row joins the column.
    ///
    /// # Panics
    ///
    /// For [`Col::None`].
    pub fn row(&self, r: Radio, tx: bool, col: Col) -> Contact {
        let c = box_core::board::col_index(col).expect("a real column");
        self.relays.row[r.index()][usize::from(!tx)][c].contact()
    }

    /// Contact of K1 of antenna column `col` (A1..A4). On NO = antenna on the
    /// column; on NC = antenna parked on the bleed.
    ///
    /// # Panics
    ///
    /// For EXP and [`Col::None`].
    pub fn k1(&self, col: Col) -> Contact {
        let c = box_core::board::col_index(col)
            .filter(|&c| c < 4)
            .expect("A1..A4");
        self.relays.k1[c].contact()
    }

    /// Every relay contact that moved while RF was on it: time and relay
    /// reference. Rule F10 and the switching sequence must keep this empty.
    pub fn hot_switches(&self) -> &[(SimTime, &'static str)] {
        &self.hot
    }

    /// The crossbar rules H1 to H4, and one TX and one RX row per radio, checked
    /// against the present contact positions. Empty = no hazard.
    pub fn hazards(&self) -> Vec<Hazard> {
        let r = &self.relays;
        let mut out = Vec::new();
        for c in 0..4 {
            let col = Col::ALL[c + 1];
            let tx: Vec<usize> = (0..3)
                .filter(|&n| r.row[n][0][c].contact().on_no())
                .collect();
            let rx: Vec<usize> = (0..3)
                .filter(|&n| r.row[n][1][c].contact().on_no())
                .collect();
            if tx.len() > 1 {
                out.push(Hazard::TwoTx(col));
            }
            if tx.iter().any(|t| tx.iter().chain(&rx).any(|o| o != t)) {
                out.push(Hazard::TxIntoRadio(col));
            }
            if !tx.is_empty() && c == A2 {
                out.push(Hazard::TxOnRxOnly(col));
            }
            if !tx.is_empty() && r.k1[c].contact() != Contact::No {
                out.push(Hazard::TxOpenLine(col));
            }
        }
        for radio in Radio::ALL {
            for (t, tx) in [(0, true), (1, false)] {
                let rows = &r.row[radio.index()][t];
                if rows.iter().filter(|k| k.contact().on_no()).count() > 1 {
                    out.push(Hazard::TwoRows(radio, tx));
                }
            }
        }
        out
    }

    /// Move time forward to `t` and settle once.
    ///
    /// # Panics
    ///
    /// If `t` is earlier than the present time.
    pub fn step_to(&mut self, t: SimTime) {
        assert!(t >= self.now, "time runs forward");
        self.now = t;
        self.settle();
    }

    /// Run for `dt` in 1 ms steps.
    pub fn run(&mut self, dt: SimTime) {
        let end = self.now + dt;
        while self.now < end {
            let next = (self.now + SimTime::ms(1)).min(end);
            self.step_to(next);
        }
    }

    /// Shack end of the data link: a byte from the shack (pair 1). It arrives at
    /// the MCU one byte time later, or never if the cable is cut.
    pub fn shack_send(&mut self, byte: u8) {
        self.from_shack.send(self.now, byte);
    }

    /// Shack end of the data link: next byte that reached the shack (pair 4).
    pub fn shack_recv(&mut self) -> Option<u8> {
        self.to_shack.recv(self.now)
    }

    /// The shack to box line (pair 1), for example to set a fault filter.
    pub fn from_shack_line(&mut self) -> &mut UartLine {
        &mut self.from_shack
    }

    /// The box to shack line (pair 4), for example to set a fault filter.
    pub fn to_shack_line(&mut self) -> &mut UartLine {
        &mut self.to_shack
    }

    /// RF from the contacts: each transmitting radio and each coupled column is a
    /// source; RF spreads through every closed contact. `only` limits the
    /// sources to one radio and leaves out the coupled RF.
    fn rf_paths(&self, only: Option<usize>) -> Rf {
        let e = &self.env;
        let r = &self.relays;
        let mut rf = Rf::default();
        for n in 0..3 {
            if e.radio_rf[n] && only.is_none_or(|o| o == n) {
                let k0 = r.k0[n].contact();
                rf.bus[n][0] |= k0.on_no();
                rf.bus[n][1] |= k0.on_nc();
            }
        }
        if only.is_none() {
            rf.column = e.rf_coupled;
        }
        loop {
            let before = (rf.bus, rf.column, rf.exp);
            for n in 0..3 {
                for t in 0..2 {
                    for c in 0..5 {
                        if !r.row[n][t][c].contact().on_no() {
                            continue;
                        }
                        let col = if c < 4 {
                            &mut rf.column[c]
                        } else {
                            &mut rf.exp[n]
                        };
                        let on = rf.bus[n][t] || *col;
                        rf.bus[n][t] = on;
                        *col = on;
                    }
                }
            }
            if (rf.bus, rf.column, rf.exp) == before {
                return rf;
            }
        }
    }

    #[allow(
        clippy::needless_range_loop,
        reason = "radio, row and column indexes over several parallel tables read clearest"
    )]
    fn settle(&mut self) {
        let now = self.now;
        let e = self.env;
        let p = e.power;
        if !p {
            self.gpio = Gpio::default();
        }

        // Controller board: supervisor, fault latch, READY, KILL, the gate.
        // R61 pulls a floating WDI low; with R64 open the supervisor's WDI floats.
        let wdi = e.wdi_link.then(|| self.gpio.wdi.unwrap_or(false));
        let reset_n = self.sup.update(now, p, wdi);
        let fault = if p {
            let clr = self.gpio.latch_clr.unwrap_or(false); // R62 pull-down
            self.fault_ff.update(reset_n, true, clr, false)
        } else {
            self.fault_ff.power_off();
            true
        };
        let mcu_en_n = !p || self.gpio.mcu_en_n.unwrap_or(true); // R63 pull-up
        let rf = self.rf_paths(None);
        let rf_a2_n = p && e.j14_plugged && !rf.column[A2];
        let ready = p && !mcu_en_n && !fault && rf_a2_n;
        let safe_current = p && e.cable_ok && e.shack_loop && (ready || e.ready_stuck_closed);
        let kill = !safe_current;
        let rly_en = p && e.j14_plugged && !(kill || mcu_en_n || fault);
        let sw12 = rly_en && e.rly_supply;
        let tx_any = p && e.j14_plugged && e.cable_ok && e.ptt_loop;

        // RF board: expanders (RESET = RLY_EN) and the levels on their input pins.
        for x in &mut self.exp {
            x.set_reset(!rly_en);
        }
        let u1001 = self.exp[3].pins();
        let bias_out: [bool; 4] =
            std::array::from_fn(|k| p && u1001 & (1 << k) != 0 && e.aux_supply && !e.bias_short[k]);
        let det = |c: usize| p && !rf.column[c]; // LM2901 open collector, 10k pull-up
        let bit = |on: bool, b: u8| u16::from(on) << b;
        let ext = [
            bit(det(0), 12) | bit(det(1), 13),
            bit(det(2), 12) | bit(det(3), 13),
            bit(tx_any, 10) | bit(tx_any, 13),
            (0..4).fold(0, |w, k| w | bit(bias_out[k], 4 + k as u8)),
        ];
        for (x, w) in self.exp.iter_mut().zip(ext) {
            x.set_external(w);
        }
        let u903 = &self.exp[2];
        let contention =
            !u903.in_reset() && u903.config_reg() & (1 << 10 | 1 << 13) != (1 << 10 | 1 << 13);
        let exp_int_n = !(p && e.j14_plugged) || self.exp.iter().all(Pca9539::int_n);

        // Coils, then the contacts.
        let pins = self.exp.each_ref().map(Pca9539::pins);
        let on = |w: u16, b: usize| w & (1 << b) != 0;
        let hot_k0: [bool; 3] =
            std::array::from_fn(|n| e.radio_rf[n] || rf.bus[n].iter().any(|&b| b));
        for n in 0..3 {
            let gate = if n == 0 { tx_any } else { on(pins[2], 10 + n) };
            let k = &mut self.relays.k0[n];
            let was = k.contact();
            let now_c = k.update(now, gate && e.rly_supply);
            if was != now_c && hot_k0[n] {
                self.hot.push((now, K0_NAMES[n]));
                self.trace.note(now, format!("hot switch {}", K0_NAMES[n]));
            }
            for t in 0..2 {
                for c in 0..5 {
                    let fitted = !(t == 0 && c == A2);
                    let coil = on(pins[n], t * 5 + c) && sw12 && fitted;
                    let k = &mut self.relays.row[n][t][c];
                    let was = k.contact();
                    let now_c = k.update(now, coil);
                    let col_rf = if c < 4 { rf.column[c] } else { rf.exp[n] };
                    if was != now_c && (rf.bus[n][t] || col_rf) {
                        self.hot.push((now, ROW_NAMES[n][t][c]));
                        self.trace
                            .note(now, format!("hot switch {}", ROW_NAMES[n][t][c]));
                    }
                }
            }
        }
        for c in 0..4 {
            let coil = on(pins[c / 2], 10 + c % 2) && sw12;
            let k = &mut self.relays.k1[c];
            let was = k.contact();
            let now_c = k.update(now, coil);
            if was != now_c && rf.column[c] {
                self.hot.push((now, K1_NAMES[c]));
                self.trace.note(now, format!("hot switch {}", K1_NAMES[c]));
            }
        }

        // RF signals, from the contacts at the start of this step.
        let k1_no: [bool; 4] = std::array::from_fn(|c| self.relays.k1[c].contact().on_no());
        let rf_antenna: [bool; 4] = std::array::from_fn(|c| rf.column[c] && k1_no[c]);
        let mut rf_into_radio = [false; 3];
        let mut rf_open = [false; 3];
        for n in 0..3 {
            let k0 = self.relays.k0[n].contact();
            let at_port = (k0.on_no() && rf.bus[n][0]) || (k0.on_nc() && rf.bus[n][1]);
            rf_into_radio[n] = !e.radio_rf[n] && at_port;
            if e.radio_rf[n] {
                let own = self.rf_paths(Some(n));
                let loaded =
                    own.exp.iter().any(|&x| x) || (0..4).any(|c| own.column[c] && k1_no[c]);
                rf_open[n] = !loaded;
            }
        }

        let link = p && e.cable_ok;
        self.from_shack.cut = !link;
        self.to_shack.cut = !link;

        let sig = Signals {
            reset_n,
            fault,
            mcu_en_n,
            rf_a2_n,
            ready,
            safe_current,
            kill,
            rly_en,
            sw12,
            tx_any,
            exp_int_n,
            contention,
            rf_column: rf.column,
            rf_antenna,
            rf_into_radio,
            rf_open,
            bias_out,
        };
        self.record(sig);
    }

    fn record(&mut self, sig: Signals) {
        let first = self.contacts.is_empty();
        for ((name, new), (_, old)) in sig.list().into_iter().zip(self.sig.list()) {
            if first || new != old {
                self.trace
                    .push(self.now, TraceKind::Signal { name, value: new });
            }
        }
        self.sig = sig;

        for (i, addr) in EXPANDERS.into_iter().enumerate() {
            let pins = self.exp[i].pins();
            for p in box_core::board::exp::ALL.iter().filter(|p| p.addr == addr) {
                let m = 1 << p.bit;
                if first || (pins ^ self.exp_pins[i]) & m != 0 {
                    let value = pins & m != 0;
                    self.trace.push(
                        self.now,
                        TraceKind::Signal {
                            name: p.name,
                            value,
                        },
                    );
                }
            }
            self.exp_pins[i] = pins;
        }

        let r = &self.relays;
        let named = K0_NAMES
            .iter()
            .zip(&r.k0)
            .chain(
                ROW_NAMES
                    .iter()
                    .flatten()
                    .flatten()
                    .zip(r.row.iter().flatten().flatten()),
            )
            .chain(K1_NAMES.iter().zip(&r.k1));
        let mut contacts = Vec::with_capacity(37);
        for (i, (name, k)) in named.enumerate() {
            let on = k.contact().on_no();
            if first || self.contacts[i] != on {
                self.trace
                    .push(self.now, TraceKind::Signal { name, value: on });
            }
            contacts.push(on);
        }
        self.contacts = contacts;
    }

    fn gpio_name(pin: u8) -> &'static str {
        match pin {
            gpio::WDI => "WDI",
            gpio::LATCH_CLR => "LATCH_CLR",
            gpio::MCU_EN_N => "MCU_EN_N_PIN",
            _ => panic!("GPIO{pin} is not a driven output on the box controller"),
        }
    }
}

impl Board for BoxBoard {
    fn now(&self) -> SimTime {
        self.now
    }

    fn i2c(&mut self, addr: u8, ops: &mut [Operation<'_>]) -> Result<(), ErrorKind> {
        let on_bus = self.env.power && self.env.j14_plugged;
        let dev: Option<&mut dyn I2cDevice> = match EXPANDERS.iter().position(|&a| a == addr) {
            Some(i) if on_bus => Some(&mut self.exp[i]),
            _ => None,
        };
        let r = i2c::transact(&mut self.trace, self.now, addr, ops, dev);
        self.settle();
        r
    }

    fn gpio_write(&mut self, pin: u8, high: bool) {
        let name = Self::gpio_name(pin);
        if !self.env.power {
            return;
        }
        let g = &mut self.gpio;
        let slot = match pin {
            gpio::WDI => &mut g.wdi,
            gpio::LATCH_CLR => &mut g.latch_clr,
            _ => &mut g.mcu_en_n,
        };
        // WDI: every write is traced, so a test sees each kick.
        if *slot != Some(high) || pin == gpio::WDI {
            *slot = Some(high);
            self.trace
                .push(self.now, TraceKind::Signal { name, value: high });
        }
        self.settle();
    }

    fn gpio_read(&mut self, pin: u8) -> bool {
        match pin {
            gpio::KILL => self.sig.kill,
            gpio::EXP_INT => self.sig.exp_int_n,
            gpio::FAULT => self.sig.fault, // through R66 1k (D-191)
            _ => panic!("GPIO{pin} is not an input on the box controller"),
        }
    }

    fn spi_write(&mut self, _: &[u8]) {
        panic!("the box controller has no SPI device");
    }

    fn uart_write(&mut self, byte: u8) {
        self.trace.push(
            self.now,
            TraceKind::Uart {
                line: "to_shack",
                byte,
            },
        );
        self.to_shack.send(self.now, byte);
    }

    fn uart_read(&mut self) -> Option<u8> {
        self.from_shack.recv(self.now)
    }

    /// The DevKit USB port is for debugging only on the box: output is dropped.
    fn usb_write(&mut self, _: u8) {}

    fn usb_read(&mut self) -> Option<u8> {
        None
    }
}
