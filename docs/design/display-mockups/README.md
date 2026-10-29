# Display mock-ups

Shack interface display, 320 x 240 landscape (D-187). Rendered with embedded-graphics, shown at 3x.

- First round (bitmap fonts): A-matrix, B-flow, C-cards, alarm-safe-stop.
- Chosen (Prins, 2026-10-29): B and C and the Safe stop screen, in the modern style: B2-flow-modern, C2-cards-modern, alarm2-safe-stop-modern (anti-aliased M+ fonts).
- On the display: B is the default page, C on `page c`, both on `page auto` (B 10 s, C 5 s). Safe stop takes over on a blocking problem. There is no touch.

The firmware draws the pages in `firmware/crates/shack-ui`. `cargo run -p sim-shack -- --pty`, then `shot screen.png`, saves what the simulated display shows.
