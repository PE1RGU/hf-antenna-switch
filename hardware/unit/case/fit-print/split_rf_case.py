"""Split the RF case tray and lid into two printable parts each (fit model, Bambu X1C 256 x 256 mm bed).

Input: rf-case-tray.step, rf-case-lid-plain.step (lid without engraving) and lid-text-sketch.json (the SolidCraft sketch
'Lid text' of rf-case.solidcraft). Case frame: x 0..288 left to right, y 0 bottom wall (SO-239) .. 250 top wall,
z 0 case back .. 63 tray top .. 66 lid top.
Tray: cut at x = XT, a plain wall section between the earth boss (x 110.5..120.5) and the lid lug at x 128. U-shaped
tongue (2 mm thick, TL long) in the floor and both walls on the left half; matching groove with CLR per side in the right half.
Lid: cut at x = XL, clear of the screw holes and the engraving; 10 mm half lap.
Rev 2 (2026-11-08): no mesh repair any more (pymeshfix replaced a patch of the lug fillet at x 70..75 and moved engraved
letters by up to 0.5 mm). The tray is meshed once by OpenCascade with the finest settings from MESH that give a closed
mesh; the engraved lid STEP has edge tolerances up to 4 mm and never meshes closed, so the plain lid is meshed and the
engraving is cut as 0.5 mm deep prisms of the text outline (lines and rho 0.5 conics = quadratic Bezier). All booleans
on meshes (manifold engine). The bottom-right pocket corner above z 18 is a spline face that meshes into flats: it is
rebuilt as a cylinder (centre 272, 16; R 10 minus the 0.06 mm fill skin).
Needs: cadquery, trimesh, manifold3d, shapely.
Usage: python3 split_rf_case.py <dir with the input files> <out dir>"""
import json, os, sys
import cadquery as cq
import numpy as np
import trimesh
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.StlAPI import StlAPI_Writer
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

src, out = sys.argv[1], sys.argv[2]
XT, TL, CLR = 122.75, 2.5, 0.15        # tray cut, tongue length, clearance per side
XL, LAP, ZL = 240.0, 5.0, 64.5         # lid cut, half lap length each side, lap split height
MESH = [(0.01, 0.1), (0.02, 0.1), (0.03, 0.2), (0.05, 0.3)]   # (chord mm, angle rad), finest first
os.makedirs(out, exist_ok=True)
box = lambda x0, x1, y0, y1, z0, z1: trimesh.creation.box(bounds=[[x0, y0, z0], [x1, y1, z1]])
U = lambda ms: trimesh.boolean.union(ms, engine="manifold")
D = lambda ms: trimesh.boolean.difference(ms, engine="manifold")
I = lambda ms: trimesh.boolean.intersection(ms, engine="manifold")


def mesh(step):
    shape = cq.importers.importStep(os.path.join(src, step)).val().wrapped
    for lin, ang in MESH:
        BRepTools.Clean_s(shape); BRepMesh_IncrementalMesh(shape, lin, False, ang, True)
        tmp = os.path.join(out, "_tmp.stl"); StlAPI_Writer().Write(shape, tmp)
        m = trimesh.load(tmp); os.remove(tmp)
        if m.is_watertight and m.is_volume:
            print(step, "meshed closed at chord", lin, "angle", ang, "triangles", len(m.faces))
            return m
    raise SystemExit(step + ": no closed mesh")


def text_polygons(path):
    sk = json.load(open(path))["sketch"]
    P = {p["id"]: np.array(p["pos"]) for p in sk["points"]}
    pt = lambda k: P[k] if isinstance(k, str) else P[f"p{k}"]
    lines = []
    for c in sk["curves"]:
        if c.get("construction"): continue
        a, b = pt(c["a"]), pt(c["b"])
        if c["type"] == "line":
            lines.append(LineString([a, b]))
        else:
            assert c["type"] == "conic" and abs(c["rho"] - 0.5) < 1e-9, c
            m, t = pt(c["apex"]), np.linspace(0, 1, 17)[:, None]
            lines.append(LineString((1 - t) ** 2 * a + 2 * (1 - t) * t * m + t ** 2 * b))
    faces = list(polygonize(unary_union(lines)))
    shells = [Polygon(f.exterior) for f in faces]
    keep = [f for f in faces if sum(1 for g, sh in zip(faces, shells) if g is not f and sh.contains(f.representative_point())) % 2 == 0]
    return unary_union(keep)


def tongue(x0, x1, c=0.0):
    """U profile in the floor (5 mm) and both 6 mm walls; c grows it for the groove."""
    return U([box(x0, x1, 2 - c, 248 + c, 1.5 - c, 3.5 + c), box(x0, x1, 2 - c, 4 + c, 1.5 - c, 61 + c),
              box(x0, x1, 246 - c, 248 + c, 1.5 - c, 61 + c)])


cyl = lambda r, h, x, y, z: trimesh.creation.cylinder(radius=r, height=h, sections=256).apply_translation([x, y, z + h / 2])
tray = mesh("rf-case-tray.step")
tray = D([U([tray, box(272, 282, 6, 16, 18, 63)]), cyl(9.94, 45.2, 272, 16, 18), cyl(1.25, 8.2, 282, 6, 55)])
tray_l = U([I([tray, box(-1, XT, -1, 251, -1, 70)]), tongue(XT - 0.5, XT + TL)])
tray_r = D([I([tray, box(XT, 289, -1, 251, -1, 70)]), tongue(XT - 1, XT + TL + 0.4, CLR)])

lid = mesh("rf-case-lid-plain.step")
TXT_D, TOP = 0.5, 66.0
txt = text_polygons(os.path.join(src, "lid-text-sketch.json"))
lid = D([lid] + [trimesh.creation.extrude_polygon(g, TXT_D + 0.5).apply_translation([0, 0, TOP - TXT_D]) for g in getattr(txt, "geoms", [txt])])
print("engraving", len(getattr(txt, "geoms", [txt])), "outlines,", round(txt.area, 1), "mm2")
lid_l = D([lid, box(XL + LAP - CLR, 290, -1, 251, 60, 70), box(XL - LAP, 290, -1, 251, ZL, 70)])
lid_r = D([lid, box(-2, XL - LAP + CLR, -1, 251, 60, 70), box(-2, XL + LAP, -1, 251, 60, ZL)])
lid_r.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))   # outside face down: lap on the bed

parts = {"rf-case-fit-tray-left": tray_l, "rf-case-fit-tray-right": tray_r,   # case back on the bed
         "rf-case-fit-lid-left": lid_l, "rf-case-fit-lid-right": lid_r}       # lid left: outside face up
for n, m in parts.items():
    m.apply_translation(-m.bounds[0])
    assert m.is_watertight and len(m.split()) == 1, n
    m.export(os.path.join(out, n + ".stl"))
    print(n, "size", m.extents.round(2).tolist(), "vol cm3", round(m.volume / 1000, 1))
