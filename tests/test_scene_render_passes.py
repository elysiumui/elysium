from copy import deepcopy
from types import SimpleNamespace
import json
import threading

import numpy as np
import pytest

from elysium.render import pbr, primitives, scene, scene_lighting, scene_render_job


def cube():
    p = SimpleNamespace(kind='Mesh3D', props={}, visible=True, name='Cube', entity_id='cube')
    primitives.bind(p, 'Cube')
    return p


@pytest.mark.parametrize('authored', [False, True])
@pytest.mark.parametrize('metallic,coat', [(0, 0), (1, 0), (.3, 1)])
def test_radiance_passes_reconstruct_beauty_and_metal_has_no_diffuse(authored, metallic, coat):
    p = cube()
    from elysium.render import mesh_materials, mesh_document
    slot = mesh_materials.add(p, values={'metallic': metallic, 'clear_coat': coat, 'emissive': [.2, .3, .4]})['slot_id']
    mesh_materials.assign(p, [f['id'] for f in mesh_document.resolve(p.mesh_kind).topology['faces']], slot)
    w = SimpleNamespace()
    if authored:
        scene_lighting.add(w, {'type': 'area', 'power': 50, 'rotation': [90, 0, 0], 'position': [0, 2, 3]})
    passes = {}
    scene.render([p], 32, 32, yaw=0, pitch=0, shading='material', grid=False,
                 lighting=getattr(w, 'scene_lighting', None), pass_output=passes)
    np.testing.assert_allclose(passes['beauty_linear'], passes['diffuse'] + passes['specular'] + passes['emission'], atol=2e-6)
    if metallic == 1:
        np.testing.assert_array_equal(passes['diffuse'], 0)
    mask = passes['mask']
    np.testing.assert_allclose(passes['emission'][mask], np.broadcast_to([.2, .3, .4], (mask.sum(), 3)), atol=1e-7)


def test_world_normals_and_camera_axis_depth_are_geometric_not_beauty_tints():
    p = cube()
    scene.update(p, {'location': [0, 0, 1]})
    passes = {}
    scene.render([p], 21, 21, target=[0, 0, 1], distance=6, yaw=0, pitch=0,
                 projection='orthographic', ortho_scale=4, grid=False, shading='material', pass_output=passes)
    # Default cube spans -1..1, translated front face z=2; camera z=7.
    assert passes['depth'][10, 10] == pytest.approx(5, abs=1e-6)
    np.testing.assert_allclose(passes['normal'][10, 10], [0, 0, 1], atol=1e-6)
    assert np.isinf(passes['depth'][0, 0]) and not passes['mask'][0, 0]
    before = deepcopy(passes)
    p.pbr_emissive = (40, 0, 0)
    scene.render([p], 21, 21, target=[0, 0, 1], distance=6, yaw=0, pitch=0,
                 projection='orthographic', ortho_scale=4, grid=False, shading='material', pass_output=passes)
    for key in ('normal', 'depth', 'mask'):
        np.testing.assert_array_equal(passes[key], before[key])
    assert not np.array_equal(passes['beauty_linear'], before['beauty_linear'])


def test_empty_scene_passes_have_no_sentinel_geometry():
    passes = {}
    scene.render([], 16, 16, shading='material', grid=False, pass_output=passes)
    assert not passes['mask'].any() and np.isinf(passes['depth']).all()
    for key in ('normal', 'diffuse', 'specular', 'emission', 'beauty_linear'):
        assert not passes[key].any()


class Window(SimpleNamespace):
    def to_json(self):
        return deepcopy(self.__dict__)


def fixture():
    p = cube()
    p.to_json = lambda: {k: v for k, v in p.__dict__.items() if k != 'to_json'}
    w = Window(scene_camera=scene.camera(), scene_frame=0)
    scene_lighting.add(w, {'type': 'sun', 'power': 3})
    return [p], w


