//! Shack interface board (hardware/shack-interface, docs/design/shack-interface.md).
//!
//! Logic as in verify_system.py sections 1, 3 and 4:
//! - SAFE loop: one series loop. Current = power AND SW_STOP source AND KILL closed AND cable AND box READY.
//! - Fault latch (D-59): PRE_N = RESET_N of the supervisor, CLK = LATCH_CLR, D = 0. Q = FAULT.
//! - SAFE latch (D-75, D-84): PRE_N = SAFE_OK AND POR_N, CLK = RESET button, D = 0. Q = LATCHED.
//! - TX_EN = NOR(FAULT, LATCHED). Per port: INH LED = PERMIT AND TX_EN; keying LED = KEY AND INH LED.
//! - PTT loop (pair 2) follows the R1 TX sense in hardware.
//!
//! Simplifications: the RESET debounce is ideal (one clean edge per press); signal levels
//! are evaluated at each step, so timing resolution is the step size the test uses.

use crate::lvc1g74::Lvc1g74;
use crate::pca9539::Pca9539;
use crate::st7789::St7789;
use crate::tps3823::{Corner, Tps3823};
use embedded_hal::i2c::{ErrorKind, Operation};
use shack_core::board::{EXPANDER_ADDR, ExpPin, exp, gpio};
use sim_core::hal::Board;
use sim_core::i2c::{self, AckStub, I2cDevice};
use sim_core::uart::UartLine;
use sim_core::{SimTime, Trace, TraceKind};

/// DevKit-RUST-1 on-board parts on the same bus (shack-interface generator notes).
const SHTC3_ADDR: u8 = 0x70;
const IMU_ADDR: u8 = 0x68;

/// Everything outside the board the test can change.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Env {
    /// 13.8 V present.
    pub power: bool,
    /// KILL switch pressed (both NC poles open).
    pub kill_pressed: bool,
    /// RESET button held down.
    pub reset_pressed: bool,
    /// Cat6 #1 intact.
    pub cable_ok: bool,
    /// Box READY switch closed (the box side of the SAFE loop).
    pub box_ready: bool,
    /// Radio TX GND active, per radio R1..R3.
    pub radio_tx: [bool; 3],
    /// FT-710 band data, bit 0 = A ... bit 3 = D. No radio: 0b1111 (pull-ups).
    pub band: u8,
    /// R64 fitted: WDI reaches the supervisor (D-123).
    pub wdi_link: bool,
}

impl Default for Env {
    fn default() -> Self {
        Env {
            power: false,
            kill_pressed: false,
            reset_pressed: false,
            cable_ok: true,
            box_ready: true,
            radio_tx: [false; 3],
            band: 0b1111,
            wdi_link: true,
        }
    }
}

/// Derived board signals, traced on every change.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Signals {
    pub reset_n: bool,
    pub por_n: bool,
    pub fault: bool,
    pub safe_source: bool,
    pub safe_current: bool,
    pub safe_lost: bool,
    pub latched: bool,
    pub tx_en: bool,
    /// INH contact closed = radio inhibited.
    pub inhibit: [bool; 3],
    /// Keying contact closed = radio keyed by the interface.
    pub key_contact: [bool; 3],
    /// Cat6 pair 2 current (R1 K0 in the box).
    pub ptt_loop: bool,
}

