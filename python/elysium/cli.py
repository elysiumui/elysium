"""`elysium` command-line entry point."""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path


def _hash_path(p: Path) -> str:
    """SHA-256 of a single file's bytes (skin manifest as a quick proxy)."""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _snapshot_skin(skin: Path) -> dict[str, str]:
    """Map every file inside the skin to its mtime+size signature."""
    sig: dict[str, str] = {}
    if skin.is_dir():
        for f in skin.rglob("*"):
            if f.is_file():
                st = f.stat()
                sig[str(f)] = f"{st.st_size}:{st.st_mtime_ns}"
    elif skin.is_file():
        st = skin.stat()
        sig[str(skin)] = f"{st.st_size}:{st.st_mtime_ns}"
    return sig


def _dev_watch(skin_path: str, socket_path: str, *, poll_hz: float = 4.0) -> int:
    """Watch `skin_path` (a `.esk` directory or file). On any file-mtime
    change, send a `SkinChanged` message to the running app over UDS."""
    from elysium._native import _native as _n  # type: ignore[attr-defined]

    skin = Path(skin_path).resolve()
    if not skin.exists():
        print(f"elysium dev: skin not found: {skin}", file=sys.stderr)
        return 2

    print(f"elysium dev: watching {skin}")
    print(f"elysium dev: socket   {socket_path}")
    print("elysium dev: press Ctrl-C to stop.")

    try:
        client = _n.IpcClient(socket_path)
    except Exception as e:
        print(f"elysium dev: cannot connect to app at {socket_path}: {e}",
              file=sys.stderr)
        print("elysium dev: start your app with `enable_hot_reload=True` first.",
              file=sys.stderr)
        return 3

    last = _snapshot_skin(skin)
    period = 1.0 / poll_hz
    try:
        while True:
            time.sleep(period)
            now = _snapshot_skin(skin)
            if now != last:
                # Compute a manifest hash for traceability.
                try:
                    manifest = skin / "manifest.json"
                    h = _hash_path(manifest) if manifest.is_file() else "dirty"
                except FileNotFoundError:
                    h = "missing"
                ok = client.send_skin_changed(str(skin), h)
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] skin-changed → ack={ok}")
                last = now
    except KeyboardInterrupt:
        print("\nelysium dev: stopped.")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elysium")
    sub = parser.add_subparsers(dest="cmd", required=False)

    dev = sub.add_parser("dev", help="Watch a skin and push hot-reloads to the running app.")
    dev.add_argument("skin", help="Path to the .esk directory (or file).")
    dev.add_argument("--socket", default=None,
                     help="UDS path the app is listening on. "
                          "Defaults to ~/.elysium/sessions/elysium-default.sock")
    dev.add_argument("--poll-hz", type=float, default=4.0)

    sub.add_parser("doctor", help="Diagnose installation")

    ae = sub.add_parser("aether", help="Aether AI agent operations.")
    ae.add_argument("action", choices=[
        "chat", "tools", "feedback", "snapshots", "share-feedback",
        # External-bridge surface — talks to the live Designer's HTTP
        # bridge. Lets the agent (or a human shell session) drive the
        # GUI without an LLM in the loop.
        "call", "snapshot", "state", "logs", "watch", "health",
        "pause", "resume", "stop", "status", "pace", "send",
    ])
    ae.add_argument("--message", "-m", default=None,
                    help="chat: prompt text. call: tool name (with --args).")
    ae.add_argument("--args", default="{}",
                    help="JSON object of tool arguments for `call`.")
    ae.add_argument("--out",  default=None,
                    help="snapshot: file to write the PNG to (default stdout).")
    ae.add_argument("--skin",  default=None,
                    help="Skin directory to bind the session to.")
    ae.add_argument("--provider", default=None,
                    help="LLM provider: anthropic[:model] | ollama[:model] | stub")
    ae.add_argument("--bridge", default="http://127.0.0.1:8183",
                    help="Aether bridge URL (default: localhost:8183).")
    ae.add_argument("--repo", default="elysiumui/elysium")
    ae.add_argument("--apply", action="store_true",
                    help="share-feedback: actually open issues (default dry-run).")

    skins = sub.add_parser("skins", help="Marketplace operations")
    skins.add_argument("action", choices=["add", "list", "migrate", "publish",
                                          "search", "init", "info"])
    skins.add_argument("name", nargs="?")

    pk = sub.add_parser("pack",
                        help="Build a one-click distributable for this platform.")
    pk.add_argument("entry", help="Path to the Python entry script.")
    pk.add_argument("--name",       default=None)
    pk.add_argument("--version",    default="0.1.0")
    pk.add_argument("--identifier", default="dev.elysium.app")
    pk.add_argument("--icon",       default=None)
    pk.add_argument("--output",     default="dist")
    pk.add_argument("--target",     default="auto",
                    choices=["auto", "macos", "windows", "linux"])
    pk.add_argument("--python",     default="3.11")
    pk.add_argument("--no-python",  action="store_true",
                    help="Do not embed an interpreter; use the system python.")
    pk.add_argument("--sign-identity", default=None,
                    help="Developer ID (macOS) or signtool subject (Windows).")
    pk.add_argument("--notarize", action="store_true",
                    help="macOS only — submit to Apple notary + staple.")
    pk.add_argument("--data", action="append", default=[],
                    help="Extra data file/dir to copy. Repeatable.")
    pk.add_argument("--module", action="append", default=[],
                    help="Extra Python module to force-include. Repeatable.")
    pk.add_argument("--console", action="store_true",
                    help="macOS: keep a Dock icon / show in cmd-tab. "
                         "Windows: keep an attached console window.")
    pk.add_argument("--min-macos", default="11.0")
    pk.add_argument("--update-feed-url", default=None,
                    help="Public URL of the appcast — emits update sidecars.")
    pk.add_argument("--update-sign-key", default=None,
                    help="Hex-encoded ed25519 seed for signing the artifact.")
    pk.add_argument("--update-base-url", default=None,
                    help="URL prefix where the artifact will be hosted.")

    args = parser.parse_args(argv)

    if args.cmd == "doctor":
        from elysium import __version__
        print(f"Elysium {__version__}")
        try:
            from elysium._native import _native as _n  # noqa: F401
            print("native module:    ok")
        except Exception as e:
            print(f"native module:    MISSING ({e})")
            return 1
        return 0

    if args.cmd == "dev":
        sock = args.socket
        if sock is None:
            home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
            sock = str(Path(home) / ".elysium" / "sessions" / "elysium-default.sock")
        return _dev_watch(args.skin, sock, poll_hz=args.poll_hz)

    if args.cmd == "pack":
        from elysium.pack import pack
        name = args.name or Path(args.entry).stem.replace("_", " ").title()
        out = pack(
            entry=args.entry,
            name=name,
            version=args.version,
            identifier=args.identifier,
            icon=Path(args.icon) if args.icon else None,
            output_dir=Path(args.output),
            target=args.target,
            embed_python=not args.no_python,
            python_version=args.python,
            sign_identity=args.sign_identity,
            notarize=args.notarize,
            extra_data=[Path(x) for x in args.data],
            extra_modules=list(args.module),
            console=args.console,
            min_macos=args.min_macos,
            update_feed_url=args.update_feed_url,
            update_sign_key=args.update_sign_key,
            update_base_url=args.update_base_url,
        )
        print(f"{out}")
        return 0

    if args.cmd == "skins":
        from elysium import marketplace
        return marketplace.cli(args.action, args.name)

    if args.cmd == "aether":
        return _aether_cli(args)

    parser.print_help()
    return 0


