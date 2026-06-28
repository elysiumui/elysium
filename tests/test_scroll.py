"""Tier-2 Phase-2: scroll system (ScrollBar, ScrollView, wheel routing)."""
from __future__ import annotations

from elysium.components.scroll import ScrollBar, ScrollView
from elysium.input import InputRouter


class FakeDL:
    def __init__(self):
        self.ops: list[str] = []

    def push_clip(self, *a): self.ops.append("push_clip")
    def pop_clip(self, *a): self.ops.append("pop_clip")
    def push_transform(self, *a): self.ops.append(("push_transform", a))
    def pop_transform(self, *a): self.ops.append("pop_transform")
    def fill_path(self, *a): self.ops.append("fill_path")
    def stroke_path(self, *a): pass


class FakeWindow:
    def __init__(self, cursor=(0, 0)):
        self._scroll = []
        self.cursor_position = cursor

    def queue_scroll(self, dx, dy, precise=False):
        self._scroll.append((dx, dy, precise))

    def poll_scroll_delta(self):
        return self._scroll.pop(0) if self._scroll else (0.0, 0.0, False)

    def poll_key_event(self):
        return None

    def preedit(self):
        return ""


# --- ScrollBar --------------------------------------------------------------

def test_scrollbar_thumb_proportional_to_viewport():
    sb = ScrollBar(x=0, y=0, w=10, h=200, content=400, viewport=200)
    start, length = sb.thumb_extent()
    # viewport/content = 0.5 → half the 200px track.
    assert abs(length - 100.0) < 1e-6
    assert abs(start - 0.0) < 1e-6  # value 0 → top


def test_scrollbar_thumb_tracks_value():
    sb = ScrollBar(x=0, y=0, w=10, h=200, content=400, viewport=200, value=200)
    start, length = sb.thumb_extent()
    # max_offset=200, value=200 → frac 1 → thumb at bottom.
    assert abs(start - (200 - length)) < 1e-6


def test_scrollbar_min_thumb_size():
    sb = ScrollBar(x=0, y=0, w=10, h=200, content=100000, viewport=200, min_thumb=24)
    _, length = sb.thumb_extent()
    assert length == 24.0


def test_scrollbar_drag_maps_to_offset():
    moved = []
    sb = ScrollBar(x=0, y=0, w=10, h=200, content=400, viewport=200, on_change=moved.append)
    # Press on the thumb (top half), then drag down 50px.
    assert sb.on_mouse_press(5, 10)
    sb.on_mouse_drag(5, 60)
    # thumb length=100, span=100; 50px drag → 50% of max_offset(200) = 100.
    assert abs(sb.value - 100.0) < 1e-6
    assert moved and abs(moved[-1] - 100.0) < 1e-6
    sb.on_mouse_release()


def test_scrollbar_click_track_pages():
    sb = ScrollBar(x=0, y=0, w=10, h=200, content=600, viewport=200)
    # Click below the thumb → page down by one viewport.
    sb.on_mouse_press(5, 190)
    assert abs(sb.value - 200.0) < 1e-6


def test_scrollbar_clamps_offset():
    sb = ScrollBar(x=0, y=0, w=10, h=200, content=400, viewport=200)
    sb.set_value(99999)
    assert sb.value == sb.max_offset() == 200.0
    sb.set_value(-50)
    assert sb.value == 0.0


def test_scrollbar_autohide_when_not_needed():
    sb = ScrollBar(x=0, y=0, w=10, h=200, content=150, viewport=200)
    assert not sb.needed()
    dl = FakeDL()
    sb.paint(dl)
    assert dl.ops == []  # nothing painted


# --- ScrollView -------------------------------------------------------------

def test_scrollview_on_scroll_clamps():
    sv = ScrollView(x=0, y=0, w=200, h=200, content_w=200, content_h=600)
    sv.on_scroll(0, -50)        # wheel down → content up
    assert sv.scroll_y == 50.0
    sv.on_scroll(0, 99999)
    assert sv.scroll_y == 0.0   # clamp at top
    sv.on_scroll(0, -99999)
    assert sv.scroll_y == sv.max_y()


def test_scrollview_viewport_shrinks_for_vertical_bar():
    sv = ScrollView(x=0, y=0, w=200, h=200, content_w=100, content_h=600,
                    bar_thickness=12)
    # Vertical content overflows → vbar shown → viewport width shrinks.
    assert sv._vbar_visible()
    assert sv.viewport_w() == 188.0


def test_scrollview_scroll_to_rect():
    sv = ScrollView(x=0, y=0, w=200, h=200, content_w=200, content_h=1000)
    sv.scroll_to_rect(0, 500, 50, 50)
    # Rect bottom at 550 must be visible in a 200-tall viewport → scroll 350.
    assert sv.scroll_y == 350.0
    sv.scroll_to_rect(0, 100, 10, 10)
    assert sv.scroll_y == 100.0  # scroll back up to show it


def test_scrollview_paint_emits_clip_and_transform():
    sv = ScrollView(x=10, y=20, w=200, h=200, content_w=100, content_h=600)
    sv.scroll_y = 40.0
    dl = FakeDL()
    painted = []
    sv.paint(dl, lambda d: painted.append(True))
    assert "push_clip" in dl.ops and "pop_clip" in dl.ops
    # Content translated up by scroll_y (and offset by the view origin).
    tx = [op for op in dl.ops if isinstance(op, tuple) and op[0] == "push_transform"][0]
    assert tx[1][0] == 10.0 and tx[1][1] == 20.0 - 40.0
    assert painted == [True]


def test_scrollview_momentum_decays_to_stop():
    sv = ScrollView(x=0, y=0, w=200, h=200, content_w=200, content_h=2000)
    sv.on_scroll(0, -40, precise=True)  # a flick sets velocity
    assert sv._vel != (0.0, 0.0)
    for _ in range(600):
        sv.update(1 / 60.0)
    assert sv._vel == (0.0, 0.0)        # eventually halts
    assert 0.0 <= sv.scroll_y <= sv.max_y()


# --- Router wheel routing ---------------------------------------------------

def test_router_routes_wheel_to_hovered_scrollable():
    win = FakeWindow(cursor=(50, 50))
    r = InputRouter(win)
    sv = ScrollView(x=0, y=0, w=200, h=200, content_w=200, content_h=600)
    r.set_scrollables([sv])
    win.queue_scroll(0, -30)
    r.tick()
    assert sv.scroll_y == 30.0


def test_router_ignores_wheel_outside_scrollable():
    win = FakeWindow(cursor=(500, 500))  # cursor outside the view
    r = InputRouter(win)
    sv = ScrollView(x=0, y=0, w=200, h=200, content_w=200, content_h=600)
    r.set_scrollables([sv])
    win.queue_scroll(0, -30)
    r.tick()
    assert sv.scroll_y == 0.0
