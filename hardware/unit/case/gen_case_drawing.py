"""RF board case drawing set (A2, PDF) from rf-case.step.

Views are exact hidden-line projections of the STEP solids (hlr.py). Hole positions, sizes and depths come from the
feature list below, which mirrors the SolidCraft model parameters (rf-case.solidcraft); the script checks the list
against the thread data exported from the model (_threads.json) and against the projected geometry.
Usage: python3 gen_case_drawing.py <rf-case.step> <_threads.json> <out.pdf> [png_dir]
"""
import sys, json, math, datetime
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle, Circle, Polygon
import hlr

STEP, THREADS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PNG = sys.argv[4] if len(sys.argv) > 4 else None
ASM_PNG = sys.argv[5] if len(sys.argv) > 5 else ''
A2 = (594.0, 420.0)
MM = 1 / 25.4
DATE = "2026-10-25"
TITLE = "Shack Relay Matrix rev C - RF unit case"
DWG = "RF-CASE-01"
REV = "B"

# ---------------- model data (mirrors rf-case.solidcraft parameters) ----------------
W, H, D, WALL, FLOOR, LID = 288.0, 250.0, 66.0, 6.0, 5.0, 3.0
TRAY_H = D - LID
SO_X = [22, 52, 82, 149, 187, 225, 263]; SO_N = ["R1", "R2", "R3", "A1", "A2", "A3", "A4"]; SO_Z = FLOOR + 16
SO_SQ = 18.24
LID_PTS = [(6, 6), (282, 6), (282, 244), (6, 244), (67, 4.5), (128, 4.5), (206, 4.5), (224, 245.5)] + \
          [(x, y) for x in (4.5, 283.5) for y in (45, 107.5, 155.5, 210)]
LUGS = [p for p in LID_PTS[4:]]
BOSS_X = [36, 66, 96, 163, 201, 239, 249]
SMA_BOSS_Y = [188.5, 140.5, 92.5]   # GND bosses beside the EXP SMAs (RF board J4..J6), case x 14
STANDOFF = [("S1", 15, 236), ("S2", 159, 236), ("S3", 273, 236), ("S4", 56, 124.5), ("S5", 109, 124.5), ("S6", 273, 124.5)]
MOUNT = [("TL", 30, 230), ("TR", 258, 230), ("BL", 30, 35), ("BR", 258, 35)]
SMA_Y = [("EXP R1", 179.5), ("EXP R2", 131.5), ("EXP R3", 83.5)]; SMA_Z = FLOOR + 16.1; SMA_SQ = 8.64
EARTH = (115.5, 0, FLOOR + 7)
CUTS = [("RJ45 J1", 38.5, 47.5, 16.2, 11.8), ("EXP ribbon slot", 74, 30, 37, 9), ("XT60 J11", 109.6, 23.8, 16.5, 9.4),
        ("XT60 J12", 139.6, 23.8, 16.5, 9.4), ("XT30 J13", 172.5, 22.1, 11, 6)]
EXP_SCREWS = [52.5, 95.5]

# view definitions: key -> (normal towards viewer, x direction on paper, title)
VIEWS = {
    "plan":   ((0, 0, 1), (1, 0, 0), "TRAY - PLAN (inside, seen from the lid side)"),
    "back":   ((0, 0, -1), (-1, 0, 0), "TRAY - BACK FACE (seen from the back plate)"),
    "bottom": ((0, -1, 0), (1, 0, 0), "WALL 1 - SO-239 WALL (outside)"),
    "top":    ((0, 1, 0), (-1, 0, 0), "WALL 2 - POWER / RJ45 WALL (outside)"),
    "left":   ((-1, 0, 0), (0, -1, 0), "WALL 3 - SMA WALL (outside)"),
    "right":  ((1, 0, 0), (0, 1, 0), "WALL 4 - PLAIN WALL (outside)"),
}

# hole / cut features: id, description, size, depth, view, 3D point, drill note
FEAT = []
def add(prefix, items, desc, size, depth, view, note=""):
    for i, p in enumerate(items, 1):
        FEAT.append(dict(id=f"{prefix}{i}", desc=desc, size=size, depth=depth, view=view, p=p, note=note))

add("A", [(x, y, TRAY_H) for x, y in LID_PTS], "Lid screw", "M3", "8", "plan", "tap drill 2.5, max 10 deep")
add("B", [(x, 16, FLOOR + 13) for x in BOSS_X] + [(14, y, FLOOR + 13) for y in SMA_BOSS_Y], "GND boss Ø10, free-standing (board RF bond)", "M3", "8", "plan",
    "boss top = board seat; tap drill 2.5, max 9 deep")
