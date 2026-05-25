# Single-file builds (Designer + examples)

`scripts/build.py` produces one self-contained binary per app per OS. No
installer, no folder tree — just one file you can hand to someone.

## Quick start

Install the build extras once per machine:

```bash
pip install -e ".[build]"
```

That gives you `pyinstaller` + `maturin`. The build scripts compile the
Rust extension themselves on every run (`cargo` is incremental, so it
takes a few seconds when nothing changed). No separate `maturin develop`
step is required.

Then on each OS run the wrapper for what you want:

| OS | Designer | One example | Every example |
|---|---|---|---|
| macOS / Linux | `scripts/build-designer.sh` | `scripts/build-example.sh butterfly` | `scripts/build-example.sh --all` |
| Windows (PowerShell) | `scripts\build-designer.ps1` | `scripts\build-example.ps1 butterfly` | `scripts\build-example.ps1 -All` |

The driver underneath:

```bash
python scripts/build.py --list                    # discover targets
python scripts/build.py designer                  # build the Designer
python scripts/build.py example butterfly         # build one example
python scripts/build.py designer --clean --debug  # full rebuild + console
python scripts/build.py designer --skip-native    # reuse last .so/.pyd
python scripts/build.py designer --native-debug   # debug Rust (faster compile)
```

## Output

```
dist/
  macos/    ElysiumDesigner            Elysium-Butterfly
  windows/  ElysiumDesigner.exe        Elysium-Butterfly.exe
  linux/    ElysiumDesigner            Elysium-Butterfly
```

Per-binary first launch is ~2-4 s on a warm cache (the `--onefile` boot-
loader self-extracts into a temp dir). Subsequent launches reuse the cache
and start ~instantly.

## Why three OSes need three machines

PyInstaller is *not* a cross-compiler. A Windows `.exe` must be produced
on Windows, a `.dylib`-linked macOS binary must come from a Mac, and the
Linux binary must come from Linux because each links to OS-specific
graphics, font, and input libraries.

The supported ways to cover all three:

1. **CI** — `.github/workflows/build-binaries.yml` runs the matrix on
   `macos-latest`, `windows-latest`, `ubuntu-latest` in parallel and
   uploads the artifacts. Trigger it manually from the Actions tab or
   push a `vX.Y.Z` tag to also draft a Release with the binaries attached.
2. **Local machines** — run the matching wrapper on each OS you own.
3. **Docker for Linux** — `docker run --rm -v $PWD:/src -w /src python:3.12
   bash -lc 'pip install -e ".[build]" && maturin develop --release ... &&
   scripts/build-designer.sh'` (only Linux works this way; macOS and
   Windows containers are not portable).

## Adding a new example

No script edits needed. Drop the new folder under `examples/`, give it a
`main.py` (or `__main__.py` / `<folder>.py`), and the build driver
discovers it on its next `--list`. Every sibling file in the example
folder (skins, textures, `.3ds`, `.blend`) is bundled automatically.

To add it to CI builds, append `example:<folder-name>` to the matrix in
`.github/workflows/build-binaries.yml`.

## Common gotchas

- **"No module named elysium._native._native"** after the build's
  maturin step → the venv Python and the maturin Python disagree.
  Confirm `which python` matches `which maturin` (or `where` on
  Windows), or re-create the venv.
- **Rust compile is slow on a fresh machine** → first `cargo build`
  on a clean target dir compiles every dep from scratch (~3-5 min).
  Subsequent builds reuse `elysium-native/target/` and finish in
  seconds. `--skip-native` skips even the cargo check when you know
  the `.so/.pyd` is fresh.
- **Want faster Rust iteration during a debug cycle** → pass
  `--native-debug` to skip the release optimisation pass (~5×
  faster Rust compile, ~2× slower Python-side call latency).
- **Linux build runs locally but the binary segfaults on a different
  distro** → glibc version skew. Build inside the oldest distro you
  want to support (the CI uses `ubuntu-latest` which targets glibc
  2.31+; for broader compat build inside `quay.io/pypa/manylinux2014`).
- **macOS binary won't open on another Mac ("damaged")** → unsigned
  binaries get quarantined. Either right-click → Open the first time,
  or run `xattr -d com.apple.quarantine ElysiumDesigner` after the
  download. For real distribution, sign with an Apple Developer ID
  (`codesign --deep --sign "Developer ID Application: ..." ./ElysiumDesigner`).
- **Windows SmartScreen warns "Unknown publisher"** → expected for
  unsigned binaries. Authenticode-sign with `signtool` for a clean
  install experience.

## Versus the existing directory build

`scripts/build-designer.spec` (already in the repo) produces a *folder*
of binaries + data — the format CI uses to wrap into AppImage / `.deb`
/ `.rpm` / `.app` artifacts. It is not the single-file build. Keep it
for full distribution; use `build.py` when you want one portable file.
