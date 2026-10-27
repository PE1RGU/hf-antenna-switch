#!/usr/bin/env python3
"""RF board layout generator, increment p1 (board, nets, rules, outline, holes, placement of the large parts).
Run with the KiCad 10 Python from this folder:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 gen_rfboard_pcb.py
Input: rf-board.kicad_pcb (footprints from the schematic), ../verify/rf9.xml (netlist). Output: rf-board.kicad_pcb, and the
netclasses in rf-board.kicad_pro. The script can run again: it sets every pad net from the netlist, replaces the outline and
the board-only holes, and moves the footprints to the positions below.
Coordinates: board mm from the top left corner (as the placement study gen_relay_placement.py, D-23, C-12), y down.
Sources: D-115 (stackup JLC06161H-7628A, 6 layers), D-12/D-116 (RF W 0.975, gap 2.0), D-117 (inner antipads), D-14, D-15, D-21, D-23, D-102 (supports), D-105, D-110,
D-111 (DRC corrections), D-112 (coil drivers in the logic zone), D-113 (corner radius),
D-120 to D-122, D-127, D-129 (review against hardware-design-rules v2.2: test points, J14 filter, pull-down arrays, decoupling, bulk)."""
import json, math, os, re, sys
import xml.etree.ElementTree as ET
import pcbnew

REV = "p3-silk"
BOARD, PRO, NETLIST = "rf-board.kicad_pcb", "rf-board.kicad_pro", "../verify/rf14.xml"
OX, OY, BW, BH = 20.0, 20.0, 268.0, 230.0            # board origin on the sheet, board size (C-12)
FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
mm = pcbnew.FromMM
P = lambda x, y: pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))

b = pcbnew.LoadBoard(BOARD)

# ---- 1. nets from the netlist (the MCP import left the hierarchical instances without nets) ----
root = ET.parse(NETLIST).getroot()
pinnet = {}
for net in root.iter("net"):
    for n in net.iter("node"):
        pinnet[(n.get("ref"), n.get("pin"))] = net.get("name")
nets = {}
def net(name):
    if name not in nets:
        ni = b.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(b, name); b.Add(ni)
        nets[name] = ni
    return nets[name]
refs_nl = {c.get("ref") for c in root.iter("comp")}
REMOVED = []
for f in list(b.GetFootprints()):                     # 3D reference of the controller board, made new below on every run
    if f.GetReference() == "CTL3D":
        b.Remove(f); REMOVED.append(f)
for f in list(b.GetFootprints()):                     # supports S1 to S6 were board-only NPTH holes (p1); now schematic parts (D-132)
    if f.GetReference() in {f"S{i}" for i in range(1, 7)} and f.IsBoardOnly():
        b.Remove(f); REMOVED.append(f)
fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
for ref in sorted(set(fps) - {c.get("ref") for c in root.iter("comp")}):   # parts removed from the schematic (D-114: GDT)
    old = fps.pop(ref); b.Remove(old); REMOVED.append(old); print("removed", ref)
# parts new in the schematic (v11a: test points, J14 filter, arrays, capacitors): footprint from the library;
# values from the netlist for every part (v11a changed some decoupling values)
ADDED, KEEP0 = [], []
for c in root.iter("comp"):
    ref, val, fpid = c.get("ref"), c.findtext("value"), c.findtext("footprint")
    if ref in fps and fps[ref].GetFPIDAsString() != fpid:          # footprint changed in the schematic (D-133: PCA9539 to TSSOP-24)
        old = fps.pop(ref); b.Remove(old); REMOVED.append(old)
    if ref not in fps:
        lib, name = fpid.split(":")
        path = "rf-board.pretty" if lib == "rf-board" else f"{FPLIB}/{lib}.pretty"
        f = pcbnew.FootprintLoad(path, name)
        assert f is not None, fpid
        f.SetFPID(pcbnew.LIB_ID(lib, name))     # keep "lib:name", else the next run sees a changed footprint and loads it again
        f.SetReference(ref); b.Add(f); KEEP0.append(f); fps[ref] = f; ADDED.append(ref)
    props = {q.get("name") for q in c.iter("property")}
    fps[ref].SetValue(val)
    fps[ref].SetDNP("dnp" in props)
    fps[ref].SetExcludedFromBOM("exclude_from_bom" in props)
assert refs_nl <= set(fps), sorted(refs_nl - set(fps))
# 3D models that the KiCad 10 library does not install: Amass vendor STEP in hardware/unit/unit.3dshapes (THIRD-PARTY.md);
# offset and rotation as on the rev B backplane (same footprints, same files)
VENDOR_3D = {"AMASS_XT60PW-M_1x02_P7.20mm_Horizontal": ("AMASS_XT60PW-M.step", (3.6, 6.0, 0.0), (-90.0, 0.0, 180.0)),
             "AMASS_XT30PW-M_1x02_P2.50mm_Horizontal": ("AMASS_XT30PW-M.step", (-2.5, 10.0, 0.0), (-90.0, 0.0, 0.0)),
             # TE RTD14012F (C-2-1419108-9, Creo 2018): body modelled below z = 0 with the pins up, so turned 180 deg about x;
             # pins at x -12.15 / 3.11 / 8.15 / 13.19 and y -3.67 / +3.83 in the file, moved onto A1 (0, 0) ... NO (25.34, -7.5)
             "Relay_SPDT_Schrack-RT1-16A-FormC_RM5mm": ("RTD14012F.step", (12.15, 3.83, 0.0), (180.0, 0.0, 0.0))}
for fp in fps.values():
    v = VENDOR_3D.get(fp.GetFPID().GetLibItemName().wx_str())
    if v:
        m = fp.Models()[0]
        m.m_Filename = "${KIPRJMOD}/../unit.3dshapes/" + v[0]
        m.m_Offset = pcbnew.VECTOR3D(*v[1]); m.m_Rotation = pcbnew.VECTOR3D(*v[2])
used = set()
for ref, fp in fps.items():
    for pad in fp.Pads():
        k = (ref, pad.GetNumber())
        if k in pinnet:
            pad.SetNet(net(pinnet[k])); used.add(k)
        else:
            pad.SetNetCode(0)
missing = set(pinnet) - used
assert not missing, sorted(missing)[:10]

# ---- 2. board settings, stackup JLC06161H-7628A (D-115), title block ----
# L1 rows + GND pour, L2 GND, L3 coil lines / logic / rails, L4 GND, L5 GND, L6 columns + GND pour.
# The physical stackup (dielectric thicknesses, Er) is entered in Board Setup; values in rf-board.md section 4.
ds = b.GetDesignSettings()
b.SetCopperLayerCount(6)
ds.SetBoardThickness(mm(1.6))
tb = b.GetTitleBlock()
tb.SetTitle("Shack Relay Matrix rev C: RF board"); tb.SetRevision(REV); tb.SetCompany("PE1RGU")
tb.SetDate("2026-10-19"); tb.SetComment(0, "JLC06161H-7628A, 6 layers, 1.6 mm. RF CPWG W 0.975 / gap 2.0 mm, L1 and L6")
tb.SetComment(1, f"Generated by gen_rfboard_pcb.py {REV}; netlist {NETLIST}")

