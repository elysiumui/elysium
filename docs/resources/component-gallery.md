# Component gallery

Everything Elysium ships, at a glance. Each widget reads the active
[theme](../guides/theming.md) at paint time and lays out to an `x / y / w / h`
box. Follow the links for the guide and the auto-rendered API.

## Core widgets — `elysium.components`

| Widget | What it is |
| --- | --- |
| `Label` | Text, with optional per-widget font / weight and `tabular` numerals |
| `Button`, `IconButton`, `FAB` | Tactile flat buttons; icon-only; floating action |
| `TextField`, `TextArea`, `NumericField` | Single-line / multi-line / numeric input |
| `Checkbox`, `Radio`, `Toggle` | Boolean and choice controls |
| `Slider` | Continuous value control |
| `ComboBox`, `Dropdown` | Pop-down selection |
| `Card`, `Divider`, `Accordion` | Containers and section structure |
| `Badge`, `Chip`, `Avatar`, `Spinner` | Status, tags, identity, loading |
| `ProgressBar` | Determinate / indeterminate progress |
| `Tabs` | In-content tab strip |
| `Tooltip`, `Popover`, `RadialPopover` | Anchored transient surfaces |
| `Menu` / `MenuItem`, `CommandPalette` | Menus and a ⌘K palette |
| `Modal` | Blocking dialog surface |
| `Toast`, `Snackbar` | Transient feedback (≠ the persistent `NotificationInbox`) |
| `Pagination`, `Breadcrumb` | Navigation chrome |
| `Tree` / `TreeRow` | Disclosure tree |

API: [`elysium.components`](../api/components.md) ·
Guide: [Components overview](../guides/components-overview.md)

## Data entry — `elysium.components.dataentry`

| Widget | What it is |
| --- | --- |
| `SpinBox`, `DoubleSpinBox` | Stepped integer / float fields |
| `DateEdit`, `TimeEdit`, `CalendarWidget` | Date / time entry + calendar |
| `EditableComboBox` | Type-ahead combo |

API: [`elysium.components.dataentry`](../api/dataentry.md) ·
Guide: [Text input and dialogs](../guides/text-input-and-dialogs.md)

## Scrolling & virtualization — `elysium.components.scroll` / `.virtual`

`ScrollBar`, `ScrollView`, `VirtualList`, `VirtualForm` — see
[Scale and scroll](../guides/scale-and-scroll.md).
API: [scroll](../api/scroll.md), [virtual](../api/virtual.md).

## App shell — `elysium.shell`

| Widget | What it is |
| --- | --- |
| `GroupBox`, `Splitter`, `StatusBar` | Framing and panes |
| `MenuBar`, `ToolBar` / `ToolButton` | Top-level menus and toolbars |
| `TabWidget` | Document tab area |
| `DockManager` / `DockWidget` | Dockable, draggable panels |
| `Drawer` | Slide-out side panel |
| `Stepper`, `Wizard` | Numbered multi-step flows |

API: [`elysium.shell`](../api/shell.md) ·
Guides: [App shell](../guides/app-shell.md),
[Wizards and flows](../guides/wizards-and-flows.md)

## Charts — `elysium.charts`

`LineChart`, `AreaChart`, `BarChart`, `DonutChart` / `PieChart`, `Sparkline`,
`Legend` + `format_money` / `format_pct` / `format_compact`.
API: [`elysium.charts`](../api/charts.md) ·
Guide: [Charts and dashboards](../guides/charts-and-dashboards.md)

## Dashboard & date bar — `elysium.components.dashboard` / `.daterange`

`MetricCard`, `Alert`, `NotificationInbox`, `SegmentedControl`,
`DateRangePicker`.
API: [dashboard](../api/dashboard.md), [daterange](../api/daterange.md) ·
Guide: [Charts and dashboards](../guides/charts-and-dashboards.md)

## Model / View — `elysium.modelview`

`ItemModel`, `TableView` / `ListView` / `TreeView`, delegates, and the
Excel-grade [`DataGrid`](../api/grid.md).
Guides: [Tables and Model/View](../patterns/tables-and-modelview.md),
[The data grid](../guides/data-grid.md)

## Canvas, rich text, drag-and-drop, autocomplete

| Module | Widgets |
| --- | --- |
| [`elysium.graphics`](../api/graphics.md) | `Scene`, `Item` (+ rect/ellipse/line/path/text), `GraphicsView` |
| [`elysium.text.richtext`](../api/richtext.md) | `RichDocument`, `RichTextView` |
| [`elysium.dnd`](../api/dnd.md) | `MimeData`, `DropZone`, `DragController` |
| [`elysium.components.completer`](../api/completer.md) | `Completer` |
| [`elysium.styling`](../api/styling.md) | `StyleSheet`, `Selector` |
| [`elysium.commands`](../api/commands.md) | `UndoStack`, `Command`, `Action` |

## See also

- [Build a Shopify-style desktop app](../tutorials/shopify-style-desktop-app.md)
- [Scope and batteries](scope-and-batteries.md) — what's in / out of scope
- [Porting from Qt](../guides/porting-from-qt.md)
