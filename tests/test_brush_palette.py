"""Tests for the unified single-strip brush palette.

The Designer's brush palette is one strip of 12 generic slots. Each
slot can hold a color, a texture, or be empty. Click semantics:

  - Left-click any slot   -> opens the Color menu popover
  - Right-click any slot  -> opens the Texture menu popover
  - Both popovers always include Apply / Clear / Cancel
  - Nothing fills automatically; the user picks, applies, or clears
    each slot explicitly.

These tests construct a Designer via ``object.__new__(...)`` to skip
the constructor (which opens an OS window) and exercise the dispatch
+ popover + persistence helpers directly.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest


# --- Helpers --------------------------------------------------------------

def _load_designer_module():
    sys.path.insert(0, "elysium-designer")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "elysium_designer_main", "elysium-designer/__main__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("elysium_designer_main", mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def designer_mod():
    return _load_designer_module()


def _make_designer(designer_mod, tmp_path: pathlib.Path):
    """Build a Designer without opening a window."""
    d = object.__new__(designer_mod.Designer)
    d.brush_palette = {}
    d.brush_color = (220, 60, 60, 255)
    d.brush_radius = 16.0
    d.brush_opacity = 1.0
    d.brush_hardness = 1.0
    d.brush_texture = None
    d.brush_texture_name = ""
    d.brush_texture_scale = 1.0
    d.palette = [None] * 12
    d._pending_color_slot = None
    d._pending_texture_slot = None
    d._pending_slurp_slot = None
    d._slot_popover = None
    d.tool = designer_mod.TOOL_SELECT
    d.menu_status = ""
    d.picker_target = ""
    d.picker_anchor = (0, 0)
    d.picker_alpha = 255
    d.picker_hex_buf = ""
    d.picker_hex_focused = False
    d.picker_open = False
    d.placements = []
    d.sel_kind = "none"
    d.sel_idx = -1
    # Tool Properties dock float state (replaces the earlier
    # brush-palette dock/float experiment); mirror __init__ defaults
    # so paint + dispatch can read them without crashing.
    d.tool_dock_mode = "docked"
    d.tool_dock_float_pos = None
    d._tool_dock_drag_offset = None
    d._tool_dock_drag_just_started = False
    d._anim_clock_t = 0.0
    d.props_section_open = {}
    d._prop_section_rects = []
    d._cb_scrub_key = None
    designer_mod._DESIGNER_PREFS_PATH = tmp_path / "designer-prefs.json"
    return d


class _FakeDL:
    # The brush palette now renders through framework `ui` components
    # (self-host migration, Stage 3d), which call richer DisplayList
    # methods (`gradient_card`, `fill_path_linear_gradient`,
    # `frosted_panel`, …). Absorb any DisplayList method as a no-op so
    # the unit tests can drive paint without the native renderer.
    def fill_path(self, *a, **kw): pass
    def stroke_path(self, *a, **kw): pass
    def draw_text(self, *a, **kw): pass

    def __getattr__(self, _name):
        def _noop(*a, **kw): pass
        return _noop


class _FakeTheme:
    is_dark = True
    primary = (167, 139, 250, 255)
    edge = (80, 80, 90, 255)
    accent = (236, 72, 153, 255)
    on_surface = (240, 240, 240, 255)
    on_surface_muted = (180, 180, 180, 255)
    surface = (30, 27, 75, 255)
    danger = (220, 60, 60, 255)


def _paint(d):
    d.tip_text = ""
    d.tip_pos = (0, 0)
    dl = _FakeDL()
    t = _FakeTheme()
    d._paint_brush_palette(dl, t, cur=None)
    # The popover is no longer painted inline by _paint_brush_palette;
    # it's painted at the very end of on_frame so the timeline and
    # status bar don't overdraw it. Replicate that "topmost" pass
    # here so tests that exercise popover rendering can still observe
    # the resulting hit-rects.
    if d._slot_popover is not None:
        d._paint_slot_popover(dl, t, cur=None)


# --- Slot click: opens the correct popover -------------------------------

def test_left_click_slot_opens_color_popover(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    class _W: cursor_position = (50, 500)
    d.win = _W()
    d._brush_palette_click(3, "empty", kind="slot", button="left")
    assert d._slot_popover is not None
    assert d._slot_popover["mode"] == "color"
    assert d._slot_popover["slot"] == 3


def test_right_click_slot_opens_texture_popover(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    class _W: cursor_position = (50, 500)
    d.win = _W()
    d._brush_palette_click(7, "empty", kind="slot", button="right")
    assert d._slot_popover is not None
    assert d._slot_popover["mode"] == "texture"
    assert d._slot_popover["slot"] == 7


def test_clicking_filled_color_slot_opens_color_popover(designer_mod,
                                                       tmp_path):
    """Left-click on a slot that already holds a color still opens the
    Color popover. It does NOT silently apply -- the user must press
    Apply inside the popover."""
    d = _make_designer(designer_mod, tmp_path)
    d.palette[2] = {"kind": "color", "rgba": (10, 20, 30, 255)}
    class _W: cursor_position = (50, 500)
    d.win = _W()
    d._brush_palette_click(2, "color", kind="slot", button="left")
    assert d._slot_popover is not None
    assert d._slot_popover["mode"] == "color"
    # Nothing was applied automatically.
    assert d.brush_color == (220, 60, 60, 255)


def test_opening_popover_closes_any_previous_popover(designer_mod,
                                                    tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    class _W: cursor_position = (50, 500)
    d.win = _W()
    d._brush_palette_click(0, "empty", kind="slot", button="left")
    first = d._slot_popover
    d._brush_palette_click(5, "empty", kind="slot", button="right")
    assert d._slot_popover is not None
    assert d._slot_popover is not first
    assert d._slot_popover["slot"] == 5


# --- Popover actions: every menu has Apply / Clear / Cancel -------------

def test_cancel_closes_popover_without_change(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._slot_popover = {"slot": 0, "mode": "color",
                       "anchor": (0, 0), "items": []}
    d._handle_popover_action(0, "cancel")
    assert d._slot_popover is None
    assert d.palette[0] is None
    assert d.brush_color == (220, 60, 60, 255)


def test_clear_wipes_slot(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.palette[5] = {"kind": "color", "rgba": (100, 200, 50, 255)}
    d._slot_popover = {"slot": 5, "mode": "color",
                       "anchor": (0, 0), "items": []}
    d._handle_popover_action(5, "clear")
    assert d.palette[5] is None
    assert d._slot_popover is None


def test_clear_on_texture_slot_wipes(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.palette[3] = {"kind": "texture", "name": "wing_tile"}
    d._slot_popover = {"slot": 3, "mode": "texture",
                       "anchor": (0, 0), "items": []}
    d._handle_popover_action(3, "clear")
    assert d.palette[3] is None


def test_apply_color_slot_sets_brush_color(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.palette[4] = {"kind": "color", "rgba": (167, 139, 250, 255)}
    d._slot_popover = {"slot": 4, "mode": "color",
                       "anchor": (0, 0), "items": []}
    d._handle_popover_action(4, "apply")
    assert d.brush_color == (167, 139, 250, 255)
    assert d.brush_texture is None
    assert d.tool == designer_mod.TOOL_BRUSH
    assert d._slot_popover is None


def test_apply_texture_slot_sets_active_texture(designer_mod, tmp_path):
    import numpy as _np
    d = _make_designer(designer_mod, tmp_path)
    tile = _np.full((8, 8, 4), 200, dtype=_np.uint8)
    tile[..., 3] = 255
    d.brush_palette["wing_tile"] = tile
    d.palette[6] = {"kind": "texture", "name": "wing_tile"}
    d._slot_popover = {"slot": 6, "mode": "texture",
                       "anchor": (0, 0), "items": []}
    d._handle_popover_action(6, "apply")
    assert d.brush_texture_name == "wing_tile"
    assert d.brush_texture is not None
    assert d.tool == designer_mod.TOOL_BRUSH


# --- Color picker integration -------------------------------------------

def test_open_color_picker_action_opens_picker(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._slot_popover = {"slot": 2, "mode": "color",
                       "anchor": (0, 0), "items": []}
    d._handle_popover_action(2, "open_color_picker")
    assert d.picker_open is True
    assert d.picker_target == "brush_palette_color:2"
    assert d._pending_color_slot == 2


def test_picked_color_lands_in_slot_and_applies(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._slot_popover = {"slot": 9, "mode": "color",
                       "anchor": (0, 0), "items": []}
    d._apply_picked_color_to_brush_palette((255, 128, 0, 255), 9)
    entry = d.palette[9]
    assert entry is not None
    assert entry["kind"] == "color"
    assert entry["rgba"] == (255, 128, 0, 255)
    # Snapshot of the current brush params lives alongside the
    # colour so re-applying the slot restores the full setup.
    assert "size" in entry and "opacity" in entry and "hardness" in entry
    assert d.brush_color == (255, 128, 0, 255)
    # Popover dismissed on confirm.
    assert d._slot_popover is None


def test_apply_picked_color_routes_brush_palette_target(designer_mod,
                                                       tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.picker_target = "brush_palette_color:3"
    d._apply_picked_color((100, 150, 200, 255))
    # The slot stores the colour + a snapshot of the current brush
    # params (size / opacity / hardness) so re-applying the slot
    # later restores the full painting setup, not just the colour.
    entry = d.palette[3]
    assert entry is not None
    assert entry["kind"] == "color"
    assert entry["rgba"] == (100, 150, 200, 255)
    assert entry["size"]     == pytest.approx(d.brush_radius)
    assert entry["opacity"]  == pytest.approx(d.brush_opacity)
    assert entry["hardness"] == pytest.approx(d.brush_hardness)


# --- Tile picker thumbnail clicks ---------------------------------------

def test_pick_tile_action_binds_slot_and_applies(designer_mod, tmp_path):
    import numpy as _np
    d = _make_designer(designer_mod, tmp_path)
    tile = _np.full((8, 8, 4), 150, dtype=_np.uint8)
    tile[..., 3] = 255
    d.brush_palette["my_tile"] = tile
    d._slot_popover = {"slot": 1, "mode": "texture",
                       "anchor": (0, 0),
                       "items": [("my_tile", tile)]}
    d._handle_popover_action(1, "pick_tile:my_tile")
    assert d.palette[1] == {"kind": "texture", "name": "my_tile"}
    assert d.brush_texture_name == "my_tile"
    assert d._slot_popover is None


def test_pick_tile_lazy_loads_library_entry(designer_mod, tmp_path,
                                           monkeypatch):
    import numpy as _np
    from PIL import Image as _PIL
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    tile_path = library_dir / "library_tile.png"
    arr = _np.full((4, 4, 4), 99, dtype=_np.uint8)
    arr[..., 3] = 255
    _PIL.fromarray(arr).save(tile_path)
    import elysium.render.texture as tex
    monkeypatch.setattr(tex, "LIBRARY_DIR", library_dir)
    d = _make_designer(designer_mod, tmp_path)
    d._slot_popover = {"slot": 2, "mode": "texture",
                       "anchor": (0, 0),
                       "items": [("library_tile", tile_path)]}
    d._handle_popover_action(2, "pick_tile:library_tile")
    assert d.palette[2] == {"kind": "texture", "name": "library_tile"}
    assert "library_tile" in d.brush_palette


# --- Import from file ---------------------------------------------------

def test_import_from_file_action_imports_chosen_file(designer_mod,
                                                    tmp_path,
                                                    monkeypatch):
    import numpy as _np
    from PIL import Image as _PIL
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "my_pattern.png"
    arr = _np.full((4, 4, 4), 200, dtype=_np.uint8)
    arr[..., 3] = 255
    _PIL.fromarray(arr).save(src)
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    d = _make_designer(designer_mod, tmp_path)
    monkeypatch.setattr(d, "_pick_texture_file", lambda: str(src))
    import elysium.render.texture as tex
    monkeypatch.setattr(tex, "LIBRARY_DIR", library_dir)
    d._slot_popover = {"slot": 8, "mode": "texture",
                       "anchor": (0, 0), "items": []}
    d._handle_popover_action(8, "import_texture_from_file")
    assert d.palette[8] == {"kind": "texture", "name": "my_pattern"}
    assert "my_pattern" in d.brush_palette
    assert d.brush_texture_name == "my_pattern"


def test_import_cancel_does_not_modify_slot_and_leaves_popover_open(
        designer_mod, tmp_path, monkeypatch):
    d = _make_designer(designer_mod, tmp_path)
    monkeypatch.setattr(d, "_pick_texture_file", lambda: None)
    d._slot_popover = {"slot": 4, "mode": "texture",
                       "anchor": (0, 0), "items": []}
    d._handle_popover_action(4, "import_texture_from_file")
    assert d.palette[4] is None
    # Popover stays open so the user can choose a different option.
    assert d._slot_popover is not None


# --- Aether-driven fill -------------------------------------------------

def test_aether_append_fills_pending_slot(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._pending_texture_slot = 11
    d._aether_append_palette_tile("agent_generated")
    assert d.palette[11] == {"kind": "texture",
                             "name": "agent_generated"}
    assert d._pending_texture_slot is None


def test_aether_append_with_no_pending_slot_is_noop(designer_mod,
                                                  tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._aether_append_palette_tile("agent_generated")
    assert all(e is None for e in d.palette)


# --- Persistence --------------------------------------------------------

def test_save_load_round_trip(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.palette[0] = {"kind": "color", "rgba": (10, 20, 30, 255)}
    d.palette[5] = {"kind": "texture", "name": "wing_tile"}
    d._save_brush_palettes_to_prefs()
    saved = json.loads(designer_mod._DESIGNER_PREFS_PATH.read_text())
    assert saved["brush_palette_slots"][0] == {
        "kind": "color", "rgba": [10, 20, 30, 255]}
    assert saved["brush_palette_slots"][5] == {
        "kind": "texture", "name": "wing_tile"}
    assert saved["brush_palette_slots"][1] is None

    d2 = _make_designer(designer_mod, tmp_path)
    d2._load_brush_palettes_from_prefs()
    assert d2.palette[0] == {"kind": "color",
                             "rgba": (10, 20, 30, 255)}
    assert d2.palette[5] == {"kind": "texture", "name": "wing_tile"}
    assert d2.palette[1] is None


def test_migration_from_old_dual_strip_layout(designer_mod, tmp_path):
    """A user who saved palettes under the previous dual-strip schema
    should see their slots migrated on first load."""
    designer_mod._DESIGNER_PREFS_PATH.parent.mkdir(parents=True,
                                                  exist_ok=True)
    designer_mod._DESIGNER_PREFS_PATH.write_text(json.dumps({
        "brush_color_palette": [
            [10, 20, 30, 255], None, [40, 50, 60, 255]],
        "brush_texture_palette_order": [
            None, "wing_tile", None],
    }))
    d = _make_designer(designer_mod, tmp_path)
    # _make_designer reset _DESIGNER_PREFS_PATH; restore the path the
    # fixture above wrote to.
    designer_mod._DESIGNER_PREFS_PATH = (
        tmp_path / "designer-prefs.json")
    designer_mod._DESIGNER_PREFS_PATH.write_text(json.dumps({
        "brush_color_palette": [
            [10, 20, 30, 255], None, [40, 50, 60, 255]],
        "brush_texture_palette_order": [
            None, "wing_tile", None],
    }))
    d._load_brush_palettes_from_prefs()
    assert d.palette[0] == {"kind": "color", "rgba": (10, 20, 30, 255)}
    assert d.palette[1] == {"kind": "texture", "name": "wing_tile"}
    assert d.palette[2] == {"kind": "color", "rgba": (40, 50, 60, 255)}


def test_load_handles_missing_prefs_file_gracefully(designer_mod,
                                                    tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._load_brush_palettes_from_prefs()
    assert all(e is None for e in d.palette)


# --- Clear button on the header -----------------------------------------

def test_clear_button_clears_active_texture(designer_mod, tmp_path):
    import numpy as _np
    d = _make_designer(designer_mod, tmp_path)
    d.brush_texture = _np.zeros((4, 4, 4), dtype=_np.uint8)
    d.brush_texture_name = "x"
    d._brush_palette_click(0, "active", kind="clear", button="left")
    assert d.brush_texture is None
    assert d.brush_texture_name == ""


# --- Paint smoke ---------------------------------------------------------

def test_paint_brush_palette_records_slot_rects(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.palette[0] = {"kind": "color", "rgba": (220, 60, 60, 255)}
    d.palette[1] = {"kind": "texture", "name": "wing_tile"}
    _paint(d)
    kinds = {hit[1] for hit in d._brush_palette_rects}
    assert "slot" in kinds
    assert "clear" in kinds
    slot_hits = [hit for hit in d._brush_palette_rects if hit[1] == "slot"]
    assert len(slot_hits) == 12


def test_paint_includes_color_popover_when_open(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.palette[3] = {"kind": "color", "rgba": (10, 20, 30, 255)}
    d._slot_popover = {"slot": 3, "mode": "color",
                       "anchor": (200, 400),
                       "items": []}
    _paint(d)
    popover_actions = [hit[2] for hit in d._brush_palette_rects
                       if hit[1] == "popover"]
    assert "open_color_picker" in popover_actions
    assert "apply" in popover_actions
    assert "clear" in popover_actions
    assert "cancel" in popover_actions


# --- Capture from Image placement ---------------------------------------

def test_capture_from_image_arms_slurp_and_switches_tool(designer_mod,
                                                        tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._slot_popover = {"slot": 4, "mode": "texture",
                       "anchor": (0, 0), "items": []}
    d._handle_popover_action(4, "capture_from_image")
    assert d._pending_slurp_slot == 4
    assert d.tool == designer_mod.TOOL_EYEDROP
    # Popover dismisses so the user can drag freely on the canvas.
    assert d._slot_popover is None


def test_capture_from_image_fills_slot_on_slurp(designer_mod, tmp_path,
                                               monkeypatch):
    """The next _commit_eyedrop call writes its tile into the armed
    slot AND saves the palette."""
    import numpy as _np
    from PIL import Image as _PIL
    d = _make_designer(designer_mod, tmp_path)
    d._pending_slurp_slot = 6

    # Fake an Image placement under the cursor.
    class _Placement:
        kind = "Image"
        x, y, w, h = 0, 0, 100, 100
        image_path = str(tmp_path / "source.png")
        props = {}
    arr = _np.full((50, 50, 4), 180, dtype=_np.uint8)
    arr[..., 3] = 255
    _PIL.fromarray(arr).save(_Placement.image_path)
    d.placements = [_Placement()]

    # Avoid touching the real on-disk library.
    import elysium.render.texture as tex
    monkeypatch.setattr(tex, "LIBRARY_DIR", tmp_path / "lib")
    (tmp_path / "lib").mkdir(exist_ok=True)
    monkeypatch.setattr(tex, "list_library", lambda: [])
    # extract_from_file is the real path; let it write into the lib.
    d._commit_eyedrop(0, 0, 32, 32)
    assert d.palette[6] is not None
    assert d.palette[6]["kind"] == "texture"
    assert d._pending_slurp_slot is None


def test_capture_cancel_via_esc_clears_pending_slurp(designer_mod,
                                                   tmp_path):
    """Setting _pending_slurp_slot to None (as the Esc handler does)
    leaves the rest of the state untouched."""
    d = _make_designer(designer_mod, tmp_path)
    d._pending_slurp_slot = 2
    d._pending_slurp_slot = None
    assert d.palette[2] is None


# --- Texture popover layout ---------------------------------------------

def test_paint_includes_texture_popover_with_picker_grid(designer_mod,
                                                       tmp_path):
    import numpy as _np
    d = _make_designer(designer_mod, tmp_path)
    tile = _np.full((4, 4, 4), 200, dtype=_np.uint8)
    tile[..., 3] = 255
    d.brush_palette["wing"] = tile
    d._slot_popover = {"slot": 0, "mode": "texture",
                       "anchor": (200, 400),
                       "items": [("wing", tile), ("velvet", tile)]}
    _paint(d)
    popover_roles = [hit[2] for hit in d._brush_palette_rects
                     if hit[1] == "popover"]
    # Headline action: capture from canvas, not pick-from-list.
    assert "capture_from_image" in popover_roles
    assert "import_texture_from_file" in popover_roles
    assert "generate_texture_aether" in popover_roles
    # Saved-tiles grid still present as a labeled secondary section.
    assert "pick_tile:wing" in popover_roles
    assert "pick_tile:velvet" in popover_roles
    assert "cancel" in popover_roles


# --- Channel Box scrub-on-drag ------------------------------------------


class _StubPlacement:
    """Minimum-viable placement stand-in for `_cb_attr_setter` tests."""
    kind = "Shape"
    name = "stub"
    def __init__(self):
        self.x = 10.0
        self.y = 20.0
        self.w = 100.0
        self.h = 60.0
        self._t_rotation = 0.0
        self._t_opacity = 1.0
        self.mesh_yaw = 0.0
        self.mesh_pitch = 0.0
        self.mesh_roll = 0.0
        self.mesh_dist = 1.0


def test_cb_attr_setter_writes_to_placement(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    p = _StubPlacement()
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._cb_attr_setter("x", 42.5)
    d._cb_attr_setter("rotation", 0.75)
    d._cb_attr_setter("opacity", 0.3)
    assert p.x == 42.5
    assert p._t_rotation == 0.75
    assert p._t_opacity == 0.3


def test_cb_attr_setter_clamps_opacity(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    p = _StubPlacement()
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._cb_attr_setter("opacity", 5.0)
    assert p._t_opacity == 1.0
    d._cb_attr_setter("opacity", -2.0)
    assert p._t_opacity == 0.0


def test_cb_attr_setter_clamps_width_to_one(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    p = _StubPlacement()
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._cb_attr_setter("w", 0.5)
    assert p.w == 1.0


def test_cb_attr_setter_mesh_angles_use_degrees(designer_mod, tmp_path):
    """Mesh angle scrubs come in as degrees because the displayed
    value carries a ° suffix. The setter converts to radians for
    storage on the placement."""
    import math
    d = _make_designer(designer_mod, tmp_path)
    p = _StubPlacement()
    d.placements = [p]
    d.sel_kind = "placement"
    d.sel_idx = 0
    d._cb_attr_setter("mesh_yaw", 90.0)
    d._cb_attr_setter("mesh_pitch", -45.0)
    d._cb_attr_setter("mesh_roll", 180.0)
    assert p.mesh_yaw == pytest.approx(math.pi / 2)
    assert p.mesh_pitch == pytest.approx(-math.pi / 4)
    assert p.mesh_roll == pytest.approx(math.pi)


def test_cb_attr_setter_noop_when_nothing_selected(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d.placements = [_StubPlacement()]
    d.sel_kind = "none"
    d.sel_idx = -1
    # Must not raise; should not mutate anything.
    d._cb_attr_setter("x", 999.0)
    assert d.placements[0].x == 10.0


def test_cb_scrub_start_returns_false_when_no_field(designer_mod, tmp_path):
    """Press lands outside any NumericField → no scrub starts."""
    d = _make_designer(designer_mod, tmp_path)
    d._cb_numeric_fields = {}
    d._channel_box_rects = []
    assert d._cb_start_scrub_if_numeric(100, 100) is False
    assert getattr(d, "_cb_scrub_key", None) is None


def test_cb_scrub_start_records_active_key(designer_mod, tmp_path):
    """Press inside a NumericField's value cell starts a scrub
    and records the key on `_cb_scrub_key`."""
    d = _make_designer(designer_mod, tmp_path)
    nf = designer_mod.ui.NumericField(x=200, y=400, w=80, h=18,
                                       value=5.0)
    d._cb_numeric_fields = {"x": nf}
    d._channel_box_rects = [("x", (100, 395, 180, 20))]
    assert d._cb_start_scrub_if_numeric(220, 405) is True
    assert d._cb_scrub_key == "x"


def test_cb_scrub_start_outside_field_does_not_start(designer_mod,
                                                      tmp_path):
    """Press inside the row but OUTSIDE the field cell (e.g. on the
    label column) does NOT start a scrub  the normal focus flow
    fires instead."""
    d = _make_designer(designer_mod, tmp_path)
    nf = designer_mod.ui.NumericField(x=200, y=400, w=80, h=18,
                                       value=5.0)
    d._cb_numeric_fields = {"x": nf}
    d._channel_box_rects = [("x", (100, 395, 180, 20))]
    # Click in the label column (x=120, < field.x=200).
    assert d._cb_start_scrub_if_numeric(120, 405) is False


# --- Properties pane Accordion sections (spec §9 Stage 3e) --------------


@pytest.mark.parametrize(
    "label, expected",
    [
        ("(Name)",          "Info"),
        ("Kind",            "Info"),
        ("Title",           "Info"),
        ("Shape",           "Info"),
        ("Image",           "Info"),
        ("Width",           "Layout"),
        ("Height",          "Layout"),
        ("Corner",          "Layout"),
        ("Fill",            "Style"),
        ("Stroke",          "Style"),
        ("Background",      "Style"),
        ("Gradient",        "Style"),
        ("Grad → ",         "Style"),
        ("Title color",     "Style"),
        ("color_fill",      "Style"),    # generic *color* hit
        ("Transparent",     "Behavior"),
        ("Title bar",       "Behavior"),
        ("Resizable",       "Behavior"),
        ("Click → Target",  "Trigger"),
        ("Click → State",   "Trigger"),
        ("Preset",          "PBR"),
        ("Metallic",        "PBR"),
        ("Roughness",       "PBR"),
        ("Specular",        "PBR"),
        ("Clear-coat",      "PBR"),
        ("CC Rough",        "PBR"),
        ("Mesh",            "Mesh"),
        ("Yaw",             "Mesh"),
        ("Pitch",           "Mesh"),
        ("Roll",            "Mesh"),
        ("Mesh Yaw",        "Mesh"),
        ("Cam Dist",        "Mesh"),
        ("Distance",        "Mesh"),
        ("Texture",         "Texture"),
        ("Tex scale",       "Texture"),
        ("Tex off X",       "Texture"),
        ("Studio",          "Studio"),
        ("─── Studio ───",  "Studio"),     # divider goes under Studio
        ("Caption",         "Info"),
        ("WeirdRow",        "Other"),
    ],
)
def test_prop_section_classifier(designer_mod, label, expected):
    """Static classifier  bucket each property row into a section
    name. Must round-trip every label the Designer can emit."""
    assert designer_mod.Designer._prop_section_for(label) == expected


def test_props_section_open_defaults_to_true(designer_mod, tmp_path):
    """A section the user has never touched defaults to open."""
    d = _make_designer(designer_mod, tmp_path)
    # `props_section_open` starts empty; `.get(sec, True)` is the
    # default-open semantic.
    assert d.props_section_open == {}
    assert d.props_section_open.get("Info", True) is True
    assert d.props_section_open.get("Style", True) is True


def test_props_section_open_toggles_on_header_click(designer_mod, tmp_path):
    """Recording a header click in `_prop_section_rects` and calling
    the press dispatcher flips that section's open state."""
    d = _make_designer(designer_mod, tmp_path)
    d._prop_section_rects = [
        ("Info",   (100, 100, 200, 20)),
        ("Layout", (100, 122, 200, 20)),
    ]
    d._swatch_rects = []
    d._toggle_rects = []
    d._state_rects = []
    # Click the "Info" header → open=False (toggled from default True).
    assert d._maybe_open_property_picker(150, 110) is True
    assert d.props_section_open["Info"] is False
    # Click again → open=True.
    assert d._maybe_open_property_picker(150, 110) is True
    assert d.props_section_open["Info"] is True
    # Click "Layout" header → open=False.
    assert d._maybe_open_property_picker(150, 132) is True
    assert d.props_section_open["Layout"] is False
    # Click outside any section header → no consumption.
    assert d._maybe_open_property_picker(900, 900) is False


