# Design review against hardware-design-rules v2.2 (2026-10-19)

Three read-only review passes. Actions taken: design log D-119 to D-125, C-14 (recomputed), C-34, M-41.

## RF board review against hardware-design-rules v2.2

Board: Shack Relay Matrix rev C RF board. Stackup JLC06161H-7628A, 6 layers (D-115). Layout state p1c-6layer, parts placed, no tracks.
Sources: `hardware/unit/verify/rf9.xml`, `docs/design/rf-board.md`, `claude/gen_rfboard_pcb.py`, `claude/design-log.md`.
Review only. No project file was changed.

| ID | Skill rule | Evidence | Severity | Proposed fix | Type |
|---|---|---|---|---|---|
| RF-01 | pcb-layout.md, "Layer changes and vias": a change between two different ground planes needs a ground via next to the signal via; RF needs up to four | RF rows on L1 (ref L2), columns on L6 (ref L5). Every relay-pin and column-link transition goes L1 to L6 through L2 to L5. `rf-board.md` and `gen_rfboard_pcb.py` have no rule for return vias at these transitions, or at the SO-239/SMA lands | major | Add a rule to `rf-board.md` and a generator step: 2 to 4 GND vias within about 1 mm of each RF via and through-hole RF pin, through all layers. Add a check to the layout verifier | clear fix in docs/generator |
| RF-02 | schematic-and-marking.md, review checklist: every input has a defined level; "open" is not "off" | PCA9539 unused IO with no pull: U901, U902, U903 IO1_6 and IO1_7; U1001 IO1_0 to IO1_7 (14 pins). They are inputs after reset; RLY_EN also drives RESET, so every reset puts them back to floating | major | Pull-down array (10k 4-pack) on the unused pins, or tie to GND directly (input-only use). The firmware rule "configure as output low" alone does not cover reset and boot | clear fix (pull-downs); decision if firmware-only |
| RF-03 | passives.md, decoupling (Bogatin): bulk capacitance on the rail; rail noise = L × dI/dt | +12V_RLY and +12V_AUX: no capacitor at all, only SMBJ15A and 1 A fuse. +12V_SW: C2 is DNP 0603. Relay coils switch on these rails across a cable from the controller | major | Bulk polymer or electrolytic (for example 47 to 100 µF, 25 V) at each 12 V entry, plus 1 µF ceramics distributed in the relay field. Check the inrush against the upstream switch and fuse | decision for Prins (value, body); then clear fix |
| RF-04 | bring-up-and-measurement.md (section 18): test points and a 0 Ω or solder jumper per supply for current measurement | No TP parts in rf9.xml. No current jumpers on +12V_RLY, +12V_AUX, +12V_SW, +5V, +3V3 | major | Add TP on every rail, I2C, EXP_INT, RLY_EN, TX_ANY, A2_RFDET; add a solder jumper in series with each rail entry; a via in open GND area as GND test point | clear fix in generator |
| RF-05 | schematic-and-marking.md, review checklist: current of all power pins per rail added up and checked against the source | +3V3 from U1 LP2985-33 feeds the PCA9539s, R801, R831 to R834 detector pull-ups and R901 to R903. Open item C-14: LDO load not recomputed after rev C changes | minor | Recalculate the +3V3 load sum and LDO dissipation at worst-case input; record in the design log and the underload register | clear fix in docs |
| RF-06 | pcb-layout.md, "Copper pour": tie every pour to a net, stitch about every λ/10; "Board edge": ground via fence on every layer, no 20H | L1 GND pour and inner planes planned, but no stitching pitch, no edge fence and no "no floating copper" rule in `rf-board.md` or the generator | minor | Specify stitching pitch (for example 5 mm grid, far below λ/10 at 54 MHz, set by logic harmonics), an edge fence through all layers, remove islands, and "no copper added without approval" on the fab notes | clear fix in docs/generator |
| RF-07 | passives.md, decoupling (Rosenberg, Bogatin): largest value in the chosen body, equal values, no mixed values | One 100 nF per PCA9539 (C901, C902, C903, C1001). +3V3 has C5 4.7 µF 0805 plus 100 nF; +5V has C3 1 µF plus C802 100 nF (mixed values) | minor | Use 1 µF X7R in the same body at each IC, or keep 100 nF but drop the mixed-value pattern; simulate the rail if mixed values stay | decision for Prins |
| RF-08 | environment-and-protection.md, chassis and bonding (Armstrong): multi-point RF bonds closer than λ/10; prototype options per mounting point | H1 is the one CHASSIS point (JP1 open, C1 DNP 10 nF 1 kV). The seven SO-239 bodies bond the RF edge. Supports S1 to S6 have no bond option | minor | Add 0 Ω / capacitor footprints at S1 to S6 so the bond scheme can be tuned on the bench; record the choice as a D- line | decision for Prins |
| RF-09 | environment-and-protection.md: every conductor crossing a shield boundary is filtered at the crossing; slow control lines get series R | J14 lines (SCL, SDA, EXP_INT, RLY_EN, TX_ANY, R1_K0_DRV, A2_RFDET) enter next to 100 W RF without series R or capacitor to GND at the connector | minor | Footprints for series 100 Ω to 1 kΩ and 100 pF to GND at J14 on each slow line (DNP allowed); check the I2C rise time with the added C | to confirm on bench; footprints are a clear fix |
| RF-10 | schematic-and-marking.md, review checklist: shared reset, reset time of every peripheral | RLY_EN is also RESET of U901 to U903 and U1001, with R3 100k pull-down. RLY_EN low holds all expanders in reset, and the IO return to input | minor | Confirm in `verify_logic.py` that every reset entry leaves all relay drivers off and that release timing meets the PCA9539 reset spec; record as a D- line | to confirm (verify script) |
| RF-11 | SKILL.md section 2 and part-selection.md: design blocks for reuse | Detector front end (R831 to R834), +3V3 LDO block and J14 protection set are not written up as blocks | minor | Write the blocks once proven on the bench | clear fix in docs (after bring-up) |
| RF-12 | bring-up-and-measurement.md / pcb-layout.md (Rosenberg two-layer note): measure port-to-port isolation on the first article | The skill note still names JLC0216A for rev C. The board is now 6 layers (D-115) | minor | Keep the isolation measurement in the bring-up plan; correct the skill note to the 6-layer stackup in the next skill revision | clear fix (skill text) |

