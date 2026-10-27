#!/usr/bin/env python3
"""Grid router, general version (RF board p2c; derived from the controller-board router r4, D-143 to D-145, D-158, D-159).
Plain Python 3 with numpy, scipy, matplotlib and numba; it does not need KiCad. Board settings come from router_cfg.json
(argument 1, default router_cfg.json). Input geom.json (export_geom.py), output routes.json (applied by the board generator).

Routing style (Prins, 2026-10-21 and 2026-10-23):
- Each routing layer has a main direction. A track against it costs ORTH per step, a 45-degree track DIAG per step.
- Every bend costs (BEND45, BEND90); turns of 135 degrees or more are not allowed.
- A track leaves and enters a pad at its centre.
- No via directly before or after a 45-degree track, except in the breakout zone around an own pad.
- 90-degree corners become 45-degree chamfers; right-angle T-junctions on tracks below 0.6 mm get two fillets (D-158, D-159).
Changes against the controller version:
- Any number of layers. Layers with route false (for example B.Cu with the RF columns) are obstacles only. A via goes
  through all layers and can move the route to any other routing layer.
- Copper of fixed_nets (RF) keeps rf_clear per layer from routed copper and vias (M-70: kicad-cli ignores .kicad_dru).
- A layer can be restricted to regions (restrict): rectangles, boxes around listed parts, and the breakout zone around
  the net's own SMD pads.
- Connections, not nets: each net is split into its minimum spanning tree of pad-to-pad connections, and all connections
  of all nets are routed shortest first. A connection joins the copper of one pad group to the copper of the other (so
  T-junctions on existing own tracks are allowed), in a window around the nearest pair (widened in steps on failure).
  Distance fields are computed in that window only. Nets that fail go first in the next pass.
- Interior segments shorter than 0.05 mm are merged away before the chamfer step; short stubs at pad and via centres stay.
- A layer change inside own through copper (THT pad, via) is free and adds no via; new vias keep clear of own through copper.
- Fixed-net pads keep rf_pad_clear on all layers (their local pad clearance, which DRC applies on every layer)."""
import collections, fnmatch, json, math, sys, time
import numpy as np
from scipy import ndimage
from matplotlib.path import Path
from numba import njit

CFG = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "router_cfg.json"))
G, MARGIN, EDGE_KEEP = CFG["grid"], CFG["margin"], CFG["edge_keep"]
VIA_D, VIA_DR = CFG["via"]
W_NARROW = 0.254
NARROWED = {}
_C = CFG.get("costs", {})                 # step costs per grid step and turn costs; defaults = controller board r4
PREF, ORTH, DIAG = _C.get("pref", 1.0), _C.get("orth", 3.0), _C.get("diag", 1.4142 * 2.5)
BEND45, BEND90, VIA = _C.get("bend45", 6.0), _C.get("bend90", 12.0), _C.get("via", 25.0)
BREAKOUT = CFG["breakout"]
SEG_MIN = int(round(CFG.get("seg_min", 0.0) / G))   # minimum track segment between bends and vias, grid steps (M-78)
NO_MIN = set()                                       # nets with a connection routed without the minimum (reported)
RL_N = CFG.get("max_states_rl", 250000000)           # shared search buffers of astar_rl
HW = CFG.get("h_weight", 1.0)
if SEG_MIN > 1:
    RL_G = np.full(RL_N, np.float32(1e30), dtype=np.float32); RL_P = np.full(RL_N, -1, dtype=np.int32); RL_C = np.zeros(RL_N, dtype=np.bool_)
LAY = [l["name"] for l in CFG["layers"]]                  # all copper layers in the model (owner index)
RL = [k for k, l in enumerate(CFG["layers"]) if l["route"]]   # routing layers (owner index)
RNAME = [LAY[k] for k in RL]
LDIR = np.array([1 if CFG["layers"][k]["dir"] == "V" else 0 for k in RL], dtype=np.int64)
CLASSES = CFG["classes"]
def netclass(n):
    for name, pats, w, c in CLASSES:
        if any(fnmatch.fnmatchcase(n, p) for p in pats): return name, w, c
def is_fixed(n): return any(fnmatch.fnmatchcase(n, p) for p in CFG["fixed_nets"])

geo = json.load(open(CFG["geom"]))
X0, Y0, X1, Y1 = geo["outline"]
X0, Y0 = math.floor(X0 / G + 1e-6) * G, math.floor(Y0 / G + 1e-6) * G
NX, NY = int(math.ceil((X1 - X0) / G)) + 1, int(math.ceil((Y1 - Y0) / G)) + 1
xs = X0 + np.arange(NX) * G; ys = Y0 + np.arange(NY) * G
cx = lambda x: int(round((x - X0) / G)); cy = lambda y: int(round((y - Y0) / G))
NETS = sorted({p["net"] for p in geo["pads"] if p["net"]} | {t["net"] for t in geo["tracks"]} | {v["net"] for v in geo["vias"]})
NID = {n: i for i, n in enumerate(NETS)}
HARD = -2
NL = len(LAY)
owner = np.full((NL, NY, NX), -1, dtype=np.int32)

def window(xa, ya, xb, yb):
    return max(0, cx(xa) - 1), min(NX, cx(xb) + 2), max(0, cy(ya) - 1), min(NY, cy(yb) + 2)
def paint(layers, mask_fn, box, val, arr=None):
    arr = owner if arr is None else arr
    i0, i1, j0, j1 = window(*box)
    if i0 >= i1 or j0 >= j1: return
    X, Y = np.meshgrid(xs[i0:i1], ys[j0:j1]); m = mask_fn(X, Y)
    for l in layers:
        sub = arr[l, j0:j1, i0:i1]
        if arr.dtype == bool: sub[m] = True
        elif val == HARD: sub[m] = HARD
        else: sub[m & (sub != HARD)] = val
def seg_mask(x1, y1, x2, y2, r):
    def f(X, Y):
        dx, dy = x2 - x1, y2 - y1; L2 = dx * dx + dy * dy
        t = np.clip(((X - x1) * dx + (Y - y1) * dy) / L2, 0, 1) if L2 > 0 else 0
        return (X - (x1 + t * dx)) ** 2 + (Y - (y1 + t * dy)) ** 2 <= r * r
    return f
def disc(x, y, r): return lambda A, B: (A - x) ** 2 + (B - y) ** 2 <= r * r
def pad_mask(p):
    path = Path(p["poly"])
    return lambda X, Y: path.contains_points(np.c_[X.ravel(), Y.ravel()], radius=1e-6).reshape(X.shape)
def pad_box(p):
    px_, py_ = zip(*p["poly"]); return min(px_), min(py_), max(px_), max(py_)
def pad_layers(p):                                      # owner indices: THT (F and B) on all layers, SMD on its layer
    if "F" in p["layers"] and "B" in p["layers"]: return list(range(NL))
    return [LAY.index(l) for l in p["layers"] if l in LAY]
def cu_layers(p):                                       # owner indices of the pad copper itself (a terminal pad keeps its own
    q = dict(p, layers=p.get("cu", p["layers"]))         # copper layers; "layers" says where the router may end on it)
    return pad_layers(q)
def pad_rl(p): return [RL.index(l) for l in pad_layers(p) if l in RL]     # routing-layer indices

X, Y = np.meshgrid(xs, ys)
owner[:, (X < X0 + EDGE_KEEP) | (X > X1 - EDGE_KEEP) | (Y < Y0 + EDGE_KEEP) | (Y > Y1 - EDGE_KEEP)] = HARD
RC = CFG.get("corner_radius", 0.0)                   # rounded board corners (RF board R 5 mm, D-113): keep EDGE_KEEP inside the arc
if RC > 0:
    for (ccx, ccy) in ((X0 + RC, Y0 + RC), (X1 - RC, Y0 + RC), (X0 + RC, Y1 - RC), (X1 - RC, Y1 - RC)):
        inq = (np.abs(X - ccx) <= RC + 0.05) & (np.abs(Y - ccy) <= RC + 0.05) & (np.sign(X - ccx) == np.sign(ccx - (X0 + X1) / 2)) & (np.sign(Y - ccy) == np.sign(ccy - (Y0 + Y1) / 2))
        owner[:, inq & (np.hypot(X - ccx, Y - ccy) > RC - EDGE_KEEP)] = HARD
