//! System scenarios (firmware/PLAN.md section 6): both firmwares on both board
//! models, joined by the cable, with faults injected from outside.
//!
//! Every test ends with the cross-end checks: no K0 rule break (D-63), no relay
//! hazard (H1 to H4), no hot switch outside an emergency stop (F12), no F3
//! contention.

use box_core::board::{ADDR_U901, ADDR_U903};
use box_core::relay_box::{Phase, RELAY_WAIT};
use link_proto::{Col, ColMask, FaultCode, Ms, Radio, Route};
use shack_core::shack::{Event, TxState};
use sim_core::TraceKind;
use sim_core::hal::Board;
use sim_models::rt1::Contact;
use sim_system::SystemSim;

/// F14 (system-verification.md): TX end no earlier than 100 ms after the inhibit.
/// The rule's own number, not the firmware constant, so a wrong constant fails.
const F14_WAIT: Ms = 100;

fn started() -> SystemSim {
    let mut s = SystemSim::new();
    s.start();
    s
}

fn route(tx: Col, rx: Col) -> Route {
    Route { tx, rx }
}

/// Route a radio from the host and wait until the box reports it.
fn routed(s: &mut SystemSim, r: Radio, tx: Col, rx: Col) {
    let line = format!("route R{} {} {}", r as u8, name(tx), name(rx));
    assert_eq!(s.host(&line), "ok", "{line}");
    let want = route(tx, rx);
    s.run_until(500, |s| {
        s.shack
            .shack
            .box_status()
            .is_some_and(|st| st.routes[r.index()] == want && !st.flags.switching)
    })
    .unwrap_or_else(|| panic!("{line} read back"));
}

fn name(c: Col) -> &'static str {
    ["-", "A1", "A2", "A3", "A4", "EXP"][c as usize]
}

/// R2 or R3 on air: routed to `col`, handshake done, the radio transmits and its RF
/// is on the column.
fn on_air(s: &mut SystemSim, r: Radio, col: Col) {
    routed(s, r, col, col);
    assert_eq!(s.host(&format!("tx R{} on", r as u8)), "ok");
    s.shack
        .board
        .borrow_mut()
        .set_env(|e| e.radio_tx[r.index()] = true);
    let c = col as usize - 1;
    s.run_until(500, |s| s.boxs.board.borrow().signals().rf_column[c])
        .unwrap_or_else(|| panic!("{r:?} RF on {col:?}"));
}

/// Last time trace signal `name` of a board changed to `value`.
fn last(trace: &sim_core::Trace, name: &str, value: bool) -> Ms {
    trace
        .signal(name)
        .into_iter()
        .rev()
        .find(|&(_, v)| v == value)
        .map(|(t, _)| t.as_ms())
        .unwrap_or_else(|| panic!("{name} never {value}"))
}

fn shack_last(s: &SystemSim, name: &str, value: bool) -> Ms {
    last(&s.shack.board.borrow().trace, name, value)
}

fn box_last(s: &SystemSim, name: &str, value: bool) -> Ms {
    last(&s.boxs.board.borrow().trace, name, value)
}

/// The cross-end checks. Hot switches are allowed only from `stop` for `window` ms
/// (an emergency stop under RF, finding F12).
fn checks(s: &SystemSim, stop: Option<(Ms, Ms)>) {
    assert!(s.violations.is_empty(), "{:?}", s.violations);
    assert!(s.boxs.hazards.is_empty(), "hazards {:?}", s.boxs.hazards);
    let b = s.boxs.board.borrow();
    for &(t, k) in b.hot_switches() {
        let t = t.as_ms();
        let ok = stop.is_some_and(|(t0, w)| t >= t0 && t <= t0 + w);
        assert!(ok, "hot switch {k} at {t} ms outside a stop");
    }
    assert!(!b.signals().contention, "F3 contention");
}

/// F10 over the box trace: no write opens and closes; a close comes at least
/// 12 ms after the last open.
fn check_f10(s: &SystemSim) {
    let b = s.boxs.board.borrow();
    let mut last = [0xFFFFu16; 3];
    let mut last_open: Option<Ms> = None;
    for e in b.trace.events() {
        let TraceKind::I2cWrite { addr, data } = &e.kind else {
            continue;
        };
        if !(ADDR_U901..=ADDR_U903).contains(addr) || data.len() != 3 || data[0] != 2 {
            continue;
        }
        let (t, i) = (e.t.as_ms(), usize::from(addr - ADDR_U901));
        let w = u16::from_le_bytes([data[1], data[2]]);
        let (opens, closes) = (last[i] & !w != 0, w & !last[i] != 0);
        assert!(!(opens && closes), "{t} ms: {addr:#x} opens and closes");
        if closes && let Some(o) = last_open {
            assert!(
                t >= o + RELAY_WAIT,
                "{t} ms: close {} ms after an open",
                t - o
            );
        }
        if opens {
            last_open = Some(t);
        }
        last[i] = w;
    }
}

