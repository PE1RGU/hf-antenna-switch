//! Virtual time in microseconds. Used both as an instant and as a duration.
//!
//! Virtual time does not follow the wall clock. It moves only when a test or the
//! harness moves it, so a run of 10 s takes milliseconds and gives the same result
//! every time (PLAN.md section 3). The resolution of 1 µs is fine enough for UART
//! byte times (1041 µs at 9600 baud) and the supervisor timing (ms).

use core::fmt;
use core::ops::{Add, AddAssign, Sub};

/// A point in virtual time, or a length of time, in microseconds.
///
/// The field is the count of microseconds since the start of the run (t = 0).
/// Use the constructors [`SimTime::us`], [`SimTime::ms`] and [`SimTime::s`] to
/// make the units clear in the code.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct SimTime(pub u64);

impl SimTime {
    /// The start of the run, or a duration of zero.
    pub const ZERO: SimTime = SimTime(0);

    /// A time of `us` microseconds.
    pub const fn us(us: u64) -> Self {
        SimTime(us)
    }

    /// A time of `ms` milliseconds.
    pub const fn ms(ms: u64) -> Self {
        SimTime(ms * 1_000)
    }

    /// A time of `s` seconds.
    pub const fn s(s: u64) -> Self {
        SimTime(s * 1_000_000)
    }

    /// The time in microseconds.
    pub const fn as_us(self) -> u64 {
        self.0
    }

    /// The time in whole milliseconds. The fraction is cut off (1999 µs gives 1 ms).
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

/// Shows the time in milliseconds with three decimals, for example `12.345 ms`.
impl fmt::Display for SimTime {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{:03} ms", self.0 / 1_000, self.0 % 1_000)
    }
}
