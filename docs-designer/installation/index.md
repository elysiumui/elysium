# Install the Elysium Designer

The Designer ships as a signed standalone executable for macOS,
Windows, and Linux. There is no Python install required to run it;
the app bundles its own interpreter and native dependencies.

## Pick your platform

| Platform | Format | Page |
|---|---|---|
| macOS 13+ (Apple Silicon or Intel) | Signed and notarized `.app` inside a `.dmg` | [macOS install](macos.md) |
| Windows 10/11 (x64) | Signed `.exe` installer (Inno Setup) | [Windows install](windows.md) |
| Linux (most modern distros, x86_64) | AppImage primary; `.deb`, `.rpm`, tarball alternates | [Linux install](linux.md) |

## After installing

Once the app launches successfully:

- Walk through [first run](first-run.md) for theme selection,
  permissions, and the initial project location.
- If something looks off (no GPU, missing fonts), the
  [troubleshooting page](../troubleshooting/index.md) has the most
  common fixes.

## Other paths

- [Build from source](build-from-source.md): for contributors and
  anyone who wants to run the Designer from a checkout.
- [Uninstall and reset](uninstall-and-reset.md): wipe preferences,
  caches, and bundled Python state cleanly.

## What you get

| Component | Bundled | Purpose |
|---|---|---|
| Designer GUI | Yes | The authoring app itself |
| Python 3.12 interpreter | Yes | Runs the Designer's Python modules |
| Elysium framework | Yes | Same package as `pip install elysium-ui`, version-pinned |
| Aether agent | Yes | Headless AI agent with ~123 tools, driven over the bridge on `127.0.0.1:8183` |
| Native renderer (Skia + wgpu) | Yes | GPU-accelerated canvas |
| Brush engine packs | Yes | 6 engines, 30 presets |
| Example assets | Yes | `examples/butterfly/` and friends |
| AI provider keys | No | Configure in `Preferences > AI` (Anthropic, OpenAI, or local Ollama) |

The Designer does not need network access to launch or to run the
butterfly tutorial. AI workflows (Generate Skin, Magic Polish, Aether
chat) need either an API key or a running local Ollama.

## Hardware notes

| Capability | Minimum | Recommended |
|---|---|---|
| RAM | 4 GB | 16 GB |
| Disk | 1.5 GB free | 5 GB free |
| GPU | Anything with modern OpenGL or Metal or DX12 | Discrete GPU or Apple Silicon |
| Display | 1280x800 | 1920x1080+ |
| Input | Mouse + keyboard | Pen tablet (Wacom, Huion, Apple Pencil) for sculpting and painting |

The Designer falls back to a CPU rasterizer if no compatible GPU is
found, but Render Final at 256 spp is significantly slower in that
mode. See [Render and GPU troubleshooting](../troubleshooting/render-and-gpu.md).
