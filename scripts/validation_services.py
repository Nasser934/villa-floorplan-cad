"""Lighting, ventilation, storage, services, privacy, core, area, and access checks."""
from __future__ import annotations
from collections import defaultdict
from typing import Any
from shapely.geometry import box
from common import bbox, centroid, distance, floor_bounds, pairwise, rect_intersection_area, room_area, room_map, rooms_by_floor
from validation_geometry import door_graph, issue

HABITABLE = {"bedroom", "living", "majlis", "dining", "office", "family-lounge"}
WET = {"bathroom", "wc", "kitchen", "laundry"}
STORAGE = {"storage", "pantry", "dressing", "linen"}

def validate_light_ventilation(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; windows=defaultdict(list)
    for w in plan.get("windows",[]): windows[w["room_id"]].append(w)
    for r in plan["rooms"]:
        if r.get("is_exterior"): continue
        if r.get("requires_natural_light") and not windows[r["id"]]:
            out.append(issue("missing-natural-light","warning",f"{r['name']} has no exterior window.",floor_id=r["floor_id"],room_ids=[r["id"]],location_m=list(centroid(r)),suggestion="Add an exterior window, courtyard opening, or approved daylight solution."))
        if r["type"] in WET and not windows[r["id"]] and not r.get("mechanical_ventilation"):
            out.append(issue("missing-ventilation","error",f"{r['name']} has neither a window nor mechanical ventilation.",floor_id=r["floor_id"],room_ids=[r["id"]],location_m=list(centroid(r)),suggestion="Add an exterior window or mechanical extract ventilation."))
    return out


def validate_storage(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; ratio=float(plan.get("standards",{}).get("minimum_storage_ratio",0.025))
    for floor in plan["floors"]:
        rooms=rooms_by_floor(plan,floor["id"])
        total=sum(r["area_m2"] for r in rooms if not r.get("is_exterior"))
        storage=sum(r["area_m2"] for r in rooms if r["type"] in STORAGE)
        if total and storage/total<ratio:
            out.append(issue("missing-storage","warning",f"Storage on {floor['name']} is {storage:.2f} m² ({storage/total:.1%}), below {ratio:.1%}.",floor_id=floor["id"],location_m=None,suggestion="Add linen, pantry, under-stair, general, or bedroom storage.",details={"storage_m2":storage,"floor_area_m2":total,"ratio":round(storage/total,4)}))
    return out


def validate_service_routes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; max_route=float(plan.get("standards",{}).get("maximum_service_route_m",8.0))
    for floor in plan["floors"]:
        rooms=rooms_by_floor(plan,floor["id"]); service=[r for r in rooms if r["type"] in {"shaft","kitchen","laundry"}]
        anchors=service
        for wet in [r for r in rooms if r["type"] in WET]:
            if wet["id"] in {a["id"] for a in anchors}: continue
            others=[a for a in anchors if a["id"]!=wet["id"]]
            if not others: continue
            dist=min(distance(centroid(wet),centroid(a)) for a in others)
            if dist>max_route:
                out.append(issue("long-service-route","warning",f"{wet['name']} is {dist:.2f} m from the nearest service anchor.",floor_id=floor["id"],room_ids=[wet["id"]],location_m=list(centroid(wet)),suggestion="Move the wet room closer to a shaft or add a service riser.",details={"route_m":round(dist,3),"maximum_m":max_route}))
    return out


def validate_kitchen_dining(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; max_d=float(plan.get("standards",{}).get("maximum_kitchen_dining_distance_m",8.0)); graph=door_graph(plan)
    for floor in plan["floors"]:
        rooms=rooms_by_floor(plan,floor["id"]); kitchens=[r for r in rooms if r["type"]=="kitchen"]; dining=[r for r in rooms if r["type"]=="dining"]
        for k in kitchens:
            if not dining: continue
            d=min(dining,key=lambda r:distance(centroid(k),centroid(r))); dist=distance(centroid(k),centroid(d))
            direct=d["id"] in graph.get(k["id"],set())
            if dist>max_d or not direct:
                out.append(issue("poor-kitchen-dining-connection","warning",f"Kitchen-to-dining connection is {'not direct' if not direct else f'{dist:.2f} m'}.",floor_id=floor["id"],room_ids=[k["id"],d["id"]],location_m=[(centroid(k)[0]+centroid(d)[0])/2,(centroid(k)[1]+centroid(d)[1])/2],suggestion="Provide a short direct door or serving route between kitchen and dining."))
    return out


def validate_privacy(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; rmap=room_map(plan)
    buffer_types={"lobby","corridor","foyer","vestibule"}
    for d in plan.get("doors",[]):
        if d["to_room_id"]=="EXTERIOR": continue
        a,b=rmap[d["from_room_id"]],rmap[d["to_room_id"]]
        zones={a["zone"],b["zone"]}
        if zones=={"guest","family"} and a["type"] not in buffer_types and b["type"] not in buffer_types:
            out.append(issue("guest-family-privacy-conflict","error",f"Direct door between guest room {a['name']} and family room {b['name']}.",floor_id=d["floor_id"],room_ids=[a["id"],b["id"]],location_m=d["hinge_m"],suggestion="Insert a lobby, controlled corridor, or separate entrance."))
        if zones=={"guest","service"} and a["type"] not in buffer_types and b["type"] not in buffer_types:
            out.append(issue("guest-service-privacy-conflict","warning",f"Direct guest-to-service connection between {a['name']} and {b['name']}.",floor_id=d["floor_id"],room_ids=[a["id"],b["id"]],location_m=d["hinge_m"],suggestion="Route service access away from the guest path."))
    return out


def validate_plumbing_alignment(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; tol=float(plan.get("standards",{}).get("plumbing_stack_tolerance_m",1.5)); floors=sorted(plan["floors"],key=lambda f:f["level_m"])
    for lower,upper in zip(floors,floors[1:]):
        lower_wet=[r for r in rooms_by_floor(plan,lower["id"]) if r["type"] in WET or r["type"]=="shaft"]
        upper_wet=[r for r in rooms_by_floor(plan,upper["id"]) if r["type"] in WET]
        for r in upper_wet:
            if not lower_wet: continue
            dist=min(distance(centroid(r),centroid(x)) for x in lower_wet)
            if dist>tol:
                out.append(issue("stacked-plumbing-misalignment","warning",f"{r['name']} is offset {dist:.2f} m from lower-floor wet/service spaces.",floor_id=upper["id"],room_ids=[r["id"]],location_m=list(centroid(r)),suggestion="Align wet walls vertically or add a documented offset riser.",details={"offset_m":round(dist,3),"tolerance_m":tol}))
    return out


def validate_vertical_conflicts(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]
    for floor in plan["floors"]:
        elems=[r for r in rooms_by_floor(plan,floor["id"]) if r["type"] in {"stair","elevator"}]
        for a,b in pairwise(elems):
            overlap=rect_intersection_area(bbox(a),bbox(b))
            if overlap>0.01:
                out.append(issue("stair-elevator-conflict","error",f"{a['name']} overlaps {b['name']}.",floor_id=floor["id"],room_ids=[a["id"],b["id"]],location_m=[(centroid(a)[0]+centroid(b)[0])/2,(centroid(a)[1]+centroid(b)[1])/2],suggestion="Separate the stair and elevator footprints."))
    floors=sorted(plan["floors"],key=lambda f:f["level_m"])
    for lower,upper in zip(floors,floors[1:]):
        for typ in ("stair","elevator"):
            lows=[r for r in rooms_by_floor(plan,lower["id"]) if r["type"]==typ]; ups=[r for r in rooms_by_floor(plan,upper["id"]) if r["type"]==typ]
            if lows and ups and distance(centroid(lows[0]),centroid(ups[0]))>0.25:
                out.append(issue("vertical-core-misalignment","error",f"{typ.title()} footprints are not vertically aligned.",floor_id=upper["id"],room_ids=[lows[0]["id"],ups[0]["id"]],location_m=list(centroid(ups[0])),suggestion="Align the vertical core across floors."))
    return out


def validate_areas_dimensions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; dims_by_room=defaultdict(set); overall=defaultdict(set)
    for d in plan.get("dimensions",[]):
        if d.get("room_id"): dims_by_room[d["room_id"]].add(d["axis"])
        elif d.get("type")=="overall": overall[d["floor_id"]].add(d["axis"])
    for r in plan["rooms"]:
        calc=room_area(r); stated=float(r.get("area_m2",0)); target=float(r.get("target_area_m2",calc))
        if abs(calc-stated)>0.02:
            out.append(issue("incorrect-room-area","error",f"{r['name']} stored area {stated:.2f} m² differs from geometry {calc:.2f} m².",floor_id=r["floor_id"],room_ids=[r["id"]],location_m=list(centroid(r)),suggestion="Recalculate area from the room polygon.",details={"stored_m2":stated,"calculated_m2":calc}))
        if target and abs(calc-target)/target>0.08:
            out.append(issue("room-area-outside-program","warning",f"{r['name']} area {calc:.2f} m² differs from target {target:.2f} m² by more than 8%.",floor_id=r["floor_id"],room_ids=[r["id"]],location_m=list(centroid(r)),suggestion="Resize the room or update the approved program target."))
        if dims_by_room[r["id"]]!={"x","y"}:
            out.append(issue("missing-dimensions","error",f"{r['name']} lacks complete internal dimensions.",floor_id=r["floor_id"],room_ids=[r["id"]],location_m=list(centroid(r)),suggestion="Add width and depth dimensions."))
    for floor in plan["floors"]:
        if overall[floor["id"]]!={"x","y"}:
            out.append(issue("missing-overall-dimensions","error",f"{floor['name']} lacks complete overall dimensions.",floor_id=floor["id"],suggestion="Add overall width and depth dimensions."))
    return out


def validate_parking_access(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; p=plan.get("parking",{})
    if p.get("provided_spaces",0)<p.get("required_spaces",0):
        out.append(issue("insufficient-parking","error",f"Only {p.get('provided_spaces',0)} parking spaces are provided; {p.get('required_spaces',0)} are required.",suggestion="Increase garage or on-site parking capacity."))
    entries=plan.get("external_access",[])
    zones={room_map(plan)[e["room_id"]]["zone"] for e in entries if e["room_id"] in room_map(plan)}
    for required in ("guest","family","service"):
        if required not in zones:
            out.append(issue("missing-external-access","warning",f"No dedicated external access is detected for the {required} zone.",suggestion=f"Add or document a separate {required} entrance."))
    return out
