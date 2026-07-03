# OPERATIONS — the Elysium UI runbook

**This file is the single source of truth for how Elysium UI is built,
published, hosted, and secured.** If you are starting from zero (new machine,
new session, new maintainer): read this top to bottom, then you know
everything that is not derivable from the code itself.

Business entity everywhere: **Lamaute Labs LLC**.
Last full review: **2026-07-03**.

---

## 1 · What the product is

Two products, two licenses:

| Product | License | Distribution |
|---|---|---|
| **Elysium UI framework** (`import elysium`) | Apache-2.0, open source | `pip install elysium-ui` (PyPI) + public GitHub repo |
| **Elysium Designer** (the `.esk` authoring app) | Commercial, closed source | PyLocket — free 14-day trial + paid license ($8/mo · $79/yr prepaid) |

The **name "Elysium UI" and the Blue Morpho logo are trademarks** of Lamaute
Labs LLC (the filed mark is **"Elysium UI"**, not "Elysium"). Code is
permissive; the brand is protected (`TRADEMARK.md`, `NOTICE` — the React/Vue
model). Apache-2.0 §6 withholds trademark rights, so no license change was
needed.

- PyPI distribution name is **`elysium-ui`** because `elysium` is squatted
  (dead 2022 Deta ODM). The import name stays `elysium`.
- The framework is **1.x, strict semver** (`docs/guides/api-stability.md`).
- The Designer **versions independently** — currently **v1.0.0**.

---

## 2 · Repo topology (three repos — who owns what)

| Repo | Visibility | Role |
|---|---|---|
| **`klamaute/Elysium`** (local checkout: `~/ElysiumUI`) | **PRIVATE — must stay private forever** (its git history contains the Designer source from before the split) | The **monorepo — source of truth for all development**: framework (Python + Rust), docs sources, examples, tests, tooling, and the **website (only exists here)** |
| **`elysiumui/elysium`** | PUBLIC | The open-source face: framework-only, **freshly scrubbed history**. Release tags fire here (wheels → PyPI), docs deploy from here |
| **`klamaute/elysium-designer`** | PRIVATE | The Designer app + its release CI (raw PyLocket artifacts) |

The GitHub **org is `elysiumui`** (the name `elysium-ui` was taken).

### The mirror discipline (monorepo → public)

There is **no automated mirror**. Framework changes are developed and tested
in the monorepo, then copied file-for-file to `elysiumui/elysium`. The public
repo must **never** receive:

- `website/` (proprietary — the public `NOTICE` says so explicitly)
- `OPERATIONS.md`, `LAUNCH-CHECKLIST.md`, `.claude/`, `.docs-staging/`, `.coverage`
- `.github/workflows/website.yml`, `.github/workflows/cf-domain-move.yml`
- `README.md` **differs deliberately** — the monorepo copy carries a private
  banner; don't copy it over the public one blindly.

Everything else at the top level is mirrored (docs, docs-designer, python,
elysium-native, examples, tests, scripts, schemas, elysium-lsp/-vscode/
-pycharm, marketplace-server, pyproject.toml, uv.lock, mkdocs*.yml,
CHANGELOG, LICENSE, NOTICE, TRADEMARK.md).

### Public-repo history scrub (2026-07-03) — standing caveats

The public repo's history was rewritten with `git-filter-repo` to purge
`website/`, `.claude/`, `LAUNCH-CHECKLIST.md`, `.docs-staging/`, `.coverage`
from **all** history (fresh-clone verified: 0 objects for purged paths).
Know these residuals:

- **Orphaned pre-scrub SHAs remain fetchable on GitHub** until GitHub Support
  garbage-collects them (optional support ticket still open as a to-do). They
  contain no secrets — this is a licensing-posture concern only.
- PyPI wheel **attestations for v1.1.2 wheels reference now-orphaned SHAs**
  (still cryptographically valid; the re-tagged run's sdist attestation
  references the scrubbed history).
- `git-filter-repo` **strips the `origin` remote** from the working clone —
  re-add it before pushing.

### Local working tree quirks (`~/ElysiumUI`)

- `elysium-designer/` exists on disk but is **untracked** (leftover working
  copy from the split — canonical source is `klamaute/elysium-designer`).
