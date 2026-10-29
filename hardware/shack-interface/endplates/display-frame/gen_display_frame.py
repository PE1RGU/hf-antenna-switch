"""Display frame for the Waveshare 2inch LCD Module (240x320, ST7789VW) behind the front plate a8 (D-187).
Frame coordinates: u, v as on the plate (seen from outside, v down), w = depth behind the plate inside face.
Built in (u, v, w) and exported in (u, -v, -w), so +z points toward the plate; print as exported: flat back on the bed.
Module data: Waveshare 2D drawing and STEP (2inch_LCD_Module_3D_Drawing.stp; STEP origin at the PCB centre-ish):
PCB x -30.71..27.29, y -17.5..17.5, z -1.85..-0.25; frame ring of the LCD cell z 2.15 (x -24.7..21.9, y +-16.8);
active area z 2.10 (x -20.4..20.4, y +-15.3); M2 holes x -28.21 / 24.79, y +-15.0; PH2.0 8-pin side-entry on the back
x 14.54..23.04, y +-9.95, z down to -7.45, mouth toward +x. The module's own M2 x 6 hex pillars are not used: M2 x 5
pan-head screws from the front go through the module into M2 heat-set inserts in the frame bosses."""
import cadquery as cq, sys
MOD = (45.71, 25.5)              # u of STEP x 0, v of STEP y 0 (module PCB u 15.0..73.0, v 8.0..43.0)
MHOLE = [(-28.21, 15.0), (24.79, 15.0), (-28.21, -15.0), (24.79, -15.0)]       # module M2 holes (STEP x, y)
DSTAND = [(11.5, 11.0), (11.5, 35.0), (77.5, 10.0), (77.5, 41.0)]              # SMD spacers on the plate (u, v)
GLASS = 2.15                     # STEP z of the cell frame ring = plate inside face (w 0)
W_PCB = GLASS + 1.85             # w of the module PCB back = 4.0
W_FACE, T = 5.5, 2.5             # frame face (= spacer length, WA-SMSI 9774055151R) and thickness; 1.5 mm over the PCB back
RIB = 0.2                        # crush ribs on the module bosses: 0.2 mm interference presses the cell ring onto the plate
INSERT_D = 3.2                   # hole for an M2 x 3 heat-set insert, from the boss face
def uv(x, y): return MOD[0] + x, MOD[1] - y
def frame():
    def box(u0, v0, u1, v1, w0, w1):
        return cq.Workplane("XY").box(u1 - u0, v1 - v0, w1 - w0, centered=False).translate((u0, v0, w0))
    f = box(8.5, 7.5, 80.5, 43.5, W_FACE, W_FACE + T).edges("|Z").fillet(3.0)   # R 3: top-left corner clear of the extrusion corner boss
    for (x, y) in MHOLE:                                         # bosses to the PCB back, ribs, insert hole
        u, v = uv(x, y)
        f = f.union(cq.Workplane("XY").circle(3.0).extrude(W_FACE - W_PCB).translate((u, v, W_PCB)))
        for a in (30, 150, 270):                                 # crush ribs 0.6 x 2.0 x 0.2 mm
            r = cq.Workplane("XY").box(2.0, 0.6, RIB, centered=(False, True, False)).translate((0.9, 0, W_PCB - RIB))
            f = f.union(r.rotate((0, 0, 0), (0, 0, 1), a).translate((u, v, 0)))
        f = f.cut(cq.Workplane("XY").circle(INSERT_D / 2).extrude(20).translate((u, v, 0)))
    for (u, v) in DSTAND:
        f = f.cut(cq.Workplane("XY").circle(1.45).extrude(20).translate((u, v, 0)))     # M2.5 clearance
    f = f.cut(box(59.5, 14.5, 75.5, 36.5, 0, 20).edges("|Z").fillet(1.0))              # connector, plug and cable window
    return f.mirror("XZ").mirror("XY")
if __name__ == "__main__":
    fr = frame()
    cq.exporters.export(fr, sys.argv[1] + ".step"); cq.exporters.export(fr, sys.argv[1] + ".stl", tolerance=0.02)
    bb = fr.val().BoundingBox(); print("frame", round(bb.xlen,2), round(bb.ylen,2), round(bb.zlen,2), "vol", round(fr.val().Volume()), "mm3")
