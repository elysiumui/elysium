//! Compile a parsed Skin document into a `DisplayList` the renderer can
//! execute. Phase 1.4 supports the subset of fills / effects /
//! `<path>` constructs needed for the Phase 0 hero card to round-trip
//! through the .esk loader.

use crate::parser::{Document, Node, NodeKind};
use ely_core::geometry::{Path as ElyPath, PathVerb};
use ely_core::{DisplayList, DrawCommand};
use serde_json::Value;

/// Compile a top-level skin Document into a flat DisplayList at the given
/// surface size. Honours `background` on the scene root, walks children,
/// emits a draw command for each path/text/image with a recognized fill.
pub fn compile(doc: &Document, surface_w: u32, surface_h: u32) -> DisplayList {
    let mut commands = Vec::new();

    // Scene background as a SCOPED FillPath of the scene's bounds, not a
    // canvas-wide Clear. This way embedding a skin's DisplayList inside
    // another UI (e.g. the Designer's preview pane) doesn't wipe out
    // the host canvas — the background only fills the scene rect.
    // The render thread auto-clears the SkiaLayer to (0,0,0,0) each
    // frame so standalone skins still get a clean slate.
    let bg_color_u8 = doc.root.background.as_ref().and_then(parse_color_as_u8);
    let scene_w = doc
        .root
        .size
        .as_ref()
        .map(|s| s.w)
        .unwrap_or(surface_w as f32);
    let scene_h = doc
        .root
        .size
        .as_ref()
        .map(|s| s.h)
        .unwrap_or(surface_h as f32);
    if let Some(bg) = bg_color_u8 {
        let d = format!(
            "M 0 0 L {sw} 0 L {sw} {sh} L 0 {sh} Z",
            sw = scene_w,
            sh = scene_h
        );
        commands.push(DrawCommand::FillPath { d, color: bg });
    }

    walk_node(
        &doc.root,
        surface_w as f32,
        surface_h as f32,
        0.0,
        0.0,
        &mut commands,
    );

    DisplayList {
        commands,
        frame_index: 0,
    }
}

fn parse_color_as_u8(v: &Value) -> Option<[u8; 4]> {
    if v.get("type").and_then(|t| t.as_str()) == Some("color") {
        let hex = v.get("value").and_then(|v| v.as_str())?;
        return parse_hex(hex);
    }
    None
}

fn walk_node(node: &Node, sw: f32, sh: f32, ox: f32, oy: f32, out: &mut Vec<DrawCommand>) {
    // Push a transform if this node has rotation or scale ≠ (1,1).
    // For pure translation we just shift the offsets, avoiding the
    // PushTransform / PopTransform overhead on common rectangular layouts.
    let mut tx = ox;
    let mut ty = oy;
    let mut pushed = false;
    if let Some(t) = node.transform {
        let has_rot = t.rotation.abs() > 1e-4;
        let has_scale = (t.scale[0] - 1.0).abs() > 1e-4 || (t.scale[1] - 1.0).abs() > 1e-4;
        if has_rot || has_scale {
            out.push(DrawCommand::PushTransform {
                tx: ox + t.x,
                ty: oy + t.y,
                sx: t.scale[0],
                sy: t.scale[1],
                rotation: t.rotation,
                anim_slot: None,
            });
            pushed = true;
            tx = 0.0;
            ty = 0.0;
        } else {
            tx = ox + t.x;
            ty = oy + t.y;
        }
    }

    match node.kind {
        NodeKind::Scene | NodeKind::Group => {
            // Pure container — nothing to emit. Children recurse.
        }
        NodeKind::Path => {
            if let Some(d) = &node.d {
                let p = ElyPath::from_svg(d);
                emit_path(
                    &p,
                    tx,
                    ty,
                    node.fill.as_ref(),
                    node.effects.as_slice(),
                    out,
                    d,
                );
            }
        }
        NodeKind::Image => {
            if let Some(src) = &node.src {
                let bbox = node.d.as_ref().and_then(|d| ElyPath::from_svg(d).bounds());
                let (x, y, w, h) = if let Some(b) = bbox {
                    (b.x + tx, b.y + ty, b.w, b.h)
                } else {
                    (tx, ty, sw.max(1.0), sh.max(1.0))
                };
                out.push(DrawCommand::DrawImageFile {
                    path: src.clone(),
                    dst: [x, y, w, h],
                });
            }
        }
        NodeKind::Text => {
            if let Some(text) = &node.text {
                let size = node.font_size.unwrap_or(14.0);
                let color = node
                    .color
                    .as_deref()
                    .and_then(parse_hex)
                    .unwrap_or([0x18, 0x1A, 0x2C, 0xFF]);
                // Honour the node's own x/y (the public schema's
                // text node placement) plus any inherited offset.
                let x = tx + node.x.unwrap_or(0.0);
                let y = ty + node.y.unwrap_or(0.0);
                out.push(DrawCommand::DrawText {
                    text: text.clone(),
                    x,
                    y,
                    size,
                    color,
                });
            }
        }
        NodeKind::Component | NodeKind::Webview => {
            // Components emit through their Python wrappers; the document
            // compiler reserves the slot but doesn't paint here. WebView
            // is Phase 3.3.
        }
    }

    for child in &node.children {
        walk_node(child, sw, sh, tx, ty, out);
    }

    if pushed {
        out.push(DrawCommand::PopTransform);
    }
}

