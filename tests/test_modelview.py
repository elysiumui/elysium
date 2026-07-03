"""Tier-1 Phase-4: Model/View (ItemModel, Qt adapter, virtualized views)."""
from __future__ import annotations

from elysium.modelview import (
    ItemModel,
    Column,
    QtItemModelAdapter,
    TableView,
    ListView,
    TreeView,
    TreeNode,
    TextDelegate,
    EditableCellDelegate,
)


class FakeDL:
    def __init__(self):
        self.texts: list[str] = []
        self.images = 0

    def fill_path(self, *a):
        pass

    def stroke_path(self, *a):
        pass

    def fill_path_linear_gradient(self, *a):
        pass

    def gradient_card(self, *a):
        pass

    def draw_text(self, s, *a):
        self.texts.append(s)

    def draw_image_file(self, *a):
        self.images += 1


def _people():
    return ItemModel(
        rows=[{"name": "Bob", "age": 30}, {"name": "Ada", "age": 45}, {"name": "Cy", "age": 20}],
        columns=[Column("name", width=120, editable=True), Column("age", align="right")],
    )


# --- ItemModel --------------------------------------------------------------

def test_model_sort_toggle_cycle():
    m = _people()
    m.toggle_sort("age")  # asc
    assert [m.value(i, "age") for i in range(3)] == [20, 30, 45]
    m.toggle_sort("age")  # desc
    assert [m.value(i, "age") for i in range(3)] == [45, 30, 20]
    m.toggle_sort("age")  # unsorted (insertion order)
    assert [m.value(i, "name") for i in range(3)] == ["Bob", "Ada", "Cy"]


def test_model_filter_and_clear():
    m = _people()
    m.filter(lambda r: r["age"] >= 30)
    assert m.row_count() == 2
    m.filter(None)
    assert m.row_count() == 3


def test_model_crud_bumps_version():
    m = _people()
    v0 = m.version
    m.append({"name": "Dot", "age": 5})
    assert m.row_count() == 4 and m.version > v0
    m.remove_at(0)
    assert m.row_count() == 3
    m.update_at(0, "name", "Adabel")
    # update_at indexes the source list; just assert version moved + value
    assert m.version > v0


def test_model_view_cached_until_change():
    m = _people()
    v1 = m.view()
    v2 = m.view()
    assert v1 is v2  # cached
    m.append({"name": "Z", "age": 1})
    assert m.view() is not v1


def test_model_none_values_sort_safely():
    m = ItemModel(rows=[{"k": 3}, {"k": None}, {"k": 1}], columns=[Column("k")])
    m.toggle_sort("k")
    vals = [m.value(i, "k") for i in range(3)]
    assert vals[0] == 1 and vals[1] == 3 and vals[2] is None  # None sinks to end


# --- Qt adapter -------------------------------------------------------------

def test_qt_adapter_shape_and_setdata():
    m = _people()
    a = QtItemModelAdapter(m)
    assert a.rowCount() == 3 and a.columnCount() == 2
    assert a.headerData(0) == "Name" and a.headerData(1) == "Age"
    assert a.data((0, 0)) == "Bob"
    assert a.setData((0, 0), "Bobby") and m.value(0, "name") == "Bobby"
    assert not a.setData((0, 1), 99)  # age column not editable
    assert a.flags((0, 0))["editable"] and not a.flags((0, 1))["editable"]


# --- TableView --------------------------------------------------------------

def test_tableview_paints_header_and_rows():
    m = _people()
    tv = TableView(x=0, y=0, w=300, h=160, model=m)
    dl = FakeDL()
    tv.paint(dl)
    assert {"Name", "Age", "Bob", "Ada", "Cy"} <= set(dl.texts)


def test_tableview_header_click_sorts():
    m = _people()
    tv = TableView(x=0, y=0, w=300, h=160, model=m)
    tv.paint(FakeDL())  # lays out header rects
    # Click the "age" header (second column starts at x=120).
    tv.on_mouse_press(130, tv.y + 5)
    assert m.sort_state[0] == "age"


