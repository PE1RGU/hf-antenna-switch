#!/usr/bin/env python3
"""Generate backplane.kicad_pcb from the schematic netlist (run on the Mac, from this folder).

Nets come from `kicad-cli sch export netlist`, so the board follows the schematic.
Decisions: claude/decisions-2026-09-26-backplane.md (stackup JLC06161H-7628A, RF on L1,
W 1.0 mm, gap 1.25 mm; inside the DIN pin fields RF runs on In2 (L3) and In4 (L5) in parallel).
"""
import re, math, uuid, subprocess, shutil, os

KCLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/"
U = lambda: str(uuid.uuid4())
F = lambda v: f"{v:.4f}".rstrip("0").rstrip(".")

# ---------------- netlist ----------------
subprocess.run([KCLI, "sch", "export", "netlist", "-o", "/tmp/bp_gen.net", "backplane.kicad_sch"],
               check=True, capture_output=True)
net_txt = open("/tmp/bp_gen.net").read()
PADNET = {}
for part in re.split(r"\(net\s+\(code", net_txt[net_txt.find("(nets"):])[1:]:
    name = re.search(r'\(name "([^"]*)"\)', part).group(1)
    for ref, pin in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', part):
        PADNET[(ref, pin)] = name.lstrip("/") if name.startswith("unconnected") else name.lstrip("/")
DESC = dict(re.findall(r'\(comp\s+\(ref "([^"]+)"\)[\s\S]*?\(description "([^"]*)"\)', net_txt))

# ---------------- geometry ----------------
BW, BH = 340.0, 126.0
PITCH = 30.48
X = [20.0 + n * PITCH for n in range(11)]          # pad a1 x of slot n (footprint rotated 180)
Y0 = 109.4                                           # pad a1 y (row 1 at the bottom)
def ry(r): return Y0 - (r - 1) * 2.54               # y of pin row r
def col(c, n): return X[n] - {"a": 0.0, "b": 2.54, "c": 5.08}[c]
def ymid(k): return Y0 - (3 * k - 1.5) * 2.54       # RF position k: between rows 3k-1 and 3k
RFW, RFS, NECK = 1.0, 1.25, 0.45                     # L1 width, L1 gap, pin-field neck on L3/L5
VIA_RF = (1.0, 0.5)                                  # RF transition via: pad, drill
VIA_G = (0.6, 0.3)
def vl(n): return [X[n] - 7.7, X[n] - 9.0]           # left transition vias of slot n
def vr(n): return [X[n] + 2.6, X[n] + 3.9]           # right transition vias
GAP_C = [X[n] + 12.7 for n in range(10)]             # centre of the gap between slot n and n+1

out = []   # board items
tracks = []  # (x1,y1,x2,y2,w,layer,net) for keep-out checks
vias = []    # (x,y,pad,net)