impl Signals {
    fn list(&self) -> [(&'static str, bool); 15] {
        [
            ("RESET_N", self.reset_n),
            ("POR_N", self.por_n),
            ("FAULT", self.fault),
            ("SAFE_SOURCE", self.safe_source),
            ("SAFE_CURRENT", self.safe_current),
            ("SAFE_LOST", self.safe_lost),
            ("LATCHED", self.latched),
            ("TX_EN", self.tx_en),
            ("INH_R1", self.inhibit[0]),
            ("INH_R2", self.inhibit[1]),
            ("INH_R3", self.inhibit[2]),
            ("KEYC_R1", self.key_contact[0]),
            ("KEYC_R2", self.key_contact[1]),
            ("KEYC_R3", self.key_contact[2]),
            ("PTT_LOOP", self.ptt_loop),
        ]
    }
}

/// Levels the MCU drives on its direct GPIO.
#[derive(Clone, Copy, Debug, Default)]
struct Gpio {
    permit: [bool; 3],
    /// None until the firmware first drives it: the pin floats after MCU reset.
    wdi: Option<bool>,
    latch_clr: bool,
}

pub struct ShackBoard {
    now: SimTime,
    env: Env,
    gpio: Gpio,
    sup: Tps3823,
    por: Tps3823,
    fault_ff: Lvc1g74,
    safe_ff: Lvc1g74,
    pub exp: Pca9539,
    pub lcd: St7789,
    shtc3: AckStub,
    imu: AckStub,
    to_box: UartLine,
    from_box: UartLine,
    sig: Signals,
    exp_pins: u16,
    pub trace: Trace,
}

impl ShackBoard {
    /// Board at t = 0, unpowered. `corner` sets both supervisors' timing.
    pub fn new(corner: Corner) -> Self {
        let mut b = ShackBoard {
            now: SimTime::ZERO,
            env: Env::default(),
            gpio: Gpio::default(),
            sup: Tps3823::new(corner),
            por: Tps3823::new(corner),
            fault_ff: Lvc1g74::new(),
            safe_ff: Lvc1g74::new(),
            exp: Pca9539::new(),
            lcd: St7789::new(),
            shtc3: AckStub,
            imu: AckStub,
            to_box: UartLine::new(9600),
            from_box: UartLine::new(9600),
            sig: Signals::default(),
            exp_pins: 0,
            trace: Trace::new(),
        };
        b.settle();
        b
    }

    pub fn env(&self) -> Env {
        self.env
    }

    /// Change the outside world at the present time.
    pub fn set_env(&mut self, f: impl FnOnce(&mut Env)) {
        f(&mut self.env);
        self.settle();
    }

    pub fn signals(&self) -> Signals {
        self.sig
    }

    pub fn exp_pin(&self, p: ExpPin) -> bool {
        self.exp.pin(p.bit)
    }

    /// Move time forward to `t` and settle.
    pub fn step_to(&mut self, t: SimTime) {
        assert!(t >= self.now, "time runs forward");
        self.now = t;
        self.settle();
    }

    /// Run for `dt` in 1 ms steps.
    pub fn run(&mut self, dt: SimTime) {
        let end = self.now + dt;
        while self.now < end {
            let next = (self.now + SimTime::ms(1)).min(end);
            self.step_to(next);
        }
    }

    /// Box end of the data link: a byte from the box (pair 4).
    pub fn box_send(&mut self, byte: u8) {
        self.from_box.send(self.now, byte);
    }

    /// Box end of the data link: next byte that reached the box (pair 1).
    pub fn box_recv(&mut self) -> Option<u8> {
        self.to_box.recv(self.now)
    }

    pub fn to_box_line(&mut self) -> &mut UartLine {
        &mut self.to_box
    }

    pub fn from_box_line(&mut self) -> &mut UartLine {
        &mut self.from_box
    }

    fn settle(&mut self) {
        let now = self.now;
        let e = self.env;
        let p = e.power;
        let por_n = self.por.update(now, p, None);
        let wdi = if e.wdi_link { self.gpio.wdi } else { None };
        let reset_n = self.sup.update(now, p, wdi);
        self.exp.set_reset(!reset_n);

        let fault = if p {
            self.fault_ff
                .update(reset_n, true, self.gpio.latch_clr, false)
        } else {
            self.fault_ff.power_off();
            true
        };

        let safe_source = self.exp_pin(exp::SW_STOP_N);
        let safe_current = p && safe_source && !e.kill_pressed && e.cable_ok && e.box_ready;
        let safe_lost = !safe_current;
        let latched = if p {
            self.safe_ff
                .update(!safe_lost && por_n, true, e.reset_pressed, false)
        } else {
            self.safe_ff.power_off();
            true
        };
        let tx_en = p && !fault && !latched;

        let keys = [exp::KEY_R1, exp::KEY_R2, exp::KEY_R3];
        let mut inhibit = [true; 3];
        let mut key_contact = [false; 3];
        for n in 0..3 {
            let led = p && self.gpio.permit[n] && tx_en;
            inhibit[n] = !led;
            key_contact[n] = led && self.exp_pin(keys[n]);
        }

        // Levels the board puts on the expander pins (used while a pin is an input).
        let ext = |pin: ExpPin| -> bool {
            match pin.name {
                "SW_STOP_N" => true, // R35 pull-up: loop closed while the expander is in reset
                "R1_TX" => p && e.radio_tx[0],
                "R2_TX" => p && e.radio_tx[1],
                "R3_TX" => p && e.radio_tx[2],
                "BAND_A" => e.band & 1 != 0,
                "BAND_B" => e.band & 2 != 0,
                "BAND_C" => e.band & 4 != 0,
                "BAND_D" => e.band & 8 != 0,
                "KILL_S" => e.kill_pressed,
                "LATCHED" => latched,
                // KEY_Rn pulled down: keys off in reset. Display pins: to confirm with the module.
                _ => false,
            }
        };
        let ext_word = exp::ALL
            .iter()
            .filter(|pin| ext(**pin))
            .fold(0u16, |w, pin| w | 1 << pin.bit);
        self.exp.set_external(ext_word);
        self.lcd.set_reset(!p || !self.exp_pin(exp::DISP_RST));

        let link = p && e.cable_ok;
        self.to_box.cut = !link;
        self.from_box.cut = !link;

        let sig = Signals {
            reset_n,
            por_n,
            fault,
            safe_source,
            safe_current,
            safe_lost,
            latched,
            tx_en,
            inhibit,
            key_contact,
            ptt_loop: link && e.radio_tx[0],
        };
        self.record(sig);
    }

