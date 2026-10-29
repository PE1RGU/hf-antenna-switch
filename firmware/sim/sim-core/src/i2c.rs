//! I2C: device trait and the transaction runner that boards use for their bus.

use crate::{SimTime, Trace, TraceKind};
use embedded_hal::i2c::{ErrorKind, NoAcknowledgeSource, Operation};

/// The device did not acknowledge.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Nack;

/// A target on the bus. One call per write or read segment of a transaction.
pub trait I2cDevice {
    fn write(&mut self, data: &[u8]) -> Result<(), Nack>;
    fn read(&mut self, buf: &mut [u8]) -> Result<(), Nack>;
}

/// Device that acknowledges everything and reads zeros (DevKit parts the firmware does not use).
#[derive(Debug, Default)]
pub struct AckStub;

impl I2cDevice for AckStub {
    fn write(&mut self, _: &[u8]) -> Result<(), Nack> {
        Ok(())
    }
    fn read(&mut self, buf: &mut [u8]) -> Result<(), Nack> {
        buf.fill(0);
        Ok(())
    }
}

/// Run one transaction against `dev` (None: no device at `addr`) and record it.
pub fn transact(
    trace: &mut Trace,
    now: SimTime,
    addr: u8,
    ops: &mut [Operation<'_>],
    dev: Option<&mut dyn I2cDevice>,
) -> Result<(), ErrorKind> {
    let Some(dev) = dev else {
        trace.push(now, TraceKind::I2cNack { addr });
        return Err(ErrorKind::NoAcknowledge(NoAcknowledgeSource::Address));
    };
    for op in ops {
        let r = match op {
            Operation::Write(data) => dev.write(data).map(|()| TraceKind::I2cWrite {
                addr,
                data: data.to_vec(),
            }),
            Operation::Read(buf) => dev.read(buf).map(|()| TraceKind::I2cRead {
                addr,
                data: buf.to_vec(),
            }),
        };
        match r {
            Ok(kind) => trace.push(now, kind),
            Err(Nack) => {
                trace.push(now, TraceKind::I2cNack { addr });
                return Err(ErrorKind::NoAcknowledge(NoAcknowledgeSource::Unknown));
            }
        }
    }
    Ok(())
}
