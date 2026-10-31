//! Shack interface pin map, as drawn in hardware/shack-interface/gen_shack_sch.py.
//! Direct GPIO: D-83. PCA9539 map: D-92, display pins D-180. SDA select: D-94.
//!
//! The safety lines that must react fast (PERMIT, WDI, LATCH_CLR, SAFE_LOST) and
//! the box link are on direct ESP32-C3 GPIO. The slow lines (keys, TX sense, band
//! data, KILL, LATCHED, display control) are on the PCA9539 expander U5, which the
//! logic polls every tick (10 ms). The expander RESET is the supervisor RESET_N, so
//! a watchdog or brown-out reset sets all its pins back to inputs.

/// I2C address of the PCA9539 (U5).
pub const EXPANDER_ADDR: u8 = 0x74;

/// ESP32-C3 GPIO numbers of the direct lines (D-83, D-180).
pub mod gpio {
    /// IO0, output: PERMIT_R1. High = R1 may transmit (C-1).
    pub const PERMIT_R1: u8 = 0;
    /// IO1, output: supervisor watchdog input. Toggled every tick (D-59).
    pub const WDI: u8 = 1;
    /// IO2, output: display SPI clock (D-180). Strapping pin; the display input is
    /// high impedance, so the boot strap keeps its pull-up.
    pub const DISP_SCK: u8 = 2;
    /// IO3, output: fault latch clear. One rising edge after start-up (D-59).
    pub const LATCH_CLR: u8 = 3;
    /// IO4, output: PERMIT_R2. High only while the box reports the permit (D-63).
    pub const PERMIT_R2: u8 = 4;
    /// IO5, output: PERMIT_R3. High only while the box reports the permit (D-63).
    pub const PERMIT_R3: u8 = 5;
    /// IO6, output: UART TX of the box link (9600 8N1).
    pub const DATA_TX: u8 = 6;
    /// IO8: I2C clock to the PCA9539 (both DevKit revisions).
    pub const SCL: u8 = 8;
    /// IO9, output: display SPI data (D-180). Strapping pin (BOOT).
    pub const DISP_MOSI: u8 = 9;
    /// IO20, input: UART RX of the box link.
    pub const DATA_RX: u8 = 20;
    /// IO21, input: high = no SAFE loop current. 1k series resistor against the
    /// boot-ROM log.
    pub const SAFE_LOST: u8 = 21;
}

/// DevKit board revision. It sets the SDA pin (JP61, D-94) and the board LED.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DevKit {
    /// ESP32-C3-DevKit-RUST-1: SDA on GPIO10, LED on GPIO7. JP61 as delivered (1-2 bridged by copper, D-192).
    Rust1,
    /// ESP32-C3-DevKit-RUST-2: SDA on GPIO7, LED on GPIO10. JP61: cut 1-2, bridge 2-3.
    Rust2,
}

impl DevKit {
    /// GPIO number of the I2C data line on this revision.
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
    /// Bit number in the 16-bit port word: port 0 is bits 0 to 7, port 1 is
    /// bits 8 to 15.
    pub bit: u8,
    /// `true` = output (configuration bit 0), `false` = input.
    pub output: bool,
    /// Net name in the schematic.
    pub name: &'static str,
}

const fn out(bit: u8, name: &'static str) -> ExpPin {
    ExpPin {
        bit,
        output: true,
        name,
    }
}

const fn inp(bit: u8, name: &'static str) -> ExpPin {
    ExpPin {
        bit,
        output: false,
        name,
    }
}

/// PCA9539 pins (D-92, D-180).
pub mod exp {
    use super::{ExpPin, inp, out};

    /// IO0_0, output: software stop, active low. Low opens the SAFE loop.
    pub const SW_STOP_N: ExpPin = out(0, "SW_STOP_N");
    /// IO0_1, input: R1 TX sense. High = R1 transmits.
    pub const R1_TX: ExpPin = inp(1, "R1_TX");
    /// IO0_2, output: key R1 through the interface. Gated by PERMIT_R1 in hardware.
    pub const KEY_R1: ExpPin = out(2, "KEY_R1");
    /// IO0_3, input: R1 band data, bit D (most significant).
    pub const BAND_D: ExpPin = inp(3, "BAND_D");
    /// IO0_4, input: R1 band data, bit A (least significant).
    pub const BAND_A: ExpPin = inp(4, "BAND_A");
    /// IO0_5, input: R1 band data, bit B.
    pub const BAND_B: ExpPin = inp(5, "BAND_B");
    /// IO0_6, input: R1 band data, bit C.
    pub const BAND_C: ExpPin = inp(6, "BAND_C");
    /// IO0_7, output: display backlight. High = on (D-180).
    pub const DISP_BL: ExpPin = out(7, "DISP_BL");
    /// IO1_0, output: key R2. Gated by PERMIT_R2 in hardware.
    pub const KEY_R2: ExpPin = out(8, "KEY_R2");
    /// IO1_1, input: R2 TX sense. High = R2 transmits.
    pub const R2_TX: ExpPin = inp(9, "R2_TX");
    /// IO1_2, output: display D/C. Low = command, high = data (D-180).
    pub const DISP_DC: ExpPin = out(10, "DISP_DC");
    /// IO1_3, output: key R3. Gated by PERMIT_R3 in hardware.
    pub const KEY_R3: ExpPin = out(11, "KEY_R3");
    /// IO1_4, input: R3 TX sense. High = R3 transmits.
    pub const R3_TX: ExpPin = inp(12, "R3_TX");
    /// IO1_5, output: display reset, active low (D-180).
    pub const DISP_RST: ExpPin = out(13, "DISP_RST");
    /// IO1_6, input: KILL switch state. High = KILL pressed.
    pub const KILL_S: ExpPin = inp(14, "KILL_S");
    /// IO1_7, input: SAFE latch state. High = latched (TX blocked until RESET).
    pub const LATCHED: ExpPin = inp(15, "LATCHED");

    /// All 16 pins in bit order. A test checks that each bit is used once.
    pub const ALL: [ExpPin; 16] = [
        SW_STOP_N, R1_TX, KEY_R1, BAND_D, BAND_A, BAND_B, BAND_C, DISP_BL, KEY_R2, R2_TX, DISP_DC,
        KEY_R3, R3_TX, DISP_RST, KILL_S, LATCHED,
    ];
}

/// PCA9539 configuration word (register 6 low byte, register 7 high byte):
/// 1 = input, 0 = output.
///
/// The value is computed from [`exp::ALL`] at compile time. The logic writes the
/// outputs first and this word second (F1), and it reads the word back every tick:
/// a different value means that the expander was reset.
///
/// ```
/// use shack_core::board::{exp, expander_config};
///
/// let cfg = expander_config();
/// assert_eq!(cfg & (1 << exp::KEY_R1.bit), 0, "KEY_R1 is an output");
/// assert_ne!(cfg & (1 << exp::LATCHED.bit), 0, "LATCHED is an input");
/// assert_eq!(cfg, 0b1101_0010_0111_1010);
/// ```
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
