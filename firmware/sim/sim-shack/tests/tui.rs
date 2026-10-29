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

fn draw(a: &mut App) -> String {
    let mut term = Terminal::new(TestBackend::new(120, 40)).unwrap();
    term.draw(|f| a.draw(f)).unwrap();
    screen_text(&term)
}

#[test]
fn draws_display_world_board_and_host() {
    let mut a = app();
    a.advance(800);
    assert!(a.text_view, "no image protocol: text view first");
    let t = draw(&mut a);
    for s in [
        "Display (text view",
        "SAFE STOP",
        "Press RESET",
        "Outside world",
        "Board",
        "Host (USB)",
        "F2  KILL switch",
        "SAFE loop",
    ] {
        assert!(t.contains(s), "missing {s:?}\n{t}");
    }
    // Tab: the pixels, as half-blocks here.
    press(&mut a, KeyCode::Tab);
    let t = draw(&mut a);
    assert!(t.contains("Display 320 x 240"));
    assert!(
        t.contains('▀') || t.contains('▄'),
        "display drawn as half-blocks"
    );
}

/// R1 transmits on A1 and receives on A2; R2 receives on A3 (named Hexbeam).
fn station(a: &mut App) {
    a.advance(600);
    press(a, KeyCode::F(1));
    for l in ["route R1 A1 A2", "route R2 - A3", "name A3 Hexbeam"] {
        type_line(a, l);
        a.advance(100);
    }
    type_line(a, ":radio R1 on");
    a.advance(200);
}

#[test]
fn text_view_flow_page() {
    let mut a = app();
    station(&mut a);
    let t = draw(&mut a);
    for s in [
        "R1", "FT-710", "TX", "G5RV", "Loop", "Hexbeam", "rx", "━", "▶", "─",
    ] {
        assert!(t.contains(s), "missing {s:?}\n{t}");
    }
}

#[test]
fn text_view_cards_and_stop() {
    let mut a = app();
    station(&mut a);
    type_line(&mut a, "page c");
    a.advance(100);
    let t = draw(&mut a);
    for s in ["▶", "◀", "A1", "G5RV", "A3", "Hexbeam", "WSPR"] {
        assert!(t.contains(s), "missing {s:?}\n{t}");
    }
    press(&mut a, KeyCode::F(2));
    a.advance(100);
    let t = draw(&mut a);
    for s in [
        "SAFE STOP",
        "KILL switch pressed",
        "1. Release the KILL switch",
        "2. Press RESET",
    ] {
        assert!(t.contains(s), "missing {s:?}\n{t}");
    }
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

/// iTerm2 that does not report its font size: ratatui-image gives half-blocks;
/// fix_picker turns that into iTerm2 images with the font size from the window.
#[test]
fn iterm2_without_font_size_gets_images() {
    use ratatui_image::picker::ProtocolType;
    use sim_shack::tui::fix_picker;
    let p = fix_picker(Picker::halfblocks(), true, Some((148, 47, 1184, 799)));
    assert_eq!(p.protocol_type(), ProtocolType::Iterm2);
    assert_eq!((p.font_size().width, p.font_size().height), (8, 17));
    let p = fix_picker(Picker::halfblocks(), true, None);
    assert_eq!(
        p.protocol_type(),
        ProtocolType::Iterm2,
        "no window size: 8 x 16"
    );
    assert_eq!((p.font_size().width, p.font_size().height), (8, 16));
    let p = fix_picker(Picker::halfblocks(), false, Some((148, 47, 1184, 799)));
    assert_eq!(
        p.protocol_type(),
        ProtocolType::Halfblocks,
        "no iTerm2 hint: unchanged"
    );
    // A window size without pixels (0) is not used.
    let p = fix_picker(Picker::halfblocks(), true, Some((148, 47, 0, 0)));
    assert_eq!((p.font_size().width, p.font_size().height), (8, 16));
    // iTerm2 images: the UI starts with the pixels.
    let a = App::new(ShackSim::new(), p, None);
    assert!(!a.text_view);
}

#[test]
fn iterm_hint_trusts_term_program_first() {
    use sim_shack::tui::iterm_hint_from;
    assert!(iterm_hint_from(Some("iTerm.app"), Some("iTerm2")));
    assert!(iterm_hint_from(Some("iTerm.app"), None));
    assert!(
        !iterm_hint_from(Some("Apple_Terminal"), Some("iTerm2")),
        "leaked LC_TERMINAL"
    );
    assert!(iterm_hint_from(None, Some("iTerm2")), "over ssh");
    assert!(!iterm_hint_from(None, None));
}

/// iTerm2 answers the kitty query (`--probe`: "query = Kitty, font 7x15"), but kitty
/// images stay empty there: use iTerm2 images. The font size comes from the window in
/// screen pixels (Retina: 2674 x 1590 px for 191 x 53 cells gives 14 x 30).
#[test]
fn iterm2_answering_kitty_gets_iterm2_images() {
    use ratatui_image::picker::ProtocolType;
    use sim_shack::tui::fix_picker;
    for proto in [ProtocolType::Kitty, ProtocolType::Sixel] {
        let mut q = Picker::halfblocks();
        q.set_protocol_type(proto);
        let p = fix_picker(q, true, Some((191, 53, 2674, 1590)));
        assert_eq!(p.protocol_type(), ProtocolType::Iterm2);
        assert_eq!(
            (p.font_size().width, p.font_size().height),
            (14, 30),
            "screen pixels"
        );
    }
    // No window size: the query's font size is kept.
    let mut q = Picker::halfblocks();
    q.set_protocol_type(ProtocolType::Kitty);
    let font = q.font_size();
    let p = fix_picker(q, true, None);
    assert_eq!(
        (p.font_size().width, p.font_size().height),
        (font.width, font.height)
    );
    // Real kitty (no iTerm2 hint) keeps kitty.
    let mut q = Picker::halfblocks();
    q.set_protocol_type(ProtocolType::Kitty);
    assert_eq!(
        fix_picker(q, false, None).protocol_type(),
        ProtocolType::Kitty
    );
}
