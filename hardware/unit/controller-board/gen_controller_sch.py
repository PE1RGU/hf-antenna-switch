#!/usr/bin/env python3
"""Generate the rev C controller board schematic (root + hierarchical sheets), drawn with wires.

Architecture: docs/architecture.md, docs/design/controller-board.md. Decisions: design-log.md (D-51, D-55 to D-58).
Run from this folder. Overwrites controller-board.kicad_sch, link.kicad_sch, mcu.kicad_sch,
controller-board.kicad_sym, sym-lib-table. Framework (Sheet, wires, junctions) copied from gen_rfboard_sch.py.
Library symbols come from _sym/ (copied from the KiCad 10 libraries).

Drawing rules (hardware skill, section 11): signal flow left to right, supplies up, ground down,
wires inside a sheet, labels only where a net leaves the sheet, junction dots at every T,
no wire end on the middle of another wire (checked by an assert).
"""
import json, math, os, re, uuid

PROJECT = "controller-board"
DATE = "2026-10-22"
GENERATOR_REV = "c17-max823"
GEN = set()   # uuids made by U(): replaced by stable uuid5 values when the files are written (Git-friendly)
def U():
    u = str(uuid.uuid4()); GEN.add(u); return u
U_ = U
# Fixed root and sheet uuids. KiCad 10 keeps the top-level sheet uuid in the .kicad_pro
# (schematic.top_level_sheets) and starts every instance path with it. A new uuid per run
# breaks the paths: KiCad then "fixes" the file and gives all sheet instances the same references.
NS = uuid.uuid5(uuid.NAMESPACE_DNS, "pe1rgu.shack-relay-matrix.rev-c.controller")
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

    def part(self, lib, ref, value, fp, x, y, conn=None, desc="", dnp=False, mpn="", rot=0, mirror=None,
             rp=None, bom=True, refs=None, unit=1):
        """ref: (prefix, number). conn: pin -> 'NC' | (kind, name) label at the pin. Returns pin -> (x, y)."""
        self.used.add(lib)
        conn = conn or {}
        lp = {**PINS_U[lib].get(0, {}), **PINS_U[lib][unit]} if lib in PINS_U else PINS[lib]
        assert set(conn) <= set(lp), (lib, conn)
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
        for p, (ex, ey, a) in pts.items():
            self.pinpts.append((ex, ey))
            c = conn.get(p)
            if c == "NC": self.items.append(f'\t(no_connect\n\t\t(at {ex} {ey})\n\t\t(uuid "{U()}")\n\t)\n')
            elif c: self.label(c[0], c[1], ex, ey, (a + 180) % 360)
        return {p: (q[0], q[1]) for p, q in pts.items()}

    def power(self, net, pt, flag=False, rp=None):
        """Power symbol at pt: GND points down, supplies point up. flag=True places a PWR_FLAG.
        Net name = Value field; the +12V graphic is used for every other positive net (+12V_SW, CLAMP_SW, ...)."""
        x, y = pt
        self.npwr += 1
        if flag: lib, pre, val = "power:PWR_FLAG", "#FLG", "PWR_FLAG"
        else: lib, pre, val = {"GND": "power:GND", "+5V": "power:+5V", "+3V3": "power:+3V3"}.get(net, "power:+12V"), "#PWR", net
        refs = [(path, f"{pre}{b + self.npwr}") for (path, _), b in zip(self.insts, self.pwr_bases)]
        dy = 5.08 if net == "GND" and not flag else -5.08
        if rp is None and net == "GND" and not flag: rp = (0, 1.905, "center")   # net name centred under the symbol
        self.part(lib, (pre, 0), val, "", x, y, desc="", bom=False, rp=rp or (-3.81, dy - 1.27), refs=refs)

    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            a, b = (R2(a[0]), R2(a[1])), (R2(b[0]), R2(b[1]))
            assert a != b and (a[0] == b[0] or a[1] == b[1]), (a, b)
            self.segs.append((a, b))
            self.items.append(f'\t(wire\n\t\t(pts\n\t\t\t(xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})\n\t\t)\n'
                              f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{U()}")\n\t)\n')

    def label(self, kind, name, x, y, a=0): self.items.append(label_sx(kind, name, x, y, a))
    def text(self, t, x, y): self.items.append(text_sx(t, x, y))
    def section(self, x0, y0, x1, y1, title):
        """Dashed frame around one function, title inside the top left corner (hardware skill, section 11)."""
        self.items.append(f'\t(rectangle\n\t\t(start {R2(x0)} {R2(y0)})\n\t\t(end {R2(x1)} {R2(y1)})\n'
                          f'\t\t(stroke\n\t\t\t(width 0.254)\n\t\t\t(type dash)\n\t\t)\n\t\t(fill\n\t\t\t(type none)\n\t\t)\n'
                          f'\t\t(uuid "{U()}")\n\t)\n')
        self.items.append(f'\t(text "{title}"\n\t\t(exclude_from_sim no)\n\t\t(at {R2(x0 + 1.27)} {R2(y0 + 1.27)} 0)\n\t\t(effects\n'
                          f'\t\t\t(font\n\t\t\t\t(size 1.524 1.524)\n\t\t\t\t(bold yes)\n\t\t\t)\n\t\t\t(justify left top)\n\t\t)\n'
                          f'\t\t(uuid "{U()}")\n\t)\n')
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
             f'\t\t(rev "C")\n\t\t(company "PE1RGU - Shack Relay Matrix")\n')
        t += "".join(f'\t\t(comment {i + 1} "{c}")\n' for i, c in enumerate([C1, C2, C3, C4])) + "\t)\n"
        t += "\t(lib_symbols\n\t\t" + "\n\t\t".join(SYMS[k].replace("\n", "\n\t") for k in sorted(self.used)) + "\n\t)\n"
        t += junc + "".join(self.items)
        t += '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n'
        if self.u == ROOT_UUID: t += '\t(embedded_fonts no)\n'   # KiCad writes this on the root file only
        t += ')\n'
        assert t.count("(") == t.count(")"), self.title
        return t

