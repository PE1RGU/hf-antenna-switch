//! Box firmware scenarios: box-core on the box board model, driven by the scripted
//! shack. Each test names the rule it checks (logic-verification.md,
//! system-verification.md, link-protocol.md).

use box_core::board::{ADDR_U901, ADDR_U903, ADDR_U1001, exp};
use box_core::relay_box::{HELLO_RELEASE, Phase, RELAY_WAIT};
use link_proto::{Col, ColMask, Command, FaultCode, Ms, Radio, ResultCode, Route, Status};
use sim_box::BoxSim;
use sim_box::shack_stub::ShackStub;
use sim_core::TraceKind;
use sim_core::hal::Board;
use sim_models::rt1::{Contact, Rt1Timing};
use sim_models::tps3823::Corner;

fn route(tx: Col, rx: Col) -> Route {
    Route { tx, rx }
}

fn set(s: &mut BoxSim, radio: Radio, tx: Col, rx: Col) -> ResultCode {
    let route = route(tx, rx);
    s.command(Command::SetRoute { radio, route }).result
}

/// Wait for the end of the switching sequence, plus one poll.
fn settle(s: &mut BoxSim) {
    s.run_until(500, |s| !s.fw.switching())
        .expect("switching sequence ends");
    s.run(20);
}

fn started() -> BoxSim {
    let mut s = BoxSim::new();
    s.start();
    s
}

/// A started box with R2 on A3 (TX and RX) and its permit out.
fn r2_permit() -> BoxSim {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R2, Col::A3, Col::A3), ResultCode::Ok);
    settle(&mut s);
    assert_eq!(
        s.command(Command::TxRequest(Radio::R2)).result,
        ResultCode::Ok
    );
    s.run_until(200, |s| s.shack.status().is_some_and(|st| st.permit_r2))
        .expect("permit");
    s
}

/// A Status from a new Poll: the answers between Polls can be 50 ms old.
fn fresh(s: &mut BoxSim) -> Status {
    s.command(Command::Poll)
}

/// Output register writes (register 2) to `addr`, as words.
fn out_writes(s: &BoxSim, addr: u8) -> Vec<(Ms, u16)> {
    s.board
        .borrow()
        .trace
        .i2c_writes(addr)
        .into_iter()
        .filter(|(_, d)| d.len() == 3 && d[0] == 2)
        .map(|(t, d)| (t.as_ms(), u16::from_le_bytes([d[1], d[2]])))
        .collect()
}

fn mcu_en_n(s: &BoxSim) -> bool {
    s.board.borrow().signals().mcu_en_n
}

/// Last time the trace signal `name` changed to `value`.
fn last_change(s: &BoxSim, name: &str, value: bool) -> Ms {
    s.board
        .borrow()
        .trace
        .signal(name)
        .into_iter()
        .rev()
        .find(|&(_, v)| v == value)
        .map(|(t, _)| t.as_ms())
        .unwrap_or_else(|| panic!("{name} never {value}"))
}

/// Output register writes to the relay expanders: time, address, word.
fn relay_writes(s: &BoxSim) -> Vec<(Ms, u8, u16)> {
    s.board
        .borrow()
        .trace
        .events()
        .iter()
        .filter_map(|e| match &e.kind {
            TraceKind::I2cWrite { addr, data }
                if (ADDR_U901..=ADDR_U903).contains(addr) && data.len() == 3 && data[0] == 2 =>
            {
                Some((e.t.as_ms(), *addr, u16::from_le_bytes([data[1], data[2]])))
            }
            _ => None,
        })
        .collect()
}

/// F10: no write opens and closes coils at once; a write that closes comes at
/// least 12 ms after the last write that opened.
fn check_f10(s: &BoxSim) {
    let mut last = [0xFFFFu16; 3];
    let mut last_open: Option<Ms> = None;
    for (t, addr, w) in relay_writes(s) {
        let i = usize::from(addr - ADDR_U901);
        let opens = last[i] & !w != 0;
        let closes = w & !last[i] != 0;
        assert!(
            !(opens && closes),
            "{t} ms: write {w:#06x} to {addr:#x} opens and closes"
        );
        if closes && let Some(o) = last_open {
            assert!(
                t >= o + RELAY_WAIT,
                "{t} ms: closes {} ms after an open",
                t - o
            );
        }
        if opens {
            last_open = Some(t);
        }
        last[i] = w;
    }
}

fn no_harm(s: &BoxSim) {
    assert!(s.hazards.is_empty(), "hazards: {:?}", s.hazards);
    let b = s.board.borrow();
    assert!(b.hot_switches().is_empty(), "hot: {:?}", b.hot_switches());
    assert!(!b.signals().contention, "F3 contention");
}

// ------------------------------------------------------------------ start-up

/// Times at which trace signal `name` changed to `value`, in order.
fn changes(s: &BoxSim, name: &str, value: bool) -> Vec<Ms> {
    s.board
        .borrow()
        .trace
        .signal(name)
        .into_iter()
        .filter(|&(t, v)| v == value && t.as_ms() > 0)
        .map(|(t, _)| t.as_ms())
        .collect()
}

