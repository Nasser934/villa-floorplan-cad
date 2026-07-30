#!/usr/bin/env python3
"""Build all villa deliverables, a local viewer, and an optional safe share bundle."""
from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from common import dump_json, load_json, resolve_project_layout, slug
from export_dxf import export_floor as export_dxf_floor
from export_ifc import export_ifc
from export_openscad import generate_scad
from export_pdf import export_pdf
from generate_plan import build_plan
from render_svg import render_floor_png, render_floor_svg
from validate_plan import validate


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def json_for_script(value: Any) -> str:
    """Serialize JSON safely for an inline script element."""
    return (
        json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


HTML_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Villa Floorplan CAD Viewer</title>
<style>
:root{font-family:Inter,Arial,sans-serif;color:#1d232a;background:#f3f5f7}body{margin:0}.top{display:flex;gap:12px;align-items:center;padding:12px 16px;background:#17212b;color:white;position:sticky;top:0;z-index:5}.top h1{font-size:16px;margin:0;margin-right:auto}select,button{padding:8px 10px;border:1px solid #c7ccd2;border-radius:6px;background:white}.tabs button.active{background:#245d83;color:white}.grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:12px;padding:12px}.panel{background:white;border:1px solid #d8dde3;border-radius:8px;overflow:hidden}.view{display:none;padding:10px}.view.active{display:block}canvas{width:100%;height:auto;border:1px solid #e0e4e8;background:white}.side{padding:14px}.side h2{font-size:14px;margin:8px 0}.room-info,.issue{font-size:12px;line-height:1.45}.issue{border-left:4px solid #c62828;padding:8px;margin:7px 0;background:#fff5f5}.issue.warning{border-color:#ef8c00;background:#fff8ed}.artifacts a{display:block;margin:6px 0;color:#245d83}.compare{display:grid;grid-template-columns:1fr 1fr;gap:8px}.badge{display:inline-block;padding:2px 6px;border-radius:10px;background:#e8edf2;font-size:11px}.status{font-size:12px;padding:5px 9px;border-radius:14px;background:#dff5e5;color:#164d27}.status.has-errors{background:#ffe2e2;color:#7b1717}@media(max-width:900px){.grid{grid-template-columns:1fr}.top{flex-wrap:wrap}.compare{grid-template-columns:1fr}}
</style></head><body>
<div class="top"><h1 id="title"></h1><span id="status" class="status"></span><label>Floor <select id="floor"></select></label><div class="tabs"><button data-tab="v2d" class="active">2D</button><button data-tab="v3d">3D</button><button data-tab="compare">Before / After</button></div></div>
<div class="grid"><div class="panel"><div id="v2d" class="view active"><canvas id="c2d" width="1200" height="850"></canvas></div><div id="v3d" class="view"><canvas id="c3d" width="1200" height="850"></canvas></div><div id="compare" class="view"><div class="compare"><div><h3>Before</h3><canvas id="cbefore" width="570" height="620"></canvas></div><div><h3>After</h3><canvas id="cafter" width="570" height="620"></canvas></div></div></div></div>
<aside class="panel side"><h2>Room information</h2><div id="roomInfo" class="room-info">Click a room in the 2D view.</div><h2>Issues <span id="issueCount" class="badge"></span></h2><div id="issues"></div><h2>Downloads</h2><div class="artifacts" id="artifacts"></div></aside></div>
<script>
const PLAN=__PLAN__; const BEFORE=__BEFORE__; const VALIDATION=__VALIDATION__; const ARTIFACTS=__ARTIFACTS__;
const zones={guest:'#f5e6cc',family:'#e4f1eb',service:'#e7e9ef',shared:'#f2f2f2'}; let floorId=PLAN.floors[0].id; let hit=[];
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
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
function updateIssues(){const el=document.getElementById('issues'),items=(VALIDATION.issues||[]).filter(i=>!i.floor_id||i.floor_id===floorId);document.getElementById('issueCount').textContent=items.length;el.innerHTML=items.map((i,n)=>`<div class="issue ${i.severity==='error'?'error':'warning'}"><b>${n+1}. ${esc(i.code)}</b><br>${esc(i.message)}${i.suggestion?'<br><em>'+esc(i.suggestion)+'</em>':''}</div>`).join('')||'<p>No issues on this floor.</p>'}
function render(){draw2d(document.getElementById('c2d'),PLAN,floorId,true);draw3d();draw2d(document.getElementById('cafter'),PLAN,floorId);draw2d(document.getElementById('cbefore'),BEFORE||PLAN,floorId);updateIssues()}
document.getElementById('title').textContent=PLAN.project.name||'Villa Floorplan CAD';const status=document.getElementById('status');status.textContent=VALIDATION.valid?'Validated':'Needs review';if(!VALIDATION.valid)status.classList.add('has-errors');PLAN.floors.forEach(f=>{const o=document.createElement('option');o.value=f.id;o.textContent=f.name;document.getElementById('floor').appendChild(o)});document.getElementById('floor').onchange=e=>{floorId=e.target.value;render()};document.getElementById('c2d').onclick=e=>{const r=e.target.getBoundingClientRect(),x=(e.clientX-r.left)*e.target.width/r.width,y=(e.clientY-r.top)*e.target.height/r.height,h=hit.find(h=>x>=h.x&&x<=h.x+h.w&&y>=h.y&&y<=h.y+h.h);if(h)document.getElementById('roomInfo').innerHTML=`<b>${esc(h.r.name)}</b><br>Type: ${esc(h.r.type)}<br>Zone: ${esc(h.r.zone)}<br>Area: ${h.r.area_m2.toFixed(2)} m²<br>Clear size: ${h.r.geometry.width_m.toFixed(2)} × ${h.r.geometry.depth_m.toFixed(2)} m`};
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active');if(b.dataset.tab==='v3d')draw3d()});document.getElementById('artifacts').innerHTML=ARTIFACTS.map(a=>`<a href="${encodeURI(a.href)}">${esc(a.label)}</a>`).join('');render();
</script></body></html>'''


def create_viewer(plan: dict[str, Any], validation: dict[str, Any], viewer_dir: Path, artifacts: list[dict[str, str]], before: dict[str, Any] | None = None) -> Path:
    viewer_dir.mkdir(parents=True, exist_ok=True)
    page = (HTML_TEMPLATE.replace("__PLAN__", json_for_script(plan)).replace("__BEFORE__", json_for_script(before) if before else "null").replace("__VALIDATION__", json_for_script(validation)).replace("__ARTIFACTS__", json_for_script(artifacts)))
    output = viewer_dir / "index.html"
    output.write_text(page, encoding="utf-8")
    return output


def relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def artifact(label: str, path: Path, root: Path) -> dict[str, str]:
    return {"label": label, "path": relative_path(path, root)}


def _zip_write(zf: zipfile.ZipFile, source: Path, archive_name: str) -> None:
    info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, source.read_bytes())


def create_share_bundle(root: Path, plan: dict[str, Any], validation: dict[str, Any], before: dict[str, Any] | None, records: list[dict[str, str]], mode: str, zip_path: Path, validation_path: Path, full_files: list[Path]) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    allowed_suffixes = {".png", ".pdf", ".svg"} if mode == "review" else None
    selected = []
    for record in records:
        rel = Path(record["path"])
        if rel.parts and rel.parts[0] == "viewer":
            continue
        if allowed_suffixes is None or rel.suffix.lower() in allowed_suffixes:
            selected.append(record)

    with tempfile.TemporaryDirectory(prefix="villa-share-") as temp_name:
        temp = Path(temp_name)
        temp_viewer = temp / "viewer"
        share_links = [{"label": item["label"], "href": "../" + item["path"]} for item in selected]
        share_viewer = create_viewer(plan, validation, temp_viewer, share_links, before)
        share_manifest = {
            "schema_version": "villa-floorplan-cad.share.v1",
            "mode": mode,
            "project": plan.get("project", {}).get("name", root.name),
            "validation": validation.get("summary", {}),
            "files": sorted(["viewer/index.html", *[item["path"] for item in selected]]),
            "source_drawings_included": False,
        }
        manifest_path = dump_json(share_manifest, temp / "share-manifest.json")
        files: list[tuple[Path, str]] = [(share_viewer, "viewer/index.html"), (manifest_path, "share-manifest.json"), (validation_path, relative_path(validation_path, root))]
        files.extend((root / item["path"], item["path"]) for item in selected)
        if mode == "full":
            for path in full_files:
                if not path.exists():
                    continue
                rel = relative_path(path, root)
                if all(name != rel for _source, name in files):
                    files.append((path, rel))
        with zipfile.ZipFile(zip_path, "w") as zf:
            for source, name in sorted(files, key=lambda item: item[1]):
                _zip_write(zf, source, name)
    return zip_path


def run(project: Path, before_path: Path | None = None, with_ifc: bool = False, share_mode: str = "none") -> dict[str, Any]:
    root, program_path, output, viewer, share_dir = resolve_project_layout(project)
    output.mkdir(parents=True, exist_ok=True)
    viewer.mkdir(parents=True, exist_ok=True)
    program = load_json(program_path)
    plan = build_plan(program)
    plan_path = dump_json(plan, output / "plan.json")
    validation = validate(plan)
    validation_path = dump_json(validation, output / "validation.json")
    records: list[dict[str, str]] = []

    for floor in plan["floors"]:
        svg = render_floor_svg(plan, floor, output / f"{floor['id']}.svg", validation)
        png = render_floor_png(plan, floor, output / f"{floor['id']}.png", validation)
        records.extend((artifact(f"{floor['name']} SVG", svg, root), artifact(f"{floor['name']} PNG", png, root)))

    pdf = export_pdf(plan_path, output / "villa-drawing-set.pdf", validation_path)
    records.append(artifact("PDF drawing set", pdf, root))
    scad = output / "villa-model.scad"
    scad.write_text(generate_scad(plan), encoding="utf-8")
    records.append(artifact("OpenSCAD 3D model", scad, root))

    if module_available("ezdxf"):
        for floor in plan["floors"]:
            dxf = export_dxf_floor(plan, floor, output / f"{floor['id']}.dxf")
            records.append(artifact(f"{floor['name']} DXF", dxf, root))
        dxf_status = "generated"
    else:
        dxf_status = "unavailable: install ezdxf"

    if with_ifc and module_available("ifcopenshell"):
        ifc = export_ifc(plan_path, output / "villa-model.ifc")
        records.append(artifact("IFC4 model", ifc, root))
        ifc_status = "generated"
    elif with_ifc:
        ifc_status = "unavailable: install requirements-ifc.txt"
    else:
        ifc_status = "not requested"

    before = load_json(before_path) if before_path else None
    local_links = [{"label": item["label"], "href": "../" + item["path"]} for item in records]
    viewer_path = create_viewer(plan, validation, viewer, local_links, before)
    records.append(artifact("Local HTML viewer", viewer_path, root))
    report: dict[str, Any] = {
        "schema_version": "villa-floorplan-cad.manifest.v1",
        "project_root": ".",
        "plan": relative_path(plan_path, root),
        "validation_path": relative_path(validation_path, root),
        "validation": validation,
        "dxf_status": dxf_status,
        "ifc_status": ifc_status,
        "artifacts": records,
    }
    manifest_path = output / "artifact-manifest.json"
    if share_mode != "none":
        project_slug = slug(plan.get("project", {}).get("name", root.name))
        share_path = share_dir / f"{project_slug}-{share_mode}.zip"
        report["share"] = {"mode": share_mode, "path": relative_path(share_path, root)}
        dump_json(report, manifest_path)
        create_share_bundle(root, plan, validation, before, records, share_mode, share_path, validation_path, [program_path, root / "villa-cad.json", plan_path, validation_path, manifest_path])
    else:
        dump_json(report, manifest_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Project folder or program.json")
    parser.add_argument("--before", default=None, help="Previous plan.json for before/after comparison")
    parser.add_argument("--ifc", action="store_true", help="Generate IFC when optional dependencies are installed")
    parser.add_argument("--share", choices=("none", "review", "full"), default="none", help="Create a safe review bundle or a complete editable bundle")
    args = parser.parse_args()
    report = run(Path(args.project).expanduser().resolve(), Path(args.before).expanduser().resolve() if args.before else None, args.ifc, args.share)
    print(json.dumps({"plan": report["plan"], "issues": report["validation"]["summary"], "dxf": report["dxf_status"], "ifc": report["ifc_status"], "share": report.get("share")}, indent=2))


if __name__ == "__main__":
    main()