# ---- 3. outline (Edge.Cuts) ----
for d in list(b.GetDrawings()):
    if d.GetLayer() == pcbnew.Edge_Cuts:
        b.Remove(d); REMOVED.append(d)
RC = 5.0        # corner radius (D-113): fits a milled case corner radius up to about 15 mm with 0.5 mm play
KEEP = []                                      # keep the Python proxies alive: freeing them corrupts the SWIG type table
def edge(shape):
    shape.SetLayer(pcbnew.Edge_Cuts); shape.SetWidth(mm(0.1)); b.Add(shape); KEEP.append(shape)
for (x1, y1, x2, y2) in ((RC, 0, BW - RC, 0), (BW, RC, BW, BH - RC), (BW - RC, BH, RC, BH), (0, BH - RC, 0, RC)):
    l = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); l.SetStart(P(x1, y1)); l.SetEnd(P(x2, y2)); edge(l)
kc = RC * (1 - 0.5 ** 0.5)
for (sx, sy, mx, my, ex, ey) in ((0, RC, kc, kc, RC, 0), (BW - RC, 0, BW - kc, kc, BW, RC),
                                 (BW, BH - RC, BW - kc, BH - kc, BW - RC, BH), (RC, BH, kc, BH - kc, 0, BH - RC)):
    a = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_ARC); a.SetArcGeometry(P(sx, sy), P(mx, my), P(ex, ey)); edge(a)

# ---- 4. supports S1 to S6 (D-102): plated M3 holes, each on its own net CHASSIS_Sn (D-132, D-162), placed in section 5 ----
SUPPORTS = [("S1", 5, 5), ("S2", 149, 5), ("S3", 263, 5), ("S4", 46, 116.5), ("S5", 99, 116.5), ("S6", 263, 116.5)]

# ---- 5. placement ----
def place(ref, x, y, rot=0.0, side="F"):
    """Place the footprint origin at board (x, y)."""
    fp = fps[ref]
    if (side == "B") != fp.IsFlipped():
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetOrientationDegrees(rot); fp.SetPosition(P(x, y))
def place_cy(ref, x, y, rot=0.0):
    """Place so that the courtyard top left corner sits at board (x, y)."""
    fp = fps[ref]
    place(ref, 0, 0, rot)
    cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    o = fp.GetPosition()
    fp.SetPosition(pcbnew.VECTOR2I(mm(OX + x) + (o.x - cy.GetX()), mm(OY + y) + (o.y - cy.GetY())))

for ref, x, y in SUPPORTS:
    place(ref, x, y)
RT1_CY = 0.3                                   # RT1 courtyard is 0.3 mm outside the body (probe of the footprint)
AX = [103 + 38 * k for k in range(4)]          # antenna cell x0 (study), column line at AX + 36
ALINE = [x + 36 for x in AX]                   # 139, 177, 215, 253 = antenna SO-239 axes (D-23)
placed = set(r for r, _, _ in SUPPORTS)
def relay(ref, bx, by, rot=0.0):
    place_cy(ref, bx - RT1_CY, by - RT1_CY, rot); placed.add(ref)

for r in range(3):                             # radio blocks R1 to R3, 48 mm each
    y0 = 38 + 48 * r
    n = 100 * (r + 1)
    relay(f"K{n+1:03d}", 38, y0 + 1)           # K0
    relay(f"K{n+6:03d}", 8, y0 + 1)            # EXP TX (x 8: clear of the SMA land, D-111)
    relay(f"K{n+11:03d}", 8, y0 + 25)          # EXP RX
    for k in range(4):
        relay(f"K{n+2+k:03d}", AX[k] + 1, y0 + 1)    # TX A1..A4 (A2 not fitted, D-103)
        relay(f"K{n+7+k:03d}", AX[k] + 1, y0 + 25)   # RX A1..A4
for k in range(4):                             # K1 antenna relays, upright, left of the column (study)
    relay(f"K{4+k}01", ALINE[k] - 19, 189, 90)       # NO at the top, next to the column link (p1b)

for i, x in enumerate((12, 42, 72)):           # radio SO-239 on the bottom edge (D-21)
    place(f"J{1+i}", x, BH); placed.add(f"J{1+i}")
for k, x in enumerate(ALINE):                  # antenna SO-239 under the columns; J10 boss on the left (D-105)
    place(f"J{7+k}", x, BH); placed.add(f"J{7+k}")
for r in range(3):                             # EXP SMA on the left edge, between the TX and RX rows (D-110)
    place(f"J{4+r}", 0, 38 + 48 * r + 23.5, 270); placed.add(f"J{4+r}")
# power entry on the top edge: mating face on the board edge (courtyard front about 16.9 / 13.6 mm before pin 1)
place("J11", 96, 16.6); place("J12", 126, 16.6); place("J13", 165, 13.4)
placed |= {"J11", "J12", "J13"}
place("J14", 60, 12, 90); placed.add("J14")    # header to the controller board (provisional, D-51)

# ---- 6. coil drivers in the logic zone (D-112): one cell per relay, above its relay column ----
def drv(n):                                    # relay K<n> -> its driver: Q, R (gate pull-down), D (clamp diode)
    if n >= 400:                               # antenna port K<a>01: Q<a>01, R<a>06, D<a>02 (antenna_port sheet)
        return [f"Q{n}", f"R{n + 5}", f"D{n + 1}"]
    return [f"Q{n}", f"R{n}", f"D{n}"]         # radio port: same number as the relay
def driver_cell(n, x):
    q, rr, d = drv(n)
    place(rr, x, 24.5, 90); place(q, x, 29.0, 0); place(d, x, 34.4, 90)
    placed.update((q, rr, d))
PITCH = 4.5
cells = [(10.5, [106, 111, 206, 211, 306, 311]), (40.5, [101, 201, 301])]
for k in range(4):
    cells.append((AX[k] + 4, [102 + k, 107 + k, 202 + k, 207 + k, 302 + k, 307 + k, 401 + 100 * k]))
for x0, ns in cells:
    for i, n in enumerate(ns):
        driver_cell(n, x0 + i * PITCH)

# ---- 7. power entry: fuse and TVS at each connector (D-45) ----
# stacked from the edge band down, so the bulk capacitor fits in the same gap; D8 upright to stay clear of the S2 washer
for ref, (x, y, rt) in {"F1": (111, 3.5, 0), "D7": (111, 6.45, 0), "F2": (138.6, 3.5, 0), "D8": (138.6, 6.45, 90),
                        "F3": (171, 3.5, 0), "D9": (171, 6.45, 0)}.items():
    place_cy(ref, x, y, rt); placed.add(ref)
for r in range(3):    # +12V_SW decoupling per radio block (D-127): bottom side under the EXP TX relay, next to its coil pin A1
    place(f"C{100 * (r + 1) + 1}", 16.0, 38 + 48 * r + 7.5, 0, side="B"); placed.add(f"C{100 * (r + 1) + 1}")

