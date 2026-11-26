# Test specification

Status: 0.2, 2026-11-25 (shack interface smoke test P-01 added). Tests are added as boards are built.
Results go in docs/test/reports/, one report per board revision.

## 1. Test levels

| Level | What | When |
|---|---|---|
| T0 Design checks | ERC, netlist checks, logic truth tables, timing desk checks | Before ordering PCBs (done in part, see design-log M-04 to M-32) |
| T1 Component and coupon | Single parts and test coupons (relay isolation, connector polarity) | Before layout release |
| T2 Board | Each board alone: power, logic, relays, loops | After assembly |
| T3 System | Shack interface and unit together, on a dummy load | Before use on air |
| T4 On air | Real antennas and radios | Last |

## 2. Test equipment

- NanoVNA-H4 (SOLT calibration)
- Oscilloscope, two channels, with RF sampler
- 100 W dummy load
- Lab power supply 13.8 V

## 3. Test cases

| Test ID | Requirement | Level | Test | Pass criterion | Status |
|---|---|---|---|---|---|
| TC-01 | DR-07, SR-04 | T0 | verify_logic.py and verify_system.py on the current netlists | All checks pass | done (M-08, M-11, M-30) |
| TC-02 | PR-04 | T1 | RT1 coupon: S21 coil off and on, S11, NC isolation, 1 to 54 MHz (M-01) | Limits to set (PR-04) | planned |
| TC-03 | – | T1 | XT60PW-M / XT30PW-M polarity on a real part (M-02) | Matches footprint | planned |
| TC-04 | SR-02, SR-03 | T3 | FT-710 TX INH response: time from TX INH active to RF off, and RF tail after PTT release (M-12) | To set | planned |
| TC-05 | SR-04 | T3 | Open each Cat6 pair in turn, press KILL, remove power, stop the watchdog | TX inhibited on all radios, all relays off | planned |
| TC-06 | SR-05 | T3 | After TC-05: restore the loop, check no restart without RESET | No relay or permit before RESET | planned |
| TC-07 | SR-01 | T3 | Try to route a TX row to A2 by every command path; check that K103, K203, K303 are not fitted (D-103); key each radio with its RX row on A2 and K0 held off (H2) | No path, no RF at A2 | planned. H2 (D-104): RF on A2 must open the SAFE loop, drop the relays and latch the shack; measure the time from RF to relays open (expected about 7 ms) |
| TC-08 | FR-01, FR-02 | T3 | Every radio to every antenna, TX and RX, on a dummy load | Path present, all other paths open | planned |
| TC-09 | FR-05 | T2 | Parked antenna: DC resistance to ground | 1 MΩ ± tolerance | planned |
| TC-10 | FR-06 | T2 | Bias-T: switch on, current limit, read-back | To set | planned |
| TC-11 | SR-08 | T2 | ESD on the radio port pins | No damage, function after test | planned |
| TC-12 | PR-01 | T3 | 100 W key-down, SWR 3:1, temperature rise of the RF board | To set | planned |
| TC-13 | – | T2 | Shack interface smoke test, without the DevKit: procedure P-01 (section 4) | All P-01 steps pass | planned |

## 4. Procedures

### P-01 Shack interface smoke test (TC-13)

Board: shack interface rev A, layout p8g. Scope: power rails, supervisor, SAFE latch and the loop sources, without the DevKit.

**Board state before the test**

- JLC parts fitted. By hand: C1, U1 (L7805CV, leads 3 mm or less), A1 sockets, J2, J6, J7, J11 to J13.
- Not fitted: the DevKit (A1), U203, U303, U403 (TX INH photorelays), the 9 jumper shunts.
- Nothing connected: no display on J15, no front panel on J6, no KILL switch on J2, no radio, no Cat6, no USB.
- U1 is not on the housing wall. Without the DevKit the 5 V load is small (about 0.3 W in U1), so free air is sufficient for this test. Do not fit the DevKit before U1 is on the wall.

**Equipment**

