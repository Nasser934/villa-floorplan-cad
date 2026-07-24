"""Door and window derivation helpers."""
from __future__ import annotations
from typing import Any
from common import bbox, floor_bounds, rooms_by_floor, shared_boundary, stable_id

HABITABLE = {"bedroom", "living", "majlis", "dining", "office", "family-lounge"}

def place_door(a: dict[str, Any], b: dict[str, Any], standards: dict[str, Any]) -> dict[str, Any] | None:
    boundary = shared_boundary(a, b)
    if not boundary:
        return None
    span = boundary["end_m"] - boundary["start_m"]
    preferred = 1.0 if a["type"] in {"living", "majlis", "dining"} or b["type"] in {"living", "majlis", "dining"} else 0.9
    width = min(preferred, max(float(standards["minimum_door_width_m"]), span - 0.4))
    position = (boundary["start_m"] + boundary["end_m"]) / 2
    priority={
        "elevator":100,"bathroom":90,"wc":90,"dressing":85,"storage":82,"pantry":82,
        "bedroom":80,"maid-room":80,"majlis":76,"kitchen":72,"laundry":72,"dining":68,
        "living":65,"garage":60,"stair":40,"lobby":20,"corridor":10,"shaft":0,
    }
    open_room=max((a,b),key=lambda r:(priority.get(r["type"],50),r["id"]))
    ox, oy, ow, od = bbox(open_room)
    if boundary["orientation"] == "vertical":
        hinge = [boundary["coordinate_m"], position - width / 2]
        closed_end = [boundary["coordinate_m"], position + width / 2]
        opens_west = abs(ox + ow - boundary["coordinate_m"]) <= 0.01
        open_end = [boundary["coordinate_m"] - width if opens_west else boundary["coordinate_m"] + width, hinge[1]]
    else:
        hinge = [position - width / 2, boundary["coordinate_m"]]
        closed_end = [position + width / 2, boundary["coordinate_m"]]
        opens_south = abs(oy + od - boundary["coordinate_m"]) <= 0.01
        open_end = [hinge[0], boundary["coordinate_m"] - width if opens_south else boundary["coordinate_m"] + width]
    is_sliding = open_room["type"] == "elevator" or a["type"] == "elevator" or b["type"] == "elevator"
    cross=(closed_end[0]-hinge[0])*(open_end[1]-hinge[1])-(closed_end[1]-hinge[1])*(open_end[0]-hinge[0])
    record={
        "id": stable_id("door", a["floor_id"], *sorted([a["id"], b["id"]])),
        "floor_id": a["floor_id"], "from_room_id": a["id"], "to_room_id": b["id"],
        "width_m": round(width, 3), "height_m": float(standards.get("door_height_m", 2.2)),
        "wall": boundary, "position_m": round(position, 4), "hinge_m": hinge,
        "closed_leaf_end_m": closed_end,
        "swing": {"direction": "none" if is_sliding else ("counterclockwise" if cross > 0 else "clockwise"), "angle_deg": 0 if is_sliding else 90, "opens_into_room_id": open_room["id"]},
        "type": "sliding" if is_sliding else "single-leaf",
    }
    if not is_sliding: record["open_leaf_end_m"]=open_end
    return record


def place_external_door(room: dict[str, Any], floor: dict[str, Any], street_side: str, standards: dict[str, Any]) -> dict[str, Any] | None:
    x, y, w, d = bbox(room)
    fp = floor["footprint"]
    fx, fy, fw, fd = float(fp.get("x_m", 0)), float(fp.get("y_m", 0)), float(fp["width_m"]), float(fp["depth_m"])
    candidates = []
    if abs(y - fy) < 1e-6: candidates.append(("south", "horizontal", fy, x, x + w))
    if abs(y + d - (fy + fd)) < 1e-6: candidates.append(("north", "horizontal", fy + fd, x, x + w))
    if abs(x - fx) < 1e-6: candidates.append(("west", "vertical", fx, y, y + d))
    if abs(x + w - (fx + fw)) < 1e-6: candidates.append(("east", "vertical", fx + fw, y, y + d))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0] != street_side, c[0]))
    side, orientation, coordinate, start, end = candidates[0]
    width = 2.8 if room["type"] == "garage" else 1.2
    width = min(width, max(float(standards["minimum_door_width_m"]), end - start - 0.4))
    pos = (start + end) / 2
    hinge = [pos - width / 2, coordinate] if orientation == "horizontal" else [coordinate, pos - width / 2]
    closed_end = [pos + width / 2, coordinate] if orientation == "horizontal" else [coordinate, pos + width / 2]
    if side == "south": open_end=[hinge[0],coordinate+width]
    elif side == "north": open_end=[hinge[0],coordinate-width]
    elif side == "west": open_end=[coordinate+width,hinge[1]]
    else: open_end=[coordinate-width,hinge[1]]
    cross=(closed_end[0]-hinge[0])*(open_end[1]-hinge[1])-(closed_end[1]-hinge[1])*(open_end[0]-hinge[0])
    return {
        "id": stable_id("door", room["floor_id"], room["id"], "exterior"),
        "floor_id": room["floor_id"], "from_room_id": room["id"], "to_room_id": "EXTERIOR",
        "width_m": round(width, 3), "height_m": 2.4 if room["type"] == "garage" else float(standards.get("door_height_m", 2.2)),
        "wall": {"orientation": orientation, "coordinate_m": coordinate, "start_m": start, "end_m": end},
        "position_m": round(pos, 4), "hinge_m": hinge,
        "closed_leaf_end_m": closed_end, "open_leaf_end_m": open_end,
        "swing": {"direction": "counterclockwise" if cross > 0 else "clockwise", "angle_deg": 90, "opens_into_room_id": room["id"]},
        "type": "overhead" if room["type"] == "garage" else "single-leaf",
        "external_side": side,
    }


