#!/usr/bin/env python3
"""Relay placement study, rev C unit: 3 radios x 4 antennas + EXP. Board-scale drawing (mm)."""
S = 4.0                      # px per mm
BW, BH = 268, 230            # board estimate (9 mm RF band, 2026-09-27)
BAND = 9.0                   # RF band: W 2.7 + 2 x gap 2.0 + fence vias
RT1 = (29.0, 12.7)           # TE RT1 (RTD14012F) body, 5 mm pinning
SIG = RT1                    # RX rows use the RT1 as well (Prins, 2026-09-27)
out = []; a = out.append
OX, OY = 60, 90
def X(x): return OX + x*S
def Y(y): return OY + y*S
OBST = []                    # (x, y, w, h, cls) of parts and keep-outs, for the standoff clearance check
def rect(x, y, w, h, cls):
    if cls in ("rt1", "sig", "band", "conn", "misc", "dnp"): OBST.append((x, y, w, h, cls))
    a(f'<rect class="{cls}" x="{X(x):.1f}" y="{Y(y):.1f}" width="{w*S:.1f}" height="{h*S:.1f}"/>')
def line(x1, y1, x2, y2, cls): a(f'<line class="{cls}" x1="{X(x1):.1f}" y1="{Y(y1):.1f}" x2="{X(x2):.1f}" y2="{Y(y2):.1f}"/>')
def text(x, y, s, size=10, anchor="start", cls="t"): a(f'<text class="{cls}" x="{X(x):.1f}" y="{Y(y):.1f}" font-size="{size}" text-anchor="{anchor}">{s}</text>')
def ptext(px, py, s, size=12, anchor="start", w="normal"): a(f'<text class="t" x="{px}" y="{py}" font-size="{size}" text-anchor="{anchor}" font-weight="{w}">{s}</text>')
count = {"RT1": 0, "SIG": 0}
def relay(kind, x, y, lab, rot=False, fitted=True):
    w, h = (RT1 if kind == "RT1" else SIG)
    if rot: w, h = h, w
    rect(x, y, w, h, ("rt1" if kind == "RT1" else "sig") if fitted else "dnp")
    text(x+w/2, y+h/2+1.3, lab if fitted else lab + " (not fitted)", 8 if kind == "RT1" else 6.5, "middle")
    if fitted: count[kind] += 1

ptext(OX, 30, "Relay placement study, rev C unit (3 radios × 4 antennas + EXP), 1:1 grid in mm, view from the component side", 15, w="bold")
ptext(OX, 52, "Red: rows on top copper. Blue and purple: columns and feeds on bottom copper (dashed purple: top). The THT relay pins make the layer change.", 12)
rect(0, 0, BW, BH, "board")
# grid every 10 mm
for gx in range(10, BW, 10): line(gx, 0, gx, BH, "grid")
for gy in range(10, BH, 10): line(0, gy, BW, gy, "grid")
BANDS = []   # filled later, drawn at the end under-layer style

# --- top zone: logic, power entry, controller above ---
rect(2, 2, BW-4, 32, "zone")
text(4, 7, "Logic zone: I2C expanders (37 outputs + inputs), low-side drivers, /RLY_EN high-side switches, 3V3 LDO, fuses", 8)
for i, (lb, w) in enumerate((("XT60 +12V RLY", 16), ("XT60 +12V AUX", 16), ("XT30 +5V", 12), ("RJ45 LINK", 16), ("RJ45 EXP CTRL", 16))):
    x = 96 + i*30
    rect(x, 0, w, 8, "conn"); text(x+w/2, 12, lb, 7, "middle")
rect(40, 14, 150, 20, "ctl"); text(42, 19, "controller board above (stacked), header here", 8, cls="tc")

# --- matrix ---
EXPX, K0X, CH0, CH1 = 4, 36, 73, 101
AX = [103 + 38*k for k in range(4)]            # cell x0, A1..A4
ALINE = [x + 36 for x in AX]                   # column line x
FEED = [81, 90, 72]          # R3 feed goes straight up from its SO-239 (no parallel run)
for r in range(3):
    y0 = 38 + r*48
    ytx, yrx = y0+18.5, y0+42.5
    text(-2, y0+17, f"R{r+1} TX", 8, "end"); text(-2, y0+33, f"R{r+1} RX", 8, "end")
    # rows (top copper)
    line(EXPX+2, ytx, ALINE[-1]+1, ytx, "rowl"); line(EXPX+2, yrx, ALINE[-1]+1, yrx, "rowl")
    # EXP relays and SMA on left wall
    relay("RT1", EXPX+2, y0+1, f"EXP TX R{r+1}")
    relay("RT1", EXPX+2, y0+25, f"EXP RX R{r+1}")
    line(0, y0+23.5, EXPX+2, y0+23.5, "coll"); text(1, y0+22.5, "SMA", 7)
    # K0
    relay("RT1", K0X+2, y0+1, f"K0 R{r+1}")
    # feed from channel into K0 COM
    line(FEED[r], [217, 213, 209][r], FEED[r], y0+7, "feed"); line(FEED[r], y0+7, K0X+31, y0+7, "feedt")
    line(K0X+26, y0+13.7, K0X+26, yrx, "coll")   # K0 NC down to the RX row (bottom copper under the TX row)
    # A relays
    for k in range(4):
        relay("RT1", AX[k]+1, y0+1, f"TX R{r+1}-A{k+1}", fitted=(k != 1))   # A2 receive-only: TX relay not fitted (D-103)
        relay("RT1", AX[k]+1, y0+25, f"RX R{r+1}-A{k+1}")
