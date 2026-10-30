from pathlib import Path
import re
import pytest
from shapely.geometry import LineString, box

from pcb_isolator.drills import DrillFeature
from pcb_isolator.router import (load_machining,depth_passes,drill_moves,
                                compensated_profiles,profile_moves,write_draft)


def test_depth_passes():
    assert depth_passes(1.9,0.95)==[-0.95,-1.9]
    assert depth_passes(2,0.95)==[-0.95,-1.9,-2]
    assert depth_passes(1.6+0.3,0.95)==pytest.approx([-0.95,-1.9])


def test_drill_retract_and_no_speed_commands(tmp_path):
    config=load_machining(Path('machining.toml'))
    config['drilling']['peck_mm']=0
    holes=[DrillFeature('a',0.5,3,4),DrillFeature('b',0.5,8,9)]
    moves=drill_moves(holes,1.9,config)
    path=tmp_path/'test.mmg.draft'
    write_draft(path,moves,config,'Test')
    text=path.read_text()
    assert 'N10M03' in text and 'M05' in text
    assert not re.search(r'S\d',text)
    assert text.index('G00X3.000Y4.000')<text.index('G00Z5.080')
    assert text.count('G1Z-1.900F127.0')==2
    assert text.count('G00Z5.080')==3
    assert text.endswith('M30\n%\n')


def test_profile_compensation_and_cut_order():
    rings=[LineString(box(0,0,20,10).exterior.coords),LineString(box(6,3,14,7).exterior.coords)]
    paths=compensated_profiles(rings,2)
    assert [p['kind'] for p in paths]==['inside','outside']
    assert LineString(paths[0]['points']).bounds==pytest.approx((7,4,13,6))
    assert LineString(paths[1]['points']).bounds==pytest.approx((-1,-1,21,11))
    config=load_machining(Path('machining.toml'))
    moves=profile_moves(paths,1.9,config)
    assert [m['z'] for m in moves if m['g']==1 and 'z' in m]==[-0.95,-1.9,-0.95,-1.9]


def test_small_cutout_rejected():
    rings=[LineString(box(0,0,20,10).exterior.coords),LineString(box(6,3,7,4).exterior.coords)]
    with pytest.raises(ValueError,match='does not fit'):
        compensated_profiles(rings,2)


def test_rapid_xy_without_clearance_rejected(tmp_path):
    config=load_machining(Path('machining.toml'))
    with pytest.raises(ValueError,match='Rapid XY'):
        write_draft(tmp_path/'bad.mmg.draft',[{'g':0,'x':2,'y':3}],config,'Test')


def test_peck_depths_and_separate_retract():
    config=load_machining(Path('machining.toml'))
    config['drilling']['peck_mm']=0.7
    moves=drill_moves([DrillFeature('a',0.5,3,4)],1.9,config)
    assert [m['z'] for m in moves if m['g']==1]==pytest.approx([-0.7,-1.4,-1.9])
    retracts=[moves[i+1]['z'] for i,m in enumerate(moves) if m['g']==1]
    assert retracts==[1.0,1.0,5.08]
    approaches=[moves[i-1]['z'] for i,m in enumerate(moves) if m['g']==1]
    assert approaches==pytest.approx([0.5,-0.5,-1.2])


def test_travel_between_holes_always_at_full_clearance():
    config=load_machining(Path('machining.toml'))
    moves=drill_moves([DrillFeature('a',0.5,3,4),DrillFeature('b',0.5,8,9)],1.9,config)
    z=None
    for move in moves:
        if move['g']==0 and 'x' in move:
            assert z==5.08
        z=move.get('z',z)


def test_per_size_override_and_spoilboard_independence():
    config=load_machining(Path('machining.toml'))
    config['drilling']['tools']=[{'diameter_mm':1.0,'peck_mm':0.0,'feed_mm_min':150.0}]
    holes=[DrillFeature('a',0.5,3,4),DrillFeature('b',1.0,8,9)]
    moves=drill_moves(holes,1.9,config)
    assert [m['z'] for m in moves if m['g']==1]==pytest.approx([-0.7,-1.4,-1.9,-1.9])
    assert [m['f'] for m in moves if m['g']==1]==[127,127,127,150]
    spoil=drill_moves([DrillFeature('pin',3.175,3,4)],5,config,override=config['spoilboard'])
    assert [m['z'] for m in spoil if m['g']==1]==[-5]


@pytest.mark.parametrize('value', [0,-1,float('nan'),6])
def test_invalid_peck_retract(value):
    from pcb_isolator.router import drilling_options
    config=load_machining(Path('machining.toml'))
    config['drilling']['peck_retract_mm']=value
    with pytest.raises(ValueError):
        drilling_options(config)


def test_profile_rapid_approach_before_first_plunge():
    config=load_machining(Path('machining.toml'))
    paths=compensated_profiles([LineString(box(0,0,20,10).exterior.coords)],2.54)
    moves=profile_moves(paths,1.9,config)
    first=next(i for i,m in enumerate(moves) if m['g']==1)
    assert moves[first-1]=={'g':0,'z':0.5}
    assert moves[first]['z']==-0.95


def test_every_drill_approaches_at_rapid_without_xy():
    config=load_machining(Path('machining.toml'))
    moves=drill_moves([DrillFeature('a',0.5,3,4),DrillFeature('b',0.5,8,9)],1.9,config)
    for i,move in enumerate(moves):
        if move['g']==1:
            assert moves[i-1]['g']==0 and set(moves[i-1])=={'g','z'}
