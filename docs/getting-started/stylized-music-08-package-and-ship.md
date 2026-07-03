# Stylized Music Player 8. Package and ship

Time: 9 minutes.

## What we are adding

Two workflows close out the tutorial: `elysium dev` for live
iteration (edits to the skin or the script hot-reload into a
running window without restarting it) and `elysium pack` for a
signed, distributable bundle per OS.

## Live iteration with `elysium dev`

`elysium dev` runs your script under a file watcher. When you edit
`player.esk/document.json` or `player.py`, the watcher detects the
change and reloads the skin (skin-only edits) or restarts the
process (Python edits).

```sh
elysium dev player.py
```

The output:

```
[elysium dev] watching player.py and player.esk/
[elysium dev] socket: ~/.elysium/sessions/elysium-default.sock
[elysium dev] launched player.py (pid 78122)
```

Open `player.esk/document.json` in your editor, change a fill color,
save: the change appears within ~200 ms in the live window.

Edit the Python file: the watcher kills the running process and
relaunches it. Window position is preserved across restarts.

### What hot-reloads vs what restarts

| Change | Reload type |
|---|---|
| `player.esk/document.json` | Skin reload (in-place) |
| `player.esk/manifest.json` | Skin reload |
| `player.esk/assets/*.png` | Skin reload |
| `player.py` (any change) | Process restart |
| Code under `examples/`, `python/elysium/` if you are running from source | Process restart |

The dividing line is: anything that affects the static skin → in-
place reload. Anything that affects Python behavior → restart, so
the new code path runs from initialization.

### Useful flags

- `--no-restart`: only skin reloads; ignore Python file edits.
- `--ipc-socket=/tmp/mine.sock`: pick a non-default socket path.
- `--log=debug`: verbose tracing of the file watcher.

## Pack a signed bundle

`elysium pack` invokes PyInstaller with sane defaults plus
per-OS code signing. From the directory containing `player.py`:

```sh
elysium pack player.py \
  --name "Stylized Music Player" \
  --identifier dev.elysium.stylized-music \
  --icon ./icon.png \
  --include player.esk
```

The build takes a couple of minutes the first time. The output:

| OS | Output |
|---|---|
| macOS | `dist/Stylized Music Player.app` (signed + notarized if env vars set) |
| Windows | `dist/Stylized Music Player/` plus `Stylized Music Player Setup.exe` |
| Linux | `dist/Stylized-Music-Player.AppImage` (plus `.deb` if dpkg-deb is on PATH) |

Run the produced bundle. The player launches with no terminal
visible, no Python window, and (on Linux) integrates into the
system tray and notification stack.

### Code signing

The framework reads three environment variables:

- `ELYSIUM_SIGNING_IDENTITY`: macOS Developer ID Application string,
  e.g. `"Developer ID Application: Your Name (TEAMID)"`.
- `ELYSIUM_NOTARY_PROFILE`: keychain profile for `notarytool`.
- `ELYSIUM_WINDOWS_CERT`: path to a PFX with a password in
  `ELYSIUM_WINDOWS_CERT_PASSWORD`.

When all three (or the relevant ones for your OS) are set,
`elysium pack` signs and (on macOS) notarizes the resulting bundle
in the same command. Otherwise the bundle is unsigned but still
runnable.

The full signing story is in [Packaging](../guides/packaging.md).

## Distribute

You now have a signed, double-clickable music player skin that ships
without Python preinstalled. Options for distribution:

- **GitHub Releases**: drop the bundles onto a tagged release. Free,
  works on every OS, scales to thousands of users.
- **Auto-update**: wire a Sparkle / appcast feed so the player checks
  for updates on launch. See [Auto-update](../guides/auto-update.md).
- **Elysium Marketplace**: publish the `.esk` (without the wrapper
  bundle) so other framework users can drop it into their own apps.
  See [Marketplace](../guides/marketplace.md).

## What you built

In ~90 minutes:

- A **non-rectangular borderless transparent window** with a hand-
  authored SVG hit region.
- A **gradient-framed album art card** using the glass material.
- **Three spherical buttons** with hover, press, and morph
  animations.
- A **scrubber** with click-and-drag seek and a glowing trail.
- A **GPU-composited equalizer visualizer** at 30 Hz.
- **Refined drag intent** so controls and dead-zones behave
  separately.
- A **custom dark-glass theme** plus an optional `magic_polish` pass.
- A **signed standalone bundle** per OS, with live-reload dev
  workflow.

You exercised: `App`, `Window`, `set_hit_test_path`, `load_skin`,
`Canvas`, `Path`, `DisplayList`, `signal`, `computed`, `effect`,
`Tween`, `Timeline`, `Spring`, `StateMachine` (via Pomodoro
patterns), `Theme`, `hsla`, `MotionPreset`, `set_theme`,
`magic_polish`, plus `elysium dev` and `elysium pack`.

That is the spine of the Framework's public surface for borderless
animated apps.

## Where to next

- [Butterfly Banner](butterfly-banner-01-load-the-skin.md) loads a
  Designer-authored `.esk` of the official Elysium logo and animates
  it onto the screen.
- [Particle Pet tutorial](../tutorials/particle-pet.md) builds a
  floating cursor-following companion using Spring physics.
- [Aurora Clock Pro tutorial](../tutorials/aurora-clock-pro.md)
  evolves the Aurora Clock from chapter 5 into a multi-window
  productivity app.

[Back to Getting Started](index.md)
