import pytest
from shapely.geometry import box,LineString
from shapely.ops import unary_union
from pcb_isolator.isolation import IsolationSettings,generate_isolation,footprint_buffer,isolation_diagnostics

def trial(lines=5):return IsolationSettings(.22,33.3333,lines,.33,.020,True)

def count_crossings(paths,cross):
    hit=unary_union(paths).intersection(cross)
    if hit.is_empty:return 0
    return 1 if hit.geom_type=='Point' else len(hit.geoms)

@pytest.mark.parametrize('vertical,expected',[(False,2),(True,5)])
def test_shared_035_gap_has_evenly_spaced_lanes(vertical,expected):
    copper=box(0,0,1,5).union(box(1.35,0,2.35,5)) if vertical else box(0,0,5,1).union(box(0,1.35,5,2.35))
    cross=LineString([(1.0001,2.5),(1.3499,2.5)]) if vertical else LineString([(2.5,1.0001),(2.5,1.3499)])
    paths=generate_isolation(copper,trial())
    assert count_crossings(paths,cross)==expected
    assert footprint_buffer(unary_union(paths),trial()).intersection(copper).area<1e-7
    points=unary_union(paths).intersection(cross)
    values=sorted((p.x if vertical else p.y) for p in points.geoms)
    spacings=[b-a for a,b in zip(values,values[1:])]
    assert max(spacings)-min(spacings)<.00001


def test_maximum_and_broad_gap_and_impossible_gap():
    copper=box(0,0,5,1).union(box(0,1.7,5,2.7))
    paths=generate_isolation(copper,trial())
    assert count_crossings(paths,LineString([(2.5,1.0001),(2.5,1.6999)]))==5
    tiny=box(0,0,5,1).union(box(0,1.02,5,2))
    paths=generate_isolation(tiny,trial())
    assert count_crossings(paths,LineString([(2.5,1.0001),(2.5,1.0199)]))==2
    assert isolation_diagnostics(tiny,paths,trial())['predicted_overcut_area_mm2']>0
    assert paths.metadata['narrow_fallback']['passes']==2


def test_exported_adaptive_curves_and_rounded_pads_protect_copper(tmp_path):
    import ezdxf
    from ezdxf.path import make_path
    from shapely.geometry import Point
    from pcb_isolator.dxf_export import export_dxf
    copper=LineString([(0,0),(3,3),(7,3)]).buffer(.1).union(Point(7,3).buffer(.6)).union(box(0,1,2,1.35))
    settings=trial();paths=generate_isolation(copper,settings)
    target=tmp_path/'adaptive.dxf';export_dxf(copper,paths,settings,target,.005)
    recovered=unary_union([LineString([(v.x,v.y) for v in make_path(e).flattening(.000001)]) for e in ezdxf.readfile(target).modelspace()])
    assert recovered.intersection(copper).length<1e-7
    assert not ezdxf.readfile(target).audit().has_errors


def test_narrow_annular_pad_gets_two_continuous_passes(tmp_path):
    from shapely.geometry import Point
    import ezdxf
    from pcb_isolator.dxf_export import export_dxf
    pad=Point(0,0).buffer(1,quad_segs=128)
    surround=box(-4,-4,4,4).difference(Point(0,0).buffer(1.03,quad_segs=128))
    copper=pad.union(surround);paths=generate_isolation(copper,trial())
    fallback=[paths[i] for i in sorted(paths.fallback_indices)]
    assert len(fallback)==2
    for contour in fallback:
        assert contour.geom_type=='LineString' and contour.is_ring
        assert contour.intersection(copper).is_empty
    for degrees in range(0,360,15):
        from math import cos,sin,radians
        x,y=cos(radians(degrees)),sin(radians(degrees))
        cross=LineString([(x,y),(1.03*x,1.03*y)])
        assert count_crossings(fallback,cross)==2
    destination=tmp_path/'annular.dxf';export_dxf(copper,paths,trial(),destination,.005)
    doc=ezdxf.readfile(destination)
    assert not doc.audit().has_errors
    for i in paths.fallback_indices:
        entities=list(doc.modelspace().query(f'*[layer=="ISOLATION_{i+1:02}"]'))
        assert len(entities)==1
        assert entities[0].dxftype()=='CIRCLE' or entities[0].closed


