//! Shack interface firmware for the ESP32-C3-DevKit-RUST-1 (phase P7).
//!
//! Glue only: [`EspHw`] implements `ShackHw` with esp-hal, and the main loop calls
//! `Shack::tick` every 10 ms. Every decision lives in `shack-core`, the code the
//! emulator tests.
//!
//! The USB Serial/JTAG port is the host port (host-protocol.md), so the firmware
//! writes no log there; a panic prints its backtrace on it. Stored settings
//! (host-protocol.md 8a) go to the flash, at [`SETTINGS_OFFSET`].
//!
//! The DevKit LED (GPIO7 on the DevKit-RUST-1) uses the same code as the box:
//! slow blink (1 Hz) = working, TX possible (self-test passed, no fault, SAFE latch
//! clear, link up, box ready); fast blink (5 Hz) = starting or waiting (self-test
//! running, latched, link down, box not ready); flicker (10 Hz) = self-test failed;
//! on solid = the box reports a link-loss stop. The main loop drives it, so a hung
//! loop also stops the blink. On the
//! shack interface board this pin goes only to JP61 pad 1 (the RUST-2 SDA choice);
//! with JP61 at 2-3 for the RUST-1 it joins no net (D-94).
#![no_std]
#![no_main]
#![deny(
    clippy::mem_forget,
    reason = "mem::forget is generally not safe to do with esp_hal types, especially those \
    holding buffers for the duration of a data transfer."
)]
#![deny(clippy::large_stack_frames)]

use embassy_executor::Spawner;
use embassy_time::{Duration, Instant, Ticker};
use esp_backtrace as _;
use esp_hal::Blocking;
use esp_hal::clock::CpuClock;
use esp_hal::gpio::{AnyPin, Input, InputConfig, Level, Output, OutputConfig, Pull};
use esp_hal::i2c::master::{Config as I2cConfig, I2c};
use esp_hal::spi::master::{Config as SpiConfig, Spi};
use esp_hal::time::Rate;
use esp_hal::timer::timg::TimerGroup;
use esp_hal::uart::{Config as UartConfig, Uart};
use esp_hal::usb::usb_serial_jtag::UsbSerialJtag;
use esp_storage::FlashStorage;
use heapless::Deque;
use host_proto::SelfTestState;
use link_proto::Radio;
use shack_core::board::{DevKit, gpio};
use shack_core::config::CONFIG_MAX;
use shack_core::hw::ShackHw;
use shack_core::shack::{Shack, TICK};
use static_cell::ConstStaticCell;

// This creates a default app-descriptor required by the esp-idf bootloader.
// For more information see: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/app_image_format.html#application-description>
esp_bootloader_esp_idf::esp_app_desc!();

/// How often the loop figures are reported, in ms.
const DIAG_PERIOD: u64 = 10_000;

/// Loop timing over one report window: how long a logic tick takes, and the
/// longest time between the starts of two ticks (the loop rhythm).
#[derive(Default)]
struct Diag {
    tick_max_us: u64,
    tick_sum_us: u64,
    ticks: u64,
    gap_max_us: u64,
    last_start: Option<esp_hal::time::Instant>,
    next_report: u64,
}

impl Diag {
    /// Call just before the tick. Returns its start time for [`Diag::end`].
    fn begin(&mut self) -> esp_hal::time::Instant {
        let t = esp_hal::time::Instant::now();
        if let Some(last) = self.last_start {
            self.gap_max_us = self.gap_max_us.max((t - last).as_micros());
        }
        self.last_start = Some(t);
        t
    }

    /// Call just after the tick.
    fn end(&mut self, start: esp_hal::time::Instant) {
        let d = start.elapsed().as_micros();
        self.tick_max_us = self.tick_max_us.max(d);
        self.tick_sum_us += d;
        self.ticks += 1;
    }

