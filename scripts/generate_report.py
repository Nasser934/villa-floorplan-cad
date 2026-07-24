#!/usr/bin/env python3
"""Run the full villa CAD pipeline and create a local HTML viewer plus manifest."""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

from common import dump_json, load_json, resolve_project_paths
from export_dxf import export_floor as export_dxf_floor
from export_ifc import export_ifc
from export_openscad import generate_scad
from export_pdf import export_pdf
from generate_plan import build_plan
from render_svg import render_floor_png, render_floor_svg
from validate_plan import validate


def module_available(name:str)->bool: return importlib.util.find_spec(name) is not None

HTML_TEMPLATE=r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Villa Floorplan CAD Viewer</title>
<style>
:root{font-family:Inter,Arial,sans-serif;color:#1d232a;background:#f3f5f7}body{margin:0}.top{display:flex;gap:12px;align-items:center;padding:12px 16px;background:#17212b;color:white;position:sticky;top:0;z-index:5}.top h1{font-size:16px;margin:0;margin-right:auto}select,button{padding:8px 10px;border:1px solid #c7ccd2;border-radius:6px;background:white}.tabs button.active{background:#245d83;color:white}.grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:12px;padding:12px}.panel{background:white;border:1px solid #d8dde3;border-radius:8px;overflow:hidden}.view{display:none;padding:10px}.view.active{display:block}canvas{width:100%;height:auto;border:1px solid #e0e4e8;background:white}.side{padding:14px}.side h2{font-size:14px;margin:8px 0}.room-info,.issue{font-size:12px;line-height:1.45}.issue{border-left:4px solid #c62828;padding:8px;margin:7px 0;background:#fff5f5}.issue.warning{border-color:#ef8c00;background:#fff8ed}.artifacts a{display:block;margin:6px 0;color:#245d83}.compare{display:grid;grid-template-columns:1fr 1fr;gap:8px}.badge{display:inline-block;padding:2px 6px;border-radius:10px;background:#e8edf2;font-size:11px}@media(max-width:900px){.grid{grid-template-columns:1fr}.compare{grid-template-columns:1fr}}
</style></head><body>
<div class="top"><h1 id="title"></h1><label>Floor <select id="floor"></select></label><div class="tabs"><button data-tab="v2d" class="active">2D</button><button data-tab="v3d">3D</button><button data-tab="compare">Before / After</button></div></div>
<div class="grid"><div class="panel"><div id="v2d" class="view active"><canvas id="c2d" width="1200" height="850"></canvas></div><div id="v3d" class="view"><canvas id="c3d" width="1200" height="850"></canvas></div><div id="compare" class="view"><div class="compare"><div><h3>Before</h3><canvas id="cbefore" width="570" height="620"></canvas></div><div><h3>After</h3><canvas id="cafter" width="570" height="620"></canvas></div></div></div></div>
<aside class="panel side"><h2>Room information</h2><div id="roomInfo" class="room-info">Click a room in the 2D view.</div><h2>Issues <span id="issueCount" class="badge"></span></h2><div id="issues"></div><h2>Artifacts</h2><div class="artifacts" id="artifacts"></div></aside></div>
<script>
const PLAN=__PLAN__; const BEFORE=__BEFORE__; const VALIDATION=__VALIDATION__; const ARTIFACTS=__ARTIFACTS__;
const zones={guest:'#f5e6cc',family:'#e4f1eb',service:'#e7e9ef',shared:'#f2f2f2'}; let floorId=PLAN.floors[0].id; let hit=[];
function floorData(data,id){return {floor:data.floors.find(f=>f.id===id),rooms:data.rooms.filter(r=>r.floor_id===id),walls:data.walls.filter(w=>w.floor_id===id),doors:data.doors.filter(d=>d.floor_id===id),windows:data.windows.filter(w=>w.floor_id===id),furniture:[...(data.furniture||[]),...(data.fixtures||[])].filter(x=>x.floor_id===id)}}
function mapper(canvas,f){const m=45,fw=f.footprint.width_m,fd=f.footprint.depth_m,s=Math.min((canvas.width-2*m)/fw,(canvas.height-2*m)/fd);return {s,m,p:(x,y)=>[m+(x-(f.footprint.x_m||0))*s,canvas.height-m-(y-(f.footprint.y_m||0))*s]}}
function draw2d(canvas,data,id,interactive=false){const ctx=canvas.getContext('2d'),d=floorData(data,id),M=mapper(canvas,d.floor);ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);if(interactive)hit=[];
 d.rooms.forEach(r=>{const g=r.geometry,a=M.p(g.x_m,g.y_m+g.depth_m),b=M.p(g.x_m+g.width_m,g.y_m);ctx.fillStyle=r.is_exterior?'#fff':(zones[r.zone]||'#f7f7f7');ctx.fillRect(a[0],a[1],b[0]-a[0],b[1]-a[1]);ctx.strokeStyle='#aab0b7';ctx.strokeRect(a[0],a[1],b[0]-a[0],b[1]-a[1]);ctx.fillStyle='#20252b';ctx.font='12px Arial';ctx.textAlign='center';ctx.fillText(r.name,(a[0]+b[0])/2,(a[1]+b[1])/2);ctx.font='10px Arial';ctx.fillText(r.area_m2.toFixed(2)+' m²',(a[0]+b[0])/2,(a[1]+b[1])/2+14);if(interactive)hit.push({r,x:a[0],y:a[1],w:b[0]-a[0],h:b[1]-a[1]})});
 d.walls.forEach(w=>{const a=M.p(...w.start_m),b=M.p(...w.end_m);ctx.strokeStyle='#20252b';ctx.lineWidth=Math.max(2,w.thickness_m*M.s);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke()});
 d.windows.forEach(w=>{const c=w.wall.coordinate_m,p=w.position_m,h=w.width_m/2;const a=w.wall.orientation==='vertical'?M.p(c,p-h):M.p(p-h,c),b=w.wall.orientation==='vertical'?M.p(c,p+h):M.p(p+h,c);ctx.strokeStyle='#1976a3';ctx.lineWidth=5;ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke()});
 d.furniture.forEach(i=>{const g=i.geometry,a=M.p(g.x_m,g.y_m+g.depth_m),b=M.p(g.x_m+g.width_m,g.y_m);ctx.strokeStyle='#6f7782';ctx.lineWidth=1;ctx.strokeRect(a[0],a[1],b[0]-a[0],b[1]-a[1])});
 (VALIDATION.issues||[]).filter(i=>i.floor_id===id&&i.location_m).forEach((i,n)=>{const p=M.p(...i.location_m);ctx.fillStyle=i.severity==='error'?'#c62828':'#ef8c00';ctx.beginPath();ctx.arc(p[0],p[1],10,0,Math.PI*2);ctx.fill();ctx.fillStyle='white';ctx.font='bold 10px Arial';ctx.fillText(String(n+1),p[0],p[1]+3)});
 ctx.fillStyle='#111';ctx.font='bold 16px Arial';ctx.textAlign='left';ctx.fillText(d.floor.name,20,24)}
