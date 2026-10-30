//! TE RT1 RTD14012F power relay, 12 V coil, one changeover contact (RT1pb rev 4).
//!
//! Datasheet maxima: operate 8 ms, release 6 ms, bounce 4 ms on the NO contact
//! (form A) and 6 ms on the NC contact (form B). The datasheet gives no minimum
//! times (verify_logic.py section 8, finding F9).
//!
//! The model moves the contact in steps: NC, NO with bounce, NO, NC with bounce.
//! While a contact bounces it counts as closed for RF (a bounce is a short
//! make and break under power, the hot switching that rule F10 avoids). The coil
//! sees no supply voltage or current: the board decides when the coil is on.

use sim_core::SimTime;

/// Relay timing. [`Rt1Timing::MAX`] is the datasheet worst case and the default.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rt1Timing {
    /// Coil on to NO contact closed.
    pub operate: SimTime,
    /// Coil off to NC contact closed.
    pub release: SimTime,
    /// NO contact bounce after it closes.
    pub bounce_no: SimTime,
    /// NC contact bounce after it closes.
    pub bounce_nc: SimTime,
}

impl Rt1Timing {
    /// Datasheet maxima: operate 8 ms, release 6 ms, bounce 4 ms (NO), 6 ms (NC).
    pub const MAX: Rt1Timing = Rt1Timing {
        operate: SimTime::ms(8),
        release: SimTime::ms(6),
        bounce_no: SimTime::ms(4),
        bounce_nc: SimTime::ms(6),
    };

    /// A fast relay (2 ms, 1 ms, no bounce): not from the datasheet. Use it to
    /// check that the firmware does not depend on the relays being slow.
    pub const FAST: Rt1Timing = Rt1Timing {
        operate: SimTime::ms(2),
        release: SimTime::ms(1),
        bounce_no: SimTime::ZERO,
        bounce_nc: SimTime::ZERO,
    };
}

impl Default for Rt1Timing {
    fn default() -> Self {
        Rt1Timing::MAX
    }
}

/// Where the moving contact is.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Contact {
    /// On the NC contact, settled. The rest position.
    #[default]
    Nc,
    /// Just arrived on NC, still bouncing.
    NcBounce,
    /// Just arrived on NO, still bouncing.
    NoBounce,
    /// On the NO contact, settled.
    No,
}

impl Contact {
    /// COM touches NO (settled or bouncing).
    pub fn on_no(self) -> bool {
        matches!(self, Contact::No | Contact::NoBounce)
    }

    /// COM touches NC (settled or bouncing).
    pub fn on_nc(self) -> bool {
        matches!(self, Contact::Nc | Contact::NcBounce)
    }

    /// Not bouncing.
    pub fn settled(self) -> bool {
        matches!(self, Contact::Nc | Contact::No)
    }
}

/// One RT1 relay. Call [`Rt1::update`] at each board step with the coil state.
#[derive(Clone, Debug, Default)]
pub struct Rt1 {
    timing: Rt1Timing,
    coil: bool,
    contact: Contact,
    /// Start of the present wait: the coil change, or the start of a bounce.
    since: SimTime,
}

impl Rt1 {
    /// A relay with its coil off and the contact on NC.
    pub fn new(timing: Rt1Timing) -> Self {
        Rt1 {
            timing,
            ..Rt1::default()
        }
    }

    /// The present contact position.
    pub fn contact(&self) -> Contact {
        self.contact
    }

    /// The coil state at the last update.
    pub fn coil(&self) -> bool {
        self.coil
    }

    /// Apply the coil state at `now` and return the contact position.
    ///
    /// A coil change restarts the wait. A coil that turns off before the operate
    /// time has passed leaves the contact on NC; one that turns off while the
    /// contact is on NO starts the release time from now.
    pub fn update(&mut self, now: SimTime, coil: bool) -> Contact {
        if coil != self.coil {
            self.coil = coil;
            self.since = now;
        }
        let t = self.timing;
        loop {
            let waited = now - self.since;
            let next = match (coil, self.contact) {
                (true, Contact::Nc | Contact::NcBounce) if waited >= t.operate => {
                    Some((Contact::NoBounce, t.operate))
                }
                (true, Contact::NoBounce) if waited >= t.bounce_no => {
                    Some((Contact::No, t.bounce_no))
                }
                (false, Contact::No | Contact::NoBounce) if waited >= t.release => {
                    Some((Contact::NcBounce, t.release))
                }
                (false, Contact::NcBounce) if waited >= t.bounce_nc => {
                    Some((Contact::Nc, t.bounce_nc))
                }
                _ => None,
            };
            match next {
                Some((c, dt)) => {
                    self.contact = c;
                    self.since += dt;
                }
                None => return self.contact,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ms(n: u64) -> SimTime {
        SimTime::ms(n)
    }

    #[test]
    fn operate_bounce_release_at_datasheet_max() {
        let mut k = Rt1::new(Rt1Timing::MAX);
        k.update(ms(10), true);
        assert_eq!(k.update(ms(17), true), Contact::Nc);
        assert_eq!(k.update(ms(18), true), Contact::NoBounce);
        assert_eq!(k.update(ms(21), true), Contact::NoBounce);
        assert_eq!(k.update(ms(22), true), Contact::No);
        k.update(ms(30), false);
        assert_eq!(k.update(ms(35), false), Contact::No);
        assert_eq!(k.update(ms(36), false), Contact::NcBounce);
        assert_eq!(k.update(ms(42), false), Contact::Nc);
    }

    #[test]
    fn a_late_update_passes_all_steps() {
        let mut k = Rt1::new(Rt1Timing::MAX);
        k.update(ms(0), true);
        assert_eq!(k.update(ms(100), true), Contact::No);
    }

    #[test]
    fn short_coil_pulse_does_not_move_the_contact() {
        let mut k = Rt1::new(Rt1Timing::MAX);
        k.update(ms(0), true);
        k.update(ms(5), false);
        assert_eq!(k.update(ms(50), false), Contact::Nc);
    }

    #[test]
    fn coil_off_during_bounce_releases_from_then() {
        let mut k = Rt1::new(Rt1Timing::MAX);
        k.update(ms(0), true);
        assert_eq!(k.update(ms(9), true), Contact::NoBounce);
        k.update(ms(9), false);
        assert_eq!(k.update(ms(14), false), Contact::NoBounce);
        assert_eq!(k.update(ms(15), false), Contact::NcBounce);
    }

    #[test]
    fn contact_helpers() {
        assert!(Contact::NoBounce.on_no() && !Contact::NoBounce.on_nc());
        assert!(Contact::NcBounce.on_nc() && !Contact::NcBounce.settled());
        assert!(Contact::No.settled());
    }
}
