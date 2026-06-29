"""Dashboard widgets — KPI metric cards and a persistent alert inbox.

These compose the existing card/badge primitives into the building blocks a
business dashboard needs: a :class:`MetricCard` (eyebrow + big value + delta
badge + optional sparkline) and an :class:`Alert` / :class:`NotificationInbox`
for a persistent "needs attention" panel (distinct from the transient
``Toast`` / ``Snackbar``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from elysium.theme import current_theme, with_alpha, lighten
from elysium.components import Component, _rounded_rect
from elysium.charts import Sparkline

__all__ = ["MetricCard", "Alert", "NotificationInbox"]


def _severity_color(t: Any, severity: str):
    return {
        "info": t.primary,
        "success": t.success,
        "warning": t.warning,
        "danger": t.danger,
    }.get(severity, t.primary)


# ---------------------------------------------------------------------------
# MetricCard — a KPI tile.
# ---------------------------------------------------------------------------

@dataclass
class MetricCard(Component):
    """A KPI tile: a small ``label``, a big ``value`` (caller-formatted), an
    optional ``delta`` badge with a direction, and an optional ``sub`` note or
    inline ``spark`` sparkline.

    ``delta_dir`` is +1 (up) / -1 (down) / 0; ``good_up`` says whether *up* is
    good — so "Net profit ▲" is green but "Refund drag ▲" is red."""

    label: str = ""
    value: str = ""
    delta: str = ""
    delta_dir: int = 0
    good_up: bool = True
    sub: str = ""
    icon: Callable[[Any, float, float, float, Any], None] | None = None
    spark: list[float] | None = None
    tabular: bool = False        # tabular numerals for the big value
    radius: float = 12.0

    def _delta_color(self, t: Any):
        if self.delta_dir == 0:
            return t.on_surface_muted
        good = (self.delta_dir > 0) == self.good_up
        return t.success if good else t.danger

    def paint(self, dl: Any) -> None:
        t = current_theme()
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, self.radius),
                     t.surface_variant)
        dl.stroke_path(
            _rounded_rect(self.x + 0.5, self.y + 0.5, self.w - 1, self.h - 1,
                          self.radius), with_alpha(t.edge, 1.0), 1.0)
        pad = 14.0
        ex = self.x + pad
        if self.icon is not None:
            self.icon(dl, ex + 6, self.y + pad + 4, 14, t.on_surface_muted)
            ex += 22
        dl.draw_text(self.label, ex, self.y + pad + 8, 11, t.on_surface_muted)
        if self.tabular:
            from elysium.components import Label
            Label(x=self.x + pad, y=self.y + pad + 18, w=self.w - 2 * pad, h=26,
                  text=self.value, size=24, color=t.on_surface,
                  tabular=True).paint(dl)
        else:
            dl.draw_text(self.value, self.x + pad, self.y + pad + 36, 24,
                         t.on_surface)
        # Delta badge.
        if self.delta:
            dc = self._delta_color(t)
            arrow = "▲" if self.delta_dir > 0 else ("▼" if self.delta_dir < 0 else "")
            by = self.y + self.h - 22
            txt = f"{arrow} {self.delta}".strip()
            dl.draw_text(txt, self.x + pad, by + 12, 11, dc)
            if self.sub:
                dw = len(txt) * 6.0 + 10
                dl.draw_text(self.sub, self.x + pad + dw, by + 12, 11,
                             t.on_surface_muted)
        elif self.sub:
            dl.draw_text(self.sub, self.x + pad, self.y + self.h - 10, 11,
                         t.on_surface_muted)
        # Inline sparkline, top-right.
        if self.spark:
            Sparkline(values=self.spark, x=self.x + self.w - 96,
                      y=self.y + pad, w=82, h=34,
                      color=self._delta_color(t) if self.delta_dir else t.primary
                      ).paint(dl)


# ---------------------------------------------------------------------------
# Alert + NotificationInbox — persistent "needs attention".
# ---------------------------------------------------------------------------

@dataclass
class Alert(Component):
    """A persistent, dismissible alert row with a severity tint and an optional
    action link."""

    title: str = ""
    body: str = ""
    severity: str = "info"          # info | success | warning | danger
    action_label: str = ""
    on_action: Callable[[], None] | None = None
    dismissible: bool = True
    on_dismiss: Callable[[], None] | None = None
    h: float = 56.0
    radius: float = 8.0

    def close_rect(self) -> tuple[float, float, float, float]:
        return (self.x + self.w - 24, self.y + 8, 16, 16)

    def on_click(self, mx: float, my: float) -> bool:
        if self.dismissible:
            cx, cy, cw, ch = self.close_rect()
            if cx - 3 <= mx <= cx + cw + 3 and cy - 3 <= my <= cy + ch + 3:
                if self.on_dismiss is not None:
                    self.on_dismiss()
                return True
        if self.action_label and self.on_action is not None:
            # Action link sits at the bottom-left.
            ay = self.y + self.h - 18
            aw = len(self.action_label) * 7.0
            if (self.x + 14 <= mx <= self.x + 14 + aw
                    and ay - 6 <= my <= ay + 8):
                self.on_action()
                return True
        return False

    def paint(self, dl: Any) -> None:
        t = current_theme()
        col = _severity_color(t, self.severity)
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, self.radius),
                     with_alpha(col, 0.12))
        # Left severity bar + dot.
        dl.fill_path(_rounded_rect(self.x, self.y, 3, self.h, 1.5), col)
        dl.draw_text(self.title, self.x + 14, self.y + 20, 12.5, t.on_surface)
        if self.body:
            dl.draw_text(self.body, self.x + 14, self.y + 38, 11,
                         t.on_surface_muted)
        if self.action_label:
            dl.draw_text(self.action_label, self.x + 14, self.y + self.h - 8,
                         11, col)
        if self.dismissible:
            cx, cy, cw, ch = self.close_rect()
            ccx, ccy = cx + cw / 2, cy + ch / 2
            dl.stroke_path(
                f"M {ccx-4} {ccy-4} L {ccx+4} {ccy+4} M {ccx+4} {ccy-4} "
                f"L {ccx-4} {ccy+4}", with_alpha(t.on_surface_muted, 0.8), 1.3)


@dataclass
class NotificationInbox(Component):
    """A persistent, scrollable list of :class:`Alert`s — the dashboard's
    "needs attention" panel."""

    title: str = "Needs attention"
    alerts: list[Alert] = field(default_factory=list)
    gap: float = 8.0
    header_h: float = 30.0
    alert_h: float = 56.0

    def _alert_y(self, i: int) -> float:
        return self.y + self.header_h + i * (self.alert_h + self.gap)

    def layout(self) -> None:
        for i, a in enumerate(self.alerts):
            a.x = self.x
            a.y = self._alert_y(i)
            a.w = self.w
            a.h = self.alert_h

    def on_click(self, mx: float, my: float) -> bool:
        self.layout()
        for a in self.alerts:
            if a.y <= my <= a.y + a.h and a.x <= mx <= a.x + a.w:
                return a.on_click(mx, my)
        return False

    def dismiss(self, alert: Alert) -> None:
        if alert in self.alerts:
            self.alerts.remove(alert)

    def paint(self, dl: Any) -> None:
        t = current_theme()
        if self.title:
            dl.draw_text(self.title, self.x, self.y + 18, 14, t.on_surface)
        self.layout()
        for a in self.alerts:
            a.paint(dl)