    /// Every [`DIAG_PERIOD`]: the report line (without a newline), and a new window.
    fn report(&mut self, now_ms: u64) -> Option<heapless::String<160>> {
        if self.next_report == 0 {
            // First call: open the first full window.
            self.next_report = now_ms + DIAG_PERIOD;
        }
        if now_ms < self.next_report {
            return None;
        }
        let mut line = heapless::String::new();
        if let Some(avg) = self.tick_sum_us.checked_div(self.ticks) {
            let (used, size) = stack::used();
            let _ = core::fmt::write(
                &mut line,
                format_args!(
                    "diag tick max {} us avg {avg} us, interval max {} us, stack used {used} of {size} bytes",
                    self.tick_max_us, self.gap_max_us
                ),
            );
        }
        *self = Diag {
            next_report: now_ms + DIAG_PERIOD,
            ..Diag::default()
        };
        (!line.is_empty()).then_some(line)
    }
}

/// Stack high-water mark: the free stack is painted with a pattern at boot; the
/// lowest overwritten word shows how deep the stack has ever gone.
mod stack {
    unsafe extern "C" {
        static _stack_end: u32;
        static _stack_start: u32;
    }

    const PAINT: u32 = 0xA55A_5AA5;
    /// esp-hal keeps a stack guard word 60 bytes above `_stack_end`, under a data
    /// watchpoint: paint above it.
    const SKIP: usize = 64;

    fn bounds() -> (usize, usize) {
        (
            &raw const _stack_end as usize + SKIP,
            &raw const _stack_start as usize,
        )
    }

    /// Paint from the low end up to 1 KB below the present stack pointer.
    #[inline(never)]
    pub fn paint() {
        let here = 0u32;
        let sp = core::ptr::addr_of!(here) as usize;
        let (lo, _) = bounds();
        let mut p = lo;
        while p + 1024 < sp {
            // SAFETY: `p` is word aligned, inside the main stack and below the live
            // frames; nothing else uses this memory.
            unsafe { (p as *mut u32).write_volatile(PAINT) };
            p += 4;
        }
    }

    /// Bytes of stack ever used, and the stack size.
    pub fn used() -> (usize, usize) {
        let (lo, hi) = bounds();
        let mut p = lo;
        // SAFETY: as in `paint`: word aligned reads inside the main stack.
        while p < hi && unsafe { (p as *const u32).read_volatile() } == PAINT {
            p += 4;
        }
        (hi - p, hi - lo)
    }
}

const DEVKIT: DevKit = DevKit::Rust1;

/// Flash offset of the stored settings: the `nvs` partition of the default
/// partition table (0x9000, 24 KB). Wi-Fi and BLE are off (D-55), so nothing else
/// uses it, and espflash does not erase it: the settings survive a firmware update.
/// Layout: one length byte, then the record (`shack_core::config`, with its own
/// magic, version and CRC). Erased flash reads 0xFF: no record.
const SETTINGS_OFFSET: u32 = 0x9000;
// The length byte holds the record length.
const _: () = assert!(CONFIG_MAX < 0xFF);

/// Host output buffer. The longest burst is the `help` list, about 1.5 KB.
const USB_OUT: usize = 4096;

// The peripherals below are picked by type; these asserts keep them in line with the pin map.
const _: () = assert!(
    DEVKIT.sda() == 10
        && DEVKIT.led() == 7
        && gpio::SCL == 8
        && gpio::PERMIT_R1 == 0
        && gpio::WDI == 1
        && gpio::DISP_SCK == 2
        && gpio::LATCH_CLR == 3
        && gpio::PERMIT_R2 == 4
        && gpio::PERMIT_R3 == 5
        && gpio::DATA_TX == 6
        && gpio::DISP_MOSI == 9
        && gpio::DATA_RX == 20
        && gpio::SAFE_LOST == 21
);

/// Display frame buffer: 150 KB, in static RAM (not on the stack).
static FRAMEBUFFER: ConstStaticCell<[u8; shack_ui::fb::BYTES]> =
    ConstStaticCell::new([0; shack_ui::fb::BYTES]);

