from copy import deepcopy
from types import SimpleNamespace
import math

import numpy as np
import pytest

from elysium.render import pbr, primitives, scene, scene_lighting as lights
from elysium.aether.tools import scene as commands


@pytest.mark.parametrize("bad", [{"power": -1}, {"power": True}, {"color": [1, 2, 0]},
                                 {"size": 0}, {"position": [0, float('nan'), 0]},
                                 {"rotation": [0, 0]}, {"type": "spot"}, {"foo": 1}])
def test_invalid_edits_are_atomic(bad):
    window = SimpleNamespace()
    identity = lights.add(window)["light_id"]
    before = deepcopy(window.__dict__)
    with pytest.raises(ValueError):
        lights.update(window, identity, bad)
    assert window.__dict__ == before


def test_public_light_lifecycle_keeps_stable_ids_and_studio_toggle():
    window = SimpleNamespace()
    session = SimpleNamespace(designer=SimpleNamespace(window_doc=window))
    a = commands.light_add(session, {"name": "Sun"})["light_id"]
    b = commands.light_add(session, {"type": "point"})["light_id"]
    commands.light_remove(session, a)
    commands.light_update(session, b, {"name": "Renamed", "power": 32})
    commands.lighting_set(session, enabled=False)
    assert lights.environment(window.scene_lighting).authored_lights is None
    commands.lighting_set(session, enabled=True, ambient=[.1, .2, .3])
    state = commands.lighting_get(session)["lighting"]
    assert state['lights'][0]['id'] == b and state['lights'][0]['power'] == 32
    assert state['ambient'] == [.1, .2, .3]
    assert commands.light_add(session, {})['light_id'] not in (a, b)


def test_point_inverse_square_and_sun_distance_independence():
    points = np.array([[0., 1., 0.], [0., 2., 0.]])
    _, values, distances = next(lights.samples(lights.light({'type': 'point', 'position': [0, 0, 0], 'power': 4 * math.pi}), points))
    np.testing.assert_allclose(values[:, 0], [1, .25])
    np.testing.assert_array_equal(distances, [1, 2])
    directions, values, distances = next(lights.samples(lights.light({'type': 'sun', 'power': 2, 'rotation': [90, 0, 0]}), points))
    np.testing.assert_allclose(directions, [[0, 0, 1]] * 2, atol=1e-6)
    np.testing.assert_array_equal(values, np.full((2, 3), 2))
    assert np.isinf(distances).all()


def test_area_is_one_sided_and_matches_far_field_flux():
    item = lights.light({'type': 'area', 'position': [0, 0, 0], 'size': 2, 'power': math.pi})
    samples = list(lights.samples(item, np.array([[0., -100., 0.], [0., 100., 0.]])))
    assert len(samples) == 16
    values = sum(v for _, v, _ in samples)
    assert values[0, 0] == pytest.approx(1e-4, rel=2e-4)
    np.testing.assert_array_equal(values[1], [0, 0, 0])


def blocker(y):
    verts = np.array([[-2, y, -2], [2, y, -2], [2, y, 2], [-2, y, 2]], np.float32)
    obj = pbr.MeshObject(pbr.Mesh(verts, np.array([[0, 1, 2], [0, 2, 3]])), [pbr.Material()])
    return obj, verts, pbr._cached_bvh_for(obj, verts)


@pytest.mark.parametrize('kind', ['sun', 'point', 'area'])
def test_occluder_blocks_direct_light_but_geometry_behind_finite_light_does_not(kind):
    state = SimpleNamespace()
    lights.add(state, {'type': kind, 'position': [0, 2, 0], 'size': .2, 'power': 20})
    env = lights.environment(state.scene_lighting)
    def direct(y):
        obj, verts, bvh = blocker(y)
        return lights.direct(env, np.array([[.1, 0., 0.]]), np.array([[0., 1., 0.]]), np.array([[0., 1., 0.]]), obj.materials[0], None, obj, verts, bvh)
    np.testing.assert_array_equal(direct(1), [[0, 0, 0]])
    if kind != 'sun':
        assert direct(3).min() > 0
    assert direct(-1).min() > 0


@pytest.mark.parametrize('kind', ['sun', 'point', 'area'])
def test_authored_lights_change_preview_and_pathtrace_and_disable_is_dark(kind):
    p = SimpleNamespace(kind='Mesh3D', props={}, visible=True)
    primitives.bind(p, 'Cube')
    window = SimpleNamespace()
    identity = lights.add(window, {'type': kind, 'power': 50, 'position': [0, 2, 3], 'rotation': [90, 0, 0]})['light_id']
    source = deepcopy(p.props)
    def preview():
        return np.frombuffer(scene.render([p], 24, 24, yaw=0, pitch=0, grid=False, shading='material', lighting=window.scene_lighting)[0], np.uint8).reshape(-1, 4)
    def trace():
        obj, _ = scene.compose([p], materials=True)
        return np.frombuffer(pbr.render_path_traced(12, 12, obj, lights.environment(window.scene_lighting), samples=1, max_bounces=0, cam_yaw=0, cam_pitch=0, denoise=False), np.uint8).reshape(-1, 4)
    assert preview()[:, :3].max() > 0 and trace()[:, :3].max() > 0
    lights.update(window, identity, {'enabled': False})
    assert preview()[:, :3].max() == 0 and trace()[:, :3].max() == 0
    assert p.props == source


def test_maximum_light_count_and_bad_restore_do_not_mutate():
    w = SimpleNamespace()
    for _ in range(32):
        lights.add(w)
    before = deepcopy(w.scene_lighting)
    with pytest.raises(ValueError, match='32'):
        lights.add(w)
    assert w.scene_lighting == before
    invalid = deepcopy(before)
    invalid['lights'][1]['id'] = invalid['lights'][0]['id']
    with pytest.raises(ValueError, match='identity'):
        lights.settings(invalid)
