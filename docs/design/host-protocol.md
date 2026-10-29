# Host protocol: Mac or Pi to shack interface

Status: v0.1, 2026-10-29. Reviewed by Prins; P3b-01 to P3b-04 and C-1 to C-3 decided as proposed. Firmware phase P3b (firmware/PLAN.md).
Implementation: crate `host-proto` (firmware/crates/host-proto), used by shack-core and by the Mac tools.

## 1. Scope

This document sets the protocol between a host (the Mac now, the Raspberry Pi 5 later) and the shack interface MCU over USB.
One protocol for both hosts (D-68).

The host asks. The shack interface decides. Nothing in this protocol can:

- clear the SAFE latch (only the RESET button can, D-64, D-65, D-75),
- give a permit that the box did not report (D-63),
- key a radio without its permit (TX INH and keying are gated in hardware, D-71).

The host can always make things safer: stop, end TX, release keys.

## 2. Transport

| Item | Value | Source |
|---|---|---|
| Port | ESP32-C3 USB Serial/JTAG, through the DevKit USB-C and the rear panel extension | D-96, D-185 |
| Host side | CDC serial device, for example `/dev/cu.usbmodem*` on the Mac, `/dev/ttyACM0` on the Pi | |
| Isolation | Delock 64226 at the Mac side | A-16, D-185 |
| Baud rate | Not used (USB full speed) | |

The same port also carries the ROM boot messages after a reset and is the flash port. The protocol must survive text it does not know (section 3).

## 3. Format: text lines

Plain ASCII text, one message per line (P3b-01).

- A host line ends with CR, LF or CR LF, so a plain serial terminal works (Enter sends CR). An empty line is no command: no answer, but it counts for the keep-alive. Maximum 120 characters without the line end.
- The shack ends its lines with CR LF. Hosts strip the line end.
- Words are separated by one or more spaces. Keywords are lower case; radio and column names are not case sensitive.
- The first character of a line from the shack tells the line type:

| Start | Line type | Example |
|---|---|---|
| `ok` | Answer: command done or accepted | `ok` |
| `err` | Answer: command refused | `err txbusy R2 is transmitting` |
| `!` | Event, sent when something changes | `!tx R2 permitted` |
| `#` | Log text, for people only | `# expander ready` |

A host ignores every line that does not start with one of these. So the boot ROM text and noise do no harm.

Every command gets exactly one answer line (`ok` or `err`), in the order the commands came. Events and log lines can come between commands and answers. A host matches answers by order, not by content.

Why text and not binary (postcard + COBS, the first idea in PLAN.md): you can drive and read the interface by hand with any serial terminal; the Pi and Mac tools are short scripts; USB already checks every packet, so the frame CRC of the box link is not needed here.

## 4. Names and values

| Item | Values |
|---|---|
| radio | `R1`, `R2`, `R3` |
| column | `A1` to `A4`, `EXP`, `-` (none) |
| column list | columns joined by commas, for example `A2,A3`, or `-` for none |
| on/off | `on`, `off` |
| band | 0 to 15: FT-710 BAND D C B A as a 4-bit number (D-86). Decoding to metres is done on the host |

## 5. Commands

| Command | Does | `ok` answer |
|---|---|---|
| `hello` | Identify | `ok shack fw <x.y.z> proto 1` |
| `status` | Full state, one line (section 7) | `ok <key=value ...>` |
| `route <radio> <tx col> <rx col>` | Route a radio. Sent to the box; the result comes as an event | `ok` (queued) |
| `tx <R2\|R3> on\|off` | Ask for TX permit (handshake) or end TX | `ok` |
| `key <radio> on\|off` | Key the radio through the interface. Works only while its permit is out | `ok` |
| `bias <column list>` | Bias-T feeds on for these columns, off for the rest | `ok` (queued) |
| `stop on\|off` | Software stop: opens the SAFE loop. `off` closes it again; the SAFE latch still needs RESET | `ok` |
| `clearfault` | Clear the shack fault latch (LATCH_CLR edge) after a supervisor reset (P3b-04) | `ok` |
| `events on\|off` | Events on (default) or off | `ok` |
| `keepalive <seconds>` | Host keep-alive time-out, 2 to 60 s (section 8) | `ok` |
| `page b\|c\|auto` | Display page: B flow (default), C cards, or auto (B 10 s, C 5 s). The Safe stop screen always takes over on a blocking problem (Prins, 2026-10-29) | `ok` |

Error answers: `err <code> <text>`. Codes:

| Code | Meaning |
|---|---|
| `syntax` | Unknown command or wrong number of words |
| `arg` | A value out of range (radio, column, on/off) |
| `linkdown` | The box link is down (tx on, route, bias) |
| `notforr1` | `tx` for R1; R1 uses the hardware PTT loop |
| `txbusy` | Route change for a radio that transmits or ends TX (F13) |
| `queuefull` | Too many commands wait for the box; try again |
| `toolong` | Line longer than 120 characters |
| `nofault` | `clearfault` while no fault is known |

