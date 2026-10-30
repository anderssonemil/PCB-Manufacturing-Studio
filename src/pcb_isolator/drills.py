"""Strict import of decimal-coordinate Excellon drills and straight slots."""
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class DrillFeature:
    id: str
    diameter_mm: float
    x: float
    y: float
    end: tuple | None = None


def load_drills(path: Path):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    factor = None
    tools = {}
    tool = None
    x = y = None
    routing = False
    route_positioning = False
    features = []
    terminated = False
    header = True

    def coordinate(part):
        nonlocal x, y
        for axis, value in re.findall(r"([XY])([+-]?\d*\.?\d+)", part):
            if "." not in value:
                raise ValueError("Use decimal-coordinate Excellon export; suppressed-zero coordinates are not supported yet.")
            number = float(value)*factor
            if axis == "X":
                x = number
            else:
                y = number
        if x is None or y is None:
            raise ValueError("Drill position is missing X or Y.")
        return (x, y)

    def add(start, end=None):
        if tool not in tools:
            raise ValueError("Drill coordinates reference an undefined tool.")
        features.append(DrillFeature(f"{path.name}:T{tool}:{len(features)+1}", tools[tool], *start, end))

    for line_number, original in enumerate(text.splitlines(), 1):
        line = original.split(";", 1)[0].strip().upper()
        if not line:
            continue
        try:
            if line == "M48":
                continue
            if line in {"%", "M95"}:
                header = False
                continue
            if line.startswith(("METRIC", "INCH")):
                new_factor = 1.0 if line.startswith("METRIC") else 25.4
                if factor is not None and factor != new_factor:
                    raise ValueError("Mixed unit declarations are not supported.")
                factor = new_factor
                continue
            if line == "FMAT,2":
                continue
            if line.startswith("T"):
                definition = re.fullmatch(r"T(\d+)C(\d*\.?\d+)(?:F[\d.]+)?(?:S[\d.]+)?", line)
                if definition:
                    if factor is None:
                        raise ValueError("Tool diameter appears before units.")
                    diameter = float(definition[2])*factor
                    if diameter <= 0:
                        raise ValueError("Tool diameter must be positive.")
                    tools[int(definition[1])] = diameter
                    continue
                selection = re.fullmatch(r"T(\d+)", line)
                if not selection:
                    raise ValueError("Unsupported tool declaration.")
                tool = int(selection[1])
                continue
            if line == "M30":
                terminated = True
                break
            if line == "G90":
                continue
            if line in {"M15", "M16", "M17"}:
                routing = line == "M15"
                continue
            if line in {"G05", "G5"}:
                routing = False
                route_positioning = False
                continue
            if factor is None:
                raise ValueError("Excellon units must be declared.")
            if header:
                raise ValueError("Unsupported Excellon header entry.")
            if "G85" in line:
                first, last = line.split("G85")
                if not re.fullmatch(r"(?:[XY][+-]?\d*\.?\d+)*", first) or not re.fullmatch(r"(?:[XY][+-]?\d*\.?\d+)+", last):
                    raise ValueError("Unsupported slot syntax.")
                start = coordinate(first)
                add(start, coordinate(last))
                continue
            command = re.match(r"G(\d+)", line)
            if command:
                mode = int(command[1])
                if mode not in {0, 1}:
                    raise ValueError(f"Unsupported Excellon command G{mode}.")
                if mode == 1 and not routing:
                    raise ValueError("Route move requires an M15 routing start.")
                route_positioning = mode == 0
                line = line[command.end():]
            if not re.fullmatch(r"(?:[XY][+-]?\d*\.?\d+)+", line):
                raise ValueError(f"Unsupported Excellon entry: {line}")
            previous = (x, y)
            point = coordinate(line)
            if routing:
                if None in previous:
                    raise ValueError("Routed slot lacks a start position.")
                add(previous, point)
            elif not route_positioning:
                add(point)
        except ValueError as error:
            raise ValueError(f"{path.name}:{line_number}: {error}") from error
    if not terminated:
        raise ValueError(f"{path.name}: missing M30 end marker.")
    if factor is None or header:
        raise ValueError(f"{path.name}: missing units or end-of-header marker.")
    # KiCad exports an empty PTH or NPTH file when that category has no holes.
    # A complete, unit-declared empty file is valid input.
    return features