def test_render_job_writes_real_passes_and_preserves_source(tmp_path):
    placements, window = fixture()
    before = deepcopy(placements[0].props)
    output = tmp_path / 'render'
    scene_render_job.render(placements, window, output, size=24, start=0, end=1)
    manifest = json.loads((output / 'manifest.json').read_text())
    assert len(manifest['frames']) == 2 and manifest['fps'] == 60
    arrays = np.load(output / 'frame-0000-passes.npz')
    np.testing.assert_allclose(arrays['beauty_linear'], arrays['diffuse'] + arrays['specular'] + arrays['emission'], atol=2e-6)
    assert arrays['depth'].dtype == np.float32 and np.isinf(arrays['depth']).any()
    assert placements[0].props == before
    with pytest.raises(ValueError, match='exists'):
        scene_render_job.render(placements, window, output, size=24)


@pytest.mark.parametrize('cancel', [False, True])
def test_failure_or_cancellation_discards_staged_files(tmp_path, monkeypatch, cancel):
    placements, window = fixture()
    output = tmp_path / 'render'
    keep = tmp_path / 'keep.txt'
    keep.write_text('untouched')
    calls = []
    actual = scene.render
    def render(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2 and not cancel:
            raise RuntimeError('injected frame failure')
        return actual(*args, **kwargs)
    monkeypatch.setattr(scene, 'render', render)
    with pytest.raises(InterruptedError if cancel else RuntimeError):
        scene_render_job.render(placements, window, output, size=16, start=0, end=2,
                                cancelled=lambda: cancel and len(calls) >= 1)
    assert not output.exists() and list(tmp_path.iterdir()) == [keep]
    assert keep.read_text() == 'untouched'


def test_job_reports_failure_and_rejects_concurrent_start(tmp_path, monkeypatch):
    placements, window = fixture()
    d = SimpleNamespace(placements=placements, window_doc=window)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    def fail(*args, **kwargs):
        entered.set()
        release.wait(2)
        raise OSError('disk unavailable')
    monkeypatch.setattr(scene_render_job, 'render', fail)
    scene_render_job.start(d, str(tmp_path / 'failed'), size=16)
    assert entered.wait(2)
    with pytest.raises(ValueError, match='already running'):
        scene_render_job.start(d, str(tmp_path / 'second'), size=16)
    scene_render_job.cancel(d)
    assert scene_render_job.status(d)['cancellation_requested']
    release.set()
    # A bounded join-like wait for the worker's error publication.
    for _ in range(100):
        if scene_render_job.status(d)['status'] != 'running':
            break
        finished.wait(.01)
    assert scene_render_job.status(d)['status'] == 'failed'
    assert 'disk unavailable' in scene_render_job.status(d)['error']


@pytest.mark.parametrize('state', ['failed', 'cancelled'])
def test_public_status_keeps_job_error_inside_job_envelope(state):
    from elysium.aether.tools import scene as commands
    d = SimpleNamespace(_scene_render_job={'status': state, 'error': 'job diagnostic'})
    session = SimpleNamespace(designer=d)
    result = commands.render_status(session)
    assert 'error' not in result
    assert result['job']['status'] == state and result['job']['error'] == 'job diagnostic'


@pytest.mark.parametrize('channels', [[], ['normal', 'depth']])
def test_png_selection_does_not_discard_numeric_data(tmp_path, channels):
    objects, window = fixture()
    output = tmp_path / 'selected'
    scene_render_job.render(objects, window, output, size=16, channels=channels)
    assert {p.stem.split('-')[-1] for p in output.glob('*.png')} == set(channels)
    arrays = np.load(output / 'frame-0000-passes.npz')
    assert {'beauty_linear', 'diffuse', 'specular', 'normal', 'depth'} <= set(arrays)
    with pytest.raises(ValueError):
        scene_render_job.render(objects, window, tmp_path / 'bad', size=16, channels=['normal', 'normal'])
    assert not (tmp_path / 'bad').exists()
