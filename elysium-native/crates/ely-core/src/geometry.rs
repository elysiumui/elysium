use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize, Default)]
pub struct Point {
    pub x: f32,
    pub y: f32,
}

impl Point {
    pub const fn new(x: f32, y: f32) -> Self {
        Self { x, y }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize, Default)]
pub struct Rect {
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
}

impl Rect {
    pub const fn new(x: f32, y: f32, w: f32, h: f32) -> Self {
        Self { x, y, w, h }
    }
    pub fn center_x(&self) -> f32 {
        self.x + self.w * 0.5
    }
    pub fn center_y(&self) -> f32 {
        self.y + self.h * 0.5
    }
    pub fn contains(&self, p: Point) -> bool {
        p.x >= self.x && p.x <= self.x + self.w && p.y >= self.y && p.y <= self.y + self.h
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Transform {
    pub tx: f32,
    pub ty: f32,
    pub sx: f32,
    pub sy: f32,
    pub rotation: f32,
}

impl Default for Transform {
    fn default() -> Self {
        Self {
            tx: 0.0,
            ty: 0.0,
            sx: 1.0,
            sy: 1.0,
            rotation: 0.0,
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Path {
    pub source: String,
    pub commands: Vec<PathVerb>,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum PathVerb {
    MoveTo(Point),
    LineTo(Point),
    CubicTo(Point, Point, Point),
    QuadTo(Point, Point),
    Close,
}

impl Path {
    pub fn from_svg(d: &str) -> Self {
        let commands = parse_svg_path(d).unwrap_or_default();
        Self {
            source: d.to_string(),
            commands,
        }
    }

    pub fn is_closed(&self) -> bool {
        matches!(self.commands.last(), Some(PathVerb::Close))
    }

    /// Flatten the path's Bezier curves to a list of polylines (one per
    /// subpath). `samples_per_curve` controls Bezier fidelity.
    pub fn flatten(&self, samples_per_curve: u32) -> Vec<Vec<Point>> {
        let n = samples_per_curve.max(2) as i32;
        let mut polylines: Vec<Vec<Point>> = Vec::new();
        let mut current = Vec::<Point>::new();
        let mut pen = Point::new(0.0, 0.0);
        let mut subpath_start = Point::new(0.0, 0.0);
        for v in &self.commands {
            match *v {
                PathVerb::MoveTo(p) => {
                    if !current.is_empty() {
                        polylines.push(std::mem::take(&mut current));
                    }
                    current.push(p);
                    pen = p;
                    subpath_start = p;
                }
                PathVerb::LineTo(p) => {
                    current.push(p);
                    pen = p;
                }
                PathVerb::QuadTo(c, p) => {
                    for i in 1..=n {
                        let t = i as f32 / n as f32;
                        let one_t = 1.0 - t;
                        let x = one_t * one_t * pen.x + 2.0 * one_t * t * c.x + t * t * p.x;
                        let y = one_t * one_t * pen.y + 2.0 * one_t * t * c.y + t * t * p.y;
                        current.push(Point::new(x, y));
                    }
                    pen = p;
                }
                PathVerb::CubicTo(c1, c2, p) => {
                    for i in 1..=n {
                        let t = i as f32 / n as f32;
                        let one_t = 1.0 - t;
                        let b0 = one_t * one_t * one_t;
                        let b1 = 3.0 * one_t * one_t * t;
                        let b2 = 3.0 * one_t * t * t;
                        let b3 = t * t * t;
                        let x = b0 * pen.x + b1 * c1.x + b2 * c2.x + b3 * p.x;
                        let y = b0 * pen.y + b1 * c1.y + b2 * c2.y + b3 * p.y;
                        current.push(Point::new(x, y));
                    }
                    pen = p;
                }
                PathVerb::Close => {
                    current.push(subpath_start);
                    pen = subpath_start;
                }
            }
        }
        if !current.is_empty() {
            polylines.push(current);
        }
        polylines
    }

    /// Even-odd point-in-path. Flattens curves first; treats every
    /// subpath as implicitly closed.
    pub fn contains(&self, p: Point) -> bool {
        let polylines = self.flatten(16);
        let mut inside = false;
        for poly in &polylines {
            if poly.len() < 2 {
                continue;
            }
            let mut j = poly.len() - 1;
            for i in 0..poly.len() {
                let (vi, vj) = (poly[i], poly[j]);
                let crosses = ((vi.y > p.y) != (vj.y > p.y))
                    && (p.x
                        < (vj.x - vi.x) * (p.y - vi.y)
                            / (vj.y - vi.y).max(1e-9).copysign(vj.y - vi.y)
                            + vi.x);
                if crosses {
                    inside = !inside;
                }
                j = i;
            }
        }
        inside
    }

    /// Axis-aligned bounding box over all explicit points.
    pub fn bounds(&self) -> Option<Rect> {
        let mut iter = self.commands.iter().flat_map(|v| match v {
            PathVerb::MoveTo(p) | PathVerb::LineTo(p) => vec![*p],
            PathVerb::CubicTo(a, b, c) => vec![*a, *b, *c],
            PathVerb::QuadTo(a, b) => vec![*a, *b],
            PathVerb::Close => vec![],
        });
        let first = iter.next()?;
        let mut min = first;
        let mut max = first;
        for p in iter {
            if p.x < min.x {
                min.x = p.x;
            }
            if p.y < min.y {
                min.y = p.y;
            }
            if p.x > max.x {
                max.x = p.x;
            }
            if p.y > max.y {
                max.y = p.y;
            }
        }
        Some(Rect::new(min.x, min.y, max.x - min.x, max.y - min.y))
    }
}

/// SVG path mini-language parser.
///
/// Supports the subset documented in spec §6.3: `M m L l H h V v C c S s
/// Q q T t Z z`. Coordinates are whitespace- or comma-separated. The
/// arc command (`A a`) is intentionally not supported in Phase 1 — `.esk`
/// authors should pre-convert arcs to cubic Béziers.
fn parse_svg_path(input: &str) -> Result<Vec<PathVerb>, PathError> {
    let mut p = Parser::new(input);
    let mut verbs: Vec<PathVerb> = Vec::new();
    let mut current = Point::new(0.0, 0.0);
    let mut subpath_start = Point::new(0.0, 0.0);
    let mut last_control: Option<Point> = None;
    let mut last_cmd: u8 = 0;

    while let Some(cmd) = p.next_command()? {
        let relative = cmd.is_ascii_lowercase();
        let upper = cmd.to_ascii_uppercase();
        match upper {
            b'M' => {
                let mut first = true;
                loop {
                    if !p.peek_number() {
                        break;
                    }
                    let x = p.read_number()?;
                    let y = p.read_number()?;
                    let pt = if relative {
                        Point::new(current.x + x, current.y + y)
                    } else {
                        Point::new(x, y)
                    };
                    if first {
                        verbs.push(PathVerb::MoveTo(pt));
                        subpath_start = pt;
                        first = false;
                    } else {
                        verbs.push(PathVerb::LineTo(pt));
                    }
                    current = pt;
                }
                last_control = None;
            }
            b'L' => loop {
                if !p.peek_number() {
                    break;
                }
                let x = p.read_number()?;
                let y = p.read_number()?;
                let pt = if relative {
                    Point::new(current.x + x, current.y + y)
                } else {
                    Point::new(x, y)
                };
                verbs.push(PathVerb::LineTo(pt));
                current = pt;
                last_control = None;
            },
            b'H' => loop {
                if !p.peek_number() {
                    break;
                }
                let x = p.read_number()?;
                let pt = if relative {
                    Point::new(current.x + x, current.y)
                } else {
                    Point::new(x, current.y)
                };
                verbs.push(PathVerb::LineTo(pt));
                current = pt;
                last_control = None;
            },
            b'V' => loop {
                if !p.peek_number() {
                    break;
                }
                let y = p.read_number()?;
                let pt = if relative {
                    Point::new(current.x, current.y + y)
                } else {
                    Point::new(current.x, y)
                };
                verbs.push(PathVerb::LineTo(pt));
                current = pt;
                last_control = None;
            },
            b'C' => loop {
                if !p.peek_number() {
                    break;
                }
                let x1 = p.read_number()?;
                let y1 = p.read_number()?;
                let x2 = p.read_number()?;
                let y2 = p.read_number()?;
                let x = p.read_number()?;
                let y = p.read_number()?;
                let (c1, c2, end) = if relative {
                    (
                        Point::new(current.x + x1, current.y + y1),
                        Point::new(current.x + x2, current.y + y2),
                        Point::new(current.x + x, current.y + y),
                    )
                } else {
                    (Point::new(x1, y1), Point::new(x2, y2), Point::new(x, y))
                };
                verbs.push(PathVerb::CubicTo(c1, c2, end));
                last_control = Some(c2);
                current = end;
            },
            b'S' => loop {
                if !p.peek_number() {
                    break;
                }
                let x2 = p.read_number()?;
                let y2 = p.read_number()?;
                let x = p.read_number()?;
                let y = p.read_number()?;
                // S's first control = reflection of previous C/S's last control
                // (or current point if previous wasn't C/S).
                let c1 = match last_control {
                    Some(c) if last_cmd == b'C' || last_cmd == b'S' => {
                        Point::new(2.0 * current.x - c.x, 2.0 * current.y - c.y)
                    }
                    _ => current,
                };
                let (c2, end) = if relative {
                    (
                        Point::new(current.x + x2, current.y + y2),
                        Point::new(current.x + x, current.y + y),
                    )
                } else {
                    (Point::new(x2, y2), Point::new(x, y))
                };
                verbs.push(PathVerb::CubicTo(c1, c2, end));
                last_control = Some(c2);
                current = end;
            },
            b'Q' => loop {
                if !p.peek_number() {
                    break;
                }
                let x1 = p.read_number()?;
                let y1 = p.read_number()?;
                let x = p.read_number()?;
                let y = p.read_number()?;
                let (c, end) = if relative {
                    (
                        Point::new(current.x + x1, current.y + y1),
                        Point::new(current.x + x, current.y + y),
                    )
                } else {
                    (Point::new(x1, y1), Point::new(x, y))
                };
                verbs.push(PathVerb::QuadTo(c, end));
                last_control = Some(c);
                current = end;
            },
            b'T' => loop {
                if !p.peek_number() {
                    break;
                }
                let x = p.read_number()?;
                let y = p.read_number()?;
                let c = match last_control {
                    Some(c) if last_cmd == b'Q' || last_cmd == b'T' => {
                        Point::new(2.0 * current.x - c.x, 2.0 * current.y - c.y)
                    }
                    _ => current,
                };
                let end = if relative {
                    Point::new(current.x + x, current.y + y)
                } else {
                    Point::new(x, y)
                };
                verbs.push(PathVerb::QuadTo(c, end));
                last_control = Some(c);
                current = end;
            },
            b'Z' => {
                verbs.push(PathVerb::Close);
                current = subpath_start;
                last_control = None;
            }
            _ => return Err(PathError::UnsupportedCommand(cmd as char)),
        }
        last_cmd = upper;
    }
    Ok(verbs)
}

#[derive(Debug, thiserror::Error)]
pub enum PathError {
    #[error("unsupported SVG path command '{0}'")]
    UnsupportedCommand(char),
    #[error("expected number at position {0}")]
    ExpectedNumber(usize),
}

struct Parser<'a> {
    bytes: &'a [u8],
    pos: usize,
}

impl<'a> Parser<'a> {
    fn new(s: &'a str) -> Self {
        Self {
            bytes: s.as_bytes(),
            pos: 0,
        }
    }

    fn skip_whitespace_and_commas(&mut self) {
        while self.pos < self.bytes.len() {
            let c = self.bytes[self.pos];
            if c == b' ' || c == b'\t' || c == b'\n' || c == b'\r' || c == b',' {
                self.pos += 1;
            } else {
                break;
            }
        }
    }

    fn next_command(&mut self) -> Result<Option<u8>, PathError> {
        self.skip_whitespace_and_commas();
        if self.pos >= self.bytes.len() {
            return Ok(None);
        }
        let c = self.bytes[self.pos];
        if c.is_ascii_alphabetic() {
            self.pos += 1;
            Ok(Some(c))
        } else {
            // Implicit repeat — caller will read more numbers under the same command.
            Err(PathError::ExpectedNumber(self.pos))
        }
    }

    fn peek_number(&mut self) -> bool {
        self.skip_whitespace_and_commas();
        if self.pos >= self.bytes.len() {
            return false;
        }
        let c = self.bytes[self.pos];
        c == b'+' || c == b'-' || c == b'.' || c.is_ascii_digit()
    }

    fn read_number(&mut self) -> Result<f32, PathError> {
        self.skip_whitespace_and_commas();
        let start = self.pos;
        if self.pos < self.bytes.len()
            && (self.bytes[self.pos] == b'+' || self.bytes[self.pos] == b'-')
        {
            self.pos += 1;
        }
        let mut saw_digit = false;
        while self.pos < self.bytes.len() && self.bytes[self.pos].is_ascii_digit() {
            self.pos += 1;
            saw_digit = true;
        }
        if self.pos < self.bytes.len() && self.bytes[self.pos] == b'.' {
            self.pos += 1;
            while self.pos < self.bytes.len() && self.bytes[self.pos].is_ascii_digit() {
                self.pos += 1;
                saw_digit = true;
            }
        }
        if self.pos < self.bytes.len()
            && (self.bytes[self.pos] == b'e' || self.bytes[self.pos] == b'E')
        {
            self.pos += 1;
            if self.pos < self.bytes.len()
                && (self.bytes[self.pos] == b'+' || self.bytes[self.pos] == b'-')
            {
                self.pos += 1;
            }
            while self.pos < self.bytes.len() && self.bytes[self.pos].is_ascii_digit() {
                self.pos += 1;
            }
        }
        if !saw_digit {
            return Err(PathError::ExpectedNumber(start));
        }
        let s = std::str::from_utf8(&self.bytes[start..self.pos])
            .map_err(|_| PathError::ExpectedNumber(start))?;
        s.parse::<f32>()
            .map_err(|_| PathError::ExpectedNumber(start))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_simple_move_line_close() {
        let p = Path::from_svg("M 10 20 L 30 40 Z");
        assert_eq!(p.commands.len(), 3);
        assert!(matches!(p.commands[0], PathVerb::MoveTo(_)));
        assert!(matches!(p.commands[1], PathVerb::LineTo(_)));
        assert!(matches!(p.commands[2], PathVerb::Close));
    }

    #[test]
    fn parses_implicit_lineto_after_moveto() {
        // After M, additional pairs are implicit L (per SVG spec).
        let p = Path::from_svg("M 0 0 10 0 10 10 0 10 Z");
        // 1 MoveTo + 3 LineTo + 1 Close = 5
        assert_eq!(p.commands.len(), 5);
        assert!(matches!(p.commands[0], PathVerb::MoveTo(_)));
        assert!(matches!(p.commands[4], PathVerb::Close));
    }

    #[test]
    fn parses_relative_moves() {
        let p = Path::from_svg("M 10 10 l 5 5 l 5 -5");
        let pts: Vec<_> = p
            .commands
            .iter()
            .filter_map(|v| match v {
                PathVerb::MoveTo(p) | PathVerb::LineTo(p) => Some(*p),
                _ => None,
            })
            .collect();
        assert_eq!(pts[0], Point::new(10.0, 10.0));
        assert_eq!(pts[1], Point::new(15.0, 15.0));
        assert_eq!(pts[2], Point::new(20.0, 10.0));
    }

    #[test]
    fn parses_cubic_bezier() {
        let p = Path::from_svg("M 0 0 C 0 50 100 50 100 100");
        assert!(matches!(p.commands[1], PathVerb::CubicTo(_, _, _)));
    }

    #[test]
    fn parses_smooth_cubic_reflects_control() {
        let p = Path::from_svg("M 0 0 C 0 50 100 50 100 100 S 200 150 200 200");
        // After C the last control was (100,50). S's first control should be
        // its reflection through (100,100): (100,150).
        if let PathVerb::CubicTo(c1, _, _) = p.commands[2] {
            assert!((c1.x - 100.0).abs() < 0.001, "got {:?}", c1);
            assert!((c1.y - 150.0).abs() < 0.001, "got {:?}", c1);
        } else {
            panic!("expected CubicTo, got {:?}", p.commands[2]);
        }
    }

    #[test]
    fn parses_quadratic() {
        let p = Path::from_svg("M 0 0 Q 50 50 100 0");
        assert!(matches!(p.commands[1], PathVerb::QuadTo(_, _)));
    }

    #[test]
    fn parses_horizontal_vertical_shortcuts() {
        let p = Path::from_svg("M 10 10 H 50 V 40 H 10 Z");
        assert_eq!(p.commands.len(), 5);
    }

    #[test]
    fn parses_hero_card_path() {
        // From examples/hello/hello.esk/document.json — must parse without error.
        let p = Path::from_svg(
            "M 24 24 Q 24 12, 36 12 L 444 12 Q 456 12, 456 24 \
             L 456 296 Q 456 308, 444 308 L 36 308 Q 24 308, 24 296 Z",
        );
        assert!(p.commands.len() > 5);
        assert!(p.is_closed());
    }

    #[test]
    fn computes_bounds() {
        let p = Path::from_svg("M 10 20 L 30 40 L 50 10");
        let b = p.bounds().unwrap();
        assert_eq!(b, Rect::new(10.0, 10.0, 40.0, 30.0));
    }

    #[test]
    fn handles_scientific_notation() {
        let p = Path::from_svg("M 1e2 2.5e1 L 3.0e0 4.0");
        if let PathVerb::MoveTo(pt) = p.commands[0] {
            assert!((pt.x - 100.0).abs() < 0.001);
            assert!((pt.y - 25.0).abs() < 0.001);
        }
    }
}