## Already complies

- Stackup: S, GND, S, GND, GND, S order gives every signal layer an adjacent ground plane; no power plane; rails routed on L3 between GND planes (pcb-layout.md, stackup ordering).
- RF lines as CPWG on L1 over L2, W 0.975 mm, gap 2.0 mm on a thick 7628 dielectric (D-116), matches the RF practice rule.
- Inner antipad 0.5 mm recorded with the fabricator in mind (D-117).
- Halogen status recorded and set aside on purpose (D-118).
- U1 LP2985-33: all pins connected, bypass C4 10 nF fitted; no open control pins.
- I2C pull-ups R901, R902 and EXP_INT pull-up R903 go to +3V3, the same rail as the expanders (no cross-rail leakage path).
- Connector protection: SMBJ15A and fuse on each 12 V entry, SMBJ6.0A and F3 on +5V.
- One continuous ground system, no split planes; single optional CHASSIS bond is a documented choice, not a default left open.
- RLY_EN and TX_ANY have defined default levels (R3, R904 pull-downs): relays off at power-up.

## Review: controller board and shack interface, rev C, against hardware-design-rules v2.2

Scope: docs/design/controller-board.md, docs/design/shack-interface.md, gen_controller_sch.py, gen_shack_sch.py (title block). Read-only review, 2026-10-19. Values marked "to confirm" were not checked against the datasheet folder in this pass.

