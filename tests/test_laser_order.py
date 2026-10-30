from collections import Counter
from pcb_isolator.laser_order import optimize_laser_routes,travel_distance


def segments(routes):
    return Counter(tuple(sorted((a,b))) for r in routes for a,b in zip(r,r[1:]))


def test_exact_segments_and_repeated_exposures_preserved():
    routes=[[(100,100),(102,100),(102,102),(100,102),(100,100)],[(2,1),(3,2)],[(50,2),(51,2)],[(2,1),(3,2)]]
    result,report=optimize_laser_routes(routes,.04)
    assert segments(result)==segments(routes)
    assert len(result)==len(routes)
    assert travel_distance(result)<=travel_distance(routes)
    assert report['saved_percent']>0
    assert routes[0][0]==(100,100)


def test_closed_entry_rotation_and_determinism():
    routes=[[(100,100),(0,100),(0,0),(100,0),(100,100)]]
    result,report=optimize_laser_routes(routes,.04)
    assert result[0][0]==(0,0) and result[0][-1]==(0,0)
    assert segments(result)==segments(routes)
    assert result==optimize_laser_routes(routes,.04)[0]
