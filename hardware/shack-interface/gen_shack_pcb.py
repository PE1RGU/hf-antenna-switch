#!/usr/bin/env python3
"""Shack interface layout generator, increment p1 (board, nets, outline, placement by function zones).
Run with the KiCad 10 Python from hardware/shack-interface/:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 gen_shack_pcb.py
Input: ../unit/verify/si15.xml (netlist), footprint libraries. Output: shack-interface.kicad_pcb (made new on every run; all
layout work is in this script). Sources: D-170 (4 layers), D-171 (Hammond 1455T1601, board about 160 x 156 mm, J1, J3),
D-172 (function zones, svg/shack-placement-zones.png), D-82 (7805 on the side wall), D-96 (J14), D-100 (mini-DIN face at
the board edge), D-138 (J1 face position).
Board frame: x across the housing (0 = left side wall slot), y from the rear panel (0) to the front panel (BH), mm.
Helpers satellite(), align() and group() as gen_rfboard_pcb.py section 8 (placement checklist of hardware-design-rules)."""
import collections, json, math, os, sys
import xml.etree.ElementTree as ET
import pcbnew

REV = "p8e"
BOARD, NETLIST = "shack-interface.kicad_pcb", "../unit/verify/si18.xml"
OX, OY = 20.0, 20.0                                  # page offset of the board frame origin
BW, BH, RC = 160.0, 159.0, 1.0                       # board (D-171): 160 mm slot width; length 159 mm in the 160 +-0.5 mm extrusion (A-25, to confirm on the STEP model)
XL, XR = 0.2, BW - 0.2                              # side edges (S-8, D-194): 159.6 mm wide for the JLC outline tolerance in the 160 mm slots;
                                                    # 0.2 mm off each side, so the centre stays at x 80 (end plates, gen_endplates.py)
SIDE = 3.5                                           # side bands in the extrusion slots and along the wall: no parts
# front notch for the 2inch display stack (D-187, front plate a8): (x0, x1, new edge y); x = u - 2.5, y = BH + 2.3 - w
NOTCH, NR = [(0.0, 71.0, 151.3), (71.0, 80.0, 149.8)], 0.5   # NR: corner radius (0.5 mm, inner corners for the mill)
# p8b (Prins, 2026-10-29): the notch runs to the left edge; the 4 mm corner piece left of it is gone (the board end stays
# in the left slot up to y 151.3 and in the right slot up to the front edge)
def in_notch(x, y, m=0.0): return any(x0 - m < x < x1 + m and y > ye - m for (x0, x1, ye) in NOTCH)
def box_in_notch(box, m=0.0): return any(box[2] > x0 - m and box[0] < x1 + m and box[3] > ye - m for (x0, x1, ye) in NOTCH)
FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
mm = pcbnew.FromMM
P = lambda x, y: pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))

b = pcbnew.BOARD()
KEEP = []                                            # keep the Python proxies alive (SWIG type table)

# ---- 1. footprints and nets from the netlist ----
root = ET.parse(NETLIST).getroot()
pinnet = {}
for n_ in root.iter("net"):
    for nd in n_.iter("node"):
        pinnet[(nd.get("ref"), nd.get("pin"))] = n_.get("name")
nets = {}
def net(name):
    if name not in nets:
        ni = pcbnew.NETINFO_ITEM(b, name); b.Add(ni); nets[name] = ni; KEEP.append(ni)
    return nets[name]
def load(fpid):
    lib, name = fpid.split(":")
    path = "lib/shack-interface.pretty" if lib == "shack-interface" else f"{FPLIB}/{lib}.pretty"
    f = pcbnew.FootprintLoad(path, name)
    assert f is not None, fpid
    f.SetFPID(pcbnew.LIB_ID(lib, name)); return f
fps = {}
for c in root.iter("comp"):
    ref = c.get("ref")
    f = load(c.findtext("footprint")); f.SetReference(ref); f.SetValue(c.findtext("value"))
    props = {q.get("name") for q in c.iter("property")}
    f.SetDNP("dnp" in props); f.SetExcludedFromBOM("exclude_from_bom" in props)
    b.Add(f); KEEP.append(f); fps[ref] = f
# 3D model of J3 (XT60PW-M): the Amass vendor STEP in hardware/unit/unit.3dshapes, offset and rotation as on the RF board
# (gen_rfboard_pcb.py VENDOR_3D; the KiCad 10 library does not install it)
VENDOR_3D = {"AMASS_XT60PW-M_1x02_P7.20mm_Horizontal": ("AMASS_XT60PW-M.step", (3.6, 6.0, 0.0), (-90.0, 0.0, 180.0))}
for f in fps.values():
    v = VENDOR_3D.get(f.GetFPID().GetLibItemName().wx_str())
    if v:
        m = f.Models()[0]
        m.m_Filename = "${KIPRJMOD}/../unit/unit.3dshapes/" + v[0]
        m.m_Offset = pcbnew.VECTOR3D(*v[1]); m.m_Rotation = pcbnew.VECTOR3D(*v[2])
used = set()
for ref, f in fps.items():
    for pad in f.Pads():
        k = (ref, pad.GetNumber())
        if k in pinnet:
            pad.SetNet(net(pinnet[k])); used.add(k)
assert not (set(pinnet) - used), sorted(set(pinnet) - used)[:10]

# ---- 2. board settings: 4 layers (D-170) ----
ds = b.GetDesignSettings()
b.SetCopperLayerCount(4)
ds.SetBoardThickness(mm(1.6))
# USB-C fan-out (section 7): 0.15 mm tracks and 0.4/0.2 mm vias between 0.5 mm pitch pads (JLCPCB 4-layer: 0.09 mm track,
# 0.15 mm via drill; to confirm in the quote form, A-26)
ds.m_TrackMinWidth = mm(0.15); ds.m_ViasMinSize = mm(0.4); ds.m_MinThroughDrill = mm(0.2)
tb = b.GetTitleBlock()
tb.SetTitle("Shack Relay Matrix rev C: shack interface"); tb.SetRevision(REV); tb.SetCompany("PE1RGU")
tb.SetDate("2026-10-25"); tb.SetComment(0, "JLC04161H-7628, 4 layers, 1.6 mm: L1 vertical, L2 GND, L3 horizontal, L4 GND (D-170). Housing Hammond 1455T1601 (D-171)")
tb.SetComment(1, f"Generated by gen_shack_pcb.py {REV}; netlist {NETLIST}")

# ---- 3. outline ----
def edge(shape):
    shape.SetLayer(pcbnew.Edge_Cuts); shape.SetWidth(mm(0.1)); b.Add(shape); KEEP.append(shape)
for (xa, ya, xb, yb) in ((XR, RC, XR, BH - RC),):   # rear edge: after J14 (tab, D-186); front and left edges below
    l = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); l.SetStart(P(xa, ya)); l.SetEnd(P(xb, yb)); edge(l)
# front edge with the display notch (D-187): straight runs and a NR fillet at each of the six corners
_fp = [(XR - RC, BH), (NOTCH[1][1], BH), (NOTCH[1][1], NOTCH[1][2]), (NOTCH[1][0], NOTCH[1][2]), (NOTCH[0][1], NOTCH[0][2]),
       (XL, NOTCH[0][2]), (XL, RC)]                                       # notch to the left edge (p8b)
_q = [_fp[0]]
for (xa, ya), (xc, yc), (xe, ye_) in zip(_fp, _fp[1:], _fp[2:]):
    l1, l2 = math.hypot(xc - xa, yc - ya), math.hypot(xe - xc, ye_ - yc)
    ui, uo = ((xc - xa) / l1, (yc - ya) / l1), ((xe - xc) / l2, (ye_ - yc) / l2)
    st_, en_ = (xc - ui[0] * NR, yc - ui[1] * NR), (xc + uo[0] * NR, yc + uo[1] * NR)
    cen = (st_[0] + uo[0] * NR, st_[1] + uo[1] * NR)
    mid = (cen[0] + (ui[0] - uo[0]) * NR / 2 ** 0.5, cen[1] + (ui[1] - uo[1]) * NR / 2 ** 0.5)
    l = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); l.SetStart(P(*_q[-1])); l.SetEnd(P(*st_)); edge(l)
    a = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_ARC); a.SetArcGeometry(P(*st_), P(*mid), P(*en_)); edge(a); _q.append(en_)
l = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); l.SetStart(P(*_q[-1])); l.SetEnd(P(*_fp[-1])); edge(l)
kc = RC * (1 - 0.5 ** 0.5)
for (sx, sy, mx_, my_, ex, ey) in ((XL, RC, XL + kc, kc, XL + RC, 0), (XR - RC, 0, XR - kc, kc, XR, RC),
                                   (XR, BH - RC, XR - kc, BH - kc, XR - RC, BH)):
    a = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_ARC); a.SetArcGeometry(P(sx, sy), P(mx_, my_), P(ex, ey)); edge(a)

# ---- 4. placement helpers (gen_rfboard_pcb.py section 8) ----
GAP = 0.6
POWER_NETS = {"GND", "+3V3", "+5V", "+13V8", "CHASSIS", "RGND"}
placed = set()
def place(ref, x, y, rot=0.0, side="F"):
    f = fps[ref]
    if (side == "B") != f.IsFlipped():
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    f.SetOrientationDegrees(rot); f.SetPosition(P(x, y))
def cy_mm(fp):
    c = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if c.GetWidth() == 0: c = fp.GetBoundingBox(False)
    return (pcbnew.ToMM(c.GetX()) - OX, pcbnew.ToMM(c.GetY()) - OY, pcbnew.ToMM(c.GetRight()) - OX, pcbnew.ToMM(c.GetBottom()) - OY)
def pad_mm(pad):
    q = pad.GetPosition(); return (pcbnew.ToMM(q.x) - OX, pcbnew.ToMM(q.y) - OY)
OBST, IDX, PARK = [], {}, []
def free(bb, obst):
    return all(bb[2] + GAP <= o[0] or bb[0] >= o[2] + GAP or bb[3] + GAP <= o[1] or bb[1] >= o[3] + GAP for o in obst)
def inside(bb, reg):
    return bb[0] >= reg[0] and bb[1] >= reg[1] and bb[2] <= reg[2] and bb[3] <= reg[3]
def fix(ref, x, y, rot=0.0):
    place(ref, x, y, rot); placed.add(ref); IDX[ref] = len(OBST); OBST.append(cy_mm(fps[ref]))
