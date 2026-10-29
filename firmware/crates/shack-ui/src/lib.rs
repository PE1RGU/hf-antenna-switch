//! Shack interface display (D-187: Waveshare 2inch, ST7789VW, used as 320 x 240 landscape).
//!
//! Pages, as chosen by Prins from docs/design/display-mockups (2026-10-29):
//! - B flow: radios left, antennas right, a line per path; TX red, RX green.
//! - C cards: one card per radio with its TX and RX antenna in words.
//! - Safe stop: takes over on a blocking problem (SAFE latch set, or a known fault).
//!
//! `render` draws a `UiState` snapshot on any RGB565 draw target. No hardware access.
//!
//! # Where this crate sits
//!
//! The crate is `no_std`: it uses only `core`, not the Rust standard library, so it
//! runs on the ESP32-C3 and on the Mac alike. It draws; it does not decide. The
//! shack logic (crate `shack-core`) decides what is true and fills a [`UiState`].
//! This crate turns that state into pixels. The simulator uses the same code for
//! its picture of the display, and [`wording`] for its text view.
//!
//! # From state to screen
//!
//! 1. The logic makes a [`UiState`]: a plain copy of what the screen must show.
//! 2. [`UiState::page`] picks the page: the host's choice (B or C), or the Safe stop
//!    screen when the SAFE latch is set or a fault is known.
//! 3. [`render`] draws the whole page into a [`FrameBuffer`]: 320 x 240 pixels,
//!    RGB565, in the byte order of the ST7789.
//! 4. The logic sends the frame buffer to the ST7789 over SPI, a few rows per tick,
//!    with the commands in [`st7789`].
//!
//! [`render`] draws through the `embedded-graphics` `DrawTarget` trait. A trait is
//! a list of functions that a type promises to supply. So the same drawing code
//! works on the frame buffer, on a test image or on any other RGB565 target.
//!
//! # Fonts need a background colour
//!
//! The text uses M+ fonts with anti-aliasing: the edge pixels of a letter are
//! mixed between the text colour and the background colour. The font has no
//! transparency (no alpha), so it cannot mix with what is already in the buffer.
//! It mixes with a colour that the caller gives. Each text call therefore names
//! the colour under the text. A wrong colour gives a visible box around the text.
//!
//! # Example
//!
//! ```
//! use shack_ui::{FrameBuffer, Page, StopCause, UiState, fb, render};
//!
//! let mut buf = vec![0u8; fb::BYTES];
//! let state = UiState {
//!     stop: Some(StopCause::PowerUp),
//!     latched: true,
//!     ..Default::default()
//! };
//! // The latch is set, so the Safe stop screen takes over from page B.
//! assert_eq!(state.page(Page::Flow), Page::Stop);
//! render(&mut FrameBuffer::new(&mut buf), &state, Page::Flow);
//! ```
#![no_std]

mod draw;
pub mod fb;
mod pages;
pub mod st7789;
mod theme;
pub mod wording;

pub use fb::FrameBuffer;
pub use pages::render;

use heapless::Vec;
pub use host_proto::Name;
use link_proto::{Col, ColMask, Route};

/// Display width in pixels (landscape).
pub const WIDTH: u32 = 320;
/// Display height in pixels (landscape).
pub const HEIGHT: u32 = 240;

/// Column labels. The names come with the state (stored settings, `name` command).
pub const ANTENNA_LABELS: [&str; 5] = ["A1", "A2", "A3", "A4", "EXP"];

/// The page on screen.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Page {
    /// Page B: radios left, antennas right, one line per path.
    #[default]
    Flow,
    /// Page C: one card per radio, with its TX and RX antenna in words.
    Cards,
    /// Takes over from Flow and Cards.
    Stop,
}

/// What a radio does now, as shown on pages B and C.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum RadioMode {
    /// No route.
    #[default]
    Off,
    /// Routed, not transmitting.
    Rx,
    /// Transmitting (TX sense, or keyed by the interface with its permit).
    Tx,
}

/// One radio on the display.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct RadioUi {
    /// TX and RX column as the box reports it. No route while the link is down.
    pub route: Route,
    /// Off, RX or TX.
    pub mode: RadioMode,
    /// Permit out (TX allowed), whether or not it transmits.
    pub permit: bool,
}

