# Accessibility

Every interactive hook can declare accessibility metadata in the `.esk` document:

```json
{
  "type": "path", "id": "play",
  "d": "...",
  "hooks": [{"name": "play",
             "type": "event", "events": ["click"],
             "accessible": {
               "role": "button",
               "label": "Play",
               "description": "Start playback of the current track",
               "keyboard_shortcut": "Space"
             }}]
}
```

## Role mapping
Roles are framework-agnostic strings that the platform layer maps:
| Framework role | macOS NSAccessibility | Linux AT-SPI2 | Windows UIA |
|---|---|---|---|
| `button` | AXButton | push button | UIA_ButtonControlTypeId |
| `slider` | AXSlider | slider | UIA_SliderControlTypeId |
| `textfield` | AXTextField | text | UIA_EditControlTypeId |
| `checkbox` | AXCheckBox | check box | UIA_CheckBoxControlTypeId |
| `radio` | AXRadioButton | radio button | UIA_RadioButtonControlTypeId |
| `image` | AXImage | image | UIA_ImageControlTypeId |
| `label` | AXStaticText | label | UIA_TextControlTypeId |
| `group` | AXGroup | panel | UIA_GroupControlTypeId |

Every translation table lives in `crates/ely-platform/src/a11y.rs`.

## Publishing a tree
Each frame the framework publishes a flat tree of accessible nodes (id, role, label, description, shortcut, bounds, children). The OS bridge re-queries it on demand.

```python
win.publish_a11y_tree(root_id=1, nodes=[
    {"id": 1, "role": "window", "bounds": (0, 0, 720, 480), "children": [2, 3]},
    {"id": 2, "role": "button", "label": "Play",  "bounds": (40, 40, 80, 32)},
    {"id": 3, "role": "label",  "label": "Hello", "bounds": (40, 100, 200, 18)},
])
```

## Path-aware focus
Tab moves focus through hooks in document order. For freeform layouts use `accessible.directional_focus` to declare which sibling each arrow key should reach.

## Reduce motion / high contrast
The Designer marks every animation that exceeds 200 ms or every
color pair below WCAG AA. Skins can ship a `reduce_motion` and
`high_contrast` variant; the framework picks them when the OS
reports those preferences.

## Read system preferences

```python
from elysium import accessibility as a11y

prefs = a11y.current()
if prefs.reduce_motion:
    # skip the slide-in animation
    descent.duration = 0.1
if prefs.high_contrast:
    # bump every accent color one step toward the on-surface color
    ...
```

Subscribe to changes:

```python
a11y.subscribe(lambda prefs: print("a11y prefs changed:", prefs))
```

The framework calls subscribers on the Python thread when the OS
publishes a change (Reduce Motion toggled, system contrast
swapped, etc.).

## A11yPrefs

The full dataclass:

```python
@dataclass
class A11yPrefs:
    reduce_motion: bool
    high_contrast: bool
    invert_colors: bool
    larger_text: bool      # OS-reported text scale > 1.0
    screen_reader_active: bool
```

## Per-component a11y

The components in `elysium.components` ship sensible a11y defaults
(buttons announce as buttons, sliders publish min/max/value).
Override the announcement:

```python
Button(
    id="play",
    label="Play",
    a11y_role="button",
    a11y_description="Start playback of the current track",
    a11y_keyboard_shortcut="Space",
)
```

## Testing

`Cmd+F5` (macOS) opens VoiceOver and reads the focused element.
On Windows, Narrator is `Ctrl+Win+Enter`. On Linux, Orca is
`Super+Alt+S`.

For automated tests, `window.publish_a11y_tree(...)` is
inspectable from any test harness; assert that the tree contains
the expected role / label structure.

## See also

- [Focus](focus.md): keyboard navigation that powers screen
  reader traversal.
- [Recipes: respect reduce-motion preferences](../recipes/14-respect-reduce-motion.md)
