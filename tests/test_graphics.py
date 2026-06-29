"""Tier 5 Phase 1 — graphics scene-graph: Scene + Item model + built-in items."""
from __future__ import annotations

import pytest

from elysium import theme as T
from elysium.graphics import (
    Item, RectItem, EllipseItem, LineItem, PathItem, TextItem, Scene,
)


@pytest.fixture(autouse=True)
def _studio():
    T.set_theme(T.studio_dark())
    yield
    T.set_theme(T.light())


def _render(scene, w=300, h=200):
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    scene.paint(dl)
    layer = n.SkiaLayer(w, h)
    layer.execute(dl)
    return bytes(layer.encode_png())


# --- items: bounds + hit-test ---------------------------------------------

def test_rect_bounds_and_contains():
    r = RectItem(x=10, y=20, w=100, h=40)
    assert r.scene_bounds() == (10, 20, 100, 40)
    assert r.center() == (60, 40)
    assert r.contains(60, 40) is True
    assert r.contains(5, 40) is False


def test_ellipse_contains_uses_radius_equation():
    e = EllipseItem(x=0, y=0, w=100, h=40)  # rx=50, ry=20, center (50,20)
    assert e.contains(50, 20) is True       # centre
    assert e.contains(99, 20) is True       # near right edge inside
    assert e.contains(50, 39) is True       # near bottom edge inside
    assert e.contains(5, 5) is False        # corner of bbox, outside ellipse


def test_line_bounds_synced_and_distance_hit():
    ln = LineItem(x1=0, y1=0, x2=100, y2=0, tolerance=4)
    assert ln.scene_bounds() == (0, 0, 100, 0)
    assert ln.contains(50, 2) is True       # within tolerance
    assert ln.contains(50, 10) is False     # too far
    ln.move_by(5, 5)
    assert (ln.x1, ln.y1, ln.x2, ln.y2) == (5, 5, 105, 5)
    assert ln.scene_bounds() == (5, 5, 100, 0)


def test_default_item_contains_is_bounds():
    it = Item(x=0, y=0, w=10, h=10)
    assert it.contains(5, 5) is True
    assert it.contains(11, 5) is False


# --- scene structure + z-order --------------------------------------------

def test_scene_add_remove_clear():
    s = Scene()
    a = s.add(RectItem(w=10, h=10))
    s.add(RectItem(w=10, h=10))
    assert len(s.items) == 2
    s.remove(a)
    assert len(s.items) == 1
    s.clear()
    assert s.items == []


def test_scene_z_sorted_and_raise_lower():
    s = Scene()
    a = s.add(RectItem(z=0, w=10, h=10))
    b = s.add(RectItem(z=1, w=10, h=10))
    c = s.add(RectItem(z=2, w=10, h=10))
    assert s.z_sorted() == [a, b, c]
    s.raise_to_top(a)
    assert a.z > c.z
    s.lower_to_bottom(a)
    assert a.z < b.z


def test_items_at_returns_topmost_first():
    s = Scene()
    bottom = s.add(RectItem(x=0, y=0, w=100, h=100, z=0))
    top = s.add(RectItem(x=0, y=0, w=100, h=100, z=5))
    hits = s.items_at(50, 50)
    assert hits == [top, bottom]
    assert s.item_at(50, 50) is top
    assert s.item_at(200, 200) is None


def test_items_at_skips_hidden():
    s = Scene()
    r = s.add(RectItem(x=0, y=0, w=50, h=50))
    r.visible = False
    assert s.items_at(10, 10) == []


# --- rubber-band query -----------------------------------------------------

def test_items_in_rect_intersect_vs_contained():
    s = Scene()
    inside = s.add(RectItem(x=10, y=10, w=20, h=20))
    straddle = s.add(RectItem(x=90, y=10, w=40, h=20))   # crosses right edge
    s.add(RectItem(x=300, y=300, w=10, h=10))            # far away
    band = (0, 0, 100, 100)
    inter = s.items_in_rect(*band, contained=False)
    assert inside in inter and straddle in inter
    cont = s.items_in_rect(*band, contained=True)
    assert inside in cont and straddle not in cont


