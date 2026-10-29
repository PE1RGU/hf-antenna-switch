//! 74LVC1G74 D flip-flop with preset and clear, as used for the fault latch and the SAFE latch.
//!
//! PRE_N low: Q = 1. CLR_N low: Q = 0. Both low: Q = 1 (and Q_N = 1).
//! Both high: Q takes D on a rising CLK edge.
//!
//! On the shack board both latches have D tied low, so a clock edge clears Q and
//! a low PRE_N sets it (verify_system.py section 3):
//! - Fault latch (D-59): PRE_N = RESET_N, CLK = LATCH_CLR. Q = FAULT.
//! - SAFE latch (D-75, D-84): PRE_N = SAFE_OK AND POR_N, CLK = RESET button.
//!   Q = LATCHED.
//!
//! Propagation delay and set-up time are not modelled.

/// One 74LVC1G74 flip-flop. Call [`Lvc1g74::update`] with the input levels at
/// each board step.
#[derive(Clone, Debug)]
pub struct Lvc1g74 {
    q: bool,
    last_clk: bool,
}

impl Default for Lvc1g74 {
    fn default() -> Self {
        Self::new()
    }
}

impl Lvc1g74 {
    /// A flip-flop at power-up, with Q = 1 (see [`Lvc1g74::power_off`]).
    pub fn new() -> Self {
        Lvc1g74 {
            q: true,
            last_clk: false,
        }
    }

    /// Apply the present input levels and return Q.
    ///
    /// The model finds a rising CLK edge by comparing `clk` with the level at the
    /// last call. So call it at every step, also when nothing seems to change.
    /// PRE_N wins over CLR_N.
    pub fn update(&mut self, pre_n: bool, clr_n: bool, clk: bool, d: bool) -> bool {
        let rising = clk && !self.last_clk;
        self.last_clk = clk;
        match (pre_n, clr_n) {
            (false, _) => self.q = true,
            (true, false) => self.q = false,
            (true, true) if rising => self.q = d,
            _ => {}
        }
        self.q
    }

    /// No supply: the state is lost. Set to 1; in both uses PRE_N is low at power-up anyway.
    pub fn power_off(&mut self) {
        *self = Lvc1g74::new();
    }

    /// Present output Q, without an update.
    pub fn q(&self) -> bool {
        self.q
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truth_table() {
        let mut f = Lvc1g74::new();
        assert!(f.update(false, true, false, false));
        assert!(!f.update(true, false, false, true));
        assert!(f.update(false, false, false, false));
        // Rising edge clocks D.
        assert!(f.update(true, true, false, false));
        assert!(!f.update(true, true, true, false));
        // Held clock: no further change.
        f.update(true, true, false, true);
        assert!(f.update(true, true, true, true));
        assert!(f.update(true, true, true, false), "no edge, Q holds");
        // Edge while PRE_N low has no effect.
        f.update(true, true, false, false);
        assert!(f.update(false, true, true, false));
    }
}
