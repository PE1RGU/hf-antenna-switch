//! Terminal UI for the simulated shack interface: macOS, Linux and Windows.
//!
//! - Left: the display as the firmware draws it. Full resolution in terminals with an
//!   image protocol (iTerm2, kitty, WezTerm, Windows Terminal: Sixel); coloured
//!   half-blocks elsewhere (macOS Terminal).
//! - Right: the outside world (F-keys) and the board signals.
//! - Bottom: host traffic and a command line. Host commands go to the USB port of the
//!   simulated shack; `:` commands go to the outside world.
//! - TCP: a host tool can connect to 127.0.0.1:<port> (one client at a time).

use crate::{ShackSim, WORLD_HELP};
use image::{DynamicImage, RgbImage};
use link_proto::{Ms, Radio};
use ratatui::Frame;
use ratatui::crossterm::event::{self, Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Paragraph};
use ratatui_image::picker::Picker;
use ratatui_image::protocol::StatefulProtocol;
use ratatui_image::{Resize, StatefulImage};
use std::collections::VecDeque;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::time::{Duration, Instant};

const LOG_LINES: usize = 200;
/// An empty host line this often while auto keep-alive is on (host-protocol.md 8).
const AUTO_ALIVE_MS: Ms = 1000;

pub struct App {
    pub sim: ShackSim,
    picker: Picker,
    image: Option<StatefulProtocol>,
    last_screen: Vec<u16>,
    pub input: String,
    log: VecDeque<(Style, String)>,
    seen_lines: usize,
    tcp: Option<TcpListener>,
    tcp_port: Option<u16>,
    client: Option<TcpStream>,
    /// The TUI sends an empty host line every second, so typing by hand does not trip
    /// the 2 s keep-alive. F10 switches it off to test the time-out.
    pub auto_alive: bool,
    last_alive: Ms,
    shots: u32,
    start: Instant,
}

impl App {
    pub fn new(sim: ShackSim, picker: Picker, tcp_port: Option<u16>) -> Self {
        let tcp = tcp_port.and_then(|p| {
            let l = TcpListener::bind(("127.0.0.1", p)).ok()?;
            l.set_nonblocking(true).ok()?;
            Some(l)
        });
        let mut app = App {
            sim,
            picker,
            image: None,
            last_screen: Vec::new(),
            input: String::new(),
            log: VecDeque::new(),
            seen_lines: 0,
            tcp_port: tcp.as_ref().and(tcp_port),
            tcp,
            client: None,
            auto_alive: true,
            last_alive: 0,
            shots: 0,
            start: Instant::now(),
        };
        let note = match (tcp_port, app.tcp_port) {
            (Some(p), Some(_)) => format!("host tools: connect to 127.0.0.1:{p}"),
            (Some(p), None) => format!("TCP port {p} not free: no TCP host port"),
            _ => "no TCP host port".into(),
        };
        app.note(&note);
        app
    }

    fn note(&mut self, text: &str) {
        self.push_log(Style::new().fg(Color::DarkGray), format!("· {text}"));
    }

    fn push_log(&mut self, style: Style, text: String) {
        if self.log.len() == LOG_LINES {
            self.log.pop_front();
        }
        self.log.push_back((style, text));
    }

    fn send_host(&mut self, line: &str) {
        self.sim.board.borrow_mut().host_send(&format!("{line}\n"));
    }

    /// Simulated time follows the wall clock.
    pub fn step_realtime(&mut self) {
        let target = self.start.elapsed().as_millis() as Ms;
        let ms = target.saturating_sub(self.sim.now());
        self.advance(ms);
    }

    /// Run `ms` of simulated time, with TCP and keep-alive handling.
    pub fn advance(&mut self, ms: Ms) {
        self.tcp_in();
        for _ in 0..ms {
            self.sim.step();
            if self.auto_alive && self.sim.now().saturating_sub(self.last_alive) >= AUTO_ALIVE_MS {
                self.last_alive = self.sim.now();
                self.send_host("");
            }
        }
        self.host_out();
    }

