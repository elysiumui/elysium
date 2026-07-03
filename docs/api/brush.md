# `elysium.brush`

The brush authoring + painting Python API. The Designer's brush
GUI sits on top of this.

## Engine framework

| Symbol | Purpose |
|---|---|
| `BrushEngine` | Base class for engines |
| `ParamSpec(name, min, max, default, ...)` | Declares one engine parameter |
| `register_engine(engine)` | Register a new engine globally |
| `get_engine(id)` | Look up an engine by id |
| `list_engines()` | List every registered engine |
| `apply_dynamics(params, dynamics, sample)` | Apply pressure / tilt / etc. to params |

## Built-in engines

| Id | Class |
|---|---|
| `round_stamp` | RoundStampEngine |
| `airbrush` | AirbrushEngine |
| `bristle` | BristleEngine |
| `texture` | TextureEngine |
| `pattern` | PatternEngine |
| `wet_mix` | WetMixEngine |

## Presets

| Symbol | Purpose |
|---|---|
| `Preset` | Dataclass of engine + params + dynamics + metadata |
| `load_preset(path)` | Load a `.elybrush` file |
| `save_preset(preset, path=None)` | Save to user library |

## Library

| Symbol | Purpose |
|---|---|
| `Library` | The in-memory preset library |
| `library()` | Get the active Library |
| `user_brushes_dir()` | Path to user brushes |
| `builtin_brushes_dir()` | Path to bundled brushes |
| `ensure_user_dir_seeded()` | Create user dir with starter brushes |
| `reload_with_skin(path)` | Refresh library when active skin changes |

## Importers

| Function | Purpose |
|---|---|
| `import_abr(path)` | Photoshop `.abr` → list of Preset |
| `import_sut(path)` | Clip Studio `.sut` → list of Preset |

## Auto-rendered details

::: elysium.brush

## See also

- [Brush](../guides/brush.md)
- [Designer > Brush system](https://designer.elysiumui.com/brush/)
