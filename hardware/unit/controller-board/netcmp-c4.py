import sys, xml.etree.ElementTree as ET
# c3 reference -> c4: J3 pin p = A1 pad p; J4 pin p = A1 pad 16+p (Espressif pin numbers = esp-rs pad numbers); SDA split by JP11 (D-94)
def load(f, old):
    t=ET.parse(f).getroot(); nets=set(); comps={c.get("ref"):c.findtext("value") for c in t.find("components")}
    for n in t.find("nets").findall("net"):
        s=set()
        for nd in n.findall("node"):
            r,p=nd.get("ref"),nd.get("pin")
            if old and r=="J3": r="A1"
            elif old and r=="J4": r,p="A1",str(16+int(p))
            s.add((r,p))
        if not (len(s)==1 and next(iter(s))[0]=="A1"): nets.add(frozenset(s))
    return nets, comps
a,ca=load(sys.argv[1],True); b,cb=load(sys.argv[2],False)
sda=[n for n in a if ("A1","12") in n]; assert len(sda)==1
s=sda[0]; rest=frozenset(x for x in s if x!=("A1","12"))
a=(a-{s})|{rest|{("JP11","2")}, frozenset({("A1","12"),("JP11","1")}), frozenset({("A1","17"),("JP11","3")})}
print("parts",len(ca),len(cb),"removed",sorted(set(ca)-set(cb)),"added",sorted(set(cb)-set(ca)))
print("nets",len(a),len(b),"identical after mapping:",a==b)
for n in list(a-b)[:6]: print(" ref only:",sorted(n)[:10])
for n in list(b-a)[:6]: print(" new only:",sorted(n)[:10])
