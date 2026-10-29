//! Demo run: start-up, RESET by the operator, R2 routed to A1, one R2 transmission
//! with an RF tail, end. Prints the timeline of the main signals and box actions.

use link_proto::{Col, Radio, Route};
use sim_core::TraceKind;
use sim_shack::ShackSim;

const SHOWN: [&str; 10] = [
    "RESET_N",
    "FAULT",
    "LATCHED",
    "TX_EN",
    "LATCH_CLR",
    "PERMIT_R2",
    "INH_R2",
    "KEYC_R2",
    "SW_STOP_N",
    "SAFE_CURRENT",
];

fn main() {
    let mut s = ShackSim::new();
    s.start();
    let route = Route {
        tx: Col::A1,
        rx: Col::A1,
    };
    s.shack.set_route(Radio::R2, route).unwrap();
    s.run(100);
    s.shack.set_tx(Radio::R2, true).unwrap();
    s.shack.set_key(Radio::R2, true);
    s.run(30);
    s.board.borrow_mut().set_env(|e| e.radio_tx[1] = true);
    s.run(500);
    s.shack.set_tx(Radio::R2, false).unwrap();
    s.run(60);
    s.board.borrow_mut().set_env(|e| e.radio_tx[1] = false);
    s.run(300);

    let mut lines: Vec<(u64, String)> = Vec::new();
    for e in s.board.borrow().trace.events() {
        if let TraceKind::Signal { name, value } = e.kind
            && SHOWN.contains(&name)
        {
            lines.push((e.t.as_us(), format!("{name:<13} {}", value as u8)));
        }
    }
    for (t, c, r) in &s.boxs.log {
        if !matches!(c, link_proto::Command::Poll) {
            lines.push((t * 1000, format!("box: {c:?} -> {r:?}")));
        }
    }
    for (t, r, on) in &s.boxs.k0_log {
        lines.push((
            t * 1000,
            format!("box: K0 {r:?} {}", if *on { "TX" } else { "RX" }),
        ));
    }
    for (t, e) in &s.events {
        lines.push((t * 1000, format!("fw:  {e:?}")));
    }
    lines.sort();
    // LATCHED is both a board signal and an expander input: same net, one line.
    lines.dedup();
    for (t, l) in lines {
        println!("{:>9.3} ms  {l}", t as f64 / 1000.0);
    }
}
