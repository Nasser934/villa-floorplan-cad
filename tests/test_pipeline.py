from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from export_openscad import generate_scad
from export_pdf import export_pdf
from generate_plan import build_plan
from render_svg import render_floor_png, render_floor_svg
from validate_plan import validate

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "assets" / "sample-villa-program.json"


def test_plan_is_deterministic_and_metric(tmp_path: Path) -> None:
    program = json.loads(SAMPLE.read_text(encoding="utf-8"))
    first = build_plan(json.loads(json.dumps(program)))
    second = build_plan(json.loads(json.dumps(program)))
    assert first == second
    assert first["units"] == "metres"
    assert first["schema_version"] == "villa-floorplan-cad.plan.v1"
    assert len(first["floors"]) == 2
    assert all(room["area_m2"] == pytest.approx(room["geometry"]["width_m"] * room["geometry"]["depth_m"]) for room in first["rooms"])
    required = {"floors", "rooms", "walls", "openings", "doors", "windows", "furniture", "fixtures", "dimensions", "adjacency_relationships", "levels_and_heights"}
    assert required.issubset(first)


def test_validator_detects_overlap() -> None:
    program = json.loads(SAMPLE.read_text(encoding="utf-8"))
    program["floors"][0]["rooms"][1]["x_m"] = program["floors"][0]["rooms"][0]["x_m"]
    program["floors"][0]["rooms"][1]["y_m"] = program["floors"][0]["rooms"][0]["y_m"]
    plan = build_plan(program)
    result = validate(plan)
    assert any(item["code"] == "overlapping-rooms" for item in result["issues"])


def test_validator_detects_plumbing_misalignment() -> None:
    program = json.loads(SAMPLE.read_text(encoding="utf-8"))
    program["standards"]["plumbing_stack_tolerance_m"] = 0.1
    plan = build_plan(program)
    result = validate(plan)
    assert any(item["code"] == "stacked-plumbing-misalignment" for item in result["issues"])


def test_core_exports_are_created_and_parseable(tmp_path: Path) -> None:
    plan = build_plan(json.loads(SAMPLE.read_text(encoding="utf-8")))
    validation = validate(plan)
    floor = plan["floors"][0]
    svg_path = render_floor_svg(plan, floor, tmp_path / "ground.svg", validation, scale=35.0)
    png_path = render_floor_png(plan, floor, tmp_path / "ground.png", validation, scale=35.0)
    assert svg_path.exists() and png_path.exists()
    ET.parse(svg_path)
    assert png_path.stat().st_size > 1000
    plan_path = tmp_path / "plan.json"
    validation_path = tmp_path / "validation.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    pdf_path = export_pdf(plan_path, tmp_path / "set.pdf", validation_path)
    scad_path = tmp_path / "model.scad"
    scad_path.write_text(generate_scad(plan), encoding="utf-8")
    assert pdf_path.read_bytes().startswith(b"%PDF")
    scad_text = scad_path.read_text(encoding="utf-8")
    assert "module villa_model" in scad_text
    assert "difference()" in scad_text


def test_full_report_pipeline_and_safe_review_share(tmp_path: Path) -> None:
    project = tmp_path / "villa"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "create_project.py"), "--root", str(tmp_path), "--project-dir", "villa"], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_report.py"), str(project), "--share", "review"], check=True)
    manifest = json.loads((project / "output" / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert (project / "output" / "plan.json").exists()
    assert (project / "output" / "villa-drawing-set.pdf").exists()
    assert (project / "output" / "villa-model.scad").exists()
    assert (project / "viewer" / "index.html").exists()
    assert manifest["schema_version"] == "villa-floorplan-cad.manifest.v1"
    assert manifest["project_root"] == "."
    assert all(not Path(item["path"]).is_absolute() for item in manifest["artifacts"])
    share_path = project / manifest["share"]["path"]
    assert share_path.exists()
    with zipfile.ZipFile(share_path) as archive:
        names = set(archive.namelist())
        assert "viewer/index.html" in names
        assert "share-manifest.json" in names
        assert "output/villa-drawing-set.pdf" in names
        assert "output/validation.json" in names
        assert any(name.endswith(".png") for name in names)
        assert "program.json" not in names
        assert "output/plan.json" not in names
        assert not any(name.startswith("source/") for name in names)


@pytest.mark.skipif(importlib.util.find_spec("ezdxf") is None, reason="ezdxf is not installed")
def test_dxf_export(tmp_path: Path) -> None:
    from export_dxf import export_floor
    plan = build_plan(json.loads(SAMPLE.read_text(encoding="utf-8")))
    path = export_floor(plan, plan["floors"][0], tmp_path / "ground.dxf")
    assert path.exists()
    assert "SECTION" in path.read_text(encoding="utf-8", errors="ignore")[:500]


@pytest.mark.skipif(importlib.util.find_spec("ifcopenshell") is None, reason="IfcOpenShell is not installed")
def test_ifc_export(tmp_path: Path) -> None:
    from export_ifc import export_ifc
    plan = build_plan(json.loads(SAMPLE.read_text(encoding="utf-8")))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    first = export_ifc(plan_path, tmp_path / "villa-first.ifc")
    second = export_ifc(plan_path, tmp_path / "villa-second.ifc")
    assert first.exists() and second.exists()
    assert first.read_text(encoding="utf-8", errors="ignore").startswith("ISO-10303-21")
    assert first.read_bytes() == second.read_bytes()


def test_sample_is_world_ready_by_default() -> None:
    program = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert program["project"]["standards_profile"] == "generic-metric"
    assert program["project"]["country_code"] == "XX"
    assert "Saudi Arabia" not in program["project"]["location"]


def test_build_plan_does_not_mutate_program() -> None:
    program = json.loads(SAMPLE.read_text(encoding="utf-8"))
    original = json.loads(json.dumps(program))
    build_plan(program)
    assert program == original


def test_project_config_controls_paths(tmp_path: Path) -> None:
    project = tmp_path / "configured-villa"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "create_project.py"), "--root", str(tmp_path), "--project-dir", project.name], check=True)
    (project / "inputs").mkdir()
    (project / "program.json").rename(project / "inputs" / "villa.json")
    config = json.loads((project / "villa-cad.json").read_text(encoding="utf-8"))
    config.update({"program": "inputs/villa.json", "output_dir": "build", "viewer_dir": "review", "share_dir": "delivery"})
    (project / "villa-cad.json").write_text(json.dumps(config), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_report.py"), str(project), "--share", "review"], check=True)
    assert (project / "build" / "plan.json").exists()
    assert (project / "review" / "index.html").exists()
    assert next((project / "delivery").glob("*-review.zip")).exists()


def test_viewer_escapes_inline_script_content(tmp_path: Path) -> None:
    program = json.loads(SAMPLE.read_text(encoding="utf-8"))
    program["project"]["name"] = "Villa </script><script>alert(1)</script>"
    project = tmp_path / "safe-viewer"
    project.mkdir()
    (project / "program.json").write_text(json.dumps(program), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_report.py"), str(project)], check=True)
    viewer = (project / "viewer" / "index.html").read_text(encoding="utf-8")
    assert "</script><script>alert(1)</script>" not in viewer
    assert "\\u003c/script\\u003e" in viewer