#[test]
fn start_up_order_f11_f1() {
    let s = started();
    let reset_n_up = changes(&s, "RESET_N", true);
    let clr = changes(&s, "LATCH_CLR", true);
    let en = changes(&s, "MCU_EN_N_PIN", false)[0];
    let kill_off = changes(&s, "KILL", false)[0];
    assert!(
        clr[0] > reset_n_up[0],
        "LATCH_CLR edge at {} ms, RESET_N high at {} ms",
        clr[0],
        reset_n_up[0]
    );
    assert!(en >= clr[0], "MCU_EN_N low at {en} ms, after the clear");
    assert!(kill_off >= en, "KILL low at {kill_off} ms");
    // Two edges: one at start-up, one after the watchdog test (cause known, rule 2),
    // only once RESET_N is high again after the trip.
    assert_eq!(clr.len(), 2, "LATCH_CLR edges {clr:?}");
    assert_eq!(reset_n_up.len(), 2, "one supervisor trip in the self-test");
    assert!(
        clr[1] > reset_n_up[1],
        "second edge after RESET_N high again"
    );
    let b = s.board.borrow();
    let tr = &b.trace;
    for addr in ADDR_U901..=ADDR_U1001 {
        let w = tr.i2c_writes(addr);
        assert!(
            w[0].0.as_ms() >= kill_off,
            "{addr:#x} written before KILL low"
        );
        assert_eq!(w[0].1, vec![2, 0, 0], "{addr:#x}: outputs 0 first (F1)");
        assert_eq!(w[1].1[0], 6, "{addr:#x}: configuration second");
    }
    drop(b);
    let st = s.fw.status();
    assert!(st.flags.ready && !st.flags.kill);
    assert_eq!(st.fault, FaultCode::NONE);
    no_harm(&s);
}

#[test]
fn safe_loop_open_at_start_up_gives_fault_5() {
    let mut s = BoxSim::new();
    s.shack.kill_pressed = true;
    s.run(3000);
    assert!(matches!(s.fw.phase(), Phase::WaitSafe { .. }));
    assert_eq!(s.fw.fault(), FaultCode::SAFE_NOT_CLOSED);
    assert!(s.board.borrow().trace.i2c_writes(ADDR_U901).is_empty());
    assert_eq!(
        s.command(Command::SetRoute {
            radio: Radio::R1,
            route: route(Col::A1, Col::A1)
        })
        .result,
        ResultCode::NotReady
    );
    s.shack.kill_pressed = false;
    s.run_until(5000, |s| s.fw.phase() == Phase::Run)
        .expect("self-test, then runs when the loop closes");
}

// ------------------------------------------------------------------ switching

#[test]
fn route_change_follows_section_8() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    assert_eq!(set(&mut s, Radio::R1, Col::A4, Col::A4), ResultCode::Ok);
    settle(&mut s);
    let open = last_change(&s, "R1_TX1_DRV", false);
    let k1_on = last_change(&s, "A4_K1_DRV", true);
    let close = last_change(&s, "R1_TX4_DRV", true);
    let k1_off = last_change(&s, "A1_K1_DRV", false);
    assert!(
        k1_on >= open + RELAY_WAIT,
        "K1 on at {k1_on}, rows open at {open}"
    );
    assert!(
        close >= k1_on + RELAY_WAIT,
        "rows close at {close}, K1 on at {k1_on}"
    );
    assert!(
        k1_off >= close + RELAY_WAIT,
        "K1 off at {k1_off}, rows close at {close}"
    );
    assert_eq!(
        last_change(&s, "R1_RX1_DRV", false),
        open,
        "one write opens both rows"
    );
    let st = fresh(&mut s);
    assert_eq!(st.routes[0], route(Col::A4, Col::A4), "read back");
    assert_eq!(st.k1, ColMask::EMPTY.with(Col::A4));
    assert!(!st.flags.switching);
    check_f10(&s);
    no_harm(&s);
}

#[test]
fn hazards_are_refused_f6() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    // H2: another radio's row on R1's TX column.
    assert_eq!(
        set(&mut s, Radio::R2, Col::None, Col::A1),
        ResultCode::Hazard
    );
    // H1: a second TX row on A1.
    assert_eq!(
        set(&mut s, Radio::R3, Col::A1, Col::None),
        ResultCode::Hazard
    );
    // H3: TX on the receive-only column.
    assert_eq!(set(&mut s, Radio::R2, Col::A2, Col::A3), ResultCode::Hazard);
    // A shared receive antenna is allowed.
    assert_eq!(set(&mut s, Radio::R2, Col::None, Col::A2), ResultCode::Ok);
    settle(&mut s);
    assert_eq!(set(&mut s, Radio::R3, Col::A3, Col::A2), ResultCode::Ok);
    settle(&mut s);
    let st = fresh(&mut s);
    assert_eq!(
        st.routes,
        [
            route(Col::A1, Col::A1),
            route(Col::None, Col::A2),
            route(Col::A3, Col::A2)
        ]
    );
    check_f10(&s);
    no_harm(&s);
}

