//! Shack firmware logic (shack-core) on the shack board model, against a scripted box.
//! Time moves in 1 ms steps; the firmware ticks every `shack::TICK` ms.
//!
//! # Where this crate sits
//!
//! This is the top layer of the emulator (README, "How the emulator works"). The
//! firmware logic in `shack-core` asks for hardware through one trait,
//! [`ShackHw`]. On the ESP32-C3 the glue implements it with `esp-hal`. Here
//! [`SimShackHw`] implements it with the board model of `sim-models`. So the
//! emulator runs the same logic code as the target. It does not run RISC-V
//! instructions.
//!
//! # Main types
//!
//! - [`ShackSim`]: the harness. It owns the board model, the firmware state
//!   ([`Shack`]), the glue and the scripted box, and moves them all in time.
//! - [`SimShackHw`]: the [`ShackHw`] implementation over the board model.
//! - [`box_stub::BoxStub`]: a scripted box at the far end of the Cat6 data link.
//! - [`tui`]: the terminal UI of the `sim-shack` program, with [`textview`] for
//!   terminals without images.
//!
//! The board is a [`Shared`] value, an `Rc<RefCell<ShackBoard>>`: the harness,
//! the glue, the I2C adapter and the test all hold a handle to the same board.
//! Call `s.board.borrow()` to read it and `s.board.borrow_mut()` to change it, and
//! drop the borrow before the next [`ShackSim::step`]. A second borrow while one is
//! active panics.
//!
//! # One step
//!
//! [`ShackSim::step`] moves virtual time by 1 ms, to `t`, in this order:
//!
//! 1. Board time: the board model moves to `t` and settles. The supervisors, the
//!    latches and the SAFE loop update; UART bytes that arrived by `t` become
//!    readable.
//! 2. Box stub: the scripted box reads the bytes that reached it, answers, and sets
//!    its READY switch.
//! 3. Firmware tick: only with board power (an off-to-on change restarts the
//!    firmware from boot, as a power cycle of the MCU; the stored settings stay).
//!    When a tick is due (every [`TICK`] = 10 ms), the harness
//!    calls [`Shack::tick`] with the glue. The firmware reads inputs, drives pins,
//!    talks to the box and the host, and draws the display. The harness records
//!    the firmware events in [`ShackSim::events`].
//! 4. Host lines: the bytes the firmware wrote to the USB port are split into
//!    lines and kept in [`ShackSim::host_lines`] with their time.
//!
//! # How to write a scenario test
//!
//! 1. Make a sim with [`ShackSim::new`]. The board has power at t = 0.
//! 2. Bring it to the ready state with [`ShackSim::start`]: link up, SAFE latch
//!    cleared, TX_EN high. Skip this step to test the start-up itself.
//! 3. Act: send host commands with [`ShackSim::host`], call the firmware
//!    directly (`s.shack.set_tx(..)`), or change the outside world
//!    (`s.board.borrow_mut().set_env(..)` or [`ShackSim::world`]).
//! 4. Move time with [`ShackSim::run`] or [`ShackSim::run_until`].
//! 5. Check the result: the board trace (`s.board.borrow().trace`), the board
//!    signals, the box logs ([`box_stub::BoxStub::log`]), the firmware events or
//!    the host lines. Put times in the assert messages; they help when a test fails.
//!
//! See `tests/scenarios.rs` and `tests/host.rs` for complete examples.
//!
//! ```
//! use sim_shack::ShackSim;
//!
//! let mut s = ShackSim::new();
//! s.start();
//! assert_eq!(s.host("route R2 A1 A1"), "ok");
//! s.run(150);
//! // KILL pressed: the SAFE loop opens and TX_EN goes low.
//! s.board.borrow_mut().set_env(|e| e.kill_pressed = true);
//! s.run(20);
//! let b = s.board.borrow();
//! assert!(!b.signals().tx_en);
//! // The trace shows when TX_EN fell.
//! let (t, high) = *b.trace.signal("TX_EN").last().unwrap();
//! assert!(!high, "TX_EN low since {t}");
//! ```
//!
//! # Example
//!
//! Start the sim, send `hello` on the host port, and read the answer. This runs
//! about 50 ms of virtual time.
//!
//! ```
//! use sim_shack::ShackSim;
//!
//! let mut s = ShackSim::new();
//! s.run(50);
//! let answer = s.host("hello");
//! assert!(answer.starts_with("ok shack"), "{answer}");
//! ```

