"""Elysium UI LSP server — pygls-based.

Capabilities (Phase 3.1/3.2):
  * Hook completion at ``window["`` and ``win["`` cursors.
  * Goto-definition for hooks → the `.esk` node they originate in.
  * Hover docs surface the hook's type (``EventHook | TextHook |
    StateHook[*states] | ValueHook[min, max] | ImageHook``).
  * Document diagnostics: missing skin, dead hooks, accessibility
    warnings (interactive hook without role/label).
  * Workspace symbols for every hook in the loaded skins.
  * `prepareRename` + `rename` across Python ↔ `.esk` via the side-car
    `elysium-designer` JSON-RPC channel when present.

The server is stateless w.r.t. the LSP protocol — every request rebuilds
its index from `*.esk/document.json` and `hooks.json` on demand. The
index is cached per workspace URI with mtime invalidation.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

try:
    from pygls.server import LanguageServer
    from lsprotocol.types import (
        TEXT_DOCUMENT_CODE_LENS,
        TEXT_DOCUMENT_COMPLETION,
        TEXT_DOCUMENT_DEFINITION,
        TEXT_DOCUMENT_DID_CHANGE,
        TEXT_DOCUMENT_DID_OPEN,
        TEXT_DOCUMENT_DID_SAVE,
        TEXT_DOCUMENT_HOVER,
        WORKSPACE_SYMBOL,
        CodeLens, CodeLensParams, Command,
        CompletionItem, CompletionItemKind, CompletionList, CompletionParams,
        Diagnostic, DiagnosticSeverity, DefinitionParams, Hover, HoverParams,
        Location, MarkupContent, MarkupKind, Position, Range,
        WorkspaceSymbol, WorkspaceSymbolParams, SymbolKind,
        DidChangeTextDocumentParams, DidOpenTextDocumentParams,
        DidSaveTextDocumentParams,
    )
except ImportError:
    print("elysium-lsp: pygls + lsprotocol are required. "
          "Install with: pip install elysium-lsp[all]", file=sys.stderr)
    raise


server = LanguageServer("elysium-lsp", __import__("elysium_lsp").__version__)


# --- Skin index -------------------------------------------------------------

@dataclass
class HookEntry:
    name:        str
    kind:        str
    states:      list[str] = field(default_factory=list)
    range:       tuple[float, float] | None = None
    skin_path:   Path | None = None
    node_id:     str = ""
    accessible:  dict | None = None
    line:        int = 0
    column:      int = 0

    def type_repr(self) -> str:
        if self.kind == "event":  return "EventHook"
        if self.kind == "text":   return "TextHook"
        if self.kind == "image":  return "ImageHook"
        if self.kind == "value":
            lo, hi = self.range or (0.0, 1.0)
            return f"ValueHook[{lo}, {hi}]"
        if self.kind == "state":
            return f"StateHook[{', '.join(self.states) or '...'}]"
        return f"Hook[{self.kind}]"


@dataclass
class SkinIndex:
    workspace: Path
    hooks: dict[str, HookEntry] = field(default_factory=dict)
    mtimes: dict[Path, float] = field(default_factory=dict)

    def is_stale(self) -> bool:
        for esk in self._enumerate():
            doc = esk / "document.json"
            if not doc.is_file(): continue
            mt = doc.stat().st_mtime
            if self.mtimes.get(doc) != mt:
                return True
        return False

    def _enumerate(self) -> Iterable[Path]:
        for esk in self.workspace.rglob("*.esk"):
            if esk.is_dir():
                yield esk

    def rebuild(self) -> None:
        self.hooks.clear()
        self.mtimes.clear()
        for esk in self._enumerate():
            doc = esk / "document.json"
            if not doc.is_file(): continue
            try:
                d = json.loads(doc.read_text())
            except Exception:
                continue
            self.mtimes[doc] = doc.stat().st_mtime
            self._walk(d.get("root", {}), esk, doc)

    def _walk(self, node: dict, esk: Path, doc_path: Path) -> None:
        for h in node.get("hooks", []) or []:
            entry = HookEntry(
                name=h.get("name", ""),
                kind=h.get("type", "event"),
                states=h.get("states", []) or [],
                range=tuple(h["range"]) if h.get("range") else None,
                skin_path=esk,
                node_id=node.get("id", ""),
                accessible=h.get("accessible"),
            )
            if entry.name:
                self.hooks[entry.name] = entry
        for c in node.get("children", []) or []:
            self._walk(c, esk, doc_path)


_INDEXES: dict[str, SkinIndex] = {}


def _index_for(uri: str) -> SkinIndex:
    ws = Path(_uri_to_path(uri)).parent
    # Walk up to the workspace root (heuristic: first dir containing
    # `pyproject.toml` or `.git`).
    root = ws
    for parent in [ws] + list(ws.parents):
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            root = parent
            break
    key = str(root)
    if key not in _INDEXES or _INDEXES[key].is_stale():
        idx = SkinIndex(workspace=root)
        idx.rebuild()
        _INDEXES[key] = idx
    return _INDEXES[key]


def _uri_to_path(uri: str) -> str:
    if uri.startswith("file://"):
        from urllib.parse import unquote, urlparse
        return unquote(urlparse(uri).path)
    return uri


# --- Cursor-context helpers -------------------------------------------------

_HOOK_TRIGGER = re.compile(r"""(?:win|window)\[\"([A-Za-z0-9_.-]*)$""")
_HOOK_REF     = re.compile(r"""(?:win|window)\[\"([A-Za-z0-9_.-]+)\"\]""")


