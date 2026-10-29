//! Page renders: key pixels, every combination without a panic, PNGs for review
//! (written to the cargo target temp folder).

use embedded_graphics::pixelcolor::Rgb565;
use embedded_graphics::pixelcolor::raw::{RawData, RawU16};
use heapless::Vec as HVec;
use link_proto::{Col, ColMask, Route};
use shack_ui::fb::{BYTES, pixel};
use shack_ui::*;

fn raw(c: Rgb565) -> u16 {
    RawU16::from(c).into_inner()
}

/// R1 TX on A1, RX on A2; R2 RX on A3; R3 off; bias-T warning on A2.
fn demo() -> UiState {
    let mut warnings = HVec::new();
    warnings.push(Warning::BiasFault(Col::A2)).unwrap();
    UiState {
        safe_ok: true,
        latched: false,
        link_up: true,
        box_ready: Some(true),
        band: Some(5),
        radios: [
            RadioUi {
                route: Route {
                    tx: Col::A1,
                    rx: Col::A2,
                },
                mode: RadioMode::Tx,
                permit: true,
            },
            RadioUi {
                route: Route {
                    tx: Col::None,
                    rx: Col::A3,
                },
                mode: RadioMode::Rx,
                permit: false,
            },
            RadioUi::default(),
        ],
        rx_only: ColMask::EMPTY.with(Col::A2),
        warnings,
        stop: None,
        fault: false,
    }
}

fn render_to(s: &UiState, page: Page) -> Vec<u8> {
    let mut buf = vec![0u8; BYTES];
    render(&mut FrameBuffer::new(&mut buf), s, page);
    buf
}

fn save(name: &str, buf: &[u8]) {
    let dir = std::path::Path::new(env!("CARGO_TARGET_TMPDIR")).join("shack-ui");
    std::fs::create_dir_all(&dir).unwrap();
    const S: u32 = 2;
    let mut data = Vec::new();
    for y in 0..HEIGHT * S {
        for x in 0..WIDTH * S {
            let p = pixel(buf, x / S, y / S);
            data.extend([
                ((p >> 11) << 3) as u8,
                (((p >> 5) & 0x3F) << 2) as u8,
                ((p & 0x1F) << 3) as u8,
            ]);
        }
    }
    let f = std::fs::File::create(dir.join(name)).unwrap();
    let mut e = png::Encoder::new(std::io::BufWriter::new(f), WIDTH * S, HEIGHT * S);
    e.set_color(png::ColorType::Rgb);
    e.set_depth(png::BitDepth::Eight);
    e.write_header().unwrap().write_image_data(&data).unwrap();
}

/// Colours used by the theme (copied: theme is private).
const TX: u32 = 0xFF4D4F;
const RX_TINT: u32 = 0x123326;
const AMBER: u32 = 0xF5A524;

fn c(h: u32) -> u16 {
    raw(Rgb565::new(
        ((h >> 19) & 0x1F) as u8,
        ((h >> 10) & 0x3F) as u8,
        ((h >> 3) & 0x1F) as u8,
    ))
}

#[test]
fn flow_page() {
    let buf = render_to(&demo(), Page::Flow);
    save("flow.png", &buf);
    // TX pill of R1, RX pill of R2 (left edge, clear of the text).
    assert_eq!(pixel(&buf, 66, 36 + 10 - 8 + 8), c(TX));
    assert_eq!(pixel(&buf, 66, 88 + 18), c(RX_TINT));
    // The active TX line runs level into A1 at y = 28 + 11.
    assert_eq!(pixel(&buf, 180, 39), c(TX));
    // Amber edge on A2 (bias-T fault) and the warning toast.
    assert_eq!(pixel(&buf, 223, 64 + 15), c(AMBER));
    assert_eq!(pixel(&buf, 22, 216), c(AMBER));
}

#[test]
fn cards_page() {
    let buf = render_to(&demo(), Page::Cards);
    save("cards.png", &buf);
    assert_eq!(pixel(&buf, 18, 40), c(TX), "R1 badge red");
    assert_eq!(pixel(&buf, 18, 100), c(RX_TINT), "R2 badge tinted");
}

#[test]
fn safe_stop_takes_over() {
    for (cause, name) in [
        (StopCause::PowerUp, "stop-powerup.png"),
        (StopCause::Kill, "stop-kill.png"),
        (StopCause::LoopOpen, "stop-loop.png"),
    ] {
        let mut s = demo();
        s.latched = true;
        s.safe_ok = cause != StopCause::LoopOpen && cause != StopCause::Kill;
        s.stop = Some(cause);
        assert_eq!(s.page(Page::Cards), Page::Stop);
        let buf = render_to(&s, Page::Flow);
        save(name, &buf);
        assert_eq!(pixel(&buf, 40, 25), c(TX), "red stop sign");
    }
    let mut s = demo();
    s.fault = true;
    let buf = render_to(&s, Page::Flow);
    save("fault.png", &buf);
    assert_eq!(pixel(&buf, 40, 25), c(AMBER), "amber sign for a fault");
}

#[test]
fn every_route_and_mode_renders() {
    let modes = [RadioMode::Off, RadioMode::Rx, RadioMode::Tx];
    let mut n = 0;
    for tx in Col::ALL {
        for rx in Col::ALL {
            for m in modes {
                for permit in [false, true] {
                    let mut s = demo();
                    s.radios[n % 3] = RadioUi {
                        route: Route { tx, rx },
                        mode: m,
                        permit,
                    };
                    s.band = Some((n % 16) as u8);
                    for page in [Page::Flow, Page::Cards] {
                        render_to(&s, page);
                    }
                    n += 1;
                }
            }
        }
    }
    assert_eq!(n, 216);
}

#[test]
fn band_names() {
    assert_eq!(band_name(5), Some("20 m"));
    assert_eq!(band_name(15), None, "no radio");
    assert_eq!(band_name(0), None);
}
