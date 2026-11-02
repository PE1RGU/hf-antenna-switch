#!/usr/bin/env python3
"""Hand-assembly order BOM for the shack interface (review B-3, as the controller gen_bom.py, M-67). Run from this folder
with plain python3. Input: the netlist (NETLIST). Output: production/bom_hand_assembly.csv, one line per order code, with
the first and the second source. Jellybean passives carry a specification, not a fixed order code (any maker that meets it).
Test points, the mounting hole and solder jumpers (bare pads) are listed apart; DNP parts are not ordered."""
import csv, collections, os
import xml.etree.ElementTree as ET

NETLIST = "../unit/verify/si18.xml"
# (value, footprint name) -> (first source, second source, specification / note)
ORDER = {
    ("ESP32-C3-DevKit-RUST-1", "ESP32-C3-DevKit-RUST_Socket"): ("Espressif ESP32-C3-DevKit-RUST-1", "Espressif ESP32-C3-DevKit-RUST-2 (JP61 cut 1-2, bridge 2-3)", "MCU board; sockets on the lines below (D-55, D-95, D-192)"),
    ("47u 35V", "CP_Radial_D6.3mm_P2.50mm"): ("Wurth 860080573003", "Panasonic EEU-FR1V680 (68 uF)", "Aluminium 47 uF 35 V radial D 6.3 mm, pitch 2.5 mm, 105 C, >= 2000 h; 12.5 mm high, below the L7805 (D-200)"),
    ("330n 50V X7R", "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"): ("Murata GRM21BR71H334KA01L", "Samsung CL21B334KBFNNNE", "MLCC 330 nF 50 V X7R 0805, L7805 input"),
    ("100n 50V X7R", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"): ("Murata GRM188R71H104KA93D", "Samsung CL10B104KB8NNNC", "MLCC 100 nF 50 V X7R 0603"),
    ("10u 16V X7R", "C_1206_3216Metric_Pad1.33x1.80mm_HandSolder"): ("Murata GRM31CR71C106KAC7L", "Samsung CL31B106KOHNNNE", "MLCC 10 uF 16 V X7R 1206"),
    ("22u 16V X7R", "C_1210_3225Metric_Pad1.33x2.70mm_HandSolder"): ("Murata GRM32ER71C226KE18L", "Samsung CL32B226KOJNNNE", "MLCC 22 uF 16 V X7R 1210, LD1117 output (>= 10 uF effective)"),
    ("1u 16V X7R", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"): ("Murata GRM188R71C105KA12D", "Samsung CL10B105KO8NNNC", "MLCC 1 uF 16 V X7R 0603 (D-127)"),
    ("10n 1kV", "C_1206_3216Metric_Pad1.33x1.80mm_HandSolder"): ("Yageo CC1206KKX7RCBB103", "Kyocera AVX KGF31AR73A103KU", "MLCC 10 nF 1 kV X7R 1206, radio GND to CHASSIS bond"),
    ("1n C0G", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"): ("Murata GRM1885C1H102JA01D", "Samsung CL10C102JB8NNNC", "MLCC 1 nF 50 V C0G 0603 (M-117)"),
    ("SS34", "D_SMC"): ("Vishay SS34-M3/57T", "onsemi SS34", "Schottky 3 A 40 V SMC, reverse polarity"),
    ("SMBJ16A", "D_SMB"): ("Littelfuse SMBJ16A", "ST SMBJ16A-TR", "TVS 600 W unidirectional, VRM 16 V, SMB"),
    ("SMBJ15CA", "D_SMB"): ("ST SMBJ15CA-TR", "Littelfuse SMBJ15CA", "TVS 600 W bidirectional, VRM 15 V, SMB (D-58)"),
    ("1N4148W", "D_SOD-123"): ("Diodes 1N4148W-7-F", "Nexperia 1N4148W,115", "Small-signal diode SOD-123"),
    ("BZX384-C5V1", "D_SOD-323_HandSoldering"): ("Vishay BZX384C5V1-E3-08", "Nexperia BZX384-C5V1,115 / onsemi MM3Z5V1T1G", "Zener 5.1 V SOD-323 (A-18)"),
    ("PESD15VL1BA", "D_SOD-323_HandSoldering"): ("Littelfuse SD15C-01FTG", "Bourns CDSOD323-T15C", "ESD diode bidirectional, VRWM 15 V, SOD-323; capacitance negligible beside the 1 nF C0G on each line. PESD15VL1BA discontinued at DigiKey"),
    ("500mA T", "Fuse_1206_3216Metric"): ("Bourns SF-1206S050-2", "Littelfuse 0468.500NR", "Fuse 500 mA slow 1206, 63 V, 50 A breaking; short at 14.4 V gives at most 32 A (M-121)"),
    ("2036-09-B2LF", "GDT_3Pin_P4.40mm_Bourns-2036-B2_Littelfuse-SL1003A-R"): ("Bourns 2036-09-B2LF", "Littelfuse SL1003A090R-001", "3-electrode GDT 90 V (D-58, D-149)"),
    ("RJ45 LINK", "RJ45_8P8C_Unshielded_TabDown"): ("Wurth 615008137121", "Molex 95501-2881", "RJ45 8P8C unshielded, tab down (D-138)"),
    ("KILL switch", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"): ("JST B2B-XH-A(LF)(SN)", "-", "JST XH 2-pin header, vertical (M-117)"),
    ("KILL state", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"): ("JST B2B-XH-A(LF)(SN)", "-", "JST XH 2-pin header, vertical (M-117)"),
    ("Front panel", "JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical"): ("JST B4B-XH-A(LF)(SN)", "-", "JST XH 4-pin header, vertical (M-117)"),
    ("13.8 V IN", "AMASS_XT60PW-M_1x02_P7.20mm_Horizontal"): ("Amass XT60PW-M", "-", "XT60 male, PCB right angle (single maker)"),
    ("R1 mini-DIN", "MiniDIN-8_SameSky_MD-80SM_Horizontal"): ("Same Sky MD-80SM", "Kycon KMDGX-8S-BS", "Mini-DIN 8 socket, right angle, shielded (M-28)"),
    ("R2 mini-DIN", "MiniDIN-8_SameSky_MD-80SM_Horizontal"): ("Same Sky MD-80SM", "Kycon KMDGX-8S-BS", "Mini-DIN 8 socket, right angle, shielded (M-28)"),
    ("R3 mini-DIN", "MiniDIN-8_SameSky_MD-80SM_Horizontal"): ("Same Sky MD-80SM", "Kycon KMDGX-8S-BS", "Mini-DIN 8 socket, right angle, shielded (M-28)"),
    ("USB4105-GF-A", "USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal"): ("GCT USB4105-GF-A", "Same Sky UJ20-C-H-G-SMT-1-P16-TR", "USB-C receptacle 16P (D-96)"),
    ("DISPLAY", "PinHeader_1x08_P2.54mm_Vertical"): ("Wurth 61300811121", "Samtec TSW-108-07-G-S", "Pin header 1 x 8, 2.54 mm, vertical, gold"),
    ("INH LEVEL", "PinHeader_1x03_P2.54mm_Vertical"): ("Wurth 61300311121", "Samtec TSW-103-07-G-S", "Pin header 1 x 3, 2.54 mm, vertical, gold"),
    ("SENSE A", "PinHeader_1x03_P2.54mm_Vertical"): ("Wurth 61300311121", "Samtec TSW-103-07-G-S", "Pin header 1 x 3, 2.54 mm, vertical, gold"),
    ("SENSE K", "PinHeader_1x03_P2.54mm_Vertical"): ("Wurth 61300311121", "Samtec TSW-103-07-G-S", "Pin header 1 x 3, 2.54 mm, vertical, gold"),
    ("51u CMC", "L_CMC_TDK_ACT45B"): ("TDK ACT45B-510-2P-TL003", "Murata DLW43SH510XK2L / Coilcraft 1812CAN-513NRC", "Common-mode choke 51 uH 1812 (D-149, D-151)"),
    ("BCP53-16", "SOT-223-3_TabPin2"): ("onsemi BCP53-16T1G", "Nexperia BCP53-16,115", "PNP 80 V 1 A SOT-223"),
    ("BC857B", "SOT-23"): ("Diodes BC857B-7-F", "Nexperia BC857B,215", "PNP 45 V SOT-23"),
    ("BSS138BK", "SOT-23"): ("Nexperia BSS138BK,215", "Diotec MMFTN138K", "N-MOSFET 60 V (D-134)"),
    ("BC847B", "SOT-23"): ("Nexperia BC847B,215", "Diodes BC847B-7-F", "NPN 45 V SOT-23"),
    ("47R", "R_MELF_MMB-0207"): ("Vishay MMB02070C4709FB200", "TE Neohm SMA-A 0207 47R 1 %", "Thin-film MELF 0207 1 W, pulse (D-58)"),
    ("2k2", "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder"): ("generic", "generic", "2k2 thick film 1206 1 % 0.25 W (79 mW at 14.4 V, C-23)"),
    ("L7805CV", "TO-220-3_Vertical"): ("ST L7805CV", "TI UA7805CKCT / onsemi MC7805CTG", "5 V regulator TO-220, insulating pad on the wall (D-82)"),
    ("LD1117S33CTR", "SOT-223-3_TabPin2"): ("ST LD1117S33CTR", "Diodes AZ1117CH-3.3TRG1", "LDO 3.3 V 800 mA SOT-223 (D-81)"),
    ("TPS3823A-33", "SOT-23-5"): ("ADI MAX823SEUK+T", "TI TPS3823A-33DBVR / Diodes APX823-29W5G-7", "Supervisor and watchdog (D-148, D-195)"),
    ("74LVC1G74", "VSSOP-8_2.3x2mm_P0.5mm"): ("TI SN74LVC1G74DCUR", "Nexperia 74LVC1G74DC,125", "D flip-flop, VSSOP-8 0.5 mm (D-154, D-190)"),
    ("PCA9539", "TSSOP-24_4.4x7.8mm_P0.65mm"): ("NXP PCA9539PW,118", "TI TCA9539PWR / Diodes PI4IOE5V9539LEX", "I/O expander. Plain PCA9539 only, never PCA9539R (D-133)"),
    ("74LVC1G14", "SOT-23-5"): ("Nexperia 74LVC1G14GV,125", "TI SN74LVC1G14DBVR", "Schmitt inverter"),
    ("74LVC1G08", "SOT-23-5"): ("Nexperia 74LVC1G08GV,125", "TI SN74LVC1G08DBVR", "2-input AND"),
    ("74LVC1G02", "SOT-23-5"): ("Nexperia 74LVC1G02GV,125", "TI SN74LVC1G02DBVR", "2-input NOR"),
    ("USBLC6-2SC6", "SOT-23-6"): ("ST USBLC6-2SC6", "UMW USBLC6-2SC6", "ESD array USB (C-26)"),
    ("TLP4176G", "SOP-4_P2.54mm_PhotoRelay_LongPad"): ("Panasonic AQY412S", "Toshiba TLP4176G(TP,M,F)", "Photorelay form B, TX INH, common long-pad footprint. TLP4176G out of stock at DigiKey; AQY412S 60 V 0.5 A"),
    ("TLP176AM", "SOP-4_P2.54mm_PhotoRelay_LongPad"): ("Toshiba TLP176AM(TPL,E)", "Panasonic AQY212G3HS", "Photorelay form A 60 V (D-101)"),
    ("PC817X", "DIP-4_W7.62mm"): ("Sharp PC817X2NSZ9F", "Lite-On LTV-817B / Everlight EL817(B)", "Opto, CTR rank B or better, DIP-4 (D-78)"),
}
GENERIC_R = {"R_0603_1608Metric_Pad0.98x0.95mm_HandSolder": "Thick film 0603 1 % 0.1 W (Yageo RC0603FR-07, Vishay CRCW0603, any maker)",
             "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder": "0R jumper 1206 (Yageo RC1206JR-070RL, any maker)"}
NO_PART = ("TestPoint", "MountingHole", "SolderJumper")
EXTRA = [("A1 sockets", "Sullins PPPC161LFBN-RC", "-", "Female header 1 x 16 gold, DevKit left side (D-95)", 1),
         ("A1 sockets", "Sullins PPPC121LFBN-RC", "-", "Female header 1 x 12 gold, DevKit right side (D-95)", 1),
         ("JP201-JP406 shunts", "Wurth 60900213421", "Samtec SNT-100-BK-G", "Jumper shunt 2.54 mm, one per 1 x 3 header", 9),
         ("J2 J7 mating", "JST XHP-2", "-", "Housing 2-pin, wiring to the KILL switch (not on the board)", 2),
         ("J6 mating", "JST XHP-4", "-", "Housing 4-pin, wiring to the front panel (not on the board)", 1),
         ("J2 J6 J7 crimps", "JST SXH-001T-P0.6", "-", "Crimp contact XH, 26 to 22 AWG (8 needed, order spares)", 8)]

root = ET.parse(NETLIST).getroot()
groups, dnp, other = collections.OrderedDict(), [], []
for c in root.iter("comp"):
    ref, val, fp = c.get("ref"), c.findtext("value"), c.findtext("footprint").split(":")[1]
    props = {p.get("name") for p in c.iter("property")}
    if "dnp" in props: dnp.append((ref, val, fp)); continue
    if fp.startswith(NO_PART): other.append((ref, val, fp)); continue
    key = (val, fp)
    if key not in ORDER and fp in GENERIC_R:
        ORDER[key] = ("generic", "generic", f"{val} {GENERIC_R[fp]}")
    assert key in ORDER, ("no order line for", ref, key)
    assert not any(s.startswith("@") for s in ORDER[key]), ("open order line", ref, key)
    groups.setdefault(key, []).append(ref)
assert not any(s.startswith("@") for e in EXTRA for s in e[1:3]), "open extra line"
nat = lambda r: (r.rstrip("0123456789"), int("".join(ch for ch in r if ch.isdigit()) or 0))
os.makedirs("production", exist_ok=True)
with open("production/bom_hand_assembly.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Qty per board", "References", "Value", "Footprint", "First source", "Second source", "Specification / note"])
    for (val, fp), refs in sorted(groups.items(), key=lambda kv: nat(sorted(kv[1], key=nat)[0])):
        a, b, n = ORDER[(val, fp)]
        w.writerow([len(refs), " ".join(sorted(refs, key=nat)), val, fp, a, b, n])
    for ref, a, b, n, q in EXTRA:
        w.writerow([q, ref, "", "", a, b, n])
    w.writerow([]); w.writerow(["Not fitted (DNP): " + " ".join(sorted((r for r, _, _ in dnp), key=nat))])
    w.writerow(["No part (pads, holes, solder jumpers): " + " ".join(sorted((r for r, _, _ in other), key=nat))])
print("lines", len(groups) + len(EXTRA), "parts", sum(len(v) for v in groups.values()) + sum(e[4] for e in EXTRA), "dnp", len(dnp), "no part", len(other))
