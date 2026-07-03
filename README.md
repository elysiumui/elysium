# Elysium UI

> Python UI without the rectangles.

**Status: 1.0 — production / stable.** The public API follows strict
[semver](docs/guides/api-stability.md); see the [CHANGELOG](CHANGELOG.md).

A GPU-accelerated framework for borderless, shaped, animated Python
desktop applications. Skia + wgpu hybrid rendering, designer-and-
developer split via `.esk` skin files, animation as a first-class
citizen, and a dedicated authoring app (Elysium Designer).

It targets Qt/PySide6 parity for desktop UI while deliberately staying
focused on the UI layer — see the [scope statement](docs/resources/scope-and-batteries.md)
for what's in and what's left to the Python ecosystem.

## Documentation

- **Framework**: [docs.elysiumui.com](https://docs.elysiumui.com) (the
  `elysium` Python package)
- **Designer**: [designer.elysiumui.com](https://designer.elysiumui.com)
  (the `.esk` authoring app)

Both sites build from this repo: `docs/` and `docs-designer/`.

## Quick start

```bash
pip install elysium-ui
```

Run the minimum borderless ellipse window:

```python
import elysium as ely

ELLIPSE = "M 0,180 A 180,180 0 1 0 360,180 A 180,180 0 1 0 0,180 Z"

app = ely.App(title="Hello", identifier="dev.example.hello")
window = app.window(transparent=True, title_bar=False,
                    resizable=False, initial_size=(360, 360))
window.set_hit_test_path(ELLIPSE)
app.run()
```

A 360 by 360 transparent ellipse window appears with no chrome,
clipping clicks to the ellipse.

## Four lead demos

The Getting Started tutorials walk through four flagship apps:

| Demo | Time | What you build |
|---|---|---|
| [Aurora Clock](https://docs.elysiumui.com/getting-started/aurora-clock-01-window/) | 30 min | Borderless transparent ellipse clock with breathing aurora glow |
| [Pomodoro Timer](https://docs.elysiumui.com/getting-started/pomodoro-01-shape-and-modes/) | 25 min | Rounded-rect Pomodoro with radial progress + popover settings |
| [Stylized Music Player](https://docs.elysiumui.com/getting-started/stylized-music-01-the-faceplate/) | 90 min | Late-1990s-style irregular faceplate music player skin |
| [Butterfly Banner](https://docs.elysiumui.com/getting-started/butterfly-banner-01-load-the-skin/) | 20 min | The Elysium logo: a butterfly descends and unfurls the wordmark |

Together they exercise the entire public API: `App`, `Window`,
shaped windows, skins, signals, effects, Tweens, Springs,
Timelines, themes, components, brush, PBR, AI, marketplace.

## The Designer

The companion authoring app ships as a signed standalone executable
per OS:

- macOS: `Elysium Designer.app`
- Windows: `ElysiumDesigner.exe`
- Linux: `Elysium-Designer.AppImage`

Download from [releases](https://github.com/elysiumui/elysium/releases),
or build from source (see
[the build-from-source guide](https://designer.elysiumui.com/installation/build-from-source/)).

The Designer's lead tutorial is the
[Blue Morpho to Monarch butterfly](https://designer.elysiumui.com/getting-started/butterfly/)
texture-transfer workflow, which produces the same `.esk` the
Butterfly Banner framework demo loads.

## Architecture

| Layer | Crate / Package |
|---|---|
| Pure-Rust primitives (geometry, display list, color, time) | [`ely-core`](elysium-native/crates/ely-core) |
| Windowing + input + a11y (winit) | [`ely-platform`](elysium-native/crates/ely-platform) |
| Skia paint + wgpu compositor + WGSL effects | [`ely-render`](elysium-native/crates/ely-render) |
| `.esk` parser + naga shader sandbox + Ed25519 signatures | [`ely-skin`](elysium-native/crates/ely-skin) |
| Hot-reload IPC | [`ely-ipc`](elysium-native/crates/ely-ipc) |
| PyO3 bindings (the `_native` module) | [`ely-py`](elysium-native/crates/ely-py) |
| Pure-Python framework | [`python/elysium/`](python/elysium) |
| Standalone visual designer | [`elysium-designer/`](elysium-designer) |

## Build from source

```bash
# Native + Python in one command:
maturin develop --release

# Rust workspace tests:
cd elysium-native && cargo test --workspace

# Python suite:
pytest python/elysium/

# Live-window end-to-end test (gated on a display):
ELYSIUM_RUN_WINDOW_TEST=1 pytest tests/test_smoke.py::test_phase0_live_window_end_to_end
```

Contributors: see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[contributing guide on the docs site](https://docs.elysiumui.com/resources/contributing/).

### Where the artifacts land

| What           | Where                                    | For                                                                 |
| -------------- | ---------------------------------------- | ------------------------------------------------------------------- |
| Framework      | `elysium-native/target/wheels/`          | `pip install` consumers (developers building apps with the library) |
| Designer (Mac) | `dist/macos/ElysiumDesigner.app`         | End-users on macOS                                                  |
| Designer (Win) | `dist/windows/ElysiumDesigner.exe`       | End-users on Windows                                                |

The framework directory holds the `pip`-installable wheel +
universal sdist produced by `maturin build --release --sdist`. The
Designer directories hold the single-file PyInstaller bundles
produced by `scripts/build-designer.sh` (or `.ps1` on Windows) — no
Python install required to run, since each bundle ships its own
interpreter and the compiled native extension.

Cross-platform wheels + Designer binaries also come out of CI:
trigger `release-library.yml` for wheels (Win/Mac arm64+x86_64/Linux),
or `build-binaries.yml` for the Designer matrix.

## Examples

| Folder | Purpose |
|---|---|
| [`examples/hello/`](examples/hello) | Minimum-viable app; smoke test |
| [`examples/butterfly/`](examples/butterfly) | Blue Morpho reference + Monarch model used by both lead tutorials |
| [`examples/components/`](examples/components) | Single-window showcase of every built-in component |
| [`examples/agent-cursor/`](examples/agent-cursor) | Aether-driven borderless cursor companion |
| [`examples/snapshot-relay/`](examples/snapshot-relay) | Headless `/snapshot` HTTP relay for tests |

## License

Permissive. See [LICENSE](LICENSE).

## Links

- [docs.elysiumui.com](https://docs.elysiumui.com) (framework)
- [designer.elysiumui.com](https://designer.elysiumui.com) (Designer)
- [GitHub Releases](https://github.com/elysiumui/elysium/releases)
- [PyPI](https://pypi.org/project/elysium)
- [Issues](https://github.com/elysiumui/elysium/issues)
- [Discussions](https://github.com/elysiumui/elysium/discussions)
