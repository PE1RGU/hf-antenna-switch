//! Page B (flow), page C (cards) and the Safe stop screen.

use crate::draw::{Target, dot, rect, route, rrect, text, tri};
use crate::theme::*;
use crate::{ANTENNA_LABELS, Page, RadioMode, RadioUi, UiState, Warning, band_name};
use embedded_graphics::pixelcolor::Rgb565;
use embedded_graphics::text::Alignment::{Center as C, Left as L, Right as R};
use link_proto::Col;

/// Draw the whole screen for `chosen` (Flow or Cards); Safe stop takes over when due.
pub fn render<D: Target>(d: &mut D, s: &UiState, chosen: Page) {
    let _ = d.clear(BG);
    match s.page(chosen) {
        Page::Stop => stop(d, s),
        page => {
            top_bar(d, s);
            if page == Page::Cards {
                cards(d, s);
            } else {
                flow(d, s);
            }
            toast(d, s);
        }
    }
}

use crate::wording::{self, RADIO_LABELS};

fn col_index(c: Col) -> Option<usize> {
    (c != Col::None).then(|| c as usize - 1)
}

fn bias_fault(s: &UiState, c: Col) -> bool {
    s.warnings.contains(&Warning::BiasFault(c))
}

fn top_bar<D: Target>(d: &mut D, s: &UiState) {
    let box_c = match s.box_ready {
        Some(true) => RX,
        Some(false) => AMBER,
        None => FAINT,
    };
    let items = [
        ("SAFE", if s.safe_ok { RX } else { TX }),
        ("LINK", if s.link_up { RX } else { TX }),
        ("BOX", box_c),
    ];
    for (i, (label, c)) in items.iter().enumerate() {
        let x = 12 + i as i32 * 58;
        dot(d, x, 12, 8, *c);
        text(d, &SMALL, label, x + 8, 12, SEC, BG, L);
    }
    text(d, &SMALL, "R1", 268, 12, SEC, BG, R);
    let band = s.band.and_then(band_name).unwrap_or("--");
    text(d, &TITLE, band, 310, 12, TEXT, BG, R);
}

fn toast<D: Target>(d: &mut D, s: &UiState) {
    let Some(msg) = wording::warning_line(s) else {
        return;
    };
    rrect(d, 8, 208, 304, 26, 13, AMBER_TINT);
    dot(d, 22, 221, 14, AMBER);
    text(d, &SMALL, "!", 22, 221, AMBER_TINT, AMBER, C);
    text(d, &BODY, &msg, 36, 221, AMBER, AMBER_TINT, L);
}

fn state_label(r: &RadioUi) -> (&'static str, Rgb565, Rgb565) {
    match r.mode {
        RadioMode::Tx => ("TX", TX, TEXT),
        RadioMode::Rx => ("RX", RX_TINT, RX),
        RadioMode::Off => ("OFF", CARD, FAINT),
    }
}

// ---------------------------------------------------------------- B: flow

const RADIO_Y: [i32; 3] = [28, 88, 148];
const ANT_X: i32 = 222;

fn ant_y(i: usize) -> i32 {
    28 + i as i32 * 36
}

