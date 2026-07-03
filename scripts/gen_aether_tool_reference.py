#!/usr/bin/env python3
"""Auto-generate the Aether tool reference partial.

Walks every module under `python/elysium/aether/tools/`, extracts every
`@register_tool(name=..., description=..., input_schema=...)` decorator, and
emits a markdown partial included by both doc sites via pymdownx.snippets.

Outputs two identical partials so each site can include from its own tree:

  docs/api/aether-tools.partial.md
  docs-designer/reference/aether-tool-reference.partial.md

Run from the repo root:

  python scripts/gen_aether_tool_reference.py

The script is also a pre-build step in the docs and docs-designer GitHub
Actions workflows so the published catalog can never drift from the shipping
code.
"""
from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "python" / "elysium" / "aether" / "tools"
OUTPUTS = (
    REPO_ROOT / "docs" / "api" / "aether-tools.partial.md",
    REPO_ROOT / "docs-designer" / "reference" / "aether-tool-reference.partial.md",
)

# Module order in the rendered catalog. Anything not listed here is appended
# alphabetically at the end so a new module shows up automatically.
MODULE_ORDER = [
    "mesh", "texture", "material", "render",
    "animation", "placement", "shape",
    "brush", "code", "codelink", "hook",
    "window", "snapshot", "meta", "run",
    "tester",
]

# Modules whose tools warrant expanded prose blocks beneath the table. The
# rendered catalog includes a paragraph for each call-out tool, pulled from
# the function's docstring's first sentence.
CALL_OUT_TOOLS = {
    "mesh.transfer_polar_normal",
    "mesh.bbox_then_landmark_gaps",
    "mesh.landmark_apply_full",
}


def _module_human_label(module_name: str) -> str:
    return {
        "mesh": "Mesh",
        "texture": "Texture",
        "material": "Material",
        "render": "Render",
        "animation": "Animation",
        "placement": "Placement",
        "shape": "Shape",
        "brush": "Brush",
        "code": "Code",
        "codelink": "Code Link",
        "hook": "Hook",
        "window": "Window",
        "snapshot": "Snapshot",
        "meta": "Meta",
        "run": "Run",
        "tester": "Tester",
    }.get(module_name, module_name.replace("_", " ").title())


def _first_sentence(text: str | None) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.strip().split())
    m = re.match(r"(.+?[.!?])\s", cleaned + " ")
    return (m.group(1) if m else cleaned)[:240]


def _extract_register_tool_calls(tree: ast.AST) -> list[dict]:
    """Find every @register_tool(...) decorator on a function def and pull
    its keyword arguments (name, description, input_schema, side_effect,
    undoable, etc.) plus the function's first-sentence docstring."""
    found: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            if call is None:
                continue
            func = call.func
            name_id = (
                func.attr if isinstance(func, ast.Attribute)
                else (func.id if isinstance(func, ast.Name) else None)
            )
            if name_id != "register_tool":
                continue
            kwargs: dict = {}
            for kw in call.keywords:
                if kw.arg is None:
                    continue
                kwargs[kw.arg] = _literal(kw.value)
            doc = ast.get_docstring(node) or ""
            found.append({
                "tool_name": kwargs.get("name", ""),
                "description": kwargs.get("description", ""),
                "side_effect": kwargs.get("side_effect", ""),
                "undoable": kwargs.get("undoable", ""),
                "python_name": node.name,
                "doc_first": _first_sentence(doc),
            })
    return found


def _literal(node: ast.AST):
    """Best-effort literal-eval. Returns the original AST repr if not literal."""
    try:
        return ast.literal_eval(node)
    except Exception:
        try:
            return ast.unparse(node)
        except Exception:
            return ""


def _walk_tools_dir(tools_dir: Path) -> dict[str, list[dict]]:
    """Returns {module_short_name: [tool, ...]}."""
    by_module: dict[str, list[dict]] = {}
    for src in sorted(tools_dir.glob("*.py")):
        if src.name == "__init__.py":
            continue
        module_name = src.stem
        try:
            tree = ast.parse(src.read_text())
        except SyntaxError:
            continue
        tools = _extract_register_tool_calls(tree)
        if tools:
            by_module[module_name] = tools
    return by_module


def _ordered_modules(by_module: dict[str, list[dict]]) -> list[str]:
    seen = set(MODULE_ORDER)
    extras = [m for m in sorted(by_module.keys()) if m not in seen]
    return [m for m in MODULE_ORDER if m in by_module] + extras


def _render(by_module: dict[str, list[dict]]) -> str:
    lines: list[str] = []
    total = sum(len(t) for t in by_module.values())
    lines.append(
        f"<!-- Auto-generated by scripts/gen_aether_tool_reference.py. -->\n"
        f"<!-- Do not edit by hand. -->\n")
    lines.append(
        f"Catalog of every Aether-callable tool. "
        f"Currently **{total} tools across {len(by_module)} modules**. "
        f"Re-generated on every doc build.\n")
    for module in _ordered_modules(by_module):
        tools = by_module[module]
        lines.append(f"\n## {_module_human_label(module)} ({len(tools)})\n")
        lines.append("| Tool | Side effect | Undoable | One-line purpose |")
        lines.append("|------|-------------|----------|------------------|")
        for tool in tools:
            tname = str(tool["tool_name"]) or tool["python_name"]
            side = str(tool["side_effect"]) or "n/a"
            undoable = (
                "Yes" if tool["undoable"] is True
                else "No" if tool["undoable"] is False
                else "n/a"
            )
            desc = (str(tool["description"]) or tool["doc_first"]).replace("|", "\\|")
            lines.append(f"| `{tname}` | {side} | {undoable} | {desc} |")
        # Expanded prose blocks for call-out tools.
        for tool in tools:
            tname = str(tool["tool_name"])
            if tname in CALL_OUT_TOOLS:
                lines.append(f"\n### `{tname}`\n")
                desc = str(tool["description"]) or tool["doc_first"]
                lines.append(f"{desc}\n")
                if tool["doc_first"] and tool["doc_first"] != desc:
                    lines.append(f"_{tool['doc_first']}_\n")
    lines.append("")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    if not TOOLS_DIR.is_dir():
        print(f"ERROR: tools dir not found: {TOOLS_DIR}")
        return 1
    by_module = _walk_tools_dir(TOOLS_DIR)
    rendered = _render(by_module)
    for dst in OUTPUTS:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(rendered)
    total = sum(len(t) for t in by_module.values())
    print(f"wrote {len(OUTPUTS)} partials covering {total} tools across "
          f"{len(by_module)} modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
