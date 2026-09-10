from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, mesh_edit, mesh_modifiers, mesh_uv, primitives, topology


def placement(kind="Plane", parameters=None):
    p = SimpleNamespace(kind="Mesh3D", name=kind, entity_id="uv-test", mesh_kind="", props={})
    mesh_document.bind(p, primitives.build(kind, parameters or {})[0])
    return p


def without_uv(doc):
    result = deepcopy(doc)
    for f in result["faces"]:
        for c in f["corners"]:
            c["uv"] = None
    return result


def test_corner_projection_preserves_geometry_attributes_stack_and_roundtrip():
    p = placement("Cube")
    doc = mesh_uv.source(p)
    doc["edges"][0].update(seam=True, sharp=True)
    for i, f in enumerate(doc["faces"]):
        f["material"] = i
        for c in f["corners"]:
            c["normal"] = [0, 1, 0]
    mesh_document.bind(p, topology.compile(doc)[0])
    mesh_modifiers.add(p, "Subdivision")
    stack = deepcopy(p.props)
    mesh_uv.project(p, "planar_xy")
    result = mesh_document.resolve(p.mesh_kind)
    mesh_document.validate(result)
    assert without_uv(result.topology) == without_uv(doc)
    assert p.props == stack
    assert mesh_edit.evaluate(p).vert_uvs is not None
    saved = mesh_document.capture([p])
    mesh_document.restore(saved, [p])
    assert mesh_document.to_json(mesh_document.resolve(p.mesh_kind)) == mesh_document.to_json(
        result
    )


def test_top_projection_matches_blender_y_up_conversion():
    p = placement()
    mesh_uv.project(p, "planar_xz")
    doc = mesh_uv.source(p)
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    for face in doc["faces"]:
        for c in face["corners"]:
            x, y, z = points[c["vertex"]]
            np.testing.assert_allclose(c["uv"], [(x + 1) / 2, (1 - z) / 2])


def test_selected_face_and_corner_edits_do_not_weld_uv_seams():
    p = placement("Cube")
    mesh_uv.project(p, "planar_xy")
    before = mesh_uv.source(p)
    face_id = before["faces"][0]["id"]
    mesh_uv.project(p, "planar_xz", face_ids=[face_id])
    after = mesh_uv.source(p)
    assert after["faces"][1:] == before["faces"][1:]
    corner = after["faces"][0]["corners"][0]
    mesh_uv.transform(p, [corner["id"]], offset=[0.25, -0.5])
    final = mesh_uv.source(p)
    np.testing.assert_allclose(
        final["faces"][0]["corners"][0]["uv"], np.array(corner["uv"]) + [0.25, -0.5]
    )
    assert final["faces"][0]["corners"][1:] == after["faces"][0]["corners"][1:]
    assert final["faces"][1:] == after["faces"][1:]
    mesh_document.validate(mesh_document.resolve(p.mesh_kind))


def test_transform_scale_rotate_translate_order():
    p = placement()
    mesh_uv.project(p, "planar_xz")
    before = [c["uv"] for f in mesh_uv.read(p)["faces"] for c in f["corners"]]
    mesh_uv.transform(p, offset=[0.25, -0.5], scale=[2, 0.5], angle=90)
    after = [c["uv"] for f in mesh_uv.read(p)["faces"] for c in f["corners"]]
    expected = ((np.array(before) - 0.5) * [2, 0.5]) @ np.array([[0, -1], [1, 0]]) + [0.75, 0]
    np.testing.assert_allclose(after, expected, atol=1e-7)


@pytest.mark.parametrize("mode", ["cylindrical", "spherical"])
def test_periodic_projection_keeps_local_seams_and_poles_finite(mode):
    p = placement("Sphere", {"segments": 8, "rings": 4})
    mesh_uv.project(p, mode)
    for f in mesh_uv.read(p)["faces"]:
        uv = np.array([c["uv"] for c in f["corners"]])
        assert np.isfinite(uv).all()
        assert np.ptp(uv[:, 0]) <= 0.5
    mesh_document.validate(mesh_document.resolve(p.mesh_kind))


def test_seams_only_change_requested_edge_flags():
    p = placement()
    before = mesh_uv.source(p)
    edge = before["edges"][0]["id"]
    mesh_uv.seams(p, [edge])
    after = mesh_uv.source(p)
    assert mesh_uv.read(p)["seams"] == [edge]
    before["edges"][0]["seam"] = True
    assert before == after
    mesh_uv.seams(p, [edge], False)
    assert not mesh_uv.read(p)["seams"]


@pytest.mark.parametrize(
    "operation",
    [
        lambda p: mesh_uv.project(p, "missing"),
        lambda p: mesh_uv.project(p, "planar", face_ids=["missing"]),
        lambda p: mesh_uv.project(p, "planar", yaw=float("nan")),
        lambda p: mesh_uv.transform(p),
        lambda p: mesh_uv.seams(p, ["missing"]),
        lambda p: mesh_uv.seams(p, [], True),
    ],
)
def test_invalid_uv_operations_leave_owned_revision_unchanged(operation):
    p = placement()
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        operation(p)
    assert p.__dict__ == before


def test_legacy_public_unwrap_uses_retained_corner_uvs_and_clears_caches():
    from elysium.aether.tools.mesh import mesh_uv_unwrap

    p = placement()
    designer = SimpleNamespace(_mesh_cache={"old": 1})
    result = mesh_uv_unwrap(
        SimpleNamespace(lookup=lambda _: p, designer=designer), "test", "planar", pitch=np.pi / 2
    )
    assert result["verts"] == 4 and result["mode"] == "planar"
    mesh_document.validate(mesh_document.resolve(p.mesh_kind))
    assert not designer._mesh_cache
    assert all(c["uv"] is not None for f in mesh_uv.read(p)["faces"] for c in f["corners"])