fn flow<D: Target>(d: &mut D, s: &UiState) {
    for (i, r) in s.radios.iter().enumerate() {
        let y = RADIO_Y[i];
        let on = r.mode != RadioMode::Off;
        let surf = if on { CARD } else { CARD_DIM };
        rrect(d, 8, y, 100, 52, 10, surf);
        text(
            d,
            &BIG,
            RADIO_LABELS[i],
            18,
            y + 18,
            if on { TEXT } else { FAINT },
            surf,
            L,
        );
        let sub = if on { s.radio_names[i].as_str() } else { "off" };
        text(
            d,
            &SMALL,
            sub,
            18,
            y + 38,
            if on { SEC } else { FAINT },
            surf,
            L,
        );
        if on {
            let (label, fill, fg) = state_label(r);
            rrect(d, 62, y + 8, 38, 20, 10, fill);
            text(d, &SMALL, label, 81, y + 18, fg, fill, C);
        }
    }

    let mut used = [false; 5];
    for r in s.radios.iter().filter(|r| r.mode != RadioMode::Off) {
        for c in [r.route.tx, r.route.rx] {
            if let Some(i) = col_index(c) {
                used[i] = true;
            }
        }
    }
    for (i, (a, n)) in ANTENNA_LABELS
        .iter()
        .zip(s.antenna_names.iter().map(|n| n.as_str()))
        .enumerate()
    {
        let col = Col::ALL[i + 1];
        let surf = if used[i] { CARD } else { CARD_DIM };
        rrect(d, ANT_X, ant_y(i), 90, 30, 8, surf);
        if bias_fault(s, col) {
            rrect(d, ANT_X, ant_y(i), 4, 30, 2, AMBER);
        }
        text(
            d,
            &TITLE,
            a,
            ANT_X + 10,
            ant_y(i) + 15,
            if used[i] { TEXT } else { FAINT },
            surf,
            L,
        );
        text(
            d,
            &SMALL,
            n,
            ANT_X + 40,
            ant_y(i) + 15,
            if used[i] { SEC } else { FAINT },
            surf,
            L,
        );
        if s.rx_only.contains(col) {
            rrect(d, ANT_X + 68, ant_y(i) + 4, 18, 11, 5, RX_TINT);
            text(d, &SMALL, "rx", ANT_X + 77, ant_y(i) + 9, RX, RX_TINT, C);
        }
    }

    // Routes: RX first, then idle TX, then active TX on top.
    let bus = |radio: usize, rx: bool| 136 + (radio as i32 * 2 + rx as i32) * 12;
    for pass in 0..3 {
        for (i, r) in s.radios.iter().enumerate() {
            if r.mode == RadioMode::Off {
                continue;
            }
            let y = RADIO_Y[i];
            match pass {
                0 => {
                    if let Some(a) = col_index(r.route.rx) {
                        route(
                            d,
                            (108, y + 36),
                            (ANT_X, ant_y(a) + 19),
                            bus(i, true),
                            RX,
                            2,
                            None,
                        );
                    }
                }
                1 if r.mode != RadioMode::Tx => {
                    if let Some(a) = col_index(r.route.tx) {
                        let w = if r.permit { 3 } else { 1 };
                        route(
                            d,
                            (108, y + 18),
                            (ANT_X, ant_y(a) + 11),
                            bus(i, false),
                            TX_IDLE,
                            w,
                            None,
                        );
                    }
                }
                2 if r.mode == RadioMode::Tx => {
                    if let Some(a) = col_index(r.route.tx) {
                        route(
                            d,
                            (108, y + 18),
                            (ANT_X, ant_y(a) + 11),
                            bus(i, false),
                            TX,
                            4,
                            Some(TX_GLOW),
                        );
                    }
                }
                _ => {}
            }
        }
    }
}

// ---------------------------------------------------------------- C: cards

fn cards<D: Target>(d: &mut D, s: &UiState) {
    for (i, r) in s.radios.iter().enumerate() {
        let y = 26 + i as i32 * 60;
        let on = r.mode != RadioMode::Off;
        let surf = if on { CARD } else { CARD_DIM };
        rrect(d, 8, y, 304, 54, 12, surf);
        let (label, fill, fg) = state_label(r);
        rrect(d, 14, y + 6, 54, 42, 10, fill);
        let font = if r.mode == RadioMode::Off {
            &TITLE
        } else {
            &BIG
        };
        text(d, font, label, 41, y + 27, fg, fill, C);
        text(
            d,
            &TITLE,
            RADIO_LABELS[i],
            80,
            y + 15,
            if on { TEXT } else { FAINT },
            surf,
            L,
        );
        text(
            d,
            &SMALL,
            s.radio_names[i].as_str(),
            104,
            y + 15,
            if on { SEC } else { FAINT },
            surf,
            L,
        );
        route_row(
            d,
            s,
            surf,
            y + 32,
            true,
            if on { r.route.tx } else { Col::None },
        );
        route_row(
            d,
            s,
            surf,
            y + 45,
            false,
            if on { r.route.rx } else { Col::None },
        );
        if i == 0
            && on
            && let Some(b) = s.band.and_then(band_name)
        {
            text(d, &NUM, b, 302, y + 30, TEXT, surf, R);
        }
    }
}