| ID | Skill rule (file, section) | Evidence | Severity | Proposed fix | Type |
|---|---|---|---|---|---|
| CT-01 | kicad.md / schematic-and-marking.md, title block C4 | gen_controller_sch.py l.84: C4 = "JLC0216A ... RF: coplanar W 2.7 / gap 2.0 mm" (copied from RF board) | minor | Set C4 to the controller stackup and "no controlled impedance" | clear fix |
| CT-02 | SKILL.md §2 design blocks, LDO envelope (IOUT ≤ 105 mA, VIN 4.75–5.25 V, air ≤ 55 °C); verification.md current sum per rail | controller-board.md register: "load with the DevKit to recompute"; LP2985-33 feeds DevKit 3V3 pin | major | Add ESP32-C3 boot and calibration peaks (radio off, still ~ tens of mA bursts), DevKit LED, USB-UART and pull-ups; check against 105 mA and the LP2985 output cap ESR window; record as C- line | to confirm on bench |
| CT-03 | schematic-and-marking.md review checklist: "no leakage between rails", "open control pins" | DevKit SY8088 buck held off, 3V3 fed into its output node | major | Confirm SY8088 EN default and that no body diode or feedback divider loads/back-feeds the LP2985 rail; measure quiescent draw | to confirm on bench |
| CT-04 | environment-and-protection.md, Chassis, shields and bonding: 360° shield bond; RJ45 springs are not 360° | RJ45 LINK, Cat6 cable, GDT to CHASSIS | major | Option A (rec.): unshielded Cat6 + full filtering at entry (loops are differential/isolated). Option B: shielded cable with 360° gland at both ends, not via RJ45 springs. Record D- line | decision for Prins |
| CT-05 | environment-and-protection.md: filter every conductor at the crossing; CM chokes at the connector | Loop lines have GDT + 47R MELF + SMBJ15CA, no RF filter, near a 100 W HF transmitter | major | Add CM choke per pair plus small C to CHASSIS at the RJ45, or ferrite on cable; check opto loop not upset at 100 W | decision for Prins |
| CT-06 | environment-and-protection.md: filter at the crossing | EXP ribbon 0.5 m, ~100 Ω series, TVS at each wall; no capacitor to ground | minor | Add C (e.g. 1 nF C0G to GND) after the 100 Ω at each wall to form an RC; check edge rates | clear fix |
| CT-07 | schematic review checklist: watchdog output can be disconnected on prototypes | TPS3823A-33 WDI/RESET into safety latch | minor | Add 0 Ω or solder jumper on WDI path / RESET to latch for bring-up | clear fix |
| CT-08 | passives.md decoupling (Bogatin, Rosenberg): one value, largest in smallest body, no mixed values | No decoupling section in controller-board.md | minor | Add decoupling table per IC: value, body, position; no 100 nF + 10 nF mixes on one rail | clear fix |
| CT-09 | bring-up-and-measurement.md / SKILL.md §18 test access | No test-point or current-jumper list | minor | List TPs: 5V_IN, 3V3, SAFE latch Q, RF_A2_N, loop currents; 0 Ω per rail for current measurement | clear fix |
| CT-10 | pcb-layout.md stackup ordering; jlcpcb-and-fabrication.md | No stackup recorded for controller | minor | 2-layer 1.6 mm with L2 solid GND (slow logic, routed power OK); record D- line and C4 | decision for Prins |
| CT-11 | SKILL.md §2 second source (DigiKey Direct/Similar) | Register: MAX823 second source, GDT second source, MELF and 220R pulse ratings open | major (release) | Run DigiKey substitutes check, file datasheets, verify MELF pulse rating against GDT let-through | to confirm |
| CT-12 | schematic review checklist: power-down leakage between rails | RF_A2_N (R36 100k pull-down), J2 lines into the RF board when RF board unpowered | minor | Check clamp-diode back-feed from 3V3 logic into unpowered RF board inputs; add series R if needed | to confirm on bench |
| CT-13 | verification.md worst case; schematic checklist reset behaviour | A-14: 74LVC1G74 latch state below 1.65 V | minor | Bench-test brown-out ramp; confirm latch resets to SAFE | to confirm on bench |
| SI-01 | verification.md worst-case corners; SKILL.md §1 underload | shack-interface.md: 13.8 V input, SMBJ16A, L7805CV, LD1117S33; C-25 budget | major | Add C- line for 11–15 V input: SMBJ16A VRWM ratio ~0.94 (document as TVS exception), 7805 dissipation ~1.3 W at 15 V/130 mA (heatsink to wall, Tj check), LD1117 dropout at VIN 4.75 V gives ~3.55 V margin min, tight | clear fix |
| SI-02 | passives.md; application notes: LDO output-capacitor stability | LD1117S33 with 22 µF X7R; D-81 second sources LM1117, AZ1117 | major | Confirm ESR window for each source (LM1117 needs tantalum-like ESR on some versions); add series 0.5–1 Ω or choose a cap all three accept | to confirm |
| SI-03 | environment-and-protection.md: 360° bonding at shack end | Cat6 entry at shack interface | major | Same decision as CT-04, mirrored at shack end | decision for Prins |
| SI-04 | SKILL.md §1, documented exceptions | PESD15VL1BA VRWM 15 V vs 14.4 V lines: ratio 0.96 | minor | Record as TVS exception with reason (clamp must sit close above rail) | clear fix |
| SI-05 | verification.md worst case | A-18: PCA9539 band input 5.07 V vs 0.7 × VDD | minor | Close A-18: divider or level shifter, or prove VIH with worst-case VDD | to confirm |
| SI-06 | SKILL.md §2 design blocks | Loop current source, radio port protection, SAFE latch repeated across boards | minor | Promote to design blocks with fixed envelopes | decision for Prins |
| SI-07 | title block C4 | gen_shack_sch.py l.84: same RF-board C4 string | minor | Correct C4 | clear fix |
| SI-08 | pcb-layout.md stackup | No stackup recorded for shack board | minor | 2-layer, L2 solid GND, record D- line | decision for Prins |
| SI-09 | passives.md: mixed values cause anti-resonance | 7805 with 330 nF + 47 µF (datasheet values) | minor | Keep (datasheet stability requirement); note exception; no extra small values on 5 V | clear fix |
| SI-10 | bring-up-and-measurement.md test access | No test points or current jumpers listed | minor | TPs on 13.8 V after fuse, 5 V, 3.3 V, each radio port line; 0 Ω per rail | clear fix |

