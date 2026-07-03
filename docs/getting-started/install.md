# Install

## Requirements
- Python 3.10 or newer
- macOS 11+, Windows 10+, or Linux with Wayland or X11

## Stable
```bash
pip install elysium-ui
```

The wheel includes the prebuilt `_native` extension (Rust + Skia + wgpu) so no toolchain is required for users.

## From source (developer install)
```bash
git clone https://github.com/elysiumui/elysium
cd elysium
python -m venv .venv
source .venv/bin/activate
pip install maturin
maturin develop --release
```

That builds the Rust crates, compiles the abi3 cdylib into `python/elysium/_native/_native.{so,pyd}`, and installs the Python package in editable mode.

## Verify
```python
import elysium as ely
print(ely.__version__)
```
