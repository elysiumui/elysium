"""Cubic transform curves with explicit free handles relative to each key.

Time is measured in frames, values in the channel's native units. Stored handles
move with their key. Evaluation limits each handle's horizontal reach to its
segment, preserving its slope; authored handle coordinates are never rewritten.
"""
import math


def validate(data, channels):
    if not isinstance(data, dict) or any(c not in channels for c in data):
        raise ValueError('Curve handles must belong to keyed transform channels')
    for pair in data.values():
        if not isinstance(pair, dict) or set(pair) != {'left', 'right'}:
            raise ValueError('Curve handles require left and right offsets')
        for side, offset in pair.items():
            if not isinstance(offset, list) or len(offset) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in offset):
                raise ValueError('Each handle needs finite frame and value offsets')
            if (side == 'left' and offset[0] > 0) or (side == 'right' and offset[0] < 0):
                raise ValueError('Left handle frame offset must be ≤ 0; right must be ≥ 0')


def handles(keys, frame, channel):
    chosen=[k for k in keys if channel in k.get('channels', (channel,))]
    index=next((i for i,k in enumerate(chosen) if k['frame']==frame),None)
    if index is None:raise ValueError('Select an existing key for curve handles')
    key=chosen[index]
    if channel in key.get('handles',{}):
        return {side:list(offset) for side,offset in key['handles'][channel].items()}
    left=(frame-chosen[index-1]['frame'])/3 if index else ((chosen[1]['frame']-frame)/3 if len(chosen)>1 else 1)
    right=(chosen[index+1]['frame']-frame)/3 if index+1<len(chosen) else left
    return {'left':[-left,0.0],'right':[right,0.0]}


def _cubic(a,b,c,d,t):
    # De Casteljau interpolation avoids large polynomial coefficients.
    ab=a*(1-t)+b*t;bc=b*(1-t)+c*t;cd=c*(1-t)+d*t
    return (ab*(1-t)+bc*t)*(1-t)+(bc*(1-t)+cd*t)*t


def evaluate(frame, first, last, a, b, outgoing, incoming):
    span=last-first
    def limited(offset):
        dx,dy=offset
        ratio=min(1.0,span/abs(dx)) if dx else 1.0
        return dx*ratio,dy*ratio
    dx1,dy1=limited(outgoing);dx2,dy2=limited(incoming)
    # Bounded time coordinates produce a monotonic cubic; bisect time before
    # reading the value. Time influence and value influence are independent.
    lo,hi=0.0,1.0
    for _ in range(52):
        t=(lo+hi)/2
        if _cubic(0,dx1,span+dx2,span,t)<frame-first:lo=t
        else:hi=t
    return _cubic(a,a+dy1,b+dy2,b,(lo+hi)/2)


def value_range(a,b,outgoing,incoming,span):
    """Exact cubic value extrema (independent of monotonic time parameterization)."""
    controls=[a,a+outgoing[1]*min(1,span/outgoing[0]) if outgoing[0] else a+outgoing[1],
              b+incoming[1]*min(1,span/-incoming[0]) if incoming[0] else b+incoming[1],b]
    size=max(abs(v) for v in controls) or 1
    p,q,r,s=(v/size for v in controls)
    aa=-p+3*q-3*r+s;bb=2*(p-2*q+r);cc=q-p
    roots=[]
    if abs(aa)<1e-15:
        if abs(bb)>1e-15:roots=[-cc/bb]
    else:
        discriminant=bb*bb-4*aa*cc
        if discriminant>=0:
            root=math.sqrt(discriminant);roots=[(-bb-root)/(2*aa),(-bb+root)/(2*aa)]
    values=[a,b]+[_cubic(*controls,t) for t in roots if 0<t<1]
    return min(values),max(values)
