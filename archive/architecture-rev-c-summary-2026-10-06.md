> ARCHIVED 2026-10-06. This was the rev C summary in the claude.ai Project (claude/architecture-rev-c.md). Its content is now in docs/architecture.md and docs/design/ (rf-board.md, controller-board.md, case.md). Not maintained.

# Architecture rev C: flat unit in an aluminium case (2026-09-27)

Replaces the card cage and DIN 41612 backplane of rev A/B. Archived: archive/architecture-rev-a.md, archive/decisions-2026-09-26-backplane.md, archive/order-jlcpcb-backplane.md; local files in archive/rev-b-backplane-2026-09/. The circuit functions of the Radio Port, Antenna Port and Controller cards stay the same (card docs rev A), except where this doc says otherwise.

Design log with every decision, reason, assumption, calculation, standard and measurement: claude/design-log.md (source for the design document).

## Decided (Prins, 2026-09-27)
- One flat RF board per unit, in a custom milled aluminium case. The case mounts flat on the RVS box back plate.
- Controller board stacked above the RF board on standoffs and a board-to-board header. MCU: ESP32-C3-DevKit-RUST-2 plugged onto it, fed on its 3V3 pin from a linear LDO, on-board buck held off (ENABLE low), Wi-Fi and BLE off (D-55).
- Scope now: unit 1. Unit 2 (EXP ribbon, D-53) is postponed until it is needed.
- Unit size: 3 radios × 4 antennas. Reason: only 3 HF coax cables run to the shack; more radios can be switched in the shack.
- Unit 1 antennas: A1 G5RV, A2 RX loop (RX only), A3 and A4 spare.
- Expansion: SMA ports carry the radio side to a second unit. With unit 2 the system is 3 radios × 8 antennas. 6 × 8 is not planned (it needs links in both directions, 30 more relays and extra interlock logic). Double-shielded jumpers (RG142 or RG400).
- Unit 2 has no controller. It is run from the unit 1 controller over the EXP ribbon (see below, D-53). One controller, one watchdog, one safety chain.
- One relay type for all positions: TE RT1 RTD14012F (K0, TX rows, RX rows, EXP, K1). Reasons: one part, footprint, PCN and halogen check; open contacts see up to 173 V peak; RX relay sits on the TX line when TX and RX share an antenna.
- SO-239: Amphenol RF 83-798 (SO-239/A), PTFE insulator per MIL-P-19468, brass contact silver-plated, zinc die-cast body nickel-plated. Drawing Rev. AG in Datasheets/. The 83-1R was rejected: PBT insulator (soldering heat, halogen status unknown).
- Spark arrestors at the RVS box entry: Comet CS-400R (CS-400P out of stock). Manual 4th ed. Apr 2023, filed in Datasheets/. M-J/M-J (SO-239 both sides), DC to 500 MHz, 0.1 dB, VSWR ≤ 1.1, 500 W PEP; DC fire 400 V ±15 % (min 340 V), impulse fire ≤ 950 V at 1 kV/µs, insulation ≥ 10 GΩ at 100 V, DC holdover ≤ 150 ms at 150 V; 10 kA 8/20 µs once, 500 A 10/1000 µs 200 times. Replaceable Sankosha arrestor Y08UZ-400A (list price 770 yen). Not waterproof: inside the RVS box only.
  - 173 V RF peak against 340 V minimum fire voltage: ratio 0.51.
  - The 12 V bias-T for the RX loop passes through it and cannot hold an arc (holdover rated at 150 V).
- GDT on the board: footprint only, not fitted (DNP), one per antenna port on the antenna side of K1 (replaces the rev A 90 V GDT, which was below the 173 V RF peak). If ever fitted, it fires above the arrestor (600 V class, part to select), so the CS-400R stays the first path and surge current does not run through the board and case.
- Static bleed stays and is needed: the CS-400R insulates (≥ 10 GΩ) below its fire voltage, so it does not drain static. The board bleed (1 MΩ, high-voltage type, on the K1 NC side) drains the parked antenna. No RF choke (design log D-32).
- Stackup: JLC0216A, 2-layer 1.6 mm, 1 oz outer (Prins, JLC calculator 2026-09-27).
- RF gap 2.0 mm, no conformal coating (Prins, option 1, 2026-09-27). RF line W 2.7 mm. See "RF line" and "Spacing check".
- Column pitch 38 mm, wider case accepted (Prins, 2026-09-27).
- The PCB is designed together with its aluminium case.

