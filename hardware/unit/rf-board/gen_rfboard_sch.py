#!/usr/bin/env python3
"""Generate the rev C unit RF board schematic (root + hierarchical sheets), v2: drawn with wires.

Architecture: docs/architecture.md, docs/design/rf-board.md. Decisions: design-log.md.
Run from this folder. Overwrites rf-board.kicad_sch, power.kicad_sch, radio_port.kicad_sch,
antenna_port.kicad_sch, rf-board.kicad_sym, sym-lib-table, fp-lib-table.
Library symbols come from _sym/ (copied from the KiCad 10 libraries).

Drawing rules (hardware skill, section 11): signal flow left to right, supplies up, ground down,
wires inside a sheet, labels only where a net leaves the sheet, junction dots at every T,
no wire end on the middle of another wire (checked by an assert).
"""
import json, math, os, re, uuid

PROJECT = "rf-board"
DATE = "2026-10-23"
GENERATOR_REV = "v12g-be3"
RX_ONLY = {"2"}   # receive-only antenna columns (unit 1: A2 RX loop). Their TX relays and drivers are not fitted (D-103, SR-01)
GEN = set()   # uuids made by U(): replaced by stable uuid5 values when the files are written (Git-friendly)
def U():
    u = str(uuid.uuid4()); GEN.add(u); return u
U_ = U
# Fixed root and sheet uuids. KiCad 10 keeps the top-level sheet uuid in the .kicad_pro
# (schematic.top_level_sheets) and starts every instance path with it. A new uuid per run
# breaks the paths: KiCad then "fixes" the file and gives all sheet instances the same references.
NS = uuid.uuid5(uuid.NAMESPACE_DNS, "pe1rgu.shack-relay-matrix.rev-c")
ROOT_UUID = str(uuid.uuid5(NS, "root"))
R2 = lambda v: round(v + 0.0, 2)

# ---------- library symbols ----------
def load(lib, name):
    t = open(f"_sym/{lib}__{name}.sym").read().strip()
    return t.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)
RLY = "rf-board:RTD14012F"
SYMS = {
    "Device:R_Pack04": load("Device", "R_Pack04"), "Connector:TestPoint": load("Connector", "TestPoint"),
    "Device:C_Polarized": load("Device", "C_Polarized"),
    # RT1 RTD14012F: KiCad has RT314A12 only as "extends RT314A03"; a flattened copy sits in the project library.
    # The library text is for the latching RT1; the drawing is a plain coil (IEC form).
    RLY: open("_sym/Relay__RT314A03.sym").read().strip().replace("RT314A03", "RTD14012F")
        .replace('(symbol "RTD14012F"', '(symbol "rf-board:RTD14012F"', 1)
        .replace("DocNm=RT1_bistable&DocType=DS", "DocNm=RT1pb&DocType=DS")
        .replace("Schrack RT1 relay, bistable single pole dual throw, single DC coil, 3V",
                 "TE RT1 RTD14012F, monostable, 1 CO 16 A, 12 VDC coil 400 mW, wash-tight (RTIII)")
        .replace("TE SPDT 1P2T CO bistable DC", "TE RT1 SPDT 1P2T CO monostable DC"),
    "Connector:Conn_Coaxial": load("Connector", "Conn_Coaxial"),
    "Device:R": load("Device", "R"), "Device:L": load("Device", "L"), "Device:C": load("Device", "C"),
    "Device:D_Schottky": load("Device", "D_Schottky"), "Device:GDT_2Pin": load("Device", "GDT_2Pin"),
    "Connector_Generic:Conn_01x02": load("Connector_Generic", "Conn_01x02"),
    "Connector_Generic:Conn_02x12_Odd_Even": load("Connector_Generic", "Conn_02x12_Odd_Even"),
    "Mechanical:MountingHole_Pad": load("Mechanical", "MountingHole_Pad"),
    "Jumper:SolderJumper_2_Open": load("Jumper", "SolderJumper_2_Open"),
    "power:GND": load("power", "GND"), "power:+12V": load("power", "+12V"), "power:+5V": load("power", "+5V"),
    "power:PWR_FLAG": load("power", "PWR_FLAG"), "power:+3V3": load("power", "+3V3"),
    "Device:D": load("Device", "D"), "Device:Fuse": load("Device", "Fuse"),
    "Comparator:LM2901": load("Comparator", "LM2901"),
    "Interface_Expansion:PCA9539xD": load("Interface_Expansion", "PCA9539xD"),
    # BAS70-04 series pair, SOT-23: KiCad has no BAS70 symbols; BAT54S has the same pin-out (1 A1, 2 K2, 3 K1/A2).
    "rf-board:BAS70-04": open("_sym/Diode__BAT54S.sym").read().strip()
        .replace('(symbol "BAT54S"', '(symbol "rf-board:BAS70-04"', 1).replace("BAT54S_", "BAS70-04_")
        .replace("Vr 30V, If 200mA, Dual schottky barrier diode, in series, SOT-323", "Vr 70V, If 70mA, dual Schottky in series, SOT-23 (1 A1, 2 K2, 3 K1/A2)"),
    "Device:D_Zener": load("Device", "D_Zener"),
    "Transistor_FET:Q_NMOS_GSD": load("Transistor_FET", "Q_NMOS_GSD"),
    "Transistor_FET:Q_PMOS_GSD": load("Transistor_FET", "Q_PMOS_GSD"),
    "Transistor_FET:Q_PMOS_GDS": load("Transistor_FET", "Q_PMOS_GDS"),
    "Transistor_BJT:Q_PNP_BEC": load("Transistor_BJT", "Q_PNP_BEC"),
    # LP2985-3.3 flattened from "extends LP2985-1.8" into the project library
    "rf-board:LP2985-3.3": open("_sym/Regulator_Linear__LP2985-3.3.sym").read().strip()
        .replace('(symbol "LP2985-3.3"', '(symbol "rf-board:LP2985-3.3"', 1),
}
def pins_of(t):
    out = {}
    for blk in t.split("(pin ")[1:]:
        m = re.search(r"\(at ([-\d.]+) ([-\d.]+) (\d+)\)", blk)
        n = re.search(r'\(number "([^"]+)"', blk)
        if m and n: out[n.group(1)] = (float(m.group(1)), float(m.group(2)), int(m.group(3)))
    return out
PINS = {k: pins_of(v) for k, v in SYMS.items()}
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
PINS_U = {"Comparator:LM2901": unit_pins(SYMS["Comparator:LM2901"], "LM2901")}

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
            f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify {just})\n\t\t\t)\n\t\t)\n')

C1 = "Design: Prins Doornekamp, PE1RGU"
C2 = "RT1 RTD14012F x37, SO-239 Amphenol 83-798 x7, SMA EXP x3, XT60 x2, XT30"
C3 = "Crossbar: rows on L1, columns on L6. Unit 1 = 3 radios x 4 antennas + EXP"
C4 = "JLC06161H-7628A, 1.6 mm, 6 layers. RF: CPWG W 0.975 / gap 2.0 mm, 50 ohm"

