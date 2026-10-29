#!/bin/sh
# Local check, same steps as CI: format, lint, host tests, no_std build, target build.
set -eu
cd "$(dirname "$0")"

cargo fmt --all --check
cargo clippy --all-targets -- -D warnings
cargo test
cargo build --workspace --target riscv32imc-unknown-none-elf

for t in targets/*/; do
    (cd "$t" && cargo fmt --check && cargo clippy --release -- -D warnings && cargo build --release)
done
echo "check: all passed"
