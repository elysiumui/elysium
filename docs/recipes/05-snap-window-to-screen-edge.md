# How do I snap a window to the screen edge?

Call `set_edge_snap` with a pixel distance.

```python
window.set_edge_snap(distance=12)
```

When the user drags the window within 12 pixels of any active-
monitor edge, the window snaps to the edge on release.

Per-edge control:

```python
window.set_edge_snap(distance={
    "left": 12, "right": 12, "top": 0, "bottom": 12
})
```

Top-edge snap to 0 disables snapping at the top: useful when the
top of your window is a notch / camera area you do not want to
hit.

See [Windowing](../guides/windowing.md).
