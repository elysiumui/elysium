"""Native .esk documents retain authoring data through the CLI Aether loader."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from elysium.aether._headless import HeadlessDesigner, Placement, AnimState
from elysium.render import mesh_document, pbr, primitives, scene


def project(tmp_path):
    d = HeadlessDesigner.from_skin(tmp_path / 'native.esk')
    p = Placement(kind='Mesh3D', name='Authored Cube')
    mesh_document.bind(p, primitives.build('Cube', {'size':2})[0], label='Owned')
    p.states = [AnimState(name='deployed', mesh_flap_target=.8)]
    p.props['authoring_extension'] = {'nested':[1,2,3]}
    d.placements=[p]
    d.window_doc.scene_view=True
    d.window_doc.scene_camera=scene.camera({'yaw':.7,'distance':6})
    d.window_doc.scene_shading='material'
    d.save_layout()
    data=json.loads((d.skin_path/'designer_layout.json').read_text())
    data['window']['future_units']={'unit':'meters'}
    data['placements'][0]['mesh']['future_option']={'keep':True}
    data['placements'][0]['points']=[[1,2],[3,4]]
    data['future_document_field']={'value':7}
    (d.skin_path/'designer_layout.json').write_text(json.dumps(data))
    return d.skin_path,data


def test_native_geometry_scene_and_nested_fields_survive_clean_load_save(tmp_path):
    path,before=project(tmp_path)
    key=before['placements'][0]['mesh']['kind']
    pbr.MESH_LIBRARY.pop(key)
    d=HeadlessDesigner.from_skin(path)
    assert d.placements[0].mesh_kind==key
    assert len(mesh_document.resolve(key).topology['vertices'])==8
    assert d.placements[0].states[0].mesh_flap_target==.8
    assert d.window_doc.scene_camera==before['window']['scene_camera']
    assert d.window_doc.scene_shading=='material'
    d.save_layout()
    after=json.loads((path/'designer_layout.json').read_text())
    assert after['mesh_document']==before['mesh_document']
    assert after['window']==before['window']
    assert after['placements']==before['placements']
    assert after['future_document_field']==before['future_document_field']


def test_native_nested_values_override_legacy_flat_fields_and_emit_edits(tmp_path):
    path,data=project(tmp_path)
    raw=data['placements'][0]
    raw['mesh_kind']='Sphere'
    raw['pbr_roughness']=.9
    raw['pbr']['roughness']=.3
    (path/'designer_layout.json').write_text(json.dumps(data))
    d=HeadlessDesigner.from_skin(path)
    p=d.placements[0]
    assert p.mesh_kind==raw['mesh']['kind']
    assert p.pbr_roughness==.3
    p.pbr_roughness=.6
    p.mesh_roll=.4
    d.save_layout()
    written=json.loads((path/'designer_layout.json').read_text())['placements'][0]
    assert written['pbr']['roughness']==.6
    assert written['mesh']['roll']==.4
    assert 'pbr_roughness' not in written and 'mesh_kind' not in written


def test_canonical_runtime_document_is_not_overwritten_by_authoring_save(tmp_path):
    path,_=project(tmp_path)
    runtime=path/'document.json';runtime.write_bytes(b'{"approved_runtime":"keep"}')
    before=runtime.read_bytes()
    HeadlessDesigner.from_skin(path).save_layout()
    assert runtime.read_bytes()==before
    assert (path/'document.designer.json').is_file()


def test_corrupt_mesh_load_preserves_active_document(tmp_path):
    path,data=project(tmp_path)
    d=HeadlessDesigner.from_skin(path)
    before=(d.window_doc,d.placements)
    data['mesh_document']['assets']={}
    (path/'designer_layout.json').write_text(json.dumps(data))
    with pytest.raises(ValueError,match='missing referenced'):
        d.load_layout()
    assert d.window_doc is before[0] and d.placements is before[1]


def test_bad_save_does_not_truncate_existing_layout(tmp_path):
    path,_=project(tmp_path)
    d=HeadlessDesigner.from_skin(path)
    before=(path/'designer_layout.json').read_bytes()
    d.placements[0].props['bad']=float('nan')
    with pytest.raises(ValueError):
        d.save_layout()
    assert (path/'designer_layout.json').read_bytes()==before
    assert not list(path.glob('.designer_layout.json.*'))


def test_unknown_fields_remain_data_without_shadowing_methods():
    raw={'kind':'Card','to_json':'untrusted-data','__class__':'not-a-class','states':[{'name':'rest','future':4}]}
    p=Placement.from_json(raw)
    assert callable(p.to_json)
    assert p.to_json()['to_json']=='untrusted-data'
    assert p.to_json()['__class__']=='not-a-class'
    assert p.to_json()['states'][0]['future']==4


def test_late_write_failure_restores_source_and_preview_bytes(tmp_path, monkeypatch):
    import elysium.aether._headless as headless
    path,_=project(tmp_path)
    d=HeadlessDesigner.from_skin(path)
    old={name:(path/name).read_bytes() for name in ('designer_layout.json','document.designer.json','manifest.json')}
    original=headless._write_json_atomic
    def fail_layout(destination, value):
        if destination.name=='designer_layout.json': raise OSError('disk full')
        return original(destination,value)
    monkeypatch.setattr(headless,'_write_json_atomic',fail_layout)
    d.window_doc.title='Pending edit'
    with pytest.raises(OSError,match='disk full'):d.save_layout()
    assert all((path/name).read_bytes()==value for name,value in old.items())


def test_persistent_dispatch_saves_before_success_and_rolls_back_failure(tmp_path):
    from types import SimpleNamespace
    from elysium.aether.tools import Registry, Tool
    from elysium.aether.types import ToolCall
    path,_=project(tmp_path);d=HeadlessDesigner.from_skin(path)
    def checkpoint(*args,**kwargs):
        d.save_layout()
        return SimpleNamespace(id='snapshot')
    session=SimpleNamespace(designer=d,snapshots=SimpleNamespace(capture=checkpoint))
    registry=Registry()
    def set_title(session, title):
        session.designer.window_doc.title=title
        return {'title':title}
    schema={'type':'object','properties':{'title':{'type':'string'}},'required':['title']}
    registry.add(Tool('set','test',schema,set_title))
    result=d.dispatch_persistent_tool(ToolCall(id='ok',name='set',args={'title':'Durable'}),session,registry)
    assert result.ok and result.snapshot_id=='snapshot'
    assert json.loads((path/'designer_layout.json').read_text())['window']['title']=='Durable'
    before=d._snapshot();saved=(path/'designer_layout.json').read_bytes()
    def broken(session,title):
        session.designer.window_doc.title=title
        session.designer.placements.clear()
        return {'error':'partial failure'}
    registry.add(Tool('set','test',schema,broken))
    result=d.dispatch_persistent_tool(ToolCall(id='failed',name='set',args={'title':'Lost'}),session,registry)
    assert not result.ok
    assert d._snapshot()==before
    assert (path/'designer_layout.json').read_bytes()==saved


def test_checkpoint_failure_prevents_handler_execution(tmp_path):
    from types import SimpleNamespace
    from elysium.aether.tools import Registry, Tool
    from elysium.aether.types import ToolCall
    path,_=project(tmp_path);d=HeadlessDesigner.from_skin(path);called=[]
    def fail(*args,**kwargs):raise OSError('checkpoint unavailable')
    session=SimpleNamespace(designer=d,snapshots=SimpleNamespace(capture=fail))
    registry=Registry();registry.add(Tool('edit','test',{'type':'object'},lambda:called.append(True)))
    result=d.dispatch_persistent_tool(ToolCall(id='fail',name='edit',args={}),session,registry)
    assert not result.ok and 'checkpoint' in result.error
    assert called==[]


@pytest.mark.parametrize('kind,payload,expected', [('tool_result',{'ok':False},False),('error',{'message':'failed'},False),('tool_result',{'ok':True},True)])
def test_cli_waits_past_quiet_interval_and_reports_failure(kind,payload,expected):
    import asyncio
    from types import SimpleNamespace
    from elysium.cli import _drive_one
    class FakeDaemon:
        def subscribe(self):
            self.queue=asyncio.Queue()
            return self.queue
        def unsubscribe(self,q):self.removed=q is self.queue
        async def turn(self,text):
            await asyncio.sleep(.55)
            await self.queue.put(SimpleNamespace(kind=kind,payload=payload))
            await self.queue.put(SimpleNamespace(kind='done',payload={}))
    daemon=FakeDaemon()
    assert asyncio.run(_drive_one(daemon,'test')) is expected
    assert daemon.removed
