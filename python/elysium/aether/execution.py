"""Acknowledged, serialized bridge operations on the Designer frame thread.

Every command that reaches the Designer from outside (HTTP bridge, CLI,
daemon) funnels through one of two entry points here:

* :func:`run_transaction` — the single transactional core: checkpoint →
  dispatch → optional persist → publish one undo entry + revision bump,
  or roll the document back. Used by :class:`Operations`,
  ``HeadlessDesigner.dispatch_persistent_tool`` and the daemon.
* :class:`Operations` — an idempotent operation journal. ``submit()``
  enqueues a command on the Designer's frame-thread dispatcher (or, when
  the Designer supplies none, on a private dispatcher drained inline under
  a lock) and hands back a receipt future. Retrying a request id never
  executes twice.

The shared policy helper :func:`confirmation_required` is the *only* place
the ``requires_confirmation`` × :class:`TrustMode` matrix is evaluated.
"""
from __future__ import annotations

import contextlib
import json
import threading
import time
import uuid
from concurrent.futures import Future

from ..concurrency import UiDispatcher
from .tools import REGISTRY
from .types import SideEffect, ToolCall, ToolResult, TrustMode

_TERMINAL = ("committed", "failed", "cancelled")
_ACTIVE = ("queued", "running")
_INLINE_NOTICE = ("aether: Designer has no command dispatcher; executing operations "
                  "inline (serialized). Update the Designer for frame-thread execution.")


# ---------------------------------------------------------------------------
# Shared policy helpers.
# ---------------------------------------------------------------------------

def is_mutation(tool) -> bool:
    """True for tools that touch the document (WRITE / DESTRUCTIVE)."""
    return tool.side_effect in (SideEffect.WRITE, SideEffect.DESTRUCTIVE)


@contextlib.contextmanager
def designer_context(designer):
    """Run a dispatch inside the Designer's own document context.

    ``transaction_context()`` is how a Designer makes its document the
    resolution context for the command that is running — the headless
    Designer returns ``mesh_document.using(self)``, which routes every
    store-less mesh lookup at that document's store. Reads need it just
    as much as writes: without it ``default_store()`` hands back the
    process-wide fallback, so a key only this document holds (a named
    registration, a restored legacy asset) is invisible and the read
    fails or silently renders a substitute.

    Every entry point uses this one helper — :func:`run_transaction`,
    ``Operations._execute``, ``Operations.invoke_read`` and the daemon —
    so there is a single answer to "which document is this call about".
    Nesting is harmless: ``mesh_document.using`` is a contextvar
    token set/reset pair, so an inner entry restores the outer binding
    exactly. A Designer without the hook (older GUI builds, test
    doubles) gets a null context.
    """
    context_fn = getattr(designer, "transaction_context", None)
    with (context_fn() if callable(context_fn) else contextlib.nullcontext()):
        yield


def validate_args(tool, args: dict) -> None:
    """Validate ``args`` against ``tool.input_schema``; raise ``ValueError``
    naming the tool and the offending path."""
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
    try:
        Draft202012Validator(tool.input_schema).validate(args)
    except ValidationError as e:
        where = "/".join(map(str, e.absolute_path)) or "<root>"
        raise ValueError(f"invalid arguments for {tool.name}: {e.message} at {where}") from e


def confirmation_required(tool, trust, confirmed: bool) -> bool:
    """The one confirmation policy: ``requires_confirmation`` × ``trust``.

    * ``"always"`` — every call needs confirmation.
    * ``"destructive"`` — DESTRUCTIVE tools need confirmation.
    * ``TrustMode.CAUTIOUS`` — every mutation (WRITE/DESTRUCTIVE) needs it.

    Returns True when confirmation is needed *and* was not given.
    """
    needs = (
        tool.requires_confirmation == "always"
        or (tool.requires_confirmation == "destructive"
            and tool.side_effect is SideEffect.DESTRUCTIVE)
        or (is_mutation(tool) and trust is TrustMode.CAUTIOUS)
    )
    return bool(needs and not confirmed)