def seg(x1, y1, x2, y2, w, layer, net):
    tracks.append((x1, y1, x2, y2, w, layer, net))
    out.append(f'\t(segment\n\t\t(start {F(x1)} {F(y1)})\n\t\t(end {F(x2)} {F(y2)})\n\t\t(width {F(w)})\n'
               f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')
def via(x, y, net, size=VIA_G):
    vias.append((x, y, size[0], net))
    out.append(f'\t(via\n\t\t(at {F(x)} {F(y)})\n\t\t(size {F(size[0])})\n\t\t(drill {F(size[1])})\n'
               f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{U()}")\n\t)\n')

# ---------------- footprints ----------------
def load_fp(lib, name):
    s = open(f"{FPLIB}{lib}.pretty/{name}.kicad_mod").read().strip()
    s = re.sub(r'\n\t\((version|generator|generator_version) [^\n]*\)', "", s)
    return s.replace(f'(footprint "{name}"', f'(footprint "{lib}:{name}"', 1)
def place(fptxt, ref, value, x, y, rot, board_only=False):
    s = fptxt.replace('(layer "F.Cu")', f'(layer "F.Cu")\n\t(uuid "{U()}")\n\t(at {F(x)} {F(y)} {F(rot)})', 1)
    s = s.replace('(property "Reference" "REF**"', f'(property "Reference" "{ref}"', 1)
    if ref in DESC:
        if '(property "Description"' in s:
            s = re.sub(r'\(property "Description" "[^"]*"', f'(property "Description" "{DESC[ref]}"', s, count=1)
        else:   # library footprint has no Description field: add a hidden one
            s = s.replace("\n\t(attr", f'\n\t(property "Description" "{DESC[ref]}"\n\t\t(at 0 0 0)\n\t\t(layer "F.Fab")\n\t\t(hide yes)\n\t\t(uuid "{U()}")\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n\t(attr', 1)
    if ref.startswith("H") and y < 10:   # top-edge hole: reference below the hole, away from the board edge
        s = re.sub(r'(\(property "Reference" "[^"]*"\s*\(at )[-\d.]+ -([\d.]+)', r'\g<1>0 \2', s, count=1)
    if ref in XT_MODEL:   # vendor STEP (KiCad 10 ships no XT30PW/XT60PW model); rotate/offset from its pin geometry
        path, off, rot3 = XT_MODEL[ref]
        s = re.sub(r'\(model "[^"]*"[\s\S]*?\(offset\s*\(xyz [^)]*\)\s*\)[\s\S]*?\(rotate\s*\(xyz [^)]*\)\s*\)',
                   f'(model "${{KIPRJMOD}}/backplane.3dshapes/{path}"\n\t\t(offset\n\t\t\t(xyz {off})\n\t\t)\n\t\t(scale\n\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n\t\t\t(xyz {rot3})\n\t\t)',
                   s, count=1)
    if ref in ("J12", "J13", "J14"):
        s = re.sub(r'(\(property "Reference" "[^"]*"\s*\(at )[-\d.]+ [-\d.]+', r'\g<1>0 5', s, count=1)
    s = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{value}"', s, count=1)
    def padfix(m):
        blk, num = m.group(0), m.group(1)
        if rot:  # pad angle includes the footprint rotation
            blk = re.sub(r'\(at ([-\d.]+) ([-\d.]+)( [-\d.]+)?\)',
                         lambda a: f'(at {a.group(1)} {a.group(2)} {F((float(a.group(3) or 0) + rot) % 360)})', blk, count=1)
        net = PADNET.get((ref, num)) if num else None
        if net:
            blk = blk.replace("\n\t\t(uuid", f'\n\t\t(net "{net}")\n\t\t(uuid', 1) if "(uuid" in blk else \
                  blk[:-1] + f'\t(net "{net}")\n\t)'
        return blk
    s = re.sub(r'\(pad "([^"]*)"[\s\S]*?\n\t\)', padfix, s)
    if ref in ("JP1", "C1"):   # reference shown as board text next to the part
        s = re.sub(r'(\(property "Reference" "[^"]*"\s*\(at [^)]*\))', r'\1\n\t\t(hide yes)', s, count=1)
    if ref == "C1":
        s = re.sub(r'\(attr ([^)]*)\)', lambda a: f'(attr {a.group(1)} dnp)', s, count=1)
    if board_only:
        s = re.sub(r'\(attr ([^)]*)\)', lambda a: f'(attr {a.group(1)} board_only exclude_from_pos_files exclude_from_bom)', s, count=1)
    return "\t" + s.replace("\n", "\n\t") + "\n"

XT_MODEL = {"J12": ("AMASS_XT60PW-M.step", "3.6 6 0", "-90 0 180"),
            "J13": ("AMASS_XT60PW-M.step", "3.6 6 0", "-90 0 180"),
            "J14": ("AMASS_XT30PW-M.step", "-2.5 10 0", "-90 0 0")}
DIN = load_fp("Connector_DIN", "DIN41612_C_3x32_Female_Vertical_THT")
for n in range(11):
    out.append(place(DIN, f"J{n+1}", "09 03 296 6824", X[n], Y0, 180))
XT60 = load_fp("Connector_AMASS", "AMASS_XT60PW-M_1x02_P7.20mm_Horizontal")
XT30 = load_fp("Connector_AMASS", "AMASS_XT30PW-M_1x02_P2.50mm_Horizontal")
# Power entry at the top edge, in the gaps between slots (mating face up, towards the PSU).
J14 = (GAP_C[4] + 2.5, 14.1)    # XT30: pad 1 at anchor, pad 2 at x-5
J12 = (GAP_C[5] - 3.6, 17.35)   # XT60: pad 1 at anchor, pad 2 at x+7.2
J13 = (GAP_C[6] - 3.6, 17.35)
out.append(place(XT30, "J14", "XT30PW-M", *J14, 0))
out.append(place(XT60, "J12", "XT60PW-M", *J12, 0))
out.append(place(XT60, "J13", "XT60PW-M", *J13, 0))
# Mounting holes are not grounded (no ground loops). H1 is the one plated hole (net CHASSIS), with JP1 (open)
# and C1 (not fitted) to GND next to it, in case a chassis bond is needed.
MH = load_fp("MountingHole", "MountingHole_3.2mm_M3")
MHP = load_fp("MountingHole", "MountingHole_3.2mm_M3_Pad")
H1 = (5, 121.5)
HOLES = [H1, (5, 5), (100, 5), (250, 5), (335, 5), (100, 121.5), (250, 121.5), (335, 121.5)]
out.append(place(MHP, "H1", "M3 CHASSIS", *H1, 0))
for i, (x, y) in enumerate(HOLES[1:]):
    out.append(place(MH, f"H{i+2}", "M3", x, y, 0, board_only=True))
JP = (4.0, 113.0); CP = (8.5, 112.0)
out.append(place(load_fp("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"), "JP1", "open", *JP, 90))
out.append(place(load_fp("Capacitor_SMD", "C_1206_3216Metric_Pad1.33x1.80mm_HandSolder"), "C1", "DNP 10nF 1kV", *CP, 90))

# ---------------- RF lines ----------------
# ANTk: slots 1..4 connect at position k; antenna slots 5..3+k pass through (pins not connected);
# slot 4+k connects at position 1 (b2+b3). Jog from position k to 1 in the gap before slot 4+k.
def field(n, y, connect_rows, left, right, net):
    xb = col("b", n)
    x0 = vl(n)[1] if left else xb
    x1 = vr(n)[1] if right else xb
    for L in ("In2.Cu", "In4.Cu"):
        seg(x0, y, x1, y, NECK, L, net)
        for r in connect_rows:
            seg(xb, y, xb, ry(r), NECK, L, net)
    if left:
        for vx in vl(n): via(vx, y, net, VIA_RF)
        seg(vl(n)[1], y, vl(n)[0], y, RFW, "F.Cu", net)
    if right:
        for vx in vr(n): via(vx, y, net, VIA_RF)
        seg(vr(n)[0], y, vr(n)[1], y, RFW, "F.Cu", net)
for k in range(1, 7):
    net = f"ANT{k}"; y = ymid(k); end = 4 + k
    for n in range(1, end):
        rows = [3 * k - 1, 3 * k] if n <= 4 else []
        field(n, y, rows, left=(n > 1), right=True, net=net)
    # L1 between slots
    for n in range(1, end - 1):
        seg(vr(n)[1], y, vl(n + 1)[1], y, RFW, "F.Cu", net)
    y1 = ymid(1); xj = GAP_C[end - 1]
    if k == 1:
        seg(vr(end - 1)[1], y, vl(end)[1], y, RFW, "F.Cu", net)
    else:
        seg(vr(end - 1)[1], y, xj - 2, y, RFW, "F.Cu", net)
        seg(xj - 2, y, xj, y + 2, RFW, "F.Cu", net)            # 45 degree bends
        seg(xj, y + 2, xj, y1 - 2, RFW, "F.Cu", net)
        seg(xj, y1 - 2, xj + 2, y1, RFW, "F.Cu", net)
        seg(xj + 2, y1, vl(end)[1], y1, RFW, "F.Cu", net)
    field(end, y1, [2, 3], left=True, right=False, net=net)

# ---------------- bussed signals (channels between pin rows) ----------------
CH = [("In2.Cu", 20, "SDA", "a", 21), ("In2.Cu", 21, "~{INT}", "a", 22), ("In2.Cu", 22, "PTT1", "a", 23),
      ("In2.Cu", 23, "PTT3", "a", 24), ("In2.Cu", 25, "TX_ANY", "c", 26), ("In2.Cu", 26, "+12V_AUX", "a", 27),
      ("In4.Cu", 20, "SCL", "c", 21), ("In4.Cu", 21, "~{RLY_EN}", "c", 22), ("In4.Cu", 22, "PTT2", "c", 23),
      ("In4.Cu", 23, "PTT4", "c", 24), ("In4.Cu", 26, "SPARE2", "c", 27)]
for L, r, net, c, prow in CH:
    y = Y0 - (r - 0.5) * 2.54
    w = 0.4 if net == "+12V_AUX" else 0.254
    seg(col(c, 0), y, col(c, 10), y, w, L, net)
    for n in range(11):
        seg(col(c, n), y, col(c, n), ry(prow), w, L, net)

# ---------------- power entry ----------------
p5 = (J14[0] - 5.0, J14[1]); p12 = (J12[0] + 7.2, J12[1]); paux = (J13[0] + 7.2, J13[1])
y5 = ry(29)
seg(p5[0], p5[1], p5[0], y5, 1.5, "In2.Cu", "+5V")                 # +5V down on L3, then vias to the L5 band
seg(p5[0] - 1.8, y5, p5[0] + 1.8, y5, 0.8, "In2.Cu", "+5V")
for dx in (-1.8, -0.9, 0.0, 0.9, 1.8): via(p5[0] + dx, y5, "+5V", (0.8, 0.4))      # into the +5V band on L5
yaux = Y0 - 25.5 * 2.54
seg(paux[0], paux[1], paux[0], yaux, 0.5, "In2.Cu", "+12V_AUX")    # joins the +12V_AUX channel

# ---------------- chassis bond ----------------
jp1, jp2 = (JP[0], JP[1] + 0.65), (JP[0], JP[1] - 0.65)          # rot 90: pad 1 below, pad 2 above
c1, c2 = (CP[0], CP[1] + 1.4875), (CP[0], CP[1] - 1.4875)
seg(*H1, *jp1, 0.8, "F.Cu", "CHASSIS"); seg(*H1, *c1, 0.8, "F.Cu", "CHASSIS")
for p in (jp2, c2):
    seg(p[0], p[1], p[0], p[1] - 1.6, 0.6, "F.Cu", "GND"); via(p[0], p[1] - 1.6, "GND")

# ---------------- zones ----------------
def zone(net, layer, pts, clearance, priority=0, pads=None):
    p = " ".join(f"(xy {F(x)} {F(y)})" for x, y in pts)
    return (f'\t(zone\n\t\t(net "{net}")\n\t\t(layer "{layer}")\n\t\t(uuid "{U()}")\n\t\t(priority {priority})\n'
            f'\t\t(hatch edge 0.5)\n\t\t(connect_pads{" " + pads if pads else ""}\n\t\t\t(clearance {F(clearance)})\n\t\t)\n\t\t(min_thickness 0.25)\n'
            f'\t\t(filled_areas_thickness no)\n\t\t(fill yes\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n'
            f'\t\t\t(island_removal_mode 0)\n\t\t)\n\t\t(polygon\n\t\t\t(pts\n\t\t\t\t{p}\n\t\t\t)\n\t\t)\n\t)\n')
BOARD = [(0.5, 0.5), (BW - 0.5, 0.5), (BW - 0.5, BH - 0.5), (0.5, BH - 0.5)]
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
YB = (ry(19) + ry(20)) / 2                                  # boundary between RF rows and signal rows
RF_REG = [(0.5, YB), (BW - 0.5, YB), (BW - 0.5, BH - 0.5), (0.5, BH - 0.5)]
SIG_REG = [(0.5, 0.5), (BW - 0.5, 0.5), (BW - 0.5, YB - 0.3), (0.5, YB - 0.3)]
for L in LAYERS:
    if L in ("F.Cu", "B.Cu"):   # 173 V peak on RF: 1.25 mm (IPC-2221 B2); logic and 12 V region: 0.25 mm
        out.append(zone("GND", L, RF_REG, RFS, pads="no")); out.append(zone("GND", L, SIG_REG, 0.25))
    else:
        out.append(zone("GND", L, BOARD, 0.25))
b12 = (ry(32) + 1.0, ry(30) - 1.0); b5 = (ry(30) + 1.0, ry(28) - 1.0)
fx = p12[0]
out.append(zone("+12V_RLY", "In4.Cu", [(3, b12[0]), (fx - 2.5, b12[0]), (fx - 2.5, p12[1] - 3), (fx + 2.5, p12[1] - 3),
                                       (fx + 2.5, b12[0]), (BW - 3, b12[0]), (BW - 3, b12[1]), (3, b12[1])], 0.3, 1))
out.append(zone("+5V", "In4.Cu", [(3, b5[0]), (BW - 3, b5[0]), (BW - 3, b5[1]), (3, b5[1])], 0.3, 1))

# ---------------- RF via fence (L1) and stitching vias ----------------
def dseg(px, py, t):
    x1, y1, x2, y2 = t[:4]; dx, dy = x2 - x1, y2 - y1; L2 = dx * dx + dy * dy
    u = 0 if L2 == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - x1 - u * dx, py - y1 - u * dy)
def in_field(x, y, m=0.6):
    for n in range(11):
        if X[n] - 8.34 - m < x < X[n] + 3.26 + m and Y0 - 87.37 - m < y < Y0 + 8.63 + m: return True
    return False
KEEP = [(1.0, 107.0, 11.0, 117.0)] + [(J14[0] - 9.65 - 1, J14[1] - 13.6 - 1, J14[0] + 4.65 + 1, J14[1] + 2.25 + 1)] + \
       [(j[0] - 4.65 - 1, j[1] - 16.85 - 1, j[0] + 11.85 + 1, j[1] + 2.55 + 1) for j in (J12, J13)]
def free(x, y, rf_min, other_min=1.0):
    if not (2.5 < x < BW - 2.5 and 2.5 < y < BH - 2.5) or in_field(x, y): return False
    if any(a < x < c and b < y < d for a, b, c, d in KEEP): return False
    if any(math.hypot(x - hx, y - hy) < 4.5 for hx, hy in HOLES): return False
    for t in tracks:
        need = (rf_min if t[6].startswith("ANT") else other_min) + t[4] / 2 + VIA_G[0] / 2
        if dseg(x, y, t) < need: return False
    for vx, vy, vs, vn in vias:
        if math.hypot(x - vx, y - vy) < (vs / 2 + (1.25 if vn.startswith("ANT") else 0.35) + VIA_G[0] / 2): return False
    if b12[0] - 1 < y < b5[1] + 1: return False           # keep the L5 power bands whole
    return True
FENCE = RFW / 2 + RFS + VIA_G[0] / 2 + 0.05                # 2.1 mm from the trace centre
nf = 0
for t in [t for t in tracks if t[5] == "F.Cu" and t[6].startswith("ANT")]:
    x1, y1, x2, y2 = t[:4]; L = math.hypot(x2 - x1, y2 - y1)
    if L < 1: continue
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    for i in range(int(L / 2.54) + 1):
        for sgn in (1, -1):
            px, py = x1 + ux * i * 2.54 - sgn * uy * FENCE, y1 + uy * i * 2.54 + sgn * ux * FENCE
            if free(px, py, RFS - 0.02): via(round(px, 3), round(py, 3), "GND"); nf += 1
ns = 0
for gx in [2.54 + 5.08 * i for i in range(int(BW / 5.08))]:
    for gy in [2.54 + 5.08 * j for j in range(int(BH / 5.08))]:
        if free(gx, gy, RFS + 0.5): via(gx, gy, "GND"); ns += 1

# ---------------- silkscreen ----------------
def txt(t, x, y, h=1.2, w=0.18, layer="F.SilkS", just=None, rot=0):
    j = f"\n\t\t\t(justify {just})" if just else ""
    return (f'\t(gr_text "{t}"\n\t\t(at {F(x)} {F(y)} {rot})\n\t\t(layer "{layer}")\n\t\t(uuid "{U()}")\n'
            f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {h} {h})\n\t\t\t\t(thickness {w})\n\t\t\t)\t{j}\n\t\t)\n\t)\n')
