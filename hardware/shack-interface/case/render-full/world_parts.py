# Shack interface full render (M-106): parts that need cleaning or are envelopes, exported as STEP in the housing frame
# (X' across, Y' along the housing, front plate outside, Z' up; same frame as fit3.py and the SolidCraft fit scripts).
# Hammond without its own aluminium end panels (the PCB plates replace them), EAO KILL without the maker's demo panel and
# with its rear parts on a 1.51 mm plate, Waveshare 2inch module without the hex pillars (not used, D-187), M2 screws as
# in the module STEP, PHR-8 plug, WA-SMSI spacers, M2.5 screw heads and the two panel LEDs as simple solids.
import cadquery as cq, sys, os
from OCP.gp import gp_Trsf
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
U, OUT = sys.argv[1], sys.argv[2]
def M(sh, m):
    t = gp_Trsf(); t.SetValues(*m); return cq.Shape.cast(BRepBuilderAPI_Transform(sh.wrapped, t, True).Shape())
def solids(p): return cq.importers.importStep(p).solids().vals()
YB, YF = 81.8, 83.31
def X(u): return 82.5 - u
def Z(v): return 51.312 - v
def W(u, v, w): return cq.Vector(X(u), YB - w, Z(v))
def save(name, L, colors=None):
    """one STEP per group as an assembly: every solid has its own name and colour (SolidCraft takes both from the file)"""
    a = cq.Assembly(name=name)
    for i, s in enumerate(L):
        c = colors(s) if callable(colors) else (colors or "#b0b4b8")
        a.add(s, name=f"{name}-{i + 1}", color=cq.Color(c))
    a.save(os.path.join(OUT, name + ".step")); print(name, len(L))
ham = [M(s, [1,0,0,0, 0,0,1,0, 0,-1,0,0]) for s in solids(U + "case/hammond/1455T1601.stp")]
save("hammond-no-endpanels", [s for s in ham if not ((s.BoundingBox().ymax - s.BoundingBox().ymin) < 3 and abs(s.BoundingBox().ymin) > 75)], "#c3c7cc")
out = []
for s in solids(U + "endplates/parts/EAO_84-5340.0020.stp"):
    b = s.BoundingBox()
    if b.xmax - b.xmin > 90: continue
    out.append(M(s, [1,0,0,X(144), 0,0,1,YF + ((4 - (YF - YB)) if b.zmax <= -1.0 else 0.0), 0,1,0,Z(21)]))
save("kill-eao-84", out, lambda s: "#c62828" if s.BoundingBox().ymin > YF - 0.2 else "#2a2a2a")   # red in front of the plate
DM = [-1,0,0,82.5-45.71, 0,0,1,YB-2.15, 0,1,0,51.312-25.5]
dsp = solids(U + "endplates/display-candidates/2inch/2inch_LCD_Module_3D_Drawing.stp")
cell = max(dsp, key=lambda s: s.Volume())
def dcol(s):
    v = s.Volume()
    return "#24476e" if v > 3500 else "#2b5aa0" if v > 3000 else "#9aa0a6" if 17 < v < 18 else "#f2f2ee"
save("display-2inch", [M(s, DM) for s in dsp if not (29 < s.Volume() < 31)], dcol)   # cell, PCB, M2 screws, header
save("display-plug", [M(cq.Solid.makeBox(6.46, 18.0, 5.3, cq.Vector(18.54, -9.0, -7.3)), DM)], "#e9e4d0")
ST = [(11.5, 11.0), (11.5, 35.0), (77.5, 10.0), (77.5, 41.0)]
save("spacers", [cq.Solid.makeCylinder(2.55, 5.5, W(u, v, 0), cq.Vector(0, -1, 0)) for (u, v) in ST], "#d0d3d6")
save("screws", [cq.Solid.makeCylinder(2.25, 1.75, W(u, v, 8.0), cq.Vector(0, -1, 0)) for (u, v) in ST], "#6e7276")
save("leds", [cq.Solid.makeCylinder(1.5, 1.0, W(u, 12, -1.51), cq.Vector(0, 1, 0)).fuse(
              cq.Solid.makeCylinder(2.6, 12.0, W(u, 12, 0), cq.Vector(0, -1, 0))) for u in (108, 121)], "#e6efe6")
fr = cq.importers.importStep(U + "endplates/display-frame/display-frame.step").solids().vals()
save("display-frame", [M(s, [-1,0,0,82.5, 0,0,1,81.8, 0,1,0,51.312]) for s in fr], "#232323")
