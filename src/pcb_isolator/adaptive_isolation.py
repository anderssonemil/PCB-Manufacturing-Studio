"""Local corridor lane allocation with exact keepout clipping.

Straight parallel corridors get evenly spaced shared lanes. Wide free areas
retain capped boundary bands. Transitions/curves are approximate and clipped
against the same expanded-copper keepout used by the directional planner.
"""
from math import hypot,floor
from collections import Counter
import numpy as np
from shapely.geometry import LineString,Point
from shapely.ops import unary_union,linemerge
from shapely.strtree import STRtree
from shapely import set_precision,prepare


class AdaptiveContours(list):
    pass


def line_parts(shape):
    if shape.is_empty:return []
    if shape.geom_type in ('LineString','LinearRing'):return [LineString(shape.coords)] if shape.length>1e-7 else []
    return [part for item in getattr(shape,'geoms',[]) for part in line_parts(item)]


def plan_lanes(first,settings):
    guard=max(.00002,settings.width_mm*.0001)
    polygons=[first] if first.geom_type=='Polygon' else first.geoms
    rings=[];edges=[]
    for polygon in polygons:
        for index,ring in enumerate([polygon.exterior,*polygon.interiors]):
            points=np.asarray(LineString(ring.coords).simplify(min(.000002,guard*.1)).coords)[:-1]
            dense=[]
            for j,start in enumerate(points):
                end=points[(j+1)%len(points)];steps=max(1,int(np.ceil(np.linalg.norm(end-start)/.10)))
                dense.extend(start+(end-start)*fraction for fraction in np.arange(steps)/steps)
            points=np.asarray(dense)
            flip=-1 if (index==0 and ring.is_ccw) or (index>0 and not ring.is_ccw) else 1
            rings.append((points,flip))
            edges.extend(LineString([points[j],points[(j+1)%len(points)]]) for j in range(len(points)))
    prepare(first)
    clipping=first.buffer(-guard*.2)
    tree=STRtree(edges);maximum=settings.lines;minimum_step=settings.spacing_mm
    # Broad coupon cells exercised steps up to about 0.116 mm. This is a
    # provisional interpolation limit, not a physical laser-speed parameter.
    maximum_step=max(minimum_step,.12)
    ray_limit=max(.001,(maximum-1)*maximum_step)
    layers=[[] for _ in range(maximum)];counts=Counter();spacings=[];shared=0
    for points,flip in rings:
        per_lane=[[] for _ in range(maximum)]
        for j,p in enumerate(points):
            before=p-points[j-1];after=points[(j+1)%len(points)]-p
            before=before/max(np.linalg.norm(before),1e-12);after=after/max(np.linalg.norm(after),1e-12)
            tangent=before+after;length=np.linalg.norm(tangent)
            if length<1e-10:tangent=after;length=max(np.linalg.norm(tangent),1e-12)
            normal=flip*np.array([-tangent[1],tangent[0]])/length
            ray=LineString([p+normal*.0001,p+normal*(ray_limit+.0002)])
            closest=None
            for edge_index in tree.query(ray):
                hit=ray.intersection(edges[int(edge_index)])
                if hit.is_empty:continue
                hits=[hit] if hit.geom_type=='Point' else list(hit.geoms) if hit.geom_type=='MultiPoint' else []
                for point in hits:
                    q=np.array([point.x,point.y]);distance=float((q-p)@normal)
                    if distance<=.0001 or distance>ray_limit+.0001:continue
                    if not first.contains(Point(q+normal*.00001)):continue
                    if closest is None or distance<closest[0]:closest=(distance,q)
            locations={i:p+normal*(i*minimum_step) for i in range(maximum)}
            if closest is not None:
                distance,q=closest
                # Keep two distinct close passes when the remaining center span is
                # smaller than target spacing (unless the user explicitly caps at one).
                count=min(maximum,max(2,int(floor((distance+.0001)/minimum_step))+1))
                spacing=distance/(count-1) if count>1 else 0
                # Only the nearer half of the shared plan comes from each
                # boundary. A deterministic owner emits the odd middle lane.
                own_middle=tuple(np.round(p,7))<tuple(np.round(q,7))
                locations={}
                for i in range((count+1)//2):
                    middle=(count%2==1 and i==count//2)
                    if middle and not own_middle:continue
                    offset=distance/2 if count==1 else i*spacing
                    locations[i]=p+normal*offset
                counts[count]+=1;shared+=1
                if spacing:spacings.append(spacing)
            for i in range(maximum):per_lane[i].append(locations.get(i))
        for i,sequence in enumerate(per_lane):
            if all(p is not None for p in sequence):
                if len(sequence)>1:layers[i].append(LineString([*sequence,sequence[0]]))
            else:
                # Rotate at a missing point so a route crossing the ring's
                # arbitrary start remains one connected run.
                pivot=next(k for k,p in enumerate(sequence) if p is None)
                run=[]
                for p in sequence[pivot+1:]+sequence[:pivot+1]:
                    if p is None:
                        if len(run)>1:layers[i].append(LineString(run))
                        run=[]
                    else:run.append(p)
    result=AdaptiveContours();previous=None
    for pieces in layers:
        if not pieces:result.append(LineString());continue
        shape=unary_union(pieces).difference(clipping)
        shape=set_precision(shape,.000001)
        if previous is not None:shape=shape.difference(previous.buffer(.000003))
        parts=line_parts(shape)
        merged=linemerge(unary_union(parts)) if len(parts)>1 else parts[0] if parts else LineString()
        result.append(merged)
        previous=unary_union([previous,merged]) if previous is not None else merged
    result.metadata={'planning':'adaptive_shared_corridors','maximum_lanes':maximum,
        'target_spacing_mm':minimum_step,'maximum_interpolated_spacing_mm':maximum_step,
        'sampled_local_lane_counts':dict(sorted(counts.items())),
        'shared_corridor_samples':shared,
        'used_spacing_range_mm':[min(spacings),max(spacings)] if spacings else [],
        'note':'Counts are local boundary samples, not independent clearance regions. Wide areas keep capped boundary bands; curved transitions are clipped to protect copper.'}
    return result
