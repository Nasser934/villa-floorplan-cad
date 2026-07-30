#!/usr/bin/env python3
"""Generate a dimensionally consistent metric villa plan.json from program.json."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
from typing import Any

from common import dump_json, load_json, round_coords
from plan_rooms import derive_walls, normalize_rooms
from plan_openings import derive_doors, derive_windows
from plan_objects import derive_adjacencies, derive_dimensions, derive_furniture_and_fixtures, vertical_elements


def validate_program(program: dict[str, Any]) -> None:
    """Fail early with readable input errors before creating partial outputs."""
    errors: list[str] = []
    if not isinstance(program, dict):
        raise ValueError("program.json must contain a JSON object")
    units = program.get("project", {}).get("units", "m")
    if units not in {"m", "metres", "meters"}:
        errors.append("project.units must be metric ('m')")
    floors = program.get("floors")
    if not isinstance(floors, list) or not floors:
        errors.append("floors must be a non-empty list")
        floors = []
    floor_ids: set[str] = set()
    for index, floor in enumerate(floors):
        label = f"floors[{index}]"
        if not isinstance(floor, dict):
            errors.append(f"{label} must be an object")
            continue
        floor_id = str(floor.get("id", "")).strip()
        if not floor_id:
            errors.append(f"{label}.id is required")
        elif floor_id in floor_ids:
            errors.append(f"duplicate floor id: {floor_id}")
        floor_ids.add(floor_id)
        footprint = floor.get("footprint")
        if not isinstance(footprint, dict):
            errors.append(f"{label}.footprint is required")
        else:
            for field in ("width_m", "depth_m"):
                try:
                    if float(footprint.get(field, 0)) <= 0:
                        errors.append(f"{label}.footprint.{field} must be positive")
                except (TypeError, ValueError):
                    errors.append(f"{label}.footprint.{field} must be a number")
        rooms = floor.get("rooms")
        if not isinstance(rooms, list):
            errors.append(f"{label}.rooms must be a list")
            continue
        room_ids: set[str] = set()
        for room_index, room in enumerate(rooms):
            room_label = f"{label}.rooms[{room_index}]"
            if not isinstance(room, dict):
                errors.append(f"{room_label} must be an object")
                continue
            if not str(room.get("name", "")).strip():
                errors.append(f"{room_label}.name is required")
            room_id = str(room.get("id", "")).strip()
            if room_id and room_id in room_ids:
                errors.append(f"duplicate room id on {floor_id or label}: {room_id}")
            if room_id:
                room_ids.add(room_id)
            for field in ("width_m", "depth_m", "target_area_m2"):
                if field not in room:
                    continue
                try:
                    if float(room[field]) <= 0:
                        errors.append(f"{room_label}.{field} must be positive")
                except (TypeError, ValueError):
                    errors.append(f"{room_label}.{field} must be a number")
    if errors:
        raise ValueError("Invalid program.json:\n- " + "\n- ".join(errors))


def build_plan(program: dict[str, Any]) -> dict[str, Any]:
    validate_program(program)
    program = copy.deepcopy(program)
    standards = program.get("standards", {})
    standards.setdefault("external_wall_thickness_m", 0.25)
    standards.setdefault("internal_wall_thickness_m", 0.15)
    standards.setdefault("minimum_door_width_m", 0.8)
    standards.setdefault("floor_to_floor_height_m", 3.4)
    standards.setdefault("clear_ceiling_height_m", 3.0)
    source_epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    floors = []
    for raw in program["floors"]:
        floors.append({
            "id": raw["id"],
            "name": raw.get("name", raw["id"]),
            "level_m": float(raw.get("level_m", 0)),
            "floor_to_floor_height_m": float(raw.get("floor_to_floor_height_m", standards["floor_to_floor_height_m"])),
            "clear_height_m": float(raw.get("clear_height_m", standards["clear_ceiling_height_m"])),
            "footprint": copy.deepcopy(raw["footprint"]),
        })
    plan = {
        "schema_version": "villa-floorplan-cad.plan.v1",
        "units": "metres",
        "unit_definitions": {"length": "m", "area": "m2", "angle": "deg"},
        "generation": {"deterministic": True, "source_date_epoch": source_epoch},
        "project": copy.deepcopy(program.get("project", {})),
        "site": copy.deepcopy(program.get("site", {})),
        "standards": copy.deepcopy(standards),
        "floors": floors,
        "levels_and_heights": {
            "floors": [
                {
                    "floor_id": floor["id"],
                    "elevation_m": floor["level_m"],
                    "floor_to_floor_height_m": floor["floor_to_floor_height_m"],
                    "clear_height_m": floor["clear_height_m"],
                    "slab_thickness_m": float(standards.get("slab_thickness_m", 0.20)),
                }
                for floor in floors
            ],
            "external_wall_height_m": float(standards.get("external_wall_height_m", standards["clear_ceiling_height_m"])),
            "internal_wall_height_m": float(standards.get("internal_wall_height_m", standards["clear_ceiling_height_m"])),
            "door_height_m": float(standards.get("door_height_m", 2.20)),
            "window_head_height_m": float(standards.get("window_head_height_m", 2.40)),
            "roof_parapet_height_m": float(standards.get("parapet_height_m", 1.10)),
        },
        "rooms": normalize_rooms(program),
    }
    plan["walls"] = derive_walls(plan, standards)
    plan["doors"] = derive_doors(plan, program, standards)
    plan["windows"] = derive_windows(plan)
    plan["openings"] = [*plan["doors"], *plan["windows"]]
    plan["furniture"], plan["fixtures"] = derive_furniture_and_fixtures(plan)
    plan["adjacency_relationships"] = derive_adjacencies(plan)
    plan["adjacencies"] = plan["adjacency_relationships"]
    plan["dimensions"] = derive_dimensions(plan)
    plan["vertical_elements"] = vertical_elements(plan)
    plan["vertical_circulation"] = plan["vertical_elements"]
    plan["parking"] = {
        "required_spaces": int(program.get("site", {}).get("parking_spaces", 0)),
        "provided_spaces": sum(1 for item in plan["furniture"] if item["type"] == "car"),
    }
    plan["external_access"] = [
        {"door_id": door["id"], "room_id": door["from_room_id"], "side": door.get("external_side")}
        for door in plan["doors"]
        if door["to_room_id"] == "EXTERIOR"
    ]
    return round_coords(plan)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", help="Path to program.json")
    parser.add_argument("--output", default=None, help="Output plan.json path")
    args = parser.parse_args()
    program_path = Path(args.program).expanduser().resolve()
    program = load_json(program_path)
    output = Path(args.output).expanduser().resolve() if args.output else program_path.parent / "output" / "plan.json"
    dump_json(build_plan(program), output)
    print(output)


if __name__ == "__main__":
    main()
