#!/usr/bin/env python3
"""Controller board footprints drawn in this project. Run from this folder (hardware/unit/controller-board/lib/);
writes into controller-board.pretty/. Datasheets in Datasheets/.

RJ45_8P8C_Unshielded_TabDown (J1, D-138)
  Wurth 615008137121  Rev 001.002 2025-07-09  pin hole 0.90, pegs 3.1 to 3.2, body 15.15 x 18, face 7.88 from the peg line
  Molex 95501-2881    SD-95501-001 Rev F1     pin hole 0.889, pegs 3.302 (plated in the vendor footprint), 15.24 x 18.10, face 7.93
  Shared pattern: pegs at +-5.715 on the peg line (y 0); odd pins at y -6.35, even pins at y -8.89; pin 1 at x -4.445,
  1.27 mm stagger. Front face toward +y. Drill 1.0 covers both leads; pegs NPTH 3.25.
  3D: Wurth STEP (origin at the body centre, 1.12 mm behind the peg line).

GDT_3Pin_Bourns_2036-B2_P4.40mm (GD1 to GD4)
  Bourns 2036 Rev B 01/26, lead form B2: body dia 5.0 +-0.3 x 7.5 +-0.3, lying flat; three leads in one row,
  pitch 4.4 +-0.3, lead dia 0.8 +-0.08. Pin 2 = centre electrode. Drill 1.2 takes the pitch tolerance.
  3D: Bourns STEP 2036-XX-B2 (lib/3d/Bourns_2036-xx-B2.stp). gen_gdt_step.py (own simple model) is kept as a fallback.
GDT_3Pin_P4.40mm_Bourns-2036-B2_Littelfuse-SL1003A-R (GD1 to GD4 from layout c-s2, D-149)
  The same three holes take both parts: Bourns 2036-09-B2 (above) and the second source Littelfuse SL1003A090R-001
  (SL1003A Revised 12/12/17: body dia 6.0 x 8.1, 12.2 overall with the outer lead bends, leads 0.8 in one row at pitch
  4.4 +-0.3, body 6.0 +-0.5 above the lead ends). Courtyard covers the larger SL1003A body (+-6.1 x +-3.0).

L_CMC_TDK_ACT45B (L1 to L4, D-149)
  TDK ACT45B (2016-02-16): body 4.5 x 3.2 x 2.8; recommended land 5.9 x 3.4 outside, 3.2 x 1.6 inside (pads 1.35 x 0.9,
  pitch 4.55 x 2.5); windings TDK 1-4 and 2-3 side by side, starts 1 and 2 at one end. Drawn with the long axis along y and
  the winding starts at the top. Pad numbers follow the KiCad symbol Device:L_Coupled (1-2 winding A, 3-4 winding B, starts
  1 and 3): pad 1 = TDK 1 (top right), pad 2 = TDK 4 (bottom right), pad 3 = TDK 2 (top left), pad 4 = TDK 3 (bottom left).
  3D: KiCad L_CommonModeChoke_Coilcraft_1812CAN (same 1812 body) as a stand-in."""
import uuid

