//! Host protocol on the simulated shack interface (docs/design/host-protocol.md).

use link_proto::{Command, Radio};
use shack_core::shack::TX_END_MIN_WAIT;
use sim_shack::ShackSim;

/// Events from line index `from`, in order, that start with `!`.
fn events_from(s: &ShackSim, from: usize) -> Vec<String> {
    s.host_lines[from..]
        .iter()
        .filter(|(_, l)| l.starts_with('!'))
        .map(|(_, l)| l.clone())
        .collect()
}

/// The lines in `want` appear in this order among the events from `from`.
fn in_order(s: &ShackSim, from: usize, want: &[&str]) {
    let ev = events_from(s, from);
    let mut i = 0;
    for e in &ev {
        if i < want.len() && e == want[i] {
            i += 1;
        }
    }
    assert_eq!(i, want.len(), "missing {:?} in {ev:#?}", want.get(i));
}

/// Run `ms`, sending `status` every 500 ms as a host keeps alive.
fn run_alive(s: &mut ShackSim, ms: u64) {
    let end = s.now() + ms;
    while s.now() < end {
        s.host("status");
        s.run(500.min(end.saturating_sub(s.now())));
    }
}

fn routed_r2(s: &mut ShackSim) {
    s.start();
    assert_eq!(s.host("route R2 A1 A1"), "ok");
    s.run(150);
}

#[test]
fn hello_and_status() {
    let mut s = ShackSim::new();
    s.run(50);
    let st = s.host("status");
    assert!(
        st.starts_with("ok link=down") && st.contains("box=?"),
        "{st}"
    );
    assert!(
        st.contains("latched=1"),
        "unknown expander shows latched: {st}"
    );
    s.start();
    assert_eq!(s.host("hello"), "ok shack fw 0.1.0 proto 1");
    let st = s.host("status");
    assert!(
        st.starts_with("ok link=up safe=ok latched=0 kill=0 fault=0 stop=0 band=15 box=ready"),
        "{st}"
    );
    assert!(st.contains("r2=-/-,tx=idle,permit=0,key=0"), "{st}");
    in_order(&s, 0, &["!expander ready", "!link up", "!latched 0"]);
}

#[test]
fn tx_over_the_host_port() {
    let mut s = ShackSim::new();
    routed_r2(&mut s);
    in_order(&s, 0, &["!route R2 A1 A1"]);
    let from = s.host_lines.len();
    assert_eq!(s.host("tx R2 on"), "ok");
    assert_eq!(s.host("key R2 on"), "ok");
    run_alive(&mut s, 300);
    in_order(
        &s,
        from,
        &["!tx R2 requesting", "!tx R2 permitted", "!permit R2 on"],
    );
    assert!(s.board.borrow().signals().key_contact[1]);
    let st = s.host("status");
    assert!(st.contains("r2=A1/A1,tx=permitted,permit=1,key=1"), "{st}");

    let from = s.host_lines.len();
    assert_eq!(s.host("tx R2 off"), "ok");
    run_alive(&mut s, 400);
    in_order(
        &s,
        from,
        &[
            "!tx R2 ending",
            "!permit R2 off",
            "!tx R2 releasing",
            "!tx R2 idle",
        ],
    );
    assert!(!s.boxs.k0(Radio::R2));
}

#[test]
fn error_answers() {
    let mut s = ShackSim::new();
    s.run(50);
    assert!(s.host("route R2 A1 A1").starts_with("err linkdown"));
    s.start();
    assert!(s.host("tx R1 on").starts_with("err notforr1"));
    assert!(s.host("fly away").starts_with("err syntax"));
    assert!(s.host("route R9 A1 A1").starts_with("err arg"));
    assert!(s.host(&"x".repeat(200)).starts_with("err toolong"));
    assert!(s.host("clearfault").starts_with("err nofault"));
    assert_eq!(s.host("route R2 A1 A1"), "ok");
    s.run(150);
    s.host("tx R2 on");
    run_alive(&mut s, 200);
    assert!(
        s.host("route R2 A3 A3").starts_with("err txbusy"),
        "F13 on the shack side"
    );
    // A blank line is no command: no answer, but it keeps the host alive.
    let n = s.host_lines.len();
    s.board.borrow_mut().host_send("\r\n");
    s.run(20);
    assert_eq!(s.host_lines.len(), n);
}

