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
