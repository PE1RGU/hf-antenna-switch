//! `sim-shack`: the simulated shack interface in a terminal UI (macOS, Linux, Windows).
//!
//! Options:
//!   --state <file>   stored settings file (default shack-sim-state.bin)
//!   --tcp <port>     TCP host port on 127.0.0.1 (default 7300); --no-tcp for none
//!   --view text|pixels  display view (default: by what the terminal supports)
//!   --probe          print what the display detection sees, then exit
//!   --demo           print a timeline of a start-up and one R2 transmission, no UI
//!   --pty            Unix only: host port on a pseudo-terminal, no UI

#[cfg(unix)]
mod pty;

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
    let args: Vec<String> = std::env::args().skip(1).collect();
    let value = |name: &str| {
        args.iter()
            .position(|a| a == name)
            .and_then(|i| args.get(i + 1).cloned())
    };
    let state_file = value("--state").unwrap_or_else(|| "shack-sim-state.bin".into());
    let tcp_port = if args.iter().any(|a| a == "--no-tcp") {
        None
    } else {
        Some(value("--tcp").and_then(|p| p.parse().ok()).unwrap_or(7300))
    };
    if args.iter().any(|a| a == "--probe") {
        sim_shack::tui::probe();
    } else if args.iter().any(|a| a == "--demo") {
        demo();
    } else if args.iter().any(|a| a == "--pty") {
        #[cfg(unix)]
        pty::run(ShackSim::use_state_file(std::path::Path::new(&state_file)));
        #[cfg(not(unix))]
        eprintln!("--pty needs a Unix system; use the terminal UI and its TCP port");
    } else if let Err(e) = sim_shack::tui::run(sim_shack::tui::Options {
        state_file: state_file.into(),
        tcp_port,
        text_view: match value("--view").as_deref() {
            Some("text") => Some(true),
            Some("pixels") => Some(false),
            _ => None,
        },
    }) {
        eprintln!("terminal UI: {e}");
    }
}

fn demo() {
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
