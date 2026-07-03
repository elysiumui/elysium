# Skins

A skin is a folder (extension `.esk`) describing a window's visual
layout. The framework loads skins via `window.load_skin(path)`;
the Designer authors them. Skins are the contract between
designer-side authoring and developer-side wiring.

## Folder layout

```
myapp.esk/
  manifest.json          # id, name, version, color space, window shape
  document.json          # the placements that compose the visual
  hooks.json             # hook names exposed to Python (auto-generated)
  textures/              # baked albedo, normal, mask PNGs
    butterfly_albedo.png
    butterfly_normal.png
  assets/                # any other resources (HDR, fonts, …)
    studio.hdr
  animations/            # exported animation tracks
    wing_flap.json
  shaders/               # custom WGSL (rare)
  variants/              # per-light / per-theme overrides
  designer_layout.json   # Designer's own UI state (ignored by runtime)
```

`manifest.json` and `document.json` are required. Everything else
is optional.

## manifest.json

```json
{
  "schema_version": "1.0",
  "id": "dev.elysium.butterfly",
  "name": "Butterfly",
  "version": "0.1.0",
  "color_space": "srgb",
  "kind": "application",
  "window": {
    "shape": {
      "kind": "path",
      "path_d": "M …"
    }
  }
}
```

The framework reads `window.shape` on `load_skin` and applies it
as the window's hit region automatically.

## Skin kinds: application vs component

The `kind` field on the manifest declares what *role* the skin
plays. Two values are supported:

| Kind          | Owns a window? | Used by                                            |
| ------------- | -------------- | -------------------------------------------------- |
| `application` | yes (default)  | `window.load_skin(path)` — the whole window paints from this skin |
| `component`   | no             | Stamped into another skin's DisplayList at runtime |

A **component** skin is a reusable sub-piece — a badge, an indicator
cluster, a glyph — that's never displayed on its own. The pomodoro
example's leaf-cluster stem is the canonical one
(`examples/pomodoro/stem.esk`). The host app loads it via the native
loader, compiles it to a DisplayList, and stamps it into the
main DisplayList under a transform that the app controls live:

```python
from elysium._native import _native as _n

stem_skin = _n.load_skin("examples/pomodoro/stem.esk")
stem_dl   = stem_skin.to_display_list(200, 200)
# Per frame, in the host's render loop:
dl.push_transform(sx - 100 * scale, sy - 100 * scale, scale, scale)
dl.extend(stem_dl)          # bakes in the component's paint commands
dl.pop_transform()
```

The framework guards against misuse: `window.load_skin(path)` raises
a `ValueError` if the manifest declares `"kind": "component"`,
because a component has no window-level chrome (no title bar, no
background, no scene background colour). Loading one as a
top-level window would render a tiny offset glyph in the corner of
an otherwise-empty window — almost certainly a bug.

In the Designer, the Kind appears as a dropdown at the top of the
**Properties — App Window** panel. Toggling it writes the new value
to `manifest.json` and reconfigures the App Window chrome to match
(`component` ⇒ transparent + no title bar; `application` ⇒ normal
chrome). Bundles authored before this field existed default to
`application`, so old skins keep working unchanged.

## document.json

```json
{
  "placements": [
    { "id": "background", "kind": "ellipse", "x": 0, "y": 0, "width": 360, "height": 360, "fill": "#0f0d1eff" },
    { "id": "time_label", "kind": "label", "x": 120, "y": 168, "text": "00:00:00", "font_size": 18, "fill": "#ffffffff" }
  ]
}
```

Each placement is a typed dict with an `id` and a `kind`. The
`kind` decides which other fields are valid. See the
[Skin schema reference](../api/elysium.md).

## Placement kinds

The most common kinds in skins:

| Kind | Common in |
|---|---|
| `ellipse` / `rectangle` / `rounded_rect` | 2D backgrounds |
| `path` | Custom shapes |
| `arc` / `ticks` | Charts and dials |
| `label` / `heading` | Text |
| `button` / `icon_button` / `orb_button` | Actions |
| `card` / `panel` | Surface containers |
| `image` | Raster images |
| `mesh3d` | 3D models |
| `light` / `camera` | 3D scene parts |
| `canvas` | Custom-drawn region (recv DisplayList from Python) |

The Designer's [Toolbox](https://designer.elysiumui.com/interface/toolbox/)
maps to these kinds one-for-one.

## Loading at runtime

```python
window.load_skin("path/to/myapp.esk/")
```

After this:

- Every placement's `id` is available via the dotted hook proxy:
  `window.time_label.text = "12:34:56"`.
- Click events on a placement with `kind: "button"` fire
  `<id>.click` hooks; bind with `@window.on("save.click")`.
- The Skin's animations (if any) are accessible via
  `window.skin.animations["wing_flap"].play(loop=True)`.

## Editing while running

`window.load_skin(path)` is idempotent. Calling it again reloads
the skin in place: useful for hot-reload (see
[Hot reload](hot-reload.md)).

## The designer-developer contract

A well-designed skin gives the developer a stable set of
**hook names**:

- `save.click`, `cancel.click`, etc. for actions.
- `name_input.value` for inputs.
- `tabs.change` for tab switches.

The developer wires these names in Python without depending on
the skin's visual structure. The designer can re-arrange the
visuals at any time without breaking the developer's code, as
long as the hook names stay.

`hooks.json` (auto-generated by the Designer on save) is the
machine-readable list of every hook the skin exposes. Use it for
codegen via [Code Link](code-link.md).

## `{theme.…}` token references

Skin placements can bind colors and motion to theme tokens:

```json
"stroke": "{theme.accent}",
"motion": "{theme.motion}",
"fill": "{theme.surface}"
```

The framework resolves on `load_skin` and on `set_theme`. See
[Theming](theming.md).

## Variants

For per-theme or per-platform skin variants, drop them into
`variants/<name>/document.json`. The framework picks the matching
variant on `load_skin` based on the active theme / platform; falls
back to the root `document.json` otherwise.

## Performance

Loading a typical skin (~30 placements, two textures) takes
~30 ms cold, ~5 ms warm (cached). The renderer pre-compiles each
placement's draw path into the display list on load, so subsequent
frames are cheap.

## See also

- [Borderless and shaped](borderless-and-shaped.md): the
  `window.shape` field.
- [Code Link](code-link.md): designer-to-code wiring.
- [Hot reload](hot-reload.md): live editing.
- [Designer .esk bundle reference](https://designer.elysiumui.com/reference/esk-bundle-format/)
 : full schema.
