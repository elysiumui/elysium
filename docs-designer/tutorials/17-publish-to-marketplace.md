# Publish to marketplace

Time: 30 minutes. Difficulty: Advanced.

Sign and publish one of your skins to the Elysium marketplace so
other framework users can install it with one CLI command.

## Prerequisites

- A finished `.esk` you want to share.
- An Ed25519 signing key (we generate one below).

## Generate a signing key

The marketplace verifies skin authorship via Ed25519 signatures.
Generate a keypair:

```sh
elysium skins keygen
# writes ~/.elysium/keys/<id>.hex (private) + <id>.pub (public)
```

The private key (`.hex`) never leaves your machine. The public key
(`.pub`) you register with the marketplace.

## Register your public key

The first time you publish, the registry asks you to claim a
publisher namespace. Visit `https://skins.elysiumui.com/register`
in a browser, sign in, paste your `.pub` content.

After the registry confirms (instant for new namespaces), every
skin signed with the matching private key publishes under your
namespace.

## Prepare the skin

Open your skin in the Designer. Confirm:

- `manifest.json` has a clear `id` (reverse-DNS,
  e.g. `dev.yourname.aurora-clock`).
- `manifest.json` has a `name`, `version`, `description`.
- The bundle contains no secrets, no absolute paths, no `.git`
  files.

The Designer's `File > Validate Skin` checks all of the above.

## Publish

```sh
ELYSIUM_SIGN_KEY=$(cat ~/.elysium/keys/<id>.hex) \
  elysium skins publish ./aurora-clock.esk
```

The CLI:

1. Validates the manifest.
2. Strips `designer_layout.json` and `.git*`.
3. Tarballs the folder.
4. Computes an Ed25519 signature.
5. POSTs the metadata + signature to the registry.
6. PUTs the tarball to the upload URL the registry returns.

A successful publish prints:

```
✓ Published dev.yourname.aurora-clock@0.1.0
  Install: elysium skins add dev.yourname.aurora-clock
  URL:     https://skins.elysiumui.com/dev.yourname.aurora-clock
```

## Install (verify)

From another machine (or after wiping local state):

```sh
elysium skins add dev.yourname.aurora-clock
```

The CLI downloads, verifies the signature, and installs the bundle
to `~/.elysium/skins/dev.yourname.aurora-clock/`.

## Versioning

Bump the `version` field in `manifest.json` before each publish.
The CLI rejects publishes of versions already in the registry.

Major bumps (breaking changes) prompt the user with a migration
note when they run `elysium skins migrate`.

## Tagging

The CLI accepts `--tags` for searchability:

```sh
elysium skins publish ./aurora-clock.esk --tags "clock,desktop,minimal"
```

Tags help users find your skin via `elysium skins search`.

## Unpublish

```sh
elysium skins unpublish dev.yourname.aurora-clock --version 0.1.0
```

Removes a specific version. To take down the namespace entirely,
contact the registry maintainers.

## What you exercised

- `elysium skins keygen` / `register` / `publish` / `add`.
- Ed25519 signatures + verification.
- Versioning.
- Tagging for discoverability.

## See also

- [Marketplace](https://docs.elysiumui.com/guides/marketplace/) (framework guide)
- [CLI](https://docs.elysiumui.com/guides/cli/)
