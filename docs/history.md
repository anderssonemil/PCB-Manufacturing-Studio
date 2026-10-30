# Project history

This is a curated development history, not reconstructed Git commit history.
The first repository commit is a preserved milestone of the working application.

| Period, 2026 | Milestone |
|---|---|
| October 18–19 | Gerber copper import, isolation preview, DXF inspection and aligned drill/profile planning |
| October 19–22 | Router programs tested physically by the owner; pecks, rapid approach, registration and tool-per-program workflow refined |
| October 22–24 | Legacy-board tests, joined curves, flat SVG, drill grouping and portable packaging experiments |
| October 24–26 | Burn-width photos/coupons, trial directional compensation, adaptive lanes and narrow-gap handling |
| October 26–27 | Direct Helix encoding/queue tests, exact-grid reviews, fragment decisions and optimized path ordering |
| October 27–29 | Laser animation, temporary-pin workflow, circular outline registration, tapered-corner fix, paper checks, reference-layer viewing and review ZIPs |
| October 29 | Owner reported the real single-sided board complete; private source/portable milestone prepared before double-sided and accessory experiments |

The owner performed the physical burning, cleaning, etching, alignment, drilling and
routing. Automated tests verify software behavior and geometry assumptions; they do
not replace those physical observations. An owner-reported successful board is not
a guarantee for other lasers, controllers, coatings or materials.

## Where ideas and code came from

The owner's earlier workflow used KiCad, FlatCAM, Inkscape/CAD and Vectric Aspire.
The application was built independently rather than by simplifying or copying FlatCAM.
A user-provided [workflow video](https://youtu.be/zn12kizaSsg) was an inspiration and
research reference; it is not the source of this application's code.

The principal imported source is the pinned, unmodified
[LibLaserCut](https://github.com/t-oster/LibLaserCut) encoder. Python geometry,
Gerber/DXF import and Qt UI rely on the projects listed in
[third-party notices](../THIRD-PARTY-NOTICES.md). A separately downloaded Arduino Micro
board from [sabogalc/KiCad-Arduino-Boards](https://github.com/sabogalc/KiCad-Arduino-Boards)
was used as a local stress-test sandbox; that board and the owner's PCB designs are
not distributed in this repository. Synthetic examples are provided instead.

Original photos, full handoff notes, laboratory results, old files and private design
samples remain in the owner's preservation archive/workspace. This public-facing
history summarizes evidence without publishing those originals or the chat transcript.
