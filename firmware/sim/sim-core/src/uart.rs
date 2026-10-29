//! One direction of a UART link, at byte level with real byte timing.
//! A cut line loses every byte, also bytes already in flight.

use crate::SimTime;
use std::collections::VecDeque;

/// Fault filter: `None` drops the byte, `Some(b)` delivers `b` (maybe corrupted).
pub type ByteFilter = Box<dyn FnMut(u8) -> Option<u8>>;

pub struct UartLine {
    byte_time: SimTime,
    in_flight: VecDeque<(SimTime, u8)>,
    free_at: SimTime,
    /// No current in the loop: nothing arrives.
    pub cut: bool,
    filter: Option<ByteFilter>,
}

impl UartLine {
    /// 8N1: 10 bit times per byte.
    pub fn new(baud: u32) -> Self {
        UartLine {
            byte_time: SimTime::us(10_000_000 / baud as u64),
            in_flight: VecDeque::new(),
            free_at: SimTime::ZERO,
            cut: false,
            filter: None,
        }
    }

    pub fn byte_time(&self) -> SimTime {
        self.byte_time
    }

    pub fn set_filter(&mut self, f: Option<ByteFilter>) {
        self.filter = f;
    }

    /// Queue a byte. It arrives one byte time after the line is free.
    pub fn send(&mut self, now: SimTime, byte: u8) {
        let start = now.max(self.free_at);
        self.free_at = start + self.byte_time;
        if self.cut {
            return;
        }
        let byte = match &mut self.filter {
            Some(f) => f(byte),
            None => Some(byte),
        };
        if let Some(b) = byte {
            self.in_flight.push_back((self.free_at, b));
        }
    }

    /// Next byte that has arrived by `now`.
    pub fn recv(&mut self, now: SimTime) -> Option<u8> {
        if self.cut {
            self.in_flight.clear();
            return None;
        }
        match self.in_flight.front() {
            Some(&(at, b)) if at <= now => {
                self.in_flight.pop_front();
                Some(b)
            }
            _ => None,
        }
    }

    /// True while the transmitter still shifts bytes out.
    pub fn busy(&self, now: SimTime) -> bool {
        self.free_at > now
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn byte_takes_ten_bit_times() {
        let mut l = UartLine::new(9600);
        assert_eq!(l.byte_time(), SimTime::us(1041));
        l.send(SimTime::ZERO, 0x55);
        l.send(SimTime::ZERO, 0xAA);
        assert_eq!(l.recv(SimTime::us(1040)), None);
        assert_eq!(l.recv(SimTime::us(1041)), Some(0x55));
        assert_eq!(l.recv(SimTime::us(2081)), None);
        assert_eq!(l.recv(SimTime::us(2082)), Some(0xAA));
    }

    #[test]
    fn cut_loses_bytes_in_flight() {
        let mut l = UartLine::new(9600);
        l.send(SimTime::ZERO, 1);
        l.cut = true;
        assert_eq!(l.recv(SimTime::ms(5)), None);
        l.cut = false;
        assert_eq!(l.recv(SimTime::ms(5)), None);
    }

    #[test]
    fn filter_corrupts_and_drops() {
        let mut l = UartLine::new(9600);
        l.set_filter(Some(Box::new(|b| (b != 2).then_some(b ^ 0x80))));
        for b in 1..=3 {
            l.send(SimTime::ZERO, b);
        }
        let got: Vec<_> = (0..10).filter_map(|_| l.recv(SimTime::ms(10))).collect();
        assert_eq!(got, [0x81, 0x83]);
    }
}
