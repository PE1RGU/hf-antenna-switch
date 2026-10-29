//! Display on the simulated ST7789: what the panel holds equals a direct render of
//! the shack state (P3c). PNGs of the screens go to the cargo target temp folder.

use embedded_graphics::pixelcolor::Rgb565;
use embedded_graphics::pixelcolor::raw::{RawData, RawU16};
use link_proto::Radio;
use shack_core::board::exp;
use shack_ui::fb::{BYTES, ROW_BYTES, pixel};
use shack_ui::{FrameBuffer, HEIGHT, Page, StopCause, WIDTH};
use sim_shack::ShackSim;

fn expected(s: &ShackSim, page: Page) -> Vec<u16> {
    let mut buf = vec![0u8; BYTES];
    shack_ui::render(&mut FrameBuffer::new(&mut buf), &s.shack.ui_state(), page);
    (0..HEIGHT)
        .flat_map(|y| (0..WIDTH).map(move |x| (x, y)))
        .map(|(x, y)| pixel(&buf, x, y))
        .collect()
}

fn shot(s: &ShackSim, name: &str) {
    let p = std::path::Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("display")
        .join(name);
    s.save_screen(&p, 2);
}

fn assert_screen(s: &ShackSim, page: Page, what: &str) {
    let got = s.screen();
    let want = expected(s, page);
    let diff = got.iter().zip(&want).filter(|(a, b)| a != b).count();
    assert_eq!(diff, 0, "{what}: {diff} pixels differ");
}

/// Keep the host alive while time runs (TX and keys are on in some tests).
fn run_alive(s: &mut ShackSim, ms: u64) {
    let end = s.now() + ms;
    while s.now() < end {
        s.host("status");
        s.run(500.min(end.saturating_sub(s.now())));
    }
}

#[test]
fn power_up_shows_safe_stop() {
    let mut s = ShackSim::new();
    s.run(800);
    let b = s.board.borrow();
    assert!(b.lcd.showing(), "display initialised");
    assert_eq!(b.lcd.madctl(), shack_ui::st7789::MADCTL_LANDSCAPE);
    assert!(b.exp_pin(exp::DISP_BL), "backlight on");
    drop(b);
    assert_eq!(s.shack.ui_state().stop, Some(StopCause::PowerUp));
    assert_screen(&s, Page::Flow, "power-up");
    shot(&s, "1-power-up.png");
}

#[test]
fn flow_page_follows_a_transmission() {
    let mut s = ShackSim::new();
    s.start();
    s.host("route R2 A1 A3");
    s.host("route R1 A3 A2");
    run_alive(&mut s, 300);
    s.host("tx R2 on");
    s.host("key R2 on");
    run_alive(&mut s, 400);
    assert!(s.shack.permit(Radio::R2));
    assert_screen(&s, Page::Flow, "R2 transmits");
    shot(&s, "2-flow-r2-tx.png");
    // R2 TX pill (left edge of the pill, card at y 88).
    let red = RawU16::from(Rgb565::new(0xFF >> 3, 0x4D >> 2, 0x4F >> 3)).into_inner();
    assert_eq!(s.screen()[(88 + 18) * WIDTH as usize + 66], red);
}

#[test]
fn page_command_and_auto() {
    let mut s = ShackSim::new();
    s.start();
    s.host("route R1 A1 A2");
    s.run(200);
    assert_eq!(s.host("page c"), "ok");
    s.run(100);
    assert_screen(&s, Page::Cards, "page c");
    assert!(s.host("status").contains("page=c"));
    shot(&s, "3-cards.png");

    assert_eq!(s.host("page auto"), "ok");
    // Into the B part of the 15 s cycle, then into the C part.
    s.run_until(16_000, |s| s.now() % 15_000 == 1_000);
    s.run(100);
    assert_screen(&s, Page::Flow, "auto, B part");
    s.run_until(16_000, |s| s.now() % 15_000 == 11_000);
    s.run(100);
    assert_screen(&s, Page::Cards, "auto, C part");
}

#[test]
fn kill_takes_over_with_its_cause() {
    let mut s = ShackSim::new();
    s.start();
    s.host("page c");
    // The display is ready about 450 ms after power-up.
    s.run_until(1000, |s| s.board.borrow().lcd.showing())
        .unwrap();
    s.board.borrow_mut().set_env(|e| e.kill_pressed = true);
    s.run(100);
    assert_eq!(s.shack.ui_state().stop, Some(StopCause::Kill));
    assert_screen(&s, Page::Cards, "KILL");
    shot(&s, "4-kill.png");
    // Released: loop back, only RESET needed; then back to the chosen page.
    s.board.borrow_mut().set_env(|e| e.kill_pressed = false);
    s.run(100);
    assert_eq!(s.shack.ui_state().stop, Some(StopCause::LoopBack));
    s.press_reset();
    s.run(100);
    assert_eq!(s.shack.ui_state().stop, None);
    assert_screen(&s, Page::Cards, "after RESET");
}

#[test]
fn frames_go_out_in_chunks() {
    let mut s = ShackSim::new();
    s.start();
    s.host("page auto");
    s.run(20_000);
    assert!(s.spi_max_per_tick > 0);
    // One chunk of rows plus a few command bytes per tick.
    let chunk = shack_core::shack::ROWS_PER_TICK as usize * ROW_BYTES;
    assert!(
        s.spi_max_per_tick <= chunk + 32,
        "{} bytes in one tick",
        s.spi_max_per_tick
    );
    // WDI still kicked every tick while frames go out.
    let b = s.board.borrow();
    let wdi = b.trace.signal("WDI");
    let gap = wdi.windows(2).map(|w| w[1].0 - w[0].0).max().unwrap();
    assert!(gap <= sim_core::SimTime::ms(20));
}

#[test]
fn display_starts_again_after_expander_loss() {
    let mut s = ShackSim::new();
    s.start();
    s.run(300);
    s.board.borrow_mut().exp.force_nack = true;
    s.run(30);
    s.board.borrow_mut().exp.force_nack = false;
    s.run(800);
    let resets = s
        .board
        .borrow()
        .trace
        .signal("DISP_RST")
        .iter()
        .filter(|(_, v)| *v)
        .count();
    assert!(resets >= 2, "display reset sequence again");
    assert!(s.board.borrow().lcd.showing());
    assert_screen(&s, Page::Flow, "after expander loss");
}
