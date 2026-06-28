use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum ColorSpace {
    #[default]
    Srgb,
    DisplayP3,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Color {
    pub r: f32,
    pub g: f32,
    pub b: f32,
    pub a: f32,
    #[serde(default)]
    pub space: ColorSpace,
}

impl Color {
    pub const TRANSPARENT: Self = Self {
        r: 0.0,
        g: 0.0,
        b: 0.0,
        a: 0.0,
        space: ColorSpace::Srgb,
    };

    pub fn rgba(r: f32, g: f32, b: f32, a: f32) -> Self {
        Self {
            r,
            g,
            b,
            a,
            space: ColorSpace::Srgb,
        }
    }

    /// Parse `#RRGGBB`, `#RRGGBBAA`, or `#RGB`. Returns None on malformed input.
    pub fn from_hex(s: &str) -> Option<Self> {
        let s = s.strip_prefix('#')?;
        let parse = |hi: u8, lo: u8| -> Option<u8> {
            let f = |c: u8| match c {
                b'0'..=b'9' => Some(c - b'0'),
                b'a'..=b'f' => Some(10 + c - b'a'),
                b'A'..=b'F' => Some(10 + c - b'A'),
                _ => None,
            };
            Some((f(hi)? << 4) | f(lo)?)
        };
        let b = s.as_bytes();
        let (r, g, bl, a) = match b.len() {
            6 => (
                parse(b[0], b[1])?,
                parse(b[2], b[3])?,
                parse(b[4], b[5])?,
                255,
            ),
            8 => (
                parse(b[0], b[1])?,
                parse(b[2], b[3])?,
                parse(b[4], b[5])?,
                parse(b[6], b[7])?,
            ),
            3 => (
                parse(b[0], b[0])?,
                parse(b[1], b[1])?,
                parse(b[2], b[2])?,
                255,
            ),
            _ => return None,
        };
        Some(Self::rgba(
            r as f32 / 255.0,
            g as f32 / 255.0,
            bl as f32 / 255.0,
            a as f32 / 255.0,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parses_six_digit_hex() {
        let c = Color::from_hex("#5B3FF5").unwrap();
        assert!((c.r - 0.357).abs() < 0.01);
        assert!((c.a - 1.0).abs() < 0.001);
    }
    #[test]
    fn parses_eight_digit_hex() {
        let c = Color::from_hex("#0000007F").unwrap();
        assert!((c.a - 0.498).abs() < 0.01);
    }
    #[test]
    fn rejects_bad_hex() {
        assert!(Color::from_hex("not-a-color").is_none());
    }
}
