# RF isolation test piece: KiCad projects

Status 2026-09-26: third layout (0.5 mm CPWG gap). DRC 0 violations on both boards (kicad-cli 10.0.5, zones refilled). Stackup JLC04161H-2116 entered in both boards (core 1.265 mm calculated from 1.6 mm total, to check against JLC).

| Project | Connector | Board |
|---|---|---|
| `rf-iso-backplane/` | J1 HARTING 09 03 296 6824, female, straight (footprint DIN41612_C_3x32_Female_Vertical_THT) | 60 × 107 mm, 4 layers |
| `rf-iso-card/` | J1 HARTING 09 03 196 6921, male, angled (footprint DIN41612_C_3x32_Male_Horizontal_THT) | 100 × 50 mm, 4 layers |

Both: SMA edge connectors J2 to J4 (Molex 73251-1153 footprint), nets S1 to S3, all other contacts GND.

Pin-out (row b): b1+b2 = S1, b3 = empty (no-connect), b4+b5 = S2, b6 = GND, b7+b8 = S3.
- S1 to S2: version A, empty position between the groups.
- S2 to S3: version B, ground contact between the groups.

Layout:
- Fab: JLCPCB, 4 layers, 1.6 mm. Proposed stackup JLC04161H-2116 (prepreg 0.1164 mm, Er 4.16), halogen-free laminate if JLCPCB offers it for this stackup.
- Layers: L1 signal (RF), L2 GND, L3 GND on the coupons (signal layer on real boards), L4 GND.
- RF traces on F.Cu, 0.254 mm, 45° bends, coplanar with ground, 0.5 mm gap to the pour (F.Cu zone clearance 0.5 mm; inner and bottom zones 0.25 mm). About 50 Ω on 2116 (own calculation, matches the KiCad TransLine calculator). With a 0.25 mm gap it would be about 48 Ω.
- Via fence along each RF trace: 0.6/0.3 mm vias at 1.0 mm offset from the trace centre, 1.27 mm pitch.
- GND stitching vias on a 2.5 mm grid elsewhere. No vias in the connector pin field or in the SMA footprint areas.
- SMA ground pads: thermal relief (zone default, gap 0.5 mm, spokes 0.5 mm) for hand soldering. At 1 to 54 MHz a spoke adds about 1 nH (about 0.2 Ω at 30 MHz). The small 0.95 × 0.46 mm tabs of the footprint have no zone connection; they connect through the mechanical leg pad.
- On the card coupon, the board edge follows the footprint's edge line (5.3 mm in front of row a).

Open before fabrication:
1. Confirm the impedance and the core thickness with the JLCPCB calculator.
2. Confirm halogen-free laminate availability for this stackup in the JLCPCB quote form.
3. Confirm the SMA part and the Molex footprint edge position against the datasheet; add to the datasheet register.
4. Done 2026-09-26: title blocks (PE1RGU), schematic note, silkscreen port and version labels, XOR art, back-side stackup legend with the JLCJLCJLCJLC order-number position. Backups `*.bak-polish`.

Backups: first layout `*.kicad_pcb.bak-2026-09-26`; before the stackup `*.bak-stackup`; before the 0.5 mm gap `*.bak-gap05`; before the thermal-relief change `*.bak-thermal`.

Fix 2026-09-26: on the backplane coupon the B.Cu, In1.Cu and In2.Cu zone outlines were still at the old board position, off the board. The planes on those layers were stale fills. The outlines now follow the board edge.

`*.kicad_dru` files are empty (version line only) and can be deleted.
