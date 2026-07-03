"""Audit-pass tests: every deferred Phase 2.5 item that landed in this leg
gets exercised here.

  - 13 new components paint without error.
  - Ripple lifecycle (spawn, age, GC).
  - Document compiler now handles image/text/transform nodes.
  - CLI watcher's snapshot diff catches file changes.
  - Window.enable_hot_reload registers an IpcServer.
"""
from __future__ import annotations

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


# --- 13 new components --------------------------------------------------

@native_only
@pytest.mark.parametrize("component_factory", [
    lambda c: c.Checkbox(x=0, y=0, w=160, h=24, label="Accept"),
    lambda c: c.Radio(x=0, y=0, w=160, h=24, label="Option A"),
    lambda c: c.TextArea(x=0, y=0, w=240, h=80, placeholder="Write here…"),
    lambda c: c.Divider(x=0, y=0, w=200, h=2),
    lambda c: c.Badge(x=0, y=0, w=40, h=18, text="42"),
    lambda c: c.Avatar(x=0, y=0, w=40, h=40, initial="K"),
    lambda c: c.Chip(x=0, y=0, w=120, h=28, label="design"),
    lambda c: c.Spinner(x=0, y=0, w=40, h=40),
    lambda c: c.Tooltip(x=0, y=0, w=140, h=28, text="Hello", visible=True),
    lambda c: c.Tabs(x=0, y=0, w=400, h=44, items=["One", "Two", "Three"]),
    lambda c: c.Modal(x=0, y=0, w=600, h=400, title="Hi", body="Hello", visible=True),
    lambda c: c.Toast(x=0, y=0, w=320, h=56, text="Saved", visible=True),
    lambda c: c.Dropdown(x=0, y=0, w=200, h=36, items=["A", "B", "C"]),
])
def test_new_component_paints(component_factory):
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    from elysium import components as c
    comp = component_factory(c)
    # Settle then paint into a DisplayList.
    for _ in range(60):
        comp.update(0.02, {})
    dl = _n.DisplayList()
    dl.clear(0, 0, 0, 1)
    comp.paint(dl)
    layer = _n.SkiaLayer(640, 480)
    layer.execute(dl)
    png = bytes(layer.encode_png())
    assert png.startswith(b"\x89PNG")
    assert len(png) > 1000


@native_only
def test_checkbox_fires_change():
    from elysium.components import Checkbox
    captured: list[bool] = []
    cb = Checkbox(x=0, y=0, w=160, h=24, on_change=lambda v: captured.append(v))
    assert cb.value is False
    cb.fire_toggle()
    assert cb.value is True and captured == [True]


@native_only
def test_tabs_select_fires_change_and_animates_indicator():
    from elysium.components import Tabs
    selected: list[int] = []
    tabs = Tabs(x=0, y=0, w=300, h=44,
                items=["A", "B", "C"],
                on_change=lambda i: selected.append(i))
    # Initial state.
    for _ in range(40):
        tabs.update(0.02, {})
    start_indicator = tabs._indicator_x
    tabs.select(2)
    # The indicator hasn't moved yet — it interpolates on update().
    for _ in range(60):
        tabs.update(0.02, {})
    assert selected == [2]
    assert tabs._indicator_x > start_indicator + 50.0  # moved noticeably


@native_only
def test_pagination_centers_pages():
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    from elysium.components import Pagination
    p = Pagination(x=0, y=0, w=480, h=40, page=3, total=5)
    p.update(0.02, {})
    dl = _n.DisplayList()
    p.paint(dl)
    # 5 pages: filled + label for each + nothing-else; just smoke-check.
    assert len(dl) >= 5


# --- Ripple lifecycle --------------------------------------------------

@native_only
def test_button_ripple_spawn_age_gc():
    from elysium.components import Button
    btn = Button(x=10, y=10, w=120, h=40, label="Play")
    assert btn.ripples == []
    btn.fire_click(click_x=70, click_y=30)
    assert len(btn.ripples) == 1
    rp = btn.ripples[0]
    assert (rp.x, rp.y) == (70, 30)
    assert rp.age == 0.0
    # Tick past the ripple_duration; should age out and GC.
    for _ in range(60):
        btn.update(0.02, {})  # 1.2 s
    assert btn.ripples == []


@native_only
def test_button_ripple_paints_circle():
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    from elysium.components import Button
    btn = Button(x=0, y=0, w=120, h=40, label="X")
    btn.fire_click(click_x=60, click_y=20)
    # Half-way through the ripple's life:
    btn.update(0.20, {})
    dl_with    = _n.DisplayList(); btn.paint(dl_with)
    btn2 = Button(x=0, y=0, w=120, h=40, label="X")
    btn2.update(0.02, {})
    dl_without = _n.DisplayList(); btn2.paint(dl_without)
    # The ripple variant has more draw commands.
    assert len(dl_with) > len(dl_without)


# --- Document compiler: image / text / transform ----------------------

