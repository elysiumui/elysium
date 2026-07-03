# Focus

`elysium.focus` provides the framework's focus navigation:
keyboard focus moves between placements via Tab/Shift+Tab (sequence
order) or arrow keys (spatial direction).

## Enable focus on a window

```python
def current_nodes():
    return [
        focus.FocusNode(id="name_input", bounds=(10, 10, 200, 32)),
        focus.FocusNode(id="email_input", bounds=(10, 52, 200, 32)),
        focus.FocusNode(id="submit", bounds=(10, 100, 100, 32)),
    ]

window.install_focus_nav(current_nodes)
```

`install_focus_nav` takes a zero-arg callable that returns the
current focusable nodes. The callable is invoked each time the
focus moves, so dynamic UIs (lists, expanded accordions) update
naturally.

## Focus nodes

A `FocusNode` describes one focusable region:

```python
focus.FocusNode(
    id="my_button",
    bounds=(x, y, w, h),       # canvas-space rectangle
    tab_index=10,              # optional explicit tab order
    skip=False,                # exclude from focus traversal
    on_focus=fn,               # optional callback on focus
    on_blur=fn,
)
```

If `tab_index` is omitted, focus traversal uses document order
(the order returned by your `current_nodes()` provider).

## Subscribe to focus changes

```python
@window.on_focus_changed
def react(new_id):
    print("focus moved to", new_id)
```

Useful for drawing focus rings, opening tooltips, or scrolling the
focused row into view.

## Handle key events

The framework needs to know about every key your window receives.
Wire `handle_focus_key` from your key handler:

```python
@window.on("window.key")
def handle(event):
    if event.pressed and window.handle_focus_key(event.code, event.modifiers):
        return     # focus consumed it
    # otherwise dispatch elsewhere
```

`handle_focus_key` returns True if it consumed the key (Tab,
arrows). Returning early prevents downstream handlers from also
seeing the key.

## Directional navigation

Out of the box:

| Key | Effect |
|---|---|
| Tab | Next node by tab order |
| Shift+Tab | Previous node |
| ArrowUp / Down / Left / Right | Move spatially to the nearest node in that direction |

Spatial movement uses a cost function that picks the node whose
center is closest in the requested direction. For a settings
panel with a 2D grid of controls, this matches user expectation.

## Programmatic focus

```python
window.focus_node("submit")    # move focus to this id
window.focused_node            # currently focused id, or None
window.clear_focus()           # remove focus
```

## Focus rings

The framework does not draw focus rings by default. Components
that ship in `elysium.components` paint their own (a 2 px stroke
in `theme.accent`). For custom components:

```python
@reactive.effect
def update_ring():
    placement_id = window.focused_node
    for nid in all_focusable_ids:
        window[nid].outline = (theme.accent if nid == placement_id else "transparent")
```

## A11y integration

Focus changes also drive screen-reader announcements when a11y is
enabled (see [Accessibility](accessibility.md)). Each `on_focus`
hook fires `window.publish_a11y_focus(id)` automatically when the
framework's a11y bridge is on.

## Disabled placements

A placement with `disabled = True` is excluded from focus
traversal. Combined with `disabled.click` hooks, you can keep the
focus skipping disabled controls while still logging
disabled-press analytics.

## Trap focus

For modals, trap focus inside the modal's nodes:

```python
modal.install_focus_nav(modal_nodes)
modal.set_focus_trap(True)    # Tab cycles inside the modal
```

Common modal pattern: open modal → focus first input → trap →
close modal → restore previous focus.

## See also

- [Events](events.md): key event payload.
- [Components overview](components-overview.md): built-in
  components already handle focus correctly.
- [Accessibility](accessibility.md): focus rings + a11y tree.