fn emit_path(
    path: &ElyPath,
    tx: f32,
    ty: f32,
    fill: Option<&Value>,
    effects: &[Value],
    out: &mut Vec<DrawCommand>,
    svg_d: &str,
) {
    let Some(bbox) = path.bounds() else {
        return;
    };
    let (mut sx, mut sy) = (bbox.x + tx, bbox.y + ty);
    let (mut w, mut h) = (bbox.w, bbox.h);

    // Try to recognise a rounded-rectangle path — the only shape we can
    // reduce to a `GradientCard` faithfully. Anything else (triangle,
    // music-note head, arbitrary glyph silhouette) gets routed through
    // the exact-path Skia fill so its shape survives.
    let corner_radius = detect_corner_radius(&path.commands).unwrap_or(0.0);
    let is_rounded_rect = looks_like_rounded_rect(&path.commands);

    // Parse fill.
    let (start_c, end_c, single_c) = parse_fill_colors(fill);
    let shadow = effects.iter().find_map(parse_shadow);

    if let (Some(start_color), Some(end_color)) = (start_c, end_c) {
        // Linear gradient. GradientCard (rounded-rect approximation) is
        // the only shader we have for now; non-rect gradient shapes
        // still render as bbox cards. Acceptable for the existing
        // demo skins which use gradients only on cards / round play
        // buttons (where the bbox+radius approximation is correct).
        let (shadow_blur, shadow_offset, shadow_color) =
            shadow.unwrap_or((0.0, [0.0, 0.0], [0, 0, 0, 0]));
        if let Some(extra) = shadow_extra_pad(&shadow) {
            sx -= extra;
            sy -= extra;
            w += 2.0 * extra;
            h += 2.0 * extra;
            let _ = (sx, sy, w, h);
        }
        out.push(DrawCommand::GradientCard {
            bounds: [bbox.x + tx, bbox.y + ty, bbox.w, bbox.h],
            corner_radius,
            start_color,
            end_color,
            shadow_blur,
            shadow_offset,
            shadow_color,
        });
    } else if let Some(c) = single_c {
        if is_rounded_rect {
            // Fast path: rounded rect with a solid fill. Uses Skia's
            // RRect — visually identical to a path-fill but cheaper
            // and preserves the shadow-blur knob via GradientCard.
            let (shadow_blur, shadow_offset, shadow_color) =
                shadow.unwrap_or((0.0, [0.0, 0.0], [0, 0, 0, 0]));
            out.push(DrawCommand::GradientCard {
                bounds: [bbox.x + tx, bbox.y + ty, bbox.w, bbox.h],
                corner_radius,
                start_color: c,
                end_color: c,
                shadow_blur,
                shadow_offset,
                shadow_color,
            });
        } else {
            // Arbitrary shape — emit a real path fill so the silhouette
            // survives. Shift the SVG `d` by (tx, ty) when an ancestor
            // applied a transform offset; for the common case tx=ty=0
            // the original `d` rides through unchanged.
            let shifted = if tx.abs() < 1e-4 && ty.abs() < 1e-4 {
                svg_d.to_string()
            } else {
                translate_svg_path(svg_d, tx, ty)
            };
            out.push(DrawCommand::FillPath {
                d: shifted,
                color: c,
            });
        }
    }
}

/// True when the path is shaped like the Designer's / Phase-0 hand-
/// authored skins' rounded rectangle:
///   M-L-Q-L-Q-L-Q-L-Q-(Z)  with 3 or 4 LineTos and 4 QuadTos.
/// Anything else (triangle, curve glyph, free-form silhouette) returns
/// false so the compiler routes it through the exact-path Skia fill.
fn looks_like_rounded_rect(verbs: &[PathVerb]) -> bool {
    let mut lines = 0;
    let mut quads = 0;
    let mut others = 0;
    for v in verbs {
        match v {
            PathVerb::MoveTo(_) => {}
            PathVerb::LineTo(_) => lines += 1,
            PathVerb::QuadTo(_, _) => quads += 1,
            PathVerb::Close => {}
            PathVerb::CubicTo(..) => others += 1,
        }
    }
    others == 0 && quads == 4 && (lines == 3 || lines == 4)
}

