//! Box controller firmware for the ESP32-C3-DevKit-RUST-1 (phase P7).
//!
//! Glue only: [`EspHw`] implements `BoxHw` with esp-hal, and the main loop calls
//! `RelayBox::tick` every 1 ms. Every decision lives in `box-core`, the code the
//! emulator tests.
//!
//! The box has no host port. Its USB Serial/JTAG port carries a debug log: one
//! line at boot, and one line each time the phase, the fault code or a status flag
//! changes. Nothing in the logic depends on it.
//!
//! The DevKit LED (GPIO7 on the DevKit-RUST-1) shows the phase: slow blink (1 Hz)
//! in Run, fast blink (5 Hz) in Boot, while waiting for the SAFE loop and during
//! the self-test, flicker (10 Hz) when the self-test failed, on solid when stopped. The main loop drives it, so a hung loop also stops the blink.
#![no_std]
#![no_main]
#![deny(
    clippy::mem_forget,
    reason = "mem::forget is generally not safe to do with esp_hal types, especially those \
    holding buffers for the duration of a data transfer."
)]
#![deny(clippy::large_stack_frames)]

use box_core::board::gpio;
use box_core::hw::BoxHw;
use box_core::relay_box::{FW_VERSION, Phase, RelayBox, TICK};
use embassy_executor::Spawner;
use embassy_time::{Duration, Instant, Ticker};
use esp_backtrace as _;
use esp_hal::Blocking;
use esp_hal::clock::CpuClock;
use esp_hal::gpio::{AnyPin, Input, InputConfig, Level, Output, OutputConfig, Pull};
use esp_hal::i2c::master::{Config as I2cConfig, I2c};
use esp_hal::time::Rate;
use esp_hal::timer::timg::TimerGroup;
use esp_hal::uart::{Config as UartConfig, Uart};
use esp_println::println;
use link_proto::{FaultCode, Flags};

// This creates a default app-descriptor required by the esp-idf bootloader.
// For more information see: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/app_image_format.html#application-description>
esp_bootloader_esp_idf::esp_app_desc!();

/// I2C data line: GPIO10 on the DevKit-RUST-1 (JP11 select on the controller board).
const SDA: u8 = 10;
/// The DevKit-RUST-1 board LED (470R to GND). On the controller board this pin
/// (pad 12) goes only to JP11 pad 1, the RUST-2 SDA choice; with JP11 at 2-3 for the
/// RUST-1 it joins no net (D-94).
const LED: u8 = 7;

// The peripherals below are picked by type; these asserts keep them in line with the pin map.
const _: () = assert!(
    SDA == 10
        && LED == 7
        && gpio::EXP_INT == 0
        && gpio::WDI == 1
        && gpio::LATCH_CLR == 3
        && gpio::MCU_EN_N == 4
        && gpio::KILL == 5
        && gpio::SCL == 8
        && gpio::DATA_RX == 20
        && gpio::DATA_TX == 21
);

/// `BoxHw` on the ESP32-C3 peripherals.
struct EspHw {
    i2c: I2c<'static, Blocking>,
    wdi: Output<'static>,
    latch_clr: Output<'static>,
    mcu_en_n: Output<'static>,
    kill: Input<'static>,
    uart: Uart<'static, Blocking>,
    /// The RX pin stays configured (pull-up) while the UART reads it inverted.
    _data_rx: Input<'static>,
}

impl BoxHw for EspHw {
    type I2c = I2c<'static, Blocking>;

    fn i2c(&mut self) -> &mut Self::I2c {
        &mut self.i2c
    }

    fn set_wdi(&mut self, high: bool) {
        self.wdi.set_level(Level::from(high));
    }

    fn set_latch_clr(&mut self, high: bool) {
        self.latch_clr.set_level(Level::from(high));
    }

    fn set_mcu_en_n(&mut self, high: bool) {
        self.mcu_en_n.set_level(Level::from(high));
    }

    fn kill(&mut self) -> bool {
        self.kill.is_high()
    }

    fn uart_write(&mut self, bytes: &[u8]) {
        // One Status (18 bytes) per frame: the 128-byte TX FIFO takes it at once.
        let mut rest = bytes;
        while !rest.is_empty() {
            match self.uart.write(rest) {
                Ok(n) => rest = &rest[n..],
                Err(_) => return,
            }
        }
    }

