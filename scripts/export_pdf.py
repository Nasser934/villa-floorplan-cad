#!/usr/bin/env python3
"""Create an A3 landscape PDF drawing set with title blocks and dimensions."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas

from common import bbox, floor_bounds, load_json, rooms_by_floor

PT_PER_M=72/0.0254
ZONE_GRAY={"guest":0.90,"family":0.94,"service":0.88,"shared":0.96}


def draw_floor(c:canvas.Canvas,plan:dict[str,Any],floor:dict[str,Any],validation:dict[str,Any]|None):
    page_w,page_h=landscape(A3); title_h=70; top_h=48; margin=36
    fx,fy,fw,fd=floor_bounds(plan,floor["id"])
    avail_w=page_w-2*margin; avail_h=page_h-title_h-top_h-2*margin
    scale=min(avail_w/fw,avail_h/fd)
    ox=margin+(avail_w-fw*scale)/2; oy=title_h+margin+(avail_h-fd*scale)/2
    def pt(x,y): return ox+(x-fx)*scale,oy+(y-fy)*scale
    c.setTitle(f"{plan.get('project',{}).get('name','Villa')} - {floor['name']}")
    for room in rooms_by_floor(plan,floor["id"]):
        x,y,w,d=bbox(room); px,py=pt(x,y)
        if room.get("is_exterior"):
            c.setDash(4,3); c.setFillColorRGB(1,1,1)
        else:
            g=ZONE_GRAY.get(room.get("zone"),0.95); c.setDash(); c.setFillColorRGB(g,g,g)
        c.setStrokeColorRGB(.65,.67,.7); c.rect(px,py,w*scale,d*scale,fill=1,stroke=1); c.setDash()
    for wall in plan["walls"]:
        if wall["floor_id"]!=floor["id"]: continue
        c.setStrokeColorRGB(.08,.09,.1); c.setLineWidth(max(1.5,wall["thickness_m"]*scale)); c.line(*pt(*wall["start_m"]),*pt(*wall["end_m"]))
    for win in plan["windows"]:
        if win["floor_id"]!=floor["id"]: continue
        co,pos,half=win["wall"]["coordinate_m"],win["position_m"],win["width_m"]/2
        a,b=((co,pos-half),(co,pos+half)) if win["wall"]["orientation"]=="vertical" else ((pos-half,co),(pos+half,co))
        c.setStrokeColorRGB(.05,.45,.65); c.setLineWidth(4); c.line(*pt(*a),*pt(*b))
    for door in plan["doors"]:
        if door["floor_id"]!=floor["id"]: continue
        hx,hy=door["hinge_m"]; w=door["width_m"]; px,py=pt(hx,hy); r=w*scale
        c.setStrokeColorRGB(.4,.25,.12); c.setLineWidth(1)
        leaf=door.get("closed_leaf_end_m")
        if leaf:
            lx,ly=pt(*leaf); c.line(px,py,lx,ly)
        else:
            c.line(px,py,px+r,py)
        opened=door.get("open_leaf_end_m")
        if door.get("type")=="single-leaf" and leaf and opened:
            start_ang=math.degrees(math.atan2(leaf[1]-hy,leaf[0]-hx))
            end_ang=math.degrees(math.atan2(opened[1]-hy,opened[0]-hx))
            extent=(end_ang-start_ang+180)%360-180
            c.arc(px-r,py-r,px+r,py+r,startAng=start_ang,extent=extent)
    for item in [*plan.get("furniture",[]),*plan.get("fixtures",[])]:
        if item["floor_id"]!=floor["id"]: continue
        g=item["geometry"]; px,py=pt(g["x_m"],g["y_m"]); c.setStrokeColorRGB(.35,.38,.42); c.setLineWidth(.5); c.rect(px,py,g["width_m"]*scale,g["depth_m"]*scale,fill=0,stroke=1)
    c.setFillColorRGB(.05,.06,.07)
    for room in rooms_by_floor(plan,floor["id"]):
        x,y,w,d=bbox(room); cx,cy=pt(x+w/2,y+d/2)
        c.setFont("Helvetica-Bold",7); c.drawCentredString(cx,cy+3,room["name"][:32]); c.setFont("Helvetica",6.5); c.drawCentredString(cx,cy-6,f"{room['area_m2']:.2f} m2")
        c.setFont("Helvetica",5.5); c.drawCentredString(cx,cy-14,f"{w:.2f} x {d:.2f} m")
    c.setStrokeColorRGB(.15,.15,.15); c.setFillColorRGB(.1,.1,.1); c.setLineWidth(.5)
    ydim=oy-18; c.line(ox,ydim,ox+fw*scale,ydim); c.line(ox,ydim-4,ox,ydim+4); c.line(ox+fw*scale,ydim-4,ox+fw*scale,ydim+4); c.setFont("Helvetica",7); c.drawCentredString(ox+fw*scale/2,ydim-12,f"{fw:.2f} m")
    xdim=ox-18; c.line(xdim,oy,xdim,oy+fd*scale); c.line(xdim-4,oy,xdim+4,oy); c.line(xdim-4,oy+fd*scale,xdim+4,oy+fd*scale); c.saveState(); c.translate(xdim-10,oy+fd*scale/2); c.rotate(90); c.drawCentredString(0,0,f"{fd:.2f} m"); c.restoreState()
    if validation:
        n=0
        for it in validation.get("issues",[]):
            if it.get("floor_id")!=floor["id"] or not it.get("location_m"): continue
            n+=1; x,y=pt(*it["location_m"]); c.setFillColorRGB(.75,.05,.05); c.circle(x,y,6,fill=1,stroke=0); c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold",6); c.drawCentredString(x,y-2,str(n))
    c.setStrokeColorRGB(0,0,0); c.setFillColorRGB(0,0,0); nx,ny=page_w-60,page_h-65; c.setLineWidth(2); c.line(nx,ny-20,nx,ny+15); c.line(nx,ny+15,nx-5,ny+5); c.line(nx,ny+15,nx+5,ny+5); c.setFont("Helvetica-Bold",9); c.drawCentredString(nx,ny+21,"N")
    sx,sy=margin,page_h-27; bar=min(5*scale,220); c.setLineWidth(4); c.line(sx,sy,sx+bar,sy); c.setLineWidth(.5)
    for i in range(6): x=sx+bar*i/5; c.line(x,sy-4,x,sy+4)
    c.setFont("Helvetica",6); c.drawString(sx,sy-12,"0     1     2     3     4     5 m")
    c.drawCentredString(page_w/2,page_h-30,"Legend: walls | windows | doors | furniture | issue marker")
    c.setStrokeColorRGB(0,0,0); c.setFillColorRGB(1,1,1); c.rect(0,0,page_w,title_h,fill=1,stroke=1); c.line(page_w-300,0,page_w-300,title_h); c.line(page_w-150,0,page_w-150,title_h)
    c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold",13); c.drawString(18,43,plan.get("project",{}).get("name","Residential Villa")); c.setFont("Helvetica",8); c.drawString(18,27,f"Floor: {floor['name']} | Units: metric | Level: {floor['level_m']:.2f} m")
    c.drawString(18,13,"Concept/design validation drawing - verify against current local authority, structural, fire, accessibility, energy, and MEP requirements before construction.")
    p=plan.get("project",{}); c.setFont("Helvetica-Bold",8); c.drawString(page_w-288,47,"Drawing"); c.setFont("Helvetica",8); c.drawString(page_w-288,32,p.get("drawing_number","VFC-001")); c.drawString(page_w-288,17,f"Rev {p.get('revision','A')}")
    c.setFont("Helvetica-Bold",8); c.drawString(page_w-138,47,"Scale"); c.setFont("Helvetica",8); c.drawString(page_w-138,32,f"1:{round(PT_PER_M/scale)}"); c.drawString(page_w-138,17,"A3 landscape")


def export_pdf(plan_path:Path,output:Path,validation_path:Path|None=None)->Path:
    plan=load_json(plan_path); validation=load_json(validation_path) if validation_path and validation_path.exists() else None
    output.parent.mkdir(parents=True,exist_ok=True); c=canvas.Canvas(str(output),pagesize=landscape(A3),pageCompression=1,invariant=1)
    for floor in plan["floors"]: draw_floor(c,plan,floor,validation); c.showPage()
    c.save(); return output


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("plan"); p.add_argument("--output",default=None); p.add_argument("--validation",default=None)
    a=p.parse_args(); path=Path(a.plan).expanduser().resolve(); out=Path(a.output).expanduser().resolve() if a.output else path.parent/"villa-drawing-set.pdf"; print(export_pdf(path,out,Path(a.validation).resolve() if a.validation else None))
if __name__=="__main__": main()