/// Translate every coordinate in an SVG path-d by (dx, dy). Used for
/// path fills nested under a `transform.x/y` offset so the path's
/// bounding box ends up where the rounded-rect fast-path would land.
fn translate_svg_path(d: &str, dx: f32, dy: f32) -> String {
    // Cheap shifter: parse → recompose. We only support M/L/Q/Z which
    // is what the skin schema emits today.
    let mut out = String::new();
    let mut tokens = d.split_whitespace();
    while let Some(tok) = tokens.next() {
        match tok {
            "M" | "L" => {
                let x: f32 = tokens.next().and_then(|t| t.parse().ok()).unwrap_or(0.0);
                let y: f32 = tokens.next().and_then(|t| t.parse().ok()).unwrap_or(0.0);
                out.push_str(&format!("{} {} {} ", tok, x + dx, y + dy));
            }
            "Q" => {
                let cx: f32 = tokens.next().and_then(|t| t.parse().ok()).unwrap_or(0.0);
                let cy: f32 = tokens.next().and_then(|t| t.parse().ok()).unwrap_or(0.0);
                let ex: f32 = tokens.next().and_then(|t| t.parse().ok()).unwrap_or(0.0);
                let ey: f32 = tokens.next().and_then(|t| t.parse().ok()).unwrap_or(0.0);
                out.push_str(&format!(
                    "Q {} {} {} {} ",
                    cx + dx,
                    cy + dy,
                    ex + dx,
                    ey + dy
                ));
            }
            "Z" | "z" => out.push_str("Z "),
            other => {
                let _ = other;
            }
        }
    }
    out
}

fn detect_corner_radius(verbs: &[PathVerb]) -> Option<f32> {
    // Designer-emitted rounded rects look like
    //   M x0 y0  L x1 y0  Q cx y0  x_end y_corner_end  L ...
    // where (cx, y0) sits at the corner of the BOUNDING rect and the
    // first LineTo lands at (x1, y0) one corner-radius before that
    // corner. The radius is therefore |cx - x1| (or |cy - y1| on a
    // vertical edge), measured from the LAST point on the path to the
    // QuadTo control — not from the MoveTo origin, which is what an
    // earlier version of this fn did and which produced radii in the
    // hundreds (effectively turning rounded rects into giant
    // ellipses).
    let mut last = None;
    for v in verbs {
        match v {
            PathVerb::MoveTo(p) | PathVerb::LineTo(p) => {
                last = Some(*p);
            }
            PathVerb::QuadTo(c, e) => {
                if let Some(l) = last {
                    let dx = (c.x - l.x).abs();
                    let dy = (c.y - l.y).abs();
                    return Some(if dx > dy { dx } else { dy });
                }
                last = Some(*e);
            }
            PathVerb::CubicTo(_, _, _) => return None,
            PathVerb::Close => return None,
        }
    }
    None
}

#[allow(clippy::type_complexity)] // (start, end, single) gradient stops
fn parse_fill_colors(fill: Option<&Value>) -> (Option<[u8; 4]>, Option<[u8; 4]>, Option<[u8; 4]>) {
    let Some(fill) = fill else {
        return (None, None, None);
    };
    let ty = fill.get("type").and_then(|v| v.as_str()).unwrap_or("");
    match ty {
        "color" => {
            let c = fill
                .get("value")
                .and_then(|v| v.as_str())
                .and_then(parse_hex);
            (None, None, c)
        }
        "linear_gradient" | "radial_gradient" | "conic_gradient" => {
            let stops = fill.get("stops").and_then(|v| v.as_array());
            let mut start = None;
            let mut end = None;
            if let Some(stops) = stops {
                for s in stops.iter() {
                    let arr = s.as_array();
                    let Some(arr) = arr else {
                        continue;
                    };
                    if arr.len() < 2 {
                        continue;
                    }
                    let t = arr[0].as_f64().unwrap_or(0.0);
                    let c = arr[1].as_str().and_then(parse_hex);
                    if let Some(c) = c {
                        if t <= 0.001 {
                            start = Some(c);
                        }
                        if t >= 0.999 {
                            end = Some(c);
                        }
                    }
                }
            }
            if start.is_none() {
                start = stops
                    .and_then(|s| s.first())
                    .and_then(|s| s.as_array())
                    .and_then(|a| a.get(1))
                    .and_then(|v| v.as_str())
                    .and_then(parse_hex);
            }
            if end.is_none() {
                end = stops
                    .and_then(|s| s.last())
                    .and_then(|s| s.as_array())
                    .and_then(|a| a.get(1))
                    .and_then(|v| v.as_str())
                    .and_then(parse_hex);
            }
            (start, end, None)
        }
        _ => (None, None, None),
    }
}

