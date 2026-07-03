"""Two-way Designer ↔ code wiring.

Given a Python source file paired with a `.esk`, this module:

* Indexes every hook handler — declarations like
  ``@win.on("play.click")`` / ``@window.on("play.click")`` and
  ``def on_play_click(...)`` / ``def play_click(...)``.
* Opens the user's editor at the handler's line via the right CLI for
  VS Code / Cursor / PyCharm / Sublime / Neovim / Helix / Zed / Xcode,
  or the system default as a fallback.
* Scaffolds a stub when no handler exists yet — appends a decorated
  function at the bottom of the file and returns the new line number.

The convention follows the framework's docs::

    @win.on("play.click")
    def on_play_click(): ...

Both forms are recognised; the scaffolder writes the decorator form because
it's the lowest-friction wiring for a developer reading the file cold.
"""
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Handler discovery.
# ---------------------------------------------------------------------------

@dataclass
class HandlerLocation:
    """Where a single hook is implemented in a Python file."""
    hook: str
    file: Path
    line: int
    column: int
    function: str
    decorator: bool   # True when reached via @win.on(...); False for naming convention.


def _safe_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _decorator_hook(dec: ast.expr) -> str | None:
    """Return the hook name when `dec` is `<x>.on("<hook>")` or
    `subscribe(<window>, "<hook>")`; otherwise None."""
    if isinstance(dec, ast.Call):
        # @win.on("play.click")
        if (isinstance(dec.func, ast.Attribute) and dec.func.attr == "on"
                and dec.args):
            return _safe_str(dec.args[0])
        # @subscribe(win, "play.click")
        if (isinstance(dec.func, ast.Name) and dec.func.id == "subscribe"
                and len(dec.args) >= 2):
            return _safe_str(dec.args[1])
    return None


def _hook_from_name(fn_name: str, hooks: Iterable[str]) -> str | None:
    """Map a function name like ``on_play_click`` back to ``play.click``
    when an `.esk` hook with that derived name exists."""
    candidate = fn_name
    if candidate.startswith("on_"):
        candidate = candidate[3:]
    flattened = {h.replace(".", "_").replace("-", "_"): h for h in hooks}
    return flattened.get(candidate)


def index_handlers(source: str | Path,
                    known_hooks: Iterable[str] = ()) -> dict[str, HandlerLocation]:
    """Return a map ``hook_name -> HandlerLocation`` for one .py file.

    Walks top-level + class-level functions. The naming-convention
    fallback only fires when `known_hooks` is supplied so we don't
    invent associations for arbitrary functions.
    """
    p = Path(source).resolve()
    if not p.is_file():
        return {}
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except SyntaxError:
        return {}
    out: dict[str, HandlerLocation] = {}
    hooks_set = set(known_hooks)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # 1. Decorator-based.
        for dec in node.decorator_list:
            hook = _decorator_hook(dec)
            if hook:
                out[hook] = HandlerLocation(
                    hook=hook, file=p, line=node.lineno,
                    column=node.col_offset, function=node.name,
                    decorator=True,
                )
                break
        # 2. Naming-convention fallback.
        if hooks_set:
            hook = _hook_from_name(node.name, hooks_set)
            if hook and hook not in out:
                out[hook] = HandlerLocation(
                    hook=hook, file=p, line=node.lineno,
                    column=node.col_offset, function=node.name,
                    decorator=False,
                )
    return out


# ---------------------------------------------------------------------------
# Scaffolder.
# ---------------------------------------------------------------------------

def scaffold_handler(source: str | Path, hook: str,
                      window_var: str = "win") -> HandlerLocation:
    """Append a stub handler for ``hook`` to ``source`` and return the
    location of the new function. Idempotent — if the file already
    declares a handler for ``hook``, returns the existing location."""
    existing = index_handlers(source, known_hooks=[hook])
    if hook in existing:
        return existing[hook]

    p = Path(source).resolve()
    if not p.is_file():
        # Create it with a minimal module preamble so the new handler
        # is a self-contained, runnable starting point.
        preamble = (
            "\"\"\"Elysium app entry — handlers wired to skin hooks.\"\"\"\n"
            "from __future__ import annotations\n\n"
            "import elysium as ely\n\n"
            "app = ely.App(title=\"App\")\n"
            f"{window_var} = app.window()\n"
            "# win.load_skin(\"path/to/skin.esk/\")\n\n"
        )
        p.write_text(preamble, encoding="utf-8")

    fn_name = _safe_fn_name(hook)
    body = _stub_for(hook, window_var, fn_name)

    text = p.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    if not text.endswith("\n\n"):
        text += "\n"
    new_text = text + body
    new_line = new_text[:new_text.index(f"def {fn_name}")].count("\n") + 1
    p.write_text(new_text, encoding="utf-8")

    return HandlerLocation(
        hook=hook, file=p, line=new_line, column=0,
        function=fn_name, decorator=True,
    )


