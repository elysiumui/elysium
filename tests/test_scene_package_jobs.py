"""Build outcomes publish complete applications only; cancellation owns its staging."""
from pathlib import Path
import importlib.util
import subprocess
import sys
import pytest
from elysium.render.scene_export import package_app


@pytest.mark.parametrize('paired_name',[None,'behavior-panel','behavior panel'])
@pytest.mark.parametrize('outcome',['success','failure','cancel'])
def test_package_job_stages_result_and_preserves_logs(tmp_path,monkeypatch,outcome,paired_name):
    source=tmp_path/'source.esk';source.mkdir();(source/'scene-animation.json').write_text('{}')
    if paired_name:
        import json
        (source/'code').mkdir();(source/'code'/f'{paired_name}.py').write_text('import decimal\n')
        (source/'scene-animation.json').write_text(json.dumps({'code_file':f'code/{paired_name}.py'}))
    original_manifest=(source/'scene-animation.json').read_text()
    destination=tmp_path/'apps';destination.mkdir();(destination/'keep.txt').write_text('user file')
    real_find=importlib.util.find_spec
    monkeypatch.setattr(importlib.util,'find_spec',lambda name:object() if name=='PyInstaller' else real_find(name))
    app_name='Ship.app' if sys.platform=='darwin' else 'Ship'
    instances=[]
    class Process:
        def __init__(self,args,**kwargs):
            if paired_name:assert args[args.index('--hidden-import')+1]==paired_name
            self.returncode=None if outcome=='cancel' else 0 if outcome=='success' else 1
            self.terminated=False;instances.append(self)
            dist=Path(args[args.index('--distpath')+1]);(dist/app_name).mkdir(parents=True)
            (dist/app_name/'complete.txt').write_text('payload')
            kwargs['stdout'].write('compiler diagnostic\n');kwargs['stdout'].flush()
        def poll(self): return self.returncode
        def terminate(self): self.terminated=True;self.returncode=-15
        def wait(self,**kwargs): return self.returncode
    monkeypatch.setattr(subprocess,'Popen',Process)
    seen=[]
    if outcome=='success':
        result=package_app(source,destination,name='Ship',progress=seen.append)
        assert Path(result['path']).is_dir() and (destination/app_name/'complete.txt').is_file()
    else:
        with pytest.raises(InterruptedError if outcome=='cancel' else RuntimeError):
            package_app(source,destination,name='Ship',progress=seen.append,cancel=lambda:outcome=='cancel' and bool(instances))
        assert not (destination/app_name).exists()
    assert seen and 'compiler diagnostic' in Path(seen[0]).read_text()
    assert not list(destination.glob('.elysium-app-build-*'))
    assert (destination/'keep.txt').read_text()=='user file'
    assert (source/'scene-animation.json').read_text()==original_manifest
    if outcome=='cancel': assert instances[0].terminated


@pytest.mark.parametrize('name',['behavior-panel','behavior panel'])
def test_installed_packager_analyzes_non_identifier_filenames_without_executing_them(tmp_path,name):
    graph_module=pytest.importorskip('PyInstaller.lib.modulegraph.modulegraph')
    source=tmp_path/(name+'.py');source.write_text('import helper\nraise RuntimeError("must never execute during packaging")\n')
    (tmp_path/'helper.py').write_text('VALUE = 42\n')
    graph=graph_module.ModuleGraph(path=[str(tmp_path)])
    node=graph.import_hook(name)[0]
    assert node.filename==str(source) and graph.find_node('helper').filename==str(tmp_path/'helper.py')