- `mark/` is an untracked scratch dir; `build/` and `site/` are gitignored
  build outputs.

---

## 3 · Live surfaces (what serves where)

| URL | What | Hosted on | Deployed by |
|---|---|---|---|
| `elysiumui.com` + `www.` | Marketing site (Astro) | Cloudflare Pages | monorepo `website.yml` → direct upload (see §6) |
| `docs.elysiumui.com` | Framework docs (MkDocs) | GitHub Pages (`elysiumui/elysium`, `gh-pages` branch) | public repo `docs.yml` |
| `designer.elysiumui.com` | Designer docs (MkDocs) | Cloudflare Pages project `elysium-designer-docs` | `docs-designer.yml` (wired in **both** repos — see §7) |
| PyPI `elysium-ui` | Framework wheels + sdist | pypi.org | public repo `release-library.yml` on `v*` tags |
| PyLocket | Designer trial + licensed builds | get.pylocket.com | manual upload of CI artifacts (see §5) |
| `support@elysiumui.com` | Support email | Purelymail (~$10/yr) | MX/SPF/DKIM records in Cloudflare DNS |

Binaries are never hosted on our own infrastructure.

---

## 4 · Framework release → PyPI

**Trusted Publishing (OIDC)** — there is **no PyPI API token anywhere**.
PyPI account: **`lamautelabs`**. Publisher config on PyPI must exactly match:
owner `elysiumui`, repo `elysium`, workflow `release-library.yml`,
environment `pypi`. (First-ever publish failed because the entry said
`elysium-ui/elysium` — the squatted org name. Exact match is everything.)

### Procedure

1. Develop + test in the **monorepo** (`build.yml` gates: `cargo test` on
   macOS/Windows/Linux, clippy + rustfmt, pytest).
2. If Rust changed, rebuild the native module — **a prebuilt `.so` sits in
   the tree** and stale copies silently mask Rust changes.
3. Bump `version` in `pyproject.toml`; add a `CHANGELOG.md` entry.
4. Mirror the changed framework files to `elysiumui/elysium` (respect the
   §2 exclusion list).
5. Tag **on the public repo**: `git tag vX.Y.Z && git push origin vX.Y.Z`.
   `release-library.yml` then builds 4 abi3 wheels + sdist, attaches them to
   a GitHub Release, and the `publish-pypi` job (environment `pypi`,
   `id-token: write`, `skip-existing: true`) uploads to PyPI.
6. Acceptance test: fresh **Python ≥3.10** venv → `pip install elysium-ui` →
   `import elysium` → render a headless chart to PNG.

### Hard-won CI facts (do not relearn these)

- Wheels are **cp310-abi3** — one wheel per platform. On Python 3.9 pip says
  "no matching distribution"; that is expected, not a bug.
- **manylinux_2_28**: Skia links `-lfontconfig -lfreetype` → maturin-action
  needs `before-script-linux: dnf install -y fontconfig-devel freetype-devel`.
- **maturin omits declared License-Files from the sdist** when
  `manifest-path` is a subdirectory → PyPI 400s the upload. Fixed with
  `[tool.maturin] include = [{path="LICENSE",format="sdist"}, {path="NOTICE",format="sdist"}]`.
- `skip-existing: true` makes partial re-runs safe (wheels already uploaded,
  sdist retried).
- **`macos-13` runners are retired** (Dec 2025) — jobs queue forever, never
  fail. Intel builds use **`macos-15-intel`** (the last x86_64 GitHub image,
  supported to Aug 2027). When it dies, Intel macOS wheels need
  cross-compilation or must be dropped.
- All actions are on Node-24-capable majors (checkout v7, setup-python v6,
  upload/download-artifact v7/v8, cache v6, deploy-pages v5, gh-release v3).

---

## 5 · Designer release → PyLocket

Repo: `klamaute/elysium-designer`, workflow `release-designer.yml`
(dispatch + tags). It checks out the framework from the **public**
`elysiumui/elysium` — **no token needed** (the `FRAMEWORK_REPO_TOKEN` secret
still exists there but is unused; safe to delete).

### Artifacts (PyLocket accepts RAW builds only — installers are rejected)