text(CH0+1, 36.5, "feeds", 7)
# columns (bottom copper) down to antenna ports
for k in range(4):
    line(ALINE[k], 38, ALINE[k], 216, "coll")
# --- antenna port zone ---
rect(101, 184, BW-103, 34, "zone")
text(103, 188.5, "Antenna ports: K1 (COM ant, NO column, NC ground via bleed), static bleed, GDT footprint (not fitted), RF detector, bias-T option", 7.5)
for k in range(4):
    relay("RT1", ALINE[k]-19, 189, f"K1 A{k+1}", rot=True)
    rect(ALINE[k]+6.5, 191, 6, 5, "misc"); text(ALINE[k]+9.5, 189.8, "bleed", 5.5, "middle")
    rect(ALINE[k]+6.5, 200, 6, 5, "dnp"); text(ALINE[k]+9.5, 198.8, "GDT DNP", 5.5, "middle")
    rect(ALINE[k]+6.5, 209, 6, 7, "misc"); text(ALINE[k]+9.5, 207.8, "det", 5.5, "middle")
# --- SO-239 row (bottom edge) ---
RX_SO = [12, 42, 72]
JOG = [217, 213, 209]
for i, x in enumerate(RX_SO):
    rect(x-12.7, BH, 25.4, 3, "so"); text(x, BH+9, f"R{i+1}", 9, "middle")
    line(x, BH-6, x, JOG[i], "feed"); line(x, JOG[i], FEED[i], JOG[i], "feedt")
for k, x in enumerate(ALINE):
    rect(x-12.7, BH, 25.4, 3, "so"); text(x, BH+9, f"A{k+1}", 9, "middle")
    line(x, 216, x, BH-4, "coll")
rect(0, BH-10, BW, 10, "strapz"); text(BW/2, BH-4.5, "SO-239 strap and GND-boss zone (10 mm)", 7.5, "middle")
# dims
a(f'<text class="t" x="{X(BW/2):.1f}" y="{Y(-4):.1f}" font-size="12" text-anchor="middle">{BW} mm</text>')
a(f'<text class="t" font-size="12" text-anchor="middle" transform="translate({X(BW+6):.1f},{Y(BH/2):.1f}) rotate(90)">{BH} mm</text>')

# RF bands (9 mm keep-out incl. gap and fence) for rows, columns and feeds
for r in range(3):
    y0 = 38 + r*48
    for yl in (y0+18.5, y0+42.5):
        rect(EXPX+2, yl-BAND/2, ALINE[-1]+1-EXPX-2, BAND, "band")
for k in range(4):
    rect(ALINE[k]-BAND/2, 38, BAND, 216-38, "band")
for f in FEED:
    rect(f-BAND/2, 45, BAND, 217-45, "band")
# --- board supports (D-102, C-29): NPTH M3, 8 mm keep-out (washer 7 mm + margin), not on GND ---
KO = 4.0
STANDOFFS = [("S1", 5, 5), ("S2", 149, 5), ("S3", 263, 5),            # top: corners and the gap XT60 AUX / XT30
             ("S4", 46, 116.5), ("S5", 99, 116.5), ("S6", 263, 116.5)]  # middle: free spots in radio block 2
BOSSES = [(x + (14 if i < 6 else -14), 225) for i, x in enumerate(RX_SO + ALINE)]  # M3 to the GND boss per SO-239 (RF bond)
def clearance(px, py):
    best = 1e9
    for (x, y, w, h, c) in OBST:
        dx = max(x - px, 0, px - (x + w)); dy = max(y - py, 0, py - (y + h))
        best = min(best, (dx*dx + dy*dy) ** 0.5 - KO)
    return best
for (n, x, y) in STANDOFFS:
    a(f'<circle class="ko" cx="{X(x):.1f}" cy="{Y(y):.1f}" r="{KO*S:.1f}"/><circle class="npth" cx="{X(x):.1f}" cy="{Y(y):.1f}" r="{1.6*S:.1f}"/>')
    text(x + (5 if x < BW - 20 else -5), y - 4.5 if y > 10 else y + 7.5, n, 7, "start" if x < BW - 20 else "end", "ts")
for (x, y) in BOSSES:
    a(f'<circle class="ko" cx="{X(x):.1f}" cy="{Y(y):.1f}" r="{KO*S:.1f}"/><circle class="pth" cx="{X(x):.1f}" cy="{Y(y):.1f}" r="{1.6*S:.1f}"/>')
