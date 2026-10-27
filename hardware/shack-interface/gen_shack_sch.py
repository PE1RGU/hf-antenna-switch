#!/usr/bin/env python3
"""Generate the shack interface board schematic, rev A (root + hierarchical sheets), drawn with wires.

Definition: hardware/shack-interface/shack-interface-rev-a.md. Decisions: design-log.md (D-62 to D-80).
Run from this folder. Overwrites shack-interface.kicad_sch, the sheet files, shack-interface.kicad_sym and sym-lib-table.
Framework (Sheet, wires, junctions, sheet blocks) copied from gen_controller_sch.py (controller board, rev C).
Library symbols come from _sym/ (copied from the KiCad 10 libraries).

Drawing rules (hardware skill, section 11): signal flow left to right, supplies up, ground down,
wires inside a sheet, labels only where a net leaves the sheet or its other end is not drawn yet,
junction dots at every T, no wire end on the middle of another wire (checked by an assert).
"""
import json, math, os, re, uuid

PROJECT = "shack-interface"
DATE = "2026-10-19"
GENERATOR_REV = "a17-display"
GEN = set()   # uuids made by U(): replaced by stable uuid5 values when the files are written (Git-friendly)
def U():
    u = str(uuid.uuid4()); GEN.add(u); return u
U_ = U
# Fixed root and sheet uuids. KiCad 10 keeps the top-level sheet uuid in the .kicad_pro
# (schematic.top_level_sheets) and starts every instance path with it. A new uuid per run
# breaks the paths: KiCad then "fixes" the file and gives all sheet instances the same references.
NS = uuid.uuid5(uuid.NAMESPACE_DNS, "pe1rgu.shack-relay-matrix.rev-c.shack-interface")
ROOT_UUID = str(uuid.uuid5(NS, "root"))
R2 = lambda v: round(v + 0.0, 2)

# ---------- library symbols ----------
def load(lib, name):
    t = open(f"_sym/{lib}__{name}.sym").read().strip()
    return t.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)
def pins_of(t):
    out = {}
    for blk in t.split("(pin ")[1:]:
        m = re.search(r"\(at ([-\d.]+) ([-\d.]+) (\d+)\)", blk)
        n = re.search(r'\(number "([^"]+)"', blk)
        if m and n: out[n.group(1)] = (float(m.group(1)), float(m.group(2)), int(m.group(3)))
    return out
def unit_pins(t, name):
    """Pins per unit of a multi-unit symbol: {unit: {pin: (x, y, a)}}; unit 0 = common to all units."""
    out = {}
    for m in re.finditer(r'\(symbol "' + re.escape(name) + r'_(\d+)_\d+"', t):
        d, j = 0, m.start()
        while True:
            d += {"(": 1, ")": -1}.get(t[j], 0)
            if d == 0: break
            j += 1
        out.setdefault(int(m.group(1)), {}).update(pins_of(t[m.start():j + 1]))
    return out
PINS, PINS_U = {}, {}
RLY = None                                                   # no relay symbol on this board
def xform(px, py, a, rot, mirror):
    """Library pin (y up) to schematic offset (y down). mirror 'x' flips top/bottom, 'y' flips left/right."""
    c, s = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
    rx, ry, a = px * c - py * s, px * s + py * c, (a + rot) % 360      # KiCad rotates first, then mirrors
    if mirror == "x": ry, a = -ry, (360 - a) % 360
    if mirror == "y": rx, a = -rx, (180 - a) % 360
    return rx, -ry, a

# ---------- s-expression helpers ----------
JUST = {0: "left", 90: "left", 180: "right", 270: "right"}
def eff(j, hide=False):
    h = "\n\t\t\t(hide yes)" if hide else ""
    return f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t){h}\n\t\t\t(justify {j})\n\t\t)\n'
def label_sx(kind, name, x, y, a):
    x, y = R2(x), R2(y)
    if kind == "L":
        return f'\t(label "{name}"\n\t\t(at {x} {y} {a})\n' + eff(JUST[a] + " bottom") + f'\t\t(uuid "{U()}")\n\t)\n'
    tag = {"H": "hierarchical_label", "G": "global_label"}[kind]
    return f'\t({tag} "{name}"\n\t\t(shape passive)\n\t\t(at {x} {y} {a})\n' + eff(JUST[a]) + f'\t\t(uuid "{U()}")\n\t)\n'
def text_sx(t, x, y):
    return (f'\t(text "{t}"\n\t\t(exclude_from_sim no)\n\t\t(at {x} {y} 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
            f'\t\t\t(justify left top)\n\t\t)\n\t\t(uuid "{U()}")\n\t)\n')
def prop(name, val, x, y, hide=False, just="left", ang=0):
    h = "\n\t\t\t(hide yes)" if hide else ""
    return (f'\t\t(property "{name}" "{val}"\n\t\t\t(at {R2(x)} {R2(y)} {ang}){h}\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n'
            f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n'
            + ("" if just == "center" else f'\t\t\t\t(justify {just})\n') + '\t\t\t)\n\t\t)\n')

C1 = "Design: Prins Doornekamp, PE1RGU"
C2 = "RT1 RTD14012F x37, SO-239 Amphenol 83-798 x7, SMA EXP x3, XT60 x2, XT30"
C3 = "Crossbar: rows on L1, columns on L2. Unit 1 = 3 radios x 4 antennas + EXP"
C4 = "Stackup and size: to decide with the layout"

class Sheet:
    def __init__(self, title, paper, insts, pwr_base=None):
        """insts: list of (sheet path, reference base). pwr_base: bases for #PWR / #FLG references."""
        self.u, self.title, self.paper, self.insts = U(), title, paper, insts
        self.pwr_bases = pwr_base or [b for _, b in insts]
        self.items, self.segs, self.pinpts, self.used, self.npwr = [], [], [], set(), 0
        self.mx = None          # set to M to draw the sheet mirrored left-right (x -> M - x); text blocks are not mirrored
        self.oy = 0             # vertical offset added to every y (moves the whole drawing on the paper)

    def part(self, lib, ref, value, fp, x, y, conn=None, desc="", dnp=False, mpn="", rot=0, mirror=None,
             rp=None, bom=True, refs=None, unit=1):
        """ref: (prefix, number). conn: pin -> 'NC' | (kind, name) label at the pin. Returns pin -> (x, y)."""
        self.used.add(lib)
        conn = conn or {}
        lp = {**PINS_U[lib].get(0, {}), **PINS_U[lib][unit]} if lib in PINS_U else PINS[lib]
        assert set(conn) <= set(lp), (lib, conn)
        y = R2(y + self.oy)
        if rp and lib in ("Device:C", "Device:C_Polarized") and rot in (0, 180) and 0 < rp[0] < 2.794:
            rp = (2.794,) + tuple(rp[1:])                           # capacitor text clear of the plates
        if self.mx is not None:                                   # mirrored sheet: rp from the unmirrored frame, then flip
            if rp is None:
                rp = (11.43, -1.27) if lib == RLY else (2.54, -1.27) if lib == "Device:C" else \
                     (max(xform(px, py, a, rot, mirror)[0] for px, py, a in lp.values()) + 1.27, -1.27)
            x = R2(self.mx - x)
            rot, mirror = {None: (rot, "y"), "y": (rot, None), "x": ((rot + 180) % 360, None)}[mirror]
            rp = (-rp[0],) + tuple(rp[1:])
        pts = {}
        for p, (px, py, a) in lp.items():
            dx, dy, aa = xform(px, py, a, rot, mirror)
            pts[p] = (R2(x + dx), R2(y + dy), aa)
        refs = refs or [(path, f"{ref[0]}{b + ref[1]}") for path, b in self.insts]
        mir = f"\t\t(mirror {mirror})\n" if mirror else ""
        s = (f'\t(symbol\n\t\t(lib_id "{lib}")\n\t\t(at {x} {y} {rot})\n{mir}\t\t(unit {unit})\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n'
             f'\t\t(in_bom {"yes" if bom else "no"})\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n\t\t(dnp {"yes" if dnp else "no"})\n'
             f'\t\t(uuid "{uuid.uuid5(NS, "sym/" + refs[0][1] + "/" + str(unit))}")\n')   # stable: keyed on reference and unit
        if rp is None and lib == RLY: rp = (11.43, -1.27)
        if rp is None and lib == "Device:C": rp = (2.54, -1.27)       # clear of the plates
        if rp is None:
            xs = [q[0] for q in pts.values()]
            rp = (max(xs) - x + 1.27, -1.27)
        hide_ref = ref[0].startswith("#")
        just = rp[2] if len(rp) > 2 else "left"
        ang = 0 if rot == 180 else (360 - rot) % 360         # keep text horizontal (KiCad shows 180 as 0, justification mirrored)
        if lib in ("Device:R", "Device:Fuse") and rot in (90, 270):     # horizontal resistor: reference above, value below, both centred
            s += prop("Reference", refs[0][1], x, R2(y - 2.54), hide_ref, "center", ang) + \
                 prop("Value", value, x, R2(y + 2.54), False, "center", ang)
        else:
            s += prop("Reference", refs[0][1], x + rp[0], y + rp[1], hide_ref, just, ang) + \
                 prop("Value", value, x + rp[0], y + rp[1] + 2.54, False, just, ang)
        s += prop("Footprint", fp, x, y, True) + prop("Datasheet", "", x, y, True) + prop("Description", desc, x, y, True)
        if mpn: s += prop("MPN", mpn, x, y, True)
        allpins = {q for u in PINS_U[lib].values() for q in u} if lib in PINS_U else pts   # KiCad lists every pin in each unit
        for p in sorted(allpins, key=lambda q: (len(q), q)): s += f'\t\t(pin "{p}"\n\t\t\t(uuid "{uuid.uuid5(NS, "pin/" + refs[0][1] + "/" + str(unit) + "/" + p)}")\n\t\t)\n'
        s += f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n'
        for path, r in refs:
            s += f'\t\t\t\t(path "{path}"\n\t\t\t\t\t(reference "{r}")\n\t\t\t\t\t(unit {unit})\n\t\t\t\t)\n'
        s += '\t\t\t)\n\t\t)\n\t)\n'
        self.items.append(s)
        self.pinpts += sorted({(q[0], q[1]) for q in pts.values()})      # stacked (hidden) pins count once
        for p, (ex, ey, a) in pts.items():
            c = conn.get(p)
            if c == "NC": self.items.append(f'\t(no_connect\n\t\t(at {ex} {ey})\n\t\t(uuid "{U()}")\n\t)\n')
            elif c: self.items.append(label_sx(c[0], c[1], ex, ey, (a + 180) % 360))
        if self.mx is not None:                                   # callers work in the unmirrored, unshifted frame
            return {p: (R2(self.mx - q[0]), R2(q[1] - self.oy)) for p, q in pts.items()}
        return {p: (q[0], R2(q[1] - self.oy)) for p, q in pts.items()}

    def power(self, net, pt, flag=False, rp=None, rot=0):
        """Power symbol at pt: GND points down, supplies point up. flag=True places a PWR_FLAG.
        Net name = Value field; the +12V graphic is used for every other positive net (+12V_SW, CLAMP_SW, ...)."""
        x, y = pt
        self.npwr += 1
        if flag: lib, pre, val = "power:PWR_FLAG", "#FLG", "PWR_FLAG"
        else: lib, pre, val = {"GND": "power:GND", "+5V": "power:+5V", "+3V3": "power:+3V3",
                               "CHASSIS": "shack-interface:CHASSIS", "RGND": "shack-interface:RGND"}.get(net, "power:+12V"), "#PWR", net
        refs = [(path, f"{pre}{b + self.npwr}") for (path, _), b in zip(self.insts, self.pwr_bases)]
        down = net in ("GND", "CHASSIS", "RGND") and not flag
        dy = 5.08 if down else -5.08
        if rp is None and down: rp = (0, {"GND": 1.905, "RGND": 1.905}.get(net, 4.445), "center")     # net name centred under the symbol
        self.part(lib, (pre, 0), val, "", x, y, desc="", bom=False, rp=rp or (-3.81, dy - 1.27), refs=refs, rot=rot)

    def wire(self, *pts):
        if self.mx is not None: pts = [(self.mx - p[0], p[1]) for p in pts]
        if self.oy: pts = [(p[0], p[1] + self.oy) for p in pts]
        for a, b in zip(pts, pts[1:]):
            a, b = (R2(a[0]), R2(a[1])), (R2(b[0]), R2(b[1]))
            assert a != b and (a[0] == b[0] or a[1] == b[1]), (a, b)
            self.segs.append((a, b))
            self.items.append(f'\t(wire\n\t\t(pts\n\t\t\t(xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})\n\t\t)\n'
                              f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{U()}")\n\t)\n')

    def label(self, kind, name, x, y, a=0):
        if self.mx is not None: x, a = self.mx - x, (180 - a) % 360
        self.items.append(label_sx(kind, name, x, y + self.oy, a))
    def text(self, t, x, y): self.items.append(text_sx(t, x, R2(y + self.oy)))
    def raw(self, s): self.items.append(s)

    def finish(self):
        ends = {}
        for a, b in self.segs:
            for p in (a, b): ends[p] = ends.get(p, 0) + 1
        for p, n in ends.items():                                # no wire end on the middle of another wire
            for a, b in self.segs:
                if p in (a, b): continue
                inside = (a[0] == b[0] == p[0] and min(a[1], b[1]) < p[1] < max(a[1], b[1])) or \
                         (a[1] == b[1] == p[1] and min(a[0], b[0]) < p[0] < max(a[0], b[0]))
                assert not inside, (self.title, "T without split", p, a, b)
        for p in self.pinpts:
            if p in ends: ends[p] += 1
        junc = "".join(f'\t(junction\n\t\t(at {p[0]} {p[1]})\n\t\t(diameter 0)\n\t\t(color 0 0 0 0)\n\t\t(uuid "{U()}")\n\t)\n'
                       for p, n in ends.items() if n >= 3)
        t = (f'(kicad_sch\n\t(version 20260101)\n\t(generator "eeschema")\n\t(generator_version "10.0")\n'
             f'\t(uuid {self.u})\n\t(paper "{self.paper}")\n\t(title_block\n\t\t(title "{self.title}")\n\t\t(date "{DATE}")\n'
             f'\t\t(rev "A")\n\t\t(company "PE1RGU - Shack Relay Matrix")\n')
        t += "".join(f'\t\t(comment {i + 1} "{c}")\n' for i, c in enumerate([C1, C2, C3, C4])) + "\t)\n"
        t += "\t(lib_symbols\n\t\t" + "\n\t\t".join(SYMS[k].replace("\n", "\n\t") for k in sorted(self.used)) + "\n\t)\n"
        t += junc + "".join(self.items)
        t += '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n'
        if self.u == ROOT_UUID: t += '\t(embedded_fonts no)\n'   # KiCad writes this on the root file only
        t += ')\n'
        assert t.count("(") == t.count(")"), self.title
        return t

def sheet_block(key, name, fn, page, x, y, w, h, left, right, file_top=False, top=(), bottom=()):
    """Sheet pins: left/right on a 2.54 slot grid from the top; top/bottom on a 2.54 grid from the left edge."""
    assert "/" not in name, ("KiCad sheet names cannot contain '/'", name)
    sp = ""
    for side, names in (("L", left), ("R", right), ("T", top), ("B", bottom)):
        for i, p in enumerate(names):
            if not p: continue
            d = R2((i + 1) * 2.54)
            px, py, a, j = {"L": (x, R2(y + d), 180, "left"), "R": (R2(x + w), R2(y + d), 0, "right"),
                            "T": (R2(x + d), y, 90, "right"), "B": (R2(x + d), R2(y + h), 270, "left")}[side]
            sp += (f'\t\t(pin "{p}" passive\n\t\t\t(at {px} {py} {a})\n\t\t\t(uuid "{U()}")\n'
                   f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify {j})\n\t\t\t)\n\t\t)\n')
    return (f'\t(sheet\n\t\t(at {x} {y})\n\t\t(size {w} {h})\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n'
            f'\t\t(dnp no)\n\t\t(fields_autoplaced yes)\n\t\t(stroke\n\t\t\t(width 0.1524)\n\t\t\t(type solid)\n\t\t)\n'
            f'\t\t(fill\n\t\t\t(color 0 0 0 0.0000)\n\t\t)\n\t\t(uuid "{SUUID[key]}")\n'
            f'\t\t(property "Sheetname" "{name}"\n\t\t\t(at {x} {R2(y - 0.71)} 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify left bottom)\n\t\t\t)\n\t\t)\n'
            f'\t\t(property "Sheetfile" "{fn}"\n\t\t\t(at {R2(x + w) if file_top else x} {R2(y - 0.71) if file_top else R2(y + h + 0.59)} 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify {"right bottom" if file_top else "left top"})\n\t\t\t)\n\t\t)\n'
            + sp + f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "/{ROOT_UUID}"\n\t\t\t\t\t(page "{page}")\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')


def mk_sym(name, desc, rect, pins, texts=(), lines=(), hide_names=False, ref=(0, 0), val=(0, 0), name_off=0.254):
    """Project library symbol, IEC 60617 style (hardware skill, section 11): rectangle with the qualifying symbol.
    pins: (number, name, etype, shape, x, y, angle, length). Symbol coordinates, y up."""
    f = '(effects (font (size 1.27 1.27)))'
    pr = lambda k, v, at, hide: (f'\t(property "{k}" "{v}" (at {at[0]} {at[1]} 0) (show_name no) (do_not_autoplace no)'
                                 f'{" (hide yes)" if hide else ""} {f})\n')
    t = (f'(symbol "shack-interface:{name}"\n\t(pin_names (offset {name_off}){" (hide yes)" if hide_names else ""})\n'
         '\t(exclude_from_sim no)\n\t(in_bom yes)\n\t(on_board yes)\n\t(in_pos_files yes)\n\t(duplicate_pin_numbers_are_jumpers no)\n')
    t += pr("Reference", "U", ref, False) + pr("Value", name, val, False) + pr("Footprint", "", (0, 0), True)
    t += pr("Datasheet", "", (0, 0), True) + pr("Description", desc, (0, 0), True)
    t += (f'\t(symbol "{name}_0_1"\n\t\t(rectangle (start {rect[0]} {rect[1]}) (end {rect[2]} {rect[3]})'
          ' (stroke (width 0.254) (type default)) (fill (type background)))\n')
    for pts in lines:
        t += '\t\t(polyline (pts ' + " ".join(f"(xy {a} {b})" for a, b in pts) + ') (stroke (width 0.254) (type default)) (fill (type none)))\n'
    for txt, x, y in texts:
        t += f'\t\t(text "{txt}" (at {x} {y} 0) {f})\n'
    t += f'\t)\n\t(symbol "{name}_1_1"\n'
    for num, nm, et, sh, x, y, a, ln, *hid in sorted(pins, key=lambda q: (not q[0].isdigit(), int(q[0]) if q[0].isdigit() else 0, q[0])):
        hide = " (hide yes)" if et == "no_connect" or hid else ""             # 9th field: hidden pin stacked on a visible one
        t += f'\t\t(pin {et} {sh} (at {x} {y} {a}) (length {ln}){hide} (name "{nm}" {f}) (number "{num}" {f}))\n'
    return t + '\t)\n\t(embedded_fonts no)\n)'

# ---------- shack interface board: symbols, sheets ----------
C2 = "Cat6 #1: 4 current loops to the matrix box (D-74, D-79, D-80)"
C3 = "SAFE loop and latch (D-62, D-75). Radio ports R1 to R3, mini-DIN 8 (D-71)"
C4 = "2 layers, 1.6 mm, L2 solid GND, routed power (D-131). No controlled impedance"
def ext(lib, name):
    return open(f"_sym/{lib}__{name}.sym").read().strip().replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)