## RF line
- JLC0216A: L1 copper 0.030 mm, core 1.43 mm (1.5 mm 1/1 oz with copper), L2 copper 0.030 mm.
- JLC calculator, gap 2.0 mm (Coplanar Single Ended, without solder mask, 50 ohm): L1 ref L2 2.6838 mm; L2 ref L1 2.6838 mm. Own conformal-mapping check (Er fitted 4.41) gave 2.70 mm.
- Design value: **W 2.7 mm, gap 2.0 mm** on L1 and L2 (about 49.8 ohm).
- Earlier result at gap 1.25 mm (superseded): 2.5128 mm without mask, 2.4559 mm with mask.
- Via fence: via centre 3.9 mm from the trace centre (1.35 + 2.0 + 0.5 + 0.05); RF band about 9 mm per line.
- Current: 2.45 A rms in 2.7 mm, 1 oz outer layer: low temperature rise (IPC-2152); record the IPC-2152 check in the layout notes.
- Order checklist for this board: stackup JLC0216A, impedance control yes, remark "50 ohm coplanar on L1 and L2: W 2.7 mm, gap 2.0 mm".

## Spacing check (2026-09-27)
- Working voltage: 173 V peak at SWR 3:1, about 122 V rms; creepage table row 125 V rms.
- Material: JLC gives no CTI for standard FR-4 (its own blog: standard FR-4 about CTI 175, group IIIa); per the skill rule material group IIIb is assumed.
- EN IEC 60664-1 creepage at 125 V rms, material group III (values from memory, to confirm with a copy of the standard): PD2 about 1.2 mm; PD3 about 1.9 mm. The outdoor box is taken as PD3.
- IEC 60664-4 (above 30 kHz, range to 10 MHz): values not checked; no copy available. The 2.0 mm gap adds a small margin above the PD3 value for this.
- Clearance in air is not the limit at 173 V peak; creepage sets the gap.
- The same gap applies to other RF copper at transmit voltage: pads of the RF relay pins to GND pour, SO-239 pads, EXP SMA launch.
- Open: buy EN IEC 60664-1 and IEC 60664-4 (NEN), confirm the table values, file them as STD in Datasheets/.

## Unit contents
- 3 radio ports: K0 changeover, TX row, RX row. Each row: 4 antenna positions + 1 EXP position.
- 4 antenna ports: K1 ground/route relay (COM antenna, NO column, NC ground via bleed), static bleed (1 MΩ HV, no choke), GDT footprint (DNP), RF detector, bias-T option.
- EXP: 5th position in each TX row and RX row; both join on one SMA per radio. The EXP relay is the series disconnect, so no open stub remains when the antenna is local. TX and RX of one radio cannot be split across units.
- Unit 2: same RF board; J14 takes the EXP ribbon from the unit 1 controller board (D-53); its 3 SMA inputs replace the radio SO-239s. RF-side build option details to decide.
- Outside the matrix: FTM-510D to GP-6N straight through.

