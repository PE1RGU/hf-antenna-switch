#!/usr/bin/env python3
"""Grid router for the controller board (routing r3 and r4, D-143, D-144, D-145). Plain Python 3 with numpy, scipy, matplotlib and
numba; it does not need KiCad. Input geom.json (export_geom.py), output routes.json, applied by gen_controller_pcb.py.

Board: 4 layers. Signals on L1 (F.Cu, vertical) and L3 (In2.Cu, horizontal); L2 and L4 are GND planes and are not routed.
Routing style (Prins, 2026-10-21):
- Each layer has a main direction. A track against it costs ORTH per step, a 45-degree track DIAG per step.
- Every bend costs (BEND45, BEND90); turns of 135 degrees or more are not allowed. So paths are straight, with few bends.
- A track leaves and enters a pad at its centre (horizontal, vertical or 45 degrees).
- No via directly before or after a 45-degree track, except in the breakout zone around an own pad (BREAKOUT mm):
  break out, go to the other layer, run in its direction, come back.
- Widths from the series 0.254 / 0.508 mm: 0.254 default, 0.508 power and Cat6 loops (current check C-35). A 0.508 net
  narrows one step in the series (1.016 -> 0.508 -> 0.254) only where it does not fit (fine-pitch pins). The Cat6 wires
  (Entry class) are 1.016 mm for the surge current (C-36).
- Clearance per netclass; the isolation band (rule area, D-142) is closed on all layers; GND and CHASSIS are not routed (planes, own
  via per SMD pad, D-145).
Method: 0.1 mm grid. A* over (layer, y, x, direction or start or after-via) with an indexed binary heap (numba). For each net a tree grows
from its first pad: the search runs from the tree to the nearest pad not yet connected. Obstacles are the copper of
other nets, dilated by clearance + half width + MARGIN. Nets in order: power, loop, then the others by size; nets that
fail move to the front and the board is routed again (rip-up by order)."""
import fnmatch, json, math, sys, time
import numpy as np
from scipy import ndimage
from matplotlib.path import Path
from numba import njit

G = 0.1                                   # grid pitch, mm
MARGIN = 0.1                              # = G: painted copper ends up to one cell short of the true edge (r4b fix, was 0.085)
EDGE_KEEP = 0.4                           # copper to board edge, mm
VIA_D, VIA_DR = 0.6, 0.3
W_NARROW = 0.254
NARROWED = {}                             # net -> widths it stepped down to (reported)
PREF, ORTH, DIAG = 1.0, 3.0, 1.4142 * 2.5     # step costs per 0.1 mm: main direction, against it, 45 degrees
BEND45, BEND90, VIA = 6.0, 12.0, 25.0
BREAKOUT = 1.5                            # mm around an own pad centre where a via may follow a 45-degree track
WINDOW = 10.0                             # search window margin around tree and targets, mm
LAYER_NAME = ["F", "In2"]                 # routing layer 0: L1 vertical; 1: L3 horizontal
CLASSES = [("GND", ["GND", "*/CHASSIS"], None, None),     # planes, not routed: GND (logic side), CHASSIS (loop side, D-145)
           ("Power", ["+5V", "+3V3", "*U11-VOUT*"], 0.508, 0.2),
           ("Entry", ["*/L?P", "*/L?N"], 1.016, 0.5),               # Cat6 wires J1 to GDT to choke: surge copper (C-36)
           ("Loop", ["Net-(C2?-Pad?)", "Net-(D?1-A?)", "Net-(D?2-K)", "Net-(D32-A)"], 0.508, 0.5),
           ("Default", ["*"], 0.254, 0.2)]
def netclass(n):
    for name, pats, w, c in CLASSES:
        if any(fnmatch.fnmatchcase(n, p) for p in pats): return name, w, c

