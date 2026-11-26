# RF board layout p2, step 1: RF copper, RF transition vias, return vias, fence vias and the GND pours.
# Run by gen_rfboard_pcb.py (exec, shares its names: b, fps, P, mm, net, KEEP, OX, OY, BW, BH, ALINE).
# Sources: D-12/D-116 (W 0.975, gap 2.0 on L1/L6), D-117 (inner antipad 0.5), D-119 (return vias, pour, fence), D-156 (layers),
# D-157 (return vias as close as the 2.0 mm gap allows; clearance mechanism M-70), placement study (rows below the relay rows).
import math, fnmatch, os, json
for t in list(b.GetTracks()): b.Remove(t); REMOVED.append(t)   # made new on every run; REMOVED keeps the proxies alive
for z in list(b.Zones()): b.Remove(z); REMOVED.append(z)
W, GAPO, FEN, FPITCH = 1.95, 2.0, 3.55, 2.54           # RF width, outer gap, fence offset from the line centre, fence pitch (D-209/D-210:
                                                       # 400 W, 50 ohm to the far plane; fence: cut edge 2.975 + 0.2 + via 0.3 + 0.05)
WC, HWC = 0.975, 1.95 / 2 + 2.0                        # D-217: width in a crossing corridor (50 ohm to the near plane); half-width of the
                                                       # inner-plane cut along a line (In1 to In3 under F.Cu, In2 to In4 under B.Cu)
_CJ = json.load(open("routing/corridors.json")) if os.path.exists("routing/corridors.json") else {"corridors": []}
CORR = _CJ["corridors"]
# D-217: after routing, the unused corridors are removed (corridors.json "pruned": true). The generator then places fence and
# return vias where those corridors were, so it keeps them clear of the routed logic (routes.json, all layers: through vias)
ROUTED = []; USE_ROUTED = False
if _CJ.get("pruned") and os.path.exists(_CJ.get("routes", "routing/routes.json")):
    _rj = json.load(open(_CJ.get("routes", "routing/routes.json")))
    ROUTED = [(t["x1"], t["y1"], t["x2"], t["y2"], t["w"] / 2) for t in _rj["tracks"]] + \
             [(v["x"], v["y"], v["x"], v["y"], v["d"] / 2) for v in _rj["vias"]]
