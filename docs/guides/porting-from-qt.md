# Porting from PySide6 / Qt

Elysium's Tier-1 work brings the desktop-app essentials a Qt developer reaches
for on day one — robust text input (incl. IME + clipboard), standard dialogs,
Model/View tables/trees, and data-entry widgets — while staying a
GPU-rendered, borderless, 3D-capable framework rather than a native-widget
toolkit.

This guide maps the Qt classes you know to their Elysium equivalents.

## Mental model

| | Qt / PySide6 | Elysium |
| --- | --- | --- |
| Render | Retained widgets, dirty-region repaint | Immediate-mode; widgets `.paint(dl)` each frame |
| Events | Signals/slots auto-dispatch | One `InputRouter` per window routes to the focused widget |
| Data | `QAbstractItemModel` + views | `ItemModel` (+ a Qt-shaped adapter) + virtualized views |
| Dialogs | Native OS chrome | Native file dialogs; **Elysium-rendered** message/input/color/font |

The big shift: you install **one `InputRouter`** and call `router.set_widgets([...])`
+ `router.tick()` each frame. It delivers keys, typed text, IME composition, and
clipboard actions to whichever widget holds focus. Tab/arrows move focus.

## Class map

| Qt | Elysium | Notes |
| --- | --- | --- |
| `QLineEdit` | `elysium.components.TextField` | caret, selection, undo/redo, validators, masks, IME, password |
| `QTextEdit` (plain) | `elysium.components.TextArea` | multi-line; styled rich text is a later phase |
| `QValidator` | `elysium.text.IntValidator` / `DoubleValidator` / `RegexValidator` | `validate()→Acceptable/Intermediate/Invalid` |
| `QLineEdit.setInputMask` | `elysium.text.Mask("000-000")` | `0 9 A a N n X` metachars |
| `QSpinBox` / `QDoubleSpinBox` | `dataentry.SpinBox` / `DoubleSpinBox` | step / clamp / wrap / prefix / suffix |
| `QDateEdit` / `QTimeEdit` | `dataentry.DateEdit` / `TimeEdit` | segmented; arrows step, digits type |
| `QCalendarWidget` | `dataentry.CalendarWidget` | arrows move day, PageUp/Down month |
| `QComboBox` (editable) | `dataentry.EditableComboBox` | filter-as-you-type + keyboard select |
| `QAbstractItemModel` | `modelview.ItemModel` (+ `QtItemModelAdapter`) | reactive; sort/filter; CRUD |
| `QTableView` | `modelview.TableView` | virtualized, sortable headers, column resize, inline edit |
| `QListView` | `modelview.ListView` | single-column convenience |
| `QTreeView` | `modelview.TreeView` | `TreeNode` hierarchy, expand/collapse |
| `QStyledItemDelegate` | `modelview.Delegate` (+ `TextDelegate`, `EditableCellDelegate`, `Mesh3DDelegate`) | the 3-D delegate has no Qt equivalent |
| `QFileDialog` | `dialogs.open_file` / `save_file` / `pick_folder` | native (`rfd`), all 3 OSes |
| `QMessageBox` | `dialogs.MessageDialog` | Elysium-rendered, borderless |
| `QInputDialog` | `dialogs.InputDialog` | |
| `QProgressDialog` | `dialogs.ProgressDialog` | |
| `QColorDialog` | `dialogs.ColorDialog` | optional 3-D color preview |
| `QFontDialog` | `dialogs.FontDialog` | live GPU preview |
| `QApplication.clipboard()` | `window.get_clipboard_text()` / `set_clipboard_text()` | |
| `QShortcut` | route through `InputRouter` / your frame loop | |

## A minimal form

