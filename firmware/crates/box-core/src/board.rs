//! Box pin map, as drawn in hardware/unit (RF board rf14.xml, controller board
//! ctl14.xml). Expander pins: RF board sheet "IO expanders" (D-49, D-63, D-121).
//! Direct GPIO: controller board sheet "MCU and safety gate" (D-55, D-59, D-62).
//!
//! The four PCA9539 expanders sit on the RF board, on one bus from J14. Their
//! RESET is RLY_EN (the output of the safety gate), so every stop of the gate puts
//! all their pins back to inputs, and the 100k gate pull-downs hold every coil off
//! (verify_logic.py section 4). The relay layout is the same on U901 to U903: one
//! expander per radio, TX row on IO0_0 to IO0_4, RX row on IO0_5 to IO1_1.
//!
//! ```
//! use box_core::board::{exp, row_relay};
//! use link_proto::{Col, Radio};
//!
//! let p = row_relay(Radio::R2, false, Col::A3).unwrap();
//! assert_eq!((p.addr, p.bit, p.name), (0x75, 7, "R2_RX3_DRV"));
//! assert_eq!(exp::ALL.len(), 64);
//! ```

use link_proto::{Col, Radio};

/// U901 (0x74): R1 TX and RX rows, K1 of A1 and A2, RF detectors A1 and A2.
pub const ADDR_U901: u8 = 0x74;
/// U902 (0x75): R2 TX and RX rows, K1 of A3 and A4, RF detectors A3 and A4.
pub const ADDR_U902: u8 = 0x75;
/// U903 (0x76): R3 TX and RX rows, the K0 lines, TX_ANY read-back.
pub const ADDR_U903: u8 = 0x76;
/// U1001 (0x77): bias-T enables and their OK read-back.
pub const ADDR_U1001: u8 = 0x77;
/// All four expander addresses, in address order.
pub const EXPANDERS: [u8; 4] = [ADDR_U901, ADDR_U902, ADDR_U903, ADDR_U1001];

/// The receive-only column on unit 1: its TX relays and drivers are not fitted
/// (D-103, SR-01).
pub const RX_ONLY: Col = Col::A2;

/// ESP32-C3 GPIO numbers of the direct lines on the controller board.
pub mod gpio {
    /// IO0, input: EXP_INT, the wired-OR INT of the four expanders (10k pull-up on
    /// the RF board). Low = an input pin changed since its port was last read.
    pub const EXP_INT: u8 = 0;
    /// IO1, output: supervisor watchdog input. R61 1k to GND, so a floating pin
    /// reads low and the watchdog trips (verify_logic.py section 3).
    pub const WDI: u8 = 1;
    /// IO3, output: fault latch clear. One rising edge after the start-up checks
    /// (D-59). R62 100k pull-down.
    pub const LATCH_CLR: u8 = 3;
    /// IO4, output: MCU_EN_N, active low: low asks for RLY_EN. R63 100k pull-up,
    /// so a floating pin keeps the relays off (D-59).
    pub const MCU_EN_N: u8 = 4;
    /// IO5, input: KILL. High = no SAFE loop current (U3 opto off, R34 pull-up).
    pub const KILL: u8 = 5;
    /// IO6, input: FAULT, the fault latch U13 Q, through R66 1k (D-191). High =
    /// the supervisor tripped and the latch was not cleared since.
    pub const FAULT: u8 = 6;
    /// IO8: I2C clock to the RF board (both DevKit revisions).
    pub const SCL: u8 = 8;
    /// IO20, input: UART RX of the shack link (pair 1).
    pub const DATA_RX: u8 = 20;
    /// IO21, output: UART TX of the shack link (pair 4).
    pub const DATA_TX: u8 = 21;
}

/// One expander pin.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ExpPin {
    /// I2C address of the expander.
    pub addr: u8,
    /// Bit number in the 16-bit port word: port 0 is bits 0 to 7, port 1 is
    /// bits 8 to 15.
    pub bit: u8,
    /// `true` = output (configuration bit 0), `false` = input.
    pub output: bool,
    /// Net name in the schematic.
    pub name: &'static str,
}

macro_rules! pins {
    ($($id:ident = $addr:ident, $bit:literal, $out:literal, $name:literal, $doc:literal;)*) => {
        $(
            #[doc = concat!("`", $name, "`: ", $doc)]
            pub const $id: ExpPin = ExpPin { addr: super::$addr, bit: $bit, output: $out, name: $name };
        )*
        /// All 64 pins, by expander and bit. A test checks that each bit is used once.
        pub const ALL: [ExpPin; 64] = [$($id),*];
    };
}

/// The 64 expander pins. Coil drivers are outputs; high = coil on.
pub mod exp {
    use super::ExpPin;

