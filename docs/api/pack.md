# `elysium.pack`

Cross-platform signed bundle packaging. The Python surface that
`elysium pack` calls into.

## Functions

| Function | Purpose |
|---|---|
| `pack(entry, name, identifier, icon=None, includes=[], sign=True, notarize=False)` | Build a per-OS bundle |
| `available_signers()` | Discover signing identities on the local machine |
| `verify_bundle(path)` | Verify signatures on a built bundle |

## Outputs

| OS | Output |
|---|---|
| macOS | `dist/<Name>.app` (signed if `ELYSIUM_SIGNING_IDENTITY` set; notarized if `--notarize`) |
| Windows | `dist/<Name>/<Name>.exe` + installer `.exe` |
| Linux | `dist/<Name>.AppImage` (+ `.deb` if `dpkg-deb` is on PATH) |

## Environment variables

| Var | Effect |
|---|---|
| `ELYSIUM_SIGNING_IDENTITY` | macOS Developer ID |
| `ELYSIUM_NOTARY_PROFILE` | macOS notarytool keychain profile |
| `ELYSIUM_WINDOWS_CERT` | Path to a Windows PFX |
| `ELYSIUM_WINDOWS_CERT_PASSWORD` | Password |

## Auto-rendered details

::: elysium.pack

## See also

- [Packaging](../guides/packaging.md)
- [CLI](../guides/cli.md)
