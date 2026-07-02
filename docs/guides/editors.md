# Editor integration

Elysium ships a sidecar Language Server (`elysium-lsp`) used by every editor we support: VS Code, PyCharm, Neovim, Helix, Zed.

## What you get
- Completion at `window["` / `win["` cursors, with full hook type info.
- Hover docs surface `EventHook | TextHook | StateHook[*states] | ValueHook[min, max] | ImageHook`.
- Goto-definition jumps from the Python reference to the `.esk` node that declares the hook.
- Diagnostics flag unknown hooks (typos, deleted nodes) and accessibility issues (interactive hooks missing role/label).
- `prepareRename` + `rename` propagate across Python and the skin atomically.
- Workspace symbols indexes every hook in every loaded skin.

## Install
```bash
pip install elysium-ui-lsp
```

## VS Code
Install the Elysium UI extension from the marketplace. It auto-spawns `elysium-lsp` over stdio.

## PyCharm
The plugin (`elysium-pycharm`) bundles the same LSP under the hood, plus an embedded Designer panel and a typed-stub generator that emits `.elysium/stubs/<skin>.pyi`.

## Neovim
```lua
require('lspconfig').elysium.setup {
  cmd = { 'elysium-lsp' },
  filetypes = { 'python', 'json' },
  root_dir = require('lspconfig.util').find_git_ancestor,
}
```

## Helix / Zed
Both have generic LSP integration; point them at the `elysium-lsp` binary the same way.

## Architecture
The LSP server lives in `elysium-lsp/src/elysium_lsp/server.py`. It walks every `.esk/document.json` under the workspace root, builds a flat hook index, and serves it through the standard LSP completion/hover/definition handlers. Indexes are cached per workspace with mtime invalidation; a save on any `.esk` invalidates the cache instantly.
