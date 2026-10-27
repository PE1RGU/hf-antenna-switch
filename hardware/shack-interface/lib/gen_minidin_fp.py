#!/usr/bin/env python3
"""Mini-DIN 8 socket Same Sky MD-80SM, right angle, shielded, at the board edge (design log D-85, D-100). Run from this folder;
writes MiniDIN-8_SameSky_MD-80SM_Horizontal.kicad_mod into shack-interface.pretty/.
Source: MD-SM datasheet rev 1.09 (2024-09-12), "Recommended PCB Layout, Top View (Date Codes after 03/03/2022)":
  8 x d0.9 +0.1/0 holes; rows 8.5 (pins 5, 2, 1, 3) and 11.0 (pins 8, 7, 4, 6) behind the board edge;
  outer columns 6.8 apart, inner columns 2.6 apart (centred), pin 7 0.9 left of the centre line;
  earth terminal slot 2.2 +0.1 x 0.7 +0.1 at 4.7; shield tab slots 13.5 apart at 5.5 (slot size not given).
The SamacSys MD80SM footprint fits neither Same Sky layout and is not used. The SamacSys STEP has its tails on the
after-2022 rows, but the outer columns 6.5 apart (as the prior layout): drill 1.0 (top of the +0.1 tolerance) takes
both 6.5 and 6.8 (0.42 mm square tail, 0.15 mm offset). Shield tabs in the STEP: 0.45 x 1.7 mm.
3D: SamacSys STEP (inch), offset X -7.0, rotate X -90 (checked by STL export).
Origin: centre line at the board edge (front face flush with the edge); the body lies at -Y. Shield pads are pad 9."""
import uuid
_n = iter(range(1, 100000))   # stable uuids: same input, same file (Git-friendly)
U = lambda: str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pe1rgu.footprint.MiniDIN-8_SameSky_MD-80SM_Horizontal.{next(_n)}"))
DRILL, PAD = 1.0, 1.6
PINS = {5: (-3.4, -8.5), 2: (-1.3, -8.5), 1: (1.3, -8.5), 3: (3.4, -8.5),
        8: (-3.4, -11.0), 7: (-0.9, -11.0), 4: (1.3, -11.0), 6: (3.4, -11.0)}
def pin(n, x, y):
    shape = 'roundrect' if n == 1 else 'circle'
    rr = ' (roundrect_rratio 0.25)' if n == 1 else ''
    return f'\t(pad "{n}" thru_hole {shape} (at {x} {y}) (size {PAD} {PAD}) (drill {DRILL}) (layers "*.Cu" "*.Mask"){rr} (uuid "{U()}"))\n'
def slot(x, y, sx, sy, dx, dy):
    return f'\t(pad "9" thru_hole oval (at {x} {y}) (size {sx} {sy}) (drill oval {dx} {dy}) (layers "*.Cu" "*.Mask") (uuid "{U()}"))\n'
L = lambda a, b, layer, w, t="solid": f'\t(fp_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width {w}) (type {t})) (layer "{layer}") (uuid "{U()}"))\n'
rect = lambda x1, y1, x2, y2, ly, w: L((x1, y1), (x2, y1), ly, w) + L((x2, y1), (x2, y2), ly, w) + L((x2, y2), (x1, y2), ly, w) + L((x1, y2), (x1, y1), ly, w)
def prop(k, v, x, y, ly, hide=False):
    return (f'\t(property "{k}" "{v}" (at {x} {y} 0) (layer "{ly}"){" (hide yes)" if hide else ""} (uuid "{U()}")\n'
            '\t\t(effects (font (size 1 1) (thickness 0.15))))\n')
utext = lambda t, x, y, ly: f'\t(fp_text user "{t}" (at {x} {y} 0) (layer "{ly}") (uuid "{U()}") (effects (font (size 0.8 0.8) (thickness 0.12))))\n'
s = ('(footprint "MiniDIN-8_SameSky_MD-80SM_Horizontal" (version 20240108) (generator "pe1rgu-gen_minidin_fp") (layer "F.Cu")\n'
     '\t(descr "Mini-DIN 8 socket, right angle, shielded, Same Sky MD-80SM, layout for date codes after 2022-03-03 (MD-SM rev 1.09). '
     'Front face at the board edge (Y = 0). Drill 1.0. Shield and earth terminal = pad 9. D-85, D-100")\n'
     '\t(tags "mini-DIN 8 MD-80SM right angle shielded")\n')
s += prop("Reference", "REF**", 0, -15.0, "F.SilkS") + prop("Value", "MiniDIN-8_SameSky_MD-80SM_Horizontal", 0, 2.0, "F.Fab")
s += prop("Footprint", "", 0, 0, "F.Fab", True) + prop("Datasheet", "", 0, 0, "F.Fab", True) + prop("Description", "", 0, 0, "F.Fab", True)
s += '\t(attr through_hole)\n'
for n in sorted(PINS): s += pin(n, *PINS[n])
s += slot(0, -4.7, 3.0, 1.5, 2.3, 0.8)                         # earth terminal, slot 2.2 +0.1 x 0.7 +0.1
for x in (-6.75, 6.75): s += slot(x, -5.5, 1.5, 2.9, 0.8, 2.2)  # shield tabs (0.45 x 1.7 in the STEP)
# fab: body 14.0 x 13.4 behind the edge; board edge line
s += rect(-7.0, -13.4, 7.0, 0, "F.Fab", 0.1) + L((-9.0, 0), (9.0, 0), "F.Fab", 0.1, "dash")
s += utext("board edge", 0, 0.9, "F.Fab") + utext("${REFERENCE}", 0, -7.0, "F.Fab")
# silk: body sides and back, clear of the shield pads
s += L((-7.12, -13.52), (7.12, -13.52), "F.SilkS", 0.12)
s += L((-7.12, -13.52), (-7.12, -7.3), "F.SilkS", 0.12) + L((7.12, -13.52), (7.12, -7.3), "F.SilkS", 0.12)
s += L((-7.12, -3.7), (-7.12, -0.5), "F.SilkS", 0.12) + L((7.12, -3.7), (7.12, -0.5), "F.SilkS", 0.12)
s += L((0.6, -9.6), (2.0, -9.6), "F.SilkS", 0.12)                # pin 1 mark between the rows, under pad 1
# courtyard: body plus 0.25, front 0.5 past the edge
s += rect(-7.35, -13.65, 7.35, 0.5, "F.CrtYd", 0.05)
s += ('\t(model "${KIPRJMOD}/lib/3d/MD-80SM.stp"\n\t\t(offset (xyz -7.0 0 0))\n\t\t(scale (xyz 1 1 1))\n'
      '\t\t(rotate (xyz -90 0 0))\n\t)\n')     # checked by STL export: tails on the pads, body behind the edge
s += ')\n'
assert s.count('(') == s.count(')')
for d in ("shack-interface.pretty",):   # written straight into the footprint libraries
    open(f"{d}/MiniDIN-8_SameSky_MD-80SM_Horizontal.kicad_mod", "w").write(s)
print("written: pads", s.count('(pad '))
