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
}

impl A11yState {
    pub fn new() -> Arc<Self> {
        Arc::new(Self::default())
    }

    pub fn publish(&self, tree: A11yTree) {
        *self.tree.lock() = tree;
        self.tree_dirty
            .store(true, std::sync::atomic::Ordering::Release);
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
        state.publish(tree);
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
}