    pins! {
        R1_TX1 = ADDR_U901, 0, true, "R1_TX1_DRV", "R1 TX row to A1 (K102).";
        R1_TX2 = ADDR_U901, 1, true, "R1_TX2_DRV", "R1 TX row to A2: relay K103 not fitted (D-103). Keep low.";
        R1_TX3 = ADDR_U901, 2, true, "R1_TX3_DRV", "R1 TX row to A3 (K104).";
        R1_TX4 = ADDR_U901, 3, true, "R1_TX4_DRV", "R1 TX row to A4 (K105).";
        R1_TXE = ADDR_U901, 4, true, "R1_TXE_DRV", "R1 TX row to EXP (K106).";
        R1_RX1 = ADDR_U901, 5, true, "R1_RX1_DRV", "R1 RX row to A1 (K107).";
        R1_RX2 = ADDR_U901, 6, true, "R1_RX2_DRV", "R1 RX row to A2 (K108).";
        R1_RX3 = ADDR_U901, 7, true, "R1_RX3_DRV", "R1 RX row to A3 (K109).";
        R1_RX4 = ADDR_U901, 8, true, "R1_RX4_DRV", "R1 RX row to A4 (K110).";
        R1_RXE = ADDR_U901, 9, true, "R1_RXE_DRV", "R1 RX row to EXP (K111).";
        A1_K1 = ADDR_U901, 10, true, "A1_K1_DRV", "A1 K1 (K401): high = antenna on the column, low = parked on the bleed.";
        A2_K1 = ADDR_U901, 11, true, "A2_K1_DRV", "A2 K1 (K501).";
        A1_RFDET = ADDR_U901, 12, false, "A1_RFDET", "A1 RF detector. Low = RF on the column (D-47).";
        A2_RFDET = ADDR_U901, 13, false, "A2_RFDET", "A2 RF detector. Low = RF; also opens the SAFE loop in hardware (D-104).";
        U901_SP6 = ADDR_U901, 14, true, "U901_IO1_6", "Spare, 10k to GND. Output driving 0 (F8).";
        U901_SP7 = ADDR_U901, 15, true, "U901_IO1_7", "Spare, 10k to GND. Output driving 0 (F8).";

        R2_TX1 = ADDR_U902, 0, true, "R2_TX1_DRV", "R2 TX row to A1 (K202).";
        R2_TX2 = ADDR_U902, 1, true, "R2_TX2_DRV", "R2 TX row to A2: relay K203 not fitted (D-103). Keep low.";
        R2_TX3 = ADDR_U902, 2, true, "R2_TX3_DRV", "R2 TX row to A3 (K204).";
        R2_TX4 = ADDR_U902, 3, true, "R2_TX4_DRV", "R2 TX row to A4 (K205).";
        R2_TXE = ADDR_U902, 4, true, "R2_TXE_DRV", "R2 TX row to EXP (K206).";
        R2_RX1 = ADDR_U902, 5, true, "R2_RX1_DRV", "R2 RX row to A1 (K207).";
        R2_RX2 = ADDR_U902, 6, true, "R2_RX2_DRV", "R2 RX row to A2 (K208).";
        R2_RX3 = ADDR_U902, 7, true, "R2_RX3_DRV", "R2 RX row to A3 (K209).";
        R2_RX4 = ADDR_U902, 8, true, "R2_RX4_DRV", "R2 RX row to A4 (K210).";
        R2_RXE = ADDR_U902, 9, true, "R2_RXE_DRV", "R2 RX row to EXP (K211).";
        A3_K1 = ADDR_U902, 10, true, "A3_K1_DRV", "A3 K1 (K601).";
        A4_K1 = ADDR_U902, 11, true, "A4_K1_DRV", "A4 K1 (K701).";
        A3_RFDET = ADDR_U902, 12, false, "A3_RFDET", "A3 RF detector. Low = RF on the column.";
        A4_RFDET = ADDR_U902, 13, false, "A4_RFDET", "A4 RF detector. Low = RF on the column.";
        U902_SP6 = ADDR_U902, 14, true, "U902_IO1_6", "Spare, 10k to GND. Output driving 0 (F8).";
        U902_SP7 = ADDR_U902, 15, true, "U902_IO1_7", "Spare, 10k to GND. Output driving 0 (F8).";

        R3_TX1 = ADDR_U903, 0, true, "R3_TX1_DRV", "R3 TX row to A1 (K302).";
        R3_TX2 = ADDR_U903, 1, true, "R3_TX2_DRV", "R3 TX row to A2: relay K303 not fitted (D-103). Keep low.";
        R3_TX3 = ADDR_U903, 2, true, "R3_TX3_DRV", "R3 TX row to A3 (K304).";
        R3_TX4 = ADDR_U903, 3, true, "R3_TX4_DRV", "R3 TX row to A4 (K305).";
        R3_TXE = ADDR_U903, 4, true, "R3_TXE_DRV", "R3 TX row to EXP (K306).";
        R3_RX1 = ADDR_U903, 5, true, "R3_RX1_DRV", "R3 RX row to A1 (K307).";
        R3_RX2 = ADDR_U903, 6, true, "R3_RX2_DRV", "R3 RX row to A2 (K308).";
        R3_RX3 = ADDR_U903, 7, true, "R3_RX3_DRV", "R3 RX row to A3 (K309).";
        R3_RX4 = ADDR_U903, 8, true, "R3_RX4_DRV", "R3 RX row to A4 (K310).";
        R3_RXE = ADDR_U903, 9, true, "R3_RXE_DRV", "R3 RX row to EXP (K311).";
        R1_K0 = ADDR_U903, 10, false, "R1_K0_DRV", "R1 K0 read-back. Driven by TX_ANY through R51: must stay an input (F3).";
        R2_K0 = ADDR_U903, 11, true, "R2_K0_DRV", "R2 K0 (K201): high = TX row. Only after the handshake (D-63).";
        R3_K0 = ADDR_U903, 12, true, "R3_K0_DRV", "R3 K0 (K301): high = TX row. Only after the handshake (D-63).";
        TX_ANY = ADDR_U903, 13, false, "TX_ANY", "PTT loop read-back: high = R1 keyed (F4). Must stay an input (F3).";
        U903_SP6 = ADDR_U903, 14, true, "U903_IO1_6", "Spare, 10k to GND. Output driving 0 (F8).";
        U903_SP7 = ADDR_U903, 15, true, "U903_IO1_7", "Spare, 10k to GND. Output driving 0 (F8).";

        A1_BIAS_EN = ADDR_U1001, 0, true, "A1_BIAS_EN", "A1 bias-T feed on.";
        A2_BIAS_EN = ADDR_U1001, 1, true, "A2_BIAS_EN", "A2 bias-T feed on (the RX loop, A-10).";
        A3_BIAS_EN = ADDR_U1001, 2, true, "A3_BIAS_EN", "A3 bias-T feed on.";
        A4_BIAS_EN = ADDR_U1001, 3, true, "A4_BIAS_EN", "A4 bias-T feed on.";
        A1_BIAS_OK = ADDR_U1001, 4, false, "A1_BIAS_OK", "A1 bias-T output present. EN high and OK low = fault (D-54).";
        A2_BIAS_OK = ADDR_U1001, 5, false, "A2_BIAS_OK", "A2 bias-T output present.";
        A3_BIAS_OK = ADDR_U1001, 6, false, "A3_BIAS_OK", "A3 bias-T output present.";
        A4_BIAS_OK = ADDR_U1001, 7, false, "A4_BIAS_OK", "A4 bias-T output present.";
        U1001_SP0 = ADDR_U1001, 8, true, "U1001_IO1_0", "Spare, 10k to GND. Output driving 0 (F8).";
        U1001_SP1 = ADDR_U1001, 9, true, "U1001_IO1_1", "Spare, 10k to GND. Output driving 0 (F8).";
        U1001_SP2 = ADDR_U1001, 10, true, "U1001_IO1_2", "Spare, 10k to GND. Output driving 0 (F8).";
        U1001_SP3 = ADDR_U1001, 11, true, "U1001_IO1_3", "Spare, 10k to GND. Output driving 0 (F8).";
        U1001_SP4 = ADDR_U1001, 12, true, "U1001_IO1_4", "Spare, 10k to GND. Output driving 0 (F8).";
        U1001_SP5 = ADDR_U1001, 13, true, "U1001_IO1_5", "Spare, 10k to GND. Output driving 0 (F8).";
        U1001_SP6 = ADDR_U1001, 14, true, "U1001_IO1_6", "Spare, 10k to GND. Output driving 0 (F8).";
        U1001_SP7 = ADDR_U1001, 15, true, "U1001_IO1_7", "Spare, 10k to GND. Output driving 0 (F8).";
    }
}

