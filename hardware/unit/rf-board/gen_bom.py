#!/usr/bin/env python3
"""Hand-assembly order BOM for the RF board (review B-3, as the controller gen_bom.py, M-67). Run from this folder with
plain python3. Input: the netlist (NETLIST). Output: production/bom_hand_assembly.csv, one line per order code, with the
first and the second source. Jellybean passives carry a specification, not a fixed order code (any maker that meets it).
Test points, mounting holes and solder jumpers (bare pads) are listed apart; DNP parts are not ordered."""
import csv, collections, os
import xml.etree.ElementTree as ET

NETLIST = "../verify/rf16.xml"
# (value, footprint name) -> (first source, second source, specification / note)
ORDER = {
    ("1u 16V X7R", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"): ("Murata GRM188R71C105KA12D", "Samsung CL10B105KO8NNNC", "MLCC 1 uF 16 V X7R 0603 (D-127)"),
    ("10n 50V X7R", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"): ("Murata GRM188R71H103KA01D", "Yageo CC0603KRX7R9BB103", "MLCC 10 nF 50 V X7R 0603 (D-190)"),
    ("4.7u 16V X7R", "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"): ("Murata GRM21BR71C475KE51L", "Samsung CL21B475KOFNNNE", "MLCC 4.7 uF 16 V X7R 0805, LDO output (>= 2.2 uF effective)"),
    ("47u 25V polymer", "CP_Elec_6.3x7.7"): ("Panasonic EEH-ZC1V470P", "Chemi-Con HHXC350ARA470MF61G", "Hybrid polymer 47 uF 35 V, 6.3 x 6.1 mm, same land as 6.3 x 7.7 (D-200; value text stays 25V)"),
    ("1u 50V X7R", "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"): ("Murata GRM21BR71H105KA12L", "Samsung CL21B105KBFNNNE", "MLCC 1 uF 50 V X7R 0805 (D-127)"),
    ("4.7p 1kV C0G", "C_1206_3216Metric_RFgap2.0"): ("Knowles 1206J1K04P70CCT", "-", "MLCC 4.7 pF 1 kV C0G 1206, +-0.25 pF, on a 2.0 mm gap land (D-202). Single source: no other stocked 4.7 pF 1 kV part found"),
    ("47p 50V C0G", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"): ("Murata GRM1885C1H470JA01D", "Samsung CL10C470JB8NNNC", "MLCC 47 pF 50 V C0G 0603, 5 %"),
    ("100n 50V X7R", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"): ("Murata GRM188R71H104KA93D", "Samsung CL10B104KB8NNNC", "MLCC 100 nF 50 V X7R 0603"),
    ("SS14", "D_SMA"): ("Vishay SS14-E3/61T", "onsemi SS14", "Schottky 1 A 40 V SMA (D-36)"),
    ("BZT52C24", "D_SOD-123"): ("Nexperia BZT52H-C24,115", "Diotec BZT52C24", "Zener 24 V SOD-123F on the SOD-123 land, surge rated (D-43, M-120)"),
    ("BZT52C15", "D_SOD-123"): ("Diodes BZT52C15-7-F", "onsemi MMSZ5245BT1G", "Zener 15 V SOD-123, Q1 VGS clamp (D-45)"),
    ("SMBJ15A", "D_SMB"): ("Littelfuse SMBJ15A", "ST SMBJ15A-TR", "TVS 600 W unidirectional, VRM 15 V, SMB (D-45)"),
    ("SMBJ6.0A", "D_SMB"): ("ST SMBJ6.0A-TR", "Littelfuse SMBJ6.0A-E", "TVS 600 W unidirectional, VRM 6.0 V, SMB (D-45)"),
    ("1N4148W", "D_SOD-123"): ("Diodes 1N4148W-7-F", "Nexperia 1N4148W,115", "Small-signal diode SOD-123"),
    ("BAS70-04", "SOT-23"): ("ST BAS70-04FILM", "MCC BAS70-04-TP", "Schottky pair in series 70 V SOT-23, detector"),
    ("1A T", "Fuse_1206_3216Metric_Pad1.42x1.75mm_HandSolder"): ("Littelfuse 0468001.NR", "Bourns SF-1206S100-2", "Fuse 1 A time-lag 1206, 63 V, 50 A breaking (D-45)"),
    ("83-798 SO-239", "SO239_83-798_StrapPad_BossRight"): ("Amphenol RF 83-1R", "Amphenol RF 83-798", "SO-239 4-hole flange, case wall; PBT, solder the strap fast (D-196)"),
    ("83-798 SO-239", "SO239_83-798_StrapPad_BossLeft"): ("Amphenol RF 83-1R", "Amphenol RF 83-798", "SO-239 4-hole flange, case wall; PBT, solder the strap fast (D-196)"),
    ("SMA jack EXP", "SMA_901-9215_StrapPad"): ("Cinch 142-0701-631", "Amphenol RF 901-9215", "SMA bulkhead jack, 4-hole flange, left wall pocket; Cinch first, the case model uses it (D-108, D-174)"),
    ("XT60PW-M", "AMASS_XT60PW-M_1x02_P7.20mm_Horizontal"): ("Amass XT60PW-M", "-", "XT60 male, PCB right angle (single maker; LCSC C98732 or TME, not at DigiKey)"),
    ("XT30PW-M", "AMASS_XT30PW-M_1x02_P2.50mm_Horizontal"): ("Amass XT30PW-M", "-", "XT30 male, PCB right angle (single maker; LCSC or TME, not at DigiKey)"),
    ("Controller header", "PinHeader_2x12_P2.54mm_Vertical"): ("Samtec TSW-112-07-L-D", "-", "Header 2 x 12, post 5.84 mm, engagement 4.89 mm in the ESQ socket (M-116)"),
    ("RTD14012F", "Relay_SPDT_Schrack-RT1-16A-FormC_RM5mm"): ("TE RTD14012F", "-", "Relay RT1 1 CO 16 A 12 VDC 400 mW, wash-tight (single maker, D-198)"),
    ("PMV50EPEA", "SOT-23"): ("Diodes DMP3056L-7", "Nexperia PMV50EPEAR", "P-MOSFET -30 V SOT-23, VGS max 25 V (D-40). PMV50EPEAR out of stock to 2027, AO3407A NRND; DMP3056L pin-out G-S-D to check on the datasheet"),
    ("BSS138BK", "SOT-23"): ("Nexperia BSS138BK,215", "Diotec MMFTN138K", "N-MOSFET 60 V (D-134)"),
    ("BC857B", "SOT-23"): ("Diodes BC857B-7-F", "Nexperia BC857B,215", "PNP 45 V SOT-23"),
    ("IRFL9014", "SOT-223-3_TabPin2"): ("Vishay IRFL9014TRPBF-BE3", "onsemi NTF2955T1G", "P-MOSFET -60 V SOT-223 (C-17, D-195)"),
    ("1M HV", "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"): ("Vishay VR25000001004FA500", "Vishay HVR2500001004FR500 / Yageo HHV-25FR-52-1M", "1 M HV axial 0207, 1600 V DC limiting, about 7 kV pulse (D-32)"),
    ("0R wire link", "WireLink_P7.62mm_D1.0mm"): ("generic", "generic", "Tinned copper wire 0.8 mm, 7.62 mm pitch (D-109)"),
    ("10k x4", "R_Array_Convex_4x0603"): ("Bourns CAY16-103J4LF", "Yageo YC164-JR-0710KL", "Resistor array 4 x 10k convex 1206 body (D-121). CAT16 is concave: do not order"),
    ("LP2985-33", "SOT-23-5"): ("TI LP2985-33DBVR", "ST LD2985BM33R", "LDO 3.3 V 150 mA"),
    ("LM2901", "SOIC-14_3.9x8.7mm_P1.27mm"): ("TI LM2901DR", "ST LM2901DT", "Quad comparator SOIC-14 (D-47)"),
    ("PCA9539", "TSSOP-24_4.4x7.8mm_P0.65mm"): ("NXP PCA9539PW,118", "TI TCA9539PWR / Diodes PI4IOE5V9539LEX", "I/O expander. Plain PCA9539 only, never PCA9539R (D-133)"),
}
GENERIC_R = {"R_0603_1608Metric_Pad0.98x0.95mm_HandSolder": "Thick film 0603 1 % 0.1 W (Yageo RC0603FR-07, Vishay CRCW0603, any maker)",
             "R_0805_2012Metric_Pad1.20x1.40mm_HandSolder": "Thick film 0805 1 % 0.125 W (Yageo RC0805FR-07, any maker)",
             "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder": "0R jumper 1206 (Yageo RC1206JR-070RL, any maker)"}
NO_PART = ("TestPoint", "MountingHole", "SolderJumper")
EXTRA = []

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
