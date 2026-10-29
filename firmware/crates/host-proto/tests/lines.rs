//! Host line parsing and formatting against docs/design/host-protocol.md.

use host_proto::*;
use link_proto::{Col, ColMask, Command, Radio, ResultCode, Route};
use proptest::prelude::*;

fn route(tx: Col, rx: Col) -> Route {
    Route { tx, rx }
}

#[test]
fn every_command_parses() {
    let cases = [
        ("hello", HostCommand::Hello),
        ("status", HostCommand::Status),
        ("clearfault", HostCommand::ClearFault),
        (
            "route R2 A1 A3",
            HostCommand::Route {
                radio: Radio::R2,
                route: route(Col::A1, Col::A3),
            },
        ),
        (
            "route r1 - exp",
            HostCommand::Route {
                radio: Radio::R1,
                route: route(Col::None, Col::Exp),
            },
        ),
        (
            "tx R3 on",
            HostCommand::Tx {
                radio: Radio::R3,
                on: true,
            },
        ),
        (
            "key R1 off",
            HostCommand::Key {
                radio: Radio::R1,
                on: false,
            },
        ),
        (
            "bias A2,A3",
            HostCommand::Bias(ColMask::EMPTY.with(Col::A2).with(Col::A3)),
        ),
        ("bias -", HostCommand::Bias(ColMask::EMPTY)),
        ("stop on", HostCommand::Stop(true)),
        ("events off", HostCommand::Events(false)),
        ("keepalive 60", HostCommand::KeepAlive(60)),
        ("page c", HostCommand::Page(PageSel::Cards)),
        ("page AUTO", HostCommand::Page(PageSel::Auto)),
        ("KEEPALIVE 2", HostCommand::KeepAlive(2)),
        ("  STATUS  \r", HostCommand::Status),
    ];
    for (line, cmd) in cases {
        assert_eq!(parse(line), Ok(cmd), "{line:?}");
    }
}

#[test]
fn errors() {
    let cases = [
        ("", ErrorCode::Syntax),
        ("reboot", ErrorCode::Syntax),
        ("hello there", ErrorCode::Syntax),
        ("route R2 A1", ErrorCode::Syntax),
        ("route R2 A1 A1 A1", ErrorCode::Syntax),
        ("route R4 A1 A1", ErrorCode::Arg),
        ("route R2 A5 A1", ErrorCode::Arg),
        ("tx R2 maybe", ErrorCode::Arg),
        ("tx R1 on", ErrorCode::NotForR1),
        ("bias A1,-", ErrorCode::Arg),
        ("bias A1,,A2", ErrorCode::Arg),
        ("keepalive 1", ErrorCode::Arg),
        ("page d", ErrorCode::Arg),
        ("keepalive 61", ErrorCode::Arg),
        ("keepalive 300", ErrorCode::Arg),
        ("keepalive soon", ErrorCode::Arg),
        ("keepalive", ErrorCode::Syntax),
    ];
    for (line, e) in cases {
        assert_eq!(parse(line), Err(e), "{line:?}");
    }
    let long = "status".to_string() + &" ".repeat(MAX_LINE);
    assert_eq!(parse(&long), Err(ErrorCode::TooLong));
}

#[test]
fn answers_and_events_as_in_the_spec() {
    let cases: [(String, &str); 9] = [
        (
            ErrorLine(ErrorCode::TxBusy).to_string(),
            "err txbusy radio transmits or ends TX",
        ),
        (
            HostEvent::Tx(Radio::R2, TxPhase::Permitted).to_string(),
            "!tx R2 permitted",
        ),
        (HostEvent::Link(false).to_string(), "!link down"),
        (
            HostEvent::Permit(Radio::R1, true).to_string(),
            "!permit R1 on",
        ),
        (
            HostEvent::Refused(Command::TxRequest(Radio::R2), ResultCode::NoTxRoute).to_string(),
            "!refused tx R2 on notxroute",
        ),
        (
            HostEvent::Refused(
                Command::SetRoute {
                    radio: Radio::R3,
                    route: route(Col::A2, Col::A2),
                },
                ResultCode::Hazard,
            )
            .to_string(),
            "!refused route R3 A2 A2 hazard",
        ),
        (
            HostEvent::TxSenseFault(Radio::R3).to_string(),
            "!txsense R3 fault",
        ),
        (
            HostEvent::Route(Radio::R1, route(Col::A1, Col::None)).to_string(),
            "!route R1 A1 -",
        ),
        (HostEvent::HostTimeout.to_string(), "!host timeout"),
    ];
    for (got, want) in cases {
        assert_eq!(got, want);
    }
}

