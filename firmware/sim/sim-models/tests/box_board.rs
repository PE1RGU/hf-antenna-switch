//! Box board model against hardware/unit/verify/verify_logic.py, section by
//! section, and the SAFE loop end of verify_system.py section 1.
//! The MCU side goes through the embedded-hal adapters, as the firmware will.

use box_core::board::{
    ADDR_U901, ADDR_U903, ADDR_U1001, EXPANDERS, ExpPin, exp, expander_config, gpio, k1, row_relay,
};
use embedded_hal::i2c::I2c;
use link_proto::{Col, Radio};
use sim_core::SimTime;
use sim_core::hal::{Board, Shared, SimI2c, shared};
use sim_models::box_board::{BoxBoard, Hazard, Signals};
use sim_models::rt1::{Contact, Rt1Timing};
use sim_models::tps3823::Corner;

type B = Shared<BoxBoard>;

fn ms(n: u64) -> SimTime {
    SimTime::ms(n)
}

fn sig(b: &B) -> Signals {
    b.borrow().signals()
}

fn run(b: &B, n: u64) {
    b.borrow_mut().run(ms(n));
}

fn gpio_set(b: &B, pin: u8, high: bool) {
    b.borrow_mut().gpio_write(pin, high);
}

/// One WDI kick: a falling edge.
fn kick(b: &B) {
    gpio_set(b, gpio::WDI, true);
    gpio_set(b, gpio::WDI, false);
}

fn clear_fault(b: &B) {
    gpio_set(b, gpio::LATCH_CLR, false);
    gpio_set(b, gpio::LATCH_CLR, true);
    gpio_set(b, gpio::LATCH_CLR, false);
}

/// Board powered for 300 ms: supervisor out of reset (td 200 ms at Typ). The MCU
/// pins still float.
fn powered() -> B {
    let b = shared(BoxBoard::new(Corner::Typ, Rt1Timing::MAX));
    b.borrow_mut().set_env(|e| e.power = true);
    run(&b, 300);
    b
}

/// Start-up in the F11 order: MCU_EN_N high, LATCH_CLR edge, MCU_EN_N low, then the
/// expanders in the F1 order with every output 0.
fn started() -> B {
    let b = powered();
    kick(&b);
    gpio_set(&b, gpio::MCU_EN_N, true);
    clear_fault(&b);
    gpio_set(&b, gpio::MCU_EN_N, false);
    assert!(sig(&b).rly_en, "RLY_EN after the start-up order");
    for addr in EXPANDERS {
        exp_setup(&b, addr, 0);
    }
    b
}

/// F1 order: output register first, then configuration.
fn exp_setup(b: &B, addr: u8, out: u16) {
    exp_write(b, addr, 2, out);
    exp_write(b, addr, 6, expander_config(addr));
}

fn exp_write(b: &B, addr: u8, reg: u8, word: u16) {
    let [lo, hi] = word.to_le_bytes();
    SimI2c(b.clone()).write(addr, &[reg, lo, hi]).unwrap();
}

fn exp_read(b: &B, addr: u8) -> u16 {
    let mut buf = [0u8; 2];
    SimI2c(b.clone()).write_read(addr, &[0], &mut buf).unwrap();
    u16::from_le_bytes(buf)
}

fn bit(p: ExpPin) -> u16 {
    1 << p.bit
}

fn all_relays_rest(b: &B) -> bool {
    let bb = b.borrow();
    Radio::ALL.iter().all(|&r| {
        Col::ALL[1..]
            .iter()
            .all(|&c| bb.row(r, true, c) == Contact::Nc && bb.row(r, false, c) == Contact::Nc)
    }) && Col::ALL[1..5].iter().all(|&c| bb.k1(c) == Contact::Nc)
}

// ------------------------------------------------------------ section 2 and 3

