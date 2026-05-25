# First run

Time: 4 minutes.

The first time you launch the Designer, a brief setup wizard walks
you through four screens. You can revisit every choice later in
`Preferences`.

## 1. Pick a theme

The wizard previews the five built-in themes side by side:

| Theme | Vibe | Best for |
|---|---|---|
| Light | Clean white surfaces | Daytime work, screenshots |
| Dark | Charcoal surfaces, soft accents | Evening work, low ambient light |
| OLED | Pure black background | OLED displays, max contrast |
| Midnight Glass | Blurred dark glass with violet glow | Live demos, presentations |
| Frost | Cool white frosted glass | Long sessions, gentle on eyes |

Click any preview to apply. The wizard switches the live UI to that
theme so you can see the effect on tab labels, the canvas grid, and
the Channel Box. You can also toggle dark mode later via
`View > Toggle Theme` or with `Cmd+Shift+T` / `Ctrl+Shift+T`.

## 2. Grant input permissions

The wizard requests pen and touch input. The flow differs by OS:

### macOS

The Designer asks for Accessibility permission so it can read pen
pressure from Wacom tablets and the Apple Pencil. macOS opens
**System Settings > Privacy & Security > Accessibility** with the
app pre-listed; tick the box, then return to the wizard.

If you do not have a tablet, click **Skip** instead.

### Windows

Windows exposes pen and touch through the Windows.Devices.Input API
which the Designer reads without an explicit prompt. The wizard
shows a "ready" tick once it detects the system has Windows Ink
enabled. If you see "not detected", open
**Settings > Bluetooth & devices > Pen & Windows Ink** and ensure
**Use your fingertip as input** is on (if you have a touchscreen).

### Linux

X11 and Wayland both expose tablet input via `libinput`. The Designer
verifies the kernel modules `wacom`, `evdev`, and `hid_uclogic` (for
non-Wacom tablets) are loaded. If you see a warning, install your
distro's tablet driver package (`xserver-xorg-input-wacom` on
Debian-family, `xf86-input-wacom` on Arch) and re-run.

## 3. Choose a default project location

The Designer asks where to put new projects. The default is
`~/Documents/Elysium Projects/`. You can change it now or later in
`Preferences > Projects`.

The Designer never writes outside this folder unless you explicitly
choose `File > Save As` to somewhere else.

## 4. Connect AI providers (optional)

The Designer's AI workflows (Generate Skin, Magic Polish, Aether
chat) need a model provider. The wizard shows four options:

| Provider | Setup | Notes |
|---|---|---|
| Anthropic | Paste an API key | Recommended for highest quality. Pay-per-use. |
| OpenAI | Paste an API key | Solid quality. Pay-per-use. |
| Ollama (local) | Pick a host (default `http://localhost:11434`) | Free, runs entirely on your machine. Slower. |
| Skip | Click Skip | All non-AI features still work; AI menus are greyed out until you configure a provider. |

Choose Skip if you only want to follow the Blue Morpho butterfly
tutorial, which does not require any AI features.

## Done

The wizard closes and the main Designer window comes up with the
Project Explorer empty. You are ready to:

- Walk through the [Blue Morpho butterfly tutorial](../getting-started/butterfly/index.md).
- Or click `File > New` and start a fresh project.

## Where the settings live

| File | Location |
|---|---|
| Preferences | `~/Library/Application Support/Elysium Designer/preferences.json` (macOS) |
| | `%AppData%\Elysium Designer\preferences.json` (Windows) |
| | `~/.config/elysium-designer/preferences.json` (Linux) |
| Recent projects | same folder, `recent_projects.json` |
| AI provider keys | OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service) |

Delete or edit these to revert any first-run choice. The
[Uninstall and reset](uninstall-and-reset.md) page covers a full
wipe.
