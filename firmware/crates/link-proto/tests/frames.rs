//! Frame and message properties: round trip, error detection, no panics, resync.

use link_proto::frame::MAX_WIRE;
use link_proto::*;
use proptest::prelude::*;

fn radio() -> impl Strategy<Value = Radio> {
    prop::sample::select(Radio::ALL.to_vec())
}

fn col() -> impl Strategy<Value = Col> {
    prop::sample::select(Col::ALL.to_vec())
}

fn mask() -> impl Strategy<Value = ColMask> {
    (0u8..32).prop_map(|b| ColMask::from_bits(b).unwrap())
}

fn route() -> impl Strategy<Value = Route> {
    (col(), col()).prop_map(|(tx, rx)| Route { tx, rx })
}

fn command() -> impl Strategy<Value = Command> {
    prop_oneof![
        any::<u8>().prop_map(|version| Command::Hello { version }),
        Just(Command::Poll),
        (radio(), route()).prop_map(|(radio, route)| Command::SetRoute { radio, route }),
        radio().prop_map(Command::TxRequest),
        radio().prop_map(Command::TxEnd),
        mask().prop_map(Command::SetBias),
    ]
}

fn result_code() -> impl Strategy<Value = ResultCode> {
    (0u8..10).prop_map(|v| ResultCode::from_u8(v).unwrap())
}

fn status() -> impl Strategy<Value = Status> {
    (
        result_code(),
        prop::array::uniform6(any::<bool>()),
        any::<(bool, bool)>(),
        prop::array::uniform3(route()),
        prop::array::uniform4(mask()),
        any::<u8>(),
    )
        .prop_map(|(result, f, (p2, p3), routes, m, fault)| Status {
            result,
            flags: Flags {
                ready: f[0],
                kill: f[1],
                tx_any: f[2],
                switching: f[3],
                link_lost_stop: f[4],
                unit2: f[5],
            },
            permit_r2: p2,
            permit_r3: p3,
            routes,
            k1: m[0],
            rfdet: m[1],
            bias_en: m[2],
            bias_ok: m[3],
            fault: FaultCode(fault),
        })
}

fn reply() -> impl Strategy<Value = Reply> {
    prop_oneof![
        (any::<u8>(), any::<[u8; 3]>(), mask(), any::<bool>()).prop_map(
            |(version, fw, rx_only, unit2)| Reply::Hello(HelloInfo {
                version,
                fw,
                rx_only,
                unit2,
            })
        ),
        status().prop_map(Reply::Status),
    ]
}

fn wire<M: Message>(seq: u8, msg: M) -> Vec<u8> {
    let mut out = [0u8; MAX_WIRE];
    let n = Frame { seq, msg }.encode(&mut out);
    out[..n].to_vec()
}

fn decode_all<M: Message>(bytes: &[u8]) -> Vec<Result<Frame<M>, DecodeError>> {
    let mut d = Decoder::new();
    bytes.iter().filter_map(|&b| d.push::<M>(b)).collect()
}

proptest! {
    #[test]
    fn command_round_trip(seq: u8, cmd in command()) {
        let w = wire(seq, cmd);
        prop_assert!(w.len() <= MAX_WIRE);
        prop_assert_eq!(w.iter().filter(|&&b| b == 0).count(), 1);
        prop_assert_eq!(decode_all::<Command>(&w), vec![Ok(Frame { seq, msg: cmd })]);
    }

    #[test]
    fn reply_round_trip(seq: u8, r in reply()) {
        let w = wire(seq, r);
        prop_assert!(w.len() <= MAX_WIRE);
        prop_assert_eq!(decode_all::<Reply>(&w), vec![Ok(Frame { seq, msg: r })]);
    }

    /// CRC-16: every error of 1 to 3 flipped bits in seq, type, payload or CRC is found.
    #[test]
    fn crc_finds_three_bit_errors(
        seq: u8,
        r in reply(),
        flips in prop::collection::vec(any::<prop::sample::Index>(), 1..=3),
    ) {
        let good = raw(seq, r);
        let bits = good.len() * 8;
        let mut bad = good.clone();
        let mut seen = std::collections::BTreeSet::new();
        for i in &flips {
            let b = i.index(bits);
            prop_assume!(seen.insert(b));
            bad[b / 8] ^= 1 << (b % 8);
        }
        prop_assert!(Frame::<Reply>::decode_raw(&bad).is_err());
    }

    /// Random bytes never panic the decoder.
    #[test]
    fn random_bytes_no_panic(bytes in prop::collection::vec(any::<u8>(), 0..512)) {
        let _ = decode_all::<Command>(&bytes);
        let _ = decode_all::<Reply>(&bytes);
    }

    /// Noise before a frame: the decoder resyncs at the next delimiter.
    #[test]
    fn resync_after_noise(
        noise in prop::collection::vec(any::<u8>(), 0..64),
        seq: u8,
        cmd in command(),
    ) {
        let mut bytes = noise;
        bytes.push(0);
        bytes.extend(wire(seq, cmd));
        let got = decode_all::<Command>(&bytes);
        prop_assert_eq!(got.last(), Some(&Ok(Frame { seq, msg: cmd })));
    }
}