geo = json.load(open("geom.json"))
X0, Y0, X1, Y1 = geo["outline"]
X0, Y0 = math.floor(X0 / G + 1e-6) * G, math.floor(Y0 / G + 1e-6) * G   # grid on multiples of G: pad centres on the grid
NX, NY = int(math.ceil((X1 - X0) / G)) + 1, int(math.ceil((Y1 - Y0) / G)) + 1
xs = X0 + np.arange(NX) * G; ys = Y0 + np.arange(NY) * G
cx = lambda x: int(round((x - X0) / G)); cy = lambda y: int(round((y - Y0) / G))
NETS = sorted({p["net"] for p in geo["pads"] if p["net"]} | {t["net"] for t in geo["tracks"]})
NID = {n: i for i, n in enumerate(NETS)}
HARD = -2
owner = np.full((2, NY, NX), -1, dtype=np.int32)          # routing layers 0 (F.Cu) and 1 (In2.Cu): -1 free, -2 hard

def window(xa, ya, xb, yb):
    return max(0, cx(xa) - 1), min(NX, cx(xb) + 2), max(0, cy(ya) - 1), min(NY, cy(yb) + 2)
def paint(layers, mask_fn, box, val):
    i0, i1, j0, j1 = window(*box)
    if i0 >= i1 or j0 >= j1: return
    X, Y = np.meshgrid(xs[i0:i1], ys[j0:j1]); m = mask_fn(X, Y)
    for l in layers:
        sub = owner[l, j0:j1, i0:i1]
        if val == HARD: sub[m] = HARD
        else: sub[m & (sub != HARD)] = val
def seg_mask(x1, y1, x2, y2, r):
    def f(X, Y):
        dx, dy = x2 - x1, y2 - y1; L2 = dx * dx + dy * dy
        t = np.clip(((X - x1) * dx + (Y - y1) * dy) / L2, 0, 1) if L2 > 0 else 0
        return (X - (x1 + t * dx)) ** 2 + (Y - (y1 + t * dy)) ** 2 <= r * r
    return f
def pad_mask(p):
    path = Path(p["poly"])
    return lambda X, Y: path.contains_points(np.c_[X.ravel(), Y.ravel()], radius=1e-6).reshape(X.shape)
def pad_box(p):
    px_, py_ = zip(*p["poly"]); return min(px_), min(py_), max(px_), max(py_)
def pad_layers(p):                                          # THT pads reach both routing layers, SMD pads only L1
    return [0, 1] if ("F" in p["layers"] and "B" in p["layers"]) else ([0] if "F" in p["layers"] else [])

# hard obstacles: board edge band, rule areas (isolation barrier), holes
X, Y = np.meshgrid(xs, ys)
owner[:, (X < X0 + EDGE_KEEP) | (X > X1 - EDGE_KEEP) | (Y < Y0 + EDGE_KEEP) | (Y > Y1 - EDGE_KEEP)] = HARD
pts = np.c_[X.ravel(), Y.ravel()]
for poly in geo["rule_areas"]:
    owner[:, Path(poly).contains_points(pts).reshape(Y.shape)] = HARD
for h in geo["holes"]:
    r = h["d"] / 2 + 0.2
    paint([0, 1], lambda A, B, h=h, r=r: (A - h["x"]) ** 2 + (B - h["y"]) ** 2 <= r * r, (h["x"] - r, h["y"] - r, h["x"] + r, h["y"] + r), HARD)
# thermal spokes on L1 (r4b): around a through-hole pad of a plane net in SPOKE_NETS, a ring of SPOKE_KEEP mm stays free of
# other nets on L1 (painted before the pads, so that no pad is overwritten), so that the zone reaches the pad with all spokes (KiCad starved_thermal otherwise)
SPOKE_NETS, SPOKE_KEEP = ["*/CHASSIS"], 1.0
for p in geo["pads"]:
    if p["net"] and pad_layers(p) == [0, 1] and any(fnmatch.fnmatchcase(p["net"], q) for q in SPOKE_NETS):
        r = max(p["w"], p["h"]) / 2 + SPOKE_KEEP
        paint([0], lambda A, B, p=p, r=r: (A - p["x"]) ** 2 + (B - p["y"]) ** 2 <= r * r, (p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r), NID[p["net"]])
