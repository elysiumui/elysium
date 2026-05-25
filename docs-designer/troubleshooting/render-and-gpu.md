# Render and GPU troubleshooting

Most rendering complaints come from one of: wrong backend, broken
driver, color-management mismatch, or low VRAM.

## Identify the backend

`Help > About > GPU` shows the active wgpu backend:

```
Backend: Metal (Apple M2)
```

The Designer's default backend picker prefers, in order: Metal
(macOS), DX12 (Windows), Vulkan (Linux), then OpenGL, then CPU.

## Force a different backend

```sh
ELYSIUM_GPU_BACKEND=vulkan elysium-designer
```

Values: `metal`, `dx12`, `vulkan`, `gl`, `cpu`.

Useful when:

- The default backend has a driver bug on your machine.
- You want to benchmark.
- You are debugging an OS-specific rendering issue.

## Flicker / corruption

Symptoms: brief black flashes, garbled text, incorrect colors.

Try:

1. Update graphics drivers (NVIDIA / AMD / Intel).
2. Switch backend (force Vulkan on Linux if Wayland's compositor
   is buggy; force DX12 on Windows if Vulkan is misbehaving).
3. Disable HDR on the active display.
4. Lower the active monitor refresh rate temporarily.

## Slow renders

If `Production` or `Final` quality presets take dramatically
longer than the [render quality table](../reference/render-quality-table.md)
predicts:

- Confirm GPU compute path is active (`elysium doctor` shows
  "GPU compute: yes").
- Reduce IBL resolution (`Preferences > Rendering > IBL Resolution`).
- Disable adaptive sampling if your scene has very stable
  variance.

## Color looks wrong

The most common color complaints:

| Symptom | Fix |
|---|---|
| Textures look washed out | Verify their **Input Space** in the Properties pane (should be sRGB for albedos) |
| Iridescence flat / dim | Switch to Textured + Lit (`7`) and add a directional light |
| Output on web looks different than Designer | The Designer's output color space is sRGB by default; verify in `Rendering > Color Space` |

See [Color management](../reference/color-management.md).

## Out of memory

| Symptom | Fix |
|---|---|
| "Texture allocation failed" toast | Lower `Preferences > Rendering > Texture Budget` |
| Crash after long brushing session | `View > Flatten Brush History` |
| Renders fail above 2K resolution | The GPU compute path needs ~`4 * w * h * 4` bytes free VRAM; CPU path tracer takes about half |

## Tablet pressure not registering

See [Touch and pen input](../reference/touch-and-pen-input.md).

Quick checks:

1. `Help > Tablet Diagnostics`: does pressure show?
2. macOS: System Settings > Privacy > Accessibility: is the
   Designer in the list?
3. Windows: latest driver from the tablet vendor's site (not just
   Windows Update).
4. Linux: `libinput list-devices | grep -A20 tablet` shows the
   axes.

## Linux Wayland

Wayland support is solid on KDE Plasma 6 and GNOME 46+. Older Sway
and Hyprland builds may not honor hit-test paths or window-move
correctly. Workarounds:

- Run under XWayland (`WAYLAND_DISPLAY= elysium-designer`).
- Update to the latest compositor.

## See also

- [Quality presets](../rendering/quality-presets.md)
- [Color management](../reference/color-management.md)
- [Environment variables](../reference/environment-variables.md)
