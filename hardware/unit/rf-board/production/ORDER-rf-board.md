# RF board: order sheet (JLCPCB)

Board: Shack Relay Matrix rev C, RF board, layout p3-c1206, netlist ../../verify/rf16.xml. Includes B-1 and B-2 (D-189), S-3 drain copper (D-193) and the 1206 detector tap land (D-202).
Order: together with the other boards of the project (D-153). Parts: ordered by Prins, hand assembly.

## Files

- Gerbers and drill: `Shack_Relay_Matrix_rev_C_RF_board_p3-c1206.zip` (Fabrication Toolkit, M-123). 6 copper layers
  (L1 F.Cu, L2 In1.Cu to L5 In4.Cu, L6 B.Cu), mask, silk and paste both sides, Edge.Cuts, PTH and NPTH drill files.
- BOM for the parts order: `bom_hand_assembly.csv` (gen_bom.py, M-122). `bom.csv` and `positions.csv` are for JLC assembly only; not used.

## JLCPCB settings

| Setting | Value |
|---|---|
| Base material | FR-4 |
| Layers | 6 |
| Dimensions | 268.0 x 230.0 mm |
| Quantity | 5 (minimum) |
| Thickness | 1.6 mm |
| Layer stackup | JLC06161H-7628A (D-115). The 50 Ω width W 0.975 / gap 2.0 mm comes from the JLC calculator for this stackup (D-116, C-30). Impedance control not needed at HF |
| Outer / inner copper | 1 oz / 0.5 oz |
| Min via hole / diameter | 0.3 / 0.6 mm |
| Via covering | Tented |
| Surface finish | ENIG |
| Solder mask / silkscreen | Green / white |
| Mark on PCB | Remove mark (no order number on the board) |
| Remove order number, castellated holes, edge plating, gold fingers | No extras |

## Checks done (M-123)

- Drill files: PTH 0.3 mm x 4196 (vias), 0.6 mm x 30 plus 4 slots, 0.8 mm x 20, 1.0 mm x 34, 1.3 mm x 296 (relays),
  1.9 mm x 2, 2.7 mm x 4, 3.2 mm x 17 (plated supports, D-102). No NPTH. Counts per tool match the board (read back by script).
- Gerber file functions L1 Top, L2 to L5 Inner, L6 Bottom; outline 268.0 x 230.0 mm.
- DRC (all severities, zones refilled) 0 violations; 30 unconnected items, all relay pad-12 pairs joined inside the relay (known); ERC 0.

## At the order

- Set the date code in the art block (now `DC 2643`) to the ISO week of the order. Change the text on the board in place, not by
  a generator run (see M-123), then DRC and the Fabrication Toolkit again.
- Upload the zip to the JLC quote form and read the DFM result before you pay.
