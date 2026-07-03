# Auto-update

`elysium.updater.Updater` wraps Sparkle (macOS), WinSparkle (Windows),
and AppImageUpdate (Linux) behind one API.

```python
from elysium.updater import Updater

upd = Updater(
    feed_url="https://example.com/appcast.xml",
    public_ed25519_key=open("keys/update.pub").read().strip(),
)
upd.on_update_available = lambda info: print("update:", info.version)
upd.check_in_background(interval_hours=24)
```

## Feeds

| Platform | Format | Convention |
|---|---|---|
| macOS    | Sparkle 2 appcast (`.xml`) | Standard `<item>` with `sparkle:version`, `url`, `sparkle:edSignature` |
| Windows  | WinSparkle appcast (`.xml`) | Same shape |
| Linux    | JSON manifest (`.json`)     | `{version, url, notes, signature}` |

When the URL ends in `.json` the JSON parser fires; otherwise the wrapper assumes a Sparkle-style XML feed.

## Signatures

For macOS/Windows we use Sparkle's native EdDSA signature scheme: generate keys with `generate_keys` from Sparkle's tools, store the private key offline, ship the public key with the app at build time.

For Linux we piggy-back on the `.zsync` sidecar's checksum + a detached GPG signature alongside the AppImage. See [packaging.md](packaging.md).

## Manual `check_now`

```python
info = upd.check_now()
if info and upd._is_newer(info.version):
    upd.install(info)   # shows the standard OS update UI
```

## Fallback

When the native backend isn't bundled (no Sparkle.framework, no
WinSparkle.dll, no AppImage runtime), `install()` opens the URL in the
user's browser so they can grab the new build manually.
