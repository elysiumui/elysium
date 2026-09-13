from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, mesh_materials, mesh_modifiers, primitives, scene


def fixture():
    p = SimpleNamespace(kind="Mesh3D", props={}, visible=True, name="Cube", entity_id="cube")
    primitives.bind(p, "Cube")
    return p


def source(p):
    return mesh_document.resolve(p.mesh_kind).topology


def front(p):
    d = source(p)
    points = {v["id"]: v["position"] for v in d["vertices"]}
    return next(
        f["id"] for f in d["faces"] if all(points[c["vertex"]][2] > 0 for c in f["corners"])
    )


def test_face_material_reaches_shared_renderer_and_actual_pixels():
    p = fixture()
    before = deepcopy(source(p))
    slot = mesh_materials.add(p, "Red", {"base_color": [1, 0, 0], "roughness": 1, "specular": 0})[
        "slot_id"
    ]
    mesh_materials.assign(p, [front(p)], slot)
    obj, owners = scene.compose([p], materials=True)
    assert len(obj.materials) == 2 and np.count_nonzero(obj.mesh.face_mats == 1) == 2
    assert (owners == 0).all()
    for name in ("vertices", "edges", "next_id"):
        assert source(p)[name] == before[name]
    for old, new in zip(before["faces"], source(p)["faces"]):
        assert {k: v for k, v in old.items() if k != "material"} == {
            k: v for k, v in new.items() if k != "material"
        }
    rgba, _ = scene.render(
        [p],
        48,
        48,
        yaw=0,
        pitch=0,
        projection="orthographic",
        ortho_scale=3,
        grid=False,
        shading="material",
    )
    color = np.frombuffer(rgba, np.uint8).reshape(48, 48, 4)[24, 24, :3].astype(int)
    assert color[0] > color[1] + 50 and color[0] > color[2] + 50
    rgba, _ = scene.render(
        [p],
        48,
        48,
        yaw=0,
        pitch=np.pi / 2,
        projection="orthographic",
        ortho_scale=3,
        grid=False,
        shading="material",
    )
    color = np.frombuffer(rgba, np.uint8).reshape(48, 48, 4)[24, 24, :3].astype(int)
    assert color.max() - color.min() < 20


def test_slot_removal_keeps_stable_assignment_and_offsets_across_objects():
    p = fixture()
    unused = mesh_materials.add(p, "Unused")["slot_id"]
    blue = mesh_materials.add(p, "Blue", {"base_color": [0, 0, 1]})["slot_id"]
    mesh_materials.assign(p, [front(p)], blue)
    before = mesh_materials.read(p)["face_slots"]
    mesh_materials.remove(p, unused)
    assert mesh_materials.read(p)["face_slots"] == before
    assert len(mesh_materials.table(p)["slots"]) == 2
    second = fixture()
    second.entity_id = "second"
    scene.update(second, {"location": [3, 0, 0]})
    obj, owners = scene.compose([p, second], materials=True)
    assert len(obj.materials) == 3
    assert (obj.mesh.face_mats[owners == 1] == 2).all()
    assert mesh_materials.add(p, "Next")["slot_id"] == "m4"


def test_material_assignment_propagates_through_subdivision_and_array():
    p = fixture()
    slot = mesh_materials.add(p, "Red")["slot_id"]
    mesh_materials.assign(p, [front(p)], slot)
    mesh_modifiers.add(p, "Subdivision", {"levels": 1, "method": "simple"})
    mesh_modifiers.add(p, "Array", {"count": 2, "offset": [3, 0, 0]})
    obj, _ = scene.compose([p], materials=True)
    assert np.count_nonzero(obj.mesh.face_mats == 1) == 16
    assert mesh_materials.read(p)["face_slots"][front(p)] == slot


@pytest.mark.parametrize(
    "values",
    [
        {"metallic": True},
        {"roughness": float("nan")},
        {"base_color": [1, 2, 3]},
        {"emissive": [65, 0, 0]},
        {"unrecognized": 1},
        False,
    ],
)
def test_invalid_surface_rejects_without_mutation(values):
    p = fixture()
    before = deepcopy(vars(p))
    with pytest.raises(ValueError):
        mesh_materials.add(p, "Invalid", values)
    assert vars(p) == before


def test_invalid_assignment_and_used_removal_preserve_source_and_slots():
    p = fixture()
    slot = mesh_materials.add(p, "Red")["slot_id"]
    mesh_materials.assign(p, [front(p)], slot)
    before = deepcopy(vars(p))
    document = deepcopy(source(p))
    for ids in ([], ["stale"], [front(p), front(p)], [1], "all"):
        with pytest.raises(ValueError):
            mesh_materials.assign(p, ids, slot)
        assert vars(p) == before and source(p) == document
    with pytest.raises(ValueError, match="Assign"):
        mesh_materials.remove(p, slot)
    assert vars(p) == before and source(p) == document


