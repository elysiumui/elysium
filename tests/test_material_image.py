from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from elysium.render import material_image, mesh_document, mesh_materials, pbr, primitives, scene
from PIL import Image


def checker(path):
    data = np.array(
        [[[255, 0, 0, 255], [0, 255, 0, 255]], [[0, 0, 255, 255], [255, 255, 255, 0]]],
        dtype=np.uint8,
    )
    Image.fromarray(data).save(path)
    return data


def cube():
    p = SimpleNamespace(kind="Mesh3D", props={}, visible=True, name="Cube", entity_id="cube")
    primitives.bind(p, "Cube")
    return p


def test_image_owns_source_after_deletion_and_uses_srgb_closest_repeat(tmp_path):
    path = tmp_path / "source.png"
    data = checker(path)
    p = cube()
    slot = mesh_materials.add(p, "Image", {"base_color": [1, 1, 1]})["slot_id"]
    source = deepcopy(mesh_document.resolve(p.mesh_kind).topology)
    mesh_materials.set_image(p, slot, str(path))
    path.unlink()
    surfaces, _ = mesh_materials.render_materials(p, mesh_document.resolve(p.mesh_kind))
    surface = surfaces[-1]
    np.testing.assert_array_equal(surface.albedo_map, data)
    uv = np.array(
        [
            [0.25, 0.75],
            [0.75, 0.75],
            [0.25, 0.25],
            [0.75, 0.25],
            [1.25, -0.25],
            [-0.25, 1.25],
            [0, 0],
            [1, 1],
        ]
    )
    sample = pbr._sample_texture(surface.albedo_map, uv, closest_repeat=True)
    np.testing.assert_array_equal(sample, data[[0, 0, 1, 1, 0, 1, 1, 1], [0, 1, 0, 1, 0, 1, 0, 0]])
    assert not surface.albedo_alpha_cutout and surface.albedo_sampling == "closest_repeat"
    assert mesh_document.resolve(p.mesh_kind).topology == source
    before = mesh_materials.read(p)
    mesh_materials.update(p, slot, values={"roughness": 0.9})
    assert (
        mesh_materials.read(p)["table"]["slots"][-1]["albedo_image"]
        == before["table"]["slots"][-1]["albedo_image"]
    )
    mesh_materials.set_image(p, slot, "")
    assert "albedo_image" not in mesh_materials.read(p)["table"]["slots"][-1]


@pytest.mark.parametrize(
    "case", ["missing", "text", "oversized", "animated", "bad_digest", "bad_data", "stale_slot"]
)
def test_image_rejection_keeps_source_and_slots_atomic(tmp_path, case):
    p = cube()
    slot = mesh_materials.add(p)["slot_id"]
    path = tmp_path / "input.png"
    checker(path)
    before = deepcopy(p.__dict__)
    if case == "missing":
        path.unlink()
    elif case == "text":
        path.write_text("not an image")
    elif case == "oversized":
        Image.new("RGB", (2049, 1)).save(path)
    elif case == "animated":
        Image.new("RGB", (2, 2), "red").save(
            path, save_all=True, append_images=[Image.new("RGB", (2, 2), "blue")]
        )
    if case in ("bad_digest", "bad_data"):
        descriptor = material_image.import_image(path)
        descriptor["sha256" if case == "bad_digest" else "png_base64"] = "x" * 64
        with pytest.raises(ValueError):
            material_image.pixels(descriptor)
    else:
        with pytest.raises(ValueError):
            mesh_materials.set_image(p, "missing" if case == "stale_slot" else slot, str(path))
    assert p.__dict__ == before


def test_image_affects_only_assigned_faces_and_preserves_opacity(tmp_path):
    path = tmp_path / "red.png"
    Image.new("RGBA", (2, 2), (255, 0, 0, 0)).save(path)
    p = cube()
    slot = mesh_materials.add(p, "Image", {"base_color": [1, 1, 1], "specular": 0, "roughness": 1})[
        "slot_id"
    ]
    mesh_materials.set_image(p, slot, str(path))
    doc = mesh_document.resolve(p.mesh_kind).topology
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    face = next(
        f["id"] for f in doc["faces"] if all(points[c["vertex"]][2] > 0 for c in f["corners"])
    )
    mesh_materials.assign(p, [face], slot)
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
    color = np.frombuffer(rgba, np.uint8).reshape(48, 48, 4)[24, 24].astype(int)
    assert color[0] > color[1] + 50 and color[0] > color[2] + 50 and color[3] == 255
    _, indices = mesh_materials.render_materials(p, mesh_document.resolve(p.mesh_kind))
    assert np.count_nonzero(indices == 1) == 2 and np.count_nonzero(indices == 0) == 10


