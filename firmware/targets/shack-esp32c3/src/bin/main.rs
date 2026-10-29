//! Shack interface firmware, P0 bring-up: log over USB, scan the I2C bus, blink the board LED.
//! Runs on a bare ESP32-C3-DevKit-RUST-1. Logic lives in shack-core; this crate is glue only.
#![no_std]
#![no_main]
#![deny(
    clippy::mem_forget,
    reason = "mem::forget is generally not safe to do with esp_hal types, especially those \
    holding buffers for the duration of a data transfer."
)]
#![deny(clippy::large_stack_frames)]

use embassy_executor::Spawner;
use embassy_time::{Duration, Timer};
use esp_backtrace as _;
use esp_hal::clock::CpuClock;
use esp_hal::gpio::{Level, Output, OutputConfig};
use esp_hal::i2c::master::{Config as I2cConfig, I2c};
use esp_hal::time::Rate;
use esp_hal::timer::timg::TimerGroup;
use log::info;
use shack_core::board::{DevKit, EXPANDER_ADDR, gpio};

// This creates a default app-descriptor required by the esp-idf bootloader.
// For more information see: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/app_image_format.html#application-description>
esp_bootloader_esp_idf::esp_app_desc!();

const DEVKIT: DevKit = DevKit::Rust1;

// The peripherals below are picked by type; these asserts keep them in line with the pin map.
const _: () = assert!(DEVKIT.led() == 7 && DEVKIT.sda() == 10 && gpio::SCL == 8);

#[allow(
    clippy::large_stack_frames,
    reason = "it's not unusual to allocate larger buffers etc. in main"
)]
#[esp_rtos::main]
async fn main(_spawner: Spawner) -> ! {
    esp_println::logger::init_logger_from_env();

    let config = esp_hal::Config::default().with_cpu_clock(CpuClock::max());
    let peripherals = esp_hal::init(config);

    let timg0 = TimerGroup::new(peripherals.TIMG0);
    esp_rtos::start(timg0.timer0, peripherals.FROM_CPU_INTR0);

    info!(
        "shack-esp32c3 {} on {:?}",
        env!("CARGO_PKG_VERSION"),
        DEVKIT
    );

    let mut i2c = I2c::new(
        peripherals.I2C0,
        I2cConfig::default().with_frequency(Rate::from_khz(100)),
    )
    .unwrap()
    .with_sda(peripherals.GPIO10)
    .with_scl(peripherals.GPIO8);

    // Bare DevKit: SHTC3 at 0x70 and the IMU at 0x68. On the shack board: the PCA9539 as well.
    let mut found = 0;
    for addr in 0x08..0x78u8 {
        if i2c.write(addr, &[]).is_ok() {
            info!("i2c: device at {addr:#04x}");
            found += 1;
        }
    }
    info!(
        "i2c: {found} device(s); PCA9539 {:#04x} {}",
        EXPANDER_ADDR,
        if i2c.write(EXPANDER_ADDR, &[]).is_ok() {
            "present"
        } else {
            "absent"
        }
    );

    let mut led = Output::new(peripherals.GPIO7, Level::Low, OutputConfig::default());
    let mut ticks: u32 = 0;
    loop {
        led.toggle();
        ticks += 1;
        if ticks.is_multiple_of(10) {
            info!("alive, {} s", ticks / 2);
        }
        Timer::after(Duration::from_millis(500)).await;
    }
}
