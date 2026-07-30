# Command workflow

Assume the skill is installed at `~/.codex/skills/villa-floorplan-cad`.

## Install dependencies

```bash
python -m pip install -r ~/.codex/skills/villa-floorplan-cad/requirements.txt
```

IfcOpenShell is optional at runtime. Install it with `requirements-ifc.txt` before requesting `--ifc`.

## Create a project in the current repository

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/create_project.py \
  --root . \
  --project-dir villa-floorplan \
  --profile generic-metric \
  --location "Project city, country" \
  --generate
```

This creates:

- `villa-floorplan/program.json`
- `villa-floorplan/villa-cad.json`
- `villa-floorplan/source/`
- `villa-floorplan/output/`
- `villa-floorplan/viewer/`
- `villa-floorplan/share/`

## Generate the canonical model

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/generate_plan.py \
  villa-floorplan/program.json \
  --output villa-floorplan/output/plan.json
```

## Validate

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/validate_plan.py \
  villa-floorplan/output/plan.json \
  --output villa-floorplan/output/validation.json \
  --fail-on error
```

Use `--fail-on warning` for a strict review gate or `--fail-on none` while iterating.

## Render and export individually

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/render_svg.py \
  villa-floorplan/output/plan.json \
  --validation villa-floorplan/output/validation.json \
  --output-dir villa-floorplan/output

python ~/.codex/skills/villa-floorplan-cad/scripts/export_dxf.py \
  villa-floorplan/output/plan.json \
  --output-dir villa-floorplan/output

python ~/.codex/skills/villa-floorplan-cad/scripts/export_pdf.py \
  villa-floorplan/output/plan.json \
  --validation villa-floorplan/output/validation.json \
  --output villa-floorplan/output/villa-drawing-set.pdf

python ~/.codex/skills/villa-floorplan-cad/scripts/export_openscad.py \
  villa-floorplan/output/plan.json \
  --output villa-floorplan/output/villa-model.scad

python ~/.codex/skills/villa-floorplan-cad/scripts/export_ifc.py \
  villa-floorplan/output/plan.json \
  --output villa-floorplan/output/villa-model.ifc
```

## Run the full pipeline and viewer

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/generate_report.py villa-floorplan
python -m http.server 8000 --directory villa-floorplan
```

Open `http://localhost:8000/viewer/index.html`.

## Before/after comparison

Preserve the previous canonical plan, then pass it to the report generator:

```bash
cp villa-floorplan/output/plan.json villa-floorplan/before-plan.json
# Edit program.json here.
python ~/.codex/skills/villa-floorplan-cad/scripts/generate_report.py \
  villa-floorplan \
  --before villa-floorplan/before-plan.json
```

## Required iteration loop

1. Edit `program.json`.
2. Generate `plan.json`.
3. Run validation.
4. Review SVG, PNG, PDF, and viewer issue markers.
5. Correct geometry or thresholds.
6. Regenerate every output from the same `plan.json`.
7. Record unresolved warnings and their design rationale.

## Apply a local profile

Use a packaged profile or supply a custom JSON file:

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/create_project.py \
  --root . \
  --project-dir villa-floorplan \
  --profile saudi-arabia
```

Keep `generic-metric` for jurisdiction-neutral concept work. Add current local requirements before any permit or construction use.

## Create a share package

Client review package, excluding source drawings and editable model files:

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/generate_report.py \
  villa-floorplan \
  --share review
```

Complete editable package:

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/generate_report.py \
  villa-floorplan \
  --share full
```

The artifact manifest stores project-relative paths. `source/` is excluded from both share modes.
