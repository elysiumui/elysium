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
