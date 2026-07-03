# Install on macOS

Time: 3 minutes.

## Requirements

- macOS 13 Ventura or later.
- Apple Silicon (M1, M2, M3, M4) **or** Intel x86_64.
- 1.5 GB free disk for the app and its caches.

## Download

Go to the [latest release](https://github.com/elysiumui/elysium/releases/latest)
on GitHub and pick the asset that matches your CPU:

| File | Architecture |
|---|---|
| `Elysium-Designer-<version>-macos-arm64.dmg` | Apple Silicon |
| `Elysium-Designer-<version>-macos-x86_64.dmg` | Intel |

If you are not sure which one to grab, open the Apple menu, choose
**About This Mac**, and read the Chip line. "Apple M1/M2/M3/M4" means
arm64; "Intel" means x86_64.

## Install

1. Double-click the downloaded `.dmg`. Finder mounts it and opens a
   window showing the `Elysium Designer.app` icon next to an
   Applications shortcut.
2. Drag `Elysium Designer.app` onto the Applications shortcut.
3. Eject the disk image (drag it to the Trash, or right-click in
   Finder and choose Eject).

## First launch

Open the app from Launchpad or by double-clicking it in
`/Applications`. On the first launch:

- macOS verifies the developer signature and notarization. This
  takes a few seconds. There should be no Gatekeeper warning,
  because the app is signed with our Developer ID Application
  certificate and notarized through Apple.
- If you do see a "cannot be opened" dialog (typical when downloading
  via a tool that strips the quarantine attribute incorrectly), open
  **System Settings > Privacy & Security**, scroll to the message
  about Elysium Designer, and click **Open Anyway**.

The app's splash screen appears, then the main window opens. Follow
the [first run guide](first-run.md) for the brief setup that comes
next.

## Permissions

The Designer asks for a small set of permissions, each lazily on
first use:

| Permission | Triggered by | Why |
|---|---|---|
| Files and Folders (chosen folder) | First save / first project open | Read and write your project on disk |
| Screen Recording | `Window > Capture > Region` | Capture a region of your screen as a reference image |
| Camera | `Window > Capture > Webcam` (optional, not used by the tutorial) | Pull a frame from the camera as a reference image |
| Accessibility | Live preview window dragging | Position the borderless preview window on screen |

You can revoke any of these later in
**System Settings > Privacy & Security**.

## Updating

The Designer checks for updates on launch and once every 24 hours.
When an update is available you see a small badge on the Help menu;
choose `Help > Check for Updates` to install. Updates are delivered
through Sparkle and signed with the same Developer ID.

To turn off update checks, open `Preferences > Updates` and untick
**Check for updates automatically**.

## Uninstall

Drag `Elysium Designer.app` from Applications to the Trash. To also
remove caches and preferences, follow
[Uninstall and reset](uninstall-and-reset.md).