fn longest_gap(trace: &sim_core::Trace, name: &str, from: Ms) -> Ms {
    let t: Vec<Ms> = trace
        .signal(name)
        .iter()
        .map(|e| e.0.as_ms())
        .filter(|&t| t >= from)
        .collect();
    t.windows(2).map(|w| w[1] - w[0]).max().unwrap_or(Ms::MAX)
}

fn tx_en(s: &SystemSim) -> bool {
    s.shack.board.borrow().signals().tx_en
}

// ------------------------------------------------------------------ normal use

#[test]
fn start_up_and_idle() {
    let mut s = started();
    let t0 = s.now();
    s.run(3000);
    assert!(tx_en(&s) && s.shack.shack.link_up());
    let st = *s.shack.shack.box_status().unwrap();
    assert!(st.flags.ready && !st.flags.kill);
    assert_eq!(st.fault, FaultCode::NONE);
    assert!(longest_gap(&s.shack.board.borrow().trace, "WDI", t0) <= 250);
    assert!(longest_gap(&s.boxs.board.borrow().trace, "WDI", t0) <= 250);
    assert!(s.boxs.board.borrow().signals().reset_n);
    checks(&s, None);
}

#[test]
fn route_changes_read_back() {
    let mut s = started();
    let from = s.shack.host_lines.len();
    routed(&mut s, Radio::R1, Col::A1, Col::A1);
    assert!(s.shack.host_seen(from, "!route R1 A1 A1").is_some());
    routed(&mut s, Radio::R2, Col::None, Col::A2);
    routed(&mut s, Radio::R3, Col::A4, Col::A2);
    routed(&mut s, Radio::R1, Col::A3, Col::A1);
    let st = *s.shack.shack.box_status().unwrap();
    assert_eq!(st.k1.bits(), 0b1111);
    check_f10(&s);
    checks(&s, None);
}

#[test]
fn r1_ptt_through_the_loop() {
    let mut s = started();
    routed(&mut s, Radio::R1, Col::A1, Col::A1);
    s.run_until(200, |s| !s.shack.board.borrow().signals().inhibit[0])
        .expect("R1 released (C-1)");
    s.shack.board.borrow_mut().set_env(|e| e.radio_tx[0] = true);
    s.run(40);
    {
        let b = s.boxs.board.borrow();
        assert_eq!(b.k0(Radio::R1), Contact::No);
        assert!(b.signals().tx_any && b.signals().rf_antenna[0]);
        assert!(!b.signals().rf_open[0]);
    }
    s.run_until(100, |s| s.shack.shack.box_status().unwrap().flags.tx_any)
        .expect("box reports TX_ANY");
    s.shack
        .board
        .borrow_mut()
        .set_env(|e| e.radio_tx[0] = false);
    s.run(40);
    assert_eq!(s.boxs.board.borrow().k0(Radio::R1), Contact::Nc);
    checks(&s, None);
}

#[test]
fn r2_and_r3_handshake_and_f14() {
    let mut s = started();
    on_air(&mut s, Radio::R2, Col::A3);
    on_air(&mut s, Radio::R3, Col::A4);
    for (r, n) in [(Radio::R2, 2), (Radio::R3, 3)] {
        assert_eq!(s.host(&format!("tx R{n} off")), "ok");
        s.run_until(1000, |s| s.shack.shack.tx_state(r) == TxState::Idle)
            .expect("TX ended");
        let inh = shack_last(&s, &format!("INH_R{n}"), true);
        let quiet = shack_last(&s, &format!("TX_R{n}"), false);
        let k0_off = box_last(&s, &format!("R{n}_K0_DRV"), false);
        assert!(
            k0_off >= inh + F14_WAIT && k0_off >= quiet,
            "R{n}: K0 off at {k0_off}, inhibit {inh}, TX sense off {quiet}"
        );
        s.shack
            .board
            .borrow_mut()
            .set_env(|e| e.radio_tx[r.index()] = false);
    }
    s.run(50);
    checks(&s, None);
}