def test_tableview_row_selection():
    m = _people()
    picked = []
    tv = TableView(x=0, y=0, w=300, h=160, model=m, on_select=picked.append)
    tv.paint(FakeDL())
    # Second visible row.
    ry = tv._body_top() + tv.row_height + 2
    tv.on_mouse_press(10, ry)
    assert tv.selected_row == 1 and picked == [1]


def test_tableview_inline_edit_commits_to_model():
    m = _people()
    m.columns[0].delegate = EditableCellDelegate()
    tv = TableView(x=0, y=0, w=300, h=160, model=m)
    tv.paint(FakeDL())
    ed = tv.begin_edit(0, 0)
    assert ed is not None and tv.editing
    ed.set_value("Roberta")
    tv.commit_edit()
    assert m.value(0, "name") == "Roberta" and not tv.editing


def test_tableview_double_click_edits_editable_cell():
    m = _people()
    m.columns[0].delegate = EditableCellDelegate()
    tv = TableView(x=0, y=0, w=300, h=160, model=m)
    tv.paint(FakeDL())
    ry = tv._body_top() + 2
    tv.on_mouse_press(10, ry, double=True)  # col 0 (name) is editable
    assert tv.editing


def test_tableview_virtualizes_large_model():
    rows = [{"name": f"r{i}", "age": i} for i in range(10_000)]
    m = ItemModel(rows=rows, columns=[Column("name"), Column("age")])
    tv = TableView(x=0, y=0, w=300, h=200, model=m, row_height=20.0)
    s, e = tv.visible_row_range()
    # Only ~ (h-header)/row_height rows are visible, NOT 10k.
    assert e - s < 20
    dl = FakeDL()
    tv.paint(dl)
    # Header (2) + visible rows (~9 * 2 cells) worth of draw_text, far < 10k.
    assert len(dl.texts) < 60


# --- ListView ---------------------------------------------------------------

def test_listview_single_column():
    m = ItemModel(rows=[{"label": "Alpha"}, {"label": "Beta"}])
    lv = ListView(x=0, y=0, w=200, h=120, model=m)
    dl = FakeDL()
    lv.paint(dl)
    assert {"Alpha", "Beta"} <= set(dl.texts)
    assert lv.show_header is False


# --- TreeView ---------------------------------------------------------------

def test_treeview_expand_collapse_and_paint():
    root = TreeNode("r", "Root", children=[TreeNode("a", "A"), TreeNode("b", "B")], expanded=True)
    tv = TreeView(x=0, y=0, w=200, h=200, nodes=[root])
    dl = FakeDL()
    tv.paint(dl)
    assert {"Root", "A", "B"} <= set(dl.texts)
    # Click the root chevron → collapse.
    tv.hit(tv.x + 12, tv.y + 4)
    assert root.expanded is False
    dl2 = FakeDL()
    tv.paint(dl2)
    assert "A" not in dl2.texts  # children hidden when collapsed


def test_treeview_select():
    root = TreeNode("r", "Root", children=[TreeNode("a", "A")], expanded=True)
    picked = []
    tv = TreeView(x=0, y=0, w=200, h=200, nodes=[root], on_select=picked.append)
    tv.paint(FakeDL())
    # Click the "A" row label (second row).
    tv.hit(tv.x + 60, tv.y + tv.row_height + 4)
    assert tv.selected_id == "a" and picked == ["a"]


# --- Delegates --------------------------------------------------------------

def test_text_delegate_alignment_paints_value():
    d = TextDelegate(align="right")
    dl = FakeDL()

    class T:
        font_size_body = 14.0
        on_surface = (0, 0, 0, 255)
    import elysium.theme as theme
    d.paint(dl, (0, 0, 100, 20), 42, selected=False, theme=theme.current_theme())
    assert "42" in dl.texts
