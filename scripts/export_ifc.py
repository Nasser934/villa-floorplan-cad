#!/usr/bin/env python3
"""Export a deterministic IFC4 model in metres using IfcOpenShell."""
from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

from common import load_json, require_dependency

FIXED_TIME = "2000-01-01T00:00:00"
FIXED_UNIX_TIME = 946684800


def _matrix(np, x: float, y: float, z: float, angle: float = 0.0):
    cosine, sine = math.cos(angle), math.sin(angle)
    return np.array([[cosine, -sine, 0.0, x], [sine, cosine, 0.0, y], [0.0, 0.0, 1.0, z], [0.0, 0.0, 0.0, 1.0]], dtype=float)


def _ifc_guid(ifcopenshell, *parts: object) -> str:
    hexadecimal = hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:32]
    return ifcopenshell.guid.compress(hexadecimal)


def _set_deterministic_metadata(model, ifcopenshell, seed: str, output_name: str) -> None:
    roots = sorted(model.by_type("IfcRoot"), key=lambda entity: (entity.is_a(), getattr(entity, "Name", "") or "", entity.id()))
    for index, entity in enumerate(roots):
        entity.GlobalId = _ifc_guid(ifcopenshell, seed, entity.is_a(), getattr(entity, "Name", ""), index)
    for owner_history in model.by_type("IfcOwnerHistory"):
        owner_history.CreationDate = FIXED_UNIX_TIME
        if hasattr(owner_history, "LastModifiedDate"):
            owner_history.LastModifiedDate = FIXED_UNIX_TIME
    try:
        model.header.file_name.name = output_name
        model.header.file_name.time_stamp = FIXED_TIME
        model.header.file_name.author = ("villa-floorplan-cad",)
        model.header.file_name.organization = ("OpenAI",)
        model.header.file_name.preprocessor_version = "IfcOpenShell"
        model.header.file_name.originating_system = "villa-floorplan-cad"
        model.header.file_name.authorization = ""
    except (AttributeError, TypeError):
        pass


def _assign_representation(api, model, product, representation) -> None:
    api.run("geometry.assign_representation", model, product=product, representation=representation)


def _place(api, model, np, product, x: float, y: float, z: float, angle: float = 0.0) -> None:
    api.run("geometry.edit_object_placement", model, product=product, matrix=_matrix(np, x, y, z, angle), is_si=True)


def _contain(api, model, product, storey) -> None:
    api.run("spatial.assign_container", model, products=[product], relating_structure=storey)


