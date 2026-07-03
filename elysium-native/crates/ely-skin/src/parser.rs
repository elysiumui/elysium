//! `.esk` loader: ZIP archive OR unzipped directory, returning a parsed
//! manifest + document + hooks.

use crate::registry::{Hook, HookKind, HookRegistry};
use crate::validator::validate_document;
use serde::{Deserialize, Serialize};
use std::io::Read;
use std::path::{Path as StdPath, PathBuf};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SkinError {
    #[error("invalid manifest: {0}")]
    Manifest(String),
    #[error("invalid document: {0}")]
    Document(String),
    #[error("hook collision: {0}")]
    HookCollision(String),
    #[error("missing required file: {0}")]
    MissingFile(String),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("json: {0}")]
    Json(#[from] serde_json::Error),
    #[error("zip: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("validation: {0}")]
    Validation(String),
    #[error("signature: {0}")]
    Signature(String),
}

/// Identifies whether an `.esk` bundle is a standalone app skin or a
/// reusable sub-component skin that gets stamped into another app's
/// window. Drives the Designer's window chrome (a component skin has
/// no title bar / frame) and lets runtime hosts reject misuse — e.g.
/// `App.window().load_skin(...)` should error on a Component, and a
/// component-renderer (`DisplayList.extend`-style) should warn on an
/// Application.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum SkinKind {
    /// Self-contained skin that owns a top-level window. Default for
    /// backward compatibility — pre-`kind` bundles all open as apps.
    #[default]
    Application,
    /// Sub-component: no window of its own, no chrome. Designed to be
    /// composed into another skin's DisplayList at runtime.
    Component,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Manifest {
    pub schema_version: String,
    #[serde(default)]
    pub elysium_min_version: Option<String>,
    pub id: String,
    pub name: String,
    pub version: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub authors: Vec<String>,
    #[serde(default)]
    pub license: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub color_space: Option<String>,
    #[serde(default)]
    pub supports_variants: Vec<String>,
    /// Standalone-app vs reusable sub-component. See `SkinKind`.
    #[serde(default)]
    pub kind: SkinKind,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Document {
    pub root: Node,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Node {
    #[serde(default)]
    pub id: Option<String>,
    #[serde(rename = "type")]
    pub kind: NodeKind,
    #[serde(default)]
    pub size: Option<Size>,
    #[serde(default)]
    pub background: Option<serde_json::Value>,
    #[serde(default)]
    pub transform: Option<Transform>,
    /// SVG path data (when `type == "path"`).
    #[serde(default)]
    pub d: Option<String>,
    #[serde(default)]
    pub fill: Option<serde_json::Value>,
    #[serde(default)]
    pub stroke: Option<serde_json::Value>,
    #[serde(default)]
    pub effects: Vec<serde_json::Value>,
    #[serde(default)]
    pub hit_test: Option<String>,
    #[serde(default)]
    pub hooks: Vec<HookSpec>,
    /// Singular "hook" alias — collapsed into `hooks` after parse.
    #[serde(default)]
    pub hook: Option<HookSpec>,
    #[serde(default)]
    pub children: Vec<Node>,
    /// `<text>` content / placeholder. Accepts either `"text"` or
    /// `"value"` from the document (the Designer + the public schema
    /// have historically used both names).
    #[serde(default, alias = "value")]
    pub text: Option<String>,
    /// `<text>` font size, in scene-local units. Optional; falls back
    /// to a sensible default in `compile.rs` when absent.
    #[serde(default)]
    pub font_size: Option<f32>,
    /// `<text>` colour. Hex string `#RRGGBB` or `#RRGGBBAA`.
    #[serde(default)]
    pub color: Option<String>,
    /// Bare `x`/`y` placement for nodes that don't ride on a full
    /// `transform` block — text labels in the public schema use
    /// these directly.
    #[serde(default)]
    pub x: Option<f32>,
    #[serde(default)]
    pub y: Option<f32>,
    /// `<image>` src.
    #[serde(default)]
    pub src: Option<String>,
    /// `<image>` fit mode.
    #[serde(default)]
    pub fit: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum NodeKind {
    #[default]
    Group,
    Scene,
    Path,
    Image,
    Text,
    Component,
    Webview,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Size {
    pub w: f32,
    pub h: f32,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, Default)]
pub struct Transform {
    #[serde(default)]
    pub x: f32,
    #[serde(default)]
    pub y: f32,
    #[serde(default)]
    pub rotation: f32,
    #[serde(default = "default_scale")]
    pub scale: [f32; 2],
}
fn default_scale() -> [f32; 2] {
    [1.0, 1.0]
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HookSpec {
    pub name: String,
    #[serde(rename = "type")]
    pub kind_str: String,
    #[serde(default)]
    pub events: Vec<String>,
    #[serde(default)]
    pub states: Vec<String>,
    #[serde(default)]
    pub range: Option<[f64; 2]>,
}

#[derive(Debug, Clone)]
pub struct Skin {
    pub manifest: Manifest,
    pub document: Document,
    pub hooks: HookRegistry,
}

/// Rewrite every `<image src>` that is currently a relative path so it
/// resolves against the skin's root directory. Absolute paths (and the
/// special `bundled://` scheme) are left as-is.
fn resolve_relative_src(node: &mut Node, root: &StdPath) {
    if let Some(src) = node.src.as_mut() {
        let p = StdPath::new(src.as_str());
        if !p.is_absolute() && !src.contains("://") {
            let abs = root.join(p);
            *src = abs.to_string_lossy().into_owned();
        }
    }
    for child in node.children.iter_mut() {
        resolve_relative_src(child, root);
    }
}

/// What to do when a skin is missing or carries an invalid signature.
///
/// * `Off` — skip verification entirely (developer mode; hand-authored skins).
/// * `Lenient` — verify when `signature.json` is present, accept when it's not.
/// * `Required` — reject any skin without a valid `signature.json`.
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub enum SignaturePolicy {
    Off,
    Lenient,
    Required,
}

impl Default for SignaturePolicy {
    fn default() -> Self {
        // Default mirrors the spec: marketplace-installed skins must be
        // signed (the marketplace client enforces this on its side too),
        // local skins are accepted without a signature.
        match std::env::var("ELYSIUM_SIGNATURE_POLICY")
            .as_deref()
            .unwrap_or("lenient")
        {
            "off" => SignaturePolicy::Off,
            "required" => SignaturePolicy::Required,
            _ => SignaturePolicy::Lenient,
        }
    }
}

/// Load a skin from either a directory ending in `.esk/` or a `.esk` ZIP.
pub fn load(path: impl AsRef<StdPath>) -> Result<Skin, SkinError> {
    load_with_policy(path, SignaturePolicy::default())
}

pub fn load_with_policy(
    path: impl AsRef<StdPath>,
    policy: SignaturePolicy,
) -> Result<Skin, SkinError> {
    let path = path.as_ref();
    let skin = if path.is_dir() {
        load_from_dir(path)?
    } else {
        load_from_zip(path)?
    };
    verify_signature_if_present(path, policy)?;
    Ok(skin)
}

fn verify_signature_if_present(path: &StdPath, policy: SignaturePolicy) -> Result<(), SkinError> {
    if policy == SignaturePolicy::Off {
        return Ok(());
    }
    if path.is_dir() {
        verify_dir(path, policy)
    } else {
        verify_zip(path, policy)
    }
}

fn verify_dir(path: &StdPath, policy: SignaturePolicy) -> Result<(), SkinError> {
    let sig_path = path.join("signature.json");
    if !sig_path.is_file() {
        if policy == SignaturePolicy::Required {
            return Err(SkinError::Signature(
                "signature.json missing (policy=required)".into(),
            ));
        }
        return Ok(());
    }
    let sig_raw = std::fs::read_to_string(&sig_path).map_err(SkinError::Io)?;
    let manifest = std::fs::read(path.join("manifest.json")).map_err(SkinError::Io)?;
    let document = std::fs::read(path.join("document.json")).map_err(SkinError::Io)?;
    verify_payload(&sig_raw, &manifest, &document)
}

fn verify_zip(path: &StdPath, policy: SignaturePolicy) -> Result<(), SkinError> {
    let file = std::fs::File::open(path)?;
    let mut archive = zip::ZipArchive::new(file)?;
    let mut grab = |name: &str| -> Option<String> {
        let mut e = archive.by_name(name).ok()?;
        let mut s = String::new();
        use std::io::Read;
        e.read_to_string(&mut s).ok()?;
        Some(s)
    };
    let sig_raw = match grab("signature.json") {
        Some(s) => s,
        None => {
            if policy == SignaturePolicy::Required {
                return Err(SkinError::Signature(
                    "signature.json missing from .esk archive".into(),
                ));
            }
            return Ok(());
        }
    };
    let manifest = grab("manifest.json")
        .ok_or_else(|| SkinError::MissingFile("manifest.json".into()))?
        .into_bytes();
    let document = grab("document.json")
        .ok_or_else(|| SkinError::MissingFile("document.json".into()))?
        .into_bytes();
    verify_payload(&sig_raw, &manifest, &document)
}

fn verify_payload(sig_raw: &str, manifest: &[u8], document: &[u8]) -> Result<(), SkinError> {
    let sig_doc: serde_json::Value =
        serde_json::from_str(sig_raw).map_err(|e| SkinError::Signature(e.to_string()))?;
    let pubkey_hex = sig_doc
        .get("publisher_pubkey")
        .and_then(|v| v.as_str())
        .ok_or_else(|| SkinError::Signature("missing publisher_pubkey".into()))?;
    let sig_hex = sig_doc
        .get("signature")
        .and_then(|v| v.as_str())
        .ok_or_else(|| SkinError::Signature("missing signature".into()))?;
    let pubkey = hex_decode_32(pubkey_hex)
        .ok_or_else(|| SkinError::Signature("publisher_pubkey not 32 hex bytes".into()))?;
    let sig = hex_decode_64(sig_hex)
        .ok_or_else(|| SkinError::Signature("signature not 64 hex bytes".into()))?;
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    h.update(manifest);
    h.update(document);
    let digest = h.finalize();
    crate::signature::verify(&pubkey, &digest, &sig)
        .map_err(|e| SkinError::Signature(e.to_string()))
}

fn hex_decode_32(s: &str) -> Option<[u8; 32]> {
    let v = hex_decode(s)?;
    if v.len() != 32 {
        return None;
    }
    let mut a = [0u8; 32];
    a.copy_from_slice(&v);
    Some(a)
}
fn hex_decode_64(s: &str) -> Option<[u8; 64]> {
    let v = hex_decode(s)?;
    if v.len() != 64 {
        return None;
    }
    let mut a = [0u8; 64];
    a.copy_from_slice(&v);
    Some(a)
}
fn hex_decode(s: &str) -> Option<Vec<u8>> {
    if !s.len().is_multiple_of(2) {
        return None;
    }
    let mut out = Vec::with_capacity(s.len() / 2);
    for i in (0..s.len()).step_by(2) {
        out.push(u8::from_str_radix(&s[i..i + 2], 16).ok()?);
    }
    Some(out)
}

fn load_from_dir(root: &StdPath) -> Result<Skin, SkinError> {
    let manifest_bytes = std::fs::read(root.join("manifest.json"))
        .map_err(|_| SkinError::MissingFile("manifest.json".into()))?;
    let manifest: Manifest =
        serde_json::from_slice(&manifest_bytes).map_err(|e| SkinError::Manifest(e.to_string()))?;

    let doc_bytes = std::fs::read(root.join("document.json"))
        .map_err(|_| SkinError::MissingFile("document.json".into()))?;
    let doc_value: serde_json::Value = serde_json::from_slice(&doc_bytes)?;
    validate_document(&doc_value).map_err(|e| SkinError::Validation(e.to_string()))?;
    let mut document: Document =
        serde_json::from_value(doc_value).map_err(|e| SkinError::Document(e.to_string()))?;
    resolve_relative_src(&mut document.root, root);

    // hooks.json is the *generated* flat index; if present we trust it,
    // otherwise we walk the document and build it ourselves.
    let hooks = if root.join("hooks.json").is_file() {
        let raw = std::fs::read_to_string(root.join("hooks.json"))?;
        super::parser::parse_hooks(&raw)?
    } else {
        collect_hooks(&document.root)?
    };

    Ok(Skin {
        manifest,
        document,
        hooks,
    })
}

fn load_from_zip(path: &StdPath) -> Result<Skin, SkinError> {
    let file = std::fs::File::open(path)?;
    let mut archive = zip::ZipArchive::new(file)?;

    let read_to_string =
        |archive: &mut zip::ZipArchive<std::fs::File>, name: &str| -> Result<String, SkinError> {
            let mut entry = archive
                .by_name(name)
                .map_err(|_| SkinError::MissingFile(name.into()))?;
            let mut s = String::new();
            entry.read_to_string(&mut s)?;
            Ok(s)
        };

    let manifest: Manifest = serde_json::from_str(&read_to_string(&mut archive, "manifest.json")?)
        .map_err(|e| SkinError::Manifest(e.to_string()))?;
    let doc_str = read_to_string(&mut archive, "document.json")?;
    let doc_value: serde_json::Value = serde_json::from_str(&doc_str)?;
    validate_document(&doc_value).map_err(|e| SkinError::Validation(e.to_string()))?;
    let document: Document =
        serde_json::from_value(doc_value).map_err(|e| SkinError::Document(e.to_string()))?;

    let hooks = if let Ok(raw) = read_to_string(&mut archive, "hooks.json") {
        super::parser::parse_hooks(&raw)?
    } else {
        collect_hooks(&document.root)?
    };

    Ok(Skin {
        manifest,
        document,
        hooks,
    })
}

/// Walk a node tree and emit a flat HookRegistry. The Designer normally
/// pre-generates `hooks.json` for us, but this fallback keeps hand-authored
/// skins working without that bookkeeping.
pub fn collect_hooks(root: &Node) -> Result<HookRegistry, SkinError> {
    let mut reg = HookRegistry::default();
    walk(root, &mut reg)?;
    Ok(reg)
}

fn walk(node: &Node, reg: &mut HookRegistry) -> Result<(), SkinError> {
    let collect_from = |reg: &mut HookRegistry, spec: &HookSpec| -> Result<(), SkinError> {
        if reg.get(&spec.name).is_some() {
            return Err(SkinError::HookCollision(spec.name.clone()));
        }
        let kind = match spec.kind_str.as_str() {
            "event" => HookKind::Event {
                events: spec.events.clone(),
            },
            "text" => HookKind::Text,
            "image" => HookKind::Image,
            "value" => HookKind::Value { range: spec.range },
            "state" => HookKind::State {
                states: spec.states.clone(),
            },
            "slot" => HookKind::Slot,
            "style" => HookKind::Style,
            other => {
                return Err(SkinError::Document(format!(
                    "unknown hook kind '{other}' on hook '{}'",
                    spec.name
                )))
            }
        };
        reg.insert(Hook {
            name: spec.name.clone(),
            node_id: 0,
            kind,
        });
        Ok(())
    };

    if let Some(spec) = &node.hook {
        collect_from(reg, spec)?;
    }
    for spec in &node.hooks {
        collect_from(reg, spec)?;
    }
    for child in &node.children {
        walk(child, reg)?;
    }
    Ok(())
}

/// Parse an in-memory `hooks.json` payload.
pub fn parse_hooks(raw: &str) -> Result<HookRegistry, SkinError> {
    let map: std::collections::HashMap<String, Hook> = serde_json::from_str(raw)?;
    let mut reg = HookRegistry::default();
    for (name, mut h) in map {
        h.name = name.clone();
        reg.insert(h);
    }
    Ok(reg)
}

/// Locate `examples/hello/hello.esk` regardless of `cargo test` cwd quirks.
#[doc(hidden)]
pub fn _test_hello_skin_path() -> Option<PathBuf> {
    // Walk up from CARGO_MANIFEST_DIR until we hit the repo root.
    let mut dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    for _ in 0..6 {
        let candidate = dir.join("examples/hello/hello.esk");
        if candidate.is_dir() {
            return Some(candidate);
        }
        if !dir.pop() {
            break;
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_state_hook() {
        let raw = r#"{
            "play_button.state": { "type": "state", "states": ["idle","hover","pressed"] }
        }"#;
        let reg = parse_hooks(raw).unwrap();
        assert!(matches!(
            reg.get("play_button.state").unwrap().kind,
            crate::registry::HookKind::State { .. }
        ));
    }

    #[test]
    fn loads_hello_skin_from_dir() {
        let Some(path) = _test_hello_skin_path() else {
            eprintln!("skipping: examples/hello/hello.esk not found");
            return;
        };
        let skin = load(&path).expect("load hello.esk");
        assert_eq!(skin.manifest.id, "dev.elysium.hello");
        assert_eq!(skin.manifest.schema_version, "1.0");
        // The hooks.json sidecar lists exactly these four.
        assert!(skin.hooks.get("greeting_button.click").is_some());
        assert!(skin.hooks.get("greeting_button.hover").is_some());
        assert!(skin.hooks.get("greeting_button.state").is_some());
        assert!(skin.hooks.get("message.text").is_some());
        assert_eq!(skin.hooks.len(), 4);
    }

    #[test]
    fn collects_hooks_from_document_when_no_sidecar() {
        let doc: Node = serde_json::from_str(
            r#"{
          "type": "scene",
          "children": [
            { "type": "path", "id": "btn", "hooks": [
              { "name": "btn.click", "type": "event", "events": ["click"] }
            ]}
          ]
        }"#,
        )
        .unwrap();
        let reg = collect_hooks(&doc).unwrap();
        assert!(reg.get("btn.click").is_some());
    }

    #[test]
    fn rejects_hook_collision() {
        let doc: Node = serde_json::from_str(
            r#"{
          "type": "scene",
          "children": [
            { "type": "path", "hooks": [{"name": "x", "type": "text"}] },
            { "type": "path", "hooks": [{"name": "x", "type": "text"}] }
          ]
        }"#,
        )
        .unwrap();
        let err = collect_hooks(&doc).err().unwrap();
        assert!(matches!(err, SkinError::HookCollision(_)));
    }
}
