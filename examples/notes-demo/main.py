"""Notes demo — Tier 6 documents & editing in one screen.

Ties the three Tier-6 pieces together:

  * `elysium.text.richtext` — each note's body is a styled `RichDocument`
    (headings, bold/italic, colour, links) shown in a `RichTextView`.
  * `elysium.commands` — reordering / adding / deleting notes go through an
    `UndoStack` as `Command`s, with `Action`s driving the Undo/Redo toolbar
    buttons; the status bar shows the clean ("saved ●") state.
  * `elysium.dnd` — drag a note in the sidebar to reorder it (the drop runs a
    `ReorderCommand`, so the reorder is itself undoable).

`build_app()` / `paint_app()` keep it headlessly testable; `main()` opens the
borderless, Studio-themed window.

Run:  python examples/notes-demo/main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field

from elysium import theme as T
from elysium.components import _rounded_rect
from elysium.commands import Command, UndoStack, Action
from elysium.dnd import MimeData, DropZone, DragController
from elysium.shell import ToolBar, ToolButton, StatusBar
from elysium.text.richtext import Run, Break, RichDocument, RichTextView

TOOLBAR_H = 40.0
STATUS_H = 24.0
SIDEBAR_W = 220.0
ROW_H = 44.0


@dataclass
class Note:
    title: str
    body: RichDocument


@dataclass
class ReorderCommand(Command):
    notes: list = None
    src: int = 0
    dst: int = 0

    def redo(self):
        self.notes.insert(self.dst, self.notes.pop(self.src))

    def undo(self):
        self.notes.insert(self.src, self.notes.pop(self.dst))


def _note(title: str, *paragraphs) -> Note:
    doc = RichDocument(default_size=15)
    doc.add(Run(text=title, bold=True, size=22))
    doc.add(Break())
    for para in paragraphs:
        for run in para:
            doc.add(run)
        doc.add(Break())
    return Note(title=title, body=doc)


def build_app(w: float, h: float) -> dict:
    T.set_theme(T.studio_dark())
    notes = [
        _note("Welcome",
              [Run(text="Elysium "), Run(text="documents", bold=True),
               Run(text=" combine "), Run(text="rich text", italic=True),
               Run(text=", undo/redo, and drag-reorder.")]),
        _note("Shortcuts",
              [Run(text="Ctrl+Z"), Run(text=" undo · "),
               Run(text="Ctrl+Y"), Run(text=" redo. Drag a note to reorder.")]),
        _note("Links",
              [Run(text="See the "),
               Run(text="docs", link="https://elysium.dev/docs"),
               Run(text=" for the full guide.")]),
    ]
    state = {"selected": 0}
    undo = UndoStack()

    undo_action = Action(text="Undo", shortcut="Ctrl+Z", on_triggered=undo.undo)
    redo_action = Action(text="Redo", shortcut="Ctrl+Y", on_triggered=undo.redo)

    def _sync_actions():
        undo_action.enabled = undo.can_undo()
        redo_action.enabled = undo.can_redo()
    undo.on_change = _sync_actions
    _sync_actions()

    toolbar = ToolBar(x=0, y=0, w=w, h=TOOLBAR_H, items=[
        undo_action.to_tool_button(),
        redo_action.to_tool_button(),
        "spacer",
    ])
    view = RichTextView(document=notes[0].body, x=SIDEBAR_W + 24,
                        y=TOOLBAR_H + 20, w=w - SIDEBAR_W - 48)
    statusbar = StatusBar(x=0, y=h - STATUS_H, w=w, h=STATUS_H, message="Ready")
    drag = DragController()

    app = {"notes": notes, "state": state, "undo": undo, "toolbar": toolbar,
           "view": view, "statusbar": statusbar, "drag": drag,
           "undo_action": undo_action, "redo_action": redo_action}

    def reorder(src: int, dst: int) -> None:
        if src != dst:
            undo.push(ReorderCommand(text="reorder", notes=notes,
                                     src=src, dst=dst))
            state["selected"] = dst
            select(dst)
    app["reorder"] = reorder

    def select(i: int) -> None:
        state["selected"] = max(0, min(i, len(notes) - 1))
        view.document = notes[state["selected"]].body
        view.relayout()
    app["select"] = select
    select(0)
    return app


def _row_rect(i: int) -> tuple[float, float, float, float]:
    return (10, TOOLBAR_H + 12 + i * (ROW_H + 6), SIDEBAR_W - 20, ROW_H)


def paint_app(dl, app: dict, w: float, h: float) -> None:
    t = T.current_theme()
    dl.fill_path(_rounded_rect(0, 0, w, h, 0), t.surface)
    # Sidebar.
    dl.fill_path(_rounded_rect(0, TOOLBAR_H, SIDEBAR_W, h - TOOLBAR_H - STATUS_H, 0),
                 t.surface_variant)
    for i, note in enumerate(app["notes"]):
        rx, ry, rw, rh = _row_rect(i)
        active = i == app["state"]["selected"]
        if active:
            dl.fill_path(_rounded_rect(rx, ry, rw, rh, 8),
                         T.with_alpha(t.primary, 0.18))
        dl.draw_text(note.title, rx + 12, ry + 20, 13,
                     t.on_surface if active else t.on_surface_muted)
        dl.draw_text(f"{len(note.body.items)} items", rx + 12, ry + 36, 11,
                     t.on_surface_muted)
    # Note body.
    app["view"].w = w - SIDEBAR_W - 48
    app["view"].paint(dl)
    # Chrome.
    app["toolbar"].paint(dl)
    undo = app["undo"]
    clean = "" if undo.is_clean() else "  ●"
    app["statusbar"].message = (
        f"{len(app['notes'])} notes{clean} · "
        + (f"undo: {undo.undo_text()}" if undo.can_undo() else "nothing to undo"))
    app["statusbar"].paint(dl)
    app["drag"].paint(dl)


def main() -> None:  # pragma: no cover - opens a real window
    import elysium as ely
    from elysium._native import _native as _n

    T.set_theme(T.studio_dark())
    a = ely.App(title="Elysium — Notes", identifier="dev.elysium.notes")
    win = a.window(transparent=True, title_bar=False, resizable=True,
                   initial_size=(900, 600))
    app = build_app(900, 600)

    def on_frame(_dt):
        ww, wh = win.surface_size()
        app["toolbar"].w = ww
        app["statusbar"].w = ww
        app["statusbar"].y = wh - STATUS_H
        dl = _n.DisplayList()
        paint_app(dl, app, ww, wh)
        win.submit(dl)

    win.on_frame(on_frame)
    a.run()


if __name__ == "__main__":
    main()
