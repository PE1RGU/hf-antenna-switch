//! Drawing helpers on any RGB565 target. Draw errors are ignored: a display
//! fault must never stop the shack logic.

use crate::theme::Font;
use embedded_graphics::pixelcolor::Rgb565;
use embedded_graphics::prelude::*;
use embedded_graphics::primitives::{
    Circle, Polyline, PrimitiveStyle, PrimitiveStyleBuilder, Rectangle, RoundedRectangle, Triangle,
};
use embedded_graphics::text::{Alignment, Baseline, Text, TextStyleBuilder};
use mplusfonts::style::BitmapFontStyleBuilder;

pub trait Target: DrawTarget<Color = Rgb565> {}
impl<T: DrawTarget<Color = Rgb565>> Target for T {}

pub fn rect<D: Target>(d: &mut D, x: i32, y: i32, w: u32, h: u32, fill: Rgb565) {
    let _ = Rectangle::new(Point::new(x, y), Size::new(w, h))
        .into_styled(PrimitiveStyle::with_fill(fill))
        .draw(d);
}

pub fn rrect<D: Target>(d: &mut D, x: i32, y: i32, w: u32, h: u32, r: u32, fill: Rgb565) {
    let st = PrimitiveStyleBuilder::new().fill_color(fill).build();
    let _ = RoundedRectangle::with_equal_corners(
        Rectangle::new(Point::new(x, y), Size::new(w, h)),
        Size::new(r, r),
    )
    .into_styled(st)
    .draw(d);
}

pub fn dot<D: Target>(d: &mut D, x: i32, y: i32, dia: u32, c: Rgb565) {
    let _ = Circle::with_center(Point::new(x, y), dia)
        .into_styled(PrimitiveStyle::with_fill(c))
        .draw(d);
}

pub fn tri<D: Target>(d: &mut D, p: [(i32, i32); 3], c: Rgb565) {
    let _ = Triangle::new(
        Point::new(p[0].0, p[0].1),
        Point::new(p[1].0, p[1].1),
        Point::new(p[2].0, p[2].1),
    )
    .into_styled(PrimitiveStyle::with_fill(c))
    .draw(d);
}

fn polyline<D: Target>(d: &mut D, pts: &[Point], c: Rgb565, w: u32) {
    let _ = Polyline::new(pts)
        .into_styled(PrimitiveStyle::with_stroke(c, w))
        .draw(d);
}

/// Metro-map route: horizontal, 45 degree turn, vertical, 45 degree turn, horizontal.
/// Nearly level routes start level with the end point (no zigzag).
pub fn route<D: Target>(
    d: &mut D,
    from: (i32, i32),
    to: (i32, i32),
    bus_x: i32,
    c: Rgb565,
    w: u32,
    glow: Option<Rgb565>,
) {
    let from = if (to.1 - from.1).abs() < 14 {
        (from.0, to.1)
    } else {
        from
    };
    let k = 6 * (to.1 - from.1).signum();
    let p = |(x, y): (i32, i32)| Point::new(x, y);
    let bent = [
        p(from),
        p((bus_x - 6, from.1)),
        p((bus_x, from.1 + k)),
        p((bus_x, to.1 - k)),
        p((bus_x + 6, to.1)),
        p(to),
    ];
    let straight = [p(from), p(to)];
    let pts: &[Point] = if to.1 == from.1 { &straight } else { &bent };
    if let Some(g) = glow {
        polyline(d, pts, g, w + 6);
    }
    polyline(d, pts, c, w);
    dot(d, from.0, from.1, w + 4, c);
    dot(d, to.0, to.1, w + 4, c);
}

/// Text centred vertically on `y`. `bg` must be the colour under the text: the
/// anti-aliased fonts have no transparency.
#[allow(
    clippy::too_many_arguments,
    reason = "one call per text: position, colours and alignment read best in line"
)]
pub fn text<D: Target>(
    d: &mut D,
    font: &'static Font,
    s: &str,
    x: i32,
    y: i32,
    fg: Rgb565,
    bg: Rgb565,
    al: Alignment,
) {
    let st = BitmapFontStyleBuilder::new()
        .text_color(fg)
        .background_color(bg)
        .font(font)
        .build();
    let ts = TextStyleBuilder::new()
        .alignment(al)
        .baseline(Baseline::Middle)
        .build();
    let _ = Text::with_text_style(s, Point::new(x, y), st, ts).draw(d);
}