## 6. Events

Sent on every change (when events are on). One line each.

| Event | When |
|---|---|
| `!link up` / `!link down` | Box link state (link-protocol.md section 6) |
| `!expander ready` / `!expander lost` | Shack expander set up, or lost (all permits dropped) |
| `!fault` | A supervisor reset was seen after start-up: TX blocked until `clearfault` |
| `!safe ok` / `!safe lost` | SAFE loop current (GPIO21) |
| `!latched 1` / `!latched 0` | SAFE latch (expander input) |
| `!kill 1` / `!kill 0` | KILL switch pressed |
| `!band <n>` | R1 band data changed |
| `!tx <radio> <state>` | `idle`, `requesting`, `permitted`, `ending`, `releasing` |
| `!permit <radio> on\|off` | PERMIT line changed (all radios, R1 included) |
| `!refused <command words> <result>` | The box refused a command; result as in link-protocol.md 4.1, lower case |
| `!permitlost <radio>` | The box dropped a permit in use |
| `!txsense <radio> fault` | Keyed with permit for 500 ms without TX sense (F14) |
| `!route <radio> <tx col> <rx col>` | Route as read back from the box |
| `!host timeout` | Host keep-alive missed: TX ended (section 8) |

## 7. Status line

`status` answers one line with `key=value` pairs, in this order:

```
ok link=up safe=ok latched=0 kill=0 fault=0 stop=0 keepalive=2 page=b band=5 box=ready
   r1=A1/A1,permit=1,key=0 r2=A3/A3,tx=permitted,permit=1,key=1 r3=-/-,tx=idle,permit=0,key=0
   k1=A1,A3 rfdet=- bias=- boxfault=0
```

(One line on the wire; wrapped here for reading. About 200 characters: the 120-character limit is for host lines only. Unknown values read `?`, for example `box=?` before the first box status.)

## 8. Host keep-alive

Decided (P3b-03). A Mac app that crashes while R2 is keyed would leave a WSPR transmitter on until someone notices.

- While any `tx` is on or any `key` is on, the host must send a line at least every keep-alive time-out. Any line counts, an empty line too; `status` is the normal one.
- The time-out is 2 s. `keepalive <seconds>` sets it from 2 to 60 s, for typing by hand (Prins, 2026-10-29). It goes back to 2 s at every power-up. A host app leaves it at 2 s.
- No line within the time-out: the shack ends every TX and releases every key, the normal way (inhibit first, F14), and sends `!host timeout`.
- Routes, bias and the software stop stay as they are.

## 9. Timing

- The shack reads host lines every tick (10 ms) and answers in the same tick.
- Commands that go to the box (`route`, `tx on`, `bias`) answer `ok` when queued. The result comes as an event, about 50 to 120 ms later (link-protocol.md 5.1).

## 10. Implementation (P3b)

- `host-proto` (no_std): line parser into a `HostCommand` enum, and formatters for answers, events and the status line into a fixed buffer. Fuzz test: no panic on any input.
- shack-core: `Shack::host_line(now, &str) -> answer` and an event formatter; keep-alive timer in `tick`.
- Simulator: the USB port as a byte channel on the board model. `sim-shack --pty` opens a pseudo-terminal, so a real terminal or a Mac script can talk to the simulated interface. Same commands, same answers as the real one.

## 11. Open points

- **P3b-01 Format. Decided (Prins, 2026-10-29): option 1.** Option 1: text lines (this document). Option 2: binary frames (postcard + COBS), smaller and typed, but needs a tool to read. Proposal: option 1.
- **P3b-02 Log output. Decided (Prins, 2026-10-29): accepted.** The firmware writes log text only as `#` lines through this protocol, never as raw `println` on the USB port. Proposal: accept; the target uses a small log adapter.
- **P3b-03 Host keep-alive. Decided (Prins, 2026-10-29): accepted.** 2 s, ends TX and keys only. Proposal: accept.
- **P3b-04 `clearfault`. Decided (Prins, 2026-10-29): option 1.** Clears the shack fault latch from the host after a supervisor reset (watchdog or brown-out) during operation. The firmware cannot read FAULT directly (it is not on the expander); it knows a fault happened when the expander was reset. The SAFE latch is not touched. Option 1: allow from the host, logged. Option 2: no command; a power cycle is needed. Proposal: option 1. The hardware still gates TX by the SAFE latch, the permits and the box.

Choices from P3a, confirmed by Prins (2026-10-29):

- **C-1 R1 permit.** PERMIT_R1 on while the box is READY and R1 has a TX column with K1 on; off while an R1 route change is pending or running.
- **C-2 Fault after start-up.** After an expander reset during operation, the firmware sets the expander up again but does not clear the fault latch by itself. `clearfault` (P3b-04) is the way back.
- **C-3 F14 plausibility.** 500 ms keyed with permit and no TX sense: the port is flagged (`!txsense`). TX is not blocked.