pub mod box_stub;
pub mod system;
pub mod textview;
pub mod tui;

use box_stub::BoxStub;
use host_proto::SelfTestState;
use link_proto::{Ms, Radio};
use shack_core::board::gpio;
use shack_core::hw::ShackHw;
use shack_core::shack::{Event, Shack, TICK};
use sim_core::SimTime;
use sim_core::hal::{Board, Shared, SimI2c, shared};
use sim_models::shack::ShackBoard;
use sim_models::tps3823::Corner;

/// `ShackHw` over the board model: the same calls the ESP32-C3 glue will make.
///
/// Each function forwards to the [`Board`] trait of [`ShackBoard`]: pins by their
/// ESP32-C3 GPIO number ([`gpio`]), I2C through [`SimI2c`]. The frame buffer is a
/// `Vec` here and a static on the target. The settings flash is a `Vec`, with an
/// optional file so the settings survive a restart of the emulator. [`ShackSim`]
/// makes and owns the one instance.
pub struct SimShackHw {
    board: Shared<ShackBoard>,
    i2c: SimI2c<ShackBoard>,
    framebuffer: Vec<u8>,
    /// Display SPI bytes since the last tick started.
    spi_bytes: usize,
    /// Stored settings record (the MCU flash), and an optional file that keeps it
    /// between simulator runs.
    stored: Vec<u8>,
    state_file: Option<std::path::PathBuf>,
    saves: usize,
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

    fn spi_write(&mut self, bytes: &[u8]) {
        self.spi_bytes += bytes.len();
        self.board.borrow_mut().spi_write(bytes);
    }

    fn framebuffer(&mut self) -> &mut [u8] {
        &mut self.framebuffer
    }

    fn config_load(&mut self, buf: &mut [u8]) -> usize {
        let n = self.stored.len().min(buf.len());
        buf[..n].copy_from_slice(&self.stored[..n]);
        n
    }

    fn config_save(&mut self, record: &[u8]) {
        self.stored = record.to_vec();
        self.saves += 1;
        if let Some(p) = &self.state_file {
            let _ = std::fs::write(p, record);
        }
    }

    fn spi_write_framebuffer(&mut self, start: usize, end: usize) {
        self.spi_bytes += end - start;
        self.board
            .borrow_mut()
            .spi_write(&self.framebuffer[start..end]);
    }
}

/// The emulator harness: board model, firmware logic, glue and scripted box, moved
/// together in 1 ms steps. See the [crate overview](crate) for one step and for
/// how to write a test.
pub struct ShackSim {
    /// The board model, shared with the glue. Borrow it to read the trace and
    /// signals, or to change the outside world with `set_env`.
    pub board: Shared<ShackBoard>,
    hw: SimShackHw,
    /// The firmware logic state. A test may call its request functions directly
    /// (`set_route`, `set_tx`, `set_key`), as the host port does.
    pub shack: Shack,
    /// The scripted box at the far end of the data link.
    pub boxs: BoxStub,
    /// The scripted box is off: the box end of the link and the loops are
    /// driven from outside (`sim-system` joins the box emulator here).
    pub external_box: bool,
    /// Firmware events with their time.
    pub events: Vec<(Ms, Event)>,
    /// False: the MCU hangs (no more ticks).
    pub mcu_running: bool,
    /// Most display SPI bytes sent in one tick.
    pub spi_max_per_tick: usize,
    next_tick: Ms,
    /// Every line the shack sent to the host, with its time.
    pub host_lines: Vec<(Ms, String)>,
    host_partial: String,
    /// The 13.8 V supply at the last step: an off-to-on change restarts the MCU.
    powered: bool,
}

impl Default for ShackSim {
    fn default() -> Self {
        Self::new()
    }
}

impl ShackSim {
    /// Board powered at t = 0; the firmware ticks from the first step (t = 1 ms,
    /// then every [`TICK`]). No stored settings. Supervisor timing at
    /// [`Corner::Typ`].
    pub fn new() -> Self {
        Self::with_stored(Vec::new())
    }

    /// As `new`, with this stored settings record in the MCU flash (a power cycle).
    pub fn with_stored(stored: Vec<u8>) -> Self {
        Self::with(Corner::Typ, stored)
    }

