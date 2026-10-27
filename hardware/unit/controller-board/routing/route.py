"""Controller board routing r1 (Freerouting 2.x). Run with the KiCad Python from this folder:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 route.py <stage> [passes]
The B.Cu GND plane on the logic side must stay nearly whole, so routing runs in two stages:
  a: B.Cu not routable (--router.layers.routable=true,false): Freerouting routes on F.Cu only. Result stage-a.ses.
  b: the stage a tracks are imported and locked (exported as protected wires), B.Cu is a signal layer again, and
     Freerouting routes only what is left, with a high via cost. Result controller-board.ses.
The GND class is not routed (-inc GND): each GND pad has its own locked via from gen_controller_pcb.py. Analytics off (-da)."""
import os, subprocess, sys, time
import pcbnew
FR = "/Applications/freerouting.app/Contents/MacOS/freerouting"   # Freerouting 2.5.0 with its own Java runtime
BOARD = "../controller-board.kicad_pcb"
STAGE = sys.argv[1]
PASSES = sys.argv[2] if len(sys.argv) > 2 else "20"
def freeroute(dsn, ses, extra=()):
    if os.path.exists(ses): os.remove(ses)
    t0 = time.time()
    r = subprocess.run([FR, "-de", dsn, "-do", ses, "-mp", PASSES, "-inc", "GND", "-da", "--gui.enabled=false",
                        *extra], capture_output=True, text=True, timeout=1700)
    lines = [l for l in (r.stdout + r.stderr).splitlines() if "unrouted" in l]
    print(ses, "exit", r.returncode, "time %.0f s" % (time.time() - t0), "|", lines[-1][-90:] if lines else "", flush=True)
    assert os.path.exists(ses), r.stderr[-2000:]
b = pcbnew.LoadBoard(BOARD)
if STAGE == "a":
    REMOVED = [t for t in b.GetTracks() if not t.IsLocked()]      # start clean: keep only the locked GND vias and stubs
    for t in REMOVED: b.Remove(t)
    assert pcbnew.ExportSpecctraDSN(b, "stage-a.dsn")
    freeroute("stage-a.dsn", "stage-a.ses", ["--router.layers.routable=true,false"])
    print("import", pcbnew.ImportSpecctraSES(b, "stage-a.ses"))
elif STAGE == "b":
    for t in b.GetTracks(): t.SetLocked(True)           # stage a result is fixed for stage b
    assert pcbnew.ExportSpecctraDSN(b, "stage-b.dsn")
    freeroute("stage-b.dsn", "controller-board.ses", ["--router.via_costs=200"])
    print("import", pcbnew.ImportSpecctraSES(b, "controller-board.ses"))
b.Save(BOARD)
tr = list(b.GetTracks())
lb = sum(pcbnew.ToMM(t.GetLength()) for t in tr if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == pcbnew.B_Cu)
lf = sum(pcbnew.ToMM(t.GetLength()) for t in tr if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == pcbnew.F_Cu)
print("tracks F.Cu %.0f mm, B.Cu %.0f mm, vias %d" % (lf, lb, sum(1 for t in tr if t.Type() == pcbnew.PCB_VIA_T)))
