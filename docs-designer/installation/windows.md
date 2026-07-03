# Install on Windows

Time: 3 minutes.

## Requirements

- Windows 10 (version 1809 or later) or Windows 11.
- x64 CPU.
- 1.5 GB free disk for the app and its caches.
- A GPU that supports DirectX 12 (any GPU from the last 8 years).

ARM64 Windows is not yet supported.

## Download

Go to the [latest release](https://github.com/elysiumui/elysium/releases/latest)
on GitHub and download:

| File | Use |
|---|---|
| `Elysium-Designer-<version>-windows-x64-setup.exe` | Recommended installer |
| `Elysium-Designer-<version>-windows-x64.zip` | Portable, no installer |

## Install

1. Double-click the downloaded `.exe`. The Inno Setup wizard opens.
2. Choose **Install for me only** (per-user, no admin) or **Install
   for all users** (system-wide, requires admin). Per-user is the
   recommended default and works without UAC.
3. Pick the install location. The default is
   `%LocalAppData%\Programs\Elysium Designer` (per-user) or
   `C:\Program Files\Elysium Designer` (all users).
4. Click **Install**. Inno Setup copies the bundle into place,
   creates a Start menu entry, and (optionally) a Desktop shortcut.
5. Tick **Launch Elysium Designer** and click **Finish**.

## SmartScreen

The installer is signed with an Authenticode certificate, but
Microsoft Defender SmartScreen accumulates "reputation" over time.
On the first download you may see:

> Windows protected your PC. Microsoft Defender SmartScreen prevented
> an unrecognized app from starting.

Click **More info**, then click the **Run anyway** button that
appears. This dialog only shows up while the signing certificate is
still new; after a few thousand downloads SmartScreen stops warning
on it automatically.

If your organization blocks SmartScreen "Run anyway" entirely, the
[portable zip](#portable-zip) below sidesteps the installer.

## Portable zip

If you cannot install or do not want to:

1. Download `Elysium-Designer-<version>-windows-x64.zip`.
2. Right-click the file, choose **Properties**, tick **Unblock**, and
   click OK. This removes the Mark of the Web that Windows attaches
   to downloaded files.
3. Extract the zip anywhere you like (a USB drive works).
4. Run `ElysiumDesigner.exe` from the extracted folder.

The portable build is byte-for-byte the same binary as the installed
one; it just skips Inno Setup.

## First launch

The Designer opens to a splash screen, then the main window. Follow
the [first run guide](first-run.md) for the brief setup that comes
next.

## Permissions

The Designer asks Windows for the following on first use:

| Capability | When | Why |
|---|---|---|
| File access (selected folder) | First save / first project open | Read and write your project on disk |
| Camera | `Window > Capture > Webcam` | Pull a frame from the camera as a reference |
| Tablet / pen input | First brush stroke with a pen | Read pressure, tilt, rotation from Wacom or Surface Pen |

Windows handles these inline; there is no separate permissions
manager to visit ahead of time.

## Updating

`Help > Check for Updates` checks the GitHub Releases feed and
installs new versions in-place. The installer signs each update with
the same certificate, so Windows will not re-trigger SmartScreen for
later releases.

Tick or untick **Check for updates automatically** in
`Preferences > Updates`.

## Uninstall

Use **Settings > Apps > Installed apps**, find Elysium Designer,
click the three-dot menu, and choose **Uninstall**. To also clear
caches and preferences, follow [Uninstall and reset](uninstall-and-reset.md).