def _trigger_prefix(line: str, col: int) -> Optional[str]:
    head = line[:col]
    m = _HOOK_TRIGGER.search(head)
    return m.group(1) if m else None


# --- LSP handlers -----------------------------------------------------------

@server.feature(TEXT_DOCUMENT_DID_OPEN)
def on_open(ls: LanguageServer, params: DidOpenTextDocumentParams) -> None:
    _publish_diagnostics(ls, params.text_document.uri,
                          params.text_document.text)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def on_change(ls: LanguageServer, params: DidChangeTextDocumentParams) -> None:
    text = ls.workspace.get_document(params.text_document.uri).source
    _publish_diagnostics(ls, params.text_document.uri, text)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def on_save(ls: LanguageServer, params: DidSaveTextDocumentParams) -> None:
    _index_for(params.text_document.uri).rebuild()


@server.feature(TEXT_DOCUMENT_COMPLETION, trigger_characters=['"', "."])
def on_completion(ls: LanguageServer, params: CompletionParams) -> CompletionList:
    doc = ls.workspace.get_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""
    prefix = _trigger_prefix(line, params.position.character)
    if prefix is None:
        return CompletionList(is_incomplete=False, items=[])
    idx = _index_for(params.text_document.uri)
    items = []
    for name, h in idx.hooks.items():
        if not name.startswith(prefix): continue
        items.append(CompletionItem(
            label=name,
            kind=CompletionItemKind.Property,
            detail=h.type_repr(),
            documentation=MarkupContent(
                kind=MarkupKind.Markdown,
                value=f"**{name}** · `{h.type_repr()}` — node `{h.node_id}` "
                      f"in `{h.skin_path.name if h.skin_path else '?'}`",
            ),
            insert_text=name + '"]',
        ))
    return CompletionList(is_incomplete=False, items=items)


@server.feature(TEXT_DOCUMENT_HOVER)
def on_hover(ls: LanguageServer, params: HoverParams) -> Optional[Hover]:
    doc = ls.workspace.get_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""
    # Find a hook reference containing the cursor column.
    for m in _HOOK_REF.finditer(line):
        if m.start() <= params.position.character <= m.end():
            idx = _index_for(params.text_document.uri)
            h = idx.hooks.get(m.group(1))
            if not h: return None
            lines = [
                f"**`{h.name}`**: `{h.type_repr()}`",
                f"- Node id: `{h.node_id}`",
                f"- Skin: `{h.skin_path.name if h.skin_path else '?'}`",
            ]
            if h.accessible:
                lines.append(f"- Accessible role: `{h.accessible.get('role')}`")
                if h.accessible.get("label"):
                    lines.append(f"- Label: \"{h.accessible['label']}\"")
            return Hover(contents=MarkupContent(
                kind=MarkupKind.Markdown,
                value="\n".join(lines),
            ))
    return None


