"""Tier-3: end-to-end real-world app flows (CRUD, multi-window, threading,
scroll+virtualization), driven through the public API the way an app would.
"""
from __future__ import annotations

import threading

from elysium.testing import UiHarness, CaptureDL, CTRL
from elysium.components import TextField
from elysium.components.dataentry import SpinBox
from elysium.components.virtual import VirtualList
from elysium.modelview import ItemModel, Column, TableView, EditableCellDelegate
from elysium.concurrency import UiDispatcher
from elysium.windowing import WindowManager
from elysium.settings import Settings
import elysium as ely


# --- CRUD journey -----------------------------------------------------------

def test_crud_create_edit_sort_filter_delete_persist(tmp_path):
    model = ItemModel(
        rows=[{"name": "Bob", "age": 30}, {"name": "Ada", "age": 45}],
        columns=[Column("name", width=120, editable=True, delegate=EditableCellDelegate()),
                 Column("age", align="right")],
    )
    table = TableView(x=0, y=0, w=320, h=240, model=model)

    name = TextField(x=0, y=260, w=160, h=32, focus_id="name")
    age = SpinBox(x=170, y=260, w=100, h=32, focus_id="age", value=20, minimum=0, maximum=120)
    h = UiHarness([name, age, table])

    # CREATE — type into the form, then append.
    h.focus("name").type("Cy")
    h.focus("age")
    for _ in range(7):           # 20 -> 27 via Up arrow
        h.key("ArrowUp")
    model.append({"name": name.value, "age": age.value})
    assert model.row_count() == 3

    # READ — sort by age asc, then filter.
    h.paint()                    # lay out header rects
    h.click(table._col_x(1) + 5, table.y + 5)        # header click → sort age
    assert [model.value(i, "age") for i in range(3)] == [27, 30, 45]
    model.filter(lambda r: r["age"] >= 30)
    assert model.row_count() == 2

    # UPDATE — inline-edit the first visible name.
    model.filter(None)
    table.begin_edit(0, 0)
    table._editor.set_value("Cyrus")
    table.commit_edit()
    assert "Cyrus" in [model.value(i, "name") for i in range(3)]

    # DELETE.
    model.remove(model.view()[0])
    assert model.row_count() == 2

    # PERSIST — round-trip through Settings.
    s = Settings("crud-e2e", path=tmp_path / "s.json")
    s.set("rows", model.rows())
    s.save()
    assert Settings("crud-e2e", path=tmp_path / "s.json").get("rows") == model.rows()


# --- multi-window flow ------------------------------------------------------

def test_multiwindow_modal_message_cascade():
    app = ely.App(title="t", identifier="dev.test.t3.mw")
    wm = WindowManager(app)
    main = wm.open(initial_size=(800, 600))
    got = []
    wm.on_message(main, got.append)

    dlg = wm.open(owner=main, modal=True, initial_size=(300, 200))
    assert main.input_blocked                      # modal blocks owner
    wm.send(main, {"hello": 1})
    main.ui_dispatcher().drain()
    assert got == [{"hello": 1}]

    child = wm.open(owner=main, initial_size=(100, 100))
    wm.close(main)                                 # cascade closes dlg + child
    assert wm.children(main) == []
    assert not wm.modal_active


# --- threading under load ---------------------------------------------------

def test_threading_many_workers_marshal_in_order():
    d = UiDispatcher()
    received: list[int] = []
    N = 200

    def worker(start):
        for i in range(start, start + 50):
            d.post(received.append, i)

    threads = [threading.Thread(target=worker, args=(b,)) for b in (0, 50, 100, 150)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Nothing ran on worker threads; drain on the UI thread applies all.
    assert received == []
    total = 0
    while d.pending():
        total += d.drain()
    assert total == N and len(received) == N and set(received) == set(range(N))


# --- scroll + virtualization ------------------------------------------------

def test_scroll_virtualization_flow():
    painted: list[int] = []
    vl = VirtualList(x=0, y=0, w=400, h=300, item_count=50_000, item_height=20.0,
                     render_item=lambda dl, i, *a: painted.append(i))
    h = UiHarness([vl])

    h.paint()
    first_top = painted[0]
    assert first_top == 0 and len(painted) < 25      # only the visible window

    painted.clear()
    h.scroll(0, -4000, at=(50, 50))                  # wheel down 4000px → row 200
    h.paint()
    assert 198 <= painted[0] <= 200
    assert len(painted) < 25                          # still windowed at depth
