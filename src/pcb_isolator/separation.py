"""User-layer cutter centerlines, clipped and noded before routing."""
from pathlib import Path
import ezdxf
from ezdxf.path import make_path
from shapely.geometry import LineString,Polygon
from shapely.ops import unary_union


def load_separation(path):
    document=ezdxf.readfile(path)
    if document.units!=4:raise ValueError('CNC Separation DXF must declare millimeters.')
    lines=[]
    for entity in document.modelspace():
        if entity.dxftype() not in ('LINE','ARC','LWPOLYLINE','POLYLINE'):
            raise ValueError('CNC Separation must contain only lines/arcs, without text or dimensions.')
        points=list(make_path(entity).flattening(distance=.001))
        if any(abs(p.z)>1e-9 for p in points):raise ValueError('Separation paths must lie in the XY plane.')
        line=LineString([(p.x,p.y) for p in points])
        if line.length>1e-8:lines.append(line)
    return lines


def line_parts(geometry):
    if geometry.geom_type=='LineString':
        if geometry.length>1e-8:yield geometry
    elif hasattr(geometry,'geoms'):
        for part in geometry.geoms:yield from line_parts(part)


def separation_paths(lines,rings,origin=(0,0)):
    if not lines:return [],{'source_lines':0,'paths':0}
    polygons=sorted([Polygon(r.coords) for r in rings],key=lambda p:p.area,reverse=True)
    board=Polygon(polygons[0].exterior.coords,[list(p.exterior.coords) for p in polygons[1:]])
    if not board.is_valid:raise ValueError('Cannot clip separation paths to an invalid board outline.')
    # Stay 0.002 mm inside boundaries so 0.001 mm G-code rounding cannot
    # place a cutter center beyond an edge, including curved/diagonal edges.
    region=board.buffer(-.002)
    source=unary_union(lines)
    clipped=unary_union([line.intersection(region) for line in line_parts(source)])
    paths=[]
    ox,oy=origin
    for line in line_parts(clipped):
        points=[(round(x-ox,3)+ox,round(y-oy,3)+oy) for x,y in line.coords]
        rounded=LineString(points)
        if rounded.length<1e-8:continue
        if not board.covers(rounded):raise ValueError('Rounded separation centerline crosses the board boundary.')
        paths.append({'kind':'separation','closed':False,'points':points})
    paths.sort(key=lambda p:(p['points'][0],p['points'][-1]))
    return paths,{'source_lines':len(lines),'paths':len(paths),'source_length_mm':source.length,
                  'clipped_length_mm':sum(LineString(p['points']).length for p in paths),
                  'boundary_rounding_guard_mm':.002,'toolpath':'centerline; drawing stroke width ignored',
                  'order':'separation before compensated profile'}
