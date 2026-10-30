"""Bounded, deterministic travel heuristics; no machining geometry is offset."""
from collections import defaultdict
from functools import lru_cache
from math import dist
from .pin_avoidance import route_around,segment_clear


class TravelCosts:
    def __init__(self,obstacles):self.obstacles=obstacles

    def distance(self,a,b):
        a,b=tuple(a),tuple(b)
        return self._distance(*sorted((a,b)))

    @lru_cache(maxsize=200000)
    def _distance(self,a,b):
        if segment_clear(a,b,self.obstacles):return dist(a,b)
        route=[a,*route_around(a,b,self.obstacles)]
        return sum(dist(x,y) for x,y in zip(route,route[1:]))


def optimize_points(features,start,costs):
    if len(features)<2:return list(features)
    points=[(f.x,f.y) for f in features];n=len(points);original=list(range(n))
    distance=costs.distance
    def score(order):return sum(distance(a,b) for a,b in zip([start]+[points[i] for i in order],[points[i] for i in order]))
    seeds=[original,original[::-1]]
    firsts=sorted(original,key=lambda i:(distance(start,points[i]),i))[:4 if n<=300 else 1]
    for first in firsts:
        remaining=set(original);remaining.remove(first);order=[first]
        while remaining:
            next_id=min(remaining,key=lambda i:(distance(points[order[-1]],points[i]),i))
            order.append(next_id);remaining.remove(next_id)
        seeds.append(order)
    for axis in (0,1):
        ordered=sorted(original,key=lambda i:(points[i][axis],points[i][1-axis],i))
        seeds.extend([ordered,ordered[::-1]])
        rows=defaultdict(list)
        for i in original:rows[round(points[i][axis],3)].append(i)
        snake=[]
        for row,key in enumerate(sorted(rows)):
            snake.extend(sorted(rows[key],key=lambda i:(points[i][1-axis],i),reverse=bool(row%2)))
        seeds.extend([snake,snake[::-1]])
    unique={tuple(seed):seed for seed in seeds}
    ranked=sorted(unique.values(),key=lambda order:(score(order),order))
    best=list(ranked[0]);best_cost=score(best)
    for seed in ranked[:3]:
        route=list(seed)
        for _ in range(10):
            change=None;best_delta=-1e-8;checks=0
            for i in range(n-1):
                before=start if i==0 else points[route[i-1]]
                for j in range(i+1,n):
                    checks+=1
                    first,last=points[route[i]],points[route[j]]
                    delta=distance(before,last)-distance(before,first)
                    if j+1<n:
                        after=points[route[j+1]];delta+=distance(first,after)-distance(last,after)
                    if delta<best_delta:best_delta=delta;change=(i,j)
                    if checks>=20000:break
                if checks>=20000:break
            if change is None:break
            i,j=change;route[i:j+1]=reversed(route[i:j+1])
        value=score(route)
        if value<best_cost-1e-8:best,best_cost=route,value
    return [features[i] for i in best]


def join_paths(paths):
    if not paths:return []
    from shapely.geometry import MultiLineString
    from shapely.ops import linemerge
    from .separation import line_parts
    merged=linemerge(MultiLineString([p['points'] for p in paths]))
    return [{'kind':'separation','closed':False,'points':list(line.coords)} for line in line_parts(merged)]


def optimize_cut_paths(paths,start,end,passes,costs):
    """Select path order and direction; account for the exit after all passes."""
    if not paths:return []
    distance=costs.distance;n=len(paths);choices=[]
    for path in paths:
        points=path['points'];pair=[]
        for direction in (0,1):
            entry=points[-1] if direction else points[0]
            finish=(points[0] if direction else points[-1]) if passes%2 else entry
            pair.append((entry,finish))
        choices.append(pair)
    def oriented(order):
        parents=[];previous=None;values=[]
        for index in order:
            new=[];parent=[]
            for direction in (0,1):
                entry=choices[index][direction][0]
                if previous is None:value=distance(start,entry);prior=0
                else:
                    value,prior=min((values[d]+distance(choices[previous][d][1],entry),d) for d in (0,1))
                new.append(value);parent.append(prior)
            parents.append(parent);values=new;previous=index
        value,direction=min((values[d]+(distance(choices[previous][d][1],end) if end is not None else 0),d) for d in (0,1))
        directions=[]
        for row in range(len(order)-1,-1,-1):
            directions.append(direction);direction=parents[row][direction]
        return value,list(reversed(directions))
    original=list(range(n));seeds=[original,original[::-1]]
    starts=sorted(((distance(start,choices[i][d][0]),i,d) for i in original for d in (0,1)))[:4]
    for _,first,direction in starts:
        order=[first];remaining=set(original)-{first};position=choices[first][direction][1]
        while remaining:
            _,next_id,d=min((distance(position,choices[i][d][0]),i,d) for i in remaining for d in (0,1))
            order.append(next_id);remaining.remove(next_id);position=choices[next_id][d][1]
        seeds.append(order)
    route=min(seeds,key=lambda order:(oriented(order)[0],order));value,directions=oriented(route)
    for _ in range(5):
        improved=None;checks=0;new_value=value
        for i in range(n-1):
            for j in range(i+1,n):
                trial=route[:i]+route[i:j+1][::-1]+route[j+1:]
                candidate,_=oriented(trial);checks+=1
                if candidate<new_value-1e-8:new_value=candidate;improved=trial
                if checks>=1200:break
            if checks>=1200:break
        if improved is None:break
        route=improved;value,directions=oriented(route)
    result=[]
    for index,direction in zip(route,directions):
        path={**paths[index],'points':list(reversed(paths[index]['points'])) if direction else list(paths[index]['points'])}
        result.append(path)
    return result


def rapid_distance(moves,config):
    """Measure the actual 0.001 mm output coordinates, including pin detours."""
    machine=config['machine'];pins=config['alignment_pins']
    xy=(pins['start_x_mm'],pins['start_y_mm']);length=0
    for move in moves:
        if 'x' not in move and 'y' not in move:continue
        target=tuple(float(f'{move[axis]-machine["origin_"+axis+"_mm"]:.3f}') if axis in move else xy[i] for i,axis in enumerate('xy'))
        if move['g']==0:length+=dist(xy,target)
        xy=target
    return length


def travel_report(before,after,method):
    return {'method':method,'original_xy_travel_mm':before,'optimized_xy_travel_mm':after,
            'saved_xy_travel_mm':max(0,before-after),'saved_percent':max(0,(before-after)/before*100) if before else 0,
            'comparison':'rounded output coordinates, staged start and pin detours included'}
