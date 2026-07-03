"""Standard dialogs — Tier-1 Qt parity.

Two families:

* **Native file dialogs** (:func:`open_file`, :func:`save_file`,
  :func:`pick_folder`) — thin wrappers over the `rfd`-backed native bindings,
  so users get the real OS picker. Blocking; call from the UI thread.

* **Elysium-rendered modal dialogs** (:class:`MessageDialog`,
  :class:`InputDialog`, :class:`ProgressDialog`, :class:`ColorDialog`,
  :class:`FontDialog`) — borderless, themed, GPU-rendered overlays that match
  the app's look (the differentiator vs Qt's native chrome). They're driven
  by a :class:`DialogHost` the app installs once and ticks/paints each frame.
  Non-blocking: each dialog resolves via an ``on_result`` callback and a
  pollable ``.result`` / ``.done``.

Ergonomic helpers on :class:`DialogHost` (``host.message(...)``,
``host.input(...)``, ``host.progress(...)``, ``host.color(...)``,
``host.font(...)``) push a dialog and return it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from elysium.theme import Color, current_theme, with_alpha, lighten, mix
from elysium.components import (
    Component,
    TextField,
    ProgressBar,
    _rounded_rect,
)


# ===========================================================================
# Native file dialogs
# ===========================================================================

def _native():
    try:
        from elysium._native import _native as _n
        return _n
    except Exception:
        return None


def open_file(*, title: str | None = None, initial_dir: str | None = None,
              filter_label: str | None = None,
              filter_patterns: Sequence[str] | None = None) -> str | None:
    """Native open-file dialog. Returns the chosen path or None on cancel."""
    n = _native()
    if n is None:
        return None
    return n.open_file_dialog(title, initial_dir, filter_label,
                              list(filter_patterns) if filter_patterns else None,
                              False)


def save_file(*, title: str | None = None, initial_dir: str | None = None,
              default_name: str | None = None, filter_label: str | None = None,
              filter_patterns: Sequence[str] | None = None) -> str | None:
    """Native save-file dialog. Returns the chosen path or None."""
    n = _native()
    if n is None:
        return None
    return n.save_file_dialog(title, initial_dir, default_name, filter_label,
                              list(filter_patterns) if filter_patterns else None)


def pick_folder(*, title: str | None = None,
                initial_dir: str | None = None) -> str | None:
    """Native folder-picker dialog. Returns the chosen directory or None."""
    n = _native()
    if n is None:
        return None
    return n.pick_folder(title, initial_dir)


# ===========================================================================
# Elysium-rendered modal dialogs
# ===========================================================================

@dataclass
class _Button:
    label: str
    primary: bool = False
    rect: tuple[float, float, float, float] = (0, 0, 0, 0)


@dataclass
class BaseDialog(Component):
    """Common modal chrome: full-window scrim + centered card + title, an
    entrance tween, and result plumbing. Subclasses lay out their body and
    define how a result is produced."""
    title: str = ""
    on_result: Optional[Callable[[Any], None]] = None
    card_w: float = 420.0
    card_h: float = 220.0

    result: Any = field(default=None, init=False)
    done: bool = field(default=False, init=False)
    _vis_t: float = field(default=0.0, init=False, repr=False)
    _closing: bool = field(default=False, init=False, repr=False)
    _card: tuple[float, float, float, float] = field(default=(0, 0, 0, 0), init=False, repr=False)

    # -- lifecycle ----------------------------------------------------------

    def resolve(self, value: Any) -> None:
        """Settle the dialog with ``value`` and begin the close animation."""
        if self.done:
            return
        self.result = value
        self.done = True
        self._closing = True
        if self.on_result is not None:
            try: self.on_result(value)
            except Exception: pass

    @property
    def dismissed(self) -> bool:
        """True once the close animation has fully played out (safe to drop)."""
        return self._closing and self._vis_t < 0.02

    def update(self, dt: float, state: ComponentStateT = None) -> None:  # type: ignore[name-defined]
        target = 0.0 if self._closing else 1.0
        self._vis_t = current_theme().motion.step(self._vis_t, target, dt, "hover_rate")

    # -- chrome -------------------------------------------------------------

    def _layout_card(self) -> tuple[float, float, float, float]:
        cw, ch = self.card_w, self.card_h
        cx = self.x + (self.w - cw) / 2.0
        cy = self.y + (self.h - ch) / 2.0
        scale = 0.94 + 0.06 * self._vis_t
        sw, sh = cw * scale, ch * scale
        scx = cx + (cw - sw) / 2.0
        scy = cy + (ch - sh) / 2.0
        return (scx, scy, sw, sh)

    def _paint_chrome(self, dl: Any) -> tuple[float, float, float, float]:
        t = current_theme()
        dl.fill_path(_rounded_rect(0, 0, max(self.w, 2000), max(self.h, 2000), 0),
                     with_alpha(t.overlay, self._vis_t))
        card = self._layout_card()
        self._card = card
        scx, scy, sw, sh = card
        s = t.shadow_far
        dl.gradient_card(scx, scy, sw, sh, t.radius_large,
                         lighten(t.surface, 0.02), t.surface,
                         s.blur, s.offset,
                         with_alpha(s.color, (s.color[3] / 255.0) * self._vis_t))
        if self.title:
            dl.draw_text(self.title, scx + 24, scy + 34,
                         t.font_size_title, t.on_surface)
        return card

    def _paint_buttons(self, dl: Any, buttons: list[_Button],
                        card: tuple[float, float, float, float]) -> None:
        t = current_theme()
        scx, scy, sw, sh = card
        bw, bh, gap = 96.0, 34.0, 10.0
        total = len(buttons) * bw + (len(buttons) - 1) * gap
        bx = scx + sw - 20 - total
        by = scy + sh - 20 - bh
        for b in buttons:
            b.rect = (bx, by, bw, bh)
            bg = t.primary if b.primary else t.surface_variant
            fg = (255, 255, 255, 255) if b.primary else t.on_surface
            dl.fill_path(_rounded_rect(bx, by, bw, bh, t.radius_small), bg)
            tw = len(b.label) * t.font_size_body * 0.55
            dl.draw_text(b.label, bx + (bw - tw) / 2.0, by + bh * 0.64,
                         t.font_size_body, fg)
            bx += bw + gap

    # -- input (host calls these) ------------------------------------------

    def on_mouse_press(self, mx: float, my: float) -> bool:
        """Return True if the press hit a dialog control (so the host stops
        propagation). Subclasses override + call super for button hits."""
        return self._hit_buttons(mx, my)

    def _hit_buttons(self, mx: float, my: float) -> bool:
        for b in getattr(self, "_buttons", []):
            x, y, w, h = b.rect
            if x <= mx <= x + w and y <= my <= y + h:
                self._on_button(b)
                return True
        return False

    def _on_button(self, b: _Button) -> None:
        self.resolve(b.label)

    def on_key(self, code: str, mods: int) -> bool:
        if code == "Escape":
            self.resolve(self._cancel_value()); return True
        if code in ("Enter", "NumpadEnter"):
            self.resolve(self._accept_value()); return True
        return False

    def _cancel_value(self) -> Any:
        return None

    def _accept_value(self) -> Any:
        return None


# `state` arg is optional for dialogs (they don't need hover/press smoothing).
ComponentStateT = Optional[dict]


@dataclass
class MessageDialog(BaseDialog):
    """Title + body + a row of buttons. Resolves to the clicked button label
    (Qt QMessageBox parity). Enter accepts the primary button, Esc the last
    (typically Cancel)."""
    body: str = ""
    buttons: Sequence[str] = ("OK",)
    primary_index: int = -1   # -1 → last button is primary

    _buttons: list[_Button] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        pi = self.primary_index if self.primary_index >= 0 else len(self.buttons) - 1
        self._buttons = [_Button(lbl, primary=(i == pi))
                         for i, lbl in enumerate(self.buttons)]

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01:
            return
        t = current_theme()
        card = self._paint_chrome(dl)
        scx, scy, sw, sh = card
        if self.body:
            dl.draw_text(self.body, scx + 24, scy + 78,
                         t.font_size_body, t.on_surface_muted)
        self._paint_buttons(dl, self._buttons, card)

    def click_button(self, index: int) -> None:
        self.resolve(self._buttons[index].label)

    def _accept_value(self) -> Any:
        for b in self._buttons:
            if b.primary:
                return b.label
        return self._buttons[-1].label if self._buttons else None

    def _cancel_value(self) -> Any:
        # Escape rejects → the conventional Cancel button is the first one.
        return self._buttons[0].label if self._buttons else None


@dataclass
class InputDialog(BaseDialog):
    """Title + prompt + a text field + OK/Cancel. Resolves to the entered
    string (OK / Enter) or None (Cancel / Esc)."""
    prompt: str = ""
    default: str = ""
    placeholder: str = ""
    password: bool = False

    text_field: TextField = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    _buttons: list[_Button] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self.text_field = TextField(value=self.default, placeholder=self.placeholder,
                               focus_id="input_dialog_field", password=self.password)
        self._buttons = [_Button("Cancel"), _Button("OK", primary=True)]

    @property
    def editables(self) -> list[Any]:
        return [self.text_field]

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01:
            return
        t = current_theme()
        card = self._paint_chrome(dl)
        scx, scy, sw, sh = card
        if self.prompt:
            dl.draw_text(self.prompt, scx + 24, scy + 72,
                         t.font_size_body, t.on_surface_muted)
        self.text_field.x = scx + 24
        self.text_field.y = scy + 92
        self.text_field.w = sw - 48
        self.text_field.h = 40
        self.text_field._focus_t = 1.0  # always focused while shown
        self.text_field.paint(dl)
        self._paint_buttons(dl, self._buttons, card)

    def _on_button(self, b: _Button) -> None:
        self.resolve(self.text_field.value if b.primary else None)

    def _accept_value(self) -> Any:
        return self.text_field.value

    def _cancel_value(self) -> Any:
        return None

    # forward typing to the embedded field
    def on_text(self, s: str) -> None:
        self.text_field.on_text(s)

    def on_key(self, code: str, mods: int) -> bool:
        if super().on_key(code, mods):
            return True
        return self.text_field.on_key(code, mods)


@dataclass
class ProgressDialog(BaseDialog):
    """Title + label + progress bar. Indeterminate by default; call
    :meth:`set_progress` with 0..1 for determinate, :meth:`close` to finish."""
    label: str = ""
    cancelable: bool = False

    bar: ProgressBar = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    _buttons: list[_Button] = field(default_factory=list, init=False, repr=False)
    _fraction: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.bar = ProgressBar()
        self.card_h = 160.0
        self._buttons = [_Button("Cancel")] if self.cancelable else []

    def set_progress(self, fraction: float | None) -> None:
        self._fraction = fraction

    def set_label(self, text: str) -> None:
        self.label = text

    def close(self) -> None:
        self.resolve(True)

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01:
            return
        t = current_theme()
        card = self._paint_chrome(dl)
        scx, scy, sw, sh = card
        if self.label:
            dl.draw_text(self.label, scx + 24, scy + 76,
                         t.font_size_body, t.on_surface_muted)
        self.bar.x = scx + 24
        self.bar.y = scy + 92
        self.bar.w = sw - 48
        self.bar.h = 8.0
        if self._fraction is not None:
            self.bar.value = max(0.0, min(1.0, self._fraction))
            self.bar.indeterminate = False
        else:
            self.bar.indeterminate = True
        self.bar.paint(dl)
        if self._buttons:
            self._paint_buttons(dl, self._buttons, card)

    def _on_button(self, b: _Button) -> None:
        self.resolve(False)  # canceled

    def _cancel_value(self) -> Any:
        return False


@dataclass
class ColorDialog(BaseDialog):
    """Palette grid + alpha slider + hex field. Resolves to an ``(r,g,b,a)``
    tuple (OK) or None (Cancel). The differentiator: an optional GPU
    swatch preview. Inspired by the Designer's in-app color picker, decoupled
    into a reusable component."""
    initial: Color = (122, 88, 244, 255)

    hex_field: TextField = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    _buttons: list[_Button] = field(default_factory=list, init=False, repr=False)
    _rgb: tuple[int, int, int] = field(default=(122, 88, 244), init=False, repr=False)
    _alpha: int = field(default=255, init=False, repr=False)
    _swatch_rects: list[tuple[Color, tuple]] = field(default_factory=list, init=False, repr=False)
    _alpha_track: tuple = field(default=(0, 0, 0, 0), init=False, repr=False)

    PALETTE = [
        (244, 67, 54), (233, 30, 99), (156, 39, 176), (103, 58, 183),
        (63, 81, 181), (33, 150, 243), (3, 169, 244), (0, 188, 212),
        (0, 150, 136), (76, 175, 80), (139, 195, 74), (205, 220, 57),
        (255, 235, 59), (255, 193, 7), (255, 152, 0), (255, 87, 34),
        (121, 85, 72), (158, 158, 158), (96, 125, 139), (0, 0, 0),
        (255, 255, 255), (122, 88, 244), (40, 90, 220), (20, 200, 160),
    ]

    def __post_init__(self) -> None:
        self.card_w, self.card_h = 360.0, 360.0
        self._rgb = self.initial[:3]
        self._alpha = self.initial[3] if len(self.initial) > 3 else 255
        self.hex_field = TextField(value=self._hex(), focus_id="color_dialog_hex")
        self.hex_field.on_change = self._on_hex_typed
        self._buttons = [_Button("Cancel"), _Button("OK", primary=True)]

    def _hex(self) -> str:
        r, g, b = self._rgb
        return f"#{r:02X}{g:02X}{b:02X}"

    def _on_hex_typed(self, text: str) -> None:
        s = text.lstrip("#")
        if len(s) == 6:
            try:
                self._rgb = (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
            except ValueError:
                pass

    @property
    def color(self) -> Color:
        return (self._rgb[0], self._rgb[1], self._rgb[2], self._alpha)

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01:
            return
        t = current_theme()
        card = self._paint_chrome(dl)
        scx, scy, sw, sh = card
        # Current-color preview swatch.
        dl.fill_path(_rounded_rect(scx + 24, scy + 56, 64, 40, 6), self.color)
        dl.stroke_path(_rounded_rect(scx + 24.5, scy + 56.5, 63, 39, 6),
                       with_alpha(t.edge, 0.8), 1.0)
        # Palette grid (8 cols).
        self._swatch_rects = []
        gx0, gy0, cell, gap = scx + 100, scy + 56, 26.0, 4.0
        for i, c in enumerate(self.PALETTE):
            col = i % 8
            row = i // 8
            x = gx0 + col * (cell + gap)
            y = gy0 + row * (cell + gap)
            color4 = (c[0], c[1], c[2], 255)
            dl.fill_path(_rounded_rect(x, y, cell, cell, 4), color4)
            self._swatch_rects.append((color4, (x, y, cell, cell)))
        # Alpha slider.
        ax, ay, aw, ah = scx + 24, scy + 200, sw - 48, 14.0
        self._alpha_track = (ax, ay, aw, ah)
        dl.fill_path(_rounded_rect(ax, ay, aw, ah, 7), with_alpha(t.on_surface, 0.12))
        kx = ax + (self._alpha / 255.0) * aw
        dl.fill_path(_rounded_rect(kx - 6, ay - 2, 12, ah + 4, 6), t.accent)
        # Hex field.
        self.hex_field.x = scx + 24
        self.hex_field.y = scy + 232
        self.hex_field.w = 140
        self.hex_field.h = 36
        self.hex_field._focus_t = 1.0
        self.hex_field.paint(dl)
        self._paint_buttons(dl, self._buttons, card)

    def on_mouse_press(self, mx: float, my: float) -> bool:
        for color4, (x, y, w, h) in self._swatch_rects:
            if x <= mx <= x + w and y <= my <= y + h:
                self._rgb = color4[:3]
                self.hex_field.set_value(self._hex())
                return True
        ax, ay, aw, ah = self._alpha_track
        if ax <= mx <= ax + aw and ay - 4 <= my <= ay + ah + 4:
            self._alpha = int(max(0, min(255, (mx - ax) / aw * 255)))
            return True
        return super().on_mouse_press(mx, my)

    def _on_button(self, b: _Button) -> None:
        self.resolve(self.color if b.primary else None)

    def _accept_value(self) -> Any:
        return self.color

    def on_text(self, s: str) -> None:
        self.hex_field.on_text(s)

    def on_key(self, code: str, mods: int) -> bool:
        if super().on_key(code, mods):
            return True
        return self.hex_field.on_key(code, mods)


@dataclass
class FontDialog(BaseDialog):
    """Family list + size stepper + live preview. Resolves to
    ``(family, size)`` or None."""
    families: Sequence[str] = ("System", "Helvetica", "Arial", "Georgia",
                               "Courier New", "Menlo", "Verdana")
    family: str = "System"
    size: float = 16.0
    preview_text: str = "The quick brown fox 1234"

    _buttons: list[_Button] = field(default_factory=list, init=False, repr=False)
    _family_rects: list[tuple[str, tuple]] = field(default_factory=list, init=False, repr=False)
    _size_minus: tuple = field(default=(0, 0, 0, 0), init=False, repr=False)
    _size_plus: tuple = field(default=(0, 0, 0, 0), init=False, repr=False)

    def __post_init__(self) -> None:
        self.card_w, self.card_h = 420.0, 360.0
        self._buttons = [_Button("Cancel"), _Button("OK", primary=True)]

    @property
    def selection(self) -> tuple[str, float]:
        return (self.family, self.size)

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01:
            return
        t = current_theme()
        card = self._paint_chrome(dl)
        scx, scy, sw, sh = card
        # Family list.
        self._family_rects = []
        ly = scy + 56
        for fam in self.families:
            rect = (scx + 24, ly, 200, 26)
            if fam == self.family:
                dl.fill_path(_rounded_rect(*rect, 4), with_alpha(t.accent, 0.22))
            dl.draw_text(fam, scx + 32, ly + 18, t.font_size_body, t.on_surface)
            self._family_rects.append((fam, rect))
            ly += 28
        # Size stepper.
        sx = scx + 248
        dl.draw_text("Size", sx, scy + 70, t.font_size_caption, t.on_surface_muted)
        self._size_minus = (sx, scy + 80, 28, 28)
        self._size_plus = (sx + 96, scy + 80, 28, 28)
        dl.fill_path(_rounded_rect(*self._size_minus, 4), t.surface_variant)
        dl.draw_text("-", sx + 11, scy + 99, t.font_size_title, t.on_surface)
        dl.draw_text(f"{int(self.size)}", sx + 44, scy + 99, t.font_size_body, t.on_surface)
        dl.fill_path(_rounded_rect(*self._size_plus, 4), t.surface_variant)
        dl.draw_text("+", sx + 103, scy + 99, t.font_size_title, t.on_surface)
        # Live preview using the chosen size (and family if non-System).
        fam = "" if self.family == "System" else self.family
        try:
            dl.draw_paragraph(self.preview_text, scx + 24, scy + 200,
                              sw - 48, self.size,
                              (t.on_surface[0], t.on_surface[1], t.on_surface[2], 255),
                              0, fam, 0, [])
        except Exception:
            dl.draw_text(self.preview_text, scx + 24, scy + 220, self.size, t.on_surface)
        self._paint_buttons(dl, self._buttons, card)

    def on_mouse_press(self, mx: float, my: float) -> bool:
        for fam, (x, y, w, h) in self._family_rects:
            if x <= mx <= x + w and y <= my <= y + h:
                self.family = fam
                return True
        for rect, delta in ((self._size_minus, -1), (self._size_plus, +1)):
            x, y, w, h = rect
            if x <= mx <= x + w and y <= my <= y + h:
                self.size = max(6.0, min(96.0, self.size + delta))
                return True
        return super().on_mouse_press(mx, my)

    def _on_button(self, b: _Button) -> None:
        self.resolve(self.selection if b.primary else None)

    def _accept_value(self) -> Any:
        return self.selection


# ===========================================================================
# DialogHost — manages the active modal stack
# ===========================================================================

class DialogHost:
    """Owns the active modal-dialog stack for a window. Install once; call
    :meth:`update` + :meth:`paint` each frame and feed mouse/keys via
    :meth:`on_mouse_press` / :meth:`on_key`. Only the topmost dialog receives
    input (true modality)."""

    def __init__(self, window: Any = None) -> None:
        self.window = window
        self._stack: list[BaseDialog] = []

    @property
    def active(self) -> BaseDialog | None:
        return self._stack[-1] if self._stack else None

    @property
    def is_modal(self) -> bool:
        return bool(self._stack)

    def show(self, dialog: BaseDialog) -> BaseDialog:
        # Size the dialog to the window so its scrim/centering work.
        if self.window is not None:
            try:
                w, h = self.window.size
                dialog.w, dialog.h = float(w), float(h)
            except Exception:
                pass
        self._stack.append(dialog)
        return dialog

    def set_size(self, w: float, h: float) -> None:
        for d in self._stack:
            d.w, d.h = w, h

    # -- ergonomic constructors --------------------------------------------

    def message(self, title: str, body: str = "",
                buttons: Sequence[str] = ("OK",), **kw) -> MessageDialog:
        return self.show(MessageDialog(title=title, body=body, buttons=buttons, **kw))  # type: ignore[arg-type]

    def input(self, title: str, prompt: str = "", default: str = "", **kw) -> InputDialog:
        return self.show(InputDialog(title=title, prompt=prompt, default=default, **kw))  # type: ignore[arg-type]

    def progress(self, title: str, label: str = "", **kw) -> ProgressDialog:
        return self.show(ProgressDialog(title=title, label=label, **kw))  # type: ignore[arg-type]

    def color(self, title: str = "Select Color",
              initial: Color = (122, 88, 244, 255), **kw) -> ColorDialog:
        return self.show(ColorDialog(title=title, initial=initial, **kw))  # type: ignore[arg-type]

    def font(self, title: str = "Select Font", **kw) -> FontDialog:
        return self.show(FontDialog(title=title, **kw))  # type: ignore[arg-type]

    # -- per-frame ----------------------------------------------------------

    def update(self, dt: float) -> None:
        if self.window is not None:
            try:
                w, h = self.window.size
                self.set_size(float(w), float(h))
            except Exception:
                pass
        for d in self._stack:
            d.update(dt)
        # Drop fully-dismissed dialogs.
        self._stack = [d for d in self._stack if not d.dismissed]

    def paint(self, dl: Any) -> None:
        for d in self._stack:
            d.paint(dl)

    def on_mouse_press(self, mx: float, my: float) -> bool:
        d = self.active
        if d is None:
            return False
        d.on_mouse_press(mx, my)
        return True  # modal: swallow all presses

    def on_key(self, code: str, mods: int) -> bool:
        d = self.active
        if d is None:
            return False
        d.on_key(code, mods)
        return True

    def on_text(self, s: str) -> bool:
        d = self.active
        if d is None:
            return False
        if hasattr(d, "on_text"):
            d.on_text(s)
        return True


__all__ = [
    "open_file", "save_file", "pick_folder",
    "BaseDialog", "MessageDialog", "InputDialog", "ProgressDialog",
    "ColorDialog", "FontDialog", "DialogHost",
]