/// Section 2: RLY_EN = NOR(KILL, MCU_EN_N, FAULT), high in one row only.
///
/// In a sound box KILL is not free: READY opens the loop when MCU_EN_N or FAULT
/// is high. With the READY photorelay stuck closed, KILL follows the shack side of
/// the loop alone, so all 8 rows of the gate table can be set up.
#[test]
fn safety_gate_is_a_nor_of_three() {
    for stuck in [false, true] {
        let mut rows = std::collections::BTreeSet::new();
        let mut on = 0;
        for clear in [false, true] {
            for en_n in [false, true] {
                for loop_closed in [false, true] {
                    let b = powered();
                    b.borrow_mut().set_env(|e| {
                        e.shack_loop = loop_closed;
                        e.ready_stuck_closed = stuck;
                    });
                    if clear {
                        clear_fault(&b);
                    }
                    gpio_set(&b, gpio::MCU_EN_N, en_n);
                    let s = sig(&b);
                    assert_eq!(s.rly_en, !(s.kill || s.mcu_en_n || s.fault));
                    assert_eq!(
                        s.ready,
                        !s.mcu_en_n && !s.fault,
                        "READY = NOR(MCU_EN_N, FAULT)"
                    );
                    rows.insert((s.kill, s.mcu_en_n, s.fault));
                    if s.rly_en {
                        on += 1;
                        assert!(!s.kill && !s.mcu_en_n && !s.fault);
                    }
                }
            }
        }
        assert_eq!(on, 1, "RLY_EN = 1 in one row only");
        assert_eq!(rows.len(), if stuck { 8 } else { 5 }, "rows reached");
    }
}

/// Section 3: every open or missing input gives RLY_EN = 0.
#[test]
fn open_inputs_give_rly_en_low() {
    // MCU not running: GPIO float. MCU_EN_N pulled high, WDI pulled low (the
    // watchdog trips), LATCH_CLR pulled low.
    let b = powered();
    run(&b, 3000);
    let s = sig(&b);
    assert!(s.mcu_en_n && s.fault && !s.rly_en);
    assert!(
        b.borrow().trace.signal("RESET_N").len() > 2,
        "floating WDI: watchdog resets"
    );

    // Cat6 cut: no loop current, KILL high.
    let b = started();
    b.borrow_mut().set_env(|e| e.cable_ok = false);
    assert!(sig(&b).kill && !sig(&b).rly_en);

    // Controller unplugged from J14: R3 pulls RLY_EN low, the expanders are gone.
    let b = started();
    b.borrow_mut().set_env(|e| e.j14_plugged = false);
    let s = sig(&b);
    assert!(!s.rly_en && !s.tx_any && !s.rf_a2_n);
    assert!(SimI2c(b.clone()).write(ADDR_U901, &[2, 0, 0]).is_err());

    // Brown-out: the supervisor sets FAULT; a new clear is needed.
    let b = started();
    b.borrow_mut().set_env(|e| e.power = false);
    run(&b, 50);
    b.borrow_mut().set_env(|e| e.power = true);
    run(&b, 400);
    let s = sig(&b);
    assert!(s.fault && !s.rly_en);
}

// ------------------------------------------------------------ section 4

/// RLY_EN = 0: no row relay or K1 can be on, by two paths: expander reset and
/// +12V_SW off. R2 and R3 K0 drop too (U903 reset, F12).
#[test]
fn rly_en_low_releases_every_switched_coil() {
    let b = started();
    // Every relay driver on; R1_K0_DRV stays an input (F3).
    exp_write(&b, ADDR_U901, 2, 0x0FFF);
    exp_write(&b, 0x75, 2, 0x0FFF);
    exp_write(&b, ADDR_U903, 2, 0x1FFF ^ bit(exp::R1_K0));
    run(&b, 13);
    assert_eq!(b.borrow().row(Radio::R2, false, Col::A4), Contact::No);
    assert_eq!(b.borrow().k1(Col::A3), Contact::No);
    assert_eq!(b.borrow().k0(Radio::R3), Contact::No);
    assert_eq!(
        b.borrow().row(Radio::R1, true, Col::A2),
        Contact::Nc,
        "TX relay at A2 not fitted (D-103)"
    );

    b.borrow_mut().set_env(|e| e.shack_loop = false);
    let s = sig(&b);
    assert!(s.kill && !s.rly_en && !s.sw12);
    assert!(b.borrow().exp.iter().all(|x| x.in_reset()));
    run(&b, 12);
    assert!(all_relays_rest(&b));
    assert_eq!(b.borrow().k0(Radio::R2), Contact::Nc);
    assert_eq!(b.borrow().k0(Radio::R3), Contact::Nc);

    // The loop closes again: KILL is not latched, the expanders come back at
    // their defaults (F5), so nothing switches until the firmware sets them up.
    b.borrow_mut().set_env(|e| e.shack_loop = true);
    run(&b, 20);
    assert!(sig(&b).rly_en);
    assert_eq!(b.borrow().exp[0].config_reg(), 0xFFFF);
    assert!(all_relays_rest(&b));
}

