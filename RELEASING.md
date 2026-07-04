# RELEASING — deployment checklist

**This is the checklist for shipping a framework (and Designer) release without
a version or deployment mistake.** It exists because 1.1.3 was published with
the Rust workspace still at 1.1.2, so the wheel reported the wrong
`__version__`. Follow it top to bottom; don't skip the post-publish gate.

Private doc — do **not** mirror to the public repo (it describes the private
monorepo + mirror flow). Companion to `OPERATIONS.md` (§4 = release, §5 =
Designer).

Legend: ⚙️ = enforced by CI (can't be skipped) · ✋ = manual.

---

## 0 · One-time truths (why this is easy to get wrong)

The framework version lives in **three** files that must always agree:

| File | Feeds | Notes |
|---|---|---|
| `pyproject.toml` `[project] version` | the **wheel/sdist** version | what `pip install` reports |
| `elysium-native/Cargo.toml` `[workspace.package] version` | the native module's `_n.__version__` (`env!("CARGO_PKG_VERSION")`) | **the one that got missed in 1.1.3** |
| `python/elysium/__init__.py` fallback literal | source-tree fallback only | `__version__` now primarily reads dist metadata |

`elysium.__version__` reads from **installed distribution metadata** first, so a
properly built wheel always self-reports correctly. But keep all three in sync
anyway — `_n.__version__` is used in frozen apps and by tooling.

**Don't hand-edit the three.** Run `python scripts/bump-version.py X.Y.Z`, which
updates all of them atomically.

---

## 1 · Prepare the release (in the private monorepo)

- [ ] ✋ Decide the version `X.Y.Z` (patch = fixes only; strict semver — see
      `docs/guides/api-stability.md`).
- [ ] ✋ `python scripts/bump-version.py X.Y.Z` (bumps pyproject + Cargo + fallback).
- [ ] ✋ Update `CHANGELOG.md`: move `[Unreleased]` items into a new
      `## [X.Y.Z] - <date>` section.
- [ ] ✋ `cargo check -p ely-py` (updates `Cargo.lock` to the new version) +
      `cargo clippy -p ely-py` + `cargo fmt -p ely-py -- --check`.
- [ ] ✋ Full test suite green: `.venv/bin/python -m pytest tests/ python/elysium -q`.
- [ ] ✋ Open a `release/X.Y.Z` PR on `klamaute/Elysium` (source of truth).

## 2 · Mirror to the public repo

- [ ] ✋ Copy the changed **framework** files to `elysiumui/elysium` on a
      `release/X.Y.Z` branch. Respect the OPERATIONS.md §2 exclusion list —
      never mirror `website/`, `OPERATIONS.md`, `RELEASING.md`, `.claude/`,
      `LAUNCH-CHECKLIST.md`, or the private workflows.
- [ ] ⚙️ On push/PR, `build.yml`'s **`version consistency`** job fails if
      `pyproject` ≠ Rust workspace version. Green = the two agree.
- [ ] ✋ Open the public `release/X.Y.Z` PR.

## 3 · Publish to PyPI

- [ ] ✋ Merge the public PR to `main` (two-party review — the classifier blocks
      self-merge; a human clicks Merge).
- [ ] ✋ Tag at `main` HEAD:
      `gh api -X POST repos/elysiumui/elysium/git/refs -f ref=refs/tags/vX.Y.Z -f sha=$(gh api repos/elysiumui/elysium/git/ref/heads/main --jq .object.sha)`
- [ ] ⚙️ `release-library.yml` builds 4 abi3 wheels + sdist, drafts a GitHub
      Release, and `publish-pypi` uploads via Trusted Publishing (no token).
- [ ] ⚙️ **`verify-published`** installs `elysium-ui==X.Y.Z` from PyPI in a clean
      env and asserts `elysium.__version__ == X.Y.Z`. **This is the gate that
      would have caught 1.1.3 — the release run is not green until it passes.**
- [ ] ✋ Merge the private `release/X.Y.Z` PR (keep source of truth consistent).

## 4 · Post-publish sanity (✋, 2 minutes)

- [ ] `pip index versions elysium-ui` (or the pypi.org page) shows X.Y.Z with
      **5 files**: 4 wheels (macOS arm64/x86_64, manylinux, win) + `.tar.gz` sdist.
- [ ] Fresh venv (Python ≥ 3.10): `pip install elysium-ui==X.Y.Z` →
      `python -c "import elysium; assert elysium.__version__ == 'X.Y.Z'"`.
      (Redundant with the CI gate, but it's the definitive user-facing check.)

## 5 · Designer release (if shipping a Designer build)

See OPERATIONS.md §5 for the full pipeline. Version-relevant steps:

- [ ] ✋ In `klamaute/elysium-designer` `release-designer.yml`, bump the pin
      `pip install elysium-ui==X.Y.Z` to the new version.
- [ ] ✋ Dispatch the build. ⚙️ Its own gates assert the bundled interpreter is
      Python 3.13 (build-interpreter, PyInstaller-log, bundled-runtime scan) and
      the smoke tests launch the frozen app (macOS ×2, Windows; Linux has no
      display).
- [ ] ✋ Download the PyLocket-ready artifacts and upload to PyLocket.

## 6 · If something is wrong after publish

- **PyPI is immutable** — you can't overwrite X.Y.Z. Ship a new patch
  (X.Y.Z+1) with the fix.
- **Yank** the bad version on pypi.org (Manage → Releases → Yank) so
  `pip install` skips it and pins to it warn. Needs the `lamautelabs` PyPI
  account — Trusted Publishing does not grant yank permission.
- Precedent: 1.1.3 (wrong `__version__`) → 1.1.4 (fixed) + yank 1.1.3.