def footprint(name, descr, tags, attr, body):
    n = iter(range(1, 100000))   # stable uuids: same input, same file
    U = lambda: str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pe1rgu.footprint.{name}.{next(n)}"))
    L = lambda a, b, ly, w: f'\t(fp_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width {w}) (type solid)) (layer "{ly}") (uuid "{U()}"))\n'
    rect = lambda x1, y1, x2, y2, ly, w: L((x1, y1), (x2, y1), ly, w) + L((x2, y1), (x2, y2), ly, w) + L((x2, y2), (x1, y2), ly, w) + L((x1, y2), (x1, y1), ly, w)
    prop = lambda k, v, x, y, ly, hide=False: (f'\t(property "{k}" "{v}" (at {x} {y} 0) (layer "{ly}"){" (hide yes)" if hide else ""} (uuid "{U()}")\n'
                                               '\t\t(effects (font (size 1 1) (thickness 0.15))))\n')
    def pad(num, x, y, drill, size, shape="circle"):
        if num is None:
            return f'\t(pad "" np_thru_hole circle (at {x} {y}) (size {size} {size}) (drill {drill}) (layers "*.Cu" "*.Mask") (uuid "{U()}"))\n'
        return f'\t(pad "{num}" thru_hole {shape} (at {x} {y}) (size {size} {size}) (drill {drill}) (layers "*.Cu" "*.Mask") (uuid "{U()}"))\n'
    utext = lambda t, x, y, ly: f'\t(fp_text user "{t}" (at {x} {y} 0) (layer "{ly}") (uuid "{U()}") (effects (font (size 0.8 0.8) (thickness 0.12))))\n'
    s = (f'(footprint "{name}" (version 20240108) (generator "pe1rgu-gen_ctl_fp") (layer "F.Cu")\n'
         f'\t(descr "{descr}")\n\t(tags "{tags}")\n')
    s += body(L, rect, prop, pad, utext)
    s = s.replace("\t(attr)\n", f"\t(attr {attr})\n")
    s += ')\n'
    assert s.count('(') == s.count(')')
    open(f"controller-board.pretty/{name}.kicad_mod", "w").write(s)
    print("written", name)

def model(path, off, rot):
    return (f'\t(model "{path}"\n\t\t(offset (xyz {off[0]} {off[1]} {off[2]}))\n\t\t(scale (xyz 1 1 1))\n'
            f'\t\t(rotate (xyz {rot[0]} {rot[1]} {rot[2]}))\n\t)\n')

# ---------- RJ45 ----------
RJ_FACE, RJ_BACK, RJ_X = 7.93, -10.17, 7.62          # union of the Wurth and Molex bodies
RJ_3D_OFF, RJ_3D_ROT = (0, 1.12, 5.83), (0, 0, 0)     # STEP origin at the body centre; checked in a KiCad render

def rj45(L, rect, prop, pad, utext):
    s = prop("Reference", "REF**", 0, RJ_BACK - 1.6, "F.SilkS") + prop("Value", "RJ45_8P8C_Unshielded_TabDown", 0, 3.0, "F.Fab")
    s += prop("Footprint", "", 0, 0, "F.Fab", True) + prop("Datasheet", "", 0, 0, "F.Fab", True) + prop("Description", "", 0, 0, "F.Fab", True)
    s += '\t(attr)\n'
    for p in range(1, 9):
        x = round(-4.445 + (p - 1) * 1.27, 3)
        y = -6.35 if p % 2 else -8.89
        s += pad(p, x, y, 1.0, 1.5, "rect" if p == 1 else "circle")
    s += pad(None, -5.715, 0, 3.25, 3.25) + pad(None, 5.715, 0, 3.25, 3.25)
    s += rect(-RJ_X, RJ_BACK, RJ_X, RJ_FACE, "F.Fab", 0.1)
    s += L((-RJ_X, RJ_FACE - 0.3), (RJ_X, RJ_FACE - 0.3), "F.Fab", 0.1)        # face line
    s += utext("${REFERENCE}", 0, -3.0, "F.Fab")
    sx, sb = RJ_X + 0.11, RJ_BACK - 0.11
    s += L((-sx, 4.0), (-sx, sb), "F.SilkS", 0.12) + L((-sx, sb), (sx, sb), "F.SilkS", 0.12) + L((sx, sb), (sx, 4.0), "F.SilkS", 0.12)
    s += L((-6.0, -6.35), (-5.5, -6.35), "F.SilkS", 0.12)                      # pin 1 mark
    s += rect(-RJ_X - 0.25, RJ_BACK - 0.25, RJ_X + 0.25, RJ_FACE, "F.CrtYd", 0.05)
    s += model("${KIPRJMOD}/lib/3d/615008137121.step", RJ_3D_OFF, RJ_3D_ROT)
    return s