NAMES = ["Link", "R1", "R2", "R3", "R4", "A1", "A2", "A3", "A4", "A5", "A6"]
for n, nm in enumerate(NAMES):
    out.append(txt(nm, X[n] - 2.54, 20.3, 1.5, 0.22))
    out.append(txt(f"slot {n}", X[n] - 2.54, 120.3, 1.0, 0.15))
def line(x1, y1, x2, y2, layer="F.SilkS", w=0.2):
    return (f'\t(gr_line\n\t\t(start {F(x1)} {F(y1)})\n\t\t(end {F(x2)} {F(y2)})\n\t\t(stroke\n\t\t\t(width {w})\n'
            f'\t\t\t(type solid)\n\t\t)\n\t\t(layer "{layer}")\n\t\t(uuid "{U()}")\n\t)\n')
def poly(pts, layer="F.SilkS", w=0.2, fill="no"):
    p = " ".join(f"(xy {F(x)} {F(y)})" for x, y in pts)
    return (f'\t(gr_poly\n\t\t(pts\n\t\t\t{p}\n\t\t)\n\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type solid)\n\t\t)\n'
            f'\t\t(fill {fill})\n\t\t(layer "{layer}")\n\t\t(uuid "{U()}")\n\t)\n')
def hv_warning(cx, cy, s=7.0):
    """High-voltage warning (IEC 60417-5036 / ISO 7010 W012 style): triangle with a lightning arrow."""
    h = s * 0.866
    o = poly([(cx, cy - h * 2 / 3), (cx + s / 2, cy + h / 3), (cx - s / 2, cy + h / 3)], w=0.3)
    k = s / 7.0
    o += poly([(cx + 0.35 * k, cy - 2.3 * k), (cx - 0.9 * k, cy + 0.2 * k), (cx + 0.2 * k, cy + 0.2 * k),
               (cx - 0.5 * k, cy + 1.9 * k), (cx + 0.9 * k, cy - 0.5 * k), (cx - 0.1 * k, cy - 0.5 * k)], fill="yes", w=0.1)
    return o
