from math import hypot
from pathlib import Path
import pytest

from pcb_isolator.drills import DrillFeature
from pcb_isolator.pin_avoidance import Keepout,avoid_pins,route_around,segment_clear
from pcb_isolator.router import load_machining


def pins():
    return [DrillFeature('pin',3.2,10,0),DrillFeature('pin2',3.2,10,20)]


def test_detour_never_crosses_pin_even_above_it():
    config=load_machining(Path('machining.toml'));config['alignment_pins']['pins_removed_before_machining']=False
    moves=[{'g':0,'z':20},{'g':0,'x':20,'y':0}]
    planned,report=avoid_pins(moves,pins(),3.175,0.5,config)
    assert report['detoured_travels']==1
    assert report['travel_clearance_mm']==12
    obstacles=[Keepout(p.x,p.y,report['keepout_radius_mm']) for p in pins()]
    xy=(0,0)
    for move in planned:
        if 'x' in move:
            target=(move['x'],move['y'])
            assert segment_clear(xy,target,obstacles)
            xy=target
    assert xy==(20,0)


def test_plunge_or_cut_near_pin_rejected():
    config=load_machining(Path('machining.toml'));config['alignment_pins']['pins_removed_before_machining']=False
    for moves in [
        [{'g':0,'z':5.08},{'g':0,'x':10,'y':0},{'g':1,'z':-1,'f':127}],
        [{'g':0,'z':5.08},{'g':1,'x':20,'y':0,'f':508}],
    ]:
        with pytest.raises(ValueError,match='keepout'):
            avoid_pins(moves,pins(),3.175,2.54,config)


def test_travel_height_raised_but_peck_retract_preserved():
    config=load_machining(Path('machining.toml'));config['alignment_pins']['pins_removed_before_machining']=False
    moves=[{'g':0,'z':5.08},{'g':0,'x':0,'y':10},{'g':1,'z':-0.7,'f':127},
           {'g':0,'z':1},{'g':1,'z':-1.4,'f':127},{'g':0,'z':5.08}]
    planned,_=avoid_pins(moves,pins(),3.175,0.5,config)
    assert [m['z'] for m in planned if m['g']==0 and 'z' in m]==[12,1,12]


def test_larger_cutter_increases_keepout():
    config=load_machining(Path('machining.toml'));config['alignment_pins']['pins_removed_before_machining']=False
    moves=[{'g':0,'z':5.08}]
    _,small=avoid_pins(moves,pins(),3.175,0.5,config)
    _,large=avoid_pins(moves,pins(),3.175,6.0,config)
    assert large['keepout_radius_mm']>small['keepout_radius_mm']


def test_start_position_and_low_park_rejected():
    config=load_machining(Path('machining.toml'));config['alignment_pins']['pins_removed_before_machining']=False
    config['alignment_pins']['start_x_mm']=10
    with pytest.raises(ValueError,match='staged start'):
        avoid_pins([],pins(),3.175,0.5,config)
    config['alignment_pins']['start_x_mm']=0
    config['machine']['park_z_mm']=10
    with pytest.raises(ValueError,match='Park Z'):
        avoid_pins([],pins(),3.175,0.5,config)


def test_overlap_obstacles_still_avoided():
    obstacles=[Keepout(10,0,3),Keepout(13,0,3)]
    xy=(0,0)
    for target in route_around(xy,(25,0),obstacles):
        assert segment_clear(xy,target,obstacles)
        xy=target
    assert xy==(25,0)
