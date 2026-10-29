# Changelog

Newest first. Board revisions follow the design log IDs.

## 2026-10-29
- M-106: full SolidCraft render of the shack interface (housing, board p8b, plates a8, controls, 2inch display and frame) in hardware/shack-interface/case/render-full/.
- README: new section 'Inside the shack interface' with an open-case view (docs/images/shack-interface-open.png, SolidCraft snapshot with the cover hidden).

## 2026-10-28
- D-187, M-103, A-31: display changes to the Waveshare 2inch LCD Module (240x320 IPS, ST7789VW). Front plate a8 (window 41.4 x 31.2 mm, centred in the housing opening); new printed frame on the module PCB back (heat-set inserts, crush ribs) on four WA-SMSI 9774055151R spacers; DRC 0 on both plates. Main board layout p8 (M-104): front notch for the display stack (10.0 to 11.5 mm deep over 76 mm), routed again 155 of 155, DRC 0 copper and unconnected; board edge 1.64 mm from the display stack. p8b (M-105): the notch runs to the left edge; the small corner piece is removed; DRC unchanged. 1.9 inch frame and plate a7 kept in endplates/_archive/front-a7-1.9in/.

## 2026-10-27
- D-186, M-102: shack interface p7: J14 (USB-C) at the rear edge in a GND channel between the entry block and R1 (port pitch 35 to 32 mm, H1 to x 27); routed 155 of 155, DRC 0 copper and unconnected; rear plate a7 with the USB slot, front plate without. Supersedes D-185 and A-30.
- D-185, A-30: the Mac USB link moves to the rear plate (panel-mount USB-C extension with a 90 degree plug into the DevKit USB-C; main board unchanged). Front plate a6 without the USB slot. Rear cut-out follows after the part is measured.
- D-184, M-101, A-29: display frame (printed, on four Wurth WA-SMSI 9774060151R SMD spacers on the plate inside face; STEP and STL in endplates/display-frame/); front plate a5, module 4 mm to the right; frame 1.86 mm from the housing, 1.98 mm from the board parts; DRC 0.
- M-100: front plate 3D fit with the EAO 84 and C&K 8125 maker models, the Waveshare module and the p6 board STEP. D-183, front plate a4: KILL to u 144 and RESET to u 123 (KILL holder was 0.3 mm from the extrusion wall; now 1.37 mm). No other clash; RESET lugs 2.7 mm from the DevKit. DRC 0 on both plates.

## 2026-10-26
- D-181 (KILL: EAO 84-5340.0020, R75 2k2), D-182 (RESET: C&K 8125SHZBE; Dialight 558 LEDs), A-28 (plates stay 1.6 mm). Schematic a17-display (M-97): R1 to R3 panel LEDs removed, display header J15 on IO2/IO9 and the PCA9539. Layout p6 (M-98): headers moved, routed again, DRC 0. Front plate a3 (M-99): display left, KILL right.
- D-180: shack interface front plate gets a colour TFT (SPI on IO2/IO9, DC/RST/backlight on the PCA9539) in place of the R1 to R3 LEDs; SAFE and LATCHED LEDs stay in hardware.
- D-179, M-95: shack interface end plates as black PCBs with white silkscreen (gen_endplates.py): rear plate done (XT60, RJ45, three mini-DIN, labels), front plate with the USB-C slot; DRC 0; SolidCraft fit with the plates in place. A-27: end plate screws to confirm.
- D-178, M-94: shack interface housing with the cap on top for access to the 7805 and the jumpers; board parts side up in the 2nd slot from the closed bottom; SolidCraft fit check: no overlap.
- D-177 option A, layout p5 (M-93): panel connectors overhang the board edges by 2.0 mm and J14 sits on a 2.0 mm board tab, so every connector face is 0.3 mm from its end panel; routed again (156 of 156 nets), DRC 0 copper and silk findings; SolidCraft fit check repeated.
- M-92: shack interface fit in the Hammond 1455T1601 checked in SolidCraft with the Hammond STEP (A-25 confirmed): board in the 2nd slot from the bottom, no clash except the 7805 model leads (trim to 3 mm). J3 has the XT60 3D model now. Open: connector faces 1.85 to 2.55 mm behind the end panels (D-177).

