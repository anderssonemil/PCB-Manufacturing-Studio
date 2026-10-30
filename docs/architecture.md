# Architecture

The desktop in `desktop.py` orchestrates independently testable Python engines through
`app_backend.py`. Saved KiCad exports are verified by hashes. Imported retained copper
is polygon geometry; manufacturing planning and review rendering remain separate.

- Import: `kicad_export.py`, `importer.py`, `drills.py`, `outline.py`, `separation.py`.
- Laser geometry: `isolation.py`, `adaptive_isolation.py`, `narrow_isolation.py`.
- Direct laser: `helix.py` quantizes/validates, `laser_order.py` orders exact paths,
  the separate Java bridge saves PRN via LibLaserCut, Python handles confirmed transfer.
- CNC: `router.py`, `drill_grouping.py`, `route_order.py` and related validators.
- Reviews: router/laser Python + embedded JS, `paper_print.py/js`, `job_guide.py`.
- Display-only layers: `reference_layers.py`; cached SVG never enters manufacturing.
- Sharing: `review_zip.py` preserves the existing standalone review bytes.

Expensive isolation plans are cached by board/geometry identity. Filter-only refresh
can reuse the plan and retain router bytes. Preview identity/hash checks prevent final
output silently differing from the reviewed file set. Laser/router failures can leave
independent diagnostic pages and a valid preview of the other module.

No machine is contacted by generating a preview. Connectivity checks and queue sending
are separate explicit actions. The app does not detect laser execution state or control
accessories, and router output is transferred to the CNC separately.
