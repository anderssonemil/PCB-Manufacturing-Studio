"""Audit the actual tracked/staged set, not the surrounding private workspace."""
from pathlib import Path
import json,re,subprocess,sys
ROOT=Path(__file__).resolve().parent.parent
files=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True).stdout.decode('utf-8').split('\0')
forbidden=[];secrets=[];total=0
private_names={'helix-settings.json','laser-transmissions.jsonl','config.toml','OPEN-TASKS.md','TESTING-BACKLOG.md','LAGUNA-SWIFT-NOTES.md'}
patterns=[re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(rb'github_pat_[A-Za-z0-9_]{30,}'),re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
for relative in filter(None,files):
 p=Path(relative);data=(ROOT/p).read_bytes();total+=len(data)
 if p.parts[0] in {'.venv','.tools','generated','jobs','local-boards','local-machine','_norton_'} or p.name in private_names or relative.startswith(('helix/java/','helix/build/','docs/laser-calibration-handoff-')) or p.name.startswith('PROJECT-CHECKPOINT-') or len(data)>25_000_000:forbidden.append(relative)
 if not relative.startswith('helix/LibLaserCut-source/') and any(pattern.search(data) for pattern in patterns):secrets.append(relative)
report=dict(files=len(list(filter(None,files))),bytes=total,forbidden_files=forbidden,possible_secrets=secrets)
print(json.dumps(report,indent=2))
if forbidden or secrets:sys.exit(1)