# drilled holes of pads (any net) and NPTH: a new via keeps 0.25 mm drill to drill (DRC hole_to_hole, M-79)
HOLES = np.zeros((1, NY, NX), dtype=bool)
pts = np.c_[X.ravel(), Y.ravel()]
for poly in geo["rule_areas"]:
    owner[:, Path(poly).contains_points(pts).reshape(Y.shape)] = HARD
del pts
PADCU = np.zeros((1, NY, NX), dtype=bool)            # pad copper of every net (GND stitching vias keep off pads, M-79)
for p in geo["pads"]:
    paint([0], pad_mask(p), pad_box(p), True, arr=PADCU)
    if p.get("drill", 0) > 0:
        r = p["drill"] / 2; paint([0], disc(p["x"], p["y"], r), (p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r), True, arr=HOLES)
for h in geo["holes"]:
    r = h["d"] / 2; paint([0], disc(h["x"], h["y"], r), (h["x"] - r, h["y"] - r, h["x"] + r, h["y"] + r), True, arr=HOLES)
for h in geo["holes"]:
    r = h["d"] / 2 + 0.2; paint(range(NL), disc(h["x"], h["y"], r), (h["x"] - r, h["y"] - r, h["x"] + r, h["y"] + r), HARD)
SP = CFG["spokes"]
for p in geo["pads"]:
    if p["net"] and len(cu_layers(p)) == NL and any(fnmatch.fnmatchcase(p["net"], q) for q in SP["nets"]):
        r = max(p["w"], p["h"]) / 2 + SP["keep"]
        paint([LAY.index(l) for l in SP["layers"]], disc(p["x"], p["y"], r), (p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r), NID[p["net"]])
REF0 = collections.defaultdict(list)
for p in geo["pads"]: REF0[p["ref"]].append(p)
PADS = {}
for p in geo["pads"]:
    paint(cu_layers(p), pad_mask(p), pad_box(p), NID[p["net"]] if p["net"] else HARD)
    if p["net"]: PADS.setdefault(p["net"], []).append(p)
def paint_track(t, nid):
    if t["layer"] not in LAY: return
    r = t["w"] / 2
    paint([LAY.index(t["layer"])], seg_mask(t["x1"], t["y1"], t["x2"], t["y2"], r),
          (min(t["x1"], t["x2"]) - r, min(t["y1"], t["y2"]) - r, max(t["x1"], t["x2"]) + r, max(t["y1"], t["y2"]) + r), nid)
VIAC = np.zeros((2, NY, NX), dtype=bool)                  # [0] every via disc (GND via spacing), [1] GND via centres
def paint_via(v, nid):
    r = v["d"] / 2; paint(range(NL), disc(v["x"], v["y"], r), (v["x"] - r, v["y"] - r, v["x"] + r, v["y"] + r), nid)
    paint([0], disc(v["x"], v["y"], r), (v["x"] - r, v["y"] - r, v["x"] + r, v["y"] + r), True, arr=VIAC)
    if v["net"] == "GND": VIAC[1, cy(v["y"]), cx(v["x"])] = True
for t in geo["tracks"]: paint_track(t, NID[t["net"]])
for v in geo["vias"]: paint_via(v, NID[v["net"]])

# escape strips (p2c): every SMD pad of a fine-pitch footprint (nearest pad of the same part closer than escape.pitch) owns a
# strip of its own width, escape.len mm long, outward from the part centre. Other nets cannot run along the pin ends, so each
# pin keeps a way out to a via. Only free cells are taken.
ESC = CFG.get("escape", {"pitch": 0.0, "len": 0.0})
for ref, ps in REF0.items():
    sm = [p for p in ps if p["net"] and len(pad_layers(p)) == 1]       # terminal pads (moved to a fan-out via) are left out
    if len(sm) < 4: continue
    mx, my = sum(p["x"] for p in ps) / len(ps), sum(p["y"] for p in ps) / len(ps)
    for p in sm:
        if min(math.hypot(p["x"] - q["x"], p["y"] - q["y"]) for q in ps if q is not p) >= ESC["pitch"]: continue
        a, b, c, d = pad_box(p); dx, dy = p["x"] - mx, p["y"] - my
        if abs(dx) >= abs(dy):
            box = (c, b, c + ESC["len"], d) if dx > 0 else (a - ESC["len"], b, a, d)
        else:
            box = (a, d, c, d + ESC["len"]) if dy > 0 else (a, b - ESC["len"], c, b)
        i0, i1, j0, j1 = window(*box)
        XX, YY = np.meshgrid(xs[i0:i1], ys[j0:j1]); m = (XX >= box[0]) & (XX <= box[2]) & (YY >= box[1]) & (YY <= box[3])
        l = pad_layers(p)[0]; sub = owner[l, j0:j1, i0:i1]; sub[m & (sub == -1)] = NID[p["net"]]
# inner escape strips (M-79): a fan-out via (terminal pad) owns a strip on the inner routing layer that runs in the stub
# direction, outward from the part, so that the via keeps a way out between the next via columns (a +3V3 trunk closed
# the In2 exit of U901 pin 7, and the via column closes In3)
IESC = CFG.get("escape_inner", {"len": 0.0, "w": 0.3})
n_ie = 0
for p in geo["pads"]:
    if not p["net"] or len(pad_layers(p)) != NL or len(cu_layers(p)) == NL: continue      # terminal pads only
    bx = pad_box(p); pcx, pcy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
    dx, dy = p["x"] - pcx, p["y"] - pcy; L = math.hypot(dx, dy)
    if L < 1e-6 or IESC["len"] <= 0: continue
    ux, uy = dx / L, dy / L
    want = "H" if abs(ux) > abs(uy) else "V"
    ls = [k for k in RL if CFG["layers"][k]["dir"] == want and LAY[k] != "F"]
    if not ls: continue
    x2, y2 = p["x"] + ux * IESC["len"], p["y"] + uy * IESC["len"]; r = IESC["w"] / 2
    i0, i1, j0, j1 = window(min(p["x"], x2) - r, min(p["y"], y2) - r, max(p["x"], x2) + r, max(p["y"], y2) + r)
    XX, YY = np.meshgrid(xs[i0:i1], ys[j0:j1]); m = seg_mask(p["x"], p["y"], x2, y2, r)(XX, YY)
    for l in ls:
        sub = owner[l, j0:j1, i0:i1]; sub[m & (sub == -1)] = NID[p["net"]]
    n_ie += 1
# distance (cells) to fixed-net copper per layer, for rf_clear
FIXED_IDS = np.array([NID[n] for n in NETS if is_fixed(n)], dtype=np.int32)
RFD = np.stack([ndimage.distance_transform_edt(~np.isin(owner[l], FIXED_IDS)).astype(np.float32) for l in range(NL)])
FIXPAD = np.zeros((NL, NY, NX), dtype=bool)
for p in geo["pads"]:
    if p["net"] and is_fixed(p["net"]): paint(cu_layers(p), pad_mask(p), pad_box(p), True, arr=FIXPAD)
