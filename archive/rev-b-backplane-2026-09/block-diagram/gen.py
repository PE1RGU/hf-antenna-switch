#!/usr/bin/env python3
"""Generate the modular antenna-switch block diagram page (HTML + inline SVG)."""

# ---------- geometry ----------
W, H = 1160, 880
BAND_X0, BAND_X1 = 176, 190           # vertical control backplane band
BAND_Y0, BAND_Y1 = 128, 142           # horizontal control band (above antenna modules)
BAND_BOTTOM = 812
DEV_X0, DEV_X1 = 18, 156              # radio devices (left column)
MOD_X0, MOD_X1 = 214, 470             # radio port modules
MAT_X1 = 1100                         # right end of RF matrix lines
ANT_X0, ANT_PITCH, ANT_W = 512, 100, 90
ANT_MOD_Y0, ANT_MOD_Y1 = 158, 248
ROW_Y0, ROW_H, ROW_GAP = 360, 92, 14
BUS_Y1 = 800

antennas = [
    ("A1", "Doublet", "TX/RX", True),
    ("A2", "LoG", "RX only", True),
    ("A3", "Vertical", "planned", True),
    ("A4", "spare", "", False),
    ("A5", "spare", "", False),
    ("A6", "spare", "", False),
]
radios = [
    ("R1", "Yaesu FT-710", "100 W · PTT out (OC)", "Radio Port Module", True, False),
    ("R2", "Airspy HF+", "receive-only SDR", "Radio Port · RX variant", True, True),
    ("R3", "spare slot", "", "Radio Port Module", False, False),
    ("R4", "spare slot", "", "Radio Port Module", False, False),
]
closed = {("R1", "TX", "A1"), ("R1", "RX", "A3"), ("R2", "", "A2")}   # example state

def ant_cx(i): return ANT_X0 + i * ANT_PITCH + ANT_W / 2
def row_y(i): return ROW_Y0 + i * (ROW_H + ROW_GAP)

s = []
a = s.append

