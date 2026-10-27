# HF Antenna Switch – Architecture

Status: draft v0.1, 2026-09-09
Owner: Prins

## 1. Purpose

Programmable HF antenna switch that:

- routes the FT-710 to a TX antenna and, independently, to any RX antenna;
- routes the Airspy HF+ (receive only) to any RX antenna;
- makes it physically impossible to transmit into the Loop on Ground (LoG);
- allows fast manual RX antenna comparison from a control head in the shack;
- is configurable over USB-UART and stores presets;
- scales to a second or third transceiver without redesign.

## 2. Station inventory

| Item | Role | Notes |
|---|---|---|
| Yaesu FT-710 | TRX 1 | Single ANT port, 100 W. TUNER/LINEAR jack: TX GND (80 mA open collector), TX INH input, +13 V out, band data A–D |
| Airspy HF+ Discovery | RX 1 | Receive only, fragile front end (approx. +10 dBm max) |
| Future TRX | TRX 2/3 | May or may not have a TX inhibit input |
| Doublet | A1 | TX + RX |
| Vertical (planned) | A2 | TX + RX |
| Loop on Ground | A3 | RX only, preamp at feedpoint |
| Spare | A4 | Reserved |

Constraints agreed: exclusive antenna assignment (no splitters), 100 W max, relay box outdoors, control head in the shack.

## 3. Top-level structure

Two independent switch fabrics, one hardware interlock between them.

```
 Shack                         Outdoor relay box                    Antennas
 -----                         -----------------                    --------
 FT-710  --coax------------->  TX path (T/R relay + TX select) ---> Doublet
         --PTT/TX INH------->  Sequencer                            Vertical
 HF+     --coax------------->  RX matrix (1-of-N per receiver) ---> LoG (RX only)
 Future  --coax + PTT------->  RX protection (shorting relays)      Spare
 Control head --CAT6-------->  Relay MCU, RS-485, 12 V
```

### 3.1 TX bus (high power)

Per transceiver:

- T/R relay: SPDT/DPDT power relay (Omron G2RL-2 class, 16 A). NC = radio to its RX matrix output. NO = radio to its TX antenna selector. Second pole used as a confirmation contact for the sequencer.
- TX antenna selector: 1-of-2 (later 1-of-3) power relays choosing among TX-capable antennas only.

The LoG is not wired to any TX selector. No firmware state can put RF into it. This is the interlock.

### 3.2 RX matrix (low power)

Per receiver a 1-of-N selector built as a relay tree (3 signal relays for 4 sources, Omron G5V-2 or Axicom IM). All antennas are tapped for RX at their antenna port. Exclusive assignment enforced in firmware: an antenna serving as a radio's TX antenna may only be received on by that same radio.

Isolation of an open signal relay is roughly 50 dB at 30 MHz. Sufficient for protection, not for simultaneous RX on a nearby antenna during TX (SO2R / diversity). Leave board space for a bandpass stage if that ever becomes a requirement.

### 3.3 RX protection

On any PTT: a shorting relay grounds each idle receiver input. Back-to-back diode pair behind it as second layer. Driven from the PTT lines through hardware, not via the MCU. Release after a 20–30 ms hold so RX reconnects only after RF has fully dropped.

### 3.4 LoG preamp

Preamp at the loop feedpoint, powered by bias-T through the relay box. Not inside the box: feedline loss ahead of the preamp would negate the low-band noise floor advantage.

## 4. FT-710 T/R sequencing

The single ANT port forces an external T/R relay on the FT-710 coax. This is the only place hot-switching can occur, so it gets a true sequencer using the radio's TX INH input.

### 4.1 Radio configuration

- Menu: TUN/LIN PORT SELECT = LINEAR
- Menu: TX INHIBIT OPERATION SETTING = ON (default is OFF; without it the TX INH pin is ignored)

### 4.2 Sequence

1. TX GND goes low (PTT). Driver stage (MOSFET or ULN2003) energises the T/R relay directly. MCU only observes.
2. TX INH is held in the inhibit state by default.
3. When the relay's confirmation contact proves the armature has moved, logic releases TX INH. RF can now flow.
4. On PTT release: re-assert TX INH first, then drop the relay after a 20–30 ms hold.