#[test]
fn second_route_during_switching_is_busy() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    // A move of R1 takes four steps (48 ms); the next command comes about 30 ms later.
    let a = Command::SetRoute {
        radio: Radio::R1,
        route: route(Col::A4, Col::A4),
    };
    let b = Command::SetRoute {
        radio: Radio::R2,
        route: route(Col::A3, Col::A3),
    };
    s.shack.queue.extend([a, b]);
    let from = s.shack.replies.len();
    let answers = |s: &BoxSim| -> Vec<ResultCode> {
        s.shack.replies[from..]
            .iter()
            .filter(|r| r.1 != Command::Poll)
            .map(|r| r.2.result)
            .collect()
    };
    s.run_until(200, |s| answers(s).len() == 2)
        .expect("both answered");
    let results = answers(&s);
    assert_eq!(results, [ResultCode::Ok, ResultCode::Busy]);
}

#[test]
fn tx_any_refuses_and_pauses_the_sequence() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    // R1 keys: K0 goes to TX in hardware, RF on A1.
    s.board.borrow_mut().set_env(|e| e.ptt_loop = true);
    s.run(15);
    s.board.borrow_mut().set_env(|e| e.radio_rf[0] = true);
    s.run(15);
    assert_eq!(
        set(&mut s, Radio::R2, Col::A3, Col::A3),
        ResultCode::TxActive
    );
    assert_eq!(
        s.command(Command::TxRequest(Radio::R2)).result,
        ResultCode::TxActive
    );
    s.board.borrow_mut().set_env(|e| {
        e.radio_rf[0] = false;
        e.ptt_loop = false;
    });
    s.run(30);

    // R1 keys again while R2 switches: the sequence waits for TX_ANY = 0.
    assert_eq!(set(&mut s, Radio::R2, Col::A3, Col::A3), ResultCode::Ok);
    s.board.borrow_mut().set_env(|e| e.ptt_loop = true);
    let n = relay_writes(&s).len();
    s.run(300);
    assert!(s.fw.switching(), "paused");
    assert_eq!(relay_writes(&s).len(), n, "no write while TX_ANY = 1");
    s.board.borrow_mut().set_env(|e| e.ptt_loop = false);
    s.run(20);
    settle(&mut s);
    assert_eq!(fresh(&mut s).routes[1], route(Col::A3, Col::A3));
    check_f10(&s);
    no_harm(&s);
}

#[test]
fn fast_relays_keep_the_rules() {
    let mut s = BoxSim::with_relays(Rt1Timing::FAST);
    s.start();
    for (tx, rx) in [
        (Col::A1, Col::A2),
        (Col::A4, Col::A1),
        (Col::A3, Col::Exp),
        (Col::None, Col::None),
    ] {
        assert_eq!(set(&mut s, Radio::R1, tx, rx), ResultCode::Ok);
        settle(&mut s);
        assert_eq!(fresh(&mut s).routes[0], route(tx, rx));
    }
    check_f10(&s);
    no_harm(&s);
}

// ------------------------------------------------------------------ handshake

#[test]
fn tx_handshake_r2() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R2, Col::A3, Col::A3), ResultCode::Ok);
    settle(&mut s);
    let from = s.shack.replies.len();
    s.shack.queue.push_back(Command::TxRequest(Radio::R2));
    let k0_on = s
        .run_until(200, |s| s.board.borrow().exp_pin(exp::R2_K0))
        .expect("K0 written");
    let t = s
        .run_until(200, |s| s.fw.status().permit_r2)
        .expect("permit");
    assert!(
        t >= k0_on + RELAY_WAIT,
        "permit at {t}, K0 written at {k0_on}"
    );
    assert_eq!(
        s.board.borrow().k0(Radio::R2),
        Contact::No,
        "K0 settled at the permit"
    );
    let answered = |s: &BoxSim| s.shack.replies[from..].iter().any(|r| r.1 != Command::Poll);
    s.run_until(100, answered).expect("answered");
    let first = s.shack.replies[from..]
        .iter()
        .find(|r| r.1 == Command::TxRequest(Radio::R2))
        .expect("answered")
        .2;
    assert_eq!(first.result, ResultCode::Ok);
    assert!(!first.permit_r2, "no permit in the first answer");

    // F13: no route change with the permit out. A repeated request is Ok.
    assert_eq!(
        set(&mut s, Radio::R2, Col::A4, Col::A4),
        ResultCode::PermitOut
    );
    assert_eq!(
        s.command(Command::TxRequest(Radio::R2)).result,
        ResultCode::Ok
    );

    let st = s.command(Command::TxEnd(Radio::R2));
    assert_eq!(st.result, ResultCode::Ok);
    assert!(!st.permit_r2);
    s.run(20);
    assert_eq!(s.board.borrow().k0(Radio::R2), Contact::Nc);
    assert_eq!(set(&mut s, Radio::R2, Col::A4, Col::A4), ResultCode::Ok);
    settle(&mut s);
    check_f10(&s);
    no_harm(&s);
}

