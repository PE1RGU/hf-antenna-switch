#!/usr/bin/env python3
"""Generate the backplane schematic (root + one A4 sheet per slot).

Pin-out and slot order: claude/decisions-2026-09-26-backplane.md (approved 2026-09-26).
Run from this folder. Regenerates all backplane*.kicad_sch / slot*.kicad_sch files.
"""
import re, uuid

COUPON = "../../test-pieces/rf-isolation/kicad/rf-iso-backplane/rf-iso-backplane.kicad_sch"
PROJECT = "backplane"
U = lambda: str(uuid.uuid4())

root_txt = open("backplane.kicad_sch").read()
ROOT_UUID = re.search(r"\(uuid ([0-9a-f-]+)\)", root_txt).group(1)

def extract(s, head):
    i = s.find(head); assert i >= 0, head
    d = 0; k = i
    while True:
        if s[k] == "(": d += 1
        elif s[k] == ")":
            d -= 1
            if d == 0: return s[i:k + 1]
        k += 1

DIN_SYM = extract(open(COUPON).read(), '(symbol "Connector:DIN41612_03x32_C_Split"')
CONN2 = open("_conn01x02.sym").read().strip().replace('(symbol "Conn_01x02"', '(symbol "Connector_Generic:Conn_01x02"', 1)

# ---------- pin-out (identical on every slot) ----------
PIN = {}
for r in "abc":
    for n in range(1, 33): PIN[f"{r}{n}"] = "GND"
PIN.update({"a21": "SDA", "c21": "SCL", "a22": "~{INT}", "c22": "~{RLY_EN}",
            "a23": "PTT1", "c23": "PTT2", "a24": "PTT3", "c24": "PTT4",
            "a25": "SLOT_ID0", "b25": "SLOT_ID1", "c25": "SLOT_ID2", "a26": "SLOT_ID3",
            "c26": "TX_ANY", "a27": "+12V_AUX", "c27": "SPARE2",
            "a29": "+5V", "c29": "+5V", "a31": "+12V_RLY", "c31": "+12V_RLY"})
RFPOS = {1: ("b2", "b3"), 2: ("b5", "b6"), 3: ("b8", "b9"), 4: ("b11", "b12"), 5: ("b14", "b15"), 6: ("b17", "b18")}
SLOTS = [(0, "Link", "link", None)] + [(i, f"R{i}", "radio", None) for i in range(1, 5)] + \
        [(4 + k, f"A{k}", "ant", k) for k in range(1, 7)]
POWER = {"GND", "+5V", "+12V_RLY", "+12V_AUX"}

def slot_nets(n, kind, k):
    nets = dict(PIN)
    for pos, pins in RFPOS.items():                       # RF positions
        for p in pins:
            if kind == "radio": nets[p] = f"ANT{pos}"
            elif kind == "ant" and pos == 1: nets[p] = f"ANT{k}"   # antenna card uses position 1
            else: nets[p] = None                               # not connected
    for bit, p in enumerate(["a25", "b25", "c25", "a26"]):  # SLOT_ID: 0 = GND strap, 1 = open (card pull-up)
        nets[p] = None if (n >> bit) & 1 else "GND"
    return nets

UNIT_X = {"a": 59.69, "b": 110.49, "c": 160.02}; UNIT_Y = 59.69
def pin_xy(p):
    return round(UNIT_X[p[0]] - 5.08, 2), round(UNIT_Y - 38.1 + (int(p[1:]) - 1) * 2.54, 2)

def glabel(name, x, y):
    shape = "passive" if name in POWER else "bidirectional"
    return (f'\t(global_label "{name}"\n\t\t(shape {shape})\n\t\t(at {x} {y} 180)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
            f'\t\t\t(justify right)\n\t\t)\n\t\t(uuid "{U()}")\n\t)\n')
def noconn(x, y): return f'\t(no_connect\n\t\t(at {x} {y})\n\t\t(uuid "{U()}")\n\t)\n'
def text(t, x, y, size=1.27):
    return (f'\t(text "{t}"\n\t\t(exclude_from_sim no)\n\t\t(at {x} {y} 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {size} {size})\n\t\t\t)\n'
            f'\t\t\t(justify left top)\n\t\t)\n\t\t(uuid "{U()}")\n\t)\n')
