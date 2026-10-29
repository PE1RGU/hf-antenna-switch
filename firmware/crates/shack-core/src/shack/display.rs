//! Display: ST7789 start-up, page choice, redraw on change (P3c).
//!
//! D/C, RST and backlight are expander pins (D-180), so every D/C change is an
//! I2C write. A frame is drawn once into the frame buffer and then sent in
//! chunks of ROWS_PER_TICK rows, one chunk per tick, so the main loop (WDI,
//! link, permits) keeps its 10 ms rhythm. The display never touches a safety line.

use super::*;
use host_proto::PageSel;
use link_proto::{Col, ColMask};
use shack_ui::fb::ROW_BYTES;
use shack_ui::{
    FrameBuffer, HEIGHT, Page, RadioMode, RadioUi, StopCause, UiState, Warning, st7789,
};

/// 48 rows = 30 720 bytes per tick: about 6 ms at 40 MHz SPI.
pub const ROWS_PER_TICK: u32 = 48;
/// `page auto`: B for 10 s, then C for 5 s.
pub const AUTO_FLOW_MS: Ms = 10_000;
pub const AUTO_CARDS_MS: Ms = 5_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Phase {
    /// Not started, or the expander was lost (pins in reset).
    Off,
    ResetLow {
        since: Ms,
    },
    WaitReset {
        since: Ms,
    },
    WaitSleepOut {
        since: Ms,
    },
    Ready,
}

pub(super) struct Display {
    phase: Phase,
    pub(super) sel: PageSel,
    rst: bool,
    dc: bool,
    backlight: bool,
    drawn: Option<(UiState, Page)>,
    next_row: Option<u32>,
}

impl Display {
    pub(super) fn new() -> Self {
        Display {
            phase: Phase::Off,
            sel: PageSel::Flow,
            rst: false,
            dc: false,
            backlight: false,
            drawn: None,
            next_row: None,
        }
    }

    /// Display bits for the expander output word.
    pub(super) fn exp_bits(&self) -> u16 {
        let bit = |on: bool, p: ExpPin| if on { 1u16 << p.bit } else { 0 };
        bit(self.rst, exp::DISP_RST)
            | bit(self.dc, exp::DISP_DC)
            | bit(self.backlight, exp::DISP_BL)
    }

    /// Expander lost: its pins are inputs again, the display is in reset.
    pub(super) fn lost(&mut self) {
        *self = Display {
            sel: self.sel,
            ..Display::new()
        };
    }

    fn chosen(&self, now: Ms) -> Page {
        match self.sel {
            PageSel::Flow => Page::Flow,
            PageSel::Cards => Page::Cards,
            PageSel::Auto if now % (AUTO_FLOW_MS + AUTO_CARDS_MS) < AUTO_FLOW_MS => Page::Flow,
            PageSel::Auto => Page::Cards,
        }
    }
}

impl Shack {
    /// Write the expander outputs now (D/C, RST, backlight change).
    fn write_exp<H: ShackHw>(&mut self, hw: &mut H) {
        let w = self.exp_word();
        if EXPANDER.write_outputs(hw.i2c(), w).is_ok() {
            self.exp_written = Some(w);
        }
    }

    fn set_dc<H: ShackHw>(&mut self, hw: &mut H, data: bool) {
        if self.display.dc != data {
            self.display.dc = data;
            self.write_exp(hw);
        }
    }

    fn lcd_cmd<H: ShackHw>(&mut self, hw: &mut H, c: u8, args: &[u8]) {
        self.set_dc(hw, false);
        hw.spi_write(&[c]);
        if !args.is_empty() {
            self.set_dc(hw, true);
            hw.spi_write(args);
        }
    }

    pub(super) fn display_step<H: ShackHw>(&mut self, now: Ms, hw: &mut H) {
        if !self.expander_ready {
            return;
        }
        let since_ok = |since: Ms, wait: Ms| now.saturating_sub(since) >= wait;
        match self.display.phase {
            Phase::Off => {
                self.display.rst = false;
                self.display.backlight = false;
                self.write_exp(hw);
                self.display.phase = Phase::ResetLow { since: now };
            }
            Phase::ResetLow { since } if since_ok(since, TICK) => {
                self.display.rst = true;
                self.write_exp(hw);
                self.display.phase = Phase::WaitReset { since: now };
            }
            Phase::WaitReset { since } if since_ok(since, st7789::WAIT_MS) => {
                self.lcd_cmd(hw, st7789::SLPOUT, &[]);
                self.display.phase = Phase::WaitSleepOut { since: now };
            }
            Phase::WaitSleepOut { since } if since_ok(since, st7789::WAIT_MS) => {
                for (c, args) in st7789::INIT {
                    self.lcd_cmd(hw, c, args);
                }
                self.display.backlight = true;
                self.write_exp(hw);
                self.display.drawn = None;
                self.display.phase = Phase::Ready;
            }
            Phase::Ready => self.frame_step(now, hw),
            _ => {}
        }
    }

