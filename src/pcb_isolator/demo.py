"""Create a synthetic offline demonstration job, never a production PCB."""
from pathlib import Path
from hashlib import sha256
import json
import ezdxf


def create_demo_job(destination):
    root=Path(destination).resolve()
    if root.exists() and any(root.iterdir()):raise ValueError('Demo destination must be new or empty.')
    inputs=root/'inputs';inputs.mkdir(parents=True);(root/'outputs').mkdir()
    copper=inputs/'demo-B_Cu.gbr'
    copper.write_text('%FSLAX46Y46*%\n%MOMM*%\n%TF.FileFunction,Copper,L2,Bot*%\n%ADD10C,4*%\n%LPD*%\nD10*\nX10000000Y5000000D03*\nM02*\n',encoding='ascii')
    drills=inputs/'demo.drl';drills.write_text('M48\nMETRIC\nT1C3.2\nT2C0.5\nT3C1.0\n%\nG90\nG05\nT1\nX3.0Y3.0\nX17.0Y3.0\nT2\nX5.0Y5.0\nT3\nX7.0Y5.0\nM30\n',encoding='ascii')
    outline=inputs/'outline.dxf';doc=ezdxf.new('R2010');doc.units=4;doc.modelspace().add_lwpolyline([(0,0),(20,0),(20,10),(0,10)],close=True);doc.saveas(outline)
    files=dict(copper='inputs/'+copper.name,outline='inputs/'+outline.name,drills=['inputs/'+drills.name])
    hashes={'inputs/'+p.name:sha256(p.read_bytes()).hexdigest() for p in [copper,drills,outline]}
    manifest=dict(schema='pcb-isolator-export',version=1,board_name='Synthetic offline demo',units='mm',origin='absolute',mirrored=False,files=files,sha256=hashes)
    (root/'manufacturing-job.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return root
