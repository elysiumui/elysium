# Frequently asked questions

## Licensing

**What license is Elysium under?**

Permissive open source. See [Contributing](contributing.md) for the
full text; the short version is "use it, ship it, no royalties".

**Can I use Elysium in a commercial closed-source app?**

Yes.

**Do I need to credit Elysium?**

The license requires a copy of the copyright notice in source
distributions. No runtime attribution required (no "Powered by
Elysium" splash needed in your app).

## Python versions

**Which Python versions does Elysium support?**

CPython 3.10, 3.11, 3.12, 3.13. We follow CPython's own support
window (drop versions 12-18 months after CPython does).

**PyPy?**

Not currently. PyPy works in theory but the native extension uses
CPython-specific APIs.

**Will it work in a virtual environment?**

Yes; `python -m venv` then `pip install elysium-ui` is the recommended
install path.

## Platforms

**Which platforms?**

macOS 13+ (Apple Silicon + Intel), Windows 10/11 (x64), Linux
glibc 2.31+ (x86_64).

**ARM Linux?**

aarch64 Linux is roadmap, not v1.

**Mobile?**

No. Elysium is desktop-only in v1.

**Web?**

No. The framework is native.

## Performance

**What's the typical frame time?**

2-4 ms on a baseline GPU at 1080p, well under the 16.67 ms/60 fps
budget. Discrete GPUs are roughly half that.

**Does it run on a GPU-less server?**

Yes; the wgpu compositor falls back to a software rasterizer.
Headless renders use the CPU path tracer in `elysium.render.pbr`.

**How much memory does the framework use?**

~30 MB resident base + ~10 MB per loaded skin.

## Packaging

**How do I ship my app?**

`elysium pack` builds a signed standalone bundle per OS:
`.app` on macOS, `.exe` + installer on Windows, AppImage on Linux.
See [Packaging](../guides/packaging.md).

**How big is the bundle?**

~80 MB on macOS, ~110 MB on Windows, ~95 MB on Linux. Skia + wgpu
+ Bullet + brush + PBR shaders together.

**Do I need to bundle Python with the app?**

`elysium pack` bundles Python for you. End users do not install
Python.

## AI features

**Is Elysium AI-dependent?**

No. AI workflows are opt-in. Set `ANTHROPIC_API_KEY` (or another
provider) to enable, leave unset to use the offline `stub`
provider.

**Where do my API keys go?**

The OS keychain (Keychain Access on macOS, Credential Manager on
Windows, Secret Service on Linux). Never written to plain config
files.

**Do you send my code to the AI?**

No. AI workflows read your skin's manifest and document; never
your application Python code.

## Skins and Designer

**Do I need the Designer to use Elysium?**

No. You can hand-edit `.esk` JSON. The Designer is convenient,
not required.

**Can I author a skin in code instead of a `.esk` folder?**

Yes; build placements at runtime via `window.add_placement(...)`.
The `.esk` is the source of truth for static layouts; code is fine
for dynamic layouts.

## GPU fallback

**My GPU isn't supported. What happens?**

The framework falls back to a CPU software rasterizer. Live UI
remains usable at the cost of higher CPU. Production renders use
the CPU path tracer in `elysium.render.pbr`.

**Vulkan / Metal / DX12: which does it use?**

wgpu picks the best available: Metal on macOS, DX12 on Windows,
Vulkan on Linux. Falls back to OpenGL where Vulkan / DX12 are not
available.

## Support

**Where do I file bugs?**

GitHub Issues at [github.com/elysiumui/elysium](https://github.com/elysiumui/elysium).

**Is there a Discord?**

Yes. Link in the repo README.

## See also

- [Which Python GUI?](which-python-gui.md)
- [Contributing](contributing.md)
- [Changelog](changelog.md)
