# Radio Port card — rev A

Block diagram artifact: https://claude.ai/code/artifact/50071472-129c-4a49-8116-c369629d1050
Parent: architecture-rev-a.md. Sibling: antenna-port-card-rev-a.md. Generator: gen_radioport.py.

## Decisions (2026-09-09)
- One PCB for TX radio and RX-only SDR. RX-only build: TX row unpopulated, K0 drive jumper set to OR(PTT bus), PTT jack unused, EEPROM/DIP flag RX-only.
- K0 SPDT changeover (COM radio, NO TX path, NC RX path) is driven in hardware from the PTT opto, on the unswitched 12 V rail. It keeps following PTT even when /RLY_EN is released.
- TX row K1–K6: power relays (100 W). RX row K7–K12: signal relays. Jumper option: RX row driver enable = /PTT (RX antenna disconnected during TX).
- K0 drive select jumper: local PTT (TX radio) or diode-OR of PTT[1..4] (RX-only card → TX-mute without a second relay).
- Matrix relay coils fed through a high-side switch enabled by /RLY_EN; drivers are a 12-ch low-side driver from a PCA9555.
- TX sense detector on the radio side of K0 (RF without PTT, PTT without RF, RF during a switch → logged / fault).
- Option: TX inhibit output (OC) to radio TX INH / TX REQ, asserted while /RLY_EN released.

## RF chain
SO-239 → tap → K0 → TX path → K1–K6 → bus edge A1–A6; K0 NC → RX path → K7–K12 → same edge pins (TX relay ∥ RX relay per line).

## Control
PTT jack (3.5 mm, front) → opto → PTT[n] on backplane, K0 driver, expander input. PCA9555 addr = SLOT_ID. 24C02: radio name, TX-capable, max P, required TX delay. DIP: force RX-only, RX row opens on PTT. Card power: polyfuse, LC, 3V3 decoupling. Backplane: all pins used; PTT[1..4] drives own, reads all.

## Rules on this card
1. Max one relay closed per row; rows may point at different lines (split) or the same line.
2. Nothing moves while this slot's PTT is active or RF_DET is high.
3. Break before make with settle delay.
4. TX row never routed to an RX-only antenna line.
5. Coil budget: K0 + max 2 matrix relays per card.

## Key-down sequence
PTT → opto → K0 to TX path + PTT[n] on bus (≈5 ms) → radio TX delay (FT-710 ext-amp delay 20–30 ms) → RF. MCU not in the chain.

## Open items
- K0 / TX-row relay part: 100 W, hot-switch tolerance, transfer < 10 ms.
- RX-row-opens-on-PTT default on or off (protection vs relay wear and click during break-in).
- Confirm FT-710 LINEAR jack signals (TX GND out, TX REQ in) before committing the TX inhibit footprint.
- Detector threshold; coarse power readout via ladder or controller ADC.