def _safe_fn_name(hook: str) -> str:
    name = hook.replace(".", "_").replace("-", "_")
    if not name.startswith("on_"):
        name = "on_" + name
    # Ensure it's a valid Python identifier.
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)


def _stub_for(hook: str, window_var: str, fn_name: str) -> str:
    event = hook.rsplit(".", 1)[-1] if "." in hook else "event"
    if event == "click":
        params = ""
    elif event in {"value", "change"}:
        params = "value"
    elif event in {"hover", "leave"}:
        params = ""
    elif event in {"drag", "drop"}:
        params = "event"
    else:
        params = ""
    decorator = f'@{window_var}.on("{hook}")'
    return (
        f"\n{decorator}\n"
        f"def {fn_name}({params}):\n"
        f"    # TODO: implement {hook!r}\n"
        f"    print(\"{hook} fired\")\n"
    )


# ---------------------------------------------------------------------------
# Editor launcher.
# ---------------------------------------------------------------------------

@dataclass
class EditorSpec:
    name: str
    cmd: str
    arg_template: str   # eg "{file}:{line}" or "+{line} {file}"


# Order matters — first match wins when auto-detecting.
_EDITORS: list[EditorSpec] = [
    EditorSpec("VS Code Insiders", "code-insiders", "-g {file}:{line}:{col}"),
    EditorSpec("VS Code",          "code",          "-g {file}:{line}:{col}"),
    EditorSpec("Cursor",           "cursor",        "-g {file}:{line}:{col}"),
    EditorSpec("Windsurf",         "windsurf",      "-g {file}:{line}:{col}"),
    EditorSpec("Zed",              "zed",           "{file}:{line}:{col}"),
    EditorSpec("Sublime",          "subl",          "{file}:{line}:{col}"),
    EditorSpec("Helix",            "hx",            "{file}:{line}:{col}"),
    EditorSpec("PyCharm",          "pycharm",       "--line {line} --column {col} {file}"),
    EditorSpec("IntelliJ",         "idea",          "--line {line} --column {col} {file}"),
    EditorSpec("Neovim",           "nvim",          "+{line} {file}"),
    EditorSpec("Vim",              "vim",           "+{line} {file}"),
    EditorSpec("Emacs",            "emacsclient",   "+{line}:{col} {file}"),
    EditorSpec("Xed",              "xed",           "-l {line} {file}"),
]


def detect_editor() -> EditorSpec | None:
    """Return the first editor available on PATH, honoring `$ELYSIUM_EDITOR`
    > `$VISUAL` > `$EDITOR` overrides."""
    explicit = (os.environ.get("ELYSIUM_EDITOR")
                or os.environ.get("VISUAL")
                or os.environ.get("EDITOR"))
    if explicit:
        bin_name = explicit.split()[0]
        for e in _EDITORS:
            if e.cmd == bin_name and shutil.which(bin_name):
                return e
        # Fallback to a generic spec built from the env var.
        if shutil.which(bin_name):
            return EditorSpec(name=bin_name, cmd=bin_name,
                              arg_template="{file}")
    for e in _EDITORS:
        if shutil.which(e.cmd):
            return e
    return None


def open_in_editor(file: str | Path, line: int = 1, col: int = 1) -> bool:
    """Open ``file`` at the given ``line`` (1-indexed) in the user's
    editor. Returns True on a successful spawn."""
    file = str(Path(file).resolve())
    editor = detect_editor()
    if editor is not None:
        argv = [editor.cmd] + editor.arg_template.format(
            file=file, line=line, col=col).split()
        try:
            subprocess.Popen(argv,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True
        except Exception:
            pass
    # Last-ditch fallback: the OS default opener (won't honor line).
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", file])
        elif sys.platform == "win32":
            os.startfile(file)         # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", file])
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# High-level entry point.
# ---------------------------------------------------------------------------

def goto_handler(source: str | Path, hook: str, *,
                  scaffold_if_missing: bool = True,
                  known_hooks: Iterable[str] = (),
                  window_var: str = "win") -> HandlerLocation | None:
    """Open the editor at the handler for ``hook`` in ``source``,
    scaffolding the stub when it doesn't exist yet."""
    handlers = index_handlers(source, known_hooks=known_hooks)
    loc = handlers.get(hook)
    if loc is None and scaffold_if_missing:
        loc = scaffold_handler(source, hook, window_var=window_var)
    if loc is None:
        return None
    open_in_editor(loc.file, loc.line, loc.column + 1)
    return loc


__all__ = [
    "HandlerLocation", "EditorSpec",
    "index_handlers", "scaffold_handler",
    "detect_editor", "open_in_editor", "goto_handler",
]
