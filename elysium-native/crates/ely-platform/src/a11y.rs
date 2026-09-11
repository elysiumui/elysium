//! Cross-platform accessibility bridge.
//!
//! Wire-up:
//! - macOS — uses the `accesskit` + `accesskit_macos` adapter, which posts
//!   into AppKit's NSAccessibility protocol.
//! - Linux — `accesskit_unix` (AT-SPI2 via D-Bus).
//! - Windows — `accesskit_windows` (UI Automation) — present on
//!   target_os = "windows" only.
//!
//! `AccessibilityNode` is the framework's lightweight surface that
//! components describe themselves against; `Bridge` translates a tree of
//! these into an accesskit `TreeUpdate`.

use parking_lot::Mutex;
use std::sync::Arc;

pub trait AccessibilityNode {
    fn role(&self) -> &str;
    fn label(&self) -> Option<&str> {
        None
    }
    fn description(&self) -> Option<&str> {
        None
    }
    fn keyboard_shortcut(&self) -> Option<&str> {
        None
    }
    /// Bounding box in window-local logical pixels: (x, y, w, h).
    fn bounds(&self) -> (f32, f32, f32, f32) {
        (0.0, 0.0, 0.0, 0.0)
    }
    /// Children, in tab order.
    fn children(&self) -> Vec<Box<dyn AccessibilityNode>> {
        Vec::new()
    }
}

#[derive(Clone, Debug)]
pub struct A11yNode {
    pub id: u64,
    pub role: String,
    pub label: Option<String>,
    pub description: Option<String>,
    pub shortcut: Option<String>,
    pub value: Option<String>,
    pub disabled: bool,
    pub selected: Option<bool>,
    pub read_only: bool,
    pub bounds: (f32, f32, f32, f32),
    pub children: Vec<A11yNode>,
}

/// A snapshot of the accessible tree pushed by the framework every time
/// it changes. The platform bridge consumes this and posts an OS-specific
/// update.
#[derive(Default, Clone, Debug)]
pub struct A11yTree {
    pub root: Option<A11yNode>,
}

impl A11yTree {
    pub fn from_flat(root_id: u64, entries: Vec<(A11yNode, Vec<u64>)>) -> Result<Self, String> {
        use std::collections::{HashMap, HashSet};
        let mut nodes = HashMap::new();
        let mut children = HashMap::new();
        for (node, kids) in entries {
            let id = node.id;
            if nodes.insert(id, node).is_some() {
                return Err(format!("Duplicate accessibility node {id}"));
            }
            children.insert(id, kids);
        }
        let mut visited = HashSet::new();
        let mut order = Vec::new();
        let mut pending = vec![(root_id, 0)];
        while let Some((id, depth)) = pending.pop() {
            if depth > 128 { return Err("Accessibility tree is too deep".into()); }
            if !nodes.contains_key(&id) { return Err(format!("Missing accessibility node {id}")); }
            if !visited.insert(id) { return Err(format!("Repeated or cyclic accessibility child {id}")); }
            order.push(id);
            for child in &children[&id] { pending.push((*child, depth + 1)); }
        }
        if visited.len() != nodes.len() { return Err("Accessibility nodes must belong to the root tree".into()); }
        let mut built = HashMap::new();
        for id in order.into_iter().rev() {
            let mut node = nodes.remove(&id).unwrap();
            node.children = children[&id].iter().map(|child| built.remove(child).unwrap()).collect();
            built.insert(id, node);
        }
        let tree = Self { root: built.remove(&root_id) };
        tree.validate()?;
        Ok(tree)
    }

    fn validate(&self) -> Result<(), String> {
        let mut seen = std::collections::HashSet::new();
        let mut pending = self.root.iter().map(|node| (node, 0)).collect::<Vec<_>>();
        while let Some((node, depth)) = pending.pop() {
            if depth > 128 { return Err("Accessibility tree is too deep".into()); }
            if node.id == u64::MAX || !seen.insert(node.id) {
                return Err(format!("Invalid or duplicate accessibility identity {}", node.id));
            }
            let (x,y,w,h) = node.bounds;
            if ![x,y,w,h].iter().all(|v| v.is_finite()) || w < 0.0 || h < 0.0 {
                return Err(format!("Invalid accessibility bounds for {}", node.id));
            }
            pending.extend(node.children.iter().map(|child| (child, depth + 1)));
        }
        Ok(())
    }
}