def _aether_cli(args) -> int:
    from elysium import aether
    # --- Bridge (talks to a running Designer's HTTP server) ----------
    if args.action in ("call", "snapshot", "state", "logs", "watch", "health",
                        "pause", "resume", "stop", "status", "pace", "send"):
        return _aether_bridge_cli(args)

    if args.action == "tools":
        for t in aether.REGISTRY.all():
            print(f"{t.name:30s} {t.side_effect.value:11s} {t.description[:60]}")
        return 0
    if args.action == "feedback":
        items = aether.feedback.list_pending()
        for it in items:
            print(f"[{it.get('severity','?'):11s}] {it.get('name'):40s} "
                  f"{it.get('summary','')[:80]}")
        return 0
    if args.action == "share-feedback":
        n = aether.feedback.share_via_github(args.repo, dry_run=not args.apply)
        print(f"{'opened' if args.apply else 'would open'} {n} issue(s)")
        return 0
    if args.action == "snapshots":
        if not args.skin:
            print("usage: elysium aether snapshots --skin <path>",
                  file=sys.stderr); return 1
        # No session = list every session's snapshots under aether/.
        import json
        from pathlib import Path
        base = Path.home() / ".elysium" / "aether" / "sessions"
        for sess in sorted(base.glob("*/snapshots/index.json")):
            print(f"== {sess.parent.parent.name} ==")
            for s in json.loads(sess.read_text()):
                print(f"  {s['id']}  {s['action']}")
        return 0
    if args.action == "chat":
        return _aether_chat_repl(args)
    return 1