| Artifact | Format |
|---|---|
| `Elysium-Designer-macOS-arm64.app.zip` / `-x86_64.app.zip` | `.app` bundle, zipped with `ditto --keepParent` (preserves symlinks/exec bits) |
| `Elysium-Designer-Linux-x86_64-elf.zip` | PyInstaller **onefile ELF**, zipped with `zip -y` |
| `Elysium-Designer-Windows-x64-exe.zip` | PyInstaller **onefile .exe**, zipped |

No `.dmg`, no Inno Setup, no AppImage — PyLocket rejects installers by design.
GitHub wraps artifacts in an extra download zip; unzip once before uploading.

**CI smoke test** (macOS + Windows legs): launch the frozen app on the runner
and poll the Aether bridge on `127.0.0.1:8183` — a crashed windowed-bootloader
app never opens the port, so the test cannot false-pass. (Linux runner has no
display, so no Linux leg.)

### PyInstaller spec facts (`scripts/build-designer.spec`)

- `__main__` imports `menus` via `importlib.import_module` and `importers`
  inside functions — invisible to static analysis. The spec needs
  `hiddenimports=['menus','importers']` **and** `pathex` including the
  designer dir. A `datas` copy of the `.py` does NOT fix it (lands off
  `sys.path`).
- Runtime data that must ship: `designer-chrome.esk/`, `assets/` (in-app
  icons), `examples/hello/hello.esk` (fallback doc), `menus.py`, `importers.py`.
- `ICON_MAC`/`ICON_WIN` default to
  `elysium-designer/assets/ElysiumDesigner.{icns,ico}` when the env vars are
  unset (CI never sets them).
- Debugging a frozen app: run the binary **from a terminal** — stderr carries
  the traceback even with `console=False`.
- Unsigned/ad-hoc macOS downloads trip Gatekeeper ("damaged") — `xattr -cr`
  for local testing. Production trial builds are **signed** (Apple Developer
  enrollment exists for Lamaute Labs LLC) and delivered via PyLocket.

### Commerce state

- PyLocket product: **Elysium Designer v1.0.0**, single trial URL for all
  OSes (user enters email + picks platform, **14-day** trial):
  `https://get.pylocket.com/t/AwTOf_-qftFk8P2qdhd3quTdomjcHVgnkDNPphAqsKc`
- Pricing **$8/month · $79/year prepaid**; PyLocket Pro adds ≈**$4/license
  COGS**.
- **Stripe is under review** → `designer.buyUrl = ''` in
  `website/src/data/downloads.ts`, which renders the "Purchasing coming soon"
  state. When checkout links arrive, set `buyUrl` — a one-line change.

---

## 6 · Website → elysiumui.com

Source: `website/` (Astro 5 + Tailwind 4, fully static) — **exists only in
the private monorepo**. Design tokens in `src/styles/global.css` mirror the
product's `studio_dark()` theme. **Every link, version, price, and URL on the
site lives in `website/src/data/downloads.ts`** — edit there, nowhere else.

### Deploy path