## EXP link (unit 1 to unit 2), D-53
- 2 x 12 IDC ribbon, single-ended, 0.5 m max inside the RVS box. Unit 1 controller board: header EXP with the J14 pin-out, from the second I2C channel (D-49), the same R1..R3_K0_DRV, RLY_EN and TX_ANY. Unit 2: the ribbon plugs into J14 of its RF board. No adapter board, no PCA9615.
- Pins 2 and 4 (+5V) are not connected at the controller end, so the two unit supplies are not in parallel. Every signal conductor lies next to a GND conductor (odd pins signals, even pins GND).
- About 100 ohm series resistor per signal at the controller end, low-capacitance TVS array at each case wall, I2C at 100 kHz. Unit 2 bus about 130 pF (C-16).
- K0 in unit 2 follows each radio's own PTT (same drives as unit 1). TX_ANY is read back on U903 IO1_5.
- Fallback if the M-line tests show RF pick-up: PCA9615 at both ends; the RF board does not change.
- Open: case wall passage (slot with clamp or panel-mount header).
- Bus pull-ups on the RF board: 2.2k on SCL and SDA, 10k on EXP_INT, to +3V3 (D-52, C-16). The controller board adds none.
- Unit 2 has its own power entry (XT60 / XT30).
- The Cat6 link to the shack stays on unit 1 only ("RJ45 LINK"), on the controller board (D-51). Four opto current loops powered from the shack (D-56): pair 1 data shack to box, pair 2 PTT, pair 3 SAFE (was KILL, D-62), pair 4 data box to shack; 9600 baud UART (D-58). PTT loop drives R1 K0 only; R2 and R3 transmit by handshake (D-63), so no Cat6 #2 is needed. RF board to controller: J14 2 x 12 header, 3.3 V logic. Odd pins: 1 SCL, 3 SDA, 5 EXP_INT, 7 RLY_EN, 9 TX_ANY, 11 to 15 R1..R3_K0_DRV, 17 to 23 spare; even pins 2, 4 +5V, 6 to 24 GND (D-52).

## Controller board (unit 1, first increment 2026-09-28)
- KiCad project: hardware/unit/controller-board/controller-board.kicad_pro. Generator gen_controller_sch.py (run from that folder). PDF: controller-board.pdf.
- Sheets: root (RJ45 LINK J1, J2 to RF board J14, CHASSIS lug H1; wires only, no labels), Link and PTT (four opto loops, PTT to K0 drives, D-56 to D-58), MCU and safety gate (DevKit on sockets J3/J4, LP2985-33, D-55; safety gate D-59).
- c5-ready (2026-10-05): READY switch U6 in the SAFE loop return, READY gate U15; R51 fitted, R52 and R53 not fitted (R2, R3 K0 from U903 after the handshake, D-63). Diagrams: hardware/docs/diagrams (L1, L2, T1 to T4, F1, F2).
- Safety gate (D-59): RLY_EN = NOR(KILL, MCU_EN_N, FAULT). TPS3823A-33 supervisor and watchdog (WDI on GPIO1, kick every 0.25 s or less, C-19) sets a 74LVC1G74 fault latch at power-up, brown-out and watchdog time-out. The firmware clears the latch with a LATCH_CLR edge (GPIO3) only when RESET_N is high. MCU_EN_N (GPIO4) is active low with a pull-up. KILL is not latched. 74LVC1G27 drives RLY_EN. Firmware rules: kick WDI only from the main loop (not from a timer interrupt); LATCH_CLR only once after the start-up self-test, and after a fault only when its cause is checked.

## Safety line and TX permit (D-62, D-63, 2026-09-29)
- SAFE loop (pair 3): one series current loop from the shack supply through the shack KILL switch, the shack sense opto, the box opto U3 (to the KILL input of U14) and the box READY switch (U6 TLP176AM photorelay, LED from U15 = NOR(MCU_EN_N, FAULT), D-101). READY excludes KILL, else the loop cannot start.
- Any fault stops the loop current: TX inhibited on all radios, all relays off. The shack hardware latch holds the stop until RESET is pressed with the loop current back.
- Start-up order: LATCH_CLR, MCU_EN_N low, SAFE current flows, KILL reads 0, then switching.
- Per radio: TX INH = SAFE latch AND permit, in hardware at the shack interface. R1 (FT-710) K0 from the PTT loop (R51 fitted, R52 and R53 DNP). R2 and R3 K0 from U903 IO1_3 and IO1_4 after a handshake over the data link (request, state check H1 to H4, K0, 12 ms, read-back, permit; at the end TX INH first, TX GND inactive, then K0 off).
- Shack interface: own MCU, USB to the Mac, bridge to the box protocol. To define.

