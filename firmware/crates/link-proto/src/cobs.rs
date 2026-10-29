//! Consistent Overhead Byte Stuffing. The 0x00 delimiter is added by the caller.
//!
//! COBS removes every 0x00 from the data. The data is cut into blocks at each
//! 0x00. Each block starts with a code byte: the distance to the next 0x00
//! (block length + 1). The 0x00 itself is not sent. Code 0xFF means 254 bytes
//! without a 0x00, and no 0x00 follows. For frames below 254 bytes the cost is
//! exactly one byte.

/// Encode `src` into `dst`. `dst` must hold `src.len() + src.len() / 254 + 1` bytes.
pub(crate) fn encode(src: &[u8], dst: &mut [u8]) -> usize {
    // `code_idx`: where the code byte of the open block goes (filled in later).
    // `code`: block length + 1 so far.
    let mut code_idx = 0;
    let mut out = 1;
    let mut code = 1u8;
    for &b in src {
        if b == 0 {
            dst[code_idx] = code;
            code_idx = out;
            out += 1;
            code = 1;
        } else {
            dst[out] = b;
            out += 1;
            code += 1;
            // 254 data bytes: close the block without a zero.
            if code == 0xFF {
                dst[code_idx] = code;
                code_idx = out;
                out += 1;
                code = 1;
            }
        }
    }
    dst[code_idx] = code;
    out
}

/// Decode `src` (without the delimiter) into `dst`. Error on a zero byte,
/// a block that runs past the end, or output larger than `dst`.
pub(crate) fn decode(src: &[u8], dst: &mut [u8]) -> Result<usize, ()> {
    let mut i = 0;
    let mut out = 0;
    while i < src.len() {
        let code = src[i] as usize;
        if code == 0 {
            return Err(());
        }
        i += 1;
        let end = i + code - 1;
        if end > src.len() {
            return Err(());
        }
        let block = &src[i..end];
        if block.contains(&0) || out + block.len() > dst.len() {
            return Err(());
        }
        dst[out..out + block.len()].copy_from_slice(block);
        out += block.len();
        i = end;
        // A block with a code below 0xFF stood for data followed by a zero.
        // The zero after the last block is not real data, so skip it.
        if code != 0xFF && i < src.len() {
            if out >= dst.len() {
                return Err(());
            }
            dst[out] = 0;
            out += 1;
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn check(raw: &[u8], wire: &[u8]) {
        let mut enc = [0u8; 300];
        let n = encode(raw, &mut enc);
        assert_eq!(&enc[..n], wire);
        let mut dec = [0u8; 300];
        let m = decode(wire, &mut dec).unwrap();
        assert_eq!(&dec[..m], raw);
    }

    #[test]
    fn known_vectors() {
        // Vectors from the COBS paper (Cheshire and Baker) and Wikipedia.
        check(&[], &[0x01]);
        check(&[0x00], &[0x01, 0x01]);
        check(&[0x00, 0x00], &[0x01, 0x01, 0x01]);
        check(&[0x11, 0x22, 0x00, 0x33], &[0x03, 0x11, 0x22, 0x02, 0x33]);
        check(&[0x11, 0x22, 0x33, 0x44], &[0x05, 0x11, 0x22, 0x33, 0x44]);
        check(&[0x11, 0x00, 0x00, 0x00], &[0x02, 0x11, 0x01, 0x01, 0x01]);
    }

    #[test]
    fn bad_input() {
        let mut dst = [0u8; 16];
        assert!(decode(&[0x00], &mut dst).is_err());
        assert!(decode(&[0x05, 0x11], &mut dst).is_err());
        assert!(decode(&[0x03, 0x11, 0x00], &mut dst).is_err());
        let mut small = [0u8; 2];
        assert!(decode(&[0x04, 1, 2, 3], &mut small).is_err());
    }
}