`website.yml` (monorepo) on any push to `main` touching `website/**`:
builds the site → **wrangler direct upload** to the Cloudflare Pages project
**`elysiumui-website`**. It deploys ONLY — it deliberately does not touch
custom domains (an earlier version moved them on every deploy, which caused
the 522 incident; domain moves are `cf-domain-move.yml`'s job, run on demand).

Why direct upload: the original Pages project (`elysium`) was git-connected
to the repo that used to hold the website; **Cloudflare cannot re-point a
git-connected project to a different repo, and wrangler cannot direct-upload
to a git-connected project** — so a fresh direct-upload project was the only
path when the website source moved to the private monorepo.

### ⚠️ Domain-cutover state (UPDATE THIS WHEN DONE)

As of 2026-07-03 the cutover is **staged but not executed**:

- Live domains (`www` + apex) still attach to the **old `elysium` project**
  (dormant — nothing rebuilds it, so it serves frozen-but-current content).
- The new `elysiumui-website` project is deployed and current at
  `elysiumui-website.pages.dev`.
- **The rule that caused a 10-minute outage: the Pages domain attachment and
  the DNS CNAME target must agree, or Cloudflare serves 522.** The first
  migration attempt moved the attachment while DNS still pointed at
  `elysium.pages.dev`.
- The fix: `.github/workflows/cf-domain-move.yml` (branch `ci/domain-cutover`,
  PR #5) moves the attachment **and** retargets the DNS records in one run.
  Requires the CF token to have Zone → DNS → Edit (added 2026-07-03).
- **To execute:** merge PR #5, then
  `gh workflow run cf-domain-move.yml --repo klamaute/Elysium -f target=elysiumui-website`,
  then verify `curl -sI https://www.elysiumui.com` and the apex both return
  200. To roll back: same command with `-f target=elysium`.
- After cutover: the old `elysium` Pages project can be deleted in the CF
  dashboard; keep `cf-domain-move.yml` as an ops tool.

### Website gotchas

- `background-attachment: fixed` + `backdrop-filter` = Chromium **black
  screen on scroll** (real browser bug). The aurora gradients use a fixed
  `body::before` layer instead.
- The butterfly hero PNG's **provenance is unverified third-party** —
  replace with the commissioned Blue Morpho
  (`examples/butterfly/BLUE_MORPHO_INTRO_SPEC.md`) or verify the license.
- Legal pages (`/terms`, `/privacy`, `/eula`) are **data-driven** Astro pages
  (arrays of `Section{h, blocks}` rendered by a template). Content is the
  counsel-provided text **verbatim**; subtitles carry only "Last updated …" —
  no draft/counsel-review language on live pages (user directive). Internal
  counsel checklists are intentionally not published.
- Footer + legal must say the **"Elysium UI"** name is the trademark (the
  filed mark) — never shorten to "Elysium".

---

## 7 · Documentation sites

Two MkDocs sites, both sourced from the monorepo and mirrored to the public
repo:

| Site | Config | Source | Deploy |
|---|---|---|---|
| docs.elysiumui.com | `mkdocs.yml` | `docs/` | public repo `docs.yml` → orphan `gh-pages` branch → GitHub Pages custom domain |
| designer.elysiumui.com | `mkdocs-designer.yml` | `docs-designer/` | `docs-designer.yml` → wrangler direct upload → CF Pages `elysium-designer-docs` |

- **`docs/CNAME` (= `docs.elysiumui.com`) must stay committed in-source**:
  the force-orphan gh-pages deploy wipes any settings-written CNAME and
  would silently detach the custom domain. Same for `docs-designer/CNAME`.
- The Designer docs use Cloudflare Pages because **GitHub allows one Pages
  site per repo** — the framework docs already claim it.
- `docs-designer.yml` is wired in **both** repos (both have the CF secrets).
  In practice the monorepo push deploys first (development happens there);
  the public-repo copy deploys again on mirror — harmless, same content.
- The **monorepo's `docs.yml`** still pushes a `gh-pages` branch on
  `klamaute/Elysium`, but the private repo's Pages is not the live site —
  vestigial, harmless (housekeeping candidate).
- Designer docs stay public on purpose: they are help/marketing content, not
  source.

---

## 8 · DNS, domains, email (Cloudflare zone `elysiumui.com`)

Registrar: **Dynadot** (renewals there); nameservers → **Cloudflare** (Free
plan). All web records are Cloudflare-proxied (orange cloud), so `dig` shows
CF edge IPs — real targets are only visible in the CF DNS dashboard.

| Record | Type | Target | Notes |
|---|---|---|---|
| `elysiumui.com` (apex) | CNAME (flattened), proxied | `elysium.pages.dev` → **after cutover** `elysiumui-website.pages.dev` | must match the Pages domain attachment (§6) |
| `www` | CNAME, proxied | same as apex | |
| `docs` | CNAME, proxied | `elysiumui.github.io` | GitHub Pages custom domain on `elysiumui/elysium` |
| `designer` | CNAME, proxied | `elysium-designer-docs.pages.dev` | |
| MX / SPF TXT / DKIM | — | Purelymail values | **DNS-only (grey cloud)** — proxying mail records breaks them |

Email: **Purelymail** hosts `support@elysiumui.com` (also the PyLocket
fulfillment reply-to).

---

## 9 · Secrets, tokens, accounts — security posture

### GitHub Actions secrets (current inventory)

| Repo | Secret | What it is |
|---|---|---|
| `klamaute/Elysium` | `CLOUDFLARE_API_TOKEN` | CF token (named "elysium-designer-docs" in the CF dashboard): **Account → Cloudflare Pages → Edit** + **Zone → DNS → Edit** (elysiumui.com, added 2026-07-03) |
| | `CLOUDFLARE_ACCOUNT_ID` | CF account id (not secret-sensitive, kept as a secret anyway) |
| `elysiumui/elysium` | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | same token value (for the designer-docs deploy) |
| `klamaute/elysium-designer` | `FRAMEWORK_REPO_TOKEN` | fine-grained read-only PAT for `elysiumui/elysium` — **UNUSED since the framework went public; delete it** |

PyPI uses **Trusted Publishing** — no token exists to leak. The public repo
has environments `pypi` and `github-pages`.

### Rules learned the hard way

- **Never put API tokens in Cloudflare Pages project env vars** — they are
  not a secret store (this briefly happened; the values were deleted).
  Secrets live in GitHub Actions secrets only.
- Editing a CF token's **permissions** keeps its value — GitHub secrets stay
  valid. Rotating (rolling) it changes the value → update both repos.
- Fine-grained PATs, minimal scope, 1-year expiry, single-repo selection.
- The **private monorepo can never be made public** — its history contains
  the full Designer source from before the split. The public repo was created
  with fresh history for exactly this reason.
- Apple Developer (Lamaute Labs LLC) signs Designer builds; signing
  credentials are **not** in CI — no signing secrets exist in any repo.

### Account inventory (who to log into)

GitHub `klamaute` + org `elysiumui` · PyPI `lamautelabs` · Cloudflare (zone +
Pages + the API token) · Dynadot (registrar only) · Purelymail (email) ·
PyLocket (Designer distribution/licensing) · Stripe (under review) · Apple
Developer (Lamaute Labs LLC).

---

## 10 · CI/workflow map

### `klamaute/Elysium` (monorepo)

| Workflow | Trigger | Does |
|---|---|---|
| `build.yml` | push/PR | the quality gate: cargo test (3 OS) + clippy/fmt + pytest |
| `docs.yml` | docs paths | mkdocs → gh-pages (vestigial here — live deploy is the public repo's) |
| `docs-designer.yml` | designer-docs paths | mkdocs → wrangler → CF Pages `elysium-designer-docs` (live) |
| `release-library.yml` | `v*` tags / dispatch | wheels + sdist (kept in sync with the public copy; PyPI publish fires only from the public repo) |
| `build-binaries.yml` | dispatch / tags | PyInstaller onefile example apps (has a dangling `designer` target — harmless) |
| `website.yml` | `website/**` push | Astro build → wrangler → CF Pages `elysiumui-website` (§6) |
| `cf-domain-move.yml` | dispatch | ops tool: move www/apex between Pages projects + retarget DNS atomically |

### `elysiumui/elysium` (public)

Same `build.yml`, `docs.yml` (live docs deploy), `docs-designer.yml`,
`build-binaries.yml`, and `release-library.yml` **with the `publish-pypi`
job** (environment `pypi`, OIDC).

### `klamaute/elysium-designer`

`release-designer.yml` — the four raw artifacts + smoke tests (§5).

---

## 11 · Open items (as of 2026-07-03)

1. **Execute the website domain cutover** (§6) — merge PR #5, dispatch
   `cf-domain-move.yml -f target=elysiumui-website`, verify, then delete the
   old `elysium` Pages project.
2. **Stripe approval** → set `designer.buyUrl` in
   `website/src/data/downloads.ts` (one line) → push (auto-deploys).
3. **Delete `FRAMEWORK_REPO_TOKEN`** from `klamaute/elysium-designer` (unused).
4. Optional: ask GitHub Support to GC the orphaned pre-scrub commits on
   `elysiumui/elysium`.
5. Butterfly hero art: verify provenance or commission the Blue Morpho model
   (`examples/butterfly/BLUE_MORPHO_INTRO_SPEC.md`).
6. Optional: USPTO registration for the "Elysium UI" mark; periodic legal
   review of terms/EULA/privacy (content lives in the three
   `website/src/pages/*.astro` files).
7. Housekeeping: tick "Enforce HTTPS" on the GitHub Pages settings of
   `elysiumui/elysium` (CF already forces HTTPS at the edge, so low stakes);
   consider disabling the monorepo's vestigial `docs.yml` gh-pages push.
