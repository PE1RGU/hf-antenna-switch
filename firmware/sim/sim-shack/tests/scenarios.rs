//! Shack firmware scenarios on the board model with the scripted box.
//! References: system-verification.md (E3, F13, F14, rules 1 to 6), link-protocol.md 5.1 and 6.

use link_proto::{Col, Command, Ms, Radio, ResultCode, Route};
use shack_core::shack::{Event, TX_END_MIN_WAIT, TX_SENSE_PLAUSIBLE, TxState};
use sim_core::SimTime;
use sim_core::hal::Board;
use sim_shack::ShackSim;
use sim_shack::box_stub::K0_SETTLE;

const A1: Route = Route {
    tx: Col::A1,
    rx: Col::A1,
};

fn rising(s: &ShackSim, name: &str) -> Vec<Ms> {
    s.board
        .borrow()
        .trace
        .signal(name)
        .into_iter()
        .filter(|(_, v)| *v)
        .map(|(t, _)| t.as_ms())
        .collect()
}

fn first_rise_after(s: &ShackSim, name: &str, after: Ms) -> Option<Ms> {
    rising(s, name).into_iter().find(|t| *t >= after)
}

fn level(s: &ShackSim, name: &str) -> bool {
    let b = s.board.borrow();
    b.trace.level_at(name, b.now()).unwrap_or(false)
}

fn box_cmd_time(s: &ShackSim, cmd: Command, after: Ms) -> Option<Ms> {
    s.boxs
        .log
        .iter()
        .find(|(t, c, _)| *c == cmd && *t >= after)
        .map(|(t, _, _)| *t)
}

/// R2 routed to A1, permit out and keyed by the interface. Returns the request time.
fn r2_transmitting(s: &mut ShackSim) -> Ms {
    s.start();
    s.shack.set_route(Radio::R2, A1).unwrap();
    s.run(100);
    let t = s.now();
    s.shack.set_tx(Radio::R2, true).unwrap();
    s.shack.set_key(Radio::R2, true);
    s.run_until(300, |s| s.shack.permit(Radio::R2))
        .expect("permit R2");
    s.run(20);
    t
}

#[test]
fn start_up_order() {
    let mut s = ShackSim::new();
    s.run(3000);
    let b = s.board.borrow();
    let writes = b.trace.i2c_writes(0x74);
    let first_out = writes.iter().position(|(_, d)| d[0] == 2).unwrap();
    let first_cfg = writes.iter().position(|(_, d)| d[0] == 6).unwrap();
    assert!(first_out < first_cfg, "F1: outputs before configuration");
    assert!(
        writes[first_out].0 >= SimTime::ms(200),
        "after the supervisor td"
    );
    let clr = rising(&s, "LATCH_CLR");
    assert_eq!(clr.len(), 1, "LATCH_CLR once");
    assert!(SimTime::ms(clr[0]) >= writes[first_cfg].0);
    let fault = b.trace.signal("FAULT");
    assert_eq!(fault.last().map(|x| x.1), Some(false));
    assert_eq!(
        fault.iter().filter(|x| x.1).count(),
        1,
        "only the power-up fault"
    );
    assert!(b.signals().latched, "LATCHED waits for the operator");
    assert!(s.shack.link_up());
    let wdi = b.trace.signal("WDI");
    let max_gap = wdi.windows(2).map(|w| w[1].0 - w[0].0).max().unwrap();
    assert!(max_gap <= SimTime::ms(20), "WDI kicked every tick");
}

#[test]
fn r2_permit_only_after_the_box_permit() {
    let mut s = ShackSim::new();
    let t_req = r2_transmitting(&mut s);
    let (t_k0, r, on) = s.boxs.k0_log[0];
    assert_eq!((r, on), (Radio::R2, true));
    let t_permit = first_rise_after(&s, "PERMIT_R2", 0).unwrap();
    assert!(t_permit >= t_k0 + K0_SETTLE, "PERMIT after K0 settled");
    assert!(
        t_permit - t_req <= 120,
        "permit latency {} ms",
        t_permit - t_req
    );
    assert!(!s.board.borrow().signals().inhibit[1]);
    assert!(s.board.borrow().signals().key_contact[1]);
    let t_key = first_rise_after(&s, "KEYC_R2", 0).unwrap();
    assert!(t_key >= t_permit);
}

#[test]
fn latched_interface_keeps_the_radio_inhibited() {
    let mut s = ShackSim::new();
    s.run_until(2000, |s| s.shack.link_up()).unwrap();
    s.shack.set_route(Radio::R2, A1).unwrap();
    s.run(100);
    s.shack.set_tx(Radio::R2, true).unwrap();
    s.shack.set_key(Radio::R2, true);
    s.run(300);
    assert!(s.shack.permit(Radio::R2), "firmware gives the permit");
    let sig = s.board.borrow().signals();
    assert!(
        sig.inhibit[1] && !sig.key_contact[1],
        "hardware SAFE latch still inhibits"
    );
}

