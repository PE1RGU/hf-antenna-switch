//! Shack board model against hardware/unit/verify/verify_system.py (sections 1, 3, 4, 5 E3)
//! and the firmware findings F1 and F14 that depend on the board.
//! The MCU side goes through the embedded-hal adapters, as the firmware will.

use embedded_hal::i2c::I2c;
use embedded_hal::spi::SpiBus;
use shack_core::board::{EXPANDER_ADDR, ExpPin, exp, gpio};
use sim_core::SimTime;
use sim_core::hal::{Board, Shared, SimI2c, SimSpi, shared};
use sim_models::shack::ShackBoard;
use sim_models::tps3823::Corner;

type B = Shared<ShackBoard>;

fn ms(n: u64) -> SimTime {
    SimTime::ms(n)
}

/// Board powered for 300 ms: both supervisors out of reset (td max 300 ms at Typ is 200).
fn powered() -> B {
    let b = shared(ShackBoard::new(Corner::Typ));
    b.borrow_mut().set_env(|e| e.power = true);
    b.borrow_mut().run(ms(300));
    b
}

fn gpio_set(b: &B, pin: u8, high: bool) {
    b.borrow_mut().gpio_write(pin, high);
}

fn clear_fault(b: &B) {
    gpio_set(b, gpio::LATCH_CLR, false);
    gpio_set(b, gpio::LATCH_CLR, true);
    gpio_set(b, gpio::LATCH_CLR, false);
}

fn press_reset(b: &B) {
    b.borrow_mut().set_env(|e| e.reset_pressed = true);
    b.borrow_mut().run(ms(1));
    b.borrow_mut().set_env(|e| e.reset_pressed = false);
}

/// Expander outputs in the F1 order: output register first, then configuration.
fn exp_setup(b: &B, out: u16) {
    let mut i2c = SimI2c(b.clone());
    let [lo, hi] = out.to_le_bytes();
    i2c.write(EXPANDER_ADDR, &[2, lo, hi]).unwrap();
    let [lo, hi] = shack_core::board::expander_config().to_le_bytes();
    i2c.write(EXPANDER_ADDR, &[6, lo, hi]).unwrap();
}

fn exp_write_out(b: &B, out: u16) {
    let [lo, hi] = out.to_le_bytes();
    SimI2c(b.clone())
        .write(EXPANDER_ADDR, &[2, lo, hi])
        .unwrap();
}

fn exp_inputs(b: &B) -> u16 {
    let mut buf = [0u8; 2];
    SimI2c(b.clone())
        .write_read(EXPANDER_ADDR, &[0], &mut buf)
        .unwrap();
    u16::from_le_bytes(buf)
}

fn bit(p: ExpPin) -> u16 {
    1 << p.bit
}

/// SW_STOP_N high (loop on), everything else 0.
const OUT_IDLE: u16 = 1 << exp::SW_STOP_N.bit;

fn sig(b: &B) -> sim_models::shack::Signals {
    b.borrow().signals()
}

#[test]
fn power_up_state_is_safe() {
    let b = shared(ShackBoard::new(Corner::Typ));
    b.borrow_mut().set_env(|e| e.power = true);
    b.borrow_mut().run(ms(100));
    let s = sig(&b);
    assert!(!s.reset_n && !s.por_n);
    assert!(s.fault && s.latched && !s.tx_en);
    assert_eq!(s.inhibit, [true; 3]);
    assert_eq!(s.key_contact, [false; 3]);
    assert!(
        s.safe_current,
        "R35 holds the SAFE source on while the expander is in reset"
    );
    b.borrow_mut().run(ms(200));
    let s = sig(&b);
    assert!(s.reset_n && s.por_n);
    assert!(s.fault && s.latched, "both latches hold until cleared");
    assert_eq!(b.borrow().exp.config_reg(), 0xFFFF);
}

