"""Tests for the Phase 3 framework components introduced for the
Elysium Designer self-host migration: Tree, NumericField, FAB,
RadialPopover. Spec source:
``docs-designer/internals/self-host-design.md`` §6.

These tests cover the public API + hit-testing + state transitions.
They use a fake DisplayList that absorbs every method as a no-op, so
the tests run on any platform without the native renderer.
"""
from __future__ import annotations

import math

import pytest

from elysium.components import (
    FAB,
    GlyphAtlas,
    IconButton,
    NumericField,
    RadialPopover,
    Tree,
    TreeRow,
    get_default_atlas,
)


class _FakeDL:
    """Catch-all DisplayList stub. Every method is a no-op."""

    def __getattr__(self, _name):
        def _noop(*_a, **_kw):
            return None
        return _noop


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------


def _build_demo_tree() -> Tree:
    return Tree(
        x=0.0, y=0.0, w=200.0, h=120.0,
        rows=[
            TreeRow(id="root", label="Project", depth=0,
                    expandable=True, expanded=True),
            TreeRow(id="win",  label="MainWindow", depth=1,
                    expandable=True, expanded=True),
            TreeRow(id="img",  label="Image", depth=2),
            TreeRow(id="mesh", label="Mesh3D", depth=2, selected=True),
        ])


def test_tree_paints_without_error():
    tree = _build_demo_tree()
    tree.paint(_FakeDL())  # must not raise


def test_tree_visible_row_range_respects_scroll_and_height():
    tree = _build_demo_tree()
    tree.row_height = 20.0
    # h=120 → 6 visible slots at scroll=0 → all 4 rows fit.
    s, e = tree.visible_row_range()
    assert s == 0 and e == 4
    tree.scroll = 2.0
    s, e = tree.visible_row_range()
    assert s == 2 and e == 4
    tree.scroll = 10.0
    s, e = tree.visible_row_range()
    assert s == 10 and e == 4
    # Zero row-height degenerate.
    tree.row_height = 0.0
    assert tree.visible_row_range() == (0, 0)


def test_tree_hit_test_distinguishes_chevron_and_label():
    tree = _build_demo_tree()
    # Root row (depth=0, expandable=True) at y=0..20.
    # Chevron starts at x = cell_pad_x (8) + depth*indent (0) = 8,
    # width 12 → chevron rect (8..20, 0..20). Label hit anywhere else
    # inside the row width.
    chev = tree.hit_test_row(12, 10)
    assert chev == ("root", "chevron")
    lbl = tree.hit_test_row(80, 10)
    assert lbl == ("root", "label")
    # Below the rendered rows: no hit.
    assert tree.hit_test_row(50, 200) is None
    # Non-expandable row (img, row index 2, depth=2) → chevron never
    # returned even if you click where the chevron would be.
    pos_y = 2 * tree.row_height + 5
    res = tree.hit_test_row(8 + 2 * tree.indent + 2, pos_y)
    assert res == ("img", "label")


def test_tree_selection_paints_highlight():
    """Selected row gets the highlight fill; we just verify the paint
    pass runs without error when a row carries selected=True."""
    tree = _build_demo_tree()
    assert tree.rows[3].selected is True
    tree.paint(_FakeDL())


# ---------------------------------------------------------------------------
# NumericField
# ---------------------------------------------------------------------------


def test_numeric_field_default_format():
    nf = NumericField(value=1.2345)
    assert nf._format_value() == "1.23"


def test_numeric_field_custom_format():
    nf = NumericField(value=42, format="{:d}")
    assert nf._format_value() == "42"


def test_numeric_field_paints_without_error():
    nf = NumericField(x=0, y=0, w=120, h=20, label="X", value=2.5)
    nf.paint(_FakeDL())


def test_numeric_field_scrub_changes_value_and_fires_callback():
    received: list[float] = []
    nf = NumericField(value=0.0, step=0.5, on_change=received.append)
    nf.scrub_start(100.0, 50.0)
    nf.scrub_drag(110.0, 50.0)
    # dx = 10, step = 0.5 → new = 5.0
    assert nf.value == pytest.approx(5.0)
    assert received == [pytest.approx(5.0)]
    nf.scrub_drag(120.0, 50.0)
    # dx = 20, step = 0.5 → new = 10.0 (from base 0.0)
    assert nf.value == pytest.approx(10.0)
    nf.scrub_end()
    # After end, further drags are no-ops.
    nf.scrub_drag(200.0, 50.0)
    assert nf.value == pytest.approx(10.0)


def test_numeric_field_clamps_to_min_max():
    received: list[float] = []
    nf = NumericField(value=5.0, step=1.0,
                      min_value=0.0, max_value=10.0,
                      on_change=received.append)
    nf.scrub_start(0.0, 0.0)
    nf.scrub_drag(20.0, 0.0)
    assert nf.value == 10.0
    nf.scrub_drag(-100.0, 0.0)
    assert nf.value == 0.0


# ---------------------------------------------------------------------------
# FAB
# ---------------------------------------------------------------------------


def test_fab_paints_without_error():
    fab = FAB(x=20, y=20, w=56, h=56, icon="+", tooltip="Add")
    fab.paint(_FakeDL())


def test_fab_circular_hit_test():
    fab = FAB(x=0, y=0, w=56, h=56)
    # Centre inside.
    assert fab.hit_test(28, 28) is True
    # Corner of the bbox is outside the circle.
    assert fab.hit_test(0, 0) is False
    assert fab.hit_test(56, 56) is False
    # Outside entirely.
    assert fab.hit_test(100, 100) is False


def test_fab_fire_click_invokes_callback():
    calls: list[int] = []
    fab = FAB(on_click=lambda: calls.append(1))
    fab.fire_click()
    fab.fire_click()
    assert calls == [1, 1]


