//! Shack interface pin map, as drawn in hardware/shack-interface/gen_shack_sch.py.
//! Direct GPIO: D-83. PCA9539 map: D-92, display pins D-180. SDA select: D-94.

/// I2C address of the PCA9539 (U5).
pub const EXPANDER_ADDR: u8 = 0x74;

/// ESP32-C3 GPIO numbers of the direct lines (D-83, D-180).
pub mod gpio {
    pub const PERMIT_R1: u8 = 0;
    pub const WDI: u8 = 1;
    pub const DISP_SCK: u8 = 2;
    pub const LATCH_CLR: u8 = 3;
    pub const PERMIT_R2: u8 = 4;
    pub const PERMIT_R3: u8 = 5;
    pub const DATA_TX: u8 = 6;
    pub const SCL: u8 = 8;
    pub const DISP_MOSI: u8 = 9;
    pub const DATA_RX: u8 = 20;
    pub const SAFE_LOST: u8 = 21;
}

/// DevKit board revision. It sets the SDA pin (JP61, D-94) and the board LED.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DevKit {
    Rust1,
    Rust2,
}

impl DevKit {
    pub const fn sda(self) -> u8 {
        match self {
            DevKit::Rust1 => 10,
            DevKit::Rust2 => 7,
        }
    }

    /// The board LED sits on the SDA pin of the other revision.
    pub const fn led(self) -> u8 {
        match self {
            DevKit::Rust1 => 7,
            DevKit::Rust2 => 10,
        }
    }
}

/// One PCA9539 pin: bit 0..=15, IO0_0 = 0, IO1_7 = 15.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ExpPin {
    pub bit: u8,
    pub output: bool,
}

const fn out(bit: u8) -> ExpPin {
    ExpPin { bit, output: true }
}

const fn inp(bit: u8) -> ExpPin {
    ExpPin { bit, output: false }
}

/// PCA9539 pins (D-92, D-180).
pub mod exp {
    use super::{ExpPin, inp, out};

    pub const SW_STOP_N: ExpPin = out(0);
    pub const R1_TX: ExpPin = inp(1);
    pub const KEY_R1: ExpPin = out(2);
    pub const BAND_D: ExpPin = inp(3);
    pub const BAND_A: ExpPin = inp(4);
    pub const BAND_B: ExpPin = inp(5);
    pub const BAND_C: ExpPin = inp(6);
    pub const DISP_BL: ExpPin = out(7);
    pub const KEY_R2: ExpPin = out(8);
    pub const R2_TX: ExpPin = inp(9);
    pub const DISP_DC: ExpPin = out(10);
    pub const KEY_R3: ExpPin = out(11);
    pub const R3_TX: ExpPin = inp(12);
    pub const DISP_RST: ExpPin = out(13);
    pub const KILL_S: ExpPin = inp(14);
    pub const LATCHED: ExpPin = inp(15);

    pub const ALL: [ExpPin; 16] = [
        SW_STOP_N, R1_TX, KEY_R1, BAND_D, BAND_A, BAND_B, BAND_C, DISP_BL, KEY_R2, R2_TX, DISP_DC,
        KEY_R3, R3_TX, DISP_RST, KILL_S, LATCHED,
    ];
}

/// PCA9539 configuration word (register 6 low byte, register 7 high byte):
/// 1 = input, 0 = output.
pub const fn expander_config() -> u16 {
    let mut cfg = 0xFFFF;
    let mut i = 0;
    while i < exp::ALL.len() {
        if exp::ALL[i].output {
            cfg &= !(1 << exp::ALL[i].bit);
        }
        i += 1;
    }
    cfg
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_expander_bit_used_once() {
        let mut seen = 0u16;
        for p in exp::ALL {
            assert!(p.bit < 16);
            assert_eq!(seen & (1 << p.bit), 0, "bit {} used twice", p.bit);
            seen |= 1 << p.bit;
        }
        assert_eq!(seen, 0xFFFF);
    }

    #[test]
    fn expander_config_matches_d92() {
        // Outputs: IO0_0, IO0_2, IO0_7, IO1_0, IO1_2, IO1_3, IO1_5.
        assert_eq!(expander_config(), 0b1101_0010_0111_1010);
    }

    #[test]
    fn devkit_sda_and_led_swap() {
        for kit in [DevKit::Rust1, DevKit::Rust2] {
            assert_ne!(kit.sda(), kit.led());
            assert_ne!(kit.sda(), gpio::SCL);
        }
        assert_eq!(DevKit::Rust1.sda(), DevKit::Rust2.led());
    }
}