## 2026-10-25
- Shack interface silkscreen p4 (M-91, D-175): zone frames with titles, jumper settings at the jumper pins and a jumper table per port on the back, connector and test point labels, art block, stackup legend; DRC 0 silk findings. D-173 planes and the GDT row accepted by Prins. Board signature D-176: the SAFE latch as an IEC D flip-flop with its truth table.
- Shack interface p3 (M-89, M-90, D-173): GDTs in one row behind J1 for a short surge path, planes with an RGND island per radio port and a CHASSIS strip and ring, USB-C fan-out as fixed copper, all 156 nets routed with the general router (new per-net keep-out keeps interface nets off the RGND islands), stitching after routing; DRC 0 copper violations, 0 unconnected. A-25 (board length, 7805 wall fit) and A-26 (JLC fine features) to confirm.
- M-88: shack interface p2 after a review of the whole board: DevKit turned along the front edge, entry and loop columns in J1 pin order, templates for the loop sources and the radio ports; airwire length 4485 to 4051 mm. Hardware skill v2.24: placement method in a board generator, placement check scripts.
- M-87: shack interface p1c, SAFE latch in two rows in signal-flow order, one decoupling capacitor per IC, LED and KILL resistors at their headers.
- M-86: shack interface p1b, no floating parts (pull-downs at their gate inputs, LED resistors at their headers, U5 in the expander row). Hardware skill v2.23.
- D-172: shack interface placement zones; zones go on the silkscreen. M-85: shack interface layout p1 (gen_shack_pcb.py), all parts placed in their zones, ports R2 and R3 copied from R1. Hardware skill v2.22 (function zones on the silkscreen).
- D-171: shack interface housing Hammond 1455T1601 (board about 160 x 156 mm); J1 RJ45 as the controller board, J3 XT60PW-M as the RF board. Schematic a16, netlist si15, ERC 0 (M-84).
- D-170: shack interface stackup 4 layers (JLC04161H-7628), as the controller board; changes D-131.
- D-169: controller board keeps the c-s5 routing; the general router is for the RF board and new boards.
- M-83: controller board regression with the general router. Two router fixes (exit from narrow own pads; entry corridor for wide tracks). After the fixes 59 of 59 nets and DRC 0, but 182 vias against 104 and less tidy power trunks; the c-s5 board stays as it is. D-168: RF board signature confirmed.
- RF board silkscreen p3 (M-82): port, supply and test point labels, HV warning on both sides, art block with the board signature (D-168, X/Y switch symbol, confirmed by Prins), stackup legend on the back. DRC 0 violations. Generator fix: board silk is now cleared before it is drawn again.
- D-166: 12 vias at 3.0 to 4.1 mm from a GND via accepted. D-167 and M-81: aggressor/victim check; detector lines now keep 1.0 mm from bias, coil and I2C copper (was 0.35 mm); RF board routed again, DRC 0 copper violations.
- C-40: narrowed CLAMP_SW and +3V3 tracks pass IPC-2152 (4.4 °C as DC upper bound, 0.6 °C as the real 10 ms pulse). M-80: final return-via check with all GND vias: 488 of 500 within 3 mm, 12 at 3.0 to 4.1 mm; router trials for the rest did not route all nets (board unchanged).

## 2026-10-24
- D-165: GND stitching with return vias placed by the router, edge fence and 5 mm grid. RF board p2d (M-79): 168 of 168 nets, 767 signal vias, 1418 new GND vias, DRC 0 copper violations and no warnings except silkscreen.
- D-164: router minimum segment 0.4 mm (no short jogs). RF board p2c4 (M-78): 168 of 168 nets, 815 vias, DRC 0 copper violations.
- D-163: router costs give right-angle branches; tracks keep clear of their own pads; automatic placement aligns parts on lines. RF board p2c3 (M-77): parts aligned, Q1/TP4/D2 on one line, 168 of 168 nets, 747 vias, DRC 0 copper violations.