/// verify_system.py section 3, sequences L1 to L5. Event = (loop, power, RESET), one per 300 ms.
#[test]
fn safe_latch_sequences() {
    #[allow(clippy::type_complexity)]
    let seqs: [(&str, [(bool, bool, bool); 4], [bool; 4]); 5] = [
        (
            "L1",
            [
                (true, false, false),
                (true, true, false),
                (true, true, true),
                (true, true, false),
            ],
            [true, true, false, false],
        ),
        (
            "L2",
            [
                (true, true, false),
                (true, true, true),
                (false, true, false),
                (true, true, false),
            ],
            [true, false, true, true],
        ),
        (
            "L3",
            [
                (true, true, true),
                (false, true, false),
                (false, true, true),
                (false, true, false),
            ],
            [false, true, true, true],
        ),
        (
            "L4",
            [
                (true, true, true),
                (false, true, true),
                (true, true, true),
                (true, true, true),
            ],
            [false, true, true, true],
        ),
        (
            "L5",
            [
                (true, true, true),
                (true, true, false),
                (true, false, false),
                (true, true, false),
            ],
            [false, false, true, true],
        ),
    ];
    for (name, events, expected) in seqs {
        let b = powered();
        let mut got = [false; 4];
        for (i, &(lp, pw, rst)) in events.iter().enumerate() {
            b.borrow_mut().set_env(|e| {
                e.cable_ok = lp;
                e.power = pw;
                e.reset_pressed = rst;
            });
            b.borrow_mut().run(ms(300));
            got[i] = sig(&b).latched;
        }
        assert_eq!(got, expected, "{name}");
    }
}

#[test]
fn reset_during_power_on_reset_does_not_clear() {
    let b = shared(ShackBoard::new(Corner::Typ));
    b.borrow_mut().set_env(|e| e.power = true);
    b.borrow_mut().run(ms(100));
    press_reset(&b);
    b.borrow_mut().run(ms(300));
    assert!(sig(&b).latched);
}

/// verify_system.py section 1, shack side: the loop is a wired AND of five conditions.
#[test]
fn safe_loop_is_a_wired_and() {
    for row in 0..32u8 {
        let [kill_closed, no_stop, cable, power, ready] =
            [0, 1, 2, 3, 4].map(|i| row & (1 << i) != 0);
        let b = powered();
        if !no_stop {
            exp_setup(&b, 0);
        }
        b.borrow_mut().set_env(|e| {
            e.kill_pressed = !kill_closed;
            e.cable_ok = cable;
            e.box_ready = ready;
            e.power = power;
        });
        b.borrow_mut().run(ms(1));
        let s = sig(&b);
        let all = kill_closed && no_stop && cable && power && ready;
        assert_eq!(s.safe_current, all, "row {row:05b}");
        if power {
            assert_eq!(b.borrow_mut().gpio_read(gpio::SAFE_LOST), !all);
        }
    }
}

/// verify_system.py section 4: TX INH and keying per port, all 32 rows, all three ports.
#[test]
fn port_inhibit_and_keying_table() {
    let keys = [exp::KEY_R1, exp::KEY_R2, exp::KEY_R3];
    let permits = [gpio::PERMIT_R1, gpio::PERMIT_R2, gpio::PERMIT_R3];
    for row in 0..32u8 {
        let [permit, key, fault, latched, power] = [0, 1, 2, 3, 4].map(|i| row & (1 << i) != 0);
        let b = powered();
        if !fault {
            clear_fault(&b);
        }
        if !latched {
            press_reset(&b);
        }
        let key_bits = keys.iter().fold(0, |w, k| w | bit(*k));
        exp_setup(&b, OUT_IDLE | if key { key_bits } else { 0 });
        for p in permits {
            gpio_set(&b, p, permit);
        }
        if !power {
            b.borrow_mut().set_env(|e| e.power = false);
        }
        let s = sig(&b);
        assert_eq!(s.fault, fault || !power, "row {row:05b}");
        assert_eq!(s.latched, latched || !power, "row {row:05b}");
        let cond = permit && !fault && !latched && power;
        for n in 0..3 {
            assert_eq!(s.inhibit[n], !cond, "row {row:05b} port {n}");
            assert_eq!(s.key_contact[n], key && cond, "row {row:05b} port {n}");
            assert!(!(s.inhibit[n] && s.key_contact[n]), "keyed while inhibited");
        }
    }
}