#[test]
fn wire_lengths_match_spec() {
    // Bytes on the wire per type, link-protocol.md section 4 (no zero bytes in these payloads).
    let st = Status {
        flags: Flags {
            ready: true,
            ..Default::default()
        },
        k1: ColMask::EMPTY.with(Col::A1),
        ..Default::default()
    };
    assert_eq!(wire(1, Command::Poll).len(), 6);
    assert_eq!(wire(1, Command::Hello { version: VERSION }).len(), 7);
    assert_eq!(wire(1, Command::TxRequest(Radio::R2)).len(), 7);
    let route = Route {
        tx: Col::A1,
        rx: Col::A3,
    };
    let set = Command::SetRoute {
        radio: Radio::R1,
        route,
    };
    assert_eq!(wire(1, set).len(), 9);
    assert!(wire(1, Reply::Status(st)).len() <= 18);
}

#[test]
fn out_of_range_values() {
    // SetRoute with column 6 and TxRequest for radio 4: good CRC, bad value.
    let raw_cases: [&[u8]; 4] = [
        &[7, 0x10, 1, 6, 0],
        &[7, 0x11, 4],
        &[7, 0x20, 0x20],
        &[7, 0x11, 0],
    ];
    for body in raw_cases {
        let r = Frame::<Command>::decode_raw(&with_crc(body));
        assert_eq!(r, Err(DecodeError::BadValue { seq: 7 }), "{body:?}");
    }
    assert_eq!(
        Frame::<Command>::decode_raw(&with_crc(&[7, 0x55])),
        Err(DecodeError::UnknownType)
    );
    assert_eq!(
        Frame::<Command>::decode_raw(&with_crc(&[7, 0x02, 0])),
        Err(DecodeError::Length)
    );
    // A Reply type is unknown to the box, a Command type unknown to the shack.
    assert_eq!(
        Frame::<Command>::decode_raw(&with_crc(&[7, 0x82])),
        Err(DecodeError::UnknownType)
    );
    assert_eq!(
        Frame::<Reply>::decode_raw(&with_crc(&[7, 0x02])),
        Err(DecodeError::UnknownType)
    );
}

#[test]
fn overlong_frame_is_dropped() {
    let mut d = Decoder::new();
    let mut got = None;
    for b in [0x55u8; 40].into_iter().chain([0]) {
        if let Some(r) = d.push::<Command>(b) {
            got = Some(r);
        }
    }
    assert_eq!(got, Some(Err(DecodeError::TooLong)));
    // The next frame decodes normally.
    let w = wire(9, Command::Poll);
    assert_eq!(
        decode_all_with(&mut d, &w),
        vec![Ok(Frame {
            seq: 9,
            msg: Command::Poll
        })]
    );
}

/// Every single bit flip on the wire, delimiter included, is never accepted.
#[test]
fn single_bit_errors_on_the_wire() {
    let frames = [
        wire(0, Reply::Status(Status::default())),
        wire(200, Reply::Hello(HelloInfo::default())),
        wire(
            17,
            Reply::Status(Status {
                permit_r2: true,
                routes: [Route {
                    tx: Col::A4,
                    rx: Col::Exp,
                }; 3],
                ..Default::default()
            }),
        ),
    ];
    for good in frames {
        for bit in 0..good.len() * 8 {
            let mut bad = good.clone();
            bad[bit / 8] ^= 1 << (bit % 8);
            let got = decode_all::<Reply>(&bad);
            assert!(got.iter().all(|g| g.is_err()), "bit {bit}: {got:?}");
        }
    }
}

fn raw<M: Message>(seq: u8, msg: M) -> Vec<u8> {
    let mut payload = [0u8; MAX_PAYLOAD];
    let (ty, n) = msg.write(&mut payload);
    let mut body = vec![seq, ty];
    body.extend(&payload[..n]);
    with_crc(&body)
}

fn decode_all_with(d: &mut Decoder, bytes: &[u8]) -> Vec<Result<Frame<Command>, DecodeError>> {
    bytes.iter().filter_map(|&b| d.push::<Command>(b)).collect()
}

fn with_crc(body: &[u8]) -> Vec<u8> {
    let crc = crc::Crc::<u16>::new(&crc::CRC_16_IBM_3740).checksum(body);
    let mut v = body.to_vec();
    v.extend(crc.to_be_bytes());
    v
}
