from pathlib import Path
from PyInstaller.utils.hooks import collect_all,copy_metadata

root=Path(SPECPATH).parent
datas=[(str(root/'Help.html'),'.'),(str(root/'machining.toml'),'.')]
datas += [(str(p),'pcb_isolator') for p in sorted((root/'src/pcb_isolator').glob('*.js'))]
for name in ('java','build'):
    folder=root/'helix'/name
    if not folder.is_dir():raise RuntimeError('Run helix/setup.ps1 before packaging: missing '+name)
    datas.append((str(folder),'helix/'+name))
datas.append((str(root/'helix/provenance.json'),'helix'))
binaries=[]
hiddenimports=[]
for package in ('pygerber','shapely','ezdxf'):
    package_data,package_binaries,package_imports=collect_all(package)
    datas+=package_data;binaries+=package_binaries;hiddenimports+=package_imports
for distribution in ('pygerber','PySide6','shapely','ezdxf'):
    datas+=copy_metadata(distribution)

a=Analysis([str(root/'packaging/launcher.py')],pathex=[str(root/'src')],
    binaries=binaries,datas=datas,hiddenimports=hiddenimports,
    excludes=['pytest','tkinter','matplotlib','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets',
              'PySide6.QtWebEngineQuick','PySide6.QtPdf','PySide6.QtPdfWidgets'],noarchive=False)
pyz=PYZ(a.pure)
# Qt uses the Windows system ICU API. Do not shadow it with an unrelated
# ICU build discovered in another development tool's PATH (e.g. Poppler).
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower() not in ('icuuc.dll','icuin.dll','icudt.dll')]
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='PCB Isolator',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='PCB Isolator')
