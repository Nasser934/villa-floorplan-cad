"""Furniture, fixture, adjacency, dimension, and vertical-element helpers."""
from __future__ import annotations
from typing import Any
from shapely.geometry import Polygon, box
from common import bbox, centroid, door_swing_polygon_points, floor_bounds, rects_touch, rooms_by_floor, round_coords, shared_boundary, stable_id

def furniture_rect(room: dict[str, Any], item_type: str, name: str, ox: float, oy: float, w: float, d: float, rotation: int = 0) -> dict[str, Any]:
    x, y, rw, rd = bbox(room)
    return {
        "id": stable_id("furniture", room["floor_id"], room["id"], item_type, ox, oy),
        "floor_id": room["floor_id"], "room_id": room["id"], "type": item_type, "name": name,
        "geometry": {"x_m": round(x + ox, 3), "y_m": round(y + oy, 3), "width_m": w, "depth_m": d, "rotation_deg": rotation},
        "clearance_m": 0.6,
    }


def optimize_object_layout(plan: dict[str, Any], furniture: list[dict[str, Any]], fixtures: list[dict[str, Any]]) -> None:
    """Move generated objects deterministically to clear door swings and each other."""
    rmap={r["id"]:r for r in plan["rooms"]}
    sectors: dict[str,list[Polygon]]={}
    for door in plan.get("doors",[]):
        room_id=door.get("swing",{}).get("opens_into_room_id")
        points=door_swing_polygon_points(door)
        if room_id and len(points)>=4:
            sectors.setdefault(room_id,[]).append(Polygon(points).buffer(0.05,join_style=2))
    by_room: dict[str,list[dict[str,Any]]]={}
    for item in [*furniture,*fixtures]: by_room.setdefault(item["room_id"],[]).append(item)
    for room_id,items in by_room.items():
        room=rmap[room_id]; rx,ry,rw,rd=bbox(room); margin=0.10
        placed=[]
        items.sort(key=lambda item:(-(item["geometry"]["width_m"]*item["geometry"]["depth_m"]),item["type"],item["id"]))
        for item in items:
            g=item["geometry"]; iw=float(g["width_m"]); idp=float(g["depth_m"]); original=(float(g["x_m"]),float(g["y_m"]))
            xmin,xmax=rx+margin,rx+rw-iw-margin; ymin,ymax=ry+margin,ry+rd-idp-margin
            if xmax<xmin or ymax<ymin: continue
            step=0.10
            xs=[]; x=xmin
            while x<=xmax+1e-6: xs.append(round(x,3)); x+=step
            ys=[]; y=ymin
            while y<=ymax+1e-6: ys.append(round(y,3)); y+=step
            if round(xmax,3) not in xs: xs.append(round(xmax,3))
            if round(ymax,3) not in ys: ys.append(round(ymax,3))
            candidates={(round(min(max(original[0],xmin),xmax),3),round(min(max(original[1],ymin),ymax),3))}
            candidates.update((x,y) for x in xs for y in ys)
            ordered=sorted(candidates,key=lambda xy:((xy[0]-original[0])**2+(xy[1]-original[1])**2,xy[1],xy[0]))
            selected=None
            for cx,cy in ordered:
                shape=box(cx,cy,cx+iw,cy+idp)
                if any(shape.intersects(sec) and shape.intersection(sec).area>0.002 for sec in sectors.get(room_id,[])): continue
                if any(shape.intersection(other).area>0.002 for other in placed): continue
                selected=(cx,cy,shape); break
            if selected:
                g["x_m"],g["y_m"]=selected[0],selected[1]; placed.append(selected[2])
            else:
                placed.append(box(original[0],original[1],original[0]+iw,original[1]+idp))


