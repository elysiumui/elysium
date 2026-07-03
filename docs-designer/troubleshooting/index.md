# Troubleshooting and FAQ

Common Designer issues with one-step fixes.

## Designer will not launch

| Symptom | Try |
|---|---|
| Bounces in the Dock then quits (macOS) | Open Console.app; search for "Elysium" to see the crash log. Most often a Gatekeeper or notarization issue: re-download the `.dmg`. |
| SmartScreen blocks launch (Windows) | Click "More info" → "Run anyway". After enough downloads the warning stops. |
| `error while loading shared libraries` (Linux) | Install the missing dep listed in the message; verify `glibc` ≥ 2.31. |

## GPU / render issues

See [Render and GPU](render-and-gpu.md).

| Symptom | Try |
|---|---|
| View Panel flickers black / white | Switch backend with `ELYSIUM_GPU_BACKEND=metal/dx12/vulkan/gl/cpu` |
| Brush strokes lag | Lower brush smoothing; check `Help > Tablet Diagnostics` |
| Render Final takes forever | Confirm GPU not falling back to CPU; verify `elysium doctor` |

## Aether / bridge issues

See [Aether and bridge](aether-and-bridge.md).

| Symptom | Try |
|---|---|
| "No AI provider configured" | Set `ANTHROPIC_API_KEY` (or use Ollama locally) |
| Aether chat unresponsive | Check `~/.elysium/sessions/elysium-default.sock` permissions |
| Tool call rejected | Check the safety policy in `Preferences > AI > Safety` |

## Skin loading issues

| Symptom | Try |
|---|---|
| "schema_version not supported" | Re-export from a newer Designer, or hand-edit the manifest |
| Black canvas after load | Verify the skin's `manifest.json` `window.shape.path_d` is valid SVG |
| Hooks not firing | Verify the placement id matches your `@window.on("<id>.click")` |

## Tablet not detected

See [Touch and pen input](../reference/touch-and-pen-input.md).

- macOS: System Settings > Privacy & Security > Accessibility (the
  Designer needs this for pressure).
- Windows: Settings > Bluetooth & devices > Pen & Windows Ink.
- Linux: install the driver package (`xserver-xorg-input-wacom`).

## File system / permission issues

| Symptom | Try |
|---|---|
| "Permission denied" on save | `Preferences > Projects > Default Project Location` outside a system-protected folder |
| Asset path not found in `.esk` | Use paths relative to the `.esk` folder, not absolute |
| Recents list empty after relaunch | Verify the preferences file at the path in [File locations](../reference/file-locations.md) |

## Performance

| Symptom | Try |
|---|---|
| Long startup | `elysium doctor`; check for slow shaders being compiled |
| High memory after long session | `View > Flatten Brush History` to drop per-stroke undo |
| FPS drops on heavy scenes | Check the HUD; lower render quality preset during authoring |

## Filing a bug

If none of the above fits, file an issue at
[github.com/elysiumui/elysium/issues](https://github.com/elysiumui/elysium/issues)
with:

- The output of `elysium doctor`.
- Designer version (`Help > About`).
- OS + Python + GPU info.
- A minimum reproducer if possible.

## See also

- [Render and GPU](render-and-gpu.md)
- [Aether and bridge](aether-and-bridge.md)
- [Uninstall and reset](../installation/uninstall-and-reset.md)
