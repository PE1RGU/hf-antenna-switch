#!/usr/bin/env python3
"""Project footprints for the RF board, second set (design log D-108 to D-110). Run from this folder; writes into rf-board.pretty/:
- SMA_901-9215_StrapPad: strap land for the EXP SMA panel jack (Amphenol RF 901-9215, second source 132142) in the left case wall.
  Origin: connector axis on the board edge (board edge = Y 0, board inside = -Y; place with rotation 270 at the left edge).
  The jack sits in a 13 x 13 x 2 mm pocket milled from the outside (wall 4 mm there, D-110); its contact (dia 1.27 mm, solder
  cup) ends about 1.1 mm past the inner wall, about 2.9 mm short of the board edge. A copper strap 3 x 0.3 mm joins the cup
  to pad 1. Pad 1: land 3.5 x 4.0 mm on F.Cu and B.Cu, 0.5 mm from the edge, 3 vias (drill 0.6, pad 1.0, pitch 1.2, D-111) at the inner end, clearance
  2.0 mm (RF gap, D-12). Pad 2 (GND): plated M3 hole to a milled GND boss, 9 mm beside the axis (towards the TX row after
  rotation), 4 mm from the edge, solid zone connection (RF return, as D-105).
- WireLink_P7.62mm_D1.0mm: column link R402 to R702 (D-109): tinned copper wire about 0.8 mm, two plated holes drill 1.0 mm,
  round pads 2.7 mm (= RF line width), pitch 7.62 mm, pad clearance 2.0 mm.
- GDT_Axial_P15.24mm: footprint for the not-fitted GDT GD401 to GD701 (D-07, D-109); not used since D-114 (GDT removed). Pads 1 and 3 (KiCad Device:GDT_2Pin),
  drill 1.0 mm, pitch 15.24 mm, body outline 8 x 6 mm (axial 600 V class, part to select; check the land at the part choice).
No 3D models."""
import uuid

class FP:
    def __init__(self, name):
        self.name, self.n, self.s = name, iter(range(1, 1000)), ""
    def U(self): return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pe1rgu.footprint.{self.name}.{next(self.n)}"))   # stable uuids
    def line(self, a, b, ly, w, t="solid"):
        self.s += f'\t(fp_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width {w}) (type {t})) (layer "{ly}") (uuid "{self.U()}"))\n'
    def rect(self, x1, y1, x2, y2, ly, w):
        for a, b in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))): self.line(a, b, ly, w)
    def prop(self, k, v, x, y, ly, hide=False):
        self.s += (f'\t(property "{k}" "{v}" (at {x} {y} 0) (layer "{ly}"){" (hide yes)" if hide else ""} (uuid "{self.U()}")\n'
                   f'\t\t(effects (font (size 1 1) (thickness 0.15))))\n')
    def text(self, t, x, y, ly):
        self.s += f'\t(fp_text user "{t}" (at {x} {y} 0) (layer "{ly}") (uuid "{self.U()}") (effects (font (size 0.8 0.8) (thickness 0.12))))\n'
    def head(self, descr, tags, ry, vy):
        self.s = (f'(footprint "{self.name}" (version 20240108) (generator "pe1rgu-gen_rf_fp") (layer "F.Cu")\n'
                  f'\t(descr "{descr}")\n\t(tags "{tags}")\n')
        self.prop("Reference", "REF**", 0, ry, "F.SilkS"); self.prop("Value", self.name, 0, vy, "F.Fab")
        for k in ("Footprint", "Datasheet", "Description"): self.prop(k, "", 0, 0, "F.Fab", True)
        self.s += '\t(attr through_hole)\n'
    def pad(self, num, kind, shape, x, y, size, drill=None, layers='"*.Cu" "*.Mask"', extra=""):
        d = f" (drill {drill})" if drill else ""
        self.s += f'\t(pad "{num}" {kind} {shape} (at {x} {y}) (size {size[0]} {size[1]}){d} (layers {layers}){extra} (uuid "{self.U()}"))\n'
    def write(self):
        self.s += ')\n'
        assert self.s.count('(') == self.s.count(')'), self.name
        open(f"rf-board.pretty/{self.name}.kicad_mod", "w").write(self.s)
        return self.s.count("(pad ")

