---
name: villa-floorplan-cad
description: Design, modify, analyse, validate, render, and export dimensionally consistent residential villa floor plans for projects worldwide inside the current repository. Use for building programming, residential typology, guest-family-service privacy zoning, room adjacency, storage and service planning, furniture fit, door swings, circulation, plumbing stacks, stairs, elevators, parking, editable SVG/DXF, PDF drawing sets, OpenSCAD, optional IFC, jurisdiction profiles, and local 2D/3D comparison viewers. Use metric units only.
---

# Villa Floorplan CAD

Create buildable, editable floor-plan data rather than decorative images. Treat `program.json` as the design source and generated `plan.json` as the canonical geometry shared by every output.

## Operating rules

- Work directly inside the current repository. Put the project in a clear subfolder unless the repository already has a villa-CAD structure.
- Use metres, square metres, and metric drawing scales only. Reject imperial inputs or convert them explicitly before creating geometry.
- Preserve existing project files and user-authored geometry. Do not overwrite unrelated repository content.
- Keep room, wall, opening, furniture, fixture, dimension, level, and vertical-core data consistent.
- Use deterministic IDs, stable ordering, rounded coordinates, and reproducible outputs.
- Never present a styled image as the plan deliverable. Generate editable data and drawings.
- Do not claim permit or code approval. Select or create a jurisdiction profile, check current local authority requirements for the project location, and state remaining review items.

## Start here

Read these references as needed:

- `references/plan-schema.md` for the canonical schema and coordinate system.
- `references/global-residential.md` for jurisdiction-neutral villa planning logic.
- `references/jurisdiction-profiles.md` for packaged and custom local-rule profiles.
- `references/saudi-residential.md` only when the project is in Saudi Arabia.
- `references/workflow.md` for exact commands and output paths.

Install dependencies:

```bash
python -m pip install -r ~/.codex/skills/villa-floorplan-cad/requirements.txt
```

Create a working project in the current repository:

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/create_project.py \
  --root . \
  --project-dir villa-floorplan
```

## Design workflow

1. Inspect the repository and any supplied drawings, brief, plot data, room schedule, municipality constraints, and prior plan.
2. Select the correct jurisdiction profile, then build or revise `program.json` with site size, footprint, levels, heights, rooms, zones, target areas, access, parking, standards, and vertical elements.
3. Establish separate guest, family, and service arrival and circulation logic before detailed room placement.
4. Place stairs, elevator, shafts, wet rooms, kitchen, laundry, and service spaces as coordinated vertical and horizontal systems.
5. Test room adjacency, storage, furniture, doors, windows, ventilation, parking, and external access.
6. Generate the canonical `plan.json`.
7. Run validation and correct every error. Review each warning and either fix it or document the project-specific decision.
8. Regenerate SVG, DXF, PDF, PNG, OpenSCAD, optional IFC, and the local viewer from the same canonical model.
9. Open the generated viewer and PDF to check labels, dimensions, issue markers, floor selection, 3D massing, and before/after comparison.

## Full generation command

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/generate_report.py villa-floorplan
```

Add `--ifc` when IfcOpenShell is available. Add `--before path/to/old-plan.json` for a comparison view.

## Individual tools

- `scripts/create_project.py`: scaffold sample data and repository folders.
- `scripts/generate_plan.py`: convert `program.json` into canonical `plan.json`.
- `scripts/validate_plan.py`: run geometry, circulation, privacy, service, light, ventilation, storage, and core checks.
- `scripts/render_svg.py`: create one layered editable SVG and PNG preview per floor.
- `scripts/export_dxf.py`: create one metric editable DXF per floor using ezdxf.
- `scripts/export_pdf.py`: create an A3 drawing set with title block, names, areas, dimensions, north arrow, scale bar, legend, and issue markers.
- `scripts/export_openscad.py`: create slabs, walls, openings, stairs, elevator shaft, roof, and parapets.
- `scripts/export_ifc.py`: create an optional IFC4 model using IfcOpenShell.
- `scripts/generate_report.py`: run the pipeline, write the manifest, and build the local HTML viewer.

## Validation gate

The validator checks:

- room overlap and footprint containment
- disconnected rooms and missing doors
- door-to-door and door-to-furniture conflicts
- furniture fit and furniture collisions
- narrow corridors and lobbies
- natural light and wet-room ventilation
- storage provision and service-route length
- kitchen-to-dining connection
- guest-family-service privacy conflicts
- plumbing-stack alignment
- stair and elevator overlap or vertical misalignment
- room area calculations and drawing dimensions
- parking and external access completeness

Use this release gate:

```bash
python ~/.codex/skills/villa-floorplan-cad/scripts/validate_plan.py \
  villa-floorplan/output/plan.json \
  --output villa-floorplan/output/validation.json \
  --fail-on error
```

Do not suppress issues by deleting rooms, openings, dimensions, furniture, or fixtures from the model. Correct the geometry or adjust a documented project threshold.

## Output contract

A completed project contains:

- `output/plan.json`
- one `output/<floor>.svg` per floor
- one `output/<floor>.png` per floor
- one `output/<floor>.dxf` per floor when ezdxf is installed
- `output/villa-drawing-set.pdf`
- `output/villa-model.scad`
- optional `output/villa-model.ifc`
- `output/validation.json`
- `output/artifact-manifest.json`
- `viewer/index.html`

Before finishing, run the automated tests in this skill and inspect at least one generated SVG, PNG, and rendered PDF page.