def export_ifc(plan_path: Path, output: Path) -> Path:
    require_dependency("ifcopenshell")
    require_dependency("numpy")
    import ifcopenshell
    import ifcopenshell.api as api
    import numpy as np

    plan = load_json(plan_path)
    project_name = plan.get("project", {}).get("name", "Residential Villa")
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name=project_name)
    length_unit = api.run("unit.add_si_unit", model, unit_type="LENGTHUNIT")
    area_unit = api.run("unit.add_si_unit", model, unit_type="AREAUNIT")
    volume_unit = api.run("unit.add_si_unit", model, unit_type="VOLUMEUNIT")
    api.run("unit.assign_unit", model, units=[length_unit, area_unit, volume_unit])
    model_context = api.run("context.add_context", model, context_type="Model")
    body_context = api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_context)
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Villa")
    api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    api.run("aggregate.assign_object", model, products=[building], relating_object=site)

    floors_by_id = {floor["id"]: floor for floor in plan["floors"]}
    storeys: dict[str, object] = {}
    for floor in plan["floors"]:
        storey = api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name=floor["name"])
        storey.Elevation = float(floor["level_m"])
        api.run("aggregate.assign_object", model, products=[storey], relating_object=building)
        storeys[floor["id"]] = storey
        footprint = floor["footprint"]
        slab = api.run("root.create_entity", model, ifc_class="IfcSlab", name=f"{floor['name']} Slab", predefined_type="FLOOR")
        polyline = [(0.0, 0.0), (float(footprint["width_m"]), 0.0), (float(footprint["width_m"]), float(footprint["depth_m"])), (0.0, float(footprint["depth_m"]))]
        slab_representation = api.run("geometry.add_slab_representation", model, context=body_context, depth=0.2, polyline=polyline)
        _assign_representation(api, model, slab, slab_representation)
        _place(api, model, np, slab, float(footprint.get("x_m", 0.0)), float(footprint.get("y_m", 0.0)), float(floor["level_m"]) - 0.2)
        _contain(api, model, slab, storey)

    for wall in plan["walls"]:
        x1, y1 = map(float, wall["start_m"]); x2, y2 = map(float, wall["end_m"])
        length = math.hypot(x2 - x1, y2 - y1); angle = math.atan2(y2 - y1, x2 - x1)
        floor = floors_by_id[wall["floor_id"]]
        entity = api.run("root.create_entity", model, ifc_class="IfcWall", name=wall["id"])
        representation = api.run("geometry.add_wall_representation", model, context=body_context, length=length, height=float(wall["height_m"]), thickness=float(wall["thickness_m"]), x_angle=0.0)
        _assign_representation(api, model, entity, representation)
        _place(api, model, np, entity, x1, y1, float(floor["level_m"]), angle)
        _contain(api, model, entity, storeys[wall["floor_id"]])

    for room in plan["rooms"]:
        if room.get("is_exterior"):
            continue
        space = api.run("root.create_entity", model, ifc_class="IfcSpace", name=room["name"])
        api.run("aggregate.assign_object", model, products=[space], relating_object=storeys[room["floor_id"]])

    for door in plan.get("doors", []):
        floor = floors_by_id[door["floor_id"]]
        entity = api.run("root.create_entity", model, ifc_class="IfcDoor", name=door["id"])
        operation_type = "SLIDING_TO_LEFT" if door.get("type") == "sliding" else "SINGLE_SWING_LEFT"
        representation = api.run("geometry.add_door_representation", model, context=body_context, overall_height=float(door["height_m"]), overall_width=float(door["width_m"]), operation_type=operation_type)
        if representation is not None:
            _assign_representation(api, model, entity, representation)
        closed = door.get("closed_leaf_end_m", door["hinge_m"])
        angle = math.atan2(closed[1] - door["hinge_m"][1], closed[0] - door["hinge_m"][0])
        _place(api, model, np, entity, float(door["hinge_m"][0]), float(door["hinge_m"][1]), float(floor["level_m"]), angle)
        _contain(api, model, entity, storeys[door["floor_id"]])

    for window in plan.get("windows", []):
        floor = floors_by_id[window["floor_id"]]
        entity = api.run("root.create_entity", model, ifc_class="IfcWindow", name=window["id"])
        representation = api.run("geometry.add_window_representation", model, context=body_context, overall_height=float(window["height_m"]), overall_width=float(window["width_m"]), partition_type="SINGLE_PANEL")
        _assign_representation(api, model, entity, representation)
        coordinate = float(window["wall"]["coordinate_m"]); position = float(window["position_m"])
        if window["wall"]["orientation"] == "vertical":
            x, y, angle = coordinate, position - float(window["width_m"]) / 2, math.pi / 2
        else:
            x, y, angle = position - float(window["width_m"]) / 2, coordinate, 0.0
        _place(api, model, np, entity, x, y, float(floor["level_m"]) + float(window["sill_height_m"]), angle)
        _contain(api, model, entity, storeys[window["floor_id"]])

    for vertical in plan.get("vertical_elements", plan.get("vertical_circulation", [])):
        floor = floors_by_id[vertical["floor_id"]]; geometry = vertical["geometry"]; element_type = vertical["type"]
        if element_type == "stair":
            ifc_class, predefined_type = "IfcStair", "STRAIGHT_RUN_STAIR"
        elif element_type == "elevator":
            ifc_class, predefined_type = "IfcTransportElement", "ELEVATOR"
        else:
            ifc_class, predefined_type = "IfcBuildingElementProxy", None
        arguments = {"ifc_class": ifc_class, "name": vertical["id"]}
        if predefined_type:
            arguments["predefined_type"] = predefined_type
        entity = api.run("root.create_entity", model, **arguments)
        height = float(floor["floor_to_floor_height_m"])
        vertices = [[(0.0, 0.0, 0.0), (float(geometry["width_m"]), 0.0, 0.0), (float(geometry["width_m"]), float(geometry["depth_m"]), 0.0), (0.0, float(geometry["depth_m"]), 0.0), (0.0, 0.0, height), (float(geometry["width_m"]), 0.0, height), (float(geometry["width_m"]), float(geometry["depth_m"]), height), (0.0, float(geometry["depth_m"]), height)]]
        faces = [[(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]]
        representation = api.run("geometry.add_mesh_representation", model, context=body_context, vertices=vertices, faces=faces)
        _assign_representation(api, model, entity, representation)
        _place(api, model, np, entity, float(geometry["x_m"]), float(geometry["y_m"]), float(floor["level_m"]))
        _contain(api, model, entity, storeys[vertical["floor_id"]])

    _set_deterministic_metadata(model, ifcopenshell, plan.get("schema_version", "plan"), output.name)
    output.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(output))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    path = Path(args.plan).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else path.parent / "villa-model.ifc"
    print(export_ifc(path, output))


if __name__ == "__main__":
    main()
