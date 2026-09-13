from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from elysium.render import layout_lighting, mesh_materials, pbr, primitives, scene, scene_lighting


def fixture():
    p = SimpleNamespace(kind='Mesh3D', props={}, name='Cube', entity_id='cube', visible=True)
    primitives.bind(p, 'Cube')
    w = SimpleNamespace(scene_lighting=scene_lighting.settings(), studio='Default Soft Studio')
    return p, w


def test_layout_context_is_frozen_and_changes_with_lights_and_world_transform():
    p, w = fixture()
    a = layout_lighting.context(p, w, [p]); saved = deepcopy(a)
    light = scene_lighting.add(w, {'type': 'point', 'position': [0, 0, 3], 'power': 100})
    b = layout_lighting.context(p, w, [p])
    assert layout_lighting.key(a) != layout_lighting.key(b)
    scene.update(p, {'location': [2, 0, 0]})
    c = layout_lighting.context(p, w, [p])
    assert layout_lighting.key(b) != layout_lighting.key(c)
    assert a == saved


def test_layout_world_geometry_matches_composed_scene_with_reflected_parent():
    p, w = fixture()
    parent = SimpleNamespace(kind='SceneGroup', props={}, name='Parent', entity_id='parent', visible=True)
    scene.update(parent, {'scale': [-2, 3, .5], 'rotation': [20, 35, 0], 'location': [4, 0, 0]})
    scene.set_parent([parent, p], p, parent, keep_world=False)
    values = layout_lighting.context(p, w, [parent, p])
    obj, _, target = layout_lighting.prepare(mesh_materials.render_object(p), values)
    expected, _ = scene.compose([parent, p], materials=True)
    np.testing.assert_allclose(obj.mesh.verts, expected.mesh.verts, atol=1e-7)
    np.testing.assert_array_equal(obj.mesh.faces, expected.mesh.faces)
    np.testing.assert_allclose(target, scene.world_matrices([parent, p])[1][:3, 3])


def test_layout_light_changes_render_and_translation_preserves_relative_light_geometry():
    p, w = fixture()
    scene_lighting.configure(w, enabled=True, ambient=[0, 0, 0])
    def render():
        obj, env, target = layout_lighting.prepare(mesh_materials.render_object(p), layout_lighting.context(p, w, [p]))
        return np.frombuffer(pbr.render_mesh(32, 32, obj, env, cam_target=target, cam_yaw=0, cam_pitch=0, transparent_bg=True), np.uint8).reshape(32, 32, 4)
    dark = render()
    assert dark[:, :, :3].max() == 0 and dark[:, :, 3].max() > 0
    added = scene_lighting.add(w, {'type': 'point', 'position': [0, 0, 3], 'power': 100})
    bright = render()
    assert bright[:, :, :3].max() > 40
    scene.update(p, {'location': [2, 0, 0]})
    assert not np.array_equal(render(), bright)
    scene_lighting.update(w, added['light_id'], {'position': [2, 0, 3]})
    np.testing.assert_array_equal(render(), bright)