# antenna ports: the column link on the column line, the rest right of the column (D-109)
# K1 (rotation 90): NO pins y 190.5, COM 195.5, NC 200.6, coil 215.8, at x c-16.2 and c-8.7 (probe of the footprint).
# Column (L2) ends at the link R<n>02 on the column line; PORT runs left to the K1 NO pins; ANTENNA from K1 COM to x = c and
# down to the SO-239; PARK from the K1 NC pins on L2 to the bleed. Detector above K1, left of the column; C401 / L402 / C402,
# bleed right of the column (no GDT since D-114), with 2.0 mm from every RF pad of another net (D-12).
for k in range(4):
    c = ALINE[k]; n = 4 + k
    pl = lambda ref, x, y, rot=0: (place(ref, x, y, rot), placed.add(ref))
    # p2b (Prins): pad 2 of the link level with the K1 NO pins (y 190.505), so PORT runs straight; pad 1 at y 182.885 in one
    # line with the detector tap and the DC block; DC block, bias choke and bias decoupling on one vertical line at c + 5.5
    pl(f"R{n}02", c, 182.885, 270)              # column link (wire), pads at y 182.885 and 190.505
    pl(f"C{n}01", c + 5.5, 185.023, 270)        # DC block (not fitted): pad 1 (ANT) at y 182.885
    pl(f"L{n}02", c + 5.5, 193.6, 90)           # bias choke: pad 2 (PORT) at the top, pad 1 (BIAS) below (not fitted)
    pl(f"C{n}02", c + 5.5, 199.6, 270)          # bias decoupling: pad 1 (BIAS) at the top (not fitted)
    pl(f"C{n}04", c - 8.5, 182.885, 180)        # detector tap: pad 1 (ANT) towards the column, level with the link pad 1
    pl(f"D{n}01", c - 14.0, 182.6, 0)           # BAS70-04 doubler
    for i, ref in enumerate((f"C{n}05", f"C{n}03", f"R{n}04", f"R{n}05")):
        pl(ref, c - 19.8 + 3.5 * i, 187.0, 0)        # p2b: 2.0 mm from the detector tap ANT pad and the K1 NO pins (D-12)
    pl(f"R{n}01", c + 9.8, 200.585, 270)        # p2b: pad 1 level with the K1 NC pins (PARK ends at the pad centre)          # bleed: pad 1 (PARK) level with the K1 NC pins (no GDT since D-114)
# ---- 8. functional placement (p1g, hardware-design-rules v2.3 pcb-layout.md placement checklist) ----
# Each group has one anchor (an IC or a connector part) at a fixed place. The other parts follow in the given order. Each
# part goes next to the pad it connects to: decoupling at the supply pin, arrays and pull-ups at their IO pins, the J14
# filter at the J14 pins. Candidate positions lie outward from that pad, then sideways; the best one is the closest pad
# distance with no courtyard overlap (gap GAP for the soldering iron), inside the group region. The regions keep the
# edge band (EDGE: GND strip and via fence, D-119), the standoff keep-outs (8 mm washer, D-102) and the RF bands free.
EDGE, GAP = 3.5, 0.6
POWER_NETS = {"GND", "+3V3", "+5V", "+12V_RLY", "+12V_SW", "+12V_AUX", "CHASSIS"}
def cy_mm(fp):
    c = fp.GetCourtyard(pcbnew.F_CrtYd if not fp.IsFlipped() else pcbnew.B_CrtYd).BBox()
    return (pcbnew.ToMM(c.GetX()) - OX, pcbnew.ToMM(c.GetY()) - OY, pcbnew.ToMM(c.GetRight()) - OX, pcbnew.ToMM(c.GetBottom()) - OY)
def pad_mm(pad):
    q = pad.GetPosition(); return (pcbnew.ToMM(q.x) - OX, pcbnew.ToMM(q.y) - OY)
OBST = [cy_mm(fps[r]) for r in placed if not fps[r].IsFlipped()]
OBST += [(x - 4.0, y - 4.0, x + 4.0, y + 4.0) for (_, x, y) in SUPPORTS]       # washer keep-out of each support
def free(bb, obst):
    return all(bb[2] + GAP <= o[0] or bb[0] >= o[2] + GAP or bb[3] + GAP <= o[1] or bb[1] >= o[3] + GAP for o in obst)
def inside(bb, reg):
    return bb[0] >= reg[0] and bb[1] >= reg[1] and bb[2] <= reg[2] and bb[3] <= reg[3]
IDX = {}                                     # ref -> its courtyard entry in OBST (the alignment pass moves it)
def fix(ref, x, y, rot=0.0):
    place(ref, x, y, rot); placed.add(ref); IDX[ref] = len(OBST); OBST.append(cy_mm(fps[ref]))
def fan_keep(ref, ext=1.9):
    """Keep-out for the fan-out vias of a TSSOP (D-161, gen_rfboard_copper.py): the pad rows plus ext mm along the pad axis."""
    bbs = [pd.GetBoundingBox() for pd in fps[ref].Pads()]
    x0, y0 = min(pcbnew.ToMM(q.GetX()) for q in bbs) - OX, min(pcbnew.ToMM(q.GetY()) for q in bbs) - OY
    x1, y1 = max(pcbnew.ToMM(q.GetRight()) for q in bbs) - OX, max(pcbnew.ToMM(q.GetBottom()) for q in bbs) - OY
    horiz = bbs[0].GetWidth() > bbs[0].GetHeight()
    OBST.append((x0 - ext, y0, x1 + ext, y1) if horiz else (x0, y0 - ext, x1, y1 + ext))