- Lab supply 13.8 V with current limit; multimeter; oscilloscope (step 5).
- For steps 6 and 7: an XH-2 jumper (or a wire link) for J2, a Cat6 patch cable with one end cut, two 470R 0.25 W resistors.

**Steps**

| Step | Action | Expected | Result |
|---|---|---|---|
| 1 | Visual check: U1 and C1 orientation, D1 (SS34) and D2 orientation, solder bridges on U4, U9 (VSSOP-8) and U5 (TSSOP-24). Measure the resistance from J3 + to GND, from TP2 (+5V) to GND and from TP3 (+3V3) to GND, both probe polarities | No short. Each value rises as the capacitors charge | |
| 2 | Reverse polarity: set the supply to 13.8 V, limit 5 mA. Disconnect everything else first (scope, meter, cables): an earthed instrument on board GND bypasses D1. Connect J3 reversed (clip leads) for 2 s. Set the limit back to 50 mA after this step | Below 1 mA (D1 blocks; SS34 leakage max 0.5 mA). Fuse F1 intact | |
| 3 | Correct polarity: set the limit to 50 mA, connect J3, switch on | Current about 10 to 25 mA (estimate: quiescent current of U1 and U2 plus logic). Current limit not reached. No part warm after 1 min (finger or thermal camera) | |
| 4 | Measure the rails against GND | TP1 +13V8: 13.3 to 13.7 V (supply minus about 0.3 V at D1). TP2 +5V: 4.80 to 5.20 V. TP3 +3V3: 3.23 to 3.37 V | |
| 5 | Supervisor and fault latch. With no MCU, WDI is held low by its pull-down, so U3 times out. Scope U3 pin 1 (RESET_N) and U4 pin 5 (FAULT) | RESET_N: low pulses of about 200 ms (140 to 280 ms) every 1.1 to 2.4 s. FAULT: high all the time. This shows that the watchdog runs | |
| 6 | SAFE latch, loop open. Measure J6 pin 2 (SAFE LED drive) and J6 pin 3 (LATCHED LED drive) against GND | Pin 2 low (no loop current). Pin 3 high, about 3.3 V (latched at power-up). Short J6 pin 1 to pin 4 (RESET): pin 3 stays high, because PRE_N is low without loop current | |
| 7 | SAFE loop with a dummy box. Switch off. Fit the J2 link (KILL closed = run). Connect the cut patch cable to J1 and put 470R across pair 3 (pins 3 and 6) and 470R across pair 4 (pins 7 and 8). Switch on. Measure across R36 (pair 3 return) and R46 (pair 4 return) | 0.88 to 1.25 V across each (8.8 to 12.5 mA, C-24). J6 pin 2 high (SAFE OK). Supply current rises by about 20 to 25 mA | |
| 8 | Clear the latch: short J6 pin 1 to pin 4 for about 0.5 s | J6 pin 3 goes low (LATCHED cleared) | |
| 9 | KILL: remove the J2 link | Voltage across R36 goes to 0. J6 pin 2 low, J6 pin 3 high again (latched). Refit the link: pin 3 stays high until the next RESET | |
| 10 | Pairs 1 and 2. Put 470R across pair 1 (pins 4 and 5) and pair 2 (pins 1 and 2) | 0 V across each resistor. Pair 1 needs DATA_TX from the MCU; pair 2 needs R1 TX sense | |
| 11 | Switch off. Record the supply current, the rail voltages and the RESET_N period in the report | – | |

**After P-01**

- Fit U203, U303, U403. With no DevKit, TX_EN is low (FAULT high), so every TX INH contact must be closed (inhibit). Check per port with the INH LEVEL shunt on LOW: DIN pin 2 to radio GND is about 0 ohm.
- Fit U1 on the housing wall with the insulating pad, then fit the DevKit. Next: 3V3 current with the DevKit, USB enumeration on J14, watchdog kick and LATCH_CLR from the firmware.
- Results go in docs/test/reports/shack-interface-p8g.md.
