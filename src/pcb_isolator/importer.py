"""Gerber copper import. All returned coordinates are millimeters."""
from dataclasses import dataclass
from pathlib import Path
import re

from pygerber.gerber.ast import get_final_state
from pygerber.gerber.ast.nodes.enums import UnitMode
from pygerber.gerber.compiler import compile as compile_gerber
from pygerber.gerber.parser import parse
from pygerber.vm.shapely import ShapelyVirtualMachine
from shapely.affinity import scale
from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class CopperLayer:
    source: Path
    geometry: BaseGeometry
    source_units: str
    file_function: str


def load_copper(path: Path) -> CopperLayer:
    path = Path(path)
    source = path.read_text(encoding="utf-8-sig")
    match = re.search(r"%TF\.FileFunction,([^*]+)\*%", source)
    function = match.group(1) if match else "Unspecified copper layer"
    if match and function.split(",")[0] != "Copper":
        raise ValueError(f"Expected copper Gerber; file declares {function}.")
    if re.search(r"%TF\.FilePolarity,Negative\*%", source):
        raise ValueError("Negative file polarity requires a board boundary; not supported yet.")
    ast = parse(source)
    state = get_final_state(ast)
    # The library default is too coarse for small pads. Use a dense preview
    # tessellation; production isolation will need a radius-aware tolerance.
    result = ShapelyVirtualMachine(
        angle_length_to_segment_count=lambda length: 512
    ).run(compile_gerber(ast))
    geometry = result.shape
    imperial = state.unit_mode == UnitMode.IMPERIAL
    if imperial:
        geometry = scale(geometry, xfact=25.4, yfact=25.4, origin=(0, 0))
    if geometry.is_empty:
        raise ValueError("Gerber contains no visible copper geometry.")
    if not geometry.is_valid:
        raise ValueError("Imported geometry is invalid; refusing to silently repair it.")
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"Expected copper areas; received {geometry.geom_type}.")
    return CopperLayer(path, geometry, "in" if imperial else "mm", function)
