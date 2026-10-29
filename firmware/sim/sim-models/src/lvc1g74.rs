//! 74LVC1G74 D flip-flop with preset and clear, as used for the fault latch and the SAFE latch.
//!
//! PRE_N low: Q = 1. CLR_N low: Q = 0. Both low: Q = 1 (and Q_N = 1).
//! Both high: Q takes D on a rising CLK edge.

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
    pub fn new() -> Self {
        Lvc1g74 {
            q: true,
            last_clk: false,
        }
    }

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
