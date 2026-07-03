"""agent.*: introspection + capability-gap reporting."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="agent.search_docs",
    description="Substring-search the framework's docs (under docs/).",
    input_schema={"type": "object",
                   "properties": {"query": {"type": "string"}},
                   "required": ["query"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def agent_search_docs(query: str) -> dict:
    from pathlib import Path
    root = Path(__file__).resolve().parents[4] / "docs"
    if not root.is_dir(): return {"hits": []}
    q = query.lower()
    hits = []
    for md in root.rglob("*.md"):
        try:
            for i, line in enumerate(md.read_text().splitlines()):
                if q in line.lower():
                    hits.append({"file": str(md.relative_to(root)),
                                  "line": i + 1, "text": line.strip()[:200]})
                    if len(hits) >= 50: break
        except Exception:
            pass
        if len(hits) >= 50: break
    return {"hits": hits}


@register_tool(
    name="agent.list_components",
    description="Return every Elysium component class shipped in v1.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def agent_list_components() -> dict:
    from elysium import components
    return {"components": [n for n in dir(components)
                            if n[0].isupper() and not n.startswith("_")]}


@register_tool(
    name="agent.list_studios",
    description="Return every lighting studio preset.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def agent_list_studios() -> dict:
    from elysium.render import pbr
    return {"studios": list(pbr.STUDIOS.keys())}


@register_tool(
    name="agent.list_presets",
    description="Return every PBR material preset.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def agent_list_presets() -> dict:
    from elysium.render import pbr
    return {"presets": list(pbr.PRESETS.keys())}


@register_tool(
    name="dev.reload_module",
    description="Hot-reload a Python module by dotted name (e.g. "
                "'elysium.render.pbr', 'elysium.aether.tools.window'). Uses "
                "importlib.reload: fresh calls hit the new code. Tools "
                "registered via @register_tool re-register on reload. Module-"
                "level state (caches, registries that aren't decorator-driven) "
                "is recreated, so caller may also want a follow-up cache flush. "
                "Does NOT reload elysium-designer/__main__.py: the running "
                "Designer instance retains its old class methods; for those "
                "changes, use `dev.reload_designer_module` (which monkey-"
                "patches the Designer class onto the live instance) or "
                "restart.",
    input_schema={"type": "object",
                   "properties": {"module": {"type": "string"}},
                   "required": ["module"]},
)
def dev_reload_module(module: str) -> dict:
    """Aggressive hot-reload: remove every tool currently registered from
    the target module's namespace, then re-import. Decorators re-run and
    register fresh Tool objects with the new function references. This
    avoids the case where the @register_tool decorator's overwrite path
    silently fails to replace tool.fn for callers that already hold a
    reference to the Tool."""
    import importlib, sys
    from . import REGISTRY
    if module not in sys.modules:
        importlib.import_module(module)
    m = sys.modules[module]
    # Snapshot which tools came from this module so we can purge + re-register.
    purged = []
    for name in list(REGISTRY._tools.keys()):
        fn = REGISTRY._tools[name].fn
        if getattr(fn, "__module__", None) == module:
            del REGISTRY._tools[name]
            purged.append(name)
    importlib.reload(m)
    return {"reloaded": module, "id": id(m), "purged": purged,
            "tools_now": sorted(REGISTRY._tools.keys())[:5] + ["..."]}


@register_tool(
    name="dev.designer_module_info",
    description="Diagnostic: report what sys.modules key the running "
                "Designer's class lives under, plus a sample of candidate "
                "module names from sys.modules.",
    input_schema={"type": "object", "properties": {}},
)
def dev_designer_module_info(session) -> dict:
    import sys
    cls = type(session.designer)
    keys = [k for k in sys.modules
            if "elysium" in k.lower() or "designer" in k.lower() or k == "__main__"]
    return {"cls_module": cls.__module__,
            "cls_qualname": cls.__qualname__,
            "in_sys_modules": cls.__module__ in sys.modules,
            "candidate_keys_in_sys_modules": sorted(keys)}


@register_tool(
    name="dev.dump_placement_attrs",
    description="Diagnostic: dump raw attribute values + presence on a "
                "placement instance, so we can tell whether a hot-reload "
                "field addition actually took effect on the live instance.",
    input_schema={"type": "object",
                   "properties": {"id":   {"type": "string"},
                                   "keys": {"type": "array",
                                             "items": {"type": "string"}}},
                   "required": ["id"]},
)
def dev_dump_placement_attrs(session, id: str,
                              keys: list[str] | None = None) -> dict:
    p = session.lookup(id)
    if not keys:
        keys = ["mesh_roll", "mesh_flip_y", "mesh_dist",
                "mesh_part_textures", "mesh_yaw", "mesh_pitch"]
    out = {}
    for k in keys:
        out[k] = {
            "has_attr": hasattr(p, k),
            "value":    repr(getattr(p, k, "<missing>"))[:120],
            "cls_default": repr(getattr(type(p), k, "<no-class-default>"))[:80],
        }
    # Also report the to_json source line range from the live class.
    import inspect
    try:
        out["__to_json_source_lines"] = inspect.getsourcelines(type(p).to_json)[1]
        # And the actual code constants: to see if it contains our marker
        co = type(p).to_json.__code__
        consts_with_str = [c for c in co.co_consts if isinstance(c, str)]
        out["__to_json_str_consts"] = consts_with_str[:20]
        out["__to_json_filename"] = co.co_filename
    except Exception as e:
        out["__to_json_error"] = str(e)
    # Also test direct invocation
    try:
        live = type(p).to_json(p)
        out["__live_to_json_keys"] = sorted(live.get("mesh", {}).keys())
    except Exception as e:
        out["__live_to_json_error"] = str(e)
    return out


@register_tool(
    name="dev.dump_tool",
    description="Dump runtime info about a registered tool: module, code "
                "object id, function id, and a few co_consts strings: so "
                "callers can verify hot-reload actually replaced the "
                "function reference.",
    input_schema={"type": "object",
                   "properties": {"name": {"type": "string"}},
                   "required": ["name"]},
)
def dev_dump_tool(name: str) -> dict:
    from . import REGISTRY
    tool = REGISTRY._tools.get(name)
    if tool is None:
        return {"found": False}
    fn = tool.fn
    consts = [c for c in fn.__code__.co_consts
              if isinstance(c, str) and len(c) > 4][:6]
    return {
        "found": True,
        "fn_module": getattr(fn, "__module__", None),
        "fn_name":   getattr(fn, "__name__", None),
        "fn_id":     id(fn),
        "code_id":   id(fn.__code__),
        "code_consts_sample": consts,
    }


@register_tool(
    name="dev.reload_designer_module",
    description="Hot-reload the running Designer's __main__ module and "
                "monkey-patch every non-dunder method/function from the "
                "fresh module onto the live Designer instance + class, so "
                "subsequent calls execute the new code without a restart. "
                "Returns the number of attributes patched. Existing in-"
                "flight state (placements, selection, animation clock) is "
                "preserved.",
    input_schema={"type": "object", "properties": {}},
)
def dev_reload_designer_module(session) -> dict:
    import importlib, sys
    # When the Designer is run via `python -m elysium-designer`, its
    # module sits in sys.modules under '__main__', but the module's spec
    # name (used by importlib.reload internally) is the package-qualified
    # 'elysium-designer.__main__' which IS NOT a sys.modules key: so
    # importlib.reload fails with "module ... not in sys.modules".
    # Work around that by mirroring the module under its spec name so
    # reload's lookup succeeds.
    designer = session.designer
    cls = type(designer)
    candidates = [cls.__module__, "__main__",
                  "elysium-designer.__main__", "elysium_designer.__main__"]
    m = None
    for c in candidates:
        if c in sys.modules:
            m = sys.modules[c]
            break
    if m is None:
        raise ImportError(
            f"could not locate Designer module; tried {candidates} "
            f"(class __module__={cls.__module__})")
    # Mirror under the spec name if it isn't there yet.
    spec_name = getattr(getattr(m, "__spec__", None), "name", None) or m.__name__
    if spec_name not in sys.modules:
        sys.modules[spec_name] = m
    # Snapshot every class object the OLD module currently exposes: these
    # are the live classes that existing instances reference. Methods on
    # these need to be replaced in place once the reload runs.
    import inspect as _inspect
    old_classes: dict[str, type] = {}
    for cls_name, c in _inspect.getmembers(m, _inspect.isclass):
        old_classes[cls_name] = c
    importlib.reload(m)
    # Walk the just-reloaded module's classes; patch each old class's
    # methods with the new module's versions so Designer, Placement,
    # AnimState, AppWindow etc. all pick up to_json / from_json /
    # method changes without a restart.
    patched = 0
    classes_touched = []
    new_by_old: dict[type, type] = {}
    for cls_name, new_cls in _inspect.getmembers(m, _inspect.isclass):
        old_cls = old_classes.get(cls_name)
        if old_cls is None or old_cls is new_cls:
            continue
        for attr in dir(new_cls):
            if attr.startswith("__") and attr.endswith("__"):
                continue
            new_val = getattr(new_cls, attr, None)
            if not callable(new_val):
                continue
            # IMPORTANT: also overwrite the OLD function's __code__ in
            # place, so any pre-captured references (e.g. bound methods
            # passed to the animation thread at startup) start executing
            # the NEW bytecode. Without this, `anim.run_animation_thread`
            # keeps calling the original on_frame forever.
            try:
                old_val = getattr(old_cls, attr, None)
                if (old_val is not None and old_val is not new_val
                        and hasattr(old_val, "__code__")
                        and hasattr(new_val, "__code__")):
                    try:
                        old_val.__code__ = new_val.__code__
                        if hasattr(old_val, "__defaults__"):
                            old_val.__defaults__ = getattr(new_val, "__defaults__", None)
                        if hasattr(old_val, "__kwdefaults__"):
                            old_val.__kwdefaults__ = getattr(new_val, "__kwdefaults__", None)
                    except (TypeError, AttributeError):
                        pass
                setattr(old_cls, attr, new_val)
                patched += 1
            except (TypeError, AttributeError):
                pass
        classes_touched.append(cls_name)
        new_by_old[old_cls] = new_cls
    # Reassign __class__ on every live instance by NAME match: handles
    # multi-reload scenarios where the instance's type is an even-older
    # class object that isn't in our just-captured `old_classes` snapshot.
    new_by_name = {cls_name: new_cls
                   for cls_name, new_cls in _inspect.getmembers(m, _inspect.isclass)}
    reassigned = 0
    visited: set[int] = set()
    def _swap(o):
        nonlocal reassigned
        if o is None or id(o) in visited: return
        visited.add(id(o))
        new_cls = new_by_name.get(type(o).__name__)
        if new_cls is not None and type(o) is not new_cls:
            try:
                o.__class__ = new_cls
                reassigned += 1
            except TypeError:
                pass
    designer = session.designer
    _swap(designer)
    for p in getattr(designer, "placements", []):
        _swap(p)
        for s in getattr(p, "states", []):
            _swap(s)
    _swap(getattr(designer, "window_doc", None))
    # IMPORTANT: `Designer.run()` passes `self.on_frame` (a bound method)
    # to the animation thread at startup. The bound method's __func__ is
    # the ORIGINAL on_frame function from before any reload: class-attr
    # reassignment doesn't update it. Patch every live function object
    # whose qualname matches a fresh Designer method, by overwriting its
    # __code__ in place. This way pre-captured bound methods immediately
    # start running the new bytecode.
    import gc, types
    fresh_funcs: dict[str, types.FunctionType] = {}
    for cls_name, new_cls in _inspect.getmembers(m, _inspect.isclass):
        for attr in dir(new_cls):
            if attr.startswith("__") and attr.endswith("__"): continue
            v = getattr(new_cls, attr, None)
            if isinstance(v, types.FunctionType):
                fresh_funcs[f"{cls_name}.{attr}"] = v
    code_swapped = 0
    swap_log: list[str] = []
    for obj in gc.get_objects():
        if not isinstance(obj, types.FunctionType): continue
        qn = getattr(obj, "__qualname__", "")
        new_fn = fresh_funcs.get(qn)
        if new_fn is None or new_fn is obj: continue
        try:
            obj.__code__ = new_fn.__code__
            obj.__defaults__ = getattr(new_fn, "__defaults__", None)
            obj.__kwdefaults__ = getattr(new_fn, "__kwdefaults__", None)
            code_swapped += 1
            if len(swap_log) < 20: swap_log.append(qn)
        except (TypeError, AttributeError):
            pass
    return {"reloaded": spec_name, "patched": patched,
            "classes_touched": classes_touched,
            "instances_reassigned": reassigned,
            "code_swapped": code_swapped,
            "code_swap_sample": swap_log,
            "designer_module": cls.__module__}


@register_tool(
    name="dev.eval",
    description="Diagnostic-only: eval a Python expression in a context "
                "with `session`, `designer`, `pbr` and `dp` (designer_"
                "preview) pre-bound. Returns repr(result) trimmed.",
    input_schema={"type": "object",
                   "properties": {"code": {"type": "string"}},
                   "required": ["code"]},
)
def dev_eval(session, code: str) -> dict:
    from elysium.render import pbr
    from elysium.render import designer_preview as dp
    ctx = {"session": session, "designer": session.designer,
           "pbr": pbr, "dp": dp}
    try:
        val = eval(code, {"__builtins__": __builtins__}, ctx)
        return {"value": repr(val)[:4000]}
    except SyntaxError:
        try:
            exec(code, {"__builtins__": __builtins__}, ctx)
            return {"value": "<exec ok>", "locals_keys": sorted(ctx.keys())}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@register_tool(
    name="dev.thread_dump",
    description="Capture a quick snapshot of every Python thread's current "
                "stack so we can see if the render thread is blocked.",
    input_schema={"type": "object", "properties": {}},
)
def dev_thread_dump() -> dict:
    import sys, traceback
    frames = sys._current_frames()
    out = {}
    for tid, frame in frames.items():
        stack = traceback.format_stack(frame, limit=10)
        out[str(tid)] = [s.strip().split("\n")[0] for s in stack]
    return out


@register_tool(
    name="dev.probe_designer",
    description="Quick liveness probe: returns selected attributes/methods "
                "on the live Designer class so callers can verify a hot-"
                "reload actually patched what they expect.",
    input_schema={"type": "object",
                   "properties": {"names": {"type": "array",
                                              "items": {"type": "string"}}}},
)
def dev_probe_designer(session, names: list[str] | None = None) -> dict:
    cls = type(session.designer)
    import sys, inspect
    mod = sys.modules.get(cls.__module__)
    names = names or ["_paint_brush_palette", "_brush_palette_click",
                       "_commit_eyedrop", "_paint_toolbox"]
    out: dict = {}
    for n in names:
        fn = getattr(cls, n, None)
        if fn is None:
            out[n] = None
        else:
            try:
                co = fn.__code__
                out[n] = {"file": co.co_filename, "line": co.co_firstlineno,
                            "calls_brush_palette": any(
                                isinstance(c, str) and "brush_palette" in c
                                for c in co.co_consts)}
            except Exception as e:
                out[n] = f"err:{e}"
    tools = getattr(mod, "TOOLS", None)
    out["TOOLS_kinds"] = ([t.tool for t in tools] if tools else None)
    out["brush_texture_attr"] = hasattr(session.designer, "brush_texture")
    out["brush_palette_rects_attr"] = hasattr(session.designer,
                                                "_brush_palette_rects")
    out["_toolbox_paint_count"] = getattr(session.designer,
                                            "_toolbox_paint_count", -1)
    out["live_menu_status"] = getattr(session.designer, "menu_status", None)
    out["playing"] = getattr(session.designer, "playing", None)
    out["play_clock"] = getattr(session.designer, "_play_clock", None)
    # First-placement runtime state.
    pls = getattr(session.designer, "placements", [])
    if pls:
        p = pls[0]
        out["p0_current_state"] = getattr(p, "current_state", None)
        out["p0_cycle_states"] = getattr(p, "cycle_states", None)
        out["p0_t_dx"] = getattr(p, "_t_dx", None)
        out["p0_t_dy"] = getattr(p, "_t_dy", None)
        out["p0_t_opacity"] = getattr(p, "_t_opacity", None)
        out["p0_mesh_flap"] = getattr(p, "mesh_flap", None)
        out["p0_states"] = [(s.name, s.dx, s.dy, s.duration) for s in p.states]
    try:
        co = type(session.designer)._mesh_render_bytes.__code__
        out["_mrb_calls_flap"] = "_flap_imported_wings" in co.co_names
    except Exception as e:
        out["_mrb_err"] = str(e)
    out["instance_cls_id"] = id(type(session.designer))
    mod_cls = getattr(mod, "Designer", None) if mod else None
    out["module_cls_id"] = id(mod_cls) if mod_cls else None
    out["instance_is_module_cls"] = (type(session.designer) is mod_cls)
    out["live_paint_toolbox_id"] = id(getattr(type(session.designer),
                                                "_paint_toolbox", None))
    out["module_paint_toolbox_id"] = (id(getattr(mod_cls, "_paint_toolbox", None))
                                        if mod_cls else None)
    for n in ("preview_mode", "preview_active", "aether_open",
              "_anim_clock_t", "tool", "_last_persist_t",
              "canvas_pan_x", "canvas_pan_y", "_pan_drag_start",
              "_space_held", "canvas_zoom", "_pan_event_count",
              "_pan_press_count", "_pan_drag_count"):
        out[f"a__{n}"] = getattr(session.designer, n, "<missing>")
    # Pull live source of _paint_toolbox to see if it actually calls
    # _paint_brush_palette (the constant-name check above is fragile -
    # method calls show up in co_names, not co_consts).
    try:
        fn = getattr(cls, "_paint_toolbox")
        co = fn.__code__
        out["_paint_toolbox_co_names"] = list(co.co_names)
        out["_paint_toolbox_source_tail"] = inspect.getsource(fn).splitlines()[-6:]
    except Exception as e:
        out["_paint_toolbox_inspect_err"] = str(e)
    # Pan-handler probe: confirm the live class has the new code.
    try:
        d = session.designer
        out["pan_tool_eq_hand"] = (getattr(d, "tool", None) == "hand")
        out["pan_x"] = getattr(d, "canvas_pan_x", "<missing>")
        out["pan_y"] = getattr(d, "canvas_pan_y", "<missing>")
        out["pan_active"] = getattr(d, "_pan_active", "<missing>")
        out["pan_events"] = getattr(d, "_pan_event_count", "<missing>")
        out["pan_press"] = getattr(d, "_pan_press_count", "<missing>")
        out["pan_drag"] = getattr(d, "_pan_drag_count", "<missing>")
        out["on_frame_calls"] = getattr(d, "_on_frame_calls", "<missing>")
        # Source of the on_frame method: search for our pan marker.
        on_frame_fn = getattr(cls, "on_frame", None) or getattr(cls, "_handle_input", None)
        if on_frame_fn is not None:
            src = inspect.getsource(on_frame_fn)
            out["pan_marker_in_on_frame"] = "Canvas pan: Hand tool" in src
            out["pan_marker_cursor_delta"] = "Cursor-delta pan" in src
        else:
            out["pan_marker_in_on_frame"] = "<no on_frame>"
    except Exception as e:
        out["pan_probe_err"] = str(e)
    return out


@register_tool(
    name="agent.report_capability_gap",
    description="File a framework feature request the agent has just "
                "hit. Persists to ~/.elysium/feedback/<date>.jsonl.",
    input_schema={
        "type": "object",
        "properties": {
            "name":     {"type": "string"},
            "summary":  {"type": "string"},
            "severity": {"type": "string"},  # blocker | enhancement | nit
            "sketch":   {"type": "object"},
        },
        "required": ["name", "summary", "severity"],
    },
)
def agent_report_capability_gap(session, name: str, summary: str,
                                  severity: str,
                                  sketch: dict | None = None) -> dict:
    from ..feedback import report_capability_gap
    entry = report_capability_gap(name=name, summary=summary,
                                    severity=severity,
                                    sketch=sketch or {},
                                    session_id=session.id)
    return {"filed": True, "path": str(entry)}
