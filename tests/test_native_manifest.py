"""Invariants of the native workspace manifests (headless; no extension).

The repository does not track ``elysium-native/Cargo.lock`` (see
``.gitignore``), so every checkout resolves the dependency graph afresh.
Two manifest details therefore matter more than usual:

* An exact ``=x.y.z`` requirement anywhere in the workspace forces that one
  version into every fresh resolve and breaks the build as soon as another
  dependency needs a newer patch release (the ``cc = "=1.4.0"`` pin did
  exactly that).  Caret requirements only.
* ``[patch.crates-io] accesskit_macos`` points at a vendored, modified copy
  of the crate.  Cargo has no target-conditional ``[patch]``; the entry is
  unconditional by design and is consumed during the platform-agnostic
  resolve on every host, so it never warns on Linux/Windows.  Its only
  consumer must stay behind ``cfg(target_os = "macos")``, its version must
  satisfy that consumer's requirement, and NOTICE must describe the copy
  actually shipped.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# tomllib is 3.11+; pyproject allows 3.10, where this file must skip, not error.
tomllib = pytest.importorskip("tomllib")

REPO = Path(__file__).resolve().parent.parent
NATIVE = REPO / "elysium-native"
VENDORED_ACCESSKIT = NATIVE / "vendor" / "accesskit_macos"


def _toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _requirement(spec) -> str:
    """The version requirement of a dependency entry (string or table)."""
    if isinstance(spec, str):
        return spec
    return str(spec.get("version", ""))


def _crate_manifests() -> list[Path]:
    members = sorted((NATIVE / "crates").glob("*/Cargo.toml"))
    assert members, "no workspace crates found"
    return members


# --- exact pins ---------------------------------------------------------------

def test_no_tracked_cargo_lock():
    """The premise of the pin rule: the lockfile is gitignored, not tracked."""
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "Cargo.lock" in ignored


def test_workspace_manifests_have_no_exact_version_pins():
    pinned = []
    for manifest in [NATIVE / "Cargo.toml", *_crate_manifests()]:
        doc = _toml(manifest)
        sections = [doc.get(k, {}) for k in
                    ("dependencies", "dev-dependencies", "build-dependencies")]
        # [workspace.dependencies] and [target.<cfg>.<kind>] tables too.
        sections.append(doc.get("workspace", {}).get("dependencies", {}))
        for target in doc.get("target", {}).values():
            for kind in ("dependencies", "dev-dependencies", "build-dependencies"):
                sections.append(target.get(kind, {}))
        for table in sections:
            for name, spec in table.items():
                if _requirement(spec).strip().startswith("="):
                    pinned.append(f"{manifest.relative_to(REPO)}: {name} = {spec!r}")
    assert not pinned, "exact pins block fresh resolves:\n" + "\n".join(pinned)


def test_ely_py_build_dep_cc_is_a_caret_requirement():
    build_deps = _toml(NATIVE / "crates" / "ely-py" / "Cargo.toml")["build-dependencies"]
    assert "cc" in build_deps, "ely-py's build.rs compiles vendored MikkTSpace C via cc"
    req = _requirement(build_deps["cc"])
    assert re.fullmatch(r"\^?1(\.\d+){0,2}", req), req


# --- [patch.crates-io] accesskit_macos --------------------------------------

def test_accesskit_macos_patch_points_at_the_vendored_fork():
    patch = _toml(NATIVE / "Cargo.toml")["patch"]["crates-io"]["accesskit_macos"]
    assert patch == {"path": "vendor/accesskit_macos"}
    assert (VENDORED_ACCESSKIT / "Cargo.toml").is_file()
    assert (VENDORED_ACCESSKIT / "ELYSIUM-PATCH.md").is_file()


def test_vendored_accesskit_macos_satisfies_its_only_consumer():
    vendored = _toml(VENDORED_ACCESSKIT / "Cargo.toml")["package"]
    assert vendored["name"] == "accesskit_macos"
    assert vendored["license"] == "MIT OR Apache-2.0"

    consumers = []
    for manifest in _crate_manifests():
        doc = _toml(manifest)
        for kind in ("dependencies", "dev-dependencies", "build-dependencies"):
            assert "accesskit_macos" not in doc.get(kind, {}), (
                f"{manifest.relative_to(REPO)}: accesskit_macos must be "
                "target-gated, not an unconditional dependency")
        for cfg, target in doc.get("target", {}).items():
            for kind in ("dependencies", "dev-dependencies", "build-dependencies"):
                if "accesskit_macos" in target.get(kind, {}):
                    consumers.append((manifest, cfg, _requirement(target[kind]["accesskit_macos"])))
    assert consumers, "nothing depends on accesskit_macos; drop the [patch]"
    for manifest, cfg, req in consumers:
        assert cfg == 'cfg(target_os = "macos")', (manifest, cfg)
        # A caret requirement "0.17" is satisfied by any 0.17.x.
        major_minor = re.fullmatch(r"\^?(\d+\.\d+)(\.\d+)?", req)
        assert major_minor, req
        assert vendored["version"].startswith(major_minor.group(1) + "."), (
            f"vendored {vendored['version']} does not satisfy {req}")


def test_notice_describes_the_vendored_accesskit_macos_copy():
    notice = (REPO / "NOTICE").read_text(encoding="utf-8")
    vendored = _toml(VENDORED_ACCESSKIT / "Cargo.toml")["package"]
    assert f"accesskit_macos {vendored['version']}" in notice
    vcs = json.loads((VENDORED_ACCESSKIT / ".cargo_vcs_info.json").read_text(encoding="utf-8"))
    assert vcs["git"]["sha1"] in notice
    assert "ELYSIUM-PATCH.md" in notice