/// Finding F1: configuration before the output register switches coils on at once.
#[test]
fn f1_config_first_switches_coils_on() {
    let b = started();
    // Back to the reset state: an RLY_EN pulse.
    b.borrow_mut().set_env(|e| e.shack_loop = false);
    b.borrow_mut().set_env(|e| e.shack_loop = true);
    exp_write(&b, ADDR_U901, 6, expander_config(ADDR_U901));
    run(&b, 13);
    assert_eq!(
        b.borrow().row(Radio::R1, true, Col::A1),
        Contact::No,
        "output register 0xFFFF after reset: K102 on"
    );

    b.borrow_mut().set_env(|e| e.shack_loop = false);
    run(&b, 12);
    b.borrow_mut().set_env(|e| e.shack_loop = true);
    exp_setup(&b, ADDR_U901, 0);
    run(&b, 13);
    assert!(all_relays_rest(&b), "F1 order: nothing moves");
}

/// Bias-T feeds: the same reset path; EN high and OK low is a fault (D-54).
#[test]
fn bias_t_follows_en_and_reports_a_short() {
    let b = powered();
    assert!(!sig(&b).bias_out[1], "RLY_EN 0: U1001 in reset, feed off");

    let b = started();
    assert!(!sig(&b).bias_out[1], "output 0: feed off");
    exp_write(&b, ADDR_U1001, 2, bit(exp::A2_BIAS_EN));
    assert!(sig(&b).bias_out[1]);
    assert_ne!(exp_read(&b, ADDR_U1001) & bit(exp::A2_BIAS_OK), 0);

    b.borrow_mut().set_env(|e| e.bias_short[1] = true);
    let inputs = exp_read(&b, ADDR_U1001);
    assert_ne!(inputs & bit(exp::A2_BIAS_EN), 0);
    assert_eq!(inputs & bit(exp::A2_BIAS_OK), 0, "EN 1 and OK 0: fault");

    b.borrow_mut().set_env(|e| {
        e.bias_short[1] = false;
        e.aux_supply = false;
    });
    assert_eq!(exp_read(&b, ADDR_U1001) & bit(exp::A2_BIAS_OK), 0);
}

// ------------------------------------------------------------ section 5

/// R1 K0 follows the PTT loop in hardware, also with RLY_EN = 0 (finding F2):
/// the radio then transmits into an open TX row.
#[test]
fn r1_k0_follows_the_ptt_loop() {
    let b = powered();
    assert!(!sig(&b).rly_en);
    b.borrow_mut().set_env(|e| e.ptt_loop = true);
    assert!(sig(&b).tx_any);
    run(&b, 8);
    assert_eq!(b.borrow().k0(Radio::R1), Contact::NoBounce);
    run(&b, 4);
    assert_eq!(
        b.borrow().k0(Radio::R1),
        Contact::No,
        "settled 12 ms after PTT (F7)"
    );
    b.borrow_mut().set_env(|e| e.radio_rf[0] = true);
    run(&b, 1);
    assert!(sig(&b).rf_open[0], "F2: TX into an open line");

    // TX_ANY is read back on U903 IO1_5 and IO1_2.
    let b = started();
    b.borrow_mut().set_env(|e| e.ptt_loop = true);
    let inputs = exp_read(&b, ADDR_U903);
    assert_ne!(inputs & bit(exp::TX_ANY), 0);
    assert_ne!(inputs & bit(exp::R1_K0), 0);

    // No 3V3 on the controller, or the controller unplugged: K0 stays on RX.
    for unplug in [false, true] {
        let b = shared(BoxBoard::new(Corner::Typ, Rt1Timing::MAX));
        b.borrow_mut().set_env(|e| {
            e.power = unplug;
            e.j14_plugged = !unplug;
            e.ptt_loop = true;
        });
        run(&b, 20);
        assert_eq!(b.borrow().k0(Radio::R1), Contact::Nc);
    }

    // No +12V_RLY: K0 cannot move.
    let b = powered();
    b.borrow_mut().set_env(|e| {
        e.rly_supply = false;
        e.ptt_loop = true;
    });
    run(&b, 20);
    assert_eq!(b.borrow().k0(Radio::R1), Contact::Nc);
}