def test_read_is_nonmutating_and_existing_object_material_stays_live():
    p = fixture()
    before = deepcopy(vars(p))
    assert mesh_materials.read(p)["table"]["slots"][0]["parameters"] is None
    assert vars(p) == before
    mesh_materials.add(p, "Other")
    p.color_fill = [0, 255, 0, 255]
    obj, _ = scene.compose([p], materials=True)
    assert obj.materials[0].base_color == (0, 1, 0)
    mesh_materials.update(p, "m1", name="Explicit", values={"base_color": [1, 0, 0]})
    obj, _ = scene.compose([p], materials=True)
    assert obj.materials[0].base_color == [1, 0, 0]


# ---------------------------------------------------------------------------
# NP-06 (g): solid viewport shading honours explicit slot colours.
# ---------------------------------------------------------------------------

def _top(p):
    d = source(p)
    points = {v["id"]: v["position"] for v in d["vertices"]}
    return next(f["id"] for f in d["faces"] if all(points[c["vertex"]][1] > 0 for c in f["corners"]))


def _solid_pixel(p, yaw, pitch):
    rgba, _ = scene.render([p], 48, 48, yaw=yaw, pitch=pitch, projection="orthographic",
                           ortho_scale=3, grid=False, shading="solid")
    return np.frombuffer(rgba, np.uint8).reshape(48, 48, 4)[24, 24, :3].astype(int)


def test_solid_shading_tints_explicit_slot_faces_and_keeps_inherited_faces_neutral():
    p = fixture()
    legacy_top, legacy_front = _solid_pixel(p, 0, np.pi / 2), _solid_pixel(p, 0, 0)
    slot = mesh_materials.add(p, "Red", {"base_color": [1, 0, 0]})["slot_id"]
    mesh_materials.assign(p, [_top(p)], slot)
    colors = mesh_materials.solid_colors(p, mesh_document.resolve(p.mesh_kind))
    assert colors.shape == (12, 3) and np.count_nonzero((colors >= 0).all(axis=1)) == 2
    top, front = _solid_pixel(p, 0, np.pi / 2), _solid_pixel(p, 0, 0)
    assert top[0] > 150 and top[1] == top[2] == 0
    assert front[0] == front[1] == front[2]
    np.testing.assert_array_equal(front, legacy_front)
    assert legacy_top[0] == legacy_top[1] == legacy_top[2]
    # A colour graph output also tints; an inherited slot never does.
    from elysium.render import material_graph
    graph, node = material_graph.add(material_graph.empty(), "Color")
    graph = material_graph.update(graph, node, value=[0, 0, 1])
    graph = material_graph.output(graph, node)
    mesh_materials.graph_set(p, "m1", graph)
    front = _solid_pixel(p, 0, 0)
    assert front[2] > 150 and front[0] == front[1] == 0


def test_legacy_object_without_slot_table_renders_all_neutral():
    p = fixture()
    assert mesh_materials.solid_colors(p, mesh_document.resolve(p.mesh_kind)) is None
    rgba, ids = scene.render([p], 48, 48, grid=False, shading="solid")
    pixels = np.frombuffer(rgba, np.uint8).reshape(48, 48, 4)
    covered = pixels[ids >= 0, :3]
    assert len(covered) and (covered[:, 0] == covered[:, 1]).all() and (covered[:, 1] == covered[:, 2]).all()


def _doc(p):
    return mesh_document.resolve(p.mesh_kind).topology


def test_primitive_regeneration_carries_per_face_material_assignments():
    p = fixture()
    slot = mesh_materials.add(p, "Red", {"base_color": [1, 0, 0]})["slot_id"]
    face = front(p)
    mesh_materials.assign(p, [face], slot)
    before = mesh_materials.read(p)["face_slots"]
    mesh = mesh_document.resolve(p.mesh_kind)
    # A dimension change rebuilds the same six faces under the same ids, so
    # the slot each face carries survives; it used to reset to slot 0 and
    # leave the second slot orphaned.
    primitives.update(p, {"size": 3.0})
    assert mesh_materials.read(p)["face_slots"] == before
    assert before[face] == slot
    assert [s["id"] for s in mesh_materials.table(p)["slots"]] == ["m1", slot]
    rebuilt = mesh_document.resolve(p.mesh_kind)
    assert primitives.settings(p)["parameters"]["size"] == 3.0
    np.testing.assert_allclose(rebuilt.verts, mesh.verts * 1.5, atol=1e-6)
    # The compiled triangles carry the slot too: one quad, two triangles.
    assert np.count_nonzero(rebuilt.face_mats == 1) == 2
    assert (rebuilt.faces == mesh.faces).all()
    obj, _ = scene.compose([p], materials=True)
    assert len(obj.materials) == 2 and np.count_nonzero(obj.mesh.face_mats == 1) == 2


