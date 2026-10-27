# Backplane: JLCPCB order settings

Check every line in the JLC order form before you pay.

| Field | Value |
|---|---|
| Base material | FR-4 |
| Layers | 6 |
| PCB thickness | 1.6 mm |
| Outer copper weight | 1 oz |
| Inner copper weight | 0.5 oz |
| Impedance control | Yes |
| Layer stackup | **JLC06161H-7628A** (Special, finished thickness 1.59 mm ±10 %) |
| Mark on PCB | None (no order number, no UL mark) |

Do not accept JLC06161H-7628 (standard) or JLC06161H-3313E.
With 7628, the 50 ohm width on L1 is 0.39 mm; the board has 1.0 mm (about 27 ohm on 7628).

PCB remark (paste in the remark field):
"Stackup JLC06161H-7628A required. L1 RF trace 1.0 mm, gap 1.25 mm to copper, 50 ohm coplanar, ref L2. Do not remove text on silkscreen."

Cross-checks:
- Silkscreen back legend: "JLC06161H-7628A 1.6 mm 6 layers 1 oz outer".
- KiCad Board Setup stackup and title block: same code.
- Source: claude/decisions-2026-09-26-backplane.md (project), JLC calculator 2026-09-26: 0.9751 mm.
