# Pre-order review: RF board, controller board, shack interface (2026-10-31)

Scope: all three boards before the PCB, parts and CNC case orders. Read-only review: no schematic, layout or BOM was changed. Base: commit dd1f485 (main), netlists rf14.xml, ctl14.xml, si16.xml, KiCad 10.0.5.

## Status (2026-11-01, after PRs #12 to #30)

Done: B-1, B-2 (D-189, M-107); S-1 (D-191, M-109: FAULT to IO6, box fault 11, host `clearfault`); S-2 (D-192, M-110: SDA jumpers bridged for RUST-1 by copper); S-3 (D-193, M-111: 0.64 in² drain copper per bias-T FET on F.Cu + B.Cu, held-short test on the prototype); S-8 (D-194, M-112: shack board 159.6 mm wide, 0.2 mm off each side); S-9 (M-113: controller production zip c-s7, ORDER sheet hole labels fixed); S-12 (M-114: the display adds no pull on IO2/IO9, no board change, boot check on the prototype); S-4 (M-115: MPN BSS138BK,215 on all 45 BSS138BK, RF and shack); S-5 (M-116: RF J14 = Samtec TSW-112-07-L-D, post 5.84 mm, engagement 4.89 mm); S-6 (M-117: LM2901DR, JST B2B/B4B-XH-A(LF)(SN), shack 1 nF GRM1885C1H102JA01D; PC817X, RF 100n and C1 105 C were already done); S-7 (D-133: plain PCA9539 only, never R; already in the part descriptions, to the order BOM with B-3); S-10 (D-195, M-118: IRFL9014TRPBF-BE3, MAX823SEUK+T first source, TLP176AM in stock; SO-239: 83-1R first, 83-798 second, D-196 / M-119); Decide D-148 (closed by D-195: MAX823SEUK+T first source, datasheet filed); Decide creepage (D-197: 2.0 mm accepted for the prototype, IEC 60664 check before product use); Decide RT1 isolation (D-198: accepted, buy all, M-01 on the first RF board); Decide D-43 (M-120: BZT52H-C24 passes the 13-coil pulse, Diotec second source); Decide A-13/D-45 (D-199: Mean Well HDR-30-12 + HDR-15-5, short-circuit current far below 50 A); Decide P-6 to P-13 (D-200: P-6 to P-12 declined, P-13 RF C6/C7 MPN with B-3); P-1 to P-5 (D-190, M-108), which also closes S-11; firmware F-1 to F-4 (PR #13).

The table lists only open items. The sections below give the evidence.

| Group | # | Open item | Board |
|---|---|---|---|
| Blocker | B-3 | Order BOMs with MPN, maker and second source on every line | RF, shack |
| Blocker | B-4 | Order-readiness pass: Gerbers, drill, position, JLC DFM, sign-off of the new RF routing | RF, shack |
| PCB | S-13 | Confirm the XT60/XT30 pad polarity | RF, shack |
| Case | S-14, S-15 | Hold CNC order W2026102506308334; first buy and measure RT1 ×4, one 83-798, one of each SMA, an XT60/XT30 pair | Case |
| Decide | | Case: unit 2 ribbon slot, end-plate screws, NPTH for the spacers | Case |
| Records | S-16 | Update `verify_logic.py` to D-162; re-run and re-file | — |
| Records | S-17 | Close the 34 design-log rows that later entries closed | — |
| Records | | Remove the iCloud duplicates ("name 2.ext") | — |

Suggested order: B-3 and B-4, with the S-items of each board in its pass.

## Verdict

**NO-GO for ordering today. GO after the 4 blockers and the "should fix" PCB items below are closed.**

Update 2026-10-31 (later): B-1 and B-2 are fixed on the RF board (D-189, M-107). B-3 and B-4 remain open.

The schematics are sound. ERC is clean. The logic and system models pass. The firmware agrees with the netlists and with the datasheets. The blockers are in the RF board layout (copper under the case bosses, relay NC pads with logic clearances) and in order readiness (no order BOM and no order-readiness pass for the RF board and the shack interface). All fixes are small. No fix changes the architecture.

Order of work:
1. RF board: fix B-1 and B-2, then do an order-readiness pass like M-67 (B-4).
2. Controller board: FAULT to IO6 (S-1) and the SDA jumper default (S-2). Then regenerate the production zip (S-9).
3. Shack interface: fix the SDA jumper default, the width, U4/U9 and IO2/IO9 (S-2, S-8, S-11, S-12). Then do an order-readiness pass.
4. Order BOMs for the RF board and the shack interface with full MPNs (B-3).
5. Buy a few long-lead or unknown parts first: RT1 ×4, one SO-239 83-798, one of each SMA, an XT60/XT30 pair. Measure them, then release the case (S-14, S-15).

## 1. What was run

| Check | Command / method | Result |
|---|---|---|
| Netlists against schematics | `kicad-cli sch export netlist --format kicadxml` on all three, then a script compare against rf14/ctl14/si16 | identical: same parts, values, footprints, connectivity |
| ERC | `kicad-cli sch erc --severity-all` | 0 violations on all three boards |
| DRC | `kicad-cli pcb drc --severity-all --schematic-parity` | see table below |
| verify_logic.py | `python3 verify_logic.py rf14.xml ctl14.xml` | 51 pass, **1 fail** (S-16: the script is stale, the board is right) |
| verify_system.py | `python3 verify_system.py si16.xml ctl14.xml` | 52 pass, 0 fail; output equals the filed system-verification.md |
| Firmware | `cargo test --workspace`; `cargo clippy --all-targets -- -D warnings`; `cargo fmt --all --check`; riscv32imc builds; `cargo build --release` of both targets | 231 pass, 0 fail, 1 ignored; clippy, fmt and builds pass. Nothing flashed |
| Firmware against spec | traceability over requirements.md, link-protocol.md, test-spec.md; probes on `SystemSim` (outside the repo) | section 5 |
| Pin maps | `box-core/src/board.rs`, `shack-core/src/board.rs` and both `main.rs` against the netlists and the RUST-1 schematic | match; section 4 |
| BOM | every line against the filed datasheets (pin-out, package, ratings); stock from web snapshots | section 6 |
| Fab and case | board rules and geometry against JLCPCB capabilities (fetched 2026-10-31); holes and cut-outs against RF-CASE-01 rev B; Gerber export | section 7 |
| Open items | design-log.md sections 1 to 6, docs, review of 2026-10-19 | section 8 |

DRC detail:

| Board | Violations | Unconnected | Parity | Assessment |
|---|---|---|---|---|
| RF board | 0 | 30 | 199 field warnings | the 30 are pad 12 pairs of the row relays, joined inside the RT1 (M-76). Accepted, but see B-2 |
| Controller | 0 | 0 | 89 field + 4 net-name warnings | the net warnings are only `/` against `{slash}` in the name. Cosmetic |
| Shack interface | 4 hole clearance, 12 starved thermal, 4 lib footprint mismatch | 0 | 199 field + 3 net-name warnings | hole clearance = USB4105 pegs, the maker's land (A-26). Starved thermals: R218 to R421 GND pads, one spoke. Footprint mismatch: J3, J11 to J13 differ from the library copy (re-sync or accept) |

The parity field warnings are all "MPN/Description missing in the footprint". They are cosmetic, but they show that the PCB files do not carry the MPNs (see B-3).

## 2. Blockers

### B-1. RF board: copper under the case bosses, with only solder mask between it and the aluminium

**Status 2026-10-31: fixed (D-189, M-107).** Nearest other-net copper now 4.47 to 4.62 mm from each support centre and 5.51 mm from each GND boss centre on B.Cu. DRC 0. Your sign-off of the new routing is still open (B-4).

- Evidence: RF-CASE-01 rev B, Ø8 seat faces C1 to C6 under S1 to S6, and Ø10 faces B1 to B10 under the GND screws. On B.Cu (board-rel mm, distances from the hole centre):
  - S2 (149, 5): +12V_RLY vias at 3.52 and 3.53, +5V via at 3.59, R3_TX2_DRV via at 3.97.
  - S1 (5, 5): R1_TX1_DRV via at 3.53.
  - J4 GND boss B8 (4, 52.5): EXP_INT via at 3.81, Net-(D211-A) (K211 coil low side) via at 3.86.
  - GND pour and GND vias reach 3.45 at all six supports.
- Found by two reviewers on their own (layout read and design-log pass). D-102 asks for an 8 mm keep-out. The layout keeps it on F.Cu only.
- Failure: the mask wears under the clamped boss (torque, vibration, temperature cycling). The result is +12V_RLY or +5V shorted to the case, K211 stuck on, or GND joined to the support, which defeats the CHASSIS_Sn split of D-162.
- Fix: B.Cu rule-area keep-outs, Ø9 at S1 to S6 and Ø11 at the 10 GND bosses (no tracks, no vias, no pour), then re-route those vias and run DRC. A 7 mm washer on top touches F.Cu GND vias at 3.40 (S3) and 3.46 (S4, S5): use the same keep-out on F.Cu, or a smaller washer.

### B-2. RF board: relay NC pads carry RF but get logic clearances

**Status 2026-10-31: fixed (D-189, M-107).** Pad 12 is in netclass RF and in the router fixed nets: 2.00 mm on F/B, 0.50 mm inner. DRC 0.

- Evidence: pad 12 (NC) of the 30 row relays is on nets `unconnected-(Knnn-Pad12)`. When the coil is off, NC is joined to the common, so the pad carries the row-bus RF (173 V peak, A-03). None of the netclass patterns in rf-board.kicad_pro matches these nets, so they get the default clearance. A scratch DRC with these nets in the RF class gives 499 hits. GND copper sits at 0.20 mm on F.Cu, and In2/In3 logic tracks at 0.28 mm (D-117 asks for 0.5 mm, D-12 asks for 2.0 mm). Example: K310 at abs (255.8, 181.8). All real RF-class copper is at ≥ 1.99 mm.
- Failure: creepage below your own rule in a humid outdoor box. RF is also coupled into the In2/In3 logic tracks. An I2C error under 100 W stops the station and can hot-switch (firmware F-3). So this coupling is a real path to a hot switch.
- Fix: add the netclass pattern `unconnected-(K*-Pad12)` → RF, refill the zones, re-route the logic tracks that fall inside, and run DRC.

### B-3. No order BOM for the RF board and the shack interface

- Evidence: only `hardware/unit/controller-board/production/bom_hand_assembly.csv` exists. It matches ctl14 one to one. On the RF board and the shack interface these lines have no MPN:
  - RF: R401 to R701 "1M HV" (D-32 open); C6/C7 47 µF 25 V polymer (D-129 open); C404 to C704 4.7 pF 1 kV C0G (A-22); J14 header; all passives.
  - Shack: C1; C205/C305/C405 10 nF 1 kV; the 1 nF C0G line filters; JST XH; headers; all resistors.
- Fix: port `gen_bom.py` to rf14 and si16, with MPN, maker, second source and voltage on every line. Carry the PCA9539 not-R rule (D-133).

### B-4. RF board and shack interface: no order-readiness pass

- Evidence: the controller has its production set and the M-67 pass. The RF board items are still "for review" (D-117, D-161; M-76 lists "open: stitching vias, aggressor/victim check, silkscreen p3"). The shack layout and plates are "for review" (M-85 to M-105, D-182 to D-187). Neither board has a production folder.
- Fix: after B-1 and B-2, do the same pass as M-67 on both boards. That means Gerbers, drill, position and BOM, a JLC DFM upload (it also closes A-26), and your sign-off.

## 3. Should fix before order

PCB changes (cheap now, rework or respin later):

| # | Board | Finding | Evidence | Fix |
|---|---|---|---|---|
| S-1 | Controller | The box MCU cannot read FAULT. After a supervisor trip while the MCU keeps running (a hang that ends, or a 3V3 dip below the TPS3823 threshold but above the ESP32 brown-out), the box stays in WaitSafe for good. Shack RESET does not help. Only a power cycle recovers, and no fault code is sent | ctl14: FAULT = TP3, U13.5, U14.6, U15.2 only; A1 pad 11 (IO6) is unconnected. relay_box.rs:317-333; probe P2 | FAULT via 1k to IO6. Firmware: a "supervisor tripped" code and an operator-requested LATCH_CLR (rule 2) |
| S-2 | Controller, shack | SDA select jumpers come open from the fab. Every PCA9539 then NACKs and the self-test fails. A three-pad solder blob joins the GPIO7 LED to SDA | JP11 (ctl) and JP61 (si): `SolderJumper-3_P1.3mm_Open_...`; pads 1 = SDA_IO7 (pad 12), 2 = SDA, 3 = SDA_IO10 (pad 17). Firmware hard-codes GPIO10 (box main.rs:153, shack main.rs:162). The shack has no assembly note | Use a footprint bridged 2-3 by copper (RUST-1 default; cut for RUST-2), or at least add an assembly step and a continuity check to bring-up |
| S-3 | RF | The bias-T FET drains have no copper area. C-17 assumes 1 in² (RthJA 60 K/W). A minimum SOT-223 pad is about 2× that. A held short at 55 °C (0.79 W) then puts Tj near 150 °C. That breaks D-54 "a short stays in current limit without firmware" | Q1012, Q1022, Q1032, Q1042 (SOT-223-3_TabPin2): /A1_BIAS to /A4_BIAS are only 0.254 mm tracks (42 to 55 mm² in all), no zone. IRFL9014 Rev G RthJA 60 K/W "PCB mount" | A ≥ 1 in² drain pour per FET (F.Cu + B.Cu with vias), or recalculate C-17 with the real pad and the firmware turn-off time |
| S-8 | Shack | The board is 160.0 mm wide in slots with 0.2 mm play (M-92). JLC outline tolerance is about ±0.2 mm | outline 160 × 161 | Trim to 159.6 mm |
| S-9 | Controller | The production zip is stale: In2, F_Mask and F_Cu differ from a fresh export. The ORDER sheet swaps the 0.8 and 1.0 mm hole labels | `controller-board/production/` | Regenerate after S-1 and S-2 |
| S-11 | Shack | U4, U9 74LVC1G74 are still in the TI-only DCT package. D-154 fixed this on the controller only | si16; R-10, D-154 | VSSOP-8 as in D-154, or a documented exception with spares |
| S-13 | RF, shack | XT60/XT30 pad polarity is not confirmed (pad 1 GND, pad 2 +). A reversed supply damages the board | A-07, M-02 | Amass drawing or one part in hand; fix the silkscreen |

Parts and BOM:

| # | Finding | Evidence | Fix |
|---|---|---|---|

Case:

| # | Finding | Fix |
|---|---|---|
| S-14 | The XT60/XT30 faces sit about 8.7 mm behind the outer wall face. The plug may sink fully into the cut-out and be pullable only by the cable | Check with a real plug pair before the CNC order |
| S-15 | CNC order W2026102506308334 has the old tray. B-1 (boss diameter) and the measured 83-798 and SMA rear lengths (A-05, A-21) can still change it | Hold or cancel; resubmit after B-1, A-05, A-21 |

Verification records:

| # | Finding | Fix |
|---|---|---|
| S-16 | verify_logic.py fails one check on rf14: "Supports S1 to S6 plated on CHASSIS (with H1)". The board is right (D-162 gives each support its own CHASSIS_Sn net, each with its own DNP bond C8 to C13). The script still tests D-132. The filed logic-verification.md says "All checks pass", but it was not re-run after D-162 (M-76 lists ERC only) | Update the check to D-162 (each Sn on its own net with only Cn to GND, H1 on CHASSIS), re-run, re-file the .md |
| S-17 | 34 design-log rows are still marked open or "to confirm", but later entries close them (for example D-58 by D-149/C-39, D-171 by M-92, A-23 to A-25, A-30) | Update the statuses, so the open list is true before the order |

## 4. Pin maps (netlist against firmware)

Result: match. No finding makes a board fail.

- Every direct GPIO, every PCA9539 address and bit, and every active level agree. Expanders: 0x74 to 0x77 (box), 0x74 (shack). DevKit sensors: 0x68, 0x70. No address clash.
- JP11 is on the controller, JP61 on the shack interface. Pads: 1 = IO7 (DevKit pad 12), 2 = expander SDA, 3 = IO10 (pad 17). Firmware uses IO10 (RUST-1). Default state: see S-2.
- GPIO7: on both carriers it goes only to jumper pad 1. With 2-3 bridged, it drives only the DevKit LED, as both firmwares expect.
- D-58 link polarity: idle = loop current = mark, in both directions. Both receivers pull low on current. Both firmwares invert RX (with a pull-up) and send TX without inversion (box main.rs:268-276, shack main.rs:339-347). A cut cable or a sender in reset reads as a break. Correct.
- SAFE/KILL, supervisor, latch, DevKit header (ENABLE, RST, strap pins) agree. R52/R53 DNP is consistent with R2/R3_K0 as outputs.

Can wait: RUST-2 needs a firmware rebuild and its LED pin is not confirmed; the box ROM boot log goes out on GPIO21 (link TX) for about 1 s per box reset (include a box reset in the link test); display SPI mode 0 against mode 3 for CS-less ST7789 modules; two 3.3 V rails on the box I2C bus (scope the back-feed at power-up); ESP32-C3 reset pull states on GPIO0/3/4/5/6 are not checked (the datasheet is not filed; an internal pull-up against the 100k pull-downs would give about 2.3 V on a PERMIT line during reset). File the C3 datasheet and close this before the bench.

## 5. Firmware, and hardware with firmware, against the spec

Result: the firmware is clean and agrees with the hardware. No firmware finding needs a PCB change, except S-1.

Agrees with the datasheets:
- RT1 operate/release 8/6 ms and bounce 4/6 ms against RELAY_WAIT 12 ms (relay_box.rs:82).
- PCA9539 power-up and RESET defaults (all inputs, so the relays are off), with the F1 order on each set-up.
- WDI toggles every 10 ms, which fits TPS3823, MAX823 and APX823. The supervisor does not reset the MCU, so the self-test watchdog step works.
- 9600 8N1 against the PC817 edges (C-18).
- The link loss (300 ms) is detected before the shortest watchdog time-out (0.9 s).

Traceability: FR-01 to FR-03, FR-05 to FR-09, SR-01 to SR-06, DR-07 and the firmware rules F1 to F15 are covered by passing tests. Most of these are sim only, so the bench must still prove the hardware part. FR-04 (unit 2) and FR-11 (presets) are not implemented, as planned. ResultCode 8 (ReadBack) is in link-protocol 4.1 but is never sent.

Fix in firmware before first use on air (no PCB impact):

| # | Finding | Evidence |
|---|---|---|
| F-1 | After a Hello, the box releases K0 after 100 ms without checking TX sense. That is a hot switch on K201 if a radio has no TX INH or has an RF tail > 100 ms, after a pair-4 failure | relay_box.rs:769-779; probes P1, P4; SR-03, F14 |
| F-2 | EXP gets a TX permit with no unit 2 fitted (R2/R3 transmit into an open SMA) | relay_box.rs:861, crossbar.rs:30; probe P5 |
| F-3 | One I2C error with a permit out stops the station and hot-switches. A read-back mismatch is only flagged, with no rewrite | relay_box.rs:545-576, 555-557; probe P3 |
| F-4 | RELAY_WAIT counts from the tick start. With real I2C time (about 3.8 ms per read), open-to-close can drop to about 8 ms, below F10 | relay_box.rs:672 |

Can wait: fault code overwritten (507-518); the LATCH_CLR pulse is tens of ns (hold for 1 ms); FR-06 against rule 8 wording; SR-02 wording; link answer margin about 53 ms against 60 ms (measure at P7); a sub-µs SAFE glitch resets all expanders (C1204 is a DNP footprint already, so size it after an EFT test).

The emulator does not model: I2C time (sim-core/src/i2c.rs:6), I2C bit errors, partial brown-out, opto edges, contact state (the read-back is the drive pin), ESD/EFT, or the panic-halt recovery. Add bench tests for these to test-spec.md.

Note: another session edited firmware files around 17:01 during this review (shack-core, the settings test, the shack target). The test counts are from the tree before those edits.

## 6. BOM

All pin-outs of the active parts, relays and connectors match the filed datasheets for the intended makers. That includes RT1 (RT1pb rev 4 p.2, S0418-CA), PCA9539/TCA9539/PI4IOE5V9539, VO2611, TPS3823, 74LVC1G74/1G27, TLP176AM, LP2985, L7805/LD1117, USBLC6-2, ACT45B, the Bourns 2036 GDT, the Wurth RJ45 and the 83-798/901-9215. Fitted capacitors are within the 0.7 voltage factor. There is no 0402. The order data has gaps: B-3.

Can wait:
- TE gives no HF data for the RT1 (no contact capacitance, no isolation). The open-contact dielectric is 1000 Vrms against 173 V peak; the current is 2.45 A against 16 A. Run the M-01 coupon test on 4 relays before you buy all 34. (Decided D-198: buy all, M-01 on the first RF board.)
- C404 is 1812 in the netlist and 1206 in rf-board.md. Fix the doc.
- ACT45B windings are rated 50 V. Coilcraft 1812CAN (250 Vrms) is the more robust first source.

## 7. Manufacturability and case fit

OK:
- The stack-ups match JLC06161H-7628A (RF, 6 layers) and JLC04161H-7628 (4 layers).
- The RF track (0.975 mm) is about 50 Ω with mask. 2.45 A rms gives about a 10 °C rise.
- Vias are 0.6/0.3 and tented. ENIG. Mask is 1:1, with a smallest pad gap of 0.2 mm.
- There are no fiducials, which is correct for hand assembly.
- Drills match the datasheets: RT1 Ø1.3, XT60, XT30, Wurth RJ45 (1.0 and 3.25), GDT 1.2, headers 1.0.
- RF J14 and controller J2 coincide pin for pin. Engagement is about 4.7 mm at 20 mm standoffs (Samtec 3.68 to 6.35).
- The holes, bosses, SO-239 and SMA axes and the top-wall cut-outs match RF-CASE-01 rev B exactly.
- Corner clearance is 2.76 mm (RF) and 0.68 mm (controller).
- Gerbers: correct layer counts, closed outlines (268 × 230, 152 × 122.5, 160 × 161), no zero apertures.

Can wait:
- The board rule floors are lower than JLC's (hole-to-hole 0.25 against 0.45, silk text 0.8 against 1.0), but the real geometry passes. Raise the rules so later edits are caught.
- The XT60 tab slot annular ring is 0.15 mm (JLC absolute minimum).
- The XT30 holes are 1.9 mm against Amass's 1.7.
- There are three partial vias in pad (same net): RF U801.11, controller U12.1, shack U11.2.
- The shack board has no date code field.
- The lid and height check used the controller STEP of 2026-10-22. Redo it after S-1.
- Not checked: IEC 60664 creepage values (C-05; accepted for the prototype, D-197) and the XT60 mating depth (no cavity depth on the Amass sheet).

## 8. Open items in design-log.md

Totals: 24 rows block ordering, 41 can wait for the bench, and 34 are closed by later entries but still marked open (S-17).

Blocks ordering (covered above or with their own closing action):

| Item | Closing action |
|---|---|
| B-1 under D-102/M-32 (bosses), C-17/D-54 (S-3), R-10/D-154 (S-11), D-180 (S-12), A-07/M-02 (S-13), A-26 (B-4 DFM), D-117/D-161 and M-85 to M-105 (B-4), D-129, D-32, A-22/D-111 (B-3) | see the findings |
| A-05, M-03, D-105 and A-21, D-110, D-174: 83-798 rear dimensions and SMA contact length, scaled from drawings | Buy one of each and measure |
| Review items 8 to 10, D-121: about 25 parts not stock-checked | Stock and second-source sweep with B-3 |
| D-160: choke interwinding capacitance | ACT45B datasheet check (low risk) |
| A-27: end-plate screws; A-29: SMD spacers without NPTH | Pan-head screws or a JLC countersink; a solder test, or add the NPTH now |
| D-53, CT-06: unit 2 ribbon slot in the case | Decide: machine the slot now or later |

Can wait for the bench: R-12, A-02, A-03, A-14, A-15, A-17, A-18, A-20, A-31, C-13, C-15, C-16, C-18 to C-25, C-29, C-31, C-34, C-37 to C-39, D-41, D-63, D-65, D-69, D-71, D-80 to D-82, D-88, D-90, D-96, D-100, D-104, D-121, D-138, D-142, D-151, D-188, M-10, M-12, M-28, M-31, M-81, RF-10 to RF-12, CT-02, CT-03, CT-12, CT-13, SI-02, SI-05, SI-06, FR-11, TC-05 to TC-08. Each is a value of a fitted-later part, a jumper or DNP footprint, a firmware setting, or a measurement on built hardware.

## 9. Housekeeping (no impact on the boards)

- The repo has many iCloud duplicates ("name 2.ext"), for example `rf-board 2.kicad_pcb` and `verify_logic 2.py`. They are gitignored. Still, a tool or a person can open the wrong file. Remove them before the production export.
- Pin-map text: shack-interface-rev-a.md fixed (M-114). D-83 still says IO2/IO9 unused; D-180 supersedes it.

## 10. Part reuse (added 2026-10-31, Prins's request)

Method: all fitted parts of rf14, ctl14 and si16, grouped by value, footprint and MPN (131 groups, test points and solder jumpers included). Each near-duplicate was checked for its role in the netlist and for a design-log reason to keep it apart. Nothing is changed yet.

The Nexperia 74LVC1G74 datasheet (Rev 18, 2025-09-22) is now filed as `Datasheets/74LVC1G74_Nexperia_DS_Rev18_2025-09-22.pdf`. 74LVC1G74DC = SOT765-1 (VSSOP8, MO-187), pin-out 1 CP, 2 D, 3 Q̄, 4 GND, 5 Q, 6 RD, 7 SD, 8 VCC (Table 3, p.3), the same as TI DCU.

| # | Proposal | Parts | Change type | Lines saved | Check |
|---|---|---|---|---|---|
| P-1 | "2.2k" (RF R2, R901, R902) and "2k2" 0603 (SI) → one line 2k2 0603 | 7 | text only | 1 | none |
| P-2 | "100n" (RF C1011 to C1041, SI C3 and others) and "100n 16V" (SI C64) → 100n 50V X7R 0603 | 8 | text and voltage | 1 | also closes S-6 (RF bias caps at 12.6 V) |
| P-3 | "10n" (RF C4, CTL C12) and "10n 50V X7R" (RF C403 to C703) → 10n 50V X7R 0603 | 6 | text only | 1 | none |
| P-4 | SI PC817X → PC817X2NSZ9F, as on the controller | 4 | MPN only | 1 | none |
| P-5 | SI U4, U9: SSOP-8 0.65 (TI DCT, one maker) → VSSOP-8 0.5, SN74LVC1G74DCUR, second source Nexperia 74LVC1G74DC,125, as controller U13 (D-154) | 3 | footprint (shack re-route near U4, U9) | 1 | closes S-11 |
| P-6 | CTL R14, R24, R34 4.7k (VO2611 output pull-up on DATA_RX and the other receive lines) → 2k2 | 3 | value | 1 | 1.5 mA into the VO2611 output, faster edges; no other effect |
| P-7 | SI R73, R74 680R (SAFE and LATCHED status LEDs) → 1k | 2 | value | 1 | about 30 % less LED current; see that the LEDs stay visible |
| P-8 | CTL R43 220R 0603 (PC817 LED from +5V) → 240R | 1 | value | 1 | LED current about 15 mA instead of 17 mA; C-18 edge timing at 9600 baud has margin |
| P-9 | SI C2 330n 50V 0805 (7805 input) → 1u 50V X7R 0805 (the RF C101 line) | 1 | value | 1 | ST asks for 0.33 µF minimum; D-124 kept the datasheet value, so this reverses a small decision |
| P-10 | SI R14, R24, R34, R44 22k (BCP53 base drive) → 10k | 4 | value | 1 | base current about 1.3 mA instead of 0.6 mA; check the loop headroom of C-21 |
| P-11 | SI C4, C5 10u 16V 1206 (+5V) → 22u 16V X7R 1210, as C6 | 2 | footprint | 1 | room on the shack board |
| P-12 | SI D1 SS34 (SMC, series input diode behind the 500 mA T fuse) → SS14 (SMA), as RF D1 | 1 | footprint | 1 | SS14 IFSM covers the fuse-blow current; saves board area |
| P-13 | RF C6, C7 (47 µF polymer, no MPN yet, D-129) and SI C1 (47 µF 35 V radial) → one 47 µF 35 V polymer part in 6.3 × 7.7 | 3 | MPN choice (RF), footprint (SI) | 1 | a 35 V part also adds margin above the SMBJ15A clamp (about 24 V) on the RF rails; pick it together with B-3 |

Kept apart on purpose:
- XT30 next to XT60 (D-17: the rails cannot be swapped).
- LD1117S33 on the shack interface (D-81: LP2985 fails the 0.7 current factor at 115 mA).
- SMBJ16A on the shack interface against SMBJ15A on the RF board (D-124: 15 V shack input; the RF rails need the lower clamp for the 25 V parts).
- TLP4176G next to TLP176AM (normally closed against normally open).
- 220R and 47R MELF parts on the link (D-58: pulse rating).
- 1M HV axial next to 1M 0603 (D-32: voltage).
- 0R 1206 next to 0R 0603 (current links).
- BZT52C15 and BZT52C24 (gate clamp and coil clamp).
- The 74LVC1G gate family (02, 08, 14, 27, 74): each gate is logic-verified; merging gates would mean new verification for one line less.

**Status 2026-10-31: P-1 to P-5 applied (D-190, M-108).** ERC 0, netlists rf15, ctl15, si17; the shack U4/U9 are re-routed with a fixed fan-out; DRC as before plus one harmless RGND island at JP306. **Status 2026-11-01: P-6 to P-12 declined; P-13 only for RF C6, C7 (MPN at B-3) (D-200).**

Total: up to 13 order lines fewer. P-1 to P-4 change no circuit and can go in with B-3. P-5 is needed anyway (S-11). P-6 to P-13: decided by D-200.

Housekeeping found on the way: shack F1 uses `Fuse_1206_3216Metric`, not the HandSolder land used on every other 1206 part (R-07).