footprint("RJ45_8P8C_Unshielded_TabDown",
          "RJ45 8P8C unshielded, tab down, THT. Wurth 615008137121, Molex 95501-2881 (D-138). Origin at the peg midpoint, "
          "front face toward +y at 7.93 mm. Drill 1.0, pegs NPTH 3.25",
          "RJ45 8P8C modular jack unshielded 615008137121 95501-2881", "through_hole", rj45)

# ---------- GDT ----------
GDT_P, GDT_L, GDT_D, GDT_H = 4.4, 7.5, 5.0, 0.5      # pitch, body length, body dia, gap body to board
# Bourns STEP (2036-XX-B2, 2012): body centre at the origin, leads toward -x, lead row along y (bbox x -6.55..2.55, y +-4.8, z +-2.55)
GDT_3D_OFF, GDT_3D_ROT = (0, 0, GDT_H + 2.55), (0, 90, 90)   # leads down, row along x; checked in a KiCad render

def gdt(L, rect, prop, pad, utext):
    s = prop("Reference", "REF**", 0, -3.6, "F.SilkS") + prop("Value", "GDT_3Pin_Bourns_2036-B2_P4.40mm", 0, 3.6, "F.Fab")
    s += prop("Footprint", "", 0, 0, "F.Fab", True) + prop("Datasheet", "", 0, 0, "F.Fab", True) + prop("Description", "", 0, 0, "F.Fab", True)
    s += '\t(attr)\n'
    s += pad(1, -GDT_P, 0, 1.2, 2.0, "rect") + pad(2, 0, 0, 1.2, 2.0) + pad(3, GDT_P, 0, 1.2, 2.0)
    hl, hd = GDT_L / 2, GDT_D / 2
    s += rect(-hl, -hd, hl, hd, "F.Fab", 0.1) + utext("${REFERENCE}", 0, 0, "F.Fab")
    s += L((-1.6, -hd - 0.11), (1.6, -hd - 0.11), "F.SilkS", 0.12) + L((-1.6, hd + 0.11), (1.6, hd + 0.11), "F.SilkS", 0.12)
    s += L((-GDT_P - 1.3, -1.3), (-GDT_P - 1.3, 1.3), "F.SilkS", 0.12)          # pin 1 mark
    cx = GDT_P + 0.4 + 0.5 + 0.25                                                # lead bend outside the body end
    s += rect(-cx, -hd - 0.25, cx, hd + 0.25, "F.CrtYd", 0.05)
    s += model("${KIPRJMOD}/lib/3d/Bourns_2036-xx-B2.stp", GDT_3D_OFF, GDT_3D_ROT)
    return s

footprint("GDT_3Pin_Bourns_2036-B2_P4.40mm",
          "Gas discharge tube, 3 electrodes, Bourns 2036-xx-B2 (Rev B 01/26): body dia 5.0 x 7.5 flat, leads 0.8 in one row, "
          "pitch 4.4. Pin 2 centre electrode. Drill 1.2",
          "GDT gas discharge tube 3 pole Bourns 2036 B2", "through_hole", gdt)

# ---------- GDT, two sources (D-149) ----------
SL_HL, SL_HD = 6.1, 3.0                               # Littelfuse SL1003A-R: half overall length, half body dia

def gdt2(L, rect, prop, pad, utext):
    s = prop("Reference", "REF**", 0, -3.9, "F.SilkS") + prop("Value", "GDT_3Pin_P4.40mm_Bourns-2036-B2_Littelfuse-SL1003A-R", 0, 3.9, "F.Fab")
    s += prop("Footprint", "", 0, 0, "F.Fab", True) + prop("Datasheet", "", 0, 0, "F.Fab", True) + prop("Description", "", 0, 0, "F.Fab", True)
    s += '\t(attr)\n'
    s += pad(1, -GDT_P, 0, 1.2, 2.0, "rect") + pad(2, 0, 0, 1.2, 2.0) + pad(3, GDT_P, 0, 1.2, 2.0)
    hl, hd = GDT_L / 2, GDT_D / 2
    s += rect(-hl, -hd, hl, hd, "F.Fab", 0.1) + rect(-SL_HL, -SL_HD, SL_HL, SL_HD, "F.Fab", 0.1) + utext("${REFERENCE}", 0, 0, "F.Fab")
    s += L((-1.6, -SL_HD - 0.11), (1.6, -SL_HD - 0.11), "F.SilkS", 0.12) + L((-1.6, SL_HD + 0.11), (1.6, SL_HD + 0.11), "F.SilkS", 0.12)
    s += L((-GDT_P - 1.3, -1.3), (-GDT_P - 1.3, 1.3), "F.SilkS", 0.12)          # pin 1 mark
    s += rect(-SL_HL - 0.25, -SL_HD - 0.25, SL_HL + 0.25, SL_HD + 0.25, "F.CrtYd", 0.05)
    s += model("${KIPRJMOD}/lib/3d/Bourns_2036-xx-B2.stp", GDT_3D_OFF, GDT_3D_ROT)
    return s

