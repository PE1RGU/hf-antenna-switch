#!/bin/sh
# Local check, same steps as CI: format, lint, host tests, no_std build, target build.
set -eu
cd "$(dirname "$0")"

cargo fmt --all --check
cargo clippy --all-targets -- -D warnings
cargo test
# Core crates must build for the ESP32-C3 (no_std). The simulator crates need std.
for c in crates/*/; do
    cargo build -p "$(basename "$c")" --target riscv32imc-unknown-none-elf
done

for t in targets/*/; do
    (cd "$t" && cargo fmt --check && cargo clippy --release -- -D warnings && cargo build --release)
done
echo "check: all passed"