SYMS = {k: ext(*k.split(":")) for k in (
    "Device:R", "Device:C", "Device:D", "Device:D_TVS", "Device:GDT_3Pin", "Device:LED",
    "Connector:8P8C", "Connector:Mini-DIN-8", "Connector_Generic:Conn_01x02", "Connector_Generic:Conn_01x03",
    "Transistor_BJT:Q_PNP_BEC", "Transistor_BJT:Q_PNP_BCE", "Transistor_BJT:Q_NPN_BEC", "Transistor_FET:Q_NMOS_GSD",
    "Mechanical:MountingHole_Pad", "power:GND", "power:+12V", "power:+5V", "power:+3V3", "power:PWR_FLAG",
    "Device:Fuse", "Device:D_Schottky", "Device:D_Zener", "Device:C_Polarized", "Regulator_Linear:L7805",
    "Power_Supervisor:TPS3823-xxDBV", "Interface_Expansion:PCA9539xD",
    "Connector_Generic:Conn_01x04", "Connector_Generic:Conn_01x08",
    "Isolator:PC817", "Jumper:SolderJumper_2_Open", "Device:L_Coupled", "Connector:TestPoint")}
# Schmitt inverter (same as the controller board), AND and NOR gates: IEC 60617 symbols, SOT-23-5 pin-out 1 A, 2 B, 3 GND, 4 Y, 5 VCC
SYMS["shack-interface:74LVC1G14_IEC"] = mk_sym("74LVC1G14_IEC", "Single Schmitt inverter, IEC 60617 symbol",
    (-7.62, 5.08, 5.08, -5.08),
    [("1", "NC", "no_connect", "line", -7.62, 5.08, 180, 5.08), ("2", "", "input", "line", -15.24, 0, 0, 7.62),
     ("3", "", "power_in", "line", -5.08, -10.16, 90, 5.08), ("4", "", "output", "output_low", 12.7, 0, 180, 7.62),
     ("5", "", "power_in", "line", -5.08, 10.16, 270, 5.08)],
    texts=[("1", -1.27, 3.175)], lines=[[(-2.54, -2.54), (0.635, -2.54), (0.635, 0)], [(-0.635, -2.54), (-0.635, 0), (2.54, 0)]],
    hide_names=True, ref=(2.54, 7.62), val=(2.54, -7.62))
def gate2(name, desc, q, neg):
    return mk_sym(name, desc, (-5.08, 5.08, 5.08, -5.08),
        [("1", "", "input", "line", -10.16, 2.54, 0, 5.08), ("2", "", "input", "line", -10.16, -2.54, 0, 5.08),
         ("4", "", "output", "output_low" if neg else "line", 10.16, 0, 180, 5.08),
         ("5", "", "power_in", "line", 0, 10.16, 270, 5.08), ("3", "", "power_in", "line", 0, -10.16, 90, 5.08)],
        texts=[(q, 1.27, 2.54)], ref=(2.54, 7.62), val=(2.54, -7.62))
SYMS["shack-interface:74LVC1G08_IEC"] = gate2("74LVC1G08_IEC", "Single 2-input AND, IEC 60617 symbol (TI SN74LVC1G08, Nexperia 74LVC1G08)", "&", False)
SYMS["shack-interface:74LVC1G02_IEC"] = gate2("74LVC1G02_IEC", "Single 2-input NOR, IEC 60617 symbol (TI SN74LVC1G02, Nexperia 74LVC1G02)", "\u22651", True)
# D flip-flop with set and reset, IEC 60617 qualifiers (same symbol as the controller board, D-59)
SYMS["shack-interface:74LVC1G74_IEC"] = mk_sym("74LVC1G74_IEC", "Single D flip-flop with preset and clear, IEC 60617 symbol (TI SN74LVC1G74 DCT/DCU, Nexperia 74LVC1G74DC)",
    (-5.08, 7.62, 5.08, -7.62),
    [("6", "R", "input", "input_low", -10.16, 5.08, 0, 5.08), ("7", "S", "input", "input_low", -10.16, 2.54, 0, 5.08),
     ("1", "C1", "input", "clock", -10.16, -2.54, 0, 5.08), ("2", "1D", "input", "line", -10.16, -5.08, 0, 5.08),
     ("5", "", "output", "line", 10.16, 2.54, 180, 5.08), ("3", "", "output", "output_low", 10.16, -2.54, 180, 5.08),
     ("8", "", "power_in", "line", 0, 10.16, 270, 2.54), ("4", "", "power_in", "line", 0, -10.16, 90, 2.54)],
    ref=(2.54, 10.16), val=(2.54, -10.16), name_off=1.016)
# LD1117: own symbol, pin numbers as the ST SOT-223 pin-out (1 GND, 2 OUT = tab, 3 IN), same geometry as the L7805 symbol
SYMS["shack-interface:LD1117S33"] = mk_sym("LD1117S33", "LDO 3.3 V 800 mA, SOT-223: 1 GND, 2 OUT (tab), 3 IN (ST LD1117 DocID2572 Rev 38)",
    (-5.08, 2.54, 5.08, -5.08),
    [("3", "IN", "power_in", "line", -7.62, 0, 0, 2.54), ("1", "GND", "power_in", "line", 0, -7.62, 90, 2.54),
     ("2", "OUT", "power_out", "line", 7.62, 0, 180, 2.54)], ref=(-5.08, 3.81), val=(0, 3.81))
# PhotoMOS (OptoMOS) relays, SOP4 2.54 mm: 1 LED anode, 2 LED cathode, 3 and 4 load (symmetric MOSFET pair)
def photomos(name, desc, form):
    contact = [[(1.27, 2.54), (5.08, 2.54)], [(1.27, -2.54), (5.08, -2.54)], [(1.27, -2.54), (1.27, -1.27)]]
    contact += [[(1.27, 2.54), (1.27, 0.635)], [(1.27, 0.635), (0, -1.27)]] if form == "A" else [[(1.27, 2.54), (1.27, 0.635)], [(1.27, 0.635), (1.905, -1.27)]]
    led = [[(-3.81, 1.27), (-2.54, -0.635), (-1.27, 1.27), (-3.81, 1.27)], [(-3.81, -0.635), (-1.27, -0.635)],
           [(-5.08, 2.54), (-2.54, 2.54), (-2.54, 1.27)], [(-5.08, -2.54), (-2.54, -2.54), (-2.54, -0.635)]]
    return mk_sym(name, desc, (-5.08, 5.08, 5.08, -5.08),
        [("1", "", "passive", "line", -10.16, 2.54, 0, 5.08), ("2", "", "passive", "line", -10.16, -2.54, 0, 5.08),
         ("4", "", "passive", "line", 10.16, 2.54, 180, 5.08), ("3", "", "passive", "line", 10.16, -2.54, 180, 5.08)],
        lines=led + contact, texts=[("1" + form, 3.175, 3.81)], hide_names=True, ref=(0, 7.62), val=(0, -7.62))
SYMS["shack-interface:TLP4176G"] = photomos("TLP4176G", "1-form-B photorelay 350 V 120 mA, 2.54SOP4 (Toshiba TLP4176G 2026-04-07). Second source Panasonic AQY412S (60 V 0.5 A, ASCTB140E). CPC1117N end of life (PDN EIC-1177, D-106)", "B")
SYMS["shack-interface:TLP176AM"] = photomos("TLP176AM", "1-form-A photorelay 60 V 0.7 A, 2.54 mm pitch (Toshiba TLP176AM Rev 7.0.A). Symbol pins = SOP4 positions 1 A, 2 K, 3 and 4 load = TLP176AM pins 1, 3, 4, 6. Second source Panasonic AQY212G3HS", "A")
# three-pad solder jumper: pins 1 and 3 outside, 2 common (bottom)
SYMS["shack-interface:SolderJumper_3_Open"] = mk_sym("SolderJumper_3_Open", "Solder jumper, 3 pads, open; bridge 2-1 or 2-3",
    (-2.54, 1.27, 2.54, -1.27),
    [("1", "", "passive", "line", -5.08, 0, 0, 2.54), ("3", "", "passive", "line", 5.08, 0, 180, 2.54),
     ("2", "", "passive", "line", 0, -5.08, 90, 3.81)],
    lines=[[(-0.635, 1.27), (-0.635, -1.27)], [(0.635, 1.27), (0.635, -1.27)]], hide_names=True, ref=(0, 2.54), val=(0, -2.54))
# mini-DIN 8 socket with the shield as pin 9; pin names = FT-710 TUNER/LINEAR pin-out (D-71, A-15)
DIN_NAMES = ["BD/KEY", "TX INH", "BAND C", "BAND B", "GND", "+13V", "BAND A", "TX GND"]
SYMS["shack-interface:MD-80SM"] = mk_sym("MD-80SM", "Mini-DIN 8 socket, PCB, right angle, side shielded (Same Sky MD-SM rev 1.09). Pin 9 = shield tabs",
    (-5.08, 11.43, 10.16, -10.16),
    [(str(n + 1), DIN_NAMES[n], "passive", "line", -7.62, R2(10.16 - 2.54 * n), 0, 2.54) for n in range(8)] +
    [("9", "SH", "passive", "line", 0, -12.7, 90, 2.54)], ref=(0, 12.7), val=(0, -13.97))
# chassis (frame) power symbol, IEC 60417-5020: a global net like GND
_g = open("_sym/power__GND.sym").read().strip()
_g = _g.replace('(symbol "GND"', '(symbol "shack-interface:CHASSIS"', 1).replace('(property "Value" "GND"', '(property "Value" "CHASSIS"')
_g = _g.replace('"GND_0_1"', '"CHASSIS_0_1"').replace('"GND_1_1"', '"CHASSIS_1_1"')
_g = _g.replace('Power symbol creates a global label with name \\"GND\\" , ground', 'Chassis (frame) connection, IEC 60417-5020')
_poly = lambda pts: ('\t\t\t(polyline\n\t\t\t\t(pts\n\t\t\t\t\t' + " ".join(f"(xy {x} {y})" for x, y in pts) +
                     '\n\t\t\t\t)\n\t\t\t\t(stroke\n\t\t\t\t\t(width 0)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n\t\t\t\t(fill\n\t\t\t\t\t(type none)\n\t\t\t\t)\n\t\t\t)\n')
_i = _g.index('(symbol "CHASSIS_0_1"'); _j = _g.index('(symbol "CHASSIS_1_1"')
_g = _g[:_i] + '(symbol "CHASSIS_0_1"\n' + "".join(_poly(q) for q in (
    [(0, 0), (0, -1.27)], [(-1.905, -1.27), (1.905, -1.27)], [(-1.905, -1.27), (-2.54, -2.54)],
    [(0, -1.27), (-0.635, -2.54)], [(1.905, -1.27), (1.27, -2.54)])) + '\t\t)\n\t\t' + _g[_j:]
