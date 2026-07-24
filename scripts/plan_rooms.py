"""Room normalization and wall derivation helpers."""
from __future__ import annotations
import copy
import math
from typing import Any
from common import bbox, floor_bounds, polygon_points, room_area, rooms_by_floor, stable_id

HABITABLE = {"bedroom", "living", "majlis", "dining", "office", "family-lounge"}
WET_TYPES = {"bathroom", "kitchen", "laundry", "wc"}
EXTERIOR_TYPES = {"terrace", "balcony", "courtyard", "garden"}

def auto_layout_floor(floor: dict[str, Any]) -> None:
    """Deterministic shelf packer for rooms lacking coordinates."""
    fp = floor["footprint"]
    width = float(fp["width_m"])
    x0 = float(fp.get("x_m", 0.0))
    y0 = float(fp.get("y_m", 0.0))
    x, y, row_h = x0, y0, 0.0
    zone_order = {"guest": 0, "family": 1, "shared": 2, "service": 3}
    rooms = sorted(floor["rooms"], key=lambda r: (zone_order.get(r.get("zone", "shared"), 9), r.get("id", "")))
    for room in rooms:
        if all(k in room for k in ("x_m", "y_m", "width_m", "depth_m")):
            continue
        area = float(room.get("target_area_m2", 12.0))
        ratio = max(0.5, min(2.0, float(room.get("aspect_ratio", 1.25))))
        w = round(math.sqrt(area * ratio), 2)
        d = round(area / w, 2)
        if x + w > x0 + width + 1e-6:
            x = x0
            y += row_h
            row_h = 0.0
        room.update({"x_m": round(x, 2), "y_m": round(y, 2), "width_m": w, "depth_m": d})
        x += w
        row_h = max(row_h, d)


def normalize_rooms(program: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for floor in program["floors"]:
        auto_layout_floor(floor)
        for raw in floor["rooms"]:
            room = copy.deepcopy(raw)
            room["floor_id"] = floor["id"]
            room["id"] = str(room.get("id") or stable_id("room", floor["id"], room["name"]))
            room["type"] = room.get("type", "room")
            room["zone"] = room.get("zone", "shared")
            room["geometry"] = {
                "x_m": float(room.pop("x_m")),
                "y_m": float(room.pop("y_m")),
                "width_m": float(room.pop("width_m")),
                "depth_m": float(room.pop("depth_m")),
            }
            room["polygon_m"] = [[x, y] for x, y in polygon_points(room)]
            room["area_m2"] = room_area(room)
            room["target_area_m2"] = float(room.get("target_area_m2", room["area_m2"]))
            room["clear_dimensions_m"] = {
                "width": room["geometry"]["width_m"],
                "depth": room["geometry"]["depth_m"],
            }
            room["requires_natural_light"] = bool(room.get("natural_light", room["type"] in HABITABLE))
            room["requires_ventilation"] = bool(room["type"] in WET_TYPES)
            room["is_exterior"] = bool(room.get("is_exterior", room["type"] in EXTERIOR_TYPES))
            result.append(room)
    return result


def room_at_side(rooms: list[dict[str, Any]], orientation: str, coordinate: float, midpoint: float, side: str) -> list[dict[str, Any]]:
    found = []
    for room in rooms:
        x, y, w, d = bbox(room)
        if orientation == "vertical":
            boundary = x + w if side == "left" else x
            if abs(boundary - coordinate) < 1e-6 and y - 1e-6 <= midpoint <= y + d + 1e-6:
                found.append(room)
        else:
            boundary = y + d if side == "below" else y
            if abs(boundary - coordinate) < 1e-6 and x - 1e-6 <= midpoint <= x + w + 1e-6:
                found.append(room)
    return found


def derive_walls(plan: dict[str, Any], standards: dict[str, Any]) -> list[dict[str, Any]]:
    walls: list[dict[str, Any]] = []
    ext_t = float(standards["external_wall_thickness_m"])
    int_t = float(standards["internal_wall_thickness_m"])
    for floor in plan["floors"]:
        rooms = rooms_by_floor(plan, floor["id"])
        fx, fy, fw, fd = floor_bounds(plan, floor["id"])
        xs = sorted({fx, fx + fw, *[v for r in rooms for v in (bbox(r)[0], bbox(r)[0] + bbox(r)[2])]})
        ys = sorted({fy, fy + fd, *[v for r in rooms for v in (bbox(r)[1], bbox(r)[1] + bbox(r)[3])]})
        for x in xs:
            for a, b in zip(ys, ys[1:]):
                if b - a < 1e-6:
                    continue
                mid = (a + b) / 2
                left = room_at_side(rooms, "vertical", x, mid, "left")
                right = room_at_side(rooms, "vertical", x, mid, "right")
                if not left and not right:
                    continue
                interior_sides = [r for r in left + right if not r["is_exterior"]]
                if not interior_sides:
                    continue
                external = abs(x - fx) < 1e-6 or abs(x - (fx + fw)) < 1e-6 or not left or not right or any(r["is_exterior"] for r in left + right)
                walls.append({
                    "id": stable_id("wall", floor["id"], "v", x, a, b),
                    "floor_id": floor["id"],
                    "start_m": [x, a], "end_m": [x, b],
                    "orientation": "vertical", "type": "external" if external else "internal",
                    "thickness_m": ext_t if external else int_t,
                    "height_m": float(floor["clear_height_m"]),
                    "adjacent_room_ids": sorted({r["id"] for r in left + right}),
                })
        for y in ys:
            for a, b in zip(xs, xs[1:]):
                if b - a < 1e-6:
                    continue
                mid = (a + b) / 2
                below = room_at_side(rooms, "horizontal", y, mid, "below")
                above = room_at_side(rooms, "horizontal", y, mid, "above")
                if not below and not above:
                    continue
                interior_sides = [r for r in below + above if not r["is_exterior"]]
                if not interior_sides:
                    continue
                external = abs(y - fy) < 1e-6 or abs(y - (fy + fd)) < 1e-6 or not below or not above or any(r["is_exterior"] for r in below + above)
                walls.append({
                    "id": stable_id("wall", floor["id"], "h", y, a, b),
                    "floor_id": floor["id"],
                    "start_m": [a, y], "end_m": [b, y],
                    "orientation": "horizontal", "type": "external" if external else "internal",
                    "thickness_m": ext_t if external else int_t,
                    "height_m": float(floor["clear_height_m"]),
                    "adjacent_room_ids": sorted({r["id"] for r in below + above}),
                })
    return sorted(walls, key=lambda w: w["id"])
