"""elysium-lsp: its packaging, and a real stdio session against the server.

The language server shipped uninstallable (it depended on ``elysium``, an
unrelated PyPI package, instead of ``elysium-ui``) and, once installable,
crashed at import under pygls 2 and registered completion with a pygls 0.x
keyword. These tests keep all three from coming back.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LSP = ROOT / "elysium-lsp"


def _requirements() -> dict[str, str]:
    deps = tomllib.loads((LSP / "pyproject.toml").read_text())["project"]["dependencies"]
    out = {}
    for dep in deps:
        name = dep.split(";")[0]
        for sep in "<>=!~ ":
            name = name.split(sep)[0]
        out[name.strip().lower()] = dep
    return out


def test_lsp_depends_on_the_framework_distribution():
    reqs = _requirements()
    assert "elysium-ui" in reqs
    assert "elysium" not in reqs           # the squatted, unrelated PyPI project


def test_lsp_pins_the_pygls_major_it_is_written_for():
    assert "<2" in _requirements()["pygls"]


def _pygls_1():
    pygls = pytest.importorskip("pygls")
    from importlib.metadata import version
    if not version("pygls").startswith("1."):
        pytest.skip(f"elysium-lsp targets pygls 1.x, found {version('pygls')}")
    return pygls


def test_server_serves_completion_and_hover(tmp_path):
    _pygls_1()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "app.esk").mkdir()
    (tmp_path / "app.esk" / "document.json").write_text(json.dumps({"root": {
        "type": "group", "id": "root", "children": [], "hooks": [
            {"name": "play", "type": "event"},
            {"name": "volume", "type": "value", "range": [0, 1]},
            {"name": "mode", "type": "state", "states": ["focus", "break"]},
        ]}}))
    source = 'win["\nwin["volume"].value = 0.5\n'
    main_py = tmp_path / "main.py"
    main_py.write_text(source)
    uri = main_py.resolve().as_uri()

    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [str(LSP / "src"), os.environ.get("PYTHONPATH", "")]))
    proc = subprocess.Popen(
        [sys.executable, "-c", "from elysium_lsp.server import main; main()"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    def send(msg):
        body = json.dumps(msg).encode()
        proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        proc.stdin.flush()

    def request(id_, method, params):
        send({"jsonrpc": "2.0", "id": id_, "method": method, "params": params})
        while True:
            length = 0
            while True:
                line = proc.stdout.readline()
                assert line, proc.stderr.read().decode()[-3000:]
                if line in (b"\r\n", b"\n"):
                    break
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":")[1])
            msg = json.loads(proc.stdout.read(length))
            if msg.get("id") == id_:
                return msg

    try:
        init = request(1, "initialize", {"processId": None, "capabilities": {},
                                         "rootUri": tmp_path.resolve().as_uri()})
        caps = init["result"]["capabilities"]
        assert caps["completionProvider"]["triggerCharacters"] == ['"', "."]
        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": {
            "uri": uri, "languageId": "python", "version": 1, "text": source}}})

        completion = request(2, "textDocument/completion", {
            "textDocument": {"uri": uri}, "position": {"line": 0, "character": 5}})["result"]
        items = completion["items"] if isinstance(completion, dict) else completion
        assert sorted(i["label"] for i in items) == ["mode", "play", "volume"]

        hover = request(3, "textDocument/hover", {
            "textDocument": {"uri": uri}, "position": {"line": 1, "character": 7}})["result"]
        assert "ValueHook[0, 1]" in hover["contents"]["value"]

        request(4, "shutdown", None)
        send({"jsonrpc": "2.0", "method": "exit"})
        assert proc.wait(10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