```python
import elysium as ely
from elysium.components import TextField
from elysium.components.dataentry import SpinBox
from elysium import dialogs as D

app = ely.App(title="Form", identifier="dev.example.form")
win = app.window(transparent=True, title_bar=False, resizable=True,
                 initial_size=(420, 240))

name = TextField(x=20, y=20, w=380, h=44, label="Name", focus_id="name")
age  = SpinBox(x=20, y=80, w=140, h=40, focus_id="age",
               value=18, minimum=0, maximum=120)

router = win.input_router()
router.set_widgets([name, age])
router.focus_widget("name")
host = D.DialogHost(win)

# In your per-frame loop:
#   router.tick()                 # delivers keys/text/IME/clipboard to focus
#   name.paint(dl); age.paint(dl) # widgets paint themselves
#   if host.is_modal: host.paint(dl)
```

See `examples/qt-parity-demo/` for a complete borderless CRUD app (validated
form + sortable/editable table + dialogs) that exercises every Tier-1 feature.

## App shell (Tier 4)

The `QMainWindow` structural widgets live in `elysium.shell`. See the
[App-shell guide](app-shell.md) and `examples/app-shell-demo/` (a docking IDE).

| Qt | Elysium | Notes |
| --- | --- | --- |
| `QMenuBar` / `QMenu` | `shell.MenuBar` (+ `components.Menu`/`MenuItem`) | persistent bar; titles open dropdowns with shortcuts |
| `QToolBar` / `QToolButton` | `shell.ToolBar` / `shell.ToolButton` | separators + a flexible `"spacer"`; pluggable icon painter; checked/disabled |
| `QTabWidget` | `shell.TabWidget` | content-width tabs, closable, content routing |
| `QSplitter` | `shell.Splitter` | H/V draggable divider, min-size clamped, `pane_rects()` |
| `QStatusBar` | `shell.StatusBar` | transient message + right-aligned permanent sections |
| `QGroupBox` | `shell.GroupBox` | titled bordered container; `content_rect()` for children |
| `QDockWidget` | `shell.DockWidget` | a titled, dockable panel (id + content) |
| `QMainWindow` docking | `shell.DockManager` | left/right/bottom/centre areas, per-area tabbing, splitter resize, drag-to-redock with drop zones, layout `serialize()`/`restore()` |

```python
from elysium.shell import DockManager, DockWidget, MenuBar, StatusBar

docks = DockManager(x=0, y=0, w=1280, h=720)
docks.add(DockWidget(id="explorer", title="Explorer", content=tree), "left")
docks.add(DockWidget(id="editor",   title="main.py",  content=editor), "center")
docks.add(DockWidget(id="console",  title="Console",  content=log),    "bottom")

# per frame: docks.paint(dl); route presses via docks.on_press/on_drag/on_release
layout = docks.serialize()           # persist via elysium.settings.Settings
docks.restore(layout, registry={...})  # id -> DockWidget
```

Floating a dock out to a separate OS window is a tracked follow-up; docked +
tabbed + drag-to-redock + persisted layouts are available now.

## Interactive 2D canvas (Tier 5)

An item scene graph lives in `elysium.graphics` — see the
[Interactive 2D canvas guide](graphics.md) and `examples/graphics-demo/` (a
flowchart editor).

| Qt | Elysium | Notes |
| --- | --- | --- |
| `QGraphicsScene` | `graphics.Scene` | z-ordered items; `items_at` / `items_in_rect` / `bounding_rect` / selection |
| `QGraphicsItem` | `graphics.Item` | scene-space bounds + `contains()` + `paint(dl)` in scene coords; subclass for custom |
| `QGraphicsRectItem` / `EllipseItem` / `LineItem` / `PathItem` / `SimpleTextItem` | `graphics.RectItem` / `EllipseItem` / `LineItem` / `PathItem` / `TextItem` | line uses a distance hit-test; ellipse uses the radius equation |
| `QGraphicsView` | `graphics.GraphicsView` | pan/zoom (`zoom_at` is cursor-anchored), `fit()`, viewport culling |
| view interaction (rubber-band, move, resize) | `graphics.SceneController` | select / Shift-multi-select / rubber-band / move (grid `snap`) / 8 resize handles |
| `item.setPos` / `setZValue` | `item.move_by` / `item.z` (+ `scene.raise_to_top`) | |
| `view.mapToScene` / `mapFromScene` | `view.to_scene` / `view.to_view` | map pointer coords before querying the scene |

