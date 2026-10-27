#!/usr/bin/env python3
"""Generate the Radio Port card block diagram page (HTML + inline SVG)."""

W, H = 1160, 600
RF_Y = 115
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

a(f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Radio Port card: radio SO-239 into a PTT-driven SPDT changeover relay K0, TX path to a bank of six power relays and RX path to a bank of six signal relays, both banks onto the six RF bus lines; control section with PTT opto, K0 drive select, I2C expander, EEPROM, DIP, relay drivers behind an RLY_EN-gated rail switch, on the backplane rail">')
a('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>')

# ---------------- RF section ----------------
label(30, 30, "RF · 50 Ω · 100 W HF", cls="sec")
box(30, RF_Y-28, 100, 56, "SO-239", ["radio in", "shell → chassis"], " ext")
line(130, RF_Y, 200, RF_Y)
a(f'<circle class="node" cx="160" cy="{RF_Y}" r="3.5"/>')
box(200, RF_Y-32, 160, 64, "K0 · SPDT changeover", ["COM = radio", "NO = TX path (keyed)", "NC = RX path (idle)"])
label(356, RF_Y-12, "NO", "end", cls="pin")
label(356, RF_Y+22, "NC", "end", cls="pin")
poly([(360, RF_Y-15), (400, RF_Y-15), (400, 70), (440, 70)], "rf")
poly([(360, RF_Y+15), (400, RF_Y+15), (400, 160), (440, 160)], "rf")
label(366, RF_Y-21, "TX path", cls="d")
label(366, RF_Y+32, "RX path", cls="d")
box(440, 42, 200, 56, "TX row · K1–K6", ["6× SPST power relays · 100 W", "one per line · max 1 closed"])
box(440, 132, 200, 56, "RX row · K7–K12", ["6× SPST signal relays", "max 1 closed · JP: open on PTT"])
line(640, 70, 780, 70, "rf6"); label(710, 62, "×6", "middle", cls="d")
line(640, 160, 780, 160, "rf6"); label(710, 152, "×6", "middle", cls="d")
a('<rect class="mod" x="780" y="42" width="100" height="146" rx="3"/>')
label(830, 60, "RF bus edge", "middle", cls="t")
label(830, 74, "TX ∥ RX per line", "middle", cls="d")
for i in range(6):
    y = 92 + i*17
    label(830, y+3, f"A{i+1}", "middle", cls="pin")
    line(880, y, 940, y, "wire")
box(940, 42, 120, 146, "RF bus board", ["6 antenna lines", "shared by all", "radio slots", "", "→ Antenna Port", "cards"], " ext")
# K0 driver under K0
line(300, RF_Y+32, 300, 178, "ctl")
label(306, 168, "coil", cls="d")
box(200, 178, 180, 54, "K0 driver", ["unswitched 12 V rail", "JP: local PTT | OR(PTT[1..4])"])
# TX sense tap straight down into detector
line(160, RF_Y, 160, 262, "wire", arrow=True)
label(166, 256, "TX sense tap", cls="d")

# ---------------- control ----------------
label(30, 242, "Control · 3V3 logic · 12 V relay rail", cls="sec")
R1, R2, R3, RH = 262, 340, 418, 56
C = {1: 30, 2: 220, 3: 400, 4: 570, 5: 740}
CW = 150
# c1: detector / opto / PTT jack
box(C[1], R1, CW, RH, "TX sense detector", ["Schottky + comparator", "→ RF_DET, /INT"])
box(C[1], R2, CW, RH, "Opto isolator", ["sinks OC PTT · 80 mA ok", "→ PTT[n] · K0 · expander"])
box(C[1], R3, CW, RH, "PTT in", ["3.5 mm jack · front", "open-collector / contact"], " ext")
line(105, R3, 105, R2+RH, "ctl", arrow=True)
# opto -> K0 driver (hardware), via gap x=195
poly([(C[1]+CW, R2+16), (195, R2+16), (195, 205), (200, 205)], "ctl", arrow=True)
# opto -> rail (drives PTT[n]) via x=188
poly([(C[1]+CW, R2+40), (188, R2+40), (188, 520)], "ctl", arrow=True); label(194, 505, "drives PTT[n]", cls="d")
# detector -> expander, hopping the opto line at (195, 290)
a('<rect class="hop" x="193" y="284" width="4" height="12"/>')
poly([(C[1]+CW, R1+28), (205, R1+28), (205, R3+28), (C[2], R3+28)], "ctl", arrow=True)
# c2: LEDs / DIP / expander
box(C[2], R1, CW, RH, "Status LEDs", ["RX · TX · fault", "from expander"])
box(C[2], R2, CW, RH, "DIP override", ["RX-only card", "RX row opens on PTT"])
line(295, R2+RH, 295, R3, "ctl", arrow=True)
box(C[2], R3, CW, RH, "I2C GPIO expander", ["PCA9555 · addr = SLOT_ID", "12 out · in: PTT, DET, DIP"])
poly([(295, R3+RH), (295, 520)], "ctl", arrow=True); label(301, 505, "I2C · /INT · SLOT_ID", cls="d")
line(C[2]+CW, R3+28, C[3], R3+28, "ctl", arrow=True); label(376, R3+22, "12", cls="d")
# c3: relay drivers, coils up to the banks
box(C[3], R3, CW, RH, "Relay drivers", ["12-ch low-side", "K1–K6 · K7–K12"])
poly([(475, R3), (475, 215), (540, 215), (540, 188)], "ctl", arrow=True)
label(552, 236, "12 coils · switched +12V", cls="d")
# c4: EEPROM / rail switch
box(C[4], R2, CW, RH, "ID EEPROM", ["24C02 · name · TX/RX", "max P · TX delay"])
poly([(C[4], R2+28), (560, R2+28), (560, 520)], "ctl", arrow=True); label(566, 505, "I2C", cls="d")
box(C[4], R3, CW, RH, "Relay rail switch", ["high-side FET on +12V RLY", "EN = /RLY_EN (hardware)"])
poly([(C[4]+CW, R3+28), (730, R3+28), (730, 215), (475, 215)], "ctl")
poly([(645, R3+RH), (645, 520)], "ctl", arrow=True); label(651, 505, "/RLY_EN", cls="d")
# c5: power / TX inhibit
box(C[5], R1, CW, RH, "Card power", ["polyfuse on +12V RLY", "LC filter · decoupling"])
poly([(C[5]+CW, R1+28), (900, R1+28), (900, 520)], "ctl", arrow=True); label(906, 505, "+12V RLY · +3V3", cls="d")
box(C[5], R3, CW, RH, "TX inhibit out", ["option · OC to radio", "on while /RLY_EN released"], " spare")
poly([(815, R3+RH), (815, 520)], "ctl spare", arrow=True); label(821, 505, "/RLY_EN", cls="d spare")

# backplane rail
a('<rect class="bus" x="30" y="520" width="1090" height="16"/>')
label(1114, 532, "backplane · 2×10 IDC", "end", cls="buslbl")
label(30, 556, "+12V RLY · +5V · +3V3 · GND ×4 · SDA · SCL · /INT · /RLY_EN · SLOT_ID[2:0] · PTT[1..4] (drives own, reads all) · spare ×2", cls="d")

a('</svg>')
svg = "\n".join(s)

html = f'''<title>Radio Port Card</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg:#f2f3ef; --panel:#fbfbf8; --ink:#1c232b; --ink2:#5b6570; --line:#8e979f; --grid:#d8dbd4;
  --ctl:#2b7a78; --ctl-soft:#2b7a7833; --rf:#1c232b; --on:#d9642a; --spare:#a9b0b6;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#161a1f; --panel:#1e242a; --ink:#e6e9ec; --ink2:#a5aeb7; --line:#7d868f; --grid:#2c333a;
  --ctl:#4fb3ad; --ctl-soft:#4fb3ad33; --rf:#e6e9ec; --on:#f08a4b; --spare:#5d666e;
}} }}
:root[data-theme="dark"] {{
  --bg:#161a1f; --panel:#1e242a; --ink:#e6e9ec; --ink2:#a5aeb7; --line:#7d868f; --grid:#2c333a;
  --ctl:#4fb3ad; --ctl-soft:#4fb3ad33; --rf:#e6e9ec; --on:#f08a4b; --spare:#5d666e;
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
.rf6 {{ stroke:var(--rf); stroke-width:6; fill:none; opacity:.85; }}
.wire {{ stroke:var(--rf); stroke-width:1.4; fill:none; }}
.wire.spare {{ stroke:var(--spare); stroke-dasharray:5 4; }}
.ctl {{ stroke:var(--ctl); stroke-width:1.6; fill:none; }}
.ctl.spare {{ stroke:var(--spare); stroke-dasharray:5 4; }}
.bus {{ fill:var(--ctl-soft); stroke:var(--ctl); stroke-width:1; }}
.buslbl {{ font-family:var(--mono); font-size:10px; fill:var(--ctl); }}
.node {{ fill:var(--rf); }}
.hop {{ fill:var(--panel); }}
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
  <h1>Radio Port Card</h1>
</header>
<p class="lede">One card per radio slot. The radio's single antenna socket comes in, a PTT-driven changeover relay splits it into a TX path and an RX path, and each path has its own row of six relays onto the RF bus lines. One PCB serves both the FT-710 and the Airspy: the RX-only build leaves the TX row empty and moves one jumper. Parent: <a href="https://claude.ai/code/artifact/e27126d0-6c2e-44ee-a48c-11e5d0845b2e">Shack Relay Matrix</a> · sibling: <a href="https://claude.ai/code/artifact/e87b98e8-e594-4f4e-8697-b0068ad870c9">Antenna Port Card</a>.</p>

<figure>
{svg}
<figcaption>
  <span class="key"><i></i> RF path</span>
  <span class="key"><i class="ctl"></i> control / power</span>
  <span class="key"><i class="sp"></i> option</span>
</figcaption>
</figure>

<div class="grid2">
<section>
<h2>Blocks</h2>
<table>
<tr><th>Block</th><th>Function and choice</th></tr>
<tr><td>K0 changeover</td><td>SPDT, COM to the radio, NO to the TX path, NC to the RX path. Idle is receive. Its coil is driven straight from the PTT opto, not through the MCU, and from the unswitched 12 V rail: the radio's own PTT decides which path it is on, always. Power-relay class, since it carries 100 W on every over. Needs the radio's TX delay to exceed its transfer time (FT-710: external-amp keying delay, set 20 to 30 ms).</td></tr>
<tr><td>TX row K1–K6</td><td>Six SPST power relays, one per RF bus line. Firmware closes at most one. Unpopulated on an RX-only card.</td></tr>
<tr><td>RX row K7–K12</td><td>Six SPST signal relays, one per line. Cheaper and better isolation than the power relays; they never carry transmit power on purpose. Jumper option: the row's driver enable is <code>/PTT</code>, so the RX antenna is disconnected during transmit. That protects the K0 NC contact from full TX voltage when TX and RX antenna are the same line, and stops the RX antenna re-radiating into the receiver path.</td></tr>
<tr><td>RF bus edge</td><td>Six edge connections to the RF bus board, one per antenna line. On the card, TX relay and RX relay for a line join at the edge pin. Keep the fan-out stubs short: five open relays hang on every line as capacitance.</td></tr>
<tr><td>TX sense detector</td><td>Tap on the radio side of K0. RF present without PTT (VOX, CW keying not wired) or PTT without RF are both logged; RF while a matrix relay is mid-switch drops <code>/RLY_EN</code>.</td></tr>
<tr><td>PTT in + opto</td><td>Front 3.5 mm jack, opto-isolated input that sinks the radio's open-collector or contact PTT (FT-710 TX GND, 80 mA rated). The opto output drives three things in hardware: this slot's <code>PTT[n]</code> line on the backplane (open-drain), the K0 driver, and an expander input for firmware lockout.</td></tr>
<tr><td>K0 drive select</td><td>Jumper. TX radio: K0 follows local PTT. RX-only card: K0 follows the diode-OR of all four <code>PTT[1..4]</code> lines, so the receiver is lifted off its antenna whenever anything in the shack transmits. That is the TX-mute function, without a second relay.</td></tr>
<tr><td>I2C expander</td><td>PCA9555, 16 bit, address from <code>SLOT_ID</code>. Twelve outputs for K1–K12, LEDs; inputs PTT, <code>RF_DET</code>, DIP.</td></tr>
<tr><td>Relay drivers + rail switch</td><td>12-channel low-side driver for the matrix relays. Their 12 V comes through a high-side MOSFET enabled by <code>/RLY_EN</code>. Firmware can set any pattern it likes; with the enable released no matrix coil has power. K0 is on the unswitched rail on purpose: it must keep following PTT even in a fault, otherwise a keyed radio could be left looking at an open RX path.</td></tr>
<tr><td>ID EEPROM + DIP</td><td>24C02: radio name, TX-capable, max power, required TX delay. DIP: force RX-only, RX row opens on PTT. Hardware truth beats EEPROM; mismatch logged.</td></tr>
<tr><td>TX inhibit out</td><td>Option. Open-collector to the radio's TX inhibit or TX REQ input where the radio has one, asserted whenever <code>/RLY_EN</code> is released or a matrix relay is moving. Belt to the TX-delay braces.</td></tr>
</table>
</section>

<section>
<h2>Two builds, one PCB</h2>
<table>
<tr><th></th><th>TX radio (FT-710)</th><th>RX-only (Airspy HF+)</th></tr>
<tr><td>K0</td><td>fitted, follows local PTT</td><td>fitted, follows OR(PTT bus): TX-mute</td></tr>
<tr><td>TX row</td><td>6 power relays</td><td>not fitted (NO contact open)</td></tr>
<tr><td>RX row</td><td>6 signal relays</td><td>6 signal relays</td></tr>
<tr><td>PTT in</td><td>from radio</td><td>not connected</td></tr>
<tr><td>TX sense</td><td>fitted</td><td>fitted, any RF is a fault</td></tr>
<tr><td>EEPROM / DIP</td><td>TX-capable</td><td>RX-only</td></tr>
</table>

<h2>What the controller enforces here</h2>
<ol>
<li>At most one relay closed per row. TX row and RX row may point at different lines (split antennas) or the same line (plain single antenna).</li>
<li>No relay in either row moves while this slot's PTT is active, and not while <code>RF_DET</code> is high.</li>
<li>Break before make with settle delay between rows and lines.</li>
<li>The TX row of a TX-capable card is never routed to a line whose Antenna Port card is flagged RX-only.</li>
<li>Coil budget: K0 plus at most two matrix relays energised per card, so a fully populated chassis stays under about 0.5 A on the relay rail.</li>
</ol>

<h2>Sequencing on key-down</h2>
<p>Radio asserts PTT → opto → K0 to TX path and <code>PTT[n]</code> on the bus (≈5 ms relay transfer) → radio's TX delay expires → RF. If the RX-row-opens-on-PTT jumper is set, K7–K12 drop in the same window. Nothing in this chain waits for the MCU. The MCU's only job during a transmission is to refuse to move anything.</p>
</section>
</div>

<h2>Open items</h2>
<ol>
<li>K0 and TX-row relay part: 100 W at 50 Ω, hot-switch tolerance for the fault case, transfer time under 10 ms.</li>
<li>Whether the RX-row-opens-on-PTT option is default on. Argues for: protects K0 contact and receiver. Against: relay wear on every over, and a small click on the RX path during break-in operation.</li>
<li>FT-710 TX inhibit: confirm what the LINEAR jack actually offers (TX GND out, TX REQ in) before committing the option footprint.</li>
<li>Detector threshold and whether the same detector should also give a coarse power reading via a comparator ladder or an ADC pin on the controller.</li>
</ol>
</main>
'''
out = "/mnt/user-data/outputs/radio-port-card.html"
open(out, "w").write(html)
print(out, len(html))
