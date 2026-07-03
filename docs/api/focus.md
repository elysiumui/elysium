# `elysium.focus`

Directional focus navigation. Tab / Shift+Tab cycles by sequence;
arrow keys move spatially.

## Classes

| Class | Purpose |
|---|---|
| `FocusNode(id, bounds, tab_index=None, skip=False, on_focus=None, on_blur=None)` | One focusable region |

## Functions

| Function | Purpose |
|---|---|
| `next_focus(nodes, current_id, direction)` | Resolve the next node given a direction (`'next'`, `'prev'`, `'up'`, `'down'`, `'left'`, `'right'`) |

## Per-window helpers

(on `Window`: re-listed here)

| Method | Purpose |
|---|---|
| `window.install_focus_nav(nodes_provider)` | Activate focus on this window |
| `window.handle_focus_key(code, mods)` | Pass a key event for focus to consume |
| `window.focus_node(id)` | Programmatic focus |
| `window.focused_node` | Currently focused id or None |
| `window.on_focus_changed(fn)` | Subscribe to focus moves |
| `window.set_focus_trap(True)` | Cycle focus inside this window only |

## Auto-rendered details

::: elysium.focus

## See also

- [Focus](../guides/focus.md)
- [Events](../guides/events.md)
