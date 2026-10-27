# Controller board: order sheet (JLCPCB)

Board: Shack Relay Matrix rev C, controller board, layout c-s5, schematic c14 (netlist ../../verify/ctl14.xml).
Order: together with the other boards of the project (D-153). Parts: ordered by Prins, hand assembly.

## Files

- Gerbers and drill: `Shack_Relay_Matrix_rev_C_controller_board_c-s5.zip` (Fabrication Toolkit, M-67, M-68, M-72, M-73; c-s4 superseded: plain T-junctions). The c-s2 zip is in archive/controller-board-fab-c-s2-2026-10-22/. 4 copper layers
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

## Checks done (M-67)

- Drill files: PTH 0.3 mm x 269 (104 signal, 34 plane pad incl. 2 under U13, 131 stitching vias), 0.8 mm x 28 (DevKit sockets), 1.0 mm x 60
  (J1 8, J2 24, U1 to U3 24, U4 4), 1.2 mm x 12 (GDT), 3.2 mm x 1 (H1); NPTH 3.2 mm x 3 (H2 to H4), 3.25 mm x 2 (J1 pegs). No slots.
- Gerber file functions L1 Top, L2 and L3 Inner, L4 Bottom; outline 152.0 x 122.5 mm.
- DRC (all severities) 0 violations, 0 unconnected; ERC 0; logic and system checks pass.

## At the order

- Set the date code in gen_controller_pcb.py (art block, now `DC 2643`) to the ISO week of the order, run the generator,
  DRC and the Fabrication Toolkit again.
- Check the TE Neohm SMA-A pulse data if the TE MELFs are used (D-151).
