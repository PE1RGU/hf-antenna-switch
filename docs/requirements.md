# Requirements

Status: draft 0.1, 2026-10-06. To review by Prins.
Source: design-log.md section 1 (R-01 to R-14), the decisions D-01 to D-102, and architecture v0.1.

Each requirement has an ID. The test specification refers to these IDs.
Status keys: decided / proposed / open.

## 1. What we build

An antenna switch for an HF amateur radio station.

- The relay unit is outdoors, close to the antennas, in an RVS box.
- A shack interface board indoors controls the unit over one Cat6 cable.
- Each radio has its own coax to the unit.
- A computer controls the system over USB.

## 2. What is important

In order of priority:

1. **Safety of the equipment.** No transmit power into a receiver or a receive-only antenna. No relay switching under RF. Any fault leads to a safe state.
2. **Safety rules in hardware.** Firmware may request a state. Hardware decides whether that state is allowed.
3. **RF performance.** Low loss and good match from 1.8 to 54 MHz at 100 W.
4. **Long life outdoors.** Wide derating margins, suitable materials, protection against static and lightning.
5. **Build by hand, parts easy to get.** For me and for others who want to build it.

## 3. Station

| Item | Role |
|---|---|
| Yaesu FT-710 | Radio R1, 100 W, TX INH input on the TUNER/LINEAR jack |
| Second and third radio | R2, R3 (WSPR or second station); may have no TX inhibit input |
| G5RV | A1, transmit and receive |
| RX loop with preamplifier | A2, receive only, fed by bias-T |
| Spare | A3, A4 |

## 4. Functional requirements

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-01 | The unit connects each of 3 radios to any of 4 antennas. | R-05, D-03 | decided |
| FR-02 | Each radio has a transmit antenna and a receive antenna that are selected separately. | Architecture v0.1, rev C (K0, TX row, RX row) | decided |
| FR-03 | One antenna serves one radio at a time. No splitters. | Architecture v0.1 | decided |
| FR-04 | A second unit extends the system to 3 radios × 8 antennas, controlled by the first unit. | D-04, D-05, D-53 | decided |
| FR-05 | An antenna that is not in use is disconnected from the matrix and connected to ground through a static bleed. | D-32, rev C (K1) | decided |
| FR-06 | Each antenna port can feed an active antenna through a switched, current-limited bias-T with read-back. | D-28, D-54 | decided |
| FR-07 | Each antenna port has an RF detector. | Rev C | decided |
| FR-08 | A computer controls the system over USB through the shack interface. A Raspberry Pi can take this role later. | D-63, D-69 | decided |
| FR-09 | The shack interface reads the FT-710 band data (BAND A to D). | D-86 | decided |
| FR-10 | The FM radio (FTM-510D to GP-6N) passes the box outside the matrix. | Rev C | decided |
| FR-11 | Presets of antenna selections are stored and recalled. | Architecture v0.1 | open (firmware) |

## 5. Safety requirements

| ID | Requirement | Source | Status |
|---|---|---|---|
| SR-01 | A receive-only antenna never receives transmit power. Hardware prevents it, not only firmware. | Architecture v0.1 principle, A-10, D-103, D-104 | met in design: H1 by D-103, H2 by D-104 (see note) |
| SR-02 | A radio cannot transmit before its K0 changeover relay is set and read back. | D-63 | decided |
| SR-03 | At the end of a transmission, TX INH is set first, then K0 is released. | D-63 | decided |
| SR-04 | A cable break, power loss, brown-out, watchdog time-out or KILL switch inhibits TX on all radios and releases all relays. | D-59, D-62 | decided |
| SR-05 | After a SAFE stop, the system restarts only after the operator presses RESET with the loop current back. | D-62, D-75 | decided |
| SR-06 | With no control power, all relays are in a defined rest state that is safe. | Architecture v0.1 principle | decided |
| SR-07 | A spark arrestor (Comet CS-400R) protects each coax at the box entry. | D-09 | decided |
| SR-08 | Radio port lines on the shack interface withstand ESD to EN 61000-4-2 level 3 (6 kV contact, 8 kV air). | R-12 | proposed |

Note on SR-01: architecture v0.1 had no TX path to the loop at all. In rev C every TX row has a relay position at every antenna column. Two hazards: H1, a TX relay closes on a receive-only column; H2, a K0 does not transfer while its RX row is on a receive-only column, so TX goes into the RX row. H1: the TX relays on a receive-only column are not fitted (D-103; unit 1: A2). H2: RF on A2 opens the SAFE loop in hardware (D-104); RF can reach A2 for about 7 ms before the relays open, so the loop is protected but a preamp is at risk. Detector false trips from antenna coupling: A-20.

## 6. Performance and environment

| ID | Requirement | Source | Status |
|---|---|---|---|
| PR-01 | Transmit power 100 W HF, SWR up to 3:1 (173 V peak, 2.45 A rms on the line). | R-01 | decided |
| PR-02 | Frequency range 1.8 to 54 MHz. | R-02 | decided |
| PR-03 | 50 ohm lines on the RF board (W 0.975 mm, gap 2.0 mm, JLC06161H-7628A 6-layer). | D-115, D-116 | decided |
| PR-04 | Insertion loss, SWR and isolation per path: limits to set. | M-01 | open |
| PR-05 | Ambient up to 45 °C in the RVS box, north side, no direct sun. | R-03, R-04 | decided |
| PR-06 | Creepage per EN IEC 60664-1, pollution degree 3, material group IIIb. | Rev C spacing check | decided, values to confirm with the standard |

## 7. Design rules

| ID | Rule | Source |
|---|---|---|
| DR-01 | Derating (operating / rated): power 0.6, temperature 0.8, voltage 0.7, current 0.7, nominal value 0.7. | Prins design rules, R-15 |
| DR-02 | Halogen-free parts and materials (IEC 61249-2-21) unless impossible or impractical; each exception recorded with its reason. | Prins design rules, D-107, D-135 |
| DR-03 | Jellybean parts, two drop-in sources, from distributors with full datasheets. | R-10 |
| DR-04 | Hand assembly: no 0402, thermal relief by default. | R-07 |
| DR-05 | PCBs by JLCPCB. | R-08 |
| DR-06 | Symbols to IEC 60617. Schematics connected with wires, labels only where a net leaves the sheet. | R-09 |
| DR-07 | All switching logic is verified with truth tables (verify_logic.py, verify_system.py). | Prins design rules |
| DR-08 | Every component has its datasheet, errata and PCNs in Datasheets/. | Prins design rules |