a(f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Radio-by-antenna relay matrix: radio port modules in rows, antenna bus lines in columns, one relay at every crossing, all modules on a shared I2C control backplane">')
a('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>')

# ---- control backplane (L shape) ----
a(f'<rect class="bus" x="{BAND_X0}" y="{BAND_Y0}" width="{BAND_X1-BAND_X0}" height="{BAND_BOTTOM-BAND_Y0}"/>')
a(f'<rect class="bus" x="{BAND_X0}" y="{BAND_Y0}" width="{ANT_X0 + 5*ANT_PITCH + ANT_W + 30 - BAND_X0}" height="{BAND_Y1-BAND_Y0}"/>')
a(f'<text class="buslbl" x="{BAND_X1 + 8}" y="{BAND_Y0-5}">control backplane (I2C + PTT bus + power)</text>')
a(f'<text class="buslbl" x="{BAND_X1 + 6}" y="{BAND_BOTTOM - 6}">+12V RLY · +5V · SDA/SCL · /INT · PTT[1..4] · /RLY_EN · SLOT_ID</text>')

# ---- host PC + controller + power (top-left) ----
a(f'<rect class="ext" x="{DEV_X0}" y="34" width="{DEV_X1-DEV_X0}" height="56" rx="3"/>')
a(f'<text class="t" x="{(DEV_X0+DEV_X1)/2}" y="56" text-anchor="middle">Host PC</text>')
a(f'<text class="d" x="{(DEV_X0+DEV_X1)/2}" y="72" text-anchor="middle">log · CAT band data</text>')
a(f'<line class="wire" x1="{(DEV_X0+DEV_X1)/2}" y1="90" x2="{(DEV_X0+DEV_X1)/2}" y2="156" marker-end="url(#arr)" marker-start="url(#arr)"/>')
a(f'<text class="d" x="{(DEV_X0+DEV_X1)/2 + 6}" y="126">USB-C</text>')

# controller module
a(f'<rect class="mod" x="{DEV_X0}" y="158" width="{DEV_X1-DEV_X0}" height="98" rx="3"/>')
for k, line in enumerate(["Controller Module", "MCU · I2C master", "USB-UART / CDC", "watchdog → /RLY_EN", "OLED+encoder (opt)"]):
    a(f'<text class="{"t" if k==0 else "d"}" x="{DEV_X0+8}" y="{176 + k*17}">{line}</text>')
a(f'<line class="stub" x1="{DEV_X1}" y1="200" x2="{BAND_X0}" y2="200"/>')

# power module
a(f'<rect class="mod" x="{DEV_X0}" y="268" width="{DEV_X1-DEV_X0}" height="60" rx="3"/>')
a(f'<text class="t" x="{DEV_X0+8}" y="286">Power Module</text>')
a(f'<text class="d" x="{DEV_X0+8}" y="303">13.8 V in · fuse</text>')
a(f'<text class="d" x="{DEV_X0+8}" y="320">12 V relay · 5 V / 3V3</text>')
a(f'<line class="stub" x1="{DEV_X1}" y1="298" x2="{BAND_X0}" y2="298"/>')

# ---- antenna devices + antenna port modules ----
for i, (aid, name, kind, fitted) in enumerate(antennas):
    cx = ant_cx(i)
    x0 = ANT_X0 + i * ANT_PITCH
    cls = "" if fitted else " spare"
    # antenna glyph
    a(f'<g class="ant{cls}"><line class="wire" x1="{cx}" y1="60" x2="{cx}" y2="{ANT_MOD_Y0}"/>'
      f'<line class="wire" x1="{cx-12}" y1="44" x2="{cx}" y2="60"/><line class="wire" x1="{cx+12}" y1="44" x2="{cx}" y2="60"/>'
      f'<line class="wire" x1="{cx-12}" y1="44" x2="{cx+12}" y2="44"/></g>')
    # hop over the control band
    a(f'<rect class="hop" x="{cx-4}" y="{BAND_Y0-1}" width="8" height="{BAND_Y1-BAND_Y0+2}"/>')
    a(f'<line class="wire{cls}" x1="{cx}" y1="{BAND_Y0-1}" x2="{cx}" y2="{BAND_Y1+1}"/>')
    a(f'<text class="t{cls}" x="{cx+7}" y="80">{aid} · {name}</text>')
    if kind:
        a(f'<text class="d{cls}" x="{cx+7}" y="96">{kind}</text>')
    # module
    a(f'<rect class="mod{cls}" x="{x0}" y="{ANT_MOD_Y0}" width="{ANT_W}" height="{ANT_MOD_Y1-ANT_MOD_Y0}" rx="3"/>')
    a(f'<text class="t{cls}" x="{cx}" y="{ANT_MOD_Y0+18}" text-anchor="middle">Ant Port {aid[1]}</text>')
    lines = ["SO-239 + surge", "idle→GND relay", "RX-only lock" if kind == "RX only" else "I2C @ SLOT_ID"]
    for k, line in enumerate(lines):
        a(f'<text class="d{cls}" x="{cx}" y="{ANT_MOD_Y0+36+k*16}" text-anchor="middle">{line}</text>')
    # stub to control band
    a(f'<line class="stub{cls}" x1="{x0+ANT_W-12}" y1="{BAND_Y1}" x2="{x0+ANT_W-12}" y2="{ANT_MOD_Y0}"/>')
    # RF bus line down the matrix
    a(f'<line class="rf{cls}" x1="{cx}" y1="{ANT_MOD_Y1}" x2="{cx}" y2="{BUS_Y1}"/>')

# ---- radio rows ----
for i, (rid, name, detail, modname, fitted, rx_only) in enumerate(radios):
    y0 = row_y(i); ym = y0 + ROW_H / 2
    cls = "" if fitted else " spare"
    # device
    a(f'<rect class="ext{cls}" x="{DEV_X0}" y="{y0+8}" width="{DEV_X1-DEV_X0}" height="{ROW_H-16}" rx="3"/>')
    a(f'<text class="t{cls}" x="{DEV_X0+8}" y="{y0+28}">{rid} · {name}</text>')
    if detail:
        a(f'<text class="d{cls}" x="{DEV_X0+8}" y="{y0+45}">{detail}</text>')
    # coax + PTT into module, hopping the band
    yc, yp = ym - 12, ym + 14
    for yy, klass in ((yc, "rf"), (yp, "ptt")):
        if klass == "ptt" and (rx_only or not fitted):
            continue
        a(f'<rect class="hop" x="{BAND_X0-1}" y="{yy-4}" width="{BAND_X1-BAND_X0+2}" height="8"/>')
        a(f'<line class="{klass}{cls}" x1="{DEV_X1}" y1="{yy}" x2="{MOD_X0}" y2="{yy}"/>')
    a(f'<text class="d{cls}" x="{DEV_X1+3}" y="{yc-4}">coax</text>')
    if fitted and not rx_only:
        a(f'<text class="d" x="{DEV_X1+3}" y="{yp+12}">PTT</text>')
    # module
    a(f'<rect class="mod{cls}" x="{MOD_X0}" y="{y0}" width="{MOD_X1-MOD_X0}" height="{ROW_H}" rx="3"/>')
    a(f'<text class="t{cls}" x="{MOD_X0+8}" y="{y0+18}">{modname} · slot {i+1}</text>')
    if rx_only:
        lines = ["6× SPST RF relays, max 1 closed", "TX-mute relay ← PTT bus (hw)", "I2C exp @ SLOT_ID · drv · /RLY_EN"]
    elif fitted:
        lines = ["PTT changeover relay: TX path / RX path", "2× 6 SPST relays, max 1 closed / path", "PTT in (opto) → PTT bus · TX sense", "I2C exp @ SLOT_ID · drv · /RLY_EN"]
    else:
        lines = ["same card, not fitted"]
    for k, line in enumerate(lines):
        if line:
            a(f'<text class="d{cls}" x="{MOD_X0+8}" y="{y0+35+k*16}">{line}</text>')
    # stub module → band (control)
    a(f'<line class="stub{cls}" x1="{BAND_X1}" y1="{y0+ROW_H-8}" x2="{MOD_X0}" y2="{y0+ROW_H-8}"/>')
    # RF path(s) across matrix: TX-capable radios get a TX row and an RX row
    paths = [("TX", ym - 16), ("RX", ym + 16)] if (fitted and not rx_only) else [("", ym)]
    for pname, py in paths:
        a(f'<line class="rf{cls}" x1="{MOD_X1}" y1="{py}" x2="{MAT_X1}" y2="{py}"/>')
        if pname:
            a(f'<text class="d" x="{MOD_X1+5}" y="{py-4}">{pname} path</text>')
        for j, (aid, _, _, afit) in enumerate(antennas):
            cx = ant_cx(j)
            both = fitted and afit
            if (rid, pname, aid) in closed:
                a(f'<circle class="relay on" cx="{cx}" cy="{py}" r="7"/>')
            else:
                a(f'<circle class="relay{"" if both else " spare"}" cx="{cx}" cy="{py}" r="5"/>')

# matrix label
a(f'<text class="d" x="{MAT_X1}" y="{BUS_Y1+14}" text-anchor="end">RF matrix · 4 radio slots × 6 antenna lines · one SPST relay per crossing</text>')

a('</svg>')
svg = "\n".join(s)

# ---------- page ----------
html = f'''<title>Shack Relay Matrix</title>
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
h1 {{ font-size:26px; font-weight:600; margin:0; letter-spacing:-0.01em; text-wrap:balance; }}
h2 {{ font-size:13px; font-weight:600; text-transform:uppercase; letter-spacing:0.08em; color:var(--ink2); margin:36px 0 10px; }}
.eyebrow {{ font-family:var(--mono); font-size:12px; color:var(--ctl); letter-spacing:0.04em; }}
.lede {{ color:var(--ink2); max-width:70ch; margin:0 0 20px; }}
figure {{ margin:0; background:var(--panel); border:1px solid var(--grid); border-radius:4px; padding:16px; overflow-x:auto; }}
figure svg {{ display:block; min-width:900px; width:100%; height:auto; color:var(--ink); }}
figcaption {{ font-size:13px; color:var(--ink2); margin-top:12px; display:flex; flex-wrap:wrap; gap:6px 22px; }}
.key {{ display:inline-flex; align-items:center; gap:6px; }}
.key i {{ display:inline-block; width:14px; height:3px; background:var(--rf); }}
.key i.ctl {{ background:var(--ctl); height:8px; opacity:.55; }}
.key i.ptt {{ background:repeating-linear-gradient(90deg,var(--rf) 0 3px,transparent 3px 6px); }}
.key b {{ display:inline-block; width:12px; height:12px; border-radius:50%; border:2px solid var(--ink); box-sizing:border-box; }}
.key b.on {{ background:var(--on); border-color:var(--on); }}
.key b.sp {{ border-color:var(--spare); border-style:dashed; }}
/* svg classes */
.mod {{ fill:var(--panel); stroke:var(--ink); stroke-width:1.4; }}
.ext {{ fill:none; stroke:var(--line); stroke-width:1.2; stroke-dasharray:none; }}
.mod.spare, .ext.spare {{ stroke:var(--spare); stroke-dasharray:5 4; }}
.bus {{ fill:var(--ctl-soft); stroke:var(--ctl); stroke-width:1; }}
.buslbl {{ font-family:var(--mono); font-size:10px; fill:var(--ctl); }}
.stub {{ stroke:var(--ctl); stroke-width:2; }}
.stub.spare {{ stroke:var(--spare); }}
.rf {{ stroke:var(--rf); stroke-width:2; fill:none; }}
.rf.spare {{ stroke:var(--spare); stroke-dasharray:6 5; }}
.wire {{ stroke:var(--rf); stroke-width:1.4; fill:none; }}
.ant.spare .wire, .wire.spare {{ stroke:var(--spare); stroke-dasharray:6 5; }}
.ptt {{ stroke:var(--rf); stroke-width:1.4; stroke-dasharray:3 3; }}
.hop {{ fill:var(--panel); }}
.relay {{ fill:var(--panel); stroke:var(--ink); stroke-width:1.6; }}
.relay.spare {{ stroke:var(--spare); stroke-dasharray:2 2; }}
.relay.on {{ fill:var(--on); stroke:var(--on); }}
.t {{ font-family:var(--sans); font-size:12px; font-weight:600; fill:var(--ink); }}
.d {{ font-family:var(--mono); font-size:10px; fill:var(--ink2); }}
.t.spare, .d.spare {{ fill:var(--spare); }}
/* tables */
.grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:24px 40px; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th {{ text-align:left; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--ink2); font-weight:600; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); }}
td {{ padding:8px 10px 8px 0; border-bottom:1px solid var(--grid); vertical-align:top; }}
td:first-child {{ font-weight:600; white-space:nowrap; }}
code {{ font-family:var(--mono); font-size:12.5px; color:var(--ctl); }}
p {{ max-width:70ch; }}
ol {{ max-width:70ch; padding-left:20px; }}
ol li {{ margin-bottom:6px; }}
</style>
<main>
<header>
  <span class="eyebrow">NOWOS shack · HF antenna switch · rev A block diagram</span>
  <h1>Shack Relay Matrix</h1>
</header>
<p class="lede">A 4-slot × 6-line radio-by-antenna crossbar. Every card plugs into one I2C control backplane; RF stays on a separate matrix. Adding a radio or an antenna is one more card, no controller change. The picture shows today's example state: FT-710 transmitting on the doublet and receiving on the vertical, Airspy listening on the Loop-on-Ground.</p>

<figure>
{svg}
<figcaption>
  <span class="key"><i></i> RF path (coax / matrix)</span>
  <span class="key"><i class="ptt"></i> PTT, open-collector</span>
  <span class="key"><i class="ctl"></i> control backplane</span>
  <span class="key"><b class="on"></b> relay closed (example state)</span>
  <span class="key"><b></b> relay open</span>
  <span class="key"><b class="sp"></b> not fitted yet</span>
</figcaption>
</figure>

<div class="grid2">
<section>
<h2>Modules</h2>
<table>
<tr><th>Card</th><th>What is on it</th></tr>
<tr><td>Controller</td><td>MCU (I2C master), USB-C with UART/CDC and a plain ASCII command set, hardware watchdog driving <code>/RLY_EN</code>, optional OLED + encoder front panel, header for a later Ethernet/Wi-Fi add-on. Holds the routing table and the interlock rules.</td></tr>
<tr><td>Power</td><td>13.8 V station supply in, fuse, 12 V relay rail, 5 V and 3V3 for logic. Separate returns for relay and logic current, joined at one point.</td></tr>
<tr><td>Radio Port</td><td>One SO-239 for the radio, then a PTT-driven SPDT changeover relay that steers the radio to a TX path (keyed) or an RX path (unkeyed). Each path has six SPST RF relays, one per antenna line; firmware allows at most one closed per path. Same antenna on both paths gives ordinary single-antenna operation. Opto-isolated PTT input drives that slot's <code>PTT[n]</code> line on the backplane. RF sense (diode detector) confirms TX is actually present. I2C expander addressed by the slot's hardwired <code>SLOT_ID</code>, relay drivers gated by <code>/RLY_EN</code>.</td></tr>
<tr><td>Radio Port, RX variant</td><td>Same card without the PTT input. Adds a TX-mute relay that shorts the receiver port whenever any <code>PTT[n]</code> is active. That is hardwired from the PTT bus, not via firmware, so a hung MCU cannot leave the Airspy exposed.</td></tr>
<tr><td>Antenna Port</td><td>One SO-239, gas-discharge surge arrestor, relay that grounds the antenna when no radio is routed to it. An antenna flagged RX-only (the LoG) is refused to any TX-capable radio in firmware.</td></tr>
<tr><td>Backplane</td><td>Passive PCB. Control signals only, no RF. Slot position sets <code>SLOT_ID</code>, so cards need no jumpers and any card fits any slot of its type.</td></tr>
</table>
</section>

<section>
<h2>Backplane signals</h2>
<table>
<tr><th>Signal</th><th>Purpose</th></tr>
<tr><td><code>+12V RLY</code></td><td>Relay coil rail, fused per card.</td></tr>
<tr><td><code>+5V / +3V3</code></td><td>Logic supply.</td></tr>
<tr><td><code>SDA / SCL</code></td><td>I2C, controller is the only master. Up to 8 expanders per bus; more via a mux if a second chassis is ever daisy-chained.</td></tr>
<tr><td><code>/INT</code></td><td>Wired-OR interrupt from expanders (PTT edge, fault).</td></tr>
<tr><td><code>PTT[1..4]</code></td><td>One line per radio slot, driven by that slot's Radio Port card, readable by every card. Carries the hardware RX protection.</td></tr>
<tr><td><code>/RLY_EN</code></td><td>Global relay enable from the controller watchdog. Released, every antenna-select relay opens and every antenna port falls to ground: the safe state.</td></tr>
<tr><td><code>SLOT_ID[2:0]</code></td><td>Hardwired per slot, read by the card to set its I2C address.</td></tr>
</table>

<h2>Rules the controller enforces</h2>
<ol>
<li>One radio per antenna line, one antenna per radio. Two TX radios can never share a line.</li>
<li>No antenna-select relay moves while that radio's <code>PTT</code> is active (hot-switch lockout). RX-mute relays are exempt because they are driven straight from the PTT bus.</li>
<li>Break before make, with a settle delay between opening the old path and closing the new one.</li>
<li>RX-only antennas may sit on a radio's RX path, never on its TX path.</li>
<li>The changeover relay is driven from the PTT bus in hardware. The radio's TX delay (FT-710 menu, external-amp keying delay) must exceed the relay transfer time so RF never hits a moving contact.</li>
<li>Loss of watchdog kick, USB command timeout or brown-out drops <code>/RLY_EN</code>.</li>
</ol>
</section>
</div>

<h2>Expansion path</h2>
<p>Second transceiver: fit a Radio Port card in slot 3, run its PTT to the card, add one line to the routing table. Vertical antenna: fit Antenna Port 3, which is already wired to line A3. Beyond 4 × 6, either a second chassis on the same USB host with its own controller, or a controller firmware option to drive a second backplane through an I2C mux. Remote relay boxes at the mast base would replace the I2C link with RS-485 on the same card footprint; the backplane signal set is chosen so that swap is a transceiver change, not a redesign.</p>
</main>
'''

out = "/mnt/user-data/outputs/shack-relay-matrix.html"
open(out, "w").write(html)
print(out, len(html))
