from copy import deepcopy
import numpy as np
import pytest
from elysium.render import primitives,topology
from elysium.render.component_transform import transformed_mesh


def fixture():
    mesh=primitives.build('Cube',{'size':2})[0]
    selection={'mode':'faces','ids':[f['id'] for f in mesh.topology['faces']]}
    return mesh,selection


def test_plane_constraints_keep_excluded_coordinate_and_source_mesh():
    mesh,selection=fixture();original=deepcopy(mesh.topology)
    result=transformed_mesh(mesh,selection,np.eye(4),np.eye(4),'location',2,'Global',2,[.6,.8,.7],True)
    before=np.array([v['position'] for v in original['vertices']]);after=np.array([v['position'] for v in result.topology['vertices']])
    np.testing.assert_allclose(after,before+[1.2,1.6,0],atol=1e-12)
    result=transformed_mesh(mesh,selection,np.eye(4),np.eye(4),'scale',2,'Global',2,plane=True)
    np.testing.assert_allclose([v['position'] for v in result.topology['vertices']],before*[2,2,1],atol=1e-12)
    assert mesh.topology==original


@pytest.mark.parametrize('updates',[{'amount':float('nan')},{'amount':True},{'axis':True},{'axis':3},
    {'space':'Normal'},{'group':'unknown'},{'free_axis':[0,0,0]},{'free_axis':[1,2]},
    {'free_axis':[float('inf'),0,0]},{'group':'rotation','plane':True},
    {'axis':None,'plane':True},{'selection':{'mode':'vertices','ids':['missing']}}])
def test_invalid_component_transform_preserves_input(updates):
    mesh,selection=fixture();before=deepcopy(mesh.topology)
    args=dict(mesh=mesh,selection=selection,world=np.eye(4),parent=np.eye(4),group='location',axis=0,space='Global',amount=1)
    args.update(updates)
    with pytest.raises(ValueError):transformed_mesh(**args)
    assert mesh.topology==before