def _aether_chat_repl(args) -> int:
    """Stand-alone REPL — opens the Designer headlessly and lets the
    user converse with Aether. Useful for scripted sessions + CI."""
    import asyncio
    from pathlib import Path
    from elysium import aether
    if not args.skin:
        print("usage: elysium aether chat --skin <path>", file=sys.stderr)
        return 1
    # We don't spin up the GUI Designer for the REPL — instead, build a
    # headless surrogate that satisfies the Session's contract.
    from elysium.aether._headless import HeadlessDesigner, MODELS
    designer = HeadlessDesigner.from_skin(Path(args.skin))
    session  = aether.Session(designer=designer, designer_models=MODELS)
    daemon   = aether.Daemon(session, provider=args.provider)

    async def go() -> None:
        if args.message:
            await _drive_one(daemon, args.message)
            return
        # Interactive REPL.
        print("aether REPL — Ctrl-D to exit")
        while True:
            try: line = input("you> ")
            except EOFError: break
            if not line.strip(): continue
            await _drive_one(daemon, line)

    asyncio.run(go())
    return 0


async def _drive_one(daemon, user_text: str) -> None:
    q = daemon.subscribe()
    task = __import__("asyncio").create_task(daemon.turn(user_text))
    try:
        while True:
            ev = await __import__("asyncio").wait_for(q.get(), timeout=0.5)
            _print_event(ev)
            if ev.kind == "done": break
            if ev.kind == "error": break
    except __import__("asyncio").TimeoutError:
        if task.done(): return
    finally:
        daemon.unsubscribe(q)
        if not task.done():
            try: await task
            except Exception: pass


def _print_event(ev) -> None:
    if ev.kind == "text":         print(ev.payload["text"], end="", flush=True)
    elif ev.kind == "thinking":   print(f"\n🧠 {ev.payload['text']}", flush=True)
    elif ev.kind == "tool_call":  print(f"\n🔧 {ev.payload['name']}"
                                         f"({_short_args(ev.payload['args'])})",
                                         flush=True)
    elif ev.kind == "tool_result":
        ok = ev.payload.get("ok")
        print(f"   {'✓' if ok else '✗'} "
              f"{(ev.payload.get('value') or ev.payload.get('error'))!r:.80}",
              flush=True)
    elif ev.kind == "done":       print("\n— done —", flush=True)
    elif ev.kind == "error":      print(f"\n[err] {ev.payload}", flush=True)


def _short_args(d):
    import json
    s = json.dumps(d, default=str)
    return s if len(s) < 100 else s[:97] + "…"


if __name__ == "__main__":
    sys.exit(main())