## Already complies

- Fail-safe form B TX INH: loss of power or link inhibits TX.
- Hardware SAFE latch independent of firmware (TPS3823 + 74LVC1G74).
- Logic and system verified against the netlist (verify_logic.py, verify_system.py); ERC 0/0.
- No switching regulator near the receivers; SY8088 held off, linear rails only.
- Coordinated entry protection on LINK: GDT to CHASSIS, series 47R MELF, SMBJ15CA.
- Radio port ESD at the connector, return to CHASSIS via 10 nF 1 kV.
- MD-80SM exception documented (D-87).
- Wi-Fi and BLE off in the shack, no on-board radio emissions.

## Shack Relay Matrix rev C: part list vs hardware-design-rules v2.2, sections 1 and 2

Date: 2026-10-19. Source: netlists rf9.xml, ctl6.xml, si12.xml; Datasheets/_register.md.
DigiKey NL checked in the in-app browser (product page Substitutes, stock, Part Status).
After 14 product pages DigiKey showed a bot check (HTTP 429, "Just a moment"). I did not try to get past it.
The DigiKey API in the KiCad tool has no credentials. Rows marked "pending" still need the DigiKey check.

Underload column: "reg" = a check is recorded in the register dated notes or rf-board.md section 3.
In this fork I did not check line by line that each record has parameter, operating value, rating, ratio and result. "?" = no record found in the register.

## Active and electromechanical parts

