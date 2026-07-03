# Patterns

Task-shaped guides for building real application UIs with Elysium — the
"how do I build a CRUD screen / a form / a data table / a dialog flow?"
recipes that go beyond the showcase tutorials.

These build on the Qt-parity widgets (Tiers 1–2). If you're coming from
Qt/PySide6, start with [Porting from Qt](../guides/porting-from-qt.md) for the
class map, then pick a pattern:

- **[CRUD app](crud-app.md)** — a complete create / read / update / delete
  screen over an `ItemModel` + `TableView`, with persistence.
- **[Forms & validation](forms-and-validation.md)** — labelled fields,
  validators and masks, focus order, and submit handling.
- **[Tables & Model/View](tables-and-modelview.md)** — sorting, filtering,
  delegates, inline editing, and virtualization at scale.
- **[Dialogs](dialogs.md)** — modal stacking, non-blocking result handling,
  and native vs Elysium-rendered dialogs.

Every code block here is compiled in CI, so the snippets stay in sync with the
real API.