#[test]
fn box_refusal_comes_as_an_event() {
    let mut s = ShackSim::new();
    s.start();
    let from = s.host_lines.len();
    assert_eq!(s.host("tx R2 on"), "ok");
    run_alive(&mut s, 300);
    in_order(&s, from, &["!refused tx R2 on notxroute"]);
}

/// Section 8: a silent host while R2 is keyed ends TX the normal way.
#[test]
fn host_keep_alive_ends_tx() {
    let mut s = ShackSim::new();
    routed_r2(&mut s);
    s.host("tx R2 on");
    s.host("key R2 on");
    let t_last = s.now();
    s.run(2500);
    let t_timeout = s.host_seen(0, "!host timeout").expect("timeout");
    assert!(
        (2000..=2020).contains(&(t_timeout - t_last)),
        "{} ms",
        t_timeout - t_last
    );
    assert!(!s.board.borrow().signals().key_contact[1]);
    let t_txend = s
        .boxs
        .log
        .iter()
        .find(|(t, c, _)| *c == Command::TxEnd(Radio::R2) && *t >= t_timeout)
        .map(|(t, _, _)| *t)
        .expect("TxEnd");
    assert!(
        t_txend >= t_timeout + TX_END_MIN_WAIT,
        "F14 also after a time-out"
    );

    // A host that keeps talking keeps its TX.
    let mut s = ShackSim::new();
    routed_r2(&mut s);
    s.host("tx R2 on");
    run_alive(&mut s, 5000);
    assert!(s.host_seen(0, "!host timeout").is_none());
    assert!(s.shack.permit(Radio::R2));
}

/// P3b-04 and C-2: a watchdog reset during operation blocks TX until `clearfault`.
#[test]
fn clearfault_after_a_watchdog_reset() {
    let mut s = ShackSim::new();
    s.start();
    s.mcu_running = false;
    s.run(2600);
    assert!(s.board.borrow().signals().fault);
    s.mcu_running = true;
    s.run(50);
    in_order(&s, 0, &["!expander lost", "!fault", "!expander ready"]);
    assert!(s.host("status").contains("fault=1"));
    assert!(!s.board.borrow().signals().tx_en, "TX blocked");
    assert_eq!(s.host("clearfault"), "ok");
    s.run(20);
    assert!(s.host_seen(0, "# fault latch cleared by host").is_some());
    assert!(!s.board.borrow().signals().fault);
    assert!(s.board.borrow().signals().tx_en);
    assert!(s.host("status").contains("fault=0"));
}

/// D-64, D-65: no host command clears the SAFE latch.
#[test]
fn no_command_clears_the_safe_latch() {
    let mut s = ShackSim::new();
    s.run_until(2000, |s| s.shack.link_up()).unwrap();
    for line in [
        "hello",
        "status",
        "clearfault",
        "stop on",
        "stop off",
        "route R2 A1 A1",
        "tx R2 on",
        "key R2 on",
        "key R1 on",
        "bias A2",
        "events off",
        "events on",
    ] {
        s.host(line);
        s.run(50);
        assert!(s.board.borrow().signals().latched, "after {line:?}");
        assert!(s.board.borrow().signals().inhibit.iter().all(|x| *x));
    }
}

#[test]
fn events_off_keeps_answers() {
    let mut s = ShackSim::new();
    s.start();
    assert_eq!(s.host("events off"), "ok");
    let from = s.host_lines.len();
    s.host("route R2 A1 A1");
    s.run(200);
    assert!(events_from(&s, from).is_empty());
    assert!(s.host("status").starts_with("ok"));
}

/// Section 8 for R1: its permit stays (route unchanged), but the interface key is released.
#[test]
fn host_keep_alive_releases_the_r1_key() {
    let mut s = ShackSim::new();
    s.start();
    s.host("route R1 A1 A1");
    run_alive(&mut s, 300);
    assert_eq!(s.host("key R1 on"), "ok");
    s.run(20);
    assert!(s.board.borrow().signals().key_contact[0]);
    s.run(2100);
    assert!(s.host_seen(0, "!host timeout").is_some());
    let sig = s.board.borrow().signals();
    assert!(!sig.key_contact[0], "key released");
    assert!(!sig.inhibit[0], "R1 permit stays: routes are not touched");
}