## 2026-10-23
- D-162: RF board supports S1 to S6 each on their own net with a local bond option; schematic v12b, netlist rf14, ERC 0. RF board p2c routed again (M-76): 168 of 168 nets, 611 vias, DRC 0 copper violations, all connected except the internal relay NC pins.
- RF board p2c (M-75): all 161 logic and supply nets routed on L3/L4 (and L1 in the logic regions), 594 vias, DRC 0 copper violations, 0 right-angle bends. D-161: fixed fan-out vias for the TSSOP-24 parts U901 to U903 and U1001. Router: general version with router_cfg.json (rf-board/routing).
- D-160: CHASSIS plane stays under the Cat6 chokes (TI SLYP762 check). c-s4 zip archived. KiCadRoutingTools cloned to ~/Projects for review.
- D-159: T-junctions on tracks below 0.6 mm get 45-degree fillets; controller board c-s5 (M-73), Gerber zip c-s5; c-s3 zip archived.
- D-158: no 90-degree bends (45-degree chamfers), aligned parts and straight pad entries. RF board p2b and controller board c-s4 (M-72): 0 right-angle bends, DRC clean; controller Gerber zip c-s4.
- RF board layout p2a (M-71): RF rows, columns, feeds, EXP and antenna ports, 1787 GND return and fence vias, GND pours; DRC copper clean; D-157 return vias as close as the 2.0 mm gap allows; M-70 clearance mechanism (kicad-cli does not read .kicad_dru).
- D-156: RF board layer use option A: L3 and L4 routing layers at right angles, L2 and L5 GND (stackup sketch in Claude outputs/rf-board-stackup-options.png).

## 2026-10-22
- RF board schematic v12a (M-69): function frames and text clean-up; netlist rf13 (same connectivity as rf12), ERC 0.
- D-155: U14 stays SOT-23-6, second source Nexperia 74LVC1G27GV (SOT457). onsemi NC7SZ27P6X is discontinued (Rev. 4). Nexperia 74LVC2G74 and 74LVC1G27 datasheets filed; c-s2 Gerber zip archived.
- D-154: U13 in VSSOP-8 (TI SN74LVC1G74DCUR, second source Nexperia 74LVC2G74DC). Schematic c14, netlist ctl14, layout c-s3 with fixed U13 fan-out (M-68): DRC 0, checks pass, new Gerber zip c-s3. Router: start tree only from locked copper on the first pad. Finding: Nexperia 74LVC1G27GV (SOT457) fits the U14 SOT-23-6 land.
- Controller board order-readiness (M-67): JLC files with the Fabrication Toolkit, hand-assembly BOM (gen_bom.py), order sheet production/ORDER-controller-board.md. VO2611 order code corrected to DIP-8; U13/U14 second sources corrected (package). D-153: all boards in one order.
- D-152: board signature on every board (main function as IEC logic symbol with truth table); hardware skill v2.8.
- Controller board schematic c13 (M-66): dashed frames with titles per function, overlapping text and wires over symbols removed; netlist ctl13 (same connectivity). MAX823 datasheet filed.
- D-150: halogen is not a selection criterion in this project. D-151: Murata DLW43SH and Coilcraft 1812CAN fit the new choke land; MELF second source TE Neohm SMA-A.
- D-149: Cat6 chokes on an own TDK ACT45B footprint, turned 90 degrees (correct common-mode sense, no crossing); GDT second source Littelfuse SL1003A090R-001 on the same footprint. Schematic c12, netlist ctl12, layout c-s2 (M-65): ERC 0, all checks pass, DRC 0, 104 vias.
- R-17: surge level of the Cat6 entry 4 kV 10/700 us line to earth (Prins). C-39: GDT, copper, 47R, 220R, SMBJ15CA and VO2611 LED pass at that level.
- M-64: Cat6 choke check against the TDK ACT45B drawing: P and N enter at opposite ends (common-mode filter does not work), footprint does not match the TDK land; decision open.
- Datasheets filed: TDK ACT45B, Vishay MMU/MMA/MMB, Diodes APX823.
- Controller board open points: C-37 3V3 load and LDO heat (79 mA worst case), C-38 DevKit buck held off, D-148 supervisor second sources proposed (MAX823SEUK+T, APX823-29W5G-7). Remaining points listed in controller-board.md section 7.

