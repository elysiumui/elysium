from copy import deepcopy
import pytest
from test_scene_keyframes import placement
from elysium.render import scene, scene_animation as a, animation_curve as curve


def two_keys():
    p=placement();a.set_key(p,0,{'rotation':[0,0,0]},channels=['rotation.z']);a.set_key(p,100,{'rotation':[0,0,100]},channels=['rotation.z']);return p


def value(p,f):return scene.transform(a.pose([p],f)[0])['rotation'][2]


def test_horizontal_handles_produce_analytic_ease_and_retain_endpoints():
    p=two_keys();a.edit_key(p,0,channels=['rotation.z'],mode='BEZIER')
    for f in (0,1,25,50,75,99,100):
        t=f/100;assert value(p,f)==pytest.approx(100*(3*t*t-2*t*t*t),abs=1e-11)
    assert value(p,200)==100


def test_time_and_value_handles_are_independent_and_source_is_immutable():
    p=two_keys();a.set_handles(p,0,'rotation.z',[-10,0],[10,50]);a.set_handles(p,100,'rotation.z',[-10,-50],[10,0]);original=deepcopy(p.props)
    # At t=.5, both the symmetric cubic time and value are their midpoint.
    assert value(p,50)==pytest.approx(50,abs=1e-10)
    assert value(p,25)>25
    assert p.props==original


def test_key_and_batch_retiming_preserve_relative_handles_and_unrelated_axes():
    p=two_keys();a.set_handles(p,0,'rotation.z',[-10,2],[20,30]);a.set_key(p,0,channels=['rotation.x'])
    a.edit_key(p,0,channels=['rotation.z'],target_frame=10)
    assert a.tracks(p)[0].get('handles',{})=={}
    assert curve.handles(a.tracks(p),10,'rotation.z')=={'left':[-10,2],'right':[20,30]}
    a.edit_keys(p,[(10,'rotation.z'),(100,'rotation.z')],offset=20)
    assert curve.handles(a.tracks(p),30,'rotation.z')=={'left':[-10,2],'right':[20,30]}
    a.edit_keys(p,[(30,'rotation.z')],offset=10,duplicate=True)
    assert curve.handles(a.tracks(p),40,'rotation.z')==curve.handles(a.tracks(p),30,'rotation.z')


def test_overlong_handle_reach_is_limited_without_rewriting_authored_values():
    p=two_keys();a.set_handles(p,0,'rotation.z',[-1,0],[200,400]);original=deepcopy(p.props)
    # Compare equivalent explicitly shortened handle preserving its slope.
    q=deepcopy(p);a.set_handles(q,0,'rotation.z',[-1,0],[100,200])
    assert [value(p,f) for f in (1,25,50,75,99)]==[value(q,f) for f in (1,25,50,75,99)]
    assert p.props==original


@pytest.mark.parametrize('left,right',[( [1,0],[1,0]),([-1,0],[-1,0]),([-1,float('nan')],[1,0]),([-1],[1,0]),([-1,0],[1,True])])
def test_invalid_handles_are_atomic(left,right):
    p=two_keys();before=deepcopy(p.props)
    with pytest.raises(ValueError):a.set_handles(p,0,'rotation.z',left,right)
    assert p.props==before


def test_scale_curve_zero_crossing_rejected_before_mutation():
    p=placement();a.set_key(p,0,channels=['scale.x']);a.set_key(p,100,channels=['scale.x']);before=deepcopy(p.props)
    with pytest.raises(ValueError,match='nonzero between keys'):
        a.set_handles(p,0,'scale.x',[-10,0],[30,-10])
    assert p.props==before
    a.set_handles(p,0,'scale.x',[-10,0],[30,-.5])
    assert all(scene.transform(a.pose([p],f)[0])['scale'][0]>0 for f in range(101))


def test_nonfinite_control_point_rejected_before_mutation():
    p=two_keys();a.set_key(p,0,{'rotation':[0,0,1e308]},channels=['rotation.z']);before=deepcopy(p.props)
    with pytest.raises(ValueError,match='finite'):
        a.set_handles(p,0,'rotation.z',[-10,0],[30,1e308])
    assert p.props==before


@pytest.mark.parametrize('frame',[False,0.0,-1,360001])
def test_curve_handle_api_requires_an_integer_frame(frame):
    p=two_keys();before=deepcopy(p.props)
    with pytest.raises(ValueError,match='integer'):
        a.set_handles(p,frame,'rotation.z',[-1,0],[1,0])
    assert p.props==before
