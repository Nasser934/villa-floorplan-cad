# Product and architecture review

## Product promise

A user provides a metric residential brief and receives one dimensionally consistent plan plus editable, reviewable, and shareable deliverables.

The product should feel like one workflow, not a collection of unrelated scripts.

## Primary user flow

1. Create a project.
2. Put private source drawings in `source/`.
3. Edit `program.json`.
4. Run `generate_report.py` once.
5. Review `viewer/index.html` and `validation.json`.
6. Share either a review ZIP or a full editable ZIP.

## Architecture decision

```text
program.json
    ↓
generate_plan.py
    ↓
plan.json  ← canonical geometry contract
    ├── validate_plan.py
    ├── render_svg.py / PNG
    ├── export_dxf.py
    ├── export_pdf.py
    ├── export_openscad.py
    ├── export_ifc.py (optional)
    └── viewer + share package
```

### Keep in the core

- Metric program data.
- Deterministic geometry.
- Validation.
- Stable artifact manifest.
- 2D documentation and neutral 3D geometry.

### Keep as adapters

- IFC.
- Blender and Blender MCP.
- Photorealistic materials and asset libraries.
- AI visual-review loops.
- Cloud rendering and customer portals.

Adapters consume `plan.json`. They do not become alternate geometry sources. This prevents DXF, PDF, Blender, and the viewer from drifting apart.

## Simplicity rules

- Keep `generate_report.py` as the single build command.
- Do not add a second orchestration framework.
- Do not require MCP for normal generation.
- Do not let Blender edit `plan.json` directly.
- Use `villa-cad.json` only for project paths and profile metadata.
- Keep all configured paths inside the project folder.
- Fail before generation when the program structure is invalid.
- Store relative paths in manifests.

## Sharing and privacy

`--share review` is the default customer-facing package. It includes the viewer, PDF, PNG, SVG, validation summary, and a share manifest. It excludes source drawings and editable model files.

`--share full` is explicit. It may include `program.json`, `plan.json`, DXF, OpenSCAD, IFC, and the complete artifact set.

Neither mode includes `source/`. A project owner must add source drawings manually when disclosure is intended.

## Viewer design

The viewer should answer four questions quickly:

1. Which floor am I reviewing?
2. Is the plan validated or does it need attention?
3. Where is the issue?
4. Which files can I download?

The viewer remains a self-contained static HTML file. It does not require a database, web framework, or hosted service.

## Blender integration boundary

A future Blender exporter should be one adapter:

```text
plan.json → export_blender.py → project.blend → preview renders
```

An AI visual-review loop may inspect renders and change cameras, lights, materials, and generated assets. Geometry changes return to `program.json` and rebuild through the canonical pipeline.

This keeps the simple 2D/CAD workflow stable when Blender or MCP is unavailable.

## Non-goals for the current core

- Automatic raster-PDF tracing without human dimension checks.
- Permit approval.
- Structural or detailed MEP design.
- A cloud account system.
- Autonomous aesthetic decisions.
- A dependency on one AI model or MCP server.
