# Test report: shack interface rev A, layout p8g

Board serial: ____  Date: 2026-11-25  Tester: Prins

## P-01 Smoke test (TC-13)

| Step | Measured | Pass / fail | Note |
|---|---|---|---|
| 1 Resistance J3+, TP2, TP3 to GND | done (values not recorded) | pass | No short |
| 2 Reverse polarity current | 7 mA at 13.8 V reversed, limit 10 mA (expected below 1 mA) | open | Deferred to the end of P-01 (Prins). Check supply no-load offset, other connections, drift over 30 s, voltage across D1 |
| 3 Supply current, no load | 11.4 mA at 13.8 V | pass | Inside the 10 to 25 mA estimate |
| 4 TP1 / TP2 / TP3 | 13.52 V / 5.014 V / 3.302 V | pass | D1 drop 0.28 V at 11 mA |
| 5 RESET_N pulse width / period; FAULT | 180 ms / 1.6 s; FAULT high | pass | Width inside 140 to 280 ms (MAX823); watchdog runs without the MCU |
| 6 J6 pin 2 / pin 3, loop open | pin 2 low, pin 3 3.3 V; stays 3.3 V with RESET short | pass | |
| 7 R36 / R46 voltage; supply current | R36 1.06 V / R46 1.06 V (10.6 mA each); supply 35 mA; J6 pin 2 3.3 V | pass | First try had the 470R on the wrong pair. 3 mA above the 32 mA sum: partly the sense pull-ups R38, R48 (0.33 mA each, now pulled low); the rest within the supply meter resolution |
| 8 LATCHED clear | `!latched 0`, status latched=0 (with MCU, P-02) | pass | Done after the DevKit was fitted |
| 9 KILL open | J2 link removed: `!latched 1`, status safe=lost latched=1 | pass | Link refitted: `!safe ok`, latched stays 1 until RESET. kill=0 because J7 stays linked; the real switch opens both poles |
| 10 Pairs 1 and 2 | pair 1 4.7 V over 470R (10.0 mA), pair 2 0 V (with MCU) | pass | Pair 1 on because DATA_TX idles high; pair 2 off without R1 TX sense. Pair assignment to confirm (Prins) |

## P-02 MCU bring-up (DevKit-RUST-1, firmware of 2026-10-31)

Dummy box on J1 (470R on pairs 3 and 4), links on J2 and J7, no display, no front panel, no radio.

| Check | Measured | Pass / fail | Note |
|---|---|---|---|
| Boot | C3 runs, host port on J14 | pass | |
| Self-test | `!selftest pass`; expander ready, lost, ready (watchdog trip on purpose) | pass | |
| status | `ok link=down safe=ok latched=1 kill=0 fault=0 stop=0 ... band=15 ... permit=0 (all) selftest=pass` | pass | latched=1 until RESET; band=15 = no radio on R1 |
| Supply current, TP3 | 50 to 54 mA (loops 3 and 4 on); TP3 3.3 V | pass | DevKit adds about 15 to 19 mA over the 35 mA of P-01 step 7. U1 about 0.45 W |
| RESET_N pulses stopped (U3 pin 1) | high, no pulses | pass | Firmware kicks WDI |

## P-03 Front panel (J6: RESET button, SAFE and LATCHED LEDs)

| Check | Measured | Pass / fail | Note |
|---|---|---|---|
| Power-up | Red (LATCHED) and green (SAFE) on; `!safe ok`, `!latched 1`, `!selftest pass` | pass | Dummy box on J1, links on J2 and J7 |
| RESET button (normally open, J6 pin 1 to 4) | Red off, green on; `!latched 0` | pass | |
| KILL switch (EAO 84, NC 1 on J2, NC 2 on J7) | Pressed: `!safe lost`, `!latched 1`, `!kill 1`. Released: `!safe ok`, `!kill 0`, latched stays 1 | pass | Four `err syntax` lines during the test: stray key presses in `screen` (Prins); firmware skips empty lines |

## P-04 Display (Waveshare 2inch on J15)

| Check | Measured | Pass / fail | Note |
|---|---|---|---|
| Display runs (SPI, DC, RST, backlight) | Page drawn, clean | pass | |
| Fault screen "Supervisor reset · TX blocked", cause "Watchdog or brown-out" | Log: `!selftest fail latch`, no `!expander lost` | no hardware fault | Boot came from the espflash monitor reset (MCU only, board stayed powered, SAFE latch already cleared). The self-test expects the latch set by a power-up, so it failed. Firmware findings FW-1 and FW-2 below. Power-cycle check pending |

Firmware findings from the bench (2026-11-26):

- FW-1 (fixed in D-220, PR #39): the self-test latch check fails after an MCU-only reset (espflash, USB reset, panic reset) while the SAFE latch is clear. Option: check the ESP32-C3 reset reason and run the latch check only after a power-on reset.
- FW-2 (fixed in D-220, PR #39): the Fault screen shows "Watchdog or brown-out" (wording.rs `cause`, `None`) when the real cause is a self-test fail. It should name the failed self-test item.