#[test]
fn tx_request_refusals() {
    let mut s = BoxSim::new();
    s.run_until(400, |s| s.shack.link_up())
        .expect("link up during boot");
    assert_eq!(
        s.command(Command::TxRequest(Radio::R2)).result,
        ResultCode::NotReady
    );
    s.start();
    assert_eq!(
        s.command(Command::TxRequest(Radio::R1)).result,
        ResultCode::BadArg
    );
    assert_eq!(
        s.command(Command::TxEnd(Radio::R1)).result,
        ResultCode::BadArg
    );
    assert_eq!(
        s.command(Command::TxRequest(Radio::R3)).result,
        ResultCode::NoTxRoute
    );
    assert_eq!(set(&mut s, Radio::R3, Col::None, Col::A4), ResultCode::Ok);
    settle(&mut s);
    assert_eq!(
        s.command(Command::TxRequest(Radio::R3)).result,
        ResultCode::NoTxRoute
    );
}

#[test]
fn repeated_seq_is_not_run_again() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R2, Col::A3, Col::A3), ResultCode::Ok);
    settle(&mut s);
    s.shack.mute = true;
    s.run(100);
    ShackStub::send_raw(&mut s.board.borrow_mut(), 200, Command::TxEnd(Radio::R2));
    s.run(30);
    // Same seq, other command: the box answers the stored result and runs nothing.
    ShackStub::send_raw(
        &mut s.board.borrow_mut(),
        200,
        Command::TxRequest(Radio::R2),
    );
    s.run(50);
    assert!(
        s.board
            .borrow()
            .trace
            .signal("R2_K0_DRV")
            .iter()
            .all(|e| !e.1)
    );
    ShackStub::send_raw(
        &mut s.board.borrow_mut(),
        201,
        Command::TxRequest(Radio::R2),
    );
    s.run(50);
    assert!(s.fw.status().permit_r2);
}

// ------------------------------------------------------------------ stops

#[test]
fn kill_releases_and_the_box_sets_up_again_f5() {
    let mut s = r2_permit();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    let writes = s.board.borrow().trace.i2c_writes(ADDR_U901).len();
    s.shack.kill_pressed = true;
    s.run(20);
    {
        let b = s.board.borrow();
        assert!(b.signals().kill && !b.signals().rly_en);
        assert_eq!(b.row(Radio::R1, true, Col::A1), Contact::Nc);
        assert_eq!(b.k0(Radio::R2), Contact::Nc, "U903 reset drops K0");
    }
    assert!(matches!(s.fw.phase(), Phase::WaitSafe { .. }));
    assert!(!mcu_en_n(&s), "MCU_EN_N stays low on KILL (F5)");
    let st = s.command(Command::Poll);
    assert!(st.flags.kill && !st.flags.ready && !st.permit_r2);
    s.shack.kill_pressed = false;
    s.run(10);
    s.shack.press_reset();
    s.run_until(100, |s| s.fw.phase() == Phase::Run)
        .expect("set up again");
    let b = s.board.borrow();
    let w = b.trace.i2c_writes(ADDR_U901);
    assert_eq!(w[writes].1, vec![2, 0, 0], "F1 order again");
    assert_eq!(w[writes + 1].1[0], 6);
    drop(b);
    s.run(20);
    assert_eq!(
        fresh(&mut s).routes,
        [Route::default(); 3],
        "relays come back off"
    );
    no_harm(&s);
}

#[test]
fn rf_on_a2_opens_safe() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A2), ResultCode::Ok);
    settle(&mut s);
    s.board.borrow_mut().set_env(|e| e.rf_coupled[1] = true);
    s.run(5);
    assert!(s.board.borrow().signals().kill);
    assert!(matches!(s.fw.phase(), Phase::WaitSafe { .. }));
    s.board.borrow_mut().set_env(|e| e.rf_coupled[1] = false);
    s.run(10);
    s.shack.press_reset();
    s.run_until(100, |s| s.fw.phase() == Phase::Run)
        .expect("runs again");
}

#[test]
fn link_loss_with_permit_opens_safe_f13() {
    let mut s = r2_permit();
    let k0_writes = out_writes(&s, ADDR_U903).len();
    s.shack.mute = true;
    let t = s
        .run_until(400, |s| s.fw.phase() == Phase::Stopped)
        .expect("stop");
    assert!(mcu_en_n(&s), "SAFE opened");
    assert_eq!(s.fw.fault(), FaultCode::LINK_TIMEOUT_PERMIT);
    s.run(20);
    assert!(s.board.borrow().signals().kill && s.shack.latched);
    assert_eq!(
        out_writes(&s, ADDR_U903).len(),
        k0_writes,
        "no K0 write after the loss (stop at {t} ms)"
    );
    // The shack is back: its link timed out too, so it sends Hello. That ends the stop.
    s.shack.mute = false;
    s.run_until(400, |s| matches!(s.fw.phase(), Phase::WaitSafe { .. }))
        .expect("Hello ends the stop");
    assert!(!mcu_en_n(&s));
    s.run(10);
    s.shack.press_reset();
    s.run_until(100, |s| s.fw.phase() == Phase::Run)
        .expect("runs again");
    no_harm(&s);
}