## Relay placement study (2026-09-27, RT1 everywhere, 9 mm RF band, 38 mm columns)
Drawing: hardware/unit/relay-placement-study.svg (generator gen_relay_placement.py). Project copy: claude/relay-placement-study.svg. RF bands (9 mm keep-out incl. gap and fence) are drawn as shaded strips.
- Board 268 × 230 mm. Case outside about 288 × 250 × 66 mm (D-98).
- 37 RT1: 3 K0, 15 TX incl. EXP, 15 RX incl. EXP, 4 K1. 37 coils; 400 mW each.
- Crossbar: rows (radio TX and RX lines) horizontal on top copper; columns (antenna lines) and radio feeds vertical on bottom copper. The THT relay pins make the layer change.
- Column pitch 38 mm = antenna SO-239 pitch (board x 139, 177, 215, 253). Column line 6 mm from the relay body, so the 9 mm band clears the relays. Radio block 48 mm (TX band 24, RX band 24).
- Left: EXP relays (SMA on the left wall at each radio block) and K0.
- Radio SO-239 at x 12, 42, 72 (30 mm pitch). R3 feed runs straight up at x 72; R1 and R2 feeds at x 81 and 90, with their jogs on top copper near the bottom edge. No parallel run between feeds.
- Top 32 mm: logic zone, power entry, RJ45 LINK and the EXP ribbon passage on the top wall, controller board above.
- Supports S1 to S6 and the SO-239 GND bosses are drawn with their 8 mm keep-out (D-102, M-32).
- Antenna port zone 34 mm above the strap zone: K1 left of each column, bleed / GDT DNP / detector right of it (2.0 mm from the column line).
- Crossing coupling: about 0.16 pF per crossing, about 60 dB at 30 MHz.

## Case (sketch, 2026-09-27)
Sketch: hardware/unit/unit-case-sketch.svg. Project copy: claude/unit-case-sketch.svg.
- Outer 288 W × 250 H × 66 D mm (D-98, was 60). Milled tray 6082-T6: walls 6 mm, floor 5 mm; lid 3 mm on M3 screws. Board 10 mm from the inner walls, except the bottom edge (see SO-239; the sketch still shows 10 mm there).
- Bottom wall: R1–R3 at 30 mm pitch (left), A1–A4 at 38 mm pitch (right, under the columns). Left wall: 3 SMA EXP, one per radio block. Top wall: XT60 +12V RLY, XT60 +12V AUX, XT30 +5V, RJ45 LINK, EXP ribbon passage (D-53).
- Mounting: 4 × M5 blind tapped from the back of the floor (top pair at case x 30 and 258, clear of S1 and S3).
- RF board supports (D-102): six M3 standoffs, 13 mm, non-plated holes, not on GND: S1 (5, 5), S2 (149, 5), S3 (263, 5), S4 (46, 116.5), S5 (99, 116.5), S6 (263, 116.5), board mm from the top left; plus the seven M3 screws to the SO-239 GND bosses at y 225 (the RF bond). Keep-out 8 mm diameter. A true 3 × 3 grid does not fit: no free spot in the relay field near the centre. First resonance about 135 Hz against 38 Hz with 4 corners (C-29, compare only).
- SO-239 (83-798) in the 6 mm bottom wall: flange outside, 4 × M3 tapped into the wall on an 18.24 mm square (flange holes 3.18 mm); wall hole 16.7 mm for the 15.75 mm rear body. Coax shield = case = RF GND. No wall pocket needed.
  - From the drawing (estimated from scale): rear body about 4 mm behind the flange, solder cup tip about 9.6 mm behind the flange, so the cup reaches about 3.6 mm into the case.
  - Board bottom edge 5 mm from the inner bottom wall (not 10 mm), so the cup-to-pad gap stays about 1.5 mm and the strap stays under 6 mm. Solder-cup opening towards the board.
