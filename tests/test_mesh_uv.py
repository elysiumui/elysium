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


@pytest.mark.parametrize("fixture_index", [0, 1])
def test_cube_projection_matches_independent_blender_gui_records(fixture_index):
    import json
    from pathlib import Path
    record = json.loads((Path(__file__).parent / "fixtures/blender_cube_projection.json").read_text())["fixtures"][fixture_index]
    p = placement("Cube")
    doc = mesh_uv.source(p)
    for vertex in doc["vertices"]:
        vertex["position"][0] += record["offset_x"]
    mesh_document.bind(p, topology.compile(doc)[0])
    mesh_uv.cube_project(p, cube_size=record["cube_size"])
    result = mesh_uv.source(p)
    assert without_uv(result) == without_uv(doc)
    points = {v["id"]: tuple(v["position"]) for v in result["vertices"]}
    actual = {}
    for face in result["faces"]:
        center = tuple(np.mean([points[c["vertex"]] for c in face["corners"]], axis=0))
        for c in face["corners"]:
            actual[(center, points[c["vertex"]])] = c["uv"]
    b = record["objects"][0]
    expected = {}
    for f in b["faces"]:
        center = tuple(np.mean([b["vertices"][v] for v in f["vertices"]], axis=0))
        for vertex, uv in zip(f["vertices"], f["uvs"]):
            expected[(center, tuple(b["vertices"][vertex]))] = uv
    assert actual == expected


def test_cube_projection_selected_faces_and_pins_survive_bounds_options():
    p = placement("Cube")
    mesh_uv.cube_project(p)
    doc = mesh_uv.source(p)
    face = doc["faces"][0]
    mesh_uv.pin(p, [face["corners"][0]["id"]])
    before = mesh_uv.source(p)
    mesh_uv.cube_project(p, [face["id"]], cube_size=1, clip=True, scale_bounds=True)
    after = mesh_uv.source(p)
    assert after["faces"][1:] == before["faces"][1:]
    assert without_uv(after) == without_uv(before)
    uv = np.array([c["uv"] for c in after["faces"][0]["corners"]])
    assert uv.min() == 0 and uv.max() == 1


@pytest.mark.parametrize("kwargs", [{"cube_size": -1}, {"cube_size": float("nan")}, {"clip": 1}, {"scale_bounds": "yes"}, {"face_ids": ["missing"]}])
def test_invalid_cube_projection_is_atomic(kwargs):
    p = placement("Cube")
    before = deepcopy(p.__dict__)
    with pytest.raises(ValueError):
        mesh_uv.cube_project(p, **kwargs)
    assert p.__dict__ == before


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


def test_pins_are_corner_attributes_and_survive_uv_edits_modifiers_and_reload():
    p=placement();mesh_uv.project(p,'planar_xz')
    before=mesh_uv.source(p);corner=before['faces'][0]['corners'][0]['id']
    mesh_uv.pin(p,[corner]);doc=mesh_uv.source(p)
    assert doc['schema_version']==3
    assert doc['faces'][0]['corners'][0]['pin'] is True
    expected=deepcopy(before);expected['schema_version']=3;expected['faces'][0]['corners'][0]['pin']=True
    assert doc==expected
    mesh_uv.transform(p,[corner],offset=[.1,0])
    assert mesh_uv.read(p)['faces'][0]['corners'][0]['pin']
    mesh_modifiers.add(p,'Subdivision')
    evaluated=mesh_edit.evaluate(p)
    assert evaluated.topology['schema_version']==3
    assert sum(c.get('pin',False) for f in evaluated.topology['faces'] for c in f['corners'])==1
    saved=mesh_document.capture([p]);mesh_document.restore(saved,[p])
    assert mesh_uv.read(p)['faces'][0]['corners'][0]['pin']
    mesh_uv.pin(p,[corner],False)
    assert not mesh_uv.read(p)['faces'][0]['corners'][0]['pin']


@pytest.mark.parametrize('kind',['Mirror','Array','Solidify'])
def test_pin_schema_is_preserved_by_retained_copy_and_shell_modifiers(kind):
    p=placement();mesh_uv.project(p,'planar_xz')
    corner=mesh_uv.read(p)['faces'][0]['corners'][0]['id'];mesh_uv.pin(p,[corner])
    mesh_modifiers.add(p,kind);result=mesh_edit.evaluate(p)
    assert result.topology['schema_version']==3
    assert sum(c.get('pin',False) for f in result.topology['faces'] for c in f['corners'])==2


def test_pinned_mesh_component_delete_keeps_new_schema_and_surviving_pins():
    p=placement('Plane',{'segments':2});mesh_uv.project(p,'planar_xz');doc=mesh_uv.source(p)
    corner=doc['faces'][0]['corners'][0]['id'];mesh_uv.pin(p,[corner])
    topology.select(p,'faces',[doc['faces'][-1]['id']]);topology.edit_selected(p,'delete')
    doc=mesh_uv.source(p)
    assert doc['schema_version']==3 and doc['faces'][0]['corners'][0]['pin']


@pytest.mark.parametrize('pin_value',[1,'yes',None])
def test_pin_schema_rejects_non_boolean_flags(pin_value):
    p=placement();mesh_uv.project(p,'planar_xz');doc=mesh_uv.source(p)
    doc['schema_version']=3;doc['faces'][0]['corners'][0]['pin']=pin_value
    with pytest.raises(ValueError):topology.compile(doc)


def test_pin_requires_defined_uv_and_rejects_old_schema_without_publication():
    p=placement();before=deepcopy(p.__dict__);doc=mesh_uv.source(p)
    corner=doc['faces'][0]['corners'][0]['id']
    with pytest.raises(ValueError):mesh_uv.pin(p,[corner])
    assert p.__dict__==before
    mesh_uv.project(p,'planar_xz');doc=mesh_uv.source(p);doc['faces'][0]['corners'][0]['pin']=True
    with pytest.raises(ValueError):topology.compile(doc)
