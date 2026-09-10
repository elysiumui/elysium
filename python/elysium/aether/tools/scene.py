"""Public model-space transforms; independent from canvas coordinates."""

from ...render import scene
from ..types import SideEffect
from . import register_tool

_VECTOR = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}


@register_tool(
    name="scene.transform_set",
    description="Set mesh location in meters, XYZ Euler rotation in degrees, scale or local pivot in Y-up model space.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "transform": {
                "type": "object",
                "additionalProperties": False,
                "properties": {k: _VECTOR for k in scene.DEFAULT},
            },
        },
        "required": ["id", "transform"],
    },
)
def transform_set(session, id, transform):
    return {"placement_id": id, "transform": scene.update(session.lookup(id), transform)}


@register_tool(
    name="scene.transform_get",
    description="Read authored model-space mesh transform and matrix.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
    side_effect=SideEffect.READ,
)
def transform_get(session, id):
    p = session.lookup(id)
    index = next(i for i, candidate in enumerate(session.designer.placements) if candidate is p)
    return {
        "placement_id": session.id_for(p),
        "transform": scene.transform(p),
        "matrix": scene.matrix(p).tolist(),
        "world_matrix": scene.world_matrices(session.designer.placements)[index].tolist(),
        "parent_id": scene.parent_data(p)[0],
    }


@register_tool(
    name="scene.parent_set",
    description="Parent a mesh/group to a stable scene entity, or detach it. Keep-world preserves visible geometry including shear. Cycles are rejected.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "parent_id": {"type": ["string", "null"]},
            "keep_world": {"type": "boolean"},
        },
        "required": ["id", "parent_id"],
    },
)
def parent_set(session, id, parent_id, keep_world=True):
    child = session.lookup(id)
    parent = None if parent_id is None else session.lookup(parent_id)
    return {
        "placement_id": session.id_for(child),
        "parent": scene.set_parent(
            session.designer.placements, child, parent, keep_world=keep_world
        ),
    }


@register_tool(
    name="scene.transform_apply",
    description="Apply local mesh transforms to editable geometry while preserving UVs, normals, pivots and child world positions.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
)
def transform_apply(session, id):
    p = session.lookup(id)
    scene.apply_transform(session.designer.placements, p)
    return {
        "placement_id": session.id_for(p),
        "mesh_key": p.mesh_kind,
        "transform": scene.transform(p),
    }


@register_tool(
    name="scene.group_create",
    description="Create an empty transform group. Children are attached with scene.parent_set.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
)
def group_create(session, name):
    d = session.designer
    p = session.designer_models.Placement(
        kind="SceneGroup", name=name, x=0, y=0, w=0, h=0, props={}
    )
    d.placements.append(p)
    d._select_placement(len(d.placements) - 1)
    return {"placement_id": session.id_for(p), "name": p.name}


@register_tool(
    name="scene.camera_set",
    description="Set the persistent shared scene camera. Angles are radians; orthographic scale is vertical meters. Enables 3D Scene view.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "camera": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target": _VECTOR,
                    "projection": {"enum": ["perspective", "orthographic"]},
                    **{k: {"type": "number"} for k in ("yaw", "pitch", "distance", "ortho_scale")},
                },
            }
        },
        "required": ["camera"],
    },
)
def camera_set(session, camera):
    w = session.designer.window_doc
    w.scene_camera = scene.camera({**w.scene_camera, **camera})
    w.scene_view = True
    return {"camera": w.scene_camera}


@register_tool(
    name="mesh.taper_set",
    description="Set a retained native taper. Start/end XYZ factors apply at minimum/maximum local axis; the axis coordinate is unchanged. Source geometry stays editable.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "taper": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"axis": {"enum": ["x", "y", "z"]}, "start": _VECTOR, "end": _VECTOR},
            },
        },
        "required": ["id", "taper"],
    },
)
def taper_set(session, id, taper):
    from ...render import mesh_edit

    p = session.lookup(id)
    return {"placement_id": session.id_for(p), "taper": mesh_edit.taper_set(p, taper)}