| MPN | Function, boards | Underload | 2nd source in register | DigiKey substitutes (other makers, in stock) | Stock NL | Lifecycle | Verdict |
|---|---|---|---|---|---|---|---|
| PCA9539D,118 (SOIC-24W) | I/O expander, RF x4, SI x1 | reg | TCA9539 (no SOIC-24W variant, to confirm) | Direct: TI PCA9539DWR (1,690). Similar: NXP PCA9539PW,118 TSSOP (17,832) | 8,272 at broker Flip Electronics only | **Obsolete (NXP)** | **lifecycle risk** |
| TPS3823A-33DBVR | Supervisor/watchdog, CTL x1, SI x2 | reg | none | TI only: TPS3823-33DBVR, -33DBVT ("Parametric Equivalent") | **0** | Active | single-source: reason needed |
| BSS138BK,215 | N-FET driver/level shift, RF x42, CTL, SI x3 | reg | DMN61D8L-7 (DS "Advanced Information") | Direct: onsemi 2V7002KT1G (103k). Similar: Panjit PJA138K_R1_00001 (668k), onsemi 2N7002K (352k), BSS138-G | **0** (backorder 2 Nov) | Active | second source to add (2V7002KT1G) |
| PMV50EPEAR | P-FET switch, RF x1 | reg | AO3407A (not on DigiKey list) | Similar only: onsemi FDN360P (38k), TSC TSM650P03CX (52k) | **0** | Active | second source to add (verify limits) |
| IRFL9014TRPBF | P-FET high side, RF x4 | reg (rf-board §3) | NTF2955 | Direct: Vishay -BE3 (same maker). Similar: onsemi NTF2955T1G (8,560) | 39,319 | Active | ok, one 2nd source (not jellybean) |
| BC857B,215 | PNP, RF x4, SI x4 | ? | none | Direct: Diodes BC857B-7-F (140k). Similar: Infineon BC857BE6433HTMA1 (132k) | **0** | Active | jellybean ok, register to add |
| BCP53-16,115 | PNP driver, SI x4 | ? | none | Direct: ST BCP53-16 (1,695), Diodes BCP5316TA (120). Similar: onsemi SBCP53-16T1G (117k) | **0** | Active | jellybean ok, register to add |
| BC847B,215 | NPN, SI x2 | ? | none | Direct: Diodes BC847B-7-F (86k) | 124,086 | Active | jellybean ok, register to add |
| LM2901DR (TI) | Quad comparator, RF x1 | reg | none | Similar: ST LM2901DT (42k), onsemi LM2901DR2G (28k) | **0** | Active | jellybean ok, register to add; TI two-die check |
| LP2985-33DBVR | 3V3 LDO, RF, CTL | reg | ST LD2985BM33R (confirmed 2026-09-27) | none listed by DigiKey | 12,000 | Active | ok via register (not on DigiKey list); TI two-die check |
| LD1117S33CTR | 3V3 LDO, SI | reg | LM1117-3.3 / AZ1117-3.3 "pin-out to confirm" (D-81) | Direct: ADI LT1117CST-3.3#PBF (5.4k). Similar: onsemi NCP1117ST33T3G (43k), MaxLinear SPX1117M3-L-3-3 (24k) | 78,389 | Active | jellybean ok; check output-cap stability per 2nd source |
| L7805CV | 5 V regulator TO-220, SI | reg | none | Direct: TI UA7805CKCS (1,550). Similar: onsemi MC7805CTG (41k) | 86,799 | Active | jellybean ok, register to add |
| RTD14012F | Relay 12 V, RF x37 | reg (D-06, coil exception) | none (D-06 single type) | pending | pending | pending | single-source: reason needed (D-06 reason to extend with 2nd maker search) |
| SN74LVC1G02/08/14/27/74 | Logic, CTL, SI | ? | none | pending | pending | pending | expected jellybean (Nexperia 74LVC1Gxx), pending |
| VO2611 | Opto, CTL x3 | reg | none | pending | pending | pending | pending (6N137-class, 2nd source likely) |
| PC817X | Opto, CTL, SI x3 | reg | none | pending | pending | pending | pending (Sharp; Everlight/Lite-On equivalents likely) |
| TLP176AM | Photorelay, CTL, SI x3 | reg | AQY212G3HS | pending | pending | pending | pending |
| TLP4176G | Photorelay, SI x3 | reg | AQY412S | pending | pending | pending | pending |
| SMBJ15A / 15CA / 16A / 6.0A | TVS, all boards | reg | none | pending | pending | pending | expected jellybean, register to add |
| SS14, SS34 | Schottky | reg | none | pending | pending | pending | expected jellybean, register to add |
| BAS70-04, BZT52C15/C24, 1N4148W | Small diodes | ? | none | pending | pending | pending | expected jellybean, register to add |
| BZX384-C5V1 | Zener, SI | reg | MM3Z5V1T1G | pending | pending | pending | pending |
| PESD15VL1BA | ESD, SI x21 | ? | CDSOD323-T15C (ratings to confirm) | pending | pending | pending | pending |
| USBLC6-2SC6 | USB ESD, SI | reg | UMW USBLC6-2SC6 | pending | pending | pending | pending |
| 2036-09-B2LF | GDT, CTL, SI | ? | none | pending | pending | pending | single-source: reason needed until checked |
| XT60PW-M, XT30PW-M | DC input, RF | ? | none | pending | pending | pending | single-source: reason needed (Amass) |
| 83-798 | SO-239, RF x7 | reg (contact derating) | none | pending | pending | pending | single-source: reason needed |
| SMA 901-9215 | SMA, RF x3 | ? | candidate 132142 | pending | pending | pending | second source to add (confirm 132142) |
| USB4105-GF-A | USB-C, SI | ? | UJ20-C-H-G-SMT-1-P16-TR | pending | pending | pending | pending |
| MD-80SM | Mini-DIN 8, SI x3 | ? | KMDGX-8S-BS | pending | pending | pending | pending |
| ESP32-C3-DevKit-RUST-1 | MCU module, CTL, SI | n/a | none | pending | pending | pending | single-source: reason needed (dev kit) |