# RF warning in the free gap between the Link slot and R1, and at the right board end
out.append(txt("JP1", 1.9, 110.5, 0.8, 0.12)); out.append(txt("C1", 10.6, 108.4, 0.8, 0.12))
out.append(txt("CHASSIS", 6.2, 105.2, 0.8, 0.12))
out.append(hv_warning(31.0, 78.0)); out.append(txt("RF", 31.0, 84.0, 1.2, 0.18)); out.append(txt("173 V pk", 31.0, 86.2, 1.0, 0.15))
out.append(txt("100 W HF", 31.0, 88.2, 1.0, 0.15))
# Art block, top right: project, board, rev and date code, IEC OR gate (TX_ANY is the OR of the PTT lines)
ax, ay = 257.0, 3.2
out.append(txt("SHACK RELAY MATRIX", ax, ay, 1.5, 0.25, just="left"))
out.append(txt("Backplane, 11 slots", ax, ay + 2.6, 1.0, 0.15, just="left"))
out.append(txt("Rev A  2026-09  DC 2639", ax, ay + 4.4, 1.0, 0.15, just="left"))
out.append(txt("73 de PE1RGU", ax, ay + 8.4, 1.2, 0.18, just="left"))
gx, gy = ax + 40.0, ay - 0.6
out.append(poly([(gx, gy), (gx + 6, gy), (gx + 6, gy + 8), (gx, gy + 8)], w=0.15))
out.append(txt("\u22651", gx + 3, gy + 1.8, 1.2, 0.18))
for dy, nm in ((1.6, "PTT1"), (3.2, "PTT2"), (4.8, "PTT3"), (6.4, "PTT4")):
    out.append(line(gx - 2.5, gy + dy, gx, gy + dy, w=0.15)); out.append(txt(nm, gx - 2.8, gy + dy, 1.0, 0.15, just="right"))
