"""Convert the validated laser DXF paths to millimeter SVG without refitting."""
from math import cos,sin,radians,atan,hypot
from xml.etree import ElementTree as ET
import ezdxf

NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)


def export_svg(source,destination):
    doc=ezdxf.readfile(source);entities=list(doc.modelspace())
    points=[]
    for entity in [piece for e in entities for piece in (list(e.virtual_entities()) if e.dxftype()=='LWPOLYLINE' else [e])]:
        kind=entity.dxftype()
        if kind=='LINE':points.extend([(entity.dxf.start.x,entity.dxf.start.y),(entity.dxf.end.x,entity.dxf.end.y)])
        elif kind in ('ARC','CIRCLE'):
            c=entity.dxf.center;r=entity.dxf.radius
            angles=[0,90,180,270] if kind=='CIRCLE' else [entity.dxf.start_angle,entity.dxf.end_angle]+[a for a in (0,90,180,270) if (a-entity.dxf.start_angle)%360<=(entity.dxf.end_angle-entity.dxf.start_angle)%360]
            points.extend((c.x+r*cos(radians(a)),c.y+r*sin(radians(a))) for a in angles)
        else:raise ValueError('Unsupported laser SVG entity: '+kind)
    if not points:raise ValueError('Laser drawing is empty.')
    # A small page margin keeps endpoint strokes inside the page.
    x0,y0=min(p[0] for p in points)-.5,min(p[1] for p in points)-.5
    x1,y1=max(p[0] for p in points)+.5,max(p[1] for p in points)+.5
    def n(v):return f'{v:.9f}'.rstrip('0').rstrip('.') or '0'
    root=ET.Element(f'{{{NS}}}svg',{'version':'1.1','width':n(x1-x0)+'mm','height':n(y1-y0)+'mm',
        'viewBox':f'0 0 {n(x1-x0)} {n(y1-y0)}'})
    ET.SubElement(root,f'{{{NS}}}title').text='PCB isolation and alignment marks — 1:1 millimeters'
    ET.SubElement(root,f'{{{NS}}}desc').text='Same paths as laser DXF. Black vector strokes, no fill; 0.01 mm fallback stroke and Inkscape hairline style. Page translates source coordinates and reverses Y for SVG; no horizontal mirroring.'
    # Bake the page translation and Y reflection into every coordinate. Keep
    # each primitive directly under the document: no groups, layers or transforms.
    attrs={'fill':'none','stroke':'#000000','stroke-width':'0.01',
        'style':'-inkscape-stroke:hairline','stroke-linecap':'round','stroke-linejoin':'round'}
    for entity in entities:
        kind=entity.dxftype()
        if kind=='LINE':
            a,b=entity.dxf.start,entity.dxf.end
            ET.SubElement(root,f'{{{NS}}}line',{**attrs,'x1':n(a.x-x0),'y1':n(y1-a.y),'x2':n(b.x-x0),'y2':n(y1-b.y)})
        elif kind=='CIRCLE':
            c=entity.dxf.center
            ET.SubElement(root,f'{{{NS}}}circle',{**attrs,'cx':n(c.x-x0),'cy':n(y1-c.y),'r':n(entity.dxf.radius)})
        elif kind=='ARC':
            c=entity.dxf.center;r=entity.dxf.radius
            a,b=entity.dxf.start_angle,entity.dxf.end_angle;sweep=(b-a)%360
            start=(c.x+r*cos(radians(a)),c.y+r*sin(radians(a)))
            end=(c.x+r*cos(radians(b)),c.y+r*sin(radians(b)))
            ET.SubElement(root,f'{{{NS}}}path',{**attrs,'d':f'M {n(start[0]-x0)} {n(y1-start[1])} A {n(r)} {n(r)} 0 {int(sweep>180)} 0 {n(end[0]-x0)} {n(y1-end[1])}'})
        elif kind=='LWPOLYLINE':
            vertices=list(entity.get_points('xyb'))
            if not vertices:continue
            commands=[f'M {n(vertices[0][0]-x0)} {n(y1-vertices[0][1])}']
            count=len(vertices) if entity.closed else len(vertices)-1
            for index in range(count):
                x,y,bulge=vertices[index];nx,ny,_=vertices[(index+1)%len(vertices)]
                if abs(bulge)<1e-14:commands.append(f'L {n(nx-x0)} {n(y1-ny)}')
                else:
                    radius=hypot(nx-x,ny-y)*(1+bulge*bulge)/(4*abs(bulge))
                    commands.append(f'A {n(radius)} {n(radius)} 0 {int(abs(4*atan(bulge))>3.141592653589793)} {int(bulge<0)} {n(nx-x0)} {n(y1-ny)}')
            if entity.closed:commands.append('Z')
            ET.SubElement(root,f'{{{NS}}}path',{**attrs,'d':' '.join(commands)})
        else:raise ValueError('Unsupported laser SVG entity: '+kind)
    ET.ElementTree(root).write(destination,encoding='utf-8',xml_declaration=True)
    return destination
