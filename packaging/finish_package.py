"""Add notices and create a shareable ZIP from the tested frozen build."""
from importlib import metadata
from pathlib import Path
import hashlib
import json
import shutil
import sys
import subprocess
import tomllib
from datetime import datetime,timezone
import zipfile

root=Path(__file__).resolve().parent.parent
folder=Path(sys.argv[1]).resolve()
shutil.copyfile(root/'packaging/READ ME.txt',folder/'READ ME.txt')
licenses=folder/'THIRD-PARTY-LICENSES';licenses.mkdir(exist_ok=True)
components=[]
for name in ['PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','pygerber','shapely','ezdxf','numpy',
             'pydantic','pydantic_core','annotated-types','typing-inspection','typing_extensions',
             'click','colorama','fonttools','pyparsing','pillow','packaging','pygments','pyinstaller']:
    dist=metadata.distribution(name)
    components.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License'),
                       'project_urls':dist.metadata.get_all('Project-URL') or []})
    target=licenses/name;target.mkdir(exist_ok=True)
    (target/'METADATA.txt').write_text(dist.read_text('METADATA') or '',encoding='utf-8')
    for file in dist.files or []:
        if any(token in str(file).lower() for token in ('license','copying','notice')):
            source=Path(dist.locate_file(file))
            if source.is_file():
                # Preserve the notice hierarchy without copying files outside the wheel.
                relative=Path(*[p for p in file.parts if p not in ('..','.')])
                destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,destination)
shutil.copyfile(Path(sys.base_prefix)/'LICENSE.txt',licenses/'Python-LICENSE.txt')
for source in (root/'packaging/licenses').glob('*'):shutil.copyfile(source,licenses/source.name)
(licenses/'COMPONENTS.json').write_text(json.dumps(components,indent=2),encoding='utf-8')
(licenses/'Qt-NOTICE.txt').write_text('''This application uses unmodified Qt/PySide6 6.12.0 and shiboken6 6.12.0
under the GNU LGPL version 3. Their shared libraries remain separate in
_internal and may be replaced with compatible modified versions for debugging.
Nothing in this application's terms restricts reverse engineering for that purpose.
The Python runtime and other libraries retain their respective licenses.

Qt/PySide source and licensing information:
https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/
https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/
https://code.qt.io/cgit/pyside/pyside-setup.git/?h=v6.12.0
https://doc.qt.io/qtforpython-6/licenses.html

Qt libraries and bindings have not been modified by this application.
''',encoding='utf-8')
# Preserve the source and notices for the separately replaceable Java helper.
helper=licenses/'Helix-helper';helper.mkdir(exist_ok=True)
for name in ['COPYING.LESSER','provenance.json','README.md','setup.ps1']:
    shutil.copyfile(root/'helix'/name,helper/name)
shutil.copyfile(root/'LICENSE',folder/'LICENSE.txt')
with zipfile.ZipFile(helper/'helper-and-LibLaserCut-source.zip','w',zipfile.ZIP_DEFLATED) as out:
    for name in ['LibLaserCut-source','src']:
        for path in sorted((root/'helix'/name).rglob('*')):
            if path.is_file() and 'test-output' not in path.parts and '.git' not in path.parts:
                out.write(path,Path('helix')/path.relative_to(root/'helix'))
    for name in ['setup.ps1','provenance.json','README.md']:
        out.write(root/'helix'/name,Path('helix')/name)
    out.write(root/'LICENSE','LICENSE')
project=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']
version=project['version'];release=version.replace('rc','-rc.')
try:revision=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,check=True).stdout.strip()
except (OSError,subprocess.CalledProcessError):revision='uncommitted-source'
assets={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'src/pcb_isolator').glob('*.js')}
manifest=dict(project='PCB Manufacturing Studio',application='PCB Isolator',version=version,release=release,
    git_commit=revision,created_utc=datetime.now(timezone.utc).isoformat(),python=sys.version,
    components=components,embedded_review_js=assets,helix=json.loads((root/'helix/provenance.json').read_text(encoding='utf-8')),
    machine_settings_included=False,private_board_data_included=False)
(folder/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
archive=folder.parent/f'PCB-Manufacturing-Studio-{release}-Windows-x64-portable.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for path in sorted(folder.rglob('*')):
        if path.is_file():z.write(path,Path('PCB Isolator')/path.relative_to(folder))
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest,'git_commit':revision},indent=2))