out.append(line(gx + 6, gy + 4, gx + 9, gy + 4, w=0.15)); out.append(txt("TX_ANY", gx + 9.4, gy + 4, 1.0, 0.15, just="left"))
tx, ty = gx + 24.0, gy + 0.6            # truth table: PTT4..PTT1 -> TX_ANY
out.append(txt("PTT4..1", tx, ty, 1.0, 0.15)); out.append(txt("Y", tx + 6.2, ty, 1.0, 0.15))
for r, bits in enumerate(("0000", "0001", "0110", "1111")):
    out.append(txt(bits, tx, ty + 1.8 + 1.6 * r, 1.0, 0.15)); out.append(txt("0" if bits == "0000" else "1", tx + 6.2, ty + 1.8 + 1.6 * r, 1.0, 0.15))
out.append(line(tx - 3.2, ty + 0.9, tx + 7.3, ty + 0.9, w=0.15)); out.append(line(tx + 4.6, ty - 0.7, tx + 4.6, ty + 7.9, w=0.15))
# Back: stackup legend and warning (no JLC order-number marker: discontinued by JLCPCB in May 2026)
for i, t in enumerate(["JLC06161H-7628A  1.6 mm  6 layers  1 oz outer",
                       "L1 RF  L2 GND  L3 SIG  L4 GND  L5 PWR  L6 GND",
                       "RF: 1.0 mm, gap 1.25 mm, about 50 ohm",
                       "Conformal coating on the connector fields"]):
    out.append(txt(t, 330.0, 4.0 + 1.8 * i, 1.0, 0.15, layer="B.SilkS", just="left mirror"))
