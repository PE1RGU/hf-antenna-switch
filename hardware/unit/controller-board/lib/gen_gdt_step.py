#!/usr/bin/env python3
"""Simple STEP model of the Bourns 2036-xx-B2 GDT (Rev B 01/26) for footprint GDT_3Pin_Bourns_2036-B2_P4.40mm.
Needs cadquery. Writes 3d/GDT_2036-B2.step (run from hardware/unit/controller-board/lib/).
KiCad frame: origin at pad 2, z = 0 on the board top, x along the pad row. Nominal sizes:
body dia 5.0 x 7.5, 0.5 mm above the board; leads dia 0.8, pitch 4.4, 4.0 below the body (3.5 below the board top)."""
import cadquery as cq

D, LEN, GAP, P, LD, LB = 5.0, 7.5, 0.5, 4.4, 0.8, 4.0
zc = GAP + D / 2                                            # body axis height
body = cq.Workplane("YZ").workplane(offset=-LEN / 2).center(0, zc).circle(D / 2).extrude(LEN)
zb = GAP - LB                                               # lead end
lead = lambda x, z0, z1: cq.Workplane("XY").workplane(offset=z0).center(x, 0).circle(LD / 2).extrude(z1 - z0)
parts = body.union(lead(0, zb, GAP + 0.5))
stub = P + LD / 2 - LEN / 2                                 # horizontal lead from the body end to the bend
for x0 in (LEN / 2 - 0.1, -P - LD / 2):                     # YZ normal is +x: both stubs extrude toward +x
    parts = parts.union(cq.Workplane("YZ").workplane(offset=x0).center(0, zc).circle(LD / 2).extrude(stub + 0.1))
for sx in (-1, 1):
    parts = parts.union(lead(sx * P, zb, zc))
cq.exporters.export(parts, "3d/GDT_2036-B2.step")
bb = parts.val().BoundingBox()
print("bbox x", round(bb.xmin, 2), round(bb.xmax, 2), "y", round(bb.ymin, 2), round(bb.ymax, 2), "z", round(bb.zmin, 2), round(bb.zmax, 2))
