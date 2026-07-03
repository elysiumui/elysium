# `elysium.codelink`

Two-way wiring between the Designer and your Python source. Same
one-click feel as Interface Builder in Xcode, or the Forms designer
in Visual Studio.

## Functions

| Function | Purpose |
|---|---|
| `index_handlers(path, known_hooks)` | Map handler-name → location |
| `scaffold_handler(path, hook, window_var)` | Insert a stub if missing |
| `goto_handler(path, hook, known_hooks, window_var)` | Open editor at handler; scaffold if needed |
| `pair_file(skin_path, py_path)` | Persist the pairing on the skin |
| `resolve_paired_file(skin_path)` | Read back a pairing |

## Editor detection

The launcher walks `$ELYSIUM_EDITOR` → `$VISUAL` → `$EDITOR`, then
probes PATH for VS Code, Cursor, Windsurf, Zed, Sublime, Helix,
PyCharm, IntelliJ, Neovim, Vim, Emacs, and Xed in that order.

## Dataclasses

| Class | Purpose |
|---|---|
| `HandlerLocation(line, function, ...)` | Where a handler lives in a file |

## Auto-rendered details

::: elysium.codelink

## See also

- [Code Link](../guides/code-link.md)
- [Designer > Code Link](https://designer.elysiumui.com/code-link/)
