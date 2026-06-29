"""Tier 6 Phase 3 — inter-widget drag-and-drop: MimeData / DropZone / DragController."""
from __future__ import annotations

from elysium import theme as T
from elysium.dnd import MimeData, DropZone, DragController, TEXT


def test_mimedata_text_and_formats():
    m = MimeData.from_text("hello")
    assert m.text == "hello" and m.has_format(TEXT)
    m.set_data("application/x-id", 42)
    assert m.data("application/x-id") == 42
    assert set(m.formats()) == {TEXT, "application/x-id"}
    assert m.data("missing", "def") == "def"


def test_dropzone_contains_rect_and_custom_hit():
    z = DropZone(rect=(10, 10, 100, 50))
    assert z.contains(50, 30) and not z.contains(5, 5)
    z2 = DropZone(hit=lambda x, y: x > 100)
    assert z2.contains(150, 0) and not z2.contains(50, 0)


def test_threshold_keeps_click_from_dragging():
    c = DragController()
    c.add_zone(DropZone(rect=(0, 0, 200, 200)))
    c.press(50, 50, MimeData.from_text("x"))
    assert c.move(52, 51) is False   # within threshold → not dragging
    assert not c.is_dragging()
    c.move(70, 70)                   # past threshold → dragging
    assert c.is_dragging()


def test_drop_delivers_to_accepting_zone():
    dropped = []
    c = DragController()
    c.add_zone(DropZone(rect=(0, 0, 100, 100),
                        accept=lambda m: m.has_format(TEXT),
                        on_drop=lambda m, x, y: dropped.append((m.text, x, y)) or True))
    c.press(50, 50, MimeData.from_text("payload"))
    c.move(80, 80)
    assert c.is_dragging()
    assert c.release(60, 60) is True
    assert dropped == [("payload", 60, 60)]
    assert not c.is_dragging()


def test_drop_rejected_outside_or_by_predicate():
    c = DragController()
    # zone only accepts a custom format the drag doesn't carry
    c.add_zone(DropZone(rect=(0, 0, 100, 100),
                        accept=lambda m: m.has_format("application/x-card"),
                        on_drop=lambda m, x, y: True))
    c.press(50, 50, MimeData.from_text("plain"))
    c.move(80, 80)
    assert c.current_target() is None      # predicate rejects → no target
    assert c.release(60, 60) is False
    # drop outside any zone
    c.press(50, 50, MimeData.from_text("plain"))
    c.move(80, 80)
    assert c.release(500, 500) is False


def test_topmost_accepting_zone_wins():
    c = DragController()
    hits = []
    c.add_zone(DropZone(rect=(0, 0, 200, 200),
                        on_drop=lambda m, x, y: hits.append("bottom") or True))
    c.add_zone(DropZone(rect=(50, 50, 100, 100),
                        on_drop=lambda m, x, y: hits.append("top") or True))
    c.press(10, 10, MimeData.from_text("x"))
    c.move(80, 80)
    c.release(80, 80)               # overlaps both; last-added (top) wins
    assert hits == ["top"]


def test_cancel_aborts_drag():
    c = DragController()
    c.add_zone(DropZone(rect=(0, 0, 100, 100), on_drop=lambda m, x, y: True))
    c.press(20, 20, MimeData.from_text("x"))
    c.move(60, 60)
    c.cancel()
    assert not c.is_dragging()
    assert c.release(60, 60) is False


def test_controller_paints_ghost_and_highlight():
    T.set_theme(T.studio_dark())
    from elysium._native import _native as n
    c = DragController()
    c.add_zone(DropZone(rect=(120, 40, 140, 120), on_drop=lambda m, x, y: True))
    c.press(40, 60, MimeData.from_text("Card"))
    c.move(160, 90)                 # dragging, hovering the zone
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    c.paint(dl)
    layer = n.SkiaLayer(320, 200)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"
    T.set_theme(T.light())