Per-item rotation/scale transforms and arbitrary-path `contains` hit-testing are
tracked follow-ups; bounds / ellipse / line hit-tests are exact today.

## Documents & editing (Tier 6)

Undo/redo, rich text, and drag-and-drop — see the
[Documents & editing guide](documents.md) and `examples/notes-demo/`.

| Qt | Elysium | Notes |
| --- | --- | --- |
| `QUndoStack` | `commands.UndoStack` | push/undo/redo, merge by `merge_id`, macros, limit, clean index, `on_change` |
| `QUndoCommand` | `commands.Command` (+ `FunctionCommand`, `MacroCommand`) | `redo`/`undo` + `merge_with` |
| `QAction` | `commands.Action` | one trigger for menu + toolbar + shortcut; `to_menu_item()` / `to_tool_button()` |
| `QTextDocument` | `text.richtext.RichDocument` | styled `Run`s + inline `Image` + `Break`; `layout(width)` |
| `QTextCharFormat` | `Run(bold=…, italic=…, size=…, color=…, family=…, underline=…, link=…)` | bold = weight, italic = slant axis (real font styling) |
| `QTextBrowser` (read) | `text.richtext.RichTextView` | word-wrap, baseline-aligned mixed sizes, `link_at`/`on_click` hyperlinks |
| `QMimeData` | `dnd.MimeData` | typed payloads + a `TEXT` slot |
| `QDrag` / drop events | `dnd.DragController` (+ `dnd.DropZone`) | press→threshold→drag, hovered accepting zone, ghost, delivered drop |

An editable `RichTextEdit` (caret/selection over styled runs) and per-paragraph
block styles are tracked follow-ups; the document model, layout, read-only view,
hyperlinks, command stack, and DnD are available now.

## Styling & accessibility (Tier 7)

The polish layer — see the [Styling & accessibility guide](styling-and-a11y.md).

| Qt | Elysium | Notes |
| --- | --- | --- |
| `setStyleSheet` (QSS) | `styling.StyleSheet` | selector → property overrides; type / `#id` / `.class` / `:state`, CSS specificity |
| `QCompleter` | `components.completer.Completer` | prefix → contains → fuzzy, history, keyboard nav, popover |
| `QAccessible` roles | `accessibility.Role` + `AccessibleNode` | `to_dict()` → accesskit-bridge shape; table `row_index`/`col_index`/`col_header` |
| live regions / announcements | `accessibility.Announcer` / `announce()` | polite/assertive; pluggable sink |
| focus rings | `accessibility.paint_focus_ring` | honours high-contrast prefs |
| `QWidget.setFont` | `Label(font_family=…, weight=…)` (+ `theme.set_ui_font`) | per-widget override (opt-in) over the app-wide font |

## Class map — Tier 2 (scale, services, native)

