# Firmware

Rust. Plan and phases: [PLAN.md](PLAN.md). Status: P1 done (link protocol, crate link-proto).

Two targets, both on the ESP32-C3-DevKit-RUST:

- Box controller (outdoor unit): relay control, safety gate, watchdog, data link to the shack.
- Shack interface: USB bridge to the computer, SAFE latch read-back, TX permits, handshake.

Firmware rules already defined: see design-log.md (F-rules) and hardware/docs/diagrams (F1, F2).

## Layout

- `crates/`: no_std logic, one host workspace (`Cargo.toml` here). Tested on the Mac with `cargo test`.
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
