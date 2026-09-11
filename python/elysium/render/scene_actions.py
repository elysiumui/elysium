"""Named scene animation actions; current placement keys remain the live edit buffer."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
from . import scene, scene_animation as animation

TIMING=('start','end','fps','loop')


def settings(value=None):
    if value is None:return None
    if not isinstance(value,dict) or set(value)!={'version','active','items'} or type(value['version']) is not int or value['version']!=1:
        raise ValueError('Invalid animation action library')
    if not isinstance(value['items'],list) or not value['items']:raise ValueError('Action library requires an action')
    ids=set();names=set()
    for item in value['items']:
        if not isinstance(item,dict) or set(item)!={'id','name','keys','timing'}:raise ValueError('Invalid animation action fields')
        identity=item['id'];name=item['name']
        if not isinstance(identity,str) or not identity or identity in ids:raise ValueError('Action IDs must be unique')
        if not isinstance(name,str) or not name.strip() or len(name)>120 or name.strip()!=name or name.casefold() in names:
            raise ValueError('Action names must be unique, nonempty and at most 120 characters')
        if not isinstance(item['timing'],dict) or set(item['timing'])!=set(TIMING):raise ValueError('Action timing requires start, end, fps and loop')
        animation.settings(item['timing'])
        if not isinstance(item['keys'],dict):raise ValueError('Action keys must use object identities')
        for object_id,keys in item['keys'].items():
            if not isinstance(object_id,str) or not object_id:raise ValueError('Action object identity is missing')
            animation.tracks(SimpleNamespace(kind='SceneGroup',props={'keys3d':keys}))
        ids.add(identity);names.add(name.casefold())
    if value['active'] not in ids:raise ValueError('Active action does not exist')
    return deepcopy(value)


def _capture(window,placements):
    return {'keys':{p.entity_id:animation.tracks(p) for p in placements if p.kind in ('Mesh3D','SceneGroup') and p.props.get('keys3d')},
            'timing':{key:animation.settings(getattr(window,'scene_timeline',None))[key] for key in TIMING}}


def read(window,placements):
    library=settings(getattr(window,'scene_actions',None))
    current=_capture(window,placements)
    if library is None:
        return {'version':1,'active':'action:default','items':[{'id':'action:default','name':'Default',**current}]}
    active=next(item for item in library['items'] if item['id']==library['active'])
    active.update(current)
    return library


def _activate(window,placements,library,identity):
    library=settings(library)
    target=next((a for a in library['items'] if a['id']==identity),None)
    if target is None:raise ValueError('This action no longer exists')
    available={p.entity_id:p for p in placements if p.kind in ('Mesh3D','SceneGroup')}
    missing=set(target['keys'])-set(available)
    if missing:raise ValueError('Action references missing objects; restore those objects or remove this action: '+', '.join(sorted(missing)))
    candidates=deepcopy(placements)
    for p in candidates:
        if p.kind not in ('Mesh3D','SceneGroup'):continue
        if p.entity_id in target['keys']:p.props['keys3d']=deepcopy(target['keys'][p.entity_id])
        else:p.props.pop('keys3d',None)
    frame=target['timing']['start']
    posed=animation.pose(candidates,frame)
    timeline=animation.settings({**animation.settings(getattr(window,'scene_timeline',None)),**target['timing']})
    transforms=[scene.transform(p) if p.kind in ('Mesh3D','SceneGroup') else None for p in posed]
    # All validation and evaluation finish before changing any live object.
    for p,q,transform in zip(placements,candidates,transforms):
        if p.kind not in ('Mesh3D','SceneGroup'):continue
        if 'keys3d' in q.props:p.props['keys3d']=deepcopy(q.props['keys3d'])
        else:p.props.pop('keys3d',None)
        p.props['transform3d']=transform
    library['active']=identity;window.scene_actions=library;window.scene_timeline=timeline;window.scene_frame=frame
    return read(window,placements)


def create(window,placements,name,*,duplicate=False,start=0,end=59):
    if not isinstance(duplicate,bool):raise ValueError('Duplicate must be on or off')
    library=read(window,placements);current=next(i for i in library['items'] if i['id']==library['active'])
    identity='action:'+uuid4().hex
    library['items'].append({'id':identity,'name':name.strip() if isinstance(name,str) else name,
        'keys':deepcopy(current['keys']) if duplicate else {},'timing':{**current['timing'],'start':start,'end':end}})
    return _activate(window,placements,library,identity)


def switch(window,placements,identity):
    library=read(window,placements)
    return _activate(window,placements,library,identity)


def rename(window,placements,identity,name):
    library=read(window,placements);item=next((a for a in library['items'] if a['id']==identity),None)
    if item is None:raise ValueError('This action no longer exists')
    item['name']=name.strip() if isinstance(name,str) else name
    window.scene_actions=settings(library)
    return read(window,placements)


def remove(window,placements,identity):
    library=read(window,placements)
    if len(library['items'])==1:raise ValueError('Keep at least one animation action')
    if not any(a['id']==identity for a in library['items']):raise ValueError('This action no longer exists')
    library['items']=[a for a in library['items'] if a['id']!=identity]
    if library['active']==identity:
        library['active']=library['items'][0]['id']
        return _activate(window,placements,library,library['active'])
    window.scene_actions=settings(library)
    return read(window,placements)