#[test]
fn link_lost_stop_ends_on_tx_end() {
    let mut s = r2_permit();
    s.shack.mute = true;
    s.run_until(400, |s| s.fw.phase() == Phase::Stopped)
        .expect("stop");
    ShackStub::send_raw(&mut s.board.borrow_mut(), 100, Command::Poll);
    s.run(30);
    let st = s.fw.status();
    assert!(st.flags.link_lost_stop && !st.flags.ready && !st.permit_r2);
    ShackStub::send_raw(
        &mut s.board.borrow_mut(),
        101,
        Command::SetRoute {
            radio: Radio::R1,
            route: route(Col::A1, Col::A1),
        },
    );
    s.run(30);
    assert_eq!(
        s.fw.phase(),
        Phase::Stopped,
        "a route does not end the stop"
    );
    ShackStub::send_raw(&mut s.board.borrow_mut(), 102, Command::TxEnd(Radio::R2));
    s.run(30);
    assert_ne!(s.fw.phase(), Phase::Stopped, "TxEnd ends the stop");
    assert!(!mcu_en_n(&s) && !s.fw.status().flags.link_lost_stop);
}

#[test]
fn link_loss_without_permit_holds_the_routes_p02() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    s.shack.mute = true;
    s.run(500);
    assert_eq!(s.fw.phase(), Phase::Run);
    assert_eq!(s.fw.fault(), FaultCode::LINK_TIMEOUT);
    assert!(!mcu_en_n(&s));
    assert_eq!(s.board.borrow().row(Radio::R1, true, Col::A1), Contact::No);
    s.shack.mute = false;
    s.run_until(400, |s| s.shack.link_up()).expect("link back");
    let st = s.command(Command::Poll);
    assert!(st.flags.ready);
    assert_eq!(st.routes[0], route(Col::A1, Col::A1));
}

#[test]
fn hello_releases_k0_after_the_f14_wait() {
    let mut s = r2_permit();
    s.shack.mute = true;
    ShackStub::send_raw(&mut s.board.borrow_mut(), 7, Command::Hello { version: 1 });
    let t = s.now();
    s.run(HELLO_RELEASE - 20);
    assert_eq!(s.board.borrow().k0(Radio::R2), Contact::No, "K0 held");
    assert!(!s.fw.status().permit_r2, "no permit after Hello");
    s.run(60);
    let off = last_change(&s, "R2_K0_DRV", false);
    assert!(
        off >= t + HELLO_RELEASE,
        "K0 off at {off}, Hello sent at {t}"
    );
}

// ------------------------------------------------------------------ faults

#[test]
fn watchdog_kicks_and_a_hang_trips_it() {
    let mut s = started();
    let t0 = s.now();
    s.run(3000);
    {
        let b = s.board.borrow();
        let kicks: Vec<Ms> = b
            .trace
            .signal("WDI")
            .iter()
            .map(|e| e.0.as_ms())
            .filter(|&t| t >= t0)
            .collect();
        let gap = kicks.windows(2).map(|w| w[1] - w[0]).max().unwrap();
        assert!(gap <= 250, "longest WDI gap {gap} ms");
        assert!(b.signals().reset_n && b.signals().rly_en);
    }
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    s.mcu_running = false;
    s.run(2600);
    let b = s.board.borrow();
    assert!(
        b.signals().fault && !b.signals().rly_en,
        "watchdog set FAULT"
    );
    assert_eq!(b.row(Radio::R1, true, Col::A1), Contact::Nc);
}

#[test]
fn expander_nack_sets_up_again() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    s.board.borrow_mut().exp[1].force_nack = true;
    // Two polls are retried (F-3), the third failure counts.
    s.run(60);
    assert_eq!(s.fw.fault(), FaultCode::EXPANDER_NACK);
    assert!(matches!(s.fw.phase(), Phase::WaitSafe { .. }));
    assert!(!mcu_en_n(&s));
    s.board.borrow_mut().exp[1].force_nack = false;
    s.run_until(50, |s| s.fw.phase() == Phase::Run)
        .expect("set up again");
    s.run(20);
    assert_eq!(
        s.board.borrow().row(Radio::R1, true, Col::A1),
        Contact::Nc,
        "outputs 0 after set-up"
    );
}

