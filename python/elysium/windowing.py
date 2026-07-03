"""Multi-window depth — Tier-2 Qt parity (modal dialogs, owned/child windows,
inter-window signals).

Tier-1 supported several independent top-level windows but no relationships
between them. :class:`WindowManager` adds:

* **Owned / child windows** — ``manager.open(owner=parent, ...)`` tracks an
  owner→children tree; closing an owner cascades to its children.
* **Application-modal windows** — ``modal=True`` blocks input to the owner
  (via the Phase-0 ``set_input_blocked`` mechanism) until the modal closes,
  and centers the child over its owner.
* **Inter-window messaging** — ``manager.send(target, message)`` delivers to
  the target window's ``on_message`` handlers on *its* UI thread.

The native window primitives (``id``, ``set_input_blocked``, ``outer_position``,
``surface_size``) come from Phase 0; this module is the Python policy layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class _WinRecord:
    window: Any
    owner_id: Optional[int]
    modal: bool
    children: list[int] = field(default_factory=list)
    handlers: list[Callable[[Any], None]] = field(default_factory=list)


class WindowManager:
    """Owns the window tree + modal stack for an :class:`elysium.App`. Create
    one per app and open all secondary windows through it so ownership,
    modality, and messaging stay consistent."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._records: dict[int, _WinRecord] = {}
        self._modal_stack: list[int] = []

    # -- lifecycle ----------------------------------------------------------

    def register(self, window: Any, owner: Any = None, modal: bool = False) -> Any:
        """Track an already-created window. Usually you call :meth:`open`
        instead, which creates + registers in one step."""
        owner_id = getattr(owner, "id", None) if owner is not None else None
        rec = _WinRecord(window=window, owner_id=owner_id, modal=modal)
        self._records[window.id] = rec
        if owner_id is not None and owner_id in self._records:
            self._records[owner_id].children.append(window.id)
        if modal and owner is not None:
            self._modal_stack.append(window.id)
            self._apply_modality(owner_id)
            self._center_over(window, owner)
        return window

    def open(self, owner: Any = None, modal: bool = False, **kwargs: Any) -> Any:
        """Create a new window owned by ``owner`` (optional) and register it.
        ``modal=True`` makes it application-modal w.r.t. its owner."""
        owner_id = getattr(owner, "id", None) if owner is not None else None
        if owner_id is not None:
            kwargs["owner_id"] = owner_id
        if modal:
            kwargs["modal"] = True
        win = self.app.window(**kwargs)
        return self.register(win, owner=owner, modal=modal)

    def close(self, window: Any) -> None:
        """Close ``window`` and cascade to its children. Restores input to
        the owner when the last modal child for that owner closes."""
        wid = getattr(window, "id", None)
        rec = self._records.get(wid)
        if rec is None:
            return
        # Cascade to children first.
        for child_id in list(rec.children):
            child = self._records.get(child_id)
            if child is not None:
                self.close(child.window)
        # Detach from owner.
        if rec.owner_id is not None and rec.owner_id in self._records:
            owner_children = self._records[rec.owner_id].children
            if wid in owner_children:
                owner_children.remove(wid)
        if wid in self._modal_stack:
            self._modal_stack.remove(wid)
        self._records.pop(wid, None)
        try:
            window.close()
        except Exception:
            pass
        # Re-evaluate the owner's input-block state.
        if rec.owner_id is not None:
            self._apply_modality(rec.owner_id)

    # -- modality -----------------------------------------------------------

    def _apply_modality(self, owner_id: Optional[int]) -> None:
        if owner_id is None or owner_id not in self._records:
            return
        owner = self._records[owner_id].window
        blocked = any(
            self._records[cid].modal
            for cid in self._records[owner_id].children
            if cid in self._records
        )
        try:
            owner.set_input_blocked(blocked)
        except Exception:
            pass

    def is_blocked(self, window: Any) -> bool:
        try:
            return bool(window.input_blocked)
        except Exception:
            return False

    def _center_over(self, child: Any, owner: Any) -> None:
        try:
            ox, oy = owner.outer_position
            ow, oh = owner.surface_size
            cw, ch = child.surface_size
            child.set_outer_position(int(ox + (ow - cw) / 2), int(oy + (oh - ch) / 2))
        except Exception:
            pass

    # -- tree queries -------------------------------------------------------

    def children(self, window: Any) -> list[Any]:
        rec = self._records.get(getattr(window, "id", None))
        if rec is None:
            return []
        return [self._records[c].window for c in rec.children if c in self._records]

    def owner_of(self, window: Any) -> Any:
        rec = self._records.get(getattr(window, "id", None))
        if rec is None or rec.owner_id is None:
            return None
        owner_rec = self._records.get(rec.owner_id)
        return owner_rec.window if owner_rec else None

    @property
    def modal_active(self) -> bool:
        return bool(self._modal_stack)

    @property
    def top_modal(self) -> Any:
        if not self._modal_stack:
            return None
        rec = self._records.get(self._modal_stack[-1])
        return rec.window if rec else None

    # -- inter-window messaging --------------------------------------------

    def on_message(self, window: Any, handler: Callable[[Any], None]) -> None:
        """Register ``handler(message)`` for messages sent to ``window``."""
        rec = self._records.get(getattr(window, "id", None))
        if rec is not None:
            rec.handlers.append(handler)

    def send(self, target: Any, message: Any) -> bool:
        """Deliver ``message`` to ``target``'s handlers on its UI thread (via
        the target window's dispatcher). Returns False if untracked."""
        rec = self._records.get(getattr(target, "id", None))
        if rec is None:
            return False
        for h in list(rec.handlers):
            if hasattr(target, "post"):
                try: target.post(h, message)
                except Exception: pass
            else:
                try: h(message)
                except Exception: pass
        return True


__all__ = ["WindowManager"]
