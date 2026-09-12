"""Pure selected-component transforms in explicit affine coordinate frames."""
import math
import numpy as np
from . import topology


def rotation(axis, degrees):
    axis=np.array(axis,dtype=float,copy=True);axis/=np.linalg.norm(axis)
    x,y,z=axis
    cross=np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])
    angle=math.radians(degrees)
    return np.eye(3)+math.sin(angle)*cross+(1-math.cos(angle))*(cross@cross)


def selected_vertices(document, selection):
    mode=selection.get('mode');chosen=set(selection.get('ids',()))
    if mode not in ('vertices','edges','faces') or not chosen or chosen-{c['id'] for c in document[mode]}:
        raise ValueError('Select existing vertices, edges or faces first')
    if mode=='vertices':return chosen
    if mode=='edges':return {v for edge in document['edges'] if edge['id'] in chosen for v in edge['vertices']}
    return {c['vertex'] for face in document['faces'] if face['id'] in chosen for c in face['corners']}


def transformed_mesh(mesh, selection, world, parent, group, axis, space, amount, free_axis=None, plane=False):
    if group not in ('location','rotation','scale') or space not in ('Global','Local','Parent'):
        raise ValueError('Choose move, rotate or scale in Global, Local or Parent space')
    if axis is not None and (type(axis) is not int or axis not in range(3)):
        raise ValueError('Axis must be X, Y, Z or free')
    if type(amount) not in (int,float):raise ValueError('Enter a finite number')
    if not math.isfinite(amount):raise ValueError('Enter a finite number')
    doc=topology.document(mesh);chosen=selected_vertices(doc,selection)
    if free_axis is not None:
        free_axis=np.asarray(free_axis,dtype=float)
        if free_axis.shape!=(3,) or not np.isfinite(free_axis).all() or np.linalg.norm(free_axis)==0:
            raise ValueError('Free direction must contain three finite values and be nonzero')
    if plane and (axis is None or group=='rotation'):raise ValueError('Plane constraints require a move or scale axis')
    if amount == (1 if group=='scale' else 0):return mesh
    original=np.array([v['position'] for v in doc['vertices']],dtype=float)
    mask=np.array([v['id'] in chosen for v in doc['vertices']])
    # Transform vertices in the chosen affine frame. Object and parent TRS
    # remain unchanged; this also handles nonuniform object/parent scale.
    basis=np.eye(4) if space=='Global' else world if space=='Local' else parent
    local_to_frame=np.linalg.solve(basis,world)
    points=original@local_to_frame[:3,:3].T+local_to_frame[:3,3]
    result=points.copy();center=points[mask].mean(axis=0)
    direction=np.eye(3)[:,axis if axis is not None else 0]
    if axis is None and free_axis is not None:
        direction=np.linalg.solve(basis[:3,:3],np.asarray(free_axis))
        if group=='rotation':direction/=np.linalg.norm(direction)
    if group=='location':
        if plane and axis is not None:
            direction=np.eye(3)[:,next(i for i in range(3) if i!=axis)] if free_axis is None else np.linalg.solve(basis[:3,:3],free_axis)
            direction[axis]=0
        result[mask]+=direction*amount
    elif group=='rotation':result[mask]=(points[mask]-center)@rotation(direction,amount).T+center
    elif group=='scale':
        if amount==0:raise ValueError('Scale must be nonzero')
        factors=np.ones(3)
        if axis is None:factors[:]=amount
        elif plane:factors[[i for i in range(3) if i!=axis]]=amount
        else:factors[axis]=amount
        result[mask]=(points[mask]-center)*factors+center
    else:raise ValueError('Choose move, rotate or scale')
    positions=np.linalg.solve(local_to_frame[:3,:3],(result-local_to_frame[:3,3]).T).T
    return topology._publish_positions(doc,positions,mask.astype(float))