/// `ShackHw` on the ESP32-C3 peripherals.
struct EspHw {
    i2c: I2c<'static, Blocking>,
    permit: [Output<'static>; 3],
    wdi: Output<'static>,
    latch_clr: Output<'static>,
    safe_lost: Input<'static>,
    uart: Uart<'static, Blocking>,
    /// The RX pin stays configured (pull-up) while the UART reads it inverted.
    _data_rx: Input<'static>,
    usb: UsbSerialJtag<'static, Blocking>,
    /// Host bytes waiting for room in the 64-byte USB FIFO. [`EspHw::usb_pump`]
    /// moves them every 1 ms.
    usb_out: Deque<u8, USB_OUT>,
    spi: Spi<'static, Blocking>,
    framebuffer: &'static mut [u8; shack_ui::fb::BYTES],
    flash: FlashStorage<'static>,
}

impl EspHw {
    /// Move waiting host bytes into the USB FIFO until it is full. Never waits.
    fn usb_pump(&mut self) {
        while let Some(&b) = self.usb_out.front() {
            if self.usb.write_byte_nb(b).is_err() {
                break;
            }
            self.usb_out.pop_front();
        }
        let _ = self.usb.flush_tx_nb();
    }
}

impl ShackHw for EspHw {
    type I2c = I2c<'static, Blocking>;

    fn i2c(&mut self) -> &mut Self::I2c {
        &mut self.i2c
    }

    fn set_permit(&mut self, radio: Radio, on: bool) {
        self.permit[radio.index()].set_level(Level::from(on));
    }

    fn set_wdi(&mut self, high: bool) {
        self.wdi.set_level(Level::from(high));
    }

    fn set_latch_clr(&mut self, high: bool) {
        self.latch_clr.set_level(Level::from(high));
    }

    fn safe_lost(&mut self) -> bool {
        self.safe_lost.is_high()
    }

