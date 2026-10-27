# Shack Relay Matrix — architecture rev A

Block diagram artifact: https://claude.ai/code/artifact/e27126d0-6c2e-44ee-a48c-11e5d0845b2e
Generator script: gen.py. Card pages: antenna-port-card-rev-a.md, radio-port-card-rev-a.md, controller-card-rev-a.md.

## Decisions (2026-09-09)
- Topology: radio × antenna crossbar, 4 radio slots × 6 antenna lines. One SPST RF relay per crossing, sitting on the Radio Port card.
- Control: single I2C backplane, controller is the only master. Card address comes from hardwired SLOT_ID pins per slot (no jumpers).
- RF is not on the backplane. Radio Port cards drive six antenna bus lines; Antenna Port cards terminate one line each.
- Host link: USB-C, UART/CDC, plain ASCII command set.

## Cards
- Controller: ESP32-S3-WROOM-1U (Wi-Fi antenna on rear SMA), native USB CDC, I2C master via PCA9517 buffer, hardware safety chain (external WDT + supply supervisor + gate) → /RLY_EN, OLED + encoder + MODE/ACK front panel. See controller-card-rev-a.md.
- Power: 13.8 V in, fuse, 12 V relay rail, 5 V / 3V3 logic. Relay and logic returns joined at one point.
- Radio Port: SO-239 → PTT-driven SPDT changeover relay (keyed = TX path, unkeyed = RX path) → two rows of 6 SPST RF relays (firmware: max one closed per path). Opto PTT input → PTT[n] on backplane, RF sense detector, I2C expander @ SLOT_ID, relay drivers gated by /RLY_EN. Same antenna on both paths = plain single-antenna use.
- Radio Port RX variant (Airspy HF+): no PTT input; TX-mute relay shorts the RX port whenever any PTT[n] is active, wired from the PTT bus in hardware.
- Antenna Port: SO-239, gas-discharge arrestor, idle→GND relay. RX-only flag (LoG) enforced in firmware.
- Backplane: passive. +12V RLY, +5V/+3V3, SDA/SCL, /INT (wired-OR), PTT[1..4], /RLY_EN, SLOT_ID[2:0].

## Controller rules
1. One radio per antenna line, one antenna per radio.
2. Hot-switch lockout: no antenna-select relay moves while that radio's PTT is active. RX-mute relays exempt (PTT-bus driven).
3. Break before make with settle delay.
4. RX-only antennas may sit on a radio's RX path, never its TX path.
5. Watchdog miss, USB timeout or brown-out drops /RLY_EN → all select relays open, all antenna ports grounded.
6. Changeover relay is hardware-driven from the PTT bus; radio TX delay (FT-710 ext-amp keying delay) must exceed relay transfer time.

## Populated today (example state)
R1 FT-710 (100 W, OC PTT): TX path → A1 doublet, RX path → A3 vertical. R2 Airspy HF+ → A2 Loop-on-Ground (RX only). A3 vertical planned. R3/R4, A4–A6 spare.

## Expansion
Second transceiver → Radio Port card in slot 3 + routing table entry. Vertical → Antenna Port 3. Beyond 4×6: second chassis on the same host, or I2C mux to a second backplane. Remote relay box at mast base: swap I2C link for RS-485 on the same card footprint.

## Open items
- Decide whether the RX-path matrix relay opens during TX as well (isolation of changeover relay vs. 100 W coupled from the TX antenna).
- I2C expander parts: PCA9554 (antenna card), PCA9555 (radio card) — confirm.
- RF relay part and PCB stackup for 100 W HF bus lines; check stub capacitance of five open relays per line at 30 MHz.
- Define the ASCII command set.
