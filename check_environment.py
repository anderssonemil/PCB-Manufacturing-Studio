"""Verify imports, geometry operations and native DXF curve round trips."""
from importlib.metadata import version
from io import StringIO

import ezdxf
from shapely.geometry import Point
from pygerber.gerber.api import GerberFile
from pygerber.vm.shapely import ShapelyVirtualMachine


def main():
    for package in ("pygerber", "shapely", "ezdxf", "pytest"):
        print(f"{package}: {version(package)}")
    assert Point(0, 0).buffer(1).buffer(0.1).area > 3.14
    doc = ezdxf.new("R2010")
    doc.units = 4  # millimeters
    model = doc.modelspace()
    model.add_line((0, 0), (10, 0))
    model.add_arc((10, 5), 5, 270, 90)
    model.add_circle((20, 5), 2)
    stream = StringIO()
    doc.write(stream)
    stream.seek(0)
    restored = ezdxf.read(stream)
    assert restored.units == 4
    assert [entity.dxftype() for entity in restored.modelspace()] == [
        "LINE", "ARC", "CIRCLE"
    ]
    print("PASS: Gerber backend imports, geometry offsets, and DXF LINE/ARC/CIRCLE round trip")


if __name__ == "__main__":
    main()