class Sheet:
    def __init__(self, title, paper, insts, pwr_base=None):
        """insts: list of (sheet path, reference base). pwr_base: bases for #PWR / #FLG references."""
        self.u, self.title, self.paper, self.insts = U(), title, paper, insts
        self.pwr_bases = pwr_base or [b for _, b in insts]
        self.items, self.segs, self.pinpts, self.used, self.npwr = [], [], [], set(), 0
        self.aliases = {}                                     # bus aliases: name -> member nets

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
    def raw(self, s): self.items.append(s)
    def section(self, x0, y0, x1, y1, title):
        """Dashed frame around one function, title inside the top left corner (hardware skill, schematic-and-marking.md)."""
        self.items.append(f'\t(rectangle\n\t\t(start {R2(x0)} {R2(y0)})\n\t\t(end {R2(x1)} {R2(y1)})\n'
                          f'\t\t(stroke\n\t\t\t(width 0.254)\n\t\t\t(type dash)\n\t\t)\n\t\t(fill\n\t\t\t(type none)\n\t\t)\n'
                          f'\t\t(uuid "{U()}")\n\t)\n')
        self.items.append(f'\t(text "{title}"\n\t\t(exclude_from_sim no)\n\t\t(at {R2(x0 + 1.27)} {R2(y0 + 1.27)} 0)\n\t\t(effects\n'
                          f'\t\t\t(font\n\t\t\t\t(size 1.524 1.524)\n\t\t\t\t(bold yes)\n\t\t\t)\n\t\t\t(justify left top)\n\t\t)\n'
                          f'\t\t(uuid "{U()}")\n\t)\n')
    def bus(self, *pts):
        for a, b in zip(pts, pts[1:]):
            self.items.append(f'\t(bus\n\t\t(pts\n\t\t\t(xy {R2(a[0])} {R2(a[1])}) (xy {R2(b[0])} {R2(b[1])})\n\t\t)\n'
                              f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{U()}")\n\t)\n')
    def bus_entry(self, x, y, dx, dy):
        self.items.append(f'\t(bus_entry\n\t\t(at {R2(x)} {R2(y)})\n\t\t(size {dx} {dy})\n\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{U()}")\n\t)\n')
    def bus_tap(self, xb, pins, side, alias, label_at="top"):
        """Vertical bus segment at x = xb with one entry per pin (x_pin, y) and a local label per entry wire.
        side = +1: pins right of the bus; -1: pins left. pins: [(name, x_pin, y)]. Bus label {alias} at the top or bottom."""
        ys = [y for _, _, y in pins]
        top, bot = R2(min(ys)), R2(max(ys) + 2.54)
        for name, xp, y in pins:
            self.bus_entry(xb, R2(y + 2.54), R2(2.54 * side), -2.54)
            xe = R2(xb + 2.54 * side)
            self.wire((xe, y), (xp, y)); self.label("L", name, xe, y, 0 if side > 0 else 180)
        if label_at == "top":
            self.bus((xb, R2(top - 2.54)), (xb, bot)); self.label("L", "{" + alias + "}", xb, R2(top - 2.54), 180 if side > 0 else 0)
        else:
            self.bus((xb, top), (xb, R2(bot + 2.54))); self.label("L", "{" + alias + "}", xb, R2(bot + 2.54), 0 if side < 0 else 180)

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
        # bus aliases go to the .kicad_pro (KiCad 10 stores them there and drops them from the .kicad_sch)
        t += junc + "".join(self.items)
        t += '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n'
        if self.u == ROOT_UUID: t += '\t(embedded_fonts no)\n'   # KiCad writes this on the root file only
        t += ')\n'
        assert t.count("(") == t.count(")"), self.title
        return t

RLY_FP = "Relay_THT:Relay_SPDT_Schrack-RT1-16A-FormC_RM5mm"
RLY_V, RLY_D = "RTD14012F", "TE RT1, 1 CO 16 A, 12 VDC 400 mW, wash-tight, 5 mm pinning"
SO239_FP = "rf-board:SO239_83-798_StrapPad_BossRight"   # project footprint (gen_so239_fp.py, D-105): GND boss hole at +14 mm
SO239_FP_L = "rf-board:SO239_83-798_StrapPad_BossLeft"   # A4, near the right board edge: GND boss hole at -14 mm
SO239_D = "Amphenol RF 83-798 (SO-239/A, PTFE) in the case wall; strap to board pad"
H = lambda n: ("H", n)

SHEETS = [("power", "Power entry", "power.kicad_sch", None), ("j14", "J14 filter", "j14_filter.kicad_sch", None)] + \
         [(f"r{i}", f"Radio port R{i}", "radio_port.kicad_sch", i) for i in (1, 2, 3)] + \
         [(f"a{k}", f"Antenna port A{k}", "antenna_port.kicad_sch", k) for k in (1, 2, 3, 4)] + \
         [("det", "RF detect", "rf_detect.kicad_sch", None), ("io", "IO expanders", "io_expanders.kicad_sch", None),
          ("bias", "Bias-T supply", "bias_supply.kicad_sch", None)]
SUUID = {s[0]: str(uuid.uuid5(NS, "sheet/" + s[0])) for s in SHEETS}
PATH = {s[0]: f"/{ROOT_UUID}/{SUUID[s[0]]}" for s in SHEETS}

# ---------- coil driver channel (D-34 to D-37) ----------
SOT23, SOD123 = "Package_TO_SOT_SMD:SOT-23", "Diode_SMD:D_SOD-123"
R0603 = "Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder"
C0603 = "Capacitor_SMD:C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"
C0805 = "Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"
QN_D = "Coil driver, N-MOSFET 60 V, RDS(on) specified at VGS 2.5 V. Second source Diotec MMFTN138K (same limits and pin-out, D-134)"
TP_FP = "TestPoint:TestPoint_Pad_D1.5mm"
RPACK_FP = "Resistor_SMD:R_Array_Convex_4x0603"
RPACK_D = ("10k x4 array, convex 4x0603 (1206 body), 62.5 mW per element. Bourns CAT16-103J4LF; "
           "second source Yageo YC164-JR-0710KL (D-121, to confirm on DigiKey)")
def coil_driver(S, a, k, net_in, clamp, h=20.32, side=-1, dnp=False):
    """Low-side driver under coil pin A2 at a: N-MOSFET, gate pull-down, clamp diode to the shared clamp net.
    side -1: parts to the left of the coil wire, +1: to the right. k: reference number (same as the relay),
    or a tuple (q, d, r) where the sheet already uses that number."""
    kq, kd, kr = k if isinstance(k, tuple) else (k, k, k)
    ax, ay = a
    M, N = (ax, R2(ay + h - 5.08)), (ax, R2(ay + h))
    gy = R2(ay + h + 5.08)
    S.wire(a, M); S.wire(M, N)
    Q = S.part("Transistor_FET:Q_NMOS_GSD", ("Q", kq), "BSS138BK", SOT23, R2(ax + side * 2.54), gy, desc=QN_D, mpn="BSS138BK,215", dnp=dnp,
               mirror=None if side < 0 else "y", rp=(side * 2.54, -6.35, "right"))   # mirror flips the justification
    assert Q["3"] == N, (Q, N)
    S.power("GND", Q["2"])
    dx = R2(ax + side * 10.16)
    S.wire(M, (dx, M[1]))
    D = S.part("Device:D", ("D", kd), "1N4148W", SOD123, dx, R2(M[1] - 3.81), rot=270, mpn="1N4148W", dnp=dnp,
               desc="Coil clamp diode to the shared clamp net (D-35, D-36). BAS16 class also fits",
               rp=(side * 1.27, -1.27, "right" if side < 0 else "left"))
    assert D["2"] == (dx, M[1]), D
    S.power(clamp, D["1"])
    T, L = (R2(ax + side * 12.7), gy), (R2(ax + side * 20.32), gy)
    S.wire(Q["1"], T); S.wire(T, L)
    R = S.part("Device:R", ("R", kr), "100k", R0603, T[0], R2(gy + 3.81), dnp=dnp, desc="Gate pull-down: coil off while the expander is in reset")
    assert R["1"] == T, R
    S.power("GND", R["2"])
    S.label("H", net_in, L[0], L[1], 180 if side < 0 else 0)

# ---------- radio port sheet (R1..R3, reference block 100 x n) ----------
def radio_sheet():
    S = Sheet("Unit RF board: radio port (K0, TX/RX rows, EXP, drivers)", "A3", [(PATH[f"r{i}"], 100 * i) for i in (1, 2, 3)])
    XS, YTX, YRX = [101.6 + j * 50.8 for j in range(5)], 63.5, 139.7
    BUS = {"TX": R2(YTX + 48.26), "RX": R2(YRX + 48.26)}             # row bus below the coil drivers
    # K0 below the RX bus: NO to the TX bus along the left edge, NC up to the RX bus, COM from the radio below
    K0 = S.part(RLY, ("K", 1), RLY_V, RLY_FP, 66.04, 205.74, {},        # mirrored: NO left, NC right, no crossing
                "K0 TX/RX changeover: off = RX row (fail-safe), on = TX row. " + RLY_D, mpn=RLY_V, mirror="y",
                rp=(11.43, -1.27, "right"))                  # mirror flips the justification
    S.power("+12V_RLY", K0["A1"])
    coil_driver(S, K0["A2"], 1, "K0_DRV", "CLAMP_RLY", side=+1)
    S.label("H", "RADIO", 30.48, 218.44, 180)               # radio SO-239 on the root sheet
    S.power("+12V_SW", (30.48, 60.96))                      # coil rail decoupling, one per radio block (D-127)
    CR = S.part("Device:C", ("C", 1), "1u 50V X7R", C0805, 30.48, 64.77, desc="+12V_SW decoupling at the radio block, X7R 50 V (D-127)")
    assert CR["1"] == (30.48, 60.96), CR
    S.power("GND", CR["2"])
    S.wire((30.48, 218.44), (K0["11"][0], 218.44), K0["11"])
    S.wire(K0["14"], (K0["14"][0], 193.04), (50.8, 193.04), (50.8, BUS["TX"]))
    S.wire(K0["12"], (K0["12"][0], BUS["RX"]))
    cols = ["1", "2", "3", "4", "E"]
    exp_pts = {}
    for row, y, k0 in (("TX", YTX, 2), ("RX", YRX, 7)):
        ybus, coms = BUS[row], []
        for j, c in enumerate(cols):
            x = XS[j]
            net = "EXP" if c == "E" else f"ANT{c}"
            nf = row == "TX" and c in RX_ONLY                 # receive-only column: no TX relay, no driver (D-103)
            K = S.part(RLY, ("K", k0 + j), RLY_V, RLY_FP, x, y, {"12": "NC"},
                       f"{row} row, position {c}: COM = row, NO = {net}, NC open. " + RLY_D
                       + (" Not fitted: A" + c + " is receive-only (D-103, SR-01)." if nf else ""), mpn=RLY_V, dnp=nf)
            S.power("+12V_SW", K["A1"])
            coil_driver(S, K["A2"], k0 + j, f"{row}{c}_DRV", "CLAMP_SW", dnp=nf)
            S.wire(K["11"], (x + 5.08, ybus)); coms.append(x + 5.08)
            if c == "E": exp_pts[row] = K["14"]
            else:
                S.wire(K["14"], (x + 7.62, y - 12.7)); S.label("H", net, x + 7.62, y - 12.7, 90)
        xs = [50.8 if row == "TX" else K0["12"][0]] + coms
        for a, b in zip(xs, xs[1:]): S.wire((a, ybus), (b, ybus))
        S.label("L", f"{row}BUS", coms[0] + 1.27, ybus)       # free gap between the first two relays
    # EXP: both 5th positions to the SMA
    XE, YE = 327.66, 91.44
    S.wire(exp_pts["TX"], (exp_pts["TX"][0], YTX - 12.7), (XE, YTX - 12.7), (XE, YE))
    S.wire(exp_pts["RX"], (exp_pts["RX"][0], YRX - 12.7), (XE, YRX - 12.7), (XE, YE))
    S.wire((XE, YE), (342.9, YE)); S.label("H", "EXP", 342.9, YE, 0)   # EXP SMA on the root sheet
    S.text("Radio port (one sheet, used for R1, R2, R3; references 1xx, 2xx, 3xx). Connectors: root sheet.\\n"
           "K0: coil off = radio on the RX row (fail-safe), coil on = TX row. K0 coil on +12V_RLY (not switched\\n"
           "by RLY_EN). R1: K0 from PTT in hardware (R51 on the controller); R2, R3: K0 from U903 IO1_3, IO1_4 after the handshake (D-63).\\n"
           "Row relays: COM on the row bus (L1), NO on the column (L2), NC open. Coils on +12V_SW (switched by RLY_EN).\\n"
           "Coil drivers: BSS138BK per coil, 100k gate pull-down, 1N4148W to CLAMP_SW (rows) or CLAMP_RLY (K0);\\n"
           "one 24 V zener per clamp net on the power sheet. Qn, Dn, Rn belong to relay Kn. *_DRV are 3.3 V logic inputs.\\n"
           "EXP: the 5th position of both rows joins on one SMA per radio. The EXP relay is the series disconnect.\\n"
           "SR-01 (D-103): on a receive-only column (unit 1: A2) the TX relay and its driver are not fitted, in all three radios.\\n"
           "No contact exists between a TX row and that column. The firmware keeps a column table (TX or RX only).\\n"
           "Rules (firmware and interlock): max one relay closed per row; TX row never on an RX-only column;\\n"
           "nothing moves while PTT or RF_DET is active; break before make. Unit 2 build option: not drawn yet.", 25.4, 256.54)
    S.section(63.5, 41.91, 335.28, 116.84, "TX row: 5 relays with coil drivers")
    S.section(63.5, 119.38, 335.28, 190.5, "RX row: 5 relays with coil drivers")
    S.section(20.32, 191.77, 104.14, 254.0, "K0 changeover")
    S.section(20.32, 49.53, 55.88, 80.01, "Decoupling")
    return S.finish()

# ---------- antenna port sheet (A1..A4, reference block 100 x (3 + k)) ----------
def antenna_sheet():
    S = Sheet("Unit RF board: antenna port (K1, driver, detector, bias-T)", "A4",
              [(PATH[f"a{k}"], 100 * (3 + k)) for k in (1, 2, 3, 4)])
    Y = 55.88                                                # column / PORT line
    S.label("H", "ANT", 30.48, Y, 180)
    S.wire((30.48, Y), (40.64, Y), (50.8, Y))
    # detector: capacitive tap on the column side, BAS70-04 voltage doubler (D-47, D-48), DET to the comparator sheet
    C4 = S.part("Device:C", ("C", 4), "4.7p 1kV C0G", "Capacitor_SMD:C_1812_4532Metric_Pad1.57x3.40mm_HandSolder", 40.64, 66.04,
                rp=(-2.54, -1.27, "right"), desc="Detector tap, series. 1 kV C0G: about 160 V peak across it at 100 W, SWR 3 (0.16). Spacing per the RF gap rule")
    C5 = S.part("Device:C", ("C", 5), "47p 50V C0G", C0603, 40.64, 77.47, rp=(-2.54, -1.27, "right"), desc="Detector tap, shunt: ratio about 1:12 with C4")
    S.wire((40.64, Y), C4["1"]); S.wire(C4["2"], (40.64, 71.12), C5["1"]); S.power("GND", C5["2"])
    D1 = S.part("rf-board:BAS70-04", ("D", 1), "BAS70-04", SOT23, 55.88, 76.2, mirror="x", mpn="BAS70-04", rp=(-3.81, 6.35),
                desc="Detector, Schottky pair in series 70 V SOT-23 (1 A1, 2 K2, 3 K1/A2), voltage doubler. The lower diode clamps negative transients and is the DC return")
    assert D1["3"] == (55.88, 71.12) and D1["1"] == (48.26, 76.2) and D1["2"] == (63.5, 76.2), D1
    S.wire((40.64, 71.12), D1["3"]); S.wire(D1["1"], (48.26, 81.28)); S.power("GND", (48.26, 81.28))
    C3 = S.part("Device:C", ("C", 3), "10n 50V X7R", C0603, 68.58, 80.01, desc="Detector hold: about 1 ms with R5 + R4")
    R5 = S.part("Device:R", ("R", 5), "47k", R0603, 86.36, 80.01, desc="Detector load, top of the divide-by-2 (DET max about 31 V)")
    R4 = S.part("Device:R", ("R", 4), "47k", R0603, 86.36, 87.63, desc="Detector load, bottom: the comparator sees DET / 2")
    S.wire(D1["2"], (68.58, 76.2), R5["1"]); S.power("GND", C3["2"])
    S.wire(R5["2"], (93.98, 83.82)); S.label("H", "DET", 93.98, 83.82, 0); S.power("GND", R4["2"])
    # 0 ohm link or DC block
    R2 = S.part("Device:R", ("R", 2), "0R wire link", "rf-board:WireLink_P7.62mm_D1.0mm", 60.96, Y, desc="Column link, fitted when no bias-T: tinned copper wire about 0.8 mm, 2.45 A rms (D-109)",
                rot=90, rp=(-6.35, -5.08))
    C1 = S.part("Device:C", ("C", 1), "DNP DC block", "Capacitor_SMD:C_1812_4532Metric_Pad1.57x3.40mm_HandSolder", 60.96, 45.72, dnp=True, rot=90, rp=(-2.54, -8.89),
                desc="DC block, fitted only on a bias-T port (RX-only). Value and part to decide")
    S.wire((50.8, Y), R2["1"]); S.wire(R2["2"], (71.12, Y))
    S.wire((50.8, Y), (50.8, 45.72), C1["1"]); S.wire(C1["2"], (71.12, 45.72), (71.12, Y))
    # PORT to K1 NO, with the bias-T feed on the matrix side of K1
    K1 = S.part(RLY, ("K", 1), RLY_V, RLY_FP, 152.4, 76.2, {},
                "K1: off = antenna parked to GND via bleed (fail-safe), on = antenna on the column. " + RLY_D, mpn=RLY_V)
    S.wire((71.12, Y), (99.06, Y), (160.02, Y), K1["14"]); S.label("L", "PORT", 81.28, Y)
    L2 = S.part("Device:L", ("L", 2), "DNP bias choke", "Inductor_SMD:L_1812_4532Metric_Pad1.30x3.40mm_HandSolder", 99.06, 45.72, dnp=True, rp=(-1.27, -1.27, "right"), desc="Bias-T feed on the matrix side of K1. Value to decide")
    C2 = S.part("Device:C", ("C", 2), "DNP 100n", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", 111.76, 41.91,
                dnp=True, rp=(3.81, -1.27), desc="Bias feed decoupling")
    S.wire(L2["2"], (99.06, Y)); S.wire(L2["1"], (99.06, 35.56), (111.76, 35.56), (119.38, 35.56)); S.label("H", "BIAS", 119.38, 35.56, 0)
    S.wire((111.76, 35.56), C2["1"]); S.power("GND", C2["2"])
    S.power("+12V_SW", K1["A1"])
    coil_driver(S, K1["A2"], (1, 2, 6), "K1_DRV", "CLAMP_SW", h=27.94, side=+1)    # below the COM wire, right of the coil
    # PARK: K1 NC to the bleed and the choke
    R1 = S.part("Device:R", ("R", 1), "1M HV", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", 132.08, 96.52,
                desc="Static bleed, parked antenna. High-voltage type (about 950 V impulse before the CS-400R fires), e.g. Vishay VR25: to confirm")
    S.wire(K1["12"], (154.94, 58.42), (132.08, 58.42), R1["1"]); S.label("L", "PARK", 137.16, 58.42)
    S.power("GND", R1["2"])
    # ANTENNA: K1 COM to the SO-239 (no GDT on the board, D-114)
    S.wire(K1["11"], (157.48, 88.9), (205.74, 88.9)); S.label("H", "ANTENNA", 205.74, 88.9, 0)   # SO-239 on the root
    S.text("Antenna port (one sheet, used for A1 to A4; references 4xx to 7xx). SO-239: root sheet.\\n"
           "K1: coil off = antenna parked (COM to NC, 1M bleed to GND), coil on = antenna on the column.\\n"
           "No RF choke on the bleed: a low-impedance path would take surge current through K1 and the board.\\n"
           "Surge: Comet CS-400R at the RVS box entry. No GDT on the board (D-114).\\n"
           "Bias-T option (A2 RX loop): fit C1 and L2, C2, remove R2. The feed sits on the matrix side of K1,\\n"
           "so the bias supply is open, not loaded, while K1 is parked.\\n"
           "Detector: capacitive tap C4/C5 (about 1:12), BAS70-04 doubler D1 (clamps negative pulses), hold C3, R5/R4 divide by 2.\\n"
           "K1 driver: Q1 BSS138BK, R6 100k gate pull-down, D2 1N4148W to CLAMP_SW. Values marked TBD are set with the part choices (design-log.md).", 25.4, 139.7)
    S.section(20.32, 30.48, 125.73, 60.96, "Column link and bias-T option")
    S.section(20.32, 62.23, 101.6, 101.6, "Detector")
    S.section(127.0, 50.8, 220.98, 134.62, "K1 antenna relay, bleed and driver")
    return S.finish()

# ---------- power sheet ----------
def power_sheet():
    S = Sheet("Unit RF board: power, coil supply, 3V3 and chassis bond", "A3", [(PATH["power"], 0)], pwr_base=[1400])
    coil_supply(S); logic_3v3(S); input_protection(S)
    return power_chassis(S)

PWR = [("+12V_RLY", "XT60PW-M", "Connector_AMASS:AMASS_XT60PW-M_1x02_P7.20mm_Horizontal", "Amass XT60PW-M, relay rail"),
           ("+12V_AUX", "XT60PW-M", "Connector_AMASS:AMASS_XT60PW-M_1x02_P7.20mm_Horizontal", "Amass XT60PW-M, clean 12 V (bias-T, preamp)"),
           ("+5V", "XT30PW-M", "Connector_AMASS:AMASS_XT30PW-M_1x02_P2.50mm_Horizontal", "Amass XT30PW-M, logic rail")]
def coil_supply(S):
    """+12V_SW high-side switch (D-38 to D-40), freewheel diode (D-36), clamp zeners (D-35, D-37), Q1 gate zener (D-45)."""
    X = 10.16                                                # Q1 and the +12V_SW line, right of the gate parts
    S.power("+12V_RLY", (81.28, 48.26))
    S.wire((81.28, 48.26), (93.98, 48.26), (101.6, 48.26), (104.14 + X, 48.26))
    Q1 = S.part("Transistor_FET:Q_PMOS_GSD", ("Q", 1), "PMV50EPEA", SOT23, 101.6 + X, 60.96, mirror="x", mpn="PMV50EPEA",
                desc="+12V_SW high-side switch, P-MOSFET -30 V, VGS +-20 V. Second source AOS AO3407A (D-40)", rp=(5.08, -1.27))
    assert Q1["2"] == (104.14 + X, 55.88) and Q1["3"] == (104.14 + X, 66.04), Q1
    S.wire((104.14 + X, 48.26), Q1["2"])
    R1 = S.part("Device:R", ("R", 1), "10k", R0603, 93.98, 54.61, desc="Q1 gate-source: holds +12V_SW off (D-38)")
    S.wire((93.98, 48.26), R1["1"]); S.wire(R1["2"], (93.98, 60.96))
    Z5 = S.part("Device:D_Zener", ("D", 6), "BZT52C15", SOD123, 101.6, 54.61, rot=270, mpn="BZT52C15",
                desc="Q1 gate-source clamp, 15 V: limits VGS when the SMBJ15A clamps a transient at about 24 V (D-45)")
    S.wire((101.6, 48.26), Z5["1"]); S.wire(Z5["2"], (101.6, 60.96))
    S.wire(Q1["1"], (101.6, 60.96), (93.98, 60.96), (91.44, 60.96), (81.28, 60.96))
    C2 = S.part("Device:C", ("C", 2), "DNP", C0603, 91.44, 64.77, dnp=True, rp=(-2.54, -1.27, "right"),
                desc="Q1 drain-gate soft start, footprint only, not fitted (D-38, onsemi AND9093)")
    assert C2["1"] == (91.44, 60.96); S.wire(C2["2"], (91.44, 71.12), (104.14 + X, 71.12))
    R2_ = S.part("Device:R", ("R", 2), "2k2", R0603, 81.28, 67.31, rp=(-1.27, -1.27, "right"),
                 desc="Q1 gate series: VGS about 10.3 V at 12.6 V with R1 (D-38); limits the D6 current")
    S.wire((81.28, 60.96), R2_["1"])
    Q2 = S.part("Transistor_FET:Q_NMOS_GSD", ("Q", 2), "BSS138BK", SOT23, 78.74, 78.74, mpn="BSS138BK,215", desc="Q1 gate driver. " + QN_D)
    S.wire(R2_["2"], Q2["3"]); S.power("GND", Q2["2"])
    S.wire(Q2["1"], (71.12, 78.74), (60.96, 78.74)); S.label("H", "RLY_EN", 60.96, 78.74, 180)
    R3 = S.part("Device:R", ("R", 3), "100k", R0603, 71.12, 82.55, desc="RLY_EN pull-down: no signal = relays off (D-39)")
    S.power("GND", R3["2"])
    S.wire(Q1["3"], (104.14 + X, 71.12), (116.84 + X, 71.12), (129.54 + X, 71.12), (144.78 + X, 71.12), (152.4 + X, 71.12), (165.1 + X, 71.12))
    D1 = S.part("Device:D_Schottky", ("D", 1), "SS14", "Diode_SMD:D_SMA", 116.84 + X, 74.93, rot=270, mpn="SS14",
                desc="+12V_SW freewheel, 1 A 40 V Schottky (D-36)")
    S.power("GND", D1["2"])
    S.power("+12V_SW", (152.4 + X, 71.12)); S.power("+12V_SW", (165.1 + X, 71.12), flag=True)
    S.wire((165.1 + X, 71.12), (172.72 + X, 71.12))
    S.part("Connector:TestPoint", ("TP", 4), "+12V_SW", TP_FP, 172.72 + X, 71.12, desc="Test point +12V_SW (D-120)", bom=False, rp=(1.27, -5.08))
    Z_D = "Clamp zener, 24 V, SOD-123 (D-35, D-37): drain peak 12.6 + 24 + 0.9 = 37.5 V against 0.7 x 60 V. Part to confirm"
    ZL = (-1.27, -1.27, "right")                             # text left of the zener
    # CLAMP_SW: two zeners in parallel, so one open zener does not remove the clamp of 34 coils
    Z1 = S.part("Device:D_Zener", ("D", 2), "BZT52C24", SOD123, 129.54 + X, 67.31, rot=270, mpn="BZT52C24", rp=ZL, desc=Z_D + ". Row and K1 coils")
    Z3 = S.part("Device:D_Zener", ("D", 4), "BZT52C24", SOD123, 144.78 + X, 67.31, rot=270, mpn="BZT52C24", rp=ZL, desc=Z_D + ". Parallel to D2")
    S.wire(Z1["1"], (129.54 + X, 60.96), (144.78 + X, 60.96), Z3["1"])
    S.power("CLAMP_SW", (129.54 + X, 60.96)); S.power("CLAMP_SW", (144.78 + X, 60.96), flag=True)
    # CLAMP_RLY: same for the three K0 coils
    Z2 = S.part("Device:D_Zener", ("D", 3), "BZT52C24", SOD123, 40.64, 101.6, rot=270, mpn="BZT52C24", rp=ZL, desc=Z_D + ". K0 coils")
    Z4 = S.part("Device:D_Zener", ("D", 5), "BZT52C24", SOD123, 55.88, 101.6, rot=270, mpn="BZT52C24", rp=ZL, desc=Z_D + ". Parallel to D3")
    S.wire(Z2["1"], (40.64, 93.98), (55.88, 93.98), Z4["1"])
    S.power("CLAMP_RLY", (40.64, 93.98)); S.power("CLAMP_RLY", (55.88, 93.98), flag=True)
    S.wire(Z2["2"], (40.64, 109.22), (55.88, 109.22), (63.5, 109.22)); S.wire(Z4["2"], (55.88, 109.22))
    S.power("+12V_RLY", (63.5, 109.22))

FUSE_FP = "Fuse:Fuse_1206_3216Metric_Pad1.42x1.75mm_HandSolder"
INPUTS = [("+12V_RLY", "SMBJ15A"), ("+12V_AUX", "SMBJ15A"), ("+5V", "SMBJ6.0A")]
def input_protection(S):
    """Per XT input: time-lag fuse, then a unidirectional TVS (also the reverse-polarity crowbar), D-45."""
    for n, (net, tvs) in enumerate(INPUTS):
        y = R2(96.52 + n * 17.78)
        S.label("H", f"{net}_IN", 220.98, y, 180)
        F = S.part("Device:Fuse", ("F", 1 + n), "1A T", FUSE_FP, 231.14, y, rot=90, mpn="0468001.NR", rp=(-3.81, -5.08),
                   desc="1 A time-lag 1206, 63 V, 50 A breaking. Littelfuse 0468001.NR; second source Bourns SF-1206S100-2 (D-45)")
        S.wire((220.98, y), F["1"]); S.wire(F["2"], (243.84, y), (254.0, y), (264.16, y), (269.24, y), (279.4, y))
        if n < 2:                                            # bulk at each 12 V entry (D-129)
            CB = S.part("Device:C_Polarized", ("C", 6 + n), "47u 25V polymer", "Capacitor_SMD:CP_Elec_6.3x7.7", 264.16, R2(y + 3.81),
                        desc="Bulk at the 12 V entry: 47 uF 25 V aluminium polymer, 6.3 mm SMD (12.6 / 25 = 0.50). Part and second source to confirm (D-129)")
            assert CB["1"] == (264.16, y), CB
            S.power("GND", CB["2"], rp=(1.27, 1.27))
        S.part("Connector:TestPoint", ("TP", 1 + n), net, TP_FP, 279.4, y, desc=f"Test point {net} (D-120)", bom=False, rp=(1.27, -5.08))
        T = S.part("Device:D_Zener", ("D", 7 + n), tvs, "Diode_SMD:D_SMB", 243.84, R2(y + 3.81), rot=270, mpn=tvs,
                   desc="Unidirectional TVS 600 W, SMB. Clamps transients; forward-biased on reverse polarity so the fuse opens (D-45)")
        assert T["1"] == (243.84, y), T
        S.power("GND", T["2"])
        S.power(net, (254.0, y)); S.power(net, (269.24, y), flag=True)

def logic_3v3(S):
    """3.3 V logic LDO (D-41): LP2985-33, second source ST LD2985BM33R."""
    U1 = S.part("rf-board:LP2985-3.3", ("U", 1), "LP2985-33", "Package_TO_SOT_SMD:SOT-23-5", 101.6, 121.92, mpn="LP2985-33DBVR",
                desc="3.3 V LDO, 150 mA, VIN max 16 V. Second source ST LD2985BM33R. ON/OFF tied to VIN", rp=(-7.62, -8.89))
    S.power("+5V", (78.74, 119.38))
    S.wire((78.74, 119.38), (83.82, 119.38), (88.9, 119.38), U1["1"])
    S.wire((88.9, 119.38), (88.9, 121.92), U1["3"])
    C3 = S.part("Device:C", ("C", 3), "1u 16V X7R", C0603, 83.82, 123.19, rp=(-2.54, -1.27, "right"), desc="LDO input, required by LD2985")
    assert C3["1"] == (83.82, 119.38); S.power("GND", C3["2"])
    S.power("GND", U1["2"])
    S.wire(U1["4"], (116.84, 121.92))
    C4 = S.part("Device:C", ("C", 4), "10n 50V X7R", C0603, 116.84, 125.73, desc="LDO noise bypass (one 10 nF line on all boards, D-190)")
    S.power("GND", C4["2"])
    S.wire(U1["5"], (124.46, 119.38), (129.54, 119.38))
    R4 = S.part("Device:R", ("R", 4), "0R", "Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", 133.35, 119.38, rot=90, rp=(-2.54, -5.08),
                desc="+3V3 current-measurement link: lift to measure the 3.3 V load (D-120)")
    assert R4["1"] == (129.54, 119.38), R4
    S.wire(R4["2"], (142.24, 119.38), (149.86, 119.38), (157.48, 119.38))
    S.power("+3V3", (149.86, 119.38), flag=True)             # the LDO output pin drives +3V3 through R4
    S.part("Connector:TestPoint", ("TP", 5), "+3V3", TP_FP, 157.48, 119.38, desc="Test point +3V3 (D-120)", bom=False, rp=(1.27, -5.08))
    C5 = S.part("Device:C", ("C", 5), "4.7u 16V X7R", C0805, 124.46, 123.19,
                desc="LDO output: at least 2.2 uF effective at 3.3 V and temperature (legacy LP2985 die, LD2985). DC-bias curve to confirm")
    assert C5["1"] == (124.46, 119.38); S.power("GND", C5["2"])
    S.power("+3V3", (142.24, 119.38))

def power_chassis(S):
    X = 71.12                                                # chassis bond block, right of the supplies
    H1 = S.part("Mechanical:MountingHole_Pad", ("H", 1), "M3 CHASSIS", "MountingHole:MountingHole_3.2mm_M3_Pad", 139.7 + X, 45.72,
                desc="Plated M3 hole, the only chassis bond point", bom=False, rp=(2.54, -3.81))
    JP1 = S.part("Jumper:SolderJumper_2_Open", ("JP", 1), "open", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", 154.94 + X, 55.88,
                 desc="CHASSIS to GND, DC bond, open by default", bom=False, rp=(-3.81, -5.08))
    C1 = S.part("Device:C", ("C", 1), "DNP 10nF 1kV", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", 143.51 + X, 66.04,
                desc="CHASSIS to GND, RF-only bond, not fitted", dnp=True)
    S.wire(H1["1"], (139.7 + X, 55.88), (143.51 + X, 55.88), JP1["1"]); S.label("L", "CHASSIS", 139.7 + X, 55.88, 180)
    S.wire((143.51 + X, 55.88), C1["1"]); S.power("GND", C1["2"])
    S.wire(JP1["2"], (170.18 + X, 55.88), (170.18 + X, 60.96)); S.power("GND", (170.18 + X, 60.96))
    # board supports S1 to S6 (D-102): plated M3 holes on the standoffs, each with one bond option footprint to GND (D-132). Each support
    # has its own net CHASSIS_Sn with only its bond option (D-162): no board copper joins the supports to each other or to H1
    for i in range(6):
        x, y0 = R2(302.26 + i * 15.24), 50.8
        HS = S.part("Mechanical:MountingHole_Pad", ("S", 1 + i), "M3", "MountingHole:MountingHole_3.2mm_M3_Pad", x, y0, bom=False, rp=(2.54, -3.81),
                    desc=f"Board support S{1 + i}: plated M3 hole on the standoff to the case floor (case potential when screwed). Own net CHASSIS_S{1 + i} (D-162). Position in case.md (D-102, D-132)")
        assert HS["1"] == (x, R2(y0 + 2.54)), HS
        CBD = S.part("Device:C", ("C", 8 + i), "DNP bond", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", x, R2(y0 + 10.16), dnp=True,
                     rp=(2.54, -1.27), desc=f"Bond option at support S{1 + i} (Armstrong, D-132): fit 0R (DC bond), 10 nF 1 kV (RF bond) or a resistor "
                                            "(cavity damping) after the bench test. Not fitted: the support floats as before (D-102)")
        S.wire(HS["1"], CBD["1"]); S.label("L", f"CHASSIS_S{1 + i}", x, R2(y0 + 2.54), 0)
        S.power("GND", CBD["2"])
    S.text("Power: the XT connectors sit on the root sheet. Each input: 1 A time-lag fuse, then a TVS to GND (D-45).\\n"
           "The TVS clamps transients and conducts on reverse polarity, so the fuse opens. D6 limits Q1 VGS to 15 V.\\n"
           "+12V_RLY: 12 V +-5 % (RT1 coil range 10.2 to 13.2 V). +12V_SW: +12V_RLY switched by Q1 when RLY_EN is high.\\n"
           "RLY_EN is active-high with R3 pull-down: no signal = relays off (D-39). C2 not fitted (soft start option).\\n"
           "Clamp nets: each coil diode goes to CLAMP_SW (rows, K1) or CLAMP_RLY (K0). Zeners D2 // D4 and D3 // D5 (24 V) return\\n"
           "the coil energy to the rail: drain peak about 37.5 V. Two in parallel: one open zener does not remove the clamp.\\n"
           "+3V3: U1 LP2985-33 from +5V, for the expanders and the I2C bus. R4 0R: lift to measure the 3.3 V load (D-120).\\n"
           "Bulk C6, C7 47 uF polymer at the 12 V entries (D-129). Test points TP1 to TP5 on every rail; the fuses F1 to F3\\n"
           "serve as the current links of the input rails (D-120).\\n"
           "Mounting holes not grounded; H1 is the only bond (JP1 open, C1 not fitted). The case bonds to the RVS earth bar at one point only.\\n"
           "Supports S1 to S6: plated, at case potential through the standoffs; each on its own net CHASSIS_Sn, joined to nothing\n"
           "else on the board. C8 to C13 are local bond options to GND, not fitted (D-132, D-162).",
           25.4, 149.86)
    S.section(27.94, 38.1, 196.85, 110.49, "Coil supply switch and clamps")
    S.section(198.12, 38.1, 250.19, 78.74, "Chassis bond")
    S.section(203.2, 86.36, 292.1, 147.32, "Input protection")
    S.section(50.8, 111.76, 167.64, 139.7, "3.3 V supply")
    S.section(297.18, 38.1, 393.7, 76.2, "Board supports")
    return S.finish()

# ---------- RF detect sheet: one LM2901 for the four antenna ports (D-47) ----------
def rf_detect_sheet():
    S = Sheet("Unit RF board: RF detect comparators (LM2901)", "A4", [(PATH["det"], 800)], pwr_base=[980])       # references 8xx
    BX = 58.42                                               # VREF bus
    S.power("+3V3", (BX, 27.94))
    RA = S.part("Device:R", ("R", 1), "10k", R0603, BX, 31.75, desc="VREF divider, top: 0.3 V threshold with R2")
    S.wire(RA["2"], (BX, 38.1)); S.wire((BX, 38.1), (50.8, 38.1), (43.18, 38.1))
    RB = S.part("Device:R", ("R", 2), "1k", R0603, 50.8, 41.91, rp=(1.27, -1.27), desc="VREF divider, bottom")
    S.power("GND", RB["2"])
    CV = S.part("Device:C", ("C", 1), "100n 50V X7R", C0603, 43.18, 41.91, rp=(-2.54, -1.27, "right"), desc="VREF decoupling")
    S.power("GND", CV["2"])
    ys = [R2(50.8 + i * 30.48) for i in range(4)]
    taps = [(BX, 38.1)] + [(BX, R2(y - 2.54)) for y in ys]
    for p0, p1 in zip(taps, taps[1:]): S.wire(p0, p1)
    for i, y in enumerate(ys):
        k = i + 1
        U = S.part("Comparator:LM2901", ("U", 1), "LM2901", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", 127.0, y, unit=k, mpn="LM2901DR",
                   desc="Quad comparator, -40 to 125 C, inputs to 36 V, open collector (D-47). TI, ST, onsemi, Diodes", rp=(-5.08, 7.62))
        pin = {v: n for n, v in {n: (q[0], q[1]) for n, q in U.items()}.items()}
        inp, inm, out = (119.38, R2(y - 2.54)), (119.38, R2(y + 2.54)), (134.62, y)
        assert inp in pin and inm in pin and out in pin, U
        S.label("H", f"DET{k}", 76.2, R2(y + 2.54), 180); S.wire((76.2, R2(y + 2.54)), inm)          # DET to IN-: output low on RF
        RS = S.part("Device:R", ("R", 10 + k), "10k", R0603, 104.14, R2(y - 2.54), rot=90, rp=(-2.54, -5.08),
                    desc="Threshold series resistor: sets the hysteresis with the feedback resistor")
        S.wire((BX, R2(y - 2.54)), RS["1"] if RS["1"][0] < RS["2"][0] else RS["2"])
        rs_out = RS["2"] if RS["1"][0] < RS["2"][0] else RS["1"]
        S.wire(rs_out, (111.76, R2(y - 2.54)), inp)
        RF = S.part("Device:R", ("R", 20 + k), "1M", R0603, 123.19, R2(y - 7.62), rot=90, rp=(-2.54, -5.08),
                    desc="Hysteresis: about 3.3 V x 10k / 1M = 33 mV")
        l, r = sorted([RF["1"], RF["2"]])
        S.wire((111.76, R2(y - 2.54)), (111.76, R2(y - 7.62)), l); S.wire(r, (139.7, R2(y - 7.62)), (139.7, y))
        S.wire(out, (139.7, y), (147.32, y), (154.94, y)); S.label("H", f"RFDET{k}", 154.94, y, 0)
        RP = S.part("Device:R", ("R", 30 + k), "10k", R0603, 147.32, R2(y - 3.81), desc="Open-collector pull-up to 3.3 V")
        assert RP["2"] == (147.32, y), RP
        S.power("+3V3", RP["1"])
    UP = S.part("Comparator:LM2901", ("U", 1), "LM2901", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", 190.5, 60.96, unit=5, rp=(2.54, 2.54))
    S.wire(UP["3"], (187.96, 50.8), (198.12, 50.8), (198.12, 57.15))
    S.power("+5V", (187.96, 50.8))
    CD = S.part("Device:C", ("C", 2), "1u 16V X7R", C0603, 198.12, 60.96, desc="LM2901 supply decoupling: one value per IC (D-127)")
    S.wire(CD["2"], (198.12, 71.12), (187.96, 71.12)); S.wire(UP["12"], (187.96, 71.12)); S.power("GND", (187.96, 71.12))
    S.text("RF detect: one LM2901 for the four antenna ports (D-47). DETk from antenna port Ak (BAS70 peak detector).\\n"
           "Threshold VREF 0.3 V (R801/R802); DET above VREF pulls RFDETk low (active low, open collector, 10k pull-up to 3.3 V).\\n"
           "Hysteresis about 33 mV per channel (R81k 10k series, R82k 1M feedback). Supply +5V: common-mode range to VCC - 1.5 V;\\n"
           "inputs rated to 36 V, DET max about 15 V at 100 W SWR 3. Detects about 0.5 W (SWR 1) to 2.5 W (SWR 3, voltage minimum).\\n"
           "RFDET1 to RFDET4 go to the expander inputs. RFDET2 (A2, receive-only) also goes to J14 pin 17: the controller opens\\n"
           "the SAFE loop on RF at A2, so the shack inhibits all radios and the relays drop (D-104, SR-01 H2).", 25.4, 175.26)
    S.section(30.48, 19.05, 167.64, 156.21, "VREF and comparators")
    S.section(177.8, 41.91, 215.9, 81.28, "Supply")
    return S.finish()

# ---------- I/O expander sheet: 3 x PCA9539 (D-49, D-50) ----------
ROWS = [f"TX{c}" for c in "1234E"] + [f"RX{c}" for c in "1234E"]
EXP = [  # (address pins A1, A0), IO0_0 .. IO1_7 (16 names, "" = not used)
    ((0, 0), [f"R1_{r}_DRV" for r in ROWS] + ["A1_K1_DRV", "A2_K1_DRV", "A1_RFDET", "A2_RFDET", "", ""]),
    ((0, 1), [f"R2_{r}_DRV" for r in ROWS] + ["A3_K1_DRV", "A4_K1_DRV", "A3_RFDET", "A4_RFDET", "", ""]),
    ((1, 0), [f"R3_{r}_DRV" for r in ROWS] + ["R1_K0_DRV", "R2_K0_DRV", "R3_K0_DRV", "TX_ANY", "", ""]),   # R1 K0 and TX_ANY readback (PTT, D-53); IO1_3, IO1_4 drive R2, R3 K0 (outputs, D-63)
]
IO_NETS = [n for _, names in EXP for n in names if n]
def pulldowns(S, n, spare):
    """Spare expander pins held low by R_Pack04 arrays (D-121): four per pack, one GND rail right of the packs.
    spare: [(px, py)] top to bottom, 2.54 apart. Pack references RN(base + n), RN(base + n + 1), ..."""
    px = spare[0][0]
    x0, xr, rail = R2(px + 5.08), R2(px + 17.78), []
    for j in range(0, len(spare), 4):
        grp = spare[j:j + 4]
        used = len(grp)
        nc = {str(1 + i): "NC" for i in range(used, 4)}
        nc.update({str(8 - i): "NC" for i in range(used, 4)})
        P = S.part("Device:R_Pack04", ("RN", n + j // 4), "10k x4", RPACK_FP, R2(x0 + 5.08), R2(grp[0][1] + 5.08), nc, rot=270,
                   mpn="CAT16-103J4LF", desc=RPACK_D, rp=(15.24, -1.27))
        for i, (qx, qy) in enumerate(grp):
            l, r = P[str(1 + i)], P[str(8 - i)]
            assert l == (x0, qy) and r[1] == qy, (l, r, qy)
            S.wire((qx, qy), l); S.wire(r, (xr, qy)); rail.append(qy)
    for a, b in zip(rail, rail[1:]): S.wire((xr, a), (xr, b))
    S.wire((xr, rail[-1]), (xr, R2(rail[-1] + 2.54))); S.power("GND", (xr, R2(rail[-1] + 2.54)))

def expander(S, n, x, y, a1, a0, names, io_kind="H"):
    """PCA9539 with decoupling, bus pins (SCL, SDA, INT, RESET = RLY_EN) as hierarchical labels, address straps,
    and the 16 I/O pins as labels of kind io_kind ("" = no-connect). n: reference number on the sheet."""
    U = S.part("Interface_Expansion:PCA9539xD", ("U", n), "PCA9539", "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm", x, y, mpn="PCA9539PW,118",
               desc=f"16-bit I/O expander, address 0x{0x74 + 2 * a1 + a0:02X}. Plain PCA9539 only (PCA9539R resets only the I2C interface). "
                    "TSSOP-24, three makers with the same pin-out (D-133): NXP/Nexperia PCA9539PW,118, TI TCA9539PWR, Diodes PI4IOE5V9539LEX. No I/O pull-ups; RESET sets all I/O as inputs",
               rp=(2.54, 30.48))
    # VDD with decoupling, VSS
    S.wire(U["24"], (x, R2(y - 30.48)), (x, R2(y - 33.02))); S.power("+3V3", (x, R2(y - 33.02)))
    C = S.part("Device:C", ("C", n), "1u 16V X7R", C0603, R2(x + 7.62), R2(y - 30.48), rot=90, rp=(-2.54, -6.35),
               desc="PCA9539 decoupling at VDD: one value per IC, the largest in 0603 (D-127)")
    l, r = sorted([C["1"], C["2"]])
    S.wire((x, R2(y - 30.48)), l); S.wire(r, (R2(x + 15.24), R2(y - 30.48))); S.power("GND", (R2(x + 15.24), R2(y - 30.48)))
    S.power("GND", U["12"])
    # bus side: SCL, SDA, INT, RESET (= RLY_EN, D-50)
    for pin, net in (("22", "SCL"), ("23", "SDA"), ("1", "EXP_INT"), ("3", "RLY_EN")):
        px, py = U[pin]
        S.wire((px, py), (R2(px - 7.62), py)); S.label("H", net, R2(px - 7.62), py, 180)
    # address straps
    ax, ay = U["21"]                                     # A0
    if a0: S.wire((ax, ay), (R2(ax - 5.08), ay), (R2(ax - 5.08), R2(ay - 5.08))); S.power("+3V3", (R2(ax - 5.08), R2(ay - 5.08)))
    else:  S.wire((ax, ay), (R2(ax - 5.08), ay)); S.power("GND", (R2(ax - 5.08), ay))
    bx, by = U["2"]                                      # A1
    if a1:
        S.wire((bx, by), (R2(bx - 2.54), by), (R2(bx - 2.54), R2(by + 10.16)), (R2(bx - 12.7), R2(by + 10.16)))
        S.power("+3V3", (R2(bx - 12.7), R2(by + 10.16)))
    else:
        S.wire((bx, by), (R2(bx - 2.54), by), (R2(bx - 2.54), R2(by + 5.08))); S.power("GND", (R2(bx - 2.54), R2(by + 5.08)))
    # I/O side; spare pins to the pull-down arrays (D-121: they are inputs again after every reset)
    spare = []
    for i, net in enumerate(names):
        pin = str(4 + i) if i < 8 else str(13 + i - 8)
        px, py = U[pin]
        if not net: spare.append((px, py)); continue
        S.wire((px, py), (R2(px + 5.08), py)); S.label(io_kind, net, R2(px + 5.08), py, 0)
    if spare: pulldowns(S, n, spare)

def io_sheet():
    S = Sheet("Unit RF board: I/O expanders (3 x PCA9539)", "A3", [(PATH["io"], 900)], pwr_base=[1001])     # references 9xx
    for k, ((a1, a0), names) in enumerate(EXP):
        expander(S, 1 + k, R2(76.2 + k * 114.3), 101.6, a1, a0, names)
    S.text("I/O expanders (D-49, D-50): U901 0x74, U902 0x75, U903 0x76 (A1 A0 = 00, 01, 10); U1001 0x77 on the bias-T sheet (D-54).\\n"
           "Same addresses on unit 2,\\n"
           "which runs on its own I2C channel from the controller. Outputs drive the coil MOSFET gates (active high, 100k pull-downs\\n"
           "at each gate), so power-on, RESET and a lost bus leave every coil off. RESET = RLY_EN (active high, R3 pull-down on\\n"
           "the power sheet): no signal holds the expanders in reset and +12V_SW off. Documented exception: the datasheet asks\\n"
           "for a pull-up on RESET. Firmware: set RLY_EN high, then configure. Spare I/Os: 10k to GND in RN901 to RN903 (D-121).\\n"
           "EXP_INT (open drain) signals a change on the RFDET, R1_K0_DRV and TX_ANY (PTT readback, D-53) inputs.\\n"
           "U903 IO1_3 and IO1_4 are outputs: they drive R2 and R3 K0 after the TX handshake (D-63). In reset they float: the 100k gate pull-downs keep K0 off.\\n"
           "Bus pull-ups on this board, so unit 1 and unit 2 are the same (D-52): R901, R902 2.2k on SCL, SDA (bus about 100 pF max:\\n"
           "rise 0.85 x 2.2k x 100 pF = 0.19 us, Fast-mode limit 0.3 us; sink 1.5 mA, PCA9539 IOL min 3 mA). R903 10k on EXP_INT.\\n"
           "The controller board adds no pull-ups on this bus. Unit 2: J14 takes the EXP ribbon from the unit 1 controller board (D-53).\\n"
           "R904 100k pull-down on TX_ANY: defined low with J14 open (logic verification F4, D-61).", 25.4, 160.02)
    # bus pull-ups (D-52)
    for k, (net, val, why) in enumerate((("SCL", "2k2", "SCL pull-up to 3.3 V (D-52)"), ("SDA", "2k2", "SDA pull-up to 3.3 V (D-52)"),
                                         ("EXP_INT", "10k", "EXP_INT pull-up to 3.3 V, open-drain INT of U901 to U903 (D-52)"))):
        x = R2(25.4 + k * 10.16)
        R = S.part("Device:R", ("R", 1 + k), val, R0603, x, 38.1, desc=why)
        t, b = sorted([R["1"], R["2"]], key=lambda q: q[1])
        S.wire(t, (x, 30.48)); S.power("+3V3", (x, 30.48))
        S.wire(b, (x, 48.26)); S.label("H", net, x, 48.26, 270)
    # TX_ANY pull-down (logic verification F4): J14 open leaves U903 IO1_5 floating without it
    x = R2(25.4 + 3 * 10.16)
    R = S.part("Device:R", ("R", 4), "100k", R0603, x, 38.1, desc="TX_ANY pull-down: defined low with J14 open (unit 2 ribbon out), like R101 on the K0 drives")
    t, b = sorted([R["1"], R["2"]], key=lambda q: q[1])
    S.wire(t, (x, 30.48)); S.label("H", "TX_ANY", x, 30.48, 90)
    S.wire(b, (x, 45.72)); S.power("GND", (x, 45.72))
    S.section(19.05, 17.78, 64.77, 61.6, "Bus pull-ups")
    S.section(48.26, 62.23, 127.0, 137.16, "U901 (0x74)")
    S.section(161.29, 62.23, 241.3, 137.16, "U902 (0x75)")
    S.section(273.05, 62.23, 355.6, 137.16, "U903 (0x76)")
    return S.finish()


# ---------- bias-T supply sheet: U1001 PCA9539 at 0x77 and four switched, current-limited feeds (D-54) ----------
SOT223 = "Package_TO_SOT_SMD:SOT-223-3_TabPin2"
R0805 = "Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder"
def bias_channel(S, k, ox, yl):
    """One feed: +12V_AUX, Rs, P-MOSFET high-side switch with PNP current limit, BSS138BK gate drive from Ak_BIAS_EN,
    output decoupling, TVS and the Ak_BIAS_OK read-back divider. yl: main line, gate line 7.62 above, output 10.16 below."""
    n = 10 * k                                               # references R10k0.., Q10k1.., per channel
    yg, yo = R2(yl - 7.62), R2(yl + 10.16)
    X = lambda d: R2(ox + d)
    S.power("+12V_AUX", (ox, yl))
    RS = S.part("Device:R", ("R", n + 1), "10R", R0805, X(17.78), yl, rot=90, rp=(-2.54, 2.54),
                desc="Current sense: limit = VBE / 10R, about 42 to 78 mA over temperature (C-17). 0805, 61 mW max in a short")
    rl, rr = sorted([RS["1"], RS["2"]])
    S.wire((ox, yl), (X(7.62), yl), rl)
    QL = S.part("Transistor_BJT:Q_PNP_BEC", ("Q", n + 1), "BC857B", SOT23, X(25.4), R2(yl - 5.08), rot=270, mirror="x", mpn="BC857B",
                desc="Current limiter: pulls the gate to the source when the drop on the sense resistor reaches VBE. Nexperia, onsemi, Diodes",
                rp=(-6.35, -8.89, "right"))
    assert QL["1"] == (X(25.4), yl) and QL["2"] == (X(20.32), yg) and QL["3"] == (X(30.48), yg), QL
    S.wire(QL["2"], (X(7.62), yg), (X(7.62), yl))            # emitter to the supply side of the sense resistor
    S.wire(rr, QL["1"], (X(35.56), yl), (X(43.18), yl))      # node S: sense resistor, limiter base, Rgs, P-MOSFET source
    RGS = S.part("Device:R", ("R", n + 2), "100k", R0603, X(35.56), R2(yl - 3.81), rp=(1.27, -2.54),
                 desc="Gate-source: holds the P-MOSFET off. With R3 47k: VGS = 12.6 x 100 / 147 = 8.6 V max")
    assert {RGS["1"], RGS["2"]} == {(X(35.56), yg), (X(35.56), yl)}, RGS
    QP = S.part("Transistor_FET:Q_PMOS_GDS", ("Q", n + 2), "IRFL9014", SOT223, X(48.26), R2(yl - 2.54), rot=270, mpn="IRFL9014TRPBF-BE3",
                desc="P-MOSFET -60 V, SOT-223 (1 G, 2 D, 3 S, tab D). Vishay IRFL9014 Rev G; second source onsemi NTF2955. "
                     "Needs about 1 square inch of drain copper (RthJA 60 K/W, C-17)", rp=(-3.81, 7.62, "right"))
    assert QP["3"] == (X(43.18), yl) and QP["2"] == (X(53.34), yl) and QP["1"] == (X(48.26), yg), QP
    S.wire(QL["3"], (X(35.56), yg), (X(40.64), yg), QP["1"])  # gate line
    RG = S.part("Device:R", ("R", n + 3), "47k", R0603, X(40.64), R2(yg - 3.81), rp=(1.27, -1.27),
                desc="Gate drive series resistor: limits VGS with R2 and sets the current the limiter must take over")
    gt = min(RG["1"], RG["2"], key=lambda q: q[1])
    QN = S.part("Transistor_FET:Q_NMOS_GSD", ("Q", n + 3), "BSS138BK", SOT23, X(60.96), R2(yg - 2.54), mirror="y", mpn="BSS138BK,215", desc=QN_D,
                rp=(2.54, -8.89))
    assert QN["3"] == (X(58.42), R2(yg - 7.62)) and QN["2"] == (X(58.42), R2(yg + 2.54)), QN
    S.wire(gt, QN["3"]); S.power("GND", QN["2"])
    en = (X(71.12), QN["1"][1])
    S.wire(QN["1"], en, (X(78.74), en[1])); S.label("L", f"A{k}_BIAS_EN", X(78.74), en[1], 0)
    RPD = S.part("Device:R", ("R", n + 4), "100k", R0603, en[0], R2(en[1] + 3.81), rp=(1.27, 1.27),
                 desc="Enable pull-down: feed off while U1001 is in reset (RLY_EN low) or not configured")
    S.power("GND", max(RPD["1"], RPD["2"], key=lambda q: q[1]))
    # output: decoupling, TVS, read-back divider, to the antenna port
    S.wire(QP["2"], (X(53.34), yo), (X(60.96), yo), (X(73.66), yo), (X(86.36), yo), (X(101.6), yo))
    S.label("H", f"A{k}_BIAS", X(101.6), yo, 0)
    CO = S.part("Device:C", ("C", n + 1), "100n 50V X7R", C0603, X(60.96), R2(yo + 3.81), desc="Output decoupling, 100 nF X7R 50 V")
    S.power("GND", max(CO["1"], CO["2"], key=lambda q: q[1]))
    T = S.part("Device:D_Zener", ("D", n + 1), "SMBJ15A", "Diode_SMD:D_SMB", X(73.66), R2(yo + 3.81), rot=270, mpn="SMBJ15A",
               desc="TVS on the feed: clamps surges that pass the bias choke; conducts on negative pulses (same part as D-45)")
    assert T["1"] == (X(73.66), yo), T
    S.power("GND", T["2"])
    RT = S.part("Device:R", ("R", n + 5), "33k", R0603, X(86.36), R2(yo + 3.81), rp=(1.27, -1.27),
                desc="Read-back divider, top: 12.6 V gives 2.93 V, 11.4 V gives 2.65 V (VIH 2.35 V)")
    RB = S.part("Device:R", ("R", n + 6), "10k", R0603, X(86.36), R2(yo + 11.43), rp=(1.27, 1.27), desc="Read-back divider, bottom")
    mid = (X(86.36), R2(yo + 7.62))
    S.wire(mid, (X(96.52), mid[1])); S.label("L", f"A{k}_BIAS_OK", X(96.52), mid[1], 0)
    S.power("GND", max(RB["1"], RB["2"], key=lambda q: q[1]))

def bias_sheet():
    S = Sheet("Unit RF board: bias-T supply (switched, current-limited)", "A3", [(PATH["bias"], 1000)], pwr_base=[1100])  # references 10xx
    expander(S, 1, 76.2, 101.6, 1, 1, [f"A{k}_BIAS_EN" for k in (1, 2, 3, 4)] + [f"A{k}_BIAS_OK" for k in (1, 2, 3, 4)] + [""] * 8, io_kind="L")
    for k, (ox, yl) in zip((1, 2, 3, 4), ((152.4, 68.58), (279.4, 68.58), (152.4, 142.24), (279.4, 142.24))):
        bias_channel(S, k, ox, yl)
    S.text("Bias-T supply (D-54). U1001 PCA9539 at 0x77 (A1 A0 = 11), on the same bus and RESET (= RLY_EN) as U901 to U903.\\n"
           "IO0_0..3 = A1..A4_BIAS_EN (outputs, active high), IO0_4..7 = A1..A4_BIAS_OK (inputs), IO1 spare, held low by RN1001, RN1002 (D-121).\\n"
           "Per feed: +12V_AUX, 10R sense, IRFL9014 P-MOSFET high side, BC857B limiter (about 42 to 78 mA over temperature), BSS138BK gate drive.\\n"
           "A short on the coax holds the feed in current limit: 0.8 W max in the P-MOSFET, Tj about 103 C at 55 C ambient on 1 sq. inch copper (C-17).\\n"
           "The firmware switches a feed off when EN is high and OK stays low (fault), and reports it. OK changes raise EXP_INT.\\n"
           "Safe state: RLY_EN low holds U1001 in reset, the 100k pull-downs keep every feed off (KILL also turns the preamps off).\\n"
           "Ak_BIAS goes to the bias-T of antenna port Ak (L2, C2 DNP there; fit on a bias-T port only).", 25.4, 190.5)
    S.section(45.72, 60.96, 127.0, 137.16, "U1001 (0x77)")
    S.section(147.32, 45.72, 266.7, 104.14, "Feed A1")
    S.section(274.32, 45.72, 393.7, 104.14, "Feed A2")
    S.section(147.32, 119.38, 266.7, 177.8, "Feed A3")
    S.section(274.32, 119.38, 393.7, 177.8, "Feed A4")
    return S.finish()

# ---------- J14 crossing filter sheet (D-122): series link, C footprint and test point per slow line ----------
J14_SIG = ["SCL", "SDA", "EXP_INT", "RLY_EN", "TX_ANY", "R1_K0_DRV", "R2_K0_DRV", "R3_K0_DRV", "A2_RFDET"]
TP_SIG = {"SCL", "SDA", "EXP_INT", "RLY_EN", "TX_ANY", "A2_RFDET"}
def j14_sheet():
    S = Sheet("Unit RF board: J14 crossing filter and test points", "A4", [(PATH["j14"], 1200)], pwr_base=[1300])   # references 12xx
    for i, net in enumerate(J14_SIG):
        y = R2(38.1 + i * 15.24)
        S.label("H", f"{net}_J", 30.48, y, 180)
        R = S.part("Device:R", ("R", 1 + i), "0R", R0603, 50.8, y, rot=90, rp=(-2.54, -5.08),
                   desc=f"{net}: series link at the J14 crossing, 0R fitted; 100R to 1k on the bench if needed (D-122)")
        assert R["1"] == (46.99, y) and R["2"] == (54.61, y), R
        S.wire((30.48, y), R["1"])
        S.wire(*([R["2"], (63.5, y)] + ([(76.2, y)] if net in TP_SIG else []) + [(101.6, y)]))
        C = S.part("Device:C", ("C", 1 + i), "DNP 100p C0G", C0603, 63.5, R2(y + 3.81), dnp=True,
                   desc=f"{net}: capacitor to GND at the J14 crossing, footprint only (D-122). I2C: 100 pF max with the 2.2k pull-ups (rise 0.19 us)")
        assert C["1"] == (63.5, y), C
        S.power("GND", C["2"], rp=(1.27, 1.27))
        if net in TP_SIG:
            S.part("Connector:TestPoint", ("TP", 1 + i), net, TP_FP, 76.2, y, desc=f"Test point {net} (D-120)", bom=False, rp=(1.27, -5.08))
        S.label("H", net, 101.6, y, 0)
    S.text("J14 crossing (D-122): each slow line from the controller board enters through a series link\\n"
           "(0R fitted) with a capacitor footprint to GND (not fitted), placed at J14. Values are set on the bench:\\n"
           "series 100R to 1k, C up to 100 pF; check the I2C rise time with the 2.2k pull-ups (IO sheet).\\n"
           "Test points on the logic side (D-120). Nets *_J run from J14 to this sheet only.", 25.4, 180.34)
    S.section(12.7, 27.94, 119.38, 175.26, "J14 crossing filter and test points")
    return S.finish()

# ---------- root sheet: connectors, crossbar and sheet blocks ----------
DRV = ["K0_DRV"] + [f"{r}{c}_DRV" for r in ("TX", "RX") for c in "1234E"]
RADIO_L = ["RADIO", "EXP", ""] + DRV                          # "" = empty pin position
ANT_R = ["ANTENNA", "", "K1_DRV", "DET", "BIAS"]
def sheet_block(key, name, fn, page, x, y, w, h, left, right):
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
            f'\t\t(property "Sheetfile" "{fn}"\n\t\t\t(at {x} {R2(y + h + 0.59)} 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify left top)\n\t\t\t)\n\t\t)\n'
            + sp + f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "/{ROOT_UUID}"\n\t\t\t\t\t(page "{page}")\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')

ALIASES = {}
def root_sheet():
    """Root: connectors, port sheets, crossbar columns as wires. Control lines run as buses (D-60): one bus segment
    at each block, joined by bus aliases; each entry wire carries its net name. Nets between neighbouring blocks are wires."""
    S = Sheet("Unit RF board: overview, connectors and crossbar", "A2", [(f"/{ROOT_UUID}", 0)], pwr_base=[900])
    S.u = ROOT_UUID
    RX, RW, RY = 76.2, 50.8, {1: 38.1, 2: 99.06, 3: 160.02}
    AX, AW, AY = 203.2, 45.72, {k: R2(38.1 + (k - 1) * 45.72) for k in (1, 2, 3, 4)}
    COLX = {k: R2(142.24 + (k - 1) * 7.62) for k in (1, 2, 3, 4)}
    pin_y = lambda y0, names, n: R2(y0 + (names.index(n) + 1) * 2.54)
    for i in (1, 2, 3): S.aliases[f"R{i}DRV"] = [f"R{i}_{d}" for d in DRV]
    S.aliases["ANT"] = [f"A{k}_{f}" for f in ("K1_DRV", "DET", "BIAS") for k in (1, 2, 3, 4)]
    S.aliases["CTRL"] = ["SCL", "SDA", "EXP_INT", "RLY_EN"]
    ALIASES.update(S.aliases)                                # KiCad 10 keeps bus aliases in the .kicad_pro (schematic.bus_aliases)
    page = 2
    PX0 = 480.06                                             # power block and XT entry, top right
    PIN_R = [""] * 23
    PIN_R[0], PIN_R[11], PIN_R[22] = "+12V_RLY_IN", "+12V_AUX_IN", "+5V_IN"     # at the height of each XT + pin
    S.raw(sheet_block("power", "Power, coil supply and 3V3", "power.kicad_sch", page, PX0, 45.72, 20.32, 60.96, ["", "", "RLY_EN"], PIN_R)); page += 1
    S.bus_tap(R2(PX0 - 20.32), [("RLY_EN", PX0, 53.34)], +1, "CTRL", "bottom")
    # radios: SO-239 (radio coax) and EXP SMA on the left; coil drives as bus R<i>DRV
    for i in (1, 2, 3):
        y = RY[i]
        S.raw(sheet_block(f"r{i}", f"Radio port R{i}", "radio_port.kicad_sch", page, RX, y, RW, R2((len(RADIO_L) + 1) * 2.54),
                          RADIO_L, [f"ANT{k}" for k in (1, 2, 3, 4)])); page += 1
        S.bus_tap(R2(RX - 20.32), [(f"R{i}_{d}", RX, pin_y(y, RADIO_L, d)) for d in DRV], +1, f"R{i}DRV", "top")
        yr, ye = pin_y(y, RADIO_L, "RADIO"), pin_y(y, RADIO_L, "EXP")
        J = S.part("Connector:Conn_Coaxial", ("J", i), "83-798 SO-239", SO239_FP, 25.4, yr, desc=f"Radio R{i}. " + SO239_D,
                   mpn="83-798", mirror="y", rp=(-3.81, -5.08, "right"))   # mirror flips the justification
        S.wire(J["1"], (RX, yr)); S.power("GND", J["2"])
        E = S.part("Connector:Conn_Coaxial", ("J", 3 + i), "SMA jack EXP", "rf-board:SMA_901-9215_StrapPad", 25.4, R2(ye + 17.78), mpn="901-9215",
                   desc=f"EXP R{i} to unit 2 (left wall pocket, strap land; 2nd source 132142, D-108, D-110)", mirror="y", rp=(-3.81, -5.08, "right"))
        S.wire(E["1"], (38.1, R2(ye + 17.78)), (38.1, ye), (RX, ye)); S.power("GND", E["2"])
        S.label("L", f"R{i}_RADIO", 43.18, yr); S.label("L", f"R{i}_EXP", 43.18, ye)
    # antennas: SO-239 on the right; K1 drive, detector and bias feed as bus ANT
    for k in (1, 2, 3, 4):
        y = AY[k]
        S.raw(sheet_block(f"a{k}", f"Antenna port A{k}", "antenna_port.kicad_sch", page, AX, y, AW, R2((len(ANT_R) + 1) * 2.54),
                          ["ANT"], ANT_R)); page += 1
        S.bus_tap(R2(AX + AW + 20.32), [(f"A{k}_{f}", R2(AX + AW), pin_y(y, ANT_R, f)) for f in ("K1_DRV", "DET", "BIAS")], -1, "ANT", "bottom")
        ya = pin_y(y, ANT_R, "ANTENNA")
        J = S.part("Connector:Conn_Coaxial", ("J", 6 + k), "83-798 SO-239", SO239_FP_L if k == 4 else SO239_FP, 279.4, ya, desc=f"Antenna A{k}. " + SO239_D,
                   mpn="83-798", rp=(3.81, -5.08))
        S.wire((R2(AX + AW), ya), J["1"]); S.power("GND", J["2"]); S.label("L", f"A{k}_ANTENNA", 254.0, ya)
    # I/O expander block: drives and inputs grouped per bus; J14 section wired straight to the header
    IOX, IOY = 406.4, 55.88
    hdr = ["SCL", "SDA", "EXP_INT", "RLY_EN", "TX_ANY", "R1_K0_DRV", "R2_K0_DRV", "R3_K0_DRV"]
    rows = lambda i: [f"R{i}_{r}_DRV" for r in ROWS]
    io_left = rows(1) + ["", ""] + rows(2) + ["", ""] + rows(3) + ["", ""] + [f"A{k}_K1_DRV" for k in (1, 2, 3, 4)] + ["", ""] + \
              [f"A{k}_RFDET" for k in (1, 2, 3, 4)] + ["", "", "", ""] + hdr
    assert sorted(n for n in io_left if n) == sorted(IO_NETS + ["RLY_EN", "SCL", "SDA", "EXP_INT"]), "IO block pins"
    S.raw(sheet_block("io", "IO expanders", "io_expanders.kicad_sch", page, IOX, IOY, 38.1, R2((len(io_left) + 1) * 2.54), io_left, [])); page += 1
    iy = lambda n: R2(IOY + (io_left.index(n) + 1) * 2.54)
    XB = R2(IOX - 20.32)
    for i in (1, 2, 3): S.bus_tap(XB, [(n, IOX, iy(n)) for n in rows(i)], +1, f"R{i}DRV", "top")
    S.bus_tap(XB, [(n, IOX, iy(n)) for n in (f"A{k}_K1_DRV" for k in (1, 2, 3, 4))], +1, "ANT", "top")
    # RF detect block: RFDETk wired straight to the IO block; DETk from the ANT bus
    DX, DY = 340.36, R2(iy("A1_RFDET") - 2.54)
    S.raw(sheet_block("det", "RF detect", "rf_detect.kicad_sch", page, DX, DY, 45.72, 12.7,
                      [f"DET{k}" for k in (1, 2, 3, 4)], [f"RFDET{k}" for k in (1, 2, 3, 4)])); page += 1
    for k in (1, 2, 3, 4):
        S.wire((R2(DX + 45.72), R2(DY + k * 2.54)), (IOX, iy(f"A{k}_RFDET")))
        if str(k) in RX_ONLY: S.label("L", f"A{k}_RFDET", R2(DX + 45.72 + 5.08), R2(DY + k * 2.54))   # also to J14 pin 17 (D-104)
    assert all(R2(DY + k * 2.54) == iy(f"A{k}_RFDET") for k in (1, 2, 3, 4))
    S.bus_tap(R2(DX - 20.32), [(f"A{k}_DET", DX, R2(DY + k * 2.54)) for k in (1, 2, 3, 4)], +1, "ANT", "top")
    # controller header J14 (D-51, D-52), mirrored: odd (signal) pins face the IO block; +5V and GND on the even pins
    FX, FW, FY = R2(IOX - 25.4 - 40.64), 40.64, R2(iy("SCL") - 2.54)        # J14 filter block (D-122) between the header and the IO block
    S.raw(sheet_block("j14", "J14 filter", "j14_filter.kicad_sch", page, FX, FY, FW, R2((len(J14_SIG) + 1) * 2.54),
                      [n + "_J" for n in J14_SIG], J14_SIG)); page += 1
    for i, net in enumerate(J14_SIG):
        py = R2(FY + (i + 1) * 2.54)
        if net in hdr:
            assert py == iy(net), (net, py)
            S.wire((R2(FX + FW), py), (IOX, py)); S.label("L", net, R2(FX + FW + 2.54), py, 0)
        else:
            S.wire((R2(FX + FW), py), (R2(FX + FW + 2.54), py)); S.label("L", net, R2(FX + FW + 2.54), py, 0)
    HX = R2(FX - 20.32 - 5.08)
    JH = S.part("Connector_Generic:Conn_02x12_Odd_Even", ("J", 14), "Controller header", "Connector_PinHeader_2.54mm:PinHeader_2x12_P2.54mm_Vertical",
                HX, R2(iy("SCL") + 12.7), mirror="y",
                desc="Board-to-board header. Unit 1: controller board (MCU, RJ45 LINK). Unit 2: EXP ribbon from the unit 1 controller board, +5V pins open at the controller end. 3.3 V logic (D-51, D-53). Samtec TSW, 0.64 mm square post 5.84 mm above the body, 10 uin gold on the post; mates with the ESQ-112-33-G-D on the controller (D-139)", mpn="TSW-112-07-L-D",
                rp=(7.62, 17.78, "left"))
    assert JH["1"][0] == R2(FX - 20.32), JH["1"]
    for i, net in enumerate(J14_SIG + ["", "", ""]):        # pin 17 = A2_RFDET: RF on the receive-only column A2 (D-104, SR-01 H2)
        px, py = JH[str(2 * i + 1)]
        if not net: S.raw(f'\t(no_connect\n\t\t(at {px} {py})\n\t\t(uuid "{U()}")\n\t)\n'); continue
        assert py == R2(FY + (i + 1) * 2.54), (net, py)
        S.wire((px, py), (FX, py)); S.label("L", net + "_J", R2(px + 2.54), py, 0)
    ex = R2(JH["2"][0] - 5.08)
    ends = []
    for n in range(2, 25, 2):
        px, py = JH[str(n)]; S.wire((px, py), (ex, py)); ends.append(py)
    S.wire((ex, ends[1]), (ex, ends[0]), (ex, R2(ends[0] - 2.54))); S.power("+5V", (ex, R2(ends[0] - 2.54)))
    g = ends[2:]
    for a, b in zip(g, g[1:]): S.wire((ex, a), (ex, b))
    S.wire((ex, g[-1]), (ex, R2(g[-1] + 2.54))); S.power("GND", (ex, R2(g[-1] + 2.54)))
    # bias-T supply block (D-54): CTRL bus in, four feeds out on the ANT bus
    BX_, BY_ = 340.36, 248.92
    S.raw(sheet_block("bias", "Bias-T supply", "bias_supply.kicad_sch", page, BX_, BY_, 20.32, 12.7,
                      ["SCL", "SDA", "EXP_INT", "RLY_EN"], [f"A{k}_BIAS" for k in (1, 2, 3, 4)])); page += 1
    S.bus_tap(R2(BX_ - 20.32), [(n, BX_, R2(BY_ + (i + 1) * 2.54)) for i, n in enumerate(("SCL", "SDA", "EXP_INT", "RLY_EN"))], +1, "CTRL", "top")
    S.bus_tap(R2(BX_ + 20.32 + 25.4), [(f"A{k}_BIAS", R2(BX_ + 20.32), R2(BY_ + k * 2.54)) for k in (1, 2, 3, 4)], -1, "ANT", "bottom")
    # columns: one vertical wire per antenna line, joined to every radio sheet and to its antenna port
    for k in (1, 2, 3, 4):
        x = COLX[k]
        taps = []
        for i in (1, 2, 3):
            py = R2(RY[i] + k * 2.54)
            S.wire((R2(RX + RW), py), (x, py)); taps.append(py)
        pa = R2(AY[k] + 2.54)
        S.wire((AX, pa), (x, pa)); taps.append(pa)
        S.label("L", f"ANT{k}", R2(AX - 12.7), pa)
        taps = sorted(set(taps))
        for a, b in zip(taps, taps[1:]): S.wire((x, a), (x, b))
    # power entry: one Amass XT per rail, + up, GND down
    for n, (net, val, fp, desc) in enumerate(PWR):
        x, y = 530.86, R2(50.8 + n * 27.94)
        J = S.part("Connector_Generic:Conn_01x02", ("J", 11 + n), val, fp, x, y, desc=desc, mpn=val, mirror="x", rp=(3.81, -2.54))
        S.wire(J["2"], (500.38, R2(y - 2.54))); S.label("L", f"{net}_IN", 502.92, R2(y - 2.54))   # to fuse and TVS
        S.wire(J["1"], (x - 20.32, y), (x - 20.32, y + 5.08)); S.power("GND", (x - 20.32, y + 5.08))
    S.wire((492.76, 124.46), (492.76, 129.54)); S.power("GND", (492.76, 129.54)); S.power("GND", (492.76, 124.46), flag=True)
    S.text("Power entry (top wall): one Amass XT per rail, board side male (PW-M).\\n"
           "XT30 on +5V cannot mate with XT60. Pin 1 = GND, pin 2 = + per the KiCad\\n"
           "footprint. OPEN: the vendor STEP puts the angled end on pad 2; convention\\n"
           "says angled = minus. Check a real part before release.", 480.06, 147.32)
    S.text("Shack Relay Matrix, unit RF board, architecture rev C. One flat board in a milled 6082-T6 case.\\n"
           "All connectors are on this sheet: radio SO-239 J1 to J3 and EXP SMA J4 to J6 (left), antenna SO-239 J7 to J10\\n"
           "(right), power J11 to J13. Unit 1: 3 radios x 4 antennas; A1 G5RV, A2 RX loop (RX only), A3 and A4 spare.\\n"
           "Crossbar: the four vertical wires are the antenna columns ANT1 to ANT4 (L2). Each radio sheet holds\\n"
           "a TX row and an RX row (L1) with one relay per column. 37 x RT1: 3 K0, 15 TX, 15 RX, 4 K1; unit 1 fits 34 (no TX relay at A2, D-103).\\n"
           "Coil drivers sit next to each relay; Rn_*_DRV and An_K1_DRV are 3.3 V gate inputs from the IO expanders sheet.\\n"
           "J14 goes to the controller board (unit 1) or takes the EXP ribbon from the unit 1 controller board (unit 2), D-51, D-53;\\n"
           "each J14 signal passes the J14 filter sheet: series link, C footprint and test point (D-122, D-120).\\n"
           "The RF board is the same in both units. R1 K0 follows PTT in hardware (TX_ANY, R51, D-58); R2, R3 K0 from U903 (D-63).\\n"
           "Control lines as buses (D-60): R1DRV to R3DRV (coil drives per radio), ANT (K1 drive, detector, bias feed per antenna port),\\n"
           "CTRL (I2C, EXP_INT, RLY_EN). One bus segment at each block; the bus alias joins them, each entry wire carries its net name.\\n"
           "Test: ERC; netlist check that each ANTk joins 6 row relays and one antenna port; logic verification (verify_logic.py, M-08).\\n"
           "Target: 50 ohm RF path, 100 W HF at SWR 3 (173 V peak, 2.45 A rms), PD3 outdoor box.", 30.48, 243.84)
    return S.finish()

files = {"radio_port.kicad_sch": radio_sheet(), "antenna_port.kicad_sch": antenna_sheet(),
         "power.kicad_sch": power_sheet(), "j14_filter.kicad_sch": j14_sheet(), "rf_detect.kicad_sch": rf_detect_sheet(), "io_expanders.kicad_sch": io_sheet(), "bias_supply.kicad_sch": bias_sheet(),
         f"{PROJECT}.kicad_sch": root_sheet()}
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
# every reference unique over the whole design (a multi-unit part counts once per unit)
_refs = [(r, u) for t in files.values() for r, u in re.findall(r'\(reference "([^"]+)"\)\s*\(unit (\d+)\)', t)]
assert len(_refs) == len(set(_refs)), sorted(r for r in set(_refs) if _refs.count(r) > 1)
# project symbol library and library tables
libs = [SYMS[k].replace(f'(symbol "{k}"', f'(symbol "{k.split(":")[1]}"', 1) for k in (RLY, "rf-board:LP2985-3.3", "rf-board:BAS70-04")]
open(f"{PROJECT}.kicad_sym", "w").write('(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kicad_symbol_editor")\n'
                                        '\t(generator_version "10.0")\n\t' + "\n\t".join(l.replace("\n", "\n\t") for l in libs) + "\n)\n")
open("sym-lib-table", "w").write('(sym_lib_table\n\t(version 7)\n\t(lib (name "rf-board")(type "KiCad")'
                                 '(uri "${KIPRJMOD}/rf-board.kicad_sym")(options "")(descr "Shack Relay Matrix rev C"))\n)\n')
os.makedirs(f"{PROJECT}.pretty", exist_ok=True)
open("fp-lib-table", "w").write('(fp_lib_table\n\t(version 7)\n\t(lib (name "rf-board")(type "KiCad")'
                                '(uri "${KIPRJMOD}/rf-board.pretty")(options "")(descr "Shack Relay Matrix rev C"))\n)\n')
# project file: keep KiCad's settings, set the top-level sheet uuid to ROOT_UUID
pro = json.load(open(f"{PROJECT}.kicad_pro")) if os.path.exists(f"{PROJECT}.kicad_pro") else \
      {"meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3}}
pro.setdefault("schematic", {})["bus_aliases"] = dict(ALIASES)
pro.setdefault("schematic", {})["top_level_sheets"] = [
    {"filename": f"{PROJECT}.kicad_sch", "name": PROJECT, "uuid": ROOT_UUID}]
open(f"{PROJECT}.kicad_pro", "w").write(json.dumps(pro, indent=2) + "\n")
print(GENERATOR_REV, "root", ROOT_UUID, "files", list(files))