/// Shared, lock-protected accessibility state. The renderer/Designer
/// writes into it; the platform layer reads it on the main thread when
/// the OS asks "what's under this point?" / "what's focused?"
#[derive(Default)]
pub struct A11yState {
    pub tree: Mutex<A11yTree>,
    /// Currently focused node id (matches A11yNode::id).
    pub focused: parking_lot::Mutex<Option<u64>>,
    /// Set to `true` on every `publish` so the platform bridge knows
    /// to push a fresh TreeUpdate to the OS adapter on its next tick.
    /// The event loop swaps it back to `false` after refreshing.
    pub tree_dirty: std::sync::atomic::AtomicBool,
    /// Actions requested by an assistive technology — VoiceOver / JAWS
    /// / Orca calling "click this button", "focus this", etc. Python
    /// drains the queue and dispatches the matching hook.
    pub action_queue: Mutex<std::collections::VecDeque<(u64, String)>>,
    /// Source bounds remain logical; AccessKit consumes physical pixels.
    scale_milli: std::sync::atomic::AtomicU32,
}

impl A11yState {
    pub fn scale_factor(&self) -> f64 {
        let value = self.scale_milli.load(std::sync::atomic::Ordering::Acquire);
        if value == 0 { 1.0 } else { value as f64 / 1000.0 }
    }

    pub fn set_scale_factor(&self, scale: f64) {
        use std::sync::atomic::Ordering;
        let value = if scale.is_finite() && scale > 0.0 { scale } else { 1.0 };
        let value = (value * 1000.0).round().max(1.0) as u32;
        if self.scale_milli.swap(value, Ordering::AcqRel) != value {
            self.tree_dirty.store(true, Ordering::Release);
        }
    }

    pub fn new() -> Arc<Self> {
        Arc::new(Self::default())
    }

    pub fn publish(&self, tree: A11yTree) -> Result<(), String> {
        tree.validate()?;
        *self.tree.lock() = tree;
        self.tree_dirty
            .store(true, std::sync::atomic::Ordering::Release);
        Ok(())
    }

    pub fn set_focus(&self, id: Option<u64>) {
        *self.focused.lock() = id;
        self.tree_dirty
            .store(true, std::sync::atomic::Ordering::Release);
    }

    pub fn push_action(&self, node_id: u64, action: String) {
        self.action_queue.lock().push_back((node_id, action));
    }

    pub fn pop_action(&self) -> Option<(u64, String)> {
        self.action_queue.lock().pop_front()
    }

    /// Hit-test a (window-local) point against the published tree.
    /// Returns the deepest node whose bounds contain the point, or None.
    pub fn hit(&self, x: f32, y: f32) -> Option<A11yNode> {
        let tree = self.tree.lock();
        tree.root
            .as_ref()
            .and_then(|n| hit_recurse(n, x, y).cloned())
    }
}

fn hit_recurse(node: &A11yNode, x: f32, y: f32) -> Option<&A11yNode> {
    let (bx, by, bw, bh) = node.bounds;
    if !(x >= bx && y >= by && x <= bx + bw && y <= by + bh) {
        return None;
    }
    // Pick the deepest child that also contains the point.
    for c in &node.children {
        if let Some(hit) = hit_recurse(c, x, y) {
            return Some(hit);
        }
    }
    Some(node)
}

/// Map the framework's lightweight role strings to OS-canonical roles.
/// Returns the macOS NSAccessibilityRole equivalent; other platforms can
/// map this on through their own bridges.
pub fn ns_role_for(role: &str) -> &'static str {
    match role {
        "button" => "AXButton",
        "checkbox" => "AXCheckBox",
        "radio" => "AXRadioButton",
        "slider" => "AXSlider",
        "textfield" => "AXTextField",
        "textarea" => "AXTextArea",
        "list" => "AXList",
        "menu" => "AXMenu",
        "menuitem" => "AXMenuItem",
        "tab" => "AXTab",
        "image" => "AXImage",
        "link" => "AXLink",
        "label" => "AXStaticText",
        "group" => "AXGroup",
        "window" => "AXWindow",
        _ => "AXUnknown",
    }
}

