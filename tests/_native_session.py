"""Shared headless Aether session helper for native-document tests.

Import the fixture into a test module with::

    from _native_session import native_session  # noqa: F401

(``tests/`` is on ``sys.path`` under both ``pytest`` and ``python -m pytest``;
the repository root is not guaranteed to be.)

It yields ``(designer, session, call)`` where ``call(tool, **args)``
dispatches a persistent public tool call (schema validation, checkpoint,
save, rollback) and returns the tool value, asserting success. Use
``call.expect_failure(tool, **args)`` to get the failed ``ToolResult``.
"""
from __future__ import annotations

import uuid

import pytest


def _make_call(designer, session):
    from elysium.aether.tools import REGISTRY
    from elysium.aether.types import ToolCall

    def dispatch(tool, /, **args):
        return designer.dispatch_persistent_tool(ToolCall(uuid.uuid4().hex, tool, args), session, REGISTRY)

    def call(tool, /, **args):
        result = dispatch(tool, **args)
        assert result.ok, f"{tool} failed: {result.error}"
        return result.value

    def expect_failure(tool, /, **args):
        result = dispatch(tool, **args)
        assert not result.ok, f"{tool} unexpectedly succeeded: {result.value}"
        return result

    call.expect_failure = expect_failure
    call.dispatch = dispatch
    return call


def make_native_session(tmp_path, monkeypatch, name="native.esk"):
    """Build a HeadlessDesigner + Session pair rooted in ``tmp_path``."""
    from elysium.aether import Session
    from elysium.aether._headless import MODELS, HeadlessDesigner

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    designer = HeadlessDesigner.from_skin(tmp_path / name)
    session = Session(designer=designer, designer_models=MODELS)
    return designer, session, _make_call(designer, session)


@pytest.fixture
def native_session(tmp_path, monkeypatch):
    designer, session, call = make_native_session(tmp_path, monkeypatch)
    yield designer, session, call
    # Release the document's mesh keys (and their MESH_LIBRARY shims) now
    # rather than whenever the garbage collector gets to the designer.
    designer.mesh_store.clear()
