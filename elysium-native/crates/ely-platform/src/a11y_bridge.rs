//! Bridge from the framework's `A11yTree` to the platform's assistive
//! technology API via `accesskit`.
//!
//! * macOS — `accesskit_macos::Adapter` posts into NSAccessibility.
//! * Linux — `accesskit_unix::Adapter` exposes the tree on AT-SPI2.
//! * Windows — `accesskit_windows::Adapter` registers a UIA provider.
//!
//! The framework publishes a fresh tree (via `Window.publish_a11y_tree`
//! from Python or `WindowHandle::a11y().publish(...)` from Rust) and
//! the bridge pushes it as an accesskit `TreeUpdate`. Focus changes go
//! the same way through `update_focus`.

use crate::a11y::{A11yNode, A11yState, A11yTree};
use accesskit::{Action, Node, NodeBuilder, NodeId, Rect, Role, Tree, TreeUpdate};
// Used only by `attach_linux` and the noop handler impls below; gated
// to avoid an "unused import" warning (which is a hard error under
// our `-D warnings` lint level in CI) on macOS / Windows.
#[cfg(target_os = "linux")]
use accesskit::{ActivationHandler, DeactivationHandler};
use std::sync::Arc;

pub struct A11yBridge {
    state: Arc<A11yState>,
    #[cfg(target_os = "macos")]
    adapter: Option<accesskit_macos::Adapter>,
    #[cfg(target_os = "windows")]
    adapter: Option<accesskit_windows::Adapter>,
    #[cfg(target_os = "linux")]
    adapter: Option<accesskit_unix::Adapter>,
}

impl A11yBridge {
    pub fn new(state: Arc<A11yState>) -> Self {
        Self {
            state,
            adapter: None,
        }
    }

    /// macOS: attach to the live NSView. Pass the raw pointer the
    /// winit window gave us (the same one `enable_blur_behind` consumes).
    // Safe to take a raw pointer here: we null-check before use and the
    // caller contract (a live NSView from winit) is documented; keeping a
    // safe signature avoids forcing `unsafe` blocks on every call site.
    #[allow(clippy::not_unsafe_ptr_arg_deref)]
    #[cfg(target_os = "macos")]
    pub fn attach_macos(&mut self, ns_view: *mut std::ffi::c_void) {
        if ns_view.is_null() {
            return;
        }
        let adapter = unsafe {
            accesskit_macos::Adapter::new(
                ns_view,
                false,
                StateActionHandler {
                    state: self.state.clone(),
                },
            )
        };
        self.adapter = Some(adapter);
        self.refresh();
    }

    /// Windows: attach to the live HWND.
    #[cfg(target_os = "windows")]
    pub fn attach_windows(&mut self, hwnd: isize) {
        // `windows` crate 0.54 (pinned transitively by
        // accesskit_windows 0.22) made `HWND` a non-primitive tuple
        // struct: `pub struct HWND(pub isize);`. winit hands the
        // raw handle out as an isize, so construct the wrapper
        // explicitly — `hwnd as _` no longer compiles because the
        // target type isn't primitive.
        use windows::Win32::Foundation::HWND;
        let hwnd = HWND(hwnd);
        let adapter = accesskit_windows::Adapter::new(
            hwnd,
            false,
            StateActionHandler {
                state: self.state.clone(),
            },
        );
        self.adapter = Some(adapter);
        self.refresh();
    }

    /// Linux: attach an AT-SPI2 adapter.
    #[cfg(target_os = "linux")]
    pub fn attach_linux(&mut self) {
        // `accesskit_unix 0.12` switched `Adapter::new` from
        //   `(is_window_focused: bool, action_handler) -> Result<Self>`
        // to a 3-handler form returning the adapter directly:
        //   `(activation_handler, action_handler, deactivation_handler) -> Self`
        // The bus connection is no longer fallible at construction
        // time; AT-SPI activation is deferred until a screen reader
        // actually asks for the tree (via the `ActivationHandler`).
        let action = StateActionHandler {
            state: self.state.clone(),
        };
        let activate = NoopActivationHandler;
        let deactivate = NoopDeactivationHandler;
        let adapter = accesskit_unix::Adapter::new(activate, action, deactivate);
        self.adapter = Some(adapter);
        self.refresh();
    }

