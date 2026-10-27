"""Import a Freerouting session into the controller board and report the routing (routing r1).
Usage (KiCad Python, this folder): import_ses.py <session.ses>"""
import sys, pcbnew
BOARD = "../controller-board.kicad_pcb"
b = pcbnew.LoadBoard(BOARD)
print("import", pcbnew.ImportSpecctraSES(b, sys.argv[1]))
print("locked GND items after import", sum(1 for t in b.GetTracks() if t.IsLocked() and t.GetNetname() == "GND"))
b.Save(BOARD)
tr = list(b.GetTracks())
OX = OY = 20.0
for t in tr:
    if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == pcbnew.B_Cu:
        s, e = t.GetStart(), t.GetEnd()
        print("B.Cu %-28s (%.1f, %.1f)-(%.1f, %.1f) %.1f mm" % (t.GetNetname()[-28:], pcbnew.ToMM(s.x) - OX, pcbnew.ToMM(s.y) - OY,
              pcbnew.ToMM(e.x) - OX, pcbnew.ToMM(e.y) - OY, pcbnew.ToMM(t.GetLength())))
lb = sum(pcbnew.ToMM(t.GetLength()) for t in tr if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == pcbnew.B_Cu)
lf = sum(pcbnew.ToMM(t.GetLength()) for t in tr if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == pcbnew.F_Cu)
print("tracks F.Cu %.0f mm, B.Cu %.0f mm, vias %d" % (lf, lb, sum(1 for t in tr if t.Type() == pcbnew.PCB_VIA_T)))