#[test]
fn software_stop_opens_loop_and_sets_latch() {
    let b = powered();
    clear_fault(&b);
    press_reset(&b);
    exp_setup(&b, OUT_IDLE);
    assert!(sig(&b).tx_en);
    exp_write_out(&b, 0);
    let s = sig(&b);
    assert!(!s.safe_current && s.latched && !s.tx_en);
    // Loop back on: the latch holds until RESET.
    exp_write_out(&b, OUT_IDLE);
    b.borrow_mut().run(ms(10));
    assert!(sig(&b).safe_current && sig(&b).latched);
    press_reset(&b);
    assert!(sig(&b).tx_en);
}

#[test]
fn latch_clr_only_works_after_reset_n() {
    let b = shared(ShackBoard::new(Corner::Typ));
    b.borrow_mut().set_env(|e| e.power = true);
    b.borrow_mut().run(ms(50));
    clear_fault(&b);
    assert!(sig(&b).fault, "RESET_N low holds PRE_N low");
    b.borrow_mut().run(ms(250));
    clear_fault(&b);
    assert!(!sig(&b).fault);
}

/// Kick period 0.25 s keeps the supervisor quiet at the shortest time-out (C-19).
#[test]
fn watchdog_kicked_every_250_ms_stays_quiet() {
    let b = shared(ShackBoard::new(Corner::Min));
    b.borrow_mut().set_env(|e| e.power = true);
    b.borrow_mut().run(ms(200));
    clear_fault(&b);
    for i in 0..40 {
        gpio_set(&b, gpio::WDI, i % 2 == 1);
        b.borrow_mut().run(ms(250));
    }
    assert!(!sig(&b).fault);
    assert_eq!(
        b.borrow().trace.signal("RESET_N").len(),
        2,
        "one reset at power-up only"
    );
}

/// verify_system.py section 5, E3: the shack MCU hangs with a permit set.
#[test]
fn mcu_hang_drops_all_permits_after_watchdog() {
    let b = shared(ShackBoard::new(Corner::Max));
    b.borrow_mut().set_env(|e| e.power = true);
    b.borrow_mut().run(ms(300));
    clear_fault(&b);
    press_reset(&b);
    exp_setup(&b, OUT_IDLE | bit(exp::KEY_R2));
    gpio_set(&b, gpio::PERMIT_R2, true);
    gpio_set(&b, gpio::WDI, true);
    assert!(!sig(&b).inhibit[1] && sig(&b).key_contact[1]);
    let hang = b.borrow().now();
    // No more WDI edges.
    b.borrow_mut().run(ms(3000));
    let t_fault = b
        .borrow()
        .trace
        .signal("FAULT")
        .into_iter()
        .find(|(t, v)| *t > hang && *v)
        .map(|(t, _)| t)
        .expect("fault set");
    assert!(t_fault - hang <= SimTime::ms(2500), "within tout max");
    let s = sig(&b);
    assert!(s.fault && s.inhibit[1] && !s.key_contact[1]);
    assert!(
        !b.borrow().exp_pin(exp::KEY_R2),
        "expander reset by RESET_N: key off"
    );
    assert!(
        s.safe_current,
        "the shack hang does not stop the box (D-75)"
    );
}

/// F1: configuring a key pin as output before writing its output register keys the radio.
#[test]
fn f1_config_before_output_keys_the_radio() {
    let b = powered();
    clear_fault(&b);
    press_reset(&b);
    gpio_set(&b, gpio::PERMIT_R3, true);
    let cfg = shack_core::board::expander_config().to_le_bytes();
    SimI2c(b.clone())
        .write(EXPANDER_ADDR, &[6, cfg[0], cfg[1]])
        .unwrap();
    assert!(sig(&b).key_contact[2], "wrong order: KEY_R3 high at once");

    let b = powered();
    clear_fault(&b);
    press_reset(&b);
    gpio_set(&b, gpio::PERMIT_R3, true);
    exp_setup(&b, OUT_IDLE);
    assert!(!b.borrow().trace.signal("KEYC_R3").iter().any(|(_, v)| *v));
}

