# Test piece: RF isolation through DIN 41612 type C

Status: draft, 2026-09-26.

## Purpose

Measure the coupling between two RF lines that pass through a mated DIN 41612 pair and a short piece of backplane.
The result sets the backplane pin-out and the RF detector threshold on the Antenna Port card.

Target: isolation of 50 dB or more at 30 MHz between adjacent RF groups. This keeps the connector at least 10 dB below the measured antenna-to-antenna coupling in the garden (25 to 40 dB, see the LoG receive-chain log).

## Hardware

Two small boards, mated:

- **Backplane coupon:** HARTING 09 03 296 6824 (female, straight), 4-layer, 1.6 mm.
- **Card coupon:** HARTING 09 03 196 6921 (male, angled), 4-layer, 1.6 mm.

Stackup (both coupons):

| Layer | Use |
|---|---|
| L1 | RF traces as coplanar waveguide with ground, 50 Ω, via fence both sides |
| L2 | solid ground |
| L3 | solid ground |
| L4 | ground pour, stitched |

Ground stitching vias along the board edges and around each RF trace, at 2.5 mm pitch or less.

## Pin-out on the connector

Three RF groups in row b, 2 contacts per group. Two different gaps on the same board:

```
position:  1  2  3  4  5  6  7  8  9 ... 32
row a:     G  G  G  G  G  G  G  G  G ... G
row b:     S1 S1 -  S2 S2 G  S3 S3 G ... G
row c:     G  G  G  G  G  G  G  G  G ... G
```

- S1 to S2: version A, empty position between the groups (your first proposal).
- S2 to S3: version B, ground contact between the groups.
- All other contacts: ground.

## Ports

Each RF group has an SMA edge connector at both ends: one on the backplane coupon, one on the card coupon. That gives 6 SMA connectors. Trace length on each coupon about 30 mm, similar to a real card and a real backplane section.

## Measurements (NanoVNA-H4, 1 to 54 MHz)

Terminate every unused SMA with 50 Ω.

1. **Through loss** S21 on S2, backplane end to card end. Check the return loss (S11) as well.
2. **Near-end crosstalk, version A:** port 1 on S2 backplane end, port 2 on S1 backplane end.
3. **Far-end crosstalk, version A:** port 1 on S2 backplane end, port 2 on S1 card end.
4. **Near-end and far-end crosstalk, version B:** the same with S3 in place of S1.
5. **Reference:** two SMA connectors joined only by the coupon ground (no connector path), to see the fixture floor.

Record values at 1.8, 3.6, 7.1, 14.1, 21.1, 28.5 and 50.1 MHz.

## Pass criteria

- Isolation 50 dB or more at 28.5 MHz for the version that goes into the backplane.
- Return loss 20 dB or more at 28.5 MHz on the through path.

## Open

- A later power test at 100 W, on the through path, to check heating of the contacts. Not part of this coupon test.
