//! Shack power-up self-test (host-protocol.md section 6): expander, SAFE latch,
//! watchdog trip, start-up inputs. Each fault is injected in the board model.

use host_proto::{SelfTestItem, SelfTestState};
use link_proto::{Col, Radio, Route};
use sim_models::tps3823::Corner;
use sim_shack::ShackSim;

/// Run until the self-test ends; its result.
fn result(s: &mut ShackSim) -> SelfTestState {
    s.run_until(6000, |s| s.shack.self_test() != SelfTestState::Running)
        .expect("self-test ends");
    s.shack.self_test()
}

/// After a failed self-test: RESET clears the SAFE latch, but the fault latch keeps
/// TX_EN low, and no permit goes out.
fn tx_stays_blocked(s: &mut ShackSim) {
    s.press_reset();
    s.run(100);
    assert!(!s.board.borrow().signals().tx_en, "TX_EN low");
    assert!(
        s.host("clearfault").starts_with("err nofault"),
        "no LATCH_CLR from the host"
    );
    for r in Radio::ALL {
        assert!(!s.shack.permit(r));
    }
}

#[test]
fn passes_at_min_and_max_supervisor_timing() {
    for corner in [Corner::Min, Corner::Max] {
        let mut s = ShackSim::with(corner, Vec::new());
        let from = s.host_lines.len();
        assert_eq!(result(&mut s), SelfTestState::Pass, "{corner:?}");
        assert!(s.host_seen(from, "!selftest pass").is_some());
        assert!(s.host("status").ends_with("selftest=pass"));
        s.run_until(1000, |s| s.shack.link_up()).expect("link up");
        s.press_reset();
        s.run(100);
        assert!(s.board.borrow().signals().tx_en, "{corner:?}: TX_EN");
    }
}

#[test]
fn no_expander_fails_and_blocks_tx() {
    let mut s = ShackSim::new();
    s.board.borrow_mut().exp.force_nack = true;
    let from = s.host_lines.len();
    assert_eq!(result(&mut s), SelfTestState::Fail(SelfTestItem::Expander));
    assert!(s.host_seen(from, "!selftest fail expander").is_some());
    assert!(s.host("status").ends_with("selftest=fail-expander"));
    // The expander comes later: the self-test stays failed until a power cycle.
    s.board.borrow_mut().exp.force_nack = false;
    s.run(500);
    tx_stays_blocked(&mut s);
}

#[test]
fn watchdog_off_fails_and_blocks_tx() {
    // R64 open: WDI does not reach the supervisor (D-123).
    let mut s = ShackSim::new();
    s.board.borrow_mut().set_env(|e| e.wdi_link = false);
    assert_eq!(result(&mut s), SelfTestState::Fail(SelfTestItem::Watchdog));
    assert!(
        s.board
            .borrow()
            .trace
            .signal("LATCH_CLR")
            .iter()
            .all(|e| !e.1),
        "no LATCH_CLR edge"
    );
    s.run_until(1000, |s| s.shack.link_up()).expect("link up");
    s.shack
        .set_route(
            Radio::R2,
            Route {
                tx: Col::A1,
                rx: Col::A1,
            },
        )
        .unwrap();
    s.run(100);
    s.shack.set_tx(Radio::R2, true).unwrap();
    s.run(300);
    tx_stays_blocked(&mut s);
    assert!(s.shack.ui_state().fault, "the display shows the fault");
}

#[test]
fn latch_clear_at_power_up_fails() {
    // RESET pressed just as POR_N releases the SAFE latch, before the first
    // expander read: the latch reads clear, which a working latch never does at
    // power-up.
    let mut s = ShackSim::new();
    s.run(200);
    s.board.borrow_mut().set_env(|e| e.reset_pressed = true);
    s.run(5);
    s.board.borrow_mut().set_env(|e| e.reset_pressed = false);
    assert_eq!(result(&mut s), SelfTestState::Fail(SelfTestItem::Latch));
}

#[test]
fn tx_sense_at_start_up_is_a_warning() {
    // R1 ignores TX INH and transmits from power-up.
    let mut s = ShackSim::new();
    s.board.borrow_mut().set_env(|e| {
        e.radio_no_inh[0] = true;
        e.radio_tx[0] = true;
    });
    let from = s.host_lines.len();
    assert_eq!(result(&mut s), SelfTestState::Pass, "a warning only");
    assert!(s.host_seen(from, "!selftest warn txsense R1").is_some());
}

#[test]
fn an_early_expander_loss_is_no_watchdog_trip() {
    // The expander is lost 100 ms into the watchdog step: too early for the
    // supervisor (0.9 s at least), so the test fails.
    let mut s = ShackSim::new();
    s.run_until(1000, |s| {
        s.board
            .borrow()
            .trace
            .signal("WDI")
            .last()
            .is_some_and(|e| e.0.as_ms() + 50 < s.now())
    })
    .expect("kicks stopped");
    s.run(50);
    s.board.borrow_mut().exp.force_nack = true;
    s.run(20);
    assert_eq!(
        s.shack.self_test(),
        SelfTestState::Fail(SelfTestItem::Watchdog)
    );
}