/// F14 with a radio RF tail after the inhibit: shorter and longer than the 100 ms minimum.
#[test]
fn tx_end_waits_for_tx_sense_and_100_ms() {
    for tail in [50, 180] {
        tx_end_with_tail(tail);
    }
}

fn tx_end_with_tail(tail: Ms) {
    let mut s = ShackSim::new();
    r2_transmitting(&mut s);
    s.board.borrow_mut().set_env(|e| e.radio_tx[1] = true);
    s.run(200);
    let t_end = s.now();
    s.shack.set_tx(Radio::R2, false).unwrap();
    s.run(tail);
    s.board.borrow_mut().set_env(|e| e.radio_tx[1] = false);
    let t_quiet = s.now();
    s.run_until(500, |s| !s.boxs.k0(Radio::R2))
        .expect("K0 released");
    let t_inh = first_rise_after(&s, "INH_R2", t_end).unwrap();
    assert!(t_inh <= t_end + 10, "inhibit at the next tick");
    let t_txend = box_cmd_time(&s, Command::TxEnd(Radio::R2), t_end).unwrap();
    assert!(t_txend >= t_quiet, "TX sense inactive first");
    assert!(
        t_txend >= t_inh + TX_END_MIN_WAIT,
        "at least 100 ms after the inhibit"
    );
    s.run(50);
    assert_eq!(s.shack.tx_state(Radio::R2), TxState::Idle);
    assert!(!level(&s, "PERMIT_R2"));
}

/// F14 with a failed TX sense opto: reads 'no TX' all the time.
#[test]
fn failed_tx_sense_is_flagged_and_end_still_waits() {
    let mut s = ShackSim::new();
    let t_req = r2_transmitting(&mut s);
    s.run(TX_SENSE_PLAUSIBLE + 50);
    let t = s
        .has_event(Event::TxSenseFault(Radio::R2))
        .expect("flagged");
    assert!(t >= t_req + TX_SENSE_PLAUSIBLE);
    let t_end = s.now();
    s.shack.set_tx(Radio::R2, false).unwrap();
    s.run_until(500, |s| !s.boxs.k0(Radio::R2)).unwrap();
    let t_inh = first_rise_after(&s, "INH_R2", t_end).unwrap();
    let t_txend = box_cmd_time(&s, Command::TxEnd(Radio::R2), t_end).unwrap();
    assert!(t_txend >= t_inh + TX_END_MIN_WAIT);
}

/// Link lost while R2 has its permit (F13): shack inhibits, box opens SAFE and keeps K0.
#[test]
fn link_loss_with_permit_out() {
    let mut s = ShackSim::new();
    r2_transmitting(&mut s);
    let t0 = s.now();
    s.boxs.mute = true;
    s.run(400);
    let t_off = s
        .board
        .borrow()
        .trace
        .signal("PERMIT_R2")
        .into_iter()
        .find(|(t, v)| t.as_ms() >= t0 && !*v)
        .unwrap()
        .0
        .as_ms();
    assert!(
        t_off <= t0 + 300 + 10,
        "permit off {} ms after the cut",
        t_off - t0
    );
    assert!(s.has_event(Event::LinkLost).is_some());
    assert!(s.boxs.k0(Radio::R2), "box keeps K0 (F13)");
    assert!(s.boxs.link_lost_stop);
    let sig = s.board.borrow().signals();
    assert!(!sig.safe_current && sig.latched && sig.inhibit[1]);
    // Link back: the shack ends the TX it had, after the F14 wait.
    s.boxs.mute = false;
    s.run_until(1000, |s| !s.boxs.k0(Radio::R2))
        .expect("TxEnd after the link returns");
    assert!(s.shack.link_up());
}

#[test]
fn refused_request_never_gives_a_permit() {
    let mut s = ShackSim::new();
    s.start();
    s.shack.set_tx(Radio::R2, true).unwrap();
    s.run(500);
    assert!(s.events.iter().any(|(_, e)| *e
        == Event::Refused {
            cmd: Command::TxRequest(Radio::R2),
            result: ResultCode::NoTxRoute
        }));
    assert!(rising(&s, "PERMIT_R2").is_empty());
    assert_eq!(s.shack.tx_state(Radio::R2), TxState::Idle);
}

