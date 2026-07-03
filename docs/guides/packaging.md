# Packaging

One command builds a self-contained, redistributable bundle:

```bash
elysium pack app/main.py --name "My App" --version 1.0.0 \
                          --identifier dev.example.myapp \
                          --icon assets/icon.png
```

- **macOS**: produces `dist/My App.app/`: proper `Info.plist`, embedded relocatable Python, your code under `Contents/Resources/`, a POSIX-shell launcher in `Contents/MacOS/`. Add `--sign-identity "Developer ID Application: …"` and `--notarize` to sign + notarize + staple in one go.
- **Windows**: produces `dist/My App/` with `My App.exe`, embedded `python\`, your code under `resources\`. Add `--sign-identity "<subject>"` to call `signtool` if it's on PATH.
- **Linux**: produces `dist/My App.AppDir/`, and a fused `.AppImage` if `appimagetool` is installed.

## What gets bundled
- A relocatable interpreter fetched once from [python-build-standalone](https://github.com/astral-sh/python-build-standalone) and cached at `~/.elysium/pack-cache/`.
- The `elysium` package + the native `_native.{so,pyd}` cdylib.
- Every package in your active venv's `site-packages` that's reachable from the entry script (walked via `modulefinder`).
- Anything you pass with `--data path/` and `--module name` (catches lazy imports the walker misses).
- The application icon, transparently converted from PNG to `.icns` on macOS via `sips` + `iconutil`.

## CI
```yaml
- run: pip install elysium-ui
- run: elysium pack app/main.py --name "My App"
- uses: actions/upload-artifact@v4
  with:
    name: my-app-${{ matrix.os }}
    path: dist/
```

## Programmatic API
```python
from elysium.pack import pack
pack(
    entry="app/main.py",
    name="My App",
    version="1.0.0",
    identifier="dev.example.myapp",
    icon="assets/icon.png",
    output_dir="dist/",
    sign_identity="Developer ID Application: Example Inc (XXXXXXXXXX)",
    notarize=True,
    extra_data=["assets/", "skins/main.esk/"],
    extra_modules=["my_lazy_package"],
)
```

## Signing recipes

### macOS: Developer ID + notarization

```bash
# One-time keychain credential: Apple ID + app-specific password.
xcrun notarytool store-credentials elysium-notary \
  --apple-id "you@example.com" --team-id ABCDE12345 \
  --password "xxxx-xxxx-xxxx-xxxx"

elysium pack app/main.py --name "My App" \
  --sign-identity "Developer ID Application: Your Name (ABCDE12345)" \
  --notarize
```

### Windows: Authenticode

1. Acquire an EV or OV code-signing cert (DigiCert, Sectigo, GoDaddy).
2. Install signtool: `winget install Microsoft.WindowsSDK.10.0.22621`.
3. Pack and sign:

```powershell
elysium pack app\main.py --name "My App" `
  --sign-identity "Your Org, LLC"
# Internally: signtool sign /n "Your Org, LLC" /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 My App.exe
```

For HSM-stored EV certs replace `/n` with `/sha1 <cert thumbprint>` and add
`/csp "eToken Base Cryptographic Provider"`.

### Linux: AppImage + zsync sidecar

```bash
elysium pack app/main.py --name "My App"
# → dist/My App.AppImage

# 1. Sign with your GPG key.
gpg --detach-sign --armor "dist/My App.AppImage"

# 2. Generate the .zsync file so AppImageUpdate can do delta updates.
zsyncmake "dist/My App.AppImage" -u "My App.AppImage"

# 3. Publish all three.
rsync "dist/My App.AppImage"{,".asc",".zsync"} you@server:/var/www/releases/
```

Wire the updater feed (see `elysium.updater`) to `My App.AppImage.zsync`
and the existing AppImage gains in-place delta updates with rollback on
signature mismatch.

## Why not PyInstaller?
Elysium's packager handles the framework-specific bits PyInstaller punts on:
- Bundles the `elysium._native` cdylib in the right place.
- Knows where Skia's data files live and copies them.
- Writes a properly-typed `Info.plist` for shaped/transparent windows (`LSUIElement`, `NSHighResolutionCapable`).
- Threads codesign + notarize without you assembling them yourself.
- One CLI command, three platforms, same options.

You can still use PyInstaller / Briefcase / py2app if you prefer: `elysium.pack` is opt-in.
