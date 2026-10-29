//! TI TPS3823A-33 supervisor with watchdog (SLVS165O, C-19).
//!
//! RESET_N is low while VDD is below the threshold, and for td after VDD returns.
//! Watchdog: any edge on WDI restarts the timer; no edge for tout asserts RESET_N for td.
//! WDI floating (open) disables the watchdog.

use sim_core::SimTime;

/// Datasheet corner for the timing values.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Corner {
    Min,
    #[default]
    Typ,
    Max,
}

impl Corner {
    /// Reset time-out td: 120 / 200 / 300 ms.
    pub fn td(self) -> SimTime {
        SimTime::ms(match self {
            Corner::Min => 120,
            Corner::Typ => 200,
            Corner::Max => 300,
        })
    }

    /// Watchdog time-out tout: 0.9 / 1.6 / 2.5 s.
    pub fn tout(self) -> SimTime {
        SimTime::ms(match self {
            Corner::Min => 900,
            Corner::Typ => 1600,
            Corner::Max => 2500,
        })
    }
}

#[derive(Clone, Debug)]
pub struct Tps3823 {
    corner: Corner,
    powered: bool,
    reset_until: Option<SimTime>,
    last_wdi: Option<bool>,
    last_kick: SimTime,
}

impl Tps3823 {
    pub fn new(corner: Corner) -> Self {
        Tps3823 {
            corner,
            powered: false,
            reset_until: None,
            last_wdi: None,
            last_kick: SimTime::ZERO,
        }
    }

    /// Returns RESET_N. `wdi` None = pin open (watchdog off).
    pub fn update(&mut self, now: SimTime, vdd_ok: bool, wdi: Option<bool>) -> bool {
        if !vdd_ok {
            self.powered = false;
            return false;
        }
        if !self.powered {
            self.powered = true;
            self.reset_until = Some(now + self.corner.td());
        }
        if let Some(until) = self.reset_until {
            self.last_wdi = wdi;
            if now < until {
                return false;
            }
            self.reset_until = None;
            self.last_kick = now;
        }
        if let Some(w) = wdi {
            if self.last_wdi != Some(w) {
                self.last_kick = now;
            }
            self.last_wdi = Some(w);
            if now - self.last_kick >= self.corner.tout() {
                self.reset_until = Some(now + self.corner.td());
                return false;
            }
        } else {
            self.last_wdi = None;
        }
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(
        s: &mut Tps3823,
        from: u64,
        to: u64,
        wdi: impl Fn(u64) -> Option<bool>,
    ) -> Vec<(u64, bool)> {
        let mut out = Vec::new();
        let mut last = None;
        for ms in from..to {
            let r = s.update(SimTime::ms(ms), true, wdi(ms));
            if last != Some(r) {
                out.push((ms, r));
                last = Some(r);
            }
        }
        out
    }

    #[test]
    fn power_up_holds_reset_for_td() {
        let mut s = Tps3823::new(Corner::Typ);
        assert_eq!(run(&mut s, 0, 500, |_| None), [(0, false), (200, true)]);
    }

    #[test]
    fn watchdog_times_out_without_edges() {
        let mut s = Tps3823::new(Corner::Min);
        // Release at 120 ms, then no edge: reset at 120 + 900, released 120 ms later.
        assert_eq!(
            run(&mut s, 0, 1300, |_| Some(false)),
            [(0, false), (120, true), (1020, false), (1140, true)]
        );
    }

    #[test]
    fn kicks_every_250_ms_keep_it_quiet() {
        let mut s = Tps3823::new(Corner::Min);
        let r = run(&mut s, 0, 10_000, |ms| Some((ms / 250) % 2 == 1));
        assert_eq!(r, [(0, false), (120, true)]);
    }

    #[test]
    fn brown_out_restarts_td() {
        let mut s = Tps3823::new(Corner::Typ);
        run(&mut s, 0, 300, |_| None);
        assert!(!s.update(SimTime::ms(300), false, None));
        assert!(!s.update(SimTime::ms(301), true, None));
        assert!(!s.update(SimTime::ms(500), true, None));
        assert!(s.update(SimTime::ms(501), true, None));
    }
}
