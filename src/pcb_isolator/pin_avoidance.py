"""Plan XY travel around circular pin keepouts and reject cutting conflicts."""
from dataclasses import dataclass
from heapq import heappop, heappush
from math import cos, hypot, isfinite, pi, sin


@dataclass(frozen=True)
class Keepout:
    x: float
    y: float
    radius: float


def segment_clear(a,b,obstacles):
    dx,dy=b[0]-a[0],b[1]-a[1]
    length2=dx*dx+dy*dy
    for circle in obstacles:
        t=max(0,min(1,((circle.x-a[0])*dx+(circle.y-a[1])*dy)/length2)) if length2 else 0
        distance=hypot(a[0]+t*dx-circle.x,a[1]+t*dy-circle.y)
        if distance<=circle.radius:
            return False
    return True


def route_around(a,b,obstacles):
    if not segment_clear(a,a,obstacles) or not segment_clear(b,b,obstacles):
        raise ValueError('Travel start or destination lies inside an alignment-pin keepout.')
    if segment_clear(a,b,obstacles):
        return [b]
    nodes=[a,b]
    # Circumscribed polygons: every neighboring chord remains outside the disk.
    # Extra geometric clearance covers numerical tangencies in the graph.
    for circle in obstacles:
        radius=(circle.radius+0.01)/cos(pi/32)
        for i in range(32):
            point=(circle.x+radius*cos(2*pi*i/32),circle.y+radius*sin(2*pi*i/32))
            if segment_clear(point,point,obstacles):
                nodes.append(point)
    graph=[[] for _ in nodes]
    for i,a0 in enumerate(nodes):
        for j in range(i+1,len(nodes)):
            b0=nodes[j]
            if segment_clear(a0,b0,obstacles):
                distance=hypot(b0[0]-a0[0],b0[1]-a0[1])
                graph[i].append((j,distance));graph[j].append((i,distance))
    queue=[(0,0)]
    distances={0:0}
    previous={}
    while queue:
        distance,index=heappop(queue)
        if distance!=distances[index]:
            continue
        if index==1:
            result=[]
            while index!=0:
                result.append(nodes[index]);index=previous[index]
            return result[::-1]
        for neighbor,step in graph[index]:
            candidate=distance+step
            if candidate<distances.get(neighbor,float('inf')):
                distances[neighbor]=candidate;previous[neighbor]=index
                heappush(queue,(candidate,neighbor))
    raise ValueError('No collision-free route around alignment pins was found.')


def pin_settings(config):
    settings=config['alignment_pins']
    if settings.get('pins_removed_before_machining'):
        if any(not isfinite(settings[k]) for k in ('start_x_mm','start_y_mm')):raise ValueError('Ordering reference must be finite.')
        return settings
    for key in ('height_above_board_mm','xy_margin_mm','vertical_margin_mm','tool_envelope_diameter_mm'):
        value=settings[key]
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value) or value<=0:
            raise ValueError(f'alignment_pins.{key} must be positive and finite.')
    for key in ('start_x_mm','start_y_mm'):
        if not isfinite(settings[key]):
            raise ValueError('Pin avoidance requires a finite staged start XY.')
    return settings


def pin_obstacles(alignment,pin_diameter,tool_diameter,config):
    settings=pin_settings(config)
    if settings.get('pins_removed_before_machining'):return []
    envelope=max(settings['tool_envelope_diameter_mm'],tool_diameter)
    # Additional 0.002 mm protects against XYZ output rounding to 0.001 mm.
    radius=(pin_diameter+envelope)/2+settings['xy_margin_mm']+0.002
    return [Keepout(f.x,f.y,radius) for f in alignment]


def avoid_pins(moves,alignment,pin_diameter,tool_diameter,config,*,start_at_first=False):
    settings=pin_settings(config)
    if settings.get('pins_removed_before_machining'):
        first=next((m for m in moves if 'x' in m or 'y' in m),{})
        machine=config['machine']
        return [dict(m) for m in moves],dict(policy='pins_removed_before_machining',pin_height_mm=0,
            travel_clearance_mm=machine['clearance_mm'],keepout_radius_mm=0,tool_envelope_diameter_mm=tool_diameter,
            start_work_xy_mm=[first.get('x',machine['origin_x_mm'])-machine['origin_x_mm'],first.get('y',machine['origin_y_mm'])-machine['origin_y_mm']],detoured_travels=0)
    envelope=max(settings['tool_envelope_diameter_mm'],tool_diameter)
    obstacles=pin_obstacles(alignment,pin_diameter,tool_diameter,config)
    radius=(pin_diameter+envelope)/2+settings['xy_margin_mm']+0.002
    clearance=max(config['machine']['clearance_mm'],settings['height_above_board_mm']+settings['vertical_margin_mm'])
    if config['machine']['park_z_mm']<clearance:
        raise ValueError('Park Z must be at least the pin-aware travel clearance.')
    machine=config['machine']
    # Staged start is expressed in machine work coordinates; move plans are in
    # source coordinates, before the common origin offset is applied.
    xy=(settings['start_x_mm']+machine['origin_x_mm'],settings['start_y_mm']+machine['origin_y_mm'])
    if start_at_first:
        first=next((m for m in moves if 'x' in m or 'y' in m),None)
        if first is not None:xy=(first.get('x',xy[0]),first.get('y',xy[1]))
    start_xy=xy
    if not segment_clear(xy,xy,obstacles):
        raise ValueError('First cutting start is inside an alignment-pin keepout.' if start_at_first else 'Configured staged start is inside an alignment-pin keepout.')
    result=[]
    z=None
    detours=0
    for original in moves:
        move=dict(original)
        if move['g']==0 and 'z' in move and move['z']>=machine['clearance_mm']:
            move['z']=max(move['z'],clearance)
        if 'x' in move or 'y' in move:
            target=(move.get('x',xy[0]),move.get('y',xy[1]))
            if move['g']==0:
                if z is None or z<clearance:
                    raise ValueError('XY travel before pin-aware Z clearance.')
                route=route_around(xy,target,obstacles)
                detours+=len(route)>1
                result.extend({'g':0,'x':p[0],'y':p[1]} for p in route)
            else:
                if not segment_clear(xy,target,obstacles):
                    raise ValueError('Cutting path enters an alignment-pin keepout; change the design or setup.')
                result.append(move)
            xy=target
        else:
            if 'z' in move and move['z']<clearance and not segment_clear(xy,xy,obstacles):
                raise ValueError('Plunge enters an alignment-pin keepout.')
            result.append(move)
        z=move.get('z',z)
    return result,{'pin_height_mm':settings['height_above_board_mm'],'travel_clearance_mm':clearance,
                   'keepout_radius_mm':radius,'tool_envelope_diameter_mm':envelope,
                   'start_work_xy_mm':[start_xy[0]-machine['origin_x_mm'],start_xy[1]-machine['origin_y_mm']],
                   'detoured_travels':detours,'policy':'xy_first_at_max_height_then_around_pins' if start_at_first else 'always_around_even_above_pins'}
