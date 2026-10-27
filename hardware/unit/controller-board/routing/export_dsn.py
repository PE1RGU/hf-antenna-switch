"""Export controller-board.kicad_pcb to Specctra DSN for Freerouting (routing r1). Run with the KiCad Python from this folder."""
import pcbnew
b = pcbnew.LoadBoard("../controller-board.kicad_pcb")
ok = pcbnew.ExportSpecctraDSN(b, "controller-board.dsn")
print("export", ok)