SYMS["shack-interface:CHASSIS"] = _g
_r = open("_sym/power__GND.sym").read().strip()
_r = _r.replace('(symbol "GND"', '(symbol "shack-interface:RGND"', 1).replace('(property "Value" "GND"', '(property "Value" "RGND"')
_r = _r.replace('"GND_0_1"', '"RGND_0_1"').replace('"GND_1_1"', '"RGND_1_1"').replace("(power global)", "(power local)")
_r = _r.replace('Power symbol creates a global label with name \\"GND\\" , ground', 'Radio GND of one port: local net, one per sheet instance (floating port)')
_r = _r.replace("(type none)", "(type outline)", 1)        # filled triangle: radio GND, apart from the hollow GND triangle
assert "(power local)" in _r and "RGND_1_1" in _r
SYMS["shack-interface:RGND"] = _r
# ESP32-C3 Rust board (DevKit-RUST-1 Rev 1.2a and DevKit-RUST-2 Rev 2.0) as one board symbol, drawn as the physical board (D-93).
# Pad numbers = esp-rs Rust_Board symbol and footprint (github.com/esp-rs/esp-rust-board): left header 1..16 top to bottom,
# right header 28..17 top to bottom, pad 28 level with pad 5. Pads 29, 30 (battery connector) are not on the headers.
# Names: RUST-1 silkscreen. Pad 12 IO7 = SDA on RUST-2, LED on RUST-1; pad 17 IO10 = SDA on RUST-1, not connected on RUST-2.
DK_L = ["RST", "3V3", "NC", "GND", "IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7", "IO8/SCL", "IO21/TXD", "IO20/RXD", "IO9/BOOT"]
DK_R = {28: "VBAT", 27: "EN", 26: "VBUS", 25: "NC", 24: "NC", 23: "NC", 22: "NC", 21: "NC", 20: "IO18/D-", 19: "IO19/D+",
        18: "IO8/SCL", 17: "IO10/SDA"}
SYMS["shack-interface:ESP32-C3-DevKit-RUST"] = mk_sym("ESP32-C3-DevKit-RUST",
    "ESP32-C3 Rust board (DevKit-RUST-1 Rev 1.2a or DevKit-RUST-2 Rev 2.0) in two socket headers. Pads as the esp-rs Rust_Board footprint, 1..28",
    (-15.24, 20.32, 15.24, -25.4),
    [(str(n + 1), DK_L[n], "passive", "line", -17.78, R2(17.78 - 2.54 * n), 0, 2.54) for n in range(16)] +
    [(str(p), nm, "passive", "line", 17.78, R2(17.78 - 2.54 * (32 - p)), 180, 2.54) for p, nm in DK_R.items()],
    texts=[("ESP32-C3-MINI-1", 5.08, 15.24), ("USB-C", 0, -23.495)], ref=(-15.24, 24.13), val=(-15.24, 21.59))
# USB-C 2.0 receptacle (GCT USB4105-GF-A, KiCad footprint pad names). Duplicate contacts stacked as hidden pins: D+ A6/B6,
# D- A7/B7, VBUS A4/A9/B4/B9, GND A1/A12/B1/B12. SBU not used. Signal pins on the left (they face the MCU block on the root).
SYMS["shack-interface:USB_C_USB2.0_16P"] = mk_sym("USB_C_USB2.0_16P", "USB 2.0 Type-C receptacle, 16 contacts, duplicate contacts stacked (D-96)",
    (-7.62, 10.16, 7.62, -7.62),
    [("A6", "D+", "passive", "line", -10.16, 7.62, 0, 2.54), ("B6", "D+", "passive", "line", -10.16, 7.62, 0, 2.54, True),
     ("A7", "D-", "passive", "line", -10.16, 5.08, 0, 2.54), ("B7", "D-", "passive", "line", -10.16, 5.08, 0, 2.54, True),
     ("A4", "VBUS", "passive", "line", -10.16, 2.54, 0, 2.54)] +
    [(n, "VBUS", "passive", "line", -10.16, 2.54, 0, 2.54, True) for n in ("A9", "B4", "B9")] +
    [("A5", "CC1", "passive", "line", -10.16, 0, 0, 2.54), ("B5", "CC2", "passive", "line", -10.16, -2.54, 0, 2.54),
     ("A8", "SBU1", "no_connect", "line", -7.62, -5.08, 0, 0), ("B8", "SBU2", "no_connect", "line", -7.62, -5.08, 0, 0),
     ("A1", "GND", "passive", "line", -2.54, -10.16, 90, 2.54)] +
    [(n, "GND", "passive", "line", -2.54, -10.16, 90, 2.54, True) for n in ("A12", "B1", "B12")] +
    [("SH", "SHIELD", "passive", "line", 2.54, -10.16, 90, 2.54)], ref=(0, 11.43), val=(0, -11.43))
# ESD array, same pin-out as the KiCad Power_Protection:USBLC6-2SC6 symbol (1, 6 I/O1; 3, 4 I/O2; 2 GND; 5 VBUS), drawn flow-through
SYMS["shack-interface:USBLC6-2SC6"] = mk_sym("USBLC6-2SC6", "ESD protection, 2 data lines + VBUS, SOT-23-6 (ST USBLC6-2). Pins 1, 6 = I/O1; 3, 4 = I/O2 (D-96)",
    (-5.08, 5.08, 5.08, -5.08),
    [("1", "I/O1", "passive", "line", -7.62, 2.54, 0, 2.54), ("6", "I/O1", "passive", "line", 7.62, 2.54, 180, 2.54),
     ("3", "I/O2", "passive", "line", -7.62, -2.54, 0, 2.54), ("4", "I/O2", "passive", "line", 7.62, -2.54, 180, 2.54),
     ("2", "GND", "passive", "line", -2.54, -7.62, 90, 2.54), ("5", "VBUS", "passive", "line", 2.54, -7.62, 90, 2.54)],
    hide_names=True, ref=(0, 6.35), val=(0, -6.35))
PINS = {k: pins_of(v) for k, v in SYMS.items()}
PINS_U = {}

SHEETS = [("link", "Link to the box", "link.kicad_sch"), ("power", "Power", "power.kicad_sch"), ("mcu", "MCU and expander", "mcu.kicad_sch"), ("safe", "SAFE latch", "safe.kicad_sch"),
          ("r1", "Radio port R1", "radioport.kicad_sch"), ("r2", "Radio port R2", "radioport.kicad_sch"), ("r3", "Radio port R3", "radioport.kicad_sch")]
SUUID = {s[0]: str(uuid.uuid5(NS, "sheet/" + s[0])) for s in SHEETS}
PATH = {s[0]: f"/{ROOT_UUID}/{SUUID[s[0]]}" for s in SHEETS}
SOT23, SOT223, SOD123 = "Package_TO_SOT_SMD:SOT-23", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", "Diode_SMD:D_SOD-123"
R0603 = "Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder"
C0603 = "Capacitor_SMD:C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"
MELF0207 = "Resistor_SMD:R_MELF_MMB-0207"
QN_D = "N-MOSFET 60 V, RDS(on) specified at VGS 2.5 V (BSS138BK, Nexperia). Second source Diotec MMFTN138K (same limits and pin-out, D-134)"
TP_FP = "TestPoint:TestPoint_Pad_D1.5mm"
CMC_FP = "shack-interface:L_CMC_TDK_ACT45B"
CMC_D = ("Common-mode choke per Cat6 pair at the entry, after the GDT (D-130): 51 uH CAN type, 1812. TDK ACT45B-510-2P-TL003; "
         "second sources Murata DLW43SH510XK2L, Coilcraft 1812CAN-513 (D-151). Footprint from the TDK land pattern, as the controller board (D-149)")
# Cat6 #1 pairs (T568B), + wire first (D-56), and the shack-end role of each loop (D-62, D-63, D-80)
# (k, pins, enable signal, enable pull, sense output)
LOOPS = [(1, (4, 5), "DATA_TX", "down", None),          # data shack to box: source switched by the UART
         (2, (1, 2), "R1_TX", "down", None),            # PTT to R1 K0: source switched by R1 TX sense, in hardware
         (3, (3, 6), "SW_STOP_N", "up", "SAFE_LOST"),   # SAFE: KILL switch in series, software stop, sensed
         (4, (7, 8), None, None, "DATA_RX")]            # data box to shack: box PC817 switches, sensed
BAND = 63.5

def shack_entry(S, k, yp):
    """Pair exit to the cable: TVS across the pair, 47R pulse resistor per wire, GDT to CHASSIS. Returns (P start, N start)."""
    yn = R2(yp + 10.16)
    n = 10 * k
    XT, XR, XG, XL = 132.08, 135.89, 157.48, 172.72
    T = S.part("Device:D_TVS", ("D", n + 1), "SMBJ15CA", "Diode_SMD:D_SMB", XT, R2(yn - 3.81), rot=90, mpn="SMBJ15CA",
               desc="Bidirectional TVS 600 W across the pair, VRM 15 V, VCL 24.4 V at 25.1 A 10/1000 us (ST DS1283 Rev 14). Same as the box entry (D-58)",
               rp=(-1.27, -2.54, "right"))
    assert T["2"] == (XT, R2(yp + 2.54)) and T["1"] == (XT, yn), T
    RP = S.part("Device:R", ("R", n + 1), "47R", MELF0207, XR, yp, rot=90, rp=(1.27, -2.54),
                desc="Pulse-proof series resistor (thin-film MELF 0207): the GDT fires first. Same as the box (D-58)")
    RN = S.part("Device:R", ("R", n + 2), "47R", MELF0207, XR, yn, rot=90, rp=(1.27, 3.81), desc="As R above, N wire")
    G = S.part("Device:GDT_3Pin", ("GD", k), "2036-09-B2LF", "shack-interface:GDT_3Pin_P4.40mm_Bourns-2036-B2_Littelfuse-SL1003A-R", XG, R2(yp + 5.08), mirror="y", mpn="2036-09-B2LF",
               desc="3-electrode GDT 90 V, THT (Bourns 2036 Rev B 01/26), centre electrode to the shack earth (CHASSIS). Same as the box. Second source Littelfuse SL1003A090R-001 on the same holes (D-149)",
               rp=(-3.81, 25.4, "right"))
    assert G["3"] == (XG, yp) and G["1"] == (XG, yn) and G["2"] == (R2(XG + 5.08), R2(yp + 5.08)), G
    CM = S.part("Device:L_Coupled", ("L", k), "51u CMC", CMC_FP, 148.59, R2(yp + 5.08), mpn="ACT45B-510-2P-TL003", desc=CMC_D, rp=(-5.08, 25.4))
    assert CM["1"] == (143.51, R2(yp + 2.54)) and CM["2"] == (153.67, R2(yp + 2.54)) and CM["3"] == (143.51, R2(yp + 7.62)) and CM["4"] == (153.67, R2(yp + 7.62)), CM
    assert RP["1"] == (XT, yp) and RN["1"] == (XT, yn) and RP["2"] == (139.7, yp) and RN["2"] == (139.7, yn), (RP, RN)
    S.wire((XT, yp), T["2"])
    S.wire(RP["2"], (143.51, yp), CM["1"])
    S.wire(CM["2"], (153.67, yp), G["3"], (XL, yp)); S.label("H", f"L{k}P", XL, yp, 0)
    S.wire(RN["2"], (143.51, yn), CM["3"])
    S.wire(CM["4"], (153.67, yn), G["1"], (XL, yn)); S.label("H", f"L{k}N", XL, yn, 0)
    YP = S.part("Device:C", ("C", 20 + 2 * k), "DNP 1n 1kV", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", 143.51, R2(yp - 3.81), dnp=True,
                rp=(1.27, -6.35), desc="P wire to CHASSIS behind the choke, footprint only: fit on the bench if the loops pick up HF (D-130)")
    assert YP["2"] == (143.51, yp), YP
    S.label("H", "CHASSIS", 143.51, R2(yp - 7.62), 90)
    YN = S.part("Device:C", ("C", 21 + 2 * k), "DNP 1n 1kV", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", 143.51, R2(yn + 3.81), dnp=True,
                rp=(1.27, 3.81), desc="N wire to CHASSIS behind the choke, footprint only (D-130)")
    assert YN["1"] == (143.51, yn), YN
    S.label("H", "CHASSIS", 143.51, R2(yn + 7.62), 270)
    S.wire(G["2"], (R2(XG + 10.16), R2(yp + 5.08))); S.label("H", "CHASSIS", R2(XG + 10.16), R2(yp + 5.08), 0)
    assert T["1"] == RN["1"], (T, RN)                        # TVS on the R pins
    return (XT, yp), (XT, yn)

def loop_source(S, k, y0, en, pull):
    """PNP current source from +13V8 (D-74, D-79): Q1 BCP53 pass, Q2 BC857 sense, Rcs 56R, Rb 22k.
    en: None = always on; else an N-MOSFET in the Rb path, gate from the hierarchical label en. Returns the Q1 collector."""
    n = 10 * k
    X = 106.68
    S.power("+13V8", (86.36, y0))
    RC = S.part("Device:R", ("R", n + 3), "56R", R0603, X, R2(y0 + 6.35), rp=(-1.27, 0, "right"),
                desc="Current set: I = VBE(Q2) / 56R = 9.5 to 13.2 mA (C-24)")
    Q1 = S.part("Transistor_BJT:Q_PNP_BCE", ("Q", n + 1), "BCP53-16", SOT223, R2(X - 2.54), R2(y0 + 15.24), mirror="x", mpn="BCP53-16",
                desc="PNP 80 V 1 A SOT-223, loop current pass transistor (Nexperia BCP53 Rev 11). 38 V / 80 V = 0.48; short 0.13 W. onsemi, Diodes",
                rp=(6.35, 7.62))                                     # text below the loop wire
    assert Q1["3"] == RC["2"] == (X, R2(y0 + 10.16)) and Q1["2"] == (X, R2(y0 + 20.32)) and Q1["1"] == (99.06, R2(y0 + 15.24)), (Q1, RC)
    Q2 = S.part("Transistor_BJT:Q_PNP_BEC", ("Q", n + 2), "BC857B", SOT23, 93.98, R2(y0 + 10.16), rot=180, mpn="BC857B",
                desc="PNP 45 V SOT-23, current sense (Nexperia BC857 Rev 9). Sees about 1.3 V. Jellybean", rp=(-6.35, 1.27, "left"))
    assert Q2["1"] == (99.06, R2(y0 + 10.16)) and Q2["2"] == (91.44, R2(y0 + 5.08)) and Q2["3"] == (91.44, R2(y0 + 15.24)), Q2
    S.wire((86.36, y0), (91.44, y0), (X, y0), RC["1"])
    S.wire((91.44, y0), Q2["2"])
    S.wire(Q2["1"], RC["2"])
    RB = S.part("Device:R", ("R", n + 4), "22k", R0603, 96.52, R2(y0 + 19.05), rp=(-1.27, 1.27, "right"),
                desc="Base drive: 0.5 mA, above IB = 13.2 mA / hFE 63 = 0.21 mA (C-24)")
    assert RB["1"] == (96.52, R2(y0 + 15.24)), RB
    S.wire(Q2["3"], RB["1"], Q1["1"])
    if en is None:
        S.power("GND", RB["2"])
        return Q1["2"]
    QE = S.part("Transistor_FET:Q_NMOS_GSD", ("Q", n + 3), "BSS138BK", SOT23, 93.98, R2(y0 + 27.94), mpn="BSS138BK", desc=QN_D,
                rp=(6.35, -3.81))
    assert QE["3"] == RB["2"] and QE["1"] == (88.9, R2(y0 + 27.94)), QE
    S.power("GND", QE["2"])
    g = QE["1"]
    xp = 83.82 if pull == "down" else 76.2
    S.wire(g, (xp, g[1]), (25.4, g[1])); S.label("H", en, 25.4, g[1], 180)
    if pull == "down":
        RG = S.part("Device:R", ("R", n + 5), "100k", R0603, xp, R2(g[1] + 3.81), rp=(1.27, 1.27),
                    desc="Gate pull-down: source off (loop open) while the MCU is not running")
        S.power("GND", RG["2"])
    else:
        RG = S.part("Device:R", ("R", n + 5), "100k", R0603, xp, R2(g[1] - 3.81), rp=(1.27, -1.27),
                    desc="Gate pull-up: SAFE source on while the expander pin is an input (power-up, reset). SW_STOP_N low opens the loop")
        S.power("+3V3", RG["1"])
    return Q1["2"]

