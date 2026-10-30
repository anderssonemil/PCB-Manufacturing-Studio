"""Order exact device-grid paths without changing their engraving segments."""
from math import floor,hypot,sqrt
import numpy as np


def travel_distance(routes,start=(0,0)):
    total=0.;position=start
    for route in routes:
        total+=hypot(route[0][0]-position[0],route[0][1]-position[1]);position=route[-1]
    return total


def orient_path(route,position,following=None):
    if route[0]==route[-1] and len(route)>2:
        points=np.asarray(route[:-1],dtype=float)
        costs=np.hypot(points[:,0]-position[0],points[:,1]-position[1])
        if following is not None:costs+=np.hypot(points[:,0]-following[0],points[:,1]-following[1])
        index=int(np.argmin(costs));core=route[:-1];result=core[index:]+core[:index];return result+[result[0]]
    def cost(r):
        value=hypot(r[0][0]-position[0],r[0][1]-position[1])
        if following is not None:value+=hypot(r[-1][0]-following[0],r[-1][1]-following[1])
        return value
    return route[::-1] if cost(route[::-1])+1e-9<cost(route) else route[:]


def optimize_laser_routes(routes,grid_mm):
    original=[list(map(tuple,r)) for r in routes]
    if not original:raise ValueError('No printable laser paths remain after filtering. Reduce the fragment threshold.')
    before=travel_distance(original)
    xs=[p[0] for r in original for p in r];ys=[p[1] for r in original for p in r]
    cell=max(1.,hypot(max(xs)-min(xs),max(ys)-min(ys))/max(2,sqrt(len(original))))
    buckets={};active=set(range(len(original)))
    for index,route in enumerate(original):
        vertices=route[:-1] if route[0]==route[-1] else [route[0],route[-1]]
        for x,y in vertices:buckets.setdefault((floor(x/cell),floor(y/cell)),[]).append((x,y,index))
    result=[];position=(0,0)
    while active:
        cx,cy=floor(position[0]/cell),floor(position[1]/cell);best=None;radius=0
        while True:
            for gx in range(cx-radius,cx+radius+1):
                for gy in range(cy-radius,cy+radius+1):
                    if radius and abs(gx-cx)!=radius and abs(gy-cy)!=radius:continue
                    key=(gx,gy)
                    if key not in buckets:continue
                    entries=[p for p in buckets[key] if p[2] in active]
                    if entries:buckets[key]=entries
                    else:del buckets[key]
                    for x,y,index in entries:
                        candidate=((x-position[0])**2+(y-position[1])**2,index,x,y)
                        if best is None or candidate<best:best=candidate
            boundary=min(position[0]-(cx-radius)*cell,(cx+radius+1)*cell-position[0],position[1]-(cy-radius)*cell,(cy+radius+1)*cell-position[1])
            if best is not None and best[0]<=boundary*boundary:break
            radius+=1
            if radius>512:
                # Bounded search fallback for extremely sparse/malformed extents.
                index=min(active,key=lambda i:min((p[0]-position[0])**2+(p[1]-position[1])**2 for p in (original[i][:-1] if original[i][0]==original[i][-1] else [original[i][0],original[i][-1]])))
                best=(0,index,0,0);break
        index=best[1];route=orient_path(original[index],position);result.append(route);active.remove(index);position=route[-1]
    # Refine closed-loop entry and open-stroke direction using both neighbours.
    for sweep in range(2):
        indices=range(len(result)) if not sweep else range(len(result)-1,-1,-1)
        for i in indices:result[i]=orient_path(result[i],result[i-1][-1] if i else (0,0),result[i+1][0] if i+1<len(result) else None)
    # Bounded adjacent relocation, followed by another entry-direction refinement.
    for i in range(len(result)-1):
        prev=result[i-1][-1] if i else (0,0);after=result[i+2][0] if i+2<len(result) else None
        a,b=result[i:i+2]
        def pair_cost(a,b):return hypot(prev[0]-a[0][0],prev[1]-a[0][1])+hypot(a[-1][0]-b[0][0],a[-1][1]-b[0][1])+(hypot(b[-1][0]-after[0],b[-1][1]-after[1]) if after else 0)
        nb=orient_path(b,prev,a[0]);na=orient_path(a,nb[-1],after)
        if pair_cost(nb,na)+1e-9<pair_cost(a,b):result[i:i+2]=[nb,na]
    after=travel_distance(result)
    if after>before+1e-8:result=original;after=before
    return result,dict(before_travel_mm=before*grid_mm,after_travel_mm=after*grid_mm,saved_travel_mm=(before-after)*grid_mm,
        saved_percent=100*(before-after)/before if before else 0,paths=len(result),method='spatial nearest path, closed-loop entry, open-path reversal and bounded neighbour improvement',
        note='Exact grid segments and repeated exposures preserved. Initial position assumed X0/Y0; no thermal simulation or guaranteed optimum.')
