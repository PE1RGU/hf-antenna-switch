# Shack interface: order sheet (JLCPCB)

Board: Shack Relay Matrix, shack interface rev A, layout p8g (p8f with the USB fan-out without vias, D-206, M-137), netlist ../../unit/verify/si18.xml. Includes S-2 (SDA jumpers bridged, D-192), S-8 (159.6 mm wide, D-194) and S-11 (U4/U9 VSSOP-8).
Order: together with the other boards of the project (D-153). Assembly (M-136, Prins 2026-11-10): JLC places the SMD parts and the THT parts it has in stock; Prins solders the rest.

## Files

- Gerbers and drill: `Shack_Relay_Matrix_rev_C_shack_interface_p8g.zip` (Fabrication Toolkit, M-123, M-135, M-137; older zips in superseded/). 4 copper layers
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
| Min via hole / diameter | 0.3 / 0.6 mm: choose 0.3mm/(0.4/0.45mm) (p8g has no 0.2 mm via; the 0.2 mm class forces TG155 and a Kelvin test, about EUR 55 more) |
| Via covering | Plugged (JLC upgrades Tented to Plugged for free on 4 layers) |
| Surface finish | ENIG |
| Solder mask / silkscreen | Green / white |
| Mark on PCB | Remove mark (no order number on the board) |
| Remove order number, castellated holes, edge plating, gold fingers | No extras |

## Checks done (M-123; M-135 for p8f; M-137 for p8g: only the fan-out changed, no 0.2 mm hole)

- Drill files (p8g): PTH 0.3 mm x 1375 (vias), 0.8 mm x 14 plus 9 slots, 0.6 mm slots x 6, 0.95 mm x 4, 1.0 mm x 99,
  1.1 mm x 3, 1.2 mm x 12, 2.7 mm x 2, 3.2 mm x 1; NPTH 0.65 mm x 2 and 3.25 mm x 2 (J14 pegs). Counts per tool match the
  board (read back by script).
- Gerber file functions L1 Top, L2 and L3 Inner, L4 Bottom; outline 159.6 x 161.0 mm.
- DRC (all severities, zones refilled) 0 copper violations, 0 unconnected. Known items: 12 starved thermals (each keeps at
  least one spoke), 4 hole clearances inside the J14 footprint (A-26), 4 footprint mismatch warnings (trimmed connector silk).

## At the order

- Upload the zip to the JLC quote form. The DFM result must accept the J14 fan-out and peg gaps (A-26). Read it before you pay.

## JLC assembly (M-136)

- Product: Standard PCBA (THT parts are not in Economic PCBA), top side only (all parts are on the top side).
- Files: `jlc_assembly_bom.csv` (Comment, Designator, Footprint, LCSC Part #; plus the part placed and its BOM source) and
  `jlc_assembly_cpl.csv` (positions of the same 223 parts, from the toolkit, p8f). Upload these two, not `bom.csv` and `positions.csv`.
- JLC places 223 parts (48 lines): all SMD parts except U203, U303, U403, plus GD1 to GD4 (Littelfuse SL1003A090R), J1 (Molex 95501-2881),
  J3 (XT60PW-M), J15, the nine 1 x 3 headers and U205, U305, U405 (PC817X).
- By hand (Prins): A1 sockets and the DevKit, U203/U303/U403 (TX INH photorelays, no JLC stock), C1, J2, J6, J7 (JST XH), J11 to J13 (mini-DIN),
  U1 (L7805CV: leads 3 mm or less, insulating pad on the wall). Shunts and the cable parts stay as in `bom_hand_assembly.csv`.
- In the JLC parts review: check the rotation of every polarised part in the 3D preview (diodes, ICs, photorelays, J14, the XT60) and the
  stock at the moment of the order; the stock was read on 2026-11-10.
