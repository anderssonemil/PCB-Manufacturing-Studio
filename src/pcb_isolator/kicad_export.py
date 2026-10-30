"""Export one saved KiCad board into a self-contained manufacturing job."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import re
import uuid
import ezdxf


def find_cli():
    found = shutil.which('kicad-cli')
    if found:
        return Path(found)
    base = Path(os.environ.get('ProgramFiles', r'C:\Program Files'))/'KiCad'
    for version in ('9.0', '8.0'):
        candidate = base/version/'bin/kicad-cli.exe'
        if candidate.exists():
            return candidate
    raise ValueError('KiCad 8 or 9 command-line exporter was not found.')


def export_board(board, root=Path('jobs'), cli=None):
    board = Path(board).resolve()
    if board.suffix.lower() != '.kicad_pcb' or not board.is_file():
        raise ValueError('Select a saved .kicad_pcb board file.')
    cli = Path(cli) if cli else find_cli()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    job = Path(root).resolve()/board.stem/(stamp+'-'+uuid.uuid4().hex[:6])
    inputs = job/'inputs'
    source = job/'source'
    inputs.mkdir(parents=True)
    source.mkdir()
    # Every output is made from this single immutable-in-use snapshot, so a
    # later save in the open KiCad editor cannot mix revisions mid-export.
    snapshot = source/board.name
    snapshot.write_bytes(board.read_bytes())
    separation_layers=re.findall(r'\(\s*\d+\s+"(User\.\d+)"\s+\w+\s+"CNC Separation"\s*\)',snapshot.read_text(encoding='utf-8'),re.I)
    if len(separation_layers)>1:raise ValueError('Use only one layer named CNC Separation.')
    commands = [
        ['pcb','export','gerbers','--layers','B.Cu,Edge.Cuts','--no-protel-ext',
         '--precision','6','--output',str(inputs)+os.sep,str(snapshot)],
        ['pcb','export','drill','--format','excellon','--drill-origin','absolute',
         '--excellon-units','mm','--excellon-zeros-format','decimal',
         '--excellon-oval-format','alternate','--excellon-separate-th',
         '--output',str(inputs)+os.sep,str(snapshot)],
        ['pcb','export','dxf','--layers','Edge.Cuts','--mode-single',
         '--output-units','mm','--drill-shape-opt','0',
         '--output',str(inputs/'outline.dxf'),str(snapshot)],
    ]
    if separation_layers:
        commands.append(['pcb','export','dxf','--layers',separation_layers[0],'--mode-single',
                         '--output-units','mm','--drill-shape-opt','0','--output',str(inputs/'separation.dxf'),str(snapshot)])
    logs = []
    try:
        version = subprocess.run([str(cli),'version'], capture_output=True, text=True, check=True).stdout.strip()
        for command in commands:
            result = subprocess.run([str(cli),*command], capture_output=True, text=True)
            logs.append({'command': command, 'returncode': result.returncode,
                         'stdout': result.stdout, 'stderr': result.stderr})
            if result.returncode:
                raise ValueError(f'KiCad export failed: {result.stderr or result.stdout}')
        # KiCad 9 exports millimeter coordinates with unitless DXF metadata.
        # The command above explicitly requested mm, so stamp those known
        # units here without changing coordinates. Never infer arbitrary DXFs.
        for name in ['outline.dxf']+(['separation.dxf'] if separation_layers else []):
            outline_doc = ezdxf.readfile(inputs/name)
            if outline_doc.units not in (0, 4):
                raise ValueError('KiCad DXF returned unexpected units despite millimeter export.')
            if outline_doc.dxfversion < 'AC1015':outline_doc.dxfversion = 'AC1024'
            outline_doc.units = 4
            outline_doc.header['$MEASUREMENT'] = 1
            outline_doc.saveas(inputs/name)
        files = {
            'copper': f'inputs/{board.stem}-B_Cu.gbr',
            'outline': 'inputs/outline.dxf',
            'outline_gerber': f'inputs/{board.stem}-Edge_Cuts.gbr',
            'drills': [f'inputs/{p.name}' for p in sorted(inputs.glob('*.drl'))],
        }
        required = [files['copper'], files['outline'], files['outline_gerber'], *files['drills']]
        if separation_layers:
            files['separation']='inputs/separation.dxf';required.append(files['separation'])
        if not files['drills'] or any(not (job/p).is_file() for p in required):
            raise ValueError('KiCad did not produce the expected copper, outline and drill outputs.')
        manifest = {'schema': 'pcb-isolator-export', 'version': 1, 'created_utc': stamp,
                    'board_name': board.stem, 'source_original': str(board),
                    'source_snapshot': f'source/{board.name}', 'kicad_version': version,
                    'units': 'mm', 'origin': 'absolute', 'mirrored': False,
                    'files': files,
                    'sha256': {p: sha256((job/p).read_bytes()).hexdigest() for p in required},
                    'source_sha256': sha256(snapshot.read_bytes()).hexdigest()}
        (job/'manufacturing-job.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        (job/'outputs').mkdir()
    finally:
        (job/'export-log.json').write_text(json.dumps(logs, indent=2), encoding='utf-8')
    return job


def resolve_job_folder(folder):
    folder = Path(folder).resolve()
    if (folder/'manufacturing-job.json').is_file():
        return folder
    if not folder.is_dir():
        raise ValueError('Drop a manufacturing job folder or its board parent folder.')
    candidates = []
    for manifest_path in folder.glob('*/manufacturing-job.json'):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('schema') == 'pcb-isolator-export':
            candidates.append((manifest.get('created_utc', ''), manifest_path.parent.name, manifest_path.parent))
    if not candidates:
        raise ValueError(f'No manufacturing export found in {folder} or its immediate subfolders.')
    return max(candidates, key=lambda entry: entry[:2])[2]


def load_job(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder/'manufacturing-job.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 'pcb-isolator-export' or manifest.get('version') != 1:
        raise ValueError('Unsupported manufacturing job format.')
    if manifest.get('units') != 'mm' or manifest.get('origin') != 'absolute' or manifest.get('mirrored') is not False:
        raise ValueError('Unexpected job coordinate settings.')
    def checked(relative):
        path = (folder/relative).resolve()
        if not path.is_relative_to(folder/'inputs'):
            raise ValueError('Job input paths must remain inside the inputs folder.')
        expected = manifest['sha256'].get(relative)
        if expected is None or sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Job input has changed since export: {relative}')
        return path
    files = manifest['files']
    if files.get('separation'):checked(files['separation'])
    return checked(files['copper']), [checked(p) for p in files['drills']], checked(files['outline'])


def separation_input(folder):
    folder=Path(folder).resolve();load_job(folder)
    files=json.loads((folder/'manufacturing-job.json').read_text(encoding='utf-8'))['files']
    return folder/files['separation'] if files.get('separation') else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('--output-root', type=Path, default=Path('jobs'))
    parser.add_argument('--cli', type=Path)
    args = parser.parse_args()
    try:
        folder = export_board(args.board, args.output_root, args.cli)
    except Exception as error:
        parser.exit(1, f'Export failed: {error}\n')
    print(f'Manufacturing job exported:\n{folder}')
    print('Save and refill zones in KiCad before each export. Only saved board contents are used.')


if __name__ == '__main__':
    main()
