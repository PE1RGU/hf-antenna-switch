#!/usr/bin/env python3
"""Shack interface end plates as PCBs (D-179): rear plate and front plate for the Hammond 1455T1601, black solder mask,
white silkscreen. Run with the KiCad 10 Python from hardware/shack-interface/endplates/:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 gen_endplates.py
Input: ../shack-interface.kicad_pcb (positions of the panel connectors). Output: rear-panel.kicad_pcb, front-panel.kicad_pcb
(made new on every run). Sources: Hammond STEP 1455T1601.stp (end plate 165.0 x 51.13 x 1.5 mm, corner R 3.9, screw holes
at +-77.762 / 3.81 mm from the top and bottom edges; bezel pocket 1.7 mm deep, so a 1.6 mm PCB fits), fit M-92 to M-94
(D-177, D-178: connector faces 0.3 mm behind the plate, board parts side up in the 2nd slot from the closed bottom),
connector face profiles measured on the board STEP (case/ref-shack-interface.step).
Panel frame: u from the left edge, v from the top edge, both as seen from outside (F side = outside face), mm."""
import math
import pcbnew

REV = "a3"
MAIN = "../shack-interface.kicad_pcb"
OX, OY = 20.0, 20.0
PW, PH, PR = 165.0, 51.13, 3.9                       # plate outline (Hammond STEP: 164.998 x 51.130, R 3.9)
ZTOP = 51.312                                        # Z' of the plate top edge (housing frame of M-94: Z' up, 0 = closed bottom face)
SLOT_C = 11.68                                       # Z' of the slot centre (2nd slot from the closed bottom, D-178)
SCREWS = [(PW / 2 - 77.762, 3.81), (PW / 2 + 77.762, 3.81), (PW / 2 - 77.762, PH - 3.81), (PW / 2 + 77.762, PH - 3.81)]
WINDOW = (PW / 2 - 80.5, ZTOP - 49.07, PW / 2 + 80.5, ZTOP - 2.44)   # opening of the bezel behind the plate (u0, v0, u1, v1)
FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
mm = pcbnew.FromMM

# connector face profiles at the plate, from the board STEP (section 0.3 mm behind the face): x offset of the face centre
# from the footprint position, width, and height range above the board underside (z0, z1), or a round boss (z centre, d)
FACE = {"J3": ("rect", 3.6, 15.5, 1.6, 10.0),          # XT60PW-M housing (chamfered on the pin 1 side)
        "J1": ("rect", 0.0, 15.15, 1.61, 13.26),       # RJ45 front
        "J11": ("round", 0.0, 9.95, 7.805), "J12": ("round", 0.0, 9.95, 7.805), "J13": ("round", 0.0, 9.95, 7.805),
        "J14": ("rect", 0.0, 8.94, 1.75, 4.91)}         # USB-C receptacle mouth
RECT_M = 0.3                                          # cut-out margin per side (board play in the slot: +-0.2 mm)
MINIDIN_D = 10.5                                      # plug shell 9.5 mm passes; the overmold stops on the plate
USBC_SLOT = (13.0, 7.0)                               # D-96: overmold up to 12.35 x 6.5 mm passes
# front plate controls (D-180 to D-182; a3 after the main board p6). Panel frame (u, v) from outside; board x = u - 2.5.
# Depth behind the plate: the DevKit (board x 56 to 122, up to y 146) leaves about 13 mm, the free area right of it
# (board x 122 to 156, front) takes the KILL and RESET bodies; the display (about 11 mm deep with its cable) sits on the
# left, over the wire headers J6, J2, J7, which moved back to y 146.5 (p6).
KILL = (146.0, 21.0)                                  # EAO 84-5340.0020: cut-out 22.3 mm with a 3.2 mm key to 24.1 mm, head 32 mm
RESET = (125.0, 31.0)                                 # C&K 8125SHZBE: 1/4-40 bushing, hole 6.5 mm (body at board x 119 to 126)
LEDS = {"SAFE": (108.0, 12.0), "LATCHED": (121.0, 12.0)}   # 3 mm panel LEDs, hole 4.0 mm (Dialight 558: 3.94 to 4.01 mm)
DISP = (12.0, 4.2)                                    # Waveshare 1.9" module top left (51.2 x 27.3); active area x 6.24..48.96, y 2.30..25.01 (module STEP)


