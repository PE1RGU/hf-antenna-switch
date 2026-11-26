#!/usr/bin/env python3
"""D-217 completion with local rip-up for grid_router.py. Loads the routes of one pass. For a failed net: the nets with copper
in the box around its unjoined pads (plus RIP_M mm) are ripped up, the failed net is routed first, then the ripped nets again.
Nets that fail go back in the queue. Usage: python3 finish2.py router_cfg.json routes_passN.json out.json [iterations]"""
import sys, json, time
cfg, src_routes, out = sys.argv[1], sys.argv[2], sys.argv[3]; ITER = int(sys.argv[4]) if len(sys.argv) > 4 else 40
sys.argv = [sys.argv[0], cfg]
src = open("grid_router.py").read()
exec(src[:src.index("t_start = time.time(); first = []")].replace("@njit(cache=True)", "@njit"))
CFG["window_steps"] = CFG["window_steps"] + CFG.get("finish_windows", [])
RIP_M, RIP_N = 2.0, 12
rj = json.load(open(src_routes))
NETCU = {}                                        # net -> [tracks, vias, return vias]
for t in rj["tracks"]: NETCU.setdefault(t["net"], [[], [], []])[0].append(t)
for v in rj["vias"]:
    if v["net"] != "GND": NETCU.setdefault(v["net"], [[], [], []])[1].append(v)
GNDV = [v for v in rj["vias"] if v["net"] == "GND"]  # return vias of the pass: kept (not tied to a net in the file)
queue = [f["net"] for f in rj["failed"]]; left = {f["net"]: f["pads_left"] for f in rj["failed"]}
def repaint(skip):
    owner[:] = OWNER0; VIAC[:] = VIAC0
    for v in GNDV: paint_via(v, NID["GND"])
    for n, (ts, vs, rs) in NETCU.items():
        if n in skip: continue
        for t in ts: paint_track(t, NID[n])
        for v in vs + rs: paint_via(v, NID[v["net"]])
def route_net(n):
    RETV.clear(); S = NetState(n)
    for (a, b, d) in sorted(EDGES[n], key=lambda e: e[2]):
        if S.find(a) != S.find(b): route_edge(S, a, b) or route_edge(S, b, a)
    comps = {S.find(k) for k in range(len(S.pads))}
    NETCU[n] = [S.tracks, S.vias, list(RETV)]
    for t in S.tracks: pass
    if len(comps) > 1:
        big = max(comps, key=lambda r: sum(1 for k in range(len(S.pads)) if S.find(k) == r))
        return [S.pads[k]["ref"] + "." + S.pads[k]["num"] for k in range(len(S.pads)) if S.find(k) != big]
    return []
PADXY = {p["ref"] + "." + p["num"]: (p["x"], p["y"]) for n in PADS for p in PADS[n]}
t0 = time.time(); it = 0; best = len(queue)
while queue and it < ITER:
    it += 1; n = queue.pop(0)
    pts = [PADXY[k] for k in left.get(n, []) if k in PADXY] + [PADXY[p["ref"] + "." + p["num"]] for p in PADS[n]]
    # box: the unjoined pads and their nearest pad of the net
    lp = [PADXY[k] for k in left.get(n, []) if k in PADXY] or pts
    other = [q for q in pts if q not in lp] or pts
    near = [min(other, key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) for p in lp]
    segs_ = list(zip(lp, near))
    def dseg(x, y, a_, b_):
        dx, dy = b_[0] - a_[0], b_[1] - a_[1]; L2 = dx * dx + dy * dy
        t = 0 if L2 == 0 else max(0, min(1, ((x - a_[0]) * dx + (y - a_[1]) * dy) / L2))
        return ((x - a_[0] - t * dx) ** 2 + (y - a_[1] - t * dy) ** 2) ** 0.5
    score = {}
    for m, (ts, vs, rs) in NETCU.items():
        if m == n or m == "GND": continue
        c_ = sum(1 for t in ts for x, y in ((t["x1"], t["y1"]), (t["x2"], t["y2"]), ((t["x1"] + t["x2"]) / 2, (t["y1"] + t["y2"]) / 2))
                 for a_, b_ in segs_ if dseg(x, y, a_, b_) < RIP_M) + sum(3 for v in vs for a_, b_ in segs_ if dseg(v["x"], v["y"], a_, b_) < RIP_M)
        if c_: score[m] = c_
    rip = sorted(score, key=lambda m: -score[m])[:RIP_N]
    repaint(set(rip) | {n})
    l_ = route_net(n)
    res_ = {n: l_}
    for m in rip:
        res_[m] = route_net(m)
    for m, l2 in res_.items():
        if l2: left[m] = l2; queue.append(m) if m not in queue else None
        else: left.pop(m, None); queue = [q for q in queue if q != m]
    print(f"it {it}: {n.split('/')[-1]} ripped {len(rip)} -> failed now {len(queue)} {[q.split('/')[-1] for q in queue]} {round(time.time() - t0)} s", flush=True)
    if len(queue) <= best:
        best = len(queue); repaint(set())
        res = {"tracks": [t for ts, vs, rs in NETCU.values() for t in ts],
               "vias": GNDV + [v for ts, vs, rs in NETCU.values() for v in vs + rs],
               "failed": [{"net": q, "pads_left": left[q]} for q in queue], "order": queue, "return_miss": []}
        json.dump(res, open(out, "w"))
print("done; failed", queue)
