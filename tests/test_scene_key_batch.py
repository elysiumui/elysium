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


def test_multi_object_keys_commit_together_and_preserve_curve_handles():
    a1=fixture();a1.entity_id='left';a2=fixture();a2.entity_id='right'
    a.set_handles(a1,10,'rotation.x',[-1,0],[1,.25]);before=[deepcopy(p.props) for p in (a1,a2)]
    chosen=[(p.entity_id,f,'rotation.x') for p in (a1,a2) for f in (10,11,12)]
    a.edit_object_keys([a1,a2],chosen,offset=5)
    assert [f for f,v,m in channel(a1,'rotation.x')]==[15,16,17]
    assert [f for f,v,m in channel(a2,'rotation.x')]==[15,16,17]
    assert next(k for k in a.tracks(a1) if k['frame']==15)['handles']['rotation.x']=={'left':[-1,0],'right':[1,.25]}
    assert channel(a1,'rotation.y')==channel(a2,'rotation.y')
    a.edit_object_keys([a1,a2],[(i,f+5,c) for i,f,c in chosen],offset=-5)
    for p,props in zip((a1,a2),before):
        baseline=deepcopy(p);baseline.props=props
        assert all(channel(p,c)==channel(baseline,c) for c in ('rotation.x','rotation.y','rotation.z'))
    assert a.tracks(a1)[0]['handles']['rotation.x']=={'left':[-1,0],'right':[1,.25]}


@pytest.mark.parametrize('failure',['collision','missing','locked','duplicate','bad frame'])
def test_multi_object_failure_leaves_every_source_unchanged(failure):
    a1=fixture();a1.entity_id='left';a2=fixture();a2.entity_id='right'
    chosen=[('left',12,'rotation.x'),('right',12,'rotation.x')]
    if failure=='collision':a.set_key(a2,13,channels=['rotation.x'])
    elif failure=='missing':chosen[1]=('missing',12,'rotation.x')
    elif failure=='locked':a2.props['selection_locked']=True
    elif failure=='duplicate':chosen.append(chosen[0])
    else:chosen[1]=('right',True,'rotation.x')
    before=deepcopy([a1.props,a2.props])
    with pytest.raises(ValueError):a.edit_object_keys([a1,a2],chosen,offset=1)
    assert [a1.props,a2.props]==before