def base(n): return n.rsplit("/", 1)[-1]
def satellite(ref, group, reg, want=None):
    """Place ref next to the pad of a part in group that shares a net with it.
    want: None (any signal net), a net name, or ("pad", number) for that pad of the anchor."""
    fp = fps[ref]
    own = {pd.GetNetname() for pd in fp.Pads()}
    targets = []
    for g in (group[:1] if isinstance(want, tuple) else group):
        cx = sum(cy_mm(fps[g])[0::2]) / 2; cyy = sum(cy_mm(fps[g])[1::2]) / 2
        for pd in fps[g].Pads():
            n = pd.GetNetname()
            ok = (pd.GetNumber() == want[1]) if isinstance(want, tuple) else (base(n) == want if want else base(n) not in POWER_NETS)
            if n and n in own and ok:
                targets.append((n, pad_mm(pd), (cx, cyy)))
    if not targets:                                    # only a supply net in common: take it
        for g in group:
            cx = sum(cy_mm(fps[g])[0::2]) / 2; cyy = sum(cy_mm(fps[g])[1::2]) / 2
            targets += [(pd.GetNetname(), pad_mm(pd), (cx, cyy)) for pd in fps[g].Pads()
                        if pd.GetNetname() and pd.GetNetname() in own and base(pd.GetNetname()) != "GND"]
    if not targets: return False                       # no shared net yet: group() tries it again later
    best = None
    obst = [o for o in OBST if o[2] > reg[0] - 2 and o[0] < reg[2] + 2 and o[3] > reg[1] - 2 and o[1] < reg[3] + 2]
    for rot in (0, 90, 180, 270):
        place(ref, 0, 0, rot)
        bb0 = cy_mm(fp); fx, fy = pcbnew.ToMM(fp.GetPosition().x) - OX, pcbnew.ToMM(fp.GetPosition().y) - OY
        for n, (tx, ty), (cx, cyy) in targets:
            cp = next(pd for pd in fp.Pads() if pd.GetNetname() == n)
            px, py = pad_mm(cp)
            vx, vy = tx - cx, ty - cyy
            if abs(vx) < 0.5 and abs(vy) < 0.5: out = None
            elif abs(vx) >= abs(vy): out = ((1 if vx >= 0 else -1), 0)
            else: out = (0, (1 if vy >= 0 else -1))
            dirs = [((1, 0), 0.0), ((-1, 0), 0.0), ((0, 1), 0.0), ((0, -1), 0.0)] if out is None else \
                   [(out, 0.0)] + [(u, 3.0) for u in ((1, 0), (-1, 0), (0, 1), (0, -1)) if u != out]
            for ((ux, uy), pen), d10 in ((u, d) for u in dirs for d in range(10, 400, 4)):
                if best is not None and d10 / 10 + pen > best[0]: continue
                for l10 in sorted(range(-400, 401, 6), key=abs):
                    d, l = d10 / 10, l10 / 10
                    qx, qy = tx + ux * d - uy * l, ty + uy * d + ux * l
                    dx, dy = qx - px, qy - py
                    bb = (bb0[0] + dx, bb0[1] + dy, bb0[2] + dx, bb0[3] + dy)
                    if not inside(bb, reg) or not free(bb, obst): continue
                    score = d + 0.6 * abs(l) + pen
                    if best is None or score < best[0]:
                        best = (score, rot, fx + dx, fy + dy)
                    break
    if best is None and not getattr(satellite, "fb", False):   # its nets lie far outside the region: place it by the anchor
        satellite.fb = True
        try:
            anc = group[0]; save = [(pd, pd.GetNet()) for pd in fps[anc].Pads()]
            n0 = next(pd.GetNetname() for pd in fp.Pads() if pd.GetNetname())
            for pd, _ in save: pd.SetNet(net(n0))              # temporary: every anchor pad counts as a target
            ok_ = satellite(ref, [anc], reg)
        finally:
            for pd, n_ in save: pd.SetNet(n_)
            satellite.fb = False
        if ok_: return True
    if best is None:                                   # no room in the region: park it right of the board for review
        PARK.append(ref); fix(ref, BW + 10.0 + 6.0 * (len(PARK) // 30), 5.0 + 4.0 * (len(PARK) % 30), 0); return True
    fix(ref, best[2], best[3], best[1]); return True
PGRID, ATOL = 0.5, 1.5
def pos(ref):
    q = fps[ref].GetPosition(); return pcbnew.ToMM(q.x) - OX, pcbnew.ToMM(q.y) - OY
def try_move(ref, x, y, reg):
    (x0, y0), k = pos(ref), IDX[ref]
    place(ref, x, y, fps[ref].GetOrientationDegrees()); bb = cy_mm(fps[ref])
    if inside(bb, reg) and free(bb, OBST[:k] + OBST[k + 1:]):
        OBST[k] = bb; return True
    place(ref, x0, y0, fps[ref].GetOrientationDegrees()); return False
def align(g, reg):
    sat = g[1:]
    for r in sat:
        x, y = pos(r); try_move(r, round(x / PGRID) * PGRID, round(y / PGRID) * PGRID, reg)
    for ax in (1, 0):
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
def group(anchor_ref, members, reg, at=None, rot=0.0, ctx=()):
    """ctx: parts placed before (other groups) that members may connect to; they are not moved"""
    if at: fix(anchor_ref, at[0], at[1], rot)
    g = [anchor_ref]
    todo = [(m if isinstance(m, tuple) else (m, None)) for m in members]
    while todo:
        for i, (ref, want) in enumerate(todo):
            if satellite(ref, g + list(ctx), reg, want):
                g.append(ref); todo.pop(i); break
        else:
            raise AssertionError(f"{anchor_ref}: no shared net for {[t[0] for t in todo]}")
    align(g, reg)

# ---- 5. panel parts (D-171, D-172) ----
# rear edge (y 0): faces at the edge. J3 XT60 as the RF board (rot 0, face to -y); J1 face 0.5 mm over the edge (D-138);
# mini-DIN face at the footprint origin (D-100), turned 180 so that the body lies on the board
# D-177 (M-92): the end panels sit 2.3 mm beyond the board ends in the 1455T1601; every panel connector face is set to
# 2.0 mm beyond the board edge (0.3 mm from the panel). OVH = face beyond the edge.
OVH = 2.0
fix("J3", 11.5, 16.6 - 0.25 - OVH, 0)                # XT60 model face 0.25 mm inside the footprint edge
J1X = 38.5                                           # J1 centred over the four entry columns
fix("J1", J1X, -0.05 - OVH + 7.93, 180)             # J1 face 0.05 mm beyond its footprint position offset
MDX = (76.5, 108.5, 140.5)                          # mini-DIN centres, 32 mm apart (D-186: was 35; frees the USB channel)
for k, x in enumerate(MDX):
    fix(f"J1{k + 1}", x, -OVH, 180)
fix("H1", 27.0, 6.0)                                 # CHASSIS bond point between J3 and J1 (lug wire to the rear panel, D-186)
# 7805 on the left wall (D-82): vertical TO-220, tab toward -x; tab face about 2.25 mm inside the board edge (inner wall)
fix("U1", 5.8, 28.0, 90)
# DevKit along the front, turned 270: its signal pin row (pads 1 to 16) on top, facing the loops (DATA_TX, DATA_RX),
# the MCU support (WDI, LATCH_CLR), U5 (SCL) and the ports (PERMIT); USB pads 19, 20 on the bottom row
A1X, A1Y = 89.5, 134.0
fix("A1", A1X, A1Y, 270)
# J14 at the rear edge (D-186): the Mac cable enters at the rear panel with the other cables. J14 sits in a GND channel
# between the Cat6 entry block (CHASSIS, x up to 55.5) and the R1 RGND island (from x 62); its support parts lie behind
# it in the channel. Turned 180: the PCB edge line of the footprint (connector face) at y -3.67 from the origin.
JX = 59.5
fix("J14", JX, 3.67 - OVH, 180)
# rear edge with a tab under J14: the shell pads of the USB4105 sit 2 mm behind its face, so J14 cannot overhang; the
# board gets a 2.0 mm tab, 13 mm wide, between J1 and J11 (the bezels only reach the board corners)
TABX = (JX - 6.5, JX + 6.5)
for (xa, ya, xb, yb) in ((XL + RC, 0, TABX[0], 0), (TABX[0], 0, TABX[0], -OVH), (TABX[0], -OVH, TABX[1], -OVH),
                         (TABX[1], -OVH, TABX[1], 0), (TABX[1], 0, XR - RC, 0)):
    l = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); l.SetStart(P(xa, ya)); l.SetEnd(P(xb, yb)); edge(l)
# front panel wire headers (KILL, RESET and LEDs) and the display header J15 (D-180): behind the display module, far enough
# from the front plate for the module and its cable (about 11 mm deep), so not at the board edge any more (p6)
FRONT_Y = BH - 12.5
for ref, x in (("J6", 8.0), ("J2", 21.8), ("J7", 31.6)):    # footprint origin at pin 1; courtyards 0.3 mm apart
    fix(ref, x, FRONT_Y, 0)
# display header J15 (1x8, 2.54 mm) upright right of the DevKit: no room in the header row left of the DevKit, and the
# area behind the KILL and RESET bodies (front right) must stay free; the 20 cm Waveshare cable reaches the display
fix("J15", 124.2, 120.5, 0)

# ---- 6. function zones (D-172) ----
Z = {"power": (SIDE, 20.0, 22.0, 70.0), "entry": (22.0, 19.0, 55.0, 71.0), "loops": (SIDE, 72.0, 55.0, 100.0),
     "latch": (SIDE, 102.0, 54.5, 145.0), "exp": (88.0, 72.0, BW - SIDE, 88.0), "mcu": (56.0, 90.0, BW - SIDE, 120.5)}
PORT = [(62.0, 15.0, 93.7, 70.0), (94.0, 15.0, 125.7, 70.0), (126.0, 15.0, BW - SIDE, 70.0)]   # D-186: 32 mm pitch
# power: fuse, reverse diode, TVS and bulk at the XT60, then the 7805 and the LD1117 with their parts and links
group("F1", ["D1", "D2", "C1", "C2", ("TP1", "+13V8")], Z["power"], at=(14.0, 24.0), rot=90)
group("U1", ["C3", "R5", "C4", ("TP2", "+5V")], Z["power"])
group("U2", ["C5", "R6", "C6", "C7", ("TP3", "+3V3")], Z["power"], at=(13.0, 52.0))
# Cat6 entry (M-89): the four GDTs in one row directly behind J1, so that every surge path to CHASSIS is short and the
# centre electrodes sit on one CHASSIS bar to H1 (skill placement checklist: protection at the connector, short surge
# path). One column per pair in the J1 pin order (J1 turned 180: pair 4, 3, 1, 2 from the left), 8.25 mm pitch, centred
# under J1. Per column, top to bottom: GDT upright (P pin on top, from J1; N pin at the bottom), choke with both inputs
# on top (P side set by the TDK pin-out), Y-capacitor footprints side by side (wire pad on top), 47R MELF per wire (P right), TVS across.
ECOL = (4, 3, 1, 2); EX0, EPITCH = J1X - 1.5 * 8.25, 8.25
YGD, YCM, YYC, YMF, YTV = 27.0, 37.5, 43.6, 51.0, 59.0
def turned(ref, x, y, ok):
    """place ref at (x, y) at the first rotation for which ok(pads) holds; pads: number -> ((x, y), net)"""
    for rot in (0, 90, 180, 270):
        place(ref, x, y, rot)
        if ok({pd.GetNumber(): (pad_mm(pd), base(pd.GetNetname())) for pd in fps[ref].Pads()}):
            fix(ref, x, y, rot); return rot
    raise AssertionError(f"{ref}: no rotation fits")
for i, k in enumerate(ECOL):
    cx = EX0 + EPITCH * i
    fix(f"GD{k}", cx, YGD, 90)                       # pin 3 (P) on top, pin 2 CHASSIS in the middle, pin 1 (N) below
    assert pad_mm(next(pd for pd in fps[f"GD{k}"].Pads() if pd.GetNumber() == "3"))[1] < YGD, f"GD{k} P pin not on top"
    P_, N_ = f"L{k}P", f"L{k}N"
    def cm_ok(pp):                                    # inputs (LkP, LkN) above the outputs, P input right of N input
        inp = {n: xy for xy, n in pp.values() if n in (P_, N_)}; out = [xy for xy, n in pp.values() if n not in (P_, N_)]
        return len(inp) == 2 and max(v[1] for v in inp.values()) < min(v[1] for v in out)
    turned(f"L{k}", cx, YCM, cm_ok)
    lp = {pd.GetNumber(): pd.GetNetname() for pd in fps[f"L{k}"].Pads()}
    outP = pinnet[(f"R{k}1", "2")]                   # choke P output = the net of the P 47R pad 2
    # the TDK pin-out puts the P output on one side; the parts below follow it, so that nothing crosses after the choke
    sP = 1.0 if next(pad_mm(pd)[0] for pd in fps[f"L{k}"].Pads() if pd.GetNetname() == outP) > cx else -1.0
    for c in [f"C{n}" for n in range(22, 30)]:
        nets_ = {pinnet.get((c, "1")), pinnet.get((c, "2"))}
        if not nets_ & set(lp.values()): continue
        side = 1.6 * sP if outP in nets_ else -1.6 * sP
        turned(c, cx + side, YYC, lambda pp: [xy for xy, n in pp.values() if n != "CHASSIS"][0][1] <
                                             [xy for xy, n in pp.values() if n == "CHASSIS"][0][1])
    for r_, side in ((f"R{k}1", 1.75 * sP), (f"R{k}2", -1.75 * sP)):  # 47R: pad 2 (choke side) on top
        turned(r_, cx + side, YMF, lambda pp: pp["2"][0][1] < pp["1"][0][1])
    pnet = pinnet[(f"R{k}1", "1")]                   # TVS across, its P pad on the P side
    turned(f"D{k}1", cx, YTV, lambda pp: [xy for xy, n in pp.values() if n == base(pnet)][0][0] * sP > cx * sP)
# loop sources: one column per loop under the entry
for k, x in zip((4, 3, 1, 2), (15.5, 27.0, 38.5, 50.0)):   # loop columns in the entry column order (no crossing pairs)
    # one column per loop (template, Prins 2026-10-25): pass transistor Qk1 on top, then the sense transistor Qk2 with
    # Rsense Rk3 and the base resistor Rk4, then the enable switch Qk3 with its pull resistor Rk5, then (loops 3, 4) the
    # return sense Qk4 with Rk7, Rk8 and the 100R Rk6 with the clamp Dk3. Small parts upright (rotation 90), in one row each
    fix(f"Q{k}1", x, 77.0, 0)
    rows = ((84.0, (f"Q{k}2", -3.5, 0), (f"R{k}3", 0.5, 90), (f"R{k}4", 3.0, 90)),
            (89.0, (f"Q{k}3", -3.5, 0), (f"R{k}5", 0.5, 90)),
            (94.0, (f"Q{k}4", -3.5, 0), (f"R{k}7", 0.5, 90), (f"R{k}8", 3.0, 90)),
            (98.5, (f"D{k}3", -3.5, 0), (f"R{k}6", 1.6, 0)))
    for y_, *parts in rows:
        for r_, dx_, rot_ in parts:
            if r_ in fps: fix(r_, x + dx_, y_, rot_)
# SAFE latch front left
# SAFE latch (D-75, D-84) in signal-flow order, left to right in one row: U7 Schmitt (SAFE_LOST -> SAFE_OK), U8 AND
# (PRE_N = SAFE_OK AND POR_N), U9 latch (LATCHED), U11 NOR (TX_EN to the ports). Under them the inputs of the row: U6 (POR_N)
# under U7/U8, U10 (RESET clock) under U9 with its RC network on the J6 side. Each IC at rotation 0 (inputs left, output
# right) with its own 1 uF upright right of it at the VCC pin. U10 sits left under U9, so that its output reaches the U9
# clock (pin 1, top left) without crossing U9; its RC network lies below it toward the RESET button on J6 (Prins, 2026-10-25: tidy the parts around U8)
YL1, YL2 = 112.0, 121.0
for u, c, x, y, dc in (("U7", "C73", 9.0, YL1, 3.5), ("U8", "C74", 18.0, YL1, 3.5), ("U9", "C75", 28.5, YL1, 4.0),
                       ("U11", "C77", 40.0, YL1, 3.5), ("U6", "C72", 9.0, YL2, 3.5), ("U10", "C76", 21.0, YL2, 3.5)):
    fix(u, x, y, 0)
    vcc = next(pd for pd in fps[u].Pads() if pd.GetNetname() == "+3V3")
    if u == "U9":                                         # VCC (pin 8) top right, PRE (pin 7) under it: the capacitor goes
        fix(c, pad_mm(vcc)[0] + 0.6, y - 3.4, 0)          # above the pin, so that PRE_N keeps a straight way in from the right
    else:
        fix(c, x + dc, pad_mm(vcc)[1] + 0.8, 90)          # pad 1 (+3V3) level with the VCC pin, GND pad below
group("U10", ["R72", "C71", "D71", "R71"], (SIDE, YL2 + 3.0, 30.0, 140.0))
# panel indicators and inputs at their headers: SAFE and LATCHED LED resistors at J6, KILL_S pull-up at J7
group("J6", ["R73", "R74"], (SIDE, 136.0, 20.0, BH - 0.5))
group("J7", ["R75"], (pos("J7")[0] - 8.0, 136.0, pos("J7")[0] + 8.0, BH - 0.5))
# expander row across the middle, MCU support right of the DevKit
group("U5", [("C61", ("pad", "24"))], Z["exp"], at=(110.0, 80.0), rot=90)
group("U3", ["U4", "C62", "C63", "R61", "R62", "R63", "JP61"], Z["mcu"], at=(100.0, 100.0), ctx=["A1", "U5"])
# USB support parts behind J14 in the GND channel (D-186): U61 (ESD array, flow-through) centred behind the fan-out,
# C64 (VBUS) right and R65 (CC2) left at the VBUS stubs, R64 (CC1) right of U61. Rotations: signal pad toward J14.
_jy = next(pad_mm(pd) for pd in fps["J14"].Pads() if pd.GetNumber() == "A6")[1]
fix("U61", JX, _jy + 7.4, 0)
turned("C64", JX + 3.6, _jy + 4.6, lambda pp: [xy for xy, n in pp.values() if n != "GND"][0][1] < [xy for xy, n in pp.values() if n == "GND"][0][1])
turned("R65", JX - 3.6, _jy + 4.6, lambda pp: [xy for xy, n in pp.values() if n != "GND"][0][1] < [xy for xy, n in pp.values() if n == "GND"][0][1])
turned("R64", JX + 3.6, _jy + 8.0, lambda pp: [xy for xy, n in pp.values() if n != "GND"][0][1] < [xy for xy, n in pp.values() if n == "GND"][0][1])
# radio ports: one column per port behind its mini-DIN; radio side (RGND) near the connector, logic side toward the middle
LEDR = ()                                          # (panel LED resistors removed with the R1 to R3 LEDs, D-180)
def port_refs(k):
    return [r for r in fps if r[-3:].isdigit() and r[0] in "RCDUJQT" and not r.startswith("J1") and r not in LEDR
            and 100 * (k + 2) <= int("".join(ch for ch in r if ch.isdigit())) < 100 * (k + 3)]
for k, (reg, x) in enumerate(zip(PORT, MDX)):
    n = 200 + 100 * k
    if k > 0:                                          # R2 and R3: a copy of R1, shifted by the connector pitch (same layout)
        dx = x - MDX[0]; bad = []
        for r in port_refs(0):
            r2 = f"{r.rstrip('0123456789')}{int(''.join(ch for ch in r if ch.isdigit())) + 100 * k}"
            x0, y0 = pos(r); fix(r2, x0 + dx, y0, fps[r].GetOrientationDegrees())
            k2 = IDX[r2]
            o_ = OBST[k2]
            if any(o_[0] < q[2] and q[0] < o_[2] and o_[1] < q[3] and q[1] < o_[3] for q in OBST[:k2] + OBST[k2 + 1:]): bad.append(r2)
        assert not bad, f"port R{k + 1}: copy overlaps {bad}"
        continue
    esd = [f"D{n + i}" for i in (11, 12, 13, 14, 16, 17, 18)] + [f"C{n + i}" for i in (11, 12, 13, 14, 16, 17, 18)]
    tps = [f"TP{n + i}" for i in (1, 2, 3, 4, 6, 7, 8)]
    # three rows behind the connector, in the pin order 1, 2, 3, 4, 6, 7, 8 at 4 mm pitch: ESD diode, 1 nF, test point
    for i, pin in enumerate((1, 2, 3, 4, 6, 7, 8)):
        xi = x - 12.0 + 4.0 * i
        fix(f"D{n + 10 + pin}", xi, 18.0, 90); fix(f"C{n + 10 + pin}", xi, 22.5, 90); fix(f"TP{n + pin}", xi, 27.0)
    # Port template (Prins, 2026-10-25: tidy, short and direct). Each DIN line runs straight down from its test point in its
    # own lane (c[i] = the column of the pin). Under the band pins (3, 4, 7 and pin 1 through JP202) one stack per line:
    # 1k series (DIN pad on top), 10k pull-up, pull-down (DNP); the band net leaves sideways to U5 below. Lanes of DIN2, DIN6
    # and DIN8 stay free down to the optos. Optos in one row, outputs (radio side) up, LED side down: U204 KEY under
    # pins 1/2, U203 TX INH under pins 2/3, U205 sense under pin 8. INH LEVEL JP201, R204 and the zener D202 on the DIN6
    # lane; FEED SEL JP203 on the DIN6 lane; SENSE A/K headers JP205/JP206 beside the DIN8 lane. Logic row (gates,
    # LED resistors, pull-downs, decoupling) under the optos, toward U5.
    c = [x - 12.0 + 4.0 * i for i in range(7)]
    YB = (31.5, 35.5, 39.5)
    for col, rs, y0_ in ((c[0] + 1.3, ("R210", "R214", "R218"), 4.0), (c[2], ("R213", "R217", "R221"), 0.0),
                         (c[3], ("R212", "R216", "R220"), 0.0), (c[5], ("R211", "R215", "R219"), 0.0)):
        for y_, r_, rot_ in zip(YB, rs, (90, 90, 270)):      # the BAND_D stack lies one row lower, under JP202 pad 3
            y_ += y0_
            fix(r_, col, y_, rot_)
    fix(f"JP{n + 2}", c[0], 31.5, 0)                      # PIN1 SEL: pad 2 (DIN1) under TP201, pad 3 over R210, pad 1 to U204
    fix(f"U{n + 4}", c[0] + 1.9, 52.0, 90)                # KEY photorelay: pin 4 (to JP202 pad 1) top left, pin 3 RGND top right
    fix(f"U{n + 3}", c[0] + 7.9, 52.0, 90)                # TX INH photorelay: pin 4 (DIN2) top left, pin 3 (to JP201) top right
    fix(f"JP{n + 1}", c[0] + 12.9, 47.0, 0)               # INH LEVEL: pin 1 zener/R204, pin 2 U203 pin 3, pin 3 RGND
    fix(f"R{n + 4}", c[4], 47.0, 90)                      # 2k2 from DIN6 (top) to the zener
    fix(f"D{n + 2}", c[4], 51.5, 270)                     # BZX384-C5V1: cathode on top
    fix(f"JP{n + 3}", c[4] + 1.3, 43.5, 0)                # FEED SEL: pad 1 on the DIN6 lane, pad 3 +13V8
    fix(f"JP{n + 5}", c[6] + 3.0, 36.58, 180)             # SENSE A: pin 3 (DIN8) on top next to TP208, pin 1 down toward JP203
    fix(f"JP{n + 6}", c[6] + 3.0, 41.0, 0)                # SENSE K: pin 1 DIN8
    fix(f"U{n + 5}", c[6], 49.5, 270)                     # PC817: LED pins (1, 2) on top, outputs (3, 4) below
    fix(f"C{n + 5}", c[6] + 3.5, 20.0, 90)                # RGND to CHASSIS 10 nF 1 kV next to the connector shield
    group(f"U{n + 5}", [f"D{n + 1}", f"R{n + 6}"], (c[4] + 4.0, 38.0, reg[2], 58.0), ctx=[f"JP{n + 5}", f"JP{n + 6}"])
    # LED resistors upright straight under the LED pin 1 of their opto (pad 2 up); gates under them, inputs left with the
    # pull-down beside the input pin, decoupling upright right of the gate
    for r_, u_ in ((f"R{n + 5}", f"U{n + 4}"), (f"R{n + 3}", f"U{n + 3}")):
        p1 = next(pd for pd in fps[u_].Pads() if pd.GetNumber() == "1"); fix(r_, pad_mm(p1)[0], 59.5, 90)
    # gates turned 180: output (pin 4) top left, under the LED resistor it drives; inputs on the right with the pull-down
    # beside input pin 1; U201 output INH_ON also feeds U202 pin 2 (right side of U202, next to U201); decoupling under
    # the VCC pin (bottom left)
    fix(f"U{n + 2}", c[0] + 2.2, 64.5, 180); fix(f"R{n + 2}", c[0] + 5.5, 64.5, 270); fix(f"C{n + 2}", c[0] + 1.2, 68.3, 0)
    fix(f"U{n + 1}", c[0] + 8.9, 64.5, 180); fix(f"R{n + 1}", c[0] + 12.2, 64.5, 270); fix(f"C{n + 1}", c[0] + 7.9, 68.3, 0)
    group(f"U{n + 5}", [f"R{n + 7}"], (c[4] - 1.0, 57.0, reg[2], reg[3]))
    # GND BOND at the RGND/GND border, in the gap between the two photorelays: RGND pad on top (linked up into the island
    # in section 7), GND pad below on the GND pour
    turned(f"JP{n + 4}", c[0] + 4.1, 58.6, lambda pp: [xy for xy, n_ in pp.values() if n_ == "RGND"][0][1] <
                                                     [xy for xy, n_ in pp.values() if n_ == "GND"][0][1])
    left_ = [r for r in port_refs(0) if r not in placed]
    assert not left_, left_
    pr = port_refs(0) + ["J11"]
    clash = [(p_, q_, round(max(OBST[IDX[q_]][0] - OBST[IDX[p_]][2], OBST[IDX[p_]][0] - OBST[IDX[q_]][2],
                               OBST[IDX[q_]][1] - OBST[IDX[p_]][3], OBST[IDX[p_]][1] - OBST[IDX[q_]][3]), 2))
             for i_, p_ in enumerate(pr) for q_ in pr[i_ + 1:]]
    clash = [c_ for c_ in clash if c_[2] < 0.25]
    print("port template: courtyard gaps below 0.25 mm:", clash)
left = [c.get("ref") for c in root.iter("comp") if c.get("ref") not in placed]
assert not left, left

# ---- 7. planes, plane vias, routes (p3, M-89) ----
# Copper regions (D-89, D-130, D-145 as the controller board, D-170 stackup):
#   CHASSIS: rear strip (mini-DIN shields, J1 area, H1), the entry block down to the Y-capacitors (GDT centres, D-130),
#            a ring along the side and front edges, and a pad around the J14 shell (D-96)
#   RGND:    one island per radio port, from the CHASSIS strip down to the opto row (radio side of the optos)
#   GND:     the rest. Each net on F.Cu (pour), In1.Cu and B.Cu (planes); In2.Cu is a signal layer.
# The RGND islands and CHASSIS zones have a higher priority than GND, so GND keeps its clearance from them.
CH_Y, CH_RING = 7.5 - OVH, 3.0                       # strip edge stays 2 mm in front of the mini-DIN signal pads (D-177)
NRING = 2.0                                          # CHASSIS ring width along the display notch (D-187)
c0s = [x - 12.0 for x in MDX]
def rect(a, b_, c, d): return [(a, b_), (c, b_), (c, d), (a, d)]
def pad_box_(pd):
    bb = pd.GetBoundingBox()
    return (pcbnew.ToMM(bb.GetX()) - OX, pcbnew.ToMM(bb.GetY()) - OY, pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)
EXL, EXR = EX0 - 4.6, EX0 + 3 * EPITCH + 4.6
# USB channel (D-186): GND from x CHL to CHR down to y CHB (J14 support parts), then x EXR to the R1 island (62.0)
CHL, CHR, CHB = 54.5, 65.0, 15.5
CH_MAIN = [(0, 0), (BW, 0), (BW, CH_Y), (CHR, CH_Y), (CHR, 3.6), (CHL, 3.6), (CHL, CHB), (EXR, CHB), (EXR, YYC + 3.4),
           (EXL, YYC + 3.4), (EXL, CH_Y), (0, CH_Y)]
CH_REG = [CH_MAIN,
          rect(0, CH_Y, CH_RING, BH), rect(BW - CH_RING, CH_Y, BW, BH),
          # front ring along the notch edge (D-187), 2 mm wide there (NRING) so GND keeps its spokes at the J6, J2, J7 pads
          rect(0, NOTCH[0][2] - NRING, NOTCH[0][1], BH), rect(NOTCH[1][0] - NRING, NOTCH[1][2] - NRING, NOTCH[1][1] + NRING, BH),
          rect(NOTCH[1][1], BH - CH_RING, BW, BH)]
SHB = {}                                              # J14 shell pads only (the USB GND pads stay on GND), per side
for pd in fps["J14"].Pads():
    if pd.GetNetname() == "CHASSIS":
        a_, b_, c_, d_ = pad_box_(pd); sd = a_ < pos("J14")[0]
        o = SHB.get(sd, (1e9, -1e9, -1e9)); SHB[sd] = (min(o[0], a_ - 0.3), max(o[1], d_ + 0.3), max(o[2], c_ + 0.3))
for (a_, d_, c_) in SHB.values():
    CH_REG.append(rect(a_, 0, c_, d_))
# one CHASSIS outline for the zones (same-net zones must not overlap): the board outline with the inner area as a hole;
# the hole has notches for the entry block and the J14 shell pads
# rear: the hole takes the GND notch under the J14 signal pads, between the two shell-pad patches (D-186)
(_la, _ld, _lc), (_ra, _rd, _rc) = sorted(SHB.values())
CH_HOLE = [(CH_RING, CH_Y), (EXL, CH_Y), (EXL, YYC + 3.4), (EXR, YYC + 3.4), (EXR, CHB), (CHL, CHB), (CHL, _ld), (_lc, _ld),
           (_lc, 3.6), (_ra, 3.6), (_ra, _rd), (CHR, _rd), (CHR, CH_Y), (BW - CH_RING, CH_Y),
           (BW - CH_RING, BH - CH_RING), (NOTCH[1][1] + NRING, BH - CH_RING), (NOTCH[1][1] + NRING, NOTCH[1][2] - NRING),
           (NOTCH[1][0] - NRING, NOTCH[1][2] - NRING), (NOTCH[1][0] - NRING, NOTCH[0][2] - NRING),
           (CH_RING, NOTCH[0][2] - NRING)]
RG_REG, RG_HOLES = {}, {}
for k, (reg, c0) in enumerate(zip(PORT, c0s)):
    x0_, x1_ = reg[0], min(reg[2] + 0.5, BW - CH_RING - 0.5)
    yb, yb2 = 53.3, 55.5                              # radio side of U2x3/U2x4 ends above 53.3, of U2x5 (and R2x6) above 55.5
    xs_ = c0 + 24.0 - 3.0
    x1_ = min(reg[2], BW - CH_RING - 0.5)             # D-186: islands 0.6 mm apart (port pitch 32 mm)
    top = [(x0_, CH_Y + 0.5)] if k else [(CHR + 0.5, CH_Y + 0.5)]      # R1: corner notch for the USB channel
    tail = [(x0_, yb)] if k else [(x0_, yb), (x0_, CHB + 0.5), (CHR + 0.5, CHB + 0.5)]
    RG_REG[f"/Radio port R{k + 1}/RGND"] = top + [(x1_, CH_Y + 0.5), (x1_, yb2), (xs_, yb2), (xs_, yb)] + tail
    # holes for the band stacks: the 1k series resistor ends the radio side; its BAND pad, the pull-up and the pull-down
    # belong to the interface GND, so GND fills these holes (with room for the plane via under each stack)
    n = 200 + 100 * k
    RG_HOLES[f"/Radio port R{k + 1}/RGND"] = [
        rect(pos(top)[0] - 1.3, pos(top)[1] + 0.3, pos(top)[0] + 1.3, pos(bot)[1] + 3.2)
        for top, bot in ((f"R{n + 10}", f"R{n + 18}"), (f"R{n + 13}", f"R{n + 21}"), (f"R{n + 12}", f"R{n + 20}"), (f"R{n + 11}", f"R{n + 19}"))]
def inside(x, y, poly):
    c_ = False
    for (xa, ya), (xb, yb_) in zip(poly, poly[1:] + poly[:1]):
        if (ya > y) != (yb_ > y) and x < xa + (y - ya) * (xb - xa) / (yb_ - ya): c_ = not c_
    return c_
def region_of(x, y):
    if any(inside(x, y, p_) for p_ in CH_REG): return "CHASSIS"
    for n_, p_ in RG_REG.items():
        if inside(x, y, p_) and not any(inside(x, y, h_) for h_ in RG_HOLES[n_]): return n_
    return "GND"
def poly(pts):
    o = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in pts: o.Append(P(x, y))
    o.SetClosed(True); return o
ZONES = [("GND", [rect(0, 0, BW, BH)], 0, 0.3)] + [("CHASSIS", [rect(0, 0, BW, BH)], 2, 0.5)] + [(n_, [p_], 1, 0.3) for n_, p_ in RG_REG.items()]
RG_HOLES["CHASSIS"] = [CH_HOLE]
for netname, polys, prio, clr in ZONES:
    for pts in polys:
        for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.B_Cu):
            z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNetCode(net(netname).GetNetCode()); z.SetAssignedPriority(prio)
            z.Outline().AddOutline(poly(pts)); z.SetLocalClearance(mm(clr)); z.SetMinThickness(mm(0.25))
            for h_ in RG_HOLES.get(netname, []):
                z.Outline().AddHole(poly(h_))
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL); z.SetThermalReliefGap(mm(0.5))
            z.SetThermalReliefSpokeWidth(mm(1.0 if netname == "CHASSIS" else 0.5))
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)   # no floating pour fragments
            b.Add(z); KEEP.append(z)