def prop(name, val, x, y, hide=False):
    h = "\n\t\t\t(hide yes)" if hide else ""
    return (f'\t\t(property "{name}" "{val}"\n\t\t\t(at {x} {y} 0){h}\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n'
            f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n')
def symbol(lib, ref, value, fp, x, y, unit, pins, path, desc="", ref_dy=-40.64, val_dy=43.18, dnp=False, bom=True):
    s = (f'\t(symbol\n\t\t(lib_id "{lib}")\n\t\t(at {x} {y} 0)\n\t\t(unit {unit})\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n'
         f'\t\t(in_bom {"yes" if bom else "no"})\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n\t\t(dnp {"yes" if dnp else "no"})\n\t\t(uuid "{U()}")\n')
    s += prop("Reference", ref, x, round(y + ref_dy, 2)) + prop("Value", value, x, round(y + val_dy, 2))
    s += prop("Footprint", fp, x, y, True) + prop("Datasheet", "", x, y, True) + prop("Description", desc, x, y, True)
    for p in pins: s += f'\t\t(pin "{p}"\n\t\t\t(uuid "{U()}")\n\t\t)\n'
    s += (f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "{path}"\n\t\t\t\t\t(reference "{ref}")\n'
          f'\t\t\t\t\t(unit {unit})\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')
    return s

C1 = "Design: Prins Doornekamp, PE1RGU"
C2 = "J1 to J11 HARTING 09 03 296 6824 (DIN 41612 C, 96 pos, female straight)"
C3 = "Row b RF: b2+b3 .. b17+b18 = ANT1..ANT6, GND between. Pin-out rev 2026-09-26"
C4 = "Stackup: to be decided (4-layer CPWG or 6-layer stripline)"
def tblock(title, page_note=""):
    c = [C1, C2, C3, C4]
    t = f'\t(title_block\n\t\t(title "{title}")\n\t\t(date "2026-09-26")\n\t\t(rev "A")\n\t\t(company "PE1RGU - Shack Relay Matrix")\n'
    t += "".join(f'\t\t(comment {i + 1} "{x}")\n' for i, x in enumerate(c))
    return t + "\t)\n"
def header(sheet_uuid, lib):
    return (f'(kicad_sch\n\t(version 20260101)\n\t(generator "eeschema")\n\t(generator_version "10.0")\n'
            f'\t(uuid {sheet_uuid})\n\t(paper "A4")\n')

sheet_blocks = []
ROLE = {"link": "link card (RS-485 bridge, PTT and KILL loops)", "radio": "radio port card",
        "ant": "antenna port card"}
for idx, (n, name, kind, k) in enumerate(SLOTS):
    fn = f"slot{n:02d}_{name.lower()}.kicad_sch"
    sheet_uuid, sym_sheet = U(), U()
    path = f"/{ROOT_UUID}/{sym_sheet}"
    nets = slot_nets(n, kind, k)
    ref = f"J{n + 1}"
    body = header(sheet_uuid, DIN_SYM)
    body += tblock(f"Backplane: slot {n} ({name}, {ROLE[kind].split(' (')[0]})")
    body += "\t(lib_symbols\n\t\t" + DIN_SYM.replace("\n", "\n\t") + "\n\t)\n"
    for r, unit in (("a", 1), ("b", 2), ("c", 3)):
        pins = [f"{r}{i}" for i in range(1, 33)]
        body += symbol("Connector:DIN41612_03x32_C_Split", ref, "09 03 296 6824",
                       "Connector_DIN:DIN41612_C_3x32_Female_Vertical_THT", UNIT_X[r], UNIT_Y, unit, pins, path,
                       "DIN 41612 C, 96 pos, female, straight, PL2")
        for p in pins:
            x, y = pin_xy(p)
            body += glabel(nets[p], x, y) if nets[p] else noconn(x, y)
    bits = format(n, "04b")[::-1]
    if kind == "ant":
        rf = f"RF position 1 (b2+b3) = ANT{k}. Positions 2 to 6 not connected: every antenna card is identical."
    elif kind == "radio":
        rf = "RF positions 1 to 6 = ANT1 to ANT6 (all antenna lines)."
    else:
        rf = "No RF on the link slot: RF positions not connected."
    note = (f"Slot {n}: {name}, {ROLE[kind]}.\\n{rf}\\n"
            f"SLOT_ID3..0 = {format(n, '04b')}: a 0 bit is strapped to GND, a 1 bit is open (pull-up on the card).\\n"
            f"Pins b20 to b32 and all other unlabelled contacts: see pin-out on the root sheet.")
    body += text(note, 25.4, 120.65)
    body += f'\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n)\n'
    open(fn, "w").write(body)
    col, row = idx % 4, idx // 4
    x, y = 25.4 + col * 45.72, 30.48 + row * 30.48
    sheet_blocks.append(
        f'\t(sheet\n\t\t(at {x} {y})\n\t\t(size 38.1 15.24)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n'
        f'\t\t(dnp no)\n\t\t(fields_autoplaced yes)\n\t\t(stroke\n\t\t\t(width 0.1524)\n\t\t\t(type solid)\n\t\t)\n'
        f'\t\t(fill\n\t\t\t(color 0 0 0 0.0000)\n\t\t)\n\t\t(uuid "{sym_sheet}")\n'
        f'\t\t(property "Sheetname" "Slot {n} {name}"\n\t\t\t(at {x} {round(y - 0.71, 2)} 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify left bottom)\n\t\t\t)\n\t\t)\n'
        f'\t\t(property "Sheetfile" "{fn}"\n\t\t\t(at {x} {round(y + 15.83, 2)} 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify left top)\n\t\t\t)\n\t\t)\n'
        f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "/{ROOT_UUID}"\n\t\t\t\t\t(page "{idx + 2}")\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')

# ---------- root sheet ----------
root = header(ROOT_UUID, None) + tblock("Backplane: overview, power entry, pin-out")
EXTRA = {n: open(f"_{n}.sym").read().strip().replace(f'(symbol "{n}"', f'(symbol "{lib}:{n}"', 1)
         for lib, n in (("Mechanical", "MountingHole_Pad"), ("Jumper", "SolderJumper_2_Open"), ("Device", "C"))}
root += "\t(lib_symbols\n\t\t" + "\n\t\t".join(x.replace("\n", "\n\t") for x in [CONN2] + list(EXTRA.values())) + "\n\t)\n"
# Chassis bond (Prins 2026-09-26): mounting holes are not grounded (ground loops). One plated hole H1 on net CHASSIS,
# with an open solder jumper JP1 (DC bond) and a not-fitted capacitor C1 (RF-only bond) to GND, in case a bond is needed.
root += symbol("Mechanical:MountingHole_Pad", "H1", "M3 CHASSIS", "MountingHole:MountingHole_3.2mm_M3_Pad", 215.9, 93.98, 1,
               ["1"], f"/{ROOT_UUID}", "Plated M3 hole, chassis bond point", -5.08, 5.08, bom=False)
root += glabel("CHASSIS", 215.9, 96.52)
root += symbol("Jumper:SolderJumper_2_Open", "JP1", "open", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", 241.3, 93.98, 1,
               ["1", "2"], f"/{ROOT_UUID}", "CHASSIS to GND, DC bond, open by default", -3.81, 3.81, bom=False)
root += glabel("CHASSIS", 236.22, 93.98) + glabel("GND", 246.38, 93.98)
root += symbol("Device:C", "C1", "DNP 10nF 1kV", "Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", 266.7, 93.98, 1,
               ["1", "2"], f"/{ROOT_UUID}", "CHASSIS to GND, RF-only bond, not fitted by default", -6.35, 6.35, dnp=True)
root += glabel("CHASSIS", 266.7, 90.17) + glabel("GND", 266.7, 97.79)
root += text("Chassis bond: the mounting holes are not grounded (no ground loops).\\n"
             "H1 is the only plated hole (net CHASSIS). JP1 open and C1 not fitted by default.\\n"
             "Close JP1 for a DC bond, or fit C1 for an RF-only bond.", 210.82, 106.68)
# Power entry: one Amass XT connector per rail, each rail with its own return (decided 2026-09-26).
# Board side male (PW-M), cable side female, so the live PSU harness has the shrouded contacts.
# XT30 on +5V cannot mate with the XT60 plugs of the 12 V rails.
# Polarity: the Amass datasheets show none; the KiCad Amass footprints mark pad 2 = + and pad 1 = -. Check on a real part.
PWR = [("J12", "+12V_RLY", "XT60PW-M", "Connector_AMASS:AMASS_XT60PW-M_1x02_P7.20mm_Horizontal", "Amass XT60PW-M, 30 A, relay rail"),
       ("J13", "+12V_AUX", "XT60PW-M", "Connector_AMASS:AMASS_XT60PW-M_1x02_P7.20mm_Horizontal", "Amass XT60PW-M, 30 A, clean 12 V (LoG preamp)"),
       ("J14", "+5V", "XT30PW-M", "Connector_AMASS:AMASS_XT30PW-M_1x02_P2.50mm_Horizontal", "Amass XT30PW-M, 15 A, logic rail")]
for i, (ref, net, val, fp, desc) in enumerate(PWR):
    px, py = 50.8, round(134.62 + i * 12.7, 2)
    root += symbol("Connector_Generic:Conn_01x02", ref, val, fp, px, py, 1, ["1", "2"], f"/{ROOT_UUID}", desc, -2.54, 5.08)
    root += glabel("GND", round(px - 5.08, 2), py) + glabel(net, round(px - 5.08, 2), round(py + 2.54, 2))  # pin 1 = -, pin 2 = +
root += "".join(sheet_blocks)
pinout = ("Pin-out (same on every slot, approved 2026-09-26)\\n"
          "1 to 19: row b RF zone: b1 GND, b2+b3 RF1, b4 GND, b5+b6 RF2, b7 GND, b8+b9 RF3, b10 GND,\\n"
          "  b11+b12 RF4, b13 GND, b14+b15 RF5, b16 GND, b17+b18 RF6, b19 GND. Rows a and c: GND.\\n"
          "20: GND.  21: SDA / GND / SCL.  22: ~INT / GND / ~RLY_EN.  23: PTT1 / GND / PTT2.  24: PTT3 / GND / PTT4.\\n"
          "25: SLOT_ID0 / SLOT_ID1 / SLOT_ID2.  26: SLOT_ID3 / GND / TX_ANY.  27: +12V_AUX / GND / SPARE2.\\n"
          "28: GND.  29: +5V / GND / +5V.  30: GND.  31: +12V_RLY / GND / +12V_RLY.  32: GND.\\n"
          "Slot order: Link, R1 to R4, A1 to A6. ANTk runs from the radio slots to slot Ak only (no stub).\\n"
          "RX-only line (LoG) on A6, furthest from the TX lines.")
root += text(pinout, 101.6, 125.73)
root += '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n)\n'
open("backplane.kicad_sch", "w").write(root)
print("root", ROOT_UUID, "sheets", len(SLOTS))
