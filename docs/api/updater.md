# `elysium.updater`

Sparkle-compatible auto-update for packaged apps.

## Functions

| Function | Purpose |
|---|---|
| `check_for_updates(url, channel='stable')` | Query an appcast feed |
| `install_update(update)` | Download + verify + apply |
| `set_check_interval(seconds)` | Configure background check cadence |
| `on_update_available(fn)` | Callback when a new version is found |
| `on_update_installed(fn)` | Callback after a successful install |

## Channels

| Channel | Use |
|---|---|
| `stable` | Public releases (default) |
| `beta` | Pre-releases |
| `dev` | Nightly / canary |

Switching channels mid-session resets the next-check timer.

## Feed format

The framework reads Sparkle's `appcast.xml` format. The feed lives
at any URL you point it at; typically `https://example.com/appcast.xml`.

## Signature verification

Updates are Ed25519-signed; the public key is baked into the
bundle at pack time. Updates whose signature does not validate are
rejected.

## Rollback

`updater.rollback()` reverts to the previously-installed version
(kept in `~/.elysium/updates/previous/` for one generation).

## Auto-rendered details

::: elysium.updater

## See also

- [Auto-update](../guides/auto-update.md)
- [Packaging](../guides/packaging.md)
