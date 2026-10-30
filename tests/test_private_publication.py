"""Publication guards tested without contacting GitHub or accessing credentials."""
import importlib.util,json,hashlib,zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest


def test_public_target_is_rejected_before_any_push(tmp_path,monkeypatch):
    source=Path('tools/publish_private.py');spec=importlib.util.spec_from_file_location('private_publisher',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    artifact=tmp_path/'portable.zip';head='1'*40
    with zipfile.ZipFile(artifact,'w') as z:z.writestr('PCB Isolator/BUILD-MANIFEST.json',json.dumps({'git_commit':head}))
    artifact.with_suffix('.zip.sha256').write_text(hashlib.sha256(artifact.read_bytes()).hexdigest()+'  portable.zip')
    calls=[]
    def run(args,capture=False,check=True):
        calls.append(list(map(str,args)));out=''
        if args[:3]==['git','rev-parse','HEAD']:out=head
        elif args[1:]==['api','user']:out=json.dumps({'login':'test-owner'})
        elif args[1:3]==['repo','view']:out=json.dumps({'isPrivate':False,'url':'https://github.com/test-owner/PCB-Manufacturing-Studio'})
        return SimpleNamespace(returncode=0,stdout=out)
    monkeypatch.setattr(module,'run',run);monkeypatch.setattr('sys.argv',['publish_private','--gh-path','gh','--artifact',str(artifact)])
    with pytest.raises(ValueError,match='not private'):module.main()
    assert not any('push' in command for command in calls)
    assert not any('create' in command for command in calls)
