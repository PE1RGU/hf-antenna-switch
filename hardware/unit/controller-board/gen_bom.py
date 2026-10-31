#!/usr/bin/env python3
"""Hand-assembly BOM for the controller board (order-readiness pass, M-67). Run from this folder with plain python3.
Input: the netlist (NETLIST). Output: production/bom_hand_assembly.csv, one line per order code, with the first and the
second source. Jellybean passives carry a specification, not a fixed order code (any maker that meets it).
Test points (bare pads), the mounting hole and DNP parts are listed apart; DNP parts are not ordered."""
import csv, collections
import xml.etree.ElementTree as ET

NETLIST = "../verify/ctl17.xml"
# (value, footprint name) -> (first source, second source, specification / note)
ORDER = {
    ("1u 16V X7R", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"): ("Murata GRM188R71C105KA12D", "Samsung CL10B105KO8NNNC", "MLCC 1 uF 16 V X7R 0603 (D-127)"),
    ("10n 50V X7R", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"): ("Murata GRM188R71H103KA01D", "Yageo CC0603KRX7R9BB103", "MLCC 10 nF 50 V X7R 0603, LDO bypass"),
    ("4.7u 16V X7R", "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"): ("Murata GRM21BR71C475KE51L", "Samsung CL21B475KOFNNNE", "MLCC 4.7 uF 16 V X7R 0805, LDO output (>= 2.2 uF effective)"),
    ("SMBJ15CA", "D_SMB"): ("ST SMBJ15CA-TR", "Littelfuse SMBJ15CA", "TVS 600 W bidirectional, VR 15 V"),
    ("1N4148W", "D_SOD-123"): ("Diodes 1N4148W-7-F", "Nexperia 1N4148W,115", "Small-signal diode SOD-123"),
    ("2036-09-B2LF", "GDT_3Pin_P4.40mm_Bourns-2036-B2_Littelfuse-SL1003A-R"): ("Bourns 2036-09-B2LF", "Littelfuse SL1003A090R-001", "3-electrode GDT 90 V (D-58, D-149)"),
    ("RJ45 LINK", "RJ45_8P8C_Unshielded_TabDown"): ("Wurth 615008137121", "Molex 95501-2881", "RJ45 8P8C unshielded, tab down (D-138)"),
    ("to RF board J14", "PinSocket_2x12_P2.54mm_Vertical"): ("Samtec ESQ-112-33-G-D", "Samtec ESW-112-33-G-D", "Elevated socket 2 x 12, 16.13 mm, fitted on the bottom side (D-139)"),
    ("51u CMC", "L_CMC_TDK_ACT45B"): ("TDK ACT45B-510-2P-TL003", "Murata DLW43SH510XK2L / Coilcraft 1812CAN-513NRC", "Common-mode choke 51 uH 1812 (D-149, D-151)"),
    ("BSS138BK", "SOT-23"): ("Nexperia BSS138BK,215", "Diotec MMFTN138K", "N-MOSFET (D-134)"),
    ("47R", "R_MELF_MMB-0207"): ("Vishay MMB02070C4709FB200", "TE Neohm SMA-A 0207 47R 1 %", "Thin-film MELF 0207 1 W, pulse (C-39, D-151)"),
    ("220R", "R_MiniMELF_MMA-0204"): ("Vishay MMA02040C2200FB300", "TE Neohm SMA-A 0204 220R 1 %", "Thin-film MiniMELF 0204, pulse (C-39, D-151)"),
    ("VO2611", "DIP-8_W7.62mm"): ("Vishay VO2611", "Broadcom HCPL-2611-000E", "Opto 10 MBd, DIP-8 through hole"),
    ("PC817X", "DIP-4_W7.62mm"): ("Sharp PC817X2NSZ9F", "Lite-On LTV-817B / Everlight EL817(B)", "Opto, CTR rank B or better, DIP-4"),
    ("TLP176AM", "SOP-4_P2.54mm_PhotoRelay_LongPad"): ("Toshiba TLP176AM(TPL,E)", "Panasonic AQY212G3HS", "Photorelay form A 60 V (D-101)"),
    ("74LVC1G14", "SOT-23-5"): ("Nexperia 74LVC1G14GV,125", "TI SN74LVC1G14DBVR", "Schmitt inverter"),
    ("74LVC1G08", "SOT-23-5"): ("Nexperia 74LVC1G08GV,125", "TI SN74LVC1G08DBVR", "2-input AND"),
    ("74LVC1G02", "SOT-23-5"): ("Nexperia 74LVC1G02GV,125", "TI SN74LVC1G02DBVR", "2-input NOR"),
    ("74LVC1G27", "SOT-23-6"): ("TI SN74LVC1G27DBVR", "Nexperia 74LVC1G27GV", "3-input NOR, SOT-23-6 / SOT457, same pin-out (D-155). Candidate: Diodes 74LVC1G27W6-7 (pin-out to check)"),
    ("74LVC1G74", "VSSOP-8_2.3x2mm_P0.5mm"): ("TI SN74LVC1G74DCUR", "Nexperia 74LVC2G74DC", "D flip-flop, VSSOP-8 0.5 mm (D-154). Same pin-out, JEDEC MO-187 CA"),
    ("LP2985-33", "SOT-23-5"): ("TI LP2985-33DBVR", "ST LD2985BM33R", "LDO 3.3 V 150 mA"),
    ("TPS3823A-33", "SOT-23-5"): ("TI TPS3823A-33DBVR", "ADI MAX823SEUK+T / Diodes APX823-29W5G-7", "Supervisor and watchdog (D-148)"),
    ("ESP32-C3-DevKit-RUST-1", "ESP32-C3-DevKit-RUST_Socket"): ("Espressif ESP32-C3-DevKit-RUST-1", "Espressif ESP32-C3-DevKit-RUST-2 (JP11 2-1)", "MCU board; sockets on the lines below (D-55, D-94, D-95)"),
    ("SDA SEL", "SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm_NumberLabels"): ("-", "-", "Solder jumper, 1-2 bridged by copper for RUST-1; RUST-2: cut 1-2, bridge 2-3 (no part, D-192)"),
}
GENERIC_R = {"R_0603_1608Metric_Pad0.98x0.95mm_HandSolder": "Thick film 0603 1 % 0.1 W (Yageo RC0603FR-07, Vishay CRCW0603, any maker)",
             "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder": "0R jumper 1206 (Yageo RC1206JR-070RL, any maker)"}
EXTRA = [("A1 sockets", "Sullins PPPC161LFBN-RC", "-", "Female header 1 x 16 gold, DevKit left side (D-95)", 1),
         ("A1 sockets", "Sullins PPPC121LFBN-RC", "-", "Female header 1 x 12 gold, DevKit right side (D-95)", 1)]

root = ET.parse(NETLIST).getroot()
groups, dnp, other = collections.OrderedDict(), [], []
for c in root.iter("comp"):
    ref, val, fp = c.get("ref"), c.findtext("value"), c.findtext("footprint").split(":")[1]
    props = {p.get("name") for p in c.iter("property")}
    if "dnp" in props: dnp.append((ref, val, fp)); continue
    if ref.startswith(("TP", "H")): other.append((ref, val, fp)); continue
    key = (val, fp)
    if key not in ORDER and fp in GENERIC_R:
        ORDER[key] = ("generic", "generic", f"{val} {GENERIC_R[fp]}")
    assert key in ORDER, ("no order line for", ref, key)
    groups.setdefault(key, []).append(ref)
nat = lambda r: (r.rstrip("0123456789"), int("".join(ch for ch in r if ch.isdigit()) or 0))
with open("production/bom_hand_assembly.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Qty per board", "References", "Value", "Footprint", "First source", "Second source", "Specification / note"])
    for (val, fp), refs in sorted(groups.items(), key=lambda kv: nat(sorted(kv[1], key=nat)[0])):
        a, b, n = ORDER[(val, fp)]
        w.writerow([len(refs), " ".join(sorted(refs, key=nat)), val, fp, a, b, n])
    for ref, a, b, n, q in EXTRA:
        w.writerow([q, ref, "", "", a, b, n])
    w.writerow([]); w.writerow(["Not fitted (DNP): " + " ".join(sorted((r for r, _, _ in dnp), key=nat))])
    w.writerow(["No part (pads, holes): " + " ".join(sorted((r for r, _, _ in other), key=nat))])
print("lines", len(groups) + len(EXTRA), "parts", sum(len(v) for v in groups.values()) + 2, "dnp", len(dnp), "no part", len(other))