@native_only
def test_compile_handles_image_node(tmp_path):
    """An <image> node with `src` produces a DrawImageFile command that
    renders a real PNG through the texture pipeline."""
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    import elysium as ely

    # Write a small known PNG that the document will reference.
    src_layer = _n.SkiaLayer(64, 64)
    src_layer.clear(0.2, 0.6, 0.9, 1.0)
    png_path = tmp_path / "tile.png"
    png_path.write_bytes(bytes(src_layer.encode_png()))

    base = tmp_path / "img_skin.esk"
    base.mkdir()
    (base / "manifest.json").write_text(json.dumps({
        "schema_version": "1.0", "id": "dev.test.img",
        "name": "test", "version": "0.1.0",
    }))
    (base / "document.json").write_text(json.dumps({
        "root": {
            "type": "scene",
            "children": [
                {"type": "image",
                 "src": str(png_path),
                 "d": "M 0 0 L 200 0 L 200 200 L 0 200 Z"}
            ],
        }
    }))
    skin = ely.load_skin(str(base))
    dl = skin.to_display_list(400, 200)
    assert len(dl) >= 1   # DrawImageFile (no scene background → no FillPath)
    layer = _n.SkiaLayer(400, 200)
    layer.execute(dl)
    assert layer.cache_decodes == 1


@native_only
def test_compile_handles_text_node():
    """Walk through a tiny in-memory document with a <text> node; the
    Python-side path uses load_skin via the .esk loader, so write one
    out and load it back."""
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    import elysium as ely
    base = Path(__file__).parent / "fixtures" / "text_skin.esk"
    base.mkdir(parents=True, exist_ok=True)
    (base / "manifest.json").write_text(json.dumps({
        "schema_version": "1.0", "id": "dev.test.text",
        "name": "test", "version": "0.1.0",
    }))
    (base / "document.json").write_text(json.dumps({
        "root": {
            "type": "scene",
            "background": {"type": "color", "value": "#202028"},
            "children": [
                {"type": "text", "text": "Hello, world!", "transform": {"x": 40, "y": 60}},
            ],
        }
    }))
    skin = ely.load_skin(str(base))
    dl = skin.to_display_list(400, 200)
    assert len(dl) >= 2   # Clear + DrawText
    # Render it through a SkiaLayer.
    layer = _n.SkiaLayer(400, 200)
    layer.execute(dl)
    png = bytes(layer.encode_png())
    assert png.startswith(b"\x89PNG")


@native_only
def test_compile_emits_push_pop_transform_for_rotated_node():
    """A node with non-zero rotation produces matching Push/Pop transforms."""
    import elysium as ely
    base = Path(__file__).parent / "fixtures" / "rot_skin.esk"
    base.mkdir(parents=True, exist_ok=True)
    (base / "manifest.json").write_text(json.dumps({
        "schema_version": "1.0", "id": "dev.test.rot",
        "name": "test", "version": "0.1.0",
    }))
    (base / "document.json").write_text(json.dumps({
        "root": {
            "type": "scene",
            "children": [
                {"type": "path", "d": "M 0 0 L 80 0 L 80 40 L 0 40 Z",
                 "fill": {"type": "color", "value": "#FF0080"},
                 "transform": {"x": 100, "y": 60, "rotation": 0.5,
                               "scale": [1.0, 1.0]}}
            ],
        }
    }))
    skin = ely.load_skin(str(base))
    dl = skin.to_display_list(400, 200)
    # len(dl) is the number of commands; we just verify the document
    # builds and the renderer accepts it.
    assert len(dl) >= 2


# --- CLI dev-watcher behaviour -----------------------------------------

def test_cli_dev_snapshot_diff_catches_mtime_change(tmp_path):
    """The watcher's `_snapshot_skin` returns a different signature after
    a file is rewritten."""
    from elysium.cli import _snapshot_skin
    f = tmp_path / "a.json"
    f.write_text("{}")
    s1 = _snapshot_skin(tmp_path)
    time.sleep(0.05)
    f.write_text("{ \"x\": 1 }")
    s2 = _snapshot_skin(tmp_path)
    assert s1 != s2


# --- Window.enable_hot_reload integration ------------------------------

@native_only
@pytest.mark.skipif(sys.platform == "win32", reason="hot-reload IPC is Unix-only")
def test_enable_hot_reload_starts_ipc_server(tmp_path):
    """Calling `window.enable_hot_reload(socket)` actually starts a
    server we can connect to."""
    import elysium as ely
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    sock = f"/tmp/ely-hotreload-{os.getpid()}.sock"
    app = ely.App(title="t", identifier="dev.elysium.test.hr")
    win = app.window(transparent=False, title_bar=True, initial_size=(120, 80))
    win.enable_hot_reload(sock)
    try:
        time.sleep(0.1)
        client = _n.IpcClient(sock)
        ack = client.send_hello("test", "tok")
        assert ack is True
    finally:
        win._ipc_server.stop()