#[test]
fn route_changes_refused_while_transmitting_f13() {
    let mut s = started();
    on_air(&mut s, Radio::R2, Col::A3);
    assert!(s.host("route R2 A4 A4").starts_with("err txbusy"));
    // R3 onto R2's TX column: the shack sends it, the box refuses it (H1).
    let from = s.shack.host_lines.len();
    assert_eq!(s.host("route R3 A3 A3"), "ok");
    s.run_until(300, |s| s.shack.host_seen(from, "!refused").is_some())
        .expect("box refuses");
    assert_eq!(
        s.shack.shack.box_status().unwrap().routes[2],
        Route::default()
    );
    checks(&s, None);
}

#[test]
fn bias_t_on_the_rx_loop() {
    let mut s = started();
    routed(&mut s, Radio::R1, Col::A1, Col::A2);
    assert_eq!(s.host("bias A2"), "ok");
    s.run(200);
    let st = *s.shack.shack.box_status().unwrap();
    assert_eq!(st.bias_en, ColMask::EMPTY.with(Col::A2));
    assert_eq!(st.bias_ok, st.bias_en);
    assert!(s.boxs.board.borrow().signals().bias_out[1]);
    assert_eq!(s.shack.shack.config().bias, st.bias_en, "stored");
    // After a KILL the box comes back with the feed off; the shack sends it again.
    s.shack
        .board
        .borrow_mut()
        .set_env(|e| e.kill_pressed = true);
    s.run(50);
    s.shack
        .board
        .borrow_mut()
        .set_env(|e| e.kill_pressed = false);
    s.run_until(1000, |s| {
        s.shack
            .shack
            .box_status()
            .is_some_and(|x| x.flags.ready && x.bias_en == st.bias_en)
    })
    .expect("bias restored");
    checks(&s, None);
}

// ------------------------------------------------------------------ stops

#[test]
fn kill_during_tx_and_recovery() {
    let mut s = started();
    on_air(&mut s, Radio::R2, Col::A3);
    let t = s.now();
    s.shack
        .board
        .borrow_mut()
        .set_env(|e| e.kill_pressed = true);
    s.run(50);
    {
        let (sh, bx) = (s.shack.board.borrow(), s.boxs.board.borrow());
        assert!(sh.signals().latched && !sh.signals().tx_en);
        assert!(!sh.signals().radio_tx_active[1], "R2 stopped by TX INH");
        assert!(!bx.signals().rly_en && bx.k0(Radio::R2) == Contact::Nc);
    }
    assert!(box_last(&s, "RLY_EN", false) <= t + 1, "RLY_EN low at once");
    s.shack.board.borrow_mut().set_env(|e| {
        e.kill_pressed = false;
        e.radio_tx[1] = false;
    });
    // The box sets up again; the shack sends the stored route again.
    s.run_until(1000, |s| {
        s.shack
            .shack
            .box_status()
            .is_some_and(|st| st.flags.ready && st.routes[1] == route(Col::A3, Col::A3))
    })
    .expect("route restored");
    assert!(!tx_en(&s), "TX stays blocked until RESET");
    s.press_reset();
    s.run(20);
    assert!(tx_en(&s));
    check_f10(&s);
    checks(&s, Some((t, 25)));
}

#[test]
fn rf_on_a2_opens_safe() {
    let mut s = started();
    routed(&mut s, Radio::R1, Col::A1, Col::A2);
    let t = s.now();
    s.boxs
        .board
        .borrow_mut()
        .set_env(|e| e.rf_coupled[1] = true);
    s.run(10);
    assert!(s.shack.board.borrow().signals().latched);
    assert!(s.shack.board.borrow().signals().inhibit[0], "R1 inhibited");
    assert!(!s.boxs.board.borrow().signals().rly_en);
    s.boxs
        .board
        .borrow_mut()
        .set_env(|e| e.rf_coupled[1] = false);
    s.run_until(1000, |s| s.boxs.fw.phase() == Phase::Run)
        .expect("box runs again");
    checks(&s, Some((t, 10)));
}

#[test]
fn cable_cut_during_tx_and_back() {
    let mut s = started();
    on_air(&mut s, Radio::R2, Col::A3);
    let t = s.now();
    s.cable(false);
    s.run(600);
    assert!(!s.shack.shack.link_up() && s.shack.board.borrow().signals().latched);
    assert!(!s.shack.board.borrow().signals().radio_tx_active[1]);
    assert_ne!(s.boxs.fw.phase(), Phase::Run);
    s.shack
        .board
        .borrow_mut()
        .set_env(|e| e.radio_tx[1] = false);
    s.cable(true);
    s.run_until(2000, |s| {
        s.shack.shack.tx_state(Radio::R2) == TxState::Idle
            && s.shack
                .shack
                .box_status()
                .is_some_and(|st| st.flags.ready && st.routes[1] == route(Col::A3, Col::A3))
    })
    .expect("link, box and route back; TX ended");
    s.press_reset();
    s.run(20);
    assert!(tx_en(&s));
    checks(&s, Some((t, 25)));
}