def satellite(ref, group, reg, want=None):
    """Place ref next to the pad of a part in group that shares a net with it.
    want: None (any signal net), a net name, or ("pad", number) for that pad of the anchor (for example VDD pin 24)."""
    fp = fps[ref]
    own = {pd.GetNetname() for pd in fp.Pads()}
    targets = []
    for g in (group[:1] if isinstance(want, tuple) else group):
        cx = sum(cy_mm(fps[g])[0::2]) / 2; cyy = sum(cy_mm(fps[g])[1::2]) / 2
        for pd in fps[g].Pads():
            n = pd.GetNetname()
            base = n.rsplit("/", 1)[-1]                        # local nets carry the sheet path ("/Power, .../CHASSIS")
            ok = (pd.GetNumber() == want[1]) if isinstance(want, tuple) else (base == want if want else base not in POWER_NETS)
            if n in own and ok:
                targets.append((n, pad_mm(pd), (cx, cyy)))
    assert targets, f"{ref}: no target pad in {group} (net {want})"
    best = None
    obst = [o for o in OBST if o[2] > reg[0] - 2 and o[0] < reg[2] + 2 and o[3] > reg[1] - 2 and o[1] < reg[3] + 2]
    for rot in (0, 90, 180, 270):
        place(ref, 0, 0, rot)
        bb0 = cy_mm(fp); fx, fy = pcbnew.ToMM(fp.GetPosition().x) - OX, pcbnew.ToMM(fp.GetPosition().y) - OY
        for n, (tx, ty), (cx, cyy) in targets:
            cp = next(pd for pd in fp.Pads() if pd.GetNetname() == n)
            px, py = pad_mm(cp)
            vx, vy = tx - cx, ty - cyy                       # outward from the target part
            if abs(vx) < 0.5 and abs(vy) < 0.5: out = None                      # pad in the centre (hole)
            elif abs(vx) >= abs(vy): out = ((1 if vx >= 0 else -1), 0)
            else: out = (0, (1 if vy >= 0 else -1))
            # outward from the part first; the other three directions cost 3 mm extra in the score
            dirs = [((1, 0), 0.0), ((-1, 0), 0.0), ((0, 1), 0.0), ((0, -1), 0.0)] if out is None else \
                   [(out, 0.0)] + [(u, 3.0) for u in ((1, 0), (-1, 0), (0, 1), (0, -1)) if u != out]
            for ((ux, uy), pen), d10 in ((u, d) for u in dirs for d in range(10, 160, 4)):   # 1.0 to 16 mm out
                if best is not None and d10 / 10 + pen > best[0]: continue
                for l10 in sorted(range(-140, 141, 6), key=abs):
                    d, l = d10 / 10, l10 / 10
                    qx, qy = tx + ux * d - uy * l, ty + uy * d + ux * l     # wanted position of the connecting pad
                    dx, dy = qx - px, qy - py
                    bb = (bb0[0] + dx, bb0[1] + dy, bb0[2] + dx, bb0[3] + dy)
                    if not inside(bb, reg) or not free(bb, obst): continue
                    score = d + 0.6 * abs(l) + pen
                    if best is None or score < best[0]:
                        best = (score, rot, fx + dx, fy + dy)
                    break
    assert best, f"{ref}: no free place in {reg}; targets {[(t[0], t[1]) for t in targets]}; near: " + \
        str([(r_, tuple(round(v, 1) for v in cy_mm(fps[r_]))) for r_ in group])
    fix(ref, best[2], best[3], best[1])
PGRID, ATOL = 0.5, 1.5                       # placement grid and alignment tolerance, mm (D-158 applied to the satellites, M-77)
def pos(ref):
    q = fps[ref].GetPosition(); return pcbnew.ToMM(q.x) - OX, pcbnew.ToMM(q.y) - OY
def try_move(ref, x, y, reg):
    """Move ref to (x, y) when its courtyard stays in reg and free of all other courtyards and keep-outs."""
    (x0, y0), k = pos(ref), IDX[ref]
    place(ref, x, y, fps[ref].GetOrientationDegrees()); bb = cy_mm(fps[ref])
    if inside(bb, reg) and free(bb, OBST[:k] + OBST[k + 1:]):
        OBST[k] = bb; return True
    place(ref, x0, y0, fps[ref].GetOrientationDegrees()); return False
def align(g, reg):
    """D-158 for the automatic placement: snap the satellites to the placement grid, then put parts whose centres lie
    within ATOL of each other on one horizontal line and on one vertical line (the anchor, or the first part, sets the line)."""
    sat = g[1:]
    for r in sat:
        x, y = pos(r); try_move(r, round(x / PGRID) * PGRID, round(y / PGRID) * PGRID, reg)
    for ax in (1, 0):                                         # rows (y) first, then columns (x)
        done = set()
        for r in sorted(g, key=lambda r: (r != g[0], pos(r)[ax])):
            if r in done: continue
            line = pos(r)[ax]
            near = [q for q in g if q not in done and q != g[0] and abs(pos(q)[ax] - line) <= ATOL]
            done.add(r)
            for q in near:
                if q == r: continue
                x, y = pos(q)
                if try_move(q, line if ax == 0 else x, line if ax == 1 else y, reg): done.add(q)
    # a test point (one pad) goes on the line of the nearest pad of its net in the group, so that the track passes
    # through its centre or reaches it straight (Prins, 2026-10-24: TP4 beside the +12V_SW track)
    for r in sat:
        pads_ = list(fps[r].Pads())
        if len(pads_) != 1 or not pads_[0].GetNetname(): continue
        n_ = pads_[0].GetNetname(); px, py = pad_mm(pads_[0])
        cand = [pad_mm(p_) for q in g if q != r for p_ in fps[q].Pads() if p_.GetNetname() == n_]
        if not cand: continue
        tx, ty = min(cand, key=lambda c: math.hypot(c[0] - px, c[1] - py))
        x, y = pos(r)
        if abs(tx - px) <= ATOL and try_move(r, x + tx - px, y, reg): continue
        if abs(ty - py) <= ATOL: try_move(r, x, y + ty - py, reg)
def group(anchor_ref, members, reg, at=None, rot=0.0):
    if at: fix(anchor_ref, at[0], at[1], rot)
    g = [anchor_ref]
    for m in members:
        ref, want = (m if isinstance(m, tuple) else (m, None))
        satellite(ref, g, reg, want); g.append(ref)
    align(g, reg)

# bulk and test points at the 12 V entries (D-129, D-120)
group("F1", [("C6", "+12V_RLY"), ("TP1", "+12V_RLY")], (107.9, EDGE, 121.0, 22.3))
group("F2", [("C7", "+12V_AUX"), ("TP2", "+12V_AUX")], (138.2, EDGE, 155.0, 22.3))
# bond option per support (D-132), next to its support, outside the washer keep-out
for sref, cref in zip(("S1", "S2", "S3", "S4", "S5", "S6"), ("C8", "C9", "C10", "C11", "C12", "C13")):
    sx, sy = next((x, y) for (r_, x, y) in SUPPORTS if r_ == sref)
    group(sref, [(cref, f"CHASSIS_{sref}")], (max(EDGE, sx - 14), max(EDGE, sy - 14), min(BW - EDGE, sx + 14), min(BH - EDGE, sy + 14)))
# logic zone, left of J14: the three expanders with decoupling (VDD pin 24), arrays (IO1_6, IO1_7), bus pull-ups at U901
R_EXP = (EDGE, EDGE, 56.8, 22.3)
for k, x in ((1, 12.5), (2, 30.0), (3, 47.5)):        # all three with their fan-out keep-out first, then the satellites; 17.5 mm apart for the escape channels with return vias (M-79)
    fix(f"U90{k}", x, 13.0); fan_keep(f"U90{k}")
for k in (1, 2, 3):
    m = [(f"C90{k}", ("pad", "24")), f"RN90{k}"] + (["R901", "R902", "R903"] if k == 1 else []) + (["R904"] if k == 3 else [])
    group(f"U90{k}", m, R_EXP)
# J14 crossing filter (D-122): series link at the J14 pin, C and test point on the logic side of the link
group("J14", [f"R120{i}" for i in range(1, 10)] + [f"C120{i}" for i in range(1, 10)] +
      [f"TP120{i}" for i in (1, 2, 3, 4, 5, 9)], (56.8, EDGE, 90.8, 22.3))