def test_clear_material_removes_owned_surfaces_and_images(tmp_path):
    from elysium.aether.tools.material import material_clear

    p = cube()
    p.props["keep"] = "other object data"
    path = tmp_path / "grid.png"
    checker(path)
    slot = mesh_materials.add(p)["slot_id"]
    mesh_materials.set_image(p, slot, str(path))
    session = SimpleNamespace(lookup=lambda identity: p, designer=SimpleNamespace())
    result = material_clear(session, "cube")
    assert "materials3d" in result["cleared"]
    assert p.props["keep"] == "other object data"
    assert "materials3d" not in p.props


@pytest.mark.parametrize("channel", ["roughness", "metallic"])
def test_scalar_image_is_linear_red_and_multiplies_only_its_channel(tmp_path, channel):
    path=tmp_path/'data.png'
    # Non-grey pixels detect accidental luminance/green/blue or sRGB decoding.
    data=np.array([[[64,220,255,0],[192,0,30,255]]],dtype=np.uint8)
    Image.fromarray(data).save(path)
    p=cube(); slot=mesh_materials.add(p,values={channel:.5})['slot_id']
    source=deepcopy(mesh_document.resolve(p.mesh_kind).topology)
    mesh_materials.set_image(p,slot,str(path),channel)
    path.unlink()
    surface=mesh_materials.render_materials(p,mesh_document.resolve(p.mesh_kind))[0][-1]
    uv=np.array([[.25,.5],[.75,.5],[1.25,-.5],[-.25,1.5]])
    values=pbr._sample_material_textures(surface,uv)
    assert set(values)=={channel}
    np.testing.assert_allclose(values[channel],np.array([64,192,64,192])/255*.5,atol=1e-7)
    assert mesh_document.resolve(p.mesh_kind).topology==source
    assert not surface.albedo_alpha_cutout
    mesh_materials.set_image(p,slot,'',channel)
    surface=mesh_materials.render_materials(p,mesh_document.resolve(p.mesh_kind))[0][-1]
    assert pbr._sample_material_textures(surface,uv)=={}


def test_multiple_owned_channels_preserve_each_other_and_invalidate_preview(tmp_path):
    p=cube();slot=mesh_materials.add(p,values={'roughness':1,'metallic':1})['slot_id']
    path=tmp_path/'channels.png';checker(path)
    keys=[]
    for channel in mesh_materials.IMAGE_CHANNELS:
        mesh_materials.set_image(p,slot,str(path),channel)
        keys.append(mesh_materials.preview_key(p))
    assert len(set(keys))==3
    before=mesh_materials.table(p)['slots'][-1]
    mesh_materials.set_image(p,slot,'','roughness')
    after=mesh_materials.table(p)['slots'][-1]
    assert 'roughness_image' not in after
    assert after['albedo_image']==before['albedo_image'] and after['metallic_image']==before['metallic_image']
    state=deepcopy(p.__dict__)
    with pytest.raises(ValueError):mesh_materials.set_image(p,slot,str(path),'unknown')
    assert p.__dict__==state


@pytest.mark.parametrize('channel',['roughness','metallic'])
def test_scalar_image_changes_actual_render(tmp_path,channel):
    p=cube();slot=mesh_materials.add(p,values={'roughness':1,'metallic':1,'base_color':[.8,.3,.1]})['slot_id']
    mesh_materials.assign(p,[f['id'] for f in mesh_document.resolve(p.mesh_kind).topology['faces']],slot)
    def render():return scene.render([p],48,48,yaw=0,pitch=0,projection='orthographic',ortho_scale=3,grid=False,shading='material')[0]
    before=render();path=tmp_path/'black.png';Image.new('RGB',(2,2),'black').save(path)
    mesh_materials.set_image(p,slot,str(path),channel)
    assert render()!=before
    mesh_materials.set_image(p,slot,'',channel)
    assert render()==before