    fn tcp_in(&mut self) {
        if let Some(l) = &self.tcp
            && let Ok((c, addr)) = l.accept()
        {
            let _ = c.set_nonblocking(true);
            self.client = Some(c);
            self.note(&format!("host tool connected from {addr}"));
        }
        let mut buf = [0u8; 512];
        let mut closed = false;
        let mut text = String::new();
        if let Some(c) = &mut self.client {
            match c.read(&mut buf) {
                Ok(0) => closed = true,
                Ok(n) => text = String::from_utf8_lossy(&buf[..n]).into_owned(),
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(_) => closed = true,
            }
        }
        if closed {
            self.client = None;
            self.note("host tool disconnected");
        }
        if !text.is_empty() {
            for l in text.lines().filter(|l| !l.trim().is_empty()) {
                self.push_log(Style::new().fg(Color::Cyan), format!("tcp> {}", l.trim()));
            }
            self.sim.board.borrow_mut().host_send(&text);
        }
    }

    fn host_out(&mut self) {
        while self.seen_lines < self.sim.host_lines.len() {
            let line = self.sim.host_lines[self.seen_lines].1.clone();
            self.seen_lines += 1;
            if let Some(c) = &mut self.client
                && c.write_all(format!("{line}\r\n").as_bytes()).is_err()
            {
                self.client = None;
            }
            let style = match line.chars().next() {
                Some('o') => Style::new().fg(Color::Green),
                Some('e') => Style::new().fg(Color::Red),
                Some('!') => Style::new().fg(Color::Yellow),
                _ => Style::new().fg(Color::DarkGray),
            };
            self.push_log(style, line);
        }
    }

    /// Handle one key. Returns false to quit.
    pub fn key(&mut self, k: KeyEvent) -> bool {
        if k.kind != KeyEventKind::Press {
            return true;
        }
        let ctrl = k.modifiers.contains(KeyModifiers::CONTROL);
        match k.code {
            KeyCode::Char('c' | 'q') if ctrl => return false,
            KeyCode::F(1) => self.world("reset"),
            KeyCode::F(2) => self.toggle_world("kill", self.env().kill_pressed),
            KeyCode::F(3) => self.toggle_world("cable", self.env().cable_ok),
            KeyCode::F(4) => self.toggle_world("power", self.env().power),
            KeyCode::F(n @ 5..=7) => {
                let i = (n - 5) as usize;
                let on = self.env().radio_tx[i];
                self.world(&format!(
                    "radio R{} {}",
                    i + 1,
                    if on { "off" } else { "on" }
                ));
            }
            KeyCode::F(8) => {
                let m = self.sim.boxs.mute;
                self.world(&format!("box mute {}", if m { "off" } else { "on" }));
            }
            KeyCode::F(9) => {
                self.shots += 1;
                self.world(&format!("shot shack-display-{}.png", self.shots));
            }
            KeyCode::F(10) => {
                self.auto_alive = !self.auto_alive;
                let s = if self.auto_alive { "on" } else { "off" };
                self.note(&format!("auto keep-alive {s}"));
            }
            KeyCode::Esc => self.input.clear(),
            KeyCode::Backspace => {
                self.input.pop();
            }
            KeyCode::Enter => {
                let line = std::mem::take(&mut self.input);
                if let Some(w) = line.trim().strip_prefix(':') {
                    let w = w.to_string();
                    self.world(&w);
                } else if !line.trim().is_empty() {
                    self.push_log(Style::new().fg(Color::Cyan), format!("> {}", line.trim()));
                    self.send_host(line.trim());
                }
            }
            KeyCode::Char(c) if !ctrl && self.input.len() < 120 => self.input.push(c),
            _ => {}
        }
        true
    }

    fn env(&self) -> sim_models::shack::Env {
        self.sim.board.borrow().env()
    }

    fn toggle_world(&mut self, what: &str, now_on: bool) {
        self.world(&format!("{what} {}", if now_on { "off" } else { "on" }));
    }