/// Index of a column in a row: A1..A4 = 0..3, EXP = 4. `None` for [`Col::None`].
pub fn col_index(col: Col) -> Option<usize> {
    match col {
        Col::None => None,
        c => Some(c as usize - 1),
    }
}

/// Expander address of a radio's rows.
pub fn row_expander(r: Radio) -> u8 {
    EXPANDERS[r.index()]
}

/// The coil driver of one row relay: radio `r`, TX row (`tx`) or RX row, column
/// `col`. `None` for [`Col::None`].
///
/// The TX relay at [`RX_ONLY`] has a pin but no relay; see [`relay_fitted`].
pub fn row_relay(r: Radio, tx: bool, col: Col) -> Option<ExpPin> {
    let c = col_index(col)?;
    Some(exp::ALL[r.index() * 16 + if tx { 0 } else { 5 } + c])
}

/// False for the TX relays at the receive-only column (D-103). Their pin exists;
/// setting it does nothing in hardware, and the firmware must never ask for it.
pub fn relay_fitted(tx: bool, col: Col) -> bool {
    !(tx && col == RX_ONLY)
}

/// The K1 driver of antenna column `col` (A1..A4). `None` for EXP and `None`.
pub fn k1(col: Col) -> Option<ExpPin> {
    match col {
        Col::A1 => Some(exp::A1_K1),
        Col::A2 => Some(exp::A2_K1),
        Col::A3 => Some(exp::A3_K1),
        Col::A4 => Some(exp::A4_K1),
        _ => None,
    }
}

