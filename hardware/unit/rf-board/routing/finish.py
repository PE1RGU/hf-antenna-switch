#!/usr/bin/env python3
"""D-217 completion step for grid_router.py. Loads the routes of one pass; all nets that routed stay fixed. The failed nets are
ripped up and routed again, one net at a time (all its connections, shortest first), with the window steps of
router_cfg.json plus 'finish_windows'. Usage: python3 finish.py router_cfg.json routes_passN.json out.json"""
import sys, json, time
cfg, src_routes, out = sys.argv[1], sys.argv[2], sys.argv[3]
sys.argv = [sys.argv[0], cfg]
src = open("grid_router.py").read()
exec(src[:src.index("t_start = time.time(); first = []")].replace("@njit(cache=True)", "@njit"))
CFG["window_steps"] = CFG["window_steps"] + CFG.get("finish_windows", [])
rj = json.load(open(src_routes))
bad = [f["net"] for f in rj["failed"]]
owner[:] = OWNER0; VIAC[:] = VIAC0; RETV.clear(); RET_MISS.clear()
keep_t = [t for t in rj["tracks"] if t["net"] not in bad]
keep_v = [v for v in rj["vias"] if v["net"] not in bad]
for t in keep_t: paint_track(t, NID[t["net"]])
for v in keep_v: paint_via(v, NID[v["net"]])
t0 = time.time(); states = {}
for n in bad:
    S = NetState(n); states[n] = S
    for (a, b, d) in sorted(EDGES[n], key=lambda e: e[2]):
        if S.find(a) == S.find(b): continue
        ok = route_edge(S, a, b) or route_edge(S, b, a)
        if not ok: print(n, S.pads[a]["ref"] + "." + S.pads[a]["num"], S.pads[b]["ref"] + "." + S.pads[b]["num"], "FAIL", round(time.time() - t0), flush=True)
res = {"tracks": keep_t + [t for S in states.values() for t in S.tracks], "vias": keep_v + list(RETV) + [v for S in states.values() for v in S.vias],
       "failed": [], "order": bad, "return_miss": list(RET_MISS)}
for n, S in states.items():
    comps = {S.find(k) for k in range(len(S.pads))}
    if len(comps) > 1:
        big = max(comps, key=lambda r: sum(1 for k in range(len(S.pads)) if S.find(k) == r))
        res["failed"].append({"net": n, "pads_left": [S.pads[k]["ref"] + "." + S.pads[k]["num"] for k in range(len(S.pads)) if S.find(k) != big]})
json.dump(res, open(out, "w"))
print("failed after finish:", [x["net"] for x in res["failed"]], round(time.time() - t0), "s", flush=True)
