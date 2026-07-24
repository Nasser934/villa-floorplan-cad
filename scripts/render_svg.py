#!/usr/bin/env python3
"""Render one editable layered SVG and one PNG preview per floor."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import svgwrite
from svgwrite.base import Desc, Title
from PIL import Image, ImageDraw, ImageFont

from common import bbox, floor_bounds, load_json, rooms_by_floor

ZONE_COLORS={"guest":"#f5e6cc","family":"#e4f1eb","service":"#e7e9ef","shared":"#f2f2f2"}
WALL_COLOR="#20252b"; WINDOW_COLOR="#1976a3"; FURNITURE_COLOR="#6f7782"; ISSUE_COLOR="#c62828"


def transform(bounds: tuple[float,float,float,float], scale: float, margin: float):
    fx,fy,fw,fd=bounds
    def pt(x:float,y:float)->tuple[float,float]: return margin+(x-fx)*scale, margin+(fy+fd-y)*scale
    return pt


def door_path(door:dict[str,Any],pt,scale:float)->str:
    hx,hy=door["hinge_m"]; x1,y1=pt(hx,hy)
    closed=door.get("closed_leaf_end_m"); opened=door.get("open_leaf_end_m")
    if not closed:
        return ""
    cx,cy=pt(*closed)
    if not opened:
        return f"M {x1:.2f},{y1:.2f} L {cx:.2f},{cy:.2f}"
    ox,oy=pt(*opened)
    sweep=0 if door["swing"].get("direction")=="counterclockwise" else 1
    return f"M {x1:.2f},{y1:.2f} L {cx:.2f},{cy:.2f} M {cx:.2f},{cy:.2f} A {door['width_m']*scale:.2f},{door['width_m']*scale:.2f} 0 0 {sweep} {ox:.2f},{oy:.2f}"


def render_floor_svg(plan:dict[str,Any],floor:dict[str,Any],out:Path,validation:dict[str,Any]|None,scale:float=60.0)->Path:
    bounds=floor_bounds(plan,floor["id"]); fx,fy,fw,fd=bounds; margin=110
    width=fw*scale+2*margin; height=fd*scale+2*margin+100; pt=transform(bounds,scale,margin)
    dwg=svgwrite.Drawing(str(out),size=(f"{width}px",f"{height}px"),viewBox=f"0 0 {width} {height}")
    dwg.add(Desc(f"Editable metric floor plan; units=m; floor_id={floor['id']}"))
    dwg.add(dwg.rect(insert=(0,0),size=(width,height),fill="white"))
    rooms_g=dwg.g(id="rooms",class_="editable-layer rooms")
    for room in rooms_by_floor(plan,floor["id"]):
        x,y,w,d=bbox(room); sx,sy=pt(x,y+d)
        fill="none" if room.get("is_exterior") else ZONE_COLORS.get(room.get("zone"),"#f8f8f8")
        attrs={"insert":(sx,sy),"size":(w*scale,d*scale),"fill":fill,"stroke":"#aab0b7","stroke_width":0.8,"id":f"room-{room['id']}","class_":f"room zone-{room.get('zone','shared')}"}
        if room.get("is_exterior"): attrs["stroke_dasharray"]="6,4"
        rooms_g.add(dwg.rect(**attrs))
    dwg.add(rooms_g)
    walls_g=dwg.g(id="walls",class_="editable-layer walls")
    for wall in plan["walls"]:
        if wall["floor_id"]!=floor["id"]: continue
        x1,y1=pt(*wall["start_m"]); x2,y2=pt(*wall["end_m"])
        walls_g.add(dwg.line((x1,y1),(x2,y2),stroke=WALL_COLOR,stroke_width=max(2,wall["thickness_m"]*scale),stroke_linecap="square",id=wall["id"],class_=f"wall {wall['type']}"))
    dwg.add(walls_g)
    windows_g=dwg.g(id="windows",class_="editable-layer windows")
    for win in plan["windows"]:
        if win["floor_id"]!=floor["id"]: continue
        c=win["wall"]["coordinate_m"]; pos=win["position_m"]; half=win["width_m"]/2
        if win["wall"]["orientation"]=="vertical": a,b=pt(c,pos-half),pt(c,pos+half)
        else: a,b=pt(pos-half,c),pt(pos+half,c)
        windows_g.add(dwg.line(a,b,stroke=WINDOW_COLOR,stroke_width=5,id=win["id"],class_="window"))
        windows_g.add(dwg.line(a,b,stroke="white",stroke_width=1.2))
    dwg.add(windows_g)
    doors_g=dwg.g(id="doors",class_="editable-layer doors")
    for door in plan["doors"]:
        if door["floor_id"]!=floor["id"]: continue
        doors_g.add(dwg.path(d=door_path(door,pt,scale),fill="none",stroke="#7b4f2b",stroke_width=1.8,id=door["id"],class_="door-swing"))
    dwg.add(doors_g)
    furn_g=dwg.g(id="furniture",class_="editable-layer furniture")
    for item in [*plan.get("furniture",[]),*plan.get("fixtures",[])]:
        if item["floor_id"]!=floor["id"]: continue
        g=item["geometry"]; sx,sy=pt(g["x_m"],g["y_m"]+g["depth_m"])
        furn_g.add(dwg.rect(insert=(sx,sy),size=(g["width_m"]*scale,g["depth_m"]*scale),fill="none",stroke=FURNITURE_COLOR,stroke_width=1,id=item["id"],class_=f"object {item['type']}"))
    dwg.add(furn_g)
    labels=dwg.g(id="room-labels",class_="editable-layer labels")
    for room in rooms_by_floor(plan,floor["id"]):
        x,y,w,d=bbox(room); cx,cy=pt(x+w/2,y+d/2)
        labels.add(dwg.text(room["name"],insert=(cx,cy-5),text_anchor="middle",font_size=12,font_family="Arial, sans-serif",font_weight="bold",fill="#1b1f23",id=f"label-{room['id']}"))
        labels.add(dwg.text(f"{room['area_m2']:.2f} m²",insert=(cx,cy+11),text_anchor="middle",font_size=10,font_family="Arial, sans-serif",fill="#40464d"))
    dwg.add(labels)
    dims=dwg.g(id="dimensions",class_="editable-layer dimensions")
    for dim in plan["dimensions"]:
        if dim["floor_id"]!=floor["id"] or dim["type"]!="overall": continue
        a=pt(*dim["start_m"]); b=pt(*dim["end_m"]); dims.add(dwg.line(a,b,stroke="#333",stroke_width=1))
        mx,my=(a[0]+b[0])/2,(a[1]+b[1])/2; dims.add(dwg.text(dim["label"],insert=(mx,my-5),text_anchor="middle",font_size=11,font_family="Arial"))
    dwg.add(dims)
    if validation:
        issues=dwg.g(id="issue-markers",class_="editable-layer issues")
        idx=0
        for it in validation.get("issues",[]):
            if it.get("floor_id")!=floor["id"] or not it.get("location_m"): continue
            idx+=1; cx,cy=pt(*it["location_m"])
            marker=dwg.circle(center=(cx,cy),r=10,fill=ISSUE_COLOR,stroke="white",stroke_width=2,id=f"issue-{idx}",class_=f"issue {it['severity']}")
            marker.add(Title(f"{it['code']}: {it['message']}"))
            issues.add(marker)
            issues.add(dwg.text(str(idx),insert=(cx,cy+4),text_anchor="middle",font_size=10,font_weight="bold",fill="white"))
        dwg.add(issues)
    nx,ny=width-75,55
    dwg.add(dwg.line((nx,ny+35),(nx,ny-15),stroke="#111",stroke_width=3)); dwg.add(dwg.polygon(points=[(nx,ny-22),(nx-7,ny-8),(nx+7,ny-8)],fill="#111")); dwg.add(dwg.text("N",insert=(nx,ny+53),text_anchor="middle",font_size=14,font_weight="bold"))
    bar_y=height-60; bar_x=margin
    dwg.add(dwg.line((bar_x,bar_y),(bar_x+5*scale,bar_y),stroke="#111",stroke_width=5));
    for i in range(6): dwg.add(dwg.line((bar_x+i*scale,bar_y-6),(bar_x+i*scale,bar_y+6),stroke="#111",stroke_width=1))
    dwg.add(dwg.text("0   1   2   3   4   5 m",insert=(bar_x,bar_y+22),font_size=10,font_family="Arial"))
    dwg.add(dwg.text(f"{plan['project'].get('name','Villa')} — {floor['name']}",insert=(margin,35),font_size=18,font_family="Arial",font_weight="bold"))
    out.parent.mkdir(parents=True,exist_ok=True); dwg.save(pretty=True); return out


def render_floor_png(plan:dict[str,Any],floor:dict[str,Any],out:Path,validation:dict[str,Any]|None,scale:float=60.0)->Path:
    bounds=floor_bounds(plan,floor["id"]); fx,fy,fw,fd=bounds; margin=90; width=int(fw*scale+2*margin); height=int(fd*scale+2*margin)
    img=Image.new("RGB",(width,height),"white"); draw=ImageDraw.Draw(img); pt=transform(bounds,scale,margin)
    try: font=ImageFont.truetype("DejaVuSans.ttf",12); bold=ImageFont.truetype("DejaVuSans-Bold.ttf",12)
    except OSError: font=bold=ImageFont.load_default()
    for room in rooms_by_floor(plan,floor["id"]):
        x,y,w,d=bbox(room); a=pt(x,y+d); b=pt(x+w,y); fill="white" if room.get("is_exterior") else ZONE_COLORS.get(room.get("zone"),"#f8f8f8")
        draw.rectangle([a,b],fill=fill,outline="#aab0b7",width=1)
    for wall in plan["walls"]:
        if wall["floor_id"]!=floor["id"]: continue
        draw.line([pt(*wall["start_m"]),pt(*wall["end_m"])],fill=WALL_COLOR,width=max(2,int(wall["thickness_m"]*scale)))
    for win in plan["windows"]:
        if win["floor_id"]!=floor["id"]: continue
        c,pos,half=win["wall"]["coordinate_m"],win["position_m"],win["width_m"]/2
        a,b=(pt(c,pos-half),pt(c,pos+half)) if win["wall"]["orientation"]=="vertical" else (pt(pos-half,c),pt(pos+half,c)); draw.line([a,b],fill=WINDOW_COLOR,width=5)
    for item in [*plan.get("furniture",[]),*plan.get("fixtures",[])]:
        if item["floor_id"]!=floor["id"]: continue
        g=item["geometry"]; draw.rectangle([pt(g["x_m"],g["y_m"]+g["depth_m"]),pt(g["x_m"]+g["width_m"],g["y_m"])],outline=FURNITURE_COLOR,width=1)
    for room in rooms_by_floor(plan,floor["id"]):
        x,y,w,d=bbox(room); cx,cy=pt(x+w/2,y+d/2); text=f"{room['name']}\n{room['area_m2']:.1f} m²"
        bb=draw.multiline_textbbox((0,0),text,font=font,align="center"); draw.multiline_text((cx-(bb[2]-bb[0])/2,cy-(bb[3]-bb[1])/2),text,font=font,fill="#1b1f23",align="center")
    if validation:
        idx=0
        for it in validation.get("issues",[]):
            if it.get("floor_id")!=floor["id"] or not it.get("location_m"): continue
            idx+=1; cx,cy=pt(*it["location_m"]); draw.ellipse([cx-10,cy-10,cx+10,cy+10],fill=ISSUE_COLOR,outline="white",width=2); draw.text((cx-3,cy-6),str(idx),font=bold,fill="white")
    draw.text((margin,20),f"{plan['project'].get('name','Villa')} — {floor['name']}",font=bold,fill="#111")
    out.parent.mkdir(parents=True,exist_ok=True); img.save(out,optimize=True); return out


def main()->None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("plan"); p.add_argument("--output-dir",default=None); p.add_argument("--validation",default=None); p.add_argument("--scale",type=float,default=60.0); p.add_argument("--no-png",action="store_true")
    a=p.parse_args(); plan_path=Path(a.plan).expanduser().resolve(); plan=load_json(plan_path); validation=load_json(a.validation) if a.validation else None; out_dir=Path(a.output_dir).expanduser().resolve() if a.output_dir else plan_path.parent
    for floor in plan["floors"]:
        svg=render_floor_svg(plan,floor,out_dir/f"{floor['id']}.svg",validation,a.scale); print(svg)
        if not a.no_png: print(render_floor_png(plan,floor,out_dir/f"{floor['id']}.png",validation,a.scale))
if __name__=="__main__": main()
