from types import SimpleNamespace
from math import dist
import ezdxf
import pytest
from shapely.geometry import LineString,box
from shapely.ops import unary_union
from pcb_isolator.travel_optimizer import TravelCosts,optimize_points,optimize_cut_paths,join_paths,rapid_distance
from pcb_isolator.pin_avoidance import Keepout,route_around,segment_clear
from pcb_isolator.router import profile_moves
from pcb_isolator.app_backend import default_router
from pcb_isolator.separation import load_separation,separation_paths


def point_score(features,start,costs):
    points=[start]+[(f.x,f.y) for f in features]
    return sum(costs.distance(a,b) for a,b in zip(points,points[1:]))


def test_drills_stop_zigzagging_and_keep_every_hole():
    features=[SimpleNamespace(id=f'{x}-{y}',x=x,y=y) for x in range(12) for y in (0,50)]
    costs=TravelCosts([]);start=(-5,0)
    optimized=optimize_points(features,start,costs)
    assert sorted(f.id for f in optimized)==sorted(f.id for f in features)
    assert point_score(optimized,start,costs)<point_score(features,start,costs)*.2
    assert [f.id for f in optimize_points(features,start,costs)]==[f.id for f in optimized]
    assert features[0].id=='0-0'


def test_costs_include_actual_pin_detours():
    obstacles=[Keepout(0,0,3)]
    costs=TravelCosts(obstacles)
    assert costs.distance((-10,0),(10,0))>20
    assert costs.distance((-10,0),(10,0))==costs.distance((10,0),(-10,0))
    features=[SimpleNamespace(id=str(i),x=x,y=y) for i,(x,y) in enumerate([(-5,5),(5,-5),(-5,-5),(5,5)])]
    start=(-10,0);ordered=optimize_points(features,start,costs)
    assert point_score(ordered,start,costs)<=point_score(features,start,costs)
    previous=start
    for f in ordered:
        for p in route_around(previous,(f.x,f.y),obstacles):
            assert segment_clear(previous,p,obstacles);previous=p


@pytest.mark.parametrize('passes',[1,2,3])
def test_cut_entries_directions_and_exit_account_for_pass_count(passes):
    config=default_router();config['profile']['stepdown_mm']=1;config['alignment_pins'].update(start_x_mm=0,start_y_mm=0)
    paths=[{'kind':'separation','closed':False,'points':[(80,2),(2,2)]},
           {'kind':'separation','closed':False,'points':[(85,5),(90,5)]},
           {'kind':'separation','closed':False,'points':[(30,5),(15,5)]}]
    anchor=(100,10)
    profile={'kind':'outside','points':[anchor,(110,10),(110,20),anchor]}
    best=optimize_cut_paths(paths,(0,0),anchor,passes,TravelCosts([]))
    assert unary_union([LineString(p['points']) for p in paths]).equals(unary_union([LineString(p['points']) for p in best]))
    assert rapid_distance(profile_moves(best+[profile],passes,config),config)<=rapid_distance(profile_moves(paths+[profile],passes,config),config)


def test_connected_arcs_join_without_changing_cut_shape(tmp_path):
    document=ezdxf.new('R2010');document.units=4
    document.modelspace().add_arc((10,10),3,0,90)
    document.modelspace().add_line((10,13),(18,13))
    path=tmp_path/'lines-and-arc.dxf';document.saveas(path)
    paths,_=separation_paths(load_separation(path),[LineString(box(0,0,30,30).exterior.coords)])
    merged=join_paths(paths)
    assert len(merged)==1
    original=unary_union([LineString(p['points']) for p in paths])
    joined=unary_union([LineString(p['points']) for p in merged])
    assert original.equals(joined)
    ordered=optimize_cut_paths(merged,(0,0),(30,30),2,TravelCosts([]))
    assert original.equals(unary_union([LineString(p['points']) for p in ordered]))
