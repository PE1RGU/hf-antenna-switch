//! Shack interface display (D-187: Waveshare 2inch, ST7789VW, used as 320 x 240 landscape).
//!
//! Pages, as chosen by Prins from docs/design/display-mockups (2026-10-29):
//! - B flow: radios left, antennas right, a line per path; TX red, RX green.
//! - C cards: one card per radio with its TX and RX antenna in words.
//! - Safe stop: takes over on a blocking problem (SAFE latch set, or a known fault).
//!
//! `render` draws a `UiState` snapshot on any RGB565 draw target. No hardware access.
#![no_std]

mod draw;
pub mod fb;
mod pages;
pub mod st7789;
mod theme;

pub use fb::FrameBuffer;
pub use pages::render;

use heapless::Vec;
pub use host_proto::Name;
use link_proto::{Col, ColMask, Route};

pub const WIDTH: u32 = 320;
pub const HEIGHT: u32 = 240;

/// Column labels. The names come with the state (stored settings, `name` command).
pub const ANTENNA_LABELS: [&str; 5] = ["A1", "A2", "A3", "A4", "EXP"];

/// The page on screen.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Page {
    #[default]
    Flow,
    Cards,
    /// Takes over from Flow and Cards.
    Stop,
}

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

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct RadioUi {
    pub route: Route,
    pub mode: RadioMode,
    /// Permit out (TX allowed), whether or not it transmits.
    pub permit: bool,
}

/// A problem that does not stop TX: one line at the bottom of the page.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Warning {
    LinkDown,
    BiasFault(Col),
    TxSense(usize),
    BoxFault(u8),
}

/// Why the SAFE latch is set (Safe stop screen).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopCause {
    /// Power-up: the latch is set until the first RESET.
    PowerUp,
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

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct UiState {
    pub safe_ok: bool,
    pub latched: bool,
    pub link_up: bool,
    /// None: no box status yet.
    pub box_ready: Option<bool>,
    /// R1 band data, 0 to 15 (BAND D C B A).
    pub band: Option<u8>,
    pub radios: [RadioUi; 3],
    pub rx_only: ColMask,
    pub warnings: Vec<Warning, 4>,
    /// Some: the SAFE latch is set.
    pub stop: Option<StopCause>,
    /// Supervisor fault known after start-up (C-2): TX blocked until `clearfault`.
    pub fault: bool,
    /// A1 to A4, EXP.
    pub antenna_names: [Name; 5],
    pub radio_names: [Name; 3],
}

impl UiState {
    /// The page to show for the page the host chose.
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