/// Finding F3: U903 IO1_2 and IO1_5 share their nets with the U5 output.
#[test]
fn f3_readback_pins_as_outputs_is_contention() {
    let b = started();
    assert!(!sig(&b).contention);
    exp_write(
        &b,
        ADDR_U903,
        6,
        expander_config(ADDR_U903) & !bit(exp::TX_ANY),
    );
    assert!(sig(&b).contention);
    exp_write(&b, ADDR_U903, 6, expander_config(ADDR_U903));
    assert!(!sig(&b).contention);
}

// ------------------------------------------------------------ section 6

/// Inputs of one sequence scenario, as in verify_logic.py section 6.
struct Scenario {
    name: &'static str,
    vdd_ok: fn(u64) -> bool,
    wdi_fall: fn(u64) -> bool,
    clr_rise: fn(u64) -> bool,
    mcu_en_n: fn(u64) -> bool,
    kill: fn(u64) -> bool,
}

fn every(t: u64, period: u64, start: u64, stop: u64) -> bool {
    (start..stop).contains(&t) && (t - start).is_multiple_of(period)
}

fn up(t: u64) -> bool {
    t >= 10
}
fn kicks(t: u64) -> bool {
    every(t, 250, 400, u64::MAX)
}
fn kicks_until_3s(t: u64) -> bool {
    every(t, 250, 400, 3000)
}
fn clr_600(t: u64) -> bool {
    t == 600
}
fn en_650(t: u64) -> bool {
    t < 650
}
fn never(_: u64) -> bool {
    false
}

const SCENARIOS: [Scenario; 7] = [
    Scenario {
        name: "S1",
        vdd_ok: up,
        wdi_fall: kicks,
        clr_rise: clr_600,
        mcu_en_n: en_650,
        kill: never,
    },
    Scenario {
        name: "S2",
        vdd_ok: up,
        wdi_fall: kicks_until_3s,
        clr_rise: clr_600,
        mcu_en_n: en_650,
        kill: never,
    },
    Scenario {
        name: "S3",
        vdd_ok: up,
        wdi_fall: kicks_until_3s,
        clr_rise: |t| every(t, 100, 600, u64::MAX),
        mcu_en_n: en_650,
        kill: never,
    },
    Scenario {
        name: "S4",
        vdd_ok: up,
        wdi_fall: kicks,
        clr_rise: |t| t == 50,
        mcu_en_n: never,
        kill: never,
    },
    Scenario {
        name: "S5",
        vdd_ok: |t| t >= 10 && !(3000..3050).contains(&t),
        wdi_fall: kicks,
        clr_rise: |t| t == 600 || t == 3600,
        mcu_en_n: en_650,
        kill: never,
    },
    Scenario {
        name: "S6",
        vdd_ok: up,
        wdi_fall: kicks,
        clr_rise: clr_600,
        mcu_en_n: en_650,
        kill: |t| (4000..5000).contains(&t),
    },
    // S7: WDI kicked from a timer interrupt while the main loop hangs: the
    // inputs of S1, the hang is invisible to the watchdog (rule 1).
    Scenario {
        name: "S7",
        vdd_ok: up,
        wdi_fall: kicks,
        clr_rise: clr_600,
        mcu_en_n: en_650,
        kill: never,
    },
];

/// RLY_EN = 1 intervals in ms, start and end.
type Intervals = &'static [(u64, u64)];