#[test]
fn ptt_loop_follows_r1_tx_sense_without_the_mcu() {
    let b = powered(); // fault and latch still set: MCU has done nothing
    b.borrow_mut().set_env(|e| e.radio_tx[0] = true);
    assert!(sig(&b).ptt_loop);
    b.borrow_mut().set_env(|e| e.cable_ok = false);
    assert!(!sig(&b).ptt_loop);
    b.borrow_mut().set_env(|e| {
        e.cable_ok = true;
        e.power = false;
    });
    assert!(!sig(&b).ptt_loop);
}

#[test]
fn inputs_read_through_the_expander() {
    let b = powered();
    exp_setup(&b, OUT_IDLE);
    b.borrow_mut().set_env(|e| {
        e.radio_tx = [true, false, true];
        e.kill_pressed = true;
        e.band = 0b0101;
    });
    let r = exp_inputs(&b);
    for (p, v) in [
        (exp::R1_TX, true),
        (exp::R2_TX, false),
        (exp::R3_TX, true),
        (exp::KILL_S, true),
        (exp::LATCHED, true),
        (exp::BAND_A, true),
        (exp::BAND_B, false),
        (exp::BAND_C, true),
        (exp::BAND_D, false),
    ] {
        assert_eq!(r & bit(p) != 0, v, "{}", p.name);
    }
}

#[test]
fn i2c_scan_sees_expander_and_devkit_parts() {
    let b = powered();
    let mut i2c = SimI2c(b.clone());
    let found: Vec<u8> = (0x08..0x78)
        .filter(|&a| i2c.write(a, &[]).is_ok())
        .collect();
    assert_eq!(found, [0x68, 0x70, 0x74]);
    b.borrow_mut().set_env(|e| e.power = false);
    assert!(i2c.write(EXPANDER_ADDR, &[]).is_err());
}

#[test]
fn data_link_bytes_and_cable_cut() {
    let b = powered();
    for byte in [0x11, 0x22] {
        b.borrow_mut().uart_write(byte);
    }
    b.borrow_mut().run(ms(1));
    assert_eq!(
        b.borrow_mut().box_recv(),
        None,
        "1 ms: first byte still on the line"
    );
    b.borrow_mut().run(ms(2));
    assert_eq!(b.borrow_mut().box_recv(), Some(0x11));
    assert_eq!(b.borrow_mut().box_recv(), Some(0x22));

    b.borrow_mut().box_send(0x33);
    b.borrow_mut().run(ms(2));
    assert_eq!(b.borrow_mut().uart_read(), Some(0x33));

    b.borrow_mut().set_env(|e| e.cable_ok = false);
    b.borrow_mut().uart_write(0x44);
    b.borrow_mut().box_send(0x55);
    b.borrow_mut().run(ms(5));
    assert_eq!(b.borrow_mut().box_recv(), None);
    assert_eq!(b.borrow_mut().uart_read(), None);
}

#[test]
fn display_over_spi_with_dc_on_the_expander() {
    let b = powered();
    exp_setup(&b, OUT_IDLE | bit(exp::DISP_RST) | bit(exp::DISP_BL));
    let mut spi = SimSpi(b.clone());
    let dc = |b: &B, data: bool| {
        let base = OUT_IDLE | bit(exp::DISP_RST) | bit(exp::DISP_BL);
        exp_write_out(b, if data { base | bit(exp::DISP_DC) } else { base });
    };
    for (c, args) in [
        (0x11u8, &[][..]),
        (0x3A, &[0x55]),
        (0x29, &[]),
        (0x2A, &[0, 5, 0, 5]),
        (0x2B, &[0, 7, 0, 7]),
        (0x2C, &[0x12, 0x34]),
    ] {
        dc(&b, false);
        spi.write(&[c]).unwrap();
        dc(&b, true);
        spi.write(args).unwrap();
    }
    let board = b.borrow();
    assert!(board.lcd.showing());
    assert_eq!(board.lcd.pixel(5, 7), 0x1234);
}

#[test]
fn trace_records_signal_changes() {
    let b = powered();
    clear_fault(&b);
    let t = b.borrow().now();
    let tr = &b.borrow().trace;
    assert_eq!(tr.level_at("FAULT", t), Some(false));
    assert_eq!(tr.signal("POR_N").last().map(|x| x.1), Some(true));
    assert!(tr.signal("LATCH_CLR").len() >= 2);
}