    fn world(&mut self, cmd: &str) {
        match self.sim.world(cmd) {
            Ok(m) => self.note(&m),
            Err(h) => self.note(&h),
        }
    }

    // ---------------------------------------------------------------- drawing

    pub fn draw(&mut self, f: &mut Frame) {
        let [top, bottom] =
            Layout::vertical([Constraint::Min(16), Constraint::Length(12)]).areas(f.area());
        let [left, right] =
            Layout::horizontal([Constraint::Min(40), Constraint::Length(36)]).areas(top);
        self.draw_display(f, left);
        let [world, board] =
            Layout::vertical([Constraint::Length(13), Constraint::Min(8)]).areas(right);
        self.draw_world(f, world);
        self.draw_board(f, board);
        self.draw_host(f, bottom);
    }

    fn draw_display(&mut self, f: &mut Frame, area: Rect) {
        let block = Block::bordered().title(" Display 320 × 240 ");
        let inner = block.inner(area);
        f.render_widget(block, area);
        let screen = self.sim.screen();
        if screen != self.last_screen || self.image.is_none() {
            let mut img = RgbImage::new(shack_ui::WIDTH, shack_ui::HEIGHT);
            for (i, p) in screen.iter().enumerate() {
                let (x, y) = (i as u32 % shack_ui::WIDTH, i as u32 / shack_ui::WIDTH);
                let rgb = [
                    ((p >> 11) << 3) as u8,
                    (((p >> 5) & 0x3F) << 2) as u8,
                    ((p & 0x1F) << 3) as u8,
                ];
                img.put_pixel(x, y, image::Rgb(rgb));
            }
            self.image = Some(
                self.picker
                    .new_resize_protocol(DynamicImage::ImageRgb8(img)),
            );
            self.last_screen = screen;
        }
        if let Some(p) = &mut self.image {
            let widget = StatefulImage::default()
                .resize(Resize::Scale(Some(image::imageops::FilterType::Triangle)));
            f.render_stateful_widget(widget, inner, p);
        }
    }

    fn draw_world(&self, f: &mut Frame, area: Rect) {
        let e = self.env();
        let state = |on: bool, yes: &'static str, no: &'static str, bad: bool| {
            let c = if on == bad { Color::Red } else { Color::Green };
            Span::styled(if on { yes } else { no }, Style::new().fg(c))
        };
        let key = |k: &'static str| Span::styled(format!("{k:<4}"), Style::new().fg(Color::Cyan));
        let row = |k, label: &'static str, s: Span<'static>| {
            Line::from(vec![key(k), Span::raw(format!("{label:<14}")), s])
        };
        let lines = vec![
            row(
                "F1",
                "RESET",
                Span::styled("press", Style::new().fg(Color::DarkGray)),
            ),
            row(
                "F2",
                "KILL switch",
                state(e.kill_pressed, "pressed", "released", true),
            ),
            row("F3", "Cat6 cable", state(e.cable_ok, "ok", "cut", false)),
            row("F4", "13.8 V", state(e.power, "on", "off", false)),
            row("F5", "R1 TX sense", state(e.radio_tx[0], "TX", "rx", true)),
            row("F6", "R2 TX sense", state(e.radio_tx[1], "TX", "rx", true)),
            row("F7", "R3 TX sense", state(e.radio_tx[2], "TX", "rx", true)),
            row(
                "F8",
                "Box",
                state(!self.sim.boxs.mute, "answering", "silent", false),
            ),
            row(
                "F9",
                "Screenshot",
                Span::styled("png", Style::new().fg(Color::DarkGray)),
            ),
            row(
                "F10",
                "Auto alive",
                state(self.auto_alive, "on", "off", false),
            ),
            Line::styled("Ctrl-C quit · Esc clear", Style::new().fg(Color::DarkGray)),
        ];
        f.render_widget(
            Paragraph::new(lines).block(Block::bordered().title(" Outside world ")),
            area,
        );
    }

