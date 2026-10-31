# Shack interface board rev A: definition (2026-09-29)

Status: all sheets drawn (M-13 to M-17): link, power, MCU, SAFE, radio port (one sheet, three instances). ERC clean. Decisions D-62 to D-97 in claude/design-log.md.

## Role
- Shack end of Cat6 #1 to the matrix box. Powers all 4 opto current loops.
- Bridges the Mac (and later a Raspberry Pi 5) to the box protocol over USB.
- Holds the SAFE loop latch and the per-radio TX permits in hardware.
- Works stand-alone: only its USB-C to the Mac, through the Delock 64226 isolator hub (A-16). The Pi 5 and its display come later (D-69).

## Blocks
- MCU: ESP32-C3-DevKit-RUST-2 on sockets, same as the box (D-66). USB-C to the Mac or the Pi. On-board buck off (ENABLE to GND), 3.3 V from the board.
- Supervisor and fault latch: TPS3823A-33 and 74LVC1G74, as the box (D-59). Gates all permits.
- IO expander: PCA9539 on the board I2C, polled (D-68). Inputs: latch state, KILL state, FT-710 BAND A to D. Outputs: software stop, per-radio LEDs.
- Link: 4 loops on Cat6 #1, T568B. Pair 1 data to box, pair 2 PTT (R1 K0), pair 3 SAFE, pair 4 data from box.
  - Each loop: PNP current source BCP53 + BC857, Rsense 56 ohm, 8.8 to 12.5 mA (D-74, D-79, C-24). Entry: GDT, 2 x 47R, SMBJ15CA.
  - No optos at the shack end (D-80): pair 1 source switched by the MCU; pairs 3 and 4 sensed by a resistor in the return; pair 2 source switched by the R1 TX sense output in hardware.
- Radio port parts: TX INH TLP4176G (second source Panasonic AQY412S; CPC1117N end of life, D-106), LED 7 mA (D-77, C-22); TX sense PC817X with 1N4148W anti-parallel (D-78, C-23).
- SAFE loop: KILL switch, sense resistor in the return (D-80), software stop by the current source (SW_STOP_N).
- SAFE latch (D-75, D-84): 74LVC1G74, PRE_N = SAFE_OK AND POR_N (second TPS3823A-33, WDI open); RESET button 1k / 100k / 1N4148W / 100n into a 74LVC1G14. TX_EN = NOR(FAULT, LATCHED) to the radio ports. Front panel J6: RESET button, SAFE and LATCHED LEDs. KILL state J7: second pole of the KILL switch.
- Radio ports R1 to R3, identical, mini-DIN 8 (FT-710 TUNER/LINEAR pin-out), adapter cable per radio (D-71, D-72):
  - TX INH: form B PhotoMOS, LED = permit AND SAFE latch; jumper LOW / HIGH / removed. HIGH = 5.1 V from pin 6 through 2k2 and a zener (D-90).
  - Keying: form A photorelay TLP176AM (second source AQY212G3HS) to the radio PTT input, after the permit (D-91).
  - TX sense: opto input; jumper CONTACT / VOLTAGE.
  - ESD: TVS 15 V and 1 nF per line to the radio GND (RGND) at the connector; RGND to CHASSIS by 10 nF 1 kV (D-89).
  - Pin 1: solder jumper per port, BAND D (R1) or KEY (R2, R3) (D-86). BAND A to D to the expander from R1 only.
  - Connector: Same Sky MD-80SM, footprint for date codes after 2022-03-03 (D-85). Voltage factor: documented exception (D-87).
- Power: 13.8 V input, fuse, reverse protection, TVS; linear 13.8 V to 5 V (D-73); LD1117S33 for 3.3 V (D-81).
- Housing: own board in an aluminium housing, connectors on panels (D-70); 7805 in TO-220 on the housing wall (D-82).

## MCU pin map (D-83, D-92)
Direct: IO0 PERMIT_R1, IO1 WDI, IO3 LATCH_CLR, IO4 PERMIT_R2, IO5 PERMIT_R3, IO6 DATA_TX, IO20 DATA_RX, IO21 SAFE_LOST (1k series). I2C: SDA IO10 (RUST-1) or IO7 (RUST-2) by JP61, SCL IO8. IO2, IO9 unused (strapping). Header pins 17, 18 not connected.
PCA9539 0x74 (D-92): IO0_0 SW_STOP_N (out), IO0_1 R1_TX, IO0_2 KEY_R1 (out), IO0_3 BAND_D, IO0_4 BAND_A, IO0_5 BAND_B, IO0_6 BAND_C, IO0_7 LED_R1 (out), IO1_0 KEY_R2 (out), IO1_1 R2_TX, IO1_2 LED_R2 (out), IO1_3 KEY_R3 (out), IO1_4 R3_TX, IO1_5 LED_R3 (out), IO1_6 KILL_S, IO1_7 LATCHED. Unmarked = input. RESET = RESET_N, INT not used. Write outputs 0 before configuring (F1).
Schematic: the DevKit (DevKit-RUST-1 Rev 1.2a in use) is one board symbol A1 with the esp-rs pad numbers: left 1..16, right 28..17 top to bottom; footprint ESP32-C3-DevKit-RUST_Socket, gold Sullins socket headers PPPC161LFBN-RC and PPPC121LFBN-RC, DevKit 11.05 mm above the board (D-95); net labels at its pins (D-93). SDA select JP61: 1-2 bridged by copper = RUST-1 (SDA IO10, pad 17); RUST-2 (SDA IO7, pad 12): cut 1-2, bridge 2-3 (D-94, D-192). USB D-/D+ on pads 20/19 (IO18/IO19), also to the own USB-C J14 at the housing wall with ESD array U61 USBLC6-2SC6 and CC pull-downs 5.1k (D-96).

## Open
- Loop sense thresholds (pairs 3, 4) against 8.8 to 12.5 mA.
- Common footprint for TLP4176G, AQY412S and CPC1117N (lead span 6.1 to 7.0 mm, D-99).
- Firmware rules F11 to F14 (verify_system.py).
- FT-710 TX INH level (A-15).
- Current budget and regulator heat sinking.
- Radio port: keying photorelay TLP176AM, second source AQY212G3HS (D-91); common long-pad footprint for TX INH and keying to draw; INH HIGH level now clamped to 5.1 V (D-90), bench test open; PCA9539 5.5 V tolerance; TVS and ESD ratings (D-89); MD-80SM footprint.
- Netlist topology checks for the shack board in verify_system.py.
- USB-C J14 (D-96): USB4105-GF-A second source, wall cut-out with the layout, panel label (use one USB-C at a time). ESD array: ST USBLC6-2SC6, second source UMW USBLC6-2SC6 (datasheets filed, C-26).
- Drawing rule D-92: done for all sheets (M-25). Accepted crossings: 3 on the root (R1_TX), 2 in the SAFE sheet (D-97).
- Box side drawn (M-30): READY switch U6 TLP176AM with gate U15 (D-101), loop 3 named SAFE, R52/R53 DNP, U903 IO1_3/IO1_4 as K0 outputs. verify_logic.py and verify_system.py pass. Diagrams L1 to L3, T1 to T4, F1, F2: hardware/docs/diagrams (M-31).