/// RLY_EN = 1 intervals in ms over 9 s.
fn rly_en_intervals(s: &Scenario, corner: Corner) -> Vec<(u64, u64)> {
    const T: u64 = 9000;
    let b = shared(BoxBoard::new(corner, Rt1Timing::MAX));
    for t in 0..T {
        b.borrow_mut().step_to(ms(t));
        b.borrow_mut().set_env(|e| {
            e.power = (s.vdd_ok)(t);
            e.shack_loop = !(s.kill)(t);
        });
        gpio_set(&b, gpio::MCU_EN_N, (s.mcu_en_n)(t));
        if (s.wdi_fall)(t) {
            kick(&b);
        }
        if (s.clr_rise)(t) {
            clear_fault(&b);
        }
    }
    let mut iv = Vec::new();
    let mut start = None;
    for (t, on) in b.borrow().trace.signal("RLY_EN") {
        match (on, start) {
            (true, None) => start = Some(t.as_ms()),
            (false, Some(a)) => {
                iv.push((a, t.as_ms()));
                start = None;
            }
            _ => {}
        }
    }
    if let Some(a) = start {
        iv.push((a, T));
    }
    iv
}

/// Section 6: the supervisor, watchdog and fault latch, scenarios S1 to S7 at the
/// datasheet minimum and maximum timing. The intervals are the ones in
/// logic-verification.md.
#[test]
fn supervisor_sequences_match_verify_logic() {
    let want: [(&str, [Intervals; 2]); 7] = [
        ("S1", [&[(650, 9000)], &[(650, 9000)]]),
        ("S2", [&[(650, 3800)], &[(650, 5400)]]),
        (
            "S3",
            [
                &[
                    (650, 3800),
                    (4000, 4820),
                    (5000, 5840),
                    (6000, 6860),
                    (7000, 7880),
                    (8000, 8900),
                ],
                &[(650, 5400), (5700, 8200), (8500, 9000)],
            ],
        ),
        ("S4", [&[], &[]]),
        (
            "S5",
            [&[(650, 3000), (3600, 9000)], &[(650, 3000), (3600, 9000)]],
        ),
        (
            "S6",
            [&[(650, 4000), (5000, 9000)], &[(650, 4000), (5000, 9000)]],
        ),
        ("S7", [&[(650, 9000)], &[(650, 9000)]]),
    ];
    for (s, (name, w)) in SCENARIOS.iter().zip(want) {
        assert_eq!(s.name, name);
        for (corner, w) in [Corner::Min, Corner::Max].into_iter().zip(w) {
            assert_eq!(rly_en_intervals(s, corner), w, "{name} at {corner:?}");
        }
    }
}

// ------------------------------------------------------------ section 7

/// Write one crossbar state of column `col`: bits 0..5 = R1 TX, R1 RX, R2 TX,
/// R2 RX, R3 TX, R3 RX; bit 6 = K1. Every other relay off.
fn set_column_state(b: &B, col: Col, st: u8) {
    let mut out = [0u16; 3];
    for r in Radio::ALL {
        for (k, tx) in [(0, true), (1, false)] {
            if st & 1 << (r.index() * 2 + k) != 0 {
                let p = row_relay(r, tx, col).unwrap();
                out[r.index()] |= bit(p);
            }
        }
    }
    if st & 1 << 6 != 0 {
        let p = k1(col).unwrap();
        out[usize::from(p.addr - ADDR_U901)] |= bit(p);
    }
    for (i, w) in out.into_iter().enumerate() {
        exp_write(b, EXPANDERS[i], 2, w);
    }
}

/// Section 7: all 128 relay states of each column, classified from the contacts
/// of the model. A1, A3, A4 as in logic-verification.md (22 allowed; H1 64, H2 100,
/// H4 56). On A2 the TX relays are not fitted: no commanded state reaches a TX
/// contact, so every state is allowed in hardware (SR-01).
#[test]
fn crossbar_states_per_column() {
    let b = started();
    for col in [Col::A1, Col::A2, Col::A3, Col::A4] {
        let (mut ok, mut h1, mut h2, mut h3, mut h4) = (0, 0, 0, 0, 0);
        for st in 0..128u8 {
            set_column_state(&b, col, st);
            run(&b, 13);
            kick(&b);
            let hz: Vec<Hazard> = b.borrow().hazards();
            let has = |f: fn(Col) -> Hazard| hz.contains(&f(col));
            h1 += usize::from(has(Hazard::TwoTx));
            h2 += usize::from(has(Hazard::TxIntoRadio));
            h3 += usize::from(has(Hazard::TxOnRxOnly));
            h4 += usize::from(has(Hazard::TxOpenLine));
            ok += usize::from(hz.is_empty());
        }
        if col == Col::A2 {
            assert_eq!((ok, h1, h2, h3, h4), (128, 0, 0, 0, 0), "{col:?}");
        } else {
            assert_eq!((ok, h1, h2, h3, h4), (22, 64, 100, 0, 56), "{col:?}");
        }
        assert!(sig(&b).rly_en);
    }
}

