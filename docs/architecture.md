# Architecture

Status: rev C, 2026-10-06. Replaces architecture v0.1 (archive/architecture-v0.1-2026-09-09.md), the rev A card documents (archive/block-diagram-rev-a-2026-09/) and the card cage design of rev B (archive/rev-b-backplane-2026-09/).
Every decision has an ID (D-xx) in design-log.md with its reason and the rejected options.

## 1. System overview

```
 Shack                                   Cat6 + 3 coax            Outdoor RVS box                       Antennas
 -----                                   -------------            ---------------                       --------
 Computer --USB--> Shack interface ==== 4 opto current loops ===> Controller board (stacked)
                   (SAFE latch,                                     |  safety gate, watchdog, I2C
                    TX permits)                                     v
 R1 FT-710  --coax-------------------------------------------->  RF board: 3 radios x 4 antennas  --> A1 G5RV
 R2         --coax-------------------------------------------->  (37 x TE RT1 relays)              --> A2 RX loop
 R3         --coax-------------------------------------------->                                   --> A3, A4 spare
 R1..R3 TUNER/LINEAR jacks <--> Shack interface radio ports       EXP (SMA + ribbon) --> unit 2 (optional, +4 antennas)
```

## 2. Main blocks

| Block | Function | Design document |
|---|---|---|
| RF board | Relay crossbar: per radio a K0 changeover, a TX row and an RX row (4 antennas + EXP). Per antenna a K1 ground/route relay, static bleed, RF detector, bias-T option. | [design/rf-board.md](design/rf-board.md) |
| Controller board | ESP32-C3 DevKit, safety gate, supervisor and watchdog, link to the shack, I2C to the RF board. | [design/controller-board.md](design/controller-board.md) |
| Case | Milled aluminium tray (6082-T6), 288 × 250 × 66 mm. SO-239 in the bottom wall. Case = RF ground. | [design/case.md](design/case.md) |
| Shack interface | Powers the 4 loops, holds the SAFE latch and the TX permits, radio ports for R1 to R3, USB bridge. | [design/shack-interface.md](design/shack-interface.md) |
| Firmware | Box and shack firmware on ESP32-C3. | [../firmware/](../firmware/) |

## 3. Key decisions

| Topic | Decision | ID |
|---|---|---|
| Construction | One flat RF board per unit in a milled case, controller board stacked above. No backplane. | D-01, D-02 |
| Size | 3 radios × 4 antennas per unit. Expansion to 8 antennas over SMA on the radio side. | D-03, D-04 |
| Relays | One type everywhere: TE RT1 RTD14012F. Open contacts see up to 173 V peak. | D-06 |
| RF line | 6-layer JLC06161H-7628A, coplanar 50 ohm with GND below, W 0.975 mm, gap 2.0 mm. Rows on L1, columns on L6, GND on L2, L4 and L5. | D-115, D-116 |
| Surge | Comet CS-400R at the box entry. GDT footprint on the board, not fitted. Static bleed 1 MΩ. | D-07, D-09, D-32 |
| Link | Cat6, four opto current loops powered from the shack: data to box, PTT, SAFE, data to shack. UART 9600 baud. | D-56, D-58, D-62 |
| R1 PTT | Hardware PTT loop drives R1 K0 directly. | D-63 |
| R2, R3 PTT | Handshake over the data link: request, state check, K0, 12 ms, read-back, permit. | D-63 |
| TX inhibit | Per radio: TX INH = SAFE latch AND permit, in hardware on the shack interface. | D-63 |
| Safety gate | RLY_EN = NOR(KILL, MCU_EN_N, FAULT). Supervisor and watchdog set a fault latch. | D-59 |
| Unit 2 | No own controller. Run from unit 1 over a ribbon (I2C, RLY_EN, TX_ANY). One safety chain. | D-05, D-53 |

## 4. Safety chain

The SAFE loop is one series current loop: shack supply, KILL switch, shack sense, box opto, box READY switch.
Any break stops the current. All radios are then inhibited and all relays released.
The shack latch holds the stop until RESET is pressed with the loop current back.

Diagrams: hardware/docs/diagrams (L1 SAFE loop, L2 box safety gate, L3 shack latch, T1 to T4 timing, F1, F2 firmware flow).

![L1 SAFE loop](../hardware/docs/diagrams/L1_safe_loop.svg)

*L1 SAFE loop. The other diagrams are in the design documents: controller-board.md (L1, L2, T1, T2, T4, F1) and shack-interface.md (L1, L3, T3a, T3b, F2).*
Verification: hardware/unit/verify (verify_logic.py, verify_system.py and their reports).

## 5. Open items at architecture level

- SR-01 is met in design: H1 by D-103 (no TX relays on a receive-only column), H2 by D-104 (RF on A2 opens the SAFE loop). To confirm on the bench: A2 detector against antenna coupling (A-20).
- FT-710 TX INH level (A-15) and inhibit response time (M-12).
- RT1 isolation and insertion loss (M-01).
- Creepage values from EN IEC 60664-1 and IEC 60664-4.
- Unit 2 build option and the ribbon passage through the case wall.