    fn draw_board(&self, f: &mut Frame, area: Rect) {
        let s = self.sim.board.borrow().signals();
        let dot = |good: bool| {
            Span::styled(
                "● ",
                Style::new().fg(if good { Color::Green } else { Color::Red }),
            )
        };
        let item = |good: bool, text: String| vec![dot(good), Span::raw(text)];
        let mut lines = vec![
            Line::from(item(
                s.safe_current,
                format!(
                    "SAFE loop  {}",
                    if s.safe_current { "current" } else { "open" }
                ),
            )),
            Line::from(item(
                !s.latched,
                format!("Latch      {}", if s.latched { "LATCHED" } else { "clear" }),
            )),
            Line::from(item(
                !s.fault,
                format!("Fault      {}", if s.fault { "FAULT" } else { "clear" }),
            )),
            Line::from(item(s.tx_en, format!("TX_EN      {}", s.tx_en as u8))),
        ];
        for r in Radio::ALL {
            let i = r.index();
            let k0 = r != Radio::R1 && self.sim.boxs.k0(r);
            let rt = self.sim.boxs.routes[i];
            lines.push(Line::from(vec![
                dot(!s.inhibit[i]),
                Span::raw(format!(
                    "R{} {} key {} {}/{}{}",
                    i + 1,
                    if s.inhibit[i] { "inhib" } else { "free " },
                    s.key_contact[i] as u8,
                    host_proto::col_name(rt.tx),
                    host_proto::col_name(rt.rx),
                    if k0 { " K0" } else { "" }
                )),
            ]));
        }
        f.render_widget(
            Paragraph::new(lines).block(Block::bordered().title(" Board ")),
            area,
        );
    }

    fn draw_host(&self, f: &mut Frame, area: Rect) {
        let title = match self.tcp_port {
            Some(p) => format!(
                " Host (USB) · tcp 127.0.0.1:{p}{} ",
                if self.client.is_some() {
                    " · connected"
                } else {
                    ""
                }
            ),
            None => " Host (USB) ".into(),
        };
        let block = Block::bordered().title(title);
        let inner = block.inner(area);
        f.render_widget(block, area);
        let [log, input] =
            Layout::vertical([Constraint::Min(1), Constraint::Length(1)]).areas(inner);
        let n = log.height as usize;
        let lines: Vec<Line> = self
            .log
            .iter()
            .skip(self.log.len().saturating_sub(n))
            .map(|(st, t)| Line::styled(t.clone(), *st))
            .collect();
        f.render_widget(Paragraph::new(lines), log);
        let prompt = Line::from(vec![
            Span::styled(
                "> ",
                Style::new().fg(Color::Cyan).add_modifier(Modifier::BOLD),
            ),
            Span::raw(self.input.clone()),
            Span::styled("█", Style::new().fg(Color::DarkGray)),
            Span::styled(
                if self.input.is_empty() {
                    "  host command, or :outside world command (:reset)"
                } else {
                    ""
                },
                Style::new().fg(Color::DarkGray),
            ),
        ]);
        f.render_widget(Paragraph::new(prompt), input);
    }
}

pub struct Options {
    pub state_file: PathBuf,
    pub tcp_port: Option<u16>,
}

/// Run the terminal UI until Ctrl-C.
pub fn run(opts: Options) -> std::io::Result<()> {
    let sim = ShackSim::use_state_file(&opts.state_file);
    let mut terminal = ratatui::init();
    let picker = Picker::from_query_stdio().unwrap_or_else(|_| Picker::halfblocks());
    let mut app = App::new(sim, picker, opts.tcp_port);
    app.note(&format!("stored settings: {}", opts.state_file.display()));
    app.note(WORLD_HELP);
    let result = (|| -> std::io::Result<()> {
        loop {
            app.step_realtime();
            terminal.draw(|f| app.draw(f))?;
            if event::poll(Duration::from_millis(30))?
                && let Event::Key(k) = event::read()?
                && !app.key(k)
            {
                return Ok(());
            }
        }
    })();
    ratatui::restore();
    result
}