def test_fab_fire_click_without_callback_is_safe():
    FAB().fire_click()           # must not raise


def test_fab_variant_changes_paint_path():
    """Each variant exercises a different fill source; verify each
    variant paints without raising."""
    for variant in ("primary", "accent", "surface", "unknown"):
        fab = FAB(x=0, y=0, w=48, h=48, variant=variant, icon="★")
        fab.paint(_FakeDL())


# ---------------------------------------------------------------------------
# RadialPopover
# ---------------------------------------------------------------------------


def _radial_demo() -> RadialPopover:
    rp = RadialPopover(
        x=0, y=0, w=200, h=200,
        items=[("n", "North"), ("e", "East"),
               ("s", "South"), ("w", "West")],
        visible=True,
        radius=80.0,
        inner_radius=24.0,
    )
    rp._vis_t = 1.0
    return rp


def test_radial_popover_paints_when_visible():
    rp = _radial_demo()
    rp.paint(_FakeDL())


def test_radial_popover_invisible_short_circuits():
    rp = _radial_demo()
    rp.visible = False
    rp._vis_t = 0.0
    rp.paint(_FakeDL())          # no-op


def test_radial_popover_hit_test_picks_correct_wedge():
    rp = _radial_demo()
    # 4 items, evenly spaced, north at index 0.
    cx, cy = 100, 100
    r = 50.0     # between inner_radius and radius
    # Sample one point per wedge centre.
    samples = {
        "n": (cx + 0,   cy - r),       # top
        "e": (cx + r,   cy + 0),       # right
        "s": (cx + 0,   cy + r),       # bottom
        "w": (cx - r,   cy + 0),       # left
    }
    for expected_id, (mx, my) in samples.items():
        assert rp.hit_test_item(mx, my) == expected_id, expected_id


def test_radial_popover_hit_test_rejects_outside_donut():
    rp = _radial_demo()
    cx, cy = 100, 100
    # Centre dead-zone (inside inner_radius).
    assert rp.hit_test_item(cx, cy) is None
    # Outside outer_radius.
    assert rp.hit_test_item(cx + 200, cy) is None


def test_radial_popover_hit_test_empty_items():
    rp = RadialPopover(x=0, y=0, w=200, h=200)
    assert rp.hit_test_item(50, 50) is None


# ---------------------------------------------------------------------------
# GlyphAtlas + IconButton (spec §6.6)
# ---------------------------------------------------------------------------


def test_glyph_atlas_register_and_lookup():
    atlas = GlyphAtlas()
    assert atlas.lookup("save") is None
    atlas.register("save", "/icons/save.png")
    assert atlas.lookup("save") == "/icons/save.png"
    assert "save" in atlas
    assert "missing" not in atlas
    assert len(atlas) == 1


def test_glyph_atlas_load_from_directory(tmp_path):
    """Scan a directory of icon files and register each by stem.
    Subdirectories + non-icon files are ignored."""
    (tmp_path / "save.png").write_bytes(b"fake-png")
    (tmp_path / "open.svg").write_bytes(b"<svg/>")
    (tmp_path / "trash.jpg").write_bytes(b"fake-jpg")
    (tmp_path / "readme.txt").write_text("ignored")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.png").write_bytes(b"x")

    atlas = GlyphAtlas()
    registered = atlas.load_from_directory(tmp_path)
    assert registered == 3
    assert atlas.lookup("save") and atlas.lookup("save").endswith("save.png")
    assert atlas.lookup("open") and atlas.lookup("open").endswith("open.svg")
    assert atlas.lookup("trash")
    # Files in subdirs aren't picked up.
    assert atlas.lookup("nested") is None
    # Non-icon files aren't picked up.
    assert atlas.lookup("readme") is None


def test_glyph_atlas_load_from_directory_missing_path_is_safe(tmp_path):
    atlas = GlyphAtlas()
    assert atlas.load_from_directory(tmp_path / "does-not-exist") == 0
    assert len(atlas) == 0


def test_get_default_atlas_is_process_wide():
    a1 = get_default_atlas()
    a2 = get_default_atlas()
    assert a1 is a2


def test_icon_button_paints_text_fallback_when_atlas_misses():
    """When the named icon doesn't exist in the atlas, the button
    renders the icon string as text. Paint must not raise."""
    btn = IconButton(x=0, y=0, w=32, h=32,
                     icon="not-registered", variant="ghost")
    btn.paint(_FakeDL())


def test_icon_button_uses_atlas_when_resolved(tmp_path):
    """When the icon name resolves in the atlas, paint calls
    `dl.draw_image_file(path, ...)`. We capture the call to confirm
    the atlas → image-file path actually fires."""
    atlas = GlyphAtlas()
    img = tmp_path / "save.png"
    img.write_bytes(b"fake")
    atlas.register("save", str(img))
    captured: list[tuple] = []

    class _DL(_FakeDL):
        def draw_image_file(self, path, x, y, w, h):
            captured.append((path, x, y, w, h))

    btn = IconButton(x=10, y=10, w=40, h=40, icon="save", atlas=atlas,
                     icon_size=18.0)
    btn.paint(_DL())
    assert len(captured) == 1
    assert captured[0][0].endswith("save.png")


def test_icon_button_variants_paint_without_error():
    for variant in ("solid", "ghost", "outline"):
        btn = IconButton(x=0, y=0, w=32, h=32,
                         variant=variant, icon="x")
        btn.paint(_FakeDL())


def test_icon_button_fire_click_invokes_callback():
    calls: list[int] = []
    btn = IconButton(on_click=lambda: calls.append(1))
    btn.fire_click()
    btn.fire_click()
    assert calls == [1, 1]
    # Without callback, fire_click is a no-op (must not raise).
    IconButton().fire_click()
