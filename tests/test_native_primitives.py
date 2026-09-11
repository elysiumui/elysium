"""Model-space dimensions and editable native primitive contracts."""

from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, primitives


@pytest.mark.parametrize(
    "kind,parameters,dimensions",
    [
        ("Cube", {"size": 3.25}, [3.25] * 3),
        ("Sphere", {"radius": 1.5}, [3.0] * 3),
        ("Cylinder", {"radius": 0.75, "height": 4}, [1.5, 4, 1.5]),
        ("Cone", {"radius": 0.75, "height": 4}, [1.5, 4, 1.5]),
        ("Plane", {"width": 3, "depth": 5}, [3, 0, 5]),
        ("Torus", {"major_radius": 2, "minor_radius": 0.5}, [5, 1, 5]),
    ],
)
def test_requested_dimensions_centering_and_valid_surface(kind, parameters, dimensions):
    mesh, values = primitives.build(kind, parameters)
    mesh_document.validate(mesh)
    np.testing.assert_allclose(np.ptp(mesh.verts, axis=0), dimensions, atol=1e-6)
    np.testing.assert_allclose(mesh.verts.max(axis=0) + mesh.verts.min(axis=0), 0, atol=1e-6)
    tri = mesh.verts[mesh.faces].astype(np.float64)
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    assert (np.linalg.norm(cross, axis=1) > 1e-10).all()
    if kind == "Plane":
        assert (cross[:, 1] > 0).all()
    else:
        assert np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() > 0
        _, inverse = np.unique(np.round(mesh.verts, 6), axis=0, return_inverse=True)
        edges = Counter(
            tuple(sorted((int(a), int(b))))
            for face in inverse[mesh.faces]
            for a, b in zip(face, np.roll(face, -1))
        )
        assert set(edges.values()) == {2}
    assert all(values[key] == value for key, value in parameters.items())


@pytest.mark.parametrize(
    "kind,params",
    [
        ("Cube", {"size": 0}),
        ("Sphere", {"rings": 2}),
        ("Cylinder", {"segments": 3.1}),
        ("Cone", {"height": float("nan")}),
        ("Plane", {"width": True}),
        ("Torus", {"minor_radius": 2}),
        ("Cube", {"missing": 1}),
    ],
)
def test_invalid_primitive_update_is_atomic(kind, params):
    p = SimpleNamespace(kind="Mesh3D", props={})
    primitives.bind(p, kind)
    before = deepcopy(p.__dict__)
    with pytest.raises((TypeError, ValueError)):
        primitives.update(p, params)
    assert p.__dict__ == before


def test_regeneration_never_discards_later_geometry_edits():
    p = SimpleNamespace(kind="Mesh3D", props={})
    primitives.bind(p, "Cube")
    mesh = mesh_document.resolve(p.mesh_kind)
    mesh_document.bind(p, mesh_document.with_vertices(mesh, mesh.verts * [1, 2, 1]))
    key = p.mesh_kind
    with pytest.raises(ValueError, match="after geometry editing"):
        primitives.update(p, {"size": 5})
    assert p.mesh_kind == key


def test_public_creation_schema_rejects_wrong_parameter_before_call():
    from elysium.aether.tools import REGISTRY
    from elysium.aether.types import ToolCall

    result = REGISTRY.dispatch(
        ToolCall("invalid", "mesh.primitive_create", {"kind": "Cube", "parameters": {"radius": 1}}),
        None,
    )
    assert not result.ok
    assert "Additional properties" in result.error


@pytest.mark.parametrize(
    "metadata",
    [
        {"kind": "Unknown", "parameters": {}},
        {"kind": "Cube", "parameters": {}},
        {"kind": "Cube", "parameters": {"size": "broken"}},
        {"kind": "Cube", "parameters": {"size": 0}},
    ],
)
def test_invalid_saved_metadata_does_not_break_inspector(metadata):
    p = SimpleNamespace(
        kind="Mesh3D",
        mesh_kind="mesh:test",
        props={"primitive": {**metadata, "mesh_key": "mesh:test"}},
    )
    assert primitives.settings(p) is None


def test_unchanged_parameters_preserve_geometry_identity():
    p = SimpleNamespace(kind="Mesh3D", props={})
    key = primitives.bind(p, "Cube")
    assert primitives.update(p, {"size": 2}) == key
    assert p.mesh_kind == key


