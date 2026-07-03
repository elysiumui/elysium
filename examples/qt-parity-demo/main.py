"""Qt-parity demo — a borderless CRUD app exercising every Tier-1 feature.

Showcases the Tier-1 Qt-parity work in one screen:

  * Validated text input (TextField + IntValidator), IME-ready, clipboard.
  * Data-entry widgets: SpinBox, DateEdit, EditableComboBox.
  * A virtualized, sortable, editable data TableView over an ItemModel.
  * Standard dialogs: message / input / color (Elysium-rendered, borderless).
  * One framework InputRouter routing keys/text/IME/clipboard to the focused
    widget; one DialogHost for modal flows.

All in a borderless, GPU-rendered window with corner-resize — the
differentiator vs Qt's native chrome.

Run:  python examples/qt-parity-demo/main.py
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import elysium as ely
from elysium._native import _native as _n
from elysium import theme as T
from elysium.components import TextField, Label, Button
from elysium.components.dataentry import SpinBox, DateEdit, EditableComboBox
from elysium.modelview import ItemModel, Column, TableView, EditableCellDelegate, TextDelegate
from elysium import dialogs as D

WIDTH, HEIGHT = 1000, 640


def build_ui():
    """Construct the widget tree + model. Returned as a dict so it can be
    smoke-tested headlessly (no window required)."""
    model = ItemModel(
        rows=[
            {"name": "Ada Lovelace", "role": "Engineer", "age": 36},
            {"name": "Alan Turing", "role": "Researcher", "age": 41},
            {"name": "Grace Hopper", "role": "Admiral", "age": 85},
            {"name": "Katherine Johnson", "role": "Mathematician", "age": 101},
        ],
        columns=[
            Column("name", width=200, editable=True, delegate=EditableCellDelegate()),
            Column("role", width=160, editable=True, delegate=EditableCellDelegate()),
            Column("age", width=70, align="right", delegate=TextDelegate(align="right")),
        ],
    )

    name = TextField(x=40, y=120, w=260, h=44, label="Name", focus_id="name")
    role = EditableComboBox(x=40, y=180, w=260, h=40, focus_id="role",
                            placeholder="Role",
                            items=["Engineer", "Researcher", "Admiral",
                                   "Mathematician", "Designer"])
    age = SpinBox(x=40, y=232, w=120, h=40, focus_id="age",
                  value=30, minimum=0, maximum=120, suffix=" yrs")
    born = DateEdit(x=176, y=232, w=124, h=40, focus_id="born",
                    date=dt.date(1990, 1, 1))

    table = TableView(x=340, y=120, w=620, h=420, model=model, row_height=30.0)

    widgets = {"name": name, "role": role, "age": age, "born": born, "table": table}
    return {"model": model, "widgets": widgets,
            "focusables": [name, role, age, born]}


def main() -> None:
    ui = build_ui()
    model = ui["model"]
    name = ui["widgets"]["name"]
    role = ui["widgets"]["role"]
    age = ui["widgets"]["age"]
    born = ui["widgets"]["born"]
    table = ui["widgets"]["table"]

    app = ely.App(title="Qt-Parity Demo", identifier="dev.elysium.qtparity")
    win = app.window(transparent=True, title_bar=False, resizable=True,
                     initial_size=(WIDTH, HEIGHT))
    try: win.set_has_shadow(False)
    except Exception: pass

    router = win.input_router()
    router.set_widgets(ui["focusables"])
    router.focus_widget("name")
    host = D.DialogHost(win)

    def add_person():
        model.append({"name": name.value or "Unnamed",
                      "role": role.value or "—",
                      "age": age.value})
        name.set_value(""); role.value = ""; role._edit.set_text("")

    def confirm_clear():
        dlg = host.message("Clear all?", "Remove every row from the table?",
                           buttons=["Cancel", "Clear"])
        def on_done(_):
            if dlg.result == "Clear":
                model.clear()
        dlg.on_result = on_done

    add_btn = Button(x=40, y=300, w=120, h=40, label="Add",
                     variant="solid", on_click=add_person)
    clear_btn = Button(x=176, y=300, w=120, h=40, label="Clear…",
                       variant="outline", on_click=confirm_clear)
    color_btn = Button(x=40, y=360, w=256, h=40, label="Pick accent color…",
                       variant="ghost",
                       on_click=lambda: host.color(initial=(122, 88, 244, 255)))

    state = {"running": True, "last_press": 0, "last_rmb": 0}

    def on_frame():
        if not state["running"]:
            return
        dt_s = 1.0 / 60.0
        cur = win.cursor_position
        pressed = win.mouse_pressed
        pc = win.press_count
        press_just = pc != state["last_press"]
        state["last_press"] = pc

        # Route input to focused widget / dialogs.
        if host.is_modal:
            host.update(dt_s)
        else:
            router.tick()

        # Click dispatch.
        if press_just and cur is not None:
            if host.is_modal:
                host.on_mouse_press(*cur)
            else:
                # focus + widget-specific presses
                for wid in ui["focusables"]:
                    fx, fy, fw, fh = wid.focus_rect()
                    if fx <= cur[0] <= fx + fw and fy <= cur[1] <= fy + fh:
                        router.focus_widget(wid.focus_id)
                        if hasattr(wid, "on_mouse_press"):
                            wid.on_mouse_press(*cur)
                        break
                table.on_mouse_press(*cur)
                for b in (add_btn, clear_btn, color_btn):
                    if b.hit_test(*cur):
                        b.fire_click()

        # Paint.
        dl = _n.DisplayList()
        t = T.current_theme()
        dl.clear(t.surface[0] / 255, t.surface[1] / 255, t.surface[2] / 255, 0.96)
        dl.draw_text("Qt-Parity Demo — Tier 1", 40, 60, 22, t.on_surface)
        dl.draw_text("People", 340, 100, 14, t.on_surface_muted)
        for wid in (name, role, age, born, table, add_btn, clear_btn, color_btn):
            try:
                wid.update(dt_s, {"focused": getattr(wid, "focus_id", None) == router.focus.focused_id})
            except Exception:
                pass
            wid.paint(dl)
        if host.is_modal:
            host.paint(dl)
        win.publish_display_list(dl)

    def quit_on_esc():
        while state["running"]:
            ev = win.poll_key_event()
            if ev is None:
                time.sleep(0.05); continue
            code, pressed, _m, _t = ev
            if code == "Escape" and pressed and not host.is_modal:
                state["running"] = False; app.quit(); return

    import threading
    threading.Thread(target=lambda: _loop(on_frame, state), daemon=True).start()
    app.run()
    state["running"] = False


def _loop(on_frame, state):
    while state["running"]:
        try:
            on_frame()
        except Exception as e:
            print(f"frame error: {e}", file=sys.stderr)
        time.sleep(1.0 / 60.0)


if __name__ == "__main__":
    main()