# router keep-out over the display notch (D-187): export_geom.py passes rule areas to the router; pours are allowed (they
# stop at the board edge with the edge clearance)
_m = 0.6
_ra = pcbnew.ZONE(b); _ra.SetIsRuleArea(True); _ra.SetLayerSet(pcbnew.LSET.AllCuMask())
_ra.SetDoNotAllowTracks(True); _ra.SetDoNotAllowVias(True); _ra.SetDoNotAllowPads(False); _ra.SetDoNotAllowFootprints(False)
_ra.SetDoNotAllowZoneFills(False)
_ra.Outline().AddOutline(poly([(NOTCH[0][0] - _m, BH + 1.0), (NOTCH[0][0] - _m, NOTCH[0][2] - _m), (NOTCH[1][0] - _m, NOTCH[0][2] - _m),
                               (NOTCH[1][0] - _m, NOTCH[1][2] - _m), (NOTCH[1][1] + _m, NOTCH[1][2] - _m), (NOTCH[1][1] + _m, BH + 1.0)]))
b.Add(_ra); KEEP.append(_ra)
# plane vias (D-145): every SMD pad of GND, RGND or CHASSIS gets its own via to the planes of its region, next to the pad,
# with a short F.Cu stub. Pads of a plane net outside their own region get a fixed link (below). The router does not route
# these nets.
VIA_D, VIA_DR, VIA_CL, GTW = 0.6, 0.3, 0.25, 0.254
def pad_box(pd):
    bb = pd.GetBoundingBox()
    return (pcbnew.ToMM(bb.GetX()) - OX, pcbnew.ToMM(bb.GetY()) - OY, pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)