RFDP = np.stack([ndimage.distance_transform_edt(~FIXPAD[l]).astype(np.float32) for l in range(NL)])
del FIXPAD
RFPC = CFG.get("rf_pad_clear", 0.0)          # local clearance of the fixed-net pads (2.0 mm on the RF board), all layers
RFC = np.array([CFG["rf_clear"].get(n, 0.0) for n in LAY])
# aggressor/victim pairs (M-81): net -> [(ids of the other group, clearance mm)], both directions
PAIR = {}
for pr in CFG.get("pairs", []):
    A_ = [n for n in NETS if any(fnmatch.fnmatchcase(n, p) for p in pr["a"])]
    B_ = [n for n in NETS if any(fnmatch.fnmatchcase(n, p) for p in pr["b"])]
    for n in A_: PAIR.setdefault(n, []).append((np.array([NID[m] for m in B_], dtype=np.int32), pr["clear"]))
    for n in B_: PAIR.setdefault(n, []).append((np.array([NID[m] for m in A_], dtype=np.int32), pr["clear"]))
# return vias (D-156, M-79): a signal via between layers with different reference planes needs a GND via within RET_R mm.
# The search allows such a via only where a GND via fits within RET_R; after the connection is painted, the GND via is
# placed at once (and painted), so later routes keep the room free.
RCFG = CFG.get("return_vias", {})
RET_R = RCFG.get("radius", 0.0)
RET_RL = RCFG.get("radius_logic", RET_R)              # larger radius in the logic regions (Prins 2026-10-24, option A)
RETMAP = np.full((NY, NX), RET_R, dtype=np.float32)
for (a_, b_, c_, d_) in CFG.get("restrict", {}).get("F", {}).get("rects", []):
    RETMAP[cy(b_):cy(d_) + 1, cx(a_):cx(c_) + 1] = RET_RL
REFL = np.array([{"F": 0, "In2": 0, "In3": 1, "B": 1}.get(LAY[k], 0) for k in RL], dtype=np.int64)
REFL = np.array([RCFG.get("ref", {}).get(LAY[k], 0) for k in RL], dtype=np.int64) if RCFG.get("ref") else REFL
GNDID = NID.get("GND", -99)
RETV = []
def gnd_spot_ok(j0, j1, i0, i1):
    """Cells in the window where a GND via (0.6/0.3) fits: other-net copper, RF copper and RF pads keep their clearance
    on every layer, other vias keep 0.9 mm centre to centre, the board edge 0.8 mm."""
    B = int(math.ceil((0.2 + VIA_D / 2 + MARGIN) / G)) + 8
    a0, a1, b0, b1 = max(0, j0 - B), min(NY, j1 + B), max(0, i0 - B), min(NX, i1 + B)
    sl = (slice(j0 - a0, j0 - a0 + (j1 - j0)), slice(i0 - b0, i0 - b0 + (i1 - i0)))
    ok = np.ones((j1 - j0, i1 - i0), dtype=bool)
    for l in range(NL):
        o = owner[l, a0:a1, b0:b1]
        ok &= ndimage.distance_transform_edt(~((o != -1) & (o != GNDID)))[sl] >= (0.2 + VIA_D / 2 + MARGIN) / G
        ok &= (RFD[l, j0:j1, i0:i1] >= (RFC[l] + VIA_D / 2 + MARGIN) / G) & (RFDP[l, j0:j1, i0:i1] >= (RFPC + VIA_D / 2 + MARGIN) / G)
    ok &= ndimage.distance_transform_edt(~VIAC[0, a0:a1, b0:b1])[sl] >= (0.9 - VIA_D / 2) / G
    ok &= ndimage.distance_transform_edt(~HOLES[0, a0:a1, b0:b1])[sl] >= (VIA_DR / 2 + 0.25 + MARGIN) / G
    ok &= ndimage.distance_transform_edt(~PADCU[0, a0:a1, b0:b1])[sl] >= (VIA_D / 2 + 0.2 + MARGIN) / G
    ok &= (owner[0, j0:j1, i0:i1] != HARD)
    return ok
RING = sorted({(dj, di) for dj in range(-25, 26) for di in range(-25, 26) if 0.8 <= math.hypot(dj * G, di * G) <= 2.5},
              key=lambda d: d[0] ** 2 + d[1] ** 2)
def place_return(x, y):
    """Put a GND via as close as possible to (x, y), within RET_R (else up to 2.5 mm); returns the distance or None."""
    jc, ic = cy(y), cx(x); j0, j1, i0, i1 = max(0, jc - 26), min(NY, jc + 27), max(0, ic - 26), min(NX, ic + 27)
    rr = int(RETMAP[jc, ic] / G)
    gj, gi = np.nonzero(VIAC[1, max(0, jc - rr):jc + rr + 1, max(0, ic - rr):ic + rr + 1])
    if len(gj):                                              # an existing GND via within the radius serves this via too
        dmin = float(np.min(np.hypot(gj + max(0, jc - rr) - jc, gi + max(0, ic - rr) - ic))) * G
        if dmin <= RETMAP[jc, ic]: return dmin
    ok = gnd_spot_ok(j0, j1, i0, i1)
    for (dj, di) in RING:
        j, i = jc + dj, ic + di
        if j0 <= j < j1 and i0 <= i < i1 and ok[j - j0, i - i0]:
            v = {"net": "GND", "x": round(X0 + i * G, 4), "y": round(Y0 + j * G, 4), "d": VIA_D, "drill": VIA_DR}
            paint_via(v, GNDID); RETV.append(v); return math.hypot(dj * G, di * G)
    return None
RET_MISS = []
# allowed regions per layer (restrict); the net's own pad breakout is added per net
ALLOW = np.ones((NL, NY, NX), dtype=bool)
REF = collections.defaultdict(list)
for p in geo["pads"]: REF[p["ref"]].append(p)
for ln, rs in CFG.get("restrict", {}).items():
    l = LAY.index(ln); ALLOW[l] = False
    for a, b, c, d in rs.get("rects", []): ALLOW[l] |= (X >= a) & (X <= c) & (Y >= b) & (Y <= d)
    for globs in rs.get("ref_boxes", []):
        ps = [q for ref, qs in REF.items() if any(fnmatch.fnmatchcase(ref, g_) for g_ in globs) for q in qs]
        bx = [pad_box(q) for q in ps]; m = rs.get("box_margin", 0.0)
        a, b, c, d = min(v[0] for v in bx) - m, min(v[1] for v in bx) - m, max(v[2] for v in bx) + m, max(v[3] for v in bx) + m
        ALLOW[l] |= (X >= a) & (X <= c) & (Y >= b) & (Y <= d)
del X, Y
PAD_BRK = {LAY.index(ln): rs.get("pad_breakout", 0.0) for ln, rs in CFG.get("restrict", {}).items()}
# per-net keep-out areas (shack interface p3, D-89): nets not in "except" may not use a cell inside "poly" minus "holes" on
# any routing layer, nor place a via there (keeps interface nets off the RGND islands of the radio ports)
KO = []
_kos = CFG.get("keepout", []) + (json.load(open(CFG["keepout_file"]))["keepout"] if CFG.get("keepout_file") else [])
if _kos:
    _X, _Y = np.meshgrid(xs, ys); _pts = np.c_[_X.ravel(), _Y.ravel()]
    for kr in _kos:
        m_ = Path(kr["poly"]).contains_points(_pts).reshape(_Y.shape)
        for h_ in kr.get("holes", []): m_ &= ~Path(h_).contains_points(_pts).reshape(_Y.shape)
        KO.append((m_, {NID[n] for n in kr["except"] if n in NID}))
    del _X, _Y, _pts

DI = np.array([1, 1, 0, -1, -1, -1, 0, 1], dtype=np.int64)
DJ = np.array([0, 1, 1, 1, 0, -1, -1, -1], dtype=np.int64)

