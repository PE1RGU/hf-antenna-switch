//! Virtual time in microseconds. Used both as an instant and as a duration.

use core::fmt;
use core::ops::{Add, AddAssign, Sub};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct SimTime(pub u64);

impl SimTime {
    pub const ZERO: SimTime = SimTime(0);

    pub const fn us(us: u64) -> Self {
        SimTime(us)
    }

    pub const fn ms(ms: u64) -> Self {
        SimTime(ms * 1_000)
    }

    pub const fn s(s: u64) -> Self {
        SimTime(s * 1_000_000)
    }

    pub const fn as_us(self) -> u64 {
        self.0
    }

    pub const fn as_ms(self) -> u64 {
        self.0 / 1_000
    }
}

impl Add for SimTime {
    type Output = SimTime;
    fn add(self, rhs: SimTime) -> SimTime {
        SimTime(self.0 + rhs.0)
    }
}

impl AddAssign for SimTime {
    fn add_assign(&mut self, rhs: SimTime) {
        self.0 += rhs.0;
    }
}

/// Saturating: an earlier minus a later time is zero.
impl Sub for SimTime {
    type Output = SimTime;
    fn sub(self, rhs: SimTime) -> SimTime {
        SimTime(self.0.saturating_sub(rhs.0))
    }
}

impl fmt::Display for SimTime {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{:03} ms", self.0 / 1_000, self.0 % 1_000)
    }
}
