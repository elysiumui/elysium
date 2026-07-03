# Customize and save

Author a custom Designer skin without leaving the app, save it as a
named user theme, and (for power users) fork the Designer's chrome
`.esk` bundle to tune layout + iconography.

## Three layers of customization

The Designer's appearance is layered. Most users only touch the
top layer; the deeper layers are for authors who want a tailored
authoring environment.

| Layer | Scope | Where |
|---|---|---|
| **Theme palette** | Colours (primary, accent, surface, danger), radii, font sizes | Theme > Customize... or the **Customize Theme** toolbar button (paint-roller icon) |
| **Built-in skin variants** | Light / Dark / OLED / Glass / Frost | Theme menu (or `Cmd+,` Preferences) |
| **Chrome `.esk` fork** | Full window geometry, panel widths, sprite atlas, accessibility variants | Edit `~/.config/elysium-designer/themes/` + load via Preferences |

## The Customize Theme dialog (toolbar)

Click the **paint-roller** icon on the toolbar (between Render Final
and the status-line toggles) to open the Customize dialog without
diving through menus. The dialog lets you:

- **Pick a base palette** by clicking a primary color swatch. Every
  derived token (`accent`, `surface`, `on_surface`, etc.) is
  regenerated via OKLCH color math so the theme stays harmonious.
- **Toggle Dark mode**: flips the surface family from light to
  dark + adjusts contrast tokens.
- **Save as user theme**: gives the in-progress edit a name so it
  shows up under Theme > Manage User Themes... and survives restart.
- **Cancel**: drops the in-progress edit, no save.

The same dialog is reachable via **Theme > Customize...** in the
menu bar.

## Saving a theme

Once the color + dark-mode toggle look right, press **Save current
as user theme...** and name it. The theme is written to:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Elysium Designer/themes/<name>.json` |
| Windows | `%AppData%\Elysium Designer\themes\<name>.json` |
| Linux | `~/.config/elysium-designer/themes/<name>.json` |

User themes appear in the Theme menu (above the divider) so you
can switch back instantly. Delete one via **Theme > Manage User
Themes...**.

## Forking the chrome `.esk`

Power-users who want to tune column widths, replace the toolbox
icons with their own sprite set, or swap the Aether FAB position
can fork the Designer's chrome bundle.

The chrome bundle lives at
[`elysium-designer/designer-chrome.esk/`](https://github.com/elysiumui/elysium/tree/main/elysium-designer/designer-chrome.esk).
Copy it into the per-user themes directory under your preferred
name (e.g. `~/.config/elysium-designer/themes/my-chrome.esk/`),
edit any of:

- **`manifest.json`**: the `"layout"` block sets `toolbox_w`,
  `right_w`, `status_h`, `timeline_h`, etc. Reload the Designer
  to see the new geometry.
- **`assets/icons/`**: drop PNG / SVG files named after the icon
  keys (e.g. `tb_save.png`). The `GlyphAtlas` framework primitive
  auto-loads them; `ui.IconButton` resolves by name.
- **`document.json` variants**: `variants/high_contrast.json` or
  `variants/reduce_motion.json` swap in when the OS accessibility
  prefs request them.

The chrome bundle uses the same `.esk` schema as user-authored
apps, so anything you learn forking the Designer's chrome carries
straight over to your own apps.

## Live preview

Every theme edit applies immediately: there is no Apply button. The
Designer renders through `elysium.theme.current_theme()` each frame,
so any change to the theme tokens (or a Theme menu switch) is
visible on the next paint.

## Resetting

**Theme > Reset to default** drops every user customization and
returns to Light. The user-themes file is left intact: the reset
just switches the active theme back to the built-in default.

## See also

- [Built-in themes](built-in.md)
- [Themes overview](index.md)
- [Reference > File locations](../reference/file-locations.md)
- [Reference > Theming reference](../reference/theming-reference.md)
