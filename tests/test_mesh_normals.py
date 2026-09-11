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


def test_flat_face_excludes_its_contribution_from_smooth_neighbor_fans():
    p = fixture()
    mesh_normals.set_policy(p, 'smooth')
    before = deepcopy(mesh(p).topology)
    points = {v['id']: v['position'] for v in before['vertices']}
    top = next(f for f in before['faces'] if all(points[c['vertex']][1] > 0 for c in f['corners']))
    mesh_normals.set_faces_smooth(p, [top['id']], False)
    doc = mesh(p).topology
    result = mesh_normals.corner_normals(doc)
    for face in doc['faces']:
        for c in face['corners']:
            position = np.array(points[c['vertex']])
            expected = np.array([0., 1., 0.]) if face['id'] == top['id'] else position.copy()
            if face['id'] != top['id'] and position[1] > 0:
                expected[1] = 0
            expected /= np.linalg.norm(expected)
            np.testing.assert_allclose(result[c['id']], expected, atol=1e-7)
    for name in ('vertices', 'edges', 'next_id'):
        assert doc[name] == before[name]
    for face, original in zip(doc['faces'], before['faces']):
        assert {k: v for k, v in face.items() if k != 'smooth'} == original
    assert mesh_normals.read(p)['face_smooth_overrides'] == {top['id']: False}
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    assert mesh(p).topology == doc
    mesh_normals.set_policy(p, 'smooth')
    assert not mesh_normals.read(p)['face_smooth_overrides']
    np.testing.assert_allclose(mesh(p).vert_normals, mesh(p).verts / np.sqrt(3), atol=1e-7)


def test_face_smooth_under_flat_policy_and_weighted_normals_respect_flat_faces():
    p = fixture()
    mesh_normals.set_policy(p, 'flat')
    doc = mesh(p).topology
    first = doc['faces'][0]
    vertices = {c['vertex'] for c in first['corners']}
    neighbor = next(f for f in doc['faces'][1:] if vertices & {c['vertex'] for c in f['corners']})
    selected = [first['id'], neighbor['id']]
    mesh_normals.set_faces_smooth(p, selected, True)
    result = mesh_normals.corner_normals(mesh(p).topology)
    assert any(np.count_nonzero(np.abs(n) > 1e-7) > 1 for n in result.values())
    settings = {'mode':'face_area', 'weight':50, 'threshold':0.01, 'keep_sharp':False}
    weighted = mesh_normals.weighted_mesh(mesh(p), settings)
    points = {v['id']: v['position'] for v in weighted.topology['vertices']}
    for face in weighted.topology['faces']:
        if face['id'] not in selected:
            expected = topology.normal([points[c['vertex']] for c in face['corners']])
            for c in face['corners']:
                np.testing.assert_allclose(c['normal'], expected, atol=1e-7)


@pytest.mark.parametrize('ids,value', [([],True),(['stale'],True),(['f1','f1'],True),([1],True),('all',True),(['f1'],1)])
def test_invalid_face_shading_is_atomic(ids, value):
    p = fixture()
    mesh_normals.set_policy(p, 'smooth')
    before = deepcopy(vars(p))
    with pytest.raises(ValueError):
        mesh_normals.set_faces_smooth(p, ids, value)
    assert vars(p) == before


def test_authored_face_shading_requires_explicit_computed_policy():
    p = fixture()
    before = deepcopy(vars(p))
    with pytest.raises(ValueError, match='whole-mesh'):
        mesh_normals.set_faces_smooth(p, [mesh(p).topology['faces'][0]['id']])
    assert vars(p) == before


def test_face_smooth_schema_and_generated_child_inheritance():
    from elysium.render import mesh_subdivision
    p = fixture()
    mesh_normals.set_policy(p, 'smooth')
    selected = mesh(p).topology['faces'][0]['id']
    mesh_normals.set_faces_smooth(p, [selected], False)
    doc = deepcopy(mesh(p).topology)
    doc['schema_version'] = 4
    with pytest.raises(ValueError):
        topology.compile(doc)
    doc['schema_version'] = 5
    doc['faces'][0]['smooth'] = 1
    with pytest.raises(ValueError, match='boolean'):
        topology.compile(doc)
    subdivided = mesh_subdivision.step(mesh(p), 'simple', 'keep_corners')
    assert sum(f.get('smooth') is False for f in subdivided.topology['faces']) == 4
    extruded = topology.extrude(mesh(p), [selected], 0.25)
    assert sum(f.get('smooth') is False for f in extruded.topology['faces']) == 5