def test_primitive_regeneration_refuses_to_discard_assignments_it_cannot_map():
    p = SimpleNamespace(kind="Mesh3D", props={}, visible=True, name="Sphere", entity_id="sphere")
    primitives.bind(p, "Sphere", {"rings": 4, "segments": 4})
    slot = mesh_materials.add(p, "Blue", {"base_color": [0, 0, 1]})["slot_id"]
    face = _doc(p)["faces"][0]["id"]
    mesh_materials.assign(p, [face], slot)
    key, before = p.mesh_kind, deepcopy(p.props)
    # A segment change rebuilds a different face set: there is no honest
    # mapping, so it is refused instead of silently resetting every face.
    with pytest.raises(ValueError, match="material assignments"):
        primitives.update(p, {"segments": 6})
    assert p.mesh_kind == key and p.props == before
    assert mesh_materials.read(p)["face_slots"][face] == slot
    # Clearing the assignment unblocks it; regeneration then keeps the slot
    # table and puts every face on the first slot.
    mesh_materials.assign(p, [face], "m1")
    primitives.update(p, {"segments": 6})
    assert set(mesh_materials.read(p)["face_slots"].values()) == {"m1"}
    assert [s["id"] for s in mesh_materials.table(p)["slots"]] == ["m1", slot]
    assert primitives.settings(p)["parameters"]["segments"] == 6


def _cone(params):
    p = SimpleNamespace(kind="Mesh3D", props={}, visible=True, name="Cone", entity_id="cone")
    primitives.bind(p, "Cone", params)
    slot = mesh_materials.add(p, "Blue", {"base_color": [0, 0, 1]})["slot_id"]
    face = _doc(p)["faces"][0]["id"]
    mesh_materials.assign(p, [face], slot)
    return p, face, slot


@pytest.mark.parametrize("kind,base,change,param", [
    ("Cone", {"segments": 6, "radius2": 0.0}, {"radius2": 0.5}, "radius2"),
    ("Cone", {"segments": 6, "radius2": 0.5}, {"radius2": 0.0}, "radius2"),
    ("Cone", {"segments": 6, "radius2": 0.5}, {"cap_fill": "trifan"}, "cap_fill"),
    ("Cylinder", {"segments": 6}, {"cap_fill": "nothing"}, "cap_fill"),
    ("Cone", {"segments": 6}, {"segments": 8}, "segments"),
])
def test_face_set_refusal_names_the_parameter_even_when_it_is_not_a_segment_count(
        kind, base, change, param):
    # `radius2` is a plain float dimension and `cap_fill` a string choice, yet
    # both rebuild a different face set. The refusal must say which parameter
    # did it instead of blaming "these parameters" / the segment counts.
    p = SimpleNamespace(kind="Mesh3D", props={}, visible=True, name=kind, entity_id=kind.lower())
    primitives.bind(p, kind, base)
    slot = mesh_materials.add(p, "Blue", {"base_color": [0, 0, 1]})["slot_id"]
    face = _doc(p)["faces"][0]["id"]
    mesh_materials.assign(p, [face], slot)
    key, before = p.mesh_kind, deepcopy(p.props)
    with pytest.raises(ValueError, match="material assignments") as raised:
        primitives.update(p, change)
    assert f"changing {param} rebuilds a different set of {kind} faces" in str(raised.value)
    assert p.mesh_kind == key and p.props == before
    assert mesh_materials.read(p)["face_slots"][face] == slot
    # The remedy the message gives is reachable.
    mesh_materials.assign(p, [face], "m1")
    primitives.update(p, change)
    assert primitives.settings(p)["parameters"][param] == change[param]


def test_a_dimension_that_keeps_its_faces_still_regenerates_with_assignments():
    # The counterpart: radius is a dimension that rebuilds the same faces, so
    # it must keep committing while a face sits on a second slot.
    p, face, slot = _cone({"segments": 6, "radius2": 0.5})
    primitives.update(p, {"radius": 2.0})
    assert primitives.settings(p)["parameters"]["radius"] == 2.0
    assert mesh_materials.read(p)["face_slots"][face] == slot


def test_primitive_update_tool_description_scopes_the_refusal_it_documents():
    # The description is the only place the refusal is visible to an agent
    # planning a parameter edit; it must not promise segment counts only.
    from elysium.aether.tools import REGISTRY
    description = REGISTRY.get("mesh.primitive_update").description
    assert "radius2" in description and "cap_fill" in description
    assert "different face set (segment counts)" not in description
