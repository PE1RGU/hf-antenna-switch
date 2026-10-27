# Controller card — rev A

Block diagram artifact: https://claude.ai/code/artifact/d58b35f7-6032-4fd3-8173-894ce5a1e149
Parent: architecture-rev-a.md. Siblings: radio-port-card-rev-a.md, antenna-port-card-rev-a.md. Generator: gen_controller.py.

## Decisions (2026-09-09)
- MCU: ESP32-S3-WROOM-1U (U.FL variant) soldered on the card. Wi-Fi antenna via rear SMA bulkhead, outside the enclosure. Native USB CDC to host, no bridge chip.
- Front panel: 128×64 OLED (I2C#2), encoder with push, MODE + ACK buttons, fault LED, on a ribbon.
- Two I2C controllers: #1 backplane master through a PCA9517 buffer (TCA9548 mux footprint for a 2nd backplane), #2 front panel.
- Card power: +5V from backplane → local 1 A 3V3 LDO. Host USB 5 V not used.
- Safety chain in hardware: external watchdog (TPS3823 class, 1.6 s, GPIO kick) + supply supervisor (+3V3, +12V RLY) + gate: /RLY_EN = WDT_OK ∧ PWR_OK ∧ MCU_EN ∧ ¬FAULT_LATCH. Latch set on power-on and on any input dropping; MCU clears it only after ACK and only if inputs healthy. Open-drain onto backplane.
- PTT[1..4] and /INT read through Schmitt input buffers; controller never drives PTT lines.
- Debug: UART0 + BOOT/RESET header on the card, not on the panel.

## Firmware scope
Discovery (scan slots, read card EEPROMs), routing table with interlocks (one radio per line, RX-only lines only on RX paths, break-before-make, settle, no move while PTT/RF_DET active), ASCII protocol over USB CDC and TCP/WebSocket (e.g. SET R1 TX A1 RX A2 / STATE / FAULT ACK), web UI with matrix view (mDNS relay-matrix.local), fault log in flash (NTP time when Wi-Fi up), named presets in NVS. Host-side CAT band data can drive per-band presets.

## Boot / fault
Power-up: latch set → /RLY_EN released → all antenna ports grounded. MCU boots, scans, kicks WDT, raises MCU_EN, clears latch → routes applied RX rows first. Fault: latch sets, /RLY_EN released immediately, K0 relays keep following PTT, display shows cause, ACK lets MCU clear.

## Open items
- Wi-Fi noise into HF receive chain: verify with Airspy before fixing enclosure layout; Wi-Fi-off mode as fallback.
- Who drives TX_ANY on a spare line (controller vs Power module).
- Physical kill switch in series with /RLY_EN on the panel, or trust the latch.
- I2C bus capacitance at 400 kHz with ~10 expanders + 10 EEPROMs; size backplane pull-ups.