ALLPADS = [(pd, pad_box(pd)) for f in fps.values() for pd in f.Pads()]
def clear_of_pads(x, y, own, cl=VIA_CL):
    r = VIA_D / 2 + cl
    for pd, (a, b_, c, d) in ALLPADS:
        if pd is own: continue
        dx = max(a - x, 0, x - c); dy = max(b_ - y, 0, y - d)
        if (dx * dx + dy * dy) ** 0.5 < r: return False
    return True
def add_via(x, y, netname):
    v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(VIA_D)); v.SetDrill(mm(VIA_DR))
    v.SetNet(net(netname)); v.SetLocked(True); b.Add(v); KEEP.append(v)
def ftrack(pts, netname, w=GTW):
    for (xa, ya), (xb, yb_) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b); t.SetStart(P(xa, ya)); t.SetEnd(P(xb, yb_)); t.SetWidth(mm(w)); t.SetLayer(pcbnew.F_Cu)
        t.SetNet(net(netname)); t.SetLocked(True); b.Add(t); KEEP.append(t)
VIAS, FSEG = [], []                                   # plane vias; fixed link segments (x1, y1, x2, y2, net)
def seg_pt(ax, ay, bx_, by_, px, py):
    dx, dy = bx_ - ax, by_ - ay; L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)
def seg_box(ax, ay, bx_, by_, box):
    """distance from a segment to a box (sampled along the segment, 0.05 mm steps)"""
    n_ = max(2, int(math.hypot(bx_ - ax, by_ - ay) / 0.05))
    a, b_, c, d = box; m = 1e9
    for i in range(n_ + 1):
        x = ax + (bx_ - ax) * i / n_; y = ay + (by_ - ay) * i / n_
        m = min(m, math.hypot(max(a - x, 0, x - c), max(b_ - y, 0, y - d)))
    return m