    /// As `with_stored`, with this supervisor timing.
    pub fn with(corner: Corner, stored: Vec<u8>) -> Self {
        let board = shared(ShackBoard::new(corner));
        board.borrow_mut().set_env(|e| e.power = true);
        ShackSim {
            hw: SimShackHw {
                board: board.clone(),
                i2c: SimI2c(board.clone()),
                framebuffer: vec![0; shack_ui::fb::BYTES],
                spi_bytes: 0,
                stored,
                state_file: None,
                saves: 0,
            },
            board,
            shack: Shack::new(),
            boxs: BoxStub::new(),
            external_box: false,
            events: Vec::new(),
            mcu_running: true,
            spi_max_per_tick: 0,
            next_tick: 0,
            host_lines: Vec::new(),
            host_partial: String::new(),
            powered: true,
        }
    }

    /// Present virtual time in ms (the board time).
    pub fn now(&self) -> Ms {
        self.board.borrow().now().as_ms()
    }

    /// One millisecond: board time, box stub, firmware tick when due, host lines.
    /// The [crate overview](crate#one-step) explains the order.
    pub fn step(&mut self) {
        let t = self.now() + 1;
        self.board.borrow_mut().step_to(SimTime::ms(t));
        if !self.external_box {
            self.boxs.step(t, &mut self.board.borrow_mut());
        }
        // Power cycle: without 13.8 V the MCU is off (no ticks). When the supply
        // returns, the MCU starts from boot: new firmware state, a hang is gone.
        // The stored settings stay, as in flash.
        let powered = self.board.borrow().env().power;
        if powered && !self.powered {
            self.shack = Shack::new();
            self.mcu_running = true;
            self.next_tick = t;
            self.host_partial.clear();
        }
        self.powered = powered;
        if powered && self.mcu_running && t >= self.next_tick {
            self.hw.spi_bytes = 0;
            self.shack.tick(t, &mut self.hw);
            self.spi_max_per_tick = self.spi_max_per_tick.max(self.hw.spi_bytes);
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
    ///
    /// The line goes in with a `\n`. The sim then steps until the firmware answers.
    /// Event lines (`!`) and log lines (`#`) on the way stay in
    /// [`ShackSim::host_lines`].
    ///
    /// # Panics
    ///
    /// If no answer comes within 100 ms.
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
    ///
    /// Returns the time of the first such line, or `None`. Take `from` from
    /// `host_lines.len()` before the action, to skip older lines.
    pub fn host_seen(&self, from: usize, prefix: &str) -> Option<Ms> {
        self.host_lines[from..]
            .iter()
            .find(|(_, l)| l.starts_with(prefix))
            .map(|(t, _)| *t)
    }

    /// Run `ms` milliseconds of virtual time, in 1 ms steps.
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

    /// Press the front panel RESET button for 5 ms, then release it. The press gives
    /// one clean clock edge to the SAFE latch (ideal debounce).
    pub fn press_reset(&mut self) {
        self.board.borrow_mut().set_env(|e| e.reset_pressed = true);
        self.run(5);
        self.board.borrow_mut().set_env(|e| e.reset_pressed = false);
    }

    /// Start-up done, link up, SAFE latch cleared by the operator: ready to transmit.
    ///
    /// Runs until the power-up self-test has passed and the box link is up (at most
    /// 5 s), presses RESET, and runs 100 ms more. With the typical supervisor this
    /// ends at about t = 2 s: the watchdog test waits for the supervisor time-out.
    ///
    /// # Panics
    ///
    /// If the self-test fails, the link does not come up, or TX_EN is not high at
    /// the end.
    pub fn start(&mut self) {
        self.run_until(5000, |s| {
            s.shack.self_test() != SelfTestState::Running && s.shack.link_up()
        })
        .expect("self-test done and link up");
        assert_eq!(self.shack.self_test(), SelfTestState::Pass, "self-test");
        self.press_reset();
        self.run(100);
        assert!(self.board.borrow().signals().tx_en, "TX_EN after start");
    }

    /// The stored settings record (empty when never saved).
    pub fn stored(&self) -> Vec<u8> {
        self.hw.stored.clone()
    }

    /// Number of flash writes of the settings.
    pub fn saves(&self) -> usize {
        self.hw.saves
    }

    /// Keep the stored settings in a file: load it now (if it exists), write it on every save.
    pub fn use_state_file(path: &std::path::Path) -> Self {
        let mut s = Self::with_stored(std::fs::read(path).unwrap_or_default());
        s.hw.state_file = Some(path.to_path_buf());
        s
    }

    /// What the simulated display shows: 320 x 240 RGB565 in window coordinates.
    pub fn screen(&self) -> Vec<u16> {
        self.board
            .borrow()
            .lcd
            .logical(shack_ui::WIDTH as usize, shack_ui::HEIGHT as usize)
    }

    /// Save the simulated display as PNG, scaled `scale` times.
    pub fn save_screen(&self, path: &std::path::Path, scale: u32) {
        save_png(path, &self.screen(), scale);
    }

    /// One outside-world command, shared by the terminal UI and the pty mode.
    /// Returns what happened, or an error with the help text.
    ///
    /// The commands are in [`WORLD_HELP`], for example `kill on`, `cable off` or
    /// `radio R2 on`. Words are split on spaces; `on` is not case sensitive.
    pub fn world(&mut self, cmd: &str) -> Result<String, String> {
        let w: Vec<&str> = cmd.split_whitespace().collect();
        let on = |x: &str| x.eq_ignore_ascii_case("on");
        match w.as_slice() {
            ["help" | "?"] => return Ok(WORLD_HELP.to_string()),
            ["reset"] => {
                self.press_reset();
                return Ok("RESET pressed".into());
            }
            ["box", "mute", v] => self.boxs.mute = on(v),
            ["radio", r, v] => {
                let i = radio_index(r)?;
                self.board.borrow_mut().set_env(|e| e.radio_tx[i] = on(v));
            }
            ["radio", r, "noinh", v] => {
                let i = radio_index(r)?;
                self.board
                    .borrow_mut()
                    .set_env(|e| e.radio_no_inh[i] = on(v));
            }
            ["kill", v] => self.board.borrow_mut().set_env(|e| e.kill_pressed = on(v)),
            ["cable", v] => self.board.borrow_mut().set_env(|e| e.cable_ok = on(v)),
            ["power", v] => self.board.borrow_mut().set_env(|e| e.power = on(v)),
            ["shot", path] => {
                self.save_screen(std::path::Path::new(path), 3);
                return Ok(format!("display saved to {path}"));
            }
            _ => return Err(WORLD_HELP.to_string()),
        }
        Ok(format!("{cmd}: done"))
    }

    /// Time of the first firmware event equal to `e`, or `None`.
    pub fn has_event(&self, e: Event) -> Option<Ms> {
        self.events.iter().find(|(_, x)| *x == e).map(|(t, _)| *t)
    }
}

/// Save 320 x 240 RGB565 pixels as PNG, scaled `scale` times.
///
/// Each pixel becomes a `scale` x `scale` block, 8 bits per colour. The function
/// makes the parent folder if needed.
///
/// # Panics
///
/// If `px` is shorter than 320 x 240, or the file cannot be written.
pub fn save_png(path: &std::path::Path, px: &[u16], scale: u32) {
    let (w, h) = (shack_ui::WIDTH, shack_ui::HEIGHT);
    let mut data = Vec::with_capacity((w * h * scale * scale * 3) as usize);
    for y in 0..h * scale {
        for x in 0..w * scale {
            let p = px[((y / scale) * w + x / scale) as usize];
            data.extend([
                ((p >> 11) << 3) as u8,
                (((p >> 5) & 0x3F) << 2) as u8,
                ((p & 0x1F) << 3) as u8,
            ]);
        }
    }
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).unwrap();
    }
    let f = std::fs::File::create(path).unwrap();
    let mut e = png::Encoder::new(std::io::BufWriter::new(f), w * scale, h * scale);
    e.set_color(png::ColorType::Rgb);
    e.set_depth(png::BitDepth::Eight);
    e.write_header().unwrap().write_image_data(&data).unwrap();
}

/// Outside-world commands (terminal UI: type them with a leading `:`).
pub const WORLD_HELP: &str = "\
outside world commands (terminal UI: type them with a leading ':')
  reset                  press RESET              F1
  kill on|off            KILL switch              F2
  cable on|off           Cat6 intact or cut       F3
  power on|off           13.8 V                   F4
  radio R1-R3 on|off     radio wants to transmit  F5-F7
  radio R1-R3 noinh on|off  radio without TX INH input: transmits while inhibited
  box mute on|off        box silent               F8
  shot <file.png>        save the display         F9
  help | ?               this list
F10 auto keep-alive, Ctrl-C quit. Type help (no ':') for the shack commands.";

/// `R1` to `R3` (any case) to the radio index 0 to 2.
fn radio_index(r: &str) -> Result<usize, String> {
    ["R1", "R2", "R3"]
        .iter()
        .position(|x| x.eq_ignore_ascii_case(r))
        .ok_or_else(|| WORLD_HELP.to_string())
}
