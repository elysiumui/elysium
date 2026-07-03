# Install on Linux

Time: 5 minutes.

## Requirements

- A recent x86_64 Linux desktop. Tested on Ubuntu 22.04+, Fedora 39+,
  Debian 12+, and Arch (rolling).
- glibc 2.31 or newer.
- A working GPU stack (Mesa 22+, NVIDIA proprietary 525+, or AMDGPU
  recent). Vulkan and OpenGL 4.5 both work.
- 1.5 GB free disk.

aarch64 (Linux ARM) is on the roadmap; not in v1.

## Recommended: AppImage

The AppImage is the most portable option. It runs on any modern
distro without touching your package manager.

1. Download `Elysium-Designer-<version>-linux-x86_64.AppImage` from
   the [latest release](https://github.com/elysiumui/elysium/releases/latest).
2. Mark it executable:

    ```sh
    chmod +x Elysium-Designer-*.AppImage
    ```

3. Run it:

    ```sh
    ./Elysium-Designer-*.AppImage
    ```

The first run extracts the bundle into `~/.cache/elysium-designer/`
and creates a desktop entry so it shows up in your application
launcher.

### Desktop integration

The AppImage bundles `appimaged`-compatible metadata. If you have
[AppImageLauncher](https://github.com/TheAssassin/AppImageLauncher)
installed, it will offer to integrate the AppImage on first launch.
Otherwise the bundled desktop file is dropped into
`~/.local/share/applications/elysium-designer.desktop` automatically.

## Debian / Ubuntu (.deb)

If you prefer system package management:

```sh
curl -LO https://github.com/elysiumui/elysium/releases/latest/download/elysium-designer_<version>_amd64.deb
sudo apt install ./elysium-designer_<version>_amd64.deb
```

The package installs to `/opt/elysium-designer/` and adds an entry
under Graphics in your application menu.

To remove: `sudo apt remove elysium-designer`.

## Fedora / RHEL (.rpm)

```sh
curl -LO https://github.com/elysiumui/elysium/releases/latest/download/elysium-designer-<version>-1.x86_64.rpm
sudo dnf install ./elysium-designer-<version>-1.x86_64.rpm
```

To remove: `sudo dnf remove elysium-designer`.

## Arch (AUR)

A community-maintained AUR package is available:

```sh
yay -S elysium-designer-bin
```

This pulls the AppImage and wires it into the system.

## Tarball

If none of the above fit, the raw tarball at
`Elysium-Designer-<version>-linux-x86_64.tar.gz` extracts to a
self-contained directory:

```sh
tar -xzf Elysium-Designer-<version>-linux-x86_64.tar.gz
cd Elysium-Designer-<version>/
./ElysiumDesigner
```

This is the same set of files the AppImage wraps.

## System dependencies

The AppImage and tarball bundle every native dependency, but the
`.deb` and `.rpm` packages declare runtime dependencies on:

- `libgl1` (or distro equivalent): OpenGL fallback path.
- `libxkbcommon0`, `libxcb-*`: windowing.
- `fonts-noto-color-emoji`: fallback emoji rendering in the UI.

Your package manager pulls these automatically.

## First launch

The Designer opens to its splash screen, then the main window.
Follow the [first run guide](first-run.md).

## Wayland vs X11

Both work. Wayland is the default on most modern distros, but the
Designer falls back to XWayland for a few features (global
shortcuts, screen capture) that the Wayland protocol does not yet
expose portably. If you hit a "cannot capture region" error, see
[render and GPU troubleshooting](../troubleshooting/render-and-gpu.md).

## Updating

`Help > Check for Updates` checks for new releases. The AppImage
update happens via `appimageupdate` if available (zsync sidecar),
otherwise it falls back to a full re-download. Package-manager
installs (`.deb`, `.rpm`, AUR) update through the usual system
channel.

## Uninstall

- AppImage: delete the file plus `~/.cache/elysium-designer/` and
  `~/.local/share/applications/elysium-designer.desktop`.
- `.deb` / `.rpm`: use the package manager (above).
- Tarball: delete the extracted directory.

To also clear preferences see [Uninstall and reset](uninstall-and-reset.md).
