#!/usr/bin/env python3
"""Common photorelay footprint, 2.54 mm pitch, 4 leads (design log D-77, D-91, D-99). Run from this folder;
writes SOP-4_P2.54mm_PhotoRelay_LongPad.kicad_mod into shack-interface.pretty/ and ../../unit/controller-board/lib/controller-board.pretty/.
Parts on this footprint (datasheets in Datasheets/):
  CPC1117N   Littelfuse R12      span 6.096 +-0.102, foot 0.559 +-0.127, land 0.60 x 1.54, inner gap 3.85 (end of life, PDN EIC-1177; land kept)
  TLP4176G   Toshiba 2026-04-07  span 7.0 +-0.4, foot 0.6 +-0.3, body 4.4 +-0.25 (SamacSys 11-5H1S land: 0.8 x 1.2 at +-3.15)
  TLP176AM   Toshiba Rev 7.0A    span 7.0 +-0.4, foot 0.5 min, body 4.55 +0.25/-0.15; pins 1, 3, 4, 6 on positions 1, 2, 3, 4
  AQY212G3HS Panasonic ASCTB133E span 6.8 +-0.4, foot 0.5, body 4.4 +-0.2, land 0.8 x 1.2 on 6.0 centres
  AQY412S    Panasonic ASCTB140E GU SOP4 body 4.3 x 4.4 (span as the GU SOP4 of ASCTB133E, 6.8 +-0.4: to confirm), D-106
One long pad per lead covers the union of the lands (inner edge 1.90 = CPC1117N, outer edge 4.00 = Toshiba 3.75 plus room
for the iron). Positions as KiCad SOP-4: 1 and 2 on the left (top, bottom), 3 and 4 on the right (bottom, top).
3D: TLP4176G STEP from SamacSys, rotate z +90 (checked: pin 1 dimple at pad 1 in a KiCad STL export; SamacSys uses -90)."""
import uuid
_n = iter(range(1, 100000))   # stable uuids: same input, same file (Git-friendly)
U = lambda: str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pe1rgu.footprint.SOP-4_P2.54mm_PhotoRelay_LongPad.{next(_n)}"))
X_IN, X_OUT, W = 1.90, 4.00, 0.80
XC, PL = round((X_IN + X_OUT) / 2, 3), round(X_OUT - X_IN, 3)
def pad(n, x, y):
    return (f'\t(pad "{n}" smd roundrect (at {x} {y}) (size {PL} {W}) (layers "F.Cu" "F.Paste" "F.Mask") '
            f'(roundrect_rratio 0.25) (uuid "{U()}"))\n')
L = lambda a, b, layer, w: f'\t(fp_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{U()}"))\n'
rect = lambda x1, y1, x2, y2, ly, w: L((x1, y1), (x2, y1), ly, w) + L((x2, y1), (x2, y2), ly, w) + L((x2, y2), (x1, y2), ly, w) + L((x1, y2), (x1, y1), ly, w)
def prop(k, v, x, y, ly, hide=False):
    return (f'\t(property "{k}" "{v}" (at {x} {y} 0) (layer "{ly}"){" (hide yes)" if hide else ""} (uuid "{U()}")\n'
            '\t\t(effects (font (size 1 1) (thickness 0.15))))\n')
utext = lambda t, x, y, ly: f'\t(fp_text user "{t}" (at {x} {y} 0) (layer "{ly}") (uuid "{U()}") (effects (font (size 0.8 0.8) (thickness 0.12))))\n'
s = ('(footprint "SOP-4_P2.54mm_PhotoRelay_LongPad" (version 20240108) (generator "pe1rgu-gen_photorelay_fp") (layer "F.Cu")\n'
     '\t(descr "Photorelay 4 leads, 2.54 mm pitch, long pads for lead spans 6.0 to 7.4 mm: TLP4176G, AQY412S, TLP176AM (pins 1, 3, 4, 6), CPC1117N, '
     'AQY212G3HS. Pads 2.10 x 0.80, 1.90 to 4.00 mm from the centre. Hand soldering. D-99")\n'
     '\t(tags "photorelay PhotoMOS OptoMOS SOP4 2.54")\n')
s += prop("Reference", "REF**", 0, -3.6, "F.SilkS") + prop("Value", "SOP-4_P2.54mm_PhotoRelay_LongPad", 0, 3.6, "F.Fab")
s += prop("Footprint", "", 0, 0, "F.Fab", True) + prop("Datasheet", "", 0, 0, "F.Fab", True) + prop("Description", "", 0, 0, "F.Fab", True)
s += '\t(attr smd)\n'
for n, x, y in ((1, -XC, -1.27), (2, -XC, 1.27), (3, XC, 1.27), (4, XC, -1.27)):
    s += pad(n, x, y)
# fab: largest body (TLP176AM 4.8 across the rows, AQY212G3HS 4.5 along the pitch), pin 1 chamfer
s += L((-1.4, -2.25), (2.4, -2.25), "F.Fab", 0.1) + L((2.4, -2.25), (2.4, 2.25), "F.Fab", 0.1) + L((2.4, 2.25), (-2.4, 2.25), "F.Fab", 0.1)
s += L((-2.4, 2.25), (-2.4, -1.25), "F.Fab", 0.1) + L((-2.4, -1.25), (-1.4, -2.25), "F.Fab", 0.1)
s += utext("${REFERENCE}", 0, 0, "F.Fab")
# silk: body edges between the pad rows, pin 1 mark outside pad 1
s += L((-1.55, -2.37), (1.55, -2.37), "F.SilkS", 0.12) + L((-1.55, 2.37), (1.55, 2.37), "F.SilkS", 0.12)
s += L((-4.0, -2.0), (-1.9, -2.0), "F.SilkS", 0.12)
s += rect(-4.25, -2.65, 4.25, 2.65, "F.CrtYd", 0.05)
s += ('\t(model "${KIPRJMOD}/lib/3d/TLP4176G.stp"\n\t\t(offset (xyz 0 0 0))\n\t\t(scale (xyz 1 1 1))\n'
      '\t\t(rotate (xyz 0 0 90))\n\t)\n')     # +90: the -90 of the SamacSys 11-5H1S footprint puts the pin 1 dimple at pin 3 (STL check)
s += ')\n'
assert s.count('(') == s.count(')')
for d in ("shack-interface.pretty", "../../unit/controller-board/lib/controller-board.pretty"):   # written straight into the footprint libraries
    open(f"{d}/SOP-4_P2.54mm_PhotoRelay_LongPad.kicad_mod", "w").write(s)
print("written: pads", PL, "x", W, "centre", XC)
