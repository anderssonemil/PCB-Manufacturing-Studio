import pytest
from pcb_isolator.router_animation import parse_motions


def test_retains_xyz_peck_order_and_modal_feed():
    moves=parse_motions('(test)\nN10M03\nN20G00Z5\nN30G00X10Y0\nN40G00Z0.5\nN50G1Z-0.7F127\nN60G00Z1\nN70G00Z-0.5\nN80G1Z-1.4\nN90G00Z12\nN100M05\n%',[-10,0])
    assert len(moves)==8
    assert moves[0]['initial_z_unknown'] and moves[0]['length_mm']==0
    assert moves[1]['length_mm']==20
    assert [m['to'][2] for m in moves]==[5,5,.5,-.7,1,-.5,-1.4,12]
    assert [m['feed'] for m in moves if not m['rapid']]==[127,127]
    assert moves[6]['from']==[10,0,-.5]
    assert moves[6]['length_mm']==pytest.approx(.9)


def test_rejects_uninterpreted_motion_and_missing_feed():
    with pytest.raises(ValueError,match='G00/G1'):parse_motions('G2X1Y1Z0',[0,0])
    with pytest.raises(ValueError,match='positive feed'):parse_motions('G00Z1\nG1Z-1',[0,0])
    with pytest.raises(ValueError,match='before a commanded Z'):parse_motions('G00X1',[0,0])
    with pytest.raises(ValueError,match='spindle-speed'):parse_motions('M03S16000',[0,0])