out.append(hv_warning(305.0, 84.0).replace('"F.SilkS"', '"B.SilkS"'))
for j, lab in ((J14, "+5V"), (J12, "+12V RLY"), (J13, "+12V AUX")):
    out.append(txt(lab, j[0] + (-2.5 if lab == "+5V" else 3.6), 24.0, 1.0, 0.15))

# ---------------- write ----------------
old = open("backplane.kicad_pcb").read()
general = '\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n'
layers = open("../../test-pieces/rf-isolation/kicad/rf-iso-card/rf-iso-card.kicad_pcb").read()
lay = re.search(r"\t\(layers\n.*?\n\t\)\n", layers, re.S).group(0)
lay = lay.replace('\t\t(4 "In1.Cu" signal)\n\t\t(6 "In2.Cu" signal)\n',
                  '\t\t(4 "In1.Cu" signal)\n\t\t(6 "In2.Cu" signal)\n\t\t(8 "In3.Cu" signal)\n\t\t(10 "In4.Cu" signal)\n')
def L(name, typ, th, er=None, mat=None):
    e = f" (material \"{mat}\") (epsilon_r {er}) (loss_tangent 0.02)" if er else ""
    return f'\t\t\t(layer "{name}" (type "{typ}") (thickness {th}){e})\n'
