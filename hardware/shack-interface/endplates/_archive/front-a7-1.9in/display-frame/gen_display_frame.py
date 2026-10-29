"""Display frame for the Waveshare 1.9 inch module behind the front plate a5 (D-184).
Frame coordinates: u, v as on the plate (seen from outside, v down), w = depth behind the plate inside face.
Build123/cadquery solid in (u, -v, -w) so that +z points toward the plate; print as exported: flat back on the bed, no supports."""
import cadquery as cq, sys
DISP = (16.0, 4.2)
DSTAND = [(11.5, 12.0), (11.5, 27.0), (71.7, 12.0), (71.7, 27.0)]
MSTAND = [(2.8, 2.79), (48.4, 2.8), (2.79, 24.49), (48.39, 24.5)]     # module standoff centres (module STEP x, y)
GLASS = 3.09                     # module STEP z of the glass front; standoff ends at z -2.91, so at w 6.0
W_EAR, W_FACE, T = 6.0, 6.3, 2.5 # ear and boss contact plane, recessed main face, frame thickness
RIB = 0.2                        # crush ribs on the module bosses: 0.2 mm interference presses the glass onto the plate
def uv_mod(x, y): return DISP[0] + x, DISP[1] + 27.3 - y
def frame():
    def box(u0, v0, u1, v1, w0, w1):
        return cq.Workplane("XY").box(u1 - u0, v1 - v0, w1 - w0, centered=False).translate((u0, v0, w0))
    sk = (cq.Sketch().push([(41.6, 18.15)]).rect(52.2, 27.3).push([(41.6, 19.5)]).rect(67.2, 22.0).clean().reset()
          .vertices().fillet(1.0))
    f = cq.Workplane("XY").placeSketch(sk).extrude(W_EAR + T - W_FACE).translate((0, 0, W_FACE))
    for (u, v) in DSTAND:                                        # ear contact pads on the SMD spacers
        f = f.union(cq.Workplane("XY").circle(3.5).extrude(W_FACE - W_EAR).translate((u, v, W_EAR)))
    for (x, y) in MSTAND:
        u, v = uv_mod(x, y)
        f = f.union(cq.Workplane("XY").circle(2.5).extrude(W_FACE - W_EAR).translate((u, v, W_EAR)))
        for a in (0, 120, 240):                                  # crush ribs 0.6 x 2.0 x 0.2 mm
            r = cq.Workplane("XY").box(2.0, 0.6, RIB, centered=(False, True, False)).translate((0.9, 0, W_EAR - RIB))
            f = f.union(r.rotate((0, 0, 0), (0, 0, 1), a).translate((u, v, 0)))
        f = f.cut(cq.Workplane("XY").circle(1.2).extrude(20).translate((u, v, 0)))     # M2 clearance
    for (u, v) in DSTAND:
        f = f.cut(cq.Workplane("XY").circle(1.45).extrude(20).translate((u, v, 0)))     # M2.5 clearance
    u0, v0 = uv_mod(3.5, 21.5); u1, v1 = uv_mod(17.2, 5.8)                              # connector and cable plug window
    f = f.cut(box(u0, v0, u1, v1, 0, 20).edges("|Z").fillet(1.0))
    return f.mirror("XZ").mirror("XY")         # to (u, -v, -w): z up = toward the plate
if __name__ == "__main__":
    fr = frame()
    cq.exporters.export(fr, sys.argv[1] + ".step"); cq.exporters.export(fr, sys.argv[1] + ".stl", tolerance=0.02)
    bb = fr.val().BoundingBox(); print("frame", round(bb.xlen,2), round(bb.ylen,2), round(bb.zlen,2), "vol", round(fr.val().Volume()), "mm3")
