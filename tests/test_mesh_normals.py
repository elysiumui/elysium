from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, mesh_normals, primitives, topology


def fixture(kind="Cube"):
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Normals", entity_id="normals")
    primitives.bind(p, kind)
    return p


def mesh(p):
    return mesh_document.resolve(p.mesh_kind)


def test_angle_limit_splits_cube_faces_without_changing_source_attributes():
    p = fixture()
    before = deepcopy(mesh(p).topology)
    mesh_normals.set_policy(p, "smooth", angle=100)
    m = mesh(p)
    np.testing.assert_allclose(m.vert_normals, m.verts / np.sqrt(3), atol=1e-7)
    mesh_normals.set_policy(p, "smooth", angle=80)
    m = mesh(p)
    assert (np.count_nonzero(np.abs(m.vert_normals) > 1e-6, axis=1) == 1).all()
    for key in ("vertices", "edges", "faces", "next_id"):
        assert m.topology[key] == before[key]


def test_sharp_flags_split_smooth_fans_without_editing_uv_seams():
    p = fixture()
    mesh_normals.set_policy(p, "smooth")
    edges = [e["id"] for e in mesh(p).topology["edges"]]
    before = deepcopy(mesh(p).topology)
    mesh_normals.set_sharp(p, edges)
    assert (np.count_nonzero(np.abs(mesh(p).vert_normals) > 1e-6, axis=1) == 1).all()
    assert [e["seam"] for e in mesh(p).topology["edges"]] == [e["seam"] for e in before["edges"]]
    assert mesh(p).topology["faces"] == before["faces"]
    mesh_normals.set_policy(p, "smooth", respect_sharp=False)
    np.testing.assert_allclose(mesh(p).vert_normals, mesh(p).verts / np.sqrt(3), atol=1e-7)
    mesh_normals.set_sharp(p, edges, False)
    assert not mesh_normals.read(p)["sharp_edge_ids"]


def test_flat_override_and_authored_restore_original_sphere_normals_exactly():
    p = fixture("Sphere")
    before = mesh_document.to_json(mesh(p))
    mesh_normals.set_policy(p, "flat")
    m = mesh(p)
    for tri in m.faces:
        np.testing.assert_array_equal(m.vert_normals[tri[0]], m.vert_normals[tri[1]])
        np.testing.assert_array_equal(m.vert_normals[tri[0]], m.vert_normals[tri[2]])
    mesh_normals.set_policy(p, "authored")
    after = mesh_document.to_json(mesh(p))
    after["topology"]["schema_version"] = before["topology"]["schema_version"]
    assert after == before


def test_retained_smoothing_recomputes_after_vertex_edit_and_round_trip():
    p = fixture()
    mesh_normals.set_policy(p, "smooth")
    old = mesh(p)
    edited = topology.move_vertices(old, [old.topology["vertices"][0]["id"]], [0.5, 0.2, 0.1])
    assert edited.topology["shading"] == old.topology["shading"]
    assert not np.allclose(edited.vert_normals, old.vert_normals)
    np.testing.assert_allclose(np.linalg.norm(edited.vert_normals, axis=1), 1, atol=1e-7)
    mesh_document.bind(p, edited)
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    assert mesh_document.to_json(mesh(p)) == mesh_document.to_json(edited)


@pytest.mark.parametrize(
    "values",
    [
        {"mode": "unknown"},
        {"mode": "smooth", "angle": True},
        {"mode": "smooth", "angle": float("nan")},
        {"mode": "smooth", "angle": 181},
        {"mode": "smooth", "angle": -1},
        {"mode": "flat", "respect_sharp": 1},
    ],
)
def test_invalid_policy_is_atomic(values):
    p = fixture()
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_normals.set_policy(p, **values)
    assert p.__dict__ == before


@pytest.mark.parametrize("ids", [[], ["stale"], ["e1", "e1"], [1], "all"])
def test_invalid_sharp_selection_is_atomic(ids):
    p = fixture()
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_normals.set_sharp(p, ids)
    assert p.__dict__ == before


def test_old_topology_version_cannot_smuggle_normal_policy():
    p = fixture()
    doc = deepcopy(mesh(p).topology)
    doc["shading"] = {"mode": "smooth", "angle": 180, "respect_sharp": True}
    with pytest.raises(ValueError, match="version 4"):
        topology.compile(doc)


def test_read_maps_split_normals_to_source_face_and_vertex():
    p = fixture()
    mesh_normals.set_policy(p, "flat")
    read = mesh_normals.read(p)
    doc = mesh(p).topology
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    faces = {f["id"]: f for f in doc["faces"]}
    covered = set()
    for triangle, face_id in zip(read["triangles"], read["triangle_face_ids"]):
        face = faces[face_id]
        vertices = {c["vertex"] for c in face["corners"]}
        expected = topology.normal([points[c["vertex"]] for c in face["corners"]])
        for i in triangle:
            vertex = read["render_vertex_ids"][i]
            assert vertex in vertices
            covered.add((face_id, vertex))
            np.testing.assert_allclose(read["normals"][i], expected, atol=1e-7)
    assert covered == {(f["id"], c["vertex"]) for f in doc["faces"] for c in f["corners"]}