/// One TX and one RX row per radio across the columns.
#[test]
fn two_rows_of_one_radio_is_a_hazard() {
    let b = started();
    let w = bit(row_relay(Radio::R2, false, Col::A1).unwrap())
        | bit(row_relay(Radio::R2, false, Col::A3).unwrap());
    exp_write(&b, 0x75, 2, w);
    run(&b, 13);
    assert_eq!(b.borrow().hazards(), [Hazard::TwoRows(Radio::R2, false)]);
}

// ------------------------------------------------------------ sections 8 and 9

/// KILL to contacts: RLY_EN drops at once; the contacts leave NO after the release
/// time (6 ms) and settle after the NC bounce (6 ms).
#[test]
fn kill_to_contacts_open_timing() {
    let b = started();
    exp_write(&b, ADDR_U901, 2, bit(exp::R1_RX1) | bit(exp::A1_K1));
    run(&b, 13);
    b.borrow_mut().set_env(|e| e.shack_loop = false);
    assert!(!sig(&b).rly_en);
    run(&b, 5);
    assert_eq!(b.borrow().row(Radio::R1, false, Col::A1), Contact::No);
    run(&b, 1);
    assert_eq!(b.borrow().row(Radio::R1, false, Col::A1), Contact::NcBounce);
    run(&b, 6);
    assert_eq!(b.borrow().row(Radio::R1, false, Col::A1), Contact::Nc);
}

// ------------------------------------------------------------ RF paths

/// R1 on A1: RF reaches the antenna, no hazard and no hot switching. Opening K1
/// under RF is a hot switch and leaves the radio on an open line.
#[test]
fn rf_follows_the_contacts() {
    let b = started();
    exp_write(&b, ADDR_U901, 2, bit(exp::R1_TX1) | bit(exp::A1_K1));
    run(&b, 13);
    b.borrow_mut().set_env(|e| e.ptt_loop = true);
    run(&b, 13);
    b.borrow_mut().set_env(|e| e.radio_rf[0] = true);
    run(&b, 1);
    let s = sig(&b);
    assert!(s.rf_column[0] && s.rf_antenna[0] && !s.rf_open[0]);
    assert!(b.borrow().hazards().is_empty());
    assert!(b.borrow().hot_switches().is_empty());

    exp_write(&b, ADDR_U901, 2, bit(exp::R1_TX1));
    run(&b, 7);
    assert_eq!(b.borrow().hot_switches()[0].1, "K401");
    assert!(sig(&b).rf_open[0]);
}

/// H2: R1 TX and R2 RX on A1. With RF, it reaches the R2 port.
#[test]
fn tx_into_another_radio() {
    let b = started();
    exp_write(&b, ADDR_U901, 2, bit(exp::R1_TX1) | bit(exp::A1_K1));
    exp_write(&b, 0x75, 2, bit(exp::R2_RX1));
    b.borrow_mut().set_env(|e| e.ptt_loop = true);
    run(&b, 13);
    assert!(b.borrow().hazards().contains(&Hazard::TxIntoRadio(Col::A1)));
    b.borrow_mut().set_env(|e| e.radio_rf[0] = true);
    run(&b, 1);
    assert!(sig(&b).rf_into_radio[1]);
}