    fn uart_write(&mut self, bytes: &[u8]) {
        // At most one frame per tick (24 bytes): the 128-byte TX FIFO takes it
        // without waiting.
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

    fn usb_write(&mut self, bytes: &[u8]) {
        // Never block: with no host reading, the USB FIFO stays full. A blocked
        // write would stop the main loop, and the watchdog would set the fault
        // latch. Bytes that do not fit in the buffer are dropped.
        for &b in bytes {
            let _ = self.usb_out.push_back(b);
        }
        self.usb_pump();
    }

    fn usb_read(&mut self) -> Option<u8> {
        self.usb.read_byte().ok()
    }

    fn spi_write(&mut self, bytes: &[u8]) {
        let _ = self.spi.write(bytes);
    }

    fn framebuffer(&mut self) -> &mut [u8] {
        &mut self.framebuffer[..]
    }

    fn spi_write_framebuffer(&mut self, start: usize, end: usize) {
        let _ = self.spi.write(&self.framebuffer[start..end]);
    }

    fn config_load(&mut self, buf: &mut [u8]) -> usize {
        let mut b = [0u8; 1 + CONFIG_MAX];
        if self.flash.read(SETTINGS_OFFSET, &mut b).is_err() {
            return 0;
        }
        let n = usize::from(b[0]);
        if n > CONFIG_MAX || n > buf.len() {
            return 0; // erased (0xFF) or not ours: the logic uses its defaults
        }
        buf[..n].copy_from_slice(&b[1..=n]);
        n
    }

    fn config_save(&mut self, record: &[u8]) {
        // The logic saves 2 s after the last change, so a burst of commands gives
        // one write. Erase and write of one 4 KB sector stop the loop for some tens
        // of ms; the watchdog allows 0.9 s.
        let n = record.len().min(CONFIG_MAX);
        let mut b = [0u8; 1 + CONFIG_MAX];
        b[0] = n as u8;
        b[1..=n].copy_from_slice(&record[..n]);
        let _ = self.flash.write(SETTINGS_OFFSET, &b[..=n]);
    }
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

    // Safety outputs low first: no permit, no LATCH_CLR edge, WDI low.
    let low = |pin: AnyPin<'static>| Output::new(pin, Level::Low, OutputConfig::default());
    let permit = [
        low(p.GPIO0.into()),
        low(p.GPIO4.into()),
        low(p.GPIO5.into()),
    ];
    let wdi = low(p.GPIO1.into());
    let mut led = low(p.GPIO7.into());
    let latch_clr = low(p.GPIO3.into());
    // SAFE_LOST: pulled up, so an open input reads 'SAFE lost'.
    let safe_lost = Input::new(p.GPIO21, InputConfig::default().with_pull(Pull::Up));

    let i2c = I2c::new(
        p.I2C0,
        I2cConfig::default().with_frequency(Rate::from_khz(100)),
    )
    .unwrap()
    .with_sda(p.GPIO10)
    .with_scl(p.GPIO8);

    // Box link, 9600 8N1. TX: high = loop current = idle (normal). RX: the sense
    // transistor pulls DATA_RX low on loop current, so the UART reads it inverted
    // (D-58). Pulled up: no cable reads as a break, not as noise.
    let data_rx = Input::new(p.GPIO20, InputConfig::default().with_pull(Pull::Up));
    let rx_signal = data_rx.peripheral_input().with_input_inverter(true);
    let uart = Uart::new(p.UART1, UartConfig::default().with_baudrate(9600))
        .unwrap()
        .with_tx(p.GPIO6)
        .with_rx(rx_signal);

    let spi = Spi::new(
        p.SPI2,
        SpiConfig::default().with_frequency(Rate::from_mhz(40)),
    )
    .unwrap()
    .with_sck(p.GPIO2)
    .with_mosi(p.GPIO9);

    let mut hw = EspHw {
        i2c,
        permit,
        wdi,
        latch_clr,
        safe_lost,
        uart,
        _data_rx: data_rx,
        usb: UsbSerialJtag::new(p.USB_DEVICE),
        usb_out: Deque::new(),
        spi,
        framebuffer: FRAMEBUFFER.take(),
        flash: FlashStorage::new(p.FLASH),
    };

    stack::paint();
    let mut diag = Diag::default();
    let mut shack = Shack::new();
    // 1 ms loop: the USB pump every pass, the logic every TICK (10 ms).
    let mut ticker = Ticker::every(Duration::from_millis(1));
    let mut next_tick = 0;
    loop {
        let now = Instant::now().as_millis();
        if now >= next_tick {
            let t = diag.begin();
            shack.tick(now, &mut hw);
            diag.end(t);
            // Half period of the blink, or `None` for on solid.
            let boxs = shack.box_status().filter(|_| shack.link_up());
            let half = match shack.self_test() {
                SelfTestState::Running => Some(100),
                SelfTestState::Fail(_) => Some(50),
                SelfTestState::Pass if boxs.is_some_and(|s| s.flags.link_lost_stop) => None,
                SelfTestState::Pass => {
                    let latched = shack.inputs().is_none_or(|i| i.latched);
                    let ready = boxs.is_some_and(|s| s.flags.ready);
                    if !latched && ready && !shack.fault_known() {
                        Some(500)
                    } else {
                        Some(100)
                    }
                }
            };
            led.set_level(Level::from(
                half.is_none_or(|h| (now / h).is_multiple_of(2)),
            ));
            next_tick = now + TICK;
            // A `#` log line for people (host-protocol.md section 3), between the
            // lines of the logic.
            if let Some(line) = diag.report(now) {
                hw.usb_write(b"# ");
                hw.usb_write(line.as_bytes());
                hw.usb_write(b"\n");
            }
        }
        hw.usb_pump();
        ticker.next().await;
    }
}