#[test]
fn status_line_as_in_the_spec() {
    let s = StatusLine {
        link: true,
        safe_ok: true,
        latched: false,
        kill: false,
        fault: false,
        stop: false,
        keepalive: 2,
        page: PageSel::Flow,
        band: 5,
        boxs: Some(BoxPart {
            ready: true,
            k1: ColMask::EMPTY.with(Col::A1).with(Col::A3),
            ..Default::default()
        }),
        radios: [
            RadioStatus {
                route: Some(route(Col::A1, Col::A1)),
                tx: None,
                permit: true,
                key: false,
            },
            RadioStatus {
                route: Some(route(Col::A3, Col::A3)),
                tx: Some(TxPhase::Permitted),
                permit: true,
                key: true,
            },
            RadioStatus {
                route: Some(route(Col::None, Col::None)),
                tx: Some(TxPhase::Idle),
                permit: false,
                key: false,
            },
        ],
    };
    assert_eq!(
        s.to_string(),
        "ok link=up safe=ok latched=0 kill=0 fault=0 stop=0 keepalive=2 page=b band=5 box=ready \
         r1=A1/A1,permit=1,key=0 r2=A3/A3,tx=permitted,permit=1,key=1 r3=-/-,tx=idle,permit=0,key=0 \
         k1=A1,A3 rfdet=- bias=- boxfault=0"
    );
    let unknown = StatusLine::default().to_string();
    assert!(
        unknown.contains("box=?") && unknown.contains("r2=?/?") && unknown.ends_with("boxfault=?")
    );
}

fn command() -> impl Strategy<Value = HostCommand> {
    let radio = prop::sample::select(Radio::ALL.to_vec());
    let col = prop::sample::select(Col::ALL.to_vec());
    prop_oneof![
        Just(HostCommand::Hello),
        Just(HostCommand::Status),
        Just(HostCommand::ClearFault),
        (radio.clone(), col.clone(), col).prop_map(|(radio, tx, rx)| HostCommand::Route {
            radio,
            route: Route { tx, rx }
        }),
        (
            prop::sample::select(vec![Radio::R2, Radio::R3]),
            any::<bool>()
        )
            .prop_map(|(radio, on)| HostCommand::Tx { radio, on }),
        (radio, any::<bool>()).prop_map(|(radio, on)| HostCommand::Key { radio, on }),
        (0u8..32).prop_map(|b| HostCommand::Bias(ColMask::from_bits(b).unwrap())),
        any::<bool>().prop_map(HostCommand::Stop),
        any::<bool>().prop_map(HostCommand::Events),
        (KEEP_ALIVE_MIN_S..=KEEP_ALIVE_MAX_S).prop_map(HostCommand::KeepAlive),
        prop::sample::select(vec![PageSel::Flow, PageSel::Cards, PageSel::Auto])
            .prop_map(HostCommand::Page),
    ]
}

proptest! {
    /// What a host tool writes, the shack reads back the same.
    #[test]
    fn command_round_trip(cmd in command()) {
        let line = cmd.to_string();
        prop_assert!(line.len() <= MAX_LINE);
        prop_assert_eq!(parse(&line), Ok(cmd));
    }

    #[test]
    fn any_text_no_panic(s in "\\PC{0,200}") {
        let _ = parse(&s);
    }
}
