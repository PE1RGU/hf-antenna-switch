# Shack interface end plates: order sheet (JLCPCB)

Plates: rear plate and front plate of the shack interface (D-179), generator `../gen_endplates.py` rev a8, made from the
main board p8e (connector positions). Front plate with the Waveshare 2inch display window (D-187) and the four WA-SMSI
spacer pads on the inside face (D-184, D-201). Order: together with the other boards of the project (D-153), as two
separate PCB orders.

## Files

- `front-panel.zip` and `rear-panel.zip` (Fabrication Toolkit, M-132): Gerbers and drill, 2 copper layers.
- `bom.csv`, `positions.csv`, `designators.csv`, `netlist.ipc` are written by the toolkit for JLC assembly. Not used.

## JLCPCB settings (each plate)

| Setting | Value |
|---|---|
| Base material | FR-4 |
| Layers | 2 |
| Dimensions | 165.0 x 51.13 mm (outline with all cut-outs in Edge.Cuts) |
| Quantity | 5 (minimum) |
| Thickness | 1.6 mm (A-28: stiffness under the KILL and RESET press) |
| Copper | 1 oz outer |
| Surface finish | ENIG (bare screw rings and the spacer pads) |
| Solder mask | Black, both sides |
| Silkscreen | White |
| Mark on PCB | Remove mark (the outside face carries the labels only) |
| Stencil | Not needed: the four spacers on the front plate are soldered by hand (A-29) |

## Checks done (M-132)

- DRC (all severities, zones refilled): 0 violations, 0 unconnected on both plates (2026-11-10).
- Read back from the zips by script: outline 165.0 x 51.13 mm; file functions Copper L1 Top, L2 Bot, mask, paste and
  legend both sides, Profile; PTH 3.7 mm x 4 (screw holes, CHASSIS); no NPTH (every opening is in Edge.Cuts).
- Front plate: B.Cu, B.Mask and B.Paste carry the four 6.0 mm spacer pads; B.Mask also opens the four screw rings.
- A new run of the generator on p8e gives the same plates (only the order of two items in the file changes).

## At the order

- Upload each zip to the JLC quote form and read the DFM result. The cut-outs are inside the outline; JLC routes them.
- Check in the viewer that the outside face (F side) shows the labels and no order number.