PADS = {}
for p in geo["pads"]:
    paint(pad_layers(p), pad_mask(p), pad_box(p), NID[p["net"]] if p["net"] else HARD)
    if p["net"]: PADS.setdefault(p["net"], []).append(p)
def paint_track(t, nid):
    r = t["w"] / 2; l = LAYER_NAME.index(t["layer"]) if t["layer"] in LAYER_NAME else None
    if l is None: return
    paint([l], seg_mask(t["x1"], t["y1"], t["x2"], t["y2"], r),
          (min(t["x1"], t["x2"]) - r, min(t["y1"], t["y2"]) - r, max(t["x1"], t["x2"]) + r, max(t["y1"], t["y2"]) + r), nid)
def paint_via(v, nid):
    r = v["d"] / 2; paint([0, 1], lambda A, B: (A - v["x"]) ** 2 + (B - v["y"]) ** 2 <= r * r, (v["x"] - r, v["y"] - r, v["x"] + r, v["y"] + r), nid)
for t in geo["tracks"]: paint_track(t, NID[t["net"]])
for v in geo["vias"]: paint_via(v, NID[v["net"]])

# directions around the circle: 0 E, 1 SE, 2 S, 3 SW, 4 W, 5 NW, 6 N, 7 NE (y down); 8 = start, 9 = just after a via
DI = np.array([1, 1, 0, -1, -1, -1, 0, 1], dtype=np.int64)
DJ = np.array([0, 1, 1, 1, 0, -1, -1, -1], dtype=np.int64)