# right of J13: 3.3 V LDO with its capacitors and link, the +12V_SW switch with clamps and freewheel, the CHASSIS bond
R_RIGHT = (176.5, EDGE, BW - EDGE, 22.3)
group("U1", [("C3", "+5V"), "C4", "C5", "R4", ("TP5", "+3V3"), ("TP3", "+5V")], R_RIGHT, at=(184.0, 12.0))
group("Q1", ["R1", "D6", "C2", "R2", "Q2", ("R3", "RLY_EN"), ("D1", "+12V_SW"), ("D2", "+12V_SW"), ("D4", "+12V_SW"),
             ("D3", "+12V_RLY"), ("D5", "+12V_RLY"), ("TP4", "+12V_SW")], R_RIGHT, at=(212.0, 12.0))
# D-158 by hand (Prins, 2026-10-24): Q1 drain (pin 3), TP4 and the D2 cathode (+12V_SW) on one vertical line; R3 steps right
# to make room for TP4
def on_line(ref, num, x_line, reg):
    p_ = next(p for p in fps[ref].Pads() if p.GetNumber() == num); x, y = pos(ref)
    return try_move(ref, x + x_line - pad_mm(p_)[0], y, reg)
XQ1 = pad_mm(next(p for p in fps["Q1"].Pads() if p.GetNumber() == "3"))[0]
x_, y_ = pos("R3")
print("Q1 line:", try_move("R3", x_ + 0.7, y_, R_RIGHT), on_line("D2", "2", XQ1, R_RIGHT), on_line("TP4", "1", XQ1, R_RIGHT))
group("H1", [("JP1", "CHASSIS"), ("C1", "CHASSIS")], R_RIGHT, at=(246.0, 12.0))
# bias-T supply (D-54) below radio block 3: U1001 with decoupling and arrays, then one block per antenna port
R_BIAS = (EDGE, 181.0, 68.0, 209.0)          # RX row band of R3 ends at about y 180, R3 feed band starts at x 68.4
fix("U1001", 9.5, 195.0, 90); fan_keep("U1001")
group("U1001", [("C1001", ("pad", "24")), "RN1001", "RN1002"], (EDGE, 181.0, 16.5, 209.0))
for k in range(1, 5):
    x1 = 16.5 + 12.875 * (k - 1); x2 = x1 + 12.875
    n = 1000 + 10 * k
    # switch Q2, sense R1 and limiter Q1, gate network R2 R3, drive Q3 with R4, output TVS D1 and C1, read-back R5 R6
    group(f"Q{n + 2}", [f"R{n + 1}", f"Q{n + 1}", f"R{n + 2}", f"R{n + 3}", f"Q{n + 3}", f"R{n + 4}", f"D{n + 1}",
                        f"C{n + 1}", f"R{n + 5}", f"R{n + 6}"], (x1, 181.0, x2, 209.0), at=((x1 + x2) / 2, 186.0))
# RF detect (D-47) between the feed bands and K401: LM2901 with decoupling, reference divider and the four channels
group("U801", [("C802", ("pad", "3")), "R811", "R812", "R813", "R814", "R821", "R822", "R823", "R824", "R831", "R832", "R833",
               "R834", "R801", "R802", "C801"], (94.0, 181.0, 119.3, 221.0), at=(106.5, 199.0))
left = [c.get("ref") for c in root.iter("comp") if c.get("ref") not in placed]
assert not left, left
# ---- 9. controller board as a 3D reference (M-54): board-only footprint without pads at the frame origin (0, 0).
# The STEP comes from kicad-cli pcb export step of controller-board.kicad_pcb (same frame and page offset): file X = page x,
# file Y = -page y, z = 0 at the controller board underside. Offset z = 20 mm standoff from the RF board top (M-53).
CTL_GAP = 20.0
ctl = pcbnew.FOOTPRINT(b); ctl.SetReference("CTL3D"); ctl.SetValue("controller board 3D (reference only)")
ctl.SetBoardOnly(True); ctl.SetExcludedFromBOM(True); ctl.SetExcludedFromPosFiles(True)
ctl.Reference().SetVisible(False); ctl.Value().SetVisible(False)
m3 = pcbnew.FP_3DMODEL(); m3.m_Filename = "${KIPRJMOD}/../unit.3dshapes/controller-board.step"
m3.m_Offset = pcbnew.VECTOR3D(-OX, OY, CTL_GAP); ctl.Add3DModel(m3)
b.Add(ctl); KEEP0.append(ctl); ctl.SetPosition(P(0, 0))
# ---- 10. RF copper, return and fence vias, GND pours (p2, gen_rfboard_copper.py) ----
exec(open("gen_rfboard_copper.py").read())
# ---- 11. tracks and vias from the grid router (p2c): routing/routes.json, made by routing/grid_router.py from routing/geom.json
# (routing/export_geom.py). Run with --no-routes before export_geom.py (old tracks on a changed board can give new vias a wrong net).
ROUTES = "routing/routes.json"
if os.path.exists(ROUTES) and "--no-routes" not in sys.argv:
    rj = json.load(open(ROUTES))
    assert not rj["failed"], [f["net"] for f in rj["failed"]]
    LYR = {"F": pcbnew.F_Cu, "In2": pcbnew.In2_Cu, "In3": pcbnew.In3_Cu, "B": pcbnew.B_Cu}
    for t in rj["tracks"]:
        tr_ = pcbnew.PCB_TRACK(b); tr_.SetStart(P(t["x1"], t["y1"])); tr_.SetEnd(P(t["x2"], t["y2"])); tr_.SetWidth(mm(t["w"]))
        tr_.SetLayer(LYR[t["layer"]]); tr_.SetNet(net(t["net"])); b.Add(tr_); KEEP.append(tr_)
    for v in rj["vias"]:
        vi = pcbnew.PCB_VIA(b); vi.SetPosition(P(v["x"], v["y"])); vi.SetWidth(mm(v["d"])); vi.SetDrill(mm(v["drill"]))
        vi.SetNet(net(v["net"])); b.Add(vi); KEEP.append(vi)
    # a fan-out via that the routes reach on F.Cu only is not needed: the F.Cu route joins the stub directly (DRC via_dangling)
    n_rm = 0
    for (vx, vy), v in FOVIA.items():
        inner = any(t["layer"] != "F" and min(math.hypot(t["x1"] - vx, t["y1"] - vy), math.hypot(t["x2"] - vx, t["y2"] - vy)) < 0.35
                    for t in rj["tracks"]) or any(math.hypot(w_["x"] - vx, w_["y"] - vy) < 0.35 for w_ in rj["vias"])
        if not inner: b.Remove(v); REMOVED.append(v); n_rm += 1
    print("routes", len(rj["tracks"]), "tracks", len(rj["vias"]), "vias; fan-out vias not needed, removed:", n_rm)
    # GND stitching (p2d, D-119, M-79): routing/stitch.json from routing/stitch.py (edge fence, 5 mm grid, return vias the
    # router could not place); return vias placed by the router are in routes.json with net GND
    if os.path.exists("routing/stitch.json"):
        sj = json.load(open("routing/stitch.json"))
        for v in sj["vias"]:
            vi = pcbnew.PCB_VIA(b); vi.SetPosition(P(v["x"], v["y"])); vi.SetWidth(mm(0.6)); vi.SetDrill(mm(0.3))
            vi.SetNet(net("GND")); b.Add(vi); KEEP.append(vi)
        print("stitching vias", len(sj["vias"]), "| signal vias without a GND via within 3 mm:", len(sj["missing_return"]))
