# API stability & versioning

As of **1.0.0**, Elysium follows [Semantic Versioning](https://semver.org)
strictly. This page is the contract: what's covered, how breaking changes are
made, and how deprecations work.

## What is "public API"

The public API is exactly the names exported by each module's `__all__`:

- The top-level `elysium` package (`App`, `Window`, `DisplayList`, …).
- The public sub-modules: `components` (+ `dataentry`, `scroll`, `virtual`),
  `layout`, `theme`, `anim`, `reactive`, `input`, `text`, `dialogs`,
  `modelview`, `concurrency`, `windowing`, `native`, `i18n`, `locale`,
  `settings`, `testing`, `focus`, `accessibility`.

Anything **not** in `__all__` is private, as is any name beginning with an
underscore (`_native`, `_window_ext`, `_deprecation`, …) and the entire
`elysium._native` extension surface. Private API may change or vanish in any
release.

The committed surface is snapshotted in `tests/_api_surface.json` and enforced
by `tests/test_public_api.py` — the public API cannot change by accident.

## Semver contract

| Bump | Means |
| --- | --- |
| **Major** (`2.0.0`) | A breaking change to the public API or the `.esk` `schema_version`. Only here may public names be removed or change behavior incompatibly. |
| **Minor** (`1.1.0`) | New public API or features, fully backward-compatible. May *add* deprecations. |
| **Patch** (`1.0.1`) | Bug fixes and polish; no public API change. |

## Deprecation path

Nothing public is removed without a deprecation window:

1. **Deprecate in a minor** — the old API keeps working but is marked with
   `@elysium.deprecated(...)` (or `elysium.deprecated_alias(...)` for renames),
   which emits a `DeprecationWarning` pointing at the replacement, and a
   `CHANGELOG.md` entry under *Deprecated*.
2. **Warn for at least one minor release** — users get time to migrate; the
   warning names the `removal=` version.
3. **Remove only in the next major** — at which point it leaves `__all__`, the
   surface snapshot is regenerated, and the removal is listed under *Removed*.

```python
from elysium import deprecated

@deprecated(since="1.2", removal="2.0", alt="new_widget")
def old_widget(*args, **kwargs):
    ...
```

Run your test suite with `-W error::DeprecationWarning` to fail on any
deprecated usage before it's removed.

## Experimental API

APIs that still need to move before they're frozen are marked **experimental**
in their docstring (and may live under a clearly-named module). Experimental
names are excluded from the semver guarantee; they graduate to stable — joining
`__all__` and the surface snapshot — once they've settled.

## Native ABI

Wheels are built `abi3` for CPython ≥ 3.10, so a single wheel works across 3.10+
without recompilation. The compiled extension's version is surfaced as
`elysium.__version__` and tracks the package version.

## Changing the public API (maintainers)

A deliberate public-API change is a reviewed act: update the code, run
`UPDATE_API_SURFACE=1 pytest tests/test_public_api.py` to regenerate
`tests/_api_surface.json`, and add a `CHANGELOG.md` entry (removals/renames must
follow the deprecation path above). The surface test then locks the new shape.
