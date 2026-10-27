#!/usr/bin/env python3
"""Grid router for the controller board (routing r2, D-143). Plain Python 3 with numpy, scipy and matplotlib; it does not
need KiCad. Input geom.json (export_geom.py), output routes.json (tracks and vias), applied by gen_controller_pcb.py.

Rules (hardware-design-rules, pcb-layout.md; D-131, D-142):
- B.Cu is the GND plane of the logic side. A track there costs COST_B_LOGIC times F.Cu, so the router takes B.Cu only
  for short jumps where F.Cu has no way through. On the loop side (no plane) B.Cu costs COST_B_LOOP.
- A via costs COST_VIA (in units of 0.1 mm of F.Cu track). The isolation barrier band is closed on both layers.
- Clearance per netclass (same classes as gen_controller_pcb.py). GND is not routed (plane and own vias).
Method: 0.1 mm grid, 8 directions per layer plus vias; for each net a tree grows from its first pad: a minimum-cost path (skimage MCP) from the tree to
the nearest pad not yet connected, until all pads are in the tree. Obstacles are the copper of other nets, dilated by
clearance + half track width + grid margin (scipy distance transform). Nets in order: power, loop, then the others by
size. Every routed net becomes an obstacle for the next."""
import fnmatch, json, math, sys, time
import numpy as np
from skimage.graph import MCP_Geometric
from scipy import ndimage
from matplotlib.path import Path

G = 0.1                                   # grid pitch, mm
MARGIN = 0.085                            # grid error allowance on every clearance, mm
COST_B_LOGIC, COST_B_LOOP, COST_VIA = 15.0, 1.5, 40.0
W_NARROW = 0.254                          # width for the last part of a power net that does not fit at full width
WINDOW = 12.0                             # search window margin around tree and targets, mm
EDGE_KEEP = 0.4                           # copper to board edge, mm
LOOP_X, LOOP_Y = 54.5, 61.5               # loop side: x < LOOP_X and y < LOOP_Y (gen_controller_pcb.py, D-142)
VIA_D, VIA_DR = 0.6, 0.3
CLASSES = [("GND", ["GND"], None, None),
           ("Power", ["+5V", "+3V3", "*U11-VOUT*"], 0.5, 0.2),
           ("Loop", ["*/L?P", "*/L?N", "*/CHASSIS", "Net-(C2?-Pad?)", "Net-(D?1-A?)", "Net-(D?2-K)", "Net-(D32-A)"], 0.4, 0.5),
           ("Default", ["*"], 0.254, 0.2)]
def netclass(n):
    for name, pats, w, c in CLASSES:
        if any(fnmatch.fnmatchcase(n, p) for p in pats): return name, w, c

geo = json.load(open("geom.json"))
X0, Y0, X1, Y1 = geo["outline"]
NX, NY = int(math.ceil((X1 - X0) / G)) + 1, int(math.ceil((Y1 - Y0) / G)) + 1
xs = X0 + np.arange(NX) * G; ys = Y0 + np.arange(NY) * G
cx = lambda x: int(round((x - X0) / G)); cy = lambda y: int(round((y - Y0) / G))
NETS = sorted({p["net"] for p in geo["pads"] if p["net"]} | {t["net"] for t in geo["tracks"]})
NID = {n: i for i, n in enumerate(NETS)}
HARD = -2
owner = np.full((2, NY, NX), -1, dtype=np.int32)          # -1 free, -2 hard obstacle, >= 0 net id

def window(xa, ya, xb, yb):
    i0, i1 = max(0, cx(xa) - 1), min(NX, cx(xb) + 2); j0, j1 = max(0, cy(ya) - 1), min(NY, cy(yb) + 2)
    return i0, i1, j0, j1
