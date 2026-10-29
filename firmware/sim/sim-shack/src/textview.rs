//! Text view of the display for terminals without image support (macOS Terminal,
//! the old Windows console). Same state and words as the pixel pages (shack-ui),
//! drawn with box and line characters and the 16 basic colours.

use link_proto::Col;
use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use ratatui::style::{Color, Modifier, Style};
use ratatui::widgets::{Block, BorderType, Widget};
use shack_ui::wording::{self, RADIO_LABELS};
use shack_ui::{ANTENNA_LABELS, Page, RadioMode, UiState, Warning, band_name};

/// Smallest area for the full layout: width in terminal cells.
pub const MIN_WIDTH: u16 = 56;
/// Smallest area for the full layout: height in terminal rows.
pub const MIN_HEIGHT: u16 = 23;

const TX: Color = Color::LightRed;
const RX: Color = Color::LightGreen;
const AMBER: Color = Color::Yellow;
const DIM: Color = Color::DarkGray;
const SEC: Color = Color::Gray;

/// A ratatui widget that draws one display page as text.
///
/// Page B (flow) shows radios on the left, antennas on the right, and routes as
/// lines between them. Page C shows one card per radio. The Safe stop page shows
/// the cause and the steps to clear it. A smaller area than [`MIN_WIDTH`] x
/// [`MIN_HEIGHT`] shows a short message instead.
pub struct TextView<'a> {
    /// The display state from the firmware (`Shack::ui_state`).
    pub state: &'a UiState,
    /// The page to draw (`Shack::shown_page`).
    pub page: Page,
}

/// Writes clipped to the area, in coordinates relative to it.
struct Pen<'a> {
    buf: &'a mut Buffer,
    area: Rect,
}

impl Pen<'_> {
    fn put(&mut self, x: u16, y: u16, s: &str, st: Style) {
        if y >= self.area.height || x >= self.area.width {
            return;
        }
        let w = (self.area.width - x) as usize;
        self.buf
            .set_stringn(self.area.x + x, self.area.y + y, s, w, st);
    }

    fn rect(&self, x: u16, y: u16, w: u16, h: u16) -> Rect {
        let r = Rect::new(self.area.x + x, self.area.y + y, w, h);
        r.intersection(self.area)
    }

    fn boxed(&mut self, x: u16, y: u16, w: u16, h: u16, st: Style) {
        let r = self.rect(x, y, w, h);
        Block::bordered()
            .border_type(BorderType::Rounded)
            .border_style(st)
            .render(r, self.buf);
    }

    /// A line segment: where it crosses another line, draw a crossing.
    fn line(&mut self, x: u16, y: u16, ch: &str, st: Style) {
        if y >= self.area.height || x >= self.area.width {
            return;
        }
        let under = self.buf[(self.area.x + x, self.area.y + y)].symbol();
        let vertical = |c: &str| matches!(c, "│" | "┃");
        let horizontal = |c: &str| matches!(c, "─" | "━");
        let ch = if (vertical(under) && horizontal(ch)) || (horizontal(under) && vertical(ch)) {
            if ch == "━" || ch == "┃" {
                "╋"
            } else {
                "┼"
            }
        } else {
            ch
        };
        self.put(x, y, ch, st);
    }

    /// Route: dot, horizontal, turn, vertical, turn, horizontal, arrow head.
    fn route(&mut self, from: (u16, u16), to: (u16, u16), bus: u16, st: Style, heavy: bool) {
        let (h, v) = if heavy {
            ("━", "┃")
        } else {
            ("─", "│")
        };
        let (down_in, down_out, up_in, up_out) = if heavy {
            ("┓", "┗", "┛", "┏")
        } else {
            ("╮", "╰", "╯", "╭")
        };
        let (x0, y0) = from;
        let (x1, y1) = to;
        if y0 == y1 {
            for x in x0..x1 {
                self.line(x, y0, h, st);
            }
        } else {
            for x in x0..bus {
                self.line(x, y0, h, st);
            }
            let down = y1 > y0;
            self.put(bus, y0, if down { down_in } else { up_in }, st);
            let (a, b) = if down { (y0 + 1, y1) } else { (y1 + 1, y0) };
            for y in a..b {
                self.line(bus, y, v, st);
            }
            self.put(bus, y1, if down { down_out } else { up_out }, st);
            for x in bus + 1..x1 {
                self.line(x, y1, h, st);
            }
        }
        self.put(x0, y0, "●", st);
        self.put(x1.saturating_sub(1), y1, "▶", st);
    }
}

