#!/usr/bin/env python3
"""Generate the site architecture page: shack head, buried run, garden RVS box."""

W, H = 1220, 640
s = []
a = s.append

def box(x, y, w, h, title, lines, cls="", align="middle"):
    a(f'<rect class="mod{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>')
    tx = x + w/2 if align == "middle" else x + 8
    a(f'<text class="t{cls}" x="{tx}" y="{y+17}" text-anchor="{align if align=="middle" else "start"}">{title}</text>')
    for k, ln in enumerate(lines):
        a(f'<text class="d{cls}" x="{tx}" y="{y+33+k*14}" text-anchor="{align if align=="middle" else "start"}">{ln}</text>')

def line(x1, y1, x2, y2, cls="rf", arrow=False):
    m = ' marker-end="url(#arr)"' if arrow else ""
    a(f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{m}/>')

def poly(pts, cls="ctl", arrow=False):
    m = ' marker-end="url(#arr)"' if arrow else ""
    a(f'<polyline class="{cls}" points="{" ".join(f"{x},{y}" for x, y in pts)}"{m}/>')

def label(x, y, txt, anchor="start", cls="d"):
    a(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{txt}</text>')

def choke(x, y):
    a(f'<rect class="choke" x="{x-9}" y="{y-6}" width="18" height="12" rx="2"/>')

a(f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Site architecture: a shack head in the basement with the controller and panel, a buried run of coax, Cat6 and mains, and the stainless garden box at the mast base holding the link card, relay matrix, linear PSU and VHF pass-through, with chokes at every cable entry">')
a('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>')

# zones
label(30, 40, "Basement shack", cls="sec")
label(400, 40, "Buried run · ~20–25 m", cls="sec")
label(680, 40, "Garden · RVS box", cls="sec")
a('<line class="zone" x1="385" y1="50" x2="385" y2="600"/>')
a('<line class="zone" x1="640" y1="50" x2="640" y2="600"/>')
# steel box
a('<rect class="steel" x="660" y="60" width="510" height="510" rx="4"/>')
label(668, 564, "RVS box · IP66 · glands · drain · bonded to mast earth", cls="d")

# ---------- shack ----------
box(30, 70, 330, 120, "Shack head", ["Controller card: ESP32-S3 · USB-C → host PC · Wi-Fi", "OLED + encoder · MODE · ACK · KILL switch", "isolated RS-485 · PTT loop driver · KILL loop", "12 V from station supply · Cat6 choke at exit"], align="left")
box(30, 250, 150, 60, "FT-710", ["HF · 100 W", "PTT out (TX GND)"], " ext")
poly([(105, 250), (105, 190)], "ctl", arrow=True); label(111, 224, "PTT → PTT loop", cls="d")
box(30, 335, 150, 60, "Airspy HF+", ["RX-only SDR", "USB direct to PC"], " ext")
box(30, 430, 150, 60, "FTM-510D", ["2 m / 70 cm", "not via matrix"], " ext")
box(30, 505, 150, 50, "House 230 V", ["RCD · own breaker"], " ext")

# ---------- run ----------
# Cat6 #1
line(360, 140, 680, 140, "ctl"); choke(375, 140); choke(650, 140)
label(400, 134, "Cat6 #1 · RS-485 · PTT loop · KILL loop", cls="d")
# Cat6 #2 spare
line(360, 175, 660, 175, "ctl spare"); label(400, 169, "Cat6 #2 · spare", cls="d spare")
# coax 1 FT-710
line(180, 280, 680, 280, "rf"); choke(650, 280); label(400, 274, "coax 1 · FT-710 line", cls="d")
# coax 2 Airspy
line(180, 365, 680, 365, "rf"); choke(650, 365); label(400, 359, "coax 2 · Airspy line", cls="d")
# coax 3 VHF
line(180, 460, 1040, 460, "rf"); choke(650, 460); label(400, 454, "coax 3 · VHF, straight through", cls="d")
# 230 V
poly([(180, 530), (1000, 530)], "mains", arrow=True); label(400, 524, "230 V · power cable", cls="d")
label(660, 606, "▮ = FT240-31, 9 turns, whole cable, at box entry (RFI log row 3) and at head exit", cls="d")

# ---------- garden box ----------
box(680, 90, 200, 110, "Link card · slot 0", ["isolated RS-485 ↔ I2C bridge MCU", "PTT loop opto → PTT[1] (hardware)", "KILL loop → gate (hardware)", "local WDT · supervisor → /RLY_EN", "link timeout → safe state"])
poly([(770, 200), (770, 230)], "ctl", arrow=True); label(776, 220, "backplane", cls="d")
box(1000, 500, 160, 60, "Linear PSU", ["toroid → bridge → linear", "12 V RLY · 5 V · no switchers"])
poly([(1010, 500), (1010, 400), (1000, 400)], "ctl", arrow=True); label(1004, 426, "+12V RLY · +5V", "end", cls="d")
# matrix chassis
a('<rect class="mod" x="680" y="230" width="320" height="180" rx="3"/>')
label(688, 248, "Relay matrix chassis", cls="t")
for k, ln in enumerate([
    "Radio Port 1 · FT-710 line · TX/RX split (K0)",
    "Radio Port 2 · RX variant · Airspy line · TX-mute",
    "2 spare radio slots",
    "Antenna Port 1 · G5RV · 4:1 balun outside",
    "Antenna Port 2 · loop · RX-only · bias-T for preamp",
    "Antenna Port 3 · vertical (planned) · 3 spare",
    "RF bus board · 6 lines · backplane",
]):
    label(688, 266 + k*14, ln, cls="d")
label(688, 400, "PTT from backplane line, not front jack", cls="d")
# antennas out the top
for x, name, sub in ((895, "G5RV", "mast"), (945, "LoG", "ground"), (995, "Vert.", "planned")):
    cls = " spare" if name == "Vert." else ""
    line(x, 230, x, 60, "rf" + cls)
    label(x, 24, name, "middle", cls="t" + cls)
    label(x, 37, sub, "middle", cls="d" + cls)
# VHF passthrough
box(1040, 430, 110, 60, "VHF pass-through", ["2× bulkhead SO-239", "choke · no relay"])
line(1095, 430, 1095, 60, "rf")
label(1095, 24, "GP-6N", "middle", cls="t"); label(1095, 37, "mast top", "middle", cls="d")

a('</svg>')
svg = "\n".join(s)

html = f'''<title>Garden Matrix Site Plan</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg:#f2f3ef; --panel:#fbfbf8; --ink:#1c232b; --ink2:#5b6570; --line:#8e979f; --grid:#d8dbd4;
  --ctl:#2b7a78; --rf:#1c232b; --mains:#a8432b; --spare:#a9b0b6; --steel:#7f8a94;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#161a1f; --panel:#1e242a; --ink:#e6e9ec; --ink2:#a5aeb7; --line:#7d868f; --grid:#2c333a;
  --ctl:#4fb3ad; --rf:#e6e9ec; --mains:#e0785a; --spare:#5d666e; --steel:#8a949e;
}} }}
:root[data-theme="dark"] {{
  --bg:#161a1f; --panel:#1e242a; --ink:#e6e9ec; --ink2:#a5aeb7; --line:#7d868f; --grid:#2c333a;
  --ctl:#4fb3ad; --rf:#e6e9ec; --mains:#e0785a; --spare:#5d666e; --steel:#8a949e;
}}
body {{ background:var(--bg); color:var(--ink); font-family:var(--sans); font-size:15px; line-height:1.5; }}
main {{ max-width:1160px; margin:0 auto; padding:32px 24px 64px; }}
header {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:8px 24px; margin-bottom:20px; }}
h1 {{ font-size:26px; font-weight:600; margin:0; letter-spacing:-0.01em; }}
h2 {{ font-size:13px; font-weight:600; text-transform:uppercase; letter-spacing:0.08em; color:var(--ink2); margin:36px 0 10px; }}
.eyebrow {{ font-family:var(--mono); font-size:12px; color:var(--ctl); letter-spacing:0.04em; }}
.lede {{ color:var(--ink2); max-width:72ch; margin:0 0 20px; }}
.lede a, p a {{ color:var(--ctl); }}
figure {{ margin:0; background:var(--panel); border:1px solid var(--grid); border-radius:4px; padding:16px; overflow-x:auto; }}
figure svg {{ display:block; min-width:960px; width:100%; height:auto; color:var(--ink); }}
figcaption {{ font-size:13px; color:var(--ink2); margin-top:12px; display:flex; flex-wrap:wrap; gap:6px 22px; }}
.key {{ display:inline-flex; align-items:center; gap:6px; }}
.key i {{ display:inline-block; width:14px; height:3px; background:var(--rf); }}
.key i.ctl {{ background:var(--ctl); }}
.key i.mains {{ background:var(--mains); }}
.key i.sp {{ background:repeating-linear-gradient(90deg,var(--spare) 0 4px,transparent 4px 7px); }}
.mod {{ fill:var(--panel); stroke:var(--ink); stroke-width:1.4; }}
.mod.ext {{ stroke:var(--line); stroke-width:1.2; }}
.steel {{ fill:none; stroke:var(--steel); stroke-width:2; stroke-dasharray:8 5; }}
.zone {{ stroke:var(--grid); stroke-width:1; }}
.rf {{ stroke:var(--rf); stroke-width:2.2; fill:none; }}
.rf.spare {{ stroke:var(--spare); stroke-dasharray:6 5; }}
.ctl {{ stroke:var(--ctl); stroke-width:1.6; fill:none; }}
.ctl.spare {{ stroke:var(--spare); stroke-dasharray:6 5; }}
.mains {{ stroke:var(--mains); stroke-width:1.6; fill:none; }}
.choke {{ fill:var(--ink); }}
.t {{ font-family:var(--sans); font-size:12px; font-weight:600; fill:var(--ink); }}
.t.spare {{ fill:var(--spare); }}
.d {{ font-family:var(--mono); font-size:10px; fill:var(--ink2); }}
.d.spare {{ fill:var(--spare); }}
.sec {{ font-family:var(--mono); font-size:11px; fill:var(--ctl); letter-spacing:.06em; text-transform:uppercase; }}
.grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:24px 40px; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th {{ text-align:left; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--ink2); font-weight:600; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); }}
td {{ padding:8px 10px 8px 0; border-bottom:1px solid var(--grid); vertical-align:top; }}
td:first-child {{ font-weight:600; white-space:nowrap; }}
code {{ font-family:var(--mono); font-size:12.5px; color:var(--ctl); }}
p, ol {{ max-width:72ch; }}
ol {{ padding-left:20px; }} ol li {{ margin-bottom:6px; }}
</style>
<main>
<header>
  <span class="eyebrow">Shack Relay Matrix · site architecture · rev B</span>
  <h1>Garden Matrix Site Plan</h1>
</header>
<p class="lede">The relay matrix lives in the stainless antenna box at the mast base, where every antenna arrives and the buried cables leave. The brains stay in the basement: a shack head with the controller and panel, talking to a link card in the garden over one Cat6. Everything that decides safety is duplicated on the garden side, so a cut cable, a hung head or a lost heartbeat leaves every antenna grounded. Card designs: <a href="https://claude.ai/code/artifact/e27126d0-6c2e-44ee-a48c-11e5d0845b2e">matrix</a> · <a href="https://claude.ai/code/artifact/50071472-129c-4a49-8116-c369629d1050">radio port</a> · <a href="https://claude.ai/code/artifact/e87b98e8-e594-4f4e-8697-b0068ad870c9">antenna port</a> · <a href="https://claude.ai/code/artifact/d58b35f7-6032-4fd3-8173-894ce5a1e149">controller</a>.</p>

<figure>
{svg}
<figcaption>
  <span class="key"><i></i> RF coax</span>
  <span class="key"><i class="ctl"></i> control / DC</span>
  <span class="key"><i class="mains"></i> 230 V</span>
  <span class="key"><i class="sp"></i> spare or planned</span>
</figcaption>
</figure>

<div class="grid2">
<section>
<h2>What moved, and why</h2>
<table>
<tr><th>Element</th><th>Rev B position</th></tr>
<tr><td>Controller + panel</td><td>Basement, in a small shack head. The ESP32, USB, Wi-Fi, OLED and buttons are the noisiest and most-touched parts of the system; none of them belong at the current maximum of a resonant grounded mast. The <a href="https://claude.ai/code/artifact/d58b35f7-6032-4fd3-8173-894ce5a1e149">Controller card</a> is unchanged except that its backplane connector becomes a link connector.</td></tr>
<tr><td>Link card</td><td>Replaces the controller in slot 0 of the garden backplane. Isolated RS-485 transceiver, a small bridge MCU that executes expander writes and reports back, and the full local safety chain: watchdog, supply supervisor, gate → <code>/RLY_EN</code>. Loss of link heartbeat for more than a second releases the gate.</td></tr>
<tr><td>PTT</td><td>Never goes through firmware or the RS-485 protocol. The FT-710's TX GND drives a current loop on its own Cat6 pair; an opto on the link card puts it straight onto <code>PTT[1]</code> on the garden backplane, where K0 on Radio Port 1 and the RX-mute on Radio Port 2 follow it in hardware. Sequencing stays inside the FT-710's TX delay, as your RFI notes require. The Radio Port card's PTT source jumper is set to "backplane" instead of "front jack".</td></tr>
<tr><td>KILL</td><td>A second Cat6 pair carries a current loop through the panel's KILL switch. Open loop, released gate, everything grounded. This is the physical kill switch the controller page left open, and it works with the head unpowered.</td></tr>
<tr><td>Power</td><td>230 V is already at the box, so the garden side gets a linear supply: toroid, bridge, linear 12 V for relays and 5 V for logic. No switch-mode converter anywhere in the box. The transformer's few watts of idle dissipation also keep the box above dew point most of the year.</td></tr>
<tr><td>RX/TX switch and bias-T</td><td>Both designed-but-unbuilt items from the RFI log land here. K0 on Radio Port 1 is the sequenced TX/RX switch; the loop's preamp is fed through the bias-T option on Antenna Port 2, no extra conductor up the mast.</td></tr>
<tr><td>VHF</td><td>GP-6N coax passes straight through on two bulkhead SO-239s with a choke. HF relays are not rated for 430 MHz and the FTM-510D has nothing to switch.</td></tr>
</table>
</section>

<section>
<h2>Buried run allocation</h2>
<table>
<tr><th>Cable</th><th>Use</th></tr>
<tr><td>Coax 1</td><td>FT-710 ↔ Radio Port 1. Choked at the box entry (this is RFI-log row 3) and already at the radio end (row 2).</td></tr>
<tr><td>Coax 2</td><td>Airspy ↔ Radio Port 2 (RX variant). Choked at box entry.</td></tr>
<tr><td>Coax 3</td><td>FTM-510D ↔ GP-6N, straight through. Choked at box entry (row 7) and to be choked at the radio (row 5).</td></tr>
<tr><td>Cat6 #1</td><td>Pair 1 RS-485 A/B · pair 2 PTT loop · pair 3 KILL loop · pair 4 spare. Whole cable through an FT240-31 at both ends. Galvanically isolated at both ends: isolated RS-485 transceivers, optos on the loops. No DC and no ground reference crosses on this cable.</td></tr>
<tr><td>Cat6 #2</td><td>Spare. Natural uses: PTT loop for a second transceiver, or Ethernet if the controller ever moves outdoors.</td></tr>
<tr><td>Power</td><td>230 V to the box on its own RCD-protected circuit. PE handling follows the earthing topology already worked out for the shed supply.</td></tr>
</table>

<h2>Limits this sets</h2>
<ol>
<li>Three coaxes means three radio lines to the basement. A third HF transceiver needs a fourth coax or a shared line; the matrix has the slots, the ground does not have the cable.</li>
<li>Every conductor entering the RVS box is a common-mode path at the noisiest point on the site. The rule is simple: nothing enters without a choke, nothing enters without isolation or surge protection, and nothing inside switches at kHz rates.</li>
<li>Latency: RS-485 route changes take milliseconds, which is fine because routing never happens during a transmission. PTT and KILL are wires, not messages, so nothing safety-relevant depends on the protocol.</li>
</ol>
</section>
</div>

<h2>Open items</h2>
<ol>
<li>Cat6 type in the ground: UTP or shielded. If shielded, decide where the shield bonds (box only, or both ends with the chokes doing the RF work). Ties into the mast-earth vs house-PE bonding question.</li>
<li>Surge protection on the Cat6 at the box: gas-discharge on each pair to the box, plus TVS behind the isolation. The box sits at the base of the tallest metal object in the garden.</li>
<li>Condensation strategy: rely on PSU self-heating plus a drain and breather, or add a small resistive heater on a thermostat. No fans.</li>
<li>Relay class in a damp box: sealed (washable) relays rather than flux-tight, and conformal coating on the cards.</li>
<li>Whether the link card's bridge MCU is the same ESP32-S3 with radio disabled (one firmware tree) or a tiny STM32G0/RP2040 (fewer things to go wrong outdoors).</li>
</ol>
</main>
'''
out = "/mnt/user-data/outputs/garden-matrix-site-plan.html"
open(out, "w").write(html)
print(out, len(html))
