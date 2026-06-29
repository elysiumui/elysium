"""animation.*: states, keyframes, playhead."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="animation.add_state",
    description="Append an AnimState to a placement.",
    input_schema={
        "type": "object",
        "properties": {
            "id":       {"type": "string"},
            "name":     {"type": "string"},
            "dx":       {"type": "number"},
            "dy":       {"type": "number"},
            "scale":    {"type": "number"},
            "opacity":  {"type": "number"},
            "rotation": {"type": "number"},
            "duration": {"type": "number"},
            "easing":   {"type": "string"},
            "mesh_flap_target": {"type": "number"},
        },
        "required": ["id", "name", "duration"],
    },
)
def animation_add_state(session, id: str, name: str,
                         duration: float, dx: float = 0, dy: float = 0,
                         scale: float = 1.0, opacity: float = 1.0,
                         rotation: float = 0.0,
                         easing: str = "ease_out",
                         mesh_flap_target: float | None = None) -> dict:
    p = session.lookup(id)
    AnimState = session.designer_models.AnimState
    s = AnimState(name=name, dx=float(dx), dy=float(dy),
                   scale=float(scale), opacity=float(opacity),
                   rotation=float(rotation),
                   duration=float(duration), easing=easing)
    if mesh_flap_target is not None and hasattr(s, "mesh_flap_target"):
        s.mesh_flap_target = float(mesh_flap_target)
    p.states.append(s)
    return {"state_index": len(p.states) - 1}


@register_tool(
    name="animation.modify_state",
    description="Patch an existing AnimState by name.",
    input_schema={
        "type": "object",
        "properties": {
            "id":       {"type": "string"},
            "name":     {"type": "string"},
            "dx":       {"type": "number"},
            "dy":       {"type": "number"},
            "scale":    {"type": "number"},
            "opacity":  {"type": "number"},
            "rotation": {"type": "number"},
            "duration": {"type": "number"},
            "easing":   {"type": "string"},
            "mesh_flap_target": {"type": "number"},
        },
        "required": ["id", "name"],
    },
)
def animation_modify_state(session, id: str, name: str, **kwargs) -> dict:
    p = session.lookup(id)
    for st in p.states:
        if st.name == name:
            for k, v in kwargs.items():
                if hasattr(st, k) and v is not None:
                    setattr(st, k, v)
            return {"updated": name}
    raise KeyError(f"no state {name!r} on {id}")


@register_tool(
    name="animation.delete_state",
    description="Remove an AnimState by name.",
    input_schema={"type": "object",
                   "properties": {"id":{"type":"string"},
                                   "name":{"type":"string"}},
                   "required": ["id","name"]},
)
def animation_delete_state(session, id: str, name: str) -> dict:
    p = session.lookup(id)
    p.states = [s for s in p.states if s.name != name]
    return {"removed": name}


@register_tool(
    name="animation.play",
    description="Start the global animation playhead.",
    input_schema={"type": "object", "properties": {}},
)
def animation_play(session) -> dict:
    session.designer.playing = True
    session.designer._play_clock = 0.0
    return {"playing": True}


@register_tool(
    name="animation.set_playhead",
    description="Seek the animation playhead to a wall-clock time.",
    input_schema={"type": "object",
                   "properties": {"t": {"type": "number"}},
                   "required": ["t"]},
)
def animation_set_playhead(session, t: float) -> dict:
    session.designer._play_clock = float(t)
    return {"t": float(t)}


@register_tool(
    name="animation.read",
    description="Dump every AnimState on a placement.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def animation_read(session, id: str) -> dict:
    p = session.lookup(id)
    scenes = [s.to_json() if hasattr(s, "to_json") else s.__dict__
              for s in p.states]
    return {"states": scenes, "scenes": scenes}


# --- Scene-named aliases ---------------------------------------------------
#
# The terminology preferred in the UI is "Scene" (rather than "State").
# These aliases let callers use the new vocabulary without breaking older
# integrations that still call animation.add_state / modify_state / etc.

@register_tool(
    name="animation.add_scene",
    description="Append a Scene (keyframed pose snapshot) to a placement. "
                "Same data model as animation.add_state: alternate name "
                "matching the Designer's UI terminology.",
    input_schema={
        "type": "object",
        "properties": {
            "id":       {"type": "string"},
            "name":     {"type": "string"},
            "dx":       {"type": "number"},
            "dy":       {"type": "number"},
            "scale":    {"type": "number"},
            "opacity":  {"type": "number"},
            "rotation": {"type": "number"},
            "duration": {"type": "number"},
            "easing":   {"type": "string"},
            "mesh_flap_target": {"type": "number"},
        },
        "required": ["id", "name", "duration"],
    },
)
def animation_add_scene(session, id: str, name: str,
                         duration: float, dx: float = 0, dy: float = 0,
                         scale: float = 1.0, opacity: float = 1.0,
                         rotation: float = 0.0,
                         easing: str = "ease_out",
                         mesh_flap_target: float | None = None) -> dict:
    return animation_add_state(session=session, id=id, name=name,
                                 duration=duration, dx=dx, dy=dy,
                                 scale=scale, opacity=opacity,
                                 rotation=rotation, easing=easing,
                                 mesh_flap_target=mesh_flap_target)


@register_tool(
    name="animation.modify_scene",
    description="Patch a Scene by name (alias of animation.modify_state).",
    input_schema={
        "type": "object",
        "properties": {
            "id":       {"type": "string"},
            "name":     {"type": "string"},
            "dx":       {"type": "number"},
            "dy":       {"type": "number"},
            "scale":    {"type": "number"},
            "opacity":  {"type": "number"},
            "rotation": {"type": "number"},
            "duration": {"type": "number"},
            "easing":   {"type": "string"},
            "mesh_flap_target": {"type": "number"},
        },
        "required": ["id", "name"],
    },
)
def animation_modify_scene(session, id: str, name: str, **kwargs) -> dict:
    return animation_modify_state(session=session, id=id, name=name, **kwargs)


@register_tool(
    name="animation.delete_scene",
    description="Remove a Scene by name (alias of animation.delete_state).",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"},
                                   "name": {"type": "string"}},
                   "required": ["id", "name"]},
)
def animation_delete_scene(session, id: str, name: str) -> dict:
    return animation_delete_state(session=session, id=id, name=name)


@register_tool(
    name="animation.set_loop",
    description="Toggle the Designer's animation-loop mode. When True, the "
                "timeline cycles continuously while playing. When False "
                "(the default) the timeline plays once and stops at the "
                "final scene. Drives the same toggle as the toolbar's "
                "↻ Loop button.",
    input_schema={"type": "object",
                   "properties": {"loop": {"type": "boolean"}},
                   "required": ["loop"]},
)
def animation_set_loop(session, loop: bool) -> dict:
    session.designer.play_loop = bool(loop)
    return {"play_loop": session.designer.play_loop}


@register_tool(
    name="animation.read_loop",
    description="Report whether play-loop is on (continuous) or off "
                "(one-shot).",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ, undoable=False,
)
def animation_read_loop(session) -> dict:
    return {"play_loop": bool(getattr(session.designer, "play_loop", False))}