@njit(cache=True)
def astar(free, via_ok, thru, breakout, hfield, start_idx, target, L, H, W, ldir, pref, orth, diag, b45, b90, via, retok, refl):
    """free[l,j,i] over the routing layers, via_ok[j,i], breakout[j,i], target[l,j,i], hfield[j,i] (cells).
    State s = ((l*H + j)*W + i)*10 + d; d 0..7 direction, 8 start, 9 just after a via."""
    N = L * H * W * 10
    g = np.full(N, np.float32(1e30), dtype=np.float32); par = np.full(N, -1, dtype=np.int32)
    heap_s = np.empty(N, dtype=np.int32); heap_f = np.empty(N, dtype=np.float32); pos = np.full(N, -1, dtype=np.int32); n = 0
    closed = np.zeros(N, dtype=np.bool_)
    for s in start_idx:
        g[s] = 0.0
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
        for nd in range(8 + L):
            if nd >= 8:                                    # via to routing layer nd - 8
                nl = nd - 8
                if nl == l or d == 9: continue
                if not thru[j, i]:
                    if not via_ok[j, i]: continue
                    if d < 8 and d % 2 == 1 and not breakout[j, i]: continue
                    if refl[l] != refl[nl] and not retok[j, i]: continue          # no room for a return via
                if not free[nl, j, i]: continue
                ns = ((nl * H + j) * W + i) * 10 + 9; cost = 1.0 if thru[j, i] else via
            else:
                if d < 8:
                    t = abs(nd - d); t = min(t, 8 - t)
                    if t >= 3: continue
                if d == 9 and nd % 2 == 1 and not breakout[j, i]: continue
                ni = i + DI[nd]; nj = j + DJ[nd]
                if ni < 0 or nj < 0 or ni >= W or nj >= H or not free[l, nj, ni]: continue
                if nd % 2 == 1 and not (free[l, j, ni] and free[l, nj, i]): continue
                if nd % 2 == 1: cost = diag
                elif (ldir[l] == 1) == (nd == 2 or nd == 6): cost = pref
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