def stub_ok(px, py, vx, vy, own, netname):
    """the via stub from the pad to the via keeps 0.2 mm from other-net pads, fixed links and vias"""
    for pd, box in ALLPADS:
        if pd is own or pd.GetNetname() == netname: continue
        if seg_box(px, py, vx, vy, box) < GTW / 2 + 0.2: return False
    m_ = max(2, int(math.hypot(vx - px, vy - py) / 0.05))
    for (ax, ay, bx_, by_, n_) in FSEG:
        if n_ == netname: continue
        if seg_pt(ax, ay, bx_, by_, vx, vy) < VIA_D / 2 + GTW / 2 + 0.25: return False
        if min(seg_pt(ax, ay, bx_, by_, px + (vx - px) * i / m_, py + (vy - py) * i / m_) for i in range(m_ + 1)) < GTW + 0.2: return False
    return True
def edge_ok(x, y, n_):
    return all(region_of(x + dx, y + dy) == n_ for dx, dy in ((0.8, 0), (-0.8, 0), (0, 0.8), (0, -0.8)))
# USB-C fan-out (p3, M-89): the USB4105 has one row of 0.5 mm pitch pads, and the A and B data pads alternate
# (B7 D-, A6 D+, A7 D-, B6 D+). The pads are too close for the router (clearance plus margin), so the fan-out is fixed
# copper here and the router ends on terminals (routing/terminals.json, read by export_geom.py), as U13 on the
# controller board (D-154). D+ joins A6 and B6 with a U over A7 (0.15 mm tracks); A7 drops into the U on a 0.4/0.2 via
# and runs on In2 to a second via at the end of the B7 stub (D- joined on In2). VBUS A9/B4 goes straight up to C64 pad 1;
# VBUS A4/B9, CC1 and CC2 get straight stubs up to their terminals. 45-degree corners (D-158).
def chamfer(pts, leg=0.3):
    q = [pts[0]]
    for (xa, ya), (xb, yb_), (xc, yc) in zip(pts, pts[1:], pts[2:]):
        l1, l2 = math.hypot(xb - xa, yb_ - ya), math.hypot(xc - xb, yc - yb_)
        u1, u2 = ((xb - xa) / l1, (yb_ - ya) / l1), ((xc - xb) / l2, (yc - yb_) / l2)
        if abs(u1[0] * u2[0] + u1[1] * u2[1]) > 0.01: q.append((xb, yb_)); continue
        d = min(leg, 0.45 * l1, 0.45 * l2)
        q += [(round(xb - u1[0] * d, 4), round(yb_ - u1[1] * d, 4)), (round(xb + u2[0] * d, 4), round(yb_ + u2[1] * d, 4))]
    return q + [pts[-1]]
def ftrack2(pts, netname, w, layer=pcbnew.F_Cu):
    pts = chamfer(pts)
    for (xa, ya), (xb, yb_) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b); t.SetStart(P(xa, ya)); t.SetEnd(P(xb, yb_)); t.SetWidth(mm(w)); t.SetLayer(layer)
        t.SetNet(net(netname)); t.SetLocked(True); b.Add(t); KEEP.append(t)
        FSEG.append((xa, ya, xb, yb_, netname))
def svia(x, y, netname, d=0.4, dr=0.2):
    v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(d)); v.SetDrill(mm(dr))
    v.SetNet(net(netname)); v.SetLocked(True); b.Add(v); KEEP.append(v); VIAS.append((x, y))
JP_ = {pd.GetNumber(): (pad_mm(pd), pd.GetNetname()) for pd in fps["J14"].Pads() if pd.GetNumber()}
def jx(num): return JP_[num][0][0]
JY, NDP, NDN = JP_["A6"][0][1], JP_["A6"][1], JP_["A7"][1]
assert NDP == JP_["B6"][1] and NDN == JP_["B7"][1] and min(jx("B6"), jx("A6")) < jx("A7") < max(jx("B6"), jx("A6")), JP_
# J14 turned 180 at the rear edge (D-186): the fan-out runs in +y (into the board); same pattern as p3 to p6
YU, YV1, YV2 = JY + 1.85, JY + 1.15, JY + 3.2             # U top, via inside the U, via at the end of the B7 stub
ftrack2([(jx("A6"), JY), (jx("A6"), YU), (jx("B6"), YU), (jx("B6"), JY)], NDP, 0.15)
ftrack2([(jx("A7"), JY), (jx("A7"), YV1)], NDN, 0.15); svia(jx("A7"), YV1, NDN)
ftrack2([(jx("B7"), JY), (jx("B7"), YV2)], NDN, 0.15); svia(jx("B7"), YV2, NDN)
ftrack2([(jx("A7"), YV1), (jx("A7"), YV2), (jx("B7"), YV2)], NDN, 0.15, pcbnew.In2_Cu)
# VBUS: both pad pairs (A4/B9, A9/B4) get a straight 0.3 mm stub inward; the router joins them to C64 and U61 pin 5
VB = JP_["A9"][1]
YVB, YT = JY + 2.05, JY + 2.6
for n_ in ("A4", "A9"):
    ftrack2([(jx(n_), JY), (jx(n_), YVB)], VB, 0.3)
# GND pads A1/B12 and A12/B1: a fixed plane via straight inward of each pad, outside the VBUS stub
HANDLED = set()
for n_ in ("A1", "A12"):
    sx = 1.0 if jx(n_) > JX else -1.0
    ftrack2([(jx(n_), JY), (jx(n_) + 0.1 * sx, JY + 1.6)], "GND", 0.254); svia(jx(n_) + 0.1 * sx, JY + 1.6, "GND", 0.6, 0.3)
    HANDLED |= {("J14", n_), ("J14", {"A1": "B12", "A12": "B1"}[n_])}
ftrack2([(jx("A5"), JY), (jx("A5"), YT)], JP_["A5"][1], 0.15)
ftrack2([(jx("B5"), JY), (jx("B5"), YT)], JP_["B5"][1], 0.15)
TERM_J14 = {"A6": [jx("A6") / 2 + jx("B6") / 2, YU, ["F"]], "B6": [jx("A6") / 2 + jx("B6") / 2, YU, ["F"]],
            "A7": [jx("B7"), YV2, ["F", "B"]], "B7": [jx("B7"), YV2, ["F", "B"]],
            "A9": [jx("A9"), YVB, ["F"]], "B4": [jx("A9"), YVB, ["F"]],
            "A4": [jx("A4"), YVB, ["F"]], "B9": [jx("A4"), YVB, ["F"]],
            "A5": [jx("A5"), YT, ["F"]], "B5": [jx("B5"), YT, ["F"]]}
# U5 VDD (pin 24, a corner pin at 0.65 mm pitch): fixed 0.3 mm link to its decoupling capacitor C61 pad 1; the router
# ends on C61 pad 1 (a power track cannot leave the pin between its neighbours with the router margin)
p24 = next(pd for pd in fps["U5"].Pads() if pd.GetNumber() == "24")
c61 = next(pd for pd in fps["C61"].Pads() if pd.GetNetname() == p24.GetNetname())
ftrack2([pad_mm(p24), pad_mm(c61)], p24.GetNetname(), 0.3)
# U4, U9 fan-out (D-190, as controller U13, D-154 and M-68): VSSOP-8 at 0.5 mm pitch; the pad gap (0.15 mm) is below the
# clearance and the router keep-out. Pins 6 and 8 (+3V3): 0.2 mm strap outside the pad tips, terminal at its middle; pin 7
# (RESET_N at U4, PRE_N at U9) and pin 4 (GND): stubs inward to vias under the body; pin 2 (GND) to pin 4 around pin 3 (NC).
# Pads get a local clearance of 0.12 mm (pad to pad only). Written for any rotation (U4 is turned 180 by its group).
TERM_U = {}
for u in ("U4", "U9"):
    UP = {pd.GetNumber(): pad_mm(pd) for pd in fps[u].Pads()}
    UN = {pd.GetNumber(): pd.GetNetname() for pd in fps[u].Pads()}
    for pd in fps[u].Pads(): pd.SetLocalClearance(mm(0.12))
    assert UN["6"] == UN["8"] == "+3V3" and UN["2"] == UN["4"] == "GND", (u, UN)
    ucx, ucy = pos(u)
    sx = 1.0 if UP["8"][0] > ucx else -1.0                 # side of pins 5 to 8
    SXU = 2.6
    p2, p4, p6, p7, p8 = (UP[k] for k in "24678")
    ftrack2([p8, (ucx + sx * SXU, p8[1]), (ucx + sx * SXU, p6[1]), p6], "+3V3", 0.2)
    v7, v4 = (ucx, p7[1]), (ucx, p4[1])
    ftrack2([p7, v7], UN["7"], 0.2); ftrack2([p4, v4], "GND", 0.2)
    ftrack2([p2, (ucx - sx * SXU, p2[1]), (ucx - sx * SXU, p4[1]), p4], "GND", 0.2)
    for v, n_ in ((v7, UN["7"]), (v4, "GND")):
        add_via(v[0], v[1], n_); VIAS.append(v)
    HANDLED |= {(u, "2"), (u, "4")}
    TERM_U[u] = {"6": [ucx + sx * SXU, (p8[1] + p6[1]) / 2, ["F"]], "8": [ucx + sx * SXU, (p8[1] + p6[1]) / 2, ["F"]],
                 "7": [v7[0], v7[1], ["F", "In2"]]}
json.dump({"J14": TERM_J14, "U5": {"24": [pad_mm(c61)[0], pad_mm(c61)[1], ["F"]]}, **TERM_U}, open("routing/terminals.json", "w"), indent=1)
# fixed links for plane-net pads outside their own region
for k, c0 in enumerate(c0s):
    n = 200 + 100 * k
    jp = fps[f"JP{n + 4}"]                                 # GND BOND: RGND pad up into the island, GND pad on the GND pour
    rp = next(pd for pd in jp.Pads() if base(pd.GetNetname()) == "RGND"); x_, y_ = pad_mm(rp)
    ftrack([(x_, y_), (x_, 52.0)], rp.GetNetname()); add_via(x_, 52.0, rp.GetNetname()); VIAS.append((x_, 52.0))
    FSEG.append((x_, y_, x_, 52.0, rp.GetNetname()))
    cp = next(pd for pd in fps[f"C{n + 5}"].Pads() if pd.GetNetname() == "CHASSIS"); x_, y_ = pad_mm(cp)
    ftrack([(x_, y_), (x_, CH_Y - 1.5)], "CHASSIS", 0.508); add_via(x_, CH_Y - 1.5, "CHASSIS"); VIAS.append((x_, CH_Y - 1.5))
    FSEG.append((x_, y_, x_, CH_Y - 1.5, "CHASSIS"))
# GND links of the band-stack holes (the holes lie inside the RGND island): a via at the bottom of each hole and an In2.Cu
# track straight down, past the opto row, to a via in the GND area below the island border. Column 3 jogs left of the
# JP201 pins; the BAND_D column ends below U204 (its LED pads are on F.Cu only).
for k, c0 in enumerate(c0s):
    n_ = f"/Radio port R{k + 1}/RGND"
    for i_, (hx0, hy0, hx1, hy1) in enumerate([(h_[0][0], h_[0][1], h_[2][0], h_[2][1]) for h_ in RG_HOLES[n_]]):
        cxh = (hx0 + hx1) / 2; y0_ = hy1 - 0.9
        path = {0: [(cxh, y0_), (cxh, 57.3)], 1: [(cxh, y0_), (cxh, 57.3)],
                2: [(cxh, y0_), (cxh - 0.7, y0_ + 0.7), (cxh - 0.7, 57.3)], 3: [(cxh, y0_), (cxh, 55.0)]}[i_]
        ftrack2(path, "GND", 0.254, pcbnew.In2_Cu)
        for q in (path[0], path[-1]):
            add_via(q[0], q[1], "GND"); VIAS.append(q)
