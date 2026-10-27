#!/usr/bin/env python3
"""Aggressor/victim check for the RF board (p2e, hardware-design-rules pcb-layout.md: aggressor/victim list with a measured
distance). Reads geom.json and routes.json. Same layer: parallel run where the edge gap is below GAP_SAME. In2 and In3 (L3
and L4, one 0.233 mm prepreg apart, no plane between): parallel overlap where the centre lines are less than GAP_BROAD apart
in plan view (broadside coupling). F.Cu and B.Cu are screened from the inner layers by L2 and L5. Prints per pair: minimum
edge gap on the same layer, parallel length on the same layer, broadside parallel length."""
import collections, fnmatch, json, math, sys

GAP_SAME, GAP_BROAD, ANG = 1.0, 0.5, 0.17          # mm, mm, rad (about 10 degrees)
VICTIM = ["/A?_DET", "Net-(D?01-K)", "Net-(D?01-COM)", "Net-(C801-Pad1)", "Net-(U801?-+)"]
AGGR = {"coil drain (37 V flyback edge)": ["Net-(D[123]??-A)"], "coil supply / clamp": ["+12V_SW", "CLAMP_SW", "CLAMP_RLY", "+12V_RLY"],
        "coil gate drive (3.3 V edge)": ["*_DRV"], "I2C": ["/SCL", "/SDA"]}
geo = json.load(open("geom.json")); rj = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "routes.json"))
tracks = [t for t in geo["tracks"] + rj["tracks"] if math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) > 1e-6]
match = lambda n, pats: any(fnmatch.fnmatchcase(n, p) for p in pats)
vic = [t for t in tracks if match(t["net"], VICTIM)]
agg = {k: [t for t in tracks if match(t["net"], p)] for k, p in AGGR.items()}

def seg_dist(a, b):
    def pt(px, py, s):
        dx, dy = s["x2"] - s["x1"], s["y2"] - s["y1"]; L2 = dx * dx + dy * dy
        u = max(0, min(1, ((px - s["x1"]) * dx + (py - s["y1"]) * dy) / L2)); return math.hypot(px - s["x1"] - u * dx, py - s["y1"] - u * dy)
    return min(pt(a["x1"], a["y1"], b), pt(a["x2"], a["y2"], b), pt(b["x1"], b["y1"], a), pt(b["x2"], b["y2"], a))
def parallel(a, b, lim):
    """overlap length of two near-parallel segments whose centre lines are closer than lim (perpendicular)"""
    ax, ay = a["x2"] - a["x1"], a["y2"] - a["y1"]; La = math.hypot(ax, ay); ux, uy = ax / La, ay / La
    bx, by = b["x2"] - b["x1"], b["y2"] - b["y1"]; Lb = math.hypot(bx, by)
    if abs(ux * by - uy * bx) / Lb > math.sin(ANG): return 0.0
    perp = abs((b["x1"] - a["x1"]) * uy - (b["y1"] - a["y1"]) * ux)
    if perp > lim: return 0.0
    t1 = (b["x1"] - a["x1"]) * ux + (b["y1"] - a["y1"]) * uy; t2 = (b["x2"] - a["x1"]) * ux + (b["y2"] - a["y1"]) * uy
    return max(0.0, min(La, max(t1, t2)) - max(0.0, min(t1, t2)))

rows = collections.defaultdict(lambda: [99.0, 0.0, 0.0])
for v in vic:
    for kind, ts in agg.items():
        for a in ts:
            if a["net"] == v["net"]: continue
            key = (v["net"], kind, a["net"])
            if a["layer"] == v["layer"]:
                d = seg_dist(v, a) - (v["w"] + a["w"]) / 2
                if d < rows[key][0]: rows[key][0] = d
                rows[key][1] += parallel(v, a, GAP_SAME + (v["w"] + a["w"]) / 2)
            elif {a["layer"], v["layer"]} == {"In2", "In3"}:
                rows[key][2] += parallel(v, a, GAP_BROAD)
out = [(k, r) for k, r in rows.items() if r[0] < 2.0 or r[2] > 0]
out.sort(key=lambda kr: (-(kr[1][1] + kr[1][2]), kr[1][0]))
print("victim | aggressor kind | aggressor net | min edge gap same layer (mm) | parallel same layer (mm) | broadside In2/In3 (mm)")
for (vn, kind, an), (d, ps, pb) in out:
    print("%s | %s | %s | %s | %.1f | %.1f" % (vn, kind, an, "%.2f" % d if d < 90 else "-", ps, pb))
tot = collections.defaultdict(lambda: [99.0, 0.0, 0.0])
for (vn, kind, an), (d, ps, pb) in rows.items():
    t = tot[(vn, kind)]; t[0] = min(t[0], d); t[1] += ps; t[2] += pb
print("\nper victim and aggressor kind:")
for (vn, kind), (d, ps, pb) in sorted(tot.items()):
    print("%s | %s | %s | %.1f | %.1f" % (vn, kind, "%.2f" % d if d < 90 else "-", ps, pb))
