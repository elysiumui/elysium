# Skin marketplace

```bash
elysium skins init my-skin           # scaffold a new publishable skin
elysium skins search music           # query the registry
elysium skins info dev.foo.player    # registry metadata
elysium skins add  dev.foo.player    # download + verify signature + install
elysium skins list                   # what's installed locally
elysium skins migrate dev.foo.player # bump to latest schema_version
elysium skins publish ./my-skin.esk  # tar + sign + upload
```

## Local layout
Installed skins land under `~/.elysium/skins/<id>/`. The native loader resolves relative asset paths against the skin root, so dragging a skin between machines is just a `cp`.

## Trust
- Every published skin carries an Ed25519 detached signature (`signature.json`).
- The registry stores only the publisher's verified public key: never the private key.
- The native loader rejects any skin whose signature doesn't validate against its declared publisher key.
- `publish` reads the private signing key from `$ELYSIUM_SIGN_KEY` (hex-encoded 32-byte seed) so CI flows don't need an interactive prompt.

## Registry endpoint
The registry URL is `$ELYSIUM_REGISTRY` (default: `https://skins.elysiumui.com/v1`). Self-hosting the registry is supported: the wire format is:

- `GET /v1/search?q=...` → `[{id, version, description, ...}, ...]`
- `GET /v1/skins/<id>` → `{manifest, download_url, publisher_pubkey, signature, size}`
- `POST /v1/skins` → `{upload_url, public_url}` (publisher posts a `PUT` of the tar bytes to `upload_url`)

## Loading an installed skin

```python
import elysium as ely
window.load_skin("~/.elysium/skins/dev.foo.player/")
```

Same loader as a local-folder skin; the marketplace is a
distribution channel, not a separate runtime.

## Versioning

Marketplace skins follow semver:

- Major bumps are breaking changes (renamed hooks, changed
  schema_version).
- Minor bumps add hooks or placements.
- Patch bumps fix bugs or polish visuals.

`elysium skins migrate <id>` upgrades a locally-installed skin to
the latest registry version, bumping `schema_version` if needed.

## Publishing

Sign + tar + upload in one command:

```sh
ELYSIUM_SIGN_KEY=$(cat ~/.elysium/keys/my-signing-key.hex) \
  elysium skins publish ./my-skin.esk
```

The CLI:

1. Validates the manifest (id, version, schema_version).
2. Strips `designer_layout.json` and any `.git*` files.
3. Computes a tarball + checksum.
4. Signs the checksum with the seed in `$ELYSIUM_SIGN_KEY`.
5. POSTs the metadata to the registry and PUTs the tarball.

The publisher's public key is registered once via the registry's
web UI; subsequent publishes from any CI machine work as long as
they have the matching private seed.

## See also

- [Skins](skins.md): `.esk` anatomy.
- [Packaging](packaging.md): bundle a runnable app (different
  from publishing a skin).
- [CLI](cli.md): `elysium skins` subcommands.
