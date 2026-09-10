from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import mesh_document, mesh_uv, mesh_uv_diagnostics, primitives, scene, topology


def plane():
    p = SimpleNamespace(kind="Mesh3D", props={}, visible=True)
    primitives.bind(p, "Plane")
    mesh_uv.project(p, "planar_xz")
    return p


def test_stretch_distinguishes_anisotropy_from_rotation_and_density():
    p = plane()
    assert mesh_uv_diagnostics.inspect(p)["max_stretch"] == pytest.approx(1)
    mesh_uv.transform(p, scale=[3, 3], angle=37, offset=[2, -4])
    report = mesh_uv_diagnostics.inspect(p)
    assert report["max_stretch"] == pytest.approx(1)
    assert all(t["area_ratio"] == pytest.approx(2.25) for t in report["faces"][0]["triangles"])
    mesh_uv.project(p, "planar_xz")
    mesh_uv.transform(p, scale=[2, 1])
    before = deepcopy(mesh_uv.source(p))
    report = mesh_uv_diagnostics.inspect(p)
    assert report["max_stretch"] == pytest.approx(2)
    assert mesh_uv.source(p) == before
    scene.update(p, {"scale": [7, 1, 2]})
    assert mesh_uv_diagnostics.inspect(p) == report  # Explicit local-source metric.


def test_missing_collapsed_and_reflected_uvs_are_explicit():
    p = plane()
    mesh_uv.transform(p, scale=[-1, 1])
    report = mesh_uv_diagnostics.inspect(p)
    assert report["max_stretch"] == pytest.approx(1)
    assert all(t["uv_winding"] == -1 for t in report["faces"][0]["triangles"])
    doc = mesh_uv.source(p)
    for c in doc["faces"][0]["corners"]:
        c["uv"] = [0, 0]
    mesh_document.bind(p, topology.compile(doc)[0])
    assert mesh_uv_diagnostics.inspect(p)["collapsed_faces"] == 1
    assert set(mesh_uv_diagnostics.face_uv_status(mesh_document.resolve(p.mesh_kind))) == {
        "collapsed"
    }
    doc["faces"][0]["corners"][0]["uv"] = None
    mesh_document.bind(p, topology.compile(doc)[0])
    assert mesh_uv_diagnostics.inspect(p)["missing_faces"] == 1
    assert set(mesh_uv_diagnostics.face_uv_status(mesh_document.resolve(p.mesh_kind))) == {
        "missing"
    }


def test_checker_uses_corner_uvs_keeps_picking_and_does_not_edit_materials():
    p = plane()
    before = deepcopy(vars(p))
    view = {
        "width": 129,
        "height": 129,
        "yaw": 0,
        "pitch": np.pi / 2,
        "projection": "orthographic",
        "ortho_scale": 2.4,
        "grid": False,
    }
    _solid, ids = scene.render([p], **view)
    checker, check_ids = scene.render([p], shading="checker", **view)
    pixels = np.frombuffer(checker, np.uint8).reshape(129, 129, 4)
    np.testing.assert_array_equal(ids, check_ids)
    assert {tuple(c) for c in pixels[ids == 0, :3]} == {(68, 68, 68), (208, 208, 208)}
    row = pixels[60, :, 0][ids[60] == 0]
    assert np.count_nonzero(row[1:] != row[:-1]) == 7
    assert vars(p) == before
    mesh_uv.transform(p, scale=[2, 1])
    stretched, _ = scene.render([p], shading="checker", **view)
    row = np.frombuffer(stretched, np.uint8).reshape(129, 129, 4)[60, :, 0][ids[60] == 0]
    assert np.count_nonzero(row[1:] != row[:-1]) == 15
    doc = mesh_uv.source(p)
    doc["faces"][0]["corners"][0]["uv"] = None
    mesh_document.bind(p, topology.compile(doc)[0])
    missing, _ = scene.render([p], shading="checker", **view)
    pixels = np.frombuffer(missing, np.uint8).reshape(129, 129, 4)
    assert np.all(pixels[ids == 0, :3] == (170, 65, 190))