def paint(layer, mask_fn, xa, ya, xb, yb, val):
    i0, i1, j0, j1 = window(xa, ya, xb, yb)
    if i0 >= i1 or j0 >= j1: return
    X, Y = np.meshgrid(xs[i0:i1], ys[j0:j1])
    m = mask_fn(X, Y)
    for l in ([0, 1] if layer == "FB" else [0 if layer == "F" else 1]):
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
    if p.get("poly"):                                          # exact outline from KiCad (custom pads, rounded corners)
        path = Path(p["poly"])
        return lambda X, Y: path.contains_points(np.c_[X.ravel(), Y.ravel()], radius=1e-6).reshape(X.shape)
    a = math.radians(-p["rot"]); ca, sa = math.cos(a), math.sin(a); hw, hh = p["w"] / 2, p["h"] / 2
    def f(X, Y):
        u = (X - p["x"]) * ca - (Y - p["y"]) * sa; v = (X - p["x"]) * sa + (Y - p["y"]) * ca
        if p["shape"] == "circle": return u * u + v * v <= hw * hw
        if p["shape"] == "oval":
            r = min(hw, hh); du = np.maximum(np.abs(u) - (hw - r), 0); dv = np.maximum(np.abs(v) - (hh - r), 0)
            return du * du + dv * dv <= r * r
        return (np.abs(u) <= hw) & (np.abs(v) <= hh)
    return f
def pad_box(p):
    if p.get("poly"):
        px_, py_ = zip(*p["poly"]); return min(px_), min(py_), max(px_), max(py_)
    r = math.hypot(p["w"], p["h"]) / 2; return p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r

# hard obstacles: outside the board edge band, rule areas (barrier), holes
X, Y = np.meshgrid(xs, ys)
edge = (X < X0 + EDGE_KEEP) | (X > X1 - EDGE_KEEP) | (Y < Y0 + EDGE_KEEP) | (Y > Y1 - EDGE_KEEP)
owner[:, edge] = HARD
pts = np.c_[X.ravel(), Y.ravel()]
for poly in geo["rule_areas"]:
    m = Path(poly).contains_points(pts).reshape(Y.shape); owner[:, m] = HARD
for h in geo["holes"]:
    r = h["d"] / 2 + 0.2; paint("FB", lambda A, B, h=h, r=r: (A - h["x"]) ** 2 + (B - h["y"]) ** 2 <= r * r, h["x"] - r, h["y"] - r, h["x"] + r, h["y"] + r, HARD)
# copper: pads, locked tracks, vias
PADS = {}
for p in geo["pads"]:
    val = NID[p["net"]] if p["net"] else HARD
    for l in p["layers"]:
        paint(l, pad_mask(p), *pad_box(p), val)
    if p["net"]: PADS.setdefault(p["net"], []).append(p)
def paint_track(t, nid):
    r = t["w"] / 2; paint(t["layer"], seg_mask(t["x1"], t["y1"], t["x2"], t["y2"], r),
                          min(t["x1"], t["x2"]) - r, min(t["y1"], t["y2"]) - r, max(t["x1"], t["x2"]) + r, max(t["y1"], t["y2"]) + r, nid)
def paint_via(v, nid):
    r = v["d"] / 2; paint("FB", lambda A, B: (A - v["x"]) ** 2 + (B - v["y"]) ** 2 <= r * r, v["x"] - r, v["y"] - r, v["x"] + r, v["y"] + r, nid)
for t in geo["tracks"]: paint_track(t, NID[t["net"]])
for v in geo["vias"]: paint_via(v, NID[v["net"]])

loop_side = (X < LOOP_X) & (Y < LOOP_Y)
COSTB = np.where(loop_side, COST_B_LOOP, COST_B_LOGIC).astype(np.float32)
OFFS = [(0, dj, di) for dj in (-1, 0, 1) for di in (-1, 0, 1) if dj or di] + [(1, 0, 0), (-1, 0, 0)]   # 8 directions, layer step