@register_tool(
    name="scene.key_set",
    description="Set or replace a persistent local-transform key at an integer frame (60 fps). Explicit transform values are optional; otherwise capture current pose.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "frame": {"type": "integer", "minimum": 0, "maximum": 360000},
            "transform": {
                "type": "object",
                "additionalProperties": False,
                "properties": {k: _VECTOR for k in scene.DEFAULT},
            },
        },
        "required": ["id", "frame"],
    },
)
def key_set(session, id, frame, transform=None):
    from ...render import scene_animation

    return scene_animation.set_key(session.lookup(id), frame, transform)


@register_tool(
    name="scene.frame_set",
    description="Seek the shared 3D scene to a frame at 60 fps. Evaluates keys and parented objects.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"frame": {"type": "integer", "minimum": 0, "maximum": 360000}},
        "required": ["frame"],
    },
)
def frame_set(session, frame):
    from ...render import scene_animation

    return {"frame": scene_animation.seek(session.designer, frame)}


@register_tool(
    name="mesh.topology_get",
    description="Read durable vertex, edge, polygon and corner identities, UVs and material slots. Legacy triangles are described without mutating the source.",
    input_schema={"type":"object","additionalProperties":False,"properties":{"id":{"type":"string"}},"required":["id"]},
    side_effect=SideEffect.READ,
)
def topology_get(session,id):
    from ...render import mesh_document, topology
    p=session.lookup(id)
    if p.kind!='Mesh3D': raise ValueError('Topology requires a mesh')
    return {'placement_id':id,'topology':topology.document(mesh_document.resolve(p.mesh_kind)),
            'selection':p.props.get('components3d',{})}


@register_tool(
    name="mesh.components_select",
    description="Select persistent vertex, edge or polygon IDs; additive selection toggles the specified IDs.",
    input_schema={"type":"object","additionalProperties":False,"properties":{
        "id":{"type":"string"},"mode":{"enum":["vertices","edges","faces"]},
        "ids":{"type":"array","items":{"type":"string"}},"additive":{"type":"boolean"}},
        "required":["id","mode","ids"]},
)
def components_select(session,id,mode,ids,additive=False):
    from ...render import topology
    return topology.select(session.lookup(id),mode,ids,additive=additive)


@register_tool(
    name="mesh.components_expand",
    description="Expand selected edge seeds into quad edge rings or loops through regular four-edge vertices. Rings cross opposite quad edges. Loops stop at boundaries, poles and non-quad neighborhoods. Preserves mesh geometry and uses persistent component IDs.",
    input_schema={"type":"object","additionalProperties":False,"properties":{
        "id":{"type":"string"},"pattern":{"enum":["loop","ring"]}},"required":["id","pattern"]},
)
def components_expand(session,id,pattern):
    from ...render import topology
    return topology.expand_edge_selection(session.lookup(id),pattern)


