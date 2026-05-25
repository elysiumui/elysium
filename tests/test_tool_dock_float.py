"""Tests for the floatable + dockable Tool Properties dock.

The Tool Properties dock (Brush Chip + 6 sliders + Recents) was
originally pinned to the bottom-centre of the form area, where it
covered the active brush stroke. The dock/float pass added a drag
grip on the header so it can be moved anywhere or pinned back to the
bottom-centre.

These tests construct a Designer via ``object.__new__(...)`` to skip
the constructor (which opens an OS window) and exercise the rect +
state helpers directly.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest


def _load_designer_module():
    sys.path.insert(0, "elysium-designer")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "elysium_designer_main_td", "elysium-designer/__main__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("elysium_designer_main_td", mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def designer_mod():
    return _load_designer_module()


def _make_designer(designer_mod, tmp_path: pathlib.Path):
    d = object.__new__(designer_mod.Designer)
    d.tool = designer_mod.TOOL_BRUSH        # so _dock_visible() is True
    d.tool_dock_mode = "docked"
    d.tool_dock_float_pos = None
    d._tool_dock_drag_offset = None
    d._tool_dock_drag_just_started = False
    d._anim_clock_t = 0.0
    # _form_rect() needs the placement + form-area state; mirror the
    # __init__ defaults a real Designer would set.
    d.placements = []
    d.sel_kind = "none"
    d.sel_idx = -1
    d.timeline_visible = False
    d.canvas_zoom = 1.0
    d.canvas_pan_x = 0.0
    d.canvas_pan_y = 0.0
    designer_mod._DESIGNER_PREFS_PATH = tmp_path / "designer-prefs.json"
    return d


def test_tool_dock_starts_docked(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    assert d.tool_dock_mode == "docked"
    r = d._dock_rect()
    assert r is not None
    dx, dy, dw, dh = r
    # Docked: pinned to bottom-centre of form area.
    fx, fy, fw, fh = d._form_rect()
    assert dx == pytest.approx(fx + (fw - dw) / 2.0)
    assert dy == pytest.approx(fy + fh - dh - 16.0)


def test_tool_dock_float_rect_uses_float_pos(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.tool_dock_mode = "floating"
    d.tool_dock_float_pos = (250.0, 350.0)
    r = d._dock_rect()
    assert r is not None
    dx, dy, _, _ = r
    assert dx == 250.0
    assert dy == 350.0


def test_tool_dock_float_seeds_on_first_open(designer_mod, tmp_path):
    """Floating without a saved position seeds at the docked
    location so the visual lift is obvious but nothing jumps."""
    d = _make_designer(designer_mod, tmp_path)
    d.tool_dock_mode = "floating"
    d.tool_dock_float_pos = None
    r = d._dock_rect()
    assert r is not None
    assert d.tool_dock_float_pos is not None
    fx, fy, fw, fh = d._form_rect()
    dw, dh = min(640.0, fw - 40.0), 84.0
    assert d.tool_dock_float_pos[0] == pytest.approx(
        fx + (fw - dw) / 2.0)
    assert d.tool_dock_float_pos[1] == pytest.approx(
        fy + fh - dh - 16.0)


def test_tool_dock_float_clamped_to_screen(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.tool_dock_mode = "floating"
    d.tool_dock_float_pos = (10_000.0, 10_000.0)
    r = d._dock_rect()
    assert r is not None
    dx, dy, dw, dh = r
    assert dx + dw <= designer_mod.WIDTH
    assert dy + dh <= designer_mod.HEIGHT - designer_mod.STATUS_H


def test_tool_dock_grip_rect_inside_header(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    grip = d._tool_dock_grip_rect()
    r = d._dock_rect()
    assert grip is not None and r is not None
    gx, gy, gw, gh = grip
    dx, dy, dw, _ = r
    assert gx == dx and gy == dy
    assert gh == 22.0
    # Docked grip spans the full header width.
    assert gw == dw


def test_tool_dock_floating_grip_reserves_redock_button(designer_mod,
                                                         tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.tool_dock_mode = "floating"
    d.tool_dock_float_pos = (300.0, 200.0)
    grip = d._tool_dock_grip_rect()
    r = d._dock_rect()
    assert grip is not None and r is not None
    _, _, gw, _ = grip
    _, _, dw, _ = r
    assert dw - gw == pytest.approx(18.0)


def test_tool_dock_redock_rect_in_header_top_right(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.tool_dock_mode = "floating"
    d.tool_dock_float_pos = (300.0, 200.0)
    rrect = d._tool_dock_redock_rect()
    r = d._dock_rect()
    assert rrect is not None and r is not None
    rx, ry, rw, rh = rrect
    dx, dy, dw, _ = r
    assert rx + rw <= dx + dw
    assert ry >= dy and ry + rh <= dy + 22


def test_tool_dock_zone_rect_matches_docked_position(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    docked_rect = d._dock_rect()
    zone = d._tool_dock_zone_rect()
    assert zone == docked_rect


def test_tool_dock_zone_contains_check(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    zone = d._tool_dock_zone_rect()
    assert zone is not None
    zx, zy, zw, zh = zone
    assert d._tool_dock_zone_contains(
        (zx + zw / 2, zy + zh / 2)) is True
    assert d._tool_dock_zone_contains(
        (zx + zw + 500, zy)) is False
    assert d._tool_dock_zone_contains(None) is False


def test_tool_dock_state_persists(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.tool_dock_mode = "floating"
    d.tool_dock_float_pos = (250.0, 350.0)
    d._save_tool_dock_state()
    prefs = json.loads(
        designer_mod._DESIGNER_PREFS_PATH.read_text())
    assert prefs["tool_dock_mode"] == "floating"
    assert prefs["tool_dock_float_pos"] == [250.0, 350.0]


def test_tool_dock_rect_returns_none_when_form_too_narrow(designer_mod,
                                                           tmp_path,
                                                           monkeypatch):
    """Very narrow forms skip the dock entirely (the sliders remain
    reachable via the Properties pane). The rect helper returns None
    and the grip / zone rects return None too."""
    d = _make_designer(designer_mod, tmp_path)
    monkeypatch.setattr(d, "_form_rect", lambda: (0.0, 0.0, 100.0, 100.0))
    assert d._dock_rect() is None
    assert d._tool_dock_grip_rect() is None
    assert d._tool_dock_zone_rect() is None
    assert d._tool_dock_redock_rect() is None
