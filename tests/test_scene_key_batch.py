from copy import deepcopy
import pytest
from test_scene_keyframes import placement
from elysium.render import scene, scene_animation as a


def fixture():
    p=placement()
    for f in (10,11,12):
        a.set_key(p,f,{'rotation':[f,.1234567891234567,f*2]},channels=['rotation.x','rotation.y','rotation.z'])
    a.edit_key(p,11,channels=['rotation.x'],mode='CONSTANT')
    return p


def channel(p,c):
    group,axis=c.split('.')
    return [(k['frame'],k['transform'][group]['xyz'.index(axis)],a.interpolation(k,c)) for k in a.tracks(p) if c in a.key_channels(k)]


def test_adjacent_keys_move_atomically_across_vacated_sources_and_keep_other_axes():
    p=fixture();z=channel(p,'rotation.z');y=channel(p,'rotation.y')
    a.edit_keys(p,[(10,'rotation.x'),(11,'rotation.x'),(12,'rotation.x')],offset=1)
    assert channel(p,'rotation.x')==[(11,10,'LINEAR'),(12,11,'CONSTANT'),(13,12,'LINEAR')]
    assert channel(p,'rotation.z')==z and channel(p,'rotation.y')==y
    assert scene.transform(a.pose([p],12.5)[0])['rotation'][0]==11


def test_multiple_channels_copy_interpolate_delete_preserve_exact_values():
    p=fixture();original=deepcopy(p.props);chosen=[(10,'rotation.x'),(11,'rotation.y')]
    a.edit_keys(p,chosen,offset=100,duplicate=True)
    assert channel(p,'rotation.y')[-1]==(111,.1234567891234567,'LINEAR')
    copied=[(f+100,c) for f,c in chosen];a.edit_keys(p,copied,mode='CONSTANT')
    assert all(a.interpolation(k,c)=='CONSTANT' for k in a.tracks(p) for f,c in copied if f==k['frame'])
    a.edit_keys(p,copied,delete=True)
    assert p.props==original


@pytest.mark.parametrize('chosen,args',[
    ([(10,'rotation.x'),(11,'rotation.x')],{'offset':1}),
    ([(10,'rotation.x'),(11,'rotation.x'),(12,'rotation.x')],{'offset':1,'duplicate':True}),
    ([(10,'rotation.x')],{'offset':-11}), ([(10,'rotation.x')],{'offset':360000}),
    ([(10,'rotation.x')],{'offset':True}), ([(10,'rotation.x')],{'duplicate':True}),
    ([(10,'rotation.x')],{'delete':True,'offset':1}),
    ([(10,'rotation.x')],{'mode':'UNKNOWN'}), ([],{}),
    ([(10,'rotation.x'),(99,'rotation.y')],{}),
    ([(10,'rotation.x'),(10,'rotation.x')],{}),
])
def test_batch_failure_has_no_partial_mutation(chosen,args):
    p=fixture();before=deepcopy(p.props)
    with pytest.raises(ValueError):a.edit_keys(p,chosen,**args)
    assert p.props==before