## 2026-10-21
- D-147: Cat6 wires on the controller board 1.016 mm (surge copper C-36); routing e1 (M-63), DRC 0 violations. Router: clearance margin = grid pitch, thermal ring around CHASSIS pads.
- Controller board silkscreen c-s1 (M-62): labels, art block with the safety gate as an IEC NOR, stackup legend on the back; DRC 0 violations. C-36: surge copper check of the Cat6 entry.
- hardware-design-rules skill v2.5: routing style, track widths, CHASSIS plane, grid router scripts.
- D-146: controller board power stays routed (4 layers, no power plane).
- D-145: CHASSIS plane on the loop side of the controller board (L1, L2, L4), stitching vias along all plane edges; layout c-r4 routed again (M-61): 59 nets, 0 unconnected, 124 vias. Router r4: exact vertical and horizontal segments; generator option --no-routes.
- D-144: controller board to 4 layers (JLC04161H-7628): L1 vertical, L2 GND, L3 horizontal, L4 GND; routing style and width series 0.127/0.254/0.508 mm. Layout c-r3 routed by grid_router.py r3 (M-60): all 60 nets, 0 unconnected, 143 vias. Current check C-35.
- D-143: controller board routed by an own grid router (routing/grid_router.py); layout c-r2, all nets routed, B.Cu plane whole with short jumps only (M-59). Freerouting trials M-58.

## 2026-10-20
- Controller board placement c-p6 (M-57): remaining parts on a grid, ICs in rows at rotation 0, passives upright on the pin they serve.
- Controller board placement c-p5 (M-56): one template per Cat6 pair in four columns, J1 centred, test points in one row under J2, safety gate in one row under the DevKit.
- D-142: isolation barrier on the controller board, loop side without GND plane, optos on the barrier; layout c-p4 with GND zones on B.Cu and F.Cu.
- D-141: controller board test points TP5 to TP9 (SCL, SDA, EXP_INT, RLY_EN, TX_ANY) for the assembled unit; schematic c11, netlist ctl11, layout c-p3 (M-55).
- C-27 build values: 20 mm standoffs between the boards; DevKit top 52.15 mm, 5.85 mm under the lid.
- D-140: DevKit stays on the 8.5 mm Sullins sockets (D-95); low-profile Samtec SLW set aside.
- RF board layout p1i: the controller board STEP is shown on the RF board as a 3D reference (CTL3D, 20 mm standoff, M-54).
- D-139: J2 is a Samtec ESQ-112-33-G-D elevated socket (second source ESW-112-33-G-D); pin engagement 5.05 mm on J14 (M-53). Controller schematic c10, netlist ctl10, layout c-p2.
- Controller board layout c-p1 (gen_controller_pcb.py) and the first 3D fit check of the stack (M-52): all parts fit the case; J2 does not reach J14 (2.57 mm gap, A-23).
- GDT 3D model: Bourns STEP 2036-XX-B2 fitted (M-51).

