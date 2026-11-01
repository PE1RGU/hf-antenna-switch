# Controller board: order sheet (JLCPCB)

Board: Shack Relay Matrix rev C, controller board, layout c-s7, schematic c16 (netlist ../../verify/ctl17.xml). Includes S-1 (FAULT to IO6, R66, D-191) and S-2 (JP11 bridged 1-2 for RUST-1, D-192).
Order: together with the other boards of the project (D-153). Parts: ordered by Prins, hand assembly.

## Files

- Gerbers and drill: `Shack_Relay_Matrix_rev_C_controller_board_c-s7.zip` (Fabrication Toolkit, M-67, M-113; c-s5 and older in backups/, superseded). The c-s2 zip is in archive/controller-board-fab-c-s2-2026-10-22/. 4 copper layers
  (L1 F.Cu, L2 In1.Cu, L3 In2.Cu, L4 B.Cu), mask, silk and paste both sides, Edge.Cuts, PTH and NPTH drill files.
- BOM for the parts order: `bom_hand_assembly.csv` (gen_bom.py). `bom.csv` and `positions.csv` are for JLC assembly only; not used.

## JLCPCB settings

| Setting | Value |
|---|---|
| Base material | FR-4 |
| Layers | 4 |
| Dimensions | 152.0 x 122.5 mm |
| Quantity | 5 (minimum) |
| Thickness | 1.6 mm |
| Layer stackup | JLC04161H-7628 (D-144). No controlled impedance on this board |
| Outer / inner copper | 1 oz / 0.5 oz |
| Min via hole / diameter | 0.3 / 0.6 mm |
| Via covering | Tented |
| Surface finish | ENIG |
| Solder mask / silkscreen | Green / white |
| Mark on PCB | Remove mark (no order number on the board) |
| Remove order number, castellated holes, edge plating, gold fingers | No extras |

## Checks done (M-67, M-113 for c-s7)

- Drill files: PTH 0.3 mm x 277 (vias: 126 GND, 151 other nets), 0.8 mm x 28 (U1 to U3 24, U4 4), 1.0 mm x 60
  (J1 8, A1 DevKit sockets 28, J2 24), 1.2 mm x 12 (GDT), 3.2 mm x 1 (H1); NPTH 3.2 mm x 3 (H2 to H4), 3.25 mm x 2 (J1 pegs). No slots.
  Counts per tool match the board (read back by script).
- Gerber file functions L1 Top, L2 and L3 Inner, L4 Bottom; outline 152.0 x 122.5 mm.
- DRC (all severities) 0 violations, 0 unconnected; ERC 0; logic and system checks pass.

## At the order

- Set the date code in gen_controller_pcb.py (art block, now `DC 2643`) to the ISO week of the order, run the generator,
  DRC and the Fabrication Toolkit again.
- Check the TE Neohm SMA-A pulse data if the TE MELFs are used (D-151).
