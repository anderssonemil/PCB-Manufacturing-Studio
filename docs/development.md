# Development and portable builds

## Windows source checkout

Python 3.12 is the tested interpreter. Run `tools/bootstrap.ps1`; optional parameters
`-Python <python.exe>` and `-JdkHome <JDK folder>` avoid guessing local installations.
The script creates `.venv`, installs `packaging/build-requirements.lock.txt`, installs
the project, initializes `config.toml` from its example only if absent, and builds the
Helix helper. JDK download is pinned and checked against `helix/provenance.json`.
The generated Java runtime is private to the project; it is not a global install.

`start-app.cmd` launches development without reinstalling the app. No board source is
changed by import. Personal settings, jobs, photos and archives are ignored by Git.
The working repository can therefore retain local development evidence without
shipping it to a remote repository.

## Checks

```powershell
./.venv/Scripts/python.exe -m pytest -q
```

Most checks use synthetic data. Personal reference tests skip when their ignored
sample files are absent. Laser transport tests use loopback mock servers; they do
not contact a real laser. Prepare the Java helper before tests that save PRN jobs.
The optional example job contains generated Gerber/Excellon/DXF inputs for offline use.

## Portable app

```powershell
./packaging/build-portable.ps1
```

Output defaults to ignored `dist/`. The bundle includes Python, Qt including SVG,
geometry libraries, all embedded review JS, the Java bridge and private Java runtime.
The final packaging step includes third-party notices, LibLaserCut/bridge source,
release metadata, archive checksum and the full portable ZIP.

The frozen executable supports `--self-test <new-directory>` for an offline synthetic
import, direct encoder, router, HTML/paper/ZIP and Qt SVG smoke check. It sends nothing.
Keep a result outside the app folder so the source-independent relocation test is real.

Packaged settings live under `%LOCALAPPDATA%/PCB Isolator`; updating the app folder
preserves them. `PCB_ISOLATOR_HOME` can redirect settings for a smoke test. KiCad is a
separate installation; the app discovers KiCad 8/9's CLI when exporting a saved board.

## GitHub preparation

The repository begins with a single honest milestone commit. History is documented
in `docs/history.md`, not fabricated as dated commits. The private upload helper
`tools/publish_private.py` requires authenticated GitHub CLI, refuses a public remote,
never force-pushes, and does not change visibility. The account is obtained from the
CLI login; no account password/token belongs in source or chat.