## 2026-10-19
- D-138: RJ45 LINK jack J1 is Wurth 615008137121, second source Molex 95501-2881, on one common footprint.
- Controller board schematic c9: footprints for J1 (RJ45, D-138) and GD1 to GD4 (Bourns 2036-B2) with 3D models; netlist ctl9 (M-51).
- RT1 3D model: TE STEP RTD14012F fitted (M-50). Controller board outline: about 150 x 118 mm on S1, S2, S4, S5 (D-137).
- RF board 3D check (M-50): XT60/XT30 vendor models fitted; RT1 uses the RT2 model of the KiCad library (body size the same); SO-239 and SMA models open.
- No GDT footprint at the antenna ports (D-114, supersedes the D-07 footprint). RF board v11d, netlist rf12; layout p1h with the A4 bleed placed (M-49).
- RF board layout p1g: placement by function (D-136, M-48): edge band 3.5 mm free, decoupling and pull-ups at the IC pins, J14 filter at J14, bias-T blocks per port; C101 to C301 moved off the TX row lines. DRC: no clearance or courtyard errors.
- General rule: halogen-free unless impossible or impractical (D-135; DR-02 updated). D-118 (standard FR-4 for the 6-layer RF board) to review.
- BSS138BK second source: Diotec MMFTN138K (D-134; ROHM BSS138BK has pins S-G-D, not a drop-in). RF board v11c, controller c8, shack interface a15 (BOM text only); netlists rf11, ctl8, si14; 52 + 52 checks pass. RF layout p1f: page A3 (M-47).
- PCA9539 to TSSOP-24 with three makers (D-133, supersedes D-126): NXP/Nexperia PCA9539PW, TI TCA9539PWR, Diodes PI4IOE5V9539LEX. RF board v11b, shack interface a14, RF layout p1e. ERC 0/0, DRC no errors, 52 + 52 checks pass (M-46).
- Review decisions drawn (Prins, 2026-10-19). RF board v11a: J14 filter sheet (D-122), pull-down arrays on the 14 spare PCA9539 pins (D-121), test points and +3V3 link (D-120), bulk C6 C7 (D-129), 1 uF decoupling (D-127), supports S1 to S6 plated with bond options (D-132), PCA9539DWR (D-126); layout p1d, DRC no errors (M-42, M-43). Controller c7: Cat6 chokes and Y-cap footprints (D-130), watchdog link R64 (D-123), test points, 1 uF decoupling, 2-layer stackup text (D-131) (M-44). Shack interface a13: Cat6 chokes, rail links, 24 test points, 1 uF decoupling, PCA9539DWR (M-45). ERC 0/0 on all boards; verify_logic.py 52 checks and verify_system.py 52 checks pass (rf10.xml, ctl7.xml, si13.xml).
- Design review against hardware-design-rules v2.2 (M-41, docs/reviews/2026-10-19-review-hdr-v2.2.md). Rules recorded: RF return vias, pour and edge fence (D-119), test access on all boards (D-120), filters at J14 and the EXP ribbon (D-122), watchdog links (D-123), TVS and 7805 exceptions (D-124). Proposed: pull-downs on 14 unused PCA9539 IO (D-121). C-14 recomputed (7.1 mA, ratio 0.05); C-34 shack interface at 11 to 15 V. Register: DigiKey check of 13 parts (PCA9539D,118 obsolete; BSS138BK second source to 2V7002KT1G). Generators: dead RF-board C4 default removed (D-125, sheets unchanged). Open decisions listed in section 7 of each board document.
- RF board stackup 6-layer JLC06161H-7628A (D-115, supersedes D-11): rows on L1, columns on L6, GND on L2, L4 and L5, coil lines and logic on L3. RF line W 0.975 mm (JLC calculator), gap 2.0 mm (D-116, C-30, C-31); fence 3.05 mm, band about 7.1 mm (C-33); inner antipads 0.5 mm (D-117). JLC 4-layer checked and rejected (outer prepreg 0.21 mm, line 0.46 mm, about 48 °C rise). Updated: design-log, docs/design/rf-board.md, requirements PR-03, architecture, schematic title blocks, gen_rfboard_pcb.py p1c-6layer (6 copper layers, physical stackup written into the board, ENIG, RF netclass 0.975 / 2.0 mm); run with the KiCad 10.0.5 Python, DRC unchanged against p1b (M-40). JLC quote 187.34 USD for 5 boards; halogen-free laminate not offered for 6 layers; halogen policy set aside for this board (D-118, Prins).
- RF board layout p1b: coil drivers in the logic zone (D-112), board corners R 5 mm (D-113), all small parts in their zones except the A4 bleed (D-114 open). DRC: no clearance or courtyard violations (M-39).
- RF board layout p1: rf-board.kicad_pcb with outline, supports, netclasses and the large parts placed (gen_rfboard_pcb.py, M-38). DRC 0 violations after D-111 (via size in the strap lands, SMA GND hole, EXP relays at x 8, 1812 for the detector tap and the bias choke). Schematic v10m, netlist rf9.xml.
- EXP SMA: Amphenol RF 901-9215 (second source 132142) in a 2 mm pocket milled from the outside, wall 4 mm there (D-110, A-21). New footprints by hardware/unit/rf-board/gen_rf_fp.py; RF board v10l: every part has a footprint, ERC 0/0, 37 checks pass with rf8.xml (M-37).
- Column link R402 to R702: THT wire link; DC block 1812, GDT THT and bias choke 1210 footprints, all not fitted (D-109).
- SMA drawings filed (Amphenol RF 132142, 901-9215). The contact reaches only 5.07 mm behind the flange, so it does not pass a 6 mm wall (A-21 open).

## 2026-10-10
- EXP SMA: bulkhead jack with a 4-hole flange in the left wall, strap to the board edge (D-108, A-21). case.md: board edge is 4 mm from the inner side walls and 3 mm from the inner top wall (was "10 mm").
- Halogen policy applies to this design (D-107, supersedes D-42). DR-02 refers to D-107. Halogen checks closed under D-42 are open again.
- Diagrams embedded in the documents: L1 to L3, T1 to T4, F1, F2 in docs/design/controller-board.md and shack-interface.md, L1 in docs/architecture.md, the placement study in rf-board.md and the case sketch in case.md.
- Design log section 1: underload factors (R-15) and critical parts, not applicable (R-16). docs/requirements.md DR-01 refers to R-15.