    fn record(&mut self, sig: Signals) {
        let first = self.now == SimTime::ZERO && self.trace.events().is_empty();
        for ((name, new), (_, old)) in sig.list().into_iter().zip(self.sig.list()) {
            if first || new != old {
                self.trace
                    .push(self.now, TraceKind::Signal { name, value: new });
            }
        }
        self.sig = sig;
        let pins = self.exp.pins();
        for pin in exp::ALL {
            let m = 1 << pin.bit;
            if first || (pins ^ self.exp_pins) & m != 0 {
                self.trace.push(
                    self.now,
                    TraceKind::Signal {
                        name: pin.name,
                        value: pins & m != 0,
                    },
                );
            }
        }
        self.exp_pins = pins;
    }

    fn gpio_name(pin: u8) -> &'static str {
        match pin {
            gpio::PERMIT_R1 => "PERMIT_R1",
            gpio::PERMIT_R2 => "PERMIT_R2",
            gpio::PERMIT_R3 => "PERMIT_R3",
            gpio::WDI => "WDI",
            gpio::LATCH_CLR => "LATCH_CLR",
            _ => panic!("GPIO{pin} is not a driven output on the shack board"),
        }
    }
}

impl Board for ShackBoard {
    fn now(&self) -> SimTime {
        self.now
    }

    fn i2c(&mut self, addr: u8, ops: &mut [Operation<'_>]) -> Result<(), ErrorKind> {
        let dev: Option<&mut dyn I2cDevice> = if !self.env.power {
            None
        } else {
            match addr {
                EXPANDER_ADDR => Some(&mut self.exp),
                SHTC3_ADDR => Some(&mut self.shtc3),
                IMU_ADDR => Some(&mut self.imu),
                _ => None,
            }
        };
        let r = i2c::transact(&mut self.trace, self.now, addr, ops, dev);
        self.settle();
        r
    }

    fn gpio_write(&mut self, pin: u8, high: bool) {
        let name = Self::gpio_name(pin);
        let g = &mut self.gpio;
        let slot = match pin {
            gpio::PERMIT_R1 => &mut g.permit[0],
            gpio::PERMIT_R2 => &mut g.permit[1],
            gpio::PERMIT_R3 => &mut g.permit[2],
            gpio::LATCH_CLR => &mut g.latch_clr,
            _ => {
                g.wdi = Some(high);
                self.trace
                    .push(self.now, TraceKind::Signal { name, value: high });
                self.settle();
                return;
            }
        };
        if *slot != high {
            *slot = high;
            self.trace
                .push(self.now, TraceKind::Signal { name, value: high });
        }
        self.settle();
    }

    fn gpio_read(&mut self, pin: u8) -> bool {
        match pin {
            gpio::SAFE_LOST => self.sig.safe_lost,
            _ => panic!("GPIO{pin} is not an input on the shack board"),
        }
    }

    fn spi_write(&mut self, data: &[u8]) {
        if self.env.power {
            let dc = self.exp_pin(exp::DISP_DC);
            self.lcd.spi(dc, data);
        }
    }

    fn uart_write(&mut self, byte: u8) {
        self.trace.push(
            self.now,
            TraceKind::Uart {
                line: "to_box",
                byte,
            },
        );
        self.to_box.send(self.now, byte);
    }

    fn uart_read(&mut self) -> Option<u8> {
        self.from_box.recv(self.now)
    }
}
