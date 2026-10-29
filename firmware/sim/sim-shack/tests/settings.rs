//! Stored settings (host-protocol.md 8a): names, routes, bias, page survive a power
//! cycle and a box restart; TX never does.

use link_proto::{Col, ColMask, Command, Radio, Route};
use sim_shack::ShackSim;
use sim_shack::box_stub::BoxStub;

fn route(tx: Col, rx: Col) -> Route {
    Route { tx, rx }
}

/// Set up a station and wait until the settings are saved.
fn configured() -> ShackSim {
    let mut s = ShackSim::new();
    s.start();
    for l in [
        "route R1 A1 A2",
        "route R2 - A3",
        "bias A2",
        "page c",
        "name A3 Hexbeam",
        "name R2 IC-7300",
    ] {
        assert_eq!(s.host(l), "ok", "{l}");
    }
    s.run(2500);
    s
}

#[test]
fn defaults_when_nothing_is_stored() {
    let mut s = ShackSim::new();
    s.run(50);
    assert!(
        s.host_seen(0, "# stored settings not found, defaults used")
            .is_some()
    );
    assert_eq!(
        s.host("names"),
        "ok A1=G5RV A2=Loop A3=spare A4=spare EXP=unit2 R1=FT-710 R2=WSPR R3=spare"
    );
}

#[test]
fn names_show_on_the_display() {
    let mut s = ShackSim::new();
    s.start();
    assert_eq!(s.host("name A3 Hexbeam"), "ok");
    assert_eq!(s.host("name R1 FT-991"), "ok");
    assert!(s.host("names").contains("A3=Hexbeam"));
    let ui = s.shack.ui_state();
    assert_eq!(ui.antenna_names[2].as_str(), "Hexbeam");
    assert_eq!(ui.radio_names[0].as_str(), "FT-991");
    assert!(s.host("name A3 Way-too-long").starts_with("err arg"));
}

#[test]
fn a_burst_of_changes_gives_one_save() {
    let s = configured();
    assert_eq!(s.saves(), 1, "six commands within 2 s, one flash write");
    assert!(!s.stored().is_empty());
}

#[test]
fn power_cycle_restores_the_station() {
    let old = configured();
    let record = old.stored();
    // Power cycle: new board, new box, same flash.
    let mut s = ShackSim::with_stored(record);
    s.run_until(3000, |s| s.shack.link_up()).unwrap();
    s.run(500);
    assert_eq!(s.boxs.routes[0], route(Col::A1, Col::A2));
    assert_eq!(s.boxs.routes[1], route(Col::None, Col::A3));
    assert_eq!(s.boxs.bias, ColMask::EMPTY.with(Col::A2));
    assert!(s.host("status").contains("page=c"));
    let names = s.host("names");
    assert!(
        names.contains("A3=Hexbeam") && names.contains("R2=IC-7300"),
        "{names}"
    );
    // Never TX: no TX request reached the box, and nothing is permitted.
    assert!(
        !s.boxs
            .log
            .iter()
            .any(|(_, c, _)| matches!(c, Command::TxRequest(_)))
    );
    assert!(
        Radio::ALL
            .iter()
            .all(|r| !s.shack.permit(*r) || *r == Radio::R1)
    );
    // The SAFE latch is set after power-up: the radios stay inhibited until RESET.
    assert!(s.board.borrow().signals().inhibit.iter().all(|x| *x));
    // Restoring gives no new save.
    assert_eq!(s.saves(), 0);
}

#[test]
fn box_restart_gets_the_routes_back() {
    let mut s = configured();
    // Box reboots: silent for 1 s, then a box without routes.
    s.boxs.mute = true;
    s.run(1000);
    s.boxs = BoxStub::new();
    s.run_until(2000, |s| s.shack.link_up()).unwrap();
    s.run(500);
    assert_eq!(s.boxs.routes[0], route(Col::A1, Col::A2));
    assert_eq!(s.boxs.routes[1], route(Col::None, Col::A3));
    assert_eq!(s.boxs.bias, ColMask::EMPTY.with(Col::A2));
}

#[test]
fn damaged_record_gives_defaults() {
    let mut record = configured().stored();
    record[5] ^= 0x40;
    let mut s = ShackSim::with_stored(record);
    s.run_until(3000, |s| s.shack.link_up()).unwrap();
    s.run(300);
    assert!(
        s.host_seen(0, "# stored settings not found, defaults used")
            .is_some()
    );
    assert_eq!(s.boxs.routes[0], Route::default(), "nothing restored");
}

/// The simulator keeps the record in a file, so a restart of the simulator is a power cycle.
#[test]
fn state_file_survives_a_simulator_restart() {
    let path = std::path::Path::new(env!("CARGO_TARGET_TMPDIR")).join("state-file-test.bin");
    let _ = std::fs::remove_file(&path);
    {
        let mut s = ShackSim::use_state_file(&path);
        s.start();
        assert_eq!(s.host("route R1 A1 A2"), "ok");
        assert_eq!(s.host("name A1 Dipole"), "ok");
        s.run(2500);
    }
    assert!(path.exists(), "saved to the file");
    let mut s = ShackSim::use_state_file(&path);
    s.run_until(3000, |s| s.shack.link_up()).unwrap();
    s.run(500);
    assert_eq!(s.boxs.routes[0], route(Col::A1, Col::A2));
    assert!(s.host("names").contains("A1=Dipole"));
}

/// F4 or `:power off`: the MCU is off, then starts from boot. The stored
/// settings stay; the SAFE latch is set again; a new start-up runs.
#[test]
fn power_cycle_in_the_emulator_restarts_the_firmware() {
    let mut s = configured();
    let lines_before = s.host_lines.len();
    s.world("power off").unwrap();
    s.run(500);
    assert_eq!(
        s.host_lines.len(),
        lines_before,
        "nothing from an unpowered MCU"
    );
    s.world("power on").unwrap();
    s.run_until(3000, |s| s.shack.link_up())
        .expect("link up after the restart");
    s.run(300);
    let ready = s
        .events
        .iter()
        .filter(|(_, e)| *e == shack_core::shack::Event::ExpanderReady)
        .count();
    assert_eq!(ready, 2, "a second start-up");
    assert_eq!(
        s.shack.ui_state().stop,
        Some(shack_ui::StopCause::PowerUp),
        "SAFE latch set at power-up"
    );
    let names = s.host("names");
    assert!(
        names.contains("A3=Hexbeam"),
        "stored settings kept: {names}"
    );
    assert!(s.host("status").contains("page=c"));
}
