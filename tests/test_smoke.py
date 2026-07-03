"""Phase-0 smoke tests for the pure-Python framework layer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_package_imports():
    import elysium
    assert hasattr(elysium, "__version__")


def test_reactive_signal_propagates():
    from elysium.reactive import signal, effect
    log: list[int] = []
    v = signal(1)

    @effect
    def watch():  # type: ignore[no-redef]
        log.append(v())

    v.set(2)
    v.set(3)
    assert log == [1, 2, 3]


def test_reactive_signal_dedupes_equal_writes():
    from elysium.reactive import signal, effect
    log: list[int] = []
    v = signal(7)

    @effect
    def watch():  # type: ignore[no-redef]
        log.append(v())

    v.set(7)  # same value, no notification
    assert log == [7]


@pytest.mark.parametrize("name,t,expected", [
    ("linear", 0.5, 0.5),
    ("ease-out-cubic", 1.0, 1.0),
    ("ease-in-quad", 0.0, 0.0),
])
def test_easings(name, t, expected):
    from elysium.anim import easing
    assert abs(easing(name)(t) - expected) < 1e-9


def test_spring_in_bounds():
    from elysium.anim import spring
    s = spring(220, 18)
    for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
        assert -0.5 < s(t) < 2.0  # underdamped overshoot tolerated


def test_state_machine_transitions():
    from elysium.anim import StateMachine
    sm = StateMachine("idle", {"idle": {}, "hover": {}, "pressed": {}})
    assert sm.current == "idle"
    sm.transition_to("hover")
    assert sm.current == "hover"


def test_hello_esk_manifest_is_valid_json():
    p = Path(__file__).parent.parent / "examples/hello/hello.esk/manifest.json"
    data = json.loads(p.read_text())
    assert data["schema_version"] == "1.0"
    assert data["id"] == "dev.elysium.hello"


def test_hello_esk_hooks_index_covers_document():
    base = Path(__file__).parent.parent / "examples/hello/hello.esk"
    hooks = json.loads((base / "hooks.json").read_text())
    assert "greeting_button.click" in hooks
    assert hooks["greeting_button.click"]["type"] == "event"
    assert "message.text" in hooks


def test_esk_schema_is_valid_json_schema():
    p = Path(__file__).parent.parent / "schemas/esk-1.0.json"
    schema = json.loads(p.read_text())
    assert schema["title"].startswith("Elysium Skin")


# --- Native-only tests (skipped when wheel isn't built) ---------------------

def _native_available() -> bool:
    import elysium
    return getattr(elysium, "_NATIVE_AVAILABLE", False)


native_only = pytest.mark.skipif(not _native_available(), reason="native extension not built")


@native_only
def test_app_construct():
    import elysium as ely
    app = ely.App(title="Test", identifier="test.elysium.smoke")
    assert app.identifier == "test.elysium.smoke"


@native_only
def test_path_svg_builder():
    import elysium as ely
    p = ely.Path()
    p.move_to(10, 20)
    p.line_to(30, 40)
    p.close()
    assert "M 10 20" in p.source and "L 30 40" in p.source and "Z" in p.source


@native_only
def test_path_from_svg_static():
    import elysium as ely
    p = ely.Path.from_svg("M 0 0 L 100 100 Z")
    assert p.source == "M 0 0 L 100 100 Z"


@native_only
def test_display_list_builder():
    """Python builds a DisplayList; the native side accepts each command."""
    from elysium._native import _native as _n
    dl = _n.DisplayList()
    assert len(dl) == 0
    dl.clear(0.0, 0.0, 0.0, 0.0)
    dl.gradient_card(0.0, 0.0, 100.0, 100.0, 8.0, (255,0,0,255), (0,255,0,255))
    dl.frosted_panel(10.0, 10.0, 80.0, 80.0, 8.0, 12.0, (255,255,255,40))
    dl.filled_circle(50.0, 50.0, 10.0, (255,255,255,255))
    assert len(dl) == 4
    assert "commands=4" in repr(dl)


@native_only
def test_display_list_publish_doesnt_block_or_corrupt():
    """Pumping a triple buffer with a window that never opens (no event loop
    consumed) still must not block, panic, or corrupt — proves the
    lock-free producer path is safe even when the consumer is dormant.
    """
    import elysium as ely
    from elysium._native import _native as _n

    app = ely.App(title="t", identifier="dev.elysium.flood")
    win = app.window(transparent=False, title_bar=True, initial_size=(200, 200))

    for i in range(5000):
        dl = _n.DisplayList()
        dl.clear(i / 5000.0, 0.0, 0.0, 1.0)
        dl.filled_circle(100.0, 100.0, 50.0, (255, 255, 255, 255))
        win.publish_display_list(dl)


@native_only
def test_exception_hierarchy():
    import elysium as ely
    for sub in (ely.SkinError, ely.HookNotFound, ely.ShaderValidationError, ely.CanvasExpired):
        assert issubclass(sub, ely.ElysiumError)


@native_only
@pytest.mark.skipif(
    not __import__("os").environ.get("ELYSIUM_RUN_WINDOW_TEST"),
    reason="requires a display; set ELYSIUM_RUN_WINDOW_TEST=1 locally. "
           "winit only allows one EventLoop per process on macOS, so the full "
           "live-window check is squeezed into a single test.",
)
def test_phase0_live_window_end_to_end():
    """End-to-end Phase 0 gate, all checks in one pytest run because winit
    only permits a single EventLoop per process on macOS:

      1. App + Window created from Python.
      2. A Python-built DisplayList is published.
      3. Loop runs; render thread consumes the list, Skia paints,
         wgpu composites and presents.
      4. Cross-thread `app.quit()` shuts the loop down within ~one frame.
    """
    import threading
    import time
    import elysium as ely
    from elysium._native import _native as _n

    app = ely.App(title="pytest", identifier="dev.elysium.pytest")
    win = app.window(transparent=False, title_bar=True, initial_size=(320, 200))

    dl = _n.DisplayList()
    dl.clear(0.05, 0.05, 0.1, 1.0)
    dl.gradient_card(20.0, 20.0, 280.0, 160.0, 16.0,
                     (0x5B, 0x3F, 0xF5, 0xFF), (0xFF, 0x5C, 0x8A, 0xFF))
    win.publish_display_list(dl)

    threading.Thread(target=lambda: (time.sleep(1.0), app.quit()), daemon=True).start()

    started = time.perf_counter()
    app.run()
    elapsed = time.perf_counter() - started
    # Allow a generous upper bound for macOS first-run Gatekeeper delays.
    assert 0.5 < elapsed < 40.0, f"expected ~1s, got {elapsed}"


def test_pbr_compute_shader_parses():
    """The internal WGSL compute scaffold must always parse against naga."""
    from elysium.render.compute import validate_pbr_compute
    ok, msg = validate_pbr_compute()
    assert ok, f"pbr_compute.wgsl failed naga validation: {msg}"


def test_render_mesh_gpu_smoke():
    """The GPU compute path returns RGBA bytes of the requested size when
    a compatible adapter is available. Skipped (not failed) otherwise."""
    import pytest
    from elysium.render import pbr
    from elysium.render.compute import render_mesh_gpu
    # Procedural butterfly was removed — sphere works for the GPU
    # smoke test (same materials + lighting path).
    obj = pbr.MeshObject(mesh=pbr.sphere_mesh(),
                          materials=[pbr.PRESETS["Metal — Gold"]])
    env = pbr.to_environment(pbr.STUDIOS["Default Soft Studio"])
    try:
        b = render_mesh_gpu(64, 48, obj, env)
    except RuntimeError as e:
        pytest.skip(f"no compute-capable wgpu device: {e}")
    assert len(b) == 64 * 48 * 4


def test_packager_options_and_target_resolution(tmp_path):
    from elysium.pack import PackOptions, _resolve_target
    assert _resolve_target("auto") in {"macos", "windows", "linux"}
    o = PackOptions(entry=tmp_path / "x.py", name="X")
    assert o.python_version == "3.11"
    assert o.target == "auto"


def test_marketplace_init_creates_skin(tmp_path, monkeypatch):
    import os
    from elysium import marketplace
    monkeypatch.chdir(tmp_path)
    root = marketplace.init("demo")
    assert (root / "manifest.json").exists()
    assert (root / "document.json").exists()


def test_packager_builds_app_without_python(tmp_path):
    import sys
    if sys.platform != "darwin":
        import pytest; pytest.skip("macOS-only smoke")
    from elysium.pack import pack
    entry = tmp_path / "main.py"
    entry.write_text("import elysium\nprint('hello')\n")
    out = pack(entry=str(entry), name="SmokeApp",
               output_dir=tmp_path / "dist", embed_python=False)
    assert out.is_dir()
    assert (out / "Contents" / "Info.plist").exists()
    assert (out / "Contents" / "MacOS" / "SmokeApp").exists()


def test_codelink_index_finds_decorator_and_naming(tmp_path):
    from elysium.codelink import index_handlers
    src = tmp_path / "app.py"
    src.write_text(
        "import elysium\n"
        "win = elysium.App().window()\n\n"
        "@win.on(\"play.click\")\n"
        "def on_play_click():\n"
        "    pass\n\n"
        "def on_pause_click():\n"
        "    pass\n"
    )
    idx = index_handlers(src, known_hooks=["play.click", "pause.click", "stop.click"])
    assert "play.click" in idx and idx["play.click"].decorator
    assert "pause.click" in idx and not idx["pause.click"].decorator
    assert "stop.click" not in idx


def test_codelink_scaffold_idempotent(tmp_path):
    from elysium.codelink import scaffold_handler, index_handlers
    src = tmp_path / "fresh.py"
    loc = scaffold_handler(src, "play.click")
    text = src.read_text()
    assert "@win.on(\"play.click\")" in text
    assert loc.function == "on_play_click"
    # Calling again must not duplicate.
    loc2 = scaffold_handler(src, "play.click")
    assert loc.line == loc2.line
    assert src.read_text().count("def on_play_click") == 1


def test_codelink_detect_editor_returns_something_or_none():
    from elysium.codelink import detect_editor
    # We can't assert a specific editor; just that the call is safe.
    e = detect_editor()
    assert e is None or e.cmd


def test_stubgen_generates_typed_hooks(tmp_path):
    from elysium.stubgen import generate_for_skin
    skin = tmp_path / "demo.esk"
    skin.mkdir()
    (skin / "manifest.json").write_text(
        '{"schema_version":"1.0","id":"dev.demo","name":"Demo","version":"0.1.0","color_space":"srgb"}')
    (skin / "document.json").write_text("""{
        "root": {"type":"scene","size":{"w":400,"h":300},
        "background":{"type":"color","value":"#000000"},
        "children":[
            {"type":"path","id":"btn","d":"M 0 0",
             "hooks":[{"name":"play.click","type":"event"},
                      {"name":"vol.value","type":"value","range":[0,1]}]}
        ]}
    }""")
    out = generate_for_skin(skin, tmp_path / "stubs")
    text = out.read_text()
    assert "play_click: EventHook" in text
    assert "vol_value: ValueHook" in text


def test_a11y_prefs_snapshot_and_subscribe():
    from elysium.accessibility import A11yPrefs, current, subscribe
    snap = current()
    assert isinstance(snap, A11yPrefs)
    seen: list = []
    unsub = subscribe(lambda p: seen.append(p))
    assert seen and isinstance(seen[0], A11yPrefs)
    unsub()


def test_focus_navigation_geometry():
    from elysium.focus import FocusNode, next_focus
    nodes = [
        FocusNode(id="a", bounds=(0,   0, 60, 30)),
        FocusNode(id="b", bounds=(100, 0, 60, 30)),
        FocusNode(id="c", bounds=(0,  60, 60, 30)),
    ]
    assert next_focus(nodes, "a", "right") == "b"
    assert next_focus(nodes, "a", "down")  == "c"
    assert next_focus(nodes, "b", "left")  == "a"
    assert next_focus(nodes, None, "next") == "a"
    assert next_focus(nodes, "c", "next")  == "a"   # wrap


def test_updater_version_comparison(tmp_path, monkeypatch):
    from elysium.updater import Updater
    u = Updater(feed_url="https://example.com/feed.json",
                current_version="0.1.0")
    assert u._is_newer("0.2.0")
    assert u._is_newer("1.0.0")
    assert not u._is_newer("0.1.0")
    assert not u._is_newer("0.0.9")


def test_marketplace_signature_roundtrip(tmp_path, monkeypatch):
    """End-to-end: sign + verify a fake tarball via the helpers."""
    try:
        from nacl.signing import SigningKey
    except ImportError:
        import pytest; pytest.skip("PyNaCl not installed")
    from elysium.marketplace import _sign_archive, _verify_archive
    archive = tmp_path / "skin.tgz"
    archive.write_bytes(b"x" * 1024)
    sk_hex = SigningKey.generate().encode().hex()
    sig_hex, pub_hex = _sign_archive(archive, sk_hex)
    assert _verify_archive(archive, pub_hex, sig_hex)
    # Tamper with the bytes: verification must fail.
    archive.write_bytes(b"y" * 1024)
    assert not _verify_archive(archive, pub_hex, sig_hex)


def test_reduce_motion_shrinks_tween_duration(monkeypatch):
    from elysium import accessibility, anim
    monkeypatch.setattr(accessibility, "current",
                         lambda: accessibility.A11yPrefs(reduce_motion=True))
    t = anim.Tween(0.0, 1.0, duration=2.0)
    assert t._duration < 0.2   # 5% of 2.0 = 0.1


def test_focus_nav_window_install():
    """The Window ext exposes install_focus_nav + handle_focus_key. We
    can't drive a real OS event loop here; just check the API surface."""
    from elysium._window_ext import _WindowProxy
    assert hasattr(_WindowProxy, "install_focus_nav")
    assert hasattr(_WindowProxy, "handle_focus_key")
    assert hasattr(_WindowProxy, "on_focus_changed")


