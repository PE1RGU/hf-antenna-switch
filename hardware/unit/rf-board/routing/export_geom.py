"""Export the RF board geometry for grid_router.py (p2c). Run with the KiCad Python from this folder, after
gen_rfboard_pcb.py --no-routes. Copy of the controller-board export_geom.py, with two changes: it reads the RF board, and it
exports every track and via (with --no-routes all copper on the board is fixed copper: RF lines, GND vias, fan-out stubs).
Writes geom.json: board outline, pads (net, layers, shape, size, rotation, drill, exact outline), tracks and vias, rule areas,
holes. Coordinates in the board frame (page minus 20 mm), mm. Pads in terminals.json move to their fixed fan-out via."""
import json, math, os, pcbnew
OX = OY = 20.0
T = pcbnew.ToMM
b = pcbnew.LoadBoard("../rf-board.kicad_pcb")
bb = b.GetBoardEdgesBoundingBox()
TERM = json.load(open("terminals.json")) if os.path.exists("terminals.json") else {}
LNAME = {pcbnew.F_Cu: "F", pcbnew.In1_Cu: "In1", pcbnew.In2_Cu: "In2", pcbnew.In3_Cu: "In3", pcbnew.In4_Cu: "In4", pcbnew.B_Cu: "B"}
out = {"outline": [T(bb.GetX()) - OX, T(bb.GetY()) - OY, T(bb.GetRight()) - OX, T(bb.GetBottom()) - OY], "pads": [],
       "tracks": [], "vias": [], "rule_areas": [], "holes": []}
SHAPE = {pcbnew.PAD_SHAPE_CIRCLE: "circle", pcbnew.PAD_SHAPE_RECTANGLE: "rect", pcbnew.PAD_SHAPE_ROUNDRECT: "rect",
         pcbnew.PAD_SHAPE_OVAL: "oval", pcbnew.PAD_SHAPE_TRAPEZOID: "rect", pcbnew.PAD_SHAPE_CHAMFERED_RECT: "rect"}
for f in b.GetFootprints():
    for p in f.Pads():
        q = p.GetPosition(); s = p.GetSize(pcbnew.F_Cu)
        lay = [l for l in ("F", "B") if p.IsOnLayer(pcbnew.F_Cu if l == "F" else pcbnew.B_Cu)]
        dr = p.GetDrillSize()
        rec = {"ref": f.GetReference(), "num": p.GetNumber(), "net": p.GetNetname(), "x": T(q.x) - OX, "y": T(q.y) - OY,
               "w": T(s.x), "h": T(s.y), "rot": p.GetOrientationDegrees(), "shape": SHAPE.get(p.GetShape(pcbnew.F_Cu), "rect"),
               "layers": lay, "drill": T(dr.x)}
        if not lay:
            continue
        poly = p.GetEffectivePolygon(pcbnew.F_Cu if "F" in lay else pcbnew.B_Cu, pcbnew.ERROR_OUTSIDE).Outline(0)
        rec["poly"] = [(T(poly.CPoint(i).x) - OX, T(poly.CPoint(i).y) - OY) for i in range(poly.PointCount())]
        rec["cu"] = lay                                         # copper layers of the pad itself (a terminal changes "layers")
        t_ = TERM.get(rec["ref"], {}).get(rec["num"])
        if t_: rec["x"], rec["y"], rec["layers"] = t_          # router ends on the fixed fan-out via
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            out["holes"].append({"x": rec["x"], "y": rec["y"], "d": max(T(dr.x), T(s.x))})
        else:
            out["pads"].append(rec)
for t in b.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        q = t.GetPosition(); out["vias"].append({"net": t.GetNetname(), "x": T(q.x) - OX, "y": T(q.y) - OY, "d": T(t.GetWidth(pcbnew.F_Cu))})
    else:
        s, e = t.GetStart(), t.GetEnd()
        out["tracks"].append({"net": t.GetNetname(), "layer": LNAME[t.GetLayer()], "w": T(t.GetWidth()),
                              "x1": T(s.x) - OX, "y1": T(s.y) - OY, "x2": T(e.x) - OX, "y2": T(e.y) - OY})
SUP_KO = []
ZONES = list(b.Zones()) + [z for f in b.GetFootprints() for z in f.Zones()]      # footprint keep-outs too (M-79: J12 to J14)
for z in ZONES:
    if z.GetIsRuleArea():
        o = z.Outline().Outline(0)
        poly = [(T(o.CPoint(i).x) - OX, T(o.CPoint(i).y) - OY) for i in range(o.PointCount())]
        if z.GetZoneName() == "SUP_KO":      # support keep-out (D-189): only the support's own net may cross it
            own = [p.GetNetname() for p in b.GetPads() if z.Outline().Contains(p.GetPosition()) and p.GetDrillSize().x > 0]
            SUP_KO.append({"poly": poly, "except": own, "layers": ["F"]})   # tracks on F.Cu (washer); vias on all layers
        else:
            out["rule_areas"].append(poly)
json.dump(out, open("geom.json", "w"), indent=0)
# GND screw holes of the SO-239 and SMA (case seat faces B1 to B10, diameter 10): other nets keep 5.5 mm (D-189, keepout_file)
R_BOSS = 5.5
ko = [{"poly": [(x + R_BOSS * math.cos(2 * math.pi * k / 48), y + R_BOSS * math.sin(2 * math.pi * k / 48)) for k in range(48)],
       "except": ["GND"], "layers": ["F"]}                        # B.Cu is not routed; vias on all layers
      for p in out["pads"] if p["ref"].startswith("J") and p["net"] == "GND" and p["drill"] >= 3.0 for x, y in [(p["x"], p["y"])]]
json.dump({"keepout": ko + SUP_KO}, open("boss_keepout.json", "w"), indent=0)
print("boss keep-outs", len(ko), "support keep-outs", [k["except"] for k in SUP_KO])
print("pads", len(out["pads"]), "tracks", len(out["tracks"]), "vias", len(out["vias"]), "holes", len(out["holes"]),
      "rule areas", len(out["rule_areas"]), "outline", out["outline"])
