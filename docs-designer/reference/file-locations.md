# File locations

Where the Designer reads and writes state on each OS.

## Per-user state

| Bucket | macOS | Windows | Linux |
|---|---|---|---|
| Preferences | `~/Library/Application Support/Elysium Designer/preferences.json` | `%AppData%\Elysium Designer\preferences.json` | `~/.config/elysium-designer/preferences.json` |
| Brush palette slots | `~/.elysium/designer-prefs.json` key `brush_palette_slots` | same | same |
| Recent projects | same folder, `recent_projects.json` | same | same |
| Workspace layouts | same folder, `workspaces/<name>.json` | same | same |
| User brushes | `~/Library/Application Support/Elysium Designer/brushes/user/` | `%AppData%\Elysium Designer\brushes\user\` | `~/.config/elysium-designer/brushes/user/` |
| User themes | `~/Library/Application Support/Elysium Designer/themes/` | `%AppData%\Elysium Designer\themes\` | `~/.config/elysium-designer/themes/` |
| Marketplace skins | `~/Library/Application Support/Elysium Designer/skins/` | `%AppData%\Elysium Designer\skins\` | `~/.config/elysium-designer/skins/` |

## Caches and logs

| Bucket | macOS | Windows | Linux |
|---|---|---|---|
| Cache (sim, AI, textures) | `~/Library/Caches/Elysium Designer/` | `%LocalAppData%\Elysium Designer\Cache\` | `~/.cache/elysium-designer/` |
| Logs | `~/Library/Logs/Elysium Designer/` | `%LocalAppData%\Elysium Designer\Logs\` | `~/.cache/elysium-designer/logs/` |
| Autosave | same as cache, under `autosave/<project_id>/` | same | same |
| AI provider cache | cache folder, under `ai_cache/` | same | same |

## API keys

Stored in the OS keychain:

| OS | Service |
|---|---|
| macOS | Keychain Access, service "elysium-designer" |
| Windows | Credential Manager > Windows Credentials |
| Linux | Secret Service (GNOME Keyring / KWallet) |

Never written to plain config files.

## Project files

Projects live wherever you saved them; the default location is
`~/Documents/Elysium Projects/` (configurable in
`Preferences > Projects > Default Project Location`).

A `.esk` bundle is a folder; the Designer never relocates project
files behind your back.

## IPC sockets

| OS | Path |
|---|---|
| macOS / Linux | `~/.elysium/sessions/elysium-default.sock` |
| Windows | `\\.\pipe\elysium-default` |

Override per-session via `Preferences > Hot Reload > Socket Path`.

## Plugins

Drop Python files into `<user data>/plugins/` for the Designer to
auto-load on startup. (Plugin support is roadmap-stable in v1;
hooks exist but are not yet fully documented.)

## Uninstall

`File > Preferences > Reset > Wipe All User State` removes every
per-user file listed above. The
[Designer's Uninstall and reset page](../installation/uninstall-and-reset.md)
also covers manual removal.

## See also

- [Installation > Uninstall and reset](../installation/uninstall-and-reset.md)
- [Environment variables](environment-variables.md)
