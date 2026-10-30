# Roadmap after the single-sided milestone

Implemented at this milestone: direct Helix preparation/queue submission; laser order
optimization and animation; router programs/animation; fragment decisions; independent
reviews; drill grouping; temporary registration pins; circular outline pin selection;
thermal-corner correction; 1:1 paper checks; main-view reference layers; router ZIPs.

## Next larger experiments

- Double-sided copper selection, flipping/mirroring and project-specific registration
  jigs. Target repeatability must be demonstrated physically, not assumed.
- Via-rivet geometry, drill/pad rules and solder-access guidance.
- Direct app-to-ESP air/exhaust prototype at a fixed IP, after verifying electrical
  characteristics and a real activity signal. Node-RED/MQTT is not the initial plan.

## Compatibility and usability

- Layer-to-manufacturing role mapping (view-only layer visibility already exists).
- Legacy/custom copper naming, empty-copper/router-only imports, outline numerical
  tolerance and descriptive zero-diameter drill diagnostics.
- Slot machining strategies and cutter fit; repeat legacy-board tests after changes.
- Standalone review regeneration for relocated app-run folders; normal GUI generation
  and sharing of its existing review already work.
- Generation phase progress, timing and cancellation; continued performance profiling.
- Optional desktop SVG/DXF delivery controls for CAD editing and paper workflows.
- Phone/tablet portability and fully portable linked diagnostic-detail pages.

## Manufacturing features

- Separate drill/router tool libraries and compatible-tool suggestions.
- V-bit chamfering and panel break-off scoring.
- Panelization, holding bridges/tabs, serial increments and copper text.
- Raster logos/images and faint alignment marks with distinct process calibration.
- Optional STEP/mechanical export.

## Process evidence

- Named process presets; actual runtime entry and timing history.
- In-app calibration coupons, controlled 600/1200 DPI comparisons and measured
  post-cleaning/post-etch dimensional changes.
- Better retained-copper/coverage/trace/spoke diagnostics, with net-data limitations.
- Camera/activity monitoring and accessory fault behavior after the basic prototype.

Private historical notes preserve additional details and superseded assumptions.
This roadmap records ideas, not a promise or authorization to implement every item.