fn col_index(c: Col) -> Option<usize> {
    (c != Col::None).then(|| c as usize - 1)
}

fn mode_style(m: RadioMode) -> (Style, &'static str) {
    match m {
        RadioMode::Tx => (Style::new().fg(TX).add_modifier(Modifier::BOLD), "TX"),
        RadioMode::Rx => (Style::new().fg(RX), "RX"),
        RadioMode::Off => (Style::new().fg(DIM), "off"),
    }
}

impl Widget for TextView<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let mut p = Pen { buf, area };
        let s = self.state;
        if area.width < MIN_WIDTH || area.height < MIN_HEIGHT {
            p.put(
                0,
                0,
                "Display: make the window larger, or Tab for pixels",
                Style::new().fg(SEC),
            );
            return;
        }
        match self.page {
            Page::Stop => stop(&mut p, s),
            page => {
                top_bar(&mut p, s);
                if page == Page::Cards {
                    cards(&mut p, s);
                } else {
                    flow(&mut p, s);
                }
                if let Some(w) = wording::warning_line(s) {
                    let y = area.height - 1;
                    p.put(
                        0,
                        y,
                        " ! ",
                        Style::new()
                            .fg(Color::Black)
                            .bg(AMBER)
                            .add_modifier(Modifier::BOLD),
                    );
                    p.put(4, y, &w, Style::new().fg(AMBER));
                }
            }
        }
    }
}

fn top_bar(p: &mut Pen, s: &UiState) {
    let dot = |ok: Option<bool>| {
        Style::new().fg(match ok {
            Some(true) => RX,
            Some(false) => TX,
            None => DIM,
        })
    };
    let box_c = match s.box_ready {
        Some(true) => Style::new().fg(RX),
        Some(false) => Style::new().fg(AMBER),
        None => Style::new().fg(DIM),
    };
    p.put(0, 0, "●", dot(Some(s.safe_ok)));
    p.put(2, 0, "SAFE", Style::new().fg(SEC));
    p.put(8, 0, "●", dot(Some(s.link_up)));
    p.put(10, 0, "LINK", Style::new().fg(SEC));
    p.put(16, 0, "●", box_c);
    p.put(18, 0, "BOX", Style::new().fg(SEC));
    let band = s.band.and_then(band_name).unwrap_or("--");
    let w = p.area.width;
    p.put(w - 9, 0, "R1", Style::new().fg(SEC));
    p.put(w - 6, 0, band, Style::new().add_modifier(Modifier::BOLD));
}

// ---------------------------------------------------------------- B: flow

const RW: u16 = 18;
const AW: u16 = 20;
const RADIO_Y: [u16; 3] = [2, 9, 16];

/// Antenna boxes are 4 rows, like the radio boxes: TX enters the upper inner row,
/// RX the lower one, so a TX and an RX route to one antenna stay apart.
fn ant_y(i: usize) -> u16 {
    2 + i as u16 * 4
}

