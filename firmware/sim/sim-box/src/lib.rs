//! Box firmware logic (box-core) on the box board model, against a scripted shack.
//! Time moves in 1 ms steps; the firmware ticks every `relay_box::TICK` ms.
//!
//! # Where this crate sits
//!
//! The same layering as `sim-shack`: the firmware logic in `box-core` asks for
//! hardware through one trait, [`BoxHw`]. On the ESP32-C3 the glue implements it
//! with `esp-hal`. Here [`SimBoxHw`] implements it with the box board model of
//! `sim-models`. The emulator runs the logic code of the target, not its RISC-V
//! instructions.
//!
//! # One step
//!
//! [`BoxSim::step`] moves virtual time by 1 ms, to `t`, in this order:
//!
//! 1. Board time: the board model moves to `t` and settles (supervisor, latch,
//!    SAFE loop, relays, RF).
//! 2. Shack stub: reads the answers that reached it, sends the next frame, and
//!    sets its end of the SAFE loop.
//! 3. Firmware tick, with board power. Power off to on restarts the firmware.
//! 4. Hazard check: the relay contacts against H1 to H4 ([`BoxSim::hazards`]).
//!
//! # Example
//!
//! ```
//! use link_proto::{Col, Command, Radio, ResultCode, Route};
//! use sim_box::BoxSim;
//!
//! let mut s = BoxSim::new();
//! s.start();
//! let route = Route { tx: Col::A1, rx: Col::A1 };
//! let st = s.command(Command::SetRoute { radio: Radio::R1, route });
//! assert_eq!(st.result, ResultCode::Ok);
//! s.run(60);
//! assert_eq!(s.shack.status().unwrap().routes[0], route);
//! assert!(s.hazards.is_empty());
//! ```

pub mod shack_stub;

use box_core::board::gpio;
use box_core::hw::BoxHw;
use box_core::relay_box::{Phase, RelayBox, TICK};
use link_proto::{Command, Ms, Status};
use shack_stub::ShackStub;
use sim_core::SimTime;
use sim_core::hal::{Board, Shared, SimI2c, shared};
use sim_models::box_board::{BoxBoard, Hazard};
use sim_models::rt1::Rt1Timing;
use sim_models::tps3823::Corner;

/// `BoxHw` over the board model: the same calls the ESP32-C3 glue will make.
pub struct SimBoxHw {
    board: Shared<BoxBoard>,
    i2c: SimI2c<BoxBoard>,
}

impl BoxHw for SimBoxHw {
    type I2c = SimI2c<BoxBoard>;

    fn i2c(&mut self) -> &mut Self::I2c {
        &mut self.i2c
    }

    fn set_wdi(&mut self, high: bool) {
        self.board.borrow_mut().gpio_write(gpio::WDI, high);
    }

    fn set_latch_clr(&mut self, high: bool) {
        self.board.borrow_mut().gpio_write(gpio::LATCH_CLR, high);
    }

    fn set_mcu_en_n(&mut self, high: bool) {
        self.board.borrow_mut().gpio_write(gpio::MCU_EN_N, high);
    }

    fn kill(&mut self) -> bool {
        self.board.borrow_mut().gpio_read(gpio::KILL)
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
}

/// The emulator harness: box board model, box firmware, glue and scripted shack,
/// moved together in 1 ms steps.
pub struct BoxSim {
    /// The board model, shared with the glue. Borrow it to read the trace and
    /// signals, or to change the outside world with `set_env`; drop the borrow
    /// before the next step.
    pub board: Shared<BoxBoard>,
    hw: SimBoxHw,
    /// The firmware state.
    pub fw: RelayBox,
    /// The scripted shack at the far end of the Cat6 cable.
    pub shack: ShackStub,
    /// The scripted shack is off: the shack end of the link and the loops are
    /// driven from outside (`sim-system` joins the shack emulator here).
    pub external_shack: bool,
    /// False: the box MCU hangs (no more ticks).
    pub mcu_running: bool,
    /// Every hazard in the relay contacts, with the time it started.
    pub hazards: Vec<(Ms, Hazard)>,
    active: Vec<Hazard>,
    next_tick: Ms,
    powered: bool,
}

impl Default for BoxSim {
    fn default() -> Self {
        Self::new()
    }
}

impl BoxSim {
    /// Box powered at t = 0, relays at the datasheet maximum timing.
    pub fn new() -> Self {
        Self::with_relays(Rt1Timing::MAX)
    }