def test_laser_time_includes_both_close_passes():
    from pcb_isolator.laser_timing import estimate_laser_time
    paths=[LineString([(0,0),(10,0)]),LineString([(0,.005),(10,.005)])]
    timing=estimate_laser_time(paths)
    assert timing['laser_on_length_mm']==20
    assert timing['objects']==2
    assert timing['estimated_seconds']>20/(790/93)


def test_partial_directional_gap_forms_a_closed_etched_isolation_barrier():
    from shapely.geometry import Point
    from pcb_isolator.isolation import planned_footprint
    stock=box(-5,-5,5,5)
    copper=Point(0,0).buffer(1.6,quad_segs=128).union(
        stock.difference(Point(0,0).buffer(1.905355,quad_segs=128)))
    settings=trial();paths=generate_isolation(copper,settings)
    fallback=[paths[i] for i in sorted(paths.fallback_indices)]
    assert count_crossings(fallback,LineString([(0,1.60001),(0,1.9053)]))==2
    assert count_crossings(fallback,LineString([(0,-1.60001),(0,-1.9053)]))==2
    # Etching starts with a solid copper sheet, not the already-separated
    # KiCad copper polygons. The burn must enclose an isolated central island.
    after_etch=stock.difference(planned_footprint(paths,settings))
    center=[p for p in after_etch.geoms if p.contains(Point(0,0))]
    assert len(center)==1 and center[0].area<12


def test_barely_fitting_gap_keeps_two_high_overlap_lanes():
    copper=box(0,0,5,1).union(box(0,1.335,5,2.335))
    settings=trial();paths=generate_isolation(copper,settings)
    cross=LineString([(2.5,1.0001),(2.5,1.3349)])
    assert count_crossings(paths,cross)==2
    assert footprint_buffer(unary_union(paths),settings).intersection(copper).area<1e-7


def thermal_copper(gap):
    from shapely.geometry import Point
    # Representative large through-hole pad and broad thermal spokes.
    pad=Point(0,0).buffer(2.325,quad_segs=128)
    stock=box(-5,-5,5,5)
    surround=stock.difference(Point(0,0).buffer(2.325+gap,quad_segs=128))
    spokes=box(-5,-.75,5,.75).union(box(-.75,-5,.75,5))
    return pad.union(surround).union(spokes)


def test_thermal_relief_corners_do_not_get_beam_on_medial_spurs():
    copper=thermal_copper(.35)
    settings=trial();paths=generate_isolation(copper,settings)
    assert paths.metadata['narrow_corner_pruning']['branches']>0
    assert not getattr(paths,'fallback_indices',set())
    assert footprint_buffer(unary_union(paths),settings).intersection(copper).area<1e-6


def test_thermal_narrow_arc_kept_but_not_its_tapered_spoke_corners():
    from shapely.geometry import Point
    from pcb_isolator.adaptive_isolation import line_parts
    copper=thermal_copper(.30);paths=generate_isolation(copper,trial())
    assert paths.metadata['narrow_corner_pruning']['branches']>0
    assert paths.metadata['narrow_fallback']['passes']==2
    for i in paths.fallback_indices:
        for line in line_parts(paths[i]):
            assert min(Point(line.coords[0]).distance(copper),Point(line.coords[-1]).distance(copper))>.02


def test_real_narrow_corridor_remains_after_dead_end_pruning():
    copper=box(0,0,5,1).union(box(0,1.30,5,2.30))
    settings=trial();paths=generate_isolation(copper,settings)
    assert count_crossings(paths,LineString([(2.5,1.0001),(2.5,1.2999)]))==2
    assert paths.metadata['narrow_fallback']['passes']==2


def test_tiny_through_gap_is_not_a_solid_copper_terminal():
    from shapely.geometry import Polygon
    from pcb_isolator.narrow_isolation import _ends_at_copper
    # Narrowing channel remains open beyond the sampled endpoint.
    top=Polygon([(0,.2),(5,.006),(6,.006),(6,2),(0,2)])
    bottom=Polygon([(0,-.2),(5,-.006),(6,-.006),(6,-2),(0,-2)])
    assert not _ends_at_copper(LineString([(0,0),(5,0)]),top.union(bottom))
    # The same ray really does terminate at a copper end wall in a blind gap.
    assert _ends_at_copper(LineString([(0,0),(5,0)]),top.union(bottom).union(box(5.01,-2,6,2)))
