"""Tier-2 acceptance test: the major subsystems composed end-to-end, plus the
runnable tier2-demo built + painted headlessly.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from elysium.testing import UiHarness, CaptureDL
from elysium.components.scroll import ScrollView
from elysium.components.virtual import VirtualList
from elysium.concurrency import UiDispatcher
from elysium.windowing import WindowManager
from elysium.settings import Settings
from elysium import i18n, native
import elysium as ely


def test_virtualized_scroll_through_router():
    """Wheel events route through the InputRouter to a virtualized list and
    shift the visible window — scale + scroll + input composed."""
    painted = []
    vl = VirtualList(x=0, y=0, w=400, h=300, item_count=10_000, item_height=20.0,
                     render_item=lambda dl, i, *a: painted.append(i))
    h = UiHarness([vl])
    h.scroll(0, -2000, at=(50, 50))      # wheel down 2000px → row 100
    h.paint()
    assert painted and 98 <= painted[0] <= 100
    assert len(painted) < 25             # only the visible window painted


def test_threading_marshal_into_frame():
    """A worker posts results; the FrameLoop-style drain applies them."""
    d = UiDispatcher()
    out = []
    import threading
    t = threading.Thread(target=lambda: d.post(out.append, "from-worker"))
    t.start(); t.join()
    assert out == []
    d.drain()
    assert out == ["from-worker"]


def test_modal_window_blocks_owner():
    app = ely.App(title="t", identifier="dev.test.tier2.integration")
    wm = WindowManager(app)
    main = wm.open(initial_size=(800, 600))
    dlg = wm.open(owner=main, modal=True, initial_size=(300, 200))
    assert main.input_blocked
    wm.close(dlg)
    assert not main.input_blocked


def test_settings_and_locale_and_native(tmp_path):
    s = Settings("tier2-int", path=tmp_path / "s.json", autosave=True)
    s.set("rows", 12345)
    assert Settings("tier2-int", path=tmp_path / "s.json").get("rows") == 12345

    i18n.load_json_catalog({"Save": "حفظ"}, locale="ar")
    assert i18n.is_rtl() and i18n.tr("Save") == "حفظ"
    i18n.load_json_catalog({}, locale="en")

    caps = native.capabilities()
    assert caps["single_instance"] and caps["power_events"]


def test_scrollview_clips_and_translates():
    sv = ScrollView(x=0, y=0, w=200, h=200, content_w=200, content_h=900)
    sv.scroll_y = 100.0
    dl = CaptureDL()
    sv.paint(dl, lambda d: None)
    assert dl.calls.get("push_clip") and dl.calls.get("push_transform")


def test_tier2_demo_builds_and_virtualizes_headless():
    demo_path = (Path(__file__).resolve().parent.parent
                 / "examples" / "tier2-demo" / "main.py")
    spec = importlib.util.spec_from_file_location("tier2_demo_main", demo_path)
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    ui = demo.build_ui()
    assert ui["rows"].item_count >= 1
    dl = CaptureDL()
    ui["rows"].paint(dl)
    # 10k rows but only the visible window draws text.
    assert dl.calls.get("draw_text", 0) < 60
