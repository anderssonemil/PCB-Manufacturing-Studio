import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import pytest
from pcb_isolator.reference_layers import snapshot_path,list_layers,export_layer


def source_job(tmp_path):
    source=tmp_path/'source';source.mkdir()
    board=source/'board.kicad_pcb';board.write_text('(kicad_pcb (layers (0 "F.Cu" signal) (31 "bottom_copper" signal) (37 "F.SilkS" user "Top markings (reference)") (50 "User.1" user "CNC Separation")) (layer "NOT A LAYER TABLE ENTRY"))',encoding='utf-8')
    manifest=dict(source_snapshot='source/board.kicad_pcb',source_sha256=sha256(board.read_bytes()).hexdigest())
    (tmp_path/'manufacturing-job.json').write_text(json.dumps(manifest))
    return board


def test_inventory_aliases_and_source_identity(tmp_path):
    board=source_job(tmp_path);layers=list_layers(tmp_path)
    assert len(layers)==4
    assert layers[1]['name']=='bottom_copper' and layers[1]['plot_name']=='B.Cu'
    assert layers[2]['label']=='F.SilkS · Top markings (reference)'
    board.write_text('changed')
    with pytest.raises(ValueError,match='changed'):list_layers(tmp_path)


def test_no_snapshot_is_allowed_and_escape_rejected(tmp_path):
    path=tmp_path/'manufacturing-job.json';path.write_text('{}');assert list_layers(tmp_path)==[]
    path.write_text(json.dumps(dict(source_snapshot='../wrong.kicad_pcb')))
    with pytest.raises(ValueError,match='inside'):snapshot_path(tmp_path)


def test_export_is_display_only_and_cached(tmp_path,monkeypatch):
    board=source_job(tmp_path);before=board.read_bytes();calls=[]
    monkeypatch.setattr('pcb_isolator.reference_layers.find_cli',lambda:Path('kicad-cli'))
    def run(command,**kwargs):
        calls.append(command);output=Path(command[command.index('--output')+1])
        output.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210"><path d="M10,20 L12,20" stroke="white"/></svg>')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr('pcb_isolator.reference_layers.subprocess.run',run)
    path=export_layer(tmp_path,'bottom_copper');assert 'reference-art' in path.read_text()
    assert calls[0][calls[0].index('--layers')+1]=='B.Cu'
    assert '--mirror' not in calls[0] and '--exclude-drawing-sheet' in calls[0]
    assert export_layer(tmp_path,'bottom_copper')==path and len(calls)==1
    assert board.read_bytes()==before and not (tmp_path/'inputs').exists() and not (tmp_path/'outputs').exists()
    path.write_text('tampered');export_layer(tmp_path,'bottom_copper');assert len(calls)==2
    with pytest.raises(ValueError,match='available'):export_layer(tmp_path,'not-layer')