def sma():
    f = FP("SMA_901-9215_StrapPad")
    f.head("Strap land for an Amphenol RF 901-9215 (or 132142) SMA panel jack in the case wall pocket: RF pad on both layers with "
           "3 vias, 2.0 mm RF clearance; plated M3 hole to the GND boss at -9 mm, 4 mm from the edge (solid). Origin = axis on the board edge. D-110",
           "SMA 901-9215 132142 strap case wall", -7.0, 1.5)
    PW, PL, EDGE = 3.5, 4.0, 0.5
    PY = -(EDGE + PL / 2)
    for ly in ("F", "B"):
        f.pad("1", "smd", "rect", 0, PY, (PW, PL), layers=f'"{ly}.Cu" "{ly}.Mask"', extra=" (clearance 2.0)")
    for x in (-1.2, 0.0, 1.2):
        f.pad("1", "thru_hole", "circle", x, round(PY - 1.3, 2), (1.0, 1.0), 0.6, '"*.Cu"', " (clearance 2.0)")
    f.pad("2", "thru_hole", "circle", -9.0, -4.0, (6.0, 6.0), 3.2, extra=" (zone_connect 2)")
    f.line((-13.0, 0), (6.5, 0), "F.Fab", 0.1, "dash"); f.text("board edge", 2.5, 0.9, "F.Fab")
    f.rect(-6.35, 0.0, 6.35, 4.0, "F.Fab", 0.1); f.text("SMA in the wall", 0, 2.4, "F.Fab")
    f.rect(-1.5, -1.4, 1.5, -3.0, "F.Fab", 0.08); f.text("strap", 0, -5.6, "F.Fab")
    f.line((-2.6, -0.3), (-2.6, -5.2), "F.SilkS", 0.12); f.line((2.6, -0.3), (2.6, -5.2), "F.SilkS", 0.12)
    f.rect(-3.85, 0.0, 3.85, -6.6, "F.CrtYd", 0.05)
    f.rect(-12.25, -0.75, -5.75, -7.25, "F.CrtYd", 0.05)
    return f.write()

def link():
    f = FP("WireLink_P7.62mm_D1.0mm")
    f.head("Wire link, tinned copper wire about 0.8 mm, pitch 7.62 mm, drill 1.0 mm, round pads 2.7 mm, clearance 2.0 mm (RF column link, D-109)",
           "wire link jumper RF", -2.6, 2.6)
    for i, x in enumerate((0.0, 7.62)):
        f.pad(str(i + 1), "thru_hole", "circle", x, 0, (2.7, 2.7), 1.0, extra=" (clearance 2.0)")
    f.line((1.35, 0), (6.27, 0), "F.Fab", 0.8); f.line((1.6, -1.6), (6.02, -1.6), "F.SilkS", 0.12); f.line((1.6, 1.6), (6.02, 1.6), "F.SilkS", 0.12)
    f.rect(-1.6, -1.6, 9.22, 1.6, "F.CrtYd", 0.05)
    return f.write()

def gdt():
    f = FP("GDT_Axial_P15.24mm")
    f.head("Gas discharge tube, axial leads, pitch 15.24 mm, drill 1.0 mm, body 8 x 6 mm; pads 1 and 3 as KiCad Device:GDT_2Pin. "
           "Part not selected: check the land at the part choice (D-07, D-109)", "GDT gas discharge tube axial", -5.0, 5.0)
    f.pad("1", "thru_hole", "circle", 0, 0, (2.0, 2.0), 1.0)
    f.pad("3", "thru_hole", "circle", 15.24, 0, (2.0, 2.0), 1.0, extra=" (clearance 2.0)")
    f.rect(4.62, -4.0, 10.62, 4.0, "F.Fab", 0.1); f.line((1.0, 0), (4.62, 0), "F.Fab", 0.1); f.line((10.62, 0), (14.24, 0), "F.Fab", 0.1)
    f.rect(4.5, -4.12, 10.74, 4.12, "F.SilkS", 0.12)
    f.rect(-1.25, -4.37, 16.49, 4.37, "F.CrtYd", 0.05)
    return f.write()

for fn in (sma, link, gdt):
    print("written", fn.__name__, "pads", fn())