def derive_furniture_and_fixtures(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    furniture: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = []
    for room in sorted(plan["rooms"], key=lambda r: r["id"]):
        x, y, w, d = bbox(room)
        t = room["type"]
        if room["is_exterior"]:
            continue
        if t == "bedroom":
            bed_w = min(1.8, max(1.2, w - 1.2)); bed_d = min(2.0, max(1.8, d - 1.2))
            furniture.append(furniture_rect(room, "bed", "Bed", 0.55, 0.55, bed_w, bed_d))
            if w >= 2.5:
                furniture.append(furniture_rect(room, "wardrobe", "Wardrobe", 0.3, max(0.3, d - 0.95), min(2.4, w - 0.6), 0.6))
        elif t in {"living", "majlis"}:
            furniture.append(furniture_rect(room, "sofa", "Sofa", 0.45, 0.45, min(2.8, w - 0.9), 0.9))
            furniture.append(furniture_rect(room, "coffee-table", "Coffee Table", max(0.6, w / 2 - 0.6), min(d - 1.2, 1.8), 1.2, 0.7))
        elif t == "dining":
            tw, td = min(2.4, w - 1.2), min(1.2, d - 1.2)
            furniture.append(furniture_rect(room, "dining-table", "Dining Table", (w - tw) / 2, (d - td) / 2, tw, td))
        elif t == "kitchen":
            furniture.append(furniture_rect(room, "counter", "Kitchen Counter", 0.2, 0.2, max(1.0, w - 0.4), 0.6))
            furniture.append(furniture_rect(room, "island", "Kitchen Island", max(0.8, w / 2 - 0.75), max(1.2, d / 2 - 0.45), min(1.5, w - 1.6), 0.9))
            fixtures.append({"id": stable_id("fixture", room["id"], "sink"), "floor_id":room["floor_id"], "room_id":room["id"], "type":"sink", "geometry":{"x_m":x+w/2-0.3,"y_m":y+0.25,"width_m":0.6,"depth_m":0.5}})
        elif t in {"bathroom", "wc"}:
            fixtures.extend([
                {"id":stable_id("fixture",room["id"],"toilet"),"floor_id":room["floor_id"],"room_id":room["id"],"type":"toilet","geometry":{"x_m":x+0.25,"y_m":y+0.25,"width_m":0.7,"depth_m":1.1}},
                {"id":stable_id("fixture",room["id"],"basin"),"floor_id":room["floor_id"],"room_id":room["id"],"type":"basin","geometry":{"x_m":x+max(0.25,w-0.85),"y_m":y+0.25,"width_m":0.6,"depth_m":0.5}},
            ])
            if w >= 1.8 and d >= 2.4:
                fixtures.append({"id":stable_id("fixture",room["id"],"shower"),"floor_id":room["floor_id"],"room_id":room["id"],"type":"shower","geometry":{"x_m":x+max(0.2,w-1.1),"y_m":y+max(1.2,d-1.2),"width_m":0.9,"depth_m":0.9}})
        elif t == "laundry":
            furniture.append(furniture_rect(room, "washer", "Washer", 0.3, 0.3, 0.7, 0.7))
            furniture.append(furniture_rect(room, "dryer", "Dryer", 1.1, 0.3, 0.7, 0.7))
        elif t == "dressing":
            furniture.append(furniture_rect(room, "wardrobe", "Wardrobe", 0.2, 0.2, 0.55, max(0.8, d - 0.4)))
        elif t in {"storage", "pantry"}:
            furniture.append(furniture_rect(room, "shelving", "Storage Shelving", 0.2, max(0.2, d - 0.65), max(0.8, w - 0.4), 0.45))
        elif t == "garage":
            car_w, car_d = 2.4, min(4.8, d - 0.4)
            furniture.append(furniture_rect(room, "car", "Car 1", 0.2, 0.2, car_w, car_d))
            if w >= 5.2:
                furniture.append(furniture_rect(room, "car", "Car 2", 2.9, 0.2, car_w, car_d))
    optimize_object_layout(plan, furniture, fixtures)
    return round_coords(furniture), round_coords(fixtures)


def derive_adjacencies(plan: dict[str, Any]) -> list[dict[str, Any]]:
    adj = []
    for floor in plan["floors"]:
        rooms = rooms_by_floor(plan, floor["id"])
        for i, a in enumerate(rooms):
            for b in rooms[i + 1 :]:
                boundary = shared_boundary(a, b)
                if boundary:
                    adj.append({
                        "id": stable_id("adj", floor["id"], a["id"], b["id"]),
                        "floor_id": floor["id"], "room_a_id": a["id"], "room_b_id": b["id"],
                        "relationship": "direct-boundary",
                        "shared_length_m": round(boundary["end_m"] - boundary["start_m"], 3),
                        "has_door": any({d["from_room_id"], d["to_room_id"]} == {a["id"], b["id"]} for d in plan.get("doors", [])),
                    })
    return sorted(adj, key=lambda a: a["id"])


def derive_dimensions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    dims = []
    for floor in plan["floors"]:
        fx, fy, fw, fd = floor_bounds(plan, floor["id"])
        dims.extend([
            {"id":stable_id("dim",floor["id"],"overall-width"),"floor_id":floor["id"],"type":"overall","axis":"x","start_m":[fx,fy-1.0],"end_m":[fx+fw,fy-1.0],"value_m":fw,"label":f"{fw:.2f} m"},
            {"id":stable_id("dim",floor["id"],"overall-depth"),"floor_id":floor["id"],"type":"overall","axis":"y","start_m":[fx-1.0,fy],"end_m":[fx-1.0,fy+fd],"value_m":fd,"label":f"{fd:.2f} m"},
        ])
        for room in rooms_by_floor(plan, floor["id"]):
            x,y,w,d=bbox(room)
            dims.extend([
                {"id":stable_id("dim",room["id"],"w"),"floor_id":floor["id"],"room_id":room["id"],"type":"internal","axis":"x","start_m":[x,y+d/2],"end_m":[x+w,y+d/2],"value_m":w,"label":f"{w:.2f} m"},
                {"id":stable_id("dim",room["id"],"d"),"floor_id":floor["id"],"room_id":room["id"],"type":"internal","axis":"y","start_m":[x+w/2,y],"end_m":[x+w/2,y+d],"value_m":d,"label":f"{d:.2f} m"},
            ])
    return sorted(dims, key=lambda d: d["id"])


def vertical_elements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for room in plan["rooms"]:
        if room["type"] not in {"stair", "elevator", "shaft"}:
            continue
        item = {"id": stable_id("vertical", room["id"]), "floor_id": room["floor_id"], "room_id": room["id"], "type": room["type"], "geometry": room["geometry"]}
        if room["type"] == "stair":
            item.update({"riser_m":0.17,"tread_m":0.28,"step_count":20,"direction":"up"})
        items.append(item)
    return items