def derive_doors(plan: dict[str, Any], program: dict[str, Any], standards: dict[str, Any]) -> list[dict[str, Any]]:
    rmap = {r["id"]: r for r in plan["rooms"]}
    floors = {f["id"]: f for f in plan["floors"]}
    street_side = str(program.get("site", {}).get("street_side", "south"))
    doors: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for room in sorted(plan["rooms"], key=lambda r: r["id"]):
        for target_id in sorted(set(room.get("connect_to", []))):
            if target_id not in rmap or rmap[target_id]["floor_id"] != room["floor_id"]:
                continue
            pair = tuple(sorted((room["id"], target_id)))
            if pair in seen:
                continue
            seen.add(pair)
            door = place_door(room, rmap[target_id], standards)
            if door:
                doors.append(door)
        if room.get("external_entry"):
            door = place_external_door(room, floors[room["floor_id"]], street_side, standards)
            if door:
                doors.append(door)
    return sorted(doors, key=lambda d: d["id"])


def place_window(room: dict[str, Any], floor: dict[str, Any], all_rooms: list[dict[str, Any]]) -> dict[str, Any] | None:
    x, y, w, d = bbox(room)
    fp = floor["footprint"]
    fx, fy, fw, fd = float(fp.get("x_m", 0)), float(fp.get("y_m", 0)), float(fp["width_m"]), float(fp["depth_m"])
    candidates = []
    if abs(x - fx) < 1e-6: candidates.append(("vertical", fx, y, y + d, "west"))
    if abs(x + w - (fx + fw)) < 1e-6: candidates.append(("vertical", fx + fw, y, y + d, "east"))
    if abs(y - fy) < 1e-6: candidates.append(("horizontal", fy, x, x + w, "south"))
    if abs(y + d - (fy + fd)) < 1e-6: candidates.append(("horizontal", fy + fd, x, x + w, "north"))
    if not candidates:
        for other in all_rooms:
            if other["floor_id"] != room["floor_id"] or not other.get("is_exterior"):
                continue
            boundary = shared_boundary(room, other)
            if boundary:
                candidates.append((boundary["orientation"], boundary["coordinate_m"], boundary["start_m"], boundary["end_m"], "exterior-space"))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-(c[3] - c[2]), c[4]))
    orientation, coordinate, start, end, side = candidates[0]
    width = min(2.4, max(1.0, (end - start) * 0.45))
    pos = (start + end) / 2
    return {
        "id": stable_id("window", room["floor_id"], room["id"], side),
        "floor_id": room["floor_id"], "room_id": room["id"],
        "width_m": round(width, 3), "height_m": 1.5, "sill_height_m": 0.9,
        "wall": {"orientation": orientation, "coordinate_m": coordinate, "start_m": start, "end_m": end},
        "position_m": round(pos, 4), "external_side": side, "type": "sliding",
    }


def derive_windows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    floors = {f["id"]: f for f in plan["floors"]}
    windows = []
    for room in sorted(plan["rooms"], key=lambda r: r["id"]):
        if room["is_exterior"] or not (room["requires_natural_light"] or room["requires_ventilation"]):
            continue
        window = place_window(room, floors[room["floor_id"]], plan["rooms"])
        if window:
            windows.append(window)
    return windows
