//! Terminal UI without a terminal: ratatui TestBackend, half-block display, keys, TCP host.

use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyEventState, KeyModifiers};
use ratatui_image::picker::Picker;
use sim_shack::ShackSim;
use sim_shack::tui::App;
use std::io::{BufRead, BufReader, Write};

fn press(app: &mut App, code: KeyCode) -> bool {
    app.key(KeyEvent {
        code,
        modifiers: KeyModifiers::NONE,
        kind: KeyEventKind::Press,
        state: KeyEventState::NONE,
    })
}

fn type_line(app: &mut App, s: &str) {
    for c in s.chars() {
        press(app, KeyCode::Char(c));
    }
    press(app, KeyCode::Enter);
}

fn screen_text(term: &Terminal<TestBackend>) -> String {
    let buf = term.backend().buffer();
    (0..buf.area.height)
        .map(|y| {
            (0..buf.area.width)
                .map(|x| buf[(x, y)].symbol().to_string())
                .collect::<String>()
                + "\n"
        })
        .collect()
}

fn app() -> App {
    App::new(ShackSim::new(), Picker::halfblocks(), None)
}

#[test]
fn draws_display_world_board_and_host() {
    let mut a = app();
    a.advance(800);
    let mut term = Terminal::new(TestBackend::new(120, 40)).unwrap();
    term.draw(|f| a.draw(f)).unwrap();
    let t = screen_text(&term);
    for s in [
        "Display 320 x 240",
        "Outside world",
        "Board",
        "Host (USB)",
        "F2  KILL switch",
        "SAFE loop",
    ] {
        assert!(t.contains(s), "missing {s:?}\n{t}");
    }
    assert!(
        t.contains('▀') || t.contains('▄'),
        "display drawn as half-blocks"
    );
}

#[test]
fn keys_drive_the_world_and_host() {
    let mut a = app();
    a.advance(600);
    assert!(a.sim.board.borrow().signals().latched);
    press(&mut a, KeyCode::F(1));
    a.advance(50);
    assert!(!a.sim.board.borrow().signals().latched, "F1 pressed RESET");
    press(&mut a, KeyCode::F(2));
    a.advance(50);
    assert!(a.sim.board.borrow().env().kill_pressed, "F2 pressed KILL");
    type_line(&mut a, ":kill off");
    a.advance(50);
    assert!(!a.sim.board.borrow().env().kill_pressed, ":kill off");
    type_line(&mut a, "status");
    a.advance(50);
    assert!(
        a.sim
            .host_lines
            .iter()
            .any(|(_, l)| l.starts_with("ok link=up"))
    );
    assert!(press(&mut a, KeyCode::F(10)));
    assert!(!a.auto_alive);
    let quit = a.key(KeyEvent::new(KeyCode::Char('c'), KeyModifiers::CONTROL));
    assert!(!quit, "Ctrl-C quits");
}

#[test]
fn auto_keep_alive_holds_tx_while_typing_slowly() {
    let mut a = app();
    a.advance(400);
    press(&mut a, KeyCode::F(1));
    type_line(&mut a, "route R2 A1 A1");
    a.advance(300);
    type_line(&mut a, "tx R2 on");
    a.advance(5000);
    assert!(!a.sim.host_lines.iter().any(|(_, l)| l == "!host timeout"));
    assert!(a.sim.shack.permit(link_proto::Radio::R2));
}

#[test]
fn tcp_host_tool() {
    let port = 47_311;
    let mut a = App::new(ShackSim::new(), Picker::halfblocks(), Some(port));
    a.advance(400);
    let mut c = std::net::TcpStream::connect(("127.0.0.1", port)).unwrap();
    a.advance(10);
    c.write_all(b"hello\n").unwrap();
    std::thread::sleep(std::time::Duration::from_millis(20));
    a.advance(50);
    c.set_read_timeout(Some(std::time::Duration::from_secs(2)))
        .unwrap();
    let mut r = BufReader::new(c);
    let mut line = String::new();
    loop {
        line.clear();
        r.read_line(&mut line).unwrap();
        if line.starts_with("ok") {
            break;
        }
    }
    assert_eq!(line.trim_end(), "ok shack fw 0.1.0 proto 1");
}

#[test]
fn help_for_both_command_sets() {
    let mut a = app();
    a.advance(600);
    type_line(&mut a, "help");
    a.advance(50);
    let host: Vec<_> = a.sim.host_lines.iter().map(|(_, l)| l.as_str()).collect();
    assert!(
        host.iter().any(|l| l.starts_with("# route R1-R3")),
        "{host:?}"
    );
    assert!(host.iter().any(|l| l.starts_with("# help | ?")));
    let i = host.iter().rposition(|l| l.starts_with('#')).unwrap();
    assert_eq!(host.get(i + 1).copied(), Some("ok"), "help ends with ok");
    type_line(&mut a, "?");
    a.advance(50);
    assert!(a.sim.world("?").unwrap().contains("radio R1-R3 on|off"));
    // The help is longer than the log panel: PgUp shows the top of it.
    let mut term = Terminal::new(TestBackend::new(120, 40)).unwrap();
    press(&mut a, KeyCode::PageUp);
    press(&mut a, KeyCode::PageUp);
    term.draw(|f| a.draw(f)).unwrap();
    assert!(
        screen_text(&term).contains("# hello"),
        "scrolled back to the start of the help"
    );
}