#[test]
fn expander_lost_with_permit_opens_safe() {
    let mut s = r2_permit();
    s.board.borrow_mut().exp[2].force_nack = true;
    s.run_until(100, |s| s.fw.phase() == Phase::Stopped)
        .expect("stop after the retries");
    assert!(mcu_en_n(&s));
    assert_eq!(s.fw.fault(), FaultCode::EXPANDER_NACK);
    assert!(!s.fw.status().flags.link_lost_stop);
}

#[test]
fn bias_t_on_a2_only_and_off_on_a_short() {
    let mut s = started();
    let a1 = ColMask::EMPTY.with(Col::A1);
    let a2 = ColMask::EMPTY.with(Col::A2);
    assert_eq!(s.command(Command::SetBias(a1)).result, ResultCode::Hazard);
    assert_eq!(s.command(Command::SetBias(a2)).result, ResultCode::Ok);
    s.run(60);
    let st = s.command(Command::Poll);
    assert_eq!(
        (st.bias_en, st.bias_ok, st.fault),
        (a2, a2, FaultCode::NONE)
    );
    assert!(s.board.borrow().signals().bias_out[1]);
    s.board.borrow_mut().set_env(|e| e.bias_short[1] = true);
    s.run(30);
    assert_eq!(s.fw.fault(), FaultCode::BIAS_T);
    let st = s.command(Command::Poll);
    assert_eq!(st.bias_en, ColMask::EMPTY, "feed switched off");
    assert_eq!(out_writes(&s, ADDR_U1001).last().unwrap().1, 0);
}

#[test]
fn k0_that_does_not_follow_gives_no_permit() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R2, Col::A3, Col::A3), ResultCode::Ok);
    settle(&mut s);
    s.board.borrow_mut().exp[2].stuck_low = 1 << exp::R2_K0.bit;
    assert_eq!(
        s.command(Command::TxRequest(Radio::R2)).result,
        ResultCode::Ok
    );
    s.run(100);
    let st = fresh(&mut s);
    assert!(!st.permit_r2, "no permit without the read-back");
    assert_eq!(st.fault, FaultCode::READ_BACK);
    assert_eq!(
        out_writes(&s, ADDR_U903).last().unwrap().1 & (1 << exp::R2_K0.bit),
        0,
        "K0 written off"
    );
}

#[test]
fn a_row_that_does_not_follow_is_a_read_back_fault() {
    let mut s = started();
    s.board.borrow_mut().exp[0].stuck_low = 1 << exp::R1_RX4.bit;
    assert_eq!(set(&mut s, Radio::R1, Col::A4, Col::A4), ResultCode::Ok);
    settle(&mut s);
    let st = fresh(&mut s);
    assert_eq!(st.fault, FaultCode::READ_BACK);
    assert_eq!(
        st.routes[0],
        route(Col::A4, Col::None),
        "status shows the read-back"
    );
}

// ------------------------------------------------------------------ self-test

/// A box powered with the SAFE loop closed, run until the self-test ends.
fn self_test(s: &mut BoxSim) -> Ms {
    s.run_until(6000, |s| matches!(s.fw.phase(), Phase::Run | Phase::Failed))
        .expect("self-test ends")
}

#[test]
fn self_test_passes_at_min_and_max_supervisor_timing() {
    for corner in [Corner::Min, Corner::Max] {
        let mut s = BoxSim::with(corner, Rt1Timing::MAX);
        let t = self_test(&mut s);
        assert_eq!(s.fw.phase(), Phase::Run, "{corner:?} at {t} ms");
        assert_eq!(s.fw.fault(), FaultCode::NONE, "{corner:?}");
        let trips = s
            .board
            .borrow()
            .trace
            .signal("RESET_N")
            .iter()
            .filter(|e| !e.1)
            .count();
        assert_eq!(trips, 2, "{corner:?}: power-up reset and one watchdog trip");
        no_harm(&s);
    }
}

#[test]
fn self_test_finds_a_stuck_ready_switch() {
    let mut s = BoxSim::new();
    s.board
        .borrow_mut()
        .set_env(|e| e.ready_stuck_closed = true);
    self_test(&mut s);
    assert_eq!(s.fw.phase(), Phase::Failed);
    assert_eq!(s.fw.fault(), FaultCode::SELFTEST_GATE);
    assert!(mcu_en_n(&s), "MCU_EN_N stays high");
    assert!(!s.board.borrow().signals().rly_en, "no relay can move");
}

#[test]
fn self_test_finds_an_expander_reset_pin_open() {
    // The fault freezes the reset state at injection: inject it while U1001 runs,
    // then power-cycle, so the next self-test meets an expander that RLY_EN = 0
    // cannot reset.
    let mut s = BoxSim::new();
    self_test(&mut s);
    s.board.borrow_mut().exp[3].reset_open = true;
    s.board.borrow_mut().set_env(|e| e.power = false);
    s.run(100);
    s.board.borrow_mut().set_env(|e| e.power = true);
    s.run(10);
    self_test(&mut s);
    assert_eq!(s.fw.fault(), FaultCode::SELFTEST_GATE);
    assert_eq!(s.fw.phase(), Phase::Failed);
}

