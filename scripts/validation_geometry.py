"""Geometry, connectivity, door, furniture, and circulation validation helpers."""
from __future__ import annotations
from collections import defaultdict, deque
from typing import Any
from shapely.geometry import Polygon, box
from common import bbox, centroid, door_swing_polygon_points, floor_bounds, pairwise, rect_contains, rect_intersection_area, room_area, room_map, rooms_by_floor

HABITABLE = {"bedroom", "living", "majlis", "dining", "office", "family-lounge"}
WET = {"bathroom", "wc", "kitchen", "laundry"}
IGNORE_CONNECTIVITY = {"terrace", "balcony", "courtyard", "garden", "shaft"}
STORAGE = {"storage", "pantry", "dressing", "linen"}

def issue(code: str, severity: str, message: str, *, floor_id: str | None = None,
          room_ids: list[str] | None = None, location_m: list[float] | None = None,
          suggestion: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "floor_id": floor_id,
        "room_ids": room_ids or [],
        "location_m": location_m,
        "suggestion": suggestion,
        "details": details or {},
    }


def validate_overlaps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for floor in plan["floors"]:
        rooms = rooms_by_floor(plan, floor["id"])
        for a, b in pairwise(rooms):
            overlap = rect_intersection_area(bbox(a), bbox(b))
            if overlap > 0.01:
                ax, ay = centroid(a); bx, by = centroid(b)
                out.append(issue("overlapping-rooms", "error", f"{a['name']} overlaps {b['name']} by {overlap:.2f} m².",
                    floor_id=floor["id"], room_ids=[a["id"], b["id"]], location_m=[(ax+bx)/2,(ay+by)/2],
                    suggestion="Move or resize one room so room polygons do not overlap.", details={"overlap_m2":round(overlap,3)}))
    return out


def validate_footprints(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]
    for floor in plan["floors"]:
        fp=floor_bounds(plan,floor["id"])
        for room in rooms_by_floor(plan,floor["id"]):
            if not rect_contains(fp,bbox(room)):
                out.append(issue("room-outside-footprint","error",f"{room['name']} extends outside the floor footprint.",floor_id=floor["id"],room_ids=[room["id"]],location_m=list(centroid(room)),suggestion="Adjust the room geometry or floor footprint."))
    return out


def door_graph(plan: dict[str, Any]) -> dict[str, set[str]]:
    graph: dict[str,set[str]]=defaultdict(set)
    for d in plan.get("doors",[]):
        a,b=d["from_room_id"],d["to_room_id"]
        if b!="EXTERIOR":
            graph[a].add(b); graph[b].add(a)
    return graph