# ---- 12. silkscreen p3 (skill schematic-and-marking.md, D-152): labels, HV warnings, art block with the board signature,
# stackup legend on the back, then every reference placed clear of pads, silk and the other texts. Text 1.0 mm, line 0.15 mm.
SH, ST = 1.0, 0.15
for d in list(b.GetDrawings()):                      # this section owns all board-level silk: clear the previous run
    if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
        b.Remove(d); REMOVED.append(d)
X0s, Y0s, X1s, Y1s = 0.0, 0.0, BW, BH
def bx(box, m=0.0):
    return (pcbnew.ToMM(box.GetX()) - OX - m, pcbnew.ToMM(box.GetY()) - OY - m,
            pcbnew.ToMM(box.GetRight()) - OX + m, pcbnew.ToMM(box.GetBottom()) - OY + m)
def hit(a, c): return a[0] < c[2] and c[0] < a[2] and a[1] < c[3] and c[1] < a[3]
SILK = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
def text(s, x, y, side="F", h=SH, t=ST, rot=0.0, just="c"):
    o = pcbnew.PCB_TEXT(b); o.SetText(s); ly = pcbnew.F_SilkS if side == "F" else pcbnew.B_SilkS; o.SetLayer(ly)
    o.SetTextSize(pcbnew.VECTOR2I(mm(h), mm(h))); o.SetTextThickness(mm(t)); o.SetTextAngleDegrees(rot)
    o.SetHorizJustify({"l": pcbnew.GR_TEXT_H_ALIGN_LEFT, "r": pcbnew.GR_TEXT_H_ALIGN_RIGHT, "c": pcbnew.GR_TEXT_H_ALIGN_CENTER}[just])
    if side == "B": o.SetMirrored(True)
    o.SetPosition(P(x, y)); b.Add(o); KEEP.append(o); SILK[ly].append(bx(o.GetBoundingBox())); return o
def sline(xa, ya, xb, yb, side="F"):
    ly = pcbnew.F_SilkS if side == "F" else pcbnew.B_SilkS
    l = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); l.SetStart(P(xa, ya)); l.SetEnd(P(xb, yb)); l.SetLayer(ly)
    l.SetWidth(mm(ST)); b.Add(l); KEEP.append(l); SILK[ly].append(bx(l.GetBoundingBox(), 0.1))
def scircle(x, y, r, side="F"):
    ly = pcbnew.F_SilkS if side == "F" else pcbnew.B_SilkS
    c = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_CIRCLE); c.SetCenter(P(x, y)); c.SetEnd(P(x + r, y)); c.SetLayer(ly)
    c.SetWidth(mm(ST)); b.Add(c); KEEP.append(c); SILK[ly].append(bx(c.GetBoundingBox(), 0.1))
def obstacles(side_cu, side_silk, side_crt):
    pads, silk, crt = [], [], []
    for f in fps.values():
        for pd in f.Pads():
            if pd.IsOnLayer(side_cu): pads.append(bx(pd.GetBoundingBox(), 0.25))
        for g in f.GraphicalItems():
            if g.GetLayer() == side_silk and g.Type() in (pcbnew.PCB_SHAPE_T, pcbnew.PCB_TEXT_T) and (g.Type() != pcbnew.PCB_TEXT_T or g.IsVisible()):
                silk.append(bx(g.GetBoundingBox(), 0.1 if g.Type() == pcbnew.PCB_SHAPE_T else 0.5))   # footprint silk drawings and texts such as (+) (-)
        cy_ = f.GetCourtyard(side_crt)
        if cy_.OutlineCount(): crt.append((f, bx(cy_.BBox())))
    return pads, silk, crt
OBS = {"F": obstacles(pcbnew.F_Cu, pcbnew.F_SilkS, pcbnew.F_CrtYd), "B": obstacles(pcbnew.B_Cu, pcbnew.B_SilkS, pcbnew.B_CrtYd)}
RFT = {"F": [], "B": []}                                       # RF copper on the outer layers: art and labels keep 1 mm off
for t in b.GetTracks():
    if t.Type() == pcbnew.PCB_TRACE_T and is_rf(t.GetNetname()) and t.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
        RFT["F" if t.GetLayer() == pcbnew.F_Cu else "B"].append(bx(t.GetBoundingBox(), 1.0))
def free_box(box, side="F", crt_too=True):
    pads, silk, crt = OBS[side]; ly = pcbnew.F_SilkS if side == "F" else pcbnew.B_SilkS
    if box[0] < X0s + 3.5 or box[2] > X1s - 3.5 or box[1] < Y0s + 3.5 or box[3] > Y1s - 3.5: return False
    if any(hit(box, o) for o in pads + silk + SILK[ly] + RFT[side]): return False
    return not (crt_too and any(hit(box, c) for _, c in crt))
def find_spot(w, h, near, side="F", step=1.0, rmax=60.0):
    """centre of the nearest free w x h box to 'near' (spiral on a grid)"""
    cand = sorted(((near[0] + i * step, near[1] + j * step) for i in range(-int(rmax / step), int(rmax / step) + 1)
                   for j in range(-int(rmax / step), int(rmax / step) + 1)), key=lambda c: math.hypot(c[0] - near[0], c[1] - near[1]))
    return next(((x, y) for (x, y) in cand if free_box((x - w / 2, y - h / 2, x + w / 2, y + h / 2), side)), None)
def tsize(s, rot=0.0, h=SH, t=ST):
    """measured size of a silk text (a temporary object, not added to the board)"""
    o = pcbnew.PCB_TEXT(b); o.SetText(s); o.SetLayer(pcbnew.F_SilkS); o.SetTextSize(pcbnew.VECTOR2I(mm(h), mm(h)))
    o.SetTextThickness(mm(t)); o.SetTextAngleDegrees(rot); o.SetPosition(P(0, 0)); bb = bx(o.GetBoundingBox()); KEEP.append(o)
    return bb[2] - bb[0], bb[3] - bb[1]
def label(s, near, rot=0.0, side="F"):
    for r_, rmax in ((rot, 12.0), ((rot + 90.0) % 180.0, 12.0), (rot, 25.0)):     # near first, then turned, then further away
        w, h = tsize(s, r_); w, h = w + 0.4, h + 0.4
        spot = find_spot(w, h, near, side, step=0.5, rmax=rmax)
        if spot: return text(s, spot[0], spot[1], side, rot=r_)
    SILK_MISS.append(s); return None
SILK_MISS = []
def pos_of(ref):
    q = fps[ref].GetPosition(); return pcbnew.ToMM(q.x) - OX, pcbnew.ToMM(q.y) - OY
# connector labels (signal names)
for i in range(3):
    label(f"R{i + 1} RADIO", (pos_of(f"J{i + 1}")[0], pos_of(f"J{i + 1}")[1] - 10.0))
    label(f"R{i + 1} EXP", (pos_of(f"J{i + 4}")[0] + 9.0, pos_of(f"J{i + 4}")[1]))
