# Link protocol: shack interface to box

Status: v0.1, 2026-10-29. Reviewed by Prins; P-01 to P-04 decided as proposed. Firmware phase P1 (firmware/PLAN.md).
Implementation: crate `link-proto` (firmware/crates/link-proto), shared by both ends.

## 1. Scope

This document sets the data link over Cat6 #1 pairs 1 and 4 (D-56, D-58).
It does not cover the safety lines. PTT (pair 2) and SAFE (pair 3) stay in hardware. The link never clears a latch and never closes a safety line.

The link carries:

- route commands (which antenna for each radio, TX and RX),
- the TX handshake for R2 and R3 (D-63, F13, F14),
- bias-T commands (D-54),
- box status back to the shack.

The Mac protocol (USB) is a different document (P3).

## 2. Physical layer

| Item | Value | Source |
|---|---|---|
| Medium | Two opto current loops, one per direction, full duplex | D-56 |
| Speed | 9600 baud | D-58, C-18 |
| Character | 8 data bits, no parity, 1 stop bit (8N1), LSB first | P-01 |
| Idle | Loop current on = mark (1). Box RX inverts in firmware | D-58 |
| Cable cut or box dead | No current = continuous space = break | D-58 |
| Byte time | 1.04 ms | |

A break or a framing error is not an error to report on its own. The receiver drops the frame. The time-out (section 6) catches a lost link.

## 3. Frame

```
| COBS( seq | type | payload (0..12) | crc16 ) | 0x00 |
```

- **seq** (u8): sequence number, set by the shack (section 5). The box copies it back.
- **type** (u8): message type (section 4).
- **payload**: fixed length per type. In v1 every payload field is one byte, so there is no byte order to choose; a future field of more than one byte is little endian. (The CRC goes high byte first, see below.)
- **crc16**: CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection, no final XOR), over seq, type and payload. Sent high byte first.
- **COBS** encoding, then one 0x00 delimiter. A receiver resyncs at the next 0x00 after any error.

Checks on receive, in this order: length within limits, COBS valid, CRC valid, type known, payload length matches the type. Any failure: drop the frame silently. One exception: a valid frame with a value out of range (radio, column, reserved bits) gets a Status with BadArg.

Why CRC-16: the cable is unshielded and buried (D-57). CRC-16 finds all 1, 2 and 3 bit errors and all bursts up to 16 bits in these short frames. CRC-8 does not give that margin.

## 4. Messages

Shack to box:

| Type | Name | Payload | Bytes on the wire |
|---|---|---|---|
| 0x01 | Hello | version u8 | 7 |
| 0x02 | Poll | – | 6 |
| 0x10 | SetRoute | radio u8, tx col u8, rx col u8 | 9 |
| 0x11 | TxRequest | radio u8 | 7 |
| 0x12 | TxEnd | radio u8 | 7 |
| 0x20 | SetBias | mask u8 | 7 |
| 0x30 to 0x3F | reserved: firmware update over the link | | |

Box to shack:

| Type | Name | Payload | Bytes on the wire |
|---|---|---|---|
| 0x81 | HelloReply | version u8, fw major u8, fw minor u8, fw patch u8, rx-only mask u8, unit 2 present u8 | 12 |
| 0x82 | Status | see below (12 bytes) | 18 |

Values:

- radio: 1 = R1, 2 = R2, 3 = R3.
- col: 0 = none, 1 to 4 = A1 to A4, 5 = EXP.
- mask (columns): bit 0 = A1 ... bit 3 = A4, bit 4 = EXP.

Status payload (12 bytes):

| Byte | Field | Content |
|---|---|---|
| 0 | result | Result of the command with this seq (section 4.1) |
| 1 | flags | bit 0 READY (MCU_EN_N = 0 and FAULT = 0), bit 1 KILL, bit 2 TX_ANY, bit 3 SWITCHING, bit 4 LINK_LOST_STOP (box opened SAFE after a time-out), bit 5 unit 2 present |
| 2 | permits | bit 1 R2 permit, bit 2 R3 permit. Bit set = K0 in TX, settled and read back |
| 3 to 5 | route R1, R2, R3 | low nibble tx col, high nibble rx col, as read back from the expanders |
| 6 | k1 | mask: K1 on per column |
| 7 | rfdet | mask: RF detected per column |
| 8 | bias_en | mask |
| 9 | bias_ok | mask; a fault is EN = 1 and OK = 0 (D-54) |
| 10 | fault | last fault code (section 4.2), 0 = none |
| 11 | reserved | 0 |

### 4.1 Result codes

| Code | Name | Meaning |
|---|---|---|
| 0 | Ok | Done, or accepted and running (see SWITCHING and permits) |
| 1 | NotReady | READY = 0 or KILL = 1 |
| 2 | PermitOut | The radio has a permit; its K0 and rows do not change (F13) |
| 3 | TxActive | TX_ANY = 1; no relay moves under RF |
| 4 | Hazard | The new state breaks H1 to H4 (verify_logic.py section 7, F6) |
| 5 | NoTxRoute | TxRequest for a radio without a TX column, or its K1 off (H4) |
| 6 | BadArg | Value out of range, or TxRequest / TxEnd for R1 (R1 uses the PTT loop) |
| 7 | Busy | A switching sequence is running |
| 8 | ReadBack | Read-back differs from the written state |
| 9 | Version | Reserved. In v1 the box answers every Hello with a HelloReply that carries its own version; the shack compares the versions (section 5) |

### 4.2 Fault codes

