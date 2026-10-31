//! Crossbar state check, rule F6 (logic-verification.md section 7 and 11).
//!
//! No hardware interlock covers H1, H2 and H4, so the firmware checks every
//! requested state before a relay moves. The hazards, per antenna column:
//!
//! - H1: two TX rows on one column.
//! - H2: a TX row and a row of another radio on one column (TX power into that radio).
//! - H3: a TX row on the receive-only column (A2, D-103).
//! - H4: a TX row on a column with K1 off (open line).
//!
//! One TX and one RX row per radio needs no check here: a [`Route`] holds one
//! column of each. The EXP column belongs to one radio's own EXP rows, so it has no
//! hazard. The bias-T rule (verify_logic.py section 10, rule 8) adds one more: no
//! bias-T feed on a column with a TX row.
//!
//! ```
//! use box_core::crossbar::{Hazard, check, used_columns};
//! use link_proto::{Col, ColMask, Route};
//!
//! let r1 = Route { tx: Col::A1, rx: Col::A1 };
//! let r2 = Route { tx: Col::None, rx: Col::A1 };
//! let routes = [r1, r2, Route::default()];
//! let k1 = used_columns(&routes);
//! assert_eq!(check(&routes, k1, ColMask::EMPTY), Err(Hazard::TxIntoRadio(Col::A1)));
//! ```

use crate::board::RX_ONLY;
use link_proto::{Col, ColMask, Radio, Route};

/// The four antenna columns. EXP has no K1 and no hazard.
pub const ANTENNAS: [Col; 4] = [Col::A1, Col::A2, Col::A3, Col::A4];

/// The first rule a state breaks.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Hazard {
    /// H1: two TX rows on this column.
    TwoTx(Col),
    /// H2: a TX row and a row of another radio on this column.
    TxIntoRadio(Col),
    /// H3: a TX row on the receive-only column.
    TxOnRxOnly(Col),
    /// H4: a TX row on this column, K1 off.
    TxOpenLine(Col),
    /// Bias-T feed on a column with a TX row (rule 8).
    BiasOnTx(Col),
}

/// The rows on one antenna column, per radio R1..R3, and its K1.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Column {
    /// TX row closed, per radio.
    pub tx: [bool; 3],
    /// RX row closed, per radio.
    pub rx: [bool; 3],
    /// K1 on: the antenna is on the column.
    pub k1: bool,
    /// This is the receive-only column.
    pub rx_only: bool,
}

/// Which of H1 to H4 a column breaks. More than one can be true.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Breaks {
    /// H1.
    pub h1: bool,
    /// H2.
    pub h2: bool,
    /// H3.
    pub h3: bool,
    /// H4.
    pub h4: bool,
}

impl Breaks {
    /// No hazard.
    pub fn none(self) -> bool {
        self == Breaks::default()
    }
}

impl Column {
    /// The rows of `col` in `routes`, with K1 from `k1`.
    pub fn of(routes: &[Route; 3], k1: ColMask, col: Col) -> Self {
        Column {
            tx: routes.map(|r| r.tx == col),
            rx: routes.map(|r| r.rx == col),
            k1: k1.contains(col),
            rx_only: col == RX_ONLY,
        }
    }

    /// Check the column against H1 to H4 (`is_state_allowed()` of
    /// logic-verification.md section 11, per column).
    pub fn breaks(&self) -> Breaks {
        let n_tx = self.tx.iter().filter(|&&t| t).count();
        let other_row = |r: usize| (0..3).any(|o| o != r && (self.tx[o] || self.rx[o]));
        let any_tx = n_tx > 0;
        Breaks {
            h1: n_tx > 1,
            h2: (0..3).any(|r| self.tx[r] && other_row(r)),
            h3: any_tx && self.rx_only,
            h4: any_tx && !self.k1,
        }
    }
}

/// The antenna columns (A1..A4) that any route uses for TX or RX: the columns
/// whose K1 must be on.
pub fn used_columns(routes: &[Route; 3]) -> ColMask {
    ANTENNAS
        .into_iter()
        .filter(|&c| routes.iter().any(|r| r.tx == c || r.rx == c))
        .fold(ColMask::EMPTY, ColMask::with)
}

/// The TX columns of all routes.
pub fn tx_columns(routes: &[Route; 3]) -> ColMask {
    routes.iter().fold(ColMask::EMPTY, |m, r| m.with(r.tx))
}

