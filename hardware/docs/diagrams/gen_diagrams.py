#!/usr/bin/env python3
"""Shack Relay Matrix rev C: logic, timing and flow diagrams for the detailed design document.
Run from this folder: python3 gen_diagrams.py  -> SVG (editable text) and PNG (200 dpi) per diagram.
Logic symbols: IEC 60617-12 rectangles with qualifying symbols (&, >=1, 1, S/R/C1/1D); the output indicator is the
polarity triangle, as in the KiCad schematics. Timing values: design log C-19, M-10, C-20, D-63 and verify_system.py
section 5 (link message 4 ms, K0 operate plus bounce 12 ms, release 0 to 6 ms, minimum end wait 100 ms).
Waveforms are drawn from these values: they show order and margins, not measured data."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, FancyBboxPatch, Circle
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "svg.fonttype": "none"})
INK, MUTE, ACC, SAFE, RED = "#1d1d1f", "#6b6b6b", "#1f4e9c", "#0b6b2e", "#b3261e"
FOOT = "PE1RGU Shack Relay Matrix rev C  |  {name}  |  2026-10-06"
OUT = []

def canvas(w, h, title, name):
    fig = plt.figure(figsize=(w / 25.4, h / 25.4))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, w); ax.set_ylim(h, 0); ax.axis("off")
    ax.text(8, 9, title, fontsize=11, fontweight="bold", color=INK, va="center")
    ax.text(8, h - 5, FOOT.format(name=name), fontsize=6.5, color=MUTE, va="center")
    return fig, ax

def save(fig, name):
    fig.savefig(f"{name}.svg"); fig.savefig(f"{name}.png", dpi=200); plt.close(fig); OUT.append(name)

# ------------------------------------------------------------------ logic diagram helpers (IEC 60617-12)
def wire(ax, *pts, c=INK, lw=0.9, dash=False):
    xs, ys = zip(*pts); ax.plot(xs, ys, color=c, lw=lw, ls=(0, (3, 2)) if dash else "-", solid_capstyle="butt")

def dot(ax, x, y, c=INK): ax.add_patch(Circle((x, y), 0.7, color=c, zorder=5))

def gate(ax, x, y, q, nin, ref, part, neg=False, h=None, w=12, pins=None):
    """Gate body with its top-left corner at (x, y). Returns input points (top to bottom) and the output point."""
    h = h or max(10, 5 * nin + 2)
    ax.add_patch(Rectangle((x, y), w, h, fill=True, fc="#fff8e1", ec=INK, lw=1.0))
    ax.text(x + w / 2, y + 3.2, q, ha="center", va="center", fontsize=9)
    ax.text(x + w / 2, y - 2.0, f"{ref}  {part}", ha="center", va="center", fontsize=6.3, color=ACC)
    ins = [(x - 5, y + h * (i + 1) / (nin + 1)) for i in range(nin)]
    for px, py in ins: wire(ax, (px, py), (x, py))
    oy = y + h / 2
    if neg:
        ax.add_patch(Polygon([(x + w, oy), (x + w + 2.2, oy), (x + w, oy - 1.6)], closed=True, fc="white", ec=INK, lw=0.8))
    wire(ax, (x + w, oy), (x + w + 6, oy))
    if pins:
        for (px, py), t in zip(ins, pins): ax.text(x + 1, py, t, va="center", fontsize=6)
    return ins, (x + w + 6, oy)

def label(ax, x, y, t, side="l", c=INK, size=7.2):
    ax.text(x - 1 if side == "l" else x + 1, y, t, ha="right" if side == "l" else "left", va="center", fontsize=size, color=c)

def block(ax, x, y, w, h, title, sub=None, fc="#eef3fb", ec=ACC):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=1.0))
    ax.text(x + w / 2, y + (h / 2 if not sub else h / 2 - 2.2), title, ha="center", va="center", fontsize=7.5)
    if sub: ax.text(x + w / 2, y + h / 2 + 2.6, sub, ha="center", va="center", fontsize=6.2, color=MUTE)

def note(ax, x, y, lines, size=6.8):
    for i, t in enumerate(lines): ax.text(x, y + i * 4.0, t, fontsize=size, color=INK, va="top")

# ------------------------------------------------------------------ L1: SAFE loop, system view
def l1_safe_loop():
    fig, ax = canvas(277, 170, "L1  SAFE loop: one series current loop over Cat6 #1 pair 3 (D-62, D-74, D-80)", "L1_safe_loop")
    ax.add_patch(Rectangle((8, 18), 110, 120, fill=False, ec=MUTE, lw=0.7, ls=(0, (4, 3))))
    ax.text(10, 22, "Shack interface", fontsize=8, fontweight="bold", color=MUTE)
    ax.add_patch(Rectangle((160, 18), 110, 120, fill=False, ec=MUTE, lw=0.7, ls=(0, (4, 3))))
    ax.text(162, 22, "Matrix box, controller board", fontsize=8, fontweight="bold", color=MUTE)
    ax.text(139, 38, "Cat6 #1 UTP\npair 3 (pins 3/6)", ha="center", fontsize=6.8, color=MUTE)
    # loop path: top run (out) and bottom run (return)
    yt, yb = 48, 108
    block(ax, 16, yt - 7, 38, 14, "Current source", "Q31, Q32, R33: 8.8 to 12.5 mA")
    block(ax, 62, yt - 7, 24, 14, "KILL switch", "J2, NC = run")
    block(ax, 172, yt - 7, 32, 14, "U3 opto LED", "VO2611: KILL = no current")
    block(ax, 216, yt + 18, 34, 14, "READY switch U6", "TLP176AM, form A")
    block(ax, 62, yb - 7, 30, 14, "Sense R36 100R", "Q34: SAFE_LOST")
    wire(ax, (35, yt + 7), (35, yb), (62, yb), c=SAFE, lw=1.6)
    wire(ax, (54, yt), (62, yt), c=SAFE, lw=1.6); wire(ax, (86, yt), (172, yt), c=SAFE, lw=1.6)
    wire(ax, (204, yt), (233, yt), (233, yt + 18), c=SAFE, lw=1.6)
    wire(ax, (233, yt + 32), (233, yb), (92, yb), c=SAFE, lw=1.6)
    ax.annotate("", xy=(150, yt), xytext=(128, yt), arrowprops=dict(arrowstyle="->", color=SAFE, lw=1.4))
    ax.annotate("", xy=(128, yb), xytext=(150, yb), arrowprops=dict(arrowstyle="->", color=SAFE, lw=1.4))
    ax.text(139, yt - 3, "L3P", ha="center", fontsize=6.5, color=SAFE); ax.text(139, yb - 3, "L3N", ha="center", fontsize=6.5, color=SAFE)
    # control inputs and outputs
    wire(ax, (35, yt - 7), (35, 30)); label(ax, 35, 28, "SW_STOP_N (U5 IO0_0), pull-up R35: on in reset (D-68)", "r", size=6.3)
    wire(ax, (233, yt + 18 + 14 + 0), (233, yt + 32))
    wire(ax, (250, yt + 25), (258, yt + 25)); label(ax, 258, yt + 25, "READY_ON", "r", size=6.5)
    ax.text(203, yt + 40, "READY = NOR(MCU_EN_N, FAULT) AND RF_A2_N (U15, U16)\nKILL is not an input: the loop can start", ha="center", fontsize=6.2, color=MUTE, va="top")
    wire(ax, (204, yt - 4), (212, yt - 4), (212, 30)); label(ax, 212, 28, "KILL to the RLY_EN gate U14 (L2)", "r", size=6.3)
    wire(ax, (77, yb + 7), (77, 124)); label(ax, 77, 126, "SAFE_LOST: high = no current (L3, IO21)", "r", size=6.3)
    note(ax, 8, 145, [
        "Any break stops the current (wired AND): shack supply off, KILL pressed, software stop, cable cut, box dead, box FAULT or MCU_EN_N high,",
        "or RF on the receive-only column A2 (D-104, SR-01 H2).",
        "Box: no current = KILL high = RLY_EN low: expanders in reset, +12V_SW off, all row relays and R2/R3 K0 open (F12).",
        "Shack: no current = SAFE_LOST high: the SAFE latch sets; TX_EN low inhibits every radio until RESET with the current back (D-75)."])
    save(fig, "L1_safe_loop")

# ------------------------------------------------------------------ L2: box safety gate
def l2_box_gate():
    fig, ax = canvas(277, 160, "L2  Box safety gate and READY switch (controller board, D-59, D-62, D-104)", "L2_box_safety_gate")
    inp = lambda y, t, x_end: (wire(ax, (8, y), (x_end, y)), ax.text(8, y - 1.6, t, fontsize=6.6))
    # supervisor
    block(ax, 70, 26, 34, 22, "U12 TPS3823A-33", "supervisor 2.93 V, watchdog", fc="#fff8e1", ec=INK)
    inp(31, "+3V3", 70); inp(43, "WDI (GPIO1), 1k pull-down", 70)
    # fault latch U13
    x, y = 128, 24
    ax.add_patch(Rectangle((x, y), 18, 28, fc="#fff8e1", ec=INK, lw=1.0)); ax.text(x + 9, y - 2.0, "U13  74LVC1G74", ha="center", fontsize=6.3, color=ACC)
    for i, (t, low) in enumerate((("R", True), ("S", True), ("C1", False), ("1D", False))):
        py = y + 5 + i * 6; ax.text(x + 1.2, py, t, va="center", fontsize=7); wire(ax, (x - 5, py), (x, py))
        if low: ax.add_patch(Polygon([(x, py), (x - 2.2, py), (x, py - 1.6)], closed=True, fc="white", ec=INK, lw=0.8))
    ax.text(x - 6, 29, "1", ha="right", va="center", fontsize=6.6); ax.text(x - 6, 47, "0", ha="right", va="center", fontsize=6.6)
    wire(ax, (104, 37), (112, 37), (112, 35), (x - 5, 35)); ax.text(105, 33.6, "RESET_N", fontsize=6.2)
    inp(62, "LATCH_CLR (GPIO3), 100k pull-down", 118); wire(ax, (118, 62), (118, 41), (x - 5, 41))
    # FAULT bus (outer, x 168) and MCU_EN_N bus (inner, x 174); gates at x 184
    G, XF, XM = 184, 168, 174
    wire(ax, (x + 18, 29), (XF, 29)); ax.text(x + 20, 27, "FAULT (Q)", fontsize=6.4)
    i15, o15 = gate(ax, G, 40, "\u22651", 2, "U15", "74LVC1G02", neg=True, h=14)
    i14, o14 = gate(ax, G, 74, "\u22651", 3, "U14", "74LVC1G27", neg=True, h=20)
    # inputs: U15 (FAULT, MCU_EN_N), U14 (MCU_EN_N, FAULT, KILL)
    wire(ax, (XF, 29), (XF, i14[1][1]), i14[1]); wire(ax, (XF, i15[0][1]), i15[0]); dot(ax, XF, i15[0][1])
    ym = (i14[1][1] + i14[2][1]) / 2 + 9
    inp(ym, "MCU_EN_N (GPIO4), 100k pull-up", XM); wire(ax, (XM, ym), (XM, i15[1][1]), i15[1]); wire(ax, (XM, i14[0][1]), i14[0]); dot(ax, XM, i14[0][1])
    wire(ax, (8, 112), (178, 112), (178, i14[2][1]), i14[2]); ax.text(8, 110.4, "KILL (U3 opto: no loop current = 1, L1)", fontsize=6.6)
    i16, o16 = gate(ax, 212, o15[1] - 5, "&", 2, "U16", "74LVC1G08", h=15, w=10)
    wire(ax, o15, i16[0]); ax.text(o15[0] + 0.5, o15[1] - 1.6, "READY_ON", fontsize=5.8)
    wire(ax, i16[1], (205, i16[1][1]), (205, 64), (220, 64))
    ax.text(222, 64, "RF_A2_N (J2 pin 17): low = RF on A2,\n100k pull-down (D-104, SR-01 H2)", va="center", fontsize=6.4)
    wire(ax, o16, (232, o16[1])); ax.text(234, o16[1], "240R to the READY\nswitch U6 (L1)", va="center", fontsize=6.6)
    wire(ax, o14, (220, o14[1])); ax.text(222, o14[1], "RLY_EN: RESET of U901 to U903,\nU1001; +12V_SW switch", va="center", fontsize=6.6)
    note(ax, 8, 126, [
        "FAULT is set (Q = 1) by RESET_N low: power-up (td 120 to 300 ms), 3V3 below 2.83 to 3.00 V, or no WDI edge for 0.9 to 2.5 s (C-19).",
        "Only a LATCH_CLR rising edge with RESET_N high clears FAULT. KILL is not latched in the box: the shack latch holds the stop (L3).",
        "RLY_EN = 1 only with KILL = 0, MCU_EN_N = 0 and FAULT = 0. READY_ON leaves out KILL, so the SAFE loop can close at start-up (F11).",
        "RF on A2 opens READY: no loop current, so KILL = 1 drops RLY_EN in the box and the shack latch inhibits all radios (D-104).",
        "Output indicator: polarity triangle (low-active), as in the schematics. Gate delays 5.4 ns max (M-10)."])
    save(fig, "L2_box_safety_gate")

# ------------------------------------------------------------------ L3: shack SAFE latch, TX_EN and one radio port
def l3_shack():
    fig, ax = canvas(277, 175, "L3  Shack SAFE latch, TX enable and radio port logic (D-71, D-75, D-84)", "L3_shack_latch_port")
    ins, out = gate(ax, 30, 26, "1", 1, "U7", "74LVC1G14", neg=True, h=10)
    wire(ax, (8, ins[0][1]), ins[0]); ax.text(8, ins[0][1] - 1.6, "SAFE_LOST (L1)", fontsize=6.6)
    ins8, out8 = gate(ax, 66, 26, "&", 2, "U8", "74LVC1G08", h=14)
    wire(ax, out, (56, out[1]), (56, ins8[0][1]), ins8[0]); ax.text(48, out[1] - 1.5, "SAFE_OK", fontsize=6.3)
    block(ax, 26, 46, 26, 12, "U6 TPS3823A-33", "POR only, WDI open", fc="#fff8e1", ec=INK)
    wire(ax, (52, 52), (58, 52), (58, ins8[1][1]), ins8[1]); ax.text(53, 55, "POR_N", fontsize=6.3)
    # latch U9
    x, y = 104, 22
    ax.add_patch(Rectangle((x, y), 18, 28, fc="#fff8e1", ec=INK, lw=1.0)); ax.text(x + 9, y - 2.0, "U9  74LVC1G74", ha="center", fontsize=6.3, color=ACC)
    for i, (t, low) in enumerate((("R", True), ("S", True), ("C1", False), ("1D", False))):
        py = y + 5 + i * 6; ax.text(x + 1.2, py, t, va="center", fontsize=7); wire(ax, (x - 5, py), (x, py))
        if low: ax.add_patch(Polygon([(x, py), (x - 2.2, py), (x, py - 1.6)], closed=True, fc="white", ec=INK, lw=0.8))
    wire(ax, out8, (94, out8[1]), (94, 33), (x - 5, 33)); ax.text(91, 31, "PRE_N", fontsize=6.3, ha="center")
    label(ax, x - 5, 27, "+3V3", size=6.3); label(ax, x - 5, 45, "GND", size=6.3)
    ins10, out10 = gate(ax, 66, 62, "1", 1, "U10", "74LVC1G14", neg=True, h=10)
    block(ax, 22, 61, 30, 12, "RESET button", "1k, 100k, 100n, 1N4148W", fc="#eef3fb")
    wire(ax, (52, 67), ins10[0]); wire(ax, out10, (98, out10[1]), (98, 39), (x - 5, 39)); ax.text(88, out10[1] - 1.5, "RESET_CLK", fontsize=6.3)
    # TX_EN
    ins11, out11 = gate(ax, 148, 26, "≥1", 2, "U11", "74LVC1G02", neg=True, h=14)
    wire(ax, (x + 18, 27), (136, 27), (136, ins11[0][1]), ins11[0]); ax.text(124, 25.4, "LATCHED", fontsize=6.3)
    wire(ax, (128, 27), (128, 18), (200, 18)); dot(ax, 128, 27); label(ax, 200, 18, "LATCHED LED, U5 IO1_7", "r", size=6.3)
    wire(ax, (124, 56), (139, 56), (139, ins11[1][1]), ins11[1]); ax.text(124, 54.4, "FAULT (U4: watchdog, power-up)", fontsize=6.3)
    ax.text(178, 52, "TX_EN", fontsize=7, fontweight="bold")
    # port
    ax.add_patch(Rectangle((116, 82), 150, 60, fill=False, ec=MUTE, lw=0.7, ls=(0, (4, 3))))
    ax.text(118, 86, "Radio port Rk (k = 1, 2, 3): U201 to U204", fontsize=7.5, color=MUTE)
    i1, o1 = gate(ax, 140, 92, "&", 2, "U201", "74LVC1G08", h=14)
    wire(ax, out11, (176, out11[1]), (176, 74), (132, 74), (132, i1[0][1]), i1[0])
    wire(ax, (120, i1[1][1]), i1[1]); label(ax, 120, i1[1][1], "PERMIT_Rk", size=6.5)
    block(ax, 196, 92, 32, 14, "U203 TLP4176G", "form B: LED off = INH closed", fc="#fdeaea", ec=RED)
    wire(ax, o1, (196, o1[1])); ax.text(170, o1[1] - 1.6, "INH_ON", fontsize=6.3)
    i2, o2 = gate(ax, 160, 118, "&", 2, "U202", "74LVC1G08", h=14)
    wire(ax, (186, o1[1]), (186, 113), (150, 113), (150, i2[0][1]), i2[0]); dot(ax, 186, o1[1])
    wire(ax, (120, i2[1][1]), i2[1]); label(ax, 120, i2[1][1], "KEY_Rk", size=6.5)
    block(ax, 206, 118, 32, 14, "U204 TLP176AM", "form A: LED on = keyed", fc="#e9f5ec", ec=SAFE)
    wire(ax, o2, (206, o2[1])); ax.text(188, o2[1] - 1.6, "KEY_ON", fontsize=6.3)
    wire(ax, (228, 99), (240, 99)); label(ax, 240, 99, "TX INH (DIN 2)", "r", size=6.3)
    wire(ax, (238, 125), (246, 125)); label(ax, 246, 125, "PTT (DIN 1)", "r", size=6.3)
    note(ax, 8, 148, [
        "LATCHED = 1 after power-up or any loss of loop current (PRE_N low). Only a RESET edge while PRE_N is high clears it; a held button gives no edge.",
        "TX_EN = NOR(FAULT, LATCHED). Inhibit released only with PERMIT AND TX_EN; keying only with KEY AND INH_ON, so keying never coincides with inhibit.",
        "Unpowered interface: both LEDs off, so INH closed (inhibit) and PTT open. LED ageing errs to the same safe side (F14)."])
    save(fig, "L3_shack_latch_port")

# ------------------------------------------------------------------ timing diagram helper
def timing(name, title, t_end, sigs, marks=(), notes=(), unit="ms", w=277, row=9.0, t0=0):
    """sigs: list of (label, [(t, level), ...], kind) with kind 'd' digital, 'a' analog-like (0..1 float), 'bus' with text."""
    h = 34 + row * len(sigs) + 8 + 4.5 * len(notes) + 8
    fig, ax = canvas(w, h, title, name)
    x0, x1, y0 = 62, w - 10, 24
    sx = lambda t: x0 + (x1 - x0) * (max(t, t0) - t0) / (t_end - t0)
    def clip(pts):                                   # start the trace at t0 with the level that holds there
        before = [q for q in pts if q[0] <= t0]
        return ([(t0, before[-1][1])] if before else []) + [q for q in pts if t0 < q[0] <= t_end]
    for i, (lab, pts, kind) in enumerate(sigs):
        pts = clip(pts)
        yb = y0 + row * (i + 1); yh = yb - row * 0.62
        ax.text(x0 - 3, yb - row * 0.3, lab, ha="right", va="center", fontsize=6.8)
        ax.plot([x0, x1], [yb + 1.2, yb + 1.2], color="#e2e2e2", lw=0.4)
        if kind == "bus":
            for (ta, txt), (tb, _) in zip(pts, pts[1:] + [(t_end, None)]):
                xa, xb = sx(ta), sx(tb)
                ax.add_patch(Polygon([(xa, yb - row * 0.31), (xa + 0.8, yh), (xb - 0.8, yh), (xb, yb - row * 0.31), (xb - 0.8, yb), (xa + 0.8, yb)],
                                     closed=True, fc="#eef3fb" if txt else "white", ec=ACC, lw=0.7))
                if txt: ax.text((xa + xb) / 2, yb - row * 0.31, txt, ha="center", va="center", fontsize=5.8)
            continue
        xs, ys = [], []
        for j, (t, lv) in enumerate(pts):
            yy = yb - (yb - yh) * lv
            if j: xs.append(sx(t)); ys.append(ys[-1])
            xs.append(sx(t)); ys.append(yy)
        xs.append(x1); ys.append(ys[-1])
        ax.plot(xs, ys, color=RED if kind == "r" else (SAFE if kind == "g" else INK), lw=1.0)
    for j, (t, txt) in enumerate(marks):
        ax.plot([sx(t), sx(t)], [y0 + 2 - 4 * (j % 2), y0 + row * len(sigs) + 2], color=MUTE, lw=0.5, ls=(0, (2, 2)))
        ax.text(sx(t), y0 + 1 - 4 * (j % 2), txt, ha="center", fontsize=5.8, color=MUTE)
    ya = y0 + row * len(sigs) + 6
    ax.plot([x0, x1], [ya, ya], color=INK, lw=0.6)
    for k in range(11):
        t = t0 + (t_end - t0) * k / 10; ax.plot([sx(t), sx(t)], [ya, ya + 1.2], color=INK, lw=0.6)
        ax.text(sx(t), ya + 3.5, f"{t:g}", ha="center", fontsize=5.8)
    ax.text(x1, ya + 7, unit, ha="right", fontsize=6)
    note(ax, 8, ya + 11, notes, size=6.4)
    save(fig, name)

def t1_startup():
    td, boot, clr, en = 200, 450, 470, 480
    timing("T1_box_startup", "T1  Box start-up: supervisor, fault latch, SAFE loop, relay enable (D-59, D-62, F11)", 900, [
        ("+3V3 (box)", [(0, 0), (10, 1)], "d"),
        ("RESET_N (U12)", [(0, 0), (10 + td, 1)], "d"),
        ("FAULT (U13 Q)", [(0, 1), (clr, 0)], "r"),
        ("MCU firmware", [(0, ""), (60, "boot"), (boot, "run: WDI kick every 0.25 s")], "bus"),
        ("LATCH_CLR", [(0, 0), (clr, 1), (clr + 5, 0)], "d"),
        ("MCU_EN_N", [(0, 1), (en, 0)], "d"),
        ("READY_ON (U15)", [(0, 0), (en, 1)], "g"),
        ("SAFE loop current", [(0, 0), (en + 1, 1)], "g"),
        ("KILL (U3)", [(0, 1), (en + 1, 0)], "d"),
        ("RLY_EN (U14)", [(0, 0), (en + 1, 1)], "g"),
        ("Expanders", [(0, "in reset"), (en + 1, "outputs 0, configure (F1)"), (en + 150, "ready to switch")], "bus"),
    ], marks=[(10 + td, "td 120-300 ms"), (clr, "LATCH_CLR"), (en, "MCU_EN_N = 0")], notes=[
        "Order (F11): LATCH_CLR, then MCU_EN_N = 0, then wait for KILL = 0 with a time-out ('SAFE loop open'). READY_ON leaves out KILL, so the loop can close.",
        "The shack must have its current source on (SW_STOP_N high) and KILL closed; otherwise KILL stays 1 and RLY_EN stays 0.",
        "Times: td from TPS3823A-33 (120 / 200 / 300 ms, C-19); boot time of the ESP32-C3 is an estimate (to measure). Loop current follows READY within microseconds."])

def t2_safe_stop():
    kill, back, rst = 100, 400, 600
    timing("T2_safe_stop", "T2  SAFE stop by the shack KILL switch, and recovery with RESET (D-62, D-75, M-10)", 800, [
        ("KILL switch (shack)", [(0, 1), (kill, 0), (back, 1)], "d"),
        ("SAFE loop current", [(0, 1), (kill, 0), (back, 1)], "g"),
        ("Box KILL (U3)", [(0, 0), (kill, 1), (back, 0)], "d"),
        ("Box RLY_EN", [(0, 1), (kill, 0), (back, 1)], "g"),
        ("Row relays, R2/R3 K0", [(0, 1), (kill + 6, 0), (back + 40, 1)], "d"),
        ("Box firmware", [(0, "normal"), (kill, "KILL = 1: relays off in hardware"), (back, "set up (F1, F5)"), (back + 40, "normal")], "bus"),
        ("SAFE_LOST (shack)", [(0, 0), (kill, 1), (back, 0)], "d"),
        ("LATCHED (U9 Q)", [(0, 0), (kill, 1), (rst, 0)], "r"),
        ("RESET button", [(0, 0), (rst - 10, 1), (rst + 60, 0)], "d"),
        ("TX_EN", [(0, 1), (kill, 0), (rst, 1)], "g"),
        ("TX INH (all radios)", [(0, 0), (kill, 1), (rst + 30, 0)], "r"),
    ], marks=[(kill, "KILL pressed"), (back, "KILL released"), (rst, "RESET edge")], notes=[
        "KILL to RLY_EN low about 0.1 us, coil MOSFETs off about 11 us, contacts open within about 6 ms (RT1 release, M-10).",
        "The shack latch holds the inhibit after the loop current returns: TX stays inhibited until RESET is pressed with the current present (L3 sequences L1 to L5).",
        "After RESET the shack firmware sends permits again (R2, R3 by handshake, T3); the box sets up its expanders before it switches (F5, F11)."])

def t3_handshake():
    req, perm, key, end_ = 5, 21, 60, 1000
    sig = [
        ("Shack: link to box", [(0, ""), (1, "request"), (req, ""), (end_ + 105, "end"), (end_ + 109, "")], "bus"),
        ("Box: K0 command (U903)", [(0, 0), (req, 1), (end_ + 109, 0)], "d"),
        ("K0 contact", [(0, 0), (req + 12, 1), (end_ + 109, 0)], "g"),
        ("Box: link to shack", [(0, ""), (req + 12, "permit"), (perm, "")], "bus"),
        ("PERMIT_Rk", [(0, 0), (perm, 1), (end_, 0)], "d"),
        ("TX INH contact", [(0, 1), (perm, 0), (end_, 1)], "r"),
        ("KEY_Rk (keying)", [(0, 0), (key, 1), (end_, 0)], "d"),
        ("Radio RF", [(0, 0), (key + 2, 1), (end_ + 5, 0)], "g"),
        ("TX sense (Rk_TX)", [(0, 0), (key + 2, 1), (end_ + 5, 0)], "d"),
        ("Shack: end wait", [(0, ""), (end_, "TX sense 0, at least 100 ms"), (end_ + 105, "")], "bus")]
    timing("T3a_tx_start", "T3a  TX handshake for R2 and R3: start (D-63; verify_system.py case N1)", 80, sig,
           marks=[(req, "request in"), (req + 12, "K0 settled"), (perm, "permit in"), (key, "keyed")], notes=[
        "Box: on a request it checks the state (H1 to H4), sets K0 through U903, waits 12 ms (operate 8 + bounce 4 ms), reads back and sends the permit.",
        "Messages take 4 ms at 9600 baud (C-18). The shack opens TX INH (PERMIT) only after the permit; the radio is keyed after that."])
    timing("T3b_tx_end", "T3b  TX handshake for R2 and R3: end (F13, F14; verify_system.py case N1)", 1140, sig, t0=980,
           marks=[(end_, "end of TX"), (end_ + 5, "RF off"), (end_ + 105, "'end' sent"), (end_ + 109, "K0 off")], notes=[
        "End: the shack drops permit and key (inhibit first), waits for TX sense 0 and at least 100 ms (F14), then sends 'end'; only then the box releases K0.",
        "Rule F13: while a permit is out the box does not change that radio's K0 or rows. On a link time-out it opens SAFE (MCU_EN_N = 1), it does not release K0."])

def t4_ptt_r1():
    timing("T4_ptt_r1", "T4  R1 (FT-710) PTT path in hardware: TX GND to K0, against the QSK delay (D-63, C-20, F7)", 40, [
        ("FT-710 TX GND", [(0, 0), (2, 1)], "d"),
        ("Loop 2 current", [(0, 0), (2.05, 1)], "g"),
        ("PTT_N (U2)", [(0, 1), (2.05, 0)], "d"),
        ("TX_ANY, R1_K0_DRV", [(0, 0), (2.06, 1)], "d"),
        ("K0 contact (R1)", [(0, 0), (14, 1)], "g"),
        ("FT-710 RF (QSK 15 ms)", [(0, 0), (17, 1)], "r"),
    ], marks=[(2, "TX GND closes"), (14, "K0 settled (8 + 4 ms)"), (17, "RF after 15 ms")], unit="ms", notes=[
        "R1 does not use the handshake: its K0 follows the FT-710 TX GND through loop 2 and the U5 inverter, with no MCU in the path (R51 fitted).",
        "Margin: K0 settled 12 ms after TX GND; the FT-710 QSK DELAY TIME is 15 ms minimum (C-20): about 3 ms. Opto and gate delays are below 0.1 ms (M-10).",
        "TX INH of R1 still needs PERMIT_R1 and TX_EN at the shack (L3)."])

# ------------------------------------------------------------------ flow diagram helpers (ISO 5807 shapes)
def fbox(ax, x, y, t, w=58, h=11, kind="p"):
    if kind == "t":
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0,rounding_size=5", fc="#eef3fb", ec=ACC, lw=1.0))
    elif kind == "d":
        ax.add_patch(Polygon([(x, y - h * 0.75), (x + w / 2, y), (x, y + h * 0.75), (x - w / 2, y)], closed=True, fc="#fff8e1", ec=INK, lw=1.0))
    else:
        ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc="white", ec=INK, lw=1.0))
    ax.text(x, y, t, ha="center", va="center", fontsize=6.4, wrap=True)

def arrow(ax, *pts, txt=None, tpos=0):
    a, b = pts[-2], pts[-1]
    if len(pts) > 2: wire(ax, *pts[:-1])
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.8, shrinkA=0, shrinkB=0))
    if txt: ax.text(pts[tpos][0] + 1.5, pts[tpos][1] + 2.5, txt, fontsize=6.2, color=MUTE)

def f1_box_firmware():
    fig, ax = canvas(277, 200, "F1  Box firmware: start-up, normal loop and stop handling (F1, F5, F11, F13; C-19)", "F1_box_firmware")
    X, Y = 64, 24
    steps = [("Power-up / reset", "t"), ("Kick WDI, MCU_EN_N = 1 (relays off)", "p"), ("LATCH_CLR rising edge", "p"),
             ("MCU_EN_N = 0  (READY closes)", "p"), ("KILL = 0 within time-out?", "d"),
             ("Expanders: outputs 0, then configure;\nspare pins outputs 0 (F1, F8)", "p"), ("Main loop", "t")]
    ys = [Y + 6 + 18 * i for i in range(len(steps))]
    for (t, k), y in zip(steps, ys): fbox(ax, X, y, t, kind=k, h=12 if k != "d" else 14)
    for a_, b_ in zip(ys, ys[1:]): arrow(ax, (X, a_ + (6 if a_ != ys[4] else 10.5)), (X, b_ - (6 if b_ != ys[4] else 10.5)))
    ax.text(X + 2, ys[4] + 13, "yes", fontsize=6.2, color=MUTE)
    RX = 128
    fbox(ax, RX, ys[4], "Report 'SAFE loop open';\nkeep MCU_EN_N = 0, retry", w=46, h=13)
    arrow(ax, (X + 29, ys[4]), (RX - 23, ys[4])); ax.text(X + 31, ys[4] - 2, "no", fontsize=6.2, color=MUTE)
    arrow(ax, (RX, ys[4] - 6.5), (RX, ys[2] + 9), (X + 0.6, ys[2] + 9)); dot(ax, X, ys[2] + 9)
    # main loop, one return bus at XB entering 'Kick WDI' from the left
    M, XB = 218, 172
    loop = [("Kick WDI (every 0.25 s or less)", "p"), ("Command from the shack?", "d"), ("Check state (H1 to H4); switch with\nTX_ANY = 0, 12 ms steps (F10)", "p"),
            ("KILL = 1?", "d"), ("Relays already off in hardware:\nwait KILL = 0, set up expanders again (F5, F11)", "p")]
    ly = [Y + 6 + 27 * i for i in range(len(loop))]
    for (t, k), y in zip(loop, ly): fbox(ax, M, y, t, w=70, kind=k, h=13 if k == "p" else 14)
    arrow(ax, (XB, ly[0]), (M - 35, ly[0]))
    arrow(ax, (M, ly[0] + 6.5), (M, ly[1] - 10.5)); arrow(ax, (M, ly[1] + 10.5), (M, ly[2] - 6.5)); ax.text(M + 2, ly[1] + 14, "yes", fontsize=6.2, color=MUTE)
    arrow(ax, (M, ly[2] + 6.5), (M, ly[3] - 10.5)); arrow(ax, (M, ly[3] + 10.5), (M, ly[4] - 6.5)); ax.text(M + 2, ly[3] + 14, "yes", fontsize=6.2, color=MUTE)
    arrow(ax, (M + 35, ly[1]), (264, ly[1]), (264, ly[2] + 13), (M + 0.6, ly[2] + 13)); dot(ax, M, ly[2] + 13)
    ax.text(M + 37, ly[1] - 2, "no", fontsize=6.2, color=MUTE)
    wire(ax, (M - 35, ly[3]), (XB, ly[3])); ax.text(M - 37, ly[3] - 2, "no", fontsize=6.2, color=MUTE, ha="right")
    wire(ax, (M, ly[4] + 6.5), (M, ly[4] + 12), (XB, ly[4] + 12), (XB, ly[0]))
    wire(ax, (X + 29, ys[-1]), (XB, ys[-1])); dot(ax, XB, ys[-1]); dot(ax, XB, ly[3])
    note(ax, 8, 172, [
        "F13: while a permit is out, never change that radio's K0 or rows. Link time-out: set MCU_EN_N = 1 (opens SAFE, inhibits every radio), do not release K0.",
        "Kick WDI only from the main loop, never from a timer interrupt. LATCH_CLR only after the start-up self-test, and after a fault only when its cause is checked (D-59).",
        "Shapes: ISO 5807 (terminator, process, decision). A dot marks a junction."])
    save(fig, "F1_box_firmware")

def f2_handshake():
    fig, ax = canvas(277, 190, "F2  TX handshake for R2 and R3: shack and box (D-63, F13, F14)", "F2_tx_handshake")
    S, B = 75, 205
    ax.text(S, 20, "Shack interface MCU", ha="center", fontsize=8, fontweight="bold", color=ACC)
    ax.text(B, 20, "Box MCU", ha="center", fontsize=8, fontweight="bold", color=ACC)
    ax.plot([140, 140], [16, 168], color=MUTE, lw=0.6, ls=(0, (4, 3)))
    sh = [("Operator or Mac asks TX on Rk", "t", 28), ("Send 'request Rk' (4 ms)", "p", 44), ("Permit received?", "d", 64),
          ("PERMIT_Rk = 1 (INH open); KEY_Rk = 1", "p", 84), ("End of TX: PERMIT 0 and KEY 0 (inhibit first)", "p", 104),
          ("TX sense 0 and at least 100 ms?", "d", 124), ("Send 'end Rk'", "p", 144), ("Done", "t", 160)]
    for t, k, y in sh: fbox(ax, S, y, t, w=70, kind=k, h=11 if k != "d" else 14)
    for (a, ka, ya), (b, kb, yb) in zip(sh, sh[1:]):
        arrow(ax, (S, ya + (10 if ka == "d" else 5.5)), (S, yb - (10 if kb == "d" else 5.5)))
    ax.text(S + 2, 76, "yes", fontsize=6.2, color=MUTE); ax.text(S + 2, 136, "yes", fontsize=6.2, color=MUTE)
    arrow(ax, (S - 35, 64), (20, 64), (20, 44), (S - 35, 44)); ax.text(21, 61, "no / time-out:\nrequest again or report", fontsize=5.8, color=MUTE)
    arrow(ax, (S - 35, 124), (14, 124), (14, 113), (S - 0.6, 113)); dot(ax, S, 113); ax.text(15, 128, "no: wait", fontsize=5.8, color=MUTE)
    bx = [("'request Rk' received", "t", 44), ("State allowed (H1 to H4)?", "d", 64), ("Set Rk K0 (U903 IO1_3 / IO1_4)", "p", 84),
          ("Wait 12 ms, read back K0 and rows", "p", 100), ("Send 'permit Rk'; hold K0 and rows (F13)", "p", 116),
          ("'end Rk' received: release K0", "p", 144)]
    for t, k, y in bx: fbox(ax, B, y, t, w=70, kind=k, h=11 if k != "d" else 14)
    for (a, ka, ya), (b, kb, yb) in list(zip(bx, bx[1:]))[:-1]:
        arrow(ax, (B, ya + (10 if ka == "d" else 5.5)), (B, yb - (10 if kb == "d" else 5.5)))
    ax.text(B + 2, 76, "yes", fontsize=6.2, color=MUTE)
    arrow(ax, (B + 35, 64), (258, 64), (258, 80)); ax.text(244, 61, "no", fontsize=5.8, color=MUTE)
    fbox(ax, 258, 86, "send 'refuse'", w=26, h=10, kind="t")
    arrow(ax, (S + 35, 44), (B - 35, 44)); ax.text(140, 41.5, "request", ha="center", fontsize=6, color=SAFE)
    arrow(ax, (B - 35, 116), (150, 116), (150, 64), (S + 35, 64)); ax.text(152, 92, "permit", fontsize=6, color=SAFE)
    arrow(ax, (S + 35, 144), (B - 35, 144)); ax.text(140, 141.5, "end", ha="center", fontsize=6, color=SAFE)
    note(ax, 8, 172, [
        "In hardware at the shack: TX INH = PERMIT AND TX_EN, keying = KEY AND INH_ON (L3). A SAFE stop or shack FAULT inhibits at once, without the MCU.",
        "Box link time-out while a permit is out: MCU_EN_N = 1 opens SAFE (inhibits every radio); K0 is not released by firmware (F13). R1 uses the PTT loop (T4)."])
    save(fig, "F2_tx_handshake")

if __name__ == "__main__":
    for f in (l1_safe_loop, l2_box_gate, l3_shack, t1_startup, t2_safe_stop, t3_handshake, t4_ptt_r1, f1_box_firmware, f2_handshake):
        f()
    print("written:", ", ".join(OUT))