@register_tool(
    name="mesh.components_edit",
    description="Extrude a face region along its averaged normal or extrude_individual faces along their own normals, inset individual planar convex faces by positive distance, move components in local meters (radius 0 affects only selection; positive radius uses smooth Euclidean falloff), rotate selected components by rotation XYZ degrees in local-axis X/Y/Z order or scale by three factors about the selected vertex mean (smooth radius weights angles or factor deltas), delete selected components, or fill one planar boundary/wire loop. Add an isolated vertex at position, connect exactly two selected vertices, or extrude_vertices by offset into independent edges. merge_center welds selected vertices at their mean within one named part; collapsed edges/faces are removed, surviving corner UVs and material slots remain, pinched polygons reject. Connect does not split existing faces. Vertex extrusion selects the new endpoints. extrude_edges sweeps boundary/wire chains by offset into quads and selects new parallel edges; branches and interior edges reject. loop_cut takes one selected edge and inserts 1–64 evenly spaced cuts across its connected quad strip, interpolating corner UVs and selecting the new cut edges; non-quad/nonmanifold strips reject. slide_edges moves one connected interior quad edge loop or boundary-to-boundary chain toward its adjacent rail by factor strictly between -1 and 1; positive follows the higher dominant local-axis rail at the geometric seed and corner UVs remain unchanged. bisect requires all faces selected and splits the mesh at plane_point with nonzero plane_normal; keep is both/negative/positive, optional fill closes one simple cut loop on a closed surface when retaining one side. Corners interpolate UVs; disconnected concave face cuts reject. bevel_edges chamfers exactly one edge of a closed convex solid with planar faces by positive offset distance with 1–64 segments and a circular profile; no clamp, offsets reaching neighboring vertices reject. bevel_vertices truncates closed convex three-edge corners by positive distance along incident edges, retaining interpolated face UVs and selecting triangular caps; single segment only, collapsed edges reject. bridge_edges joins two separate boundary/wire loops or chains with equal vertex counts using nearest alignment and consistent winding; no subdivisions/twist/merge, new quads receive unit-square UVs. dissolve_edges joins coplanar faces across selected interior edges, retaining boundary vertices and corner UVs; holes, mixed materials and nonmanifold regions reject. Delete preserves surviving loose geometry; fill creates a material-0 face with planar UVs. Inset rejects collapsed offsets. One atomic mesh revision with stable IDs and corner attributes.",
    input_schema={"type":"object","additionalProperties":False,"properties":{
        "id":{"type":"string"},"operation":{"enum":["extrude","extrude_individual","inset","move","rotate","scale","delete","fill","add_vertex","connect","extrude_vertices","extrude_edges","merge_center","dissolve_edges","loop_cut","slide_edges","bridge_edges","bevel_vertices","bisect","bevel_edges"]},
        "distance":{"type":"number"},"offset":_VECTOR,"position":_VECTOR,"rotation":_VECTOR,"scale":_VECTOR,"radius":{"type":"number","minimum":0},"cuts":{"type":"integer","minimum":1,"maximum":64},"segments":{"type":"integer","minimum":1,"maximum":64},"factor":{"type":"number","exclusiveMinimum":-1,"exclusiveMaximum":1},"plane_point":_VECTOR,"plane_normal":_VECTOR,"keep":{"enum":["both","negative","positive"]},"fill":{"type":"boolean"}},"required":["id","operation"]},
)
def components_edit(session,id,operation,distance=1.0,offset=(0.,0.,0.),position=(0.,0.,0.),radius=0.0,rotation=(0.,0.,0.),scale=(1.,1.,1.),cuts=1,factor=0.0,segments=1,plane_point=(0.,0.,0.),plane_normal=(1.,0.,0.),keep="both",fill=False):
    from ...render import topology
    return topology.edit_selected(session.lookup(id),operation,distance=distance,offset=offset,position=position,radius=radius,rotation=rotation,scale=scale,cuts=cuts,factor=factor,segments=segments,plane_point=plane_point,plane_normal=plane_normal,keep=keep,fill=fill)


@register_tool(
    name='mesh.modifiers_get',
    description='Read the retained modifier stack, unchanged editable source topology and evaluated topology. Generated copies become directly editable only after applying the stack.',
    input_schema={'type':'object','additionalProperties':False,'properties':{'id':{'type':'string'}},'required':['id']},
    side_effect=SideEffect.READ,
)
def modifiers_get(session,id):
    from ...render import mesh_modifiers,mesh_edit,mesh_document,topology
    p=session.lookup(id)
    if p.kind!='Mesh3D': raise ValueError('Modifiers require a mesh')
    return {'stack':mesh_modifiers.settings(p),'source_topology':topology.document(mesh_document.resolve(p.mesh_kind)),'evaluated_topology':topology.document(mesh_edit.evaluate(p))}


@register_tool(
    name='mesh.modifier_add',
    description='Append a retained Mirror, Array, Solidify or Subdivision modifier without changing source geometry. Mirror: axis x/y/z, offset plane coordinate in meters, merge boolean, threshold distance to plane. Array: count 1–64 and absolute local-meter XYZ offset. Solidify: nonzero thickness in meters, offset -1 to 1, rim boolean; simple angle-weighted normals on consistently oriented manifold surfaces, without even-thickness correction or intersection repair. Subdivision: levels 1–4, method catmull-clark or simple, boundary all or keep_corners; discrete levels without limit-surface projection or creases, linear face-varying UV interpolation. Stack order is significant.',
    input_schema={'type':'object','additionalProperties':False,'properties':{'id':{'type':'string'},'kind':{'enum':['Mirror','Array','Solidify','Subdivision']},'parameters':{'type':'object'}},'required':['id','kind']},
)
def modifier_add(session,id,kind,parameters=None):
    from ...render import mesh_modifiers
    return mesh_modifiers.add(session.lookup(id),kind,parameters)