## 2026-10-07
- Design documents drafted for all boards and the case: docs/design/rf-board.md, controller-board.md, case.md, shack-interface.md (function, circuit, part choice and derating, calculations, layout rules, verification, open items). Found on the way: C-14 still counts the PCA9615 load that D-53 removed (to recompute).
- AQY41xS catalog ASCTB140E 202601 filed: AQY412S lead span 6.8 +-0.4 and pin 1 = LED anode confirmed (D-106 closed).
- TX INH photorelay: TLP4176G main part, Panasonic AQY412S second source; CPC1117N is at end of life (Littelfuse PDN EIC-1177). Shack interface a12, D-106, M-36.
- Part checks: PCA9539 inputs take up to 5.5 V (VIH max; 6 V absolute); a 5 V push-pull band output would sit above the 0.7 factor, so the FT-710 band output type (A-18) decides. USB-C cut-out waits for the housing choice.

## 2026-10-06
- SO-239 strap footprints (D-105): generator hardware/unit/rf-board/gen_so239_fp.py; RF board v10k. ERC now 0/0 on all three boards (M-35).
- SR-01 H2: RF on the receive-only column A2 opens the SAFE loop (D-104). RF board v10j: A2 detector to J14 pin 17. Controller c6-rf-a2: U16 AND in the READY drive, R36 pull-down. Checks: 37 and 46 pass (M-34). Diagrams L1, L2 updated. A-20 (detector against antenna coupling) to confirm on the bench.
- SR-01 H1: the TX relays on the receive-only column A2 and their drivers are not fitted (D-103). RF board generator v10i; verify_logic.py checks it (36 checks, M-33). H2 is open.
- Repository structure and document set prepared for publication: README, requirements, architecture, design and test skeletons.
- Moved to archive: architecture v0.1 and the rev A block-diagram folder.
- Licence: CERN-OHL-S-2.0 for hardware and documentation, MIT for the scripts.
- Vendor libraries and KiCad generated output excluded from the repository (.gitignore, hardware/THIRD-PARTY.md).
- RF board supports: six M3 standoffs at free spots of the relay field plus the seven SO-239 GND bosses; a true 3 x 3 grid does not fit (D-102, C-29, M-32).
- Shack interface: symbol folder hardware/shack-interface/_sym/ added (49 symbols from the KiCad 10 libraries), so gen_shack_sch.py runs from the repository; output unchanged except the UUIDs.
- Rev C summary (Project doc claude/architecture-rev-c.md) carried into docs/design/rf-board.md, controller-board.md and case.md; the summary itself moved to archive/architecture-rev-c-summary-2026-10-06.md.
- Generators: stable UUIDs (uuid5). Symbols and pins are keyed on reference, unit and pin; other items on file and order. The same input now gives the same files; the schematics were regenerated once with the new UUIDs (content unchanged, ERC unchanged).
- Footprint generators write straight into lib/shack-interface.pretty/ and, for the DevKit socket and the photorelay, also into the controller board library.
- verify_logic.py and verify_system.py use the current netlists (rf5.xml, ctl5.xml, si.xml) when no arguments are given.
- tools/README.md: list of all generators and verification scripts with their folders and commands. The scripts stay next to their boards.
- Design log section 7: sources moved to the current repository paths. A-10: the TX interlock for receive-only antennas (SR-01) is open before layout.

## 2026-10-05
- Controller board c5-ready: READY switch U6 and READY gate U15 in the SAFE loop (D-101). R52, R53 not fitted (D-63).
- Shack interface rev A: all sheets drawn, ERC clean (M-13 to M-27).
- Logic, timing and flow diagrams L1 to L3, T1 to T4, F1, F2 (M-31).

## 2026-09-29
- SAFE loop (D-62) and per-radio TX permit with handshake (D-63).

## 2026-09-27
- Architecture rev C: one flat RF board per unit in a milled aluminium case (D-01). Card cage and backplane (rev A/B) archived.

## 2026-09-09
- Architecture v0.1 (now archive/architecture-v0.1-2026-09-09.md).