    /// Send the next chunk of a frame, or start a new frame when the screen changed.
    fn frame_step<H: ShackHw>(&mut self, now: Ms, hw: &mut H) {
        if self.display.next_row.is_none() {
            let state = self.ui_state();
            let page = state.page(self.display.chosen(now));
            if self.display.drawn.as_ref() == Some(&(state.clone(), page)) {
                return;
            }
            shack_ui::render(&mut FrameBuffer::new(hw.framebuffer()), &state, page);
            for (c, args) in st7789::window(0, 0, shack_ui::WIDTH as u16 - 1, HEIGHT as u16 - 1) {
                self.lcd_cmd(hw, c, &args);
            }
            self.lcd_cmd(hw, st7789::RAMWR, &[]);
            self.set_dc(hw, true);
            self.display.drawn = Some((state, page));
            self.display.next_row = Some(0);
        }
        if let Some(row) = self.display.next_row {
            let end = (row + ROWS_PER_TICK).min(HEIGHT);
            hw.spi_write_framebuffer(row as usize * ROW_BYTES, end as usize * ROW_BYTES);
            self.display.next_row = (end < HEIGHT).then_some(end);
        }
    }

    /// Snapshot of what the display shows.
    pub fn ui_state(&self) -> UiState {
        let inp = self.inputs;
        let latched = inp.is_none_or(|i| i.latched);
        let status = self.status.filter(|_| self.link.is_up());
        let radios = Radio::ALL.map(|r| {
            let i = r.index();
            let route = status.map(|s| s.routes[i]).unwrap_or_default();
            let sense = inp.is_some_and(|x| x.tx_sense[i]);
            let transmitting = sense || (self.permit_out[i] && self.want_key[i]);
            let mode = if transmitting {
                RadioMode::Tx
            } else if route != Route::default() {
                RadioMode::Rx
            } else {
                RadioMode::Off
            };
            RadioUi {
                route,
                mode,
                permit: self.permit_out[i],
            }
        });

        let mut warnings = heapless::Vec::new();
        if !self.link.is_up() {
            let _ = warnings.push(Warning::LinkDown);
        }
        if let Some(s) = status {
            for c in &Col::ALL[1..] {
                if s.bias_en.contains(*c) && !s.bias_ok.contains(*c) {
                    let _ = warnings.push(Warning::BiasFault(*c));
                }
            }
            if s.fault.0 != 0 {
                let _ = warnings.push(Warning::BoxFault(s.fault.0));
            }
        }
        for i in 0..3 {
            if self.sense_fault[i] {
                let _ = warnings.push(Warning::TxSense(i));
            }
        }

        let stop = latched.then(|| {
            if inp.is_some_and(|i| i.kill) {
                StopCause::Kill
            } else if self.sw_stop {
                StopCause::SoftwareStop
            } else if status.is_some_and(|s| s.flags.link_lost_stop) {
                StopCause::LinkLostStop
            } else if self.safe_lost {
                StopCause::LoopOpen
            } else if !self.ever_unlatched {
                StopCause::PowerUp
            } else {
                StopCause::LoopBack
            }
        });

        UiState {
            safe_ok: !self.safe_lost,
            latched,
            link_up: self.link.is_up(),
            box_ready: status.map(|s| s.flags.ready),
            band: inp.map(|i| i.band),
            radios,
            // Unit 1: A2 is receive only (D-103).
            rx_only: ColMask::EMPTY.with(Col::A2),
            warnings,
            stop,
            fault: self.fault_known,
            antenna_names: self.config.antenna_names,
            radio_names: self.config.radio_names,
        }
    }

    /// Page selection (`page` host command).
    pub fn set_page(&mut self, sel: PageSel) {
        self.display.sel = sel;
    }

    pub fn page(&self) -> PageSel {
        self.display.sel
    }

    /// The page the display shows at `now` (Safe stop takes over from the chosen page).
    pub fn shown_page(&self, now: Ms) -> Page {
        self.ui_state().page(self.display.chosen(now))
    }
}