/// R1: permit while its TX column is routed and terminated; off during a route change.
#[test]
fn r1_permit_follows_its_route() {
    let mut s = ShackSim::new();
    s.start();
    assert!(!s.shack.permit(Radio::R1), "no route, no permit");
    s.shack.set_route(Radio::R1, A1).unwrap();
    s.run_until(300, |s| s.shack.permit(Radio::R1))
        .expect("R1 permit");
    let t_change = s.now();
    s.shack
        .set_route(
            Radio::R1,
            Route {
                tx: Col::A3,
                rx: Col::A3,
            },
        )
        .unwrap();
    s.run(300);
    let route_cmd = Command::SetRoute {
        radio: Radio::R1,
        route: Route {
            tx: Col::A3,
            rx: Col::A3,
        },
    };
    let t_box = box_cmd_time(&s, route_cmd, t_change).unwrap();
    let b = s.board.borrow();
    assert_eq!(
        b.trace.level_at("PERMIT_R1", SimTime::ms(t_box)),
        Some(false)
    );
    drop(b);
    assert!(s.shack.permit(Radio::R1), "back after the switching");
}

#[test]
fn software_stop_opens_the_loop() {
    let mut s = ShackSim::new();
    s.start();
    s.shack.software_stop(true);
    s.run(20);
    let sig = s.board.borrow().signals();
    assert!(!sig.safe_current && sig.latched && !sig.tx_en);
    s.shack.software_stop(false);
    s.run(20);
    assert!(s.board.borrow().signals().latched, "only RESET clears");
    s.press_reset();
    assert!(s.board.borrow().signals().tx_en);
}

#[test]
fn expander_lost_drops_permits_and_sets_up_again() {
    let mut s = ShackSim::new();
    r2_transmitting(&mut s);
    let t0 = s.now();
    s.board.borrow_mut().exp.force_nack = true;
    s.run(30);
    assert!(s.has_event(Event::ExpanderLost).is_some());
    assert!(!level(&s, "PERMIT_R2"));
    s.board.borrow_mut().exp.force_nack = false;
    s.run(30);
    let writes = s.board.borrow().trace.i2c_writes(0x74);
    let after: Vec<_> = writes
        .iter()
        .filter(|(t, _)| t.as_ms() > t0)
        .map(|(_, d)| d[0])
        .collect();
    let out = after.iter().position(|r| *r == 2).unwrap();
    let cfg = after.iter().position(|r| *r == 6).unwrap();
    assert!(out < cfg, "F1 again after the loss");
    assert_eq!(
        rising(&s, "LATCH_CLR").len(),
        1,
        "fault latch not cleared again"
    );
    assert_eq!(
        s.events
            .iter()
            .filter(|(_, e)| *e == Event::ExpanderReady)
            .count(),
        2
    );
}

/// system-verification.md E3: shack MCU hangs with a permit out.
#[test]
fn shack_mcu_hang() {
    let mut s = ShackSim::new();
    r2_transmitting(&mut s);
    let t0 = s.now();
    s.mcu_running = false;
    s.run(3000);
    let t_fault = first_rise_after(&s, "FAULT", t0).expect("watchdog fault");
    assert!(t_fault - t0 <= 2500);
    let sig = s.board.borrow().signals();
    assert!(sig.inhibit[1] && !sig.key_contact[1]);
    assert!(s.boxs.k0(Radio::R2), "box keeps K0: no RF off the TX row");
}

/// Link lost: the R1 permit drops too (the box state is unknown).
#[test]
fn link_loss_drops_the_r1_permit() {
    let mut s = ShackSim::new();
    s.start();
    s.shack.set_route(Radio::R1, A1).unwrap();
    s.run_until(300, |s| s.shack.permit(Radio::R1)).unwrap();
    let t0 = s.now();
    s.boxs.mute = true;
    s.run(400);
    assert!(!s.shack.permit(Radio::R1));
    let off = s
        .board
        .borrow()
        .trace
        .signal("PERMIT_R1")
        .into_iter()
        .find(|(t, v)| t.as_ms() >= t0 && !*v)
        .unwrap()
        .0
        .as_ms();
    assert!(off <= t0 + 310);
}

/// A slow box: the permit bit comes 200 ms after K0. PERMIT waits for the bit, not for a time.
#[test]
fn permit_waits_for_the_permit_bit() {
    let mut s = ShackSim::new();
    s.boxs.k0_settle = 200;
    r2_transmitting(&mut s);
    let (t_k0, _, _) = s.boxs.k0_log[0];
    let t_permit = first_rise_after(&s, "PERMIT_R2", 0).unwrap();
    assert!(
        t_permit >= t_k0 + 200,
        "PERMIT {} ms after K0",
        t_permit - t_k0
    );
}