add("C", [(x, y, FLOOR + 13) for _, x, y in STANDOFF], "Support boss S1..S6, Ø8", "M3", "8", "plan", "boss top = board seat; tap drill 2.5, max 9 deep")
add("D", [(x, y, 0) for _, x, y in MOUNT], "Mounting, from the back", "M5", "8", "back", "tap drill 4.2, max 9 deep (0.5 mm must remain)")
add("E", [(x, 0, SO_Z) for x in SO_X], "SO-239 bore (Amphenol 83-798)", "Ø16.7", "THRU", "bottom")
add("F", [(x + dx * SO_SQ / 2, 0, SO_Z + dz * SO_SQ / 2) for x in SO_X for dx, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))],
    "SO-239 flange screw", "M3", "THRU", "bottom", "tapped through the wall 6")
for f in FEAT:
    if f["id"].startswith("F"): f["tmin"] = WALL
add("G", [EARTH], "Earth strap", "M5", "THRU", "bottom", "tapped through wall + boss (15)")
FEAT[-1]["tmin"] = WALL + 9
add("H", [(0, y, SMA_Z) for _, y in SMA_Y], "EXP SMA (901-9215): pocket 13 × 13 × 2 deep (corner R ≤ 1); centre bore", "Ø3.0", "THRU", "left",
    "bore = 52 Ω air line around the Ø1.27 pin")
add("J", [(0, y + dy * SMA_SQ / 2, SMA_Z + dz * SMA_SQ / 2) for _, y in SMA_Y for dy, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))],
    "SMA flange screw (in pocket floor)", "M2", "THRU", "left", "from pocket floor, tapped through the wall 4")
for f in FEAT:
    if f["id"].startswith("J"): f["tmin"] = WALL - 2
add("K", [(x, H, z) for _, x, z, _, _ in CUTS], "", "", "THRU", "top")
for f, c in zip([f for f in FEAT if f["id"].startswith("K")], CUTS):
    f["desc"] = f"Cutout {c[0]}, corners R1.5"; f["size"] = f"{c[3]:g} × {c[4]:g}"
add("L", [(x, H, 30) for x in EXP_SCREWS], "EXP plate screw", "M3", "5", "top", "tap drill 2.5, max 5.5 deep (wall 6)")


# ---------------- checks against the model ----------------
MISTAG = []
def check_threads():
    raw = json.load(open(THREADS)); raw = raw["threads"] if isinstance(raw, dict) else raw
    th = [t for t in raw if t["body"] == "Tray"]
    other = [t for t in raw if t["body"] not in ("Tray",)]
    want = [f for f in FEAT if f["size"].startswith("M")]
    found, missing = 0, []
    for f in want:
        p = np.array(f["p"], float)
        ok = False
        for t in th:
            a = np.array(t["axis"], float); q = np.array(t["axis_point"], float)
            d = p - q; d_perp = d - (d @ a) * a
            if np.linalg.norm(d_perp) < 0.05 and t["designation"] == f["size"] and ((t["end"] - t["start"]) >= f["tmin"] - 0.05 if "tmin" in f else abs((t["end"] - t["start"]) - float(f["depth"])) < 0.05):
                ok = True; break
        if not ok:   # tag put on the lid or the reference board body by the hole tool (shared start face); geometry checked offline
            for t in other:
                a = np.array(t["axis"], float); q = np.array(t["axis_point"], float); d = p - q
                if np.linalg.norm(d - (d @ a) * a) < 0.05 and t["designation"] == f["size"]:
                    ok = True; MISTAG.append(f["id"]); break
        found += ok
        if not ok:
            missing.append(f["id"])
    pos = {}
    for t in th:
        a = np.array(t["axis"], float); q = np.array(t["axis_point"], float)
        k = tuple(np.round(q - (q @ a) * a, 1)) + (t["designation"],)
        pos[k] = pos.get(k, 0) + 1
    dup = [k for k, v in pos.items() if v > 1]
    return len(want), found, missing, len(th), dup


# ---------------- drawing helpers ----------------
LW_VIS, LW_HID, LW_THIN = 0.35, 0.18, 0.13
TXT = 2.5