def _aether_bridge_cli(args) -> int:
    """Talk to the running Designer's Aether HTTP bridge."""
    import json, sys, urllib.request, urllib.error

    base = args.bridge.rstrip("/")

    # Memo so we only banner-print a control-state transition once.
    _last_seen = {"paused": False, "stopped": False,
                   "feedback_pending": 0, "last_ts": 0.0}

    def _surface_bridge_state(doc: dict, paused_header: str | None = None,
                                 stopped_header: str | None = None) -> None:
        """Print a loud banner whenever the bridge tells us its control
        state changed since the previous call. This is how the agent
        learns the user paused/stopped without having to poll /status."""
        st = (doc or {}).get("_bridge") if isinstance(doc, dict) else None
        if st is None:
            # Header-only path (binary responses): synthesise a minimal
            # snapshot from the X-Aether-* headers if present.
            if paused_header is None and stopped_header is None: return
            st = {"paused": paused_header == "1",
                   "stopped": stopped_header == "1",
                   "last_action": None, "last_ts": 0.0,
                   "feedback_pending": 0}
        # Print on any transition.
        if (st["paused"] != _last_seen["paused"]
                or st["stopped"] != _last_seen["stopped"]
                or st["feedback_pending"] != _last_seen["feedback_pending"]):
            tag = ("■ STOPPED"  if st["stopped"]
                    else "⏸ PAUSED" if st["paused"]
                    else "▶ RESUMED")
            extra = (f" · feedback_pending={st['feedback_pending']}"
                      if st["feedback_pending"] else "")
            print(f">>> bridge {tag} (user){extra} <<<", file=sys.stderr)
            _last_seen.update({
                "paused": st["paused"], "stopped": st["stopped"],
                "feedback_pending": st["feedback_pending"],
                "last_ts": st["last_ts"],
            })
        # ALWAYS show a one-line reminder when paused/stopped — even
        # without a transition — so successive failed calls don't slip
        # by silently.
        elif st["paused"] or st["stopped"]:
            tag = "■ STOPPED" if st["stopped"] else "⏸ PAUSED"
            print(f">>> bridge still {tag} — POST /resume to continue <<<",
                  file=sys.stderr)

    def _req(path: str, method: str = "GET", body: dict | None = None,
              expect_binary: bool = False):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{base}{path}", data=data,
                                       method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                paused_h  = r.headers.get("X-Aether-Paused")
                stopped_h = r.headers.get("X-Aether-Stopped")
        except urllib.error.HTTPError as e:
            raw = e.read()
            paused_h  = e.headers.get("X-Aether-Paused")  if e.headers else None
            stopped_h = e.headers.get("X-Aether-Stopped") if e.headers else None
            try: doc = json.loads(raw)
            except Exception: doc = {"error": raw.decode(errors="replace")}
            _surface_bridge_state(doc, paused_h, stopped_h)
            print(json.dumps(doc, indent=2), file=sys.stderr)
            return None
        except urllib.error.URLError as e:
            print(f"bridge unreachable at {base}: {e}\n"
                  f"  is the Designer running with ELYSIUM_AETHER_BRIDGE=1?",
                  file=sys.stderr)
            return None
        if expect_binary:
            _surface_bridge_state(None, paused_h, stopped_h)
            return raw
        try:
            doc = json.loads(raw)
            _surface_bridge_state(doc, paused_h, stopped_h)
            return doc
        except Exception:
            _surface_bridge_state(None, paused_h, stopped_h)
            return raw.decode(errors="replace")

    if args.action == "health":
        r = _req("/health");  return 0 if r else 1

    if args.action == "state":
        r = _req("/state")
        if r is None: return 1
        print(json.dumps(r, indent=2)); return 0

    if args.action == "logs":
        r = _req("/logs?n=200")
        if r is None: return 1
        for e in r.get("audit", []):
            ts = e.get("ts", 0)
            tool = e.get("tool", "?")
            ok = "✓" if e.get("ok") else "✗"
            print(f"{ts:.1f}  {ok}  {tool:30s} {str(e.get('value') or e.get('error',''))[:80]}")
        if r.get("menu_status"):
            print(f"# status: {r['menu_status']}")
        return 0

    if args.action == "snapshot":
        raw = _req("/snapshot", expect_binary=True)
        if raw is None: return 1
        if args.out:
            from pathlib import Path
            Path(args.out).write_bytes(raw)
            print(f"wrote {len(raw)} bytes → {args.out}")
        else:
            sys.stdout.buffer.write(raw)
        return 0

    if args.action == "call":
        if not args.message:
            print("usage: elysium aether call -m <tool.name> [--args '{...}']",
                  file=sys.stderr); return 1
        try: tool_args = json.loads(args.args)
        except json.JSONDecodeError as e:
            print(f"--args is not valid JSON: {e}", file=sys.stderr); return 1
        r = _req("/tool", method="POST", body={"name": args.message,
                                                 "args": tool_args})
        if r is None: return 1
        print(json.dumps(r, indent=2))
        return 0 if r.get("ok") else 2

    if args.action in ("pause", "resume", "stop"):
        r = _req(f"/{args.action}", method="POST", body={})
        if r is None: return 1
        print(json.dumps(r, indent=2))
        return 0

    if args.action == "status":
        r = _req("/status")
        if r is None: return 1
        print(json.dumps(r, indent=2))
        return 0

    if args.action == "pace":
        ms = int(args.message or "0")
        r = _req("/pace", method="POST", body={"ms": ms})
        if r is None: return 1
        print(json.dumps(r, indent=2))
        return 0

    if args.action == "send":
        text = args.message or ""
        if not text:
            print("usage: elysium aether send -m '<feedback>'",
                  file=sys.stderr); return 1
        r = _req("/feedback", method="POST", body={"text": text})
        if r is None: return 1
        print(json.dumps(r, indent=2))
        return 0

    if args.action == "watch":
        # SSE — print each event line as it lands.
        try:
            with urllib.request.urlopen(f"{base}/events", timeout=None) as r:
                for line in r:
                    line = line.decode(errors="replace").rstrip()
                    if line.startswith("data: "):
                        try:
                            ev = json.loads(line[6:])
                            kind = ev.get("kind")
                            payload = ev.get("payload", {})
                            if kind == "tool_call":
                                print(f"🔧 {payload.get('name')}({_short_args(payload.get('args'))})")
                                for fb in payload.get("pending_feedback") or []:
                                    print(f"   💬 user: {fb}")
                            elif kind == "tool_result":
                                ok = "✓" if payload.get("ok") else "✗"
                                v = payload.get("value") or payload.get("error")
                                print(f"   {ok} {_short_args(v)}")
                            elif kind == "user_feedback":
                                print(f"\n💬 USER → {payload.get('text')}")
                            elif kind == "control":
                                action = payload.get('action')
                                print(f"\n🎛  {action.upper()} (user)")
                            elif kind == "feedback_observed":
                                for m in payload.get("messages", []):
                                    print(f"   💬 observed: {m}")
                            else:
                                print(f"[{kind}] {payload}")
                        except Exception:
                            print(line)
        except KeyboardInterrupt:
            return 0
        return 0
    return 1
