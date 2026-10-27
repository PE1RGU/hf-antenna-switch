# Test specification

Status: skeleton 0.1, 2026-10-06. Tests are added as boards are built.
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
