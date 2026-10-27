# Antenna Port card — rev A

Block diagram artifact: https://claude.ai/code/artifact/e87b98e8-e594-4f4e-8697-b0068ad870c9
Parent: architecture-rev-a.md (Shack Relay Matrix). Generator: gen_antport.py.

## Decisions (2026-09-09)
- RF sensing: presence detector (Schottky + comparator → RF_DET, /INT) populated; directional coupler footprint + fwd/ref analog header left unpopulated for later per-antenna SWR.
- Antenna identity lives on the card: 24C02 EEPROM (name, RX-only flag, bias-T flag, card rev) + 2-way DIP hardware override. Controller reads at boot; DIP wins on mismatch and the mismatch is logged.
- One PCB for all antenna cards; RX-only and bias-T are population options + flags.

## RF chain (matrix → antenna)
Matrix line connector → [coupler footprint] → RF tap → [bias-T DC block, else 0 Ω] → K1 SPDT (NO = matrix, COM = antenna, NC = GND via 1 MΩ ∥ RF choke static bleed) → [bias-T inject L + 12 V] → 90 V GDT to chassis → SO-239 (shell to chassis).
- K1 de-energised = antenna grounded. Fail-safe by construction.
- GDT sits on the antenna side of K1 so it protects the relay as well.

## Control
- PCA9554-class I2C expander, addr = SLOT_ID. In: RF_DET, DIP. Out: ROUTE, bias-T enable, LED.
- Relay driver: logic MOSFET + flyback; gate = ROUTE AND /RLY_EN in hardware.
- Card power: polyfuse on +12V RLY, LC filter, 3V3 decoupling.
- Backplane pins used: +12V RLY, +3V3, SDA/SCL, /INT, /RLY_EN, SLOT_ID[2:0]. PTT[1..4] present but n/c (reserved for a variant that opens K1 on non-owning PTT).

## States
Power off / idle / /RLY_EN released → grounded. Routed and /RLY_EN asserted → on matrix line. RF detected while idle or on an RX-only card → controller drops /RLY_EN, all ports grounded, fault logged.

## Open items
- Relay part: 100 W at 50 Ω, isolation at 30 MHz, hot-switch survival in the fault case.
- Detector threshold (~0 to +20 dBm at the tap).
- Coupler style for the footprint: Tandem Match (two ferrite transformers) vs stripline.
- Mechanical: SO-239 on the card front edge vs rear bulkhead with coax jumper.
