"""Tier 8 Phase 3 — DataGrid: spreadsheet features over ItemModel."""
from __future__ import annotations

import pytest

from elysium import theme as T
from elysium.modelview import ItemModel, Column
from elysium.modelview.grid import DataGrid


@pytest.fixture(autouse=True)
def _studio():
    T.set_theme(T.studio_dark())
    yield
    T.set_theme(T.light())


def _grid(rows=8, w=600, h=300, frozen=2):
    cols = [Column(key="handle", width=120, align="left"),
            Column(key="title", width=160),
            Column(key="sku", width=100),
            Column(key="price", width=80, align="right"),
            Column(key="inv", width=60, align="right")]
    data = [{"handle": f"item-{i}", "title": f"Item {i}", "sku": f"SKU-{i}",
             "price": 10 + i, "inv": i * 5} for i in range(rows)]
    return DataGrid(model=ItemModel(rows=data, columns=cols),
                    x=0, y=0, w=w, h=h, frozen_cols=frozen)


def _render(g, w=600, h=300):
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    g.paint(dl)
    layer = n.SkiaLayer(w, h)
    layer.execute(dl)
    return bytes(layer.encode_png())


# --- columns ---------------------------------------------------------------

def test_visible_cols_hide_and_reorder():
    g = _grid()
    assert [c.key for c in g.visible_cols()][:3] == ["handle", "title", "sku"]
    g.set_col_visible("sku", False)
    assert "sku" not in [c.key for c in g.visible_cols()]
    g.set_col_visible("sku", True)
    g.move_col("price", 0)
    assert g.visible_cols()[0].key == "price"


def test_resize_clamps_min():
    g = _grid()
    g.resize_col("title", 10)
    assert next(c for c in g.model.columns if c.key == "title").width == 40.0


def test_frozen_vs_scrolled_col_x():
    g = _grid(frozen=2)
    g.scroll_x = 50
    # frozen columns ignore scroll_x
    assert g._col_x(0) == 0
    assert g._col_x(1) == 120
    # scrolled columns start after the frozen band, offset by scroll_x
    frozen_w = 120 + 160
    assert g._col_x(2) == pytest.approx(frozen_w - 50)


# --- hit-testing -----------------------------------------------------------

def test_cell_at_frozen_and_scrolled():
    g = _grid(frozen=2)
    # a frozen cell (first column, second row)
    cell = g.cell_at(10, g.header_h + g.row_h + 5)
    assert cell == (1, 0)
    # a scrolled cell (price column, index 3)
    px = g._col_x(3) + 5
    cell2 = g.cell_at(px, g.header_h + 5)
    assert cell2 == (0, 3)
    assert g.cell_at(10, 5) is None        # header → no cell


def test_header_border_for_resize():
    g = _grid()
    edge = g._col_x(0) + g.visible_cols()[0].width
    assert g.header_border_at(edge, 10) == "handle"
    assert g.header_border_at(edge, 200) is None   # below header


# --- selection -------------------------------------------------------------

def test_range_selection():
    g = _grid()
    g.select(1, 1)
    g.select(3, 3, extend=True)
    assert g.selected_range() == (1, 1, 3, 3)
    # press + shift-drag via on_press/on_drag
    g2 = _grid()
    assert g2.on_press(g2._col_x(0) + 5, g2.header_h + 5) is True
    g2.on_drag(g2._col_x(1) + 5, g2.header_h + g2.row_h * 2 + 5)
    assert g2.selected_range()[0] == 0 and g2.selected_range()[3] >= 1


# --- copy / paste / fill ---------------------------------------------------

def test_copy_range_to_tsv():
    g = _grid()
    g.select(0, 0)
    g.select(1, 1, extend=True)        # handle+title, rows 0-1
    tsv = g.copy()
    assert tsv == "item-0\tItem 0\nitem-1\tItem 1"


def test_paste_tsv_writes_marks_dirty_and_validates():
    g = _grid()
    g.validators["price"] = lambda v: None if str(v).replace(".", "").isdigit() \
        else "not a number"
    g.select(0, 3)                      # active = (row 0, price col)
    n = g.paste("99\nNaN\n120")         # 3 rows into price column
    assert n == 3
    assert g.model.value(0, "price") == "99"
    assert g.dirty_count() == 3
    # the "NaN" cell failed validation
    assert g.error_count() == 1
    assert g.cell_error(1, g.visible_cols()[3]) == "not a number"


def test_paste_rectangular_block():
    g = _grid()
    g.select(0, 0)
    g.paste("A\tB\nC\tD")               # 2×2 block into handle/title
    assert g.model.value(0, "handle") == "A"
    assert g.model.value(0, "title") == "B"
    assert g.model.value(1, "handle") == "C"
    assert g.model.value(1, "title") == "D"


def test_fill_down():
    g = _grid()
    g.model.set_value(0, "price", 42)
    g.select(0, 3)
    g.select(3, 3, extend=True)         # price col, rows 0-3
    written = g.fill_down()
    assert written == 3                 # rows 1,2,3
    assert all(g.model.value(r, "price") == 42 for r in range(4))


def test_clear_pending():
    g = _grid()
    g.select(0, 0)
    g.paste("x")
    assert g.dirty_count() == 1
    g.clear_pending()
    assert g.dirty_count() == 0 and g.error_count() == 0


# --- dirty survives sort ---------------------------------------------------

def test_dirty_keyed_by_row_identity_survives_sort():
    g = _grid()
    g.select(0, 3)
    g.paste("5")                        # edit first view-row's price
    row0 = g.model.view()[0]
    g.model.toggle_sort("price")        # reorder
    # the edited row is dirty wherever it now sits
    new_index = g.model.view().index(row0)
    assert g.is_dirty(new_index, g.visible_cols()[3])


# --- render ----------------------------------------------------------------

def test_grid_renders_with_selection_and_badges():
    g = _grid(rows=20)
    g.validators["price"] = lambda v: "bad" if v == "x" else None
    g.select(1, 1)
    g.select(4, 3, extend=True)
    g.paste("x")                        # creates a validation error badge
    assert _render(g)[:4] == b"\x89PNG"