Positional feedback instead of a timer: independent of relay ageing and temperature.

Known limitation: inhibit-based sequencing kills RF but not keying, so CW full break-in (QSK) is not usable. Semi break-in is fine.

### 4.3 Open item: TX INH polarity

Sources disagree. FT-817 family: +12 V on TX INH inhibits, ground releases. FC-40 tuner protocol notes: pin pulled low to inhibit. Verify on the FT-710 with a dummy load, LINEAR mode, TX INHIBIT menu ON, before designing the driver. Record the result here.

### 4.4 Measurement plan: PTT-to-RF delay

- Ch1: TX GND, DC coupled, trigger falling edge, single shot.
- Ch2: RF sample via 40 dB tap or pickup loop near the dummy load coax. Never probe the coax centre directly at 100 W.
- Test at 5 W in FM, CW (semi break-in), DATA-U, SSB with tone. Record rise delay per mode and fall time on release.
- Result determines hold-off timing and confirms the inhibit is doing real work.

### 4.5 Power for inhibit logic

Use the radio's +13 V OUT (TUNER/LINEAR jack) to power only the inhibit logic at the radio end. The inhibit is then asserted whenever the radio is on, even with the outdoor box unpowered.

### 4.6 Radios without TX inhibit

Sequencer stage is optional per TX channel. Fallback for a radio without inhibit: faster T/R relay (5 ms reed or small coax relay) plus measured margin, and the same release hold.

## 5. Control architecture

### 5.1 Control head (shack)

- MCU: RP2040 or ESP32.
- USB-UART command interface, CAT-style plain text.
- One rotary encoder per receiver for quick antenna comparison.
- Small OLED showing the routing table.
- Stores presets.

### 5.2 Relay box (outdoor)

- Second MCU, same firmware image, role set by jumper.
- Relay drive, PTT sensing, confirmation-contact sensing.
- Watchdog: if the RS-485 bus is silent for a few seconds, fall back to a stored default routing.
- Relay rest positions chosen so that an unpowered box gives FT-710 to doublet direct and the SDR disconnected. A control failure never leaves the station without a working radio.

### 5.3 Shack-to-box cable

One CAT6 run plus one coax per radio.

| Pairs / wires | Function |
|---|---|
| 2 pairs | 12–13.8 V supply (box draws approx. 0.5 A) |
| 1 pair | RS-485 half duplex |
| Remaining conductors | One discrete PTT line per TRX |

PTT lines are hard-wired because the safety chain must not depend on the serial link.

### 5.4 Command set (draft)

```
SET RX <rx-id> <ant-id>      assign RX antenna to receiver
SET TX <trx-id> <ant-id>     assign TX antenna to transceiver
GET                          dump routing table
SAVE <n> / LOAD <n>          preset store / recall
STATUS                       PTT states, confirmation contacts, bus health
```

Firmware rules:

- Two radios cannot share a TX antenna.
- A TX antenna may only be received on by the radio transmitting on it.
- No TX assignment changes while any PTT is active.
- LoG is never a valid TX target (also enforced by wiring).

## 6. Physical layout

Modular: one TX module per TRX, one RX module per receiver, one antenna I/O board, one controller board. Adding a radio is a plug-in card. Estimated relay count with three TRX: 20–25.

Connectors: SO-239 on the TX bus and antenna ports, BNC on the RX side.

## 7. Open items

- [ ] Measure TX INH polarity on the FT-710 (section 4.3)
- [ ] Measure PTT-to-RF delay per mode (section 4.4)
- [ ] Confirm HF+ max input level from datasheet and size the limiter
- [ ] Decide LoG preamp type and bias-T voltage
- [ ] Confirm CAT6 run length and voltage drop budget
- [ ] Decide whether to use band data A–D for automatic antenna selection

## 8. Next steps

1. Bench measurements (open items 1 and 2).
2. Relay-by-relay schematic for one TX module and one RX module.
3. Firmware command set and state machine.
