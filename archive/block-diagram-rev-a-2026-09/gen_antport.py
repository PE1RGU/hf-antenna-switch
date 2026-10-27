#!/usr/bin/env python3
"""Generate the Antenna Port card block diagram page (HTML + inline SVG)."""

W, H = 1160, 580
RF_Y = 110          # RF chain centre line
s = []
a = s.append

def box(x, y, w, h, title, lines, cls=""):
    a(f'<rect class="mod{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>')
    a(f'<text class="t{cls}" x="{x+w/2}" y="{y+17}" text-anchor="middle">{title}</text>')
    for k, ln in enumerate(lines):
        a(f'<text class="d{cls}" x="{x+w/2}" y="{y+33+k*14}" text-anchor="middle">{ln}</text>')

def line(x1, y1, x2, y2, cls="rf", arrow=False):
    m = ' marker-end="url(#arr)"' if arrow else ""
    a(f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{m}/>')

def poly(pts, cls="ctl", arrow=False):
    m = ' marker-end="url(#arr)"' if arrow else ""
    a(f'<polyline class="{cls}" points="{" ".join(f"{x},{y}" for x, y in pts)}"{m}/>')

def label(x, y, txt, anchor="start", cls="d"):
    a(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{txt}</text>')

def gnd(x, y, chassis=False):
    line(x, y, x, y+10, "wire")
    line(x-9, y+10, x+9, y+10, "wire")
    line(x-6, y+14, x+6, y+14, "wire")
    line(x-3, y+18, x+3, y+18, "wire")
    if chassis:
        label(x+12, y+18, "chassis", cls="d")

a(f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Antenna Port card: RF chain from matrix line through coupler footprint, detector tap, fail-safe SPDT relay and surge arrestor to the SO-239; control section with backplane connector, I2C expander, EEPROM, DIP switch, relay driver gated by RLY_EN">')
a('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>')

# ---------------- RF chain ----------------
label(30, 40, "RF chain · 50 Ω · 100 W HF", cls="sec")
box(30, RF_Y-28, 100, 56, "Matrix line", ["A[n] from RF bus", "SMA / edge pin"], " ext")
line(130, RF_Y, 170, RF_Y)
box(170, RF_Y-28, 120, 56, "Dir. coupler", ["footprint only", "fwd / ref taps"], " spare")
line(290, RF_Y, 350, RF_Y)
a(f'<circle class="node" cx="320" cy="{RF_Y}" r="3.5"/>')
box(350, RF_Y-28, 90, 56, "C block", ["bias-T option", "else 0 Ω link"], " spare")
line(440, RF_Y, 480, RF_Y)
# K1 relay
box(480, RF_Y-32, 140, 64, "K1 · SPDT relay", ["COM = antenna", "NO = matrix · NC = GND", "de-energised → GND"])
label(484, RF_Y+3, "NO", cls="pin")
label(616, RF_Y+3, "COM", "end", cls="pin")
label(562, RF_Y+38, "NC", "middle", cls="pin")
# NC -> bleed -> GND
line(560, RF_Y+32, 560, 170, "wire")
box(470, 170, 110, 40, "Static bleed", ["1 MΩ ∥ RF choke"])
line(560, 210, 560, 232, "wire"); gnd(560, 232)
# coil from driver
line(600, RF_Y+32, 600, 260, "ctl", arrow=False)
label(606, 200, "coil", cls="d")
label(606, 214, "+12V RLY", cls="d")
# K1 -> antenna
line(620, RF_Y, 880, RF_Y)
a(f'<circle class="node" cx="700" cy="{RF_Y}" r="3.5"/>')
a(f'<circle class="node" cx="800" cy="{RF_Y}" r="3.5"/>')
# bias-T inject (above)
line(700, RF_Y, 700, 62, "wire spare")
box(640, 22, 120, 40, "Bias-T inject", ["L + 12 V · option"], " spare")
# GDT (below)
line(800, RF_Y, 800, 160, "wire")
box(740, 160, 120, 40, "GDT", ["90 V gas arrestor"])
line(800, 200, 800, 222, "wire"); gnd(800, 222, chassis=True)
# SO-239
box(880, RF_Y-28, 110, 56, "SO-239", ["antenna out", "shell → chassis"], " ext")
line(990, RF_Y, 1040, RF_Y, "wire")
# antenna glyph
line(1040, RF_Y, 1040, 60, "wire"); line(1028, 44, 1040, 60, "wire"); line(1052, 44, 1040, 60, "wire"); line(1028, 44, 1052, 44, "wire")
label(1060, 66, "antenna", cls="d")

# detector tap
line(320, RF_Y, 320, 360, "wire")
label(326, 250, "RF tap", cls="d")
line(320, 360, 310, 360, "wire", arrow=True)
# coupler analog (dashed) down to header
line(180, RF_Y+28, 180, 430, "wire spare")

# ---------------- control ----------------
label(30, 245, "Control · 3V3 logic · 12 V relay rail", cls="sec")
# backplane connector
a('<rect class="mod" x="30" y="258" width="100" height="272" rx="3"/>')
label(80, 276, "Backplane", "middle", cls="t")
label(80, 290, "2×10 IDC", "middle", cls="d")
pins = ["+12V RLY", "+5V · +3V3", "GND ×4", "SDA · SCL", "/INT", "/RLY_EN", "SLOT_ID[2:0]", "PTT[1..4] n/c", "spare ×2"]
for k, p in enumerate(pins):
    label(80, 312 + k*22, p, "middle", cls="pin")
# I2C bus to expander
line(130, 280, 360, 280, "ctl", arrow=True)
label(140, 274, "I2C · /INT · SLOT_ID", cls="d")
# expander
box(360, 258, 150, 60, "I2C GPIO expander", ["PCA9554 · addr = SLOT_ID", "in: RF_DET, DIP · out: ROUTE"])
# EEPROM below expander
line(380, 318, 380, 338, "ctl")
box(360, 338, 150, 50, "ID EEPROM", ["24C02 · addr = SLOT_ID", "name · RX-only · bias-T"])
# detector
box(190, 338, 120, 50, "RF detector", ["diode + comparator", "→ RF_DET, /INT"])
poly([(310, 375), (330, 375), (330, 300), (360, 300)], "ctl", arrow=True)
# DIP
box(190, 408, 120, 50, "DIP override", ["RX-only · bias-T", "→ expander inputs"])
poly([(310, 440), (340, 440), (340, 310), (360, 310)], "ctl", arrow=True)
# analog header
box(190, 478, 120, 40, "Analog header", ["fwd/ref → future ADC"], " spare")
poly([(180, 430), (180, 498), (190, 498)], "wire spare")
# relay driver
line(510, 280, 550, 280, "ctl", arrow=True)
label(514, 274, "ROUTE", cls="d")
box(550, 258, 140, 60, "Relay driver", ["MOSFET + flyback diode", "EN = ROUTE AND /RLY_EN"])
line(600, 258, 600, 240, "ctl")   # continues up to K1 coil (drawn above)
# /RLY_EN from connector
poly([(130, 470), (610, 470), (610, 318)], "ctl", arrow=True)
label(360, 464, "/RLY_EN · hardware enable, bypasses firmware", cls="d")
# power
poly([(130, 510), (720, 510)], "ctl", arrow=True)
label(330, 504, "+12V RLY · +3V3", cls="d")
box(720, 480, 140, 50, "Card power", ["polyfuse on +12V RLY", "LC filter · decoupling"])
label(870, 500, "→ K1 coil, driver,", cls="d")
label(870, 514, "logic, bias-T", cls="d")
# status LED
box(730, 258, 110, 50, "Status LED", ["green = routed", "off = grounded"])
line(690, 290, 730, 290, "ctl", arrow=True)

a('</svg>')
svg = "\n".join(s)

html = f'''<title>Antenna Port Card</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg:#f2f3ef; --panel:#fbfbf8; --ink:#1c232b; --ink2:#5b6570; --line:#8e979f; --grid:#d8dbd4;
  --ctl:#2b7a78; --rf:#1c232b; --on:#d9642a; --spare:#a9b0b6;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#161a1f; --panel:#1e242a; --ink:#e6e9ec; --ink2:#a5aeb7; --line:#7d868f; --grid:#2c333a;
  --ctl:#4fb3ad; --rf:#e6e9ec; --on:#f08a4b; --spare:#5d666e;
}} }}
:root[data-theme="dark"] {{
  --bg:#161a1f; --panel:#1e242a; --ink:#e6e9ec; --ink2:#a5aeb7; --line:#7d868f; --grid:#2c333a;
  --ctl:#4fb3ad; --rf:#e6e9ec; --on:#f08a4b; --spare:#5d666e;
}}
body {{ background:var(--bg); color:var(--ink); font-family:var(--sans); font-size:15px; line-height:1.5; }}
main {{ max-width:1120px; margin:0 auto; padding:32px 24px 64px; }}
header {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:8px 24px; margin-bottom:20px; }}
h1 {{ font-size:26px; font-weight:600; margin:0; letter-spacing:-0.01em; }}
h2 {{ font-size:13px; font-weight:600; text-transform:uppercase; letter-spacing:0.08em; color:var(--ink2); margin:36px 0 10px; }}
.eyebrow {{ font-family:var(--mono); font-size:12px; color:var(--ctl); letter-spacing:0.04em; }}
.lede {{ color:var(--ink2); max-width:70ch; margin:0 0 20px; }}
.lede a {{ color:var(--ctl); }}
figure {{ margin:0; background:var(--panel); border:1px solid var(--grid); border-radius:4px; padding:16px; overflow-x:auto; }}
figure svg {{ display:block; min-width:900px; width:100%; height:auto; color:var(--ink); }}
figcaption {{ font-size:13px; color:var(--ink2); margin-top:12px; display:flex; flex-wrap:wrap; gap:6px 22px; }}
.key {{ display:inline-flex; align-items:center; gap:6px; }}
.key i {{ display:inline-block; width:14px; height:3px; background:var(--rf); }}
.key i.ctl {{ background:var(--ctl); }}
.key i.sp {{ background:repeating-linear-gradient(90deg,var(--spare) 0 4px,transparent 4px 7px); }}
.mod {{ fill:var(--panel); stroke:var(--ink); stroke-width:1.4; }}
.mod.ext {{ stroke:var(--line); stroke-width:1.2; }}
.mod.spare {{ stroke:var(--spare); stroke-dasharray:5 4; }}
.rf {{ stroke:var(--rf); stroke-width:2.2; fill:none; }}
.wire {{ stroke:var(--rf); stroke-width:1.4; fill:none; }}
.wire.spare {{ stroke:var(--spare); stroke-dasharray:5 4; }}
.ctl {{ stroke:var(--ctl); stroke-width:1.6; fill:none; }}
.node {{ fill:var(--rf); }}
.t {{ font-family:var(--sans); font-size:12px; font-weight:600; fill:var(--ink); }}
.t.spare {{ fill:var(--spare); }}
.d {{ font-family:var(--mono); font-size:10px; fill:var(--ink2); }}
.d.spare {{ fill:var(--spare); }}
.pin {{ font-family:var(--mono); font-size:9.5px; fill:var(--ink); }}
.sec {{ font-family:var(--mono); font-size:11px; fill:var(--ctl); letter-spacing:.06em; text-transform:uppercase; }}
.grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:24px 40px; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th {{ text-align:left; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--ink2); font-weight:600; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); }}
td {{ padding:8px 10px 8px 0; border-bottom:1px solid var(--grid); vertical-align:top; }}
td:first-child {{ font-weight:600; white-space:nowrap; }}
code {{ font-family:var(--mono); font-size:12.5px; color:var(--ctl); }}
p, ol {{ max-width:70ch; }}
ol {{ padding-left:20px; }} ol li {{ margin-bottom:6px; }}
</style>
<main>
<header>
  <span class="eyebrow">Shack Relay Matrix · card architecture · rev A</span>
  <h1>Antenna Port Card</h1>
</header>
<p class="lede">One card per antenna line. It does three things: connects the antenna to its matrix line only when told to and only while the controller is alive, grounds it otherwise, and tells the controller what it is and whether RF is present. Same footprint and backplane pinout as the Radio Port card. Parent diagram: <a href="https://claude.ai/code/artifact/e27126d0-6c2e-44ee-a48c-11e5d0845b2e">Shack Relay Matrix</a>.</p>

<figure>
{svg}
<figcaption>
  <span class="key"><i></i> RF path</span>
  <span class="key"><i class="ctl"></i> control / power</span>
  <span class="key"><i class="sp"></i> option, footprint only on rev A</span>
</figcaption>
</figure>

<div class="grid2">
<section>
<h2>Blocks</h2>
<table>
<tr><th>Block</th><th>Function and choice</th></tr>
<tr><td>K1 SPDT relay</td><td>The only moving part in the RF path. COM to the antenna, NO to the matrix line, NC to ground through the static bleed. De-energised is grounded, so a dead controller, released <code>/RLY_EN</code> or lost 12 V all leave the antenna parked. 12 V coil, 16 A HF-rated signal relay class (RT2/Omron G2RL or similar), rated well beyond 100 W at 50 Ω.</td></tr>
<tr><td>Static bleed</td><td>1 MΩ in parallel with an RF choke on the NC side. Drains precipitation static while grounded; the choke keeps the DC path when the bias-T option is fitted.</td></tr>
<tr><td>GDT</td><td>90 V gas-discharge arrestor from antenna centre to chassis, on the antenna side of K1 so it protects the relay too. Not a lightning solution; that stays at the mast base and the shed entry.</td></tr>
<tr><td>RF detector</td><td>Capacitive tap after the matrix connector, Schottky detector, comparator with fixed threshold. Gives <code>RF_DET</code> to the expander and pulls <code>/INT</code>. Route verification: RF seen on a card the controller thinks is idle, or on an RX-only card, is a fault and drops <code>/RLY_EN</code>.</td></tr>
<tr><td>Coupler footprint</td><td>Unpopulated on rev A. Directional coupler plus dual detector lands here; fwd/ref analog goes to the header for a later ADC card or controller input. Per-antenna SWR without a new PCB.</td></tr>
<tr><td>Bias-T option</td><td>Series DC-block capacitor on the matrix side and an inductor injecting 12 V on the antenna side. Fitted only on a card feeding an active RX antenna. Enable via expander output, flag in EEPROM.</td></tr>
<tr><td>I2C expander</td><td>PCA9554 class, address from <code>SLOT_ID</code>. Inputs: <code>RF_DET</code>, DIP switches. Outputs: <code>ROUTE</code>, bias-T enable, LED.</td></tr>
<tr><td>ID EEPROM</td><td>24C02 class, address from <code>SLOT_ID</code>. Holds antenna name, RX-only flag, bias-T flag, card revision. Controller reads it at boot, so the card carries its identity to any slot.</td></tr>
<tr><td>DIP override</td><td>Two switches: force RX-only, force bias-T off. Hardware truth beats EEPROM when they disagree; controller logs the mismatch.</td></tr>
<tr><td>Relay driver</td><td>Logic-level MOSFET with flyback diode. Gate is <code>ROUTE</code> AND <code>/RLY_EN</code> in hardware (one gate or a driver with an enable pin). Firmware alone cannot energise K1 when the watchdog has released the bus.</td></tr>
<tr><td>Card power</td><td>Polyfuse on <code>+12V RLY</code>, LC filter so relay switching does not appear on the RF ground, local 3V3 decoupling. One card failing short does not take the rail down.</td></tr>
</table>
</section>

<section>
<h2>States</h2>
<table>
<tr><th>Condition</th><th>K1</th><th>Antenna</th></tr>
<tr><td>Power off</td><td>de-energised</td><td>grounded</td></tr>
<tr><td>Idle, no radio routed</td><td>de-energised</td><td>grounded</td></tr>
<tr><td>Routed, <code>/RLY_EN</code> asserted</td><td>energised</td><td>on matrix line</td></tr>
<tr><td><code>/RLY_EN</code> released (watchdog, brown-out, fault)</td><td>de-energised</td><td>grounded, regardless of <code>ROUTE</code></td></tr>
<tr><td>RF detected while idle or RX-only</td><td>controller drops <code>/RLY_EN</code></td><td>all ports grounded, fault logged</td></tr>
</table>

<h2>Backplane pins used</h2>
<table>
<tr><th>Signal</th><th>Use on this card</th></tr>
<tr><td><code>+12V RLY</code></td><td>K1 coil, bias-T supply. Polyfused.</td></tr>
<tr><td><code>+3V3</code></td><td>Expander, EEPROM, comparator.</td></tr>
<tr><td><code>SDA / SCL</code></td><td>Expander and EEPROM.</td></tr>
<tr><td><code>/INT</code></td><td>Open-drain, pulled on <code>RF_DET</code> edge.</td></tr>
<tr><td><code>/RLY_EN</code></td><td>Hardware enable into the relay driver.</td></tr>
<tr><td><code>SLOT_ID[2:0]</code></td><td>I2C address for both chips.</td></tr>
<tr><td><code>PTT[1..4]</code></td><td>Present on the connector, not connected on this card. Reserved for a variant that opens K1 on PTT of a non-owning radio.</td></tr>
</table>

<h2>RX-only variant</h2>
<p>Same PCB. EEPROM flag and DIP set RX-only; bias-T parts fitted if the antenna is active. The controller refuses this card on any TX path. The detector is the hardware tripwire behind that rule: if it ever sees transmit-level RF, the whole matrix goes to safe state.</p>
</section>
</div>

<h2>Open items</h2>
<ol>
<li>Relay part: confirm contact rating and isolation at 30 MHz for 100 W with the NC side grounded; check hot-switch survival for the fault case.</li>
<li>Detector threshold: set between the strongest expected receive signal and the lowest transmit power that matters, roughly 0 dBm to +20 dBm at the tap.</li>
<li>Whether the coupler footprint uses a Tandem Match (two ferrite transformers) or a stripline coupler; footprint size differs.</li>
<li>Card edge: 100 × 80 mm Eurocard-half with the SO-239 on the front edge, or a rear-panel bulkhead SO-239 with a short coax jumper to the card.</li>
</ol>
</main>
'''
out = "/mnt/user-data/outputs/antenna-port-card.html"
open(out, "w").write(html)
print(out, len(html))
