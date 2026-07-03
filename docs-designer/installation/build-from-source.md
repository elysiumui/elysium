# Build from source

For contributors and anyone who wants to run the Designer from a
checkout instead of an installed bundle. The end product is the same
signed binary the official releases ship, minus the signing.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12 | The bundle pins this exact minor |
| uv | latest | Replaces pip + venv. Optional but recommended |
| Rust | stable | Builds the native renderer crate |
| Node | 20+ | Only if you touch the embedded webview demos |
| Git | any | To clone |

Per-OS extras:

- **macOS**: Xcode Command Line Tools (`xcode-select --install`).
- **Windows**: Visual Studio 2022 Build Tools with the "Desktop
  development with C++" workload.
- **Linux**: `build-essential`, `pkg-config`, `libfontconfig1-dev`,
  `libxkbcommon-dev`, `libwayland-dev`.

## Clone

```sh
git clone https://github.com/elysiumui/elysium.git
cd elysium
```

## Install dependencies

The project uses uv for fast dependency resolution. With uv:

```sh
uv sync
```

Without uv:

```sh
python3.12 -m venv .venv
source .venv/bin/activate          # or .venv\Scripts\activate on Windows
pip install -e ".[designer,dev]"
```

This installs the framework, the Designer app's pure-Python modules,
the brush engines, and the development tools.

## Build the native renderer

The Skia + wgpu renderer lives in `elysium-native/`. Build it once
per fresh checkout:

```sh
cd elysium-native
cargo build --release
cd ..
```

The build produces `elysium-native/target/release/libelysium_native.{dylib|dll|so}`
which the Python side loads at startup.

## Run from source

```sh
python -m elysium_designer
```

The Designer launches against your local checkout. Hot-edit the
Python files and `Run > Reload Modules` picks them up without a
restart. Code changes in `elysium-native/` need a fresh
`cargo build --release` before they show up.

## Package a standalone binary

To produce the same artifact the official releases ship:

```sh
pyinstaller scripts/build-designer.spec
```

The spec file (`scripts/build-designer.spec`) wires PyInstaller with:

- Hidden imports for every brush engine, Aether tool module, and AI
  provider module.
- Data files for the example assets (`examples/butterfly/`), the
  built-in brushes (`python/elysium/brush/builtin/`), the menu
  definition (`elysium-designer/menus.py`), and the bundled native
  renderer library.
- Per-OS branches: `BUNDLE` on macOS produces `Elysium Designer.app`,
  `EXE` + `COLLECT` on Windows and Linux produce the
  platform-specific executable.

PyInstaller writes the output under `dist/`:

| OS | Output |
|---|---|
| macOS | `dist/Elysium Designer.app` |
| Windows | `dist/ElysiumDesigner/ElysiumDesigner.exe` (with a sibling DLL folder) |
| Linux | `dist/ElysiumDesigner/ElysiumDesigner` (with a sibling lib folder) |

## Sign and notarize (optional)

The signing steps run in CI through
`.github/workflows/release-designer.yml`. To sign locally you need
the platform's certificate:

### macOS

```sh
codesign --deep --force --options runtime \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  "dist/Elysium Designer.app"

xcrun notarytool submit "dist/Elysium Designer.app.zip" \
  --apple-id you@example.com --team-id TEAMID --keychain-profile elysium

xcrun stapler staple "dist/Elysium Designer.app"
```

### Windows

```sh
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 \
  /f cert.pfx /p PASSWORD dist/ElysiumDesigner/ElysiumDesigner.exe
```

### Linux

AppImages are signed with a detached GPG signature alongside the
file:

```sh
gpg --detach-sign --armor dist/Elysium-Designer-x86_64.AppImage
```

## Run the tests

```sh
pytest python/elysium/         # framework tests
pytest elysium-designer/       # designer tests
cargo test --manifest-path elysium-native/Cargo.toml
```

CI runs all three on every PR.

## What CI does differently

The release workflow does three extra things you may want to skip
locally:

1. Builds wheels for the framework on `cibuildwheel` for the full
   PyPI matrix (CPython 3.10 to 3.13 on macOS, Windows, Linux).
2. Runs `cibuildwheel`'s test pass per wheel.
3. Uploads everything (Designer per-OS bundles + framework wheels)
   to a GitHub Release tagged with the version.

Day-to-day contribution rarely needs any of this.
