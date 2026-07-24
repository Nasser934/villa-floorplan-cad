#!/usr/bin/env python3
"""Shared deterministic geometry and I/O helpers for villa-floorplan-cad."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

EPS = 1e-6


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return text or "item"


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{slug(prefix)}-{digest}"


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(data: Any, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def bbox(room: dict[str, Any]) -> tuple[float, float, float, float]:
    g = room["geometry"]
    return float(g["x_m"]), float(g["y_m"]), float(g["width_m"]), float(g["depth_m"])


def polygon_points(room: dict[str, Any]) -> list[tuple[float, float]]:
    x, y, w, d = bbox(room)
    return [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]


def room_area(room: dict[str, Any]) -> float:
    x, y, w, d = bbox(room)
    return round(w * d, 4)


def centroid(room: dict[str, Any]) -> tuple[float, float]:
    x, y, w, d = bbox(room)
    return x + w / 2, y + d / 2


def rect_intersection_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ad = a
    bx, by, bw, bd = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ad, by + bd) - max(ay, by))
    return ix * iy


def rects_touch(a: tuple[float, float, float, float], b: tuple[float, float, float, float], tol: float = 0.01) -> bool:
    ax, ay, aw, ad = a
    bx, by, bw, bd = b
    vertical = (abs(ax + aw - bx) <= tol or abs(bx + bw - ax) <= tol) and min(ay + ad, by + bd) - max(ay, by) > tol
    horizontal = (abs(ay + ad - by) <= tol or abs(by + bd - ay) <= tol) and min(ax + aw, bx + bw) - max(ax, bx) > tol
    return vertical or horizontal


def shared_boundary(a: dict[str, Any], b: dict[str, Any], tol: float = 0.01) -> dict[str, Any] | None:
    ax, ay, aw, ad = bbox(a)
    bx, by, bw, bd = bbox(b)
    if abs(ax + aw - bx) <= tol:
        lo, hi = max(ay, by), min(ay + ad, by + bd)
        if hi - lo > tol:
            return {"orientation": "vertical", "coordinate_m": bx, "start_m": lo, "end_m": hi}
    if abs(bx + bw - ax) <= tol:
        lo, hi = max(ay, by), min(ay + ad, by + bd)
        if hi - lo > tol:
            return {"orientation": "vertical", "coordinate_m": ax, "start_m": lo, "end_m": hi}
    if abs(ay + ad - by) <= tol:
        lo, hi = max(ax, bx), min(ax + aw, bx + bw)
        if hi - lo > tol:
            return {"orientation": "horizontal", "coordinate_m": by, "start_m": lo, "end_m": hi}
    if abs(by + bd - ay) <= tol:
        lo, hi = max(ax, bx), min(ax + aw, bx + bw)
        if hi - lo > tol:
            return {"orientation": "horizontal", "coordinate_m": ay, "start_m": lo, "end_m": hi}
    return None


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def floor_by_id(plan: dict[str, Any], floor_id: str) -> dict[str, Any]:
    return next(f for f in plan["floors"] if f["id"] == floor_id)


def rooms_by_floor(plan: dict[str, Any], floor_id: str) -> list[dict[str, Any]]:
    return [r for r in plan["rooms"] if r["floor_id"] == floor_id]


def room_map(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in plan["rooms"]}


def floor_bounds(plan: dict[str, Any], floor_id: str) -> tuple[float, float, float, float]:
    floor = floor_by_id(plan, floor_id)
    fp = floor["footprint"]
    return float(fp.get("x_m", 0)), float(fp.get("y_m", 0)), float(fp["width_m"]), float(fp["depth_m"])


def opening_center(opening: dict[str, Any]) -> tuple[float, float]:
    wall = opening["wall"]
    pos = float(opening["position_m"])
    if wall["orientation"] == "vertical":
        return float(wall["coordinate_m"]), pos
    return pos, float(wall["coordinate_m"])


def door_swing_bbox(door: dict[str, Any]) -> tuple[float, float, float, float]:
    hx, hy = door["hinge_m"]
    width = float(door["width_m"])
    return hx - width, hy - width, width * 2, width * 2


def door_swing_polygon_points(door: dict[str, Any], segments: int = 12) -> list[tuple[float, float]]:
    """Return a quarter-sector polygon for a swinging door in plan metres."""
    if door.get("type") == "overhead" or not door.get("open_leaf_end_m") or not door.get("closed_leaf_end_m"):
        return []
    hx, hy = map(float, door["hinge_m"])
    cx, cy = map(float, door["closed_leaf_end_m"])
    ox, oy = map(float, door["open_leaf_end_m"])
    start = math.atan2(cy - hy, cx - hx)
    end = math.atan2(oy - hy, ox - hx)
    delta = (end - start + math.pi) % (2 * math.pi) - math.pi
    radius = float(door["width_m"])
    points = [(hx, hy)]
    for index in range(segments + 1):
        angle = start + delta * index / segments
        points.append((hx + radius * math.cos(angle), hy + radius * math.sin(angle)))
    points.append((hx, hy))
    return points


def rect_contains(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float], tol: float = EPS) -> bool:
    ox, oy, ow, od = outer
    ix, iy, iw, id_ = inner
    return ix >= ox - tol and iy >= oy - tol and ix + iw <= ox + ow + tol and iy + id_ <= oy + od + tol


def pairwise(items: Iterable[Any]):
    values = list(items)
    for i, a in enumerate(values):
        for b in values[i + 1 :]:
            yield a, b


def round_coords(obj: Any, digits: int = 4) -> Any:
    if isinstance(obj, float):
        return round(obj, digits)
    if isinstance(obj, list):
        return [round_coords(x, digits) for x in obj]
    if isinstance(obj, dict):
        return {k: round_coords(v, digits) for k, v in obj.items()}
    return obj


def resolve_project_paths(project: str | Path) -> tuple[Path, Path, Path]:
    root = Path(project).expanduser().resolve()
    if root.is_file():
        program = root
        root = root.parent
    else:
        program = root / "program.json"
    output = root / "output"
    return root, program, output


def require_dependency(module: str, install_name: str | None = None):
    try:
        return __import__(module)
    except ImportError as exc:
        package = install_name or module
        raise SystemExit(f"Missing dependency '{package}'. Install with: python -m pip install {package}") from exc
