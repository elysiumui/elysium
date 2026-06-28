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
| `QTableView` | `modelview.TableView` | virtualized, sortable headers, inline edit |
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