def sheet_block(key, name, fn, page, x, y, w, h, left, right, file_top=False):
    assert "/" not in name, ("KiCad sheet names cannot contain '/'", name)
    sp = ""
    for side, names in (("L", left), ("R", right)):
        for i, p in enumerate(names):
            if not p: continue
            px, py, a, j = (x, R2(y + (i + 1) * 2.54), 180, "left") if side == "L" else (R2(x + w), R2(y + (i + 1) * 2.54), 0, "right")
            sp += (f'\t\t(pin "{p}" passive\n\t\t\t(at {px} {py} {a})\n\t\t\t(uuid "{U()}")\n'
                   f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify {j})\n\t\t\t)\n\t\t)\n')
    return (f'\t(sheet\n\t\t(at {x} {y})\n\t\t(size {w} {h})\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n'
            f'\t\t(dnp no)\n\t\t(fields_autoplaced yes)\n\t\t(stroke\n\t\t\t(width 0.1524)\n\t\t\t(type solid)\n\t\t)\n'
            f'\t\t(fill\n\t\t\t(color 0 0 0 0.0000)\n\t\t)\n\t\t(uuid "{SUUID[key]}")\n'
            f'\t\t(property "Sheetname" "{name}"\n\t\t\t(at {x} {R2(y - 0.71)} 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify left bottom)\n\t\t\t)\n\t\t)\n'
            f'\t\t(property "Sheetfile" "{fn}"\n\t\t\t(at {R2(x + w) if file_top else x} {R2(y - 0.71) if file_top else R2(y + h + 0.59)} 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify {"right bottom" if file_top else "left top"})\n\t\t\t)\n\t\t)\n'
            + sp + f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "/{ROOT_UUID}"\n\t\t\t\t\t(page "{page}")\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')


# ---------- controller board: symbols, sheets ----------
C2 = "ESP32-C3 Rust board in sockets (D-55, D-95), RJ45 LINK 4 opto loops (D-56, D-57)"
C3 = "J2 2x12 to RF board J14 (D-51, D-52). PTT to K0 in hardware (no MCU)"
C4 = "4 layers JLC04161H-7628 (D-144), CHASSIS plane at the Cat6 entry (D-145)"
SYMS = {
    "Device:R": load("Device", "R"), "Device:C": load("Device", "C"), "Device:D": load("Device", "D"),
    "Device:L_Coupled": load("Device", "L_Coupled"), "Connector:TestPoint": load("Connector", "TestPoint"),
    "Device:D_TVS": load("Device", "D_TVS"), "Device:GDT_3Pin": load("Device", "GDT_3Pin"),
    "Isolator:HCPL-261A": load("Isolator", "HCPL-261A"), "Isolator:PC817": load("Isolator", "PC817"),
    "Connector:8P8C": load("Connector", "8P8C"),
    "Connector_Generic:Conn_02x12_Odd_Even": load("Connector_Generic", "Conn_02x12_Odd_Even"),
    "Transistor_FET:Q_NMOS_GSD": load("Transistor_FET", "Q_NMOS_GSD"),
    "Mechanical:MountingHole_Pad": load("Mechanical", "MountingHole_Pad"),
    "power:GND": load("power", "GND"), "power:+12V": load("power", "+12V"), "power:+5V": load("power", "+5V"),
    "power:+3V3": load("power", "+3V3"), "power:PWR_FLAG": load("power", "PWR_FLAG"),
    "controller-board:LP2985-3.3": open("_sym/Regulator_Linear__LP2985-3.3.sym").read().strip()
        .replace('(symbol "LP2985-3.3"', '(symbol "controller-board:LP2985-3.3"', 1),
}

def mk_sym(name, desc, rect, pins, texts=(), lines=(), hide_names=False, ref=(0, 0), val=(0, 0), name_off=0.254):
    """Project library symbol, IEC 60617 style (hardware skill, section 11): rectangle with the qualifying symbol.
    pins: (number, name, etype, shape, x, y, angle, length). Symbol coordinates, y up."""
    f = '(effects (font (size 1.27 1.27)))'
    pr = lambda k, v, at, hide: (f'\t(property "{k}" "{v}" (at {at[0]} {at[1]} 0) (show_name no) (do_not_autoplace no)'
                                 f'{" (hide yes)" if hide else ""} {f})\n')
    t = (f'(symbol "controller-board:{name}"\n\t(pin_names (offset {name_off}){" (hide yes)" if hide_names else ""})\n'
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
    for num, nm, et, sh, x, y, a, ln in sorted(pins, key=lambda q: int(q[0])):     # KiCad order: by pin number
        hide = " (hide yes)" if et == "no_connect" else ""
        t += f'\t\t(pin {et} {sh} (at {x} {y} {a}) (length {ln}){hide} (name "{nm}" {f}) (number "{num}" {f}))\n'
    return t + '\t)\n\t(embedded_fonts no)\n)'
# Schmitt inverter: same pin positions as the KiCad 74LVC1G14 symbol, so the link sheet wiring stays
SYMS["controller-board:74LVC1G14_IEC"] = mk_sym("74LVC1G14_IEC", "Single Schmitt inverter, IEC 60617 symbol",
    (-7.62, 5.08, 5.08, -5.08),
    [("1", "NC", "no_connect", "line", -7.62, 5.08, 180, 5.08), ("2", "", "input", "line", -15.24, 0, 0, 7.62),
     ("3", "", "power_in", "line", -5.08, -10.16, 90, 5.08), ("4", "", "output", "output_low", 12.7, 0, 180, 7.62),
     ("5", "", "power_in", "line", -5.08, 10.16, 270, 5.08)],
    texts=[("1", -1.27, 3.175)], lines=[[(-2.54, -2.54), (0.635, -2.54), (0.635, 0)], [(-0.635, -2.54), (-0.635, 0), (2.54, 0)]],
    hide_names=True, ref=(2.54, 7.62), val=(2.54, -7.62))
# 3-input NOR: qualifier >=1, IEC negation indicator on the output (D-59)
SYMS["controller-board:74LVC1G27_IEC"] = mk_sym("74LVC1G27_IEC", "Single 3-input NOR, IEC 60617 symbol (TI SN74LVC1G27DBV, Nexperia 74LVC1G27GV)",
    (-5.08, 5.08, 5.08, -5.08),
    [("6", "", "input", "line", -10.16, 2.54, 0, 5.08), ("1", "", "input", "line", -10.16, 0, 0, 5.08),
     ("3", "", "input", "line", -10.16, -2.54, 0, 5.08), ("4", "", "output", "output_low", 10.16, 0, 180, 5.08),
     ("5", "", "power_in", "line", 0, 10.16, 270, 5.08), ("2", "", "power_in", "line", 0, -10.16, 90, 5.08)],
    texts=[("\u22651", 1.27, 2.54)], ref=(2.54, 7.62), val=(2.54, -7.62))
# D flip-flop with set and reset: IEC qualifiers S, 1D, C1, R; low-active inputs with the IEC indicator (D-59)
SYMS["controller-board:74LVC1G74_IEC"] = mk_sym("74LVC1G74_IEC", "Single D flip-flop with preset and clear, IEC 60617 symbol (TI SN74LVC1G74 DCU, Nexperia 74LVC2G74DC)",
    (-5.08, 7.62, 5.08, -7.62),
    [("6", "R", "input", "input_low", -10.16, 5.08, 0, 5.08), ("7", "S", "input", "input_low", -10.16, 2.54, 0, 5.08),
     ("1", "C1", "input", "clock", -10.16, -2.54, 0, 5.08), ("2", "1D", "input", "line", -10.16, -5.08, 0, 5.08),
     ("5", "", "output", "line", 10.16, 2.54, 180, 5.08), ("3", "", "output", "output_low", 10.16, -2.54, 180, 5.08),
     ("8", "", "power_in", "line", 0, 10.16, 270, 2.54), ("4", "", "power_in", "line", 0, -10.16, 90, 2.54)],
    ref=(2.54, 10.16), val=(2.54, -10.16), name_off=1.016)
SYMS["Power_Supervisor:TPS3823-xxDBV"] = load("Power_Supervisor", "TPS3823-xxDBV")
# 2-input NOR (READY gate, D-62): same symbol as the shack interface (SOT-23-5: 1 A, 2 B, 3 GND, 4 Y, 5 VCC)
SYMS["controller-board:74LVC1G02_IEC"] = mk_sym("74LVC1G02_IEC", "Single 2-input NOR, IEC 60617 symbol (TI SN74LVC1G02, Nexperia 74LVC1G02)",
    (-5.08, 5.08, 5.08, -5.08),
    [("1", "", "input", "line", -10.16, 2.54, 0, 5.08), ("2", "", "input", "line", -10.16, -2.54, 0, 5.08),
     ("4", "", "output", "output_low", 10.16, 0, 180, 5.08),
     ("5", "", "power_in", "line", 0, 10.16, 270, 5.08), ("3", "", "power_in", "line", 0, -10.16, 90, 5.08)],
    texts=[("\u22651", 1.27, 2.54)], ref=(2.54, 7.62), val=(2.54, -7.62))
# 2-input AND (READY drive with the A2 RF stop, D-104): same symbol as the shack interface
SYMS["controller-board:74LVC1G08_IEC"] = mk_sym("74LVC1G08_IEC", "Single 2-input AND, IEC 60617 symbol (TI SN74LVC1G08, Nexperia 74LVC1G08)",
    (-5.08, 5.08, 5.08, -5.08),
    [("1", "", "input", "line", -10.16, 2.54, 0, 5.08), ("2", "", "input", "line", -10.16, -2.54, 0, 5.08),
     ("4", "", "output", "line", 10.16, 0, 180, 5.08),
     ("5", "", "power_in", "line", 0, 10.16, 270, 5.08), ("3", "", "power_in", "line", 0, -10.16, 90, 5.08)],
    texts=[("&", 1.27, 2.54)], ref=(2.54, 7.62), val=(2.54, -7.62))
# form A photorelay (READY switch, D-62, D-101): same symbol as the shack interface keying part
_led = [[(-3.81, 1.27), (-2.54, -0.635), (-1.27, 1.27), (-3.81, 1.27)], [(-3.81, -0.635), (-1.27, -0.635)],
        [(-5.08, 2.54), (-2.54, 2.54), (-2.54, 1.27)], [(-5.08, -2.54), (-2.54, -2.54), (-2.54, -0.635)]]
_ctc = [[(1.27, 2.54), (5.08, 2.54)], [(1.27, -2.54), (5.08, -2.54)], [(1.27, -2.54), (1.27, -1.27)], [(1.27, 2.54), (1.27, 0.635)], [(1.27, 0.635), (0, -1.27)]]
SYMS["controller-board:TLP176AM"] = mk_sym("TLP176AM", "1-form-A photorelay 60 V 0.7 A, 2.54 mm pitch (Toshiba TLP176AM Rev 7.0.A). Symbol pins = SOP4 positions 1 A, 2 K, 3 and 4 load = TLP176AM pins 1, 3, 4, 6. Second source Panasonic AQY212G3HS",
    (-5.08, 5.08, 5.08, -5.08),
    [("1", "", "passive", "line", -10.16, 2.54, 0, 5.08), ("2", "", "passive", "line", -10.16, -2.54, 0, 5.08),
     ("4", "", "passive", "line", 10.16, 2.54, 180, 5.08), ("3", "", "passive", "line", 10.16, -2.54, 180, 5.08)],
    lines=_led + _ctc, texts=[("1A", 3.175, 3.81)], hide_names=True, ref=(0, 7.62), val=(0, -7.62))
# ESP32-C3 Rust board as one board symbol, the same as on the shack interface board (D-93): pad numbers = esp-rs Rust_Board
# footprint; left header 1..16 top to bottom, right header 28..17 top to bottom, pad 28 level with pad 5. Battery pads 29, 30 not used.
DK_L = ["RST", "3V3", "NC", "GND", "IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7", "IO8/SCL", "IO21/TXD", "IO20/RXD", "IO9/BOOT"]
DK_R = {28: "VBAT", 27: "EN", 26: "VBUS", 25: "NC", 24: "NC", 23: "NC", 22: "NC", 21: "NC", 20: "IO18/D-", 19: "IO19/D+",
        18: "IO8/SCL", 17: "IO10/SDA"}
SYMS["controller-board:ESP32-C3-DevKit-RUST"] = mk_sym("ESP32-C3-DevKit-RUST",
    "ESP32-C3 Rust board (DevKit-RUST-1 Rev 1.2a or DevKit-RUST-2 Rev 2.0) in two socket headers. Pads as the esp-rs Rust_Board footprint, 1..28",
    (-15.24, 20.32, 15.24, -25.4),
    [(str(n + 1), DK_L[n], "passive", "line", -17.78, R2(17.78 - 2.54 * n), 0, 2.54) for n in range(16)] +
    [(str(p), nm, "passive", "line", 17.78, R2(17.78 - 2.54 * (32 - p)), 180, 2.54) for p, nm in DK_R.items()],
    texts=[("ESP32-C3-MINI-1", 5.08, 15.24), ("USB-C", 0, -23.495)], ref=(-15.24, 24.13), val=(-15.24, 21.59))
SYMS["controller-board:SolderJumper_3_Open"] = mk_sym("SolderJumper_3_Open", "Solder jumper, 3 pads, open; bridge 2-1 or 2-3",
    (-2.54, 1.27, 2.54, -1.27),
    [("1", "", "passive", "line", -5.08, 0, 0, 2.54), ("3", "", "passive", "line", 5.08, 0, 180, 2.54),
     ("2", "", "passive", "line", 0, -5.08, 90, 3.81)],
    lines=[[(-0.635, 1.27), (-0.635, -1.27)], [(0.635, 1.27), (0.635, -1.27)]], hide_names=True, ref=(0, 2.54), val=(0, -2.54))
# the same, with pads 1 and 2 joined by copper on the board (D-192): the bar across the left gap
SYMS["controller-board:SolderJumper_3_Bridged12"] = mk_sym("SolderJumper_3_Bridged12", "Solder jumper, 3 pads, 1-2 bridged by copper; cut 1-2 and bridge 2-3 for the other setting",
    (-2.54, 1.27, 2.54, -1.27),
    [("1", "", "passive", "line", -5.08, 0, 0, 2.54), ("3", "", "passive", "line", 5.08, 0, 180, 2.54),
     ("2", "", "passive", "line", 0, -5.08, 90, 3.81)],
    lines=[[(-0.635, 1.27), (-0.635, -1.27)], [(0.635, 1.27), (0.635, -1.27)], [(-1.27, 0), (0, 0)]], hide_names=True, ref=(0, 2.54), val=(0, -2.54))
PINS = {k: pins_of(v) for k, v in SYMS.items()}
PINS_U = {}

SHEETS = [("link", "Link and PTT", "link.kicad_sch"), ("mcu", "MCU and safety gate", "mcu.kicad_sch")]
SUUID = {s[0]: str(uuid.uuid5(NS, "sheet/" + s[0])) for s in SHEETS}
PATH = {s[0]: f"/{ROOT_UUID}/{SUUID[s[0]]}" for s in SHEETS}
SOT23, SOD123 = "Package_TO_SOT_SMD:SOT-23", "Diode_SMD:D_SOD-123"
R0603 = "Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder"
C0603 = "Capacitor_SMD:C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"
C0805 = "Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"
MELF0204 = "Resistor_SMD:R_MiniMELF_MMA-0204"
MELF0207 = "Resistor_SMD:R_MELF_MMB-0207"
QN_D = "N-MOSFET 60 V, RDS(on) specified at VGS 2.5 V (BSS138BK, Nexperia). Second source Diotec MMFTN138K (same limits and pin-out, D-134)"
TP_FP = "TestPoint:TestPoint_Pad_D1.5mm"
CMC_FP = "controller-board:L_CMC_TDK_ACT45B"
CMC_D = ("Common-mode choke per Cat6 pair at the entry, after the GDT (D-130): 51 uH CAN type, 1812. TDK ACT45B-510-2P-TL003; "
         "TDK land pattern, winding starts at the top (D-149). Second sources Murata DLW43SH510XK2L, Coilcraft 1812CAN-513: "
         "same geometry, mount by position (D-151)")
# Cat6 #1 pairs (T568B pin numbers), loop + wire first (D-56): pair 1 data in, 2 PTT, 3 SAFE (D-62), 4 data out
LOOPS = [(1, "L1", (4, 5), "data shack to box"), (2, "L2", (1, 2), "PTT (FT-710 TX GND at the shack)"),
         (3, "L3", (3, 6), "SAFE (closed loop = run, D-62)"), (4, "L4", (7, 8), "data box to shack")]

def loop_entry(S, k, yp):
    """Pair entry: GDT to CHASSIS, 47R pulse resistor per wire, TVS across the pair. Returns the P and N wire ends."""
    yn = R2(yp + 10.16)
    n = 10 * k
    S.label("H", f"L{k}P", 25.4, yp, 180); S.label("H", f"L{k}N", 25.4, yn, 180)
    G = S.part("Device:GDT_3Pin", ("GD", k), "2036-09-B2LF", "controller-board:GDT_3Pin_P4.40mm_Bourns-2036-B2_Littelfuse-SL1003A-R", 35.56, R2(yp + 5.08), mpn="2036-09-B2LF",
               desc="3-electrode GDT 90 V, THT (Bourns 2036 Rev B 01/26): DC sparkover 72 to 108 V, impulse 550 V at 1 kV/us, "
                    "10 kA 8/20 us x10, glow 70 V (loop 12 V cannot hold an arc). Second source Littelfuse SL1003A090R-001 on the same footprint (D-149)", rp=(-12.7, 7.62))
    assert G["3"] == (35.56, yp) and G["1"] == (35.56, yn), G
    S.wire(G["2"], (25.4, R2(yp + 5.08))); S.label("H", "CHASSIS", 25.4, R2(yp + 5.08), 180)
    CM = S.part("Device:L_Coupled", ("L", k), "51u CMC", CMC_FP, 46.99, R2(yp + 5.08), mpn="ACT45B-510-2P-TL003", desc=CMC_D, rp=(7.62, -1.27))
    assert CM["1"] == (41.91, R2(yp + 2.54)) and CM["2"] == (52.07, R2(yp + 2.54)) and CM["3"] == (41.91, R2(yp + 7.62)) and CM["4"] == (52.07, R2(yp + 7.62)), CM
    RP = S.part("Device:R", ("R", n + 1), "47R", MELF0207, 58.42, yp, rot=90, rp=(1.27, -5.08),
                desc="Pulse-proof series resistor (thin-film MELF 0207, Vishay MMB 0207; second source TE Neohm SMA-A 0207, D-151): the GDT fires first. Pulse check C-39")
    RN = S.part("Device:R", ("R", n + 2), "47R", MELF0207, 58.42, yn, rot=90, rp=(1.27, 3.81), desc="As R above, N wire")
    S.wire((25.4, yp), G["3"], (40.64, yp), (40.64, R2(yp + 2.54)), CM["1"]); S.wire(CM["2"], (52.07, yp), RP["1"])
    S.wire((25.4, yn), G["1"], (40.64, yn), (40.64, R2(yp + 7.62)), CM["3"]); S.wire(CM["4"], (52.07, yn), RN["1"])
    # Y-capacitor footprints to CHASSIS on the inner side of the choke, not fitted (D-130)
    YP = S.part("Device:C", ("C", 19 + 2 * k), "DNP 1n 1kV", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", 52.07, R2(yp - 3.81), dnp=True,
                rp=(1.27, -6.35), desc="P wire to CHASSIS behind the choke, footprint only: fit on the bench if the loops pick up HF (D-130)")
    assert YP["2"] == (52.07, yp), YP
    S.label("H", "CHASSIS", 52.07, R2(yp - 7.62), 90)
    YN = S.part("Device:C", ("C", 20 + 2 * k), "DNP 1n 1kV", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", 52.07, R2(yn + 3.81), dnp=True,
                rp=(1.27, 3.81), desc="N wire to CHASSIS behind the choke, footprint only (D-130)")
    assert YN["1"] == (52.07, yn), YN
    S.label("H", "CHASSIS", 52.07, R2(yn + 7.62), 270)
    T = S.part("Device:D_TVS", ("D", n + 1), "SMBJ15CA", "Diode_SMD:D_SMB", 68.58, R2(yn - 3.81), rot=90, mpn="SMBJ15CA",
               desc="Bidirectional TVS 600 W across the pair, VR 15 V (Littelfuse SMBJ, multi-source)", rp=(1.27, -2.54))
    assert T["2"] == (68.58, R2(yp + 2.54)) and T["1"] == (68.58, yn), T
    S.wire((68.58, yp), T["2"])
    return RP["2"], RN["2"], yn

def loop_rx(S, k, yp, sig):
    """Receive loop: entry, 220R LED series resistor, anti-parallel diode, VO2611 opto, pull-up to 3.3 V. Returns VO end."""
    n = 10 * k
    p, q, yn = loop_entry(S, k, yp)
    S.wire(p, (68.58, yp), (77.47, yp))
    if k == 3:                                   # SAFE loop: READY switch U6 in the return (D-62, D-101)
        UR = S.part("controller-board:TLP176AM", ("U", 6), "TLP176AM", "controller-board:SOP-4_P2.54mm_PhotoRelay_LongPad", 81.28, R2(yn + 10.16),
                    rot=90, mpn="TLP176AM(TPL,E)", rp=(7.62, 2.54),
                    desc="READY switch in the SAFE loop: closed only while NOR(MCU_EN_N, FAULT) is high and no RF is on A2 (D-62, D-101, D-104). Form A, 60 V, 0.7 A, RON max 2 ohm, "
                         "IFT max 3 mA, 3750 Vrms (Toshiba Rev 7.0.A). Second source Panasonic AQY212G3HS")
        assert UR["4"] == (78.74, yn) and UR["3"] == (83.82, yn) and UR["1"] == (78.74, R2(yn + 20.32)) and UR["2"] == (83.82, R2(yn + 20.32)), UR
        S.wire(q, (68.58, yn), UR["4"]); S.wire(UR["3"], (93.98, yn), (101.6, yn), (101.6, R2(yp + 5.08)), (106.68, R2(yp + 5.08)))
        S.power("GND", UR["2"], rp=(1.27, 0.635, "left"))          # net name beside the symbol, clear of the R35 wire
        ya = R2(yn + 25.4)
        RR = S.part("Device:R", ("R", 35), "240R", R0603, 101.6, ya, rot=90, rp=(-2.54, -5.08),
                    desc="READY LED drive about 7 mA from the 3.3 V gate (as C-22): (3.3 - 1.4 - 0.2) / 240")
        # U16: LED drive = READY_ON AND RF_A2_N. RF on the receive-only column A2 (RF board detector, active low) opens the
        # SAFE loop: the shack inhibits all radios and latches; the box KILL input drops RLY_EN (D-104, SR-01 H2)
        UA = S.part("controller-board:74LVC1G08_IEC", ("U", 16), "74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5", 127.0, ya, mpn="74LVC1G08GV",
                    mirror="y", rp=(-7.62, -10.16, "left"),
                    desc="2-input AND: READY LED drive = READY_ON AND RF_A2_N (D-104). Nexperia, TI, Diodes")
        assert UA["4"] == (116.84, ya) and UA["1"] == (137.16, R2(ya - 2.54)) and UA["2"] == (137.16, R2(ya + 2.54)), UA
        S.wire(UR["1"], (78.74, ya), RR["1"]); S.wire(RR["2"], UA["4"])
        S.wire(UA["1"], (154.94, R2(ya - 2.54))); S.label("H", "READY_ON", 154.94, R2(ya - 2.54), 0)      # labels clear of the TP4 text
        S.wire(UA["2"], (142.24, R2(ya + 2.54)), (154.94, R2(ya + 2.54))); S.label("H", "RF_A2_N", 154.94, R2(ya + 2.54), 0)
        S.part("Connector:TestPoint", ("TP", 4), "RF_A2_N", TP_FP, 142.24, R2(ya + 2.54), desc="Test point RF_A2_N (D-120)", bom=False, rp=(2.54, -1.27))
        RD = S.part("Device:R", ("R", 36), "100k", R0603, 142.24, R2(ya + 6.35), rp=(1.27, 1.27),
                    desc="RF_A2_N pull-down: J2 open or RF board missing = READY open (fail-safe). RF board pull-up 10k (D-104)")
        assert RD["1"] == (142.24, R2(ya + 2.54)), RD
        S.power("GND", RD["2"])
        S.power("+3V3", UA["5"]); S.power("GND", UA["3"])
    else:
        S.wire(q, (68.58, yn), (93.98, yn), (101.6, yn), (101.6, R2(yp + 5.08)), (106.68, R2(yp + 5.08)))
    RL = S.part("Device:R", ("R", n + 3), "220R", MELF0204, 81.28, yp, rot=90, rp=(-2.54, -5.08),
                desc="LED series resistor: limits the LED pulse to (28 - 1.7) / 220 = 0.12 A while the TVS clamps (VO2611: 200 mA for 100 us)")
    assert RL["1"] == (77.47, yp)
    S.wire(RL["2"], (93.98, yp), (106.68, yp))
    DA = S.part("Device:D", ("D", n + 2), "1N4148W", SOD123, 93.98, R2(yn - 3.81), rot=270, mpn="1N4148W", rp=(-2.54, -2.54, "right"),
                desc="Anti-parallel diode: LED reverse voltage (VR 5 V) and negative pulses")
    assert DA["1"] == (93.98, R2(yp + 2.54)) and DA["2"] == (93.98, yn), DA
    S.wire((93.98, yp), DA["1"])
    xo, yo = 114.3, R2(yp + 2.54)
    U = S.part("Isolator:HCPL-261A", ("U", k), "VO2611", "Package_DIP:DIP-8_W7.62mm", xo, yo, mpn="VO2611",
               desc="10 MBd opto, open-drain output, 15 kV/us CMTI (Vishay VO2611, Rev 2.2 2023-03-15; 6N137 pin-out). "
                    "Second source Broadcom HCPL-2611. IF 10 mA (max 20 mA), IFH max 5 mA", rp=(-12.7, 12.7))
    assert U["2"] == (106.68, yp) and U["3"] == (106.68, R2(yp + 5.08)), U
    for nc in ("1", "4"): S.raw(f'\t(no_connect\n\t\t(at {U[nc][0]} {U[nc][1]})\n\t\t(uuid "{U_()}")\n\t)\n')
    top = (xo, R2(yo - 12.7))
    S.wire(U["8"], top); S.power("+5V", top)
    S.wire(U["7"], (124.46, R2(yo - 2.54)), (124.46, top[1]), top)
    S.power("GND", U["5"])
    RU = S.part("Device:R", ("R", n + 4), "4.7k", R0603, 129.54, R2(yo - 3.81), rp=(1.27, -1.27), desc="Open-drain pull-up to 3.3 V")
    S.power("+3V3", min(RU["1"], RU["2"], key=lambda t: t[1]))
    S.wire(U["6"], (129.54, yo), (137.16, yo))
    S.label("L", sig, 137.16, yo, 0)
    return (137.16, yo)

def loop_tx(S, k, yp):
    """Transmit loop: entry, reverse-polarity diode, PC817 transistor switches the shack loop; LED from DATA_TX via BSS138BK."""
    n = 10 * k
    p, q, yn = loop_entry(S, k, yp)
    S.wire(p, (68.58, yp), (77.47, yp))
    DS = S.part("Device:D", ("D", n + 2), "1N4148W", SOD123, 81.28, yp, rot=180, mpn="1N4148W", rp=(-2.54, -5.08),
                desc="Series diode: protects the PC817 transistor against reverse polarity (VECO 6 V)")
    assert DS["2"] == (77.47, yp), DS
    xo, yo = 99.06, R2(yp + 2.54)
    U = S.part("Isolator:PC817", ("U", k), "PC817X", "Package_DIP:DIP-4_W7.62mm", xo, yo, mirror="y", mpn="PC817X2NSZ9F",
               desc="Phototransistor opto, VCEO 80 V, 5 kV (Sharp D2-A03101EN). CTR rank B or better. Lite-On LTV-817, Everlight EL817", rp=(-3.81, -7.62))
    assert U["4"] == (91.44, yp) and U["3"] == (91.44, R2(yp + 5.08)), U
    S.wire(DS["1"], U["4"])
    S.wire(q, (68.58, yn), (88.9, yn), (88.9, R2(yp + 5.08)), U["3"])
    S.wire(U["1"], (111.76, yp))
    RL = S.part("Device:R", ("R", n + 3), "220R", R0603, 111.76, R2(yp - 3.81), rp=(1.27, -1.27),
                desc="LED current: (5 - 1.2 - 0.1) / 220 = 17 mA (IF max 50 mA). Gives 10 mA loop current over CTR spread and ageing (C-18)")
    S.power("+5V", min(RL["1"], RL["2"], key=lambda t: t[1]))
    Q = S.part("Transistor_FET:Q_NMOS_GSD", ("Q", k), "BSS138BK", SOT23, 119.38, R2(yp + 10.16), mirror="y", mpn="BSS138BK", desc=QN_D,
               rp=(-6.35, 5.08, "left"))                         # mirrored symbol: KiCad flips the justification
    assert Q["3"] == (116.84, R2(yp + 5.08)), Q
    S.wire(U["2"], Q["3"])
    S.power("GND", Q["2"])
    g = (129.54, Q["1"][1])
    S.wire(Q["1"], g, (137.16, g[1])); S.label("H", "DATA_TX", 137.16, g[1], 0)
    RG = S.part("Device:R", ("R", n + 4), "100k", R0603, g[0], R2(g[1] + 3.81), rp=(1.27, 1.27),
                desc="Gate pull-down: LED off (loop open = break) while the MCU is not running")
    S.power("GND", max(RG["1"], RG["2"], key=lambda t: t[1]))

def link_sheet():
    S = Sheet("Controller board: link to the shack and PTT", "A3", [(PATH["link"], 0)], pwr_base=[100])
    vo = {}
    for (k, _, _, what), yp, sig in zip(LOOPS[:3], (50.8, 101.6, 152.4), ("DATA_RX", "PTT_N", "KILL")):
        vo[k] = loop_rx(S, k, yp, sig)
    loop_tx(S, 4, 228.6)
    # data in and KILL to the MCU and the safety gate
    for k, name in ((1, "DATA_RX"), (3, "KILL")):
        x, y = vo[k]
        S.wire((x, y), (147.32, y)); S.label("H", name, 147.32, y, 0)
    # PTT: inverter, then TX_ANY and the three K0 drives in hardware (no MCU in the chain)
    x, y = vo[2]
    UI = S.part("controller-board:74LVC1G14_IEC", ("U", 5), "74LVC1G14", "Package_TO_SOT_SMD:SOT-23-5", 162.56, y, mpn="74LVC1G14GV",
                desc="Schmitt inverter: PTT_N (low = key down) to PTT. Nexperia, TI, Diodes", rp=(2.54, -12.7))
    assert UI["2"] == (147.32, y), UI
    S.wire((x, y), UI["2"])
    S.power("+3V3", UI["5"]); S.power("GND", UI["3"])
    S.raw(f'\t(no_connect\n\t\t(at {UI["1"][0]} {UI["1"][1]})\n\t\t(uuid "{U()}")\n\t)\n')
    bx = 182.88
    S.wire(UI["4"], (bx, y))
    S.wire((bx, y), (bx, R2(y - 7.62)), (198.12, R2(y - 7.62)), (205.74, R2(y - 7.62))); S.label("H", "TX_ANY", 205.74, R2(y - 7.62), 0)
    S.part("Connector:TestPoint", ("TP", 9), "TX_ANY", TP_FP, 198.12, R2(y - 7.62), desc="Test point TX_ANY (D-141)", bom=False, rp=(1.27, -5.08))
    ys = [R2(y + 7.62 * i) for i in (1, 2, 3)]
    S.wire((bx, y), *[(bx, v) for v in ys])
    for i, v in enumerate(ys):
        R = S.part("Device:R", ("R", 51 + i), "0R", R0603, 193.04, v, rot=90, rp=(-2.54, -5.08), dnp=i > 0,
                   desc=["K0 drive select: R1 FT-710 follows its own PTT (fitted, D-63)",
                         "K0 drive select R2: not fitted. R2 K0 comes from RF board U903 IO1_3 after the TX handshake (D-63); fit only for TX mute by PTT",
                         "K0 drive select R3: not fitted. R3 K0 comes from RF board U903 IO1_4 after the TX handshake (D-63); fit only for TX mute by PTT"][i])
        S.wire((bx, v), R["1"]); S.wire(R["2"], (205.74, v)); S.label("H", f"R{i + 1}_K0_DRV", 205.74, v, 0)
    # decoupling, one per opto and the inverter (place each next to its part)
    for i, (net, ref) in enumerate((("+5V", 1), ("+5V", 2), ("+5V", 3), ("+3V3", 4), ("+3V3", 5))):
        xc = R2(256.54 + i * 17.78)
        C = S.part("Device:C", ("C", ref), "1u 16V X7R", C0603, xc, 40.64,
                   desc=["VO2611 U1 VCC decoupling, at the part", "VO2611 U2 VCC decoupling, at the part",
                         "VO2611 U3 VCC decoupling, at the part", "74LVC1G14 U5 decoupling, at the part", "74LVC1G08 U16 decoupling, at the part"][i])
        S.power(net, min(C["1"], C["2"], key=lambda t: t[1])); S.power("GND", max(C["1"], C["2"], key=lambda t: t[1]))
    S.text("Link to the shack (D-56, D-57): Cat6 #1 UTP, four opto current loops, 10 mA each, powered from the shack (12 V, about 820R there).\\n"
           "T568B pairs, + wire first: pair 1 = pins 4/5 data in, pair 2 = 1/2 PTT, pair 3 = 3/6 SAFE, pair 4 = 7/8 data out.\\n"
           "Entry per pair: GDT to CHASSIS (box earth), common-mode choke L1 to L4 with Y-capacitor footprints to CHASSIS (not fitted, D-130),\\n"
           "47R MELF per wire (loop current = voltage across it / 47R, the test access), SMBJ15CA across the pair; then the opto.\\n"
           "Receive: loop current = LED on = output low. DATA_RX idle (mark) is low: the UART RX is inverted in firmware (ESP32-C3 line inverse).\\n"
           "PTT: FT-710 TX GND closes loop 2; PTT_N low; U5 gives TX_ANY and the K0 drives, in hardware, not through the MCU.\\n"
           "SAFE (D-62): loop 3 through the shack KILL switch and sense, and the box READY switch U6 (closed while NOR(MCU_EN_N, FAULT) = 1 and RF_A2_N = 1);\\n"
           "RF_A2_N (D-104, SR-01 H2): RF board A2 detector, low = RF on the receive-only column: U16 opens READY, the shack inhibits all radios.\\n"
           "any break (KILL, READY open, cut cable, no shack supply) = no current = KILL high (to the safety gate). R52, R53 not fitted (D-63).\\n"
           "Transmit: DATA_TX high (UART idle) = LED on = loop closed; MCU off = loop open, so the shack sees a break. 9600 baud (C-18).", 25.4, 259.08)
    S.section(15.24, 30.48, 170.18, 78.74, "Pair 1: data shack to box (receive loop)")
    S.section(15.24, 81.28, 144.78, 129.54, "Pair 2: PTT from the FT-710 (receive loop)")
    S.section(146.05, 81.28, 228.6, 129.54, "PTT to TX_ANY and K0 drives (D-63)")
    S.section(15.24, 132.08, 170.18, 205.74, "Pair 3: SAFE loop, READY switch and A2 RF stop (D-62, D-104)")
    S.section(15.24, 208.28, 170.18, 256.54, "Pair 4: data box to shack (transmit loop)")
    S.section(248.92, 25.4, 345.44, 55.88, "Decoupling, one 1 uF at each IC (D-127)")
    return S.finish()

def mcu_sheet():
    S = Sheet("Controller board: MCU, 3.3 V and safety gate", "A3", [(PATH["mcu"], 0)], pwr_base=[200])
    gnd = lambda pt: S.power("GND", pt, rp=(0, 1.905, "center"))     # net name centred under the symbol (Value at rp y + 2.54)
    # 3.3 V LDO, same part as on the RF board (D-41, D-55)
    U1 = S.part("controller-board:LP2985-3.3", ("U", 11), "LP2985-33", "Package_TO_SOT_SMD:SOT-23-5", 60.96, 45.72, mpn="LP2985-33DBVR",
                desc="3.3 V LDO, 150 mA, VIN max 16 V. Second source ST LD2985BM33R. ON/OFF tied to VIN (D-55)", rp=(-7.62, -8.89))
    y0 = U1["1"][1]
    S.power("+5V", (38.1, y0))
    S.wire((38.1, y0), (43.18, y0), (45.72, y0), (48.26, y0), U1["1"])
    S.wire((48.26, y0), (48.26, U1["3"][1]), U1["3"])
    CI = S.part("Device:C", ("C", 11), "1u 16V X7R", C0603, 43.18, R2(y0 + 3.81), rp=(-2.54, -1.27, "right"), desc="LDO input")
    assert CI["1"] == (43.18, y0); gnd(CI["2"])
    gnd(U1["2"])
    S.wire(U1["4"], (76.2, U1["4"][1]))
    CB = S.part("Device:C", ("C", 12), "10n 50V X7R", C0603, 76.2, R2(U1["4"][1] + 3.81), rp=(-2.54, -1.27, "right"), desc="LDO noise bypass")
    gnd(CB["2"])
    yo = U1["5"][1]
    S.wire(U1["5"], (83.82, yo), (88.9, yo))
    CO = S.part("Device:C", ("C", 13), "4.7u 16V X7R", C0805, 83.82, R2(yo + 3.81),
                desc="LDO output: at least 2.2 uF effective at 3.3 V (legacy LP2985 die, LD2985)")
    assert CO["1"] == (83.82, yo); gnd(CO["2"])
    RL3 = S.part("Device:R", ("R", 65), "0R", "Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", 92.71, yo, rot=90, rp=(-2.54, -5.08),
                 desc="+3V3 current-measurement link: lift to measure the 3.3 V load (D-120)")
    assert RL3["1"] == (88.9, yo), RL3
    S.wire(RL3["2"], (101.6, yo), (109.22, yo), (116.84, yo))
    S.power("+3V3", (101.6, yo)); S.power("+3V3", (109.22, yo), flag=True)     # U11 drives +3V3 through R65
    S.part("Connector:TestPoint", ("TP", 2), "+3V3", TP_FP, 116.84, yo, desc="Test point +3V3 (D-120)", bom=False, rp=(1.27, -5.08))
    S.part("Connector:TestPoint", ("TP", 1), "+5V", TP_FP, 45.72, y0, desc="Test point +5V (D-120)", bom=False, rp=(1.27, -5.08))
    # DevKit A1: one board symbol as the physical board, a short wire and a net label at each used pin (D-93)
    A1 = S.part("controller-board:ESP32-C3-DevKit-RUST", ("A", 1), "ESP32-C3-DevKit-RUST-1", "controller-board:ESP32-C3-DevKit-RUST_Socket",
                60.96, 182.88, rp=(15.24, 27.94, "right"),
                desc="ESP32-C3 Rust board pushed into gold-flash socket headers Sullins PPPC161LFBN-RC (1x16) and PPPC121LFBN-RC (1x12) (D-55, D-93 to D-95). RUST-1 Rev 1.2a fitted; RUST-2 fits with JP11 1-2 cut and 2-3 bridged")
    assert A1["1"] == (43.18, 165.1) and A1["16"] == (43.18, 203.2) and A1["28"] == (78.74, 175.26) and A1["17"] == (78.74, 203.2), A1
    dk = {5: "EXP_INT", 6: "WDI", 8: "LATCH_CLR", 9: "MCU_EN_N", 10: "KILL", 11: "FAULT_IO6", 12: "SDA_IO7", 13: "SCL", 14: "DATA_TX", 15: "DATA_RX"}
    for n in range(1, 29):
        x, y = A1[str(n)]
        if n in dk: S.wire((x, y), (35.56, y)); S.label("L", dk[n], 35.56, y, 180)
        elif n == 2: S.wire((x, y), (20.32, y)); S.power("+3V3", (20.32, y))
        elif n == 4: S.wire((x, y), (20.32, y)); gnd((20.32, y))
        elif n == 27: S.wire((x, y), (83.82, y)); gnd((83.82, y))                              # EN low: board buck off (D-55)
        elif n == 17: S.wire((x, y), (86.36, y)); S.label("L", "SDA_IO10", 86.36, y, 0)     # SDA on RUST-1 (D-94)
        else: S.raw(f'\t(no_connect\n\t\t(at {x} {y})\n\t\t(uuid "{U()}")\n\t)\n')
    # nets that leave the sheet: hierarchical labels as before, fed from the DevKit net labels
    for net, y in (("EXP_INT", 111.76), ("SCL", 132.08), ("DATA_TX", 134.62), ("DATA_RX", 137.16)):
        S.wire((58.42, y), (66.04, y)); S.label("L", net, 58.42, y, 180); S.label("H", net, 66.04, y, 0)
    JS = S.part("controller-board:SolderJumper_3_Bridged12", ("JP", 11), "SDA SEL", "Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm_NumberLabels",
                48.26, 129.54, rot=90, rp=(-3.81, -1.27, "right"),
                desc="SDA select (D-94, D-192): 1-2 bridged by copper = DevKit-RUST-1 (SDA GPIO10, pad 17). DevKit-RUST-2 (SDA GPIO7, pad 12): cut 1-2, bridge 2-3. Firmware SDA pin must match")
    assert JS["2"] == (53.34, 129.54) and JS["1"] == (48.26, 134.62) and JS["3"] == (48.26, 124.46), JS
    S.wire(JS["2"], (66.04, 129.54)); S.label("H", "SDA", 66.04, 129.54, 0)
    S.wire(JS["1"], (48.26, 142.24)); S.label("L", "SDA_IO10", 48.26, 142.24, 270)
    S.wire(JS["3"], (48.26, 116.84)); S.label("L", "SDA_IO7", 48.26, 116.84, 90)
    # ---- safety gate (D-59): RLY_EN = NOR(KILL, MCU_EN_N, FAULT) ----
    # U12 supervisor and watchdog: WDI from GPIO1, 1k to GND so that a floating WDI still trips the watchdog
    U12 = S.part("Power_Supervisor:TPS3823-xxDBV", ("U", 12), "TPS3823A-33", "Package_TO_SOT_SMD:SOT-23-5", 114.3, 93.98,
                 mpn="MAX823SEUK+T", rp=(-8.89, -11.43, "right"),
                 desc="Supervisor 2.93 V (2.85 to 3.00) + watchdog 1.12 to 2.4 s, push-pull RESET_N (150 uA source: logic loads only), -40 to 125 C (ADI MAX823 19-0487 Rev 5). Second sources TI TPS3823A-33DBVR (A version only: no latch-up on WDI pulses during reset) and Diodes APX823-29W5G-7 (D-148, D-195)")
    assert U12["4"] == (104.14, 91.44) and U12["1"] == (124.46, 93.98), U12
    S.wire((88.9, 91.44), (96.52, 91.44)); S.label("L", "WDI", 88.9, 91.44, 180)
    RWL = S.part("Device:R", ("R", 64), "0R", R0603, 100.33, 91.44, rot=90, rp=(-5.08, -3.81, "right"),
                 desc="Watchdog link (D-123): fitted in use. Open on the bench: U12 WDI floats, so the watchdog is off (MAX823 WDI pin; TPS3823 SLVS165O 7.3.4); the supply supervisor stays active")
    assert RWL["1"] == (96.52, 91.44) and RWL["2"] == U12["4"], RWL
    RW = S.part("Device:R", ("R", 61), "1k", R0603, 96.52, 95.25, rp=(1.27, 1.27),
                desc="WDI pull-down: a floating WDI would disable the watchdog (MAX823 WDI pin; TPS3823 7.3.4). MAX823 WDI sources max 20 uA: 20 mV low")
    assert RW["1"] == (96.52, 91.44); gnd(RW["2"])
    S.raw(f'\t(no_connect\n\t\t(at {U12["3"][0]} {U12["3"][1]})\n\t\t(uuid "{U()}")\n\t)\n')     # MR: internal 90k pull-up
    S.power("+3V3", U12["5"]); gnd(U12["2"])
    # U13 fault latch: set by RESET_N (power-up, brown-out, watchdog); cleared by a LATCH_CLR edge only when RESET_N is high
    FX, FY = 147.32, 96.52
    U13 = S.part("controller-board:74LVC1G74_IEC", ("U", 13), "74LVC1G74", "Package_SO:VSSOP-8_2.3x2mm_P0.5mm", FX, FY,
                 mpn="SN74LVC1G74DCUR", rp=(6.35, -12.7),
                 desc="D flip-flop, fault latch. D = GND, CLR_N = 3V3, PRE_N = RESET_N. -40 to 125 C (TI SCES794G, DCU VSSOP-8, D-154). Second source Nexperia 74LVC2G74DC (SOT765-1, same pin-out and MO-187 land)")
    assert U13["7"] == (137.16, 93.98) and U13["1"] == (137.16, 99.06) and U13["5"] == (157.48, 93.98), U13
    S.wire(U12["1"], U13["7"]); S.label("L", "RESET_N", 127.0, 93.98)
    S.wire(U13["6"], (134.62, U13["6"][1])); S.power("+3V3", (134.62, U13["6"][1]))
    S.wire(U13["2"], (134.62, U13["2"][1])); gnd((134.62, U13["2"][1]))
    S.raw(f'\t(no_connect\n\t\t(at {U13["3"][0]} {U13["3"][1]})\n\t\t(uuid "{U()}")\n\t)\n')
    S.power("+3V3", U13["8"]); gnd(U13["4"])
    XC = 127.0
    S.wire(U13["1"], (XC, U13["1"][1]), (XC, 109.22), (132.08, 109.22)); S.label("L", "LATCH_CLR", 132.08, 109.22, 0)
    RL = S.part("Device:R", ("R", 62), "100k", R0603, 123.19, 109.22, rot=90, rp=(-2.54, -5.08),
                desc="LATCH_CLR pull-down: no clock edge while the MCU is in reset")
    assert RL["2"] == (127.0, 109.22), RL
    lo = RL["1"]
    gnd(lo)
    # U14 gate: any input high (KILL, MCU_EN_N, FAULT) forces RLY_EN low
    NX, NY = 177.8, 121.92
    U14 = S.part("controller-board:74LVC1G27_IEC", ("U", 14), "74LVC1G27", "Package_TO_SOT_SMD:SOT-23-6", NX, NY,
                 mpn="SN74LVC1G27DBVR", rp=(3.81, -10.16),
                 desc="3-input NOR, relay enable gate. -40 to 125 C (TI SCES488E). Second source Nexperia 74LVC1G27GV (SOT457, same pin-out and land, D-155); candidate Diodes 74LVC1G27W6-7 (SOT26, pin-out to check)")
    assert U14["6"] == (167.64, 119.38) and U14["1"] == (167.64, 121.92) and U14["3"] == (167.64, 124.46), U14
    S.wire(U13["5"], (160.02, 93.98), (165.1, 93.98)); S.wire((160.02, 93.98), (160.02, 101.6), (160.02, 119.38), U14["6"]); S.label("L", "FAULT", 160.02, 119.38)
    # FAULT read-back (D-191, review S-1): the MCU sees a supervisor trip that the MCU itself did not notice. 1k limits the
    # current if GPIO6 is ever driven by mistake
    RF_ = S.part("Device:R", ("R", 66), "1k", R0603, 167.64, 101.6, rot=90, rp=(0, -2.54),
                 desc="FAULT to GPIO6 (D-191): series resistor, the MCU reads the fault latch")
    assert RF_["1"] == (163.83, 101.6) and RF_["2"] == (171.45, 101.6), RF_
    S.wire((160.02, 101.6), RF_["1"]); S.wire(RF_["2"], (177.8, 101.6)); S.label("L", "FAULT_IO6", 177.8, 101.6, 0)
    S.part("Connector:TestPoint", ("TP", 3), "FAULT", TP_FP, 165.1, 93.98, desc="Test point FAULT, the fault latch Q (D-120)", bom=False, rp=(1.27, -5.08))
    S.wire((134.62, 121.92), (142.24, 121.92), U14["1"]); S.label("L", "MCU_EN_N", 134.62, 121.92, 180)
    RE = S.part("Device:R", ("R", 63), "100k", R0603, 142.24, 118.11, rp=(1.27, -3.81),
                desc="MCU_EN_N pull-up: relays off while the MCU is in reset or not fitted")
    assert RE["2"] == (142.24, 121.92), RE
    S.power("+3V3", RE["1"])
    S.wire((139.7, 124.46), (149.86, 124.46), U14["3"]); S.label("L", "KILL", 139.7, 124.46, 180)
    S.wire((149.86, 124.46), (149.86, 127.0)); S.label("H", "KILL", 149.86, 127.0, 0)
    S.power("+3V3", U14["5"]); gnd(U14["2"])
    S.wire(U14["4"], (195.58, NY)); S.label("H", "RLY_EN", 195.58, NY, 0)
    # test points for the assembled unit (D-141): the RF board test points of these nets are under the controller board
    for i, (n, net) in enumerate(((5, "SCL"), (6, "SDA"), (7, "EXP_INT"), (8, "RLY_EN"))):
        tx = R2(233.68 + 15.24 * i)
        S.part("Connector:TestPoint", ("TP", n), net, TP_FP, tx, 78.74, desc=f"Test point {net} (D-141)", bom=False, rp=(1.27, -5.08))
        S.wire((tx, 78.74), (tx, 83.82)); S.label("L", net, tx, 83.82, 270)
    # U15 READY gate (D-62): READY_ON = NOR(MCU_EN_N, FAULT), drives the READY photorelay LED on the link sheet. KILL is not an input,
    # else the SAFE loop could never start
    U15 = S.part("controller-board:74LVC1G02_IEC", ("U", 15), "74LVC1G02", "Package_TO_SOT_SMD:SOT-23-5", NX, 162.56, mpn="74LVC1G02GV",
                 rp=(3.81, -10.16), desc="2-input NOR, READY gate: READY_ON = NOR(MCU_EN_N, FAULT) (D-62). Nexperia, TI, Diodes")
    assert U15["1"] == (167.64, 160.02) and U15["2"] == (167.64, 165.1) and U15["4"] == (187.96, 162.56), U15
    S.wire((160.02, 160.02), U15["1"]); S.label("L", "MCU_EN_N", 160.02, 160.02, 180)
    S.wire((160.02, 165.1), U15["2"]); S.label("L", "FAULT", 160.02, 165.1, 180)
    S.wire(U15["4"], (195.58, 162.56)); S.label("H", "READY_ON", 195.58, 162.56, 0)
    S.power("+3V3", U15["5"]); gnd(U15["3"])
    # decoupling, one 100n at each gate IC
    for i, (x, what) in enumerate(((233.68, "U12"), (251.46, "U13"), (269.24, "U14"), (287.02, "U15"))):
        C = S.part("Device:C", ("C", 14 + i), "1u 16V X7R", C0603, x, 40.64, desc=f"{what} decoupling, at the part (one value, D-127)")
        S.power("+3V3", C["1"]); gnd(C["2"])
    S.text("MCU: ESP32-C3 Rust board A1 (DevKit-RUST-1 Rev 1.2a fitted, RUST-2 fits) in gold socket headers (D-93 to D-95). Net labels at the DevKit pins.\\n"
           "3V3 pin from U11 (LDO); EN low keeps the board buck off;\\n"
           "5V/VBUS not connected, so the PC can stay on USB (board diode D6). Wi-Fi and BLE off in firmware.\\n"
           "I2C: board bus SDA GPIO10 (RUST-1) or GPIO7 (RUST-2), set by JP11 (1-2 bridged by copper for RUST-1; RUST-2: cut 1-2, bridge 2-3; D-94, D-192); SCL GPIO8. 10k on the board; 2.2k on the RF board.\\n"
           "GPIO0 EXP_INT, GPIO1 WDI (kick at least every 0.9 s), GPIO3 LATCH_CLR (rising edge), GPIO4 MCU_EN_N (low = relays allowed),\\n"
           "GPIO5 KILL (read), GPIO6 FAULT (read, 1k R66, D-191), GPIO20/21 UART 9600 baud. GPIO2, 8, 9 are strapping pins: GPIO2 and GPIO9 not used; GPIO8 is SCL.\\n"
           "Board LED on GPIO7 (RUST-1) or GPIO10 (RUST-2): the SDA pin of the other board.\\n"
           "Safety gate (D-59): RLY_EN = NOR(KILL, MCU_EN_N, FAULT). FAULT is set by RESET_N: power-up, 3V3 below 2.83 to 3.00 V, or no WDI edge for 0.9 to 2.5 s.\\n"
           "After a reset the relays stay off until the MCU gives a LATCH_CLR edge. KILL is not latched. RLY_EN has a 100k pull-down on the RF board.\\n"
           "READY_ON = NOR(MCU_EN_N, FAULT) (U15, D-62): closes the READY switch in the SAFE loop. Start-up: LATCH_CLR, MCU_EN_N low, then KILL reads 0 (F11).\\n"
           "U12 RESET_N does not reset the MCU (DevKit pin 1 RST open); the ESP32-C3 has its own watchdogs. MR open: internal 90k pull-up.", 25.4, 223.52)
    S.section(25.4, 25.4, 124.46, 63.5, "3.3 V supply (D-55, D-120)")
    S.section(15.24, 101.6, 81.28, 152.4, "SDA select and sheet I/O (D-94)")
    S.section(15.24, 154.94, 99.06, 218.44, "MCU: ESP32-C3 Rust board (D-55, D-93 to D-95)")
    S.section(83.82, 66.04, 215.9, 139.7, "Safety gate: RLY_EN = NOR(KILL, MCU_EN_N, FAULT) (D-59)")
    S.section(152.4, 142.24, 215.9, 182.88, "READY gate (D-62)")
    S.section(223.52, 25.4, 302.26, 55.88, "Decoupling, one 1 uF at each IC (D-127)")
    S.section(223.52, 63.5, 302.26, 96.52, "Test points, assembled unit (D-141)")
    return S.finish()

def root_sheet():
    """Overview: signal flow left to right, RJ45 LINK -> Link and PTT -> MCU and J2. Nets are wires.
    Sheet pins sit on a common 2.54 mm slot grid so that every wire is one straight segment."""
    S = Sheet("Controller board: overview and connectors", "A3", [(f"/{ROOT_UUID}", 0)], pwr_base=[900])
    S.u = ROOT_UUID
    LX, LY, LW = 76.2, 50.8, 38.1                            # Link and PTT block
    MX, MW = 139.7, 55.88                                    # MCU block, same top as Link; wide for name and file
    slot = lambda i: R2(LY + (i + 1) * 2.54)
    # RJ45 LINK (top wall), T568B. Pin 1 on slot 0, so that each pin wires straight to its Link sheet pin
    J1 = S.part("Connector:8P8C", ("J", 1), "RJ45 LINK", "controller-board:RJ45_8P8C_Unshielded_TabDown", 38.1, R2(slot(0) + 10.16),
                mpn="615008137121", desc="RJ45 LINK, Cat6 #1 UTP to the shack (D-56, D-57). Unshielded, tab down: Wurth 615008137121, "
                     "second source Molex 95501-2881 (D-138)", rp=(-5.08, -17.78))
    pinnet = {}
    for k, nm, (a, b), _ in LOOPS: pinnet[a], pinnet[b] = f"L{k}P", f"L{k}N"
    jp = sorted(range(1, 9), key=lambda p: J1[str(p)][1])
    assert [J1[str(p)][1] for p in jp] == [slot(i) for i in range(8)], "J1 pins off the slot grid"
    left = [pinnet[p] for p in jp] + ["", "", "", "CHASSIS"]
    right = ["DATA_RX", "DATA_TX", "KILL", "READY_ON", "", "", "", "", "TX_ANY", "R1_K0_DRV", "R2_K0_DRV", "R3_K0_DRV", "RF_A2_N"]
    S.raw(sheet_block("link", "Link and PTT", "link.kicad_sch", 2, LX, LY, LW, R2(14 * 2.54), left, right))
    for i, p in enumerate(jp): S.wire(J1[str(p)], (LX, slot(i)))
    # chassis lug: GDT centre electrodes to the box earth
    HX = 63.5
    H1 = S.part("Mechanical:MountingHole_Pad", ("H", 1), "M3 CHASSIS", "MountingHole:MountingHole_3.2mm_M3_Pad", HX, slot(9),
                desc="Plated M3 lug: short wire to the RVS box earth bar. GDT surge path (D-57)", bom=False, rp=(-3.81, -1.27, "right"))
    assert H1["1"] == (HX, slot(10)), H1
    S.wire(H1["1"], (HX, slot(11)), (LX, slot(11)))
    # MCU block: link data on the left; I2C to J2 and the safety-gate signals on the right
    ml = ["DATA_RX", "DATA_TX", "KILL", "READY_ON"]
    mr = ["", "", "", "", "SCL", "SDA", "EXP_INT", "RLY_EN"]
    S.raw(sheet_block("mcu", "MCU and safety gate", "mcu.kicad_sch", 3, MX, LY, MW, R2(8.5 * 2.54), ml, mr, file_top=True))
    for i in range(4): S.wire((R2(LX + LW), slot(i)), (MX, slot(i)))
    # J2: mates with RF board J14 (same pin-out, D-52): +5V comes from the RF board. Pin 1 on slot 4
    JX = 215.9
    JH = S.part("Connector_Generic:Conn_02x12_Odd_Even", ("J", 2), "to RF board J14", "Connector_PinSocket_2.54mm:PinSocket_2x12_P2.54mm_Vertical",
                JX, R2(slot(4) + 12.7), mpn="ESQ-112-33-G-D",
                desc="Board-to-board elevated socket on the controller board underside, onto RF board J14 (D-51, D-52, D-139): Samtec "
                     "ESQ-112-33-G-D, 16.13 mm high; second source ESW-112-33-G-D. +5V from the RF board on pins 2 and 4",
                rp=(-5.08, -20.32))
    assert JH["1"] == (R2(JX - 5.08), slot(4)), JH["1"]
    PX = JH["1"][0]
    for i in (4, 5, 6, 7): S.wire((R2(MX + MW), slot(i)), (PX, slot(i)))                        # SCL, SDA, EXP_INT, RLY_EN
    for i in range(8, 13): S.wire((R2(LX + LW), slot(i)), (PX, slot(i)))                        # TX_ANY, R1..R3_K0_DRV, RF_A2_N (pin 17)
    assert JH["17"] == (PX, slot(12)), JH["17"]
    for n in (19, 21, 23): S.raw(f'\t(no_connect\n\t\t(at {JH[str(n)][0]} {JH[str(n)][1]})\n\t\t(uuid "{U()}")\n\t)\n')
    ex = R2(JX + 10.16)
    ends = []
    for n in range(2, 25, 2):
        px, py = JH[str(n)]; S.wire((px, py), (ex, py)); ends.append(py)
    top = R2(ends[0] - 2.54)                                 # +5V feed from the right: text clear of the J2 fields
    S.wire((ex, ends[1]), (ex, ends[0]), (ex, top), (R2(ex + 7.62), top), (R2(ex + 15.24), top))
    S.power("+5V", (R2(ex + 7.62), top)); S.power("+5V", (R2(ex + 15.24), top), flag=True)
    g = ends[2:]
    for a, b in zip(g, g[1:]): S.wire((ex, a), (ex, b))
    S.wire((ex, g[-1]), (ex, R2(g[-1] + 2.54)), (R2(ex + 7.62), R2(g[-1] + 2.54))); S.power("GND", (ex, R2(g[-1] + 2.54)))
    S.power("GND", (R2(ex + 7.62), R2(g[-1] + 2.54)), flag=True)
    S.text("Controller board, unit 1 (architecture rev C, D-51, D-55 to D-58). Stacked above the RF board; J2 plugs onto RF board J14.\\n"
           "RJ45 LINK on the top wall: Cat6 #1 to the shack, T568B, four opto current loops (L1 data in, L2 PTT, L3 SAFE, L4 data out).\\n"
           "Safety gate on the MCU sheet (D-59): supervisor with watchdog, fault latch and NOR gate drive RLY_EN (J2 pin 7).\\n"
           "RLY_EN has its 100k pull-down on the RF board: without the controller board all relays stay off.", 25.4, 104.14)
    return S.finish()

files = {"link.kicad_sch": link_sheet(), "mcu.kicad_sch": mcu_sheet(), f"{PROJECT}.kicad_sch": root_sheet()}
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
libs = [v.replace('(symbol "controller-board:', '(symbol "', 1) for k, v in sorted(SYMS.items()) if k.startswith("controller-board:")]
open(f"{PROJECT}.kicad_sym", "w").write('(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kicad_symbol_editor")\n'
                                        '\t(generator_version "10.0")\n\t' + "\n\t".join(l.replace("\n", "\n\t") for l in libs) + "\n)\n")
open("fp-lib-table", "w").write('(fp_lib_table\n\t(version 7)\n\t(lib (name "controller-board")(type "KiCad")'
                                '(uri "${KIPRJMOD}/lib/controller-board.pretty")(options "")(descr "Controller board rev C, project footprints"))\n)\n')
open("sym-lib-table", "w").write('(sym_lib_table\n\t(version 7)\n\t(lib (name "controller-board")(type "KiCad")'
                                 '(uri "${KIPRJMOD}/controller-board.kicad_sym")(options "")(descr "Shack Relay Matrix rev C controller"))\n)\n')
pro = json.load(open(f"{PROJECT}.kicad_pro")) if os.path.exists(f"{PROJECT}.kicad_pro") else \
      {"meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3}}
pro.setdefault("schematic", {})["top_level_sheets"] = [{"filename": f"{PROJECT}.kicad_sch", "name": PROJECT, "uuid": ROOT_UUID}]
open(f"{PROJECT}.kicad_pro", "w").write(json.dumps(pro, indent=2) + "\n")
print(GENERATOR_REV, "root", ROOT_UUID, "files", list(files))
