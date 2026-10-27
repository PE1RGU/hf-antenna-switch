"""Export the controller board geometry for grid_router.py (routing r2). Run with the KiCad Python from this folder.
Writes geom.json: board outline, pads (net, layers, shape, size, rotation, drill), locked tracks and vias, rule areas,
mounting holes. Coordinates in the RF board frame (page minus 20 mm), mm."""
import json, pcbnew
OX = OY = 20.0
T = pcbnew.ToMM
b = pcbnew.LoadBoard("../controller-board.kicad_pcb")
bb = b.GetBoardEdgesBoundingBox()
import os
TERM = json.load(open("terminals.json")) if os.path.exists("terminals.json") else {}   # fan-out terminals (D-154)
out = {"outline": [T(bb.GetX()) - OX, T(bb.GetY()) - OY, T(bb.GetRight()) - OX, T(bb.GetBottom()) - OY], "pads": [],
       "tracks": [], "vias": [], "rule_areas": [], "holes": []}
SHAPE = {pcbnew.PAD_SHAPE_CIRCLE: "circle", pcbnew.PAD_SHAPE_RECTANGLE: "rect", pcbnew.PAD_SHAPE_ROUNDRECT: "rect",
         pcbnew.PAD_SHAPE_OVAL: "oval", pcbnew.PAD_SHAPE_TRAPEZOID: "rect", pcbnew.PAD_SHAPE_CHAMFERED_RECT: "rect"}
for f in b.GetFootprints():
    for p in f.Pads():
        q = p.GetPosition(); s = p.GetSize(pcbnew.F_Cu) if hasattr(p, "GetSize") else p.GetSize()
        lay = [l for l in ("F", "B") if p.IsOnLayer(pcbnew.F_Cu if l == "F" else pcbnew.B_Cu)]
        dr = p.GetDrillSize()
        rec = {"ref": f.GetReference(), "num": p.GetNumber(), "net": p.GetNetname(), "x": T(q.x) - OX, "y": T(q.y) - OY,
               "w": T(s.x), "h": T(s.y), "rot": p.GetOrientationDegrees(), "shape": SHAPE.get(p.GetShape(pcbnew.F_Cu), "rect"),
               "layers": lay, "drill": T(dr.x)}
        ly = pcbnew.F_Cu if "F" in lay else pcbnew.B_Cu
        poly = p.GetEffectivePolygon(ly, pcbnew.ERROR_OUTSIDE).Outline(0)               # exact copper outline
        t_ = TERM.get(rec["ref"], {}).get(rec["num"])
        if t_: rec["x"], rec["y"], rec["layers"] = t_          # router ends on the fixed fan-out copper
        rec["poly"] = [(T(poly.CPoint(i).x) - OX, T(poly.CPoint(i).y) - OY) for i in range(poly.PointCount())]
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            out["holes"].append({"x": rec["x"], "y": rec["y"], "d": max(T(dr.x), T(s.x))})
        else:
            out["pads"].append(rec)
for t in b.GetTracks():
    if not t.IsLocked(): continue                      # only the fixed GND vias and stubs; routed tracks come from routes.json
    if t.Type() == pcbnew.PCB_VIA_T:
        q = t.GetPosition(); out["vias"].append({"net": t.GetNetname(), "x": T(q.x) - OX, "y": T(q.y) - OY, "d": T(t.GetWidth(pcbnew.F_Cu))})
    else:
        s, e = t.GetStart(), t.GetEnd()
        out["tracks"].append({"net": t.GetNetname(), "layer": "F" if t.GetLayer() == pcbnew.F_Cu else "B", "w": T(t.GetWidth()),
                              "x1": T(s.x) - OX, "y1": T(s.y) - OY, "x2": T(e.x) - OX, "y2": T(e.y) - OY})
for z in b.Zones():
    if z.GetIsRuleArea():
        o = z.Outline().Outline(0)
        out["rule_areas"].append([(T(o.CPoint(i).x) - OX, T(o.CPoint(i).y) - OY) for i in range(o.PointCount())])
json.dump(out, open("geom.json", "w"), indent=0)
print("pads", len(out["pads"]), "tracks", len(out["tracks"]), "vias", len(out["vias"]), "holes", len(out["holes"]),
      "rule areas", len(out["rule_areas"]), "outline", out["outline"])