Passives (value and size groups, 1206 fuses, 1812 chokes, R/C): not checked in this fork.

## Counts (checked rows only, 13 parts on DigiKey)

- jellybean ok (register to add): 6 (BC857B, BCP53-16, BC847B, LM2901, LD1117S33, L7805CV)
- ok via named second source, not jellybean: 2 (IRFL9014, LP2985-33)
- second source to add: 2 (BSS138BK, PMV50EPEA)
- single-source: reason needed: 1 (TPS3823A-33)
- lifecycle risk: 1 (PCA9539D,118 obsolete)
- From the register only, DigiKey pending: about 25 lines.

## Register updates to make

1. PCA9539: record NXP PCA9539D,118 as Obsolete. Decide: (a) keep SOIC-24W and change to TI PCA9539DWR (DigiKey Direct); or (b) move to TSSOP-24 (NXP PCA9539PW,118 + TI TCA9539PWR, two makers). Recommended (a) for rev C: no footprint change. Replace "TCA9539" as second source, it has no SOIC-24W variant (to confirm).
2. BSS138BK: second source = onsemi 2V7002KT1G (Direct). Retire DMN61D8L-7 (Advanced Information). Check Rds(on) at the 3.3 V gate drive against the relay coil current.
3. PMV50EPEA: confirm AO3407A against limits, or add onsemi FDN360P after a limits check (Vds, Vgs(th), Rds at the drive voltage).
4. TPS3823A-33: zero stock, TI only. Write the reason, or name a pin-compatible supervisor with watchdog from another maker (to find; DigiKey list gives TI only). Check the A/non-A difference before using TPS3823-33.
5. Add second sources by full order code: BC857B-7-F, BC847B-7-F, ST BCP53-16, ST LM2901DT, onsemi MC7805CTG, onsemi NCP1117ST33T3G.
6. LD1117S33 alternatives: record output-capacitor stability per part (old LM1117 needs a tantalum ESR window; LD1117 and NCP1117 are ceramic-stable, to confirm).
7. TI two-die rule: check LM2901 (TI has legacy and new die) and LP2985 for a die change; record which die the datasheet covers.
8. Stock: BSS138BK, PMV50EPEA, BC857B, BCP53-16, LM2901DR (TI) and TPS3823A-33 show 0 at DigiKey NL today. Order from the second source or set a buy date.
9. Finish the DigiKey check for the pending rows (relay, optos, photorelays, TVS, connectors) when the bot gate clears, or with DigiKey API credentials.
10. Each underload record: confirm the 5 fields (parameter, operating value, rating, ratio, result) and the halogen status per part.

