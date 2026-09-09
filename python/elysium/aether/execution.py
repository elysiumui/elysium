"""Acknowledged, serialized bridge operations on the Designer frame thread."""
from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import Future

from .tools import REGISTRY
from .types import SideEffect, ToolCall, TrustMode


class Operations:
    def __init__(self, designer, session_factory, control_check=lambda: False):
        self.designer = designer
        self.session_factory = session_factory
        self.control_check = control_check
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def submit(self, payload: dict) -> tuple[str, Future]:
        if not isinstance(payload, dict):
            raise TypeError("tool request must be an object")
        name, args = payload.get("name"), payload.get("args", {})
        if not isinstance(name, str) or not isinstance(args, dict):
            raise TypeError("name must be a string and args an object")
        request_id = payload.get("id", "bridge-" + uuid.uuid4().hex)
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            raise ValueError("invalid request id")
        confirmed = payload.get("confirm", False)
        if not isinstance(confirmed, bool):
            raise TypeError("confirm must be a boolean")
        signature = json.dumps([name, args, confirmed], sort_keys=True, allow_nan=False)
        dispatcher = getattr(self.designer, "_aether_dispatcher", None)
        if dispatcher is None:
            raise RuntimeError("Designer has no acknowledged command dispatcher; update Designer")
        with self._lock:
            old = self._jobs.get(request_id)
            if old is not None:
                if old["signature"] != signature:
                    raise ValueError("request id already used for a different operation")
                return request_id, old["future"]
            # Never silently evict idempotency records during a session: an
            # old timed-out client could otherwise execute a write twice.
            if len(self._jobs) >= 10000:
                raise RuntimeError("operation journal full; start a new bridge session")
            record = {"id": request_id, "name": name, "signature": signature,
                      "status": "queued", "submitted_at": time.time()}
            self._jobs[request_id] = record
            future = dispatcher.invoke(self._execute, record, args, confirmed)
            record["future"] = future
        return request_id, future

    def _execute(self, record, args, confirmed):
        record["status"] = "running"
        record["started_at"] = time.time()
        before = None
        undo_before = redo_before = None
        session = None
        write = False
        try:
            if self.control_check():
                raise PermissionError("aether_paused_or_stopped")
            session = self.session_factory()
            tool = REGISTRY.get(record["name"])
            if tool is None:
                raise ValueError(f"unknown tool {record['name']}")
            from jsonschema import Draft202012Validator
            Draft202012Validator(tool.input_schema).validate(args)
            write = tool.side_effect in (SideEffect.WRITE, SideEffect.DESTRUCTIVE)
            requires = tool.requires_confirmation == "always" or (
                tool.requires_confirmation == "destructive" and
                tool.side_effect == SideEffect.DESTRUCTIVE) or (
                write and session.trust == TrustMode.CAUTIOUS)
            if requires and not confirmed:
                raise PermissionError("confirmation_required: resubmit with confirm=true and a new id")
            if write:
                before = self.designer._snapshot()
                undo_before = list(self.designer._undo_stack)
                redo_before = list(self.designer._redo_stack)
                snapshot = session.snapshots.capture(session, action=f"bridge:{tool.name}")
                record["snapshot"] = snapshot.id
            result = REGISTRY.dispatch(ToolCall(record["id"], tool.name, args), session)
            if not result.ok:
                raise RuntimeError(result.error)
            if write:
                # Existing GUI handlers may have pushed an entry themselves.
                # Publish exactly one user-visible transaction per tool call.
                self.designer._undo_stack[:] = undo_before + [before]
                limit = getattr(self.designer, "_undo_limit", 100)
                self.designer._undo_stack[:] = self.designer._undo_stack[-limit:]
                self.designer._redo_stack.clear()
                self.designer._document_revision = getattr(self.designer, "_document_revision", 0) + 1
            record.update(status="committed", ok=True, value=result.value,
                          revision=getattr(self.designer, "_document_revision", 0), error=None)
        except Exception as exc:  # noqa: BLE001 — operation boundary reports all failures
            if before is not None:
                try:
                    self.designer._restore(before)
                    if undo_before is not None:
                        self.designer._undo_stack[:] = undo_before
                        self.designer._redo_stack[:] = redo_before
                except Exception as restore_error:  # noqa: BLE001 — retain both failures
                    record["rollback_error"] = str(restore_error)
            record.update(status="failed", ok=False, error=f"{type(exc).__name__}: {exc}")
        finally:
            record["completed_at"] = time.time()
        result = self._public(record)
        if session is not None:
            try:
                session.audit({"kind": "acknowledged_operation", **result})
            except Exception as exc:  # noqa: BLE001 — operation boundary reports all failures
                record["audit_error"] = str(exc)
                result = self._public(record)
        return result

    def _public(self, record):
        return {k: v for k, v in record.items() if k not in ("future", "signature")}

    def read(self, request_id):
        with self._lock:
            if request_id not in self._jobs:
                raise KeyError(request_id)
            return self._public(self._jobs[request_id])

    def invoke_read(self, fn, timeout=120):
        if self.control_check():
            raise PermissionError("aether_paused_or_stopped")
        dispatcher = getattr(self.designer, "_aether_dispatcher", None)
        if dispatcher is None:
            raise RuntimeError("Designer has no acknowledged command dispatcher")
        def read():
            if self.control_check():
                raise PermissionError("aether_paused_or_stopped")
            return fn()
        return dispatcher.invoke(read).result(timeout=timeout)