#[test]
fn bit_errors_are_survived() {
    let mut s = started();
    for line in 0..2 {
        let mut n = 0u32;
        let flip: Box<dyn FnMut(u8) -> Option<u8>> = Box::new(move |b| {
            n += 1;
            Some(if n.is_multiple_of(37) { b ^ 0x10 } else { b })
        });
        let mut sb = s.shack.board.borrow_mut();
        if line == 0 {
            sb.to_box_line().set_filter(Some(flip));
        } else {
            sb.from_box_line().set_filter(Some(flip));
        }
    }
    routed(&mut s, Radio::R1, Col::A1, Col::A1);
    on_air(&mut s, Radio::R2, Col::A3);
    assert_eq!(s.host("tx R2 off"), "ok");
    s.shack
        .board
        .borrow_mut()
        .set_env(|e| e.radio_tx[1] = false);
    s.run_until(2000, |s| s.shack.shack.tx_state(Radio::R2) == TxState::Idle)
        .expect("TX ended");
    s.run(3000);
    assert!(
        s.shack.shack.link_up(),
        "no link loss from single bit errors"
    );
    assert!(s.shack.has_event(Event::LinkLost).is_none());
    checks(&s, None);
}

#[test]
fn answers_lost_on_pair_4() {
    let mut s = started();
    on_air(&mut s, Radio::R2, Col::A3);
    s.shack
        .board
        .borrow_mut()
        .from_box_line()
        .set_filter(Some(Box::new(|_| None)));
    s.run_until(500, |s| !s.shack.shack.link_up())
        .expect("shack: link lost");
    s.run(200);
    assert!(s.shack.board.borrow().signals().inhibit[1], "R2 inhibited");
    s.shack
        .board
        .borrow_mut()
        .set_env(|e| e.radio_tx[1] = false);
    s.shack.board.borrow_mut().from_box_line().set_filter(None);
    s.run_until(2000, |s| {
        s.shack.shack.link_up() && s.shack.shack.tx_state(Radio::R2) == TxState::Idle
    })
    .expect("link back, TX ended");
    assert_eq!(s.boxs.board.borrow().k0(Radio::R2), Contact::Nc);
    checks(&s, None);
}

#[test]
fn shack_mcu_hang_during_tx() {
    let mut s = started();
    on_air(&mut s, Radio::R2, Col::A3);
    s.shack.mcu_running = false;
    let t = s
        .run_until(500, |s| s.boxs.fw.phase() == Phase::Stopped)
        .expect("box stops on the link time-out (F13)");
    s.run(30);
    {
        let sh = s.shack.board.borrow();
        assert!(sh.signals().latched && !sh.signals().radio_tx_active[1]);
    }
    assert_eq!(s.boxs.fw.fault(), FaultCode::LINK_TIMEOUT_PERMIT);
    s.run(3000);
    assert!(s.shack.board.borrow().signals().fault, "shack watchdog");
    checks(&s, Some((t, 25)));
}

#[test]
fn box_mcu_hang() {
    let mut s = started();
    on_air(&mut s, Radio::R2, Col::A3);
    s.boxs.mcu_running = false;
    let t = s
        .run_until(3000, |s| s.boxs.board.borrow().signals().fault)
        .expect("box watchdog");
    s.run(30);
    let sh = s.shack.board.borrow();
    assert!(sh.signals().latched && !sh.signals().radio_tx_active[1]);
    assert!(!s.boxs.board.borrow().signals().rly_en);
    drop(sh);
    checks(&s, Some((t - 1, 25)));
}

#[test]
fn box_brown_out() {
    let mut s = started();
    routed(&mut s, Radio::R2, Col::A3, Col::A3);
    s.boxs.board.borrow_mut().set_env(|e| e.power = false);
    s.run(50);
    s.boxs.board.borrow_mut().set_env(|e| e.power = true);
    // The outage is shorter than the link time-out: the new box answers the next
    // Poll, not READY yet.
    s.run_until(500, |s| {
        s.shack.shack.box_status().is_some_and(|st| !st.flags.ready)
    })
    .expect("box not ready after the restart");
    s.run_until(3000, |s| {
        s.shack
            .shack
            .box_status()
            .is_some_and(|st| st.flags.ready && st.routes[1] == route(Col::A3, Col::A3))
    })
    .expect("box restarts, route restored");
    assert!(s.shack.board.borrow().signals().latched);
    s.press_reset();
    s.run(20);
    assert!(tx_en(&s));
    checks(&s, None);
}

