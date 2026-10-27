"""Hidden-line projection of OCC shapes into 2D polylines (orthographic)."""
from OCP.STEPControl import STEPControl_Reader
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID, TopAbs_EDGE, TopAbs_FACE
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir, gp_Pln
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Common
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
import numpy as np


def load_solids(path):
    r = STEPControl_Reader(); r.ReadFile(path); r.TransferRoots()
    e = TopExp_Explorer(r.OneShape(), TopAbs_SOLID); out = []
    while e.More():
        g = GProp_GProps(); BRepGProp.VolumeProperties_s(e.Current(), g)
        out.append((g.Mass(), e.Current())); e.Next()
    return out


def frame(n, vx):
    n = np.array(n, float); vx = np.array(vx, float); vy = np.cross(n, vx)
    return n, vx, vy


def uv(p, n, vx):
    """Projection coordinates of a 3D point, same convention as HLRAlgo_Projector(gp_Ax2(O, n, vx))."""
    _, vx, vy = frame(n, vx); p = np.array(p, float)
    return float(p @ vx), float(p @ vy)


def _edges(comp, defl=0.03):
    out = []
    if comp is None or comp.IsNull():
        return out
    e = TopExp_Explorer(comp, TopAbs_EDGE)
    while e.More():
        c = BRepAdaptor_Curve(TopoDS.Edge(e.Current()))
        d = GCPnts_QuasiUniformDeflection(c, defl)
        if d.IsDone() and d.NbPoints() > 1:
            out.append(np.array([(d.Value(i).X(), d.Value(i).Y()) for i in range(1, d.NbPoints() + 1)]))
        e.Next()
    return out


def project(shape, n, vx, hidden=True):
    a = HLRBRep_Algo(); a.Add(shape)
    a.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*n), gp_Dir(*vx))))
    a.Update(); a.Hide()
    h = HLRBRep_HLRToShape(a)
    vis = _edges(h.VCompound()) + _edges(h.OutLineVCompound()) + _edges(h.Rg1LineVCompound())
    hid = (_edges(h.HCompound()) + _edges(h.OutLineHCompound())) if hidden else []
    return vis, hid


def halfspace_cut(shape, axis, at, keep):
    """Keep the part of shape with coordinate[axis] >= at (keep='+') or <= at (keep='-')."""
    big = 2000.0
    lo = [-big] * 3; hi = [big] * 3
    if keep == '+':
        hi[axis] = at   # remove the low side
    else:
        lo[axis] = at   # remove the high side
    box = BRepPrimAPI_MakeBox(gp_Pnt(*lo), gp_Pnt(*hi)).Shape()
    return BRepAlgoAPI_Cut(shape, box).Shape()


def section_faces(shape, axis, at, n, vx, t=0.02):
    """Triangles (in view coordinates) of the cut face: common of shape and a thin slab at the plane."""
    big = 2000.0
    lo = [-big] * 3; hi = [big] * 3; lo[axis] = at - t / 2; hi[axis] = at + t / 2
    slab = BRepPrimAPI_MakeBox(gp_Pnt(*lo), gp_Pnt(*hi)).Shape()
    c = BRepAlgoAPI_Common(shape, slab).Shape()
    BRepMesh_IncrementalMesh(c, 0.05)
    tris = []
    e = TopExp_Explorer(c, TopAbs_FACE)
    while e.More():
        f = TopoDS.Face(e.Current()); loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is not None:
            pts = [tri.Node(i).Transformed(loc.Transformation()) for i in range(1, tri.NbNodes() + 1)]
            for k in range(1, tri.NbTriangles() + 1):
                i1, i2, i3 = tri.Triangle(k).Get()
                tris.append([uv((pts[i - 1].X(), pts[i - 1].Y(), pts[i - 1].Z()), n, vx) for i in (i1, i2, i3)])
        e.Next()
    return tris