def run_transaction(designer, session, tool, call, *, registry,
                    persist: bool = False, action: str | None = None,
                    confirmed: bool | None = None,
                    exclusive_history: bool = False) -> ToolResult:
    """Checkpoint → dispatch → persist? → publish undo/revision, or rollback.

    Every ``designer`` attribute is optional so old Designers keep working:
    ``_snapshot``/``_restore`` give in-memory rollback, ``_undo_stack``/
    ``_redo_stack``/``_undo_limit`` publish exactly one undo entry per
    committed call, ``_document_revision`` is bumped on commit (created at
    1 when the designer never defined it), and
    ``save_layout`` persists when ``persist`` is set.

    A checkpoint failure aborts *before* the handler runs. A failing
    handler (or a failing persist) rolls the document and both history
    stacks back; a rollback failure is retained in ``rollback_error``.

    Two more optional hooks let a designer own resources across the whole
    transaction: ``transaction_context()`` returns a context manager that
    wraps checkpoint, handler, persist and rollback (the headless designer
    uses it to make its mesh store the resolution context), and
    ``after_commit()`` runs once a command has been persisted and published
    (the headless designer sweeps superseded mesh revisions there). An
    ``after_commit`` failure never un-commits the command; it is reported
    as a warning on the result.


    ``exclusive_history`` says the calling thread is the only writer of the
    designer's history while the transaction runs — true on the Designer
    frame thread draining ``_aether_dispatcher``, and the mode in which a
    user edit cannot race a command at all. Both modes write history
    wholesale, so it always agrees with the document; in shared mode
    (inline execution on an HTTP thread, the daemon beside a GUI Designer)
    an undo or redo the user performs mid-command is detected and reported
    as a ``history`` warning on the result rather than discarded silently.
    """
    with designer_context(designer):
        return _run_transaction(designer, session, tool, call, registry=registry,
                                persist=persist, action=action, confirmed=confirmed,
                                exclusive_history=exclusive_history)


def _run_transaction(designer, session, tool, call, *, registry, persist, action,
                     confirmed, exclusive_history) -> ToolResult:
    snapshot_fn = getattr(designer, "_snapshot", None)
    restore_fn = getattr(designer, "_restore", None)
    has_stacks = (hasattr(designer, "_undo_stack")
                  and hasattr(designer, "_redo_stack"))
    before = None
    undo_before = redo_before = None
    try:
        if callable(snapshot_fn):
            before = snapshot_fn()
        if has_stacks:
            undo_before = list(designer._undo_stack)
            redo_before = list(designer._redo_stack)
        snap = session.snapshots.capture(session, action=action or tool.name)
    except Exception as e:  # noqa: BLE001 — abort before the handler runs
        return ToolResult(id=call.id, ok=False,
                          error=f"Cannot checkpoint command: {type(e).__name__}: {e}")
    # dispatch() never raises: handler failures (interrupts included) come
    # back as a failed result, so the rollback below always runs.
    result = registry.dispatch(call, session, confirmed=confirmed)
    result.snapshot_id = snap.id
    if result.ok and persist:
        try:
            if designer.save_layout() is False:
                raise RuntimeError("Designer save failed")
        except BaseException as e:  # noqa: BLE001 — a failed (or interrupted) persist is a failed command
            result.ok = False
            result.error = f"Cannot persist command: {type(e).__name__}: {e}"
            result.value = None
    if result.ok:
        # Existing GUI handlers may have pushed an entry themselves.
        # Publish exactly one user-visible transaction per tool call.
        if has_stacks and before is not None:
            if _publish_history(designer, before, undo_before, redo_before,
                                exclusive_history):
                result.warnings.append({"path": "history", "message": _RACE_WARNING})
        # Create-on-first-commit: the shipped GUI Designer defines the undo
        # stacks and _snapshot/_restore but never _document_revision, and
        # every receipt / GET /state reports this counter.
        designer._document_revision = getattr(designer, "_document_revision", 0) + 1
        after_commit = getattr(designer, "after_commit", None)
        if callable(after_commit):
            try:
                after_commit()
            except Exception as e:  # noqa: BLE001 — the command is committed; report, don't un-commit
                result.warnings.append({"path": "after_commit",
                                        "message": f"{type(e).__name__}: {e}"[:200]})
        return result
    try:
        if before is not None and callable(restore_fn):
            restore_fn(before)
        if has_stacks and _rollback_history(designer, before, undo_before,
                                            redo_before, exclusive_history):
            result.warnings.append({"path": "history", "message": _RACE_WARNING})
    except Exception as e:  # noqa: BLE001 — retain both failures
        result.rollback_error = f"{type(e).__name__}: {e}"
        result.error = f"{result.error}; rollback failed: {result.rollback_error}"
    return result


# --- history publication ------------------------------------------------------
#
# The undo stacks are raw lists the GUI Designer mutates from its frame
# thread (_push_undo / _undo / _redo). A transaction publishes exactly one
# entry per committed command and puts both stacks back on failure.
#
# ``exclusive_history`` says the calling thread is the only writer while the
# transaction runs — true on the frame thread draining ``_aether_dispatcher``.
# Shared mode (inline execution on an HTTP thread beside a GUI Designer)
# cannot serialize against the frame thread, so a user undo/redo can land
# mid-command. History is still written wholesale there, because the
# document is: rollback calls ``_restore(before)``, which takes the document
# past the user's action, and stacks that disagreed with the document would
# leave states unreachable, a redo that does nothing, or undo steps out of
# order. Instead of silently discarding such an action, the transaction
# detects it and reports it on the result, and the Designer is expected to
# supply a dispatcher (see the Aether guide) to make the race impossible.


