# Third-party sources and attribution

The root MIT license applies to original application code. It does not relicense
third-party source, shared libraries, runtimes or separately downloaded examples.
Portable archives carry a detailed `THIRD-PARTY-LICENSES` directory and component list.

| Component | Use | Source / license |
|---|---|---|
| LibLaserCut, Thomas Oster and contributors | Offline Epilog job encoding | [Upstream](https://github.com/t-oster/LibLaserCut), LGPL-3.0-or-later |
| Eclipse Temurin / OpenJDK | Private Java runtime | [Adoptium](https://adoptium.net/), runtime license files and Classpath Exception retained |
| PyGerber | Gerber interpretation | [Upstream](https://github.com/Argmaster/pygerber), MIT |
| Shapely / GEOS | Polygon and offset operations | [Shapely](https://github.com/shapely/shapely), BSD-3-Clause; GEOS LGPL notices retained |
| ezdxf | DXF import/export | [Upstream](https://github.com/mozman/ezdxf), MIT |
| PySide6 / Qt / shiboken6 | Desktop and SVG rendering | [Qt for Python](https://www.qt.io/qt-for-python), installed component LGPL/GPL notices retained |
| NumPy | Numerical geometry work | [Upstream](https://github.com/numpy/numpy), BSD-3-Clause |
| Python and other Python dependencies | Runtime and support | Installed distribution license/metadata files included in portable notices |
| PyInstaller | Portable bundling | [Upstream](https://github.com/pyinstaller/pyinstaller), GPL with bootloader distribution exception |
| KiCad | Saved-board CLI export | [KiCad](https://www.kicad.org/), separately installed; no KiCad binary bundled |

LibLaserCut source at commit `90ccd5f1d381a6dc1f3a67be686b99509ec0b6d4` is kept
unmodified in `helix/LibLaserCut-source/`, with its AUTHORS, headers and license files.
`helix/src/PCBHelixJob.java` is the separate original app bridge. Source, setup details
and pinned runtime provenance are supplied alongside the portable helper.

See [history](docs/history.md) for workflow inspirations and local test-board sources.
No FlatCAM/Vectric source or downloaded Arduino board design is incorporated into the
original app code or the synthetic example. This attribution inventory is not a claim
that every dependency shares one license; each component's own text remains authoritative.