- SO-239 axis 16 mm from the inner floor; RF board on 13 mm standoffs; copper strap 3 × 0.3 mm from cup to pad; milled GND boss with M3 next to each SO-239.
- Height stack: standoff 13, PCB 1.6, RT1 15.7, gap 4, controller board 1.6, DevKit on sockets (11.05 + 1.6 + USB-C 3.3); DevKit top at 51.85 mm, lid inside at 58 mm, about 6.2 mm free (C-27, D-98). DevKit USB end toward open space, 40 mm corridor (R-14).
- 3D: no 83-798 STEP available; the 83-1R STEP (hardware/unit/unit.3dshapes/AmphenolRF_83-1R.step, same flange and thread) is the placeholder.

## Schematic (2026-09-27, first increment)
- KiCad project: hardware/unit/rf-board/rf-board.kicad_pro. Generator gen_rfboard_sch.py (run from that folder). PDF: rf-board.pdf.
- Sheets: root overview; power entry (XT60 ×2, XT30, CHASSIS bond H1/JP1/C1); radio_port ×3 (K0, 5 TX, 5 RX, SO-239, EXP SMA); antenna_port ×4 (K1, bleed, choke, GDT DNP, 0R link / DC block, bias-T DNP, detector).
- Drawn since (generator v9k): coil drivers and clamps, power (+12V_SW switch, 3V3, input protection), RF detect, IO expanders with bus pull-ups, J14, bias-T supply (D-54: U1001 PCA9539 at 0x77, four switched and current-limited feeds with read-back). Not drawn yet: RF-side unit 2 build option. K0 is driven from J14 (Rn_K0_DRV); the unit 2 link is the EXP ribbon on J14 (D-53).
- Bias-T feed on the matrix side of K1 (design log D-28, decided).
- All connectors on the root sheet (D-33).

## Rules the PCB follows for the case
- Cable forces into the case, not the PCB. Outline at a fixed offset from the inner walls with a keep-out band. Mounting grid shared with the case drawing. The case bonds to the RVS earth bar at one point only.

## RT1 isolation test (postponed by Prins, 2026-09-27)
- Coupon: 2-layer 1.6 mm, one RT1, CPWG lines from COM and NO to two edge SMA, a through line of the same length as reference, GND via fence.
- NanoVNA-H4, SOLT calibration at the SMA planes, 1 to 54 MHz. Measure S21 coil off, S21 and S11 coil on, NC isolation coil on; values at 1.8, 3.5, 7, 14, 21, 28 and 50 MHz.

## Taken over from the backplane work (archived docs)
- RT1 RTD14012F (datasheet RT1pb rev 4). +12V RLY regulated 12 V ±5 %.
- I/O expanders: 4 x PCA9539 per unit at 0x74 to 0x77 (D-49, D-54: 0x77 for the bias-T feeds); unit 2 on its own I2C channel from the controller; no EEPROM; 3.3 V logic from the local LDO.
- XT power entry: XT60PW-M +12V RLY, XT60PW-M +12V AUX, XT30PW-M +5V; STEP models in hardware/unit/unit.3dshapes/.
- XT polarity check open: vendor models put the angled end on pad 2 (KiCad footprint says pad 2 = +; convention says angled = −). Check a real part before release.
- Stackup method: JLC impedance calculator (Coplanar Single Ended), order checklist per board, spacing per IPC-2221 and EN IEC 60664-1 / IEC 60664-4.
- Markings: HV warning triangle, date code DC YYWW, no UL mark, no JLC order number. Mounting holes not grounded except the defined bond.

## Open (before layout)
- EN IEC 60664-1 and IEC 60664-4 copies to confirm the table values.
- XT polarity on a real part (Prins).
- GDT part for the DNP footprint (600 V class, THT, hand-solderable).
- Unit 2 build option details (SMA inputs instead of radio SO-239s; K0 on unit 2).
- EXP ribbon passage through the case wall (D-53).
- Case isolation from the RVS back plate or direct mounting.
- SMA and RG142 rating at 173 V peak, 2.45 A rms, SWR 3, 45 °C.
- CNC quotes for the tray.