def test_prop_section_order_includes_every_classifier_value(designer_mod):
    """Every value `_prop_section_for` can return must be listed in
    `_PROP_SECTION_ORDER`; otherwise that section's rows would
    silently render at the bottom (or not at all)."""
    classifier_values = set()
    for label in ("(Name)", "Width", "Fill", "Transparent",
                   "Click → x", "Preset", "Mesh", "Tex scale", "Studio",
                   "Other thing"):
        classifier_values.add(
            designer_mod.Designer._prop_section_for(label))
    assert classifier_values <= set(
        designer_mod.Designer._PROP_SECTION_ORDER)


# --- Slot popover slider scrubs -----------------------------------------


def test_slider_writes_param_into_slot(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._handle_popover_slider(2, "size", 0.5)
    entry = d.palette[2]
    assert entry is not None
    assert entry["kind"] == "color"
    # frac=0.5 over [2.0, 64.0] → 33.0.
    assert entry["size"] == pytest.approx(33.0)


def test_slider_clamps_frac(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._handle_popover_slider(0, "opacity", 2.5)
    assert d.palette[0]["opacity"] == 1.0
    d._handle_popover_slider(0, "opacity", -1.0)
    assert d.palette[0]["opacity"] == 0.0


def test_slider_live_applies_to_brush_state(designer_mod, tmp_path):
    """Dragging a slot's slider should ALSO mutate the live brush
    state so the user sees the effect on the next stroke without
    pressing Apply."""
    d = _make_designer(designer_mod, tmp_path)
    d._handle_popover_slider(4, "size", 0.0)        # minimum
    assert d.brush_radius == 2.0
    d._handle_popover_slider(4, "size", 1.0)        # maximum
    assert d.brush_radius == 64.0
    d._handle_popover_slider(4, "hardness", 0.5)
    assert d.brush_hardness == pytest.approx(0.5)


def test_slider_unknown_key_is_safe(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    d._handle_popover_slider(0, "not_a_known_key", 0.5)
    # Slot stays empty when the key doesn't map to a known range.
    assert d.palette[0] is None


def test_slider_out_of_range_slot_is_safe(designer_mod, tmp_path):
    d = _make_designer(designer_mod, tmp_path)
    # Must not raise.
    d._handle_popover_slider(-1, "size", 0.5)
    d._handle_popover_slider(999, "opacity", 0.5)


def test_apply_palette_color_entry_restores_params(designer_mod, tmp_path):
    """Applying a slot that stores size/opacity/hardness restores
    them onto the live brush  the full painting setup, one click."""
    d = _make_designer(designer_mod, tmp_path)
    d.palette[5] = {
        "kind": "color", "rgba": (200, 100, 50, 255),
        "size": 40.0, "opacity": 0.65, "hardness": 0.30,
    }
    d._apply_palette_color_entry(d.palette[5])
    assert d.brush_color == (200, 100, 50, 255)
    assert d.brush_radius == 40.0
    assert d.brush_opacity == pytest.approx(0.65)
    assert d.brush_hardness == pytest.approx(0.30)


# --- Native right-button API --------------------------------------------

def test_window_proxy_exposes_right_button_getters():
    """Native + Python proxy expose right-button counters."""
    import elysium as ely
    app = ely.App(title="t", identifier="dev.test.rmb-3")
    w = app.window(transparent=False, title_bar=True, resizable=True,
                   initial_size=(200, 200))
    assert hasattr(w, "mouse_right_pressed")
    assert hasattr(w, "right_press_count")
    assert w.mouse_right_pressed is False
    assert w.right_press_count == 0