FIXED = {f"JP{200 + 100 * k + 4}" for k in range(3)} | {f"C{200 + 100 * k + 5}" for k in range(3)}
pv, miss, DONE = 0, [], set()
ALLPADS = [(pd, pad_box(pd)) for f in fps.values() for pd in f.Pads()]
for f in fps.values():
    if f.GetReference() in FIXED: continue
    fx, fy = pos(f.GetReference())
    for pd in f.Pads():
        pn = pd.GetNetname()
        if not (pn in ("GND", "CHASSIS") or base(pn) == "RGND") or pd.GetAttribute() != pcbnew.PAD_ATTRIB_SMD: continue
        a, b_, c, d = pad_box(pd); px, py = (a + c) / 2, (b_ + d) / 2
        if (round(px, 2), round(py, 2), pn) in DONE or (f.GetReference(), pd.GetNumber()) in HANDLED: continue   # stacked pads, fixed links
        DONE.add((round(px, 2), round(py, 2), pn))
        ox, oy = px - fx, py - fy
        dirs = sorted(((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)),
                      key=lambda u: -(u[0] * ox + u[1] * oy) / (abs(u[0]) + abs(u[1])) ** 0.5)
        hx, hy = (c - a) / 2, (d - b_) / 2
        cand = [(px + ux * (hx + VIA_D / 2 + g), py + uy * (hy + VIA_D / 2 + g)) for g in (0.15, 0.4, 0.7, 1.0, 1.4, 1.8, 2.4, 3.0) for ux, uy in dirs]
        spot = next((q for q in cand if clear_of_pads(q[0], q[1], pd) and edge_ok(q[0], q[1], pn) and stub_ok(px, py, q[0], q[1], pd, pn)
                     and XL + 0.8 < q[0] < XR - 0.8 and 0.8 < q[1] < BH - 0.8 and not in_notch(q[0], q[1], 0.8)
                     and all((q[0] - a_) ** 2 + (q[1] - b2) ** 2 >= 1.0 for a_, b2 in VIAS)), None)
        if spot is None: miss.append(f"{f.GetReference()}.{pd.GetNumber()}"); continue
        add_via(spot[0], spot[1], pn); VIAS.append(spot); ftrack([(px, py), spot], pn); pv += 1
print("plane vias", pv, "| no place:", miss)
# keep-out for the router (D-89): nets of the interface side do not run over an RGND island (their reference plane would
# change); nets with a pad in the island (radio side, and the deliberate crossings such as +13V8 to FEED SEL) may
ko = []
for n_, poly_ in RG_REG.items():
    # nets with a pad in the island, or in a band-stack hole of it (BAND, +3V3: slow DC lines that cross the island to the
    # stack; the GND BOND carries their return, D-89)
    inn = sorted({pd.GetNetname() for f in fps.values() for pd in f.Pads() if pd.GetNetname()
                  and (region_of(*pad_mm(pd)) == n_ or (inside(*pad_mm(pd), poly_) and pd.GetNetname() not in ("GND",)))})
    ko.append({"poly": poly_, "holes": RG_HOLES[n_], "except": inn})