@njit(cache=True)
def astar_rl(free, via_ok, thru, breakout, hfield, start_idx, target, L, H, W, ldir, pref, orth, diag, b45, b90, via, retok, refl, R, g, par, closed):
    """As astar, with a minimum segment length (M-78): the state also holds k, the steps since the last turn or via
    (capped at R - 1). A turn or a via needs k = R - 1, so every segment between two bends or vias is at least R - 1
    grid steps long. The last segment into a target may be shorter (it ends at a pad or via centre), and so may segments
    in the breakout zone around own pads (pin fields need the freedom; the 1.5 mm zone lies at the pads).
    State s = (((l*H + j)*W + i)*10 + d)*R + k. Lazy heap (no decrease-key). g, par and closed are shared buffers (set to
    1e30, -1, False); every state touched is listed and reset before return, so a call costs only the states it visits."""
    KM = R - 1
    cap = 1 << 20
    tcap = 1 << 20; tl = np.empty(tcap, dtype=np.int64); nt = 0
    hs = np.empty(cap, dtype=np.int64); hf = np.empty(cap, dtype=np.float32); n = 0
    for s0 in start_idx:
        s = s0 * R + KM; g[s] = 0.0
        if nt == tcap:
            tcap *= 2; tl2 = np.empty(tcap, dtype=np.int64); tl2[:nt] = tl[:nt]; tl = tl2
        tl[nt] = s; nt += 1
        if n == cap:
            cap *= 2; hs2 = np.empty(cap, dtype=np.int64); hf2 = np.empty(cap, dtype=np.float32); hs2[:n] = hs[:n]; hf2[:n] = hf[:n]; hs = hs2; hf = hf2
        k_ = n; n += 1; hs[k_] = s; hf[k_] = hfield[(s0 // 10 // W) % H, (s0 // 10) % W]
        while k_ > 0:
            pk = (k_ - 1) // 2
            if hf[pk] <= hf[k_]: break
            hs[pk], hs[k_] = hs[k_], hs[pk]; hf[pk], hf[k_] = hf[k_], hf[pk]; k_ = pk
    while n > 0:
        s = hs[0]; n -= 1
        if n > 0:
            hs[0] = hs[n]; hf[0] = hf[n]; k_ = 0
            while True:
                a = 2 * k_ + 1; b = a + 1; m = k_
                if a < n and hf[a] < hf[m]: m = a
                if b < n and hf[b] < hf[m]: m = b
                if m == k_: break
                hs[m], hs[k_] = hs[k_], hs[m]; hf[m], hf[k_] = hf[k_], hf[m]; k_ = m
        if closed[s]: continue
        closed[s] = True
        kk = s % R; sd = s // R; d = sd % 10; c = sd // 10; i = c % W; j = (c // W) % H; l = c // (W * H)
        if target[l, j, i] and g[s] > 0:
            path = np.empty(0, dtype=np.int64); q = s; m_ = 0
            while q >= 0: m_ += 1; q = par[q]
            path = np.empty(m_, dtype=np.int64); q = s; m_ = 0
            while q >= 0: path[m_] = q; m_ += 1; q = par[q]
            for t_ in range(nt): g[tl[t_]] = np.float32(1e30); par[tl[t_]] = -1; closed[tl[t_]] = False
            return path
        gs = g[s]
        for nd in range(8 + L):
            if nd >= 8:
                nl = nd - 8
                if nl == l or d == 9: continue
                if d < 8 and kk < KM and not breakout[j, i]: continue   # no via right after a bend (free in a pad breakout zone)
                if not thru[j, i]:
                    if not via_ok[j, i]: continue
                    if d < 8 and d % 2 == 1 and not breakout[j, i]: continue
                    if refl[l] != refl[nl] and not retok[j, i]: continue          # no room for a return via
                if not free[nl, j, i]: continue
                ns = (((nl * H + j) * W + i) * 10 + 9) * R; cost = 1.0 if thru[j, i] else via
            else:
                if d < 8:
                    t = abs(nd - d); t = min(t, 8 - t)
                    if t >= 3: continue
                if d == 9 and nd % 2 == 1 and not breakout[j, i]: continue
                ni = i + DI[nd]; nj = j + DJ[nd]
                if ni < 0 or nj < 0 or ni >= W or nj >= H or not free[l, nj, ni]: continue
                if nd % 2 == 1 and not (free[l, j, ni] and free[l, nj, i]): continue
                turn = d < 8 and nd != d
                if turn and kk < KM and not target[l, nj, ni] and not breakout[j, i]: continue     # segment too short for a bend
                if nd % 2 == 1: cost = diag
                elif (ldir[l] == 1) == (nd == 2 or nd == 6): cost = pref
                else: cost = orth
                if turn:
                    t = abs(nd - d); t = min(t, 8 - t); cost += b45 if t == 1 else b90
                nk = 1 if (turn or d >= 8) else min(kk + 1, KM)
                ns = (((l * H + nj) * W + ni) * 10 + nd) * R + nk
            ng = gs + cost
            if ng < g[ns] and not closed[ns]:
                if g[ns] > np.float32(1e29):
                    if nt == tcap:
                        tcap *= 2; tl2 = np.empty(tcap, dtype=np.int64); tl2[:nt] = tl[:nt]; tl = tl2
                    tl[nt] = ns; nt += 1
                g[ns] = ng; par[ns] = s
                if n == cap:
                    cap *= 2; hs2 = np.empty(cap, dtype=np.int64); hf2 = np.empty(cap, dtype=np.float32); hs2[:n] = hs[:n]; hf2[:n] = hf[:n]; hs = hs2; hf = hf2
                k_ = n; n += 1; hs[k_] = ns; hf[k_] = ng + hfield[(ns // R // 10 // W) % H, (ns // R // 10) % W]
                while k_ > 0:
                    pk = (k_ - 1) // 2
                    if hf[pk] <= hf[k_]: break
                    hs[pk], hs[k_] = hs[k_], hs[pk]; hf[pk], hf[k_] = hf[k_], hf[pk]; k_ = pk
    for t_ in range(nt): g[tl[t_]] = np.float32(1e30); par[tl[t_]] = -1; closed[tl[t_]] = False
    return np.empty(0, dtype=np.int64)

def masks(nid, w, clr, j0, j1, i0, i1, own_allow, centres=(), ownpad=None, corr=None, pair=()):
    """free (routing layers) and via_ok in the window; distance fields over the window plus a border.
    Own copper is free only where the whole track width stays inside it ('deep'), and at the own pad centres: a track
    drawn on the grid over an off-grid own stub could otherwise come closer than the clearance to the next net.
    Own pads repel like another net (Prins, 2026-10-24: a track must not graze a pad of its own net), except inside the pad
    and in four straight entry corridors from the pad centre (D-158: a track enters a pad straight)."""
    B = int(math.ceil((max([clr] + [c_ for _, c_ in pair]) + max(w, VIA_D) / 2 + MARGIN) / G)) + 2
    a0, a1, b0, b1 = max(0, j0 - B), min(NY, j1 + B), max(0, i0 - B), min(NX, i1 + B)
    sl = (slice(j0 - a0, j0 - a0 + (j1 - j0)), slice(i0 - b0, i0 - b0 + (i1 - i0)))
    dist = []
    for l in range(NL):
        o = owner[l, a0:a1, b0:b1]
        dist.append(ndimage.distance_transform_edt(~((o != -1) & (o != nid)))[sl])
    r_tr = (clr + w / 2 + MARGIN) / G; r_via = (clr + VIA_D / 2 + MARGIN) / G
    rfd = RFD[:, j0:j1, i0:i1]; rfdp = RFDP[:, j0:j1, i0:i1]
    fr = []
    for k, l in enumerate(RL):
        own = owner[l, j0:j1, i0:i1] == nid
        deep = ndimage.distance_transform_edt(owner[l, a0:a1, b0:b1] == nid)[sl] >= (w / 2 + MARGIN) / G
        ctr = np.zeros_like(own)
        for (j, i) in centres:
            if j0 <= j < j1 and i0 <= i < i1: ctr[j - j0, i - i0] = True
        ok = (dist[l] >= r_tr) & (rfd[l] >= (RFC[l] + w / 2 + MARGIN) / G) & (rfdp[l] >= (RFPC + w / 2 + MARGIN) / G) & (ALLOW[l, j0:j1, i0:i1] | own_allow[l])
        if ownpad is not None:
            ok &= (ndimage.distance_transform_edt(~ownpad[l]) >= r_tr) | corr[l]
        for m_, al_ in KO:
            if nid not in al_: ok &= ~m_[j0:j1, i0:i1]
        for ids_, c_ in pair:                                 # aggressor/victim pairs keep a larger gap (M-81)
            o = owner[l, a0:a1, b0:b1]
            ok &= ndimage.distance_transform_edt(~np.isin(o, ids_))[sl] >= (c_ + w / 2 + MARGIN) / G
        if ownpad is not None:
            # inside own pad copper (M-83): a cell is free when the track disc stays clear of the zone where track copper
            # would come closer than the clearance to another net (own copper itself is not in that zone). Without this a
            # pad narrower than w + 2 x MARGIN (VSSOP 0.35 mm at 0.5 mm pitch) has no free cell next to its centre.
            zone = ~own & (dist[l] < (clr + MARGIN) / G)
            ok_in = ownpad[l] & (ndimage.distance_transform_edt(~zone) >= (w / 2) / G)
            fr.append(ok | (own & (deep | ctr)) | ok_in)
        else:
            fr.append(ok | (own & (deep | ctr)))
    vo = np.ones((j1 - j0, i1 - i0), dtype=bool)
    for l in range(NL): vo &= (dist[l] >= r_via) & (rfd[l] >= (RFC[l] + VIA_D / 2 + MARGIN) / G) & (rfdp[l] >= (RFPC + VIA_D / 2 + MARGIN) / G)
    for m_, al_ in KO:
        if nid not in al_: vo &= ~m_[j0:j1, i0:i1]
    return np.ascontiguousarray(np.stack(fr)), vo

def mst_edges(pads):
    """Prim over the pad centres: the connections of one net, as pad index pairs with their length (mm)."""
    n = len(pads); inn = [0]; out = []
    best = {k: (math.hypot(pads[k]["x"] - pads[0]["x"], pads[k]["y"] - pads[0]["y"]), 0) for k in range(1, n)}
    while best:
        k = min(best, key=lambda q: best[q][0]); d, a = best.pop(k); out.append((a, k, d)); inn.append(k)
        for q in best:
            dq = math.hypot(pads[q]["x"] - pads[k]["x"], pads[q]["y"] - pads[k]["y"])
            if dq < best[q][0]: best[q] = (dq, k)
    return out

class NetState:
    """Routing state of one net: pad components (union-find), the cells of each component, its width, tracks and vias."""
    def __init__(self, net):
        self.net = net; self.nid = NID[net]; self.pads = PADS[net]; cls, self.w, self.clr = netclass(net)
        self.centre = [(cy(p["y"]), cx(p["x"])) for p in self.pads]
        self.parent = list(range(len(self.pads)))
        self.cells = {k: {(q, self.centre[k][0], self.centre[k][1]) for q in pad_rl(p)} for k, p in enumerate(self.pads)}
        self.tracks, self.vias = [], []
        self.smd = [p for p in self.pads if len(cu_layers(p)) == 1]
        # own fixed copper (fan-out stubs, D-154) joins the component of the pad it touches
        for k, p in enumerate(self.pads):
            if not CFG.get("join_fixed", True): break
            for q in pad_rl(p):
                l = RL[q]; jc, ic = self.centre[k]
                j0_, j1_, i0_, i1_ = max(0, jc - 100), min(NY, jc + 101), max(0, ic - 100), min(NX, ic + 101)
                lab, _ = ndimage.label(OWNER_FIX[l, j0_:j1_, i0_:i1_] == self.nid); k0 = lab[jc - j0_, ic - i0_]
                if not k0: continue
                pc = np.zeros((j1_ - j0_, i1_ - i0_), dtype=bool)
                Xs, Ys = np.meshgrid(xs[i0_:i1_], ys[j0_:j1_])
                for pp in self.pads:
                    if l in cu_layers(pp): pc |= pad_mask(pp)(Xs, Ys)
                self.cells[k] |= {(q, j + j0_, i + i0_) for j, i in zip(*np.nonzero((lab == k0) & ~pc))}
    def local(self, j0, j1, i0, i1):
        """own SMD pad cells (no via there), own breakout allowance per restricted layer, and the via breakout zone, in a window."""
        Xs, Ys = np.meshgrid(xs[i0:i1], ys[j0:j1])
        smd = np.zeros((j1 - j0, i1 - i0), dtype=bool); allow = {l: np.zeros_like(smd) for l in range(NL)}
        for p in self.smd:
            bx = pad_box(p)
            if bx[2] < xs[i0] - 3 or bx[0] > xs[i1 - 1] + 3 or bx[3] < ys[j0] - 3 or bx[1] > ys[j1 - 1] + 3: continue
            smd |= pad_mask(p)(Xs, Ys)
            l = cu_layers(p)[0]
            if l in PAD_BRK:
                r = PAD_BRK[l]; allow[l] |= (Xs >= bx[0] - r) & (Xs <= bx[2] + r) & (Ys >= bx[1] - r) & (Ys <= bx[3] + r)
        brk = np.zeros_like(smd); rb = int(BREAKOUT / G)
        for (j, i) in self.centre:
            brk[max(0, j - rb - j0):max(0, j + rb + 1 - j0), max(0, i - rb - i0):max(0, i + rb + 1 - i0)] = True
        # own pad copper per layer, and four straight entry corridors (half width 0.3 mm) from each pad centre
        ownpad = {l: np.zeros_like(smd) for l in range(NL)}; corr = {l: np.zeros_like(smd) for l in range(NL)}
        for p in self.pads:
            bx = pad_box(p)
            if bx[2] < xs[i0] - 3 or bx[0] > xs[i1 - 1] + 3 or bx[3] < ys[j0] - 3 or bx[1] > ys[j1 - 1] + 3: continue
            m = pad_mask(p)(Xs, Ys); ls = cu_layers(p)
            for l in ls: ownpad[l] |= m
            if not (bx[0] <= p["x"] <= bx[2] and bx[1] <= p["y"] <= bx[3]): continue      # terminal: the router ends on its via
            L = max(bx[2] - bx[0], bx[3] - bx[1]) / 2 + self.clr + self.w / 2 + MARGIN + 0.3   # past the repel zone of a wide track too (M-83)
            c = ((np.abs(Xs - p["x"]) <= 0.3) & (np.abs(Ys - p["y"]) <= L)) | ((np.abs(Ys - p["y"]) <= 0.3) & (np.abs(Xs - p["x"]) <= L))
            for l in ls: corr[l] |= c
        return smd, allow, brk, ownpad, corr
    def find(self, k):
        while self.parent[k] != k: self.parent[k] = self.parent[self.parent[k]]; k = self.parent[k]
        return k
    def union(self, a, b):
        ra, rb_ = self.find(a), self.find(b)
        if ra != rb_: self.parent[rb_] = ra; self.cells[ra] |= self.cells.pop(rb_)
        return ra

def route_edge(S, a, b):
    """Connect the component of pad a to the component of pad b. Returns True on success (copper painted at once)."""
    ra, rb_ = S.find(a), S.find(b)
    if ra == rb_: return True
    A = np.array(sorted(S.cells[ra])); B_ = np.array(sorted(S.cells[rb_]))
    # nearest cell pair between the two components (on a sample of B for speed)
    Bs = B_[:: max(1, len(B_) // 400)]
    d2 = (A[:, None, 1] - Bs[None, :, 1]) ** 2 + (A[:, None, 2] - Bs[None, :, 2]) ** 2 if len(A) * len(Bs) < 4e6 else None
    if d2 is None: pa, pb = A[0], Bs[0]
    else: ia, ib = np.unravel_index(np.argmin(d2), d2.shape); pa, pb = A[ia], Bs[ib]
    w = S.w; s_end = -1
    for wstep in CFG["window_steps"]:
        PW = int(wstep / G)
        j0 = max(0, min(pa[1], pb[1]) - PW); j1 = min(NY, max(pa[1], pb[1]) + PW + 1)
        i0 = max(0, min(pa[2], pb[2]) - PW); i1 = min(NX, max(pa[2], pb[2]) + PW + 1)
        H, Wd = j1 - j0, i1 - i0
        if len(RL) * H * Wd * 10 > CFG["max_states"]: break
        smd, allow, brk, ownpad, corr = S.local(j0, j1, i0, i1)
        while True:
            free, via_ok = masks(S.nid, w, S.clr, j0, j1, i0, i1, allow, S.centre, ownpad, corr, PAIR.get(S.net, ()))
            via_ok &= ~smd
            via_ok &= ndimage.distance_transform_edt(~HOLES[0, j0:j1, i0:i1]) >= (VIA_DR / 2 + 0.25 + MARGIN) / G   # drill to drill
            thru = np.ones((H, Wd), dtype=bool)
            for l in range(NL): thru &= owner[l, j0:j1, i0:i1] == S.nid
            via_ok &= ndimage.distance_transform_edt(~thru) >= (VIA_D / 2 + 0.2 + MARGIN) / G      # hole to hole
            # a free layer change only at the centre of own through copper (THT or terminal pad, own via), so that the
            # tracks on both layers end at that centre (a change at the rim left a track end on the pad edge, M-77)
            tc = np.zeros_like(thru)
            for k_, p_ in enumerate(S.pads):
                jp, ip = S.centre[k_]
                if len(pad_rl(p_)) == len(RL) and j0 <= jp < j1 and i0 <= ip < i1: tc[jp - j0, ip - i0] = True
            for v_ in S.vias:
                jv, iv = cy(v_["y"]), cx(v_["x"])
                if j0 <= jv < j1 and i0 <= iv < i1: tc[jv - j0, iv - i0] = True
            tc &= thru
            if RET_R > 0:
                retok = ndimage.distance_transform_edt(~(gnd_spot_ok(j0, j1, i0, i1) | VIAC[1, j0:j1, i0:i1])) <= RETMAP[j0:j1, i0:i1] / G   # a GND via fits, or one is there
            else:
                retok = np.ones((H, Wd), dtype=bool)
            target = np.zeros((len(RL), H, Wd), dtype=bool); tmask = np.ones((H, Wd), dtype=bool)
            for (q, j, i) in S.cells[rb_]:
                if j0 <= j < j1 and i0 <= i < i1 and free[q, j - j0, i - i0]: target[q, j - j0, i - i0] = True; tmask[j - j0, i - i0] = False
            hfield = ndimage.distance_transform_edt(tmask).astype(np.float64)
            starts = np.array([((q * H + (j - j0)) * Wd + (i - i0)) * 10 + 8 for (q, j, i) in S.cells[ra]
                               if j0 <= j < j1 and i0 <= i < i1 and free[q, j - j0, i - i0]], dtype=np.int64)
            s_end = -1; RR = 1
            if len(starts) and target.any():
                args = (free, np.ascontiguousarray(via_ok), np.ascontiguousarray(tc), np.ascontiguousarray(brk), hfield, starts,
                        target, len(RL), H, Wd, LDIR, PREF, ORTH, DIAG, BEND45, BEND90, VIA, np.ascontiguousarray(retok), REFL)
                if SEG_MIN > 1 and wstep == CFG["window_steps"][0] and len(RL) * H * Wd * 10 * (SEG_MIN + 1) <= RL_N:   # first window only
                    a2 = list(args); a2[4] = hfield * HW                 # weighted A* (HW >= 1): fewer states, path cost at most HW x optimal
                    pth = astar_rl(*a2, SEG_MIN + 1, RL_G, RL_P, RL_C); RR = SEG_MIN + 1
                    if len(pth): s_end = int(pth[0]); par = None
                    else: NO_MIN.add(S.net)
                if s_end < 0:                                        # too large, or no path with the minimum length
                    s_end, par = astar(*args); RR = 1
            if s_end >= 0 or w <= W_NARROW or any(fnmatch.fnmatchcase(S.net, p_) for p_ in CFG.get("no_narrow", [])): break   # coil supply keeps its width
            w = max(W_NARROW, round(w / 2, 3)); NARROWED.setdefault(S.net, []).append(w)
        if s_end >= 0: break
    else:
        return False
    if s_end < 0: return False
    path = []
    if par is None:                                          # astar_rl returned the state list itself (end first)
        for s in pth:
            c = int(s) // RR // 10; path.append((c // (Wd * H), (c // Wd) % H + j0, c % Wd + i0))
    else:
        s = s_end
        while s >= 0:
            c = s // RR // 10; path.append((c // (Wd * H), (c // Wd) % H + j0, c % Wd + i0)); s = par[s]
    path.reverse()
    pts_xy = lambda c: (X0 + c[2] * G, Y0 + c[1] * G)
    exact = {S.centre[k]: (p["x"], p["y"]) for k, p in enumerate(S.pads)}
    tr, vi, need_ret = [], [], []
    def emit(p1, p2, q):
        if p1 != p2: tr.append({"net": S.net, "layer": RNAME[q], "w": w, "x1": round(p1[0], 4), "y1": round(p1[1], 4),
                                "x2": round(p2[0], 4), "y2": round(p2[1], 4)})
    start_c = path[0]; prev = path[0]; prev_d = None; seg_a = pts_xy(start_c)
    emit(exact.get((start_c[1], start_c[2]), seg_a), seg_a, start_c[0])
    for c in path[1:]:
        if c[0] != prev[0]:
            pc = exact.get((c[1], c[2]), pts_xy(c))                    # exact centre of a pad or terminal via
            emit(seg_a, pc, prev[0])
            if not tc[c[1] - j0, c[2] - i0]:
                vi.append({"net": S.net, "x": round(pts_xy(c)[0], 4), "y": round(pts_xy(c)[1], 4), "d": VIA_D, "drill": VIA_DR})
                if REFL[prev[0]] != REFL[c[0]]: need_ret.append(vi[-1])
            seg_a = pc; prev_d = None
        else:
            dd = (c[1] - prev[1], c[2] - prev[2])
            if prev_d is not None and dd != prev_d: emit(seg_a, pts_xy(prev), prev[0]); seg_a = pts_xy(prev)
            prev_d = dd
        prev = c
    emit(seg_a, pts_xy(prev), prev[0]); emit(pts_xy(prev), exact.get((prev[1], prev[2]), pts_xy(prev)), prev[0])
    for t in tr: paint_track(t, S.nid)
    for v in vi: paint_via(v, S.nid)
    if RET_R > 0:
        for v in need_ret:
            d_ = place_return(v["x"], v["y"])
            if d_ is None or d_ > RETMAP[cy(v["y"]), cx(v["x"])]: RET_MISS.append((S.net.split("/")[-1], v["x"], v["y"], d_))
    S.tracks += tr; S.vias += vi
    r = S.union(ra, rb_); S.cells[r] |= set(path)
    return True

route_nets = [n for n in PADS if netclass(n)[0] != "GND" and not is_fixed(n) and len(PADS[n]) > 1 and not n.startswith("unconnected")]
OWNER_FIX = owner.copy()
OWNER0 = owner.copy(); VIAC0 = VIAC.copy()
EDGES = {n: mst_edges(PADS[n]) for n in route_nets}
def run(first):
    """One pass: all connections of all nets, shortest first; the connections of the nets in 'first' (failed before) go first."""
    owner[:] = OWNER0; VIAC[:] = VIAC0; RETV.clear(); RET_MISS.clear()
    states = {n: NetState(n) for n in route_nets}
    # connections that leave a fan-out via (terminal pad) go before the others: they need the escape room at the IC (M-79)
    term = lambda n, k: len(pad_layers(PADS[n][k])) == NL and len(cu_layers(PADS[n][k])) < NL
    ed = sorted(((n not in first, first.index(n) if n in first else 0, not (term(n, a) or term(n, b)), d, n, a, b)
                 for n in route_nets for (a, b, d) in EDGES[n]))
    for (_, _, _, d, n, a, b) in ed:
        S = states[n]
        if not route_edge(S, a, b):
            # second try: the far pad to any copper of the near component, from the other side
            if not route_edge(S, b, a): pass
    res_ = {"tracks": [], "vias": list(RETV), "failed": [], "order": first, "return_miss": list(RET_MISS)}
    for n, S in states.items():
        res_["tracks"] += S.tracks; res_["vias"] += S.vias
        comps = {S.find(k) for k in range(len(S.pads))}
        if len(comps) > 1:
            big = max(comps, key=lambda r: sum(1 for k in range(len(S.pads)) if S.find(k) == r))
            res_["failed"].append({"net": n, "pads_left": [S.pads[k]["ref"] + "." + S.pads[k]["num"] for k in range(len(S.pads)) if S.find(k) != big]})
    return res_
t_start = time.time(); first = []; result = None
print("nets to route", len(route_nets), "connections", sum(len(v) for v in EDGES.values()), "grid", NX, "x", NY, flush=True)
for it in range(CFG["passes"]):
    r = run(first)
    print("  return vias placed %d, beyond %.1f mm or none: %d" % (len(r["vias"]) and sum(1 for v in r["vias"] if v["net"] == "GND"), RET_R, len(r["return_miss"])), flush=True)
    print("pass %d: failed %d %s | vias %d | %.0f s" % (it + 1, len(r["failed"]), [f["net"].split("/")[-1] for f in r["failed"]],
          len(r["vias"]), time.time() - t_start), flush=True)
    if result is None or len(r["failed"]) < len(result["failed"]): result = r
    json.dump(r, open("routes_pass%d.json" % (it + 1), "w"))
    if not r["failed"]: break
    first = [f["net"] for f in r["failed"]] + [n for n in first if n not in [f["net"] for f in r["failed"]]]

# merge away interior segments shorter than 0.05 mm
def KQ(v):                                          # 0.001 mm key, stable for values like x.xxx5 (M-78)
    return int(math.floor(v * 1000 + 0.5 + 1e-6))
def drop_short(res, lmin=0.05):
    fixed_pts = {(KQ(v["x"]), KQ(v["y"])) for v in res["vias"]} | {(KQ(p["x"]), KQ(p["y"])) for p in geo["pads"]}
    keep, n = [], 0
    for t in res["tracks"]:
        a, b = (KQ(t["x1"]), KQ(t["y1"])), (KQ(t["x2"]), KQ(t["y2"]))
        # a short stub at a pad or via centre stays: the pad copper covers it, and merging it would tilt the long segment
        if math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) >= lmin or a in fixed_pts or b in fixed_pts: keep.append(t); continue
        n += 1                       # an interior short segment: its end 2 moves onto end 1
        (fx, fy), free_end = (t["x1"], t["y1"]), b
        for u in res["tracks"]:
            if u is t or u["net"] != t["net"] or u["layer"] != t["layer"]: continue
            for e in ("1", "2"):
                if (KQ(u["x" + e]), KQ(u["y" + e])) == free_end: u["x" + e], u["y" + e] = fx, fy
    res["tracks"] = keep
    return n

def piece_ok(net, layer, x1, y1, x2, y2, w):
    """Clearance check of a chamfer or fillet piece against the painted copper of other nets and the RF copper (the router
    checked only its own grid tracks; a chamfer piece came 0.156 mm to a J14 pad, M-77)."""
    l = LAY.index(layer); nid = NID[net]; clr = netclass(net)[2]
    r = clr + w / 2 + 0.08; rc = int(math.ceil(r / G)) + 1
    n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.05) + 1)
    for k in range(n + 1):
        x, y = x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n
        jc, ic = cy(y), cx(x)
        j0, j1, i0, i1 = max(0, jc - rc), min(NY, jc + rc + 1), max(0, ic - rc), min(NX, ic + rc + 1)
        Xs, Ys = np.meshgrid(xs[i0:i1], ys[j0:j1]); o = owner[l, j0:j1, i0:i1]
        if np.any(((Xs - x) ** 2 + (Ys - y) ** 2 <= r * r) & (o != -1) & (o != nid)): return False
        if RFD[l, jc, ic] * G < RFC[l] + w / 2 + 0.05 or RFDP[l, jc, ic] * G < RFPC + w / 2 + 0.05: return False
    return True

CH_LEG = 0.5
def chamfer_result(res):
    keep = {(v["net"], KQ(v["x"]), KQ(v["y"])) for v in res["vias"]} | {(p["net"], KQ(p["x"]), KQ(p["y"])) for p in geo["pads"]}
    ends = collections.defaultdict(list)
    for t in res["tracks"]:
        for e in ("1", "2"): ends[(t["net"], t["layer"], KQ(t["x" + e]), KQ(t["y" + e]))].append((t, e))
    n = 0
    PTS = collections.defaultdict(list)                       # all track ends per net and layer (a T may rest on a leg)
    for (nn_, ln_, xk, yk) in ends: PTS[(nn_, ln_)].append((xk / 1000, yk / 1000))
    for (nn, ln, x, y), v in ends.items():
        if len(v) != 2 or (nn, x, y) in keep: continue
        x, y = x / 1000, y / 1000
        (ta, ea), (tb, eb) = v
        oa, ob = ("2" if ea == "1" else "1"), ("2" if eb == "1" else "1")
        ax, ay = ta["x" + oa] - x, ta["y" + oa] - y; bx, by = tb["x" + ob] - x, tb["y" + ob] - y
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la < 0.1 or lb < 0.1 or abs((ax * bx + ay * by) / la / lb) > 0.02: continue     # a stub under a pad needs no chamfer
        dmax = CH_LEG                                         # stay short of a branch that ends on a leg (M-78: A1_BIAS)
        for (px_, py_) in PTS[(nn, ln)]:
            for (ux_, uy_, l_) in ((ax / la, ay / la, la), (bx / lb, by / lb, lb)):
                pr = (px_ - x) * ux_ + (py_ - y) * uy_
                if 1e-3 < pr < l_ - 1e-3 and abs((px_ - x) * uy_ - (py_ - y) * ux_) < 1e-3: dmax = min(dmax, pr - 0.15)
        if dmax < 0.2: continue                                   # corner stays (counted)
        for d in sorted({min(dmax, CH_LEG, 0.45 * la, 0.45 * lb), min(dmax, 0.3, 0.45 * la, 0.45 * lb), min(0.2, 0.45 * la, 0.45 * lb)}, reverse=True):
            pa = (round(x + ax / la * d, 4), round(y + ay / la * d, 4)); pb = (round(x + bx / lb * d, 4), round(y + by / lb * d, 4))
            if piece_ok(nn, ln, pa[0], pa[1], pb[0], pb[1], min(ta["w"], tb["w"])): break          # smaller leg when the full one hits
        else:
            continue                                                                              # corner stays (counted)
        ta["x" + ea], ta["y" + ea] = pa; tb["x" + eb], tb["y" + eb] = pb
        res["tracks"].append({"net": nn, "layer": ln, "w": min(ta["w"], tb["w"]), "x1": pa[0], "y1": pa[1], "x2": pb[0], "y2": pb[1]})
        n += 1
    return n
CH_T, T_MAXW = 0.5, 0.6
def chamfer_tees(res):
    keep = {(v["net"], KQ(v["x"]), KQ(v["y"])) for v in res["vias"]} | {(p["net"], KQ(p["x"]), KQ(p["y"])) for p in geo["pads"]}
    add = []
    trs = res["tracks"]
    for A in trs:
        if A["w"] >= T_MAXW: continue
        for e, o in (("1", "2"), ("2", "1")):
            ex, ey = A["x" + e], A["y" + e]
            if (A["net"], KQ(ex), KQ(ey)) in keep: continue
            la = math.hypot(A["x" + o] - ex, A["y" + o] - ey)
            if la < 1e-6: continue
            ux, uy = (A["x" + o] - ex) / la, (A["y" + o] - ey) / la
            for B in trs:
                if B is A or B["net"] != A["net"] or B["layer"] != A["layer"]: continue
                bx, by = B["x2"] - B["x1"], B["y2"] - B["y1"]; lb = math.hypot(bx, by)
                if lb < 1e-6: continue
                vx, vy = bx / lb, by / lb
                t = (ex - B["x1"]) * vx + (ey - B["y1"]) * vy
                if t <= 1e-3 or t >= lb - 1e-3 or abs((ex - B["x1"]) * vy - (ey - B["y1"]) * vx) > 1e-3: continue
                if abs(ux * vx + uy * vy) > 0.02: continue
                d = min(CH_T, 0.45 * la, 0.45 * t, 0.45 * (lb - t))
                if d < 0.2: break                                  # too short for a fillet (KiCad: dangling)
                px, py = round(ex + ux * d, 4), round(ey + uy * d, 4)
                if not all(piece_ok(A["net"], A["layer"], px, py, ex + sg * vx * d, ey + sg * vy * d, A["w"]) for sg in (1, -1)): break
                for sg in (1, -1):
                    add.append({"net": A["net"], "layer": A["layer"], "w": A["w"], "x1": px, "y1": py,
                                "x2": round(ex + sg * vx * d, 4), "y2": round(ey + sg * vy * d, 4)})
                break
    ends = collections.defaultdict(list)
    for T_ in trs:
        for e, o in (("1", "2"), ("2", "1")):
            ex, ey = T_["x" + e], T_["y" + e]; l = math.hypot(T_["x" + o] - ex, T_["y" + o] - ey)
            if l > 1e-6: ends[(T_["net"], T_["layer"], KQ(ex), KQ(ey))].append(((T_["x" + o] - ex) / l, (T_["y" + o] - ey) / l, l, T_["w"]))
    for (nn, ln, ex, ey), v in ends.items():
        if len(v) != 3 or (nn, ex, ey) in keep: continue
        ex, ey = ex / 1000, ey / 1000
        for i in range(3):
            br, m = v[i], [v[j] for j in range(3) if j != i]
            if br[3] >= T_MAXW or abs(m[0][0] + m[1][0]) > 0.02 or abs(m[0][1] + m[1][1]) > 0.02: continue
            if abs(br[0] * m[0][0] + br[1] * m[0][1]) > 0.02: continue
            d = min(CH_T, 0.45 * br[2], 0.45 * m[0][2], 0.45 * m[1][2])
            if d < 0.2: break
            px, py = round(ex + br[0] * d, 4), round(ey + br[1] * d, 4)
            if not all(piece_ok(nn, ln, px, py, ex + mm_[0] * d, ey + mm_[1] * d, br[3]) for mm_ in m): break
            for mm_ in m:
                add.append({"net": nn, "layer": ln, "w": br[3], "x1": px, "y1": py, "x2": round(ex + mm_[0] * d, 4), "y2": round(ey + mm_[1] * d, 4)})
            break
    trs += add
    # split every segment at a fillet end that lies on its interior, so that each fillet end meets segment ends
    # (KiCad reported fillets that end on the middle of a track as dangling, M-78)
    addids = {id(P) for P in add}
    for P in add:
        for (qx, qy) in ((P["x1"], P["y1"]), (P["x2"], P["y2"])):
            for T_ in list(trs):
                if id(T_) in addids or T_["net"] != P["net"] or T_["layer"] != P["layer"]: continue
                dx, dy = T_["x2"] - T_["x1"], T_["y2"] - T_["y1"]; L_ = math.hypot(dx, dy)
                if L_ < 1e-6: continue
                pr = ((qx - T_["x1"]) * dx + (qy - T_["y1"]) * dy) / L_
                if 1e-3 < pr < L_ - 1e-3 and abs((qx - T_["x1"]) * dy - (qy - T_["y1"]) * dx) / L_ < 1e-3:
                    trs.append(dict(T_, x1=qx, y1=qy)); T_["x2"], T_["y2"] = qx, qy; break
    return len(add) // 2
owner[:] = OWNER0                                  # paint the kept result again (the last pass may not be the kept one)
for t in result["tracks"]: paint_track(t, NID[t["net"]])
for v in result["vias"]: paint_via(v, NID[v["net"]])
print("short segments merged:", drop_short(result))
print("chamfered corners:", chamfer_result(result), "T-junction fillets:", chamfer_tees(result), "(pieces that fail the clearance check are left out)")
json.dump(result, open(CFG["out"], "w"), indent=0)
print("narrowed:", {n.split("/")[-1]: w for n, w in NARROWED.items()})
print("connections without the minimum segment length (nets):", sorted(n.split("/")[-1] for n in NO_MIN))
Ls = {ln: sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) for t in result["tracks"] if t["layer"] == ln) for ln in RNAME}
print("nets %d routed %d failed %d | %s | vias %d | %.0f s" % (len(route_nets), len(route_nets) - len(result["failed"]),
      len(result["failed"]), " ".join("%s %.0f mm" % kv for kv in Ls.items()), len(result["vias"]), time.time() - t_start))