def loop_sense(S, k, y0, xn, yn, out):
    """Return path: N wire down to Rs 100R to GND; NPN BC847 senses the drop (D-80). Output low while current flows."""
    n = 10 * k
    ys = R2(y0 + 45.72)
    S.wire((xn, yn), (124.46, yn), (124.46, ys))
    RS = S.part("Device:R", ("R", n + 6), "100R", R0603, 124.46, R2(ys + 3.81), rp=(1.27, 1.27),
                desc="Loop sense: 0.95 to 1.32 V at 9.5 to 13.2 mA; NPN threshold about 0.6 V = about 6 mA (C-24)")
    assert RS["1"] == (124.46, ys)
    S.power("GND", RS["2"])
    RI = S.part("Device:R", ("R", n + 7), "1k", R0603, 116.84, ys, rot=90, rp=(-2.54, -2.54),
                desc="Base series resistor")
    S.wire(RI["2"], (124.46, ys))
    QD = S.part("Transistor_BJT:Q_NPN_BEC", ("Q", n + 4), "BC847B", SOT23, 107.95, ys, mirror="y", mpn="BC847B",
                desc="NPN 45 V SOT-23, loop sense (Nexperia BC847, jellybean)", rp=(-5.08, 2.54, "left"))
    assert QD["1"] == RI["1"] and QD["3"] == (105.41, R2(ys - 5.08)), QD
    S.power("GND", QD["2"])
    DB = S.part("Device:D", ("D", n + 3), "1N4148W", SOD123, 113.03, R2(ys + 3.81), rot=270, mpn="1N4148W",
                rp=(1.27, 1.27), desc="Base-emitter reverse protection (VEBO 6 V) against negative pulses on the N wire")
    assert DB["1"] == (113.03, ys) and DB["2"] == (113.03, R2(ys + 7.62)), DB
    S.power("GND", DB["2"])
    RU = S.part("Device:R", ("R", n + 8), "10k", R0603, 105.41, R2(ys - 8.89), rp=(1.27, -1.27), desc="Collector pull-up to 3.3 V")
    S.power("+3V3", RU["1"])
    yo = R2(y0 + 53.34)
    S.wire(QD["3"], (91.44, R2(ys - 5.08)), (91.44, yo), (25.4, yo)); S.label("H", out, 25.4, yo, 180)

def link_sheet():
    S = Sheet("Shack interface: link to the matrix box", "A3", [(PATH["link"], 0)], pwr_base=[100])
    S.mx = 203.2            # drawn mirrored: cable side on the left, logic side on the right, as on the root block
    for i, (k, _, en, pull, sense) in enumerate(LOOPS):
        y0 = R2(25.4 + i * BAND)
        c = loop_source(S, k, y0, en, pull)
        yp = c[1]
        (xp, _), (xn, yn) = shack_entry(S, k, yp)
        if k == 3:                                      # KILL switch in series with the SAFE loop, on the front panel
            Y1, Y2 = R2(y0 - 12.7), R2(y0 - 7.62)                # KILL switch wires out on the cable side, like the root block
            S.wire(c, (111.76, yp), (111.76, Y1), (172.72, Y1)); S.label("H", "KILL_1", 172.72, Y1, 0)
            S.wire((172.72, Y2), (119.38, Y2), (119.38, yp), (xp, yp)); S.label("H", "KILL_2", 172.72, Y2, 0)
        else:
            S.wire(c, (xp, yp))
        if sense:
            loop_sense(S, k, y0, xn, yn, sense)
        else:
            S.wire((xn, yn), (124.46, yn), (124.46, R2(yn + 5.08))); S.power("GND", (124.46, R2(yn + 5.08)))
    S.text("Link to the matrix box (D-56, D-62, D-74, D-79, D-80): Cat6 #1 UTP, T568B, + wire first.\\n"
           "Pair 1 = pins 4/5 data to the box, pair 2 = 1/2 PTT (R1 K0), pair 3 = 3/6 SAFE, pair 4 = 7/8 data from the box.\\n"
           "Each loop: PNP current source from +13V8, 9.5 to 13.2 mA (C-24). Isolation is at the box end only (optos, D-56).\\n"
           "Loop 1: DATA_TX high (UART idle) = current = box DATA_RX low (inverted UART). MCU off = loop open.\\n"
           "Loop 2: R1_TX (FT-710 TX GND through the R1 TX sense) switches the source in hardware: PTT to R1 K0 without the MCU.\\n"
           "Loop 3 SAFE: KILL switch in series (front panel); SW_STOP_N low turns the source off (software stop).\\n"
           "The box READY switch closes the loop (D-62). SAFE_LOST high = no loop current (to the SAFE latch).\\n"
           "Loop 4: the box PC817 switches the current; DATA_RX low = current (inverted UART).\\n"
           "Drawn with the cable side on the left and the logic side on the right, as the block on the root sheet.", 218.44, 25.4)
    return S.finish()

