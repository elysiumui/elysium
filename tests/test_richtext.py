"""Tier 6 Phase 2 — rich text: RichDocument layout + RichTextView."""
from __future__ import annotations

import pytest

from elysium import theme as T
from elysium.text.richtext import (
    Run, Image, Break, RichDocument, RichTextView,
)


@pytest.fixture(autouse=True)
def _studio():
    T.set_theme(T.studio_dark())
    yield
    T.set_theme(T.light())


def test_layout_places_runs_left_to_right_on_one_line():
    doc = RichDocument(default_size=16)
    doc.add(Run(text="Hello")).add(Run(text=" world", bold=True))
    placements, height = doc.layout(width=1000)   # wide → single line
    xs = [p.x for p in placements]
    assert xs == sorted(xs)                        # left to right
    assert all(p.baseline == placements[0].baseline for p in placements)
    assert height > 0


def test_layout_wraps_at_width():
    doc = RichDocument(default_size=16)
    doc.add(Run(text="word " * 30))
    placements, height = doc.layout(width=160)
    ys = {round(p.y) for p in placements}
    assert len(ys) > 1                             # wrapped onto several lines
    tall = doc.layout(width=160)[1]
    wide = doc.layout(width=2000)[1]
    assert tall > wide                             # narrower → taller


def test_break_starts_new_paragraph():
    doc = RichDocument(default_size=16)
    doc.add(Run(text="para one"))
    doc.add(Break())
    doc.add(Run(text="para two"))
    placements, _ = doc.layout(width=1000)
    one = [p for p in placements if p.text == "one"][0]
    two = [p for p in placements if p.text == "two"][0]
    assert two.y > one.y                           # second paragraph lower


def test_mixed_sizes_share_a_baseline():
    doc = RichDocument(default_size=14)
    doc.add(Run(text="small")).add(Run(text=" BIG", size=28))
    placements, _ = doc.layout(width=1000)
    # baselines equal; the bigger run sits higher (smaller y/top)
    assert placements[0].baseline == pytest.approx(placements[-1].baseline)
    big = [p for p in placements if p.run.size == 28][0]
    small = [p for p in placements if p.text == "small"][0]
    assert big.y < small.y


def test_link_hit_testing():
    doc = RichDocument(default_size=16)
    doc.add(Run(text="visit ")).add(
        Run(text="elysium", link="https://example.test"))
    view = RichTextView(document=doc, x=10, y=20, w=1000)
    view.relayout()
    link_p = [p for p in view._placements if p.link][0]
    # hit inside the link run (offset by the view origin)
    hit = view.link_at(10 + link_p.x + 2, 20 + link_p.y + 2)
    assert hit == "https://example.test"
    assert view.link_at(10, 20 + 200) is None      # far below → no link


def test_on_click_fires_link_callback():
    fired = []
    doc = RichDocument()
    doc.add(Run(text="go", link="L"))
    view = RichTextView(document=doc, x=0, y=0, w=1000,
                        on_link=lambda url: fired.append(url))
    view.relayout()
    p = view._placements[0]
    assert view.on_click(p.x + 1, p.y + 1) is True
    assert fired == ["L"]


def test_view_renders_styled_document():
    from elysium._native import _native as n
    doc = RichDocument(default_size=16)
    doc.add(Run(text="The ")).add(Run(text="quick", bold=True))
    doc.add(Run(text=" brown ")).add(Run(text="fox", italic=True, color=(240, 160, 60, 255)))
    doc.add(Run(text=" jumps. "))
    doc.add(Run(text="A link", link="https://x.test"))
    doc.add(Break())
    doc.add(Image(w=60, h=40))
    doc.add(Run(text=" inline image."))
    view = RichTextView(document=doc, x=12, y=12, w=360)
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    view.paint(dl)
    assert view.content_height() > 0
    layer = n.SkiaLayer(400, 200)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"


# --- notes-app demo smoke (Tier 6 Phase 4) ---------------------------------

def test_notes_demo_reorder_undo_and_paint():
    import importlib.util
    import sys
    from elysium._native import _native as n
    spec = importlib.util.spec_from_file_location(
        "notes_demo", "examples/notes-demo/main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["notes_demo"] = mod   # dataclasses need the module registered
    spec.loader.exec_module(mod)
    app = mod.build_app(900, 600)
    titles = [nt.title for nt in app["notes"]]
    assert app["undo_action"].enabled is False     # nothing to undo yet
    app["reorder"](0, 2)                            # move first note to the end
    assert [nt.title for nt in app["notes"]] == titles[1:] + titles[:1]
    assert app["undo_action"].enabled is True
    app["undo"].undo()                              # reorder is undoable
    assert [nt.title for nt in app["notes"]] == titles
    # paint the whole app headlessly
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    mod.paint_app(dl, app, 900, 600)
    layer = n.SkiaLayer(900, 600)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"