USBN = {NDP, NDN, VB, JP_["A5"][1], JP_["B5"][1]}
ALLN = sorted({pd.GetNetname() for f in fps.values() for pd in f.Pads() if pd.GetNetname()})
ko.append({"poly": CH_MAIN, "holes": [], "except": [n_ for n_ in ALLN if n_ not in USBN]})
json.dump({"keepout": ko}, open("routing/keepout.json", "w"), indent=1)
# tracks and vias from the general router (routing/routes.json); --no-routes leaves them out (board for export_geom.py)
ROUTES = "routing/routes.json"
if os.path.exists(ROUTES) and "--no-routes" not in sys.argv:
    rj = json.load(open(ROUTES))
    assert not rj["failed"], rj["failed"]
    LYR = {"F": pcbnew.F_Cu, "In2": pcbnew.In2_Cu, "B": pcbnew.B_Cu, "In1": pcbnew.In1_Cu}
    for t in rj["tracks"]:
        if abs(t["x2"] - t["x1"]) + abs(t["y2"] - t["y1"]) < 1e-6: continue   # zero-length pieces at terminals (p7)
        tr = pcbnew.PCB_TRACK(b); tr.SetStart(P(t["x1"], t["y1"])); tr.SetEnd(P(t["x2"], t["y2"])); tr.SetWidth(mm(t["w"]))
        tr.SetLayer(LYR[t["layer"]]); tr.SetNet(net(t["net"])); b.Add(tr); KEEP.append(tr)
    for v in rj["vias"]:
        vi = pcbnew.PCB_VIA(b); vi.SetPosition(P(v["x"], v["y"])); vi.SetWidth(mm(v["d"])); vi.SetDrill(mm(v["drill"]))
        vi.SetNet(net(v["net"])); b.Add(vi); KEEP.append(vi)
    print("routes", len(rj["tracks"]), "tracks", len(rj["vias"]), "vias")
    # stitching vias (D-145, skill section 8), after routing (as stitch.py on the RF board): a 5 mm grid over every plane
    # region (GND, each RGND island, CHASSIS); each via inside its own region with 0.8 mm around it, clear of pads, of every
    # track and via of another net (0.25 mm), and 2 mm from other vias
    SEGS = collections.defaultdict(list)                  # 5 mm buckets of (x1, y1, x2, y2, half width, net)
    def bucket(x, y): return (int(x // 5), int(y // 5))
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T:
            x1, y1 = pcbnew.ToMM(t.GetStart().x) - OX, pcbnew.ToMM(t.GetStart().y) - OY
            x2, y2 = pcbnew.ToMM(t.GetEnd().x) - OX, pcbnew.ToMM(t.GetEnd().y) - OY
            rec = (x1, y1, x2, y2, pcbnew.ToMM(t.GetWidth()) / 2, t.GetNetname())
        elif t.Type() == pcbnew.PCB_VIA_T:
            x1, y1 = pcbnew.ToMM(t.GetPosition().x) - OX, pcbnew.ToMM(t.GetPosition().y) - OY
            x2, y2 = x1, y1; rec = (x1, y1, x1, y1, pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2, t.GetNetname())
            VIAS.append((x1, y1))
        else:
            continue
        for bx_ in range(int(min(x1, x2) // 5) - 1, int(max(x1, x2) // 5) + 2):
            for by_ in range(int(min(y1, y2) // 5) - 1, int(max(y1, y2) // 5) + 2):
                SEGS[(bx_, by_)].append(rec)
    VB_ = collections.defaultdict(list)
    for (a_, b2_) in VIAS: VB_[bucket(a_, b2_)].append((a_, b2_))
    import fnmatch
    def clr_of(nn):                                       # netclass clearance (Entry and Loop 0.5 mm, others 0.2 mm)
        return 0.5 if any(fnmatch.fnmatchcase(nn, p_) for p_ in ("*/L?P", "*/L?N", "Net-(C2?-Pad?)")) else 0.25
    PCL = [(box, clr_of(pd.GetNetname())) for pd, box in ALLPADS if clr_of(pd.GetNetname()) > 0.3]
    st = collections.Counter()
    for gy in [2.5 + 5.0 * i for i in range(int(BH // 5) + 1)]:
        for gx in [2.5 + 5.0 * i for i in range(int(BW // 5) + 1)]:
            for dx, dy in ((0, 0), (1.0, 0), (-1.0, 0), (0, 1.0), (0, -1.0), (1.0, 1.0), (-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0)):
                x, y = gx + dx, gy + dy
                if not (XL + 1.2 < x < XR - 1.2 and 1.2 < y < BH - 1.2) or in_notch(x, y, 1.2): continue
                n_ = region_of(x, y)
                if not edge_ok(x, y, n_) or not clear_of_pads(x, y, None, 0.3): continue
                if any(math.hypot(max(a_ - x, 0, x - c_), max(b2_ - y, 0, y - d_)) < VIA_D / 2 + cl_ for (a_, b2_, c_, d_), cl_ in PCL): continue
                kx, ky = bucket(x, y)
                if any(math.hypot(x - a_, y - b2_) < 2.0 for i_ in (-1, 0, 1) for j_ in (-1, 0, 1) for a_, b2_ in VB_[(kx + i_, ky + j_)]): continue
                if any(seg_pt(x1, y1, x2, y2, x, y) < VIA_D / 2 + hw + clr_of(nn) for (x1, y1, x2, y2, hw, nn) in SEGS[(kx, ky)] if nn != n_): continue
                add_via(x, y, n_); VIAS.append((x, y)); VB_[(kx, ky)].append((x, y)); st[base(n_)] += 1; break
    print("stitching vias", dict(st))
# ---- 8. silkscreen p4 (skill schematic-and-marking.md; D-152, D-172): zone frames with titles, jumper settings at the
# jumper pins (Prins, 2026-10-25), connector and test point labels, art block, stackup and jumper tables on the back,
# then every reference clear of pads, silk and the other texts. Text 1.0 mm, line 0.15 mm (as the RF board p3).
SH, ST = 1.0, 0.15
# panel connectors overhang the board edge (D-177): their body outlines on F.SilkS end 0.4 mm inside the edge
for ref in ("J1", "J3", "J11", "J12", "J13", "J14"):
    f_ = fps[ref]; yl = 0.4
    for g in list(f_.GraphicalItems()):
        if g.GetLayer() != pcbnew.F_SilkS or g.Type() != pcbnew.PCB_SHAPE_T or g.GetShape() != pcbnew.SHAPE_T_SEGMENT: continue
        a_, b_ = g.GetStart(), g.GetEnd(); ya, yb = pcbnew.ToMM(a_.y) - OY, pcbnew.ToMM(b_.y) - OY
        out = lambda y: y < yl
        if out(ya) and out(yb): f_.Remove(g); continue
        if out(ya) != out(yb):
            xa, xb = pcbnew.ToMM(a_.x) - OX, pcbnew.ToMM(b_.x) - OX; t_ = (yl - ya) / (yb - ya); xm = xa + t_ * (xb - xa)
            if out(ya): g.SetStart(P(xm, yl))
            else: g.SetEnd(P(xm, yl))
for ref in ["JP61"] + [f"JP{200 + 100 * k + j}" for k in range(3) for j in (2, 3)]:   # pad numbers give way to the setting names
    for g in list(fps[ref].GraphicalItems()):
        if g.Type() == pcbnew.PCB_TEXT_T and g.GetLayer() == pcbnew.F_SilkS and g.GetText() in ("1", "2", "3"): fps[ref].Remove(g)
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
def sline(xa, ya, xb, yb, side="F", keep=True):
    ly = pcbnew.F_SilkS if side == "F" else pcbnew.B_SilkS
    l = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); l.SetStart(P(xa, ya)); l.SetEnd(P(xb, yb)); l.SetLayer(ly)
    l.SetWidth(mm(ST)); b.Add(l); KEEP.append(l)
    if keep: SILK[ly].append(bx(l.GetBoundingBox(), 0.1))
def obstacles(side_cu, side_silk, side_crt):
    pads, silk, crt = [], [], []
    for f in fps.values():
        for pd in f.Pads():
            if pd.IsOnLayer(side_cu): pads.append(bx(pd.GetBoundingBox(), 0.25))
        for g in f.GraphicalItems():
            if g.GetLayer() == side_silk and g.Type() in (pcbnew.PCB_SHAPE_T, pcbnew.PCB_TEXT_T) and (g.Type() != pcbnew.PCB_TEXT_T or g.IsVisible()):
                silk.append(bx(g.GetBoundingBox(), 0.1 if g.Type() == pcbnew.PCB_SHAPE_T else 0.5))
        cy_ = f.GetCourtyard(side_crt)
        if cy_.OutlineCount(): crt.append((f, bx(cy_.BBox())))
    return pads, silk, crt
OBS = {"F": obstacles(pcbnew.F_Cu, pcbnew.F_SilkS, pcbnew.F_CrtYd), "B": obstacles(pcbnew.B_Cu, pcbnew.B_SilkS, pcbnew.B_CrtYd)}
def free_box(box, side="F", crt_too=True, edge=1.0):
    pads, silk, crt = OBS[side]; ly = pcbnew.F_SilkS if side == "F" else pcbnew.B_SilkS
    if box[0] < XL + edge or box[2] > XR - edge or box[1] < edge or box[3] > BH - edge or box_in_notch(box, edge): return False
    if any(hit(box, o) for o in pads + silk + SILK[ly]): return False
    return not (crt_too and any(hit(box, c) for _, c in crt))
def tsize(s, rot=0.0, h=SH, t=ST):
    o = pcbnew.PCB_TEXT(b); o.SetText(s); o.SetLayer(pcbnew.F_SilkS); o.SetTextSize(pcbnew.VECTOR2I(mm(h), mm(h)))
    o.SetTextThickness(mm(t)); o.SetTextAngleDegrees(rot); o.SetPosition(P(0, 0)); bb = bx(o.GetBoundingBox()); KEEP.append(o)
    return bb[2] - bb[0], bb[3] - bb[1]
def find_spot(w, h, near, side="F", step=0.5, rmax=12.0, crt_too=True):
    n_ = int(rmax / step)
    cand = sorted(((near[0] + i * step, near[1] + j * step) for i in range(-n_, n_ + 1) for j in range(-n_, n_ + 1)),
                  key=lambda c: math.hypot(c[0] - near[0], c[1] - near[1]))
    return next(((x, y) for (x, y) in cand if math.hypot(x - near[0], y - near[1]) <= rmax
                 and free_box((x - w / 2, y - h / 2, x + w / 2, y + h / 2), side, crt_too)), None)
SILK_MISS = []
def label(s, near, rot=0.0, side="F", rmax=8.0):
    for r_, rm, ct in ((rot, rmax, True), ((rot + 90.0) % 180.0, rmax, True), (rot, rmax, False), ((rot + 90.0) % 180.0, rmax, False)):
        w, h = tsize(s, r_); spot = find_spot(w + 0.4, h + 0.4, near, side, rmax=rm, crt_too=ct)
        if spot: return text(s, spot[0], spot[1], side, rot=r_)
    SILK_MISS.append(s); return None

# zone frames (D-172): a frame per function zone with its title on the top left. The frame lines are broken where they
# would cross a pad (0.25 mm) so that no silk is clipped by the solder mask.
FRAMES = [("POWER", Z["power"]), ("CAT6 ENTRY", Z["entry"]), ("SAFE LOOPS", Z["loops"]), ("SAFE LATCH", Z["latch"]),
          ("EXPANDER", Z["exp"]), ("MCU", (Z["mcu"][0], Z["mcu"][1], Z["mcu"][2], BH - SIDE))] + \
         [(f"RADIO PORT R{k + 1}", reg) for k, reg in enumerate(PORT)]
def frame_seg(xa, ya, xb, yb):
    pads = OBS["F"][0] + OBS["F"][1]; n_ = max(1, int(math.hypot(xb - xa, yb - ya) / 0.25)); run = None   # pads and part silk
    for i in range(n_ + 1):
        x, y = xa + (xb - xa) * i / n_, ya + (yb - ya) * i / n_
        ok = not any(o[0] - 0.1 < x < o[2] + 0.1 and o[1] - 0.1 < y < o[3] + 0.1 for o in pads) and not in_notch(x, y, 0.9)
        if ok and run is None: run = (x, y)
        if (not ok or i == n_) and run is not None:
            e = (x, y) if ok else (xa + (xb - xa) * (i - 1) / n_, ya + (yb - ya) * (i - 1) / n_)
            if math.hypot(e[0] - run[0], e[1] - run[1]) > 0.5: sline(run[0], run[1], e[0], e[1])
            run = None
for name, (x0, y0, x1, y1) in FRAMES:
    x0, y0, x1, y1 = x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3
    for s_ in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)): frame_seg(*s_)
    if box_in_notch((x0, y0, x1, y1), 0.9):           # D-187: close the frame along the notch edge, 1.0 mm inside it
        (_a, _b, _y0), (_c, _d, _y1) = NOTCH
        xa_ = max(x0, _a - 1.0); xd_ = min(x1, _d + 1.0)
        path = [(xa_, _y0 - 1.0), (_b - 1.0, _y0 - 1.0), (_b - 1.0, _y1 - 1.0), (xd_, _y1 - 1.0), (xd_, y1)]
        for (pa, pb) in zip(path, path[1:]):
            if pa[0] >= x0 - 1e-6 and pb[0] >= x0 - 1e-6: frame_seg(*pa, *pb)

# radio ports: the three ports are one template copied at the connector pitch (35 mm), so each label is placed at the
# first spot that is free in all three ports, and the three ports carry the same silk
PITCH = MDX[1] - MDX[0]
def free_all(box):
    return all(free_box((box[0] + k * PITCH, box[1], box[2] + k * PITCH, box[3]), crt_too=False) for k in range(3))
def port_text(s, cand):
    """cand: (x, y, rot) for port R1, in order of preference; placed in all three ports at the first common free spot"""
    for x, y, rot in cand:
        w, h = tsize(s, rot)
        if free_all((x - w / 2, y - h / 2, x + w / 2, y + h / 2)):     # pads carry 0.25 mm, silk 0.1 mm already
            for k in range(3): text(s.replace("{k}", str(k + 2)), x + k * PITCH, y, rot=rot)
            return True
    SILK_MISS.append(s); return False
def pad_cand(pd, s, away):
    """candidates around pad pd: beyond the pad end in direction away, then beside the pad, at 0 and 90 degrees"""
    a_, b_, c_, d_ = bx(pd.GetBoundingBox()); px, py = (a_ + c_) / 2, (b_ + d_) / 2; hx, hy = (c_ - a_) / 2, (d_ - b_) / 2
    out = []
    for rot in (0.0, 90.0):
        w, h = tsize(s, rot)
        for e_ in (0.35, 0.6, 0.9):
            for sl in (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0, 2.5, 3.0):
                for ux, uy in (away, (-away[1], away[0]), (away[1], -away[0])):
                    ext = abs(ux) * (hx + e_ + w / 2) + abs(uy) * (hy + e_ + h / 2)
                    out.append((px + ux * ext + uy * sl, py + uy * ext + ux * sl, rot))
    return out
# test points DIN1 to DIN8: the pin number above each test point, "DIN" after the row
for n in (1, 2, 3, 4, 6, 7, 8):
    tp = fps[f"TP20{n}"]; x, y = pos(f"TP20{n}")
    port_text(str(n), [(x + sl, y - 2.0 - d_, 0.0) for d_ in (0.0, 0.2, 0.4, 0.6, 0.8) for sl in (0.0, 0.4, -0.4)])
x8, y8 = pos("TP208"); port_text("DIN", [(x8 + 3.0 + d_, y8, 0.0) for d_ in (0.0, 0.3, 0.6)] + [(x8 + 2.4, y8 + d_, 90.0) for d_ in (0.0, -1.0, 1.0)])
TPS = {r for r in fps if r.startswith("TP")}
# jumper settings (Prins, 2026-10-25): the setting name at each end pin of a 3-way jumper, the function with the reference
# beside the jumper. Settings from the schematic (D-86, D-90, D-94, D-71); the full table per port is on the back.
JPSET = {"01": ("TX INH", "HI", "LO"), "02": ("PIN 1", "KEY", "BAND"), "03": (None, "RADIO", "13V8"),
         "04": ("GND BOND", None, None), "05": ("SENSE A", "CONT", "VOLT"), "06": ("SENSE K", "CONT", "VOLT")}
# the function name stands at the jumper; the reference is placed with the other references
JPS = {f"JP{200 + 100 * k + int(s_)}": v for k in range(3) for s_, v in JPSET.items()}
JPS["JP61"] = ("SDA", "RUST-1", "RUST-2")      # pad 1 = RUST-1, bridged to 2 by copper (D-192)
def jp_axis(ref):
    pdn = {pd.GetNumber(): pd for pd in fps[ref].Pads()}
    p1 = pad_mm(pdn["1"]); pl = pad_mm(pdn["3"] if "3" in pdn else pdn["2"])
    L_ = math.hypot(pl[0] - p1[0], pl[1] - p1[1]); return pdn, ((pl[0] - p1[0]) / L_, (pl[1] - p1[1]) / L_)
for j_, (fn, s1, s3) in JPSET.items():                 # pin names first (they must sit at the pin), then the titles
    ref = f"JP2{j_}"; pdn, u = jp_axis(ref)
    if s1:
        port_text(s1, pad_cand(pdn["1"], s1, (-u[0], -u[1]))); port_text(s3, pad_cand(pdn["3"], s3, u))
for j_, (fn, s1, s3) in JPSET.items():
    if fn is None: continue
    ref = f"JP2{j_}"; pdn, u = jp_axis(ref); cx, cy = pos(ref)
    fb = bx(fps[ref].GetBoundingBox(False))
    cand = []
    for rot in (90.0, 0.0):
        w, h = tsize(fn, rot)
        for d_ in (0.3, 0.6, 1.0, 1.5):                  # close to the jumper only; no title is better than a title at the wrong part
            for sl in (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5):
                cand += [(fb[0] - d_ - w / 2, cy + sl, rot), (fb[2] + d_ + w / 2, cy + sl, rot),
                         (cx + sl, fb[1] - d_ - h / 2, rot), (cx + sl, fb[3] + d_ + h / 2, rot)]
    if not port_text(fn, cand): SILK_MISS[-1] = f"title {fn} (reference only)"
pdn, u = jp_axis("JP61")
for s_, pd_, a_ in (("RUST-1", pdn["1"], (-u[0], -u[1])), ("RUST-2", pdn["3"], u)):
    for x, y, rot in pad_cand(pd_, s_, a_):
        w, h = tsize(s_, rot)
        if free_box((x - w / 2 - 0.1, y - h / 2 - 0.1, x + w / 2 + 0.1, y + h / 2 + 0.1), crt_too=False):
            text(s_, x, y, rot=rot); break
    else: SILK_MISS.append(s_)
cx, cy = pos("JP61"); label("SDA", (cx, cy - 2.4), rmax=6.0)
# zone titles: in a corner inside the frame, top left first
for name, (x0, y0, x1, y1) in FRAMES:
    x0, y0, x1, y1 = x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3
    w, h = tsize(name, h=1.2, t=0.2)
    for cx_, cy_ in ((x0 + w / 2 + 0.6, y0 + h / 2 + 0.5), (x0 + w / 2 + 0.6, y1 - h / 2 - 0.5),
                     (x1 - w / 2 - 0.6, y0 + h / 2 + 0.5), (x1 - w / 2 - 0.6, y1 - h / 2 - 0.5)):
        sp = find_spot(w + 0.4, h + 0.4, (cx_, cy_), rmax=4.0, crt_too=False)
        if sp and x0 < sp[0] - w / 2 and sp[0] + w / 2 < x1 and y0 < sp[1] - h / 2 and sp[1] + h / 2 < y1:
            text(name, sp[0], sp[1], h=1.2, t=0.2); break
    else:
        SILK_MISS.append(name)
# connectors, power test points, chassis bond
for ref, s in (("J1", "CAT6 TO BOX"), ("J3", "13.8 V IN"), ("J11", "R1 RADIO"), ("J12", "R2 RADIO"), ("J13", "R3 RADIO"),
               ("J14", "USB"), ("J2", "KILL"), ("J7", "KILL STATE"), ("J15", "DISPLAY"),
               ("H1", "CHASSIS")):
    x, y = pos(ref); fps[ref].Reference().SetVisible(False)
    near = (x, y + (8.0 if y < BH / 2 else -4.0))
    label(f"{ref} {s}" if ref not in ("H1",) else s, near, rmax=14.0)
x, y = pos("J6"); fps["J6"].Reference().SetVisible(False); label("J6 1 RST 2 SAFE 3 LATCH 4 GND", (x + 6.0, y - 4.0), rmax=12.0)
for ref in ("TP1", "TP2", "TP3"):
    fps[ref].Reference().SetVisible(False); x, y = pos(ref)
    label(f"{ref} {fps[ref].GetValue()}", (x, y + 2.2))
for ref in TPS: fps[ref].Reference().SetVisible(False)

# art block with the board signature (D-152, D-176: the SAFE latch U9, 74LVC1G74, as an IEC 60617 D flip-flop):
# S with negation = PRE_N (loop OK AND power-on reset), 1D = 0, C1 with the dynamic input = RESET_CLK (RESET button),
# Q = LATCHED. Title lines and truth table on the left, symbol on the right.
def scircle(x, y, r):
    c = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_CIRCLE); c.SetCenter(P(x, y)); c.SetEnd(P(x + r, y)); c.SetLayer(pcbnew.F_SilkS)
    c.SetWidth(mm(ST)); b.Add(c); KEEP.append(c)
TITLE = [("SHACK RELAY MATRIX", 1.5, 0.3), (f"Shack interface  rev A  ({REV})", SH, ST), ("2026-10", SH, ST), ("73 de PE1RGU", SH, ST)]
TRUTH = ["PRE_N 0  ->  LATCHED 1", "RESET, PRE_N 1  ->  LATCHED 0", "PRE_N = SAFE_OK AND POR_N"]
LW = max(max(tsize(t_, h=h_, t=w_)[0] for t_, h_, w_ in TITLE), max(tsize(t_)[0] for t_ in TRUTH))
INW = max(tsize(t_)[0] for t_ in ("PRE_N", "RESET", "0"))
BXW, BXH = 7.0, 11.0
SYW = INW + 2.8 + BXW + 2.5 + tsize("LATCHED")[0]
ART_W = max(LW, SYW) + 2.0; ART_H = 8.0 + BXH + 2.0 + 2.0 * len(TRUTH) + 2.0        # title, symbol, truth table, stacked
sp = find_spot(ART_W, ART_H, (BW - ART_W / 2 - 4.0, BH - ART_H / 2 - 6.0), step=1.0, rmax=60.0)
if sp:
    AX, AY = sp[0] - ART_W / 2 + 1.0, sp[1] - ART_H / 2 + 1.5
    ys = (AY, AY + 2.6, AY + 4.6, AY + 6.6)
    for (t_, h_, w_), y_ in zip(TITLE, ys): text(t_, AX, y_, h=h_, t=w_, just="l")
    gx0 = AX + INW + 2.8; gy0 = AY + 8.5; gx1, gy1 = gx0 + BXW, gy0 + BXH
    for n_, t_ in enumerate(TRUTH): text(t_, AX, gy1 + 2.0 + 2.0 * n_, just="l")
    for xa, ya, xb, yb in ((gx0, gy0, gx1, gy0), (gx1, gy0, gx1, gy1), (gx1, gy1, gx0, gy1), (gx0, gy1, gx0, gy0)):
        sline(xa, ya, xb, yb)
    yS, yD, yC = gy0 + 2.5, gy0 + 5.5, gy0 + 8.5
    scircle(gx0 - 0.45, yS, 0.45); sline(gx0 - 2.6, yS, gx0 - 0.9, yS)          # S, active low (negation circle)
    text("S", gx0 + 1.2, yS); text("PRE_N", gx0 - 2.9, yS, just="r")
    sline(gx0 - 2.6, yD, gx0, yD); text("1D", gx0 + 1.6, yD); text("0", gx0 - 2.9, yD, just="r")
    sline(gx0 - 2.6, yC, gx0, yC); text("RESET", gx0 - 2.9, yC, just="r")      # C1 with the dynamic input indicator
    sline(gx0, yC - 0.6, gx0 + 0.9, yC); sline(gx0 + 0.9, yC, gx0, yC + 0.6); text("C1", gx0 + 2.4, yC)
    sline(gx1, yS, gx1 + 2.2, yS); text("LATCHED", gx1 + 2.5, yS, just="l")
else:
    SILK_MISS.append("art block")

# back: jumper table per radio port under its column, stackup legend
JTAB = ("JUMPERS  R{n}", "TX sense CONTACT: A, K 1-2", "TX sense VOLTAGE: A, K 2-3", "TX INH: HI 1-2  LO 2-3  open off",
        "PIN 1: KEY 2-1  BAND D 2-3", "FEED: RADIO 2-1  13V8 2-3", "GND BOND: close for BAND D", "  and for FEED 13V8")
TW = max(tsize(s_)[0] for s_ in JTAB) + 0.6
for k, reg in enumerate(PORT):
    hgt = 2.0 * len(JTAB) + 1.0
    sp = find_spot(TW, hgt, ((reg[0] + reg[2]) / 2, 40.0), "B", step=1.0, rmax=40.0)
    if sp:
        for i, s in enumerate(JTAB):                  # mirrored text, left-justified: it runs to -x from the anchor
            text(s.format(n=k + 1), sp[0] + TW / 2 - 0.3, sp[1] - hgt / 2 + 1.5 + 2.0 * i, side="B", just="l")
    else: SILK_MISS.append(f"jumper table R{k + 1}")
LEG = ("JLC04161H-7628 1.6 mm 4 layers", "L1 signals + pour   L2 planes", "L3 signals   L4 planes",
       "planes: GND, CHASSIS, RGND R1-R3", "signals 0.254  power 0.508", "Cat6 entry 1.016")
sp = find_spot(31.0, 2.0 * len(LEG) + 1.0, (30.0, 130.0), "B", step=1.0, rmax=60.0)
if sp:
    for i, s in enumerate(LEG): text(s, sp[0], sp[1] - len(LEG) + 1.0 + 2.0 * i, side="B")
else: SILK_MISS.append("stackup legend")

# references (as gen_rfboard_pcb.py p3): first spot clear of pads (+0.25), silk and texts, the board edge and, if possible,
# of the other parts' courtyards; the labelled parts above carry their reference in the label
unplaced = []
LABELLED = TPS | {"J1", "J2", "J3", "J6", "J7", "J11", "J12", "J13", "J14", "J15", "H1"}
for ref in sorted(fps, key=lambda r: (not r.startswith("JP"), pos(r)[1], pos(r)[0])):   # jumper references first
    if ref in LABELLED: continue
    f = fps[ref]; fld = f.Reference(); ly = pcbnew.F_SilkS
    pads, silk, crt = OBS["F"]
    fld.SetTextSize(pcbnew.VECTOR2I(mm(SH), mm(SH))); fld.SetTextThickness(mm(ST)); fld.SetVisible(True)
    fld.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER); fld.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    own = next((c for g_, c in crt if g_ is f), None) or bx(f.GetBoundingBox(False))
    ocx, ocy = (own[0] + own[2]) / 2, (own[1] + own[3]) / 2
    others = [c for g_, c in crt if g_ is not f]
    best = None
    for strict in (True, False):
        for gap in (0.3, 0.8, 1.5, 2.5, 3.5):
            for slide in (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0, 3.0, -3.0):
                for rot, where in ((0, "N"), (0, "S"), (90, "W"), (90, "E"), (0, "W"), (0, "E"), (90, "N"), (90, "S")):
                    fld.SetTextAngleDegrees(rot); fld.SetPosition(P(ocx, ocy)); tb_ = bx(fld.GetBoundingBox())
                    hw, hh = (tb_[2] - tb_[0]) / 2, (tb_[3] - tb_[1]) / 2
                    x, y = {"N": (ocx + slide, own[1] - gap - hh), "S": (ocx + slide, own[3] + gap + hh),
                            "W": (own[0] - gap - hw, ocy + slide), "E": (own[2] + gap + hw, ocy + slide)}[where]
                    box = (x - hw, y - hh, x + hw, y + hh)
                    if box[0] < XL + 0.6 or box[2] > XR - 0.6 or box[1] < 0.6 or box[3] > BH - 0.6 or box_in_notch(box, 0.6): continue
                    if any(hit(box, o) for o in pads + silk + SILK[ly]): continue
                    if strict and any(hit(box, o) for o in others): continue
                    best = (rot, x, y, box); break
                if best: break
            if best: break
        if best: break
    if best is None:                                   # no room: the reference stays on the fab layer only (assembly drawing)
        unplaced.append(ref); fld.SetVisible(False); continue
    fld.SetTextAngleDegrees(best[0]); fld.SetPosition(P(best[1], best[2])); SILK[ly].append(best[3])
for f in fps.values():
    f.Value().SetVisible(False)                        # values on the fab layer only
print("SILK: references not placed", unplaced, "| labels not placed", SILK_MISS)
b.Save(BOARD)
# physical stackup JLC04161H-7628 (D-170, as the controller board D-144): written as text, the Python wrapper does not expose it
STACKUP = [("F.Cu", "copper", 0.035, None, None), ("dielectric 1", "prepreg", 0.2104, "FR4 7628", 4.4),
           ("In1.Cu", "copper", 0.0152, None, None), ("dielectric 2", "core", 1.065, "FR4", 4.6),
           ("In2.Cu", "copper", 0.0152, None, None), ("dielectric 3", "prepreg", 0.2104, "FR4 7628", 4.4),
           ("B.Cu", "copper", 0.035, None, None)]
def stackup_text():
    st = ['\t\t(stackup', '\t\t\t(layer "F.SilkS"\n\t\t\t\t(type "Top Silk Screen")\n\t\t\t)',
          '\t\t\t(layer "F.Paste"\n\t\t\t\t(type "Top Solder Paste")\n\t\t\t)',
          '\t\t\t(layer "F.Mask"\n\t\t\t\t(type "Top Solder Mask")\n\t\t\t\t(thickness 0.01)\n\t\t\t)']
    for name, typ, th, mat, er in STACKUP:
        body = [f'(type "{typ}")'] + (['(color "FR4 natural")', f'(thickness {th})', f'(material "{mat}")', f'(epsilon_r {er})',
                                       '(loss_tangent 0.02)'] if mat else [f'(thickness {th})'])
        st.append(f'\t\t\t(layer "{name}"\n' + "".join(f"\t\t\t\t{x}\n" for x in body) + '\t\t\t)')
    st += ['\t\t\t(layer "B.Mask"\n\t\t\t\t(type "Bottom Solder Mask")\n\t\t\t\t(thickness 0.01)\n\t\t\t)',
           '\t\t\t(layer "B.Paste"\n\t\t\t\t(type "Bottom Solder Paste")\n\t\t\t)',
           '\t\t\t(layer "B.SilkS"\n\t\t\t\t(type "Bottom Silk Screen")\n\t\t\t)',
           '\t\t\t(copper_finish "ENIG")', '\t\t\t(dielectric_constraints no)', '\t\t)']
    return "\n".join(st) + "\n"
txt = open(BOARD).read()
i = txt.find("\n\t(setup\n"); assert i > 0, "no setup block"
j = i + len("\n\t(setup\n")
if txt.startswith("\t\t(stackup", j):
    k = txt.index("\n\t\t)\n", j) + len("\n\t\t)\n"); txt = txt[:j] + txt[k:]
open(BOARD, "w").write(txt[:j] + stackup_text() + txt[j:])
# netclasses in the project file (as the controller board: widths 0.254 / 0.508, Cat6 entry 1.016 for the surge current, C-36)
PRO = "shack-interface.kicad_pro"
pro = json.load(open(PRO)) if os.path.exists(PRO) else {}
ns = pro.setdefault("net_settings", {})
classes = ns.setdefault("classes", [])
base_ = next((c for c in classes if c.get("name") == "Default"), None)
if base_ is None:
    base_ = {"name": "Default"}; classes.insert(0, base_)
base_.update({"track_width": 0.254, "clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3})
def cls(name, tw, cl):
    c = dict(base_); c.update({"name": name, "track_width": tw, "clearance": cl, "priority": 0}); return c
ns["classes"] = [base_, cls("Power", 0.508, 0.2), cls("Entry", 1.016, 0.5), cls("Loop", 0.508, 0.5), cls("GND", 0.254, 0.2)]
ns["netclass_patterns"] = ([{"netclass": "GND", "pattern": p_} for p_ in ("GND", "CHASSIS", "*/RGND")] +
                           [{"netclass": "Power", "pattern": p_} for p_ in ("+13V8", "+5V", "+3V3", "*/VIN_P", "Net-(D1-A)", "Net-(U?-OUT)")] +
                           [{"netclass": "Entry", "pattern": p_} for p_ in ("*/L?P", "*/L?N")] +
                           [{"netclass": "Loop", "pattern": p_} for p_ in ("Net-(C2?-Pad?)",)])
open(PRO, "w").write(json.dumps(pro, indent=2) + "\n")
print("parked (no room in the zone):", PARK)
print(REV, "footprints", len(list(b.GetFootprints())), "nets", len(nets), "placed", len(placed))
