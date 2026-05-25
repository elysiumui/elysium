# Uninstall and reset

Two flavors of cleanup live on this page:

- **Reset only**: keep the Designer installed but wipe preferences,
  caches, and recents. Useful when you want to repeat the first-run
  wizard, or when something looks corrupted.
- **Full uninstall**: remove the app and every trace of it.

## Where state lives

The Designer keeps four pieces of state on disk:

| Bucket | macOS | Windows | Linux |
|---|---|---|---|
| Preferences | `~/Library/Application Support/Elysium Designer/` | `%AppData%\Elysium Designer\` | `~/.config/elysium-designer/` |
| Cache | `~/Library/Caches/Elysium Designer/` | `%LocalAppData%\Elysium Designer\Cache\` | `~/.cache/elysium-designer/` |
| Logs | `~/Library/Logs/Elysium Designer/` | `%LocalAppData%\Elysium Designer\Logs\` | `~/.cache/elysium-designer/logs/` |
| API keys | macOS Keychain | Windows Credential Manager | Secret Service (GNOME Keyring / KWallet) |

Project files live wherever you saved them. The Designer never
auto-writes outside the four folders above (and the user keychain).

## Reset only

### macOS

```sh
rm -rf "$HOME/Library/Application Support/Elysium Designer"
rm -rf "$HOME/Library/Caches/Elysium Designer"
rm -rf "$HOME/Library/Logs/Elysium Designer"
```

Optionally clear stored AI keys via **Keychain Access > search
"elysium" > delete**.

### Windows

In PowerShell:

```powershell
Remove-Item -Recurse -Force "$env:APPDATA\Elysium Designer"
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Elysium Designer"
```

Optionally clear stored AI keys via **Credential Manager > Windows
Credentials > search "elysium" > Remove**.

### Linux

```sh
rm -rf ~/.config/elysium-designer
rm -rf ~/.cache/elysium-designer
```

Optionally clear stored AI keys with `secret-tool clear service elysium-designer`.

The next launch goes through the [first-run wizard](first-run.md)
again.

## Full uninstall

### macOS

1. Drag `Elysium Designer.app` from `/Applications` to the Trash.
2. Run the three `rm -rf` commands from the Reset section above.
3. Clear AI keys from Keychain Access.

### Windows

1. **Settings > Apps > Installed apps**, find Elysium Designer, click
   the three-dot menu, choose **Uninstall**.
2. Run the two `Remove-Item` commands from the Reset section above.
3. Clear AI keys from Credential Manager.

### Linux

- AppImage: delete the `.AppImage` file plus `~/.cache/elysium-designer/`
  and `~/.local/share/applications/elysium-designer.desktop`.
- `.deb`: `sudo apt remove elysium-designer && sudo apt autoremove`.
- `.rpm`: `sudo dnf remove elysium-designer`.
- AUR: `yay -Rs elysium-designer-bin`.

Then run the two `rm -rf` commands from the Reset section.

## What does not get removed automatically

- **Your projects**. Anything you saved to disk stays put. Delete the
  containing folder yourself if you want it gone.
- **Exported `.esk` bundles**. Same as above; they live in your
  project folders.
- **AI provider account state on the provider's side**. Removing your
  API key from the keychain does not revoke it. Rotate it in the
  provider's dashboard if needed.

## Verify a clean slate

After a full uninstall plus state wipe, the next install should:

1. Show the first-run wizard.
2. List zero recent projects.
3. Show the AI providers as "not configured".

If you still see old recents or a previous theme on first launch,
double-check the preferences folder for your OS still exists; some
file managers hide it by default.
