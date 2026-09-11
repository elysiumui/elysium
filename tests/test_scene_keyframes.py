from types import SimpleNamespace as NS
from copy import deepcopy
import pytest
from elysium.render import scene, scene_animation as animation


def placement():
    return NS(kind='Mesh3D',props={})


def test_legacy_transform_keys_preserve_linear_parent_local_evaluation():
    p=placement()
    animation.set_key(p,0)
    animation.set_key(p,72,{'rotation':[0,0,22]})
    assert all(set(k)=={'frame','transform'} for k in animation.tracks(p))
    assert scene.transform(animation.pose([p],36)[0])['rotation']==[0,0,11]
    assert scene.transform(animation.pose([p],100)[0])['rotation']==[0,0,22]


def test_channel_insertion_does_not_add_unrelated_keys_or_overwrite_other_axes():
    p=placement()
    animation.set_key(p,0,{'rotation':[10,20,30]},channels=['rotation.x'])
    animation.set_key(p,10,{'rotation':[50,60,70]},channels=['rotation.x'])
    animation.set_key(p,5,{'location':[4,5,6]},channels=['location.y'])
    pose=scene.transform(animation.pose([p],5)[0])
    assert pose['rotation']==[30,0,0] and pose['location']==[0,5,0]
    animation.set_key(p,0,{'rotation':[90,80,70]},channels=['rotation.z'])
    k=animation.tracks(p)[0]
    assert k['transform']['rotation']==[10,20,70]
    assert set(k['channels'])=={'rotation.x','rotation.z'}


def test_move_duplicate_delete_and_constant_interpolation_are_channel_isolated():
    p=placement()
    animation.set_key(p,0)
    animation.set_key(p,10,{'rotation':[10,20,30]})
    before=deepcopy(p.props)
    animation.edit_key(p,10,channels=['rotation.x'],target_frame=20)
    values=scene.transform(animation.pose([p],10)[0])
    assert values['rotation']==[5,20,30]
    animation.edit_key(p,0,channels=['rotation.y'],mode='CONSTANT')
    assert scene.transform(animation.pose([p],5)[0])['rotation']==[2.5,0,15]
    assert scene.transform(animation.pose([p],10)[0])['rotation'][1]==20
    animation.edit_key(p,20,channels=['rotation.x'],target_frame=30,duplicate=True)
    animation.edit_key(p,20,channels=['rotation.x'],delete=True)
    assert 20 not in [k['frame'] for k in animation.tracks(p)]
    assert scene.transform(animation.pose([p],15)[0])['rotation'][0]==5
    other=[c for c in animation.CHANNELS if c not in ('rotation.x','rotation.y')]
    for frame in (0,10):
        original=next(k for k in before['keys3d'] if k['frame']==frame)
        current=next(k for k in animation.tracks(p) if k['frame']==frame)
        assert all(current['transform'][c.split('.')[0]]['xyz'.index(c[-1])]==original['transform'][c.split('.')[0]]['xyz'.index(c[-1])] for c in other)


@pytest.mark.parametrize('changes',[
    {'target_frame':0}, {'target_frame':True}, {'target_frame':2.5},
    {'target_frame':-1}, {'target_frame':360001}, {'mode':'UNKNOWN'},
    {'duplicate':True}, {'channels':['unknown']},
])
def test_failed_key_edit_preserves_every_key(changes):
    p=placement();animation.set_key(p,0);animation.set_key(p,10)
    before=deepcopy(p.props)
    args={'channels':['rotation.x'],**changes}
    with pytest.raises(ValueError):animation.edit_key(p,10,**args)
    assert p.props==before


@pytest.mark.parametrize('change',[{'fps':0},{'fps':True},{'start':10,'end':5},{'loop':1},{'flight_seconds':float('nan')}])
def test_rejects_invalid_playback_settings(change):
    with pytest.raises(ValueError):animation.settings(change)
