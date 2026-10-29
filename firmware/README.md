# Firmware

Rust. Plan and phases: [PLAN.md](PLAN.md). Status: P3c done (display pages). Next: P4, the box board models.

Two targets, both on the ESP32-C3-DevKit-RUST:

- Box controller (outdoor unit): relay control, safety gate, watchdog, data link to the shack.
- Shack interface: USB bridge to the computer, SAFE latch read-back, TX permits, handshake.

Firmware rules already defined: see design-log.md (F-rules) and hardware/docs/diagrams (F1, F2).

## Layout

- `crates/`: no_std logic, one host workspace (`Cargo.toml` here). Tested on the Mac with `cargo test`.
- `sim/sim-core`: virtual time, trace, I2C and UART plumbing, embedded-hal adapters.
- `sim/sim-models`: part models (PCA9539, 74LVC1G74, TPS3823, ST7789) and board models (shack interface).
- `crates/host-proto`: the Mac or Pi text protocol (docs/design/host-protocol.md).
- `crates/shack-ui`: display pages B (flow), C (cards) and Safe stop, 320 x 240, anti-aliased M+ fonts. Mock-ups: docs/design/display-mockups.
- `sim/sim-shack`: shack logic on the board model, against a scripted box. `cargo run -p sim-shack` prints a demo timeline.

## Talk to the simulated shack interface

```bash
cargo run -p sim-shack -- --pty
```

It prints a pty path, for example `/dev/ttys003`. Open it with a serial terminal or a script, then type host commands (`hello`, `status`, `route R2 A1 A1`, `tx R2 on`, ...). The terminal where `sim-shack` runs controls the outside world: `reset`, `kill on`, `cable off`, `radio R2 on`, `box mute on`, `shot screen.png` (saves the display), `quit`. The terminal does not echo what you type.
- `targets/<name>/`: ESP32-C3 binaries, each its own workspace with its own `.cargo/config.toml`. Glue only.

## Tools

- Rust stable with `riscv32imc-unknown-none-elf` (set by `rust-toolchain.toml`).
- espflash 4: `cargo install espflash --locked`.

## Commands

All checks (same as CI):

```bash
./check.sh
```

Development runs on the Mac against the simulator. The ESP32-C3 targets are only built until P7.

Later (P7), flash the shack target and open the log:

```bash
cd targets/shack-esp32c3 && cargo run --release
```

The present target is a bring-up stub: version log, I2C scan (bare DevKit-RUST-1: 0x68 IMU, 0x70 SHTC3), LED blink on GPIO7.