def test_scene_bounding_rect():
    s = Scene()
    assert s.bounding_rect() == (0, 0, 0, 0)
    s.add(RectItem(x=10, y=20, w=30, h=40))
    s.add(RectItem(x=50, y=10, w=20, h=20))
    assert s.bounding_rect() == (10, 10, 60, 50)  # x:10..70, y:10..60


# --- selection -------------------------------------------------------------

def test_scene_selection_helpers():
    s = Scene()
    a = s.add(RectItem(w=10, h=10))
    b = s.add(RectItem(w=10, h=10))
    a.selected = True
    assert s.selected_items() == [a]
    s.clear_selection()
    assert s.selected_items() == []


# --- paint -----------------------------------------------------------------

def test_scene_paints_all_item_types():
    s = Scene()
    s.add(RectItem(x=10, y=10, w=80, h=40, fill=(108, 124, 255, 255)))
    s.add(EllipseItem(x=120, y=10, w=60, h=60))
    s.add(LineItem(x1=10, y1=80, x2=180, y2=120))
    s.add(PathItem(d="M 200 20 L 240 60 L 200 100 Z", x=200, y=20, w=40, h=80,
                   stroke=(232, 235, 240, 255)))
    s.add(TextItem(x=10, y=140, w=200, h=20, text="scene", size=14))
    s.items[0].selected = True
    assert _render(s)[:4] == b"\x89PNG"


# --- GraphicsView (Phase 2) ------------------------------------------------

from elysium.graphics import GraphicsView  # noqa: E402


def _view_with_scene():
    s = Scene()
    s.add(RectItem(x=0, y=0, w=50, h=50))         # near origin
    s.add(RectItem(x=1000, y=1000, w=50, h=50))   # far away
    return GraphicsView(scene=s, x=0, y=0, w=400, h=300)


def test_view_coord_roundtrip():
    v = GraphicsView(x=10, y=20, w=400, h=300, pan_x=100, pan_y=50, zoom=2.0)
    vx, vy = v.to_view(130, 80)
    assert (vx, vy) == (10 + (130 - 100) * 2, 20 + (80 - 50) * 2)
    sx, sy = v.to_scene(vx, vy)
    assert sx == pytest.approx(130) and sy == pytest.approx(80)


def test_view_zoom_at_keeps_focal_point_fixed():
    v = GraphicsView(x=0, y=0, w=400, h=300, zoom=1.0)
    focal = (250, 150)
    before = v.to_scene(*focal)
    v.zoom_at(*focal, 2.0)
    after = v.to_scene(*focal)
    assert v.zoom == pytest.approx(2.0)
    assert after[0] == pytest.approx(before[0])
    assert after[1] == pytest.approx(before[1])


def test_view_zoom_clamped():
    v = GraphicsView(w=400, h=300, zoom=1.0, min_zoom=0.5, max_zoom=4.0)
    v.set_zoom(100)
    assert v.zoom == 4.0
    v.set_zoom(0.001)
    assert v.zoom == 0.5


def test_view_pan_drag():
    v = GraphicsView(w=400, h=300, zoom=2.0)
    v.begin_pan(100, 100)
    v.drag_pan(120, 110)        # moved +20,+10 screen px
    v.end_pan()
    # content followed the cursor → pan shifted by -delta/zoom
    assert v.pan_x == pytest.approx(-10) and v.pan_y == pytest.approx(-5)


def test_view_fit_frames_scene():
    v = _view_with_scene()
    v.fit(margin=10)
    # the whole scene bbox (0..1050) now fits within the viewport
    vis = v.visible_scene_rect()
    sb = v.scene.bounding_rect()
    assert vis[0] <= sb[0] + 1 and vis[1] <= sb[1] + 1
    assert vis[0] + vis[2] >= sb[0] + sb[2] - 1
    assert vis[1] + vis[3] >= sb[1] + sb[3] - 1


def test_view_culls_offscreen_items():
    v = _view_with_scene()      # zoom 1, viewport 400×300 at origin
    vis = v.visible_items()
    assert len(vis) == 1        # only the near rect is on-screen
    v.fit(margin=10)            # now both fit
    assert len(v.visible_items()) == 2


def test_view_renders():
    v = _view_with_scene()
    v.scene.items[0].selected = True
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    v.paint(dl)
    layer = n.SkiaLayer(400, 300)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"