stack = ('\t\t(stackup\n\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))\n\t\t\t(layer "F.Paste" (type "Top Solder Paste"))\n'
         + L("F.Mask", "Top Solder Mask", 0.01) + L("F.Cu", "copper", 0.035)
         + L("dielectric 1", "prepreg", 0.5124, 4.33, "7628 + 7628 + 1080") + L("In1.Cu", "copper", 0.0152)
         + L("dielectric 2", "core", 0.1, 4.6, "FR4") + L("In2.Cu", "copper", 0.0152)
         + L("dielectric 3", "prepreg", 0.2328, 4.16, "2116 + 2116") + L("In3.Cu", "copper", 0.0152)
         + L("dielectric 4", "core", 0.1, 4.6, "FR4") + L("In4.Cu", "copper", 0.0152)
         + L("dielectric 5", "prepreg", 0.5124, 4.33, "1080 + 7628 + 7628") + L("B.Cu", "copper", 0.035)
         + L("B.Mask", "Bottom Solder Mask", 0.01)
         + '\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))\n\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))\n'
         '\t\t\t(copper_finish "ENIG")\n\t\t\t(dielectric_constraints no)\n\t\t)\n')
setup = re.search(r"\t\(setup\n.*?\n\t\)\n", layers, re.S).group(0)
setup = re.sub(r"\t\t\(stackup\n.*?\n\t\t\)\n", "", setup, flags=re.S)
setup = setup.replace("\t(setup\n", "\t(setup\n" + stack, 1)
C = ["Design: Prins Doornekamp, PE1RGU",
     "J1 to J11 HARTING 09 03 296 6824. J12, J13 XT60PW-M, J14 XT30PW-M",
     "RF on L1: 1.0 mm, gap 1.25 mm, about 50 ohm. Pin fields: L3 + L5, 0.45 mm",
     "JLC06161H-7628A, 1.6 mm, 6 layers, 1 oz outer. L2 L4 L6 GND"]
