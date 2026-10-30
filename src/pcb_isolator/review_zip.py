"""Share the existing self-contained router review without machine programs."""
from pathlib import Path
import os,uuid,zipfile


def save_router_review_zip(review,destination):
    review=Path(review).resolve();destination=Path(destination)
    if not review.is_file():raise ValueError('Generate a router review before saving its ZIP.')
    if destination.suffix.lower()!='.zip':destination=destination.with_name(destination.name+'.zip')
    temporary=destination.with_name('.'+destination.name+'.'+uuid.uuid4().hex+'.tmp')
    instructions=('Extract this ZIP, then open Router Review.html in a modern web browser.\n'
        'Animation and the paper-print function are embedded when included in that generated review.\n'
        'This archive contains a visual review only; no CNC machine programs are included.\n'
        'The original review status and settings are unchanged. It shows the last generated job, not unsaved app edits.\n')
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('Router Review.html',review.read_bytes())
            archive.writestr('READ ME.txt',instructions)
        os.replace(temporary,destination)
    finally:
        if temporary.exists():temporary.unlink()
    return destination.resolve()