#[test]
fn shack_restart_during_tx() {
    let mut s = started();
    on_air(&mut s, Radio::R2, Col::A3);
    let t = s.now();
    s.shack.board.borrow_mut().set_env(|e| e.power = false);
    s.run(100);
    s.shack.board.borrow_mut().set_env(|e| {
        e.power = true;
        e.radio_tx[1] = false;
    });
    s.run_until(3000, |s| {
        s.shack.shack.link_up() && s.boxs.fw.phase() == Phase::Run
    })
    .expect("both up again");
    s.run(300);
    assert_eq!(s.boxs.board.borrow().k0(Radio::R2), Contact::Nc);
    checks(&s, Some((t, 25)));
}

#[test]
fn box_expander_nack_and_restore() {
    let mut s = started();
    routed(&mut s, Radio::R2, Col::A3, Col::A3);
    s.boxs.board.borrow_mut().exp[1].force_nack = true;
    s.run(40);
    assert_eq!(s.boxs.fw.fault(), FaultCode::EXPANDER_NACK);
    s.boxs.board.borrow_mut().exp[1].force_nack = false;
    s.run_until(1000, |s| {
        s.shack
            .shack
            .box_status()
            .is_some_and(|st| st.flags.ready && st.routes[1] == route(Col::A3, Col::A3))
    })
    .expect("set up again, route restored");
    assert!(tx_en(&s), "an expander fault does not latch SAFE");
    checks(&s, None);
}

// ------------------------------------------------------------------ SAFE table

/// system-verification.md section 1: all 256 rows of the SAFE loop across both
/// boards and the cable, firmware off, inputs driven directly.
#[test]
fn safe_loop_table_256_rows() {
    use box_core::board::gpio;
    use embedded_hal::i2c::Operation;
    use shack_core::board::{EXPANDER_ADDR, exp};

    for row in 0u8..=255 {
        let bit = |n: u8| row & (1 << n) != 0;
        let (kill_closed, sw_stop, cable, shack_pwr) = (bit(0), bit(1), bit(2), bit(3));
        let (box_pwr, mcu_en_n, fault, rf_a2) = (bit(4), bit(5), bit(6), bit(7));

        let mut s = SystemSim::new();
        s.shack.mcu_running = false;
        s.boxs.mcu_running = false;
        s.run(300);
        {
            let mut b = s.boxs.board.borrow_mut();
            b.gpio_write(gpio::MCU_EN_N, mcu_en_n);
            if !fault {
                b.gpio_write(gpio::LATCH_CLR, true);
                b.gpio_write(gpio::LATCH_CLR, false);
            }
            b.set_env(|e| {
                e.rf_coupled[1] = rf_a2;
                e.power = box_pwr;
            });
        }
        {
            let mut b = s.shack.board.borrow_mut();
            if sw_stop {
                // SW_STOP_N as an output driving low (F1 order: outputs first).
                let cfg = !(1u16 << exp::SW_STOP_N.bit);
                let [lo, hi] = cfg.to_le_bytes();
                let _ = b.i2c(EXPANDER_ADDR, &mut [Operation::Write(&[2, 0, 0])]);
                let _ = b.i2c(EXPANDER_ADDR, &mut [Operation::Write(&[6, lo, hi])]);
            }
            b.set_env(|e| {
                e.kill_pressed = !kill_closed;
                e.power = shack_pwr;
            });
        }
        s.cable(cable);
        s.run(5);

        let all_good = kill_closed
            && !sw_stop
            && cable
            && shack_pwr
            && box_pwr
            && !mcu_en_n
            && !fault
            && !rf_a2;
        let (sh, bx) = (
            s.shack.board.borrow().signals(),
            s.boxs.board.borrow().signals(),
        );
        let ready = box_pwr && !mcu_en_n && !fault && !rf_a2;
        let msg = format!("row {row:08b}");
        assert_eq!(bx.ready, ready, "READY, {msg}");
        assert_eq!(sh.safe_current, all_good, "shack loop current, {msg}");
        assert_eq!(bx.safe_current, all_good, "box loop current, {msg}");
        assert_eq!(bx.kill, !all_good, "box KILL, {msg}");
        assert_eq!(bx.rly_en, all_good, "RLY_EN, {msg}");
    }
}
