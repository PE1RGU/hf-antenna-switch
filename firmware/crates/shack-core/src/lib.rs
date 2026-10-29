//! Shack interface logic. No direct hardware access: the ESP32-C3 target and the
//! simulator each implement `hw::ShackHw`.
#![no_std]

pub mod board;
pub mod hw;
pub mod shack;