@njit(cache=True)
def astar(free, via_ok, breakout, hfield, start_idx, target, H, W, pref, orth, diag, b45, b90, via):
    """free[l,j,i], via_ok[j,i], breakout[j,i], target[l,j,i] (bool), hfield[j,i] heuristic (cells).
    State s = ((l*H + j)*W + i)*10 + d. Returns the reached target state and the parent array (-1 if none)."""
    N = 2 * H * W * 10
    g = np.full(N, np.float32(1e30), dtype=np.float32); par = np.full(N, -1, dtype=np.int32)
    heap_s = np.empty(N, dtype=np.int32); heap_f = np.empty(N, dtype=np.float32); pos = np.full(N, -1, dtype=np.int32); n = 0
    closed = np.zeros(N, dtype=np.bool_)
    for s in start_idx:
        g[s] = 0.0
        # push
        k = n; n += 1; heap_s[k] = s; heap_f[k] = hfield[(s // 10 // W) % H, (s // 10) % W]; pos[s] = k
        while k > 0:
            pk = (k - 1) // 2
            if heap_f[pk] <= heap_f[k]: break
            heap_s[pk], heap_s[k] = heap_s[k], heap_s[pk]; heap_f[pk], heap_f[k] = heap_f[k], heap_f[pk]
            pos[heap_s[k]] = k; pos[heap_s[pk]] = pk; k = pk
    while n > 0:
        s = heap_s[0]; pos[s] = -1; n -= 1
        if n > 0:
            heap_s[0] = heap_s[n]; heap_f[0] = heap_f[n]; pos[heap_s[0]] = 0; k = 0
            while True:
                a = 2 * k + 1; b = a + 1; m = k
                if a < n and heap_f[a] < heap_f[m]: m = a
                if b < n and heap_f[b] < heap_f[m]: m = b
                if m == k: break
                heap_s[m], heap_s[k] = heap_s[k], heap_s[m]; heap_f[m], heap_f[k] = heap_f[k], heap_f[m]
                pos[heap_s[k]] = k; pos[heap_s[m]] = m; k = m
        if closed[s]: continue
        closed[s] = True
        d = s % 10; c = s // 10; i = c % W; j = (c // W) % H; l = c // (W * H)
        if target[l, j, i] and g[s] > 0: return s, par
        gs = g[s]
        for nd in range(9):
            if nd == 8:                                    # via: change layer, direction starts again
                if not via_ok[j, i]: continue
                if d < 8 and d % 2 == 1 and not breakout[j, i]: continue
                if d == 9: continue
                nl = 1 - l
                if not free[nl, j, i]: continue
                ns = ((nl * H + j) * W + i) * 10 + 9; cost = via
            else:
                if d < 8:
                    t = abs(nd - d); t = min(t, 8 - t)
                    if t >= 3: continue
                if d == 9 and nd % 2 == 1 and not breakout[j, i]: continue     # no 45 degrees straight out of a via
                ni = i + DI[nd]; nj = j + DJ[nd]
                if ni < 0 or nj < 0 or ni >= W or nj >= H or not free[l, nj, ni]: continue
                if nd % 2 == 1 and not (free[l, j, ni] and free[l, nj, i]): continue
                if nd % 2 == 1: cost = diag
                elif (l == 0) == (nd == 2 or nd == 6): cost = pref     # L1 vertical, L3 horizontal
                else: cost = orth
                if d < 8 and nd != d:
                    t = abs(nd - d); t = min(t, 8 - t); cost += b45 if t == 1 else b90
                ns = ((l * H + nj) * W + ni) * 10 + nd
            ng = gs + cost
            if ng < g[ns] and not closed[ns]:
                g[ns] = ng; par[ns] = s
                f = ng + hfield[(ns // 10 // W) % H, (ns // 10) % W]
                k = pos[ns]
                if k < 0:
                    k = n; n += 1; heap_s[k] = ns; pos[ns] = k
                heap_f[k] = f
                while k > 0:
                    pk = (k - 1) // 2
                    if heap_f[pk] <= heap_f[k]: break
                    heap_s[pk], heap_s[k] = heap_s[k], heap_s[pk]; heap_f[pk], heap_f[k] = heap_f[k], heap_f[pk]
                    pos[heap_s[k]] = k; pos[heap_s[pk]] = pk; k = pk
    return -1, par

def route_net(net):
    cls, w, clr = netclass(net); nid = NID[net]; pads = PADS[net]
    dist = [ndimage.distance_transform_edt(~((owner[l] != -1) & (owner[l] != nid))) for l in (0, 1)]
    own_smd = np.zeros((NY, NX), dtype=bool)
    for p in pads:
        if pad_layers(p) == [0]:
            i0, i1, j0, j1 = window(*pad_box(p)); Xs, Ys = np.meshgrid(xs[i0:i1], ys[j0:j1]); own_smd[j0:j1, i0:i1] |= pad_mask(p)(Xs, Ys)
    def masks(w):
        r_tr = (clr + w / 2 + MARGIN) / G; r_via = (clr + VIA_D / 2 + MARGIN) / G
        fr = np.stack([(dist[l] >= r_tr) | (owner[l] == nid) for l in (0, 1)])
        return fr, (dist[0] >= r_via) & (dist[1] >= r_via) & ~own_smd
    free, via_ok = masks(w)
    centre = [(cy(p["y"]), cx(p["x"])) for p in pads]
    brk = np.zeros((NY, NX), dtype=bool); rb = int(BREAKOUT / G)
    for (j, i) in centre: brk[max(0, j - rb):j + rb + 1, max(0, i - rb):i + rb + 1] = True
    # tree: first pad centre, plus own copper that is not a pad (locked items)
    tree = {(l, centre[0][0], centre[0][1]) for l in pad_layers(pads[0])}
    padcells = np.zeros((2, NY, NX), dtype=bool)
    for p in pads:
        i0, i1, j0, j1 = window(*pad_box(p)); Xs, Ys = np.meshgrid(xs[i0:i1], ys[j0:j1]); m = pad_mask(p)(Xs, Ys)
        for l in pad_layers(p): padcells[l, j0:j1, i0:i1] |= m
    # locked own copper joins the tree only where it touches the first pad (D-154: the U13 fan-out copper is not yet
    # connected to the rest of the net; before D-154 routed nets had no locked copper)
    for l in pad_layers(pads[0]):
        lab, _ = ndimage.label(owner[l] == nid); k0 = lab[centre[0][0], centre[0][1]]
        if k0: tree |= {(l, j, i) for j, i in zip(*np.nonzero((lab == k0) & ~padcells[l]))}
    todo = list(range(1, len(pads))); tracks, vias = [], []
    while todo:
        pts_t = [(c[1], c[2]) for c in tree] + [centre[k] for k in todo]
        PW = int(WINDOW / G)
        j0 = max(0, min(p[0] for p in pts_t) - PW); j1 = min(NY, max(p[0] for p in pts_t) + PW + 1)
        i0 = max(0, min(p[1] for p in pts_t) - PW); i1 = min(NX, max(p[1] for p in pts_t) + PW + 1)
        H, Wd = j1 - j0, i1 - i0
        target = np.zeros((2, H, Wd), dtype=bool); tmask = np.ones((H, Wd), dtype=bool)
        for k in todo:
            j, i = centre[k]
            for l in pad_layers(pads[k]):
                if free[l, j, i]: target[l, j - j0, i - i0] = True
            tmask[j - j0, i - i0] = False
        hfield = ndimage.distance_transform_edt(tmask).astype(np.float64)      # cells to the nearest target (admissible)
        starts = np.array([((l * H + (j - j0)) * Wd + (i - i0)) * 10 + 8 for (l, j, i) in tree
                           if j0 <= j < j1 and i0 <= i < i1 and free[l, j, i]], dtype=np.int64)
        s_end, par = astar(np.ascontiguousarray(free[:, j0:j1, i0:i1]), np.ascontiguousarray(via_ok[j0:j1, i0:i1]),
                           np.ascontiguousarray(brk[j0:j1, i0:i1]), hfield, starts, target, H, Wd, PREF, ORTH, DIAG, BEND45, BEND90, VIA)
        if s_end < 0:
            if w > W_NARROW:                               # one step down the width series (1.016, 0.508, 0.254)
                w = max(W_NARROW, round(w / 2, 3)); NARROWED.setdefault(net, []).append(w); free, via_ok = masks(w); continue
            return None, todo
        path = []
        s = s_end
        while s >= 0:
            c = s // 10; path.append((c // (Wd * H), (c // Wd) % H + j0, c % Wd + i0)); s = par[s]
        path.reverse()
        jj, ii = path[-1][1], path[-1][2]
        k_hit = next(k for k in todo if centre[k] == (jj, ii))
        # path cells -> straight segments and vias; the end points are the exact pad centres
        pts_xy = lambda c: (X0 + c[2] * G, Y0 + c[1] * G)
        def emit(a, b_, l):
            if a != b_: tracks.append({"net": net, "layer": LAYER_NAME[l], "w": w, "x1": round(a[0], 4), "y1": round(a[1], 4),
                                       "x2": round(b_[0], 4), "y2": round(b_[1], 4)})
        start_c = path[0]; prev = path[0]; prev_d = None; seg_a = pts_xy(start_c)
        exact = {centre[k]: (pads[k]["x"], pads[k]["y"]) for k in range(len(pads))}
        # pad centres are off the grid by up to G/2: a short stub joins the exact centre to the grid, so that long
        # segments stay exactly vertical or horizontal (r4)
        emit(exact.get((start_c[1], start_c[2]), seg_a), seg_a, start_c[0])
        for c in path[1:]:
            if c[0] != prev[0]:
                emit(seg_a, pts_xy(prev), prev[0]); vias.append({"net": net, "x": round(pts_xy(c)[0], 4), "y": round(pts_xy(c)[1], 4), "d": VIA_D, "drill": VIA_DR})
                seg_a = pts_xy(c); prev_d = None
            else:
                dd = (c[1] - prev[1], c[2] - prev[2])
                if prev_d is not None and dd != prev_d: emit(seg_a, pts_xy(prev), prev[0]); seg_a = pts_xy(prev)
                prev_d = dd
            prev = c
        emit(seg_a, pts_xy(prev), prev[0]); emit(pts_xy(prev), (pads[k_hit]["x"], pads[k_hit]["y"]), prev[0])
        tree |= set(path)
        for l in pad_layers(pads[k_hit]): tree.add((l, jj, ii))
        todo.remove(k_hit)
    return (tracks, vias), []

def order_key(n):
    cls = netclass(n)[0]; ps = PADS[n]
    hp = (max(p["x"] for p in ps) - min(p["x"] for p in ps)) + (max(p["y"] for p in ps) - min(p["y"] for p in ps))
    return ({"Power": 0, "Entry": 1, "Loop": 1}.get(cls, 2), hp)
route_nets = sorted([n for n in PADS if netclass(n)[0] != "GND" and len(PADS[n]) > 1 and not n.startswith("unconnected")], key=order_key)
OWNER0 = owner.copy()
def run(order):
    owner[:] = OWNER0
    res_ = {"tracks": [], "vias": [], "failed": [], "order": order}
    for n in order:
        res, left = route_net(n)
        if res is None:
            res_["failed"].append({"net": n, "pads_left": [PADS[n][k]["ref"] + "." + PADS[n][k]["num"] for k in left]}); continue
        for t in res[0]: paint_track(t, NID[n])
        for v in res[1]: paint_via(v, NID[n])
        res_["tracks"] += res[0]; res_["vias"] += res[1]
    return res_
t_start = time.time(); order = route_nets; result = None
for it in range(8):
    r = run(order)
    print("pass %d: failed %d %s | vias %d | %.0f s" % (it + 1, len(r["failed"]), [f["net"].split("/")[-1] for f in r["failed"]],
          len(r["vias"]), time.time() - t_start), flush=True)
    if result is None or len(r["failed"]) < len(result["failed"]): result = r
    if not r["failed"]: break
    bad = [f["net"] for f in r["failed"]]
    order = bad + [n for n in order if n not in bad]
# 45-degree corners (Prins, 2026-10-23): every 90-degree bend of a routed net becomes a chamfer of CH_LEG per leg. Bends at a
# via or a pad centre stay: the via or pad copper covers them, and a chamfer there would cut the connection.
CH_LEG = 0.5
def chamfer_result(res):
    import collections
    keep = {(round(v["x"], 3), round(v["y"], 3)) for v in res["vias"]} | {(round(p["x"], 3), round(p["y"], 3)) for p in geo["pads"]}
    ends = collections.defaultdict(list)
    for t in res["tracks"]:
        for e in ("1", "2"): ends[(t["net"], t["layer"], round(t["x" + e], 3), round(t["y" + e], 3))].append((t, e))
    n = 0
    for (nn, ln, x, y), v in ends.items():
        if len(v) != 2 or (x, y) in keep: continue
        (ta, ea), (tb, eb) = v
        oa, ob = ("2" if ea == "1" else "1"), ("2" if eb == "1" else "1")
        ax, ay = ta["x" + oa] - x, ta["y" + oa] - y; bx, by = tb["x" + ob] - x, tb["y" + ob] - y
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la < 1e-6 or lb < 1e-6 or abs((ax * bx + ay * by) / la / lb) > 0.02: continue
        d = min(CH_LEG, 0.45 * la, 0.45 * lb)
        pa = (round(x + ax / la * d, 4), round(y + ay / la * d, 4)); pb = (round(x + bx / lb * d, 4), round(y + by / lb * d, 4))
        ta["x" + ea], ta["y" + ea] = pa; tb["x" + eb], tb["y" + eb] = pb
        res["tracks"].append({"net": nn, "layer": ln, "w": min(ta["w"], tb["w"]), "x1": pa[0], "y1": pa[1], "x2": pb[0], "y2": pb[1]})
        n += 1
    return n
# T-junctions on tracks narrower than 0.6 mm (Prins, 2026-10-23, D-159): two 45-degree fillets of CH_T per leg fill the two
# right-angle corners where a branch meets a straight track at right angles. Not at a via or pad centre (their copper covers it).
CH_T, T_MAXW = 0.5, 0.6
def chamfer_tees(res):
    keep = {(round(v["x"], 3), round(v["y"], 3)) for v in res["vias"]} | {(round(p["x"], 3), round(p["y"], 3)) for p in geo["pads"]}
    add = []
    trs = res["tracks"]
    for A in trs:
        if A["w"] >= T_MAXW: continue
        for e, o in (("1", "2"), ("2", "1")):
            ex, ey = A["x" + e], A["y" + e]
            if (round(ex, 3), round(ey, 3)) in keep: continue
            la = math.hypot(A["x" + o] - ex, A["y" + o] - ey)
            if la < 1e-6: continue
            ux, uy = (A["x" + o] - ex) / la, (A["y" + o] - ey) / la
            for B in trs:
                if B is A or B["net"] != A["net"] or B["layer"] != A["layer"]: continue
                bx, by = B["x2"] - B["x1"], B["y2"] - B["y1"]; lb = math.hypot(bx, by)
                if lb < 1e-6: continue
                vx, vy = bx / lb, by / lb
                t = (ex - B["x1"]) * vx + (ey - B["y1"]) * vy
                if t <= 1e-3 or t >= lb - 1e-3 or abs((ex - B["x1"]) * vy - (ey - B["y1"]) * vx) > 1e-3: continue   # E on B's interior
                if abs(ux * vx + uy * vy) > 0.02: continue                                  # branch at right angles only
                d = min(CH_T, 0.45 * la, 0.45 * t, 0.45 * (lb - t))
                px, py = round(ex + ux * d, 4), round(ey + uy * d, 4)
                for sg in (1, -1):
                    add.append({"net": A["net"], "layer": A["layer"], "w": A["w"], "x1": px, "y1": py,
                                "x2": round(ex + sg * vx * d, 4), "y2": round(ey + sg * vy * d, 4)})
                break
    # T at a shared vertex: three segment ends meet, two of them on one straight line, the third at right angles
    import collections
    ends = collections.defaultdict(list)
    for T_ in trs:
        for e, o in (("1", "2"), ("2", "1")):
            ex, ey = T_["x" + e], T_["y" + e]; l = math.hypot(T_["x" + o] - ex, T_["y" + o] - ey)
            if l > 1e-6: ends[(T_["net"], T_["layer"], round(ex, 3), round(ey, 3))].append(((T_["x" + o] - ex) / l, (T_["y" + o] - ey) / l, l, T_["w"]))
    for (nn, ln, ex, ey), v in ends.items():
        if len(v) != 3 or (ex, ey) in keep: continue
        for i in range(3):
            br, m = v[i], [v[j] for j in range(3) if j != i]
            if br[3] >= T_MAXW or abs(m[0][0] + m[1][0]) > 0.02 or abs(m[0][1] + m[1][1]) > 0.02: continue      # main: opposite
            if abs(br[0] * m[0][0] + br[1] * m[0][1]) > 0.02: continue                                        # branch at right angles
            d = min(CH_T, 0.45 * br[2], 0.45 * m[0][2], 0.45 * m[1][2])
            px, py = round(ex + br[0] * d, 4), round(ey + br[1] * d, 4)
            for mm_ in m:
                add.append({"net": nn, "layer": ln, "w": br[3], "x1": px, "y1": py, "x2": round(ex + mm_[0] * d, 4), "y2": round(ey + mm_[1] * d, 4)})
            break
    trs += add
    return len(add) // 2
print("chamfered corners:", chamfer_result(result), "T-junction fillets:", chamfer_tees(result))
json.dump(result, open("routes.json", "w"), indent=0)
print("narrowed:", {n.split("/")[-1]: w for n, w in NARROWED.items()})
L = {ln: sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) for t in result["tracks"] if t["layer"] == ln) for ln in LAYER_NAME}
print("nets %d routed %d failed %d | L1 %.0f mm L3 %.0f mm vias %d | %.0f s" % (len(route_nets), len(route_nets) - len(result["failed"]),
      len(result["failed"]), L["F"], L["In2"], len(result["vias"]), time.time() - t_start))
