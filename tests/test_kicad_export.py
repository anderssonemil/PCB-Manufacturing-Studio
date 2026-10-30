from hashlib import sha256
import json
from pathlib import Path
import pytest

from pcb_isolator.kicad_export import load_job, resolve_job_folder


def fake_job(tmp_path):
    inputs = tmp_path/'inputs'; inputs.mkdir()
    files = {'copper':'inputs/copper.gbr','outline':'inputs/outline.dxf', 'drills':['inputs/holes.drl']}
    hashes = {}
    for name in ['copper.gbr','outline.dxf','holes.drl']:
        p = inputs/name; p.write_text('test')
        hashes['inputs/'+name] = sha256(p.read_bytes()).hexdigest()
    data = {'schema':'pcb-isolator-export','version':1,'units':'mm','origin':'absolute',
            'mirrored':False,'files':files,'sha256':hashes}
    (tmp_path/'manufacturing-job.json').write_text(json.dumps(data))
    return data


def test_load_job(tmp_path):
    fake_job(tmp_path)
    copper, drills, outline = load_job(tmp_path)
    assert copper.name == 'copper.gbr'
    assert len(drills) == 1
    assert outline.name == 'outline.dxf'


def test_changed_input_rejected(tmp_path):
    fake_job(tmp_path)
    (tmp_path/'inputs/holes.drl').write_text('another revision')
    with pytest.raises(ValueError, match='changed'):
        load_job(tmp_path)


def test_path_escape_rejected(tmp_path):
    data = fake_job(tmp_path)
    data['files']['copper'] = '../outside.gbr'
    (tmp_path/'manufacturing-job.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='inside'):
        load_job(tmp_path)


def test_parent_resolves_latest_export(tmp_path):
    for name, date in [('older','20260101T000000Z'), ('newer','20260201T000000Z')]:
        child = tmp_path/name; child.mkdir()
        data = fake_job(child)
        data['created_utc'] = date
        (child/'manufacturing-job.json').write_text(json.dumps(data))
    assert resolve_job_folder(tmp_path).name == 'newer'
    assert resolve_job_folder(tmp_path/'older').name == 'older'


def test_empty_parent_error(tmp_path):
    with pytest.raises(ValueError, match='No manufacturing export'):
        resolve_job_folder(tmp_path)