def validate_connectivity(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; graph=door_graph(plan)
    for floor in plan["floors"]:
        rooms=[r for r in rooms_by_floor(plan,floor["id"]) if r["type"] not in IGNORE_CONNECTIVITY and not r.get("is_exterior")]
        ids={r["id"] for r in rooms}
        if not ids: continue
        starts=[d["from_room_id"] for d in plan.get("doors",[]) if d["floor_id"]==floor["id"] and d["to_room_id"]=="EXTERIOR" and d["from_room_id"] in ids]
        if not starts:
            vertical_ids={r["id"] for r in rooms if r["type"] in {"stair","elevator"}}
            starts=sorted(rid for rid in vertical_ids if graph.get(rid))
        if not starts:
            starts=[sorted(ids)[0]]
        seen=set(starts); q=deque(starts)
        while q:
            cur=q.popleft()
            for nxt in graph.get(cur,set()):
                if nxt in ids and nxt not in seen:
                    seen.add(nxt);q.append(nxt)
        for rid in sorted(ids-seen):
            r=next(x for x in rooms if x["id"]==rid)
            out.append(issue("disconnected-room","error",f"{r['name']} is disconnected from the floor circulation graph.",floor_id=floor["id"],room_ids=[rid],location_m=list(centroid(r)),suggestion="Add a door or circulation connection to a reachable room."))
    return out


def validate_missing_doors(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; counts=defaultdict(int)
    for d in plan.get("doors",[]):
        counts[d["from_room_id"]]+=1
        if d["to_room_id"]!="EXTERIOR": counts[d["to_room_id"]]+=1
    for r in plan["rooms"]:
        if r["type"] in IGNORE_CONNECTIVITY or r.get("is_exterior"): continue
        if counts[r["id"]]==0:
            out.append(issue("missing-door","error",f"{r['name']} has no door.",floor_id=r["floor_id"],room_ids=[r["id"]],location_m=list(centroid(r)),suggestion="Add at least one dimensioned door opening."))
    return out


def validate_door_collisions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]
    furniture=defaultdict(list)
    for item in [*plan.get("furniture",[]),*plan.get("fixtures",[])]: furniture[item["room_id"]].append(item)
    for floor in plan["floors"]:
        doors=[d for d in plan.get("doors",[]) if d["floor_id"]==floor["id"] and d.get("type")=="single-leaf"]
        sectors={}
        for door in doors:
            points=door_swing_polygon_points(door)
            if len(points)>=4: sectors[door["id"]]=Polygon(points)
        for a,b in pairwise(doors):
            if a["swing"].get("opens_into_room_id") != b["swing"].get("opens_into_room_id"): continue
            pa,pb=sectors.get(a["id"]),sectors.get(b["id"])
            if pa is not None and pb is not None and pa.intersection(pb).area>0.03:
                hx=(a["hinge_m"][0]+b["hinge_m"][0])/2; hy=(a["hinge_m"][1]+b["hinge_m"][1])/2
                out.append(issue("door-collision","warning",f"Door swings {a['id']} and {b['id']} overlap.",floor_id=floor["id"],room_ids=[a["from_room_id"],b["from_room_id"]],location_m=[hx,hy],suggestion="Reverse a swing, move a hinge, or use a sliding door."))
        for d in doors:
            sector=sectors.get(d["id"]); room_id=d["swing"].get("opens_into_room_id")
            if sector is None or not room_id: continue
            for item in furniture.get(room_id,[]):
                g=item["geometry"]; shape=box(g["x_m"],g["y_m"],g["x_m"]+g["width_m"],g["y_m"]+g["depth_m"])
                if sector.intersection(shape).area>0.025:
                    out.append(issue("door-furniture-collision","warning",f"Door {d['id']} swing conflicts with {item.get('name',item['type'])}.",floor_id=floor["id"],room_ids=[room_id],location_m=d["hinge_m"],suggestion="Relocate the object or revise the door swing."))
    return out


def validate_furniture(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; rmap=room_map(plan); by_room=defaultdict(list)
    for item in plan.get("furniture",[]): by_room[item["room_id"]].append(item)
    for rid,items in by_room.items():
        room=rmap[rid]
        rb=bbox(room)
        for item in items:
            g=item["geometry"]; ib=(g["x_m"],g["y_m"],g["width_m"],g["depth_m"])
            if not rect_contains(rb,ib,0.001):
                out.append(issue("furniture-outside-room","error",f"{item.get('name',item['type'])} does not fit inside {room['name']}.",floor_id=room["floor_id"],room_ids=[rid],location_m=[g["x_m"],g["y_m"]],suggestion="Resize or reposition the furniture."))
        for a,b in pairwise(items):
            ga,gb=a["geometry"],b["geometry"]
            aa=(ga["x_m"],ga["y_m"],ga["width_m"],ga["depth_m"]); bb=(gb["x_m"],gb["y_m"],gb["width_m"],gb["depth_m"])
            overlap=rect_intersection_area(aa,bb)
            if overlap>0.02:
                out.append(issue("furniture-collision","warning",f"{a.get('name',a['type'])} overlaps {b.get('name',b['type'])} in {room['name']}.",floor_id=room["floor_id"],room_ids=[rid],location_m=list(centroid(room)),suggestion="Rearrange the furniture layout.",details={"overlap_m2":round(overlap,3)}))
    return out


def validate_circulation(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]; min_w=float(plan.get("standards",{}).get("minimum_corridor_width_m",1.2))
    for r in plan["rooms"]:
        if r["type"] in {"corridor","lobby"}:
            width=min(r["geometry"]["width_m"],r["geometry"]["depth_m"])
            if width+1e-6<min_w:
                out.append(issue("narrow-circulation","error",f"{r['name']} clear width is {width:.2f} m, below {min_w:.2f} m.",floor_id=r["floor_id"],room_ids=[r["id"]],location_m=list(centroid(r)),suggestion="Widen the circulation space.",details={"clear_width_m":width,"minimum_m":min_w}))
    return out