/// A problem that does not stop TX: one line at the bottom of the page.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Warning {
    /// No box link: routes and box state unknown.
    LinkDown,
    /// Bias-T on for this column, but the box measures no current. Never
    /// `Col::None`.
    BiasFault(Col),
    /// Radio index (0 = R1 to 2 = R3) keyed with its permit for 500 ms, without TX
    /// sense (C-3). TX is not blocked.
    TxSense(usize),
    /// The radio (index 0 to 2) transmits without its permit (F15, D-188).
    TxWithoutPermit(usize),
    /// Fault code from the box Status (link-protocol.md 4.2).
    BoxFault(u8),
}

/// Why the SAFE latch is set (Safe stop screen).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopCause {
    /// Power-up: the latch is set until the first RESET.
    PowerUp,
    /// The KILL switch is pressed.
    Kill,
    /// `stop on` from the host.
    SoftwareStop,
    /// The box opened SAFE after a link loss with a permit out (F13).
    LinkLostStop,
    /// No loop current, cause outside the shack (box, cable, RF on A2).
    LoopOpen,
    /// Loop current is back; only RESET is needed.
    LoopBack,
}

/// Everything the display shows, as one plain value.
///
/// The logic makes a new one each tick. When it equals the last one drawn, the
/// display is not redrawn. The `Default` value is a blank state: no link, no box,
/// all radios off.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct UiState {
    /// SAFE loop current present.
    pub safe_ok: bool,
    /// SAFE latch set (or unknown, which counts as set).
    pub latched: bool,
    /// Box link up.
    pub link_up: bool,
    /// None: no box status yet.
    pub box_ready: Option<bool>,
    /// R1 band data, 0 to 15 (BAND D C B A).
    pub band: Option<u8>,
    /// R1, R2, R3.
    pub radios: [RadioUi; 3],
    /// Receive-only columns, marked `rx` on page B (unit 1: A2, D-103).
    pub rx_only: ColMask,
    /// Problems that do not stop TX. The first one is shown; the rest are counted.
    pub warnings: Vec<Warning, 4>,
    /// Some: the SAFE latch is set.
    pub stop: Option<StopCause>,
    /// Supervisor fault known after start-up (C-2): TX blocked until `clearfault`.
    pub fault: bool,
    /// A1 to A4, EXP.
    pub antenna_names: [Name; 5],
    /// R1 to R3 names, from the stored settings.
    pub radio_names: [Name; 3],
}

impl UiState {
    /// The page to show for the page the host chose.
    ///
    /// The Safe stop screen takes over while the SAFE latch is set or a fault is
    /// known. Otherwise the chosen page stays.
    ///
    /// ```
    /// use shack_ui::{Page, UiState};
    ///
    /// let mut s = UiState::default();
    /// assert_eq!(s.page(Page::Cards), Page::Cards);
    /// s.fault = true;
    /// assert_eq!(s.page(Page::Cards), Page::Stop);
    /// ```
    pub fn page(&self, chosen: Page) -> Page {
        if self.stop.is_some() || self.fault {
            Page::Stop
        } else {
            chosen
        }
    }
}

/// FT-710 band data to a band name. Yaesu band data table, to confirm against the
/// FT-710 manual (A-18). 15 = no radio (pull-ups).
///
/// `code` is the 4-bit band data (BAND D C B A). Codes without a band give `None`;
/// the display then shows `--`.
///
/// ```
/// use shack_ui::band_name;
///
/// assert_eq!(band_name(5), Some("20 m"));
/// assert_eq!(band_name(10), Some("6 m"));
/// assert_eq!(band_name(15), None); // no radio connected
/// ```
pub fn band_name(code: u8) -> Option<&'static str> {
    Some(match code {
        1 => "160 m",
        2 => "80 m",
        3 => "40 m",
        4 => "30 m",
        5 => "20 m",
        6 => "17 m",
        7 => "15 m",
        8 => "12 m",
        9 => "10 m",
        10 => "6 m",
        _ => return None,
    })
}
