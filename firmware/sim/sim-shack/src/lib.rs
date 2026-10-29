//! Shack firmware logic (shack-core) on the shack board model, against a scripted box.
//! Time moves in 1 ms steps; the firmware ticks every `shack::TICK` ms.

pub mod box_stub;

use box_stub::BoxStub;
use link_proto::{Ms, Radio};
use shack_core::board::gpio;
use shack_core::hw::ShackHw;
use shack_core::shack::{Event, Shack, TICK};
use sim_core::SimTime;
use sim_core::hal::{Board, Shared, SimI2c, shared};
use sim_models::shack::ShackBoard;
use sim_models::tps3823::Corner;

/// `ShackHw` over the board model: the same calls the ESP32-C3 glue will make.
pub struct SimShackHw {
    board: Shared<ShackBoard>,
    i2c: SimI2c<ShackBoard>,
}

impl ShackHw for SimShackHw {
    type I2c = SimI2c<ShackBoard>;

    fn i2c(&mut self) -> &mut Self::I2c {
        &mut self.i2c
    }

    fn set_permit(&mut self, radio: Radio, on: bool) {
        let pin = [gpio::PERMIT_R1, gpio::PERMIT_R2, gpio::PERMIT_R3][radio.index()];
        self.board.borrow_mut().gpio_write(pin, on);
    }

    fn set_wdi(&mut self, high: bool) {
        self.board.borrow_mut().gpio_write(gpio::WDI, high);
    }

    fn set_latch_clr(&mut self, high: bool) {
        self.board.borrow_mut().gpio_write(gpio::LATCH_CLR, high);
    }

    fn safe_lost(&mut self) -> bool {
        self.board.borrow_mut().gpio_read(gpio::SAFE_LOST)
    }

    fn uart_write(&mut self, bytes: &[u8]) {
        let mut b = self.board.borrow_mut();
        for &x in bytes {
            b.uart_write(x);
        }
    }

    fn uart_read(&mut self) -> Option<u8> {
        self.board.borrow_mut().uart_read()
    }

    fn usb_write(&mut self, bytes: &[u8]) {
        let mut b = self.board.borrow_mut();
        for &x in bytes {
            b.usb_write(x);
        }
    }

    fn usb_read(&mut self) -> Option<u8> {
        self.board.borrow_mut().usb_read()
    }
}

pub struct ShackSim {
    pub board: Shared<ShackBoard>,
    hw: SimShackHw,
    pub shack: Shack,
    pub boxs: BoxStub,
    /// Firmware events with their time.
    pub events: Vec<(Ms, Event)>,
    /// False: the MCU hangs (no more ticks).
    pub mcu_running: bool,
    next_tick: Ms,
    /// Every line the shack sent to the host, with its time.
    pub host_lines: Vec<(Ms, String)>,
    host_partial: String,
}

impl Default for ShackSim {
    fn default() -> Self {
        Self::new()
    }
}

impl ShackSim {
    /// Board powered at t = 0; the firmware ticks from t = 0.
    pub fn new() -> Self {
        let board = shared(ShackBoard::new(Corner::Typ));
        board.borrow_mut().set_env(|e| e.power = true);
        ShackSim {
            hw: SimShackHw {
                board: board.clone(),
                i2c: SimI2c(board.clone()),
            },
            board,
            shack: Shack::new(),
            boxs: BoxStub::new(),
            events: Vec::new(),
            mcu_running: true,
            next_tick: 0,
            host_lines: Vec::new(),
            host_partial: String::new(),
        }
    }

    pub fn now(&self) -> Ms {
        self.board.borrow().now().as_ms()
    }

    /// One millisecond.
    pub fn step(&mut self) {
        let t = self.now() + 1;
        self.board.borrow_mut().step_to(SimTime::ms(t));
        self.boxs.step(t, &mut self.board.borrow_mut());
        if self.mcu_running && t >= self.next_tick {
            self.shack.tick(t, &mut self.hw);
            self.next_tick = t + TICK;
            while let Some(e) = self.shack.take_event() {
                self.events.push((t, e));
            }
        }
        let out = self.board.borrow_mut().host_take();
        self.host_partial.push_str(&out);
        while let Some(i) = self.host_partial.find('\n') {
            let line: String = self.host_partial.drain(..=i).collect();
            self.host_lines.push((t, line.trim_end().to_string()));
        }
    }

    /// Send one line as the host and return the answer (`ok ...` or `err ...`).
    pub fn host(&mut self, line: &str) -> String {
        let from = self.host_lines.len();
        self.board.borrow_mut().host_send(&format!("{line}\n"));
        for _ in 0..100 {
            self.step();
            if let Some((_, l)) = self.host_lines[from..]
                .iter()
                .find(|(_, l)| l.starts_with("ok") || l.starts_with("err"))
            {
                return l.clone();
            }
        }
        panic!("no answer to {line:?}");
    }

    /// Host lines that start with `prefix`, from line index `from`.
    pub fn host_seen(&self, from: usize, prefix: &str) -> Option<Ms> {
        self.host_lines[from..]
            .iter()
            .find(|(_, l)| l.starts_with(prefix))
            .map(|(t, _)| *t)
    }

    pub fn run(&mut self, ms: Ms) {
        for _ in 0..ms {
            self.step();
        }
    }

    /// Run until `cond` holds, at most `max` ms. Returns the time it held, if it did.
    pub fn run_until(&mut self, max: Ms, cond: impl Fn(&Self) -> bool) -> Option<Ms> {
        for _ in 0..max {
            if cond(self) {
                return Some(self.now());
            }
            self.step();
        }
        cond(self).then(|| self.now())
    }

    pub fn press_reset(&mut self) {
        self.board.borrow_mut().set_env(|e| e.reset_pressed = true);
        self.run(5);
        self.board.borrow_mut().set_env(|e| e.reset_pressed = false);
    }

    /// Start-up done, link up, SAFE latch cleared by the operator: ready to transmit.
    pub fn start(&mut self) {
        self.run_until(2000, |s| s.shack.link_up())
            .expect("link up");
        self.press_reset();
        self.run(100);
        assert!(self.board.borrow().signals().tx_en, "TX_EN after start");
    }

    pub fn has_event(&self, e: Event) -> Option<Ms> {
        self.events.iter().find(|(_, x)| *x == e).map(|(t, _)| *t)
    }
}