#[test]
fn self_test_finds_the_watchdog_off() {
    // R64 open: WDI does not reach the supervisor (D-123).
    let mut s = BoxSim::new();
    s.board.borrow_mut().set_env(|e| e.wdi_link = false);
    let t = self_test(&mut s);
    assert_eq!(s.fw.fault(), FaultCode::SELFTEST_WATCHDOG, "at {t} ms");
    assert_eq!(s.fw.phase(), Phase::Failed);
    assert!(mcu_en_n(&s) && !s.board.borrow().signals().rly_en);
    // The box keeps answering, not ready, and keeps its fault code.
    s.shack.mute = true;
    s.run(500);
    let st = s.fw.status();
    assert!(!st.flags.ready);
    assert_eq!(st.fault, FaultCode::SELFTEST_WATCHDOG);
}

#[test]
fn self_test_finds_a_missing_expander() {
    let mut s = BoxSim::new();
    s.board.borrow_mut().exp[2].force_nack = true;
    self_test(&mut s);
    assert_eq!(s.fw.fault(), FaultCode::EXPANDER_NACK);
    assert_eq!(s.fw.phase(), Phase::Failed);
}

#[test]
fn self_test_warns_on_tx_any_at_start_up() {
    let mut s = BoxSim::new();
    s.board.borrow_mut().set_env(|e| e.ptt_loop = true);
    self_test(&mut s);
    assert_eq!(s.fw.phase(), Phase::Run, "a warning only");
    assert_eq!(s.fw.fault(), FaultCode::SELFTEST_INPUT);
}

#[test]
fn a_failed_box_starts_again_after_a_power_cycle() {
    let mut s = BoxSim::new();
    s.board.borrow_mut().set_env(|e| e.wdi_link = false);
    self_test(&mut s);
    assert_eq!(s.fw.phase(), Phase::Failed);
    s.board.borrow_mut().set_env(|e| {
        e.power = false;
        e.wdi_link = true;
    });
    s.run(100);
    s.board.borrow_mut().set_env(|e| e.power = true);
    s.run(10);
    self_test(&mut s);
    assert_eq!(s.fw.phase(), Phase::Run);
}

#[test]
fn self_test_rejects_an_early_trip() {
    // The loop opens 200 ms into the watchdog step (KILL pressed): too early to be
    // the supervisor, so the test fails rather than taking it as a trip.
    let mut s = BoxSim::new();
    s.run_until(3000, |s| {
        matches!(
            s.fw.phase(),
            Phase::SelfTest(box_core::relay_box::SelfTest::Watchdog { .. })
        )
    })
    .expect("watchdog step");
    s.run(200);
    s.shack.kill_pressed = true;
    s.run(20);
    assert_eq!(s.fw.phase(), Phase::Failed);
    assert_eq!(s.fw.fault(), FaultCode::SELFTEST_WATCHDOG);
}

#[test]
fn self_test_finds_a_latch_that_does_not_clear() {
    // The loop stays open after the second LATCH_CLR edge.
    let mut s = BoxSim::new();
    s.run_until(5000, |s| {
        matches!(
            s.fw.phase(),
            Phase::SelfTest(box_core::relay_box::SelfTest::Recover { .. })
        )
    })
    .expect("recover step");
    s.shack.kill_pressed = true;
    self_test(&mut s);
    assert_eq!(s.fw.phase(), Phase::Failed);
    assert_eq!(s.fw.fault(), FaultCode::SELFTEST_LATCH);
    assert!(mcu_en_n(&s));
}

// ------------------------------------------------------------------ review 2026-10-31

#[test]
fn hello_keeps_k0_while_rf_is_on_the_column_f1() {
    // R2 has no TX INH and keeps sending RF on A3 after the shack lost its link:
    // the Hello must not release K0 under that RF.
    let mut s = r2_permit();
    s.board.borrow_mut().set_env(|e| e.radio_rf[1] = true);
    s.run(20);
    s.shack.mute = true;
    ShackStub::send_raw(&mut s.board.borrow_mut(), 7, Command::Hello { version: 1 });
    s.run(HELLO_RELEASE + 200);
    assert_eq!(
        s.board.borrow().k0(Radio::R2),
        Contact::No,
        "K0 held under RF"
    );
    s.board.borrow_mut().set_env(|e| e.radio_rf[1] = false);
    s.run(50);
    assert_eq!(
        s.board.borrow().k0(Radio::R2),
        Contact::Nc,
        "released after the RF"
    );
    no_harm(&s);
}

#[test]
fn no_tx_on_exp_without_unit_2_f2() {
    let mut s = started();
    assert_eq!(
        set(&mut s, Radio::R2, Col::Exp, Col::A3),
        ResultCode::Hazard
    );
    assert_eq!(
        set(&mut s, Radio::R2, Col::A3, Col::Exp),
        ResultCode::Ok,
        "RX on EXP is fine"
    );
    settle(&mut s);
    assert_eq!(
        s.command(Command::TxRequest(Radio::R2)).result,
        ResultCode::Ok
    );
}

