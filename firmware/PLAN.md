# Firmware plan: Rust, emulated board first

Status: draft, 2026-10-29. For review by Prins.

## 1. Goal

Write the shack interface firmware first, then the box (relay matrix) firmware.
Develop and test both on the Mac, against an emulated board, before any board is built.
The same firmware logic runs later on the ESP32-C3-DevKit-RUST without change.

## 2. Approach: emulate at the HAL boundary

The firmware talks to hardware only through `embedded-hal` 1.0 traits: `I2c`, `SpiDevice`, `InputPin`, `OutputPin`, plus `embedded-io` for the UART and a clock.

- On the target, `esp-hal` gives these traits.
- On the Mac, the simulator gives them. Behind each trait sits a model of the real part.

We do not emulate the RISC-V CPU. Reason: the risk in this project is the logic and timing (F1 to F14, the handshake, the SAFE chain), not the instructions. A HAL-level model is fast, deterministic and easy to probe.

Virtual time: the simulator owns the clock. A test can run 10 minutes of operation in milliseconds, and can step 1 ms at a time to check the 12 ms and 100 ms rules.

## 3. Workspace layout

```
firmware/
  Cargo.toml              workspace
  crates/
    link-proto/           no_std. Frame format, encode, decode, CRC, sequence numbers. Shared by box and shack.
    pca9539/              no_std driver, generic over embedded-hal I2c. Enforces the F1 write order.
    shack-core/           no_std. Shack logic as a state machine: inputs + time in, actions out. No hardware calls.
    box-core/             no_std. Box logic: routes, crossbar check, handshake, safety start-up.
    host-proto/           no_std. Commands and reports between the Mac and the shack (USB CDC).
  targets/
    shack-esp32c3/        binary. esp-hal + embassy. Glue only.
    box-esp32c3/          binary. esp-hal + embassy. Glue only.
  sim/
    sim-core/             virtual clock, nets, event queue, trace recorder.
    models/               part and board models (section 4).
    sim-shack/            runs shack-core on the shack board model. CLI and front panel window.
    sim-system/           runs both firmwares, both boards and the link together.
    scenarios/            scripted tests (section 6).
```

Rule: `*-core` crates hold all decisions. Target crates hold no logic. So the code we test in the simulator is the code we flash.

## 4. Models

Each model follows the datasheet and the netlist. Source of truth: the KiCad netlists (si16.xml, ctl14.xml, rf14.xml) and the verify scripts.

| Model | Behaviour to model | Source |
|---|---|---|
| PCA9539 | Registers 0 to 7, output register = 0xFF after reset, RESET pin holds all pins as inputs, polled reads, bus errors on demand | Datasheet, F1, F3, F8 |
| I2C bus | Address decode 0x74 to 0x77, NACK on missing device, stuck SDA fault | D-49, D-52 |
| RT1 relay | Coil on, operate 8 ms, release 6 ms, bounce 4 to 6 ms, contact state | M-10 |
| RF crossbar | 37 relay positions, path from each radio to each antenna, hazard check H1 to H4 | rf-board.md, D-103 |
| Box safety gate | RLY_EN = NOR(KILL, MCU_EN_N, FAULT); expanders in reset while RLY_EN = 0 | D-59 |
| TPS3823 + 74LVC1G74 | Watchdog time-out 0.9 to 2.5 s, power-up and brown-out set FAULT, LATCH_CLR edge | C-19 |
| Shack SAFE latch | PRE_N, RESET button edge, LATCHED, TX_EN = NOR(FAULT, LATCHED) | D-75, D-84 |
| Radio port | TX INH = SAFE latch AND permit; KEY; TX sense with optional opto failure | D-63, D-71, F14 |
| Radio | PTT, TX delay, RF tail after inhibit, band data A to D | F7, F9, M-12 |
| Current loops | 4 loops: data to box, PTT, SAFE, data to shack. UART 9600 bit timing, cable break, noise, bit errors | D-56, D-58 |
| RF detectors | RF on a column, A2 opens the SAFE loop | D-47, D-104 |
| Bias-T | EN, OK read-back, short fault | D-54 |
| ST7789 display | 240 x 320 frame buffer, shown in a window or saved as PNG | D-187 |
| USB CDC | Pseudo-terminal or TCP socket on the Mac, so a real Mac app can connect | D-68 |

Display: the firmware draws with `embedded-graphics`. On the Mac, `embedded-graphics-simulator` shows the same picture.