def _same_entry(a, b) -> bool:
    """Whole-document snapshots compare by value (JSON-like dicts); ones
    that refuse to compare are treated as different."""
    try:
        return bool(a == b)
    except Exception:  # noqa: BLE001 — snapshots need not be comparable
        return False


def _history_raced(designer, before, undo_before: list, redo_before: list) -> bool:
    """True when another thread wrote the designer's history while the
    handler ran.

    Undo and redo each move an entry off ``_redo_stack`` or shorten
    ``_undo_stack``, so a changed redo stack or a rewritten undo prefix is a
    concurrent writer. Appends are ambiguous — the handler may publish its
    own entry — so exactly one appended entry recording the pre-command
    document is taken as the handler's own ``_push_undo`` (this transaction
    collapses it into its single entry) and anything else is reported."""
    try:
        redo = designer._redo_stack
        if len(redo) != len(redo_before) or any(a is not b for a, b in zip(redo, redo_before)):
            return True
        undo = designer._undo_stack
        if len(undo) < len(undo_before):
            return True
        if any(a is not b for a, b in zip(undo, undo_before)):
            return True
        appended = undo[len(undo_before):]
        if not appended:
            return False
        return len(appended) > 1 or not _same_entry(appended[0], before)
    except Exception:  # noqa: BLE001 — detection must never fail a command
        return False


def _publish_history(designer, before, undo_before: list, redo_before: list,
                     exclusive: bool) -> bool:
    """Publish ``before`` as the one undo entry of a committed call; a
    committed edit clears redo, exactly as the Designer's ``_push_undo``.
    Returns True when a concurrent history write was observed (shared mode)."""
    raced = (not exclusive) and _history_raced(designer, before, undo_before, redo_before)
    limit = getattr(designer, "_undo_limit", 100)
    designer._undo_stack[:] = (undo_before + [before])[-limit:]
    designer._redo_stack.clear()
    return raced


def _rollback_history(designer, before, undo_before: list, redo_before: list,
                      exclusive: bool) -> bool:
    """Put both stacks back where the transaction found them — the document
    has just been restored to the same point, so history follows it.
    Returns True when a concurrent history write was observed (shared mode)."""
    raced = (not exclusive) and _history_raced(designer, before, undo_before, redo_before)
    designer._undo_stack[:] = undo_before
    designer._redo_stack[:] = redo_before
    return raced


_RACE_WARNING = ("an undo or redo performed while this command ran was discarded: "
                 "the document and its history are back in step, but the action is "
                 "lost. Give the Designer an _aether_dispatcher so commands run on "
                 "the frame thread and cannot race user edits.")


# ---------------------------------------------------------------------------
# Operation journal.
# ---------------------------------------------------------------------------