def route_net(net):
    cls, w, clr = netclass(net); nid = NID[net]
    dist = [ndimage.distance_transform_edt(~((owner[l] != -1) & (owner[l] != nid))) for l in (0, 1)]
    def masks(w):
        r_tr = (clr + w / 2 + MARGIN) / G; r_via = (clr + VIA_D / 2 + MARGIN) / G
        fr = np.stack([(dist[l] >= r_tr) | (owner[l] == nid) for l in (0, 1)])
        return fr, (dist[0] >= r_via) & (dist[1] >= r_via)
    free, via_ok = masks(w)
    smd_own = np.zeros((NY, NX), dtype=bool)                  # no via inside an own SMD pad
    for p in PADS[net]:
        if p["layers"] == ["F"]:
            i0, i1, j0, j1 = window(*pad_box(p)); Xs, Ys = np.meshgrid(xs[i0:i1], ys[j0:j1])
            smd_own[j0:j1, i0:i1] |= pad_mask(p)(Xs, Ys)
    via_ok &= ~smd_own
    pads = PADS[net]
    def pad_cells(p):
        i0, i1, j0, j1 = window(*pad_box(p)); Xs, Ys = np.meshgrid(xs[i0:i1], ys[j0:j1]); m = pad_mask(p)(Xs, Ys)
        jj, ii = np.nonzero(m); out = []
        for l in p["layers"]:
            li = 0 if l == "F" else 1
            out += [(li, j0 + j, i0 + i) for j, i in zip(jj, ii)]
        return out
    cells = [pad_cells(p) for p in pads]
    tree = set(cells[0]); todo = list(range(1, len(pads))); new_tracks, new_vias = [], []
    padset = {c for cl in cells for c in cl}
    tree |= {c for c in zip(*np.nonzero(owner == nid)) if c not in padset}   # own copper that is not a pad (locked items)
    while todo:
        tgt = {}
        for k in todo:
            for c in cells[k]: tgt[c] = k
        if any(c in tree for c in tgt):                       # pad already touched by the tree
            done = {tgt[c] for c in tgt if c in tree}
            for k in done: tree |= set(cells[k])
            todo = [k for k in todo if k not in done]; continue
        tj = [c[1] for c in tree] + [cy(pads[k]["y"]) for k in todo]; ti = [c[2] for c in tree] + [cx(pads[k]["x"]) for k in todo]
        PADW = int(WINDOW / G)                                 # search window: tree and targets plus WINDOW mm
        wi0, wi1 = max(0, min(ti) - PADW), min(NX, max(ti) + PADW + 1); wj0, wj1 = max(0, min(tj) - PADW), min(NY, max(tj) + PADW + 1)
        C = np.full((3, wj1 - wj0, wi1 - wi0), np.inf, dtype=np.float64)          # z 0 F.Cu, 1 via, 2 B.Cu
        C[0][free[0, wj0:wj1, wi0:wi1]] = 1.0
        fb = free[1, wj0:wj1, wi0:wi1]; C[2][fb] = COSTB[wj0:wj1, wi0:wi1][fb]
        vk = via_ok[wj0:wj1, wi0:wi1] & free[0, wj0:wj1, wi0:wi1] & fb; C[1][vk] = COST_VIA
        Z = lambda l: 0 if l == 0 else 2
        starts = [(Z(l), j - wj0, i - wi0) for (l, j, i) in tree if wj0 <= j < wj1 and wi0 <= i < wi1]
        ends = [(Z(l), j - wj0, i - wi0) for (l, j, i) in tgt]
        mcp = MCP_Geometric(C, offsets=OFFS)
        costs, _ = mcp.find_costs(starts, ends, find_all_ends=False)
        reach = [e for e in ends if np.isfinite(costs[e])]
        if not reach:
            if w > W_NARROW:                                   # a wide track does not fit (fine-pitch pin): narrow
                w = W_NARROW; free, via_ok = masks(w); via_ok &= ~smd_own; continue
            return None, todo
        best = min(reach, key=lambda e: costs[e])
        raw = mcp.traceback(best)
        path = []
        for z, j, i in raw:
            if z == 1:
                continue                                       # via node: the layer change shows in the F/B neighbours
            path.append((0 if z == 0 else 1, j + wj0, i + wi0))
        found = path[-1]
        # cells -> segments (merge straight runs) and vias
        seg_start = path[0]; prev = path[0]; prev_d = None
        def emit(a, b_):
            if a[1:] != b_[1:]:
                new_tracks.append({"net": net, "layer": "F" if a[0] == 0 else "B", "w": w,
                                   "x1": round(X0 + a[2] * G, 4), "y1": round(Y0 + a[1] * G, 4),
                                   "x2": round(X0 + b_[2] * G, 4), "y2": round(Y0 + b_[1] * G, 4)})
        for c in path[1:]:
            if c[0] != prev[0]:
                emit(seg_start, prev); new_vias.append({"net": net, "x": round(X0 + c[2] * G, 4), "y": round(Y0 + c[1] * G, 4), "d": VIA_D, "drill": VIA_DR})
                seg_start = c; prev_d = None
            else:
                d = (c[1] - prev[1], c[2] - prev[2])
                if prev_d is not None and d != prev_d: emit(seg_start, prev); seg_start = prev
                prev_d = d
            prev = c
        emit(seg_start, prev)
        for c in path: tree.add(c)
        tree |= set(cells[tgt[found]])
        todo = [k for k in todo if k != tgt[found]]
    return (new_tracks, new_vias), []