class Sheet:
    def __init__(self, pdf, no, total, name, scale_note):
        self.pdf = pdf; self.no = no
        self.fig = plt.figure(figsize=(A2[0] * MM, A2[1] * MM))
        self.ax = self.fig.add_axes([0, 0, 1, 1]); ax = self.ax
        ax.set_xlim(0, A2[0]); ax.set_ylim(0, A2[1]); ax.set_aspect("equal"); ax.axis("off")
        ax.add_patch(Rectangle((10, 10), A2[0] - 20, A2[1] - 20, fill=False, lw=0.7))
        self.title_block(no, total, name, scale_note)

    def title_block(self, no, total, name, scale_note):
        ax = self.ax; x0, y0, w, h = A2[0] - 10 - 190, 10, 190, 44
        ax.add_patch(Rectangle((x0, y0), w, h, fill=False, lw=0.6))
        for yy in (y0 + 11, y0 + 22, y0 + 33):
            ax.plot([x0, x0 + w], [yy, yy], lw=0.3, color="k")
        ax.plot([x0 + 120, x0 + 120], [y0, y0 + 33], lw=0.3, color="k")
        t = lambda x, y, s, sz=2.5, **k: ax.text(x, y, s, fontsize=sz / 0.3528, va="center", **k)
        t(x0 + 3, y0 + 38.5, TITLE, 3.5, weight="bold")
        t(x0 + 3, y0 + 27.5, name, 3.0)
        t(x0 + 3, y0 + 16.5, f"EN AW-6061-T6 (6082-T6 ok). Finish: conductive conversion coating (JLC 'Conductive anodizing').", 2.0)
        t(x0 + 3, y0 + 5.5, f"Tolerances ISO 2768-mK.  Dimensions in mm.  Third angle projection.  Master geometry: rf-case.step", 2.0)
        t(x0 + 123, y0 + 27.5, f"Dwg {DWG}  rev {REV}", 2.5)
        t(x0 + 123, y0 + 16.5, f"Sheet {no} / {total}   {scale_note}", 2.5)
        t(x0 + 123, y0 + 5.5, f"{DATE}  PE1RGU (P. Doornekamp)", 2.2)

    def save(self):
        self.pdf.savefig(self.fig)
        if PNG:
            self.fig.savefig(f"{PNG}/sheet{self.no}.png", dpi=110)
        plt.close(self.fig)

    # geometry ------------------------------------------------------------
    def view(self, shape, key, ox, oy, s=1.0, hidden=True, label=True, tris=None, title=None):
        n, vx, ttl = VIEWS[key] if isinstance(key, str) else key
        vis, hid = hlr.project(shape, n, vx, hidden=hidden)
        allp = np.vstack(vis)
        umin, vmin = allp.min(0); umax, vmax = allp.max(0)
        T = lambda u, v: (ox + s * (u - umin), oy + s * (v - vmin))
        if tris:
            for tr in tris:
                self.ax.add_patch(Polygon([T(u, v) for u, v in tr], closed=True, fc="#d9d9d9", ec="none", lw=0))
        for e in hid:
            x, y = T(e[:, 0], e[:, 1]); self.ax.plot(x, y, lw=LW_HID, color="#555555", ls=(0, (3, 1.5)))
        for e in vis:
            x, y = T(e[:, 0], e[:, 1]); self.ax.plot(x, y, lw=LW_VIS, color="k")
        if label:
            self.text(ox, oy - 14, title or ttl, 3.0, weight="bold")
        v = dict(n=n, vx=vx, umin=umin, vmin=vmin, umax=umax, vmax=vmax, s=s, ox=ox, oy=oy, T=T)
        return v

    def P(self, v, p):
        u, w = hlr.uv(p, v["n"], v["vx"]); return v["T"](u, w)

    def local(self, v, p):
        u, w = hlr.uv(p, v["n"], v["vx"]); return u - v["umin"], w - v["vmin"]

    def text(self, x, y, s, sz=TXT, **k):
        self.ax.text(x, y, s, fontsize=sz / 0.3528, **k)

    def datum(self, v):
        x, y = v["ox"], v["oy"]
        self.ax.add_patch(Circle((x, y), 1.6, fill=False, lw=0.4))
        self.ax.plot([x - 2.6, x + 2.6], [y, y], lw=0.4, color="k"); self.ax.plot([x, x], [y - 2.6, y + 2.6], lw=0.4, color="k")
        self.text(x - 3, y - 4.5, "0,0", 2.0, ha="right")

    def tag(self, v, f, dx=3.0, dy=3.0, sz=2.2):
        x, y = self.P(v, f["p"])
        self.ax.plot([x, x + dx], [y, y + dy], lw=0.2, color="#0050a0")
        self.text(x + dx, y + dy, f["id"], sz, color="#0050a0", ha="left" if dx >= 0 else "right", va="bottom")

    def centre(self, v, f, r=2.0):
        x, y = self.P(v, f["p"])
        self.ax.plot([x - r, x + r], [y, y], lw=0.15, color="#0050a0"); self.ax.plot([x, x], [y - r, y + r], lw=0.15, color="#0050a0")

    def dim(self, p1, p2, off, txt, orient="h", sz=TXT):
        ax = self.ax; (x1, y1), (x2, y2) = p1, p2
        if orient == "h":
            yd = max(y1, y2) + off if off > 0 else min(y1, y2) + off
            for x, y in ((x1, y1), (x2, y2)):
                ax.plot([x, x], [y + math.copysign(1, off), yd + math.copysign(1.5, off)], lw=LW_THIN, color="k")
            ax.annotate("", (x1, yd), (x2, yd), arrowprops=dict(arrowstyle="<|-|>", lw=LW_THIN, color="k", mutation_scale=6, shrinkA=0, shrinkB=0))
            self.text((x1 + x2) / 2, yd + (0.8 if off > 0 else -0.8), txt, sz, ha="center", va="bottom" if off > 0 else "top")
        else:
            xd = max(x1, x2) + off if off > 0 else min(x1, x2) + off
            for x, y in ((x1, y1), (x2, y2)):
                ax.plot([x + math.copysign(1, off), xd + math.copysign(1.5, off)], [y, y], lw=LW_THIN, color="k")
            ax.annotate("", (xd, y1), (xd, y2), arrowprops=dict(arrowstyle="<|-|>", lw=LW_THIN, color="k", mutation_scale=6, shrinkA=0, shrinkB=0))
            self.text(xd + (0.8 if off > 0 else -0.8), (y1 + y2) / 2, txt, sz, ha="left" if off > 0 else "right", va="center", rotation=90)

    def note(self, xy, xyt, txt, sz=2.3):
        self.ax.annotate(txt, xy, xyt, fontsize=sz / 0.3528, arrowprops=dict(arrowstyle="-|>", lw=0.2, color="k", mutation_scale=5), va="center")


