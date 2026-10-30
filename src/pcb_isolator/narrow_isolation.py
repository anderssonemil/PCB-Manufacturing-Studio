"""Two closely spaced medial passes where the calibrated spot cannot fit.

This is an explicit, reported copper-sacrificing fallback, never a smaller
claimed physical spot. Voronoi ridges are generated in footprint-scaled space.
"""
import numpy as np
import shapely
from shapely.affinity import scale
from shapely.geometry import MultiPoint,LineString,Point,Polygon
from shapely.ops import unary_union,linemerge
from shapely.strtree import STRtree
from .adaptive_isolation import line_parts


def _ends_at_copper(line,copper):
    """Distinguish a closing corner from a through-gap's sampled endpoint."""
    if line.is_ring:return False
    points=list(line.coords)
    for endpoint,inside in ((points[0],points[1]),(points[-1],points[-2])):
        if Point(endpoint).distance(copper)>=.01:continue
        vector=np.asarray(endpoint)-inside;length=np.linalg.norm(vector)
        if length<1e-12:continue
        ahead=np.asarray(endpoint)+vector/length*.03
        if LineString([endpoint,ahead]).intersects(copper):return True
    return False


def add_narrow_fallback(copper, contours, settings):
    x,y=settings.width_mm/2,settings.width_y_mm/2
    material=scale(copper,xfact=1/x,yfact=1/y,origin=(0,0))
    # Restrict the Voronoi problem to boundaries the spot-safe outline
    # cannot reach. Sampling an entire board creates hundreds of thousands
    # of unnecessary sites, particularly on large ground planes.
    expanded=material.buffer(1,quad_segs=64)
    missing=material.boundary.difference(expanded.boundary.simplify(.002).buffer(1.02,quad_segs=16))
    if missing.is_empty or missing.length<.001:return contours
    region=missing.buffer(2.5,quad_segs=8)
    # Remove import tessellation noise, then sample at <= 0.01 physical mm.
    boundary=material.boundary.intersection(region).simplify(.0005/max(x,y),preserve_topology=True)
    sampled=shapely.segmentize(boundary,.01/max(x,y))
    coords=np.unique(shapely.get_coordinates(sampled),axis=0)
    if len(coords)<4:return contours
    sites=MultiPoint(coords);tree=STRtree(list(sites.geoms))
    ridges=shapely.voronoi_polygons(sites,only_edges=True)
    parts=list(ridges.geoms)
    mids=shapely.line_interpolate_point(np.asarray(parts,dtype=object),.5,normalized=True)
    segments=[]
    for wall in line_parts(material.boundary):
        points=np.asarray(wall.coords)
        segments.append(np.stack((points[:-1],points[1:]),axis=1))
    wall_tree=STRtree(shapely.linestrings(np.concatenate(segments)))
    indices,distances=wall_tree.query_nearest(mids,all_matches=False,return_distance=True)
    radii=np.zeros(len(mids));radii[indices[0]]=distances
    shapely.prepare(material)
    radii[shapely.contains(material,mids)]=0
    # Narrow free-space medial branches only. Adjacent samples on the same
    # smooth wall generate outward bisectors too; reject those by site angle.
    selected=np.flatnonzero((radii>.0001)&(radii<.9999))
    keep=[]
    for index in selected:
        p=mids[index];r=radii[index]
        ids=tree.query(p.buffer(r+.08))
        if len(ids)<2:continue
        deltas=coords[ids]-[p.x,p.y]
        distances=np.linalg.norm(deltas,axis=1)
        nearest=deltas[distances<=distances.min()+1e-7]
        if len(nearest)<2:continue
        unit=nearest/np.linalg.norm(nearest,axis=1)[:,None]
        pair_dist=np.linalg.norm(nearest[:,None,:]-nearest[None,:,:],axis=2)
        if not np.any(((unit@unit.T)<-.25)&(pair_dist>1.5*.01/max(x,y))):continue
        keep.append(parts[index])
    if not keep:return contours
    # Keep centerlines physically in the original gap, but intentionally do
    # not clip by the full spot: that is precisely why these gaps were lost.
    medial=unary_union(keep).intersection(region).difference(material.buffer(.00001))
    paths=line_parts(scale(medial,xfact=x,yfact=y,origin=(0,0)))
    if not paths:return contours
    center=linemerge(unary_union(paths)) if len(paths)>1 else paths[0]
    # A free-space medial axis also has dead-end branches into tapered corners.
    # They are not narrow through-corridors: at their terminal point the gap
    # closes to solid copper. Following them makes an unnecessary beam-on spur
    # into the thermal spoke/end wall. Keep the normal compensated cap there,
    # rather than extending the copper-sacrificing narrow-gap rescue to the wall.
    retained=[];pruned=[]
    for line in line_parts(center):
        ends=[Point(line.coords[0]),Point(line.coords[-1])]
        end_gap=min(p.distance(copper) for p in ends)
        interior_gap=max(line.interpolate(f,normalized=True).distance(copper) for f in (.25,.5,.75))
        # Boundary sampling is 0.01 mm, so the sampled ridge can stop several
        # microns short of the actual corner. Require a strong taper as well,
        # so genuine uniformly tiny gaps retain their repeated fallback lanes.
        if end_gap<.01 and interior_gap>max(.03,3*end_gap) and _ends_at_copper(line,copper):
            pruned.append(line)
        else:retained.append(line)
    if not retained:
        contours.metadata['narrow_corner_pruning']={'branches':len(pruned),'length_mm':sum(p.length for p in pruned)}
        return contours
    center=linemerge(unary_union(retained)) if len(retained)>1 else retained[0]
    contours.metadata['narrow_corner_pruning']={'branches':len(pruned),'length_mm':sum(p.length for p in pruned)}
    passes=[[],[]]
    blocked_centers=copper.buffer(.000001)
    for line in line_parts(center):
        for i,offset in enumerate((-.0025,.0025)):
            shifted=(Polygon(line).buffer(-offset if shapely.is_ccw(line) else offset,quad_segs=32).boundary
                     if line.is_ring else line.offset_curve(offset,quad_segs=32))
            # Very tiny gaps cannot hold the requested separation. Keep
            # distinct passes in free space; never let centerlines cross copper.
            passes[i].extend(line_parts(shifted.difference(blocked_centers)))
    fallback_indices=[]
    for pieces in passes:
        if pieces:
            fallback_indices.append(len(contours))
            contours.append(unary_union(pieces))
    contours.fallback_indices=set(fallback_indices)
    contours.metadata['narrow_fallback']={'passes':2,'spacing_mm':.005,
        'centerline_length_mm':center.length,
        'note':'Two near-overlapping medial passes; the real calibrated burn can remove intended copper in narrow gaps.'}
    return contours