    /// As `new`, with this relay timing.
    pub fn with_relays(relays: Rt1Timing) -> Self {
        Self::with(Corner::Typ, relays)
    }

    /// As `new`, with this supervisor timing and relay timing.
    pub fn with(corner: Corner, relays: Rt1Timing) -> Self {
        let board = shared(BoxBoard::new(corner, relays));
        board.borrow_mut().set_env(|e| e.power = true);
        BoxSim {
            hw: SimBoxHw {
                board: board.clone(),
                i2c: SimI2c(board.clone()),
            },
            board,
            fw: RelayBox::new(),
            shack: ShackStub::new(),
            external_shack: false,
            mcu_running: true,
            hazards: Vec::new(),
            active: Vec::new(),
            next_tick: 0,
            powered: true,
        }
    }

    /// Present virtual time in ms.
    pub fn now(&self) -> Ms {
        self.board.borrow().now().as_ms()
    }

    /// One millisecond: board time, shack stub, firmware tick, hazard check.
    pub fn step(&mut self) {
        let t = self.now() + 1;
        self.board.borrow_mut().step_to(SimTime::ms(t));
        if !self.external_shack {
            self.shack.step(t, &mut self.board.borrow_mut());
        }
        let powered = self.board.borrow().env().power;
        if powered && !self.powered {
            self.fw = RelayBox::new();
            self.mcu_running = true;
            self.next_tick = t;
        }
        self.powered = powered;
        if powered && self.mcu_running && t >= self.next_tick {
            self.fw.tick(t, &mut self.hw);
            self.next_tick = t + TICK;
        }
        let now = self.board.borrow().hazards();
        for h in &now {
            if !self.active.contains(h) {
                self.hazards.push((t, *h));
            }
        }
        self.active = now;
    }

    /// Run for `ms` milliseconds.
    pub fn run(&mut self, ms: Ms) {
        for _ in 0..ms {
            self.step();
        }
    }

    /// Step until `cond` holds, at most `max` ms. The time it held, or `None`.
    pub fn run_until(&mut self, max: Ms, cond: impl Fn(&Self) -> bool) -> Option<Ms> {
        for _ in 0..max {
            self.step();
            if cond(self) {
                return Some(self.now());
            }
        }
        None
    }

    /// Queue `cmd` at the shack and step until its answer comes back.
    ///
    /// # Panics
    ///
    /// If no answer comes within 1 s.
    pub fn command(&mut self, cmd: Command) -> Status {
        let from = self.shack.replies.len();
        self.shack.queue.push_back(cmd);
        for _ in 0..1000 {
            self.step();
            if let Some(r) = self.shack.replies[from..].iter().find(|r| r.1 == cmd) {
                return r.2;
            }
        }
        panic!("no answer to {cmd:?} by {} ms", self.now());
    }

    /// Bring the box up: boot, MCU_EN_N low, RESET pressed at the shack, link up,
    /// expanders set up.
    ///
    /// # Panics
    ///
    /// If the box is not in [`Phase::Run`] with the link up within 5 s (the
    /// self-test takes 1 to 3.5 s).
    pub fn start(&mut self) {
        self.run_until(1000, |s| matches!(s.fw.phase(), Phase::WaitSafe { .. }))
            .expect("MCU_EN_N low after the boot delay");
        self.step();
        self.shack.press_reset();
        self.run_until(5000, |s| s.fw.phase() == Phase::Run && s.shack.link_up())
            .expect("box running and link up");
    }
}