## 5. Phases

| Phase | Work | Done when |
|---|---|---|
| P0 | Workspace, toolchain (`riscv32imc-unknown-none-elf`, esp-hal, embassy), CI with `cargo test` and `clippy`. The ESP32-C3 target is built, not flashed. | `./check.sh` passes, including the target build |
| P1 | Link protocol spec (doc first, [docs/design/link-protocol.md](../docs/design/link-protocol.md)), then `link-proto` crate with property tests (round trip, corrupt frames, lost frames) | Spec reviewed; tests pass |
| P2 | `sim-core` and the shack board model (PCA9539, latch, ports, KILL, RESET, display). USB moves to P3, with the Mac protocol. | Model tests reproduce the shack checks of verify_system.py |
| P3a | `shack-core`: start-up, F1 init, 10 ms poll, WDI kick, permits, shack side of the handshake, F14 end rule, link loss | Shack runs in `sim-shack` against a scripted box stub |
| P3b | Mac protocol spec ([docs/design/host-protocol.md](../docs/design/host-protocol.md)), `host-proto`, USB CDC model | Spec reviewed; Mac commands drive the shack in the simulator |
| P3c | Display pages (`embedded-graphics`, M+ fonts): B flow, C cards, Safe stop; `page b\|c\|auto` | Pages render on the simulated ST7789 and match a direct render |
| P4 | Box board models: 4 expanders, relays, safety gate, fault latch, RF detectors, bias-T. Pin map in `box-core` | Model tests reproduce verify_logic.py. Done 2026-10-30: sections 2 to 9, the S1 to S7 intervals at minimum and maximum timing, the crossbar counts |
| P5 | `box-core`: F1, F5, F10, F11, F13, crossbar check (F6), box side of the handshake, link time-out | Box runs against a scripted shack stub. Done 2026-10-31: `sim/sim-box`, 22 scenarios; each rule broken once on purpose and caught |
| P6 | `sim-system`: both firmwares, both boards, the link. Fault injection. | All scenarios in section 6 pass |
| P7 | First flash. Target glue on ESP32-C3. Same scenarios as hardware-in-the-loop tests when boards exist. | Bench test plan in docs/test/test-spec.md |

Rule: no flashing before the simulator scenarios pass. Until P7 the target crates are only built, so the esp-hal glue keeps compiling.

P0 to P3 gives a working shack interface in the simulator. P4 to P6 adds the box.

## 6. Scenarios and checks

The simulator records every pin, register write and relay contact with a time stamp. A checker runs over the trace after each scenario. It fails the test on any rule break.

Rules the checker enforces:

- F1: no expander config write before its output write after a reset.
- F10: no register write that opens and closes relays together; 12 ms between open and close.
- F11: start-up order LATCH_CLR, MCU_EN_N = 0, wait for KILL = 0.
- F13: no K0 or route change while that radio has a permit.
- F14: no 'end' before TX sense inactive and at least 100 ms after the inhibit.
- WDI kicked from the main loop, every 0.25 s or faster.
- Hazards H1 to H4: never a TX path into A2, never two radios on one antenna, never RF on an open row.

Scenarios: normal start-up, route change, R1 PTT, R2 and R3 handshake, KILL during TX, RF on A2, cable cut, bit errors, link time-out, shack MCU hang, box MCU hang, brown-out, failed TX sense opto, expander NACK, the 256-state SAFE table.

## 7. Open points

- Link physical layer. The design uses four opto current loops with UART 9600 baud over Cat6 (D-56, D-58), not RS-485. The plan models the current loops. Confirm.
- Link protocol is not specified yet. P1 writes it.
- Mac protocol: decided, text lines (docs/design/host-protocol.md, P3b-01).
- Async (embassy) or a plain super-loop. Proposal: embassy for the I/O, with a synchronous state machine in each core crate, so tests need no executor.
- Box firmware (P5): how the box leaves its "link lost during TX" stop (F13: MCU_EN_N = 1). Decided (Prins, 2026-10-31): on a Hello, or when every radio that had a permit got its TxEnd. Then MCU_EN_N = 0 and the F11 start-up; the SAFE latch in the shack still needs RESET. The scripted box in `sim-shack` still stays stopped (P6 replaces it).
- Emulator of the real binary (Wokwi or Espressif QEMU) as a later extra. Only if the HAL-level model misses a class of bugs.
