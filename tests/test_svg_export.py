from xml.etree import ElementTree as ET
import ezdxf
import pytest
from pcb_isolator.svg_export import export_svg,NS
from pcb_isolator.app_backend import read_board,generate,default_router,export_preview
from test_job_outputs import make_job


def test_native_curves_and_physical_page(tmp_path):
    doc=ezdxf.new();doc.units=4
    doc.modelspace().add_line((10,20),(20,20))
    doc.modelspace().add_circle((15,25),2)
    doc.modelspace().add_arc((15,25),2,10,300)
    source=tmp_path/'laser.dxf';doc.saveas(source)
    target=tmp_path/'laser.svg';export_svg(source,target)
    root=ET.parse(target).getroot()
    assert root.attrib['width']=='11mm'
    assert root.attrib['height']=='8mm'
    assert not root.findall(f'.//{{{NS}}}g')
    assert not any('transform' in node.attrib for node in root.iter())
    line=root.find(f'{{{NS}}}line')
    assert [line.attrib[k] for k in ('x1','y1','x2','y2')]==['0.5','7.5','10.5','7.5']
    assert line.attrib['fill']=='none' and line.attrib['stroke-width']=='0.01'
    assert len(root.findall(f'.//{{{NS}}}circle'))==1
    paths=root.findall(f'.//{{{NS}}}path')
    assert len(paths)==1 and ' A 2 2 0 1 0 ' in paths[0].attrib['d']


@pytest.mark.parametrize('format,extensions',[('dxf',{'.dxf'}),('svg',{'.svg'}),('both',{'.dxf','.svg'})])
def test_selected_formats_published_and_guide_matches(tmp_path,format,extensions):
    selection=make_job(tmp_path);board=read_board(tmp_path)
    result=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,
        {'width':.075,'overlap':33.3333,'lines':1,'format':format},default_router(),
        make_router=False,output_folder=tmp_path/'preview')
    final=export_preview(result,tmp_path/'final')
    assert {p.suffix for p in final['laser'].iterdir() if p.suffix!='.html'}==extensions
    guide=final['guide'].read_text(encoding='utf-8')
    assert 'laser-isolation-and-marks.'+('svg' if format!='dxf' else 'dxf') in guide
    if format!='dxf':
        root=ET.parse(final['laser']/'laser-isolation-and-marks.svg').getroot()
        assert not root.findall(f'.//{{{NS}}}g')
        doc=ezdxf.readfile(result['record']/'laser/laser-isolation-and-marks.dxf')
        shapes=[e for e in root if e.tag.split('}')[-1] in ('line','circle','path')]
        assert len(shapes)==len(doc.modelspace())
        for shape in shapes:
            assert shape.attrib['stroke']=='#000000' and shape.attrib['stroke-width']=='0.01'