| Qt | Elysium | Notes |
| --- | --- | --- |
| `QScrollArea` | `elysium.components.scroll.ScrollView` | clips + translates content, momentum |
| `QScrollBar` | `elysium.components.scroll.ScrollBar` | standalone, drag + page |
| `QAbstractItemView` virtualization | `elysium.components.virtual.VirtualList` / `VirtualForm` | paint only visible items |
| dirty-region repaint | automatic (render-thread damage diff) | `ELYSIUM_DIRTY_RECT=0` to disable |
| `QMetaObject::invokeMethod` / queued slots | `elysium.concurrency.call_on_ui_thread` / `post` / `@ui_thread` | |
| `QThread` + signals | `FrameLoop` + `UiDispatcher` + `run_async` | asyncio bridge included |
| modal `QDialog.exec()` / owned windows | `elysium.windowing.WindowManager.open(owner=…, modal=True)` | blocks owner, cascades close |
| `QSystemTrayIcon` | `elysium.native.Tray` | macOS/Windows |
| `QShortcut` (global) | `elysium.native.HotKeys` | macOS/Windows |
| OS notifications | `elysium.native.notify` | native mac/win, notify-send Linux |
| single-instance (`QtSingleApplication`) | `elysium.native.single_instance` | all platforms |
| `QTranslator` / `tr()` | `elysium.i18n.tr` / `tr_n` (gettext `.mo`) | |
| `QLocale` | `elysium.locale.format_*` | Babel-backed when installed |
| RTL `setLayoutDirection` | `elysium.i18n` `is_rtl` / `flip_align` / `mirror_x` + `draw_paragraph(rtl=True)` | |
| `QSettings` | `elysium.settings.Settings` | dotted groups, atomic writes |
| `QTest` | `elysium.testing.UiHarness` | headless click/key/scroll/find |

See [Scale, scrolling & virtualization](scale-and-scroll.md) and
[Threading, multi-window, native integration, i18n, settings & testing](threading-and-services.md).

## Business-app widgets (Tier 8)

The dashboard / bulk-editor class of app — charts, KPI tiles, an Excel-grade
grid, wizards.

| Qt | Elysium | Notes |
| --- | --- | --- |
| `QtCharts` (`QLineSeries` / `QAreaSeries` / `QBarSeries` / `QPieSeries`) | `charts.LineChart` / `AreaChart` / `BarChart` / `DonutChart` / `PieChart` | pure Python on the `DisplayList`; `Series`, `Legend`, `nice_ticks`, money/pct formatters |
| sparkline (custom) | `charts.Sparkline` | inline mini line; used inside `MetricCard` |
| KPI tile (hand-rolled) | `components.dashboard.MetricCard` | eyebrow + value + ▲/▼ delta + sparkline; direction-aware colour |
| `QMessageBar` / persistent banners | `components.dashboard.Alert` / `NotificationInbox` | severity tint, action link, dismiss (≠ transient `Toast`) |
| `QDateEdit` range / two `QDateEdit`s | `components.daterange.DateRangePicker` | presets (Today/Yesterday/7d/30d) + Custom → `(start, end)` |
| `QButtonGroup` (exclusive) | `components.daterange.SegmentedControl` | single-choice segmented toggle |
| `QWizard` / `QWizardPage` | `shell.Wizard` (+ `shell.Stepper`) | numbered header, routed content, Back/Next/Finish |
| `QDockWidget` (floating) / slide-over | `shell.Drawer` | animated slide-out + scrim (left/right/bottom) |
| `QTableView` + bulk edit / `QSqlTableModel` | `modelview.grid.DataGrid` | frozen cols, range select, copy/paste TSV, fill-down, per-cell validation + pending highlight, 100k rows |
| tabular figures (`QFont` features) | `draw_paragraph(tabular=True)`, `Label(tabular=True)`, `MetricCard(tabular=True)` | OpenType `tnum`+`lnum` so money columns align |

See [Charts and dashboards](charts-and-dashboards.md), [The data grid](data-grid.md)
and [Wizards, steppers and drawers](wizards-and-flows.md).

## What's intentionally different

* **Dialogs are borderless + themed**, not native chrome (except file dialogs,
  which stay native). This is the differentiator — your dialogs match your app.
* **A `Mesh3DDelegate`** renders a real GPU 3-D thumbnail per table cell —
  impossible in Qt item views without a custom OpenGL widget.
* **Immediate-mode**: there is no retained widget tree yet (Tier-2). You hold
  widget references and paint them each frame; the `InputRouter` supplies the
  interaction layer.

## Not yet at parity (tracked separately)

Styled rich text, full RTL/bidi + locale formatting, a retained component tree,
and `QtNetwork`/`QtMultimedia`/`QtSql`/printing are out of Tier-1 scope — see
issues #2 (Tier 2) and #3 (Tier 3).
