#!/usr/bin/env python3
"""Generate the Controller card block diagram page (HTML + inline SVG)."""

W, H = 1160, 580
s = []
a = s.append

def box(x, y, w, h, title, lines, cls=""):
    a(f'<rect class="mod{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>')
    a(f'<text class="t{cls}" x="{x+w/2}" y="{y+17}" text-anchor="middle">{title}</text>')
    for k, ln in enumerate(lines):
        a(f'<text class="d{cls}" x="{x+w/2}" y="{y+33+k*14}" text-anchor="middle">{ln}</text>')

def line(x1, y1, x2, y2, cls="ctl", arrow=False):
    m = ' marker-end="url(#arr)"' if arrow else ""
    a(f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{m}/>')

def poly(pts, cls="ctl", arrow=False):
    m = ' marker-end="url(#arr)"' if arrow else ""
    a(f'<polyline class="{cls}" points="{" ".join(f"{x},{y}" for x, y in pts)}"{m}/>')

def label(x, y, txt, anchor="start", cls="d"):
    a(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{txt}</text>')

a(f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Controller card: ESP32-S3 module with USB-C host link, debug header, Wi-Fi antenna path to a rear SMA, front panel connector; below it the safety chain of external watchdog, supply supervisor and hardware gate that produces RLY_EN, plus the I2C bus buffer and PTT/INT input buffer onto the backplane rail">')
a('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>')

# ---------------- MCU + interfaces ----------------
label(30, 40, "Compute · host link · panel", cls="sec")
box(380, 60, 240, 240, "ESP32-S3-WROOM-1U", ["dual core · 8 MB flash", "native USB (CDC) · Wi-Fi 2.4 GHz", "I2C#1 backplane master", "I2C#2 front panel", "GPIO: WDT kick, MCU_EN,", "PTT[1..4], /INT, buttons", "", "routing table · interlocks", "ASCII protocol · web UI"])
# USB-C
box(60, 60, 160, 56, "USB-C", ["to host PC · ESD array", "5 V not used for logic"], " ext")
line(220, 88, 380, 88, "wire", arrow=True); label(226, 82, "USB 2.0 · native CDC", cls="d")
# debug
box(60, 150, 160, 56, "Debug header", ["UART0 · BOOT · RESET", "not on the panel"])
line(220, 178, 380, 178, "wire"); label(226, 172, "UART0", cls="d")
# Wi-Fi antenna path
line(620, 88, 680, 88, "wire"); label(626, 82, "RF · U.FL", cls="d")
box(680, 60, 160, 56, "Wi-Fi antenna path", ["U.FL → rear SMA bulkhead", "antenna outside the box"])
# front panel
line(620, 200, 680, 200, "ctl", arrow=True); label(626, 194, "I2C#2 · GPIO", cls="d")
box(680, 150, 160, 90, "Front panel", ["OLED 128×64 (I2C)", "encoder + push", "MODE · ACK buttons", "fault LED · ribbon"], " ext")
# card power
box(880, 60, 220, 56, "Card power", ["+5V from backplane → 3V3 LDO 1 A", "clean rail for MCU + panel"])
poly([(990, 116), (990, 480)], "ctl", arrow=True); label(996, 440, "+5V", cls="d")
label(880, 134, "3V3 → MCU, panel, logic", cls="d")

# ---------------- safety chain ----------------
label(30, 345, "Safety chain · hardware only", cls="sec")
box(60, 360, 160, 60, "External watchdog", ["TPS3823 class · 1.6 s", "kicked by MCU GPIO"])
poly([(400, 300), (400, 325), (140, 325), (140, 360)], "ctl", arrow=True); label(148, 320, "WDT kick", cls="d")
box(250, 360, 150, 60, "Supply supervisor", ["+3V3 and +12V RLY", "under-voltage → not OK"])
poly([(325, 420), (325, 480)], "ctl", arrow=True); label(331, 465, "+12V RLY sense", cls="d")
box(440, 360, 220, 60, "Safety gate", ["/RLY_EN = WDT_OK ∧ PWR_OK ∧ MCU_EN", "fault latch · MCU clears after ACK"])
line(470, 300, 470, 360, "ctl", arrow=True); label(476, 340, "MCU_EN", cls="d")
poly([(140, 420), (140, 440), (500, 440), (500, 420)], "ctl", arrow=True); label(148, 435, "WDT_OK", cls="d")
line(400, 390, 440, 390, "ctl", arrow=True); label(402, 384, "PWR_OK", cls="d")
poly([(560, 420), (560, 480)], "ctl", arrow=True); label(566, 465, "/RLY_EN · open-drain", cls="d")
# I2C buffer
poly([(620, 290), (720, 290), (720, 360)], "ctl", arrow=True); label(726, 340, "I2C#1", cls="d")
box(680, 360, 170, 60, "I2C bus buffer", ["PCA9517 · strong pull-ups", "TCA9548 mux footprint"])
poly([(760, 420), (760, 480)], "ctl", arrow=True); label(766, 465, "SDA · SCL", cls="d")
# PTT / INT buffer
poly([(620, 255), (940, 255), (940, 360)], "ctl", arrow=True); label(626, 268, "PTT[1..4] · /INT → GPIO", cls="d")
box(870, 360, 150, 60, "Input buffer", ["PTT[1..4], /INT", "Schmitt · pull-ups"])
poly([(920, 480), (920, 420)], "ctl", arrow=True); label(866, 465, "PTT · /INT", cls="d")

# rail
a('<rect class="bus" x="30" y="480" width="1090" height="16"/>')
label(1114, 492, "backplane · 2×10 IDC · slot 0", "end", cls="buslbl")
label(30, 516, "+5V in · +3V3 n/c (own LDO) · GND · SDA/SCL (master) · /INT (in) · /RLY_EN (out) · SLOT_ID n/c · PTT[1..4] (in) · spare: TX_ANY out (option)", cls="d")

a('</svg>')
svg = "\n".join(s)

html = f'''<title>Controller Card</title>
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
.mod {{ fill:var(--panel); stroke:var(--ink); stroke-width:1.4; }}
.mod.ext {{ stroke:var(--line); stroke-width:1.2; }}
.wire {{ stroke:var(--rf); stroke-width:1.6; fill:none; }}
.ctl {{ stroke:var(--ctl); stroke-width:1.6; fill:none; }}
.bus {{ fill:var(--ctl-soft); stroke:var(--ctl); stroke-width:1; }}
.buslbl {{ font-family:var(--mono); font-size:10px; fill:var(--ctl); }}
.t {{ font-family:var(--sans); font-size:12px; font-weight:600; fill:var(--ink); }}
.d {{ font-family:var(--mono); font-size:10px; fill:var(--ink2); }}
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
  <h1>Controller Card</h1>
</header>
<p class="lede">Slot 0. An ESP32-S3 holds the routing table and talks to every card over I2C, to the host over USB, and to the shack over Wi-Fi. Around it sits a safety chain built so that the firmware can only ever <em>permit</em> relays to be energised: the external watchdog, the supply supervisor and the gate that produces <code>/RLY_EN</code> are hardware. Parent: <a href="https://claude.ai/code/artifact/e27126d0-6c2e-44ee-a48c-11e5d0845b2e">Shack Relay Matrix</a> · siblings: <a href="https://claude.ai/code/artifact/50071472-129c-4a49-8116-c369629d1050">Radio Port Card</a>, <a href="https://claude.ai/code/artifact/e87b98e8-e594-4f4e-8697-b0068ad870c9">Antenna Port Card</a>.</p>

<figure>
{svg}
<figcaption>
  <span class="key"><i></i> data / RF</span>
  <span class="key"><i class="ctl"></i> control / power</span>
</figcaption>
</figure>

<div class="grid2">
<section>
<h2>Blocks</h2>
<table>
<tr><th>Block</th><th>Function and choice</th></tr>
<tr><td>ESP32-S3-WROOM-1U</td><td>The -1U variant has a U.FL socket instead of a PCB antenna, so the Wi-Fi antenna goes through a rear bulkhead SMA and sits outside the steel box. Native USB gives the host a CDC serial port with no bridge chip. Two I2C controllers: #1 is the backplane master, #2 drives the front panel, so a wedged card cannot freeze the display.</td></tr>
<tr><td>USB-C</td><td>Host link only. ESD array on the data pair. The 5 V from the host is not used to power anything; the card runs from the backplane so the switch works with the PC off.</td></tr>
<tr><td>Card power</td><td>+5 V from the Power module through a 1 A 3V3 LDO on this card. The ESP32 draws 500 mA bursts on Wi-Fi TX; keeping that off the shared backplane 3V3 keeps the card-side expanders and comparators quiet.</td></tr>
<tr><td>External watchdog</td><td>TPS3823 class, 1.6 s window, kicked from a GPIO in the main loop. The ESP32's internal watchdogs only reset the chip; this one also drops <code>WDT_OK</code>, so a hung MCU takes the relays to safe state before it reboots.</td></tr>
<tr><td>Supply supervisor</td><td>Watches +3V3 and +12V RLY. Under-voltage on either releases <code>PWR_OK</code>. Relays that lose coil voltage mid-transmission are worse than relays that were never closed.</td></tr>
<tr><td>Safety gate</td><td>Small logic: <code>/RLY_EN</code> is asserted only while <code>WDT_OK</code>, <code>PWR_OK</code> and <code>MCU_EN</code> are all true and the fault latch is clear. Any of them dropping sets the latch. The MCU can clear the latch only after the ACK button, and only if the inputs are healthy again. Open-drain onto the backplane so a second controller or a panel kill switch could pull it too.</td></tr>
<tr><td>I2C bus buffer</td><td>PCA9517 between the MCU and the backplane: strong pull-ups on the card side, isolation from a shorted card, and a TCA9548 mux footprint for a second backplane later.</td></tr>
<tr><td>Input buffer</td><td>Schmitt buffers with pull-ups on <code>PTT[1..4]</code> and <code>/INT</code>. The MCU reads PTT for hot-switch lockout and the display; it never drives those lines.</td></tr>
<tr><td>Front panel</td><td>Ribbon to the panel: 128×64 OLED on I2C#2, encoder with push for pick-and-confirm, MODE and ACK buttons, fault LED. Enough to run the shack with the PC off.</td></tr>
<tr><td>Debug header</td><td>UART0, BOOT and RESET on the card edge. Not reachable from the panel.</td></tr>
</table>
</section>

<section>
<h2>What the firmware owns</h2>
<table>
<tr><th>Function</th><th>Behaviour</th></tr>
<tr><td>Discovery</td><td>At boot: scan slots, read each card's EEPROM (type, name, RX-only, bias-T, TX-capable, TX delay). Build the routing table from what is actually plugged in.</td></tr>
<tr><td>Routing</td><td>Per radio slot: TX line and RX line. Enforce one radio per line, RX-only lines only on RX paths, break-before-make, settle delay, no moves while that slot's PTT or <code>RF_DET</code> is active.</td></tr>
<tr><td>Host protocol</td><td>ASCII over USB CDC, same protocol over TCP/WebSocket on Wi-Fi. Commands like <code>SET R1 TX A1 RX A2</code>, <code>STATE</code>, <code>FAULT ACK</code>. Host-side band data from CAT can drive per-band presets.</td></tr>
<tr><td>Web UI</td><td>Matrix view, tap to route, fault log. mDNS so it is <code>relay-matrix.local</code>.</td></tr>
<tr><td>Faults</td><td>RF on an idle or RX-only line, PTT while a move is in progress, expander not answering, EEPROM/DIP mismatch. Log to flash with timestamp (NTP when Wi-Fi is up).</td></tr>
<tr><td>Presets</td><td>Named routes stored in NVS, selectable from encoder, host or web.</td></tr>
</table>

<h2>Boot and fault sequence</h2>
<ol>
<li>Power up: <code>/RLY_EN</code> released by default (latch set on power-on). Every antenna port grounded, every matrix relay open.</li>
<li>MCU boots, scans cards, loads last state, starts kicking the watchdog, raises <code>MCU_EN</code>.</li>
<li>Firmware clears the latch → <code>/RLY_EN</code> asserted → routes applied in order, RX rows before TX rows.</li>
<li>On any fault: latch sets, <code>/RLY_EN</code> released within microseconds, K0 relays on the radio cards keep following PTT. Display shows the cause. ACK on the panel or host lets the MCU clear the latch.</li>
</ol>
</section>
</div>

<h2>Open items</h2>
<ol>
<li>Wi-Fi radiated and conducted noise into the HF receive chain. Mitigations drawn in: antenna outside the box, LDO on the card, module far from the RF bus board. Verify with the Airspy before committing the enclosure layout. Fallback is a Wi-Fi-off mode.</li>
<li>Whether <code>TX_ANY</code> (diode-OR of PTT) should be driven onto a spare backplane line by this card or by the Power module; the Radio Port RX variant would prefer a clean single line to read.</li>
<li>Panel kill switch: a physical switch in series with <code>/RLY_EN</code> on the front panel, or trust the ACK-gated latch.</li>
<li>ESP32-S3 I2C at 400 kHz across the full backplane with 10 expanders and 10 EEPROMs: check bus capacitance; the PCA9517 helps but the backplane pull-ups need sizing.</li>
</ol>
</main>
'''
out = "/mnt/user-data/outputs/controller-card.html"
open(out, "w").write(html)
print(out, len(html))
