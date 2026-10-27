#!/usr/bin/env python3
"""ESP32-C3 Rust board (DevKit-RUST-1 Rev 1.2a, DevKit-RUST-2) socket footprint, shared by the shack interface board and the
box controller board (design log D-93, D-95). Run from this folder; writes ESP32-C3-DevKit-RUST_Socket.kicad_mod into shack-interface.pretty/ and ../../unit/controller-board/lib/controller-board.pretty/.
Copy the output unchanged to hardware/unit/controller-board/lib/controller-board.pretty/.
Geometry: esp-rs Rust_Board and SnapEDA MODULE_ESP32-C3-DEVKIT-RUST-1 (they agree). Pad numbers as esp-rs (A1 symbol).
Sockets: Sullins PPPC161LFBN-RC (1x16) and PPPC121LFBN-RC (1x12), gold flash, 8.50 mm. No standoff holes (Prins).
DevKit stack: 8.50 mm socket + 2.54 mm male header body; pin 6.01 mm against 6.00 mm insertion depth: 11.05 mm (Prins, measured)."""
import uuid
_n = iter(range(1, 100000))   # stable uuids: same input, same file (Git-friendly)
U = lambda: str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pe1rgu.footprint.ESP32-C3-DevKit-RUST_Socket.{next(_n)}"))
STACK = 11.05
def pad(n, x, y, shape):
    rr = ' (roundrect_rratio 0.15)' if shape == 'roundrect' else ''
    return f'\t(pad "{n}" thru_hole {shape} (at {x} {y}) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask"){rr} (uuid "{U()}"))\n'
L = lambda a, b, layer, w: f'\t(fp_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{U()}"))\n'
rect = lambda x1, y1, x2, y2, ly, w: L((x1, y1), (x2, y1), ly, w) + L((x2, y1), (x2, y2), ly, w) + L((x2, y2), (x1, y2), ly, w) + L((x1, y2), (x1, y1), ly, w)
def prop(k, v, x, y, ly, hide=False):
    return (f'\t(property "{k}" "{v}" (at {x} {y} 0) (layer "{ly}"){" (hide yes)" if hide else ""} (uuid "{U()}")\n'
            '\t\t(effects (font (size 1 1) (thickness 0.15))))\n')
utext = lambda t, x, y, ly, a=0: f'\t(fp_text user "{t}" (at {x} {y} {a}) (layer "{ly}") (uuid "{U()}") (effects (font (size 1 1) (thickness 0.15))))\n'
def model(path, off, rot=(0, 0, 0)):
    return (f'\t(model "{path}"\n\t\t(offset (xyz {off[0]} {off[1]} {off[2]}))\n\t\t(scale (xyz 1 1 1))\n'
            f'\t\t(rotate (xyz {rot[0]} {rot[1]} {rot[2]}))\n\t)\n')
s = ('(footprint "ESP32-C3-DevKit-RUST_Socket" (version 20240108) (generator "pe1rgu-gen_devkit_fp") (layer "F.Cu")\n'
     '\t(descr "ESP32-C3 Rust board (DevKit-RUST-1 Rev 1.2a, DevKit-RUST-2) in Sullins PPPC161LFBN-RC (1x16) and PPPC121LFBN-RC (1x12) '
     'gold-flash socket headers, 8.50 mm, rows 20.32 mm apart. Pads as esp-rs Rust_Board (1..16 left, 28..17 right top to bottom); '
     'DevKit battery pads 29, 30 not used. Drill 1.0 mm (Sullins 1.02). USB-C at the +Y end. D-93, D-95")\n'
     '\t(tags "ESP32-C3 DevKit RUST socket")\n')
s += prop("Reference", "REF**", -8.3, -33.3, "F.SilkS") + prop("Value", "ESP32-C3-DevKit-RUST_Socket", 0, 35.3, "F.Fab")
s += prop("Footprint", "", 0, 0, "F.Fab", True) + prop("Datasheet", "", 0, 0, "F.Fab", True) + prop("Description", "", 0, 0, "F.Fab", True)
s += '\t(attr through_hole)\n'
for n in range(16): s += pad(n + 1, -10.16, round(-20.32 + 2.54 * n, 2), 'roundrect' if n == 0 else 'circle')
for p in range(28, 16, -1): s += pad(p, 10.16, round(-10.16 + 2.54 * (28 - p), 2), 'circle')
s += rect(-11.43, -31.75, 11.43, 31.75, "F.Fab", 0.1) + rect(-4.5, 31.75, 4.5, 33.51, "F.Fab", 0.1)
s += utext("USB-C", 0, 30.0, "F.Fab") + utext("${REFERENCE}", 0, 0, "F.Fab", 90)
s += rect(-11.55, -31.87, 11.55, 31.87, "F.SilkS", 0.12) + L((-12.4, -21.0), (-12.4, -19.64), "F.SilkS", 0.12)
s += utext("USB-C", 0, 29.6, "F.SilkS")
s += rect(-12.7, -32.0, 11.68, 33.76, "F.CrtYd", 0.05)
s += model("${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x16_P2.54mm_Vertical.step", (-10.16, 20.32, 0))
s += model("${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x12_P2.54mm_Vertical.step", (10.16, 10.16, 0))
s += model("${KIPRJMOD}/lib/snapeda-devkit-rust-1/ESP32-C3-DEVKIT-RUST-1.step", (0, 0, STACK), (-90, 0, 0))
s += ')\n'
assert s.count('(') == s.count(')')
for d in ("shack-interface.pretty", "../../unit/controller-board/lib/controller-board.pretty"):   # written straight into the footprint libraries
    open(f"{d}/ESP32-C3-DevKit-RUST_Socket.kicad_mod", "w").write(s)
print("written, pads:", s.count('(pad '))
