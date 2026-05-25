# Status line

The thin one-line bar at the very bottom of the window shows live
state: cursor coordinates, snap toggles, current frame, render FPS,
and any transient toast or error from a recent action.

![Status line annotated with each segment](../assets/interface-status-line.png)

## Segments, left to right

| Segment | Format | Notes |
|---|---|---|
| Cursor position | `x: 412.5, y: 198.0` | Canvas space, not screen space |
| Selection summary | `1 placement` / `3 placements` / `nothing selected` | Shows mesh / image / curve count when mixed |
| Current frame | `frame 0 / 24` | Hidden when the timeline is collapsed |
| Render FPS | `60 fps · 0.7 ms` | GPU frame time of the View Panel |
| Mode | `Modeling` | Active menu set |
| Snap | `grid on` / `grid off` | Click to toggle; same as `View > Snap to Grid` |
| Theme | `Dark` | Click to cycle themes; same as cycling `Theme > …` |

## Transient toasts

When an action completes (Export .esk, Bake textures, Save), a
toast appears in the status line for 3 seconds. Errors stay on
screen until the next action.

To recall the last 20 toasts: `Window > History > Recent Messages`.

## Customizing visibility

`File > Preferences > Status Line` lets you hide any segment. Most
people leave them all on; some workflows hide FPS to reduce
distraction during long renders.

## Keyboard shortcuts shown here

A handful of common hotkeys flash in the status line when used so
new users can see what they pressed. Disable that with
`File > Preferences > Status Line > Show Pressed Shortcut`.