/// D-104: RF on A2 opens READY, so the SAFE loop opens and the relays drop. Here
/// R1 transmits with K0 on RX (TX into the RX row, F2) while its RX row is on A2.
#[test]
fn rf_on_a2_opens_the_safe_loop() {
    let b = started();
    exp_write(&b, ADDR_U901, 2, bit(exp::R1_RX2) | bit(exp::A2_K1));
    run(&b, 13);
    b.borrow_mut().set_env(|e| e.radio_rf[0] = true);
    run(&b, 1);
    let s = sig(&b);
    assert!(s.rf_column[1] && !s.rf_a2_n && !s.ready && s.kill && !s.rly_en);
    run(&b, 13);
    assert!(all_relays_rest(&b));
    assert!(!sig(&b).rf_column[1]);
    assert!(sig(&b).ready, "READY returns once RF is gone");

    // Coupled RF on A2 (A-20) acts the same, without any path.
    let b = started();
    b.borrow_mut().set_env(|e| e.rf_coupled[1] = true);
    assert!(!sig(&b).ready && !sig(&b).rly_en);
}

/// EXP_INT goes low when a detector input changes and high when its port is read.
#[test]
fn exp_int_on_detector_change() {
    let b = started();
    for addr in EXPANDERS {
        exp_read(&b, addr);
    }
    assert!(sig(&b).exp_int_n);
    b.borrow_mut().set_env(|e| e.rf_coupled[0] = true);
    assert!(!sig(&b).exp_int_n);
    assert!(!b.borrow_mut().gpio_read(gpio::EXP_INT));
    assert_eq!(exp_read(&b, ADDR_U901) & bit(exp::A1_RFDET), 0, "low = RF");
    assert!(sig(&b).exp_int_n);
}

/// The trace carries the relay contacts by reference and the expander pins by net name.
#[test]
fn trace_names() {
    let b = started();
    exp_write(&b, ADDR_U901, 2, bit(exp::A1_K1));
    run(&b, 13);
    let bb = b.borrow();
    assert_eq!(bb.trace.signal("A1_K1_DRV").last().map(|x| x.1), Some(true));
    assert_eq!(bb.trace.signal("K401").last().map(|x| x.1), Some(true));
    assert_eq!(bb.trace.signal("RLY_EN").last().map(|x| x.1), Some(true));
}

/// Section 4, the second path: with the expander RESET pins open, the outputs stay
/// high after RLY_EN drops, and +12V_SW off still releases every switched coil.
#[test]
fn switched_supply_alone_releases_the_coils() {
    let b = started();
    for x in &mut b.borrow_mut().exp {
        x.reset_open = true;
    }
    exp_write(&b, ADDR_U901, 2, bit(exp::R1_RX1) | bit(exp::A1_K1));
    run(&b, 13);
    b.borrow_mut().set_env(|e| e.shack_loop = false);
    assert!(!sig(&b).sw12);
    assert!(b.borrow().exp_pin(exp::A1_K1), "expander output still high");
    run(&b, 12);
    assert!(all_relays_rest(&b));
}

/// Section 8, step 3: K1 must be settled before a TX row closes. K1 and the TX row
/// in one write give H4 while K1 still bounces.
#[test]
fn k1_and_tx_row_together_is_h4_during_the_bounce() {
    let b = started();
    exp_write(&b, ADDR_U901, 2, bit(exp::R1_TX1) | bit(exp::A1_K1));
    run(&b, 9);
    assert_eq!(b.borrow().k1(Col::A1), Contact::NoBounce);
    assert_eq!(b.borrow().hazards(), [Hazard::TxOpenLine(Col::A1)]);
    run(&b, 4);
    assert!(b.borrow().hazards().is_empty());
}

/// A row relay that opens under RF is a hot switch (rule 7: switch only with
/// TX_ANY = 0).
#[test]
fn row_relay_opening_under_rf_is_a_hot_switch() {
    let b = started();
    exp_write(&b, ADDR_U901, 2, bit(exp::R1_TX1) | bit(exp::A1_K1));
    b.borrow_mut().set_env(|e| e.ptt_loop = true);
    run(&b, 13);
    b.borrow_mut().set_env(|e| e.radio_rf[0] = true);
    let t0 = b.borrow().now();
    exp_write(&b, ADDR_U901, 2, bit(exp::A1_K1));
    run(&b, 7);
    assert_eq!(
        b.borrow().hot_switches(),
        [(t0 + ms(6), "K102")],
        "release time"
    );
}