class Operations:
    """Idempotent, acknowledged command journal.

    ``submit(payload)`` returns ``(request_id, future)``; the future resolves
    to the receipt dict once the command reached a terminal state
    (``committed`` | ``failed`` | ``cancelled``). Resubmitting an id with the
    same signature returns the *same* future and bumps ``attempts`` — the
    command never runs twice. ``read(id)`` returns the live receipt.

    Execution happens on ``designer._aether_dispatcher`` (the frame thread)
    when the Designer supplies one; otherwise on a private dispatcher that
    is drained inline on the submitting thread under a lock, which keeps
    HeadlessDesigner / CLI / older Designers serialized without extra
    threads. Inline execution serializes bridge commands against each
    other only: a GUI Designer's frame thread keeps running, so a user edit
    can race a command; the transaction reports such a race instead of
    losing it silently (see :func:`run_transaction`).
    """

    def __init__(self, designer, session_factory, control_check=lambda: None, *,
                 wake=None, on_activity=None, ack_hint: str = "") -> None:
        self.designer = designer
        self.session_factory = session_factory
        self.control_check = control_check
        self.wake = wake
        self.on_activity = on_activity
        self.ack_hint = ack_hint
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._owned: UiDispatcher | None = None
        self._inline_lock = threading.Lock()
        self._activity_lock = threading.Lock()
        self._active = False

    # --- dispatcher selection -------------------------------------------
    def _dispatcher(self) -> tuple[UiDispatcher, bool]:
        supplied = getattr(self.designer, "_aether_dispatcher", None)
        if supplied is not None:
            return supplied, False
        with self._lock:
            if self._owned is None:
                self._owned = UiDispatcher()
                print(_INLINE_NOTICE, flush=True)
            return self._owned, True

    def _drain_inline(self) -> None:
        with self._inline_lock:
            self._owned.drain()

    def _fire_wake(self) -> None:
        fn = self.wake or getattr(self.designer, "_aether_wake", None)
        if fn is None:
            return
        try:
            fn()
        except Exception:  # noqa: BLE001 — a broken waker must not fail the submit
            pass

    # --- receipts --------------------------------------------------------
    @staticmethod
    def _public(record: dict) -> dict:
        return {k: v for k, v in record.items()
                if k not in ("future", "signature", "args", "listeners")}

    def _set(self, record: dict, **fields) -> None:
        with self._lock:
            record.update(fields)

    def read(self, request_id: str) -> dict:
        with self._lock:
            if request_id not in self._jobs:
                raise KeyError(request_id)
            return self._public(self._jobs[request_id])

    def on_terminal(self, request_id: str, fn) -> None:
        """Call ``fn(receipt)`` exactly once when the operation settles
        (``committed`` | ``failed`` | ``cancelled``): right away, on this
        thread, if it already has; else from the thread that settles it.
        Registration and the terminal transition share the journal lock,
        so a listener can neither be missed nor fired twice. Unknown ids
        raise ``KeyError``; a listener that raises is dropped."""
        with self._lock:
            record = self._jobs.get(request_id)
            if record is None:
                raise KeyError(request_id)
            if record["status"] not in _TERMINAL:
                record.setdefault("listeners", []).append(fn)
                return
            receipt = self._public(record)
        self._call_listeners([fn], receipt)

    def _pop_listeners(self, record: dict) -> tuple[list, dict]:
        with self._lock:
            return record.pop("listeners", []), self._public(record)

    @staticmethod
    def _call_listeners(listeners: list, receipt: dict) -> None:
        for fn in listeners:
            try:
                fn(receipt)
            except Exception:  # noqa: BLE001 — observers never break the journal
                pass

    def stats(self) -> dict:
        with self._lock:
            statuses = [r["status"] for r in self._jobs.values()]
        return {"queued": statuses.count("queued"),
                "running": statuses.count("running"),
                "total": len(statuses),
                "inline": getattr(self.designer, "_aether_dispatcher", None) is None}

    def _notify_activity(self) -> None:
        if self.on_activity is None:
            return
        with self._activity_lock:
            with self._lock:
                active = any(r["status"] in _ACTIVE for r in self._jobs.values())
            if active == self._active:
                return
            self._active = active
            try:
                self.on_activity(active)
            except Exception:  # noqa: BLE001 — observers never break the journal
                pass

    # --- submission ------------------------------------------------------
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
        # `wait` is transport-only: it never enters the idempotency signature.
        signature = json.dumps([name, args, confirmed], sort_keys=True, allow_nan=False)
        dispatcher, inline = self._dispatcher()
        with self._lock:
            old = self._jobs.get(request_id)
            if old is not None:
                if old["signature"] != signature:
                    raise ValueError("request id already used for a different operation")
                old["attempts"] += 1
                return request_id, old["future"]
            # Never silently evict idempotency records during a session: an
            # old timed-out client could otherwise execute a write twice.
            if len(self._jobs) >= 10000:
                raise RuntimeError("operation journal full; start a new bridge session")
            record = {"id": request_id, "name": name, "signature": signature,
                      "args": args, "status": "queued",
                      "submitted_at": time.time(), "attempts": 1,
                      "revision": None, "snapshot": None}
            self._jobs[request_id] = record
            future = dispatcher.invoke(self._execute, record, args, confirmed,
                                      not inline)
            record["future"] = future
        self._fire_wake()
        self._notify_activity()
        if inline:
            self._drain_inline()
        return request_id, future

    def cancel(self, request_id: str, reason: str = "cancelled") -> dict:
        """Cancel a *queued* operation. A running or finished one is left
        alone; the returned receipt says which. Idempotent: an operation
        that is already cancelled keeps its original reason."""
        listeners: list = []
        with self._lock:
            record = self._jobs.get(request_id)
            if record is None:
                raise KeyError(request_id)
            future = record["future"]
            if not future.cancelled() and future.cancel():
                record.update(status="cancelled", ok=False,
                              error=f"cancelled: {reason}", reason=reason,
                              completed_at=time.time())
                listeners = record.pop("listeners", [])
            receipt = self._public(record)
        self._notify_activity()
        self._call_listeners(listeners, receipt)
        return receipt

    def cancel_all(self, reason: str) -> list[str]:
        with self._lock:
            queued = [rid for rid, r in self._jobs.items() if r["status"] == "queued"]
        cancelled = []
        for rid in queued:
            try:
                if self.cancel(rid, reason)["status"] == "cancelled":
                    cancelled.append(rid)
            except KeyError:
                pass
        return cancelled

    # --- execution (frame thread or inline) ------------------------------
    def _control_reason(self) -> str | None:
        reason = self.control_check()
        if not reason:
            return None
        return reason if isinstance(reason, str) else "aether_paused_or_stopped"

    def _execute(self, record: dict, args: dict, confirmed: bool,
                 exclusive_history: bool = False) -> dict:
        self._set(record, status="running", started_at=time.time())
        session = None
        try:
            reason = self._control_reason()
            if reason:
                raise PermissionError(reason)
            session = self.session_factory()
            tool = REGISTRY.get(record["name"])
            if tool is None:
                raise ValueError(f"unknown tool {record['name']}")
            validate_args(tool, args)
            if confirmation_required(tool, session.trust, confirmed):
                raise PermissionError("confirmation_required: resubmit with confirm=true and a new id")
            call = ToolCall(record["id"], tool.name, args)
            if is_mutation(tool):
                # Only the frame thread (a supplied dispatcher) owns the
                # undo stacks; inline execution shares them with it.
                result = run_transaction(
                    self.designer, session, tool, call, registry=REGISTRY,
                    action=f"bridge:{tool.name}",
                    persist=hasattr(self.designer, "dispatch_persistent_tool"),
                    exclusive_history=exclusive_history)
            else:
                # A read is about the same document a write is about: it
                # resolves the Designer's own assets, not the process
                # fallback's (see designer_context).
                with designer_context(self.designer):
                    result = REGISTRY.dispatch(call, session)
            revision = getattr(self.designer, "_document_revision", 0)
            if result.ok:
                fields = {"status": "committed", "ok": True, "value": result.value,
                          "error": None, "warnings": list(result.warnings),
                          "snapshot": result.snapshot_id, "revision": revision}
            else:
                fields = {"status": "failed", "ok": False, "value": result.value,
                          "error": result.error, "warnings": list(result.warnings),
                          "rollback_error": result.rollback_error,
                          "snapshot": result.snapshot_id, "revision": revision}
        except BaseException as exc:  # noqa: BLE001 — the operation boundary
            # Everything ends as a failed receipt here, interrupts included.
            # Handler code is fenced by Registry.dispatch (the transaction
            # has already rolled back); what reaches this branch is a
            # control / session / checkpoint failure. Re-raising would leave
            # the future unresolved (UiDispatcher.drain fences Exception
            # only) and end the frame loop mid-session.
            fields = {"status": "failed", "ok": False,
                      "revision": getattr(self.designer, "_document_revision", 0)}
            if isinstance(exc, PermissionError):
                fields["error"] = str(exc)
                if str(exc).startswith("aether_"):
                    fields["reason"] = str(exc)
            else:
                fields["error"] = f"{type(exc).__name__}: {exc}"
        # One terminal transition: the receipt turns terminal *and*
        # complete in the same lock hold, and the activity flag follows
        # before anything else runs.
        self._set(record, completed_at=time.time(), **fields)
        self._notify_activity()
        public = self.read(record["id"])
        if session is not None:
            try:
                session.audit({"kind": "acknowledged_operation", **public})
            except Exception as exc:  # noqa: BLE001 — audit must not lose the acknowledgement
                self._set(record, audit_error=str(exc))
        listeners, public = self._pop_listeners(record)
        self._call_listeners(listeners, public)
        return public

    def invoke_read(self, fn, timeout: float = 120):
        """Run ``fn`` on the Designer's thread, inside its document context.

        This is the bridge's read path (``GET /state``, ``GET /snapshot``),
        so the preview it renders must resolve the same assets the
        Designer draws — see :func:`designer_context`.
        """
        reason = self._control_reason()
        if reason:
            raise PermissionError(reason)
        dispatcher, inline = self._dispatcher()

        def read():
            inner = self._control_reason()
            if inner:
                raise PermissionError(inner)
            with designer_context(self.designer):
                return fn()

        future = dispatcher.invoke(read)
        self._fire_wake()
        if inline:
            self._drain_inline()
        return future.result(timeout=timeout)


__all__ = ["Operations", "run_transaction", "confirmation_required",
           "designer_context", "validate_args", "is_mutation"]
