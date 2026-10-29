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
//!
//! # Use
//!
//! A test changes the outside world with [`ShackBoard::set_env`] and moves time
//! with [`ShackBoard::step_to`] or [`ShackBoard::run`]. The firmware side uses the
//! [`Board`] trait. After every change and every bus access the board settles:
//! it updates the parts, works out the [`Signals`], and records each changed
//! signal and expander pin in [`ShackBoard::trace`]. The names in the trace are the
//! net names: `RESET_N`, `TX_EN`, `INH_R2`, `SW_STOP_N`, and so on.
//!
//! The box end of the data link is open to the test: [`ShackBoard::box_send`] and
//! [`ShackBoard::box_recv`]. In `sim-shack` the scripted box uses them.

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
use std::collections::VecDeque;

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
///
/// The board works these out in each settle, from [`Env`], the MCU outputs and
/// the part states. Read them with [`ShackBoard::signals`]. In the trace each field
/// has its net name (in brackets below).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Signals {
    /// Main supervisor output (`RESET_N`). Low: expander in reset, fault latch set.
    pub reset_n: bool,
    /// Second supervisor output, WDI open (`POR_N`). Low: SAFE latch held set (D-84).
    pub por_n: bool,
    /// Fault latch Q (`FAULT`). Set by a supervisor reset, cleared by a rising
    /// edge on LATCH_CLR (D-59).
    pub fault: bool,
    /// SW_STOP_N expander pin: the firmware switches on the SAFE loop source
    /// (`SAFE_SOURCE`).
    pub safe_source: bool,
    /// Current flows in the SAFE loop (`SAFE_CURRENT`): power, source, KILL
    /// closed, cable intact and box READY, all in series (verify_system.py section 1).
    pub safe_current: bool,
    /// No loop current (`SAFE_LOST`). The MCU reads this on GPIO21.
    pub safe_lost: bool,
    /// SAFE latch Q (`LATCHED`). Set by a loss of loop current or power-up;
    /// cleared by the RESET button while PRE_N is high (D-75).
    pub latched: bool,
    /// Transmit enable (`TX_EN`) = NOR(FAULT, LATCHED), and power present.
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

/// The shack interface board: the parts, their wiring, and the board end of the
/// links (UART to the box, USB to the host).
///
/// Make one with [`ShackBoard::new`]. It starts unpowered at t = 0; set
/// `power` in [`Env`] to start it.
pub struct ShackBoard {
    now: SimTime,
    env: Env,
    gpio: Gpio,
    sup: Tps3823,
    por: Tps3823,
    fault_ff: Lvc1g74,
    safe_ff: Lvc1g74,
    /// PCA9539 I/O expander at [`EXPANDER_ADDR`], RESET from RESET_N (D-68).
    /// Public so a test can inject faults (`force_nack`) or read registers.
    pub exp: Pca9539,
    /// The display controller on the Waveshare module. Public so a test can read the
    /// picture.
    pub lcd: St7789,
    shtc3: AckStub,
    imu: AckStub,
    to_box: UartLine,
    from_box: UartLine,
    usb_in: VecDeque<u8>,
    usb_out: Vec<u8>,
    sig: Signals,
    exp_pins: u16,
    /// Record of every signal change, I2C transfer and UART byte to the box.
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
            usb_in: VecDeque::new(),
            usb_out: Vec::new(),
            sig: Signals::default(),
            exp_pins: 0,
            trace: Trace::new(),
        };
        b.settle();
        b
    }

    /// The present outside world.
    pub fn env(&self) -> Env {
        self.env
    }

    /// Change the outside world at the present time.
    pub fn set_env(&mut self, f: impl FnOnce(&mut Env)) {
        f(&mut self.env);
        self.settle();
    }

    /// The derived board signals after the last settle.
    pub fn signals(&self) -> Signals {
        self.sig
    }

    /// Level of one expander pin, for example `exp_pin(exp::KEY_R2)`.
    pub fn exp_pin(&self, p: ExpPin) -> bool {
        self.exp.pin(p.bit)
    }

    /// Move time forward to `t` and settle.
    ///
    /// The board settles once, at `t`. Use [`ShackBoard::run`] for a long time span,
    /// so the supervisors and latches see the steps in between.
    ///
    /// # Panics
    ///
    /// If `t` is earlier than the present time.
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

    /// Box end of the data link: a byte from the box (pair 4). It arrives at the
    /// MCU one byte time (1041 µs) later, or never if the cable is cut.
    pub fn box_send(&mut self, byte: u8) {
        self.from_box.send(self.now, byte);
    }

    /// Box end of the data link: next byte that reached the box (pair 1).
    pub fn box_recv(&mut self) -> Option<u8> {
        self.to_box.recv(self.now)
    }

    /// Host side of the USB port: send text. Lost while the board has no power
    /// (the DevKit is not fed from USB VBUS, D-96).
    pub fn host_send(&mut self, text: &str) {
        if self.env.power {
            self.usb_in.extend(text.bytes());
        }
    }

    /// Host side of the USB port: everything the MCU wrote since the last call.
    pub fn host_take(&mut self) -> String {
        String::from_utf8_lossy(&std::mem::take(&mut self.usb_out)).into_owned()
    }

    /// The MCU to box line (pair 1), for example to set a fault filter.
    pub fn to_box_line(&mut self) -> &mut UartLine {
        &mut self.to_box
    }

    /// The box to MCU line (pair 4), for example to set a fault filter.
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

    fn usb_write(&mut self, byte: u8) {
        // No board power: the MCU is off and nothing reaches the host.
        if self.env.power {
            self.usb_out.push(byte);
        }
    }

    fn usb_read(&mut self) -> Option<u8> {
        self.usb_in.pop_front()
    }
}