1 expander NACK, 2 read-back mismatch, 3 bias-T fault, 4 link time-out with permit out, 5 SAFE loop did not close at start-up (F11), 6 link time-out with no permit out (P-02). More codes are added with the box firmware. The field holds the last fault since the box powered up.

## 5. Exchange

The shack is the master. The box speaks only to answer.

- The shack sends one frame. The box answers each valid frame with one Status (or HelloReply).
- The shack sends the next frame after the answer, or after the answer time-out. When it has no command, it sends Poll.
- Minimum cycle: Poll 6 bytes + Status 18 bytes + processing, about 30 ms. Poll period: 50 ms.
- Each new command gets a new seq (+1, wraps). A retry keeps its seq.
- The box keeps the last seq and its result. A frame with the same seq is not executed again; the box sends the present Status with the stored result. So a lost answer cannot run a command twice.
- All commands set a state, not a step. SetRoute, TxRequest, TxEnd and SetBias give the same result when sent twice.

Start: the shack sends Hello until a HelloReply comes. Hello also clears the box seq store, so a restarted shack cannot hit an old seq. If the version differs, the shack does not send commands, reports this to the Mac once, and keeps sending Hello, one every answer time-out (60 ms, section 6). The rx-only mask in HelloReply must match the shack's own table (unit 1: A2, D-103).

Hello also ends every permit. The shack that sends it has all PERMIT lines off (after a boot or a link loss), and a restarted shack does not know its old permits. The box clears the permit bits at once and releases K0 100 ms after the Hello (the F14 wait), unless a TxRequest or TxEnd for that radio comes first.

### 5.1 TX handshake, R2 and R3 (D-63, T3a, T3b, F2)

Start:

1. Shack sends TxRequest(Rk).
2. Box checks: READY, TX route set and K1 on (H4), state allowed (H1 to H4). A repeated TxRequest for a radio that has its permit gives Ok. Fail: result code, nothing moves.
3. Box sets K0 of Rk (U903 IO1_3 / IO1_4), waits 12 ms, reads back. Then permit bit k = 1 in Status.
4. Shack sets PERMIT_Rk only when it sees permit bit k = 1. Then it may key the radio.

End:

1. Shack drops KEY_Rk and PERMIT_Rk (inhibit first).
2. Shack waits for Rk TX sense inactive and at least 100 ms (F14).
3. Shack sends TxEnd(Rk). Box releases K0, permit bit k = 0.

Timing on the wire: the box answers the TxRequest at once (7.3 + 18.8 ms, permit bit still 0). K0 is settled 12 ms after the request. The next Poll and Status (6.3 + 18.8 ms) carry the permit. Permit seen at the shack about 55 ms after the request, worst case about 115 ms with one lost frame. C-18 and diagram T3a assume 4 ms per message; the real frames are longer. This adds latency only. It does not change safety, because the radio stays inhibited until the permit.

## 6. Time-outs

| Item | Value | Action |
|---|---|---|
| Shack: answer time-out | 60 ms | Retry the same frame (same seq) every 60 ms until the link is lost: at most 5 sends |
| Shack: link lost | no valid answer for 300 ms | Drop all PERMIT and KEY lines; report to the Mac; send Hello until the link is back; then TxEnd for each radio that had a permit, after the F14 wait |
| Box: link lost | no valid frame for 300 ms, after at least one valid frame | Permit out: MCU_EN_N = 1 (opens SAFE), do not release K0 (F13), fault 4. No permit out: hold the routes, fault 6 (P-02) |

300 ms is 6 poll periods. It is well below the box watchdog minimum (0.9 s, C-19), so a link loss is handled by firmware before the watchdog acts.

The box leaves its link-loss stop (fault 4) on a Hello, or when each radio that had a permit got its TxEnd (decided by Prins, 2026-10-31). It then sets MCU_EN_N = 0 and runs the F11 start-up again. The relays come back off. The SAFE latch in the shack still needs RESET, so an operator is in the loop. While stopped, the box answers every command with READY = 0 and refuses SetRoute, TxRequest and SetBias with NotReady.

## 7. Rules for the implementation

- `link-proto` is `no_std`, no allocation, no panics on any input. A fuzz test feeds random bytes to the decoder.
- Encode and decode are pure functions. The time-outs and the seq store are in a small state machine without hardware calls, so the simulator can drive it with virtual time.
- The decoder accepts bytes one at a time from the UART (streaming).

## 8. Open points

- **P-01 Stop bits. Decided (Prins, 2026-10-29): 8N1.** C-18 gives 10 to 20 % bit distortion through the PC817X. 8N2 adds margin for resync at a cost of 10 % throughput. Proposal: start with 8N1, measure the distortion on the bench, change to 8N2 if needed. The framing does not change.
- **P-02 Box link loss with no permit out. Decided (Prins, 2026-10-29): option 1.** Option 1: hold the routes, flag the fault, wait for the link. A shack MCU reboot then needs no RESET press. Option 2: always open SAFE. Every link loss then needs RESET. Proposal: option 1. A cable cut opens SAFE anyway, because pair 3 is in the same cable.
- **P-03 TxRequest while TX_ANY = 1. Decided (Prins, 2026-10-29): option 2.** R1 transmits (PTT loop) and R2 asks for TX. Moving R2 K0 does not touch the R1 path. Option 1: allow it. Option 2: refuse with TxActive (the step 1 rule of verify_logic.py section 8, written for route changes). Proposal: option 2 for now, as it is the stricter rule; review when R2 is in use.
- **P-04 Firmware update over the link. Decided (Prins, 2026-10-29): reserved, not in v1.** Types 0x30 to 0x3F are reserved. About 10 min per update (D-56). Not in v1.
