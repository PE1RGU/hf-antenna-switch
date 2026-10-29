//! Time-stamped record of everything that happens on a board.
//! The rule checker (P6) and the tests read it after a run.

use crate::SimTime;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TraceKind {
    /// A board signal changed level.
    Signal {
        name: &'static str,
        value: bool,
    },
    /// I2C write accepted by a device: register pointer and data as sent.
    I2cWrite {
        addr: u8,
        data: Vec<u8>,
    },
    /// I2C read: the bytes the device returned.
    I2cRead {
        addr: u8,
        data: Vec<u8>,
    },
    /// No device answered, or the device refused.
    I2cNack {
        addr: u8,
    },
    /// A byte left a UART (`line` names the direction).
    Uart {
        line: &'static str,
        byte: u8,
    },
    Note(String),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TraceEvent {
    pub t: SimTime,
    pub kind: TraceKind,
}

#[derive(Clone, Debug, Default)]
pub struct Trace {
    events: Vec<TraceEvent>,
}

impl Trace {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn push(&mut self, t: SimTime, kind: TraceKind) {
        self.events.push(TraceEvent { t, kind });
    }

    pub fn note(&mut self, t: SimTime, text: impl Into<String>) {
        self.push(t, TraceKind::Note(text.into()));
    }

    pub fn events(&self) -> &[TraceEvent] {
        &self.events
    }

    pub fn clear(&mut self) {
        self.events.clear();
    }

    /// All level changes of one signal, in order.
    pub fn signal(&self, name: &str) -> Vec<(SimTime, bool)> {
        self.events
            .iter()
            .filter_map(|e| match e.kind {
                TraceKind::Signal { name: n, value } if n == name => Some((e.t, value)),
                _ => None,
            })
            .collect()
    }

    /// Level of a signal at time `t` (last change at or before `t`).
    pub fn level_at(&self, name: &str, t: SimTime) -> Option<bool> {
        self.signal(name)
            .into_iter()
            .take_while(|(at, _)| *at <= t)
            .last()
            .map(|(_, v)| v)
    }

    /// Accepted I2C writes to one address.
    pub fn i2c_writes(&self, addr: u8) -> Vec<(SimTime, Vec<u8>)> {
        self.events
            .iter()
            .filter_map(|e| match &e.kind {
                TraceKind::I2cWrite { addr: a, data } if *a == addr => Some((e.t, data.clone())),
                _ => None,
            })
            .collect()
    }
}
