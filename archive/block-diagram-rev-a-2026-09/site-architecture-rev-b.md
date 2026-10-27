# Site architecture — rev B (garden matrix + shack head)

Artifact: https://claude.ai/code/artifact/2e85d6cf-658a-4a54-aa9f-3e810f3cf07c
Generator: gen_site.py. Supersedes the single-chassis assumption in architecture-rev-a.md (card designs unchanged).
Station facts from the vault: wiki/topics/ham-shack-rfi-log.md (G5RV at 6 m on grounded 6 m aluminium pole, loop-on-ground RX, GP-6N VHF, RVS interface box in the garden, FT-710 + FTM-510D + Airspy HF+, choke programme rows 1–10).

## Decisions (2026-09-09)
- Relay matrix chassis lives in the stainless (RVS) antenna interface box at the mast base. Controller + front panel live in the basement in a "shack head".
- Link: one buried Cat6. Pair 1 RS-485 A/B (isolated both ends), pair 2 PTT current loop (FT-710 TX GND → opto on link card → PTT[1] on garden backplane, hardware), pair 3 KILL current loop through the panel KILL switch (open loop = /RLY_EN released), pair 4 spare. Whole cable through FT240-31 at both ends. No DC, no ground reference on the Cat6.
- Garden slot 0 = Link card: isolated RS-485 ↔ I2C bridge MCU, PTT opto, KILL loop into the gate, local WDT + supply supervisor + gate → /RLY_EN, link-heartbeat timeout (~1 s) → safe state.
- Power: 230 V is at the box → linear PSU in the box (toroid, bridge, linear 12 V relay rail + 5 V). No switch-mode converters anywhere in the box. Self-heating helps with condensation.
- Buried run allocation: coax 1 FT-710 ↔ Radio Port 1; coax 2 Airspy ↔ Radio Port 2 (RX variant); coax 3 FTM-510D ↔ GP-6N straight through (2× bulkhead SO-239 + choke, no relay); Cat6 #1 link; Cat6 #2 spare; power cable 230 V on own RCD circuit.
- Radio Port card PTT source: backplane line (from link card) instead of front jack. Radio Port 1 K0 = the sequenced TX/RX switch from the RFI log; Antenna Port 2 bias-T feeds the loop preamp.
- Controller card unchanged except backplane connector → link connector (RS-485 + loop drivers). Wi-Fi/USB noise now indoors, where the Airspy dummy-load comparison shows the shack side is 27–48 dB below the antenna path.

## Limits
- 3 coaxes = 3 radio lines. A 3rd HF transceiver needs a 4th coax (or sharing).
- Every conductor into the RVS box: choke + isolation/surge. Nothing switching at kHz inside.
- Routing over RS-485 is ms-latency; PTT and KILL are wires, so no safety function depends on the protocol.

## Open items
- Cat6 type (UTP vs shielded) and shield bonding (box only vs both ends) — tied to mast-earth vs house-PE bonding topology.
- Cat6 surge protection at the box: GDT per pair to box + TVS behind isolation.
- Condensation: PSU self-heat + drain/breather vs small thermostat heater. No fans.
- Sealed relays + conformal coating for the damp box.
- Link-card MCU: ESP32-S3 with radio off (one firmware tree) vs STM32G0/RP2040.
