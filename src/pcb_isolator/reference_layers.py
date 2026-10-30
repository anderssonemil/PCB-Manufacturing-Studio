"""Display-only KiCad layer exports from the job's verified saved snapshot."""
from hashlib import sha256
from pathlib import Path
import json,re,subprocess,tempfile
from xml.etree import ElementTree as ET
from .kicad_export import find_cli


def snapshot_path(job):
    job=Path(job).resolve();manifest=json.loads((job/'manufacturing-job.json').read_text(encoding='utf-8'))
    relative=manifest.get('source_snapshot')
    if not relative:return None
    path=(job/relative).resolve()
    if not path.is_relative_to(job/'source'):raise ValueError('Reference snapshot must stay inside the job source folder.')
    expected=manifest.get('source_sha256')
    if not expected or sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('Saved KiCad snapshot changed. Reload the board before viewing extra layers.')
    return path


def list_layers(job):
    path=snapshot_path(job)
    if path is None:return []
    text=path.read_text(encoding='utf-8')
    start=re.search(r'\(layers\s',text)
    if not start:return []
    depth=0;quoted=False;escaped=False;end=None
    for i in range(start.start(),len(text)):
        char=text[i]
        if escaped:escaped=False;continue
        if quoted and char=='\\':escaped=True;continue
        if char=='"':quoted=not quoted;continue
        if quoted:continue
        if char=='(':depth+=1
        elif char==')':
            depth-=1
            if not depth:end=i;break
    if end is None:return []
    table=text[start.end():end]
    rows=[]
    pattern=r'\(\s*(\d+)\s+("(?:[^"\\]|\\.)*")\s+\w+(?:\s+("(?:[^"\\]|\\.)*"))?[^()]*\)'
    for match in re.finditer(pattern,table):
        number,name,alias=match.groups();name=json.loads(name);alias=json.loads(alias) if alias else name
        layer_id=int(number)
        standard={0:'F.Cu',31:'B.Cu',**{i:f'In{i}.Cu' for i in range(1,31)},**dict(enumerate(['B.Adhes','F.Adhes','B.Paste','F.Paste','B.SilkS','F.SilkS','B.Mask','F.Mask','Dwgs.User','Cmts.User','Eco1.User','Eco2.User','Edge.Cuts','Margin','B.CrtYd','F.CrtYd','B.Fab','F.Fab'],32)),**{i:f'User.{i-49}' for i in range(50,59)}}
        rows.append(dict(id=layer_id,name=name,plot_name=standard.get(layer_id,name),label=name if name==alias else name+' · '+alias))
    return rows


def export_layer(job,name):
    job=Path(job).resolve();source=snapshot_path(job)
    if source is None:raise ValueError('This job has no saved KiCad board snapshot. Open the saved KiCad board to view extra layers.')
    layer=next((r for r in list_layers(job) if r['name']==name),None)
    if layer is None:raise ValueError('Layer is not available in this board snapshot.')
    plot_name=layer['plot_name']
    if ',' in plot_name:raise ValueError('This custom layer name needs a canonical KiCad layer mapping before it can be plotted.')
    cache=job/'reference-layers';cache.mkdir(exist_ok=True)
    token=sha256(name.encode()).hexdigest()[:16];target=cache/(token+'.svg');record=cache/(token+'.json')
    source_hash=sha256(source.read_bytes()).hexdigest()
    if target.exists() and record.exists():
        try:saved=json.loads(record.read_text(encoding='utf-8'))
        except (OSError,ValueError):saved={}
        if saved.get('version')==1 and saved.get('source_sha256')==source_hash and saved.get('sha256')==sha256(target.read_bytes()).hexdigest():return target
    cli=find_cli()
    with tempfile.TemporaryDirectory(prefix='plot-',dir=cache) as temporary:
        output=Path(temporary)/'layer.svg'
        command=[str(cli),'pcb','export','svg','--layers',plot_name,'--mode-single','--page-size-mode','1','--exclude-drawing-sheet','--drill-shape-opt','0','--output',str(output),str(source)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not output.exists():raise ValueError('Could not plot reference layer '+name+': '+(result.stderr or result.stdout)[-1200:])
        # Render only actual ink, so the SVG paper size does not alter board fit.
        root=ET.fromstring(output.read_bytes());group=ET.Element('{http://www.w3.org/2000/svg}g',{'id':'reference-art'})
        for child in list(root):
            if child.tag.rsplit('}',1)[-1] in ('defs','title','desc'):continue
            root.remove(child);group.append(child)
        root.append(group);target.write_bytes(ET.tostring(root,encoding='utf-8',xml_declaration=True))
    record.write_text(json.dumps(dict(version=1,layer=name,source_sha256=source_hash,sha256=sha256(target.read_bytes()).hexdigest())),encoding='utf-8')
    return target
