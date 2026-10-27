"""Read a KiCad XML netlist: parts {ref: (value, lib:part)} and nets {name: [(ref, pin, pinfunction)]}.

links: series parts that the logic model treats as a short (0R links, common-mode choke windings),
       as (ref, pin_a, pin_b). The two nets join; the name kept is the one not ending in "_J" and not auto-named.
drop:  references left out of the net member lists (filter capacitors, test points, the links themselves).
       Their own checks use load() without links and drop.
"""
import xml.etree.ElementTree as ET
def load(fn, links=(), drop=()):
    r = ET.parse(fn).getroot()
    parts = {c.get("ref"): (c.findtext("value"), c.find("libsource").get("lib") + ":" + c.find("libsource").get("part"))
             for c in r.find("components")}
    nets = {n.get("name"): [(x.get("ref"), x.get("pin"), x.get("pinfunction") or "") for x in n.findall("node")] for n in r.find("nets")}
    if links:
        pinnet = {(ref, pin): name for name, ns in nets.items() for ref, pin, _ in ns}
        rank = lambda n: (n.startswith(("Net-(", "unconnected-")), n.endswith("_J"), n)
        for ref, a, b in links:
            na, nb = pinnet[(ref, a)], pinnet[(ref, b)]
            if na == nb: continue
            keep, gone = sorted((na, nb), key=rank)
            nets[keep] += nets.pop(gone)
            for (rr, pp), nn in list(pinnet.items()):
                if nn == gone: pinnet[(rr, pp)] = keep
    drop = set(drop) | {ref for ref, _, _ in links}
    nets = {n: [x for x in ns if x[0] not in drop] for n, ns in nets.items()}
    pinnet = {(ref, pin): name for name, ns in nets.items() for ref, pin, _ in ns}
    return parts, nets, pinnet

def load_model(fn):
    """load() with the series links and the filter / test parts of the hardware-design-rules v2.2 review (D-120 to D-130)
    taken out, so the logic models see the same nets as before. Board found from its parts; older netlists load unchanged."""
    parts = load(fn)[0]
    links, drop = [], []
    if "R1201" in parts:                                     # RF board v11: J14 filter links, +3V3 link
        links = [(r, "1", "2") for r in parts if r.startswith("R12") or r == "R4"]
        drop = [r for r in parts if r.startswith(("C12", "TP", "RN"))] + ["C6", "C7", "C101", "C201", "C301"]
    elif "U12" in parts and "L1" in parts:                   # controller board c7: chokes, watchdog and +3V3 links
        links = [("R64", "1", "2"), ("R65", "1", "2")] + [(f"L{k}", a, b) for k in (1, 2, 3, 4) for a, b in (("1", "2"), ("3", "4"))]
        drop = [r for r in parts if r.startswith("TP")] + [f"C{c}" for c in range(21, 29)]
    elif "U61" in parts and any(r.startswith("TP") for r in parts):   # shack interface a13
        links = [(r, a, b) for r, a, b in SHACK_LINKS if r in parts]
        drop = [r for r in parts if r.startswith("TP")] + [r for r in SHACK_DROP if r in parts]
    return load(fn, links, drop)
SHACK_LINKS = [("R5", "1", "2"), ("R6", "1", "2")] + [(f"L{k}", a, b) for k in (1, 2, 3, 4) for a, b in (("1", "2"), ("3", "4"))]
SHACK_DROP = [f"C{c}" for c in range(22, 30)]                # shack interface a13: rail links, chokes, Y-capacitor footprints
