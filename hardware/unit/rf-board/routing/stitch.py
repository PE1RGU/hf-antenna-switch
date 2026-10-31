#!/usr/bin/env python3
"""GND stitching for the RF board (p2d, D-119 items 2 and 3, D-156, M-79). Plain Python 3 (numpy, scipy, numba, matplotlib).
Reads router_cfg.json, geom.json (board without routes) and routes.json; writes stitch.json {"vias": [{x, y}]}, which
gen_rfboard_pcb.py adds as GND vias (0.6/0.3 mm, through all layers). Three kinds, in this order of priority:
  1. return vias: one GND via next to every signal via whose tracks change the reference plane (F.Cu and In2 refer to L2,
     In3 and B.Cu to L5; D-156), as close as the clearances allow (0.8 to 2.0 mm from the via centre);
  2. edge fence: along the board outline, 1.5 mm inside the edge, pitch 2.54 mm (D-119 item 3);
  3. grid: a GND via on a 5 mm grid wherever the pours have room (D-119 item 2), moved up to 1 mm to find room.
A place is valid when, on every copper layer of the model, other-net copper keeps the via clearance (0.2 mm + margin),
RF copper keeps rf_clear (2.0 mm outer, 0.5 mm inner) and RF pads rf_pad_clear, the board edge keeps 0.8 mm, and the
GND vias keep 0.9 mm centre to centre (hole to hole above 0.5 mm)."""
import json, math, sys
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

sys.argv = [sys.argv[0], sys.argv[1] if len(sys.argv) > 1 else "router_cfg.json"]
src = open("grid_router.py").read()
exec(src[:src.index("route_nets = [n for n in PADS")].replace("@njit(cache=True)", "@njit"))         # model, painting and distance fields of the router

R_V, CLR, MRG, GAP_GV = VIA_D / 2, 0.2, 0.1, 0.9
RMAX = float(CFG.get("return_vias", {}).get("max", 3.0))
DIST = []
rj = json.load(open(CFG["out"]))
for t in rj["tracks"]: paint_track(t, NID[t["net"]])
for v in rj["vias"]: paint_via(v, NID[v["net"]])
GND = NID["GND"]
foreign = [ndimage.distance_transform_edt(~((owner[l] != -1) & (owner[l] != GND))) for l in range(NL)]
ok = np.ones((NY, NX), dtype=bool)
for l in range(NL):
    ok &= foreign[l] >= (CLR + R_V + MRG) / G
    ok &= RFD[l] >= (RFC[l] + R_V + MRG) / G
    ok &= RFDP[l] >= (RFPC + R_V + MRG) / G
ok &= ndimage.distance_transform_edt(~HOLES[0]) >= (VIA_DR / 2 + 0.25 + MRG) / G            # drill to drill
ok &= ndimage.distance_transform_edt(~PADCU[0]) >= (R_V + CLR + MRG) / G                     # off all pads (GND pads too)
ok &= ndimage.distance_transform_edt(~VIAC[0]) >= (GAP_GV - R_V) / G                         # all vias, any net
Xg, Yg = np.meshgrid(xs, ys)
ok &= (Xg > X0 + 0.8) & (Xg < X1 - 0.8) & (Yg > Y0 + 0.8) & (Yg < Y1 - 0.8)
for (cx_, cy_) in ((5, 5), (X1 - 5, 5), (5, Y1 - 5), (X1 - 5, Y1 - 5)):                # 5 mm corner radius (D-113)
    corner = ((Xg < 5) | (Xg > X1 - 5)) & ((Yg < 5) | (Yg > Y1 - 5))
    ok &= ~(corner & (np.hypot(Xg - cx_, Yg - cy_) > 5 - 0.8) & (np.abs(Xg - cx_) < 5.01) & (np.abs(Yg - cy_) < 5.01))