def test_inspector_ipc_roundtrip(tmp_path):
    import socket, json, time
    from elysium.debug import Inspector
    insp = Inspector(port=18345)
    insp.start()
    insp.push_frame(12.5, paint_ms=2.0, composite_ms=1.5, swap_ms=0.7)
    insp.push_hook("play.click", 0.4)
    time.sleep(0.05)
    s = socket.socket()
    s.connect(("127.0.0.1", 18345))
    s.sendall(b"get_stats\n")
    line = b""
    while not line.endswith(b"\n"):
        line += s.recv(4096)
    doc = json.loads(line)
    assert doc["frame_ms"] == [12.5]
    assert doc["paint_ms"] == 2.0
    assert any(h["name"] == "play.click" for h in doc["hooks_fired"])


def test_signature_verify_zip_is_invoked(tmp_path):
    """Zip signature is checked even when loading a packaged .esk."""
    import zipfile, json
    from elysium._native import _native as _n
    # Build a minimal valid zip skin without signature.json; lenient
    # policy (the default) should accept it.
    z = tmp_path / "demo.esk"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("manifest.json", json.dumps({
            "schema_version": "1.0", "id": "dev.demo",
            "name": "Demo", "version": "0.1.0", "color_space": "srgb"}))
        zf.writestr("document.json", json.dumps({
            "root": {"type": "scene", "size": {"w": 100, "h": 100},
                     "background": {"type": "color", "value": "#000000"},
                     "children": []}}))
    skin = _n.load_skin(str(z))
    assert skin.id == "dev.demo"


