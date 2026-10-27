import sys, xml.etree.ElementTree as ET
# a6 reference -> a7: J4 pin p = A1 pad p; J5 pin 11 (ENABLE) = A1 pad 27 (esp-rs pad numbers, D-93); SDA split by JP61 (D-94); U5 expander pins regrouped (D-92); port swaps as netcmp2
SW={("U",2):{"1":"2","2":"1"},("U",4):{"3":"4","4":"3"},("JP",2):{"1":"3","3":"1"}}
OLD=["KEY_R1","KEY_R2","KEY_R3","SW_STOP_N","LED_R1","LED_R2","LED_R3","R3_TX","LATCHED","KILL_S","BAND_A","BAND_B","BAND_C","BAND_D","R1_TX","R2_TX"]
NEW=["SW_STOP_N","R1_TX","KEY_R1","BAND_D","BAND_A","BAND_B","BAND_C","LED_R1","KEY_R2","R2_TX","LED_R2","KEY_R3","R3_TX","LED_R3","KILL_S","LATCHED"]
pn=lambda i: str(4+i) if i<8 else str(13+i-8)
U5={pn(i):pn(NEW.index(s)) for i,s in enumerate(OLD)}
def load(f, old):
    t=ET.parse(f).getroot(); nets=set(); comps={c.get("ref"):c.findtext("value") for c in t.find("components")}
    for n in t.find("nets").findall("net"):
        s=set()
        for nd in n.findall("node"):
            r,p=nd.get("ref"),nd.get("pin")
            if old:
                if r=="J4": r="A1"
                elif r=="J5": r,p="A1",{"11":"27"}.get(p,"J5-"+p)   # J5 pin 11 = ENABLE = A1 pad 27 (EN, esp-rs pad numbers); other J5 pins not connected
                elif r=="U5": p=U5.get(p,p)
            else:
                pre="JP" if r.startswith("JP") else r[0]; num=r[len(pre):]
                if r in ("R61","R63"): p={"1":"2","2":"1"}[p]   # drawn the other way round (equivalent pins)
                if num.isdigit() and 200<=int(num)<500 and (pre,int(num)%100) in SW: p=SW[(pre,int(num)%100)].get(p,p)
            s.add((r,p))
        if not (len(s) == 1 and next(iter(s))[0] == "A1"): nets.add(frozenset(s))   # unconnected DevKit pads: 14 old right pins, 12 new
    return nets, comps
a,ca=load(sys.argv[1],True); b,cb=load(sys.argv[2],False)
old_sda=frozenset({("A1","12"),("U5","23")})      # D-94: SDA select jumper JP61 between U5 SDA and DevKit pads 12 / 17
if old_sda in a:
    a=(a-{old_sda})|{frozenset({("U5","23"),("JP61","2")}),frozenset({("A1","12"),("JP61","1")}),frozenset({("A1","17"),("JP61","3")})}
print("parts",len(ca),len(cb),"removed",sorted(set(ca)-set(cb)),"added",sorted(set(cb)-set(ca)))
print("nets",len(a),len(b),"identical after mapping:",a==b)
for n in list(a-b)[:8]: print(" ref only:",sorted(n))
for n in list(b-a)[:8]: print(" new only:",sorted(n))
