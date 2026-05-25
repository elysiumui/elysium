# Native `.elybrush` format

`.elybrush` is the Designer's portable brush file. One file holds a
complete preset (engine + parameters + dynamics curves + optional
texture / pattern image). Built-in presets, Studio-saved presets,
and `.abr` / `.sut` imports all live in this format.

## Why a custom format

- **One file per preset**: trivial to share, version-control, and
  rsync across machines.
- **Forward-compatible JSON wrapper**: Designer versions ignore
  fields they do not understand instead of refusing to load.
- **Embeddable images**: textures and pattern stamps base64-embed
  into the same file (or reference an external PNG when the user
  prefers).

## File anatomy

A `.elybrush` is a JSON document (`.elybrush` is the extension; the
content is text). Minimal example:

```json
{
  "schema_version": "1.0",
  "id": "ely.builtin.pencil",
  "name": "Pencil",
  "engine": "round_stamp",
  "params": {
    "size_px": 4,
    "opacity": 0.7,
    "hardness": 0.95,
    "spacing": 0.18
  },
  "dynamics": {
    "size_px": {
      "channel": "pressure",
      "curve": [[0.0, 0.1], [0.5, 0.5], [1.0, 1.0]]
    },
    "opacity": {
      "channel": "pressure",
      "curve": [[0.0, 0.2], [1.0, 1.0]]
    }
  },
  "tags": ["sketch", "dry"],
  "color": "#222222ff",
  "thumbnail": "data:image/png;base64,iVBORw0KGgo..."
}
```

## Top-level fields

| Field | Required | Notes |
|---|---|---|
| `schema_version` | Yes | "1.0" today. Loader rejects schema versions it does not recognize. |
| `id` | Yes | Globally unique. Built-ins use `ely.builtin.*`. User presets use `user.<machine_id>.<uuid>`. |
| `name` | Yes | Display name |
| `engine` | Yes | One of `round_stamp` / `airbrush` / `bristle` / `texture` / `pattern` / `wet_mix` / a registered custom engine id |
| `params` | Yes | Engine-specific parameter values (see [Engines reference](engines-reference.md)) |
| `dynamics` | No | Per-parameter input channel + curve |
| `tags` | No | Free-form list of strings; used by Library filter |
| `color` | No | Default color (CSS hex `#rrggbbaa`) |
| `thumbnail` | No | Base64 PNG (typically 96 x 96); auto-generated if missing |
| `texture` | No | Embedded texture image for Texture/Pattern engines |
| `notes` | No | Free-form user notes |
| `source` | No | Provenance: `{ "kind": "abr", "file": "name.abr" }` for imported brushes |

## `dynamics` shape

```json
"dynamics": {
  "size_px": {
    "channel": "pressure",       // pressure | tilt | rotation | velocity | altitude | distance | random
    "curve": [[0.0, 0.1], [0.5, 0.5], [1.0, 1.0]]
  }
}
```

- `channel` is one of the seven dynamics input channels.
- `curve` is a list of `[input, multiplier]` pairs, monotonic on
  `input`, evaluated by linear interpolation.

## `texture` shape

```json
"texture": {
  "embed": true,
  "data": "data:image/png;base64,iVBORw0KGgo...",
  "scale": 1.0,
  "rotation_deg": 0,
  "offset_x": 0,
  "offset_y": 0
}
```

`embed: false` stores `data: "textures/foliage_stamp.png"` instead
of base64, resolved relative to the `.elybrush` file's parent
directory. Useful when sharing a folder of brushes together rather
than as individual files.

## Versioning

Schema versions are major-numbered. The 1.x line is forward-
compatible: a `.elybrush` saved with a newer Designer that adds
fields will load in an older Designer (the new fields are
ignored). A `2.0` schema would be a breaking change with a
migration tool.

## Validation

The Designer validates every `.elybrush` on load:

- Engine id must exist (built-in or registered Python engine).
- Parameter names must be valid for that engine.
- Curves must be monotonic on x.
- Embedded textures must be valid PNG / JPG / WebP.

Validation failures are surfaced as a Library entry with a warning
icon and a one-line explanation; the preset is still loadable but
flagged as suspect.

## Tooling

A small CLI ships with the framework:

```sh
elybrush inspect mybrush.elybrush      # prints a summary
elybrush diff a.elybrush b.elybrush    # field-level diff
elybrush minify mybrush.elybrush       # strip thumbnails, compact JSON
elybrush extract mybrush.elybrush      # write the embedded texture to a .png
```

Useful for inspecting third-party brush packs or pruning size from
brushes destined for a shared distribution.

## On disk

The user library at `<user_dir>/brushes/user/` holds one
`.elybrush` per preset. The built-in library at
`<install>/python/elysium/brush/builtin/` is read-only; copy a
built-in into the user folder via the Library's right-click menu
to derive from it.