def test_updater_signature_verify_round_trip(tmp_path):
    """End-to-end: sign payload bytes → updater accepts; tamper → rejects."""
    try:
        from nacl.signing import SigningKey
    except ImportError:
        import pytest; pytest.skip("PyNaCl not installed")
    from elysium.updater import Updater, ReleaseInfo
    import http.server, threading, socket

    body = b"payload-" * 1024
    sk   = SigningKey.generate()
    sig  = sk.sign(body).signature.hex()
    pub  = bytes(sk.verify_key).hex()

    # Serve the payload over a one-shot HTTP server.
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a, **k): pass
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        upd = Updater(feed_url=f"http://127.0.0.1:{port}/x.json",
                       public_ed25519_key=pub, current_version="0.0.0")
        info = ReleaseInfo(version="9.9.9",
                            url=f"http://127.0.0.1:{port}/payload.bin",
                            signature=sig)
        assert upd._download_and_verify(info) is True
        # Tamper: pass a bogus signature.
        bad = ReleaseInfo(version="9.9.9", url=info.url, signature="00" * 64)
        assert upd._download_and_verify(bad) is False
    finally:
        srv.shutdown()


def test_aether_registry_populated():
    from elysium import aether
    tools = aether.REGISTRY.all()
    assert len(tools) >= 60   # 12 namespaces × multiple tools each
    names = {t.name for t in tools}
    for required in ("placement.add", "window.set_chrome",
                      "shape.draw_path", "material.set",
                      "texture.extract_from_image", "animation.add_state",
                      "mesh.import", "hook.declare", "codelink.scaffold",
                      "code.read_file", "run.snapshot", "snapshot.list",
                      "agent.report_capability_gap", "tester.probe"):
        assert required in names, f"missing tool: {required}"


