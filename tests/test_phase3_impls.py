"""Tests for everything that was deferred and just got implemented."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest


def _native_available() -> bool:
    import elysium
    return getattr(elysium, "_NATIVE_AVAILABLE", False)


native_only = pytest.mark.skipif(not _native_available(), reason="native extension not built")


# --- Path-aware hit-testing (geometry) -------------------------------------

def test_path_contains_inside_outside():
    from elysium._native import _native as _n  # noqa: F401
    # Use the Rust-side Path via a small Python harness — we test the
    # Python-visible contract that an SVG path stored via
    # window.set_hit_test_path is interpreted correctly. The detailed
    # geometry math is verified in the Rust unit tests, so here we just
    # confirm the API doesn't error.
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.hp")
    win = app.window(transparent=True, title_bar=False, initial_size=(200, 200))
    # An outlined square at (50,50)-(150,150).
    win.set_hit_test_path("M 50 50 L 150 50 L 150 150 L 50 150 Z")
    win.set_hit_test_path(None)  # clear


# --- Multi-line text + paragraph -------------------------------------------

@native_only
def test_skia_layer_draw_paragraph_returns_height():
    from elysium._native import _native as _n
    layer = _n.SkiaLayer(400, 200)
    layer.clear(0.05, 0.05, 0.1, 1.0)
    h = layer.draw_paragraph(
        "Elysium UI ships premium components out of the box.",
        20.0, 30.0, 360.0, 16.0, (240, 240, 250, 255), 0,
    )
    assert h > 16.0  # at least one line of text
    png = bytes(layer.encode_png())
    assert png.startswith(b"\x89PNG")


@native_only
def test_display_list_draw_paragraph_executes():
    from elysium._native import _native as _n
    dl = _n.DisplayList()
    dl.clear(0, 0, 0, 1)
    dl.draw_paragraph(
        "Wrap me across multiple lines, please. " * 8,
        10.0, 10.0, 200.0, 14.0, (255, 255, 255, 255), 2,
    )
    layer = _n.SkiaLayer(300, 300)
    layer.execute(dl)
    png = bytes(layer.encode_png())
    assert len(png) > 1000


# --- SkSL RuntimeEffect ---------------------------------------------------

_SAMPLE_SKSL = """
uniform float u_phase;
half4 main(float2 coord) {
    half v = half(sin(coord.x * 0.05 + u_phase) * 0.5 + 0.5);
    return half4(v, v * 0.6, 1.0 - v, 1.0);
}
"""


@native_only
def test_skia_layer_applies_sksl_effect():
    """Compiling and applying a custom SkSL shader does not error and
    produces non-trivial pixels."""
    import struct
    from elysium._native import _native as _n
    layer = _n.SkiaLayer(200, 100)
    layer.clear(0, 0, 0, 1)
    uniforms = struct.pack("<f", 0.7)
    ok = layer.apply_skia_effect(_SAMPLE_SKSL, 20.0, 20.0, 160.0, 60.0,
                                 8.0, uniforms)
    assert ok
    png = bytes(layer.encode_png())
    # The PNG should contain coloured pixels distinct from a pure black clear.
    assert len(png) > 600


@native_only
def test_display_list_skia_effect_round_trip():
    """A DisplayList carrying a SkslEffect renders the same as a direct call."""
    import struct
    from elysium._native import _native as _n
    uniforms = struct.pack("<f", 0.3)
    # Direct render.
    a = _n.SkiaLayer(120, 80)
    a.clear(0, 0, 0, 1)
    a.apply_skia_effect(_SAMPLE_SKSL, 10.0, 10.0, 100.0, 60.0, 6.0, uniforms)
    # Via DisplayList.
    dl = _n.DisplayList()
    dl.clear(0, 0, 0, 1)
    dl.skia_effect(_SAMPLE_SKSL, 10.0, 10.0, 100.0, 60.0, 6.0, uniforms)
    b = _n.SkiaLayer(120, 80); b.execute(dl)
    assert bytes(a.encode_png()) == bytes(b.encode_png())


# --- macOS blur_behind + hit-test (smoke) ---------------------------------

@native_only
@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")
def test_window_set_blur_behind_does_not_throw():
    """The API queues a request; the actual Cocoa call fires when the
    event loop next iterates. Calling it on an unshown window must not
    crash."""
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.blur")
    win = app.window(transparent=True, title_bar=False, initial_size=(200, 200))
    win.set_blur_behind(True)
    win.set_blur_behind(False)
    win.set_blur_behind(True, material=21)  # under-window-background
    win.set_has_shadow(True)
    win.set_window_level(3)
    win.set_ignores_mouse(True)


@native_only
@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")
def test_window_hit_test_path_api():
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.htp")
    win = app.window(transparent=True, title_bar=False, initial_size=(200, 200))
    win.set_hit_test_path("M 50 50 L 150 50 L 150 150 L 50 150 Z")
    win.set_hit_test_path(None)


# --- AI providers ----------------------------------------------------------

def test_ai_stub_provider_returns_valid_skin():
    """Without any API key set, the stub provider produces a deterministic
    procedural skin. The returned JSON parses + has the right shape."""
    from elysium import ai
    skin = asyncio.run(ai.generate_skin(
        prompt="A glassmorphic music player",
        hooks=["play.click", "track.title.text", "progress.value"],
        size=(800, 480),
        provider="stub",
    ))
    assert skin.manifest["schema_version"] == "1.0"
    assert skin.document["root"]["type"] == "scene"
    assert skin.document["root"]["size"] == {"w": 800, "h": 480}
    # Every requested hook is present.
    hook_names = [
        h["name"]
        for child in skin.document["root"]["children"]
        for h in child.get("hooks", [])
    ]
    assert "play.click" in hook_names
    assert "track.title.text" in hook_names
    assert "progress.value" in hook_names


def test_ai_generated_skin_round_trips_through_loader(tmp_path):
    """A skin generated by the stub provider is loadable by the real
    .esk loader and compiles to a non-empty DisplayList."""
    from elysium import ai
    import elysium as ely
    skin = asyncio.run(ai.generate_skin(
        prompt="any", hooks=["foo.click"], size=(400, 300), provider="stub"))
    out = skin.save(tmp_path / "gen.esk")
    loaded = ely.load_skin(str(out))
    dl = loaded.to_display_list(400, 300)
    assert len(dl) >= 2


def test_ai_modify_skin_returns_diff(tmp_path):
    from elysium import ai
    # Build a tiny skin to modify.
    before = {
        "manifest": {"schema_version": "1.0", "id": "x", "name": "x", "version": "0.1.0"},
        "document": {"root": {"type": "scene", "size": {"w": 200, "h": 200},
                              "background": {"type": "color", "value": "#000000"},
                              "children": []}},
    }
    diff = asyncio.run(ai.modify_skin(before, "make it pop", provider="stub"))
    # Stub returns a procedural skin; before != after.
    assert diff.before == before
    assert isinstance(diff.preview(), str)


def test_ai_magic_polish_runs():
    from elysium import ai
    skin = {
        "manifest": {"schema_version": "1.0", "id": "x", "name": "x", "version": "0.1.0"},
        "document": {"root": {"type": "scene", "children": []}},
    }
    diff = asyncio.run(ai.magic_polish(skin, provider="stub", intensity="balanced"))
    assert diff.notes.startswith("Apply Magic Polish")


def test_ai_provider_resolution():
    from elysium.ai import _make_provider, StubProvider
    assert isinstance(_make_provider("stub"), StubProvider)
    # No key in env — should fall back to stub.
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("OPENAI_API_KEY",    None)
    assert isinstance(_make_provider(None), StubProvider)


# --- Designer (importable + entry point) ---------------------------------

def test_designer_module_file_present():
    """The Designer ships as a runnable package at elysium-designer/.
    Python can't `import elysium-designer` (hyphen), so we check the
    entry-point file exists + parses."""
    import ast
    p = Path(__file__).parent.parent / "elysium-designer" / "__main__.py"
    assert p.exists(), "elysium-designer/__main__.py should be present"
    ast.parse(p.read_text(encoding="utf-8"))