def pad_access(net):
    """Pads of net with no free cell next to them on any of their layers (cannot be reached)."""
    cls, w, clr = netclass(net); nid = NID[net]; r_tr = (clr + w / 2 + MARGIN) / G; bad = []
    free = [None, None]
    for l in (0, 1):
        other = (owner[l] != -1) & (owner[l] != nid); d = ndimage.distance_transform_edt(~other)
        free[l] = (d >= r_tr) | (owner[l] == nid)
    for p in PADS[net]:
        i0, i1, j0, j1 = window(*pad_box(p)); Xs, Ys = np.meshgrid(xs[i0:i1], ys[j0:j1]); m = pad_mask(p)(Xs, Ys)
        ring = ndimage.binary_dilation(m, iterations=2) & ~m
        ok = any((free[0 if l == "F" else 1][j0:j1, i0:i1] & ring).any() for l in p["layers"])
        if not ok: bad.append(p["ref"] + "." + p["num"])
    return bad
def order_key(n):
    cls = netclass(n)[0]; ps = PADS[n]
    hp = (max(p["x"] for p in ps) - min(p["x"] for p in ps)) + (max(p["y"] for p in ps) - min(p["y"] for p in ps))
    return ({"Power": 0, "Loop": 1}.get(cls, 2), hp)
if "--check" in sys.argv:
    for n in sorted(PADS):
        if netclass(n)[0] == "GND" or len(PADS[n]) < 2 or n.startswith("unconnected"): continue
        bad = pad_access(n)
        if bad: print("blocked", n, bad)
    sys.exit()
route_nets = sorted([n for n in PADS if netclass(n)[0] != "GND" and len(PADS[n]) > 1 and not n.startswith("unconnected")], key=order_key)
OWNER0 = owner.copy()
def run(order):
    owner[:] = OWNER0
    res_ = {"tracks": [], "vias": [], "failed": [], "order": order}
    for n in order:
        res, left = route_net(n)
        if res is None:
            res_["failed"].append({"net": n, "pads_left": [PADS[n][k]["ref"] + "." + PADS[n][k]["num"] for k in left]}); continue
        tr, vi = res
        for t in tr: paint_track(t, NID[n])
        for v in vi: paint_via(v, NID[n])
        res_["tracks"] += tr; res_["vias"] += vi
    return res_
# rip-up and reroute by order: nets that fail move to the front, and the whole board is routed again
t_start = time.time(); order = route_nets; result = None
for it in range(8):
    r = run(order)
    lb = sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) for t in r["tracks"] if t["layer"] == "B")
    print("pass %d: failed %d %s | B.Cu %.0f mm vias %d | %.0f s" % (it + 1, len(r["failed"]), [f["net"].split("/")[-1] for f in r["failed"]],
          lb, len(r["vias"]), time.time() - t_start), flush=True)
    if result is None or len(r["failed"]) < len(result["failed"]): result = r
    if not r["failed"]: break
    bad = [f["net"] for f in r["failed"]]
    order = bad + [n for n in order if n not in bad]
json.dump(result, open("routes.json", "w"), indent=0)
LB = sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) for t in result["tracks"] if t["layer"] == "B")
LF = sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) for t in result["tracks"] if t["layer"] == "F")
print("nets %d routed %d failed %d | F.Cu %.0f mm B.Cu %.0f mm vias %d | %.0f s" % (len(route_nets), len(route_nets) - len(result["failed"]),
      len(result["failed"]), LF, LB, len(result["vias"]), time.time() - t_start))