@register_tool(
    name='mesh.modifier_update',
    description='Update retained modifier parameters, enable/bypass it, move it to a zero-based stack index, or remove it. The complete candidate stack is evaluated before one atomic change is published.',
    input_schema={'type':'object','additionalProperties':False,'properties':{'id':{'type':'string'},'modifier_id':{'type':'string'},'parameters':{'type':'object'},'enabled':{'type':'boolean'},'index':{'type':'integer','minimum':0},'remove':{'type':'boolean'}},'required':['id','modifier_id']},
)
def modifier_update(session,id,modifier_id,parameters=None,enabled=None,index=None,remove=False):
    from ...render import mesh_modifiers
    return mesh_modifiers.update(session.lookup(id),modifier_id,values=parameters,enabled=enabled,index=index,remove=remove)


@register_tool(
    name='mesh.modifiers_apply',
    description='Bake the complete enabled modifier stack and existing taper into a new editable source revision, then remove all stack entries. Disabled entries are discarded. One undoable operation; generated components receive durable editable identities.',
    input_schema={'type':'object','additionalProperties':False,'properties':{'id':{'type':'string'}},'required':['id']},
)
def modifiers_apply(session,id):
    from ...render import mesh_modifiers
    return mesh_modifiers.apply_all(session.lookup(id))


_UV_PAIR = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
_UV_IDS = {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True}


@register_tool(
    name="mesh.uv_get",
    description="Read editable face-corner UV identities, coordinates and marked seam edge identities.",
    input_schema={"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}}, "required": ["id"]},
    side_effect=SideEffect.READ,
)
def uv_get(session, id):
    from ...render import mesh_uv
    return mesh_uv.read(session.lookup(id))


@register_tool(
    name="mesh.uv_project",
    description="Project selected source faces (omitted face_ids means all) into independent corner UVs. planar_xy uses +X/+Y, planar_xz +X/-Z, planar_yz -Z/+Y; planar/camera uses yaw/pitch radians. Planar bounds normalize independently to 0..1. Cylindrical and spherical wrap the local Y axis with per-face seam discontinuities. Geometry, custom normals, materials and modifier stack remain unchanged.",
    input_schema={"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}, "mode": {"enum": ["planar", "camera", "planar_xy", "planar_xz", "planar_yz", "cylindrical", "spherical"]}, "face_ids": _UV_IDS, "yaw": {"type": "number"}, "pitch": {"type": "number"}}, "required": ["id", "mode"]},
)
def uv_project(session, id, mode, face_ids=None, yaw=0.0, pitch=0.0):
    from ...render import mesh_uv
    return mesh_uv.project(session.lookup(id), mode, face_ids=face_ids, yaw=yaw, pitch=pitch)


@register_tool(
    name="mesh.uv_transform",
    description="Scale then rotate UV corners around their arithmetic mean, then translate. Omitted corner_ids means all; positive angle is clockwise degrees (Blender UV convention), offset and scale are UV pairs. Each selected corner must have UVs. Negative scale mirrors the selected UVs. One atomic owned mesh revision.",
    input_schema={"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}, "corner_ids": _UV_IDS, "offset": _UV_PAIR, "scale": _UV_PAIR, "angle": {"type": "number"}}, "required": ["id"]},
)
def uv_transform(session, id, corner_ids=None, offset=(0., 0.), scale=(1., 1.), angle=0.):
    from ...render import mesh_uv
    return mesh_uv.transform(session.lookup(id), corner_ids, offset=offset, scale=scale, angle=angle)


@register_tool(
    name="mesh.uv_seams_set",
    description="Mark or clear seams on specified editable source edge identities. Does not unwrap or move UVs.",
    input_schema={"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}, "edge_ids": _UV_IDS, "enabled": {"type": "boolean"}}, "required": ["id", "edge_ids"]},
)
def uv_seams_set(session, id, edge_ids, enabled=True):
    from ...render import mesh_uv
    return mesh_uv.seams(session.lookup(id), edge_ids, enabled)