fn flow(p: &mut Pen, s: &UiState) {
    let ax = p.area.width - AW;
    for (i, r) in s.radios.iter().enumerate() {
        let y = RADIO_Y[i];
        let (st, label) = mode_style(r.mode);
        p.boxed(0, y, RW, 4, st);
        let on = r.mode != shack_ui::RadioMode::Off;
        p.put(
            2,
            y + 1,
            RADIO_LABELS[i],
            Style::new()
                .add_modifier(Modifier::BOLD)
                .fg(if on { Color::White } else { DIM }),
        );
        if on {
            p.put(RW - 2 - label.len() as u16, y + 1, label, st);
        }
        let sub = if on { s.radio_names[i].as_str() } else { "off" };
        p.put(2, y + 2, sub, Style::new().fg(if on { SEC } else { DIM }));
    }

    let mut used = [false; 5];
    for r in s.radios.iter().filter(|r| r.mode != RadioMode::Off) {
        for c in [r.route.tx, r.route.rx] {
            if let Some(i) = col_index(c) {
                used[i] = true;
            }
        }
    }
    for (i, label) in ANTENNA_LABELS.iter().enumerate() {
        let col = Col::ALL[i + 1];
        let y = ant_y(i);
        let bias = s.warnings.contains(&Warning::BiasFault(col));
        let border = if bias {
            Style::new().fg(AMBER)
        } else if used[i] {
            Style::new().fg(SEC)
        } else {
            Style::new().fg(DIM)
        };
        p.boxed(ax, y, AW, 4, border);
        let text = if used[i] { Color::White } else { DIM };
        p.put(
            ax + 2,
            y + 1,
            label,
            Style::new().fg(text).add_modifier(Modifier::BOLD),
        );
        p.put(
            ax + 6,
            y + 1,
            s.antenna_names[i].as_str(),
            Style::new().fg(if used[i] { SEC } else { DIM }),
        );
        if s.rx_only.contains(col) {
            p.put(ax + AW - 4, y + 2, "rx", Style::new().fg(RX));
        }
    }

    // Routes: RX first, then idle TX, then active TX on top.
    // Column of the vertical part. TX starts one row above RX and ends one row above
    // it. Going down, RX turns first (nearer the radio); going up, TX turns first.
    // So the two routes of one radio never touch.
    let bus = |radio: usize, rx: bool, from: u16, to: u16| {
        let first = (to > from) == rx;
        RW + 2 + radio as u16 * 5 + if first { 0 } else { 2 }
    };
    for pass in 0..3 {
        for (i, r) in s.radios.iter().enumerate() {
            if r.mode == RadioMode::Off {
                continue;
            }
            let y = RADIO_Y[i];
            match pass {
                0 => {
                    if let Some(a) = col_index(r.route.rx) {
                        p.route(
                            (RW, y + 2),
                            (ax, ant_y(a) + 2),
                            bus(i, true, y + 2, ant_y(a) + 2),
                            Style::new().fg(RX),
                            false,
                        );
                    }
                }
                1 if r.mode != RadioMode::Tx => {
                    if let Some(a) = col_index(r.route.tx) {
                        let st = if r.permit {
                            Style::new().fg(TX)
                        } else {
                            Style::new().fg(TX).add_modifier(Modifier::DIM)
                        };
                        p.route(
                            (RW, y + 1),
                            (ax, ant_y(a) + 1),
                            bus(i, false, y + 1, ant_y(a) + 1),
                            st,
                            false,
                        );
                    }
                }
                2 if r.mode == RadioMode::Tx => {
                    if let Some(a) = col_index(r.route.tx) {
                        let st = Style::new().fg(TX).add_modifier(Modifier::BOLD);
                        p.route(
                            (RW, y + 1),
                            (ax, ant_y(a) + 1),
                            bus(i, false, y + 1, ant_y(a) + 1),
                            st,
                            true,
                        );
                    }
                }
                _ => {}
            }
        }
    }
}

// ---------------------------------------------------------------- C: cards