ok &= ~GNDKO                                                                             # support keep-outs (D-189)
gv = [(v["x"], v["y"]) for v in geo["vias"] + rj["vias"] if v["net"] == "GND"]          # fixed GND vias and the return vias of the router
new = []
def free_at(j, i):
    if not (0 <= j < NY and 0 <= i < NX) or not ok[j, i]: return False
    x, y = xs[i], ys[j]
    return all(math.hypot(x - a, y - b) >= GAP_GV for (a, b) in near_pts(x, y))
tree = [cKDTree(np.array(gv))]
def near_pts(x, y):
    out = [gv[k] for k in tree[0].query_ball_point((x, y), GAP_GV)]
    return out + [p for p in new if abs(p[0] - x) < GAP_GV and abs(p[1] - y) < GAP_GV]
def put(x, y): new.append((round(x, 3), round(y, 3)))

# 1. return vias at signal vias that change the reference plane
REF = {"F": "L2", "In2": "L2", "In3": "L5", "B": "L5"}
ends = {}
for t in rj["tracks"] + geo["tracks"]:
    for e in ("1", "2"): ends.setdefault((t["net"], round(t["x" + e], 2), round(t["y" + e], 2)), set()).add(t["layer"])
sig = [(v["net"], v["x"], v["y"]) for v in rj["vias"] + geo["vias"] if v["net"] != "GND" and not is_fixed(v["net"])]   # RF vias: own return vias (D-157)
rings = sorted({(round(dj * G, 3), round(di * G, 3)) for dj in range(-31, 32) for di in range(-31, 32) if 0.8 <= math.hypot(dj * G, di * G) <= RMAX},
               key=lambda d: math.hypot(*d))
n_need = n_ret = 0; miss = []
for (net, x, y) in sig:
    lay = set()
    for dx in (-0.01, 0, 0.01):
        for dy in (-0.01, 0, 0.01): lay |= ends.get((net, round(x + dx, 2), round(y + dy, 2)), set())
    if len({REF[l] for l in lay if l in REF}) < 2: continue
    n_need += 1
    have = [math.hypot(a - x, b - y) for (a, b) in new + [g_ for g_ in gv if abs(g_[0] - x) < 3.1 and abs(g_[1] - y) < 3.1] if abs(a - x) < 3.1 and abs(b - y) < 3.1]
    if have and min(have) <= 1.5:
        n_ret += 1; DIST.append(min(have)); continue                # a GND via within 1.5 mm is there already
    j0, i0 = cy(y), cx(x)
    spot = next(((j0 + int(round(dj / G)), i0 + int(round(di / G))) for (dj, di) in rings if free_at(j0 + int(round(dj / G)), i0 + int(round(di / G)))), None)
    if spot is None: miss.append((net.split("/")[-1], round(x, 2), round(y, 2))); continue
    dnew = math.hypot(xs[spot[1]] - x, ys[spot[0]] - y)
    if have and min(have) <= dnew: n_ret += 1; DIST.append(min(have)); continue
    put(xs[spot[1]], ys[spot[0]]); n_ret += 1; DIST.append(dnew)
DIST = np.array(DIST)
print("return vias: signal vias with a reference change", n_need, "| GND via within 1.5 mm", int((DIST <= 1.5).sum()), "| 1.5 to 2.0", int(((DIST > 1.5) & (DIST <= 2.0)).sum()),
      "| 2.0 to %.1f" % RMAX, int((DIST > 2.0).sum()), "| none within %.1f mm:" % RMAX, len(miss), miss[:12])

# 2. edge fence, 1.5 mm inside the outline (straight sides and the 5 mm corner arcs), pitch 2.54 mm
OFF, PITCH = 1.5, 2.54
path = []
W_, H_ = X1, Y1
def seg(a, b):
    L = math.hypot(b[0] - a[0], b[1] - a[1]); return [(a[0] + (b[0] - a[0]) * s / L, a[1] + (b[1] - a[1]) * s / L) for s in np.arange(0, L, 0.05)]
