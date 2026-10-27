#!/usr/bin/env python3
"""SO-239 strap land for the Amphenol RF 83-798 in the case bottom wall (design log D-10, D-15, D-102, D-105). Run from this
folder; writes SO239_83-798_StrapPad_BossRight.kicad_mod and SO239_83-798_StrapPad_BossLeft.kicad_mod into rf-board.pretty/.
The connector sits in the case wall; the board carries only the strap land and the M3 hole to the milled GND boss.
Origin: connector axis on the board edge (board edge = Y 0, board inside = -Y; place with rotation 0 at the bottom edge).
Pad 1 (RF): strap land 3.5 x 4.0 mm on F.Cu and B.Cu, 0.5 mm from the edge, joined by 3 vias (drill 0.6, pad 1.0, pitch 1.2: hole gap 0.6 mm, D-111) so the column or
feed can arrive on either layer; pad clearance 2.0 mm = RF gap (D-12). The copper strap 3 x 0.3 mm from the solder cup
lands on the F.Cu pad between the edge and the vias (the vias sit at the inner end, so solder does not wick into them): the cup centre is about 1.5 mm above the top surface, its tip about 1.4 mm short of the edge (D-15).
Pad 2 (GND): plated M3 hole to the GND boss, 14 mm beside the axis, 5 mm from the edge (D-102), solid zone connection:
it carries the RF return current (2.45 A rms at SWR 3, C-01), so thermal spokes are not used (hardware rules section 6).
BossRight: hole at +14 mm (R1 to R3, A1 to A3). BossLeft: hole at -14 mm (A4, near the right board edge).
No 3D model: the connector body is in the case wall, not on the board."""
import uuid

def build(name, side):
    n = iter(range(1, 1000))
    U = lambda: str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pe1rgu.footprint.{name}.{next(n)}"))   # stable uuids
    L = lambda a, b, ly, w, t="solid": (f'\t(fp_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width {w}) (type {t})) '
                                        f'(layer "{ly}") (uuid "{U()}"))\n')
    rect = lambda x1, y1, x2, y2, ly, w: L((x1, y1), (x2, y1), ly, w) + L((x2, y1), (x2, y2), ly, w) + L((x2, y2), (x1, y2), ly, w) + L((x1, y2), (x1, y1), ly, w)
    prop = lambda k, v, x, y, ly, hide=False: (f'\t(property "{k}" "{v}" (at {x} {y} 0) (layer "{ly}"){" (hide yes)" if hide else ""} '
                                               f'(uuid "{U()}")\n\t\t(effects (font (size 1 1) (thickness 0.15))))\n')
    ut = lambda t, x, y, ly: (f'\t(fp_text user "{t}" (at {x} {y} 0) (layer "{ly}") (uuid "{U()}") '
                              f'(effects (font (size 0.8 0.8) (thickness 0.12))))\n')
    PW, PL, EDGE = 3.5, 4.0, 0.5                              # strap land, distance to the board edge
    PY = -(EDGE + PL / 2)
    GX, GY = 14.0 * side, -5.0                                # GND boss hole
    s = (f'(footprint "{name}" (version 20240108) (generator "pe1rgu-gen_so239_fp") (layer "F.Cu")\n'
         f'\t(descr "Strap land for an Amphenol RF 83-798 SO-239 in the case wall: RF pad on both layers with 3 vias, '
         f'2.0 mm RF clearance; plated M3 hole to the GND boss at {GX:+.0f} mm (solid connection). Origin = axis on the board edge. D-105")\n'
         '\t(tags "SO-239 UHF 83-798 strap case wall")\n')
    s += prop("Reference", "REF**", 0, -7.5, "F.SilkS") + prop("Value", name, 0, 1.5, "F.Fab")
    s += prop("Footprint", "", 0, 0, "F.Fab", True) + prop("Datasheet", "", 0, 0, "F.Fab", True) + prop("Description", "", 0, 0, "F.Fab", True)
    s += '\t(attr through_hole)\n'
    for ly in ("F", "B"):
        s += (f'\t(pad "1" smd rect (at 0 {PY}) (size {PW} {PL}) (layers "{ly}.Cu" "{ly}.Mask") (clearance 2.0) (uuid "{U()}"))\n')
    for x in (-1.2, 0.0, 1.2):
        s += (f'\t(pad "1" thru_hole circle (at {x} {round(PY - 1.3, 2)}) (size 1.0 1.0) (drill 0.6) (layers "*.Cu") '
              f'(clearance 2.0) (uuid "{U()}"))\n')
    s += (f'\t(pad "2" thru_hole circle (at {GX} {GY}) (size 6.0 6.0) (drill 3.2) (layers "*.Cu" "*.Mask") (zone_connect 2) '
          f'(uuid "{U()}"))\n')
    # fab: board edge, connector outline seen through the wall (flange 25.4 square outside, rear body 15.75 inside the wall)
    s += L((-14.0 if side > 0 else -18.0, 0), (18.0 if side > 0 else 14.0, 0), "F.Fab", 0.1, "dash") + ut("board edge", 0, 0.9, "F.Fab")
    s += rect(-7.875, 0.0, 7.875, 6.0, "F.Fab", 0.1) + ut("83-798 in the wall", 0, 3.0, "F.Fab")
    s += rect(-1.5, -1.4, 1.5, -3.0, "F.Fab", 0.08) + ut("strap", 0, -5.6, "F.Fab")
    # silk: outline of the land area, clear of the pads
    s += L((-2.6, -0.3), (-2.6, -5.2), "F.SilkS", 0.12) + L((2.6, -0.3), (2.6, -5.2), "F.SilkS", 0.12)
    # courtyard: RF land with its 2.0 mm clearance, and the GND pad
    s += rect(-3.85, 0.0, 3.85, -6.6, "F.CrtYd", 0.05)
    s += rect(GX - 3.25, GY + 3.25, GX + 3.25, GY - 3.25, "F.CrtYd", 0.05)
    s += ')\n'
    assert s.count('(') == s.count(')')
    open(f"rf-board.pretty/{name}.kicad_mod", "w").write(s)
    return s.count("(pad ")

for name, side in (("SO239_83-798_StrapPad_BossRight", +1), ("SO239_83-798_StrapPad_BossLeft", -1)):
    print("written", name, "pads", build(name, side))
