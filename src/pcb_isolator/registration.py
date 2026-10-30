"""Round internal Edge.Cuts can serve as manually prepared registration holes."""
from math import hypot,pi
from shapely.geometry import Polygon
from .drills import DrillFeature


def outline_candidates(rings,features):
    from .router import cutout_info
    polygons=sorted((Polygon(r.coords) for r in rings),key=lambda p:p.area,reverse=True)
    result=[]
    for polygon in polygons[1:]:
        if not polygon.is_valid or not polygons[0].contains(polygon):continue
        x,y=polygon.centroid.coords[0];points=list(polygon.exterior.coords)[:-1]
        if len(points)<12:continue
        radii=[hypot(px-x,py-y) for px,py in points];radius=sum(radii)/len(radii)
        if max(radii)-min(radii)>max(.005,radius*.005):continue
        if abs(polygon.area-pi*radius*radius)>pi*radius*radius*.025:continue
        if any(f.end is None and hypot(f.x-x,f.y-y)<.001 for f in features):continue
        result.append(DrillFeature('outline:'+cutout_info(polygon)['id'],radius*2,x,y))
    return result


def candidates(board):
    return board.get('alignment_candidates',board['features'])


def edge_warnings(board,ids,pin_diameter):
    outside=max((Polygon(r.coords) for r in board['outline']),key=lambda p:p.area)
    from shapely.geometry import Point
    warnings=[]
    for f in candidates(board):
        if f.id not in ids:continue
        distance=outside.boundary.distance(Point(f.x,f.y))
        if distance+1e-5<pin_diameter/2:
            warnings.append(f'Alignment at X{f.x:.3f}, Y{f.y:.3f}: {pin_diameter:g} mm pin hole extends {pin_diameter/2-distance:.3f} mm beyond the outer board edge. Check registration support or revise the location/pin size.')
    return warnings
