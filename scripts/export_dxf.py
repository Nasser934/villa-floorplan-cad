#!/usr/bin/env python3
"""Export one editable, deterministic, metric DXF per floor using ezdxf."""
from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

from common import bbox, load_json, require_dependency, rooms_by_floor


def ensure_layer(doc, name: str, color: int, linetype: str = "CONTINUOUS") -> None:
    if name not in doc.layers:
        doc.layers.add(name=name, color=color, linetype=linetype)


def _fixed_guid(*parts: object) -> str:
    value = hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:32]
    return "{" + f"{value[:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:]}".upper() + "}"


def _minor_arc_angles(hinge: list[float], closed: list[float], opened: list[float]) -> tuple[float, float]:
    """Return start/end angles for the minor CCW DXF arc between two leaves."""
    cx, cy = hinge
    closed_angle = math.degrees(math.atan2(closed[1] - cy, closed[0] - cx)) % 360
    open_angle = math.degrees(math.atan2(opened[1] - cy, opened[0] - cx)) % 360
    if (open_angle - closed_angle) % 360 <= 180:
        return closed_angle, open_angle
    return open_angle, closed_angle


def export_floor(plan: dict, floor: dict, output: Path) -> Path:
    ezdxf = require_dependency("ezdxf")
    from ezdxf import units
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2018", setup=True)
    doc.units = units.M
    doc.header["$INSUNITS"] = units.M
    doc.header["$MEASUREMENT"] = 1
    for variable, value in (
        ("$TDCREATE", 2451544.5),
        ("$TDUPDATE", 2451544.5),
        ("$FINGERPRINTGUID", _fixed_guid(plan.get("schema_version"), floor["id"], "fingerprint")),
        ("$VERSIONGUID", _fixed_guid(plan.get("schema_version"), floor["id"], "version")),
    ):
        try:
            doc.header[variable] = value
        except (KeyError, TypeError, ValueError):
            pass

    for name, color, linetype in (
        ("A-WALL-EXT", 7, "CONTINUOUS"),
        ("A-WALL-INT", 8, "CONTINUOUS"),
        ("A-DOOR", 30, "CONTINUOUS"),
        ("A-DOOR-SWING", 30, "DASHED"),
        ("A-WIND", 4, "CONTINUOUS"),
        ("A-FURN", 9, "CONTINUOUS"),
        ("A-FIXT", 3, "CONTINUOUS"),
        ("A-ROOM", 2, "CONTINUOUS"),
        ("A-DIMS", 6, "CONTINUOUS"),
        ("A-TEXT", 7, "CONTINUOUS"),
    ):
        ensure_layer(doc, name, color, linetype)

    msp = doc.modelspace()
    for wall in plan["walls"]:
        if wall["floor_id"] != floor["id"]:
            continue
        layer = "A-WALL-EXT" if wall["type"] == "external" else "A-WALL-INT"
        msp.add_line(tuple(wall["start_m"]), tuple(wall["end_m"]), dxfattribs={"layer": layer, "lineweight": 70 if wall["type"] == "external" else 40})

    for window in plan["windows"]:
        if window["floor_id"] != floor["id"]:
            continue
        coordinate = window["wall"]["coordinate_m"]
        position = window["position_m"]
        half = window["width_m"] / 2
        start, end = (((coordinate, position - half), (coordinate, position + half)) if window["wall"]["orientation"] == "vertical" else ((position - half, coordinate), (position + half, coordinate)))
        msp.add_line(start, end, dxfattribs={"layer": "A-WIND", "lineweight": 50})

    for door in plan["doors"]:
        if door["floor_id"] != floor["id"]:
            continue
        hinge = list(door["hinge_m"])
        closed = list(door.get("closed_leaf_end_m", (hinge[0] + door["width_m"], hinge[1])))
        opened = list(door.get("open_leaf_end_m", closed))
        msp.add_line(tuple(hinge), tuple(closed), dxfattribs={"layer": "A-DOOR"})
        if door.get("type") == "single-leaf":
            msp.add_line(tuple(hinge), tuple(opened), dxfattribs={"layer": "A-DOOR-SWING"})
            start_angle, end_angle = _minor_arc_angles(hinge, closed, opened)
            msp.add_arc(tuple(hinge), float(door["width_m"]), start_angle=start_angle, end_angle=end_angle, dxfattribs={"layer": "A-DOOR-SWING"})

    for room in rooms_by_floor(plan, floor["id"]):
        x, y, width, depth = bbox(room)
        msp.add_lwpolyline([(x, y), (x + width, y), (x + width, y + depth), (x, y + depth)], close=True, dxfattribs={"layer": "A-ROOM"})
        text = msp.add_mtext(f"{room['name']}\\P{room['area_m2']:.2f} m2", dxfattribs={"layer": "A-TEXT", "char_height": 0.18})
        text.set_location((x + width / 2, y + depth / 2))

    fixture_ids = {item["id"] for item in plan.get("fixtures", [])}
    for item in [*plan.get("furniture", []), *plan.get("fixtures", [])]:
        if item["floor_id"] != floor["id"]:
            continue
        geometry = item["geometry"]
        layer = "A-FIXT" if item["id"] in fixture_ids else "A-FURN"
        x, y = geometry["x_m"], geometry["y_m"]
        width, depth = geometry["width_m"], geometry["depth_m"]
        msp.add_lwpolyline([(x, y), (x + width, y), (x + width, y + depth), (x, y + depth)], close=True, dxfattribs={"layer": layer})

    for dimension in plan["dimensions"]:
        if dimension["floor_id"] != floor["id"]:
            continue
        start, end = tuple(dimension["start_m"]), tuple(dimension["end_m"])
        msp.add_line(start, end, dxfattribs={"layer": "A-DIMS"})
        midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        msp.add_text(dimension["label"], height=0.16, dxfattribs={"layer": "A-DIMS"}).set_placement(midpoint, align=TextEntityAlignment.MIDDLE_CENTER)

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    path = Path(args.plan).expanduser().resolve()
    plan = load_json(path)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else path.parent
    for floor in plan["floors"]:
        print(export_floor(plan, floor, output_dir / f"{floor['id']}.dxf"))


if __name__ == "__main__":
    main()
