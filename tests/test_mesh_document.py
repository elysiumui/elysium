"""Persistence and ownership regressions for native authored geometry."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document as doc
from elysium.render import pbr


@pytest.fixture
def mesh():
    return pbr.Mesh(
        verts=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32),
        faces=np.array([[0, 1, 2]], dtype=np.int32),
        face_mats=np.array([2], dtype=np.int32),
        vert_normals=np.array([[0, 0, 1]] * 3, dtype=np.float32),
        vert_uvs=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32),
        vert_part_ids=np.array([0, 0, 0], dtype=np.int32),
        part_names=["Wing"], part_pivots=np.array([[0, 0, 0]], dtype=np.float32),
    )


@pytest.fixture(autouse=True)
def preserve_library():
    saved = dict(pbr.MESH_LIBRARY)
    yield
    pbr.MESH_LIBRARY.clear()
    pbr.MESH_LIBRARY.update(saved)


def test_fresh_process_load_retains_all_authored_arrays(mesh, tmp_path):
    placement = SimpleNamespace(kind="Mesh3D", props={})
    key = doc.bind(placement, mesh)
    document = doc.capture([placement])
    path = tmp_path / "geometry.json"
    path.write_text(json.dumps(document))
    result = subprocess.run([sys.executable, "-c", '''
import json, sys
from elysium.render import mesh_document as doc
value = json.load(open(sys.argv[1]))
doc.restore(value)
print(json.dumps(doc.to_json(doc.resolve(sys.argv[2]))))
''', str(path), key], capture_output=True, text=True, check=True, env=os.environ.copy())
    assert json.loads(result.stdout) == doc.to_json(mesh)


def test_duplicate_and_uv_edit_do_not_change_source(mesh):
    from elysium.aether.tools.mesh import mesh_uv_unwrap
    first = SimpleNamespace(kind="Mesh3D", props={})
    doc.bind(first, mesh)
    duplicate = SimpleNamespace(kind="Mesh3D", props={})
    doc.bind(duplicate, doc.resolve(first.mesh_kind))
    first_before = doc.to_json(doc.resolve(first.mesh_kind))
    original_key = duplicate.mesh_kind
    session = SimpleNamespace(lookup=lambda _: duplicate, designer=SimpleNamespace())
    mesh_uv_unwrap(session, "duplicate", "cylindrical")
    assert duplicate.mesh_kind != original_key
    assert doc.to_json(doc.resolve(first.mesh_kind)) == first_before
    assert doc.to_json(doc.resolve(original_key)) == first_before
    assert not np.array_equal(doc.resolve(duplicate.mesh_kind).vert_uvs, mesh.vert_uvs)


def test_deformation_preserves_uv_material_and_rig_metadata(mesh):
    verts = mesh.verts.copy()
    verts[2, 2] = 1
    deformed = doc.with_vertices(mesh, verts)
    for key in ("faces", "face_mats", "vert_uvs", "vert_part_ids", "part_pivots"):
        np.testing.assert_array_equal(getattr(deformed, key), getattr(mesh, key))
    assert deformed.part_names == ["Wing"]
    np.testing.assert_allclose(deformed.vert_normals, [[0, -2**-.5, 2**-.5]] * 3, atol=1e-6)
    np.testing.assert_array_equal(mesh.verts[2], [0, 1, 0])


def test_invalid_asset_set_is_not_partially_published(mesh):
    valid = doc.to_json(mesh)
    bad = doc.to_json(mesh)
    bad["faces"] = [[0, 1, 999]]
    keys = set(pbr.MESH_LIBRARY)
    with pytest.raises(ValueError, match="face index"):
        doc.restore({"schema_version": 1, "assets": {"valid-new": valid, "bad": bad}})
    assert set(pbr.MESH_LIBRARY) == keys


@pytest.mark.parametrize("field,value", [
    ("verts", None), ("verts", [[float("nan"), 0, 0]]),
    ("faces", [[0, 1, .5]]), ("faces", [[0, 1, 2**32]]),
    ("vert_uvs", [[0, 0]]), ("part_names", ["Wing", "Wing"]),
])
def test_malformed_geometry_rejected_before_binding(mesh, field, value):
    data = doc.to_json(mesh)
    data[field] = value
    with pytest.raises((ValueError, TypeError)):
        doc.from_json(data)


def test_skin_bind_source_is_persisted_even_after_deformation(mesh):
    placement = SimpleNamespace(kind="Mesh3D", props={})
    original = doc.bind(placement, mesh)
    placement.props["skin_source_mesh"] = original
    current = doc.bind(placement, doc.with_vertices(mesh, mesh.verts * 2))
    assert set(doc.capture([placement])["assets"]) == {original, current}


def test_cylinder_dimensions_winding_uvs_and_closed_surface():
    mesh = pbr.cylinder_mesh(radius=2, height=3, segs=32)
    doc.validate(mesh)
    np.testing.assert_allclose(mesh.verts.min(axis=0), [-2, -1.5, -2], atol=1e-6)
    np.testing.assert_allclose(mesh.verts.max(axis=0), [2, 1.5, 2], atol=1e-6)
    triangles = mesh.verts[mesh.faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    assert (np.einsum("ij,ij->i", normals, triangles.mean(axis=1)) > 0).all()
    assert len(mesh.faces) == 128
    assert (mesh.vert_uvs >= 0).all() and (mesh.vert_uvs <= 1).all()
    # Weld positional duplicates only for the closed-surface check: UV seams
    # and flat caps legitimately need distinct render vertices.
    from collections import Counter
    _, inverse = np.unique(np.round(mesh.verts, 6), axis=0, return_inverse=True)
    edges = Counter(tuple(sorted((int(a), int(b)))) for face in inverse[mesh.faces]
                    for a, b in zip(face, np.roll(face, -1)))
    assert set(edges.values()) == {2}


@pytest.mark.parametrize("kwargs", [{"radius": 0}, {"height": -1},
                                    {"segs": 2}, {"segs": 3.5}, {"radius": float("inf")}])
def test_cylinder_rejects_invalid_dimensions(kwargs):
    with pytest.raises(ValueError):
        pbr.cylinder_mesh(**kwargs)