def power_sheet():
    S = Sheet("Shack interface: power 13.8 V, 5 V, 3.3 V", "A3", [(PATH["power"], 0)], pwr_base=[300])
    Y = 50.8
    cap = lambda ref, val, fp, x, desc, lib="Device:C": S.part(lib, ("C", ref), val, fp, x, R2(Y + 3.81), rp=(1.27, 1.27), desc=desc)
    S.wire((25.4, Y), (34.29, Y)); S.label("H", "VIN_P", 25.4, Y, 180)
    F = S.part("Device:Fuse", ("F", 1), "500mA T", "Fuse:Fuse_1206_3216Metric", 38.1, Y, rot=90, rp=(-2.54, -5.08), mpn="SF-1206S050",
               desc="Input fuse, slow, 500 mA (budget C-25: about 0.2 A). Bourns SF-1206S class (as the box); part to confirm")
    D = S.part("Device:D_Schottky", ("D", 1), "SS34", "Diode_SMD:D_SMC", 53.34, Y, rot=180, rp=(-2.54, -5.08), mpn="SS34-M3/57T",
               desc="Reverse-polarity series diode, Schottky 40 V 3 A, SMC (Vishay 88751, M3 = halogen-free). 14.4 / 40 = 0.36; VF about 0.35 V at 0.2 A. onsemi, Diodes")
    assert F["1"] == (34.29, Y) and D["2"] == (49.53, Y) and D["1"] == (57.15, Y), (F, D)
    S.wire(F["2"], D["2"])
    X13, XC1, XC2 = 66.04, 81.28, 96.52
    U1 = S.part("Regulator_Linear:L7805", ("U", 1), "L7805CV", "Package_TO_SOT_THT:TO-220-3_Vertical", 121.92, Y, mpn="L7805CV",
                rp=(-5.08, -7.62), desc="5 V linear regulator, TO-220 on the housing wall with an insulating pad (tab = GND) (D-82). ST DS0422 Rev 38. "
                "Second sources TI UA7805, onsemi MC7805. About 1.2 W, junction about 60 C (C-25)")
    assert U1["1"] == (114.3, Y) and U1["3"] == (129.54, Y) and U1["2"] == (121.92, R2(Y + 7.62)), U1
    S.wire(D["1"], (X13, Y), (XC1, Y), (XC2, Y), (104.14, Y), U1["1"])
    TV = S.part("Device:D_Zener", ("D", 2), "SMBJ16A", "Diode_SMD:D_SMB", X13, R2(Y + 3.81), rot=270, rp=(-1.27, 1.27, "right"), mpn="SMBJ16A",
                desc="Unidirectional TVS 600 W, VRM 16 V (above 14.4 V), VBR 17.8 to 18.7 V, VCL 26 V at 23.1 A 10/1000 us (ST DS1283 Rev 14). Littelfuse, Vishay")
    assert TV["1"] == (X13, Y), TV
    S.power("GND", TV["2"])
    C1 = cap(1, "47u 35V", "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm", XC1, "Input bulk, 105 C long-life aluminium (35 V: above the TVS clamp)", "Device:C_Polarized")
    C2 = cap(2, "330n 50V X7R", "Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder", XC2, "L7805 input capacitor 0.33 uF (ST)")
    for C in (C1, C2): S.power("GND", C["2"])
    S.power("+13V8", (X13, Y)); S.power("+13V8", (XC1, Y), flag=True)
    S.power("GND", U1["2"])
    X5 = [139.7, 154.94, 170.18]
    U2 = S.part("shack-interface:LD1117S33", ("U", 2), "LD1117S33CTR", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 190.5, Y, mpn="LD1117S33CTR",
                rp=(-5.08, -7.62), desc="3.3 V LDO 800 mA SOT-223, C version -40 to 125 C (ST DocID2572 Rev 38) (D-81). Second sources TI LM1117-3.3, Diodes AZ1117-3.3")
    assert U2["3"] == (182.88, Y) and U2["2"] == (198.12, Y), U2
    S.wire(U1["3"], (X5[0], Y), (143.51, Y)); S.wire((151.13, Y), (X5[1], Y), (162.56, Y), (X5[2], Y), (176.53, Y), U2["3"])
    R5L = S.part("Device:R", ("R", 5), "0R", "Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", 147.32, Y, rot=90,
                 desc="+5V current-measurement link: lift to measure the 5 V load (D-120)")
    assert R5L["1"] == (143.51, Y) and R5L["2"] == (151.13, Y), R5L
    C3 = cap(3, "100n", C0603, X5[0], "L7805 output capacitor 0.1 uF (ST)")
    C4 = cap(4, "10u 16V X7R", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", X5[1], "5 V rail bulk")
    C5 = cap(5, "10u 16V X7R", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", X5[2], "LD1117 input capacitor")
    for C in (C3, C4, C5): S.power("GND", C["2"])
    S.power("+5V", (X5[1], Y)); S.power("+5V", (176.53, Y), flag=True)          # U1 drives +5V through R5
    S.power("GND", U2["1"])
    X3 = [208.28, 223.52, 238.76]
    S.wire(U2["2"], (X3[0], Y), (212.09, Y)); S.wire((219.71, Y), (X3[1], Y), (X3[2], Y), (246.38, Y), (254.0, Y))
    R6L = S.part("Device:R", ("R", 6), "0R", "Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", 215.9, Y, rot=90,
                 desc="+3V3 current-measurement link: lift to measure the 3.3 V load (D-120)")
    assert R6L["1"] == (212.09, Y) and R6L["2"] == (219.71, Y), R6L
    S.power("+3V3", (246.38, Y), flag=True)                  # U2 drives +3V3 through R6
    for i, (net, x) in enumerate((("+13V8", 104.14), ("+5V", 162.56), ("+3V3", 254.0))):
        S.part("Connector:TestPoint", ("TP", 1 + i), net, TP_FP, x, Y, desc=f"Test point {net} (D-120)", bom=False, rp=(1.27, -5.08))
    C6 = cap(6, "22u 16V X7R", "Capacitor_SMD:C_1210_3225Metric_Pad1.33x2.70mm_HandSolder", X3[0],
             "LD1117 output: at least 10 uF effective at 3.3 V (ST: 10 uF minimum for stability)")
    C7 = cap(7, "1u 16V X7R", C0603, X3[1], "3.3 V rail decoupling: one value (D-127)")
    for C in (C6, C7): S.power("GND", C["2"])
    S.power("+3V3", (X3[2], Y))
    S.power("GND", (X13 - 10.16, R2(Y + 17.78))); S.wire((X13 - 10.16, R2(Y + 17.78)), (X13 - 2.54, R2(Y + 17.78)))
    S.power("GND", (X13 - 2.54, R2(Y + 17.78)), flag=True)          # GND comes in on J3 pin 2 (root sheet)
    S.text("Power (D-73, D-81, D-82, C-25): 13.8 V in, 500 mA fuse, SS34 reverse-polarity diode, SMBJ16A TVS.\\n"
           "+13V8 feeds the four loop current sources (link sheet). L7805CV on the housing wall (tab = GND, insulating pad) gives +5V.\\n"
           "LD1117S33 gives +3V3 for the DevKit, the logic and the PhotoMOS LEDs. No switch-mode converter (D-73).\\n"
           "Budget about 130 mA at 5 V and 115 mA at 3.3 V. Heat: 7805 about 1.2 W, LD1117 about 0.2 W (C-25); 11 to 15 V input checked (C-34).\\n"
           "R5, R6 0R: lift to measure the 5 V and 3.3 V loads; F1 serves for +13V8. Test points TP1 to TP3 (D-120).\\n"
           "Exceptions (D-124): SMBJ16A at 15 V max (0.94); L7805 capacitors 330 nF in, 100 nF out per the ST datasheet.", 25.4, 88.9)
    return S.finish()

# PCA9539 0x74 pin map (D-92): IO0_0..1 to the left edge, IO0_2..IO1_5 to the bottom edge (port group, root order),
# IO1_6..7 under the chip to the right edge. Directions per bit in firmware; F1 unchanged.
EXP = ["SW_STOP_N", "R1_TX", "KEY_R1", "BAND_D", "BAND_A", "BAND_B", "BAND_C", "DISP_BL",
       "KEY_R2", "R2_TX", "DISP_DC", "KEY_R3", "R3_TX", "DISP_RST", "KILL_S", "LATCHED"]      # IO0_0..7, IO1_0..7 (D-180: LED_R1..R3 -> display)
MCU_BOTTOM = ["PERMIT_R1", "KEY_R1", "BAND_D", "BAND_A", "BAND_B", "BAND_C",
              "PERMIT_R2", "KEY_R2", "R2_TX", "PERMIT_R3", "KEY_R3", "R3_TX"]                  # = root MCU block bottom edge

def mcu_sheet():
    S = Sheet("Shack interface: MCU, supervisor and expander", "A3", [(PATH["mcu"], 0)], pwr_base=[400])
    NC = lambda p: S.raw(f'\t(no_connect\n\t\t(at {p[0]} {p[1]})\n\t\t(uuid "{U()}")\n\t)\n')
    XL, XRT, YBOT = 30.48, 388.62, 254.0                     # left, right and bottom edge of the drawing (hierarchical labels)
    # ---- DevKit: one board symbol, a short wire and a net label at each used pin (D-93) ----
    A1 = S.part("shack-interface:ESP32-C3-DevKit-RUST", ("A", 1), "ESP32-C3-DevKit-RUST-1", "shack-interface:ESP32-C3-DevKit-RUST_Socket", 101.6, 170.18,
                rp=(-15.24, -27.94), desc="ESP32-C3 Rust board pushed into gold-flash socket headers Sullins PPPC161LFBN-RC (1x16) and PPPC121LFBN-RC (1x12), rows 20.32 mm apart (D-55, D-66, D-93, D-95). RUST-1 Rev 1.2a fitted; RUST-2 fits with JP61 2-1")
    assert A1["1"] == (83.82, 152.4) and A1["16"] == (83.82, 190.5) and A1["28"] == (119.38, 162.56) and A1["17"] == (119.38, 190.5), A1
    dk = {5: "PERMIT_R1", 6: "WDI", 7: "DISP_SCK", 8: "LATCH_CLR", 9: "PERMIT_R2", 10: "PERMIT_R3", 11: "DATA_TX", 12: "SDA_IO7", 13: "SCL",
          15: "DATA_RX", 16: "DISP_MOSI"}                    # IO2 SCK, IO9 MOSI: display SPI (D-180)
    for n in range(1, 29):
        x, y = A1[str(n)]
        if n in dk: S.wire((x, y), (76.2, y)); S.label("L", dk[n], 76.2, y, 180)
        elif n == 2: S.wire((x, y), (60.96, y)); S.power("+3V3", (60.96, y), rot=90, rp=(-5.08, -2.54, "right"))
        elif n == 4: S.wire((x, y), (60.96, y)); S.power("GND", (60.96, y), rot=270, rp=(-5.08, -2.54, "right"))
        elif n == 27: S.wire((x, y), (124.46, y)); S.power("GND", (124.46, y))      # EN low: board buck off
        elif n == 17: S.wire((x, y), (127.0, y)); S.label("L", "SDA_IO10", 127.0, y, 0)   # SDA on RUST-1
        elif n in (19, 20): S.wire((x, y), (127.0, y)); S.label("L", {19: "USB_DP", 20: "USB_DN"}[n], 127.0, y, 0)   # to J14 (D-96)
        elif n != 14: NC((x, y))
    y = A1["14"][1]
    RS = S.part("Device:R", ("R", 61), "1k", R0603, 59.69, y, rot=90,
                desc="Series resistor: IO21 is the boot-ROM UART TX; limits the current into the loop 3 sense transistor during boot")
    assert RS["2"] == (63.5, y) and RS["1"] == (55.88, y), RS
    S.wire(A1["14"], RS["2"]); S.wire(RS["1"], (50.8, y)); S.label("L", "SAFE_LOST", 50.8, y, 180)
    # ---- left edge (root block order): SAFE_LOST, DATA_TX, SW_STOP_N, DATA_RX, R1_TX ----
    for nm, yy in (("SAFE_LOST", 109.22), ("DATA_TX", 114.3), ("DATA_RX", 124.46)):
        S.wire((XL, yy), (43.18, yy)); S.label("H", nm, XL, yy, 180); S.label("L", nm, 43.18, yy, 0)
    # ---- supervisor, watchdog and fault latch: same circuit as the box (D-59), gates the permits (D-66) ----
    S.text("Supervisor and fault latch (D-59, D-66)", 246.38, 40.64)
    U3 = S.part("Power_Supervisor:TPS3823-xxDBV", ("U", 3), "TPS3823A-33", "Package_TO_SOT_SMD:SOT-23-5", 269.24, 66.04,
                mpn="TPS3823A-33DBVR", rp=(-8.89, -11.43, "right"),
                desc="Supervisor 2.93 V + watchdog 0.9 to 2.5 s, push-pull RESET_N, -40 to 125 C (TI SLVS165O). A version")
    assert U3["4"] == (259.08, 63.5) and U3["1"] == (279.4, 66.04) and U3["3"] == (259.08, 68.58), U3
    RW = S.part("Device:R", ("R", 62), "1k", R0603, 251.46, 67.31, rp=(1.27, 1.27),
                desc="WDI pull-down: a floating WDI would disable the watchdog (TPS3823 7.3.4)")
    assert RW["1"] == (251.46, 63.5), RW
    S.wire((246.38, 63.5), RW["1"], U3["4"]); S.label("L", "WDI", 246.38, 63.5, 180); S.power("GND", RW["2"])
    NC(U3["3"]); S.power("+3V3", U3["5"]); S.power("GND", U3["2"])
    U4 = S.part("shack-interface:74LVC1G74_IEC", ("U", 4), "74LVC1G74", "Package_SO:SSOP-8_2.95x2.8mm_P0.65mm", 304.8, 68.58,
                mpn="SN74LVC1G74DCTR", rp=(6.35, -12.7),
                desc="D flip-flop, fault latch: D = GND, CLR_N = 3V3, PRE_N = RESET_N (TI SCES794G). Second source Nexperia 74LVC1G74DC")
    assert U4["7"] == (294.64, 66.04) and U4["6"] == (294.64, 63.5) and U4["1"] == (294.64, 71.12) and U4["2"] == (294.64, 73.66), U4
    XR, XC = 281.94, 287.02
    S.wire(U3["1"], (XR, 66.04), U4["7"])
    S.wire(U4["6"], (292.1, 63.5)); S.power("+3V3", (292.1, 63.5))
    S.wire(U4["2"], (292.1, 73.66)); S.power("GND", (292.1, 73.66))
    NC(U4["3"]); S.power("+3V3", U4["8"]); S.power("GND", U4["4"])
    S.wire(U4["1"], (XC, 71.12), (XC, 88.9)); S.wire((XC, 88.9), (294.64, 88.9)); S.label("L", "LATCH_CLR", 294.64, 88.9, 0)
    RL = S.part("Device:R", ("R", 63), "100k", R0603, XC, 92.71, rp=(-1.27, 1.27, "right"),
                desc="LATCH_CLR pull-down: no clock edge while the MCU is in reset")
    assert RL["1"] == (XC, 88.9), RL
    S.power("GND", RL["2"])
    S.wire(U4["5"], (XRT, 66.04)); S.label("H", "FAULT", XRT, 66.04, 0)
    # ---- USB-C J14 on the board edge (root): ESD array, CC pull-downs; D+ and D- to DevKit pads 19, 20 (D-96) ----
    S.text("USB-C J14 (root): ESD and CC (D-96)", 302.26, 15.24)
    UE = S.part("shack-interface:USBLC6-2SC6", ("U", 61), "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", 360.68, 25.4, mpn="USBLC6-2SC6",
                rp=(-5.08, -10.16), desc="ESD protection for D+, D- and VBUS at J14 (ST USBLC6-2 DS4260 Rev 7). Second source UMW USBLC6-2SC6 (same pin-out). C-26")
    assert UE["1"] == (353.06, 22.86) and UE["6"] == (368.3, 22.86) and UE["3"] == (353.06, 27.94) and UE["5"] == (363.22, 33.02), UE
    S.wire((XRT, 22.86), UE["6"]); S.label("H", "USB_DP", XRT, 22.86, 0); S.wire(UE["1"], (345.44, 22.86)); S.label("L", "USB_DP", 345.44, 22.86, 180)
    S.wire((XRT, 27.94), UE["4"]); S.label("H", "USB_DN", XRT, 27.94, 0); S.wire(UE["3"], (345.44, 27.94)); S.label("L", "USB_DN", 345.44, 27.94, 180)
    S.power("GND", UE["2"])
    S.wire(UE["5"], (363.22, 35.56), (365.76, 35.56), (XRT, 35.56)); S.label("H", "USB_VBUS", XRT, 35.56, 0)
    CV = S.part("Device:C", ("C", 64), "100n 16V", C0603, 365.76, 39.37, desc="VBUS bypass at the ESD array (ST USBLC6-2 layout note)")
    assert CV["1"] == (365.76, 35.56), CV
    S.power("GND", CV["2"])
    for k, (nm, yc) in enumerate((("USB_CC1", 48.26), ("USB_CC2", 58.42))):
        RC = S.part("Device:R", ("R", 64 + k), "5k1", R0603, 375.92, yc, rot=90,
                    desc=f"{nm[4:]} pull-down Rd 5.1k: the host sees a device and enables the port (USB Type-C)")
        assert RC["2"] == (379.73, yc), RC
        S.wire(RC["2"], (XRT, yc)); S.label("H", nm, XRT, yc, 0); S.power("GND", RC["1"])
    for i, (x, what) in enumerate(((330.2, "U3"), (342.9, "U4"))):
        C = S.part("Device:C", ("C", 61 + i), "1u 16V X7R", C0603, x, 81.28, desc=f"{what} decoupling, at the part (one value, D-127)")
        S.power("+3V3", C["1"]); S.power("GND", C["2"])
    # ---- expander 0x74 (A0 = A1 = GND), RESET = RESET_N, INT not used (polled, D-68); drawn mirrored: I/O on the left ----
    EX, EY = 241.3, 139.7
    U5 = S.part("Interface_Expansion:PCA9539xD", ("U", 5), "PCA9539", "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm", EX, EY, mpn="PCA9539PW,118",
                mirror="y", rp=(-15.24, -27.94), desc="16-bit I/O expander 0x74, RESET from the supervisor. Plain PCA9539 (not R). TSSOP-24, three makers (D-133): NXP/Nexperia PCA9539PW,118, TI TCA9539PWR, Diodes PI4IOE5V9539LEX. "
                "Defaults after reset: all inputs, output register 1: write outputs 0 before configuring (F1)")
    assert U5["22"] == (254.0, 119.38) and U5["23"] == (254.0, 121.92) and U5["3"] == (254.0, 142.24) and U5["4"] == (228.6, 119.38), U5
    S.wire(U5["22"], (259.08, 119.38)); S.label("L", "SCL", 259.08, 119.38, 0)
    JS = S.part("shack-interface:SolderJumper_3_Open", ("JP", 61), "SDA SEL", "Jumper:SolderJumper-3_P1.3mm_Open_RoundedPad1.0x1.5mm_NumberLabels",
                274.32, 121.92, rot=270, rp=(2.54, 3.81),
                desc="SDA select (D-94): bridge 2-3 for DevKit-RUST-1 (SDA GPIO10, pad 17), 2-1 for DevKit-RUST-2 (SDA GPIO7, pad 12). Firmware SDA pin must match")
    assert JS["2"] == (269.24, 121.92) and JS["1"] == (274.32, 116.84) and JS["3"] == (274.32, 127.0), JS
    S.wire(U5["23"], JS["2"]); S.label("L", "SDA", 256.54, 121.92, 0)
    S.wire(JS["1"], (274.32, 111.76)); S.label("L", "SDA_IO7", 274.32, 111.76, 90)
    S.wire(JS["3"], (274.32, 132.08)); S.label("L", "SDA_IO10", 274.32, 132.08, 270)
    S.wire((XR, 66.04), (XR, 142.24), U5["3"]); S.label("L", "RESET_N", 257.81, 142.24, 0)
    NC(U5["1"])
    S.wire(U5["21"], (259.08, U5["21"][1])); S.wire(U5["2"], (259.08, U5["2"][1]))
    S.wire((259.08, U5["21"][1]), (259.08, U5["2"][1]), (259.08, 165.1)); S.power("GND", (259.08, 165.1))
    S.power("+3V3", U5["24"]); S.power("GND", U5["12"])
    C = S.part("Device:C", ("C", 63), "1u 16V X7R", C0603, 251.46, 104.14, desc="U5 decoupling, at the part (one value, D-127)")
    S.power("+3V3", C["1"]); S.power("GND", C["2"])
    io = {nm: U5[str(4 + i) if i < 8 else str(13 + i - 8)] for i, nm in enumerate(EXP)}
    # left edge: SW_STOP_N straight across, R1_TX steps down past the DATA_RX label
    S.wire(io["SW_STOP_N"], (XL, 119.38)); S.label("H", "SW_STOP_N", XL, 119.38, 180)
    S.wire(io["R1_TX"], (60.96, 121.92), (60.96, 129.54), (XL, 129.54)); S.label("H", "R1_TX", XL, 129.54, 180)
    # bottom edge: one vertical per signal, 5.08 mm pitch, in the root order; permits from the DevKit labels
    bx = {nm: R2(149.86 + 5.08 * k) for k, nm in enumerate(MCU_BOTTOM)}
    for nm in MCU_BOTTOM:
        x = bx[nm]
        if nm.startswith("PERMIT"): S.wire((x, 241.3), (x, YBOT)); S.label("L", nm, x, 241.3, 90)
        else: S.wire(io[nm], (x, io[nm][1]), (x, YBOT))
        S.label("H", nm, x, YBOT, 270)
    assert max(bx.values()) < 223.52, bx
    # display control from the expander (D-180): short stub and a net label at each pin
    for nm in ("DISP_BL", "DISP_DC", "DISP_RST"):
        x, y = io[nm]; S.wire((x, y), (R2(x - 2.54), y)); S.label("L", nm, R2(x - 2.54), y, 180)
    # display connector J15: the Waveshare 1.9" LCD module cable (P2 order BL, RST, DC, CS, CLK, DIN, GND, VCC), CS tied low
    S.text("Display J15 (D-180)", 25.4, 205.74)
    JD = S.part("Connector_Generic:Conn_01x08", ("J", 15), "DISPLAY", "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
                55.88, 223.52, desc="Waveshare 1.9inch LCD Module (ST7789V2, 170 x 320) cable: 1 BL, 2 RST, 3 DC, 4 CS (GND), 5 CLK, 6 DIN, 7 GND, "
                "8 VCC 3.3 V (module: RT9193-33, TXS0108, backlight about 40 mA max). SPI mode 0 on IO2/IO9, DC/RST/BL on the PCA9539 (D-180)")
    jp = {n: JD[str(n)] for n in range(1, 9)}
    assert all(jp[n][0] == jp[1][0] for n in jp) and round(jp[2][1] - jp[1][1], 3) == 2.54, jp
    for n, nm in ((1, "DISP_BL"), (2, "DISP_RST"), (3, "DISP_DC"), (5, "DISP_SCK"), (6, "DISP_MOSI")):
        x, y = jp[n]; S.wire((x, y), (R2(x - 5.08), y)); S.label("L", nm, R2(x - 5.08), y, 180)
    for n, pw in ((4, "GND"), (7, "GND"), (8, "+3V3")):
        x, y = jp[n]; S.wire((x, y), (R2(x - 5.08), y)); S.power(pw, (R2(x - 5.08), y), rot=270 if pw == "GND" else 90, rp=(-5.08, -2.54, "right"))
    # right edge: LATCHED and KILL_S under the chip
    for nm, xt, yt in (("LATCHED", 226.06, 177.8), ("KILL_S", 223.52, 180.34)):
        S.wire(io[nm], (xt, io[nm][1]), (xt, yt), (XRT, yt)); S.label("H", nm, XRT, yt, 0)
    S.text("MCU: ESP32-C3 Rust board (A1) in two socket headers, the same module as the box (D-66). DevKit-RUST-1 Rev 1.2a fitted, RUST-2 also fits.\\n"
           "Pads as the esp-rs Rust_Board footprint: left 1..16, right 28..17 top to bottom (D-93). SDA SEL JP61: 2-3 RUST-1 (SDA IO10), 2-1 RUST-2 (SDA IO7) (D-94). Net labels at the DevKit pins; everything else is wired. 3V3 pin from the LD1117 (power sheet); EN low keeps the board buck off;\\n"
           "5V not connected. USB-C to the Mac (Delock 64226) or the Pi (D-68).\\n"
           "Direct GPIO (D-83): IO0 PERMIT_R1, IO1 WDI (kick at least every 0.9 s), IO3 LATCH_CLR (rising edge), IO4 PERMIT_R2, IO5 PERMIT_R3,\\n"
           "IO6 DATA_TX, IO20 DATA_RX, IO21 SAFE_LOST (boot-ROM log pin, 1k series). SDA IO10 or IO7, SCL IO8 (board 10k pull-ups, SHTC3 0x70, IMU 0x68).\\n"
           "IO2 DISP_SCK (WS2812 on the board sees only short pulses), IO9 DISP_MOSI (BOOT button: a press only disturbs the picture); both straps keep their pull-ups (D-180).\\n"
           "Board LED on IO7 (RUST-1) or IO10 (RUST-2): the SDA pin of the other board.\\n"
           "Fault latch (D-59): FAULT set at power-up, brown-out and watchdog time-out; cleared by a LATCH_CLR edge only when RESET_N is high.\\n"
           "FAULT goes to the SAFE sheet and blocks every permit in hardware. RESET_N also resets the PCA9539: keys off, SW_STOP_N released.\\n"
           "PCA9539 0x74 (D-92): IO0_0 SW_STOP_N (out), IO0_1 R1_TX, IO0_2 KEY_R1 (out), IO0_3 BAND_D, IO0_4 BAND_A, IO0_5 BAND_B, IO0_6 BAND_C,\\n"
           "IO0_7 DISP_BL (out), IO1_0 KEY_R2 (out), IO1_1 R2_TX, IO1_2 DISP_DC (out), IO1_3 KEY_R3 (out), IO1_4 R3_TX, IO1_5 DISP_RST (out),\\n"
           "IO1_6 KILL_S, IO1_7 LATCHED. Inputs not marked. Write outputs 0 before configuring (F1).", 25.4, 22.86)
    return S.finish()

def safe_sheet():
    """SAFE latch, RESET and TX enable (D-62, D-75, D-84). Sides as on the root block (D-92): SAFE_LOST top;
    FAULT, LATCHED, KILL_S left; TX_EN, BTN, LED_SAFE, LED_LATCHED right. Two crossings are needed with this pin order:
    SAFE_LOST crosses FAULT and LATCHED (no junction)."""
    S = Sheet("Shack interface: SAFE latch, RESET and TX enable", "A3", [(PATH["safe"], 0)], pwr_base=[500])
    SOT5, SSOP8 = "Package_TO_SOT_SMD:SOT-23-5", "Package_SO:SSOP-8_2.95x2.8mm_P0.65mm"
    nc = lambda p: S.raw(f'\t(no_connect\n\t\t(at {p[0]} {p[1]})\n\t\t(uuid "{U()}")\n\t)\n')
    XL, XR, YT = 25.4, 203.2, 30.48
    YF, YQ, YB, YS, YL, YK = 45.72, 55.88, 111.76, 132.08, 147.32, 165.1      # FAULT, LATCHED, BTN, LED_SAFE, LED_LATCHED, KILL_S rows
    # loop OK: SAFE_LOST from the top edge, inverted (Schmitt)
    U7 = S.part("shack-interface:74LVC1G14_IEC", ("U", 7), "74LVC1G14", SOT5, 60.96, 76.2, mpn="74LVC1G14GV", rp=(2.54, -12.7),
                desc="Schmitt inverter: SAFE_OK = NOT SAFE_LOST (loop current present). Nexperia, TI, Diodes")
    assert U7["2"] == (45.72, 76.2) and U7["4"] == (73.66, 76.2), U7
    S.label("H", "SAFE_LOST", 45.72, YT, 90); S.wire((45.72, YT), U7["2"])
    nc(U7["1"]); S.power("+3V3", U7["5"]); S.power("GND", U7["3"])
    # PRE_N = SAFE_OK AND POR_N: a lost loop or a power-up sets the latch
    U8 = S.part("shack-interface:74LVC1G08_IEC", ("U", 8), "74LVC1G08", SOT5, 104.14, 78.74, mpn="74LVC1G08GV", rp=(2.54, -12.7),
                desc="2-input AND: PRE_N = SAFE_OK AND POR_N. Nexperia, TI, Diodes")
    assert U8["1"] == (93.98, 76.2) and U8["2"] == (93.98, 81.28) and U8["4"] == (114.3, 78.74), U8
    S.wire(U7["4"], (78.74, 76.2), U8["1"]); S.label("L", "SAFE_OK", 81.28, 76.2)
    S.power("+3V3", U8["5"]); S.power("GND", U8["3"])
    # power-on reset of the latch: second supervisor, drawn mirrored under U8; WDI open = watchdog disabled (D-84)
    U6 = S.part("Power_Supervisor:TPS3823-xxDBV", ("U", 6), "TPS3823A-33", SOT5, 101.6, 109.22, mpn="TPS3823A-33DBVR", mirror="y",
                rp=(6.35, -11.43, "left"),
                desc="Power-on and brown-out reset for the SAFE latch. WDI left open: watchdog disabled (TPS3823 7.3.4). MR open (90k pull-up)")
    assert U6["1"] == (91.44, 109.22), U6
    nc(U6["4"]); nc(U6["3"]); S.power("+3V3", U6["5"]); S.power("GND", U6["2"])
    S.wire(U6["1"], (91.44, 81.28), U8["2"]); S.label("L", "POR_N", 91.44, 101.6, 90)
    # SAFE latch (D-75): D = GND, CLR_N = 3V3, PRE_N from U8, CLK = debounced RESET
    U9 = S.part("shack-interface:74LVC1G74_IEC", ("U", 9), "74LVC1G74", SSOP8, 132.08, 81.28, mpn="SN74LVC1G74DCTR", rp=(6.35, -12.7),
                desc="SAFE latch. Q = LATCHED. Set by a lost loop or power-up; cleared by a RESET edge only while PRE_N is high (TI SCES794G)")
    assert U9["7"] == (121.92, 78.74) and U9["1"] == (121.92, 83.82) and U9["5"] == (142.24, 78.74), U9
    S.wire(U8["4"], U9["7"]); S.label("L", "PRE_N", 115.57, 78.74)
    S.wire(U9["6"], (119.38, 76.2)); S.power("+3V3", (119.38, 76.2))
    S.wire(U9["2"], (119.38, 86.36)); S.power("GND", (119.38, 86.36))
    nc(U9["3"]); S.power("+3V3", U9["8"]); S.power("GND", U9["4"])
    # TX_EN = NOR(FAULT, LATCHED): any fault or a latched SAFE stop blocks every permit and key in hardware
    U11 = S.part("shack-interface:74LVC1G02_IEC", ("U", 11), "74LVC1G02", SOT5, 170.18, 48.26, mpn="74LVC1G02GV", rp=(2.54, -12.7),
                 desc="2-input NOR: TX_EN = NOR(FAULT, LATCHED). Nexperia, TI, Diodes")
    assert U11["1"] == (160.02, 45.72) and U11["2"] == (160.02, 50.8) and U11["4"] == (180.34, 48.26), U11
    S.label("H", "FAULT", XL, YF, 180); S.wire((XL, YF), U11["1"])                     # crosses SAFE_LOST
    S.power("+3V3", U11["5"]); S.power("GND", U11["3"])
    S.wire(U11["4"], (XR, 48.26)); S.label("H", "TX_EN", XR, 48.26, 0)
    # LATCHED: Q to the NOR, to the left edge (crosses SAFE_LOST) and round the bottom to the LATCHED LED
    S.wire(U9["5"], (149.86, 78.74), (149.86, YQ), (149.86, 50.8), U11["2"])
    S.wire((149.86, YQ), (35.56, YQ), (XL, YQ)); S.label("H", "LATCHED", XL, YQ, 180)
    RL2 = S.part("Device:R", ("R", 74), "680R", R0603, 190.5, YL, rot=90, rp=(-2.54, -2.54), desc="LATCHED LED, about 2 mA")
    assert RL2["1"] == (186.69, YL), RL2
    S.wire((35.56, YQ), (35.56, YL), RL2["1"]); S.wire(RL2["2"], (XR, YL)); S.label("H", "LED_LATCHED", XR, YL, 0)
    # RESET button from the right edge: 1k series, 100k pull-up with 1N4148W across it, 100n, Schmitt inverter (mirrored): press = one rising edge (D-84)
    S.label("H", "BTN", XR, YB, 0)
    RB = S.part("Device:R", ("R", 71), "1k", R0603, 182.88, YB, rot=90, rp=(-2.54, -2.54),
                desc="Button series resistor: limits the discharge current and, with the 100n, filters ESD on the panel wire")
    RP = S.part("Device:R", ("R", 72), "100k", R0603, 160.02, R2(YB - 3.81), rp=(-1.27, 0, "right"), desc="Button node pull-up: release recharges in 10 ms")
    DB = S.part("Device:D", ("D", 71), "1N4148W", SOD123, 165.1, R2(YB - 3.81), rot=270, mpn="1N4148W", rp=(1.27, -1.27),
                desc="Discharges the 100n into 3V3 at power-down (good practice; the 74LVC1G14 input has Ioff)")
    CB = S.part("Device:C", ("C", 71), "100n", C0603, 154.94, R2(YB + 3.81), rp=(1.27, 1.27), desc="Debounce capacitor: press discharges in 0.1 ms")
    U10 = S.part("shack-interface:74LVC1G14_IEC", ("U", 10), "74LVC1G14", SOT5, 134.62, YB, mpn="74LVC1G14GV", mirror="y", rp=(-2.54, -12.7, "left"),     # mirrored part: KiCad flips the justification
                 desc="Schmitt inverter: RESET press gives a rising clock edge")
    assert RB["2"] == (186.69, YB) and RB["1"] == (179.07, YB) and RP["2"] == (160.02, YB) and DB["1"] == (165.1, R2(YB - 7.62)) \
        and DB["2"] == (165.1, YB) and CB["1"] == (154.94, YB) and U10["2"] == (149.86, YB) and U10["4"] == (121.92, YB), (RB, RP, DB, CB, U10)
    S.wire((XR, YB), RB["2"]); S.wire(RB["1"], DB["2"], RP["2"], CB["1"], U10["2"])
    S.wire(RP["1"], DB["1"]); S.power("+3V3", RP["1"]); S.power("GND", CB["2"])
    nc(U10["1"]); S.power("+3V3", U10["5"]); S.power("GND", U10["3"])
    S.wire(U10["4"], (116.84, YB), (116.84, 83.82), U9["1"]); S.label("L", "RESET_CLK", 116.84, 109.22, 90)
    # SAFE LED: from SAFE_OK down, under U6, to the right edge
    RL1 = S.part("Device:R", ("R", 73), "680R", R0603, 190.5, YS, rot=90, rp=(-2.54, -2.54), desc="SAFE LED, about 2 mA")
    assert RL1["1"] == (186.69, YS), RL1
    S.wire((78.74, 76.2), (78.74, YS), RL1["1"]); S.wire(RL1["2"], (XR, YS)); S.label("H", "LED_SAFE", XR, YS, 0)
    # KILL state: second pole of the KILL switch, closed = run (low)
    S.label("H", "KILL_S", XL, YK, 180); S.wire((XL, YK), (40.64, YK))
    RK = S.part("Device:R", ("R", 75), "2k2", R0603, 40.64, R2(YK - 3.81), rp=(1.27, 0),
                desc="KILL_S pull-up: open (KILL pressed or switch unplugged) reads high. 2k2 gives 1.5 mA, above the 1 mA contact minimum of the EAO 84 (D-181)")
    assert RK["2"] == (40.64, YK), RK
    S.power("+3V3", RK["1"])
    for i, what in enumerate(("U6", "U7", "U8", "U9", "U10", "U11")):
        C = S.part("Device:C", ("C", 72 + i), "1u 16V X7R", C0603, R2(76.2 + i * 10.16), 180.34, desc=f"{what} decoupling, at the part (one value, D-127)")
        S.power("+3V3", C["1"]); S.power("GND", C["2"])
    S.text("SAFE latch (D-62, D-75, D-84): LATCHED = 1 after a power-up or any loss of SAFE loop current.\\n"
           "Only a RESET press clears it, and only while the loop current is present (PRE_N high). A held button gives no new edge.\\n"
           "TX_EN = NOR(FAULT, LATCHED) goes to every radio port: TX INH and keying need TX_EN high (D-71).\\n"
           "POR_N: second TPS3823A-33 with WDI open (watchdog off), independent of the MCU watchdog (U3).\\n"
           "LEDs on the front panel: SAFE = loop current present; LATCHED = stop held, RESET needed.\\n"
           "Labels on the same sides as the root block (D-92). SAFE_LOST crosses FAULT and LATCHED: these wires are not connected (no junction).", 25.4, 200.66)
    return S.finish()

PORT_BASES = [200, 300, 400]
R1206 = "Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder"

def port_sheet():
    """Radio port, drawn once, placed three times (R1 to R3, D-71, D-72, D-77, D-78, D-85, D-86, D-89 to D-91).
    Sides as on the root block: logic inputs on the top edge (one vertical per row, lower rows further left),
    TX_EN on the bottom edge, radio pins (mini-DIN) and the panel LED on the right edge."""
    S = Sheet("Shack interface: radio port (R1, R2, R3)", "A3", [(PATH[k], b) for k, b in zip(("r1", "r2", "r3"), PORT_BASES)],
              pwr_base=[600, 700, 800])
    S.oy = 10.16            # whole drawing 10 mm down: the top-edge labels stay clear of the frame
    SOT5 = "Package_TO_SOT_SMD:SOT-23-5"
    XR, YT = 368.3, 17.78
    lab_r = lambda n, y: S.label("H", n, XR, y, 0)
    STX = {"PERMIT": 25.4, "KEY": 27.94, "BAND_D": 30.48, "TX": 33.02, "BAND_A": 35.56, "BAND_B": 38.1, "BAND_C": 40.64}
    def top(n, y):
        """Top-edge input n, wired straight down to its row at y. Returns the row start point."""
        x = STX[n]; S.label("H", n, x, YT, 90); S.wire((x, YT), (x, y)); return (x, y)
    rv = lambda ref, val, x, y, desc, fp=R0603, dnp=False, rp=(1.27, 1.27): S.part("Device:R", ("R", ref), val, fp, x, y, desc=desc, dnp=dnp, rp=rp)
    rh = lambda ref, val, x, y, desc, fp=R0603, dnp=False: S.part("Device:R", ("R", ref), val, fp, x, y, rot=90, desc=desc, dnp=dnp, rp=(-2.54, -2.54))
    XT, XC = 345.44, 353.06
    def clamp(n, y):
        """ESD clamp at the connector side of mini-DIN line n: bidirectional TVS and 1 nF C0G, both to the radio GND (RGND)."""
        T = S.part("Device:D_TVS", ("D", 10 + n), "PESD15VL1BA", "Diode_SMD:D_SOD-323_HandSoldering", XT, R2(y + 3.81), rot=90, mpn="PESD15VL1BA",
                   rp=(-1.27, 1.27, "right"), desc="ESD clamp, bidirectional, VRWM 15 V, VBR min 17.1 V, 30 kV (Nexperia PESD15VL1BA). Second source Bourns CDSOD323-T15C")
        C = S.part("Device:C", ("C", 10 + n), "1n C0G", C0603, XC, R2(y + 3.81), rp=(1.27, 1.27),
                   desc="RF bypass at the connector, 50 V C0G (14.4 / 50 = 0.29)")
        assert T["2"] == (XT, y) and C["1"] == (XC, y), (T, C)
        S.power("RGND", T["1"]); S.power("RGND", C["2"])
    def to_din(name, y, *pts, cl=True):
        S.wire(*pts, (XT, y), (XC, y), *([(360.68, y)] if cl else []), (XR, y)); lab_r(name, y)
        if cl:
            clamp(int(name[3]), y)
            S.part("Connector:TestPoint", ("TP", int(name[3])), name, TP_FP, 360.68, y, desc=f"Test point {name}, radio side (D-120)", bom=False, rp=(1.27, -5.08))
    # (per-radio panel LED removed: the front display shows the radio states, D-180)
    # --- BAND A to D inputs (FT-710 band data), to the expander (R1 only on the root, D-86)
    def band(k, y, out):
        RS = rh(10 + k, "1k", 76.2, y, "Series resistor: limits the current into the PCA9539 input (5.5 V tolerant, to confirm)")
        RU = rv(14 + k, "10k", 60.96, R2(y - 3.81), "Pull-up to 3.3 V: serves open-collector and push-pull band outputs (FC-40: radio outputs with 47k pull-ups in the tuner). No radio = 1111", rp=(1.27, -2.54))
        RD = rv(18 + k, "DNP", 48.26, R2(y + 3.81), "Pull-down footprint, not fitted (only for a radio that needs a low default)", dnp=True)
        S.wire(top(out, y), RD["1"], RU["2"], RS["1"])
        S.power("+3V3", RU["1"]); S.power("GND", RD["2"])
        return RS["2"]
    for k, (y, out, din) in enumerate(((68.58, "BAND_A", "DIN7"), (53.34, "BAND_B", "DIN4"), (38.1, "BAND_C", "DIN3")), 1):
        to_din(din, y, band(k, y, out))
    # --- TX sense: PC817X, two jumpers CONTACT (both 1-2) / VOLTAGE (both 2-3) (D-72, D-78, C-23)
    JP2 = S.part("shack-interface:SolderJumper_3_Open", ("JP", 3), "FEED SEL", "Jumper:SolderJumper-3_P1.3mm_Open_RoundedPad1.0x1.5mm_NumberLabels",
                 165.1, 91.44, rot=270, rp=(2.54, 6.35), desc="CONTACT feed: bridge 2-1 = radio +13V OUT (pin 6, port stays floating), 2-3 = interface +13V8 (close the GND bond too)")
    assert JP2["2"] == (160.02, 91.44) and JP2["1"] == (165.1, 86.36) and JP2["3"] == (165.1, 96.52), JP2
    to_din("DIN6", 86.36, JP2["1"], cl=False)
    S.wire(JP2["3"], (175.26, 96.52)); S.power("+13V8", (175.26, 96.52))
    JS1 = S.part("Connector_Generic:Conn_01x03", ("JP", 5), "SENSE A", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                 147.32, 101.6, rp=(3.81, -1.27), desc="TX sense, LED resistor source: 1-2 CONTACT (feed), 2-3 VOLTAGE (radio TX output on pin 8)")
    JS2 = S.part("Connector_Generic:Conn_01x03", ("JP", 6), "SENSE K", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                 147.32, 116.84, rp=(3.81, -1.27), desc="TX sense, LED cathode: 1-2 CONTACT (to pin 8, the radio closes it to its GND), 2-3 VOLTAGE (to radio GND)")
    assert JS1["2"] == (142.24, 101.6) and JS2["2"] == (142.24, 116.84), (JS1, JS2)
    S.wire(JS1["1"], (139.7, 99.06), (139.7, 91.44), JP2["2"])
    S.wire(JS1["3"], (139.7, 104.14), (139.7, 109.22), (139.7, 114.3), JS2["1"])
    to_din("DIN8", 109.22, (139.7, 109.22))
    S.wire(JS2["3"], (139.7, 119.38), (139.7, 121.92)); S.power("RGND", (139.7, 121.92))
    RS = rh(6, "2k2", 129.54, 101.6, "TX sense LED resistor: 5.7 mA at 13.8 V (C-23); 79 mW at 14.4 V, 1206 (0.32). Value per radio in VOLTAGE mode", fp=R1206)
    U5 = S.part("Isolator:PC817", ("U", 5), "PC817X", "Package_DIP:DIP-4_W7.62mm", 101.6, 109.22, mirror="y", mpn="PC817X",
                rp=(0, -8.89, "center"), desc="TX sense opto (Sharp D2-A03101EN), CTR min 50 % at 5 mA. Lite-On LTV-817, Everlight EL817 (D-78)")
    assert U5["1"] == (109.22, 106.68) and U5["2"] == (109.22, 111.76) and U5["4"] == (93.98, 106.68) and U5["3"] == (93.98, 111.76), U5
    D1 = S.part("Device:D", ("D", 1), "1N4148W", SOD123, 121.92, 109.22, rot=270, mpn="1N4148W", rp=(1.27, 0),
                desc="Anti-parallel across the opto LED (VR 6 V): a reversed VOLTAGE-mode radio (D-78)")
    assert D1["1"] == (121.92, 105.41) and D1["2"] == (121.92, 113.03), D1
    S.wire(U5["1"], (111.76, 106.68), (111.76, 101.6), (121.92, 101.6), RS["1"]); S.wire(RS["2"], JS1["2"])
    S.wire(D1["1"], (121.92, 101.6))
    S.wire(U5["2"], (111.76, 111.76), (111.76, 116.84), (121.92, 116.84), JS2["2"]); S.wire(D1["2"], (121.92, 116.84))
    S.wire(U5["4"], (93.98, 101.6)); S.power("+3V3", (93.98, 101.6))
    RE = rv(7, "10k", 83.82, 115.57, "Emitter resistor: TX output active high (emitter follower)")
    S.wire(top("TX", 111.76), RE["1"], U5["3"]); S.power("GND", RE["2"])
    # --- pin 1: BAND D (R1) or KEY (R2, R3), solder jumper (D-86); BAND D row above the KEY row
    YK = 157.48                                                   # KEY gate U2 centre
    JP1 = S.part("shack-interface:SolderJumper_3_Open", ("JP", 2), "PIN1 SEL", "Jumper:SolderJumper-3_P1.3mm_Open_RoundedPad1.0x1.5mm_NumberLabels",
                 139.7, 147.32, rot=90, rp=(6.35, 3.81), desc="Mini-DIN pin 1: bridge 2-1 = KEY (R2, R3), 2-3 = BAND D input (R1, FT-710) (D-86)")
    assert JP1["3"] == (139.7, 142.24) and JP1["1"] == (139.7, 152.4) and JP1["2"] == (144.78, 147.32), JP1
    S.wire(band(0, 139.7, "BAND_D"), (139.7, 139.7), JP1["3"])
    to_din("DIN1", 147.32, JP1["2"])
    # --- keying: U2 = KEY AND INH_ON drives the form A photorelay: the radio is keyed only with a permit (D-71, D-91)
    U2 = S.part("shack-interface:74LVC1G08_IEC", ("U", 2), "74LVC1G08", SOT5, 71.12, YK, mpn="74LVC1G08GV", rp=(2.54, -12.7),
                desc="2-input AND: KEY_ON = KEY AND INH_ON. Nexperia, TI, Diodes")
    assert U2["1"] == (60.96, 154.94) and U2["2"] == (60.96, 160.02) and U2["4"] == (81.28, YK), U2
    RK = rv(2, "100k", 40.64, 158.75, "KEY pull-down: expander pins are inputs after reset")
    S.wire(top("KEY", 154.94), RK["1"], U2["1"]); S.power("GND", RK["2"])
    S.power("+3V3", U2["5"]); S.power("GND", U2["3"])
    R5 = rh(5, "240R", 95.25, YK, "Photorelay LED drive about 7 mA from 3.3 V")
    U4 = S.part("shack-interface:TLP176AM", ("U", 4), "TLP176AM", "shack-interface:SOP-4_P2.54mm_PhotoRelay_LongPad", 114.3, 160.02, mpn="TLP176AM(TPL,E)",
                rp=(-5.08, -7.62, "right"), desc="Keying, 1-form-A photorelay 60 V 0.7 A, RON 2 ohm, IFT 3 mA, 3750 Vrms, -40 to 110 C, halogen-free (Toshiba Rev 7.0.A). "
                "14.4 / 60 = 0.24; IF 7 mA (recommended 5 to 25). Second source Panasonic AQY212G3HS. Common long-pad footprint with U3 to draw (D-91)")
    assert U4["1"] == (104.14, YK) and U4["4"] == (124.46, YK) and U4["3"] == (124.46, 162.56), U4
    S.label("L", "KEY_ON", 82.55, YK)
    S.wire(U2["4"], R5["1"]); S.wire(R5["2"], U4["1"])
    S.wire(U4["2"], (101.6, 162.56), (101.6, 167.64)); S.power("GND", (101.6, 167.64))
    S.wire(U4["4"], (139.7, YK), JP1["1"])
    S.wire(U4["3"], (127.0, 162.56)); S.power("RGND", (127.0, 162.56))
    # --- radio GND: sheet pin, RF bond to CHASSIS, GND bond jumper
    YR = 162.56
    S.wire((175.26, YR), (337.82, YR), (XT, YR), (XC, YR), (XR, YR)); lab_r("RGND", YR)      # mini-DIN pin 5, radio GND
    S.power("RGND", (XT, YR)); S.power("RGND", (337.82, YR), flag=True, rp=(0, -6.35, "center"))
    CB = S.part("Device:C", ("C", 5), "10n 1kV", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", XC, R2(YR + 3.81), rp=(1.27, 1.27),
                desc="RF and ESD bond, radio GND to CHASSIS (X7R 1 kV): the ESD current of a floating port goes to the shield, not across the board")
    S.power("CHASSIS", CB["2"])
    JP3 = S.part("Jumper:SolderJumper_2_Open", ("JP", 4), "GND BOND", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", 175.26, R2(YR + 5.08), rot=90,
                 rp=(2.54, 0), desc="Radio GND (pin 5) to interface GND. Close on R1 (BAND data needs a common reference) and in CONTACT mode with the interface feed")
    assert JP3["2"] == (175.26, YR), JP3
    S.power("GND", JP3["1"])
    # --- TX INH: U1 = PERMIT AND TX_EN drives the form B OptoMOS LED; no LED current = inhibit (D-71, D-77, C-22)
    YI = 205.74                                                   # TX INH gate U1 centre
    U1 = S.part("shack-interface:74LVC1G08_IEC", ("U", 1), "74LVC1G08", SOT5, 71.12, YI, mpn="74LVC1G08GV", rp=(2.54, -12.7),
                desc="2-input AND: INH_ON = PERMIT AND TX_EN. Nexperia, TI, Diodes")
    assert U1["1"] == (60.96, 203.2) and U1["2"] == (60.96, 208.28) and U1["4"] == (81.28, YI), U1
    RP = rv(1, "100k", 40.64, 207.01, "PERMIT pull-down: inhibit while the MCU pin floats (reset, boot)", rp=(-1.27, 1.27, "right"))
    S.wire(top("PERMIT", 203.2), RP["1"], U1["1"]); S.power("GND", RP["2"])
    S.wire(U1["2"], (45.72, 208.28), (45.72, 233.68)); S.label("H", "TX_EN", 45.72, 233.68, 270)
    S.power("+3V3", U1["5"]); S.power("GND", U1["3"])
    R3 = rh(3, "240R", 95.25, YI, "OptoMOS LED drive about 7 mA from 3.3 V (C-22)")
    U3 = S.part("shack-interface:TLP4176G", ("U", 3), "TLP4176G", "shack-interface:SOP-4_P2.54mm_PhotoRelay_LongPad", 114.3, 208.28, mpn="TLP4176G",
                rp=(-5.08, -7.62, "right"),
                desc="TX INH, 1-form-B photorelay (Toshiba TLP4176G: 350 V, 120 mA, RON max 25 ohm, IFT max 3 mA). Closed without LED current = inhibit. Second source Panasonic AQY412S (60 V, 0.5 A, RON max 2.5 ohm, IFoff max 3 mA). Common footprint D-99. D-77, D-106")
    assert U3["1"] == (104.14, YI) and U3["4"] == (124.46, YI) and U3["3"] == (124.46, 210.82), U3
    S.label("L", "INH_ON", 82.55, YI)
    S.wire(U1["4"], (86.36, YI), R3["1"]); S.wire(R3["2"], U3["1"])
    S.wire((86.36, YI), (86.36, 175.26), (55.88, 175.26), (55.88, 160.02), U2["2"])        # INH_ON up to the KEY gate
    S.wire(U3["2"], (101.6, 210.82), (101.6, 215.9)); S.power("GND", (101.6, 215.9))
    to_din("DIN2", 180.34, U3["4"], (129.54, YI), (129.54, 180.34))
    JL = S.part("Connector_Generic:Conn_01x03", ("JP", 1), "INH LEVEL", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                142.24, 210.82, rp=(3.81, -1.27), desc="TX INH level jumper: 1-2 HIGH (contact to 5.1 V from the radio supply pin), 2-3 LOW (contact to radio GND), removed = TX INH not used (D-71, D-90)")
    assert JL["1"] == (137.16, 208.28) and JL["2"] == (137.16, 210.82) and JL["3"] == (137.16, 213.36), JL
    S.wire(U3["3"], JL["2"])
    # HIGH level: radio +13V OUT through RH, clamped to 5.1 V against RGND (D-90; FC-40: TX INH is a 5 V logic input, A-18)
    RH = rh(4, "2k2", 177.8, 200.66, "HIGH level source from the radio +13V OUT: (14.4 - 5.1) V / 2k2 = 4.2 mA, 39 mW (0.39). Not fitted for radios with a LOW inhibit (saves 4 mA from pin 6)")
    DZ = S.part("Device:D_Zener", ("D", 2), "BZX384-C5V1", "Diode_SMD:D_SOD-323_HandSoldering", 165.1, 204.47, rot=270, mpn="BZX384-C5V1",
                rp=(1.27, 1.27), desc="Clamps the HIGH level to 5.1 V (radio TX INH is a 5 V logic input, A-18); 21 mW of 300 mW. Nexperia BZX384; second source onsemi MM3Z5V1T1G")
    assert DZ["1"] == (165.1, 200.66) and DZ["2"] == (165.1, 208.28), DZ
    S.power("RGND", DZ["2"])
    S.wire(JL["1"], (134.62, 208.28), (134.62, 200.66), (165.1, 200.66), RH["1"])
    to_din("DIN6", 200.66, RH["2"])
    S.wire(JL["3"], (132.08, 213.36), (132.08, 215.9)); S.power("RGND", (132.08, 215.9))
    for i, what in enumerate(("U1", "U2")):
        C = S.part("Device:C", ("C", 1 + i), "1u 16V X7R", C0603, R2(203.2 + i * 10.16), 128.27, desc=f"{what} decoupling, at the part (one value, D-127)")
        S.power("+3V3", C["1"]); S.power("GND", C["2"])
    S.text("Radio port (D-71, D-72, D-77, D-78, D-85 to D-91). One sheet, three instances: R1 (FT-710), R2, R3. Mini-DIN 8 on the root sheet.\\n"
           "Sides as on the root block: logic inputs on the top edge, TX_EN on the bottom edge, mini-DIN pins and the panel LED on the right edge.\\n"
           "TX INH: LED current only with PERMIT AND TX_EN; no current (unpowered, stop, no permit) = contact closed = inhibit.\\n"
           "INH LEVEL: 1-2 HIGH (5.1 V from the radio +13V OUT via RH and DZ), 2-3 LOW (radio GND), removed = not used. FT-710: HIGH expected (A-15, A-18).\\n"
           "Keying: KEY AND INH_ON. PIN1 SEL: KEY (R2, R3) or BAND D (R1). BAND A to D to the expander on R1 only (root).\\n"
           "TX sense: SENSE A and SENSE K both 1-2 = CONTACT (FEED SEL: radio +13V OUT or interface 13.8 V), both 2-3 = VOLTAGE.\\n"
           "GND BOND: radio GND to interface GND; close on R1 and with the interface feed. Otherwise the port floats.\\n"
           "RGND = radio GND of this port (local net). Each mini-DIN line: TVS 15 V and 1 nF to RGND at the connector; RGND to CHASSIS by 10 nF 1 kV.", 101.6, 231.14)
    return S.finish()

def root_sheet():
    S = Sheet("Shack interface: overview and connectors", "A3", [(f"/{ROOT_UUID}", 0)], pwr_base=[900])
    S.u = ROOT_UUID
    LX, LY, LW = 101.6, 50.8, 38.1
    slot = lambda i: R2(LY + (i + 1) * 2.54)
    # RJ45 to Cat6 #1 (T568B), pins on the slot grid so that each wires straight to its sheet pin (block on the right)
    J1 = S.part("Connector:8P8C", ("J", 1), "RJ45 LINK", "shack-interface:RJ45_8P8C_Unshielded_TabDown", 63.5, R2(slot(0) + 10.16),
                mpn="615008137121", desc="RJ45, Cat6 #1 UTP to the matrix box (D-56). Wurth 615008137121 (unshielded, THT, tab down), "
                "second source Molex 95501-2881; footprint as the controller board (D-138, D-171)", rp=(-5.08, -12.7))
    pinnet = {}
    for k, (a, b), *_ in LOOPS: pinnet[a], pinnet[b] = f"L{k}P", f"L{k}N"
    jp = sorted(range(1, 9), key=lambda p: J1[str(p)][1])
    assert [J1[str(p)][1] for p in jp] == [slot(i) for i in range(8)], [J1[str(p)] for p in jp]
    left = [pinnet[p] for p in jp] + ["", "CHASSIS", "", "KILL_1", "KILL_2"]
    right = ["SAFE_LOST", "DATA_TX", "SW_STOP_N", "DATA_RX", "R1_TX"]     # SAFE_LOST first: it branches up; R1_TX last: it branches down to R1
    S.raw(sheet_block("link", "Link to the box", "link.kicad_sch", 2, LX, LY, LW, R2(14 * 2.54), left, right))
    for i, p in enumerate(jp): S.wire(J1[str(p)], (LX, slot(i)))
    HX = 88.9
    H1 = S.part("Mechanical:MountingHole_Pad", ("H", 1), "M3 CHASSIS", "MountingHole:MountingHole_3.2mm_M3_Pad", HX, slot(8),
                desc="Plated M3 lug: short wire to the shack earth. GDT surge path", bom=False, rp=(-3.81, -1.27, "right"))
    assert H1["1"] == (HX, slot(9)), H1
    S.wire(H1["1"], (93.98, slot(9)), (99.06, slot(9)), (LX, slot(9))); S.power("CHASSIS", (93.98, slot(9)), rp=(-7.62, 1.27, "right"))
    S.power("CHASSIS", (99.06, slot(9)), flag=True, rp=(0, -6.35, "center"))      # CHASSIS has no source: the lug to the shack earth
    JK = S.part("Connector_Generic:Conn_01x02", ("J", 2), "KILL switch", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
                83.82, slot(11), mirror="y", rp=(-2.54, 0, "left"), desc="Front-panel KILL switch (latching, normally closed = run), in series with the SAFE loop (D-62). Part to select")
    assert JK["1"] == (88.9, slot(11)) and JK["2"] == (88.9, slot(12)), JK
    S.wire(JK["1"], (LX, slot(11))); S.wire(JK["2"], (LX, slot(12)))
    # MCU block: the link signals wire straight across (same slots); port signals leave on the bottom edge
    MX, MW = 165.1, 45.72
    mr = ["USB_DP", "USB_DN", "USB_VBUS", "USB_CC1", "USB_CC2"] + [""] * 6 + ["FAULT", "LATCHED", "KILL_S"]
    G1 = ["PERMIT_R1", "KEY_R1", "BAND_D", "BAND_A", "BAND_B", "BAND_C"]                     # to R1, fans out to the left (port top-edge order)
    G2 = ["PERMIT_R2", "KEY_R2", "R2_TX", "PERMIT_R3", "KEY_R3", "R3_TX"]                    # to R2 and R3, fans out to the right
    MH = R2(15 * 2.54)
    S.raw(sheet_block("mcu", "MCU and expander", "mcu.kicad_sch", 4, MX, LY, MW, MH, right, mr, file_top=True, bottom=G1 + G2))
    for i in range(len(right)):
        if right[i] == "SAFE_LOST": S.wire((R2(LX + LW), slot(i)), (152.4, slot(i)), (MX, slot(i)))
        elif right[i] == "R1_TX": S.wire((R2(LX + LW), slot(i)), (147.32, slot(i)), (MX, slot(i)))
        else: S.wire((R2(LX + LW), slot(i)), (MX, slot(i)))
    # SAFE block right of the MCU: FAULT, LATCHED, KILL_S wire straight across; SAFE_LOST comes in on the top edge
    SX, SW = 241.3, 45.72
    sl = [""] * 11 + ["FAULT", "LATCHED", "KILL_S"]
    sr = ["TX_EN", "", "BTN", "LED_SAFE", "LED_LATCHED"]
    S.raw(sheet_block("safe", "SAFE latch", "safe.kicad_sch", 5, SX, LY, SW, R2(15 * 2.54), sl, sr, file_top=True, top=["SAFE_LOST"]))
    # USB-C J14 at the board edge (housing wall), between the MCU and SAFE blocks (D-96)
    JU = S.part("shack-interface:USB_C_USB2.0_16P", ("J", 14), "USB4105-GF-A", "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
                223.52, 60.96, mpn="USB4105-GF-A", rp=(-7.62, -13.97),
                desc="USB 2.0 Type-C receptacle at the housing wall, to the DevKit D+/D- (pads 19, 20). VBUS only to the ESD array; shell to CHASSIS (D-96). GCT spec Rev A3: 48 V, 5 A VBUS, -40 to 85 C. Second source Same Sky UJ20-C-H-G-SMT-1-P16-TR (same land pattern)")
    assert JU["A6"] == (213.36, slot(0)) and JU["B5"] == (213.36, slot(4)) and JU["A1"] == (220.98, 71.12) and JU["SH"] == (226.06, 71.12), JU
    for i, pn in enumerate(("A6", "A7", "A4", "A5", "B5")): S.wire((R2(MX + MW), slot(i)), JU[pn])
    S.power("GND", JU["A1"]); S.power("CHASSIS", JU["SH"])
    for i, nm in enumerate(mr):
        if not nm or nm.startswith("USB"): continue
        a = (R2(MX + MW), slot(i))
        if nm == "KILL_S": S.wire(a, (238.76, slot(i)), (SX, slot(i)))
        else: S.wire(a, (SX, slot(i)))
    YT = 43.18
    S.wire((152.4, slot(0)), (152.4, YT), (R2(SX + 2.54), YT), (R2(SX + 2.54), LY))
    # KILL state connector (second pole of the KILL switch)
    JK2 = S.part("Connector_Generic:Conn_01x02", ("J", 7), "KILL state", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
                 231.14, 114.3, mirror="y", rp=(-2.54, 0, "left"), desc="Second pole of the front-panel KILL switch, closed = run (KILL_S low)")
    assert JK2["1"] == (236.22, 114.3), JK2
    S.wire(JK2["1"], (238.76, 114.3), (238.76, slot(13))); S.wire(JK2["2"], (241.3, 116.84)); S.power("GND", (241.3, 116.84))
    # front panel: RESET button, SAFE and LATCHED LEDs
    JF = S.part("Connector_Generic:Conn_01x04", ("J", 6), "Front panel", "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical",
                304.8, R2(slot(2) + 2.54), rp=(2.54, -5.08), desc="Front panel: 1 RESET button (to pin 4), 2 SAFE LED anode, 3 LATCHED LED anode, 4 GND")
    assert JF["1"] == (299.72, slot(2)), JF
    for i in (2, 3, 4): S.wire((R2(SX + SW), slot(i)), JF[str(i - 1)])
    S.wire(JF["4"], (294.64, JF["4"][1])); S.power("GND", (294.64, JF["4"][1]))
    # radio ports R1 to R3 (one sheet, three instances), mini-DIN 8 and panel LED connector beside each
    PY, PW, PH = 152.4, 50.8, R2(11 * 2.54)
    PXS = [101.6, 203.2, 304.8]
    DIN = [f"DIN{n}" if n != 5 else "RGND" for n in range(1, 9)]       # pin 5 = radio GND (local net RGND in the port sheet)
    BANDS = ["BAND_A", "BAND_B", "BAND_C", "BAND_D"]
    tops = [["", "", "", "PERMIT", "KEY", "BAND_D", "TX", "BAND_A", "BAND_B", "BAND_C"]] * 3        # same order as the port sheet top edge
    bottom = [""] * 9 + ["TX_EN"]
    for k, (px, tp) in enumerate(zip(PXS, tops)):
        S.raw(sheet_block(f"r{k + 1}", f"Radio port R{k + 1}", "radioport.kicad_sch", 6 + k, px, PY, PW, PH, [], DIN, top=tp, bottom=bottom))
        tx = lambda n: R2(px + (tp.index(n) + 1) * 2.54)
        if k > 0:
            for n in BANDS: S.raw(f'\t(no_connect\n\t\t(at {tx(n)} {PY})\n\t\t(uuid "{U()}")\n\t)\n')    # band data from R1 only (D-86)
        JD = S.part("shack-interface:MD-80SM", ("J", 11 + k), f"R{k + 1} mini-DIN", "shack-interface:MiniDIN-8_SameSky_MD-80SM_Horizontal", R2(px + PW + 15.24), R2(PY + 12.7), mpn="MD-80SM",
                    rp=(0, -15.24, "center"), desc="Mini-DIN 8 socket, PCB, right angle, side shielded (Same Sky MD-80SM rev 1.09). Footprint: layout after 2022-03-03 (D-85, D-100). Second source Kycon KMDGX-8S-BS (same tail positions, M-28)")
        for n in range(8):
            assert JD[str(n + 1)] == (R2(px + PW + 7.62), R2(PY + (n + 1) * 2.54)), JD
            S.wire((R2(px + PW), R2(PY + (n + 1) * 2.54)), JD[str(n + 1)])
        S.power("CHASSIS", JD["9"])
    # fan-out from the MCU bottom edge to the port top edges: one level per signal, no crossings
    # (left-going: leftmost source turns highest; right-going: rightmost source turns highest)
    YB = R2(LY + MH)
    lev = lambda i: R2(127.0 + i * 2.54)
    mx = lambda i: R2(MX + (i + 1) * 2.54)
    dst1 = lambda n: R2(PXS[0] + (tops[0].index(n) + 1) * 2.54)
    S.wire((147.32, slot(4)), (147.32, lev(0)), (dst1("TX"), lev(0)), (dst1("TX"), PY))
    for i, n in enumerate(G1):
        pin = "PERMIT" if n.startswith("PERMIT") else "KEY" if n.startswith("KEY") else n
        S.wire((mx(i), YB), (mx(i), lev(i + 1)), (dst1(pin), lev(i + 1)), (dst1(pin), PY))
    for j, n in enumerate(G2):
        i = len(G1) + j
        port = 1 if n.endswith("R2") or n.startswith("R2") else 2
        pin = n.split("_")[0] if not n.endswith("_TX") else "TX"
        d = R2(PXS[port] + (tops[port].index(pin) + 1) * 2.54)
        S.wire((mx(i), YB), (mx(i), lev(len(G2) - 1 - j)), (d, lev(len(G2) - 1 - j)), (d, PY))
    # TX_EN from the SAFE block to every port (bottom edge)
    XE, YE = 393.7, 195.58
    te = [R2(px + 10 * 2.54) for px in PXS]
    S.wire((R2(SX + SW), slot(0)), (292.1, slot(0)), (292.1, 45.72), (XE, 45.72), (XE, YE), (te[2], YE), (te[1], YE), (te[0], YE))
    for x in te: S.wire((x, YE), (x, R2(PY + PH)))
    # power: 13.8 V input connector to the power sheet
    PY = 215.9
    S.raw(sheet_block("power", "Power", "power.kicad_sch", 3, LX, PY, LW, R2(2 * 2.54), ["VIN_P"], []))
    # XT60PW-M as the RF board (D-171): KiCad footprint pin 1 = GND, pin 2 = + (polarity on the real part: M-02)
    JP = S.part("Connector_Generic:Conn_01x02", ("J", 3), "13.8 V IN", "Connector_AMASS:AMASS_XT60PW-M_1x02_P7.20mm_Horizontal",
                83.82, R2(PY + 5.08), rot=180, rp=(-2.54, 0, "left"), mpn="XT60PW-M",
                desc="13.8 V input from the shack supply, fused there. Amass XT60PW-M, as the RF board power inputs (D-17, D-171). Pin 1 GND, pin 2 +")
    assert JP["2"] == (88.9, R2(PY + 2.54)) and JP["1"] == (88.9, R2(PY + 5.08)), JP
    S.wire(JP["2"], (LX, R2(PY + 2.54))); S.wire(JP["1"], (93.98, R2(PY + 5.08))); S.power("GND", (93.98, R2(PY + 5.08)))
    S.text("Shack interface board, rev A (2026-10-02). Sheets: link, power, MCU and expander, SAFE latch, radio ports R1 to R3.\\n"
           "R1 = FT-710: band data to the expander, TX sense also keys the PTT loop (R1_TX). R2, R3: band pins not used (D-86).\\n"
           "CHASSIS: shack earth lug, GDT centre electrodes, mini-DIN shields, USB-C shell (J14).", 177.8, 233.68)
    return S.finish()

files = {"link.kicad_sch": link_sheet(), "power.kicad_sch": power_sheet(), "mcu.kicad_sch": mcu_sheet(), "safe.kicad_sch": safe_sheet(),
         "radioport.kicad_sch": port_sheet(), f"{PROJECT}.kicad_sch": root_sheet()}
_map = {}
def _stable(fn, t):
    """Replace each random uuid from U() by uuid5(file, order of appearance): the same input gives the same files."""
    k = [0]
    def rep(m):
        u = m.group(0)
        if u not in GEN: return u
        if u not in _map: k[0] += 1; _map[u] = str(uuid.uuid5(NS, f"{fn}#{k[0]}"))
        return _map[u]
    return re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', rep, t)
files = {fn: _stable(fn, t) for fn, t in files.items()}
for fn, t in files.items(): open(fn, "w").write(t)
_refs = [(r, u) for t in files.values() for r, u in re.findall(r'\(reference "([^"]+)"\)\s*\(unit (\d+)\)', t)]
assert len(_refs) == len(set(_refs)), sorted(r for r in set(_refs) if _refs.count(r) > 1)
libs = [v.replace(f'(symbol "{PROJECT}:', '(symbol "', 1) for k, v in sorted(SYMS.items()) if k.startswith(f"{PROJECT}:")]
open(f"{PROJECT}.kicad_sym", "w").write('(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kicad_symbol_editor")\n'
                                        '\t(generator_version "10.0")\n\t' + "\n\t".join(l.replace("\n", "\n\t") for l in libs) + "\n)\n")
open("fp-lib-table", "w").write('(fp_lib_table\n\t(version 7)\n\t(lib (name "shack-interface")(type "KiCad")'
                                '(uri "${KIPRJMOD}/lib/shack-interface.pretty")(options "")(descr "Shack interface board rev A, project footprints"))\n)\n')
open("sym-lib-table", "w").write('(sym_lib_table\n\t(version 7)\n\t(lib (name "shack-interface")(type "KiCad")'
                                 '(uri "${KIPRJMOD}/shack-interface.kicad_sym")(options "")(descr "Shack interface board rev A"))\n)\n')
pro = json.load(open(f"{PROJECT}.kicad_pro")) if os.path.exists(f"{PROJECT}.kicad_pro") else \
      {"meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3}}
pro.setdefault("schematic", {})["top_level_sheets"] = [{"filename": f"{PROJECT}.kicad_sch", "name": PROJECT, "uuid": ROOT_UUID}]
open(f"{PROJECT}.kicad_pro", "w").write(json.dumps(pro, indent=2) + "\n")
print(GENERATOR_REV, "root", ROOT_UUID, "files", list(files))
