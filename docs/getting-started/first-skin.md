# Your first skin

A skin is either a `.esk` zip file or a directory of the same shape. Minimum contents:

```
my-skin.esk/
├── manifest.json     # name, id, version
├── document.json     # scene tree
└── hooks.json        # optional pre-generated hook index
```

## manifest.json
```json
{
  "schema_version": "1.0",
  "id": "dev.elysium.hello",
  "name": "Hello",
  "version": "0.1.0",
  "color_space": "srgb"
}
```

## document.json
```json
{
  "root": {
    "type": "scene",
    "size": {"w": 720, "h": 480},
    "background": {"type": "color", "value": "#0E0B1A"},
    "children": [
      {
        "type": "path", "id": "card",
        "d": "M 80 80 L 640 80 L 640 400 L 80 400 Z",
        "fill": {"type": "linear_gradient",
                 "stops": [[0, "#5B3FF5"], [1, "#FF5C8A"]],
                 "angle": 135},
        "hooks": [{"name": "greet", "type": "event", "events": ["click"]}]
      },
      {
        "type": "text", "id": "message",
        "value": "Drag me into Elysium",
        "x": 120, "y": 240, "size": 28, "color": "#FFFFFF",
        "hooks": [{"name": "message", "type": "text"}]
      }
    ]
  }
}
```

## Hooks
Every interactive primitive can carry a hook. `type: "event"` exposes events like `click`, `hover`, `drag`. `type: "text"` lets Python set the text. `type: "image"` accepts an absolute or `.esk`-relative file path. `type: "state"` declares allowed state names; `type: "value"` carries a numeric range.

Open it with the standalone Designer (`elysium-designer my-skin.esk/`) for a visual editor with hot-reload.