for k in range(4):
    label(f"A{k + 1} ANT", (pos_of(f"J{k + 7}")[0], pos_of(f"J{k + 7}")[1] - 10.0))
for ref, s in (("J11", "+12V RLY IN"), ("J12", "+12V AUX IN"), ("J13", "+5V IN"), ("J14", "J14 to controller J2")):
    x, y = pos_of(ref); label(s, (x, y + 7.0))
# test points with their signal
TPS = {}
for ref in sorted(r for r in fps if r.startswith("TP")):
    n = next((pd.GetNetname() for pd in fps[ref].Pads() if pd.GetNetname()), "").rsplit("/", 1)[-1]
    TPS[ref] = n; x, y = pos_of(ref); label(f"{ref} {n}", (x, y + 2.2))
# matrix rows and columns, A2 receive only (D-103)
for r in range(3):
    y0 = 38 + 48 * r
    label(f"R{r + 1} TX", (8.0 + 120.0, y0 + 18.5 - 3.0)); label(f"R{r + 1} RX", (8.0 + 120.0, y0 + 42.5 - 3.0))
for k, x in enumerate(ALINE):
    label(f"A{k + 1}", (x, 33.0))
label("A2 RX ONLY: TX relays not fitted (D-103)", (ALINE[1], 37.0))
# high-voltage warning (IEC 60417-5036 style): triangle with a lightning arrow, value and condition
def hv(x, y, side="F", s="RF 173 V pk  100 W HF"):
    a = 3.0; hgt = a * 0.866
    for (xa, ya), (xb, yb) in (((x - a / 2, y + hgt / 2), (x + a / 2, y + hgt / 2)), ((x + a / 2, y + hgt / 2), (x, y - hgt / 2)), ((x, y - hgt / 2), (x - a / 2, y + hgt / 2))):
        sline(xa, ya, xb, yb, side)
    for (xa, ya), (xb, yb) in (((x + 0.25, y - 0.65), (x - 0.3, y + 0.15)), ((x - 0.3, y + 0.15), (x + 0.3, y + 0.15)), ((x + 0.3, y + 0.15), (x - 0.2, y + 0.95))):
        sline(xa, ya, xb, yb, side)
    text(s, x + 2.5, y, side, just="l" if side == "F" else "r")
for side in ("F", "B"):
    sp = find_spot(28.0, 4.0, (196.0, 30.0), side, step=1.0, rmax=40.0)
    if sp: hv(sp[0] - 11.0, sp[1], side)
    else: SILK_MISS.append("HV " + side)
# art block with the board signature (D-152): the matrix as an IEC 60617 X/Y switch, truth table beside it
ART_W, ART_H = 62.0, 18.0
sp = find_spot(ART_W, ART_H, (180.0, 214.0), "F", step=1.0, rmax=120.0)
if sp:
    AX, AY = sp[0] - ART_W / 2 + 1.0, sp[1] - ART_H / 2 + 1.5
    text("SHACK RELAY MATRIX", AX, AY, h=1.5, t=0.3, just="l")
    text(f"RF board  rev C  ({REV})", AX, AY + 2.6, just="l")
    text("2026-10  DC 2643", AX, AY + 4.6, just="l")
    text("73 de PE1RGU", AX, AY + 6.6, just="l")
    gx0, gy0 = AX + 30.0, AY - 0.5; gx1, gy1 = gx0 + 9.0, gy0 + 13.0
    for (xa, ya), (xb, yb) in (((gx0, gy0), (gx1, gy0)), ((gx1, gy0), (gx1, gy1)), ((gx1, gy1), (gx0, gy1)), ((gx0, gy1), (gx0, gy0))):
        sline(xa, ya, xb, yb)
    text("X/Y", (gx0 + gx1) / 2, gy0 + 1.6)
    for i in range(3):
        y = gy0 + 4.0 + 3.0 * i; sline(gx0 - 2.5, y, gx0, y); text(f"R{i + 1}", gx0 - 2.8, y, just="r")
    for i in range(4):
        y = gy0 + 3.0 + 2.6 * i; sline(gx1, y, gx1 + 2.5, y); text(f"A{i + 1}", gx1 + 2.8, y, just="l")
    sline((gx0 + gx1) / 2, gy1, (gx0 + gx1) / 2, gy1 + 2.0); text("EN = RLY_EN", (gx0 + gx1) / 2 + 0.8, gy1 + 2.2, just="l")
    for i, s in enumerate(("K(n,m) on, EN 1:", "  Rn = Am", "EN 0: all open")):
        text(s, gx1 + 6.5, gy0 + 3.0 + 2.2 * i, just="l")
else:
    SILK_MISS.append("art block")
# back: stackup legend (D-115, D-156)
LEG = ("JLC06161H-7628A 1.6 mm 6 layers", "L1 RF rows + GND   L2 GND", "L3 signals H   L4 signals V",
       "L5 GND   L6 RF columns + GND", "RF 0.975 gap 2.0 CPWG", "signals 0.254  power 0.508")
sp = find_spot(30.0, 2.0 * len(LEG) + 1.0, (120.0, 115.0), "B", step=1.0, rmax=130.0)   # fits between two RF columns
if sp:
    for i, s in enumerate(LEG):
        text(s, sp[0], sp[1] - len(LEG) + 1.0 + 2.0 * i, side="B")
else:
    SILK_MISS.append("stackup legend")