fn cards(p: &mut Pen, s: &UiState) {
    let w = p.area.width;
    for (i, r) in s.radios.iter().enumerate() {
        let y = 2 + i as u16 * 5;
        let on = r.mode != RadioMode::Off;
        let (_, label) = mode_style(r.mode);
        p.boxed(
            0,
            y,
            w,
            5,
            if on {
                Style::new().fg(SEC)
            } else {
                Style::new().fg(DIM)
            },
        );
        let chip = format!(" {label:^5} ");
        let chip_st = match r.mode {
            RadioMode::Tx => Style::new()
                .fg(Color::White)
                .bg(Color::Red)
                .add_modifier(Modifier::BOLD),
            RadioMode::Rx => Style::new().fg(Color::Black).bg(Color::Green),
            RadioMode::Off => Style::new().fg(DIM),
        };
        p.put(2, y + 2, &chip, chip_st);
        p.put(
            12,
            y + 1,
            RADIO_LABELS[i],
            Style::new()
                .add_modifier(Modifier::BOLD)
                .fg(if on { Color::White } else { DIM }),
        );
        p.put(16, y + 1, s.radio_names[i].as_str(), Style::new().fg(SEC));
        for (row, is_tx) in [(2u16, true), (3, false)] {
            let c = if !on {
                Col::None
            } else if is_tx {
                r.route.tx
            } else {
                r.route.rx
            };
            let (arrow, name, col_c) = if is_tx {
                ("▶", "TX", TX)
            } else {
                ("◀", "RX", RX)
            };
            let has = col_index(c);
            p.put(
                12,
                y + row,
                arrow,
                Style::new().fg(if has.is_some() { col_c } else { DIM }),
            );
            p.put(14, y + row, name, Style::new().fg(SEC));
            match has {
                Some(a) => {
                    let warn = s.warnings.contains(&Warning::BiasFault(c));
                    let st = Style::new().fg(if warn { AMBER } else { Color::White });
                    p.put(
                        18,
                        y + row,
                        ANTENNA_LABELS[a],
                        st.add_modifier(Modifier::BOLD),
                    );
                    p.put(
                        22,
                        y + row,
                        s.antenna_names[a].as_str(),
                        Style::new().fg(if warn { AMBER } else { SEC }),
                    );
                }
                None => p.put(18, y + row, "-", Style::new().fg(DIM)),
            }
        }
        if i == 0
            && on
            && let Some(b) = s.band.and_then(band_name)
        {
            p.put(
                w - 2 - b.len() as u16,
                y + 2,
                b,
                Style::new().add_modifier(Modifier::BOLD),
            );
        }
    }
}

// ---------------------------------------------------------------- Safe stop

fn stop(p: &mut Pen, s: &UiState) {
    let (title, sub) = wording::stop_title(s);
    let c = if s.stop.is_some() { TX } else { AMBER };
    p.put(
        0,
        0,
        "  STOP  ",
        Style::new()
            .fg(Color::White)
            .bg(if s.stop.is_some() {
                Color::Red
            } else {
                Color::Yellow
            })
            .add_modifier(Modifier::BOLD),
    );
    p.put(
        10,
        0,
        &title.to_uppercase(),
        Style::new().fg(c).add_modifier(Modifier::BOLD),
    );
    p.put(10, 1, sub, Style::new().fg(SEC));

    let w = p.area.width;
    p.boxed(0, 3, w, 6, Style::new().fg(DIM));
    let rows = [
        ("Cause", wording::cause(s), AMBER),
        (
            "SAFE loop",
            if s.safe_ok { "closed" } else { "open" },
            if s.safe_ok { RX } else { TX },
        ),
        (
            "Latch",
            if s.latched { "latched" } else { "clear" },
            if s.latched { TX } else { RX },
        ),
        (
            "Box link",
            if s.link_up { "up" } else { "down" },
            if s.link_up { RX } else { TX },
        ),
    ];
    for (i, (k, v, col)) in rows.iter().enumerate() {
        let y = 4 + i as u16;
        p.put(2, y, k, Style::new().fg(SEC));
        p.put(w - 4 - v.len() as u16, y, v, Style::new().fg(Color::White));
        p.put(w - 3, y, "●", Style::new().fg(*col));
    }

    let steps = wording::steps(s);
    p.boxed(0, 10, w, steps.len() as u16 + 2, Style::new().fg(AMBER));
    for (i, st) in steps.iter().enumerate() {
        let y = 11 + i as u16;
        p.put(
            2,
            y,
            &format!("{}.", i + 1),
            Style::new().fg(AMBER).add_modifier(Modifier::BOLD),
        );
        p.put(
            5,
            y,
            st,
            Style::new().fg(AMBER).add_modifier(Modifier::BOLD),
        );
    }
}