@pytest.mark.parametrize(
    "kind,parameters,counts,sizes",
    [
        ("Cylinder", {"segments": 8}, (16, 24, 10), {4: 8, 8: 2}),
        ("Cone", {"segments": 8}, (9, 16, 9), {3: 8, 8: 1}),
        ("Plane", {"segments": 2}, (9, 12, 4), {4: 4}),
        ("Sphere", {"rings": 4, "segments": 8}, (26, 56, 32), {3: 16, 4: 16}),
        ("Torus", {"major_segments": 8, "minor_segments": 4}, (32, 64, 32), {4: 32}),
    ],
)
def test_authored_primitive_polygon_connectivity(kind, parameters, counts, sizes):
    mesh, _ = primitives.build(kind, parameters)
    doc = mesh.topology
    assert tuple(len(doc[k]) for k in ("vertices", "edges", "faces")) == counts
    assert dict(Counter(len(f["corners"]) for f in doc["faces"])) == sizes
    restored = mesh_document.from_json(mesh_document.to_json(mesh))
    assert restored.topology == doc


def test_cylinder_welded_source_preserves_uv_seam_and_separate_cap_normals():
    from elysium.render import topology

    mesh, _ = primitives.build("Cylinder", {"segments": 8})
    doc = mesh.topology
    first = doc["vertices"][0]["id"]
    corners = [c for f in doc["faces"] for c in f["corners"] if c["vertex"] == first]
    assert {tuple(c["uv"]) for c in corners} >= {(0.0, 0.0), (1.0, 0.0)}
    assert {tuple(c["normal"]) for c in corners} >= {(1.0, 0.0, 0.0), (0.0, -1.0, 0.0)}
    _, compiled_ids, _ = topology.compile(doc)
    assert compiled_ids.count(first) == 3
    # The source rim vertex moves as one component despite three render corners.
    moved = topology.move_vertices(mesh, [first], [0.1, 0, 0])
    _, ids, _ = topology.compile(moved.topology)
    np.testing.assert_allclose(moved.verts[np.array(ids) == first], [[1.1, -1, 0]] * 3)


@pytest.mark.parametrize(
    "kind,parameters,euler",
    [
        ("Sphere", {"rings": 4, "segments": 8}, 2),
        ("Torus", {"major_segments": 8, "minor_segments": 4}, 0),
    ],
)
def test_curved_polygon_primitives_close_seams_without_losing_corner_uvs(kind, parameters, euler):
    mesh, _ = primitives.build(kind, parameters)
    doc = mesh.topology
    assert len(doc["vertices"]) - len(doc["edges"]) + len(doc["faces"]) == euler
    usages = {}
    corner_uvs = {}
    for f in doc["faces"]:
        ids = [c["vertex"] for c in f["corners"]]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            usages.setdefault(tuple(sorted((a, b))), []).append((a, b))
        for c in f["corners"]:
            corner_uvs.setdefault(c["vertex"], set()).add(tuple(c["uv"]))
    assert all(len(v) == 2 and v[0] == v[1][::-1] for v in usages.values())
    assert any(len(uvs) > 1 for uvs in corner_uvs.values())
    if kind == "Sphere":
        poles = [v for v in doc["vertices"] if abs(v["position"][1]) == 1]
        assert len(poles) == 2
        assert all(len(corner_uvs[v["id"]]) == parameters["segments"] for v in poles)


@pytest.mark.parametrize('segments', [3, 7, 8, 32])
def test_sphere_uvs_have_blender_orientation_and_polar_midpoints(segments):
    mesh, _ = primitives.build('Sphere', {'rings': 4, 'segments': segments})
    faces = mesh.topology['faces']
    for face in faces:
        coords = np.asarray([c['uv'] for c in face['corners']])
        assert np.ptp(coords[:, 0]) <= 1/segments + 1e-7
        if len(coords) == 3:
            pole = next(i for i, uv in enumerate(coords) if uv[1] in (0., 1.))
            others = np.delete(coords, pole, axis=0)
            assert coords[pole, 0] == pytest.approx(others[:, 0].mean(), abs=1e-7)
    first = faces[0]['corners']
    assert first[0]['uv'] == pytest.approx([.5-.5/segments, 1.])
    assert first[1]['uv'] == pytest.approx([.5-1/segments, .75])
    assert first[2]['uv'] == pytest.approx([.5, .75])
