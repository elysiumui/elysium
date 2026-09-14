from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from elysium.render import scene_actions as actions, scene_animation as animation
from elysium.aether._headless import AppWindow


def fixture():
    w=AppWindow();p=NS(entity_id='wing',kind='SceneGroup',props={})
    animation.set_key(p,0,{'rotation':[0,0,0]},channels=['rotation.z'])
    animation.set_key(p,72,{'rotation':[0,0,22]},channels=['rotation.z'])
    animation.set_handles(p,0,'rotation.z',[-24,0],[24,0])
    return w,[p]


def test_actions_capture_live_edits_switch_timing_and_retain_curves_after_reload():
    w,ps=fixture();original=deepcopy(ps[0].props);before=deepcopy(w.to_json())
    assert actions.read(w,ps)['active']=='action:default' and w.to_json()==before
    actions.rename(w,ps,'action:default','Deployment')
    actions.create(w,ps,'Idle',start=100,end=160)
    idle=w.scene_actions['active'];assert not animation.tracks(ps[0]) and w.scene_frame==100
    animation.set_key(ps[0],100,{'location':[0,3,0]},channels=['location.y'])
    idle_keys=animation.tracks(ps[0]);w.scene_timeline['fps']=24
    # Saved active keys need no synchronization hook: live placement keys win.
    w=AppWindow.from_json(w.to_json())
    actions.switch(w,ps,'action:default')
    assert ps[0].props['keys3d']==original['keys3d'] and w.scene_frame==0
    actions.switch(w,ps,idle)
    assert animation.tracks(ps[0])==idle_keys and w.scene_timeline['fps']==24
    assert w.scene_timeline['flight_seconds']==3


def test_duplicate_is_independent_and_active_removal_restores_previous_clip():
    w,ps=fixture();original=animation.tracks(ps[0])
    actions.create(w,ps,'Copy',duplicate=True)
    copy_id=w.scene_actions['active'];assert animation.tracks(ps[0])==original
    animation.edit_key(ps[0],72,channels=['rotation.z'],target_frame=100)
    actions.remove(w,ps,copy_id)
    assert animation.tracks(ps[0])==original and w.scene_actions['active']=='action:default'


@pytest.mark.parametrize('operation',[
    lambda w,p:actions.create(w,p,' default '),lambda w,p:actions.create(w,p,' '),
    lambda w,p:actions.create(w,p,'Bad',start=10,end=1),
    lambda w,p:actions.switch(w,p,'missing'),lambda w,p:actions.remove(w,p,'action:default'),
    lambda w,p:actions.rename(w,p,'action:default',''),
])
def test_invalid_actions_are_atomic(operation):
    w,ps=fixture();before=deepcopy((w.to_json(),ps))
    with pytest.raises(ValueError):operation(w,ps)
    assert (w.to_json(),ps)==before


def test_missing_object_switch_is_atomic_and_can_remove_broken_clip():
    w,ps=fixture();actions.create(w,ps,'Idle');ps.clear();before=deepcopy(w.to_json())
    with pytest.raises(ValueError,match='missing objects'):actions.switch(w,ps,'action:default')
    assert w.to_json()==before
    actions.remove(w,ps,'action:default');assert len(w.scene_actions['items'])==1


def test_switch_validates_unkeyed_objects_before_committing_any_keys():
    w,ps=fixture();actions.create(w,ps,'Idle')
    ps.append(NS(entity_id='bad',kind='SceneGroup',props={'transform3d':{'scale':[0,1,1]}}))
    before=deepcopy((w.to_json(),ps))
    with pytest.raises(ValueError,match='Scale'):actions.switch(w,ps,'action:default')
    assert (w.to_json(),ps)==before


def test_idle_output_duration_rounds_up_by_less_than_one_frame():
    from elysium.render.scene_export import idle_clip
    w,ps=fixture();actions.create(w,ps,'Idle',start=10,end=11);identity=w.scene_actions['active']
    w.scene_timeline['fps']=30
    clip,count=idle_clip(w,ps,identity,24)
    assert count==2 and 0<=count/24-2/30<1/24
    assert clip['timing']['fps']==30