footprint("GDT_3Pin_P4.40mm_Bourns-2036-B2_Littelfuse-SL1003A-R",
          "Gas discharge tube, 3 electrodes, leads in one row at pitch 4.4: Bourns 2036-xx-B2 (Rev B 01/26) or Littelfuse "
          "SL1003AxxxR-001 (Revised 12/12/17). Pin 2 centre electrode. Drill 1.2. Courtyard for the SL1003A body (D-149)",
          "GDT gas discharge tube 3 pole Bourns 2036 B2 Littelfuse SL1003A", "through_hole", gdt2)

# ---------- common-mode choke TDK ACT45B (D-149) ----------
CMC_PX, CMC_PY, CMC_PW, CMC_PH = 1.25, 2.275, 0.9, 1.35   # pad centre x, y; pad size x, y (TDK land 5.9 x 3.4 / 3.2 x 1.6)

def cmc(L, rect, prop, pad, utext):
    U = lambda k: str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pe1rgu.footprint.L_CMC_TDK_ACT45B.pad{k}"))
    s = prop("Reference", "REF**", 0, -3.8, "F.SilkS") + prop("Value", "L_CMC_TDK_ACT45B", 0, 3.8, "F.Fab")
    s += prop("Footprint", "", 0, 0, "F.Fab", True) + prop("Datasheet", "", 0, 0, "F.Fab", True) + prop("Description", "", 0, 0, "F.Fab", True)
    s += '\t(attr)\n'
    for num, x, y in (("1", CMC_PX, -CMC_PY), ("2", CMC_PX, CMC_PY), ("3", -CMC_PX, -CMC_PY), ("4", -CMC_PX, CMC_PY)):
        s += (f'\t(pad "{num}" smd rect (at {x} {y}) (size {CMC_PW} {CMC_PH}) (layers "F.Cu" "F.Paste" "F.Mask") '
              f'(uuid "{U(num)}"))\n')
    s += rect(-1.6, -2.25, 1.6, 2.25, "F.Fab", 0.1) + utext("${REFERENCE}", 0, 0, "F.Fab")
    s += L((-1.71, -1.3), (-1.71, 1.3), "F.SilkS", 0.12) + L((1.71, -1.3), (1.71, 1.3), "F.SilkS", 0.12)
    s += L((0.8, -3.15), (1.7, -3.15), "F.SilkS", 0.12)                           # pin 1 mark (TDK 1, winding start)
    s += rect(-1.95, -3.2, 1.95, 3.2, "F.CrtYd", 0.05)
    s += model("${KICAD10_3DMODEL_DIR}/Inductor_SMD.3dshapes/L_CommonModeChoke_Coilcraft_1812CAN.step", (0, 0, 0), (0, 0, 0))
    return s

footprint("L_CMC_TDK_ACT45B",
          "Common-mode choke TDK ACT45B (4.5 x 3.2 mm), TDK land pattern. Long axis along y, winding starts at the top. Pads follow "
          "Device:L_Coupled: 1 = TDK 1, 2 = TDK 4, 3 = TDK 2, 4 = TDK 3 (D-149)",
          "common mode choke CMC TDK ACT45B", "smd", cmc)
