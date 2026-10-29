//! Time-stamped record of everything that happens on a board.
//! The rule checker (P6) and the tests read it after a run.
//!
//! A board model pushes a [`TraceEvent`] for each signal change, each I2C transfer
//! and each UART byte. A test then asks questions about the history, for example
//! "when did TX_EN go high" ([`Trace::signal`]) or "what did the firmware write to
//! the expander" ([`Trace::i2c_writes`]). The trace only grows; call
//! [`Trace::clear`] to start a new record.

use crate::SimTime;

/// What happened in one [`TraceEvent`].
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TraceKind {
    /// A board signal changed level.
    Signal {
        /// Net name as in the schematic, for example `"TX_EN"` or `"RESET_N"`.
        name: &'static str,
        /// New level: true = high.
        value: bool,
    },
    /// I2C write accepted by a device: register pointer and data as sent.
    I2cWrite {
        /// 7-bit device address.
        addr: u8,
        /// Bytes as sent. The first byte is the register pointer.
        data: Vec<u8>,
    },
    /// I2C read: the bytes the device returned.
    I2cRead {
        /// 7-bit device address.
        addr: u8,
        /// Bytes that the device returned.
        data: Vec<u8>,
    },
    /// No device answered, or the device refused.
    I2cNack {
        /// 7-bit address that got no acknowledge.
        addr: u8,
    },
    /// A byte left a UART (`line` names the direction).
    Uart {
        /// Line name, for example `"to_box"`.
        line: &'static str,
        /// The byte as sent.
        byte: u8,
    },
    /// Free text from a model or a test, to mark a moment in the record.
    Note(String),
}

/// One entry in the [`Trace`]: what happened, and when.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TraceEvent {
    /// Virtual time of the event.
    pub t: SimTime,
    /// What happened.
    pub kind: TraceKind,
}

/// The record of one board: a list of [`TraceEvent`]s in the order they happened.
#[derive(Clone, Debug, Default)]
pub struct Trace {
    events: Vec<TraceEvent>,
}

impl Trace {
    /// An empty trace.
    pub fn new() -> Self {
        Self::default()
    }

    /// Add an event at time `t`. Models call this; `t` must not be earlier than the
    /// last event, or the queries below give a wrong order.
    pub fn push(&mut self, t: SimTime, kind: TraceKind) {
        self.events.push(TraceEvent { t, kind });
    }

    /// Add a [`TraceKind::Note`] at time `t`.
    pub fn note(&mut self, t: SimTime, text: impl Into<String>) {
        self.push(t, TraceKind::Note(text.into()));
    }

    /// All events, oldest first.
    pub fn events(&self) -> &[TraceEvent] {
        &self.events
    }

    /// Remove all events. Time does not change.
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