def main_board():
    m = pcbnew.LoadBoard(MAIN)
    t = pcbnew.ToMM(m.GetDesignSettings().GetBoardThickness())
    pos = {r: pcbnew.ToMM(m.FindFootprintByReference(r).GetPosition().x) - OX for r in FACE}
    pins = {n: pcbnew.ToMM(p.GetPosition().x) - OX for p in m.FindFootprintByReference("J3").Pads() for n in [p.GetNumber()] if n}
    return t, pos, pins


T_MAIN, XPOS, XT60_PINS = main_board()
ZB = SLOT_C - T_MAIN / 2                               # Z' of the main board underside


def panel_uv(side, x_board, z_above_bottom):
    """main-board x and height above its underside -> panel (u, v) as seen from outside"""
    u = (PW / 2 + 80.0 - x_board) if side == "rear" else (PW / 2 - 80.0 + x_board)
    return u, ZTOP - (ZB + z_above_bottom)


def build(side):
    b = pcbnew.BOARD()
    KEEP = []
    P = lambda u, v: pcbnew.VECTOR2I(mm(OX + u), mm(OY + v))
    ds = b.GetDesignSettings()
    ds.SetBoardThickness(mm(1.6)); ds.m_CopperEdgeClearance = mm(0.5)
    ds.SetCopperLayerCount(2)
    ch = pcbnew.NETINFO_ITEM(b, "CHASSIS"); b.Add(ch); KEEP.append(ch)

    def seg(a, c, layer=pcbnew.Edge_Cuts, w=0.1):
        if math.hypot(c[0] - a[0], c[1] - a[1]) < 1e-6: return      # a full-round slot end has no straight side
        s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); s.SetStart(P(*a)); s.SetEnd(P(*c)); s.SetLayer(layer)
        s.SetWidth(mm(w)); b.Add(s); KEEP.append(s)

    def arc(st, mid, en, layer=pcbnew.Edge_Cuts, w=0.1):
        s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_ARC); s.SetArcGeometry(P(*st), P(*mid), P(*en)); s.SetLayer(layer)
        s.SetWidth(mm(w)); b.Add(s); KEEP.append(s)

    def rrect(u0, v0, u1, v1, r, layer=pcbnew.Edge_Cuts, w=0.1):
        k = r * (1 - 0.5 ** 0.5)
        seg((u0 + r, v0), (u1 - r, v0), layer, w); seg((u1, v0 + r), (u1, v1 - r), layer, w)
        seg((u1 - r, v1), (u0 + r, v1), layer, w); seg((u0, v1 - r), (u0, v0 + r), layer, w)
        arc((u1 - r, v0), (u1 - k, v0 + k), (u1, v0 + r), layer, w); arc((u1, v1 - r), (u1 - k, v1 - k), (u1 - r, v1), layer, w)
        arc((u0 + r, v1), (u0 + k, v1 - k), (u0, v1 - r), layer, w); arc((u0, v0 + r), (u0 + k, v0 + k), (u0 + r, v0), layer, w)

    def circle(cu, cv, d, layer=pcbnew.Edge_Cuts, w=0.1):
        c = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_CIRCLE); c.SetCenter(P(cu, cv)); c.SetEnd(P(cu + d / 2, cv)); c.SetLayer(layer)
        c.SetWidth(mm(w)); b.Add(c); KEEP.append(c)

    def text(s, u, v, h=1.0, t=0.15, layer=pcbnew.F_SilkS, just="c"):
        o = pcbnew.PCB_TEXT(b); o.SetText(s); o.SetLayer(layer); o.SetTextSize(pcbnew.VECTOR2I(mm(h), mm(h)))
        o.SetTextThickness(mm(t)); o.SetPosition(P(u, v))
        o.SetHorizJustify({"l": pcbnew.GR_TEXT_H_ALIGN_LEFT, "r": pcbnew.GR_TEXT_H_ALIGN_RIGHT, "c": pcbnew.GR_TEXT_H_ALIGN_CENTER}[just])
        if layer == pcbnew.B_SilkS: o.SetMirrored(True)
        b.Add(o); KEEP.append(o); return o

    # outline
    rrect(0.0, 0.0, PW, PH, PR)
    # screw holes: plated 3.7 mm for the Hammond ST3.5 screws (shank 3.5 mm, measured on the STEP), CHASSIS, bare copper
    # ring 6.0 mm on both faces (bond to the extrusion through the screws). The hole centre is 3.81 mm from the top and
    # bottom edges, so the ring is 6.0 mm (0.81 mm to the edge) and not the library 7.4 mm.
    for (u, v) in SCREWS:
        f = pcbnew.FootprintLoad(f"{FPLIB}/MountingHole.pretty", "MountingHole_3.7mm_Pad")
        f.SetPosition(P(u, v)); f.Reference().SetVisible(False); f.Value().SetVisible(False)
        for pd in f.Pads(): pd.SetNet(ch); pd.SetSize(pcbnew.VECTOR2I(mm(6.0), mm(6.0)))
        b.Add(f); KEEP.append(f)
    # cut-outs
    CUTS = []                                          # (u0, v0, u1, v1) of every opening, for the vias and the labels
    refs = ["J3", "J1", "J11", "J12", "J13"] if side == "rear" else ["J14"]
    for r in refs:
        kind = FACE[r][0]
        if kind == "round":
            _, dx, d, zc = FACE[r]; cu, cv = panel_uv(side, XPOS[r] + dx, zc)
            circle(cu, cv, MINIDIN_D); CUTS.append((r, cu - MINIDIN_D / 2, cv - MINIDIN_D / 2, cu + MINIDIN_D / 2, cv + MINIDIN_D / 2))
        elif r == "J14":
            _, dx, w, z0, z1 = FACE[r]; cu, cv = panel_uv(side, XPOS[r] + dx, (z0 + z1) / 2)
            sw, sh = USBC_SLOT; rrect(cu - sw / 2, cv - sh / 2, cu + sw / 2, cv + sh / 2, sh / 2)
            CUTS.append((r, cu - sw / 2, cv - sh / 2, cu + sw / 2, cv + sh / 2))
        else:
            _, dx, w, z0, z1 = FACE[r]; cu, va = panel_uv(side, XPOS[r] + dx, z1); _, vb = panel_uv(side, XPOS[r] + dx, z0)
            u0, u1, v0, v1 = cu - w / 2 - RECT_M, cu + w / 2 + RECT_M, va - RECT_M, vb + RECT_M
            rrect(u0, v0, u1, v1, 0.5); CUTS.append((r, u0, v0, u1, v1))
    if side == "front":
        ku, kv = KILL; rk = 22.3 / 2; dn = math.sqrt(rk ** 2 - 1.6 ** 2)
        arc((ku + 1.6, kv - dn), (ku, kv + rk), (ku - 1.6, kv - dn))          # Ø22.3 with the anti-rotation key upward
        seg((ku - 1.6, kv - dn), (ku - 1.6, kv - (24.1 - rk))); seg((ku - 1.6, kv - (24.1 - rk)), (ku + 1.6, kv - (24.1 - rk)))
        seg((ku + 1.6, kv - (24.1 - rk)), (ku + 1.6, kv - dn))
        CUTS.append(("KILL", ku - rk, kv - (24.1 - rk), ku + rk, kv + rk))
        circle(*RESET, 6.5); CUTS.append(("RESET", RESET[0] - 3.25, RESET[1] - 3.25, RESET[0] + 3.25, RESET[1] + 3.25))
        for n, (lu, lv) in LEDS.items():
            circle(lu, lv, 4.0); CUTS.append((n, lu - 2.0, lv - 2.0, lu + 2.0, lv + 2.0))
        du, dv = DISP; wu0, wu1 = du + 6.24 - 0.3, du + 48.96 + 0.3; wv0, wv1 = dv + 27.3 - 25.01 - 0.3, dv + 27.3 - 2.30 + 0.3
        rrect(wu0, wv0, wu1, wv1, 0.5); CUTS.append(("DISPLAY", wu0, wv0, wu1, wv1))
        rrect(du, dv, du + 51.2, dv + 27.3, 1.0, pcbnew.B_SilkS, 0.15)     # module outline on the inside face (assembly)
    for (r, u0, v0, u1, v1) in CUTS:
        assert WINDOW[0] < u0 and u1 < WINDOW[2] and WINDOW[1] < v0 and v1 < WINDOW[3], (r, "outside the bezel window")
    C = {r: (u0, v0, u1, v1) for (r, u0, v0, u1, v1) in CUTS}

    # CHASSIS copper on the inside face only: one plane is the shield; the outside face stays plain black (no copper
    # pattern or via dots under the mask). The plated screw holes join the plane to the bare rings on both faces.
    for layer in (pcbnew.B_Cu,):
        z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNetCode(ch.GetNetCode())
        o = pcbnew.SHAPE_LINE_CHAIN()
        for (u, v) in ((0, 0), (PW, 0), (PW, PH), (0, PH)): o.Append(P(u, v))
        o.SetClosed(True); z.Outline().AddOutline(o); z.SetLocalClearance(mm(0.3)); z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); b.Add(z); KEEP.append(z)
    # silkscreen, outside face (white on black). Labels above the openings; title along the top.
    def above(r, s, h=1.5, t=0.25, dv=1.8):
        u0, v0, u1, v1 = C[r]; text(s, (u0 + u1) / 2, v0 - dv, h, t)
    text("SHACK RELAY MATRIX   SHACK INTERFACE", PW / 2, 8.0 if side == "rear" else PH - 5.0, 2.0, 0.3)
    if side == "rear":
        above("J11", "R1  FT-710"); above("J12", "R2"); above("J13", "R3"); above("J1", "CAT6  BOX")
        above("J3", "13.8 V DC")
        # polarity beside the XT60 opening, on the side of each pin (KiCad footprint pin 1 GND, pin 2 +, D-171;
        # polarity on the real part M-02)
        u0, v0, u1, v1 = C["J3"]; pu = {n: panel_uv(side, XT60_PINS[n], 0.0)[0] for n in ("1", "2")}
        for n, s_ in (("1", "-"), ("2", "+")):
            left = pu[n] < (u0 + u1) / 2
            text(s_, u0 - 2.6 if left else u1 + 2.6, (v0 + v1) / 2, 2.5, 0.35)
    else:
        above("J14", "USB")
        def below(r, s, h=1.5, t=0.25, dv=2.2):
            u0, v0, u1, v1 = C[r]; text(s, (u0 + u1) / 2, v1 + dv, h, t)
        text("KILL", KILL[0], KILL[1] + 16.0 + 2.2, 2.0, 0.3)               # below the 32 mm head
        below("RESET", "RESET"); below("SAFE", "SAFE", 1.2, 0.2, 1.6); below("LATCHED", "LATCHED", 1.2, 0.2, 1.6)
    text("73 de PE1RGU", 9.0, PH - 7.0, 1.0, 0.15, just="l")
    # inside face: identification
    text(f"SRM shack interface {side} plate  rev A ({REV})  2026-10", PW / 2, PH - 8.0, 1.0, 0.15, pcbnew.B_SilkS)

    fn = f"{side}-panel.kicad_pcb"
    b.Save(fn)
    # stackup with black mask and white silkscreen (the Python wrapper does not expose BOARD_STACKUP)
    st = ('\t\t(stackup\n'
          '\t\t\t(layer "F.SilkS"\n\t\t\t\t(type "Top Silk Screen")\n\t\t\t\t(color "White")\n\t\t\t)\n'
          '\t\t\t(layer "F.Paste"\n\t\t\t\t(type "Top Solder Paste")\n\t\t\t)\n'
          '\t\t\t(layer "F.Mask"\n\t\t\t\t(type "Top Solder Mask")\n\t\t\t\t(color "Black")\n\t\t\t\t(thickness 0.01)\n\t\t\t)\n'
          '\t\t\t(layer "F.Cu"\n\t\t\t\t(type "copper")\n\t\t\t\t(thickness 0.035)\n\t\t\t)\n'
          '\t\t\t(layer "dielectric 1"\n\t\t\t\t(type "core")\n\t\t\t\t(color "FR4 natural")\n\t\t\t\t(thickness 1.51)\n'
          '\t\t\t\t(material "FR4")\n\t\t\t\t(epsilon_r 4.5)\n\t\t\t\t(loss_tangent 0.02)\n\t\t\t)\n'
          '\t\t\t(layer "B.Cu"\n\t\t\t\t(type "copper")\n\t\t\t\t(thickness 0.035)\n\t\t\t)\n'
          '\t\t\t(layer "B.Mask"\n\t\t\t\t(type "Bottom Solder Mask")\n\t\t\t\t(color "Black")\n\t\t\t\t(thickness 0.01)\n\t\t\t)\n'
          '\t\t\t(layer "B.Paste"\n\t\t\t\t(type "Bottom Solder Paste")\n\t\t\t)\n'
          '\t\t\t(layer "B.SilkS"\n\t\t\t\t(type "Bottom Silk Screen")\n\t\t\t\t(color "White")\n\t\t\t)\n'
          '\t\t\t(copper_finish "ENIG")\n\t\t\t(dielectric_constraints no)\n\t\t)\n')
    txt = open(fn).read()
    i = txt.find("\n\t(setup\n"); assert i > 0
    j = i + len("\n\t(setup\n")
    open(fn, "w").write(txt[:j] + st + txt[j:])
    print(side, "cut-outs", {r: tuple(round(x, 2) for x in c) for r, c in C.items()})


print("main board thickness", T_MAIN, "| board underside Z'", round(ZB, 3))
build("rear")
build("front")
