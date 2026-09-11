"""Behavioral and atomicity checks for selected distance welding."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, primitives, topology


def wire(points):
    mesh = primitives.build('Cube', {'size': 2})[0]
    mesh = topology.delete_components(mesh, 'faces', [f['id'] for f in mesh.topology['faces']])
    ids = []
    for point in points:
        mesh, identity = topology.add_vertex(mesh, point)
        ids.append(identity)
    return mesh, ids


@pytest.mark.parametrize('centroid', [False, True])
def test_extruded_wire_pairs_match_saved_blender_geometry(centroid):
    mesh, ids = wire([[0,0,0], [1,0,0], [1,1,0], [0,1,0]])
    for a, b in zip(ids, ids[1:]):
        mesh, _ = topology.connect_vertices(mesh, [a,b])
    mesh, extra = topology.extrude_vertices(mesh, ids, [0.00005,0,0])
    before = mesh_document.to_json(mesh)
    merged, selected = topology.merge_distance(mesh, ids + extra, centroid=centroid)
    assert [len(merged.topology[k]) for k in ('vertices','edges','faces')] == [4,3,0]
    np.testing.assert_allclose(merged.verts, np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]]) + [0.000025 if centroid else 0,0,0], atol=1e-7)
    assert selected == ids
    assert mesh_document.to_json(mesh) == before
    assert mesh_document.from_json(mesh_document.to_json(merged)).topology == merged.topology


def test_surface_weld_retains_corner_uvs_materials_and_unions_edge_flags():
    mesh = primitives.build('Cube', {'size': 2})[0]
    original = deepcopy(mesh.topology)
    ids = [v['id'] for v in original['vertices']]
    mesh, added = topology.extrude_vertices(mesh, ids, [0.00005,0,0])
    doc = deepcopy(mesh.topology)
    for f in doc['faces']:
        f['material'] = 2
    edge = doc['edges'][0]
    edge['seam'] = True
    mesh = topology.compile(doc)[0]
    # A second copy of one edge collapses onto the existing flagged edge.
    mapping = dict(zip(ids, added))
    mesh, duplicate = topology.connect_vertices(mesh, [mapping[v] for v in edge['vertices']])
    doc = deepcopy(mesh.topology)
    next(e for e in doc['edges'] if e['id'] == duplicate)['sharp'] = True
    mesh = topology.compile(doc)[0]
    merged, selected = topology.merge_distance(mesh, ids + added, centroid=False)
    assert [len(merged.topology[k]) for k in ('vertices','edges','faces')] == [8,12,6]
    result_edge = next(e for e in merged.topology['edges'] if e['id'] == edge['id'])
    assert result_edge['seam'] and result_edge['sharp']
    assert all(f['material'] == 2 for f in merged.topology['faces'])
    assert [[c['uv'] for c in f['corners']] for f in merged.topology['faces']] == [[c['uv'] for c in f['corners']] for f in original['faces']]
    assert selected == ids


def test_selection_isolation_inclusive_threshold_and_no_transitive_chain():
    mesh, ids = wire([[0,0,0], [0.125,0,0], [0.25,0,0], [0.01,0,0]])
    merged, selected = topology.merge_distance(mesh, ids[:3], .125, centroid=False)
    assert selected == [ids[0], ids[2]]
    assert [v['id'] for v in merged.topology['vertices']] == [ids[0], ids[2], ids[3]]
    np.testing.assert_array_equal(merged.verts[-1], np.array([.01,0,0], dtype=np.float32))


def test_zero_threshold_and_centroid_survivor_for_three_coincident_points():
    mesh, ids = wire([[0,0,0], [0,0,0], [0,0,0], [1,0,0]])
    merged, selection = topology.merge_distance(mesh, ids, 0)
    assert selection == [ids[0], ids[3]]
    assert len(merged.topology['vertices']) == 2


def test_noop_preserves_mesh_asset_and_selection():
    mesh, ids = wire([[0,0,0], [1,0,0]])
    p = SimpleNamespace(kind='Mesh3D', name='Wire', props={}, mesh_kind='')
    mesh_document.bind(p, mesh, label=p.name)
    topology.select(p, 'vertices', ids)
    before = deepcopy(vars(p))
    result = topology.edit_selected(p, 'merge_distance')
    assert vars(p) == before
    assert result['mesh_key'] == before['mesh_kind']


@pytest.mark.parametrize('threshold', [-1, float('nan'), float('inf'), True])
def test_invalid_distance_rejects_before_mutation(threshold):
    mesh, ids = wire([[0,0,0], [0,0,0]])
    before = mesh_document.to_json(mesh)
    with pytest.raises(ValueError, match='threshold'):
        topology.merge_distance(mesh, ids, threshold)
    assert mesh_document.to_json(mesh) == before


def test_stale_selection_and_invalid_centroid_reject():
    mesh, ids = wire([[0,0,0], [0,0,0]])
    with pytest.raises(ValueError, match='existing'):
        topology.merge_distance(mesh, [ids[0], 'stale'])
    with pytest.raises(ValueError, match='boolean'):
        topology.merge_distance(mesh, ids, centroid='yes')


def test_pinched_face_failure_is_atomic():
    mesh = primitives.build('Plane', {'width':2,'depth':2,'segments':1})[0]
    ids = [v['id'] for v in mesh.topology['vertices'] if v['position'][0] == v['position'][2]]
    p = SimpleNamespace(kind='Mesh3D', name='Plane', props={}, mesh_kind='')
    mesh_document.bind(p, mesh, label=p.name)
    topology.select(p, 'vertices', ids)
    before = deepcopy(vars(p))
    with pytest.raises(ValueError, match='pinch'):
        topology.edit_selected(p, 'merge_distance', threshold=3)
    assert vars(p) == before