def arc(c, a0, a1):
    r = 5 - OFF; return [(c[0] + r * math.cos(a), c[1] + r * math.sin(a)) for a in np.arange(a0, a1, 0.05 / r)]
path += seg((5, OFF), (W_ - 5, OFF)) + arc((W_ - 5, 5), -math.pi / 2, 0) + seg((W_ - OFF, 5), (W_ - OFF, H_ - 5)) + arc((W_ - 5, H_ - 5), 0, math.pi / 2)
path += seg((W_ - 5, H_ - OFF), (5, H_ - OFF)) + arc((5, H_ - 5), math.pi / 2, math.pi) + seg((OFF, H_ - 5), (OFF, 5)) + arc((5, 5), math.pi, 1.5 * math.pi)
n_edge = 0; last = None; acc = PITCH
for k, (x, y) in enumerate(path):
    if last is not None: acc += math.hypot(x - last[0], y - last[1])
    last = (x, y)
    if acc < PITCH: continue
    nx_, ny_ = (W_ / 2 - x), (H_ / 2 - y); nl = math.hypot(nx_, ny_); nx_, ny_ = nx_ / nl, ny_ / nl
    for sh in (0.0, 0.3, 0.6, 1.0):                                  # inward when the place is taken
        j, i = cy(y + ny_ * sh), cx(x + nx_ * sh)
        if free_at(j, i): put(xs[i], ys[j]); n_edge += 1; acc = 0.0; break
print("edge fence vias", n_edge)

# 3. grid stitching, 5 mm
n_grid = 0
off = [(dj, di) for dj in range(-10, 11) for di in range(-10, 11)]; off.sort(key=lambda d: d[0] ** 2 + d[1] ** 2)
for gy in np.arange(5.0, Y1 - 2, 5.0):
    for gx in np.arange(5.0, X1 - 2, 5.0):
        j0, i0 = cy(gy), cx(gx)
        if any(math.hypot(a - gx, b - gy) < 2.5 for (a, b) in near_pts(gx, gy) + [g_ for g_ in gv if abs(g_[0] - gx) < 2.6 and abs(g_[1] - gy) < 2.6]): continue
        spot = next(((j0 + dj, i0 + di) for (dj, di) in off if free_at(j0 + dj, i0 + di)), None)
        if spot: put(xs[spot[1]], ys[spot[0]]); n_grid += 1
print("grid stitching vias", n_grid, "| total new GND vias", len(new))
json.dump({"vias": [{"x": x, "y": y} for (x, y) in new], "missing_return": miss}, open("stitch.json", "w"), indent=0)
# final check (M-80): nearest GND via for every signal via with a reference change, with all GND vias in place
allg = np.array(gv + new)
tr = cKDTree(allg)
fin = []
for (net, x, y) in sig:
    lay = set()
    for dx in (-0.01, 0, 0.01):
        for dy in (-0.01, 0, 0.01): lay |= ends.get((net, round(x + dx, 2), round(y + dy, 2)), set())
    if len({REF[l] for l in lay if l in REF}) < 2: continue
    fin.append((tr.query((x, y))[0], net.split("/")[-1], round(x, 2), round(y, 2)))
d_ = np.array([f[0] for f in fin])
print("final: signal vias with a reference change %d | nearest GND via <= 1.5 mm %d | 1.5 to 2.0 %d | 2.0 to 3.0 %d | above 3.0 %d (max %.2f mm)" %
      (len(fin), (d_ <= 1.5).sum(), ((d_ > 1.5) & (d_ <= 2.0)).sum(), ((d_ > 2.0) & (d_ <= 3.0)).sum(), (d_ > 3.0).sum(), d_.max()))
json.dump({"vias": [{"x": x, "y": y} for (x, y) in new], "missing_return": [[f[1], f[2], f[3], round(f[0], 2)] for f in fin if f[0] > 3.0]},
          open("stitch.json", "w"), indent=0)