    /// Publish the latest tree to the platform. Call after the
    /// framework's `A11yState::publish` so the OS sees the new layout.
    pub fn refresh(&mut self) {
        #[cfg(any(target_os = "macos", target_os = "windows", target_os = "linux"))]
        if let Some(adapter) = self.adapter.as_mut() {
            let lock = self.state.tree.lock();
            let update = build_tree_update(&lock);
            adapter.update_if_active(|| update);
        }
    }
}

/// Translate a framework `A11yTree` into an accesskit `TreeUpdate`.
fn build_tree_update(tree: &A11yTree) -> TreeUpdate {
    let mut nodes: Vec<(NodeId, Node)> = Vec::new();
    let root_id: NodeId = NodeId(1);
    if let Some(root) = &tree.root {
        push_node(&mut nodes, root);
    } else {
        let b = NodeBuilder::new(Role::Window);
        nodes.push((root_id, b.build()));
    }
    let focus = tree.root.as_ref().map(node_id_for).unwrap_or(root_id);
    TreeUpdate {
        nodes,
        tree: Some(Tree::new(root_id)),
        focus,
    }
}

fn push_node(out: &mut Vec<(NodeId, Node)>, n: &A11yNode) {
    let mut b = NodeBuilder::new(role_for(&n.role));
    if let Some(label) = &n.label {
        b.set_name(label.as_str());
    }
    if let Some(desc) = &n.description {
        b.set_description(desc.as_str());
    }
    if let Some(short) = &n.shortcut {
        b.set_keyboard_shortcut(short.as_str());
    }
    let (x, y, w, h) = n.bounds;
    b.set_bounds(Rect {
        x0: x as f64,
        y0: y as f64,
        x1: (x + w) as f64,
        y1: (y + h) as f64,
    });
    if !n.children.is_empty() {
        let kids: Vec<NodeId> = n.children.iter().map(node_id_for).collect();
        b.set_children(kids);
    }
    // Anything clickable gets the default click action so screen
    // readers offer "press this button" to the user.
    b.add_action(Action::Default);
    out.push((node_id_for(n), b.build()));
    for c in &n.children {
        push_node(out, c);
    }
}

fn node_id_for(n: &A11yNode) -> NodeId {
    // accesskit IDs must be non-zero — bias by 1 so our root id 0 still
    // becomes a valid NodeId.
    NodeId(n.id.saturating_add(1))
}

fn role_for(role: &str) -> Role {
    match role {
        "button" => Role::Button,
        "checkbox" => Role::CheckBox,
        "radio" => Role::RadioButton,
        "slider" => Role::Slider,
        "textfield" => Role::TextInput,
        "textarea" => Role::MultilineTextInput,
        "list" => Role::List,
        "menu" => Role::Menu,
        "menuitem" => Role::MenuItem,
        "tab" => Role::Tab,
        "image" => Role::Image,
        "link" => Role::Link,
        "label" => Role::Label,
        "group" => Role::Group,
        "window" => Role::Window,
        _ => Role::GenericContainer,
    }
}

/// Pushes incoming AT actions onto the shared `A11yState::action_queue`
/// so the Python side can drain + dispatch them on the next frame.
/// VoiceOver / JAWS / Orca clicking "press this button" hits here.
struct StateActionHandler {
    state: Arc<A11yState>,
}

impl accesskit::ActionHandler for StateActionHandler {
    fn do_action(&mut self, req: accesskit::ActionRequest) {
        // accesskit Node IDs are biased by +1 so 0 is reserved; reverse
        // the bias when handing back to the framework.
        let node_id = req.target.0.saturating_sub(1);
        let name = format!("{:?}", req.action);
        self.state.push_action(node_id, name);
    }
}

/// No-op handler given to `accesskit_unix::Adapter::new` so a screen
/// reader can wake the tree on demand. Returning `None` tells accesskit
/// "no initial tree yet" — the next `refresh()` call from the framework
/// pushes the real one via `update_if_active`.
#[cfg(target_os = "linux")]
struct NoopActivationHandler;
#[cfg(target_os = "linux")]
impl ActivationHandler for NoopActivationHandler {
    fn request_initial_tree(&mut self) -> Option<accesskit::TreeUpdate> {
        None
    }
}

/// No-op deactivation handler — we don't carry any AT-SPI-specific
/// resources that need explicit teardown when the bus drops us; the
/// `Adapter` itself owns whatever it allocates.
#[cfg(target_os = "linux")]
struct NoopDeactivationHandler;
#[cfg(target_os = "linux")]
impl DeactivationHandler for NoopDeactivationHandler {
    fn deactivate_accessibility(&mut self) {}
}
