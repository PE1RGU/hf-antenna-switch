# Shack interface: order sheet (JLCPCB)

Board: Shack Relay Matrix, shack interface rev A, layout p8e, netlist ../../unit/verify/si18.xml. Includes S-2 (SDA jumpers bridged, D-192), S-8 (159.6 mm wide, D-194) and S-11 (U4/U9 VSSOP-8).
Order: together with the other boards of the project (D-153). Parts: ordered by Prins, hand assembly.

## Files

- Gerbers and drill: `Shack_Relay_Matrix_rev_C_shack_interface_p8e.zip` (Fabrication Toolkit, M-123). 4 copper layers
  (L1 F.Cu, L2 In1.Cu, L3 In2.Cu, L4 B.Cu), mask, silk and paste both sides, Edge.Cuts, PTH and NPTH drill files.
- BOM for the parts order: `bom_hand_assembly.csv` (gen_bom.py, M-122). `bom.csv` and `positions.csv` are for JLC assembly only; not used.

## JLCPCB settings

| Setting | Value |
|---|---|
| Base material | FR-4 |
| Layers | 4 |
| Dimensions | 159.6 x 161.0 mm |
| Quantity | 5 (minimum) |
| Thickness | 1.6 mm |
| Layer stackup | JLC04161H-7628 (D-170). No controlled impedance |
| Outer / inner copper | 1 oz / 0.5 oz |
| Min via hole / diameter | 0.2 / 0.4 mm (two USB D- vias at J14, M-89; A-26) |
| Via covering | Tented |
| Surface finish | ENIG |
| Solder mask / silkscreen | Green / white |
| Mark on PCB | Remove mark (no order number on the board) |
| Remove order number, castellated holes, edge plating, gold fingers | No extras |

## Checks done (M-123)

- Drill files: PTH 0.2 mm x 2, 0.3 mm x 1375 (vias), 0.8 mm x 14 plus 9 slots, 0.6 mm slots x 6, 0.95 mm x 4, 1.0 mm x 99,
  1.1 mm x 3, 1.2 mm x 12, 2.7 mm x 2, 3.2 mm x 1; NPTH 0.65 mm x 2 and 3.25 mm x 2 (J14 pegs). Counts per tool match the
  board (read back by script).
- Gerber file functions L1 Top, L2 and L3 Inner, L4 Bottom; outline 159.6 x 161.0 mm.
- DRC (all severities, zones refilled) 0 copper violations, 0 unconnected. Known items: 12 starved thermals (each keeps at
  least one spoke), 4 hole clearances inside the J14 footprint (A-26), 4 footprint mismatch warnings (trimmed connector silk).

## At the order

- Upload the zip to the JLC quote form. The DFM result must accept the J14 fan-out and peg gaps (A-26). Read it before you pay.
- The 0.2 mm via hole can add a small charge. If JLC refuses it, the two vias must move to 0.3 mm (layout change).
