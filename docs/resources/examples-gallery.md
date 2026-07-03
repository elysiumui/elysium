# Examples gallery

Every runnable app under the repo's `examples/` folder, with a
one-line description and a link to its source.

## Hello

[examples/hello/](https://github.com/elysiumui/elysium/tree/main/examples/hello)
  minimum-viable app. Loads `hello.esk` and prints to stdout on
button click. Used for smoke tests of the native renderer.

## Butterfly

[examples/butterfly/](https://github.com/elysiumui/elysium/tree/main/examples/butterfly)
  the Monarch model + Blue Morpho reference image used in the
[Designer's Blue Morpho tutorial](https://designer.elysiumui.com/getting-started/butterfly/)
and the framework's [Butterfly Banner](../getting-started/butterfly-banner-01-load-the-skin.md)
demo. Holds the source `.3ds`, the reference photo, and the
produced `butterfly.esk` bundle.

## Components showcase

[examples/components/](https://github.com/elysiumui/elysium/tree/main/examples/components)
  a single-window app demonstrating every built-in component
(Button, Slider, Toggle, Card, Popover, etc.) with live theme
switching. Powers
[components-overview](../guides/components-overview.md)
documentation screenshots.

## Agent cursor

[examples/agent-cursor/](https://github.com/elysiumui/elysium/tree/main/examples/agent-cursor)
  a borderless cursor-following agent driven by Aether. Reads its
prompt from a paired Python file and re-skins itself in response.

## Snapshot relay

[examples/snapshot-relay/](https://github.com/elysiumui/elysium/tree/main/examples/snapshot-relay)
  headless background process that exposes a `/snapshot` HTTP
endpoint to capture the live View Panel. Used by integration tests
and remote debugging.

## Running an example

Clone the repo, install the framework, and run the example's
`main.py`:

```sh
git clone https://github.com/elysiumui/elysium.git
cd elysium
pip install -e .
python examples/hello/main.py
```

For Designer-side examples (the Blue Morpho tutorial), open the
Designer and load `examples/butterfly/butterfly.esk/`.

## Tutorial outputs

The Getting Started tutorials produce projects that double as
examples:

- Aurora Clock: see [chapter 5 final](../getting-started/aurora-clock-05-theme-and-events.md).
- Pomodoro: see [chapter 4 final](../getting-started/pomodoro-04-notifications-and-shipping.md).
- Stylized Music Player: see [chapter 8 final](../getting-started/stylized-music-08-package-and-ship.md).
- Butterfly Banner: see [chapter 3 final](../getting-started/butterfly-banner-03-banner-unfurl-and-logo.md).

## Submit an example

Open a PR against `examples/`. Examples should be self-contained
(one folder, no cross-imports), runnable with
`python examples/<name>/main.py`, and accompanied by a `README.md`.

## See also

- [Getting Started](../getting-started/index.md): the four
  flagship tutorials.
- [Tutorials](../tutorials/index.md): follow-on builds.
