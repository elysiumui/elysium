from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from elysium.render import pbr,mesh_materials,mesh_document,mesh_uv,primitives,scene


def triangle():
    return pbr.MeshObject(pbr.Mesh(np.array([[0,0,0],[1,0,0],[0,1,0]],np.float32),np.array([[0,1,2]]),vert_uvs=np.array([[0,0],[1,0],[0,1]],np.float32)),[pbr.Material()])


def direction(rgb):
    a=np.array(rgb,dtype=np.float32)/255*2-1
    return a/np.linalg.norm(a)


@pytest.mark.parametrize('mirrored',[False,True])
@pytest.mark.parametrize('scale',[(1,1,1),(2,3,.5),(-2,3,.5)])
def test_uv_frame_respects_handedness_and_world_scale(mirrored,scale):
    obj=triangle();obj.scale=scale
    if mirrored:obj.mesh.vert_uvs[:,0]*=-1
    mat=obj.materials[0];mat.normal_map=np.array([[[204,128,230,0]]],np.uint8);mat.normal_sampling='closest_repeat'
    world,_,_=pbr._world_transform(obj)
    # Authored surface normal retains +Z even under X reflection.
    normal=np.array([[0,0,1]],np.float32)
    out=pbr._mapped_normals(obj,mat,np.array([0]),np.array([[.2,.2]]),normal,world)[0]
    expected=direction([204,128,230]);expected[0]*=(-1 if mirrored else 1)*np.sign(scale[0])
    np.testing.assert_allclose(out,expected,atol=1e-6)
    assert np.linalg.norm(out)==pytest.approx(1)


def test_normal_frame_rotates_with_object_and_handles_degenerate_uvs():
    obj=triangle();obj.rotation=(0,np.pi/2,0)
    mat=obj.materials[0];mat.normal_map=np.array([[[204,128,230,255]]],np.uint8)
    world,_,_=pbr._world_transform(obj)
    N=np.array([[1,0,0]],np.float32)
    out=pbr._mapped_normals(obj,mat,np.array([0]),np.array([[.2,.2]]),N,world)
    d=direction([204,128,230]);np.testing.assert_allclose(out,[[d[2],d[1],-d[0]]],atol=1e-6)
    obj.mesh.vert_uvs[:]=0
    np.testing.assert_array_equal(pbr._mapped_normals(obj,mat,np.array([0]),np.array([[0,0]]),N,world),N)
    assert pbr._mapped_normals(obj,mat,np.array([0]),None,N,world) is N


def test_normal_maps_change_preview_and_path_trace_without_editing_geometry(tmp_path):
    p=SimpleNamespace(kind='Mesh3D',props={},visible=True,name='Cube',entity_id='cube')
    primitives.bind(p,'Cube');mesh_uv.cube_project(p)
    slot=mesh_materials.add(p)['slot_id'];mesh_materials.assign(p,[f['id'] for f in mesh_document.resolve(p.mesh_kind).topology['faces']],slot)
    source=deepcopy(mesh_document.resolve(p.mesh_kind).topology)
    def preview():return scene.render([p],32,32,yaw=0,pitch=0,projection='orthographic',ortho_scale=3,grid=False,shading='material')[0]
    def pathtrace():
        obj,_=scene.compose([p],materials=True)
        return pbr.render_path_traced(16,16,obj,pbr.Environment(),samples=1,max_bounces=0,cam_yaw=0,cam_pitch=0,denoise=False,seed=1)
    before=preview();before_path=pathtrace();path=tmp_path/'normal.png';Image.new('RGB',(2,2),(204,128,230)).save(path)
    mesh_materials.set_image(p,slot,str(path),'normal');path.unlink()
    assert preview()!=before and pathtrace()!=before_path
    assert mesh_document.resolve(p.mesh_kind).topology==source
    mesh_materials.set_image(p,slot,'','normal')
    assert preview()==before and pathtrace()==before_path