RBUCK = {}                                             # ROUTED by 5 mm cell (each item in every cell it comes within 1.5 mm of)
for it_ in ROUTED:
    for gx_ in range(int((min(it_[0], it_[2]) - 1.5) // 5), int((max(it_[0], it_[2]) + 1.5) // 5) + 1):
        for gy_ in range(int((min(it_[1], it_[3]) - 1.5) // 5), int((max(it_[1], it_[3]) + 1.5) // 5) + 1):
            RBUCK.setdefault((gx_, gy_), []).append(it_)
RFPC = []                                              # D-217: RF pieces (lay, xa, ya, xb, yb, net, in_corridor) for the plane cuts
VRF_D, VRF_DR, VG_D, VG_DR = 1.2, 0.8, 0.6, 0.3        # RF transition via, GND via
LAY = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu}
T = pcbnew.ToMM
RFSEG, RFVIA, GVIA = [], [], []
RF_PAT = ("/ANT*", "*TXBUS", "*RXBUS", "/R?_RADIO", "/R?_EXP", "/A?_ANTENNA", "*/PORT", "*/PARK")
def is_rf(netname): return any(fnmatch.fnmatchcase(netname, p) for p in RF_PAT)
def pads(ref, num):
    return sorted({(round(T(p.GetPosition().x) - OX, 3), round(T(p.GetPosition().y) - OY, 3)) for p in fps[ref].Pads()
                   if p.GetNumber() == num and p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or
                   (p.GetNumber() == num and ref[0] in "CLR")})
def strap(ref):
    p = next(p for p in fps[ref].Pads() if p.GetNumber() == "1" and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD)
    return (round(T(p.GetPosition().x) - OX, 3), round(T(p.GetPosition().y) - OY, 3))
def netof(ref, num): return next(p.GetNetname() for p in fps[ref].Pads() if p.GetNumber() == num)
CH = 2.0                                               # chamfer leg at every bend (Prins, p2b: no 90-degree bends)
def chamfer(pts):
    """Replace every 90-degree bend of a polyline by a 45-degree segment (legs CH, at most 0.45 of each adjacent segment).
    T-junctions are made by separate polylines and stay at 90 degrees."""
    q = [pts[0]]
    for i in range(1, len(pts) - 1):
        (xa, ya), (xb, yb), (xc_, yc_) = pts[i - 1], pts[i], pts[i + 1]
        l1, l2 = math.hypot(xb - xa, yb - ya), math.hypot(xc_ - xb, yc_ - yb)
        if l1 < 1e-6 or l2 < 1e-6: q.append(pts[i]); continue
        u1, u2 = ((xb - xa) / l1, (yb - ya) / l1), ((xc_ - xb) / l2, (yc_ - yb) / l2)
        if abs(u1[0] * u2[0] + u1[1] * u2[1]) > 0.01: q.append(pts[i]); continue    # straight on, or already 45 degrees
        leg = min(CH, 0.45 * l1, 0.45 * l2)
        q += [(round(xb - u1[0] * leg, 4), round(yb - u1[1] * leg, 4)), (round(xb + u2[0] * leg, 4), round(yb + u2[1] * leg, 4))]
    return q + [pts[-1]]
def corr_split(lay, xa, ya, xb, yb, netname):
    """D-217: split a straight piece at the corridors that lie on it: [(xa, ya, xb, yb, in_corridor)]."""
    L = math.hypot(xb - xa, yb - ya); ux, uy = (xb - xa) / L, (yb - ya) / L; cuts = []
    for c in CORR:
        if c["layer"] != lay or c["net"] != netname: continue
        ts = [((px - xa) * ux + (py - ya) * uy, abs((px - xa) * uy - (py - ya) * ux)) for px, py in (c["p0"], c["p1"])]
        if all(d < 0.01 and -0.01 < t < L + 0.01 for t, d in ts): cuts.append(tuple(sorted(t for t, _ in ts)))
    out, t0 = [], 0.0
    for a, b_ in sorted(cuts):
        if a > t0 + 1e-6: out.append((t0, a, False))
        out.append((a, b_, True)); t0 = b_
    if t0 < L - 1e-6: out.append((t0, L, False))
    return [(round(xa + ux * a, 4), round(ya + uy * a, 4), round(xa + ux * b_, 4), round(ya + uy * b_, 4), k) for a, b_, k in out]
def tr(lay, pts, netname, w=W):
    pts = chamfer(pts)
    for (xa0, ya0), (xb0, yb0) in zip(pts, pts[1:]):
        if abs(xa0 - xb0) < 1e-6 and abs(ya0 - yb0) < 1e-6: continue
        for xa, ya, xb, yb, inc in corr_split(lay, xa0, ya0, xb0, yb0, netname):
            wp = WC if inc else w
            t = pcbnew.PCB_TRACK(b); t.SetStart(P(xa, ya)); t.SetEnd(P(xb, yb)); t.SetWidth(mm(wp)); t.SetLayer(LAY[lay])
            t.SetNet(net(netname)); t.SetLocked(True); b.Add(t); KEEP.append(t); RFSEG.append((lay, xa, ya, xb, yb, wp, netname))
            RFPC.append((lay, xa, ya, xb, yb, netname, inc))
def rfvia(x, y, netname):
    v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(VRF_D)); v.SetDrill(mm(VRF_DR)); v.SetNet(net(netname)); v.SetLocked(True)
    b.Add(v); KEEP.append(v); RFVIA.append((x, y, VRF_D, netname))
def transition(x, y, dx, dy, netname):
    """Two RF vias in a row, at (x, y) and 1.6 mm along (dx, dy), joined on L1 and L6."""
    x2, y2 = x + 1.6 * dx, y + 1.6 * dy
    rfvia(x, y, netname); rfvia(x2, y2, netname); tr("F", [(x, y), (x2, y2)], netname); tr("B", [(x, y), (x2, y2)], netname)
    return [(x, y), (x2, y2)]
CHANGES = []                                           # (x, y) of RF layer changes: relay contact pins, RF vias, links, straps

# ---- rows (L1), K0, EXP and radio feeds per radio block ----
FEEDX = [90.0, 81.0, 72.0]       # R1 feed farthest from K0: no feed crosses another feed on L6 (study had 81, 90, 72)
for r in range(3):
    n = 100 * (r + 1); y0 = 38 + 48 * r
    ytx, yrx, yf = y0 + 18.5, y0 + 42.5, y0 + 15.5
    txb, rxb, rad = netof(f"K{n+1}", "14"), netof(f"K{n+1}", "12"), netof(f"K{n+1}", "11")
    def row(members, yr, netname, extra=()):
        """members: [((x, ya), (x, yb))] COM pin pairs; the two end members and the row form one polyline (chamfered corners),
        the others join the row as T stubs. extra: x of further T points on the row (K0 RXBUS)."""
        m = sorted(members, key=lambda q: q[0][0]); L, R = m[0], m[-1]
        mid = sorted([q[0][0] for q in m[1:-1]] + list(extra))
        tr("F", [L[0], L[1], (L[0][0], yr)] + [(x, yr) for x in mid] + [(R[0][0], yr), R[1], R[0]], netname)
        for q in m[1:-1]: tr("F", [q[0], q[1], (q[0][0], yr)], netname)
    mem = [pads(ref, num) for ref, num in [(f"K{n+6}", "11"), (f"K{n+1}", "14")] + [(f"K{n+2+k}", "11") for k in range(4)]]
    row(mem, ytx, txb); CHANGES += [q for pr in mem for q in pr]
    mem = [pads(ref, "11") for ref in [f"K{n+11}"] + [f"K{n+7+k}" for k in range(4)]]
    (xk, ya), (_, yb) = pads(f"K{n+1}", "12")
    tr("B", [(xk, ya), (xk, yb), (xk, yrx - 1.6), (xk, yrx)], rxb); CHANGES += transition(xk, yrx, 0, -1, rxb)
    row(mem, yrx, rxb, extra=(xk,)); CHANGES += [q for pr in mem for q in pr]
    # EXP: both EXP NO pins on L6, then left to the SMA strap
    exn = netof(f"K{n+6}", "14")
    (xe, ya), _ = pads(f"K{n+6}", "14"); _, (_, yb) = pads(f"K{n+11}", "14")
    sx, sy = strap(f"J{4+r}")
    pins = sorted(set(pads(f"K{n+6}", "14") + pads(f"K{n+11}", "14")), key=lambda q: q[1])
    tr("B", sorted(set([q for q in pins] + [(xe, sy)]), key=lambda q: q[1]), exn); tr("B", [(xe, sy), (sx, sy)], exn)
    CHANGES += pins + [(sx, sy)]
    # radio feed: SO-239 strap, up on L6 (R1, R2 with a jog on L1 near the bottom edge), into K0 COM from below
    (xc, ya), (_, yb) = pads(f"K{n+1}", "11"); fx = FEEDX[r]; sx, sy = strap(f"J{1+r}")
    top = [(fx, yf), (xc, yf), (xc, yb), (xc, ya)]
    if r == 0:
        tr("F", [(sx, sy), (sx, 219.5), (fx, 219.5), (fx, 217.5)], rad); CHANGES += transition(fx, 217.5, 0, -1, rad)
        tr("B", [(fx, 217.5), (fx, 215.9)] + top, rad)
    elif r == 1:
        tr("B", [(sx, sy), (sx, 217.6), (sx, 216.0)], rad); CHANGES += transition(sx, 216.0, 0, -1, rad)
        tr("F", [(sx, 216.0), (sx, 214.4), (sx, 212.5), (fx, 212.5), (fx, 210.5)], rad); CHANGES += transition(fx, 210.5, 0, -1, rad)
        tr("B", [(fx, 210.5), (fx, 208.9)] + top, rad)
    else:
        tr("B", [(sx, sy)] + top, rad)
    CHANGES += [(sx, sy), (xc, ya), (xc, yb)]

# ---- columns (L6) and antenna ports ----
for k in range(4):
    c, a = ALINE[k], 4 + k
    col = netof(f"K{102+k}", "14")
    stubs = []
    for r in range(3):
        n = 100 * (r + 1)
        for ref in (f"K{n+2+k}", f"K{n+7+k}"):
            (xn, ya), (_, yb) = pads(ref, "14"); ym = round((ya + yb) / 2, 3)
            tr("B", [(xn, ya), (xn, ym), (xn, yb)], col); stubs.append((ym, xn))
            CHANGES += [(xn, ya), (xn, yb)]
    stubs.sort()
    (lx, l1y), = pads(f"R{a}02", "1"); (_, l2y), = pads(f"R{a}02", "2")
    assert abs(lx - c) < 0.01
    tr("B", [(stubs[0][1], stubs[0][0]), (c, stubs[0][0])] + [(c, ym) for ym, _ in stubs[1:]] + [(lx, l1y)], col)
    for ym, xn in stubs[1:]: tr("B", [(xn, ym), (c, ym)], col)
    ct, cd = pads(f"C{a}04", "1")[0], pads(f"C{a}01", "1")[0]
    assert abs(ct[1] - l1y) < 0.01 and abs(cd[1] - l1y) < 0.01, (ct, cd, l1y)
    tr("F", [ct, (lx, l1y), cd], col)                                        # detector tap, link pad 1, DC block: one line
    port = netof(f"K{a}01", "14")
    no = pads(f"K{a}01", "14")
    assert abs(no[1][1] - l2y) < 0.01, (no, l2y)
    tr("B", [no[0], no[1], (lx, l2y)], port)                                 # K1 NO to link pad 2: straight
    c2, lp = pads(f"C{a}01", "2")[0], pads(f"L{a}02", "2")[0]
    assert abs(c2[0] - lp[0]) < 0.01 and c2[1] < l2y < lp[1], (c2, lp, l2y)
    tr("F", [c2, (c2[0], l2y), lp], port); tr("F", [(c2[0], l2y), (lx, l2y)], port)   # DC block to choke vertical, T to the link
    ant = netof(f"K{a}01", "11"); com = pads(f"K{a}01", "11"); sx, sy = strap(f"J{7+k}")
    tr("F", [com[0], com[1], (sx, com[1][1]), (sx, sy)], ant)
    park = netof(f"K{a}01", "12"); nc = pads(f"K{a}01", "12"); bl = pads(f"R{a}01", "1")[0]
    assert abs(bl[1] - nc[1][1]) < 0.001, (bl, nc)
    tr("B", [nc[0], nc[1], bl], park)                                       # ends at the bleed pad centre
    CHANGES += no + com + [(lx, l1y), (lx, l2y), (sx, sy)]

# ---- D-217 inner-plane cuts: rule areas (name RF_CUT, no zone fill) HWC each side of every RF piece outside the corridors.
# F.Cu rows: In1 to In3 cut (reference In4); B.Cu columns: In2 to In4 cut (reference In1). Where a row and a column cross, only
# the near plane of each is cut, so In2 and In3 stay as a shield between them. Inside a corridor no plane is cut (reference
# In1 or In4 at 0.512 mm, line WC). A piece end that joins a non-collinear RF piece gets HWC more length (corners, T points).
# routing/export_geom.py turns these areas into one router keep-out for In2 and In3.
CUT_L = {"F": [pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu], "B": [pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu]}
NEAR_L = {"F": [pcbnew.In1_Cu], "B": [pcbnew.In4_Cu]}
def _pd(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1; l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - x1 - t * dx, py - y1 - t * dy)
def _colin(a, c):
    return abs((a[3] - a[1]) * (c[4] - c[2]) - (a[4] - a[2]) * (c[3] - c[1])) < 1e-6 * max(1.0, math.hypot(a[3] - a[1], a[4] - a[2]) * math.hypot(c[3] - c[1], c[4] - c[2]))
RFCUT = []                                             # (layer names, polygon) for the report and the router keep-out
RFCUT_L = []                                           # layer ids of each cut (plane_cut_all)
def cut_area(lids, poly):
    ka = pcbnew.ZONE(b); ka.SetIsRuleArea(True); ls_ = pcbnew.LSET()
    for lid in lids: ls_.AddLayer(lid)
    ka.SetLayerSet(ls_); ka.SetZoneName("RF_CUT"); ka.SetDoNotAllowZoneFills(True); ka.SetDoNotAllowTracks(False)
    ka.SetDoNotAllowVias(False); ka.SetDoNotAllowPads(False); ka.SetDoNotAllowFootprints(False)
    o = ka.Outline(); o.NewOutline()
    for x, y in poly: o.Append(mm(OX + x), mm(OY + y))
    b.Add(ka); KEEP.append(ka); RFCUT.append(([pcbnew.LayerName(l) for l in lids], poly)); RFCUT_L.append(set(lids))
for pc in RFPC:
    lay, xa, ya, xb, yb, nn, inc = pc
    L = math.hypot(xb - xa, yb - ya)
    if inc or L < 1e-6: continue
    ux, uy = (xb - xa) / L, (yb - ya) / L
    def joined(px, py): return any(q is not pc and not _colin(pc, q) and _pd(px, py, *q[1:5]) < 0.01 for q in RFPC)
    a0 = -HWC if joined(xa, ya) else 0.0; b0 = L + (HWC if joined(xb, yb) else 0.0)
    xs_ = []
    for q in RFPC:                                     # crossings with a piece of another net on the other outer layer
        if q[0] == lay or q[5] == nn: continue
        x3, y3, x4, y4 = q[1:5]; den = (xb - xa) * (y4 - y3) - (yb - ya) * (x4 - x3)
        if abs(den) < 1e-9: continue
        t = ((x3 - xa) * (y4 - y3) - (y3 - ya) * (x4 - x3)) / den; u = ((x3 - xa) * (yb - ya) - (y3 - ya) * (xb - xa)) / den
        if -0.01 <= u <= 1.01 and -HWC <= t * L <= L + HWC: xs_.append((t * L - HWC, t * L + HWC))
    parts, t0 = [], a0
    for c0, c1 in sorted(xs_):
        c0, c1 = max(c0, a0), min(c1, b0)
        if c1 <= t0: continue
        if c0 > t0: parts.append((t0, c0, CUT_L[lay]))
        parts.append((max(c0, t0), c1, NEAR_L[lay])); t0 = c1
    if t0 < b0: parts.append((t0, b0, CUT_L[lay]))
    for a, c, lids in parts:
        if c - a < 1e-3: continue
        cut_area(lids, [(round(xa + ux * a - uy * HWC * sd, 4), round(ya + uy * a + ux * HWC * sd, 4)) for sd in (1, -1)] +
                       [(round(xa + ux * c - uy * HWC * sd, 4), round(ya + uy * c + ux * HWC * sd, 4)) for sd in (-1, 1)])
print("RF plane cuts", len(RFCUT), "| corridors", len(CORR), "| RF pieces in corridors", sum(1 for q in RFPC if q[6]))
CBOX = []                                              # D-217: no via in a corridor and its approach (fence row and 1 mm beyond)
for c in CORR:
    (x0_, y0_), (x1_, y1_) = c["p0"], c["p1"]; L = math.hypot(x1_ - x0_, y1_ - y0_); ux, uy = (x1_ - x0_) / L, (y1_ - y0_) / L
    CBOX.append((x0_ - ux * 0.3, y0_ - uy * 0.3, x1_ + ux * 0.3, y1_ + uy * 0.3, FEN + 1.0))
def in_cbox(x, y, r):
    return any(_pd(x, y, xa, ya, xb, yb) < hw + r and -r - 1e-6 <= ((x - xa) * (xb - xa) + (y - ya) * (yb - ya)) / math.hypot(xb - xa, yb - ya)
               <= math.hypot(xb - xa, yb - ya) + r for xa, ya, xb, yb, hw in CBOX)

# ---- geometry for the checks: exact pad copper per outer layer, bucketed on a 5 mm grid ----
def seg_pt(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1; L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - x1 - t * dx, py - y1 - t * dy)
def seg_seg(a, b_):
    (x1, y1, x2, y2), (x3, y3, x4, y4) = a, b_
    def ccw(ax, ay, bx, by, cx, cy): return (cy - ay) * (bx - ax) - (by - ay) * (cx - ax)
    d1, d2 = ccw(x3, y3, x4, y4, x1, y1), ccw(x3, y3, x4, y4, x2, y2)
    d3, d4 = ccw(x1, y1, x2, y2, x3, y3), ccw(x1, y1, x2, y2, x4, y4)
    if d1 * d2 < 0 and d3 * d4 < 0: return 0.0
    return min(seg_pt(x1, y1, x3, y3, x4, y4), seg_pt(x2, y2, x3, y3, x4, y4), seg_pt(x3, y3, x1, y1, x2, y2), seg_pt(x4, y4, x1, y1, x2, y2))
def inside(px, py, pts):
    c = False
    for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
        if (ya > py) != (yb > py) and px < xa + (py - ya) * (xb - xa) / (yb - ya): c = not c
    return c
POLY, BUCK = [], {}
for ref, f in fps.items():
    for p in f.Pads():
        rfpad = is_rf(p.GetNetname()) or (ref.startswith("K") and p.GetNumber() in ("11", "12", "14"))
        for ln, lid in LAY.items():
            if not p.IsOnLayer(lid): continue
            o = p.GetEffectivePolygon(lid, pcbnew.ERROR_OUTSIDE).Outline(0)
            pts = [(T(o.CPoint(i).x) - OX, T(o.CPoint(i).y) - OY) for i in range(o.PointCount())]
            xs_, ys_ = [q[0] for q in pts], [q[1] for q in pts]
            k = len(POLY); POLY.append((p.GetNetname(), ln, (min(xs_), min(ys_), max(xs_), max(ys_)), pts, rfpad, f"{ref}.{p.GetNumber()}"))
            for gx in range(int(min(xs_) // 5), int(max(xs_) // 5) + 1):
                for gy in range(int(min(ys_) // 5), int(max(ys_) // 5) + 1):
                    BUCK.setdefault((gx, gy), []).append(k)
def near(x0, y0, x1, y1, m):
    s = set()
    for gx in range(int((min(x0, x1) - m) // 5), int((max(x0, x1) + m) // 5) + 1):
        for gy in range(int((min(y0, y1) - m) // 5), int((max(y0, y1) + m) // 5) + 1):
            s.update(BUCK.get((gx, gy), ()))
    return s
def d_seg_poly(sg, pts):
    if inside(sg[0], sg[1], pts) or inside(sg[2], sg[3], pts): return 0.0
    return min(seg_seg(sg, (xa, ya, xb, yb)) for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]))

# ---- RF spacing check on L1 / L6 (DRC checks only the 0.5 mm netclass value, M-70) ----
VIOL = []
for i, (ln, xa, ya, xb, yb, w, nn) in enumerate(RFSEG):
    sg = (xa, ya, xb, yb)
    for k in near(xa, ya, xb, yb, 3.5):
        pn, pl, bb, pts, rfpad, tag = POLY[k]
        if pl != ln or pn == nn: continue
        g = d_seg_poly(sg, pts) - w / 2
        if g < GAPO - 0.01: VIOL.append((round(g, 2), ln, nn.split("/")[-1], tag, (xa, ya, xb, yb)))
    for j, (l2, x3, y3, x4, y4, w2, n2) in enumerate(RFSEG):
        if j <= i or l2 != ln or n2 == nn: continue
        if max(xa, xb) + 4 < min(x3, x4) or max(x3, x4) + 4 < min(xa, xb) or max(ya, yb) + 4 < min(y3, y4) or max(y3, y4) + 4 < min(ya, yb): continue
        g = seg_seg(sg, (x3, y3, x4, y4)) - w / 2 - w2 / 2
        if g < GAPO - 0.01: VIOL.append((round(g, 2), ln, nn.split("/")[-1], n2.split("/")[-1], (xa, ya, xb, yb)))
    for (vx, vy, vd, vn) in RFVIA:
        if vn != nn and seg_pt(vx, vy, *sg) - w / 2 - vd / 2 < GAPO - 0.01:
            VIOL.append((round(seg_pt(vx, vy, *sg) - w / 2 - vd / 2, 2), ln, nn.split("/")[-1], "via " + vn.split("/")[-1], (vx, vy)))
def d_poly_poly(p1, p2):
    if inside(p1[0][0], p1[0][1], p2) or inside(p2[0][0], p2[0][1], p1): return 0.0
    e1, e2 = list(zip(p1, p1[1:] + p1[:1])), list(zip(p2, p2[1:] + p2[:1]))
    return min(seg_seg((a[0], a[1], b_[0], b_[1]), (c_[0], c_[1], d_[0], d_[1])) for a, b_ in e1 for c_, d_ in e2)
for i, (pn, pl, bb, pts, rfpad, tag) in enumerate(POLY):         # RF pad to a pad of another part and net on L1/L6: 2.0 mm
    if not rfpad: continue
    for j in near(bb[0], bb[1], bb[2], bb[3], 2.5):
        qn, ql, qb, qpts, qrf, qtag = POLY[j]
        if j == i or ql != pl or qn == pn or qtag.split(".")[0] == tag.split(".")[0] or (qrf and j < i): continue
        if qb[0] > bb[2] + 2.0 or bb[0] > qb[2] + 2.0 or qb[1] > bb[3] + 2.0 or bb[1] > qb[3] + 2.0: continue
        g = d_poly_poly(pts, qpts)
        if g < GAPO - 0.01: VIOL.append((round(g, 2), pl, "pad " + tag, "pad " + qtag))
print("RF segments", len(RFSEG), "RF vias", len(RFVIA), "RF spacing violations", len(VIOL))
for v in sorted(VIOL)[:25]: print("  ", v)

# ---- GND vias: return vias at every RF layer change (D-157), then the fence along every RF line (D-119) ----
FSTUB = []                                                # fixed signal stubs (fan-out, p2c): vias keep clear of them
# ---- keep-outs at the supports S1 to S6 (D-189): the case seat face C1 to C6 (diameter 8, RF-CASE-01 rev B) presses on B.Cu, the
# standoff and washer (7 mm) on F.Cu. No via or pour of any net within R_SUP of the hole centre (rule area on F.Cu and B.Cu; a
# through via touches both). Tracks: routing/export_geom.py turns these areas (name SUP_KO) into router keep-outs that only the
# support's own net CHASSIS_Sn may cross (its track to the bond option Cn); the logic routes never come in.
R_SUP = 4.5
SUP = [(round(T(fps[f"S{i}"].GetPosition().x) - OX, 3), round(T(fps[f"S{i}"].GetPosition().y) - OY, 3)) for i in range(1, 7)]
for sx, sy in SUP:
    ka = pcbnew.ZONE(b); ka.SetIsRuleArea(True)
    ls_ = pcbnew.LSET(); ls_.AddLayer(pcbnew.F_Cu); ls_.AddLayer(pcbnew.B_Cu); ka.SetLayerSet(ls_)
    ka.SetZoneName("SUP_KO"); ka.SetDoNotAllowTracks(False); ka.SetDoNotAllowVias(True); ka.SetDoNotAllowZoneFills(True)
    ka.SetDoNotAllowPads(False); ka.SetDoNotAllowFootprints(False)
    o = ka.Outline(); o.NewOutline()
    for k_ in range(48):
        o.Append(mm(OX + sx + R_SUP * math.cos(2 * math.pi * k_ / 48)), mm(OY + sy + R_SUP * math.sin(2 * math.pi * k_ / 48)))
    b.Add(ka); KEEP.append(ka)
# ---- case fill keep-outs CASE_KO (D-204): where the milled fill of the tray touches the board underside: no via, no pour.
# Polygons in case_ko.json (board frame, mm), taken 2026-11-20 from the p3-case board (they were added there by a patch, M-125
# and D-204, and were not in this generator). D-218: logic copper on B.Cu keeps 0.5 mm from them (routing/export_geom.py).
CASE_KO = json.load(open("case_ko.json")) if os.path.exists("case_ko.json") else []
for pts_ in CASE_KO:
    ka = pcbnew.ZONE(b); ka.SetIsRuleArea(True)
    ls_ = pcbnew.LSET(); ls_.AddLayer(pcbnew.F_Cu); ls_.AddLayer(pcbnew.B_Cu); ka.SetLayerSet(ls_)
    ka.SetZoneName("CASE_KO"); ka.SetDoNotAllowTracks(False); ka.SetDoNotAllowVias(True); ka.SetDoNotAllowZoneFills(True)
    ka.SetDoNotAllowPads(False); ka.SetDoNotAllowFootprints(False)
    o = ka.Outline(); o.NewOutline()
    for x_, y_ in pts_: o.Append(mm(OX + x_), mm(OY + y_))
    b.Add(ka); KEEP.append(ka)
_CUTB = [(RFCUT_L[i], poly, min(q[0] for q in poly), min(q[1] for q in poly), max(q[0] for q in poly), max(q[1] for q in poly))
         for i, (lids, poly) in enumerate(RFCUT)]
# places where KiCad reported a dangling GND via (no fill on two layers after the refill), board frame: routing/no_via.json
NO_VIA = json.load(open("routing/no_via.json"))["vias"] if os.path.exists("routing/no_via.json") else []
def plane_cut_all(x, y):
    cut = set()
    for lids, poly, x0_, y0_, x1_, y1_ in _CUTB:
        if x0_ - 0.5 <= x <= x1_ + 0.5 and y0_ - 0.5 <= y <= y1_ + 0.5 and (inside(x, y, poly) or
                min(_pd(x, y, xa, ya, xb, yb) for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1])) < VG_D / 2 + 0.2):
            cut.update(lids)
    n = len({pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu} - cut)
    if n >= 2: return False
    for ln in ("F", "B"):                                  # the outer GND pour counts where it keeps its 2.0 mm gap to RF copper
        if all(_pd(x, y, xa, ya, xb, yb) >= w_ / 2 + GAPO + VG_D / 2 + 0.25 for (l_, xa, ya, xb, yb, w_, nn_) in RFSEG if l_ == ln): n += 1
    return n < 2                                           # a GND via must join two copper layers at least (DRC via_dangling)
def in_case_ko(x, y, r):
    for pts_ in CASE_KO:
        if inside(x, y, [tuple(q) for q in pts_]): return True
        if min(_pd(x, y, xa, ya, xb, yb) for (xa, ya), (xb, yb) in zip(pts_, pts_[1:] + pts_[:1])) < r + 0.5: return True
    return False
def via_ok(x, y):
    if not (1.0 <= x <= BW - 1.0 and 1.0 <= y <= BH - 1.0): return False
    if any(math.hypot(x - sx, y - sy) < R_SUP + VG_D / 2 for sx, sy in SUP): return False
    if in_cbox(x, y, VG_D / 2): return False                                    # D-217 corridors
    if in_case_ko(x, y, VG_D / 2): return False                                 # D-204 case fill
    if any(math.hypot(x - q[0], y - q[1]) < (q[2] if len(q) > 2 else 0.3) for q in NO_VIA): return False   # DRC via_dangling list
    if plane_cut_all(x, y): return False                                        # D-217: fewer than two inner planes left (via dangling)
    if USE_ROUTED and any(_pd(x, y, xa, ya, xb, yb) < hw + 0.2 + 0.05 + VG_D / 2 for xa, ya, xb, yb, hw in RBUCK.get((int(x // 5), int(y // 5)), ())): return False   # routed logic
    for cx_, cy_ in ((5, 5), (BW - 5, 5), (5, BH - 5), (BW - 5, BH - 5)):          # corner radius 5 mm (D-113)
        if (x < 5 or x > BW - 5) and (y < 5 or y > BH - 5) and math.hypot(x - cx_, y - cy_) > 4.0: return False
    r = VG_D / 2
    for (xa, ya, xb, yb, w_) in FSTUB:
        if seg_pt(x, y, xa, ya, xb, yb) < w_ / 2 + 0.2 + r: return False
    for (ln, xa, ya, xb, yb, w, nn) in RFSEG:
        if seg_pt(x, y, xa, ya, xb, yb) < w / 2 + GAPO + r: return False
    for (vx, vy, vd, vn) in RFVIA:
        if math.hypot(x - vx, y - vy) < vd / 2 + GAPO + r: return False
    for k in near(x, y, x, y, 3.0):
        pn, pl, bb, pts, rfpad, tag = POLY[k]
        need = GAPO + r if rfpad else 0.25 + r
        if bb[0] - need > x or x > bb[2] + need or bb[1] - need > y or y > bb[3] + need: continue
        if inside(x, y, pts) or min(seg_pt(x, y, xa, ya, xb, yb) for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1])) < need: return False
    return all(math.hypot(x - gx, y - gy) >= 1.0 for gx, gy in GVIA)
def gvia(x, y):
    v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(VG_D)); v.SetDrill(mm(VG_DR)); v.SetNet(net("GND")); v.SetLocked(True)
    b.Add(v); KEEP.append(v); GVIA.append((x, y))
USE_ROUTED = True                                     # D-217 pruned: return and fence vias keep off the routed logic
n_ret = 0
for (cx_, cy_) in sorted(set((round(x, 3), round(y, 3)) for x, y in CHANGES)):
    got = 0
    for rr in (3.4, 3.8, 4.3):
        for ang in range(0, 360, 15):
            if got >= 2: break
            x, y = round(cx_ + rr * math.cos(math.radians(ang)), 3), round(cy_ + rr * math.sin(math.radians(ang)), 3)
            if any(math.hypot(x - gx, y - gy) < 2.0 for gx, gy in GVIA): continue      # spread them around the pin
            if via_ok(x, y): gvia(x, y); got += 1; n_ret += 1
USE_ROUTED = False                                    # own-net vias (decoupling, terminals, fan-out, plane vias) keep their places
# bottom-side decoupling C101, C201, C301 (D-127): the 2.0 mm pour cannot reach their GND pad between the coil pins
# (starved thermal); each GND pad gets its own via to the planes with a short B.Cu track
for r in range(3):
    ref = f"C{100 * (r + 1) + 1}"
    p2 = next(p for p in fps[ref].Pads() if p.GetNetname() == "GND"); px, py = T(p2.GetPosition().x) - OX, T(p2.GetPosition().y) - OY
    spot = next(((round(px + d * ux, 3), round(py + d * uy, 3)) for d in (1.3, 1.6, 2.0) for ux, uy in ((1, 0), (0, 1), (0, -1), (-1, 0))
                 if via_ok(round(px + d * ux, 3), round(py + d * uy, 3))), None)
    assert spot, ref
    gvia(*spot)
    t = pcbnew.PCB_TRACK(b); t.SetStart(P(px, py)); t.SetEnd(P(*spot)); t.SetWidth(mm(0.4)); t.SetLayer(pcbnew.B_Cu)
    t.SetNet(net("GND")); t.SetLocked(True); b.Add(t); KEEP.append(t)
    p2.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_NONE)    # joined by the via track, not by spokes
# bottom-side +12V_SW pad of C101, C201, C301: own via (net +12V_SW) with a short B.Cu track; the router ends on the via
# (routing/terminals.json, layers F and B = all layers)
TERM = {}
for r in range(3):
    ref = f"C{100 * (r + 1) + 1}"
    p1 = next(p for p in fps[ref].Pads() if p.GetNetname() != "GND"); px, py = T(p1.GetPosition().x) - OX, T(p1.GetPosition().y) - OY
    spot = next(((round(px + d * ux, 3), round(py + d * uy, 3)) for d in (1.3, 1.6, 2.0) for ux, uy in ((-1, 0), (0, 1), (0, -1), (1, 0))
                 if via_ok(round(px + d * ux, 3), round(py + d * uy, 3))), None)
    assert spot, ref
    v = pcbnew.PCB_VIA(b); v.SetPosition(P(*spot)); v.SetWidth(mm(VG_D)); v.SetDrill(mm(VG_DR)); v.SetNet(net(p1.GetNetname())); v.SetLocked(True)
    b.Add(v); KEEP.append(v); GVIA.append(spot)
    t = pcbnew.PCB_TRACK(b); t.SetStart(P(px, py)); t.SetEnd(P(*spot)); t.SetWidth(mm(0.4)); t.SetLayer(pcbnew.B_Cu)
    t.SetNet(net(p1.GetNetname())); t.SetLocked(True); b.Add(t); KEEP.append(t)
    TERM.setdefault(ref, {})[p1.GetNumber()] = [spot[0], spot[1], ["F", "B"]]
# fan-out of the TSSOP-24 expanders (p2c, D-161, as D-154 on the controller board): every signal pin gets a straight F.Cu stub
# outward to its own via, in two staggered columns 0.6 and 1.6 mm beyond the pad end (pin index mod 2; 1.3 mm via pitch in a column), so that each
# pin has a way to the inner routing layers. The router ends on the via (routing/terminals.json).
FW, FCL = 0.254, 0.2
n_fo = 0; NOFO = []; FOVIA = {}
for ref in ("U901", "U902", "U903", "U1001"):
    f = fps[ref]; fx, fy = T(f.GetPosition().x) - OX, T(f.GetPosition().y) - OY
    rows = {}
    for pd in f.Pads():
        q = pd.GetPosition(); px, py = T(q.x) - OX, T(q.y) - OY
        pb_ = pd.GetBoundingBox(); horiz = pb_.GetWidth() > pb_.GetHeight()   # long pad axis = stub direction
        key = (horiz, 1 if (px - fx if horiz else py - fy) > 0 else -1)
        rows.setdefault(key, []).append((py if horiz else px, pd, px, py))
    for (horiz, sg), pins in rows.items():
        pins.sort(key=lambda t_: t_[0])
        for idx, (_, pd, px, py) in enumerate(pins):
            nn = pd.GetNetname()
            if not nn or nn == "GND": continue
            bb = pd.GetBoundingBox()
            end = (T(bb.GetRight()) - OX if sg > 0 else T(bb.GetX()) - OX) if horiz else (T(bb.GetBottom()) - OY if sg > 0 else T(bb.GetY()) - OY)
            spot = None
            for off in [0.6 + (idx % 2) * 1.0] + [2.6, 3.6, 4.6]:
                vx, vy = (round(end + sg * off, 3), round(py, 3)) if horiz else (round(px, 3), round(end + sg * off, 3))
                sgm = (px, py, vx, vy)
                if not via_ok(vx, vy): continue
                if any(seg_pt(gx, gy, *sgm) < FW / 2 + FCL + VG_D / 2 for gx, gy in GVIA): continue
                if any(POLY[k][0] != nn and POLY[k][1] == "F" and d_seg_poly(sgm, POLY[k][3]) < FW / 2 + FCL for k in near(px, py, vx, vy, 1.0)): continue
                spot = (vx, vy); break
            if spot is None: NOFO.append(f"{ref}.{pd.GetNumber()}"); continue
            v = pcbnew.PCB_VIA(b); v.SetPosition(P(*spot)); v.SetWidth(mm(VG_D)); v.SetDrill(mm(VG_DR)); v.SetNet(net(nn)); v.SetLocked(True)
            b.Add(v); KEEP.append(v); GVIA.append(spot); FOVIA[spot] = v
            t = pcbnew.PCB_TRACK(b); t.SetStart(P(px, py)); t.SetEnd(P(*spot)); t.SetWidth(mm(FW)); t.SetLayer(pcbnew.F_Cu)
            t.SetNet(net(nn)); t.SetLocked(True); b.Add(t); KEEP.append(t); FSTUB.append((px, py, spot[0], spot[1], FW))
            TERM.setdefault(ref, {})[pd.GetNumber()] = [spot[0], spot[1], ["F", "B"]]; n_fo += 1
print("fan-out vias", n_fo, "no place:", NOFO)
os.makedirs("routing", exist_ok=True)
json.dump(TERM, open("routing/terminals.json", "w"), indent=1)
# plane vias (skill: own via per SMD plane pad): every SMD GND pad on F.Cu gets its own via next to the pad, outward from the
# part centre first, with a short F.Cu track. Placed before the fence, so that the fence fills in around them.
USE_ROUTED = True                                     # plane vias keep off the routed logic too (D-217 pruned)
n_pv = 0; NOPV = []
for ref, f in fps.items():
    fx, fy = T(f.GetPosition().x) - OX, T(f.GetPosition().y) - OY
    for pd in f.Pads():
        if pd.GetNetname() != "GND" or pd.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not pd.IsOnLayer(pcbnew.F_Cu): continue
        bb = pd.GetBoundingBox(); a_, b2, c_, d_ = (T(bb.GetX()) - OX, T(bb.GetY()) - OY, T(bb.GetRight()) - OX, T(bb.GetBottom()) - OY)
        px, py = (a_ + c_) / 2, (b2 + d_) / 2; hx, hy = (c_ - a_) / 2, (d_ - b2) / 2
        ox_, oy_ = px - fx, py - fy
        dirs = sorted(((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)),
                      key=lambda u: -(u[0] * ox_ + u[1] * oy_) / (abs(u[0]) + abs(u[1])) ** 0.5)
        def stub_ok(vx, vy, w_=0.3):             # the stub keeps 0.2 mm from other-net pads and from the fan-out stubs (p2c)
            sg_ = (px, py, vx, vy)
            if any(POLY[k][0] != "GND" and POLY[k][1] == "F" and d_seg_poly(sg_, POLY[k][3]) < w_ / 2 + 0.2 for k in near(px, py, vx, vy, 1.0)): return False
            return all(seg_seg(sg_, fs[:4]) >= w_ / 2 + fs[4] / 2 + 0.2 for fs in FSTUB)
        spot = next(((round(px + ux * (hx + VG_D / 2 + g), 3), round(py + uy * (hy + VG_D / 2 + g), 3)) for g in (0.2, 0.4, 0.7, 1.0, 1.5, 2.0, 2.5)
                     for ux, uy in dirs if via_ok(round(px + ux * (hx + VG_D / 2 + g), 3), round(py + uy * (hy + VG_D / 2 + g), 3))
                     and stub_ok(round(px + ux * (hx + VG_D / 2 + g), 3), round(py + uy * (hy + VG_D / 2 + g), 3))), None)
        if spot is None: NOPV.append(f"{ref}.{pd.GetNumber()}"); continue
        gvia(*spot); n_pv += 1
        t = pcbnew.PCB_TRACK(b); t.SetStart(P(px, py)); t.SetEnd(P(*spot)); t.SetWidth(mm(0.3)); t.SetLayer(pcbnew.F_Cu)
        t.SetNet(net("GND")); t.SetLocked(True); b.Add(t); KEEP.append(t)
        if fnmatch.fnmatch(ref, "C[4-7]02") or ref == "C12":   # C12: next to the R2 TXBUS narrow piece (D-217), one spoke only          # bias decoupling in the RF area: the 2.0 mm pour gap leaves one spoke;
            pd.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_NONE)     # the own via joins the pad (as C101, M-77)
print("GND pad vias", n_pv, "no place:", NOPV)
USE_ROUTED = False
USE_ROUTED = True
n_fen = 0
for (ln, xa, ya, xb, yb, w, nn) in RFSEG:
    L = math.hypot(xb - xa, yb - ya)
    if L < 1.0: continue
    ux, uy = (xb - xa) / L, (yb - ya) / L
    s = FPITCH / 2
    while s < L:
        for sd in (1, -1):
            x, y = round(xa + ux * s - uy * FEN * sd, 3), round(ya + uy * s + ux * FEN * sd, 3)
            if via_ok(x, y): gvia(x, y); n_fen += 1
        s += FPITCH
print("return vias", n_ret, "fence vias", n_fen)
# ---- bias-T drain copper (S-3, C-17, D-54): per feed FET a drain pour on F.Cu around the tab (top part of the cell, above the
# gate drive) and on B.Cu over the whole cell, joined by thermal vias next to the tab. B.Cu carries no routes (router_cfg), so
# the B.Cu pour is cut only by vias; stitch.py puts no grid vias in these cells (stitch_no_grid). Area target: C-17.
BY0, BY1, BYF, BIN = 181.0, 209.0, 190.8, 0.3            # cell band, lower end of the F.Cu part (Q?3 starts at 191.5), inset
TV_MAX = 9
DRAIN = []
for q, dn, x1, x2 in BIAS_CELLS:
    tab = max((p_ for p_ in fps[q].Pads() if p_.GetNumber() == "2"), key=lambda p_: p_.GetSize(pcbnew.F_Cu).x * p_.GetSize(pcbnew.F_Cu).y)
    bb = tab.GetBoundingBox(); ta, tb, tc, td = T(bb.GetX()) - OX, T(bb.GetY()) - OY, T(bb.GetRight()) - OX, T(bb.GetBottom()) - OY
    def d_tab(x, y): return math.hypot(max(ta - x, 0, x - tc), max(tb - y, 0, y - td))
    cand = sorted(((round(x1 + BIN + 0.6 + 0.5 * i, 2), round(BY0 + BIN + 0.6 + 0.5 * j, 2)) for i in range(40) for j in range(40)
                   if x1 + BIN + 0.6 + 0.5 * i <= x2 - BIN - 0.6 and BY0 + BIN + 0.6 + 0.5 * j <= BYF - 0.6),
                  key=lambda c: d_tab(*c))
    n_tv = 0
    for x, y in cand:
        if n_tv >= TV_MAX or d_tab(x, y) > 3.5: break
        if not via_ok(x, y): continue
        v = pcbnew.PCB_VIA(b); v.SetPosition(P(x, y)); v.SetWidth(mm(VG_D)); v.SetDrill(mm(VG_DR)); v.SetNet(net(dn)); v.SetLocked(True)
        b.Add(v); KEEP.append(v); GVIA.append((x, y)); n_tv += 1
    DRAIN.append((dn, x1, x2, n_tv))
print("drain thermal vias", [(d[0], d[3]) for d in DRAIN])

# ---- GND pours (D-119, D-156, M-70): outer layers 2.0 mm in the RF area, 0.25 mm in the logic regions; inner layers 0.2 mm ----
def zone(lid, cl, pts, prio):
    z = pcbnew.ZONE(b); z.SetLayer(lid); z.SetNet(net("GND")); z.SetLocalClearance(mm(cl)); z.SetMinThickness(mm(0.25))
    z.SetAssignedPriority(prio); z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.5)); z.SetThermalReliefSpokeWidth(mm(0.5))
    o = z.Outline(); o.NewOutline()
    for x, y in pts: o.Append(mm(OX + x), mm(OY + y))
    b.Add(z); KEEP.append(z)
ALL = [(0, 0), (BW, 0), (BW, BH), (0, BH)]
LOGIC = [(0, 0, BW, 36.0), (0, 181.0, 68.0, 209.0), (95.0, 181.0, 119.3, 221.0)]   # 2.0 mm or more from every RF copper
for lid in (pcbnew.F_Cu, pcbnew.B_Cu):
    zone(lid, GAPO, ALL, 0)
    for x0_, y0_, x1_, y1_ in LOGIC: zone(lid, 0.25, [(x0_, y0_), (x1_, y0_), (x1_, y1_), (x0_, y1_)], 1)
for lid in (pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu):
    zone(lid, 0.2, ALL, 0)
def dzone(lid, dn, pts):                                  # drain pour: solid pad connection (heat path), above the GND pour
    z = pcbnew.ZONE(b); z.SetLayer(lid); z.SetNet(net(dn)); z.SetLocalClearance(mm(0.25)); z.SetMinThickness(mm(0.25))
    z.SetAssignedPriority(2); z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    o = z.Outline(); o.NewOutline()
    for x, y in pts: o.Append(mm(OX + x), mm(OY + y))
    b.Add(z); KEEP.append(z)
for dn, x1, x2, _ in DRAIN:
    dzone(pcbnew.F_Cu, dn, [(x1 + BIN, BY0 + BIN), (x2 - BIN, BY0 + BIN), (x2 - BIN, BYF), (x1 + BIN, BYF)])
    dzone(pcbnew.B_Cu, dn, [(x1 + BIN, BY0 + BIN), (x2 - BIN, BY0 + BIN), (x2 - BIN, BY1 - BIN), (x1 + BIN, BY1 - BIN)])
