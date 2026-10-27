#!/usr/bin/env python3
"""Sketch of the rev C unit: milled aluminium case, RF board, stacked controller, SO-239 mounting."""
S = 2.0                     # px per mm, views A and B
CW, CH, CD = 288, 250, 66   # case outer width, height, depth (mm); depth 66 for the DevKit on sockets (D-98, C-27)
WALL, FLOOR, LID = 6, 5, 3
PCB_W, PCB_H, PCB_T = 268, 230, 1.6
SO_PITCH, SO_FL = 32, 25.4  # SO-239 pitch, square flange
out = []
a = out.append
def T(x, y, s, size=11, anchor="start", w="normal", cls="t"):
    a(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" font-weight="{w}">{s}</text>')
def R(x, y, w, h, cls, rx=0):
    a(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}"/>')
def L(x1, y1, x2, y2, cls="dim"):
    a(f'<line class="{cls}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
def C(x, y, r, cls):
    a(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"/>')
def dimh(x1, x2, y, txt):
    L(x1, y, x2, y, "dim"); L(x1, y-5, x1, y+5); L(x2, y-5, x2, y+5); T((x1+x2)/2, y-4, txt, 11, "middle")
def dimv(y1, y2, x, txt):
    L(x, y1, x, y2, "dim"); L(x-5, y1, x+5, y1); L(x-5, y2, x+5, y2)
    a(f'<text class="t" font-size="11" text-anchor="middle" transform="translate({x-6:.1f},{(y1+y2)/2:.1f}) rotate(-90)">{txt}</text>')

# ---------- View A: front, lid removed ----------
ox, oy = 190, 110
T(ox, oy-65, "A  Front view, lid removed (as mounted on the RVS back plate)", 14, w="bold")
R(ox, oy, CW*S, CH*S, "case")
R(ox+WALL*S, oy+WALL*S, (CW-2*WALL)*S, (CH-2*WALL)*S, "cavity")
px, py = ox+10*S, oy+10*S
R(px, py, PCB_W*S, PCB_H*S, "pcb")
T(px+PCB_W*S-8, py+PCB_H*S-44, "RF board 268 × 230 mm (placement study)", 11, "end", cls="tp")
# relay field and zones
R(px+2*S, py+38*S, 99*S, 146*S, "zone"); T(px+2*S+6, py+38*S+16, "EXP + K0 R1–R3,", 10); T(px+2*S+6, py+38*S+30, "radio feeds", 10)
R(px+101*S, py+38*S, 165*S, 180*S, "zone"); T(px+101*S+6, py+38*S+16, "Crossbar TX/RX × A1–A4,", 10); T(px+101*S+6, py+38*S+30, "antenna ports (K1, bleed, detector) below", 10)
# controller board stacked
R(px+40*S, py+14*S, 150*S, 20*S, "ctl"); T(px+40*S+6, py+14*S+16, "Controller board, stacked above", 10)
T(px+40*S+6, py+14*S+30, "RS-485, PTT, KILL, watchdog, /RLY_EN", 10)
# SO-239 row on bottom wall
labels = ["R1", "R2", "R3", "A1", "A2", "A3", "A4"]
xs = []
x0 = 20 + SO_FL/2
for i, lb in enumerate(labels):
    xc = 10 + [12, 42, 72, 139, 177, 215, 253][i]   # board x + 10 mm offset in the case
    xs.append(xc)
    X = ox + xc*S
    R(X-SO_FL/2*S, oy+CH*S, SO_FL*S, 6, "so")          # flange outside bottom wall
    R(X-8*S, oy+CH*S+6, 16*S, 16, "sob")               # threaded barrel (PL-259 side)
    C(X, oy+(CH-WALL)*S-4, 5, "pin")                   # rear + solder cup inside
    T(X, oy+CH*S+40, lb, 11, "middle", "bold")
    # GND boss next to each connector
    C(X+(14 if i < 6 else -14)*S, py+225*S, 5, "boss")       # board y 225, as the placement study (D-102)
# RF board supports S1-S6 (D-102): M3 standoffs 13 mm, NPTH, not on GND; board coordinates as the placement study
for (n, bxs, bys) in (("S1", 5, 5), ("S2", 149, 5), ("S3", 263, 5), ("S4", 46, 116.5), ("S5", 99, 116.5), ("S6", 263, 116.5)):
    C(px+bxs*S, py+bys*S, 5, "stoff"); T(px+bxs*S+(9 if bxs < 200 else -9), py+bys*S+(16 if bys < 10 else -8), n, 10, "start" if bxs < 200 else "end", "bold", "tso")
T(ox + (xs[0]+xs[2])/2*S, oy+CH*S+58, "radios", 10, "middle")
T(ox + (xs[3]+xs[6])/2*S, oy+CH*S+58, "antennas", 10, "middle")
T(ox + CW*S/2, oy+CH*S+74, "SO-239, PL-259 pointing down; radios 30 mm pitch, antennas 38 mm = column pitch", 10, "middle")
# top wall: power + Cat6
for k, (lb, w) in enumerate((("XT60 RLY", 16), ("XT60 AUX", 16), ("XT30 5V", 12), ("RJ45 LINK", 16), ("RJ45 EXP", 16))):
    x = ox + (100 + k*32)*S
    R(x, oy-6, w*S, 12, "conn"); T(x+w*S/2, oy-12, lb, 10, "middle")
# left wall: SMA expansion, one per radio at its row
for k in range(3):
    y = oy + (10 + 38 + 23.5 + k*48)*S
    C(ox, y, 7, "sma"); T(ox-12, y+4, f"SMA EXP R{k+1}", 10, "end")
T(ox-12, oy+(10+38+23.5+3*48)*S-40, "to unit 2 (RG142 / RG400)", 10, "end")
# mounting holes (floor) and lid screws
for (mx, my) in ((3, 3), (CW-3, 3), (3, CH-3), (CW-3, CH-3)):
    pass
for (mx, my) in ((30, 20), (CW-30, 20), (20, CH-40), (CW-20, CH-40)):   # top pair 15 mm from S1, S3 (D-102)
    C(ox+mx*S, oy+my*S, 6, "mh")
T(ox+(CW-20)*S+10, oy+(CH-29)*S, "4 × M5 blind tapped from the back", 10, "end")
# dims
dimh(ox, ox+CW*S, oy-34, f"{CW} mm (outer)")
dimv(oy, oy+CH*S, ox+CW*S+40, f"{CH} mm (outer)")
dimh(ox+xs[0]*S, ox+xs[1]*S, oy+CH*S+92, "30 mm")

# ---------- View B: section through a SO-239 ----------
bx, by = 190, oy+CH*S+170
T(bx, by-42, "B  Section through one SO-239 (side view)", 14, w="bold")
sc = 4.0
h_show = 80
R(bx, by, FLOOR*sc, h_show*sc, "metal")
R(bx+(CD-LID)*sc, by, LID*sc, h_show*sc, "metal")
R(bx, by+h_show*sc, CD*sc, WALL*sc, "metal")
axis = 16
pcb_front = FLOOR + axis - 1.5
pcb_back = pcb_front - PCB_T
R(bx+pcb_back*sc, by+6*sc, PCB_T*sc, (h_show-7)*sc, "pcbs")
R(bx+FLOOR*sc, by+30*sc, (pcb_back-FLOOR)*sc, 5*sc, "stand")
R(bx+pcb_front*sc, by+14*sc, 15.7*sc, 29*sc, "relay")
ctl_x = pcb_front + 15.7 + 4
R(bx+ctl_x*sc, by+2*sc, PCB_T*sc, 24*sc, "pcbs")
# DevKit on gold sockets (D-95): socket 8.50, DevKit spacer 2.54, DevKit 1.6, USB-C 3.3 (C-27)
dk0 = ctl_x + PCB_T
R(bx+dk0*sc, by+4*sc, 8.5*sc, 2.5*sc, "sock"); R(bx+(dk0+8.5)*sc, by+4*sc, 2.54*sc, 2.5*sc, "spacer")
dk1 = dk0 + 8.5 + 2.54
R(bx+dk1*sc, by+3*sc, PCB_T*sc, 20*sc, "dk"); R(bx+(dk1+PCB_T)*sc, by+5*sc, 3.3*sc, 9*sc, "usb")
dk_top = dk1 + PCB_T + 3.3
dimh(bx+dk_top*sc, bx+(CD-LID)*sc, by+28*sc, f"{CD-LID-dk_top:.1f} mm")
axx = bx+(FLOOR+axis)*sc
wy = by+h_show*sc
R(axx-SO_FL/2*sc, wy+WALL*sc, SO_FL*sc, 2.5*sc, "so")
R(axx-8*sc, wy+(WALL+2.5)*sc, 16*sc, 14*sc, "sob")
R(axx-8*sc, wy-4*sc, 16*sc, (WALL+4)*sc, "sob")
R(axx-1.5*sc, wy-10*sc, 3*sc, 6*sc, "cup")
L(axx, wy+(WALL+16.5)*sc, axx, wy+(WALL+34)*sc, "axis")
a(f'<path class="strap" d="M{axx-1.5*sc:.1f},{wy-8*sc:.1f} L{bx+pcb_front*sc+2:.1f},{wy-8*sc:.1f} L{bx+pcb_front*sc+2:.1f},{wy-12*sc:.1f}"/>')
R(bx+FLOOR*sc, wy-8*sc, (pcb_back-FLOOR)*sc, 8*sc, "boss2")
# callouts, right of the lid
cxl = bx + CD*sc + 40
def call(tx, ty, lines, fx, fy):
    L(cxl-4, ty-4, fx, fy, "lead")
    for i, ln in enumerate(lines): T(cxl, ty+i*13, ln, 10)
call(cxl, by+4,  ["floor 5 mm, against the RVS back plate", "(left side of this view)"], bx+FLOOR*sc/2, by+4*sc)
call(cxl, by+34, ["lid 3 mm, M3 screws"], bx+(CD-LID/2)*sc, by+8*sc)
call(cxl, by+60, ["controller board, stacked"], bx+(ctl_x+0.8)*sc, by+14*sc)
call(cxl, by+73, ["DevKit on sockets, USB-C toward open space (R-14)"], bx+(dk1+0.8)*sc, by+20*sc)
call(cxl, by+86, ["RT1 relay, 15.7 mm high"], bx+(pcb_front+8)*sc, by+28*sc)
call(cxl, by+112,["RF board 1.6 mm on 13 mm standoffs"], bx+(pcb_back+0.8)*sc, by+45*sc)
call(cxl, by+138,["standoff M3"], bx+(FLOOR+6)*sc, by+32*sc)
call(cxl, by+180,["copper strap 3 × 0.3 mm, &lt; 6 mm long:", "solder cup to RF pad, takes up height error"], axx+1, wy-8*sc)
call(cxl, by+222,["milled GND boss next to each SO-239,", "board GND screwed to it (M3)"], bx+(FLOOR+5)*sc, wy-4*sc)
call(cxl, by+262,["bottom wall 6 mm, tapped M3 for the flange"], bx+(CD-12)*sc, wy+3*sc)
call(cxl, by+292,["SO-239 flange outside the wall;", "PL-259 and coax go down"], axx+SO_FL/2*sc-4, wy+(WALL+1.2)*sc)
# dims: depth and axis distance (horizontal)
dimh(bx, bx+CD*sc, wy+(WALL+42)*sc, f"{CD} mm outer depth")
dimh(bx, axx, by-10, f"{FLOOR+axis} mm to SO-239 axis")
# ---------- View C: SO-239 from below ----------
cx0, cy0 = 820, by+10
T(cx0, cy0-52, "C  SO-239 on the bottom wall (seen from below)", 14, w="bold")
sc2 = 5
R(cx0, cy0, 120*sc2/2, 60*sc2/2, "metal")
fx, fy = cx0+30*sc2/2+10, cy0+30*sc2/2-6
R(fx-SO_FL/2*sc2/1.2, fy-SO_FL/2*sc2/1.2, SO_FL*sc2/1.2, SO_FL*sc2/1.2, "so")
C(fx, fy, 8*sc2/1.2, "sob"); C(fx, fy, 2*sc2/1.2, "pin")
for dx in (-9.15, 9.15):
    for dy in (-9.15, 9.15):
        C(fx+dx*sc2/1.2, fy+dy*sc2/1.2, 1.7*sc2/1.2, "screw")
T(cx0+62*sc2/2+10, cy0+20, "4 × M3 into tapped wall,", 10); T(cx0+62*sc2/2+10, cy0+34, "hole pitch 18.3 mm", 10)
T(cx0+62*sc2/2+10, cy0+58, "flange square 25.4 mm", 10)
T(cx0+62*sc2/2+10, cy0+82, "flange bonds to the case:", 10); T(cx0+62*sc2/2+10, cy0+96, "coax shield = case = RF GND", 10)

# ---------- Notes ----------
nx, ny = 820, cy0+190
notes = [
 "Load path: coax → SO-239 → case wall. The PCB carries no cable force.",
 "RF return: shield → flange → case → GND boss → board GND, at each connector.",
 "Case: milled tray from 6082-T6, walls 6 mm, floor 5 mm, lid 3 mm on M3 screws.",
 "Case to RVS box: one bond to the earth bar (isolated mounting to decide).",
 "RF board supports: S1–S6 M3 standoffs (13 mm, NPTH, not on GND) + 7 GND bosses at the SO-239 (D-102).",
 "All dimensions are estimates until the relay placement study.",
]
T(nx, ny, "Notes", 13, w="bold")
for i, n in enumerate(notes): T(nx, ny+20+i*17, n, 11)
T(nx, ny+20+len(notes)*17+14, "Shack Relay Matrix rev C · 3 radios × 4 antennas · case sketch · 2026-09-27 · PE1RGU", 10, cls="tg")

W, H = 1400, by + 540
css = """
.t{fill:#1d1d1f;font-family:Helvetica,Arial,sans-serif}.tp{fill:#0b5d1e;font-family:Helvetica,Arial,sans-serif}.tg{fill:#777;font-family:Helvetica,Arial,sans-serif}
.case{fill:#c9ced4;stroke:#555;stroke-width:1.5}.cavity{fill:#eef0f2;stroke:#888}
.pcb{fill:#d7ecd9;stroke:#2e7d32;stroke-width:1.2}.pcbs{fill:#2e7d32}.zone{fill:none;stroke:#2e7d32;stroke-dasharray:5 3}
.sock{fill:#333}.spacer{fill:#555}.dk{fill:#1f4e9c}.usb{fill:#9aa3ad;stroke:#555}
.ctl{fill:#dfe8f7;stroke:#1f4e9c;stroke-dasharray:6 3}.so{fill:#b08d57;stroke:#6b5230}.sob{fill:#d9c193;stroke:#6b5230}
.pin{fill:#e0b040;stroke:#6b5230}.cup{fill:#e0b040;stroke:#6b5230}.boss{fill:#9aa3ad;stroke:#555}.stoff{fill:#fff;stroke:#e65100;stroke-width:2}.tso{fill:#e65100;font-family:Helvetica,Arial,sans-serif}.boss2{fill:#9aa3ad;stroke:#555}
.conn{fill:#333}.sma{fill:#e0b040;stroke:#6b5230}.mh{fill:#fff;stroke:#555}.metal{fill:#c9ced4;stroke:#555}
.stand{fill:#9aa3ad;stroke:#555}.relay{fill:#f2f2f2;stroke:#444}.screw{fill:#666}
.dim{stroke:#444;stroke-width:0.8}.axis{stroke:#444;stroke-dasharray:8 3 2 3}.lead{stroke:#444;stroke-width:0.6}
.strap{fill:none;stroke:#c0392b;stroke-width:3}
"""
svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" width="{W}" height="{H:.0f}"><style>{css}</style><rect width="100%" height="100%" fill="#fff"/>' + "".join(out) + "</svg>"
open("unit-case-sketch.svg", "w").write(svg)
print("ok", W, H)