fn route_row<D: Target>(d: &mut D, s: &UiState, surf: Rgb565, y: i32, is_tx: bool, c: Col) {
    let col = match (col_index(c), is_tx) {
        (None, _) => FAINT,
        (Some(_), true) => TX,
        (Some(_), false) => RX,
    };
    if is_tx {
        tri(d, [(80, y - 4), (80, y + 4), (87, y)], col);
    } else {
        tri(d, [(87, y - 4), (87, y + 4), (80, y)], col);
    }
    text(
        d,
        &SMALL,
        if is_tx { "TX" } else { "RX" },
        93,
        y,
        SEC,
        surf,
        L,
    );
    match col_index(c) {
        Some(i) => {
            let (a, n) = (ANTENNA_LABELS[i], s.antenna_names[i].as_str());
            let warn = bias_fault(s, c);
            text(
                d,
                &BODY,
                a,
                116,
                y,
                if warn { AMBER } else { TEXT },
                surf,
                L,
            );
            text(
                d,
                &SMALL,
                n,
                142,
                y,
                if warn { AMBER } else { SEC },
                surf,
                L,
            );
        }
        None => text(d, &SMALL, "-", 116, y, FAINT, surf, L),
    }
}

// ---------------------------------------------------------------- Safe stop

fn stop<D: Target>(d: &mut D, s: &UiState) {
    let (title, sub) = wording::stop_title(s);
    let icon = if s.stop.is_some() { TX } else { AMBER };
    octagon(d, 40, 40, 26, icon);
    rect(d, 28, 37, 24, 7, TEXT);
    text(d, &HUGE, title, 78, 30, TEXT, BG, L);
    text(d, &SMALL, sub, 79, 54, SEC, BG, L);

    let cause = wording::cause(s);
    let rows = [
        ("Cause", cause, AMBER),
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
    rrect(d, 8, 76, 304, 92, 12, CARD);
    for (i, (k, v, c)) in rows.iter().enumerate() {
        let y = 89 + i as i32 * 21;
        text(d, &BODY, k, 20, y, SEC, CARD, L);
        dot(d, 296, y, 8, *c);
        text(d, &BODY, v, 288, y, TEXT, CARD, R);
    }

    let steps = wording::steps(s);
    rrect(d, 8, 176, 304, 56, 12, AMBER_TINT);
    let y0 = if steps.len() == 1 { 204 } else { 191 };
    for (i, st) in steps.iter().enumerate() {
        let y = y0 + i as i32 * 26;
        dot(d, 26, y, 18, AMBER);
        let n = ["1", "2"][i.min(1)];
        text(d, &SMALL, n, 26, y, AMBER_TINT, AMBER, C);
        text(d, &TITLE, st, 42, y, AMBER, AMBER_TINT, L);
    }
}

/// Stop sign: a regular octagon as a fan of triangles (corners precomputed, no floating point).
fn octagon<D: Target>(d: &mut D, cx: i32, cy: i32, r: i32, c: Rgb565) {
    // cos and sin of 22.5 + k * 45 degrees, times 1000.
    const P: [(i32, i32); 8] = [
        (924, 383),
        (383, 924),
        (-383, 924),
        (-924, 383),
        (-924, -383),
        (-383, -924),
        (383, -924),
        (924, -383),
    ];
    let pt = |k: usize| (cx + P[k].0 * r / 1000, cy + P[k].1 * r / 1000);
    for k in 0..8 {
        tri(d, [(cx, cy), pt(k), pt((k + 1) % 8)], c);
    }
}