#[test]
fn one_i2c_error_with_a_permit_out_is_ridden_out_f3() {
    let mut s = r2_permit();
    s.board.borrow_mut().exp[2].force_nack = true;
    s.run(15); // one or two polls fail
    s.board.borrow_mut().exp[2].force_nack = false;
    s.run(50);
    assert_eq!(s.fw.phase(), Phase::Run, "no stop");
    assert!(s.fw.status().permit_r2, "permit kept");
    assert!(!mcu_en_n(&s));
    no_harm(&s);
}

#[test]
fn a_disturbed_output_register_is_written_again_f3() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    // A disturbance clears U901's output register (all R1 rows and K1 off).
    {
        let mut b = s.board.borrow_mut();
        let _ = b.i2c(
            ADDR_U901,
            &mut [embedded_hal::i2c::Operation::Write(&[2, 0, 0])],
        );
    }
    s.run(40);
    assert_eq!(s.fw.fault(), FaultCode::READ_BACK);
    let b = s.board.borrow();
    assert!(
        b.exp_pin(exp::R1_TX1) && b.exp_pin(exp::A1_K1),
        "written again"
    );
}

#[test]
fn switching_steps_leave_room_for_the_i2c_time_f4() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    assert_eq!(set(&mut s, Radio::R1, Col::A4, Col::A4), ResultCode::Ok);
    settle(&mut s);
    let open = last_change(&s, "R1_TX1_DRV", false);
    let k1_on = last_change(&s, "A4_K1_DRV", true);
    let close = last_change(&s, "R1_TX4_DRV", true);
    // 12 ms relay time plus 8 ms for up to two full expander reads at 100 kHz.
    assert!(
        k1_on >= open + 20 && close >= k1_on + 20,
        "{open} {k1_on} {close}"
    );
}

#[test]
fn separate_i2c_glitches_do_not_add_up_f3() {
    // Two short glitches, far apart: each is ridden out on its own.
    let mut s = r2_permit();
    for _ in 0..3 {
        s.board.borrow_mut().exp[2].force_nack = true;
        s.run(12);
        s.board.borrow_mut().exp[2].force_nack = false;
        s.run(200);
    }
    assert_eq!(s.fw.phase(), Phase::Run, "no stop");
    assert!(s.fw.status().permit_r2);
}

/// LATCH_CLR rising edges since `from`.
fn latch_clr_edges(s: &BoxSim, from: Ms) -> usize {
    s.board
        .borrow()
        .trace
        .signal("LATCH_CLR")
        .iter()
        .filter(|e| e.0.as_ms() >= from && e.1)
        .count()
}

#[test]
fn supervisor_trip_waits_for_clear_fault_d191() {
    let mut s = started();
    assert_eq!(set(&mut s, Radio::R1, Col::A1, Col::A1), ResultCode::Ok);
    settle(&mut s);
    // A loop hang that ends (review S-1): the supervisor trips, the MCU runs on.
    s.mcu_running = false;
    s.run_until(3000, |s| s.board.borrow().signals().fault)
        .expect("watchdog sets FAULT");
    s.mcu_running = true;
    s.run(200);
    assert_eq!(s.fw.fault(), FaultCode::SUPERVISOR_TRIP);
    // No way back by itself: no LATCH_CLR edge, READY stays open.
    let t = s.now();
    s.run(2000);
    let st = fresh(&mut s);
    assert_eq!(st.fault, FaultCode::SUPERVISOR_TRIP);
    assert!(!st.flags.ready && st.flags.kill);
    assert_eq!(latch_clr_edges(&s, t), 0, "no edge without the request");
    assert!(s.board.borrow().signals().fault);
    // The operator request: one edge, the latch clears, the box runs again.
    let t = s.now();
    let st = s.command(Command::ClearFault);
    assert_eq!(st.result, ResultCode::Ok);
    assert_eq!(latch_clr_edges(&s, t), 1);
    assert!(!s.board.borrow().signals().fault);
    s.run_until(200, |s| s.fw.phase() == Phase::Run)
        .expect("back in Run");
    assert_eq!(s.fw.fault(), FaultCode::NONE);
    assert!(fresh(&mut s).flags.ready);
    assert_eq!(
        s.board.borrow().row(Radio::R1, true, Col::A1),
        Contact::Nc,
        "relays come back off; the shack restores the routes"
    );
}

#[test]
fn clear_fault_without_a_trip_does_nothing_d191() {
    let mut s = started();
    let t = s.now();
    let st = s.command(Command::ClearFault);
    assert_eq!(st.result, ResultCode::Ok);
    assert_eq!(st.fault, FaultCode::NONE);
    assert_eq!(
        latch_clr_edges(&s, t),
        0,
        "rule 2: no edge without a known cause"
    );
    assert_eq!(s.fw.phase(), Phase::Run);
}
