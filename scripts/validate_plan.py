#!/usr/bin/env python3
"""Validate villa plan geometry, circulation, privacy, furniture, and services."""
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Any
from common import dump_json, load_json
from validation_geometry import *
from validation_services import *

def validate(plan: dict[str, Any]) -> dict[str, Any]:
    checks=[validate_overlaps,validate_footprints,validate_connectivity,validate_missing_doors,validate_door_collisions,validate_furniture,validate_circulation,validate_light_ventilation,validate_storage,validate_service_routes,validate_kitchen_dining,validate_privacy,validate_plumbing_alignment,validate_vertical_conflicts,validate_areas_dimensions,validate_parking_access]
    issues=[]
    for check in checks: issues.extend(check(plan))
    severity_order={"error":0,"warning":1,"info":2}
    issues.sort(key=lambda i:(severity_order.get(i["severity"],9),i.get("floor_id") or "",i["code"],i["message"]))
    counts={s:sum(1 for i in issues if i["severity"]==s) for s in ("error","warning","info")}
    return {"schema_version":"villa-floorplan-cad.validation.v1","valid":counts["error"]==0,"summary":counts,"issue_count":len(issues),"issues":issues}


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("plan"); p.add_argument("--output",default=None); p.add_argument("--fail-on",choices=["none","error","warning"],default="error")
    a=p.parse_args(); plan_path=Path(a.plan).expanduser().resolve(); result=validate(load_json(plan_path)); out=Path(a.output).expanduser().resolve() if a.output else plan_path.parent/"validation.json"; dump_json(result,out); print(out)
    if a.fail_on=="error" and result["summary"]["error"]: raise SystemExit(2)
    if a.fail_on=="warning" and (result["summary"]["error"] or result["summary"]["warning"]): raise SystemExit(2)
if __name__=="__main__": main()