function iso(x,y,z){return [600+(x-y)*28,650-(x+y)*14-z*50]}
function draw3d(){const c=document.getElementById('c3d'),ctx=c.getContext('2d'),d=floorData(PLAN,floorId);ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='white';ctx.fillRect(0,0,c.width,c.height);const z=d.floor.level_m;d.rooms.filter(r=>!r.is_exterior).forEach(r=>{const g=r.geometry,p=[iso(g.x_m,g.y_m,z),iso(g.x_m+g.width_m,g.y_m,z),iso(g.x_m+g.width_m,g.y_m+g.depth_m,z),iso(g.x_m,g.y_m+g.depth_m,z)];ctx.fillStyle=zones[r.zone]||'#eee';ctx.strokeStyle='#777';ctx.beginPath();ctx.moveTo(...p[0]);p.slice(1).forEach(q=>ctx.lineTo(...q));ctx.closePath();ctx.fill();ctx.stroke()});d.walls.forEach(w=>{const a=iso(w.start_m[0],w.start_m[1],z),b=iso(w.end_m[0],w.end_m[1],z),a2=iso(w.start_m[0],w.start_m[1],z+d.floor.clear_height_m),b2=iso(w.end_m[0],w.end_m[1],z+d.floor.clear_height_m);ctx.fillStyle=w.type==='external'?'#a9afb5':'#c5c9cd';ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.lineTo(...b2);ctx.lineTo(...a2);ctx.closePath();ctx.fill();ctx.strokeStyle='#777';ctx.stroke()})}
function updateIssues(){const el=document.getElementById('issues'),items=(VALIDATION.issues||[]).filter(i=>!i.floor_id||i.floor_id===floorId);document.getElementById('issueCount').textContent=items.length;el.innerHTML=items.map((i,n)=>`<div class="issue ${i.severity}"><b>${n+1}. ${i.code}</b><br>${i.message}${i.suggestion?'<br><em>'+i.suggestion+'</em>':''}</div>`).join('')||'<p>No issues on this floor.</p>'}
function render(){draw2d(document.getElementById('c2d'),PLAN,floorId,true);draw3d();draw2d(document.getElementById('cafter'),PLAN,floorId);draw2d(document.getElementById('cbefore'),BEFORE||PLAN,floorId);updateIssues()}
document.getElementById('title').textContent=PLAN.project.name||'Villa Floorplan CAD';PLAN.floors.forEach(f=>{const o=document.createElement('option');o.value=f.id;o.textContent=f.name;document.getElementById('floor').appendChild(o)});document.getElementById('floor').onchange=e=>{floorId=e.target.value;render()};document.getElementById('c2d').onclick=e=>{const r=e.target.getBoundingClientRect(),x=(e.clientX-r.left)*e.target.width/r.width,y=(e.clientY-r.top)*e.target.height/r.height,h=hit.find(h=>x>=h.x&&x<=h.x+h.w&&y>=h.y&&y<=h.y+h.h);if(h)document.getElementById('roomInfo').innerHTML=`<b>${h.r.name}</b><br>Type: ${h.r.type}<br>Zone: ${h.r.zone}<br>Area: ${h.r.area_m2.toFixed(2)} m²<br>Clear size: ${h.r.geometry.width_m.toFixed(2)} x ${h.r.geometry.depth_m.toFixed(2)} m`};
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active');if(b.dataset.tab==='v3d')draw3d()});document.getElementById('artifacts').innerHTML=ARTIFACTS.map(a=>`<a href="${a.href}">${a.label}</a>`).join('');render();
</script></body></html>'''


def create_viewer(plan:dict[str,Any],validation:dict[str,Any],viewer_dir:Path,artifacts:list[dict[str,str]],before:dict[str,Any]|None=None)->Path:
    viewer_dir.mkdir(parents=True,exist_ok=True)
    page=HTML_TEMPLATE.replace("__PLAN__",json.dumps(plan,separators=(",",":"),ensure_ascii=False)).replace("__BEFORE__",json.dumps(before,separators=(",",":"),ensure_ascii=False) if before else "null").replace("__VALIDATION__",json.dumps(validation,separators=(",",":"),ensure_ascii=False)).replace("__ARTIFACTS__",json.dumps(artifacts,separators=(",",":"),ensure_ascii=False))
    out=viewer_dir/"index.html"; out.write_text(page,encoding="utf-8"); return out


def run(project:Path,before_path:Path|None=None,with_ifc:bool=False)->dict[str,Any]:
    root,program_path,output=resolve_project_paths(project); output.mkdir(parents=True,exist_ok=True); viewer=root/"viewer"
    program=load_json(program_path); plan=build_plan(program); plan_path=dump_json(plan,output/"plan.json")
    validation=validate(plan); validation_path=dump_json(validation,output/"validation.json")
    manifest=[]
    for floor in plan["floors"]:
        svg=render_floor_svg(plan,floor,output/f"{floor['id']}.svg",validation); png=render_floor_png(plan,floor,output/f"{floor['id']}.png",validation); manifest += [{"label":f"{floor['name']} SVG","path":str(svg)},{"label":f"{floor['name']} PNG","path":str(png)}]
    pdf=export_pdf(plan_path,output/"villa-drawing-set.pdf",validation_path); manifest.append({"label":"PDF drawing set","path":str(pdf)})
    scad=output/"villa-model.scad"; scad.write_text(generate_scad(plan),encoding="utf-8"); manifest.append({"label":"OpenSCAD 3D model","path":str(scad)})
    if module_available("ezdxf"):
        for floor in plan["floors"]:
            dxf=export_dxf_floor(plan,floor,output/f"{floor['id']}.dxf"); manifest.append({"label":f"{floor['name']} DXF","path":str(dxf)})
        dxf_status="generated"
    else: dxf_status="skipped: install ezdxf"
    if with_ifc:
        if module_available("ifcopenshell"):
            ifc=export_ifc(plan_path,output/"villa-model.ifc"); manifest.append({"label":"IFC4 model","path":str(ifc)}); ifc_status="generated"
        else: ifc_status="skipped: install ifcopenshell"
    else: ifc_status="not requested"
    before=load_json(before_path) if before_path else None
    links=[{"label":m["label"],"href":"../output/"+Path(m["path"]).name} for m in manifest]
    viewer_path=create_viewer(plan,validation,viewer,links,before); manifest.append({"label":"Local HTML viewer","path":str(viewer_path)})
    report={"schema_version":"villa-floorplan-cad.manifest.v1","project_root":str(root),"plan":str(plan_path),"validation":validation,"dxf_status":dxf_status,"ifc_status":ifc_status,"artifacts":manifest}
    dump_json(report,output/"artifact-manifest.json"); return report


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("project",help="Project folder or program.json"); p.add_argument("--before",default=None); p.add_argument("--ifc",action="store_true")
    a=p.parse_args(); report=run(Path(a.project).expanduser().resolve(),Path(a.before).expanduser().resolve() if a.before else None,a.ifc); print(json.dumps({"plan":report["plan"],"issues":report["validation"]["summary"],"dxf":report["dxf_status"],"ifc":report["ifc_status"]},indent=2))
if __name__=="__main__": main()