/// Check a complete state: the routes of R1..R3, the columns with K1 on and the
/// columns with the bias-T on. `Ok` = no hazard.
pub fn check(routes: &[Route; 3], k1: ColMask, bias: ColMask) -> Result<(), Hazard> {
    for col in ANTENNAS {
        let b = Column::of(routes, k1, col).breaks();
        let hazard = if b.h1 {
            Hazard::TwoTx(col)
        } else if b.h2 {
            Hazard::TxIntoRadio(col)
        } else if b.h3 {
            Hazard::TxOnRxOnly(col)
        } else if b.h4 {
            Hazard::TxOpenLine(col)
        } else if bias.contains(col) && tx_columns(routes).contains(col) {
            Hazard::BiasOnTx(col)
        } else {
            continue;
        };
        return Err(hazard);
    }
    Ok(())
}

/// `routes` with the route of `radio` replaced by `route`.
pub fn with_route(routes: &[Route; 3], radio: Radio, route: Route) -> [Route; 3] {
    let mut r = *routes;
    r[radio.index()] = route;
    r
}

#[cfg(test)]
mod tests {
    use super::*;

    /// All 128 row and K1 states of one column.
    fn all_states(rx_only: bool) -> impl Iterator<Item = Column> {
        (0u8..128).map(move |s| Column {
            tx: [s & 1 != 0, s & 2 != 0, s & 4 != 0],
            rx: [s & 8 != 0, s & 16 != 0, s & 32 != 0],
            k1: s & 64 != 0,
            rx_only,
        })
    }

    #[test]
    fn counts_match_logic_verification_section_7() {
        // (allowed, H1, H2, H3, H4) for A1, A3, A4, then A2.
        for (rx_only, want) in [
            (false, (22, 64, 100, 0, 56)),
            (true, (16, 64, 100, 112, 56)),
        ] {
            let mut n = (0, 0, 0, 0, 0);
            for c in all_states(rx_only) {
                let b = c.breaks();
                n.0 += usize::from(b.none());
                n.1 += usize::from(b.h1);
                n.2 += usize::from(b.h2);
                n.3 += usize::from(b.h3);
                n.4 += usize::from(b.h4);
            }
            assert_eq!(n, want, "rx_only {rx_only}");
        }
    }

    fn route(tx: Col, rx: Col) -> Route {
        Route { tx, rx }
    }

    #[test]
    fn state_check() {
        let none = Route::default();
        let ok = [
            route(Col::A1, Col::A1),
            route(Col::A3, Col::A2),
            route(Col::None, Col::A2),
        ];
        assert_eq!(check(&ok, used_columns(&ok), ColMask::EMPTY), Ok(()));
        // Shared RX antenna, K1 off: allowed (no TX row).
        let rx = [route(Col::None, Col::A4), route(Col::None, Col::A4), none];
        assert_eq!(check(&rx, ColMask::EMPTY, ColMask::EMPTY), Ok(()));

        let two_tx = [route(Col::A3, Col::None), route(Col::A3, Col::None), none];
        let k = used_columns(&two_tx);
        assert_eq!(
            check(&two_tx, k, ColMask::EMPTY),
            Err(Hazard::TwoTx(Col::A3))
        );
        let a2 = [none, route(Col::A2, Col::A1), none];
        let k = used_columns(&a2);
        assert_eq!(
            check(&a2, k, ColMask::EMPTY),
            Err(Hazard::TxOnRxOnly(Col::A2))
        );
        let open = [route(Col::A4, Col::A4), none, none];
        assert_eq!(
            check(&open, ColMask::EMPTY, ColMask::EMPTY),
            Err(Hazard::TxOpenLine(Col::A4))
        );
        let bias = ColMask::EMPTY.with(Col::A1);
        let k = used_columns(&ok);
        assert_eq!(check(&ok, k, bias), Err(Hazard::BiasOnTx(Col::A1)));
        // EXP is no antenna column: two radios on EXP rows is no hazard.
        let exp = [route(Col::Exp, Col::Exp), route(Col::Exp, Col::None), none];
        assert_eq!(check(&exp, ColMask::EMPTY, ColMask::EMPTY), Ok(()));
    }

    #[test]
    fn helpers() {
        let routes = [
            route(Col::A1, Col::A2),
            route(Col::Exp, Col::A4),
            Route::default(),
        ];
        assert_eq!(used_columns(&routes).bits(), 0b1011);
        assert_eq!(tx_columns(&routes).bits(), 0b10001);
        let r = with_route(&routes, Radio::R3, route(Col::A3, Col::A3));
        assert_eq!(r[2], route(Col::A3, Col::A3));
    }
}
