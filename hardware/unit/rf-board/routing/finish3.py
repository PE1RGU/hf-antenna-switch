#!/usr/bin/env python3
"""D-217 completion, region step (Prins 2026-11-19, option 1): all nets with a pad on the given parts (the expanders) are
ripped up together; the rest of the board stays fixed. They are routed again as in a router pass (the failed nets first,
then the shortest connections first), up to PASSES local passes; the failed nets of a pass go first in the next one.
Usage: python3 finish3.py router_cfg.json in_routes.json out.json REF[,REF...]|nets=NET[,NET...] [passes]"""
import sys, json, time
cfg, src_routes, out, refs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(",")
PASSES = int(sys.argv[5]) if len(sys.argv) > 5 else 4
sys.argv = [sys.argv[0], cfg]
src = open("grid_router.py").read()
exec(src[:src.index("t_start = time.time(); first = []")].replace("@njit(cache=True)", "@njit"))
CFG["window_steps"] = CFG["window_steps"] + CFG.get("finish_windows", [])
rj = json.load(open(src_routes))
if refs[0].startswith("nets="):                            # explicit net list (D-218: nets with a via in a case keep-out)
    refs[0] = refs[0][5:]; RIP = sorted(n for n in route_nets if n in refs)
else:
    RIP = sorted(n for n in route_nets if any(p["ref"] in refs for p in PADS[n]))
first = [f["net"] for f in rj["failed"] if f["net"] in RIP]
other_failed = [f for f in rj["failed"] if f["net"] not in RIP]
keep_t = [t for t in rj["tracks"] if t["net"] not in RIP]
keep_v = [v for v in rj["vias"] if v["net"] not in RIP and not (v["net"] == "GND" and GNDKO[cy(v["y"]), cx(v["x"])])]   # GND return vias stay unless now in a keep-out
print("ripped", len(RIP), "nets; failed first", first, "| failed outside the region", [f["net"] for f in other_failed], flush=True)
t0 = time.time(); best = None
for it in range(PASSES):
    owner[:] = OWNER0; VIAC[:] = VIAC0; RETV.clear(); RET_MISS.clear()
    for t in keep_t: paint_track(t, NID[t["net"]])
    for v in keep_v: paint_via(v, NID[v["net"]])
    states = {n: NetState(n) for n in RIP}
    ed = sorted(((n not in first, first.index(n) if n in first else 0, d, n, a, b) for n in RIP for (a, b, d) in EDGES[n]))
    for (_, _, d, n, a, b) in ed:
        S = states[n]
        if S.find(a) != S.find(b): route_edge(S, a, b) or route_edge(S, b, a)
    failed = []
    for n, S in states.items():
        comps = {S.find(k) for k in range(len(S.pads))}
        if len(comps) > 1:
            big = max(comps, key=lambda r: sum(1 for k in range(len(S.pads)) if S.find(k) == r))
            failed.append({"net": n, "pads_left": [S.pads[k]["ref"] + "." + S.pads[k]["num"] for k in range(len(S.pads)) if S.find(k) != big]})
    print("local pass %d: failed %d %s | %d s" % (it + 1, len(failed), [f["net"].split("/")[-1] for f in failed], time.time() - t0), flush=True)
    if best is None or len(failed) < best:
        best = len(failed)
        res = {"tracks": keep_t + [t for S in states.values() for t in S.tracks], "vias": keep_v + list(RETV) + [v for S in states.values() for v in S.vias],
               "failed": failed + other_failed, "order": [f["net"] for f in failed], "return_miss": list(RET_MISS)}
        json.dump(res, open(out, "w"))
    if not failed: break
    first = [f["net"] for f in failed] + [n for n in first if n not in [f["net"] for f in failed]]
print("best", best)