CLR = {n: round(clearance(x, y), 2) for (n, x, y) in STANDOFFS}
CLR.update({f"B{i+1}": round(clearance(x, y), 2) for i, (x, y) in enumerate(BOSSES)})
assert min(CLR.values()) >= 0, CLR
# --- results table ---
tx, ty = X(BW) + 60, Y(0)
res = [
 ("Result", ""),
 ("Board", f"{BW} × {BH} mm"),
 ("Case outside", f"about {BW+20} × {BH+20} × 66 mm (D-98)"),
 ("RT1 relays", f"{count['RT1']} fitted (3 K0, 12 TX, 15 RX incl. EXP, 4 K1)"),
 ("", "3 TX at A2 not fitted: A2 receive-only (D-103)"),
 ("Relay types", "one: TE RT1 RTD14012F"),
 ("Coils", f"{count['RT1']}"),
 ("Column pitch", "38 mm = antenna SO-239 pitch"),
 ("Radio block", "48 mm (TX band 24, RX band 24)"),
 ("RF line", "W 2.7 mm, gap 2.0 mm, band 9 mm"),
 ("Walls", "bottom: 7 SO-239; left: 3 SMA EXP;"),
 ("", "top: XT60 ×2, XT30, RJ45 LINK, RJ45 EXP CTRL"),
 ("Layers", "2-layer 1.6 mm: rows top, columns bottom"),
 ("Crossing", "about 0.16 pF each; about 60 dB at 30 MHz"),
 ("Supports", "S1–S6 NPTH M3 (not on GND) + 7 SO-239 GND bosses"),
 ("", "largest free panel 164 × 112 mm (D-102, C-29)"),
]
for i, (k, v) in enumerate(res):
    ptext(tx, ty + 18*i, k, 12 if i == 0 else 11, w="bold" if i == 0 or k else "normal"); ptext(tx+140, ty + 18*i, v, 11)
ny = ty + 18*len(res) + 30
ptext(tx, ny, "Assumptions to confirm", 12, w="bold")
for i, n in enumerate([
 "RT1 body 29.0 × 12.7 mm (RTD14012F datasheet).",
 "RT1 open-contact isolation at 30 MHz: to measure",
 "  with the NanoVNA-H4 (not in the datasheet).",
 "RF band 9 mm: W 2.7, gaps 2.0, fence 3.9 mm from centre.",
 "Coil drivers and expanders fit in the 32 mm logic zone.",
 "Feeds at x 72, 81, 90 (9 mm pitch); R3 straight up.",
]):
    ptext(tx, ny + 18 + 16*i, n, 11)
ptext(tx, ny + 18 + 16*7 + 10, "Shack Relay Matrix rev C · relay placement study · 2026-09-27 · PE1RGU", 10)

W, H = int(X(BW) + 560), int(Y(BH) + 70)
css = """.t{fill:#1d1d1f;font-family:Helvetica,Arial,sans-serif}.tc{fill:#1f4e9c;font-family:Helvetica,Arial,sans-serif}
.board{fill:#e3f1e5;stroke:#2e7d32;stroke-width:2}.grid{stroke:#2e7d32;stroke-opacity:.12;stroke-width:.6}
.zone{fill:none;stroke:#2e7d32;stroke-dasharray:5 3}.ctl{fill:#dfe8f7;fill-opacity:.6;stroke:#1f4e9c;stroke-dasharray:6 3}
.rt1{fill:#f4f4f4;stroke:#333;stroke-width:1.2}.sig{fill:#fff7e0;stroke:#8a6d1a;stroke-width:1}
.rowl{stroke:#c0392b;stroke-width:4;stroke-opacity:.75}.coll{stroke:#1565c0;stroke-width:4;stroke-opacity:.6}
.feed{stroke:#6a1b9a;stroke-width:4;stroke-opacity:.6;fill:none}.feedt{stroke:#6a1b9a;stroke-width:4;stroke-opacity:.6;stroke-dasharray:6 3}.conn{fill:#333}.so{fill:#b08d57;stroke:#6b5230}
.misc{fill:#ddd;stroke:#666}.dnp{fill:#fff;stroke:#666;stroke-dasharray:2 1.5}.band{fill:#c0392b;fill-opacity:.08;stroke:#c0392b;stroke-opacity:.35;stroke-dasharray:2 2}.strapz{fill:#9aa3ad;fill-opacity:.25;stroke:none}
.ko{fill:#ff8f00;fill-opacity:.18;stroke:#e65100;stroke-width:1;stroke-dasharray:3 2}.npth{fill:#fff;stroke:#e65100;stroke-width:1.5}.pth{fill:#b08d57;stroke:#6b5230;stroke-width:1.5}
.ts{fill:#e65100;font-family:Helvetica,Arial,sans-serif;font-weight:bold}"""
svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}"><style>{css}</style><rect width="100%" height="100%" fill="#fff"/>' + "".join(out) + "</svg>"
open("relay-placement-study.svg", "w").write(svg)
print(count, W, H, "standoff clearance (mm beyond the 8 mm keep-out):", CLR)
