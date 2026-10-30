//! Words on the screen, shared by the pixel pages and the simulator's text view,
//! so both always say the same.
//!
//! The texts use printable ASCII and the middle dot only: the display fonts hold
//! no other characters.

use crate::{ANTENNA_LABELS, StopCause, UiState, Warning};
use core::fmt::Write;
use heapless::String;

/// Radio labels, by radio index (0 = R1). The names come with the state.
pub const RADIO_LABELS: [&str; 3] = ["R1", "R2", "R3"];

/// Title and subtitle of the Safe stop (or Fault) screen.
///
/// "Safe stop" while the SAFE latch is set; "Fault" when only a supervisor fault
/// is known (C-2).
pub fn stop_title(s: &UiState) -> (&'static str, &'static str) {
    if s.stop.is_some() {
        ("Safe stop", "All radios inhibited · relays released")
    } else {
        ("Fault", "Supervisor reset · TX blocked")
    }
}

/// The cause line of the Safe stop screen, from [`UiState::stop`]. Without a
/// stop cause the screen is the Fault screen: a watchdog or brown-out reset.
pub fn cause(s: &UiState) -> &'static str {
    match s.stop {
        Some(StopCause::PowerUp) => "Power-up",
        Some(StopCause::Kill) => "KILL switch pressed",
        Some(StopCause::SoftwareStop) => "Software stop (host)",
        Some(StopCause::LinkLostStop) => "Box: link lost during TX",
        Some(StopCause::LoopOpen) => "SAFE loop open (box, cable)",
        Some(StopCause::LoopBack) => "SAFE loop closed again",
        None => "Watchdog or brown-out",
    }
}

/// What the operator does, in order.
pub fn steps(s: &UiState) -> &'static [&'static str] {
    match s.stop {
        Some(StopCause::Kill) => &["Release the KILL switch", "Press RESET"],
        Some(StopCause::SoftwareStop) => &["Host: stop off", "Press RESET"],
        Some(StopCause::LinkLostStop) => &["Restore the box link", "Press RESET"],
        Some(StopCause::LoopOpen) => &["Check the box and the cable", "Press RESET"],
        Some(StopCause::PowerUp | StopCause::LoopBack) => &["Press RESET"],
        None => &["Check the supply and the log", "Host: clearfault"],
    }
}

/// The first warning, and how many more there are.
///
/// For example `Box link down  (+1)`. `None` when there is no warning.
pub fn warning_line(s: &UiState) -> Option<String<48>> {
    let w = s.warnings.first()?;
    let mut msg = String::new();
    let _ = match *w {
        Warning::LinkDown => write!(msg, "Box link down"),
        Warning::BiasFault(c) => write!(
            msg,
            "{} bias-T · no current",
            ANTENNA_LABELS[c as usize - 1]
        ),
        Warning::TxSense(r) => write!(msg, "{} TX sense · no signal", RADIO_LABELS[r]),
        Warning::TxWithoutPermit(r) => write!(msg, "{} transmits without permit", RADIO_LABELS[r]),
        Warning::BoxFault(n) => write!(msg, "Box fault {n}"),
    };
    if s.warnings.len() > 1 {
        let _ = write!(msg, "  (+{})", s.warnings.len() - 1);
    }
    Some(msg)
}
