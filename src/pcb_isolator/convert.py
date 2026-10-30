"""Convert a copper Gerber to native LINE/ARC/CIRCLE isolation DXF."""
import argparse
import json
from pathlib import Path
import tomllib

from .dxf_export import export_dxf
from .importer import load_copper
from .isolation import generate_isolation, load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gerber", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--output", type=Path, default=Path("generated/isolation.dxf"))
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
        with args.config.open("rb") as stream:
            config = tomllib.load(stream)
        copper = load_copper(args.gerber).geometry
        contours = generate_isolation(copper, settings)
        report = export_dxf(copper, contours, settings, args.output,
                            config.get("geometry", {}).get("curve_tolerance_mm", 0.001))
        report.update(source=str(args.gerber), lines=settings.lines,
                      laser_width_mm=settings.width_mm, overlap_percent=settings.overlap_percent)
        args.output.with_suffix(".report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception as error:
        parser.exit(1, f"Could not export DXF: {error}\n")
    print(f"Saved: {args.output.resolve()}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