tb = ('\t(title_block\n\t\t(title "Backplane: Shack Relay Matrix")\n\t\t(date "2026-09-26")\n\t\t(rev "A")\n'
      '\t\t(company "PE1RGU - Shack Relay Matrix")\n' + "".join(f'\t\t(comment {i+1} "{c}")\n' for i, c in enumerate(C)) + "\t)\n")
edge = (f'\t(gr_rect\n\t\t(start 0 0)\n\t\t(end {F(BW)} {F(BH)})\n\t\t(stroke\n\t\t\t(width 0.1)\n\t\t\t(type solid)\n\t\t)\n'
        f'\t\t(fill no)\n\t\t(layer "Edge.Cuts")\n\t\t(uuid "{U()}")\n\t)\n')
pcb = ('(kicad_pcb\n\t(version 20260206)\n\t(generator "pcbnew")\n\t(generator_version "10.0")\n' + general +
       '\t(paper "A3")\n' + tb + lay + setup + edge + "".join(out) + ")\n")
if os.path.exists("backplane.kicad_pcb") and "footprint" in old:
    shutil.copy("backplane.kicad_pcb", "backplane.kicad_pcb.bak-gen")
open("backplane.kicad_pcb", "w").write(pcb)
print("footprints", 11 + 3 + len(HOLES), "tracks", len(tracks), "vias", len(vias), "fence", nf, "stitch", ns)
