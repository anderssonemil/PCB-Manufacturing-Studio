import json,re
import pytest
from shapely.geometry import box,LinearRing
from pcb_isolator.drills import DrillFeature
from pcb_isolator.paper_print import paper_data,attach_paper_print


def test_paper_geometry_preserves_dimensions_centers_and_holes():
    g=box(10,20,90,60).difference(box(15,25,16,26))
    outline=[LinearRing([(9,19),(91,19),(91,61),(9,61)])]
    d=paper_data('test','Laser',g,outline,[DrillFeature('a',.8,12,23),DrillFeature('b',.8,14.54,23)])
    assert d['bounds']==[9,-61,82,42]
    assert d['copper'].count(' Z')==2
    assert d['holes'][1]['x']-d['holes'][0]['x']==pytest.approx(2.54)
    assert '12' not in d['outline']


def test_paper_embedding_is_standalone_and_safe_for_titles():
    d=paper_data('</script><script>bad()</script>','Router',box(0,0,80,40))
    page=attach_paper_print('<button id="fit">Fit</button>',d,'<button id="fit">')
    assert 'Print 1:1' in page and '50 mm' in page and '20 mm vertical' in page
    payload=re.search(r'<script id="paper-print-data" type="application/json">(.*?)</script>',page).group(1)
    assert '<script>' not in payload and json.loads(payload)['title']==d['title']
    assert 'window.open' in page and 'w.print()' in page
    assert "setAttribute('width',(width+pad*2)+'mm')" in page
    assert "setAttribute('height',(height+pad*2)+'mm')" in page
    assert 'laserPlayback' not in page and 'fetch(' not in page


def test_router_paper_uses_source_positions_and_assigned_diameters(tmp_path):
    from test_job_outputs import make_job
    from pcb_isolator.app_backend import read_board,generate,default_router
    selection=make_job(tmp_path);board=read_board(tmp_path);router=default_router()
    router['drilling']['assignments']=[{'source_diameter_mm':.5,'tool_diameter_mm':.8},{'source_diameter_mm':1.,'tool_diameter_mm':.8}]
    result=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,
        {'width':.075,'overlap':33.3,'lines':1},router,make_laser=False,output_folder=tmp_path/'paper')
    page=result['router_review'].read_text(encoding='utf-8')
    data=json.loads(re.search(r'<script id="paper-print-data" type="application/json">(.*?)</script>',page).group(1))
    assert data['bounds']==[0.,-10.,20.,10.]
    holes={(f['x'],f['y']):f['diameter_mm'] for f in data['holes']}
    assert holes=={(3.,3.):3.175,(17.,3.):3.175,(5.,5.):.8,(7.,5.):.8}
    assert len(data['tools'])==3
