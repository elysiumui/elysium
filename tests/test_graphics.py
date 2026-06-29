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