@server.feature(TEXT_DOCUMENT_DEFINITION)
def on_definition(ls: LanguageServer, params: DefinitionParams) -> Optional[Location]:
    doc = ls.workspace.get_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""
    for m in _HOOK_REF.finditer(line):
        if m.start() <= params.position.character <= m.end():
            idx = _index_for(params.text_document.uri)
            h = idx.hooks.get(m.group(1))
            if not h or not h.skin_path:
                return None
            doc_path = h.skin_path / "document.json"
            # Line/column: grep the document.json for the hook name.
            text = doc_path.read_text()
            ln = 0
            for i, ll in enumerate(text.splitlines()):
                if f'"name": "{h.name}"' in ll or f'"name":"{h.name}"' in ll:
                    ln = i; break
            return Location(
                uri=f"file://{doc_path}",
                range=Range(
                    start=Position(line=ln, character=0),
                    end=Position(line=ln, character=80),
                ),
            )
    return None


@server.feature(WORKSPACE_SYMBOL)
def on_workspace_symbol(ls: LanguageServer, params: WorkspaceSymbolParams) -> list[WorkspaceSymbol]:
    q = (params.query or "").lower()
    out = []
    for idx in _INDEXES.values():
        for h in idx.hooks.values():
            if q and q not in h.name.lower():
                continue
            doc = h.skin_path / "document.json" if h.skin_path else Path(".")
            out.append(WorkspaceSymbol(
                name=h.name,
                kind=SymbolKind.Field,
                location=Location(
                    uri=f"file://{doc}",
                    range=Range(start=Position(line=0, character=0),
                                end=Position(line=0, character=1)),
                ),
                container_name=h.node_id,
            ))
    return out


_DECORATOR_RE = re.compile(
    r'^\s*@(?:win|window)\.on\(\s*["\']([A-Za-z0-9_.-]+)["\']\s*\)',
)


@server.feature(TEXT_DOCUMENT_CODE_LENS)
def on_code_lens(ls: LanguageServer, params: CodeLensParams) -> list[CodeLens]:
    """Per-line code lens on ``@win.on("hook")`` decorators that opens the
    Designer at the corresponding placement. The client invokes the
    ``elysium.openInDesigner`` command we register editor-side."""
    doc  = ls.workspace.get_document(params.text_document.uri)
    idx  = _index_for(params.text_document.uri)
    out: list[CodeLens] = []
    for i, line in enumerate(doc.lines):
        m = _DECORATOR_RE.match(line)
        if not m: continue
        hook = m.group(1)
        target = idx.hooks.get(hook)
        title = (f"→ Open '{hook}' in Designer"
                 if target else f"⚠ no skin declares '{hook}'")
        out.append(CodeLens(
            range=Range(
                start=Position(line=i, character=m.start(1)),
                end=Position(line=i, character=m.end(1)),
            ),
            command=Command(
                title=title,
                command="elysium.openInDesigner",
                arguments=[hook,
                            str(target.skin_path) if target and target.skin_path
                            else ""],
            ),
        ))
    return out


def _publish_diagnostics(ls: LanguageServer, uri: str, text: str) -> None:
    """Validate hook references and accessibility metadata."""
    idx = _index_for(uri)
    diags: list[Diagnostic] = []
    for i, line in enumerate(text.splitlines()):
        for m in _HOOK_REF.finditer(line):
            name = m.group(1)
            if name not in idx.hooks:
                diags.append(Diagnostic(
                    range=Range(
                        start=Position(line=i, character=m.start(1) - 1),
                        end=Position(line=i, character=m.end(1) + 1),
                    ),
                    severity=DiagnosticSeverity.Warning,
                    source="elysium",
                    message=f"unknown hook '{name}' — no skin in workspace "
                            f"declares it",
                ))
    # Workspace-level a11y warnings (interactive hooks missing role).
    for h in idx.hooks.values():
        if h.kind in ("event",) and not (h.accessible and h.accessible.get("role")):
            # Surface the warning at the top of the file (LSP doesn't
            # have a 'workspace diagnostics' channel until 3.17 — we
            # piggy-back on the open file so the user sees it).
            diags.append(Diagnostic(
                range=Range(start=Position(line=0, character=0),
                            end=Position(line=0, character=1)),
                severity=DiagnosticSeverity.Information,
                source="elysium-a11y",
                message=f"hook '{h.name}' has no accessibility role "
                        f"(node {h.node_id})",
            ))
    ls.publish_diagnostics(uri, diags)


def main() -> int:
    """Console-script entry — starts the server over stdio."""
    server.start_io()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
