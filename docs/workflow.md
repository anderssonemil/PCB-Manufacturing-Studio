# Manufacturing workflow

## Saved input and output

The app uses a saved KiCad board snapshot. Refill zones and save before exporting;
unsaved editor changes are not included. Inputs share one revision and coordinate
system. Internal snapshots live in `.pcb-isolator/jobs` beside the board.
Final files normally live in the shallow `Manufacturing Output` folder beside it.
Old outputs are archived internally rather than silently destroyed.

## Laser

Choose real process settings, generate the preview, and inspect the quantized paths
and predicted footprint. Tiny fragments have visible omission decisions; a filter
is not proof that every omitted detail is electrically harmless. Direct submission
requires explicit confirmation, reports progress and waits for acknowledgement.
Run the selected job at the laser panel. Focus, air and exhaust remain manual.
Then clean/etch using the validated physical process for the particular coating.

The directional X/Y burn envelope is a process model. Higher DPI gives a finer
coordinate grid, not a guarantee of smaller burns or better mechanical accuracy.
The laser's artwork top-left is separate from the selected router registration datum.

## Registration and CNC

Select at least two registration locations. Undersized source holes require manual
preparation; source KiCad geometry is not silently resized. Circular internal
Edge.Cuts can also be selected, and their profile cutting is then excluded.
Check warnings for a pin hole that would break out of the board edge.

Drill the spoilboard registration holes. Prepare the PCB holes at the laser marks,
register on pins, press double-sided tape firmly, and **remove all pins**.
Set XY zero at the selected reference hole. Reset Z on the correct surface for each
tool: spoilboard top for pin-hole drilling; PCB top for PCB drilling/profiling.
The tested tool-setting routine leaves Z at machine maximum. Programs first move XY
to the first actual feature and lower there. This assumption must match the controller.

Set spindle speed manually; M03/M05 start/stop it automatically. Use the configured
actual tool diameters. Drilling, separation and profile programs are individual files;
separation cuts precede the outside profile. Current profiles have no holding tabs.

## Review and paper check

Laser and router HTML reviews are independent and embed their drawings/animation.
Router review ZIPs contain the existing HTML and opening instructions, not machine
programs. Extract before opening on another device. Reference layers are shown only
on the main app view and never change reviews or manufacturing.

Print 1:1 opens a separate paper view, independent of screen zoom/playback. Use
Actual size / 100% in the printer dialog, with no Fit to page, and measure both the
50 mm horizontal and 20 mm vertical bars before comparing components. Mirroring is
optional and visibly labelled. The printable artwork is not automatically tiled.