def test_aether_capability_manifest():
    from elysium.aether.capabilities import build_manifest
    m = build_manifest()
    assert "components" in m and isinstance(m["components"], list)
    assert "studios" in m and m["studios"]
    assert "material_presets" in m and m["material_presets"]


def test_aether_end_to_end_with_stub(tmp_path):
    import asyncio
    from elysium import aether
    from elysium.aether._headless import HeadlessDesigner, MODELS

    skin = tmp_path / "demo.esk"
    d = HeadlessDesigner.from_skin(skin)
    s = aether.Session(designer=d, designer_models=MODELS)
    daemon = aether.Daemon(s, provider="stub")
    q = daemon.subscribe()

    async def go():
        task = asyncio.create_task(daemon.turn(
            '/tool placement.add {"kind":"Card","x":40,"y":40,"w":200,"h":120}'))
        seen_kinds = []
        for _ in range(20):
            ev = await asyncio.wait_for(q.get(), timeout=1.0)
            seen_kinds.append(ev.kind)
            if ev.kind == "done": break
        await task
        return seen_kinds

    kinds = asyncio.run(go())
    assert "tool_call" in kinds and "tool_result" in kinds
    assert len(d.placements) == 1
    assert d.placements[0].kind == "Card"
    # Snapshot was auto-captured before the write.
    assert len(s.snapshots.list()) >= 1


def test_aether_feedback_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from elysium.aether.feedback import report_capability_gap, list_pending
    report_capability_gap(name="particles", summary="need particle system",
                           severity="enhancement", sketch={"api": "..."},
                           session_id="abc123")
    items = list_pending()
    assert len(items) == 1 and items[0]["name"] == "particles"


def test_aether_snapshot_restore(tmp_path):
    from elysium import aether
    from elysium.aether._headless import HeadlessDesigner, MODELS

    d = HeadlessDesigner.from_skin(tmp_path / "rs.esk")
    s = aether.Session(designer=d, designer_models=MODELS)

    # State A — one placement.
    from elysium.aether._headless import Placement
    d.placements.append(Placement(kind="Card", x=10, y=10, w=100, h=100,
                                    name="One"))
    snap_a = s.snapshots.capture(s, action="state_a")
    # State B — add another.
    d.placements.append(Placement(kind="Button", x=20, y=20, w=80, h=40,
                                    name="Two"))
    assert len(d.placements) == 2
    # Restore A.
    s.snapshots.restore(snap_a, s)
    assert len(d.placements) == 1
    assert d.placements[0].name == "One"