# references: first spot clear of pads (+0.25), silk and texts (+0.1), the board edge and, if possible, of the other
# parts' courtyards. Board-only parts, supports, H1 and the labelled test points have no reference on the silk.
unplaced = []
for ref in sorted(fps, key=lambda r: (pos_of(r)[1], pos_of(r)[0])):
    f = fps[ref]; fld = f.Reference()
    if ref == "CTL3D" or ref in TPS or ref.startswith("S") and ref[1:].isdigit() or ref == "H1":
        fld.SetVisible(False); continue
    side = "B" if f.IsFlipped() else "F"; ly = pcbnew.B_SilkS if side == "B" else pcbnew.F_SilkS
    pads, silk, crt = OBS[side]
    fld.SetTextSize(pcbnew.VECTOR2I(mm(SH), mm(SH))); fld.SetTextThickness(mm(ST)); fld.SetVisible(True)
    fld.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER); fld.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    own = next((c for g_, c in crt if g_ is f), None) or bx(f.GetBoundingBox(False))
    ocx, ocy = (own[0] + own[2]) / 2, (own[1] + own[3]) / 2
    others = [c for g_, c in crt if g_ is not f]
    best = None
    for strict in (True, False):
        for gap in (0.3, 0.8, 1.5, 2.5, 3.5, 4.5):
            for slide in (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0, 3.0, -3.0, 4.0, -4.0):   # along the side (p3)
                for rot, where in ((0, "N"), (0, "S"), (90, "W"), (90, "E"), (0, "W"), (0, "E"), (90, "N"), (90, "S")):
                    fld.SetTextAngleDegrees(rot); fld.SetPosition(P(ocx, ocy)); tb_ = bx(fld.GetBoundingBox()); hw, hh = (tb_[2] - tb_[0]) / 2, (tb_[3] - tb_[1]) / 2
                    x, y = {"N": (ocx + slide, own[1] - gap - hh), "S": (ocx + slide, own[3] + gap + hh),
                            "W": (own[0] - gap - hw, ocy + slide), "E": (own[2] + gap + hw, ocy + slide)}[where]
                    box = (x - hw, y - hh, x + hw, y + hh)
                    if box[0] < X0s + 0.6 or box[2] > X1s - 0.6 or box[1] < Y0s + 0.6 or box[3] > Y1s - 0.6: continue
                    if any(hit(box, o) for o in pads + silk + SILK[ly]): continue
                    if strict and any(hit(box, o) for o in others): continue
                    best = (rot, x, y, box); break
                if best: break
            if best: break
        if best: break
    if best is None:
        fx, fy = pos_of(ref)
        for rot in (90, 0):
            fld.SetTextAngleDegrees(rot); fld.SetPosition(P(fx, fy)); tb_ = bx(fld.GetBoundingBox()); hw, hh = (tb_[2] - tb_[0]) / 2, (tb_[3] - tb_[1]) / 2
            for dx in sorted((i * 0.25 for i in range(-14, 15)), key=abs):
                for dy in sorted((i * 0.25 for i in range(-10, 11)), key=abs):
                    box = (fx + dx - hw, fy + dy - hh, fx + dx + hw, fy + dy + hh)
                    if not any(hit(box, o) for o in pads + silk + SILK[ly]):
                        best = (rot, fx + dx, fy + dy, box); break
                if best: break
            if best: break
    if best is None:                                   # no room: the reference stays on the fab layer only (assembly drawing)
        unplaced.append(ref); fld.SetVisible(False); continue
    fld.SetTextAngleDegrees(best[0]); fld.SetPosition(P(best[1], best[2])); SILK[ly].append(best[3])
for f in fps.values():
    f.Value().SetVisible(False)                                 # values on the fab layer only
print("SILK: references not placed", unplaced, "| labels not placed", SILK_MISS)
b.Save(BOARD)

# ---- 7b. physical stackup JLC06161H-7628A (D-115). The pcbnew Python wrapper does not expose BOARD_STACKUP,
# so the (stackup ...) block in (setup ...) is written as text after the save. Values: JLC impedance page / skill section 9.
STACKUP = [  # (layer name, type, thickness mm, material, epsilon_r)
    ("F.Cu", "copper", 0.035, None, None),
    ("dielectric 1", "prepreg", 0.5124, "FR4 7628+7628+1080", 4.33),
    ("In1.Cu", "copper", 0.0152, None, None),
    ("dielectric 2", "core", 0.1, "FR4", 4.6),
    ("In2.Cu", "copper", 0.0152, None, None),
    ("dielectric 3", "prepreg", 0.2328, "FR4 2116+2116", 4.16),
    ("In3.Cu", "copper", 0.0152, None, None),
    ("dielectric 4", "core", 0.1, "FR4", 4.6),
    ("In4.Cu", "copper", 0.0152, None, None),
    ("dielectric 5", "prepreg", 0.5124, "FR4 1080+7628+7628", 4.33),
    ("B.Cu", "copper", 0.035, None, None)]
def stackup_text():
    s = ['\t\t(stackup', '\t\t\t(layer "F.SilkS"\n\t\t\t\t(type "Top Silk Screen")\n\t\t\t)',
         '\t\t\t(layer "F.Paste"\n\t\t\t\t(type "Top Solder Paste")\n\t\t\t)',
         '\t\t\t(layer "F.Mask"\n\t\t\t\t(type "Top Solder Mask")\n\t\t\t\t(thickness 0.01)\n\t\t\t)']
    for name, typ, th, mat, er in STACKUP:
        body = [f'(type "{typ}")']
        if mat:
            body += ['(color "FR4 natural")', f'(thickness {th})', f'(material "{mat}")', f'(epsilon_r {er})', '(loss_tangent 0.02)']
        else:
            body += [f'(thickness {th})']
        s.append(f'\t\t\t(layer "{name}"\n' + "".join(f"\t\t\t\t{x}\n" for x in body) + '\t\t\t)')
    s += ['\t\t\t(layer "B.Mask"\n\t\t\t\t(type "Bottom Solder Mask")\n\t\t\t\t(thickness 0.01)\n\t\t\t)',
          '\t\t\t(layer "B.Paste"\n\t\t\t\t(type "Bottom Solder Paste")\n\t\t\t)',
          '\t\t\t(layer "B.SilkS"\n\t\t\t\t(type "Bottom Silk Screen")\n\t\t\t)',
          '\t\t\t(copper_finish "ENIG")', '\t\t\t(dielectric_constraints yes)', '\t\t)']
    return "\n".join(s) + "\n"
txt = open(BOARD).read()
i = txt.find("\n\t(setup\n"); assert i > 0, "no setup block"
j = i + len("\n\t(setup\n")
if txt.startswith("\t\t(stackup", j):                 # replace an existing block (rerun)
    k = txt.index("\n\t\t)\n", j) + len("\n\t\t)\n")
    txt = txt[:j] + txt[k:]
txt = txt[:j] + stackup_text() + txt[j:]
# page A3 landscape (the Python wrapper has no PAGE_INFO): the 268 x 230 mm board at (20, 20) does not fit A4
txt, n_paper = re.subn(r'\(paper "[^"]*"( portrait)?\)', '(paper "A3")', txt, count=1)
assert n_paper == 1
open(BOARD, "w").write(txt)

# ---- 7. netclasses in the project file (the schematic generator keeps unknown keys) ----
pro = json.load(open(PRO))
ns = pro.setdefault("net_settings", {})
base = next(c for c in ns["classes"] if c["name"] == "Default")
base.update({"track_width": 0.254, "clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3})
def cls(name, tw, cl, vd=0.6, vdr=0.3):
    c = dict(base); c.update({"name": name, "track_width": tw, "clearance": cl, "via_diameter": vd, "via_drill": vdr, "priority": 0})
    return c
ns["classes"] = [base, cls("RF", 0.975, 0.5, 1.2, 0.8), cls("Power", 0.508, 0.2)]   # Power 0.508 (p2c: current budget, M-75)   # RF 0.5: inner antipad (D-117); outer 2.0 by the zones (M-70)
ns["netclass_patterns"] = (
    [{"netclass": "RF", "pattern": p} for p in ("/ANT*", "*TXBUS", "*RXBUS", "/R?_RADIO", "/R?_EXP", "/A?_ANTENNA", "*/PORT", "*/PARK")] +
    [{"netclass": "Power", "pattern": p} for p in ("+12V*", "+5V*", "+3V3", "CLAMP_*", "*/CHASSIS*")])   # +3V3, CHASSIS: as routed (M-75, D-162)
open(PRO, "w").write(json.dumps(pro, indent=2) + "\n")

nn = sum(1 for p in b.GetPads() if p.GetNetCode() > 0)
print("added", len(ADDED), ADDED)
print(REV, "footprints", len(list(b.GetFootprints())), "pads with net", nn, "nets", len(nets), "placed", len(placed))