    fn uart_read(&mut self) -> Option<u8> {
        if !self.uart.read_ready() {
            return None;
        }
        let mut b = [0u8; 1];
        match self.uart.read_buffered(&mut b) {
            Ok(1) => Some(b[0]),
            _ => None,
        }
    }
}

/// What the debug log follows: a line goes out when one of these changes.
#[derive(Clone, Copy, PartialEq)]
struct Seen {
    phase: Phase,
    fault: FaultCode,
    flags: Flags,
}

#[allow(
    clippy::large_stack_frames,
    reason = "it's not unusual to allocate larger buffers etc. in main"
)]
#[esp_rtos::main]
async fn main(_spawner: Spawner) -> ! {
    let config = esp_hal::Config::default().with_cpu_clock(CpuClock::max());
    let p = esp_hal::init(config);

    let timg0 = TimerGroup::new(p.TIMG0);
    esp_rtos::start(timg0.timer0, p.FROM_CPU_INTR0);

    // Safe levels first: MCU_EN_N high (no RLY_EN, READY open), LATCH_CLR and WDI low.
    let out = |pin: AnyPin<'static>, level| Output::new(pin, level, OutputConfig::default());
    let mcu_en_n = out(p.GPIO4.into(), Level::High);
    let latch_clr = out(p.GPIO3.into(), Level::Low);
    let wdi = out(p.GPIO1.into(), Level::Low);
    let mut led = out(p.GPIO7.into(), Level::Low);
    // KILL: pulled up as R34 does, so an open input reads 'no SAFE loop current'.
    let kill = Input::new(p.GPIO5, InputConfig::default().with_pull(Pull::Up));

    let i2c = I2c::new(
        p.I2C0,
        I2cConfig::default().with_frequency(Rate::from_khz(100)),
    )
    .unwrap()
    .with_sda(p.GPIO10)
    .with_scl(p.GPIO8);

    // Shack link, 9600 8N1. TX: high = PC817 LED on = loop current = idle (normal).
    // RX: the VO2611 pulls DATA_RX low on loop current, so the UART reads it
    // inverted (D-58). Pulled up: no cable reads as a break.
    let data_rx = Input::new(p.GPIO20, InputConfig::default().with_pull(Pull::Up));
    let rx_signal = data_rx.peripheral_input().with_input_inverter(true);
    let uart = Uart::new(p.UART1, UartConfig::default().with_baudrate(9600))
        .unwrap()
        .with_tx(p.GPIO21)
        .with_rx(rx_signal);

    let mut hw = EspHw {
        i2c,
        wdi,
        latch_clr,
        mcu_en_n,
        kill,
        uart,
        _data_rx: data_rx,
    };

    let [a, b, c] = FW_VERSION;
    println!("box-esp32c3 {a}.{b}.{c}: boot");

    let mut fw = RelayBox::new();
    let mut seen: Option<Seen> = None;
    let mut ticker = Ticker::every(Duration::from_millis(TICK));
    loop {
        let now = Instant::now().as_millis();
        fw.tick(now, &mut hw);
        let st = fw.status();
        let s = Seen {
            phase: fw.phase(),
            fault: st.fault,
            flags: st.flags,
        };
        // Half period of the blink, or `None` for on solid.
        let half = match s.phase {
            Phase::Run => Some(500),
            Phase::Boot | Phase::WaitSafe { .. } | Phase::SelfTest(_) => Some(100),
            Phase::Stopped => None,
            Phase::Failed => Some(50),
        };
        led.set_level(Level::from(
            half.is_none_or(|h| (now / h).is_multiple_of(2)),
        ));
        if seen != Some(s) {
            let f = s.flags;
            println!(
                "{now} ms: {:?}, fault {}, ready {}, kill {}, tx_any {}, switching {}, link_lost_stop {}",
                s.phase,
                s.fault.0,
                u8::from(f.ready),
                u8::from(f.kill),
                u8::from(f.tx_any),
                u8::from(f.switching),
                u8::from(f.link_lost_stop)
            );
            seen = Some(s);
        }
        ticker.next().await;
    }
}