/// The RF detector input of antenna column `col` (A1..A4).
pub fn rf_det(col: Col) -> Option<ExpPin> {
    match col {
        Col::A1 => Some(exp::A1_RFDET),
        Col::A2 => Some(exp::A2_RFDET),
        Col::A3 => Some(exp::A3_RFDET),
        Col::A4 => Some(exp::A4_RFDET),
        _ => None,
    }
}

/// The K0 pin of a radio. For R1 this is the read-back input (K0 follows the PTT
/// loop in hardware); for R2 and R3 the driver output.
pub fn k0(r: Radio) -> ExpPin {
    [exp::R1_K0, exp::R2_K0, exp::R3_K0][r.index()]
}

/// Bias-T enable and OK pins of antenna column `col` (A1..A4).
pub fn bias(col: Col) -> Option<(ExpPin, ExpPin)> {
    let i = col_index(col).filter(|&i| i < 4)?;
    Some((exp::ALL[48 + i], exp::ALL[52 + i]))
}

/// PCA9539 configuration word of the expander at `addr`: 1 = input, 0 = output.
/// Computed from [`exp::ALL`]. An unknown address gives 0xFFFF (all inputs).
pub const fn expander_config(addr: u8) -> u16 {
    let mut cfg = 0xFFFF;
    let mut i = 0;
    while i < exp::ALL.len() {
        let p = exp::ALL[i];
        if p.addr == addr && p.output {
            cfg &= !(1 << p.bit);
        }
        i += 1;
    }
    cfg
}

#[cfg(test)]
mod tests {
    extern crate std;
    use super::*;
    use std::format;

    #[test]
    fn every_expander_bit_used_once() {
        for (n, addr) in EXPANDERS.iter().enumerate() {
            let mut seen = 0u16;
            for p in exp::ALL.iter().filter(|p| p.addr == *addr) {
                assert_eq!(seen & (1 << p.bit), 0, "{} bit {} twice", addr, p.bit);
                seen |= 1 << p.bit;
            }
            assert_eq!(seen, 0xFFFF);
            // ALL is in expander order, 16 per expander, in bit order.
            for (b, p) in exp::ALL[n * 16..n * 16 + 16].iter().enumerate() {
                assert_eq!((p.addr, p.bit as usize), (*addr, b));
            }
        }
    }

    #[test]
    fn row_layout_matches_the_netlist() {
        for r in Radio::ALL {
            for (tx, row) in [(true, "TX"), (false, "RX")] {
                for (col, c) in [(Col::A1, "1"), (Col::A4, "4"), (Col::Exp, "E")] {
                    let p = row_relay(r, tx, col).unwrap();
                    assert_eq!(p.name, format!("R{}_{row}{c}_DRV", r as u8));
                    assert!(p.output);
                }
            }
        }
        assert_eq!(row_relay(Radio::R1, true, Col::None), None);
        assert!(!relay_fitted(true, Col::A2) && relay_fitted(false, Col::A2));
    }

    #[test]
    fn readback_pins_stay_inputs() {
        // F3: R1_K0_DRV and TX_ANY share their nets with the U5 output.
        let cfg = expander_config(ADDR_U903);
        assert_ne!(cfg & (1 << exp::R1_K0.bit), 0);
        assert_ne!(cfg & (1 << exp::TX_ANY.bit), 0);
        assert_eq!(cfg & (1 << exp::R2_K0.bit), 0);
        assert_eq!(expander_config(ADDR_U1001), 0x00F0);
        assert_eq!(expander_config(ADDR_U901), 0x3000);
    }

    #[test]
    fn helpers() {
        assert_eq!(k1(Col::A3), Some(exp::A3_K1));
        assert_eq!(k1(Col::Exp), None);
        assert_eq!(rf_det(Col::A2), Some(exp::A2_RFDET));
        assert_eq!(k0(Radio::R3), exp::R3_K0);
        assert_eq!(bias(Col::A2), Some((exp::A2_BIAS_EN, exp::A2_BIAS_OK)));
        assert_eq!(bias(Col::Exp), None);
        assert_eq!(row_expander(Radio::R2), ADDR_U902);
    }
}