#[cfg(target_os = "linux")]
pub fn atspi_role_for(role: &str) -> &'static str {
    match role {
        "button" => "push button",
        "checkbox" => "check box",
        "radio" => "radio button",
        "slider" => "slider",
        "textfield" => "text",
        "textarea" => "text",
        "list" => "list",
        "menu" => "menu",
        "menuitem" => "menu item",
        "image" => "image",
        "link" => "link",
        "label" => "label",
        "group" => "panel",
        "window" => "window",
        _ => "unknown",
    }
}

#[cfg(target_os = "windows")]
pub fn uia_control_type_for(role: &str) -> i32 {
    // UIA_ControlTypeIds from oleacc.h.
    match role {
        "button" => 50000,
        "checkbox" => 50002,
        "radio" => 50013,
        "slider" => 50015,
        "textfield" => 50004,
        "textarea" => 50004,
        "list" => 50008,
        "menu" => 50009,
        "menuitem" => 50011,
        "image" => 50006,
        "link" => 50005,
        "label" => 50020,
        "group" => 50026,
        "window" => 50032,
        _ => 50025, // Pane
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn n(id: u64, role: &str, b: (f32, f32, f32, f32), kids: Vec<A11yNode>) -> A11yNode {
        A11yNode {
            id,
            role: role.into(),
            label: None,
            description: None,
            shortcut: None,
            value: None,
            disabled: false,
            selected: None,
            read_only: false,
            bounds: b,
            children: kids,
        }
    }

    #[test]
    fn hit_test_returns_deepest() {
        let state = A11yState::new();
        let tree = A11yTree {
            root: Some(n(
                1,
                "window",
                (0.0, 0.0, 800.0, 600.0),
                vec![n(
                    2,
                    "group",
                    (10.0, 10.0, 200.0, 200.0),
                    vec![n(3, "button", (20.0, 20.0, 60.0, 30.0), vec![])],
                )],
            )),
        };
        state.publish(tree).unwrap();
        let h = state.hit(30.0, 30.0).unwrap();
        assert_eq!(h.id, 3);
        let g = state.hit(150.0, 150.0).unwrap();
        assert_eq!(g.id, 2);
        let w = state.hit(700.0, 500.0).unwrap();
        assert_eq!(w.id, 1);
        assert!(state.hit(900.0, 900.0).is_none());
    }

    #[test]
    fn role_mapping() {
        assert_eq!(ns_role_for("button"), "AXButton");
        assert_eq!(ns_role_for("nonsense"), "AXUnknown");
    }

    #[test]
    fn malformed_flat_trees_are_rejected_before_os_publication() {
        let node = |id| n(id, "button", (0.0,0.0,20.0,20.0), vec![]);
        assert!(A11yTree::from_flat(0, vec![(node(0),vec![1,1]),(node(1),vec![])]).is_err());
        assert!(A11yTree::from_flat(0, vec![(node(0),vec![1]),(node(1),vec![0])]).is_err());
        assert!(A11yTree::from_flat(0, vec![(node(0),vec![9])]).is_err());
        assert!(A11yTree::from_flat(0, vec![(node(0),vec![]),(node(0),vec![])]).is_err());
        assert!(A11yTree::from_flat(0, vec![(node(0),vec![]),(node(1),vec![])]).is_err());
        let state = A11yState::new();
        state.publish(A11yTree::from_flat(0,vec![(node(0),vec![1]),(node(1),vec![])]).unwrap()).unwrap();
        let invalid = A11yTree { root:Some(n(0,"window",(0.0,0.0,20.0,20.0),vec![node(1),node(1)])) };
        assert!(state.publish(invalid).is_err());
        assert_eq!(state.tree.lock().root.as_ref().unwrap().children.len(),1);
    }
}