# --- SceneController interaction (Phase 3) ---------------------------------

from elysium.graphics import SceneController  # noqa: E402


def _controller():
    s = Scene()
    a = s.add(RectItem(x=20, y=20, w=80, h=60))
    b = s.add(RectItem(x=160, y=40, w=80, h=60))
    view = GraphicsView(scene=s, x=0, y=0, w=400, h=300, zoom=1.0)  # screen==scene
    return SceneController(view=view), a, b


def test_click_selects_topmost_and_clears_others():
    c, a, b = _controller()
    c.on_press(50, 40)        # inside a
    c.on_release()
    assert a.selected and not b.selected
    c.on_press(190, 70)       # inside b
    c.on_release()
    assert b.selected and not a.selected


def test_additive_click_toggles_multi_select():
    c, a, b = _controller()
    c.on_press(50, 40); c.on_release()
    c.on_press(190, 70, additive=True); c.on_release()
    assert a.selected and b.selected
    c.on_press(190, 70, additive=True); c.on_release()   # toggle b off
    assert a.selected and not b.selected


def test_rubber_band_selects_intersecting():
    c, a, b = _controller()
    c.on_press(0, 0)                 # empty → band
    assert c._mode == "band"
    c.on_drag(300, 200)             # band covers both rects
    c.on_release()
    assert a.selected and b.selected


def test_move_drag_moves_selection_with_snap():
    c, a, b = _controller()
    c.snap = 10
    c.on_press(50, 40)              # select + grab a (a at 20,20)
    c.on_drag(63, 52)              # delta (13,12) → snapped to (10,10)
    c.on_release()
    assert (a.x, a.y) == (30, 30)
    assert not b.selected


def test_resize_se_handle_changes_bounds():
    c, a, b = _controller()
    c.on_press(50, 40); c.on_release()     # select a (20,20,80,60)
    handles = c.handle_rects()
    assert set(handles) == set(("nw", "n", "ne", "e", "se", "s", "sw", "w"))
    hx, hy, hw, hh = handles["se"]
    c.on_press(hx + hw / 2, hy + hh / 2)   # grab SE handle
    assert c._mode == "resize"
    c.on_drag(140, 110)                    # drag SE corner to (140,110)
    c.on_release()
    assert a.x == 20 and a.y == 20
    assert a.w == pytest.approx(120) and a.h == pytest.approx(90)


def test_no_handles_for_line_or_multi_selection():
    s = Scene()
    ln = s.add(LineItem(x1=0, y1=0, x2=100, y2=100))
    r = s.add(RectItem(x=10, y=10, w=40, h=40))
    view = GraphicsView(scene=s, x=0, y=0, w=400, h=300)
    c = SceneController(view=view)
    ln.selected = True
    assert c.handle_rects() == {}        # line is not resizable
    ln.selected = False
    r.selected = True
    assert len(c.handle_rects()) == 8    # single resizable rect
    ln.selected = True                   # now 2 selected
    assert c.handle_rects() == {}        # multi-select → no handles


def test_controller_overlay_renders():
    c, a, b = _controller()
    a.selected = True
    c.on_press(0, 0); c.on_drag(120, 120)   # active rubber-band
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    c.view.paint(dl)
    c.paint_overlay(dl)
    layer = n.SkiaLayer(400, 300)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"
    c.on_release()


# --- graphics demo smoke (Phase 4) -----------------------------------------

def test_graphics_demo_builds_and_paints():
    import importlib.util
    from elysium._native import _native as n
    spec = importlib.util.spec_from_file_location(
        "graphics_demo", "examples/graphics-demo/main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ed = mod.build_editor(900, 600)
    assert len(ed["scene"].items) >= 6
    # exercise a select + move through the controller
    box = next(it for it in ed["scene"].items if isinstance(it, RectItem))
    cx, cy = box.center()
    vx, vy = ed["view"].to_view(cx, cy)
    ed["controller"].on_press(vx, vy)
    ed["controller"].on_drag(vx + 24, vy + 24)
    ed["controller"].on_release()
    assert box.selected
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    mod.paint_editor(dl, ed, 900, 600)
    layer = n.SkiaLayer(900, 600)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"
