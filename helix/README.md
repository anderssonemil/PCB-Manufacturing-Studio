# Offline Helix encoder

`src/PCBHelixJob.java` is the app's small MIT-licensed bridge. It consumes already
quantized integer paths and saves a printer job. It never opens a laser connection.
The Python app owns the separately confirmed queue transfer.

`LibLaserCut-source/` is unmodified upstream source pinned by `provenance.json`.
Its own LGPL license, copyright headers and authorship notices remain in place.
Do not treat the repository's MIT license as relicensing this directory.

Run `./helix/setup.ps1` from the project root, or provide `-JdkHome <JDK folder>`.
Without an installed JDK, setup downloads the pinned, checksum-verified Temurin
Windows archive into ignored `.tools/`, compiles the required dependency closure,
and creates a small private Java runtime with jlink. No global Java install is made.
`build/` and `java/` are generated, ignored by Git, and included in portable builds.
The upstream source and bridge source are included with the portable license bundle.