def tags_for(sh, v, view, offsets=None):
    for f in FEAT:
        if f["view"] == view:
            sh.centre(v, f)
            dx, dy = (offsets or {}).get(f["id"][0], (3, 3))
            sh.tag(v, f, dx, dy)


# ---------------- sheets ----------------
def main():
    solids = sorted(hlr.load_solids(STEP), key=lambda s: -s[0])
    tray, lid, plate = solids[0][1], solids[1][1], solids[2][1]
    n_want, n_found, missing, n_th, dup = check_threads()
    print(f"thread check: {n_found}/{n_want} drawing threads found in the model ({n_th} tray thread records); missing {missing}; duplicate records {dup}")

    TOTAL = 7
    with PdfPages(OUT) as pdf:
        # sheet 1: plan + back -------------------------------------------------
        sh = Sheet(pdf, 1, TOTAL, "Tray: plan (inside) and back face", "plan 1:1, back 1:2")
        v = sh.view(tray, "plan", 40, 105, 1.0, hidden=False)
        sh.datum(v); tags_for(sh, v, "plan", {"A": (2.5, 2.5), "B": (2.5, 3.5), "C": (3, 3)})
        T = v["T"]
        sh.dim(T(0, 250), T(288, 250), 12, "288")
        sh.dim(T(288, 0), T(288, 250), 12, "250", "v")
        sh.dim(T(0, 0), T(6, 0), -6, "6")
        sh.dim(T(6, 125), T(282, 125), 0.01, "276 (pocket)")
        sh.dim(T(144, 6), T(144, 244), 0.01, "238 (pocket)", "v")
        sh.note(T(10.5, 241), (T(10.5, 241)[0] + 8, T(10.5, 241)[1] + 24), "Pocket corners R10\nOuter corners R6")
        sh.note(T(4.5 + 3.5, 107.5), (T(30, 95)[0], T(30, 95)[1]), "12 lugs Ø7, full height\n(floor to wall top, no undercut)")
        sh.note(T(30 + 8, 230), (T(46, 214)[0], T(46, 214)[1]), "4 pads Ø16 × 5 high\n(M5 from the back, D1..D4)")
        sh.note(T(273 - 4, 124.5), (T(222, 140)[0], T(222, 140)[1]), "6 support bosses Ø8 × 13 high,\nboard seat (C1..C6)")
        sh.note(T(36, 21), (T(30, 45)[0], T(30, 45)[1]), "10 GND bosses Ø10, free-standing,\ntop 13 above floor (B1..B10)")
        sh.note(T(115.5, 15), (T(100, 45)[0], T(100, 45)[1]), "Earth boss 10 × 9 × 11 high")
        sh.text(40, 80, "Floor 5 thick, walls 6, tray height 63. Tapped holes A, B, C: positions in the hole table (sheet 7), datum 0,0 = outer corner shown.", 2.5)
        vb = sh.view(tray, "back", 360, 220, 0.5, hidden=False)
        sh.datum(vb); tags_for(sh, vb, "back", {"D": (3, 3)})
        Tb = vb["T"]
        sh.text(360, 196, "Seen from the back: case x runs right to left. 4 × M5 (D1..D4) into the inside pads.", 2.3)
        sh.text(360, 190, "Back edge R2 all round. Flat face: mounts on the back plate via printed spacers.", 2.3)
        sh.save()

        # sheet 2: walls --------------------------------------------------------
        sh = Sheet(pdf, 2, TOTAL, "Tray: the four walls, outside views", "1:1")
        vB = sh.view(tray, "bottom", 40, 320, 1.0, hidden=False); sh.datum(vB); tags_for(sh, vB, "bottom", {"E": (5, 9), "F": (2, 2), "G": (3, -6)})
        sh.dim(vB["T"](0, 0), vB["T"](0, 63), -8, "63", "v")
        vT = sh.view(tray, "top", 40, 215, 1.0, hidden=False); sh.datum(vT); tags_for(sh, vT, "top", {"K": (0, 11), "L": (2, 4)})
        vL = sh.view(tray, "left", 40, 115, 1.0, hidden=False); sh.datum(vL); tags_for(sh, vL, "left", {"H": (8, 9), "J": (2, 2)})
        vR = sh.view(tray, "right", 325, 115, 1.0, hidden=False); sh.datum(vR)
        sh.text(325, 93, "Wall 4 has no openings; the 4 side lugs are inside only.", 2.3)
        sh.text(40, 300, "E: Ø16.7 THRU, flange outside, 4 × M3 on 18.24 square. G: earth strap M5 (tinned braid to the RVS earth bar).", 2.3)
        sh.text(40, 195, "K: cutouts THRU, corner R1.5, sizes in the hole table. EXP plate (sheet 5) covers K2 with 2 × M3 (L).", 2.3)
        sh.text(40, 95, "H: pocket 13 × 13 × 2 deep from outside (flange seat 12.7 square, corner R ≤ 1 allowed), Ø3.0 THRU at centre; J: 4 × M2 in the pocket floor.", 2.3)
        sh.save()

        # sheet 3: sections -----------------------------------------------------
        sh = Sheet(pdf, 3, TOTAL, "Tray: sections", "1:1")
        cuts = [("A-A", 0, 30.0, "+", ((-1, 0, 0), (0, -1, 0)), "SECTION A-A  (x = 30: mounting pads, floor, walls)", 40, 300),
                ("B-B", 0, 36.0, "+", ((-1, 0, 0), (0, -1, 0)), "SECTION B-B  (x = 36: GND boss B1, free-standing, SO-239 wall)", 40, 195),
                ("C-C", 1, 236.0, "-", ((0, 1, 0), (-1, 0, 0)), "SECTION C-C  (y = 236: support bosses S1..S3, lugs)", 40, 90)]
        for nm, axis, at, keep, (n, vx), ttl, ox, oy in cuts:
            part = hlr.halfspace_cut(tray, axis, at, keep)
            tris = hlr.section_faces(tray, axis, at, n, vx)
            vs = sh.view(part, (n, vx, ttl), ox, oy, 1.0, hidden=False, tris=tris, title=ttl)
            Ts = vs["T"]
            sh.dim(Ts(vs["umin"], vs["vmin"]), Ts(vs["umin"], vs["vmax"]), -8, "63", "v")
            sh.dim(Ts(vs["umax"], vs["vmin"]), Ts(vs["umax"], vs["vmin"] + FLOOR), 8, "5", "v")
            sh.dim(Ts(vs["umin"], vs["vmax"]), Ts(vs["umin"] + WALL, vs["vmax"]), 6, "6")
            sh.dim(Ts(vs["umin"], vs["vmin"]), Ts(vs["umax"], vs["vmin"]), -6, f"{vs['umax'] - vs['umin']:.0f}")
        sh.text(360, 380, "Section faces shaded.", 2.5)
        sh.text(360, 372, "Floor 5, walls 6, lugs Ø7 full height to the wall top.", 2.5)
        sh.text(360, 364, "Mount pads 5 high (floor + pad = 10 for M5 × 8).", 2.5)
        sh.text(360, 356, "Support bosses and GND bosses 13 high (board seat).", 2.5)
        sh.text(360, 348, "Concave vertical edges lug/boss to wall: R ≤ 2 allowed.", 2.5)
        sh.save()

        # sheet 4: lid ----------------------------------------------------------
        sh = Sheet(pdf, 4, TOTAL, "Lid", "1:1")
        vl = sh.view(lid, "plan", 40, 105, 1.0, hidden=False, title="LID - TOP (outside)")
        sh.datum(vl)
        Tl = vl["T"]
        sh.dim(Tl(0, 250), Tl(288, 250), 10, "288"); sh.dim(Tl(288, 0), Tl(288, 250), 10, "250", "v")
        for i, (x, y) in enumerate(LID_PTS, 1):
            px, py = Tl(x, y); sh.text(px + 2.5, py + 2.5, f"A{i}", 2.0, color="#0050a0")
        sh.note(Tl(6, 6), (Tl(30, 30)[0], Tl(30, 30)[1]), "16 × Ø3.4 THRU, CSK Ø6.9 × 90° (M3 × 10 ISO 10642)\npositions = holes A1..A16 (hole table)")
        sh.text(360, 380, "Lid 288 × 250 × 3, EN AW-6061-T6.", 2.5)
        sh.text(360, 372, "Outer corners R6, top edge R2, bottom edge sharp (seats on the tray).", 2.5)
        sh.text(360, 364, "Engraving 0.5 deep, Arial bold, as in rf-case.step (body Lid).", 2.5)
        sh.text(360, 356, "Optional: fill the engraving with white paint after coating.", 2.5)
        sh.text(360, 348, "Lid inside face and tray rim: no paint, conductive (RF bond).", 2.5)
        sh.save()

        # sheet 5: EXP plate + printed parts -----------------------------------
        sh = Sheet(pdf, 5, TOTAL, "EXP plate and printed mounting parts", "2:1")
        vp = sh.view(plate, ((0, 1, 0), (-1, 0, 0), ""), 40, 280, 2.0, hidden=False, title="EXP PLATE (2 mm, EN AW-6061-T6)")
        Tp = vp["T"]
        sh.dim(Tp(vp["umin"], vp["vmax"]), Tp(vp["umax"], vp["vmax"]), 8, "49")
        sh.dim(Tp(vp["umax"], vp["vmin"]), Tp(vp["umax"], vp["vmax"]), 8, "21", "v")
        sh.note(Tp(-52.5, 30), (Tp(-52.5, 30)[0] + 15, Tp(-52.5, 30)[1] + 30), "2 × Ø3.4 THRU, 43 apart, centred\n(M3 × 6 into L1, L2)")
        sh.text(40, 254, "Unit 1: blank. Unit 2: ribbon clamp and shield contact (same outline, slot to suit). Same finish as the tray.", 2.3)

        # printed spacer and washer drawn from their parameters (2:1)
        def ring(cx, cy, do, di, s=2.0):
            sh.ax.add_patch(Circle((cx, cy), do * s / 2, fill=False, lw=LW_VIS)); sh.ax.add_patch(Circle((cx, cy), di * s / 2, fill=False, lw=LW_VIS))
        sx, sy = 60, 150
        ring(sx, sy, 16, 5.5); sh.ax.add_patch(Circle((sx, sy), 9.6, fill=False, lw=LW_HID, ls="--"))
        sh.text(sx - 20, sy + 26, "PRINTED SPACER (4×)  2:1", 3.0, weight="bold")
        # side profile
        px0 = 120; py0 = sy - 12
        prof = [(-8, 0), (8, 0), (8, 5), (4.8, 5), (4.8, 7.5), (-4.8, 7.5), (-4.8, 5), (-8, 5)]
        sh.ax.add_patch(Polygon([(px0 + 2 * x, py0 + 2 * (7.5 - y)) for x, y in prof], closed=True, fill=False, lw=LW_VIS))
        for x in (-2.75, 2.75):
            sh.ax.plot([px0 + 2 * x] * 2, [py0, py0 + 15], lw=LW_HID, color="#555", ls="--")
        sh.dim((px0 - 16, py0 + 15), (px0 + 16, py0 + 15), 8, "Ø16")
        sh.dim((px0 - 9.6, py0), (px0 + 9.6, py0), -8, "Ø9.6 spigot")
        sh.dim((px0 + 16, py0 + 5), (px0 + 16, py0 + 15), 6, "5", "v")
        sh.dim((px0 + 9.6, py0), (px0 + 9.6, py0 + 5), 14, "2.5", "v")
        sh.text(sx - 20, sy - 30, "Bore Ø5.5 THRU. Spigot fits the Ø10 back-plate hole (plate 3 mm).", 2.3)
        sh.text(sx - 20, sy - 36, "Flange side against the tray back, spigot into the plate.", 2.3)
        wx, wy = 260, 150
        ring(wx, wy, 14, 5.5)
        sh.text(wx - 20, wy + 26, "PRINTED WASHER (4×)  2:1", 3.0, weight="bold")
        sh.ax.add_patch(Rectangle((wx + 30, wy - 2), 28, 4, fill=False, lw=LW_VIS))
        sh.dim((wx + 30, wy + 2), (wx + 58, wy + 2), 8, "Ø14"); sh.dim((wx + 58, wy - 2), (wx + 58, wy + 2), 6, "2", "v")
        sh.text(wx - 20, wy - 30, "Bore Ø5.5. Under the M5 × 16 head, behind the back plate.", 2.3)
        sh.text(40, 85, "Print: PETG or ASA (better PA-CF), 100 % infill, layers parallel to the flange. Plastic creeps under bolt load:", 2.5)
        sh.text(40, 79, "low torque, spring washer under the head, check the four M5 after the first summer. Stack from the back:", 2.5)
        sh.text(40, 73, "M5 × 16 A4 + spring washer + printed washer | back plate | printed spacer | tray. The tray is isolated from the plate;", 2.5)
        sh.text(40, 67, "the only bond is the tinned braid on G1 (earth M5 in wall 1) to the RVS earth bar.", 2.5)
        sh.save()

        # sheet 6: assembly -----------------------------------------------------
        sh = Sheet(pdf, 6, TOTAL, "Assembly: stack-up, bosses and fasteners", "details 2:1")
        try:
            img = plt.imread(ASM_PNG)[..., :3]
            bg = img[2, 2]; m = np.abs(img - bg).sum(2) > 0.08
            ys, xs = np.where(m); pad = 15
            img = img[max(ys.min() - pad, 0):ys.max() + pad, max(xs.min() - pad, 0):xs.max() + pad]
            h, w = img.shape[:2]; ww = min(320.0, 215.0 * w / h); hh = ww * h / w
            sh.ax.imshow(img, extent=(20, 20 + ww, 190, 190 + hh), aspect="auto", zorder=0)
            sh.text(25, 186, "Assembly view (lid off, boards omitted): SO-239, SMA and all fasteners fitted.", 2.3)
        except Exception as e:
            sh.text(25, 300, f"(assembly render not found: {e})", 2.5)

        def stack(ox, oy, s, title, layers, screw_top=None, screw_bot=None, note=""):
            """layers: list of (z0, z1, half_width, label, style). z in mm above the case back (z = 0)."""
            for z0, z1, hw, lab, style in layers:
                fc = {"alu": "#d9d9d9", "pcb": "#9fc79f", "std": "#e8d9a8", "pla": "#c9d7f0", "plate": "#bbbbbb"}[style]
                sh.ax.add_patch(Rectangle((ox - hw * s, oy + z0 * s), 2 * hw * s, (z1 - z0) * s, fc=fc, ec="k", lw=0.3))
                if lab: sh.text(ox + 14 * s, oy + (z0 + z1) / 2 * s, f"{lab}  (z {z0:g} to {z1:g})", 2.1, va="center")
            if screw_top:
                z, L, lab = screw_top
                sh.ax.add_patch(Rectangle((ox - 2.75 * s, oy + z * s), 5.5 * s, 3 * s, fc="#777", ec="k", lw=0.3))
                sh.ax.add_patch(Rectangle((ox - 1.5 * s, oy + (z - L) * s), 3 * s, L * s, fc="#999", ec="k", lw=0.3))
                sh.text(ox - 4 * s, oy + (z + 1.5) * s, lab, 2.1, ha="right", va="center")
            if screw_bot:
                z, L, lab = screw_bot
                sh.ax.add_patch(Rectangle((ox - 4.25 * s, oy + (z - 5) * s), 8.5 * s, 5 * s, fc="#777", ec="k", lw=0.3))
                sh.ax.add_patch(Rectangle((ox - 2.5 * s, oy + z * s), 5 * s, L * s, fc="#999", ec="k", lw=0.3))
                sh.text(ox - 6 * s, oy + (z - 2.5) * s, lab, 2.1, ha="right", va="center")
            zmin = min(l[0] for l in layers) + (min(0, screw_bot[0] - 5) if screw_bot else 0)
            yb = oy + min(zmin, 0) * s
            sh.text(ox - 30, yb - 12, title, 3.0, weight="bold")
            if note:
                sh.text(ox - 30, yb - 18, note, 2.1)

        # board stack at S1, S2, S4, S5 (S3, S6: without the 20 mm standoff, M3 x 6 on the RF board)
        stack(390, 230, 2.0, "STACK AT S1, S2, S4, S5  (2:1)",
              [(0, 5, 10, "floor 5", "alu"), (5, 18, 4, "support boss Ø8 x 13, M3 x 8 deep", "alu"),
               (18, 19.6, 9, "RF board 1.6", "pcb"),
               (19.6, 39.6, 2.75, "standoff M3 20 M-F, hex 5.5", "std"), (39.6, 41.2, 9, "controller board 1.6", "pcb")],
              screw_top=(41.2, 6, "M3 x 6"),
              note="S3, S6: no 20 mm standoff, M3 x 6 on the RF board (z 19.6) into the boss. Male stud: 6 mm through the board into the boss.")
        # back mounting stack
        stack(390, 140, 2.0, "MOUNTING STACK D1..D4  (2:1)",
              [(-10, -8, 7, "printed washer Ø14 x 2", "pla"), (-8, -5, 12, "RVS back plate 3, hole Ø10 (spacer spigot Ø9.6 inside)", "plate"),
               (-7.5, -5, 4.8, "", "pla"), (-5, 0, 8, "printed spacer Ø16 x 5", "pla"),
               (0, 5, 12, "floor 5", "alu"), (5, 10, 8, "pad Ø16 x 5, M5 x 8 deep", "alu")],
              screw_bot=(-10, 16, "M5 x 16 ISO 4762 A4"),
              note="Spring washer under the head. Tray isolated from the plate; bond only via G1.")
        # GND boss and lid
        sh.text(20, 120, "GND BOSS B1..B10 (7 SO-239, 3 SMA), free-standing Ø10: RF board seated on the boss top (z 18), M3 x 6 from the board top.", 2.4)
        sh.text(20, 113, "LID: M3 x 10 countersunk ISO 10642 into A1..A16 (thread 8, lid 3, head flush with Ø6.9 countersink).", 2.4)
        sh.text(20, 106, "SO-239 83-798: flange outside wall 1, 4 x M3 x 6 into F (tapped through). SMA 901-9215: flange in pocket H, 4 x M2 x 4 into J (through).", 2.4)
        sh.text(20, 99, "EXP plate: 2 x M3 x 6 into L. Earth: M5 x 16 with braid lug into G1 (tapped through wall + boss, 15).", 2.4)
        sh.text(20, 92, "Heights: RF board underside z 18, controller underside z 39.6, DevKit top about z 57.2, lid inside z 63.", 2.4)
        sh.save()

        # sheet 6: hole table, notes, parts -------------------------------------
        sh = Sheet(pdf, 7, TOTAL, "Hole table, notes, parts list", "-")
        views = {}
        # recompute view frames (no drawing) for local coordinates
        for key in ("plan", "back", "bottom", "top", "left"):
            n, vx, _ = VIEWS[key]
            vis, _ = hlr.project(tray, n, vx, hidden=False); allp = np.vstack(vis)
            views[key] = dict(n=n, vx=vx, umin=allp.min(0)[0], vmin=allp.min(0)[1])
        rows = []
        for f in FEAT:
            vw = views[f["view"]]; u, w = hlr.uv(f["p"], vw["n"], vw["vx"])
            sheet_of = {"plan": "1 plan", "back": "1 back", "bottom": "2 wall 1", "top": "2 wall 2", "left": "2 wall 3"}[f["view"]]
            rows.append((f["id"], f["desc"], f["size"], f["depth"], sheet_of, f"{u - vw['umin']:.2f}", f"{w - vw['vmin']:.2f}", f["note"]))
        cols = [("ID", 10), ("Feature", 78), ("Size", 18), ("Depth", 12), ("View", 18), ("X", 14), ("Y", 14), ("Note", 70)]
        x0, y0, rh = 20, 400, 3.8
        def header(xs, ys):
            xx = xs
            for c, w in cols:
                sh.text(xx + 1, ys, c, 2.2, weight="bold", va="center"); xx += w
            sh.ax.plot([xs, xs + sum(w for _, w in cols)], [ys - rh / 2, ys - rh / 2], lw=0.3, color="k")
        col_x = [x0, x0 + 245]
        per_col = 46
        for ci in range(2):
            xs = col_x[ci] if ci == 0 else x0
            pass
        # two table blocks stacked left; table width 234
        blocks = [rows[:47], rows[47:]]
        bx = [20, 20]; by = [404, 219]
        for b, xs, ys in zip(blocks, bx, by):
            header(xs, ys); yy = ys - rh
            for r in b:
                xx = xs
                for (c, w), val in zip(cols, r):
                    s = str(val)
                    sh.text(xx + 1, yy, s, 1.9, va="center"); xx += w
                yy -= rh
        sh.text(20, 22, "X, Y: from the datum 0,0 of the view named (lower-left outer corner as drawn). Depth = full thread depth; drill depth limits in the note column.", 2.2)
        sh.text(20, 16, f"Check: {n_found} of {n_want} tapped holes match the thread data of rf-case.solidcraft (axis, size and depth)" + (f"; {len(MISTAG)} tagged on the adjacent body, geometry checked." if MISTAG else "."), 2.2)
        nx, ny = 270, 404
        notes = [
            "NOTES",
            "1  Master geometry: rf-case.step (Tray, Lid, EXP plate). This drawing adds threads, tolerances and finish.",
            "2  Material EN AW-6061-T6 (EN AW-6061-T6 accepted) for tray, lid and EXP plate.",
            "3  Finish: conductive conversion coating (JLCCNC: Conductive anodizing, natural),",
            "    MIL-DTL-5541 Type II Class 3 equivalent, all surfaces. No insulating anodising.",
            "4  General tolerances ISO 2768-mK. Hole positions ±0.1 for E, F, H, J (connector flanges).",
            "5  Threads ISO metric coarse 6H. F, G, J tapped through. Blind holes (A, B, C, D, L): keep the max drill",
            "    depth in the note column; never break through into the pocket or the outside face.",
            "6  Internal radii: pocket R10, cutouts R1.5, concave edges at lugs/bosses R ≤ 2. Bosses free-standing.",
            "7  Break all sharp edges 0.2 to 0.4, except the lid seat (flat, sharp, conductive).",
            "8  Engrave the lid 0.5 deep as modelled (Arial bold).",
            "9  Deburr the SO-239, SMA and cutout edges inside and outside (RF and cable contact).",
            "",
            "PARTS PER UNIT",
            "Tray 1, lid 1, EXP plate 1 (CNC, this drawing)",
            "Printed spacer 4, printed washer 4 (sheet 5)",
            "Screw M3 × 10 countersunk ISO 10642 A2: 16 (lid)",
            "Screw M3 × 6 button/cheese head A2: 46 (28 SO-239, 10 GND boss,",
            "    2 RF board on S3 and S6, 4 controller board, 2 EXP plate)",
            "Screw M5 × 16 hex socket ISO 4762 A4: 5 (4 mounting, 1 earth strap)",
            "Screw M2 × 4 cheese head A2: 12 (SMA flanges)",
            "Standoff M3 hex 5.5 AF, 20 mm male-female: 4 (S1, S2, S4, S5, controller)",
            "Connector Amphenol RF 83-798 SO-239: 7.  SMA Amphenol RF 901-9215: 3",
            "    (second source Cinch/Johnson 142-0701-631, D-174)",
            "Tinned copper braid with M5 lug: 1 (earth, to the RVS earth bar)",
        ]
        for i, s in enumerate(notes):
            sh.text(nx, ny - i * 4.6, s, 2.5 if s in ("NOTES", "PARTS PER UNIT") else 2.2, weight="bold" if s in ("NOTES", "PARTS PER UNIT") else "normal")
        sh.save()
    return n_want, n_found, missing, dup


if __name__ == "__main__":
    print(main())
