# Changelog

Per-version release notes. The authoritative source is
[`CHANGELOG.md`](https://github.com/elysiumui/elysium/blob/main/CHANGELOG.md)
at the repo root; this page mirrors it for searchability.

From **1.0.0**, Elysium follows strict semver — see the
[API stability policy](../guides/api-stability.md):

- **Major** bumps signal breaking changes to the public API or
  `.esk` schema_version (only after a deprecation window).
- **Minor** bumps add features or new components without breaking
  existing code.
- **Patch** bumps fix bugs and ship polish.

## v1.0.0

First stable release — strict-semver public API. Consolidates the Qt-parity
work (Tiers 1–3): robust text input + IME + clipboard, standard dialogs,
Model/View, data-entry widgets, dirty-rect compositing + virtualization, a
scroll system, threading→UI marshalling, multi-window depth, native OS
integration, i18n/RTL/locale, a settings API, and a UI-test harness — plus the
API-stability policy, deprecation mechanism, and an explicit
[scope statement](scope-and-batteries.md). Full notes in the root
`CHANGELOG.md`.

## v0.1.0 (development)

Initial public release. Includes:

- Native wgpu + Skia compositor.
- `App` / `Window` / `Skin` / `Canvas` / `DisplayList` core.
- 30 built-in components.
- Five themes (Light, Dark, OLED, Midnight Glass, Frost).
- Animation primitives (Tween, Timeline, StateMachine, Spring,
  AnimationClock).
- Reactive (signal, computed, effect).
- Borderless / shaped windows with `set_hit_test_path`.
- Brush system (6 engines, 30 presets, `.abr` + `.sut` import).
- PBR materials + path tracer.
- Aether agent with 123 tools.
- Code Link (Designer ↔ editor bridge).
- Hot reload via IPC server.
- `elysium dev` / `doctor` / `aether` / `pack` / `new` CLI.
- Designer ships alongside as a separate signed installer.

### Unreleased (development tip)

- **Skin kinds.** Manifests now declare `"kind": "application"`
  (default) or `"kind": "component"`. Component skins are reusable
  sub-pieces stamped into another window's DisplayList; they have
  no chrome of their own. `Window.load_skin(path)` raises if you
  try to load a component as a window's top-level content. See
  [Skins → Skin kinds](../guides/skins.md#skin-kinds-application-vs-component).
- **Designer Kind dropdown.** Properties → App Window now exposes a
  Kind dropdown that toggles Application ↔ Component, writes the
  choice back to `manifest.json`, and reconfigures the canvas
  chrome to match.
- **Designer File menu cleanup.** "Close Window" renamed to
  "Exit Designer"; new "Close Skin" item below "Save As…" unloads
  the current bundle without exiting the Designer (switches to a
  per-user `~/.elysium/untitled.esk` scratch bundle so a stray
  Save can't clobber the bundle you just closed).
- **Designer reads `.esk` bundles authored outside it.** File →
  Open Skin now imports nodes from `document.json` when no
  `designer_layout.json` is present, preserving semantic IDs and
  centring placements on the App Window.
- **Pomodoro reference app polished:** 15%-smaller chassis, real
  tomato photo with clam-open animation, working countdown +
  audible ding, drag-anywhere window, hover-reveal × close button.
  Leaf-cluster stem moved to its own `stem.esk` component skin
  (see `examples/pomodoro/`).

## Roadmap

See [Roadmap](roadmap.md) for what's planned next.

## Subscribing to releases

- GitHub watch the [releases tab](https://github.com/elysiumui/elysium/releases).
- The Sparkle appcast at `https://elysiumui.com/appcast.xml` powers
  in-app auto-update for packaged apps.
- The PyPI listing at `pypi.org/project/elysium` is the
  authoritative source of wheel releases.

## Migration

When a breaking change ships, an entry in this changelog links to
a per-version migration note. Major-version bumps are rare and
always come with such a note.

## See also

- [Roadmap](roadmap.md)
- [Contributing](contributing.md)