fn parse_shadow(effect: &Value) -> Option<(f32, [f32; 2], [u8; 4])> {
    let ty = effect.get("type").and_then(|v| v.as_str())?;
    if ty != "outer_shadow" {
        return None;
    }
    let blur = effect.get("blur").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
    let offset = effect
        .get("offset")
        .and_then(|v| v.as_array())
        .map(|a| {
            [
                a.first().and_then(|v| v.as_f64()).unwrap_or(0.0) as f32,
                a.get(1).and_then(|v| v.as_f64()).unwrap_or(0.0) as f32,
            ]
        })
        .unwrap_or([0.0, 0.0]);
    let color = effect
        .get("color")
        .and_then(|v| v.as_str())
        .and_then(parse_hex)
        .unwrap_or([0, 0, 0, 0x7F]);
    Some((blur, offset, color))
}

fn shadow_extra_pad(s: &Option<(f32, [f32; 2], [u8; 4])>) -> Option<f32> {
    s.as_ref().map(|s| s.0 * 0.0) // currently unused; reserved for tight-bbox compensation
}

#[allow(dead_code)] // kept for the upcoming f32-color shader path
fn parse_color_as_f4(v: &Value) -> Option<[f32; 4]> {
    if v.get("type").and_then(|t| t.as_str()) == Some("color") {
        let hex = v.get("value").and_then(|v| v.as_str())?;
        let c = parse_hex(hex)?;
        return Some([
            c[0] as f32 / 255.0,
            c[1] as f32 / 255.0,
            c[2] as f32 / 255.0,
            c[3] as f32 / 255.0,
        ]);
    }
    None
}

fn parse_hex(s: &str) -> Option<[u8; 4]> {
    let s = s.strip_prefix('#')?;
    let h = |hi: u8, lo: u8| -> Option<u8> {
        fn d(c: u8) -> Option<u8> {
            match c {
                b'0'..=b'9' => Some(c - b'0'),
                b'a'..=b'f' => Some(10 + c - b'a'),
                b'A'..=b'F' => Some(10 + c - b'A'),
                _ => None,
            }
        }
        Some((d(hi)? << 4) | d(lo)?)
    };
    let b = s.as_bytes();
    match b.len() {
        6 => Some([h(b[0], b[1])?, h(b[2], b[3])?, h(b[4], b[5])?, 0xFF]),
        8 => Some([
            h(b[0], b[1])?,
            h(b[2], b[3])?,
            h(b[4], b[5])?,
            h(b[6], b[7])?,
        ]),
        3 => Some([h(b[0], b[0])?, h(b[1], b[1])?, h(b[2], b[2])?, 0xFF]),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::{_test_hello_skin_path, load};

    #[test]
    fn compiles_hello_skin_to_display_list() {
        let Some(path) = _test_hello_skin_path() else {
            eprintln!("skipping: hello.esk not located");
            return;
        };
        let skin = load(&path).unwrap();
        let dl = compile(&skin.document, 480, 320);
        // Borderless hello skin: gradient card + label text + button
        // card + button label = 4 commands (no scene background fill).
        assert!(dl.commands.len() >= 3, "got {:?}", dl.commands);
        // At least one GradientCard (the rounded card and/or the button).
        let card_count = dl
            .commands
            .iter()
            .filter(|c| matches!(c, DrawCommand::GradientCard { .. }))
            .count();
        assert!(
            card_count >= 2,
            "expected ≥2 cards (card + button), got {card_count}"
        );
        // At least one text node (either the greeting or the button label).
        let text_count = dl
            .commands
            .iter()
            .filter(|c| matches!(c, DrawCommand::DrawText { .. }))
            .count();
        assert!(text_count >= 1, "expected ≥1 text, got {text_count}");
    }

    #[test]
    fn parses_color_fill() {
        let v: Value =
            serde_json::from_str(r##"{ "type": "color", "value": "#5B3FF5" }"##).unwrap();
        let (s, e, c) = parse_fill_colors(Some(&v));
        assert!(s.is_none() && e.is_none() && c.is_some());
    }

    #[test]
    fn parses_linear_gradient_fill() {
        let v: Value = serde_json::from_str(
            r##"{"type":"linear_gradient","stops":[[0.0,"#5B3FF5"],[1.0,"#FF5C8A"]]}"##,
        )
        .unwrap();
        let (s, e, _) = parse_fill_colors(Some(&v));
        assert_eq!(s.unwrap(), [0x5B, 0x3F, 0xF5, 0xFF]);
        assert_eq!(e.unwrap(), [0xFF, 0x5C, 0x8A, 0xFF]);
    }
}
