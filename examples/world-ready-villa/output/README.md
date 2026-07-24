# World-ready villa example

This folder contains lightweight editable SVG previews for the packaged `generic-metric` villa program.

Run the full pipeline to generate the canonical `plan.json`, DXF, PDF set, PNG previews, OpenSCAD model, optional IFC, validation report, artifact manifest, and local HTML viewer:

```bash
python scripts/create_project.py --root /tmp --project-dir world-ready-villa --profile generic-metric --generate
```

The checked-in previews are documentation assets. The generated deliverables remain reproducible from `assets/sample-villa-program.json`.
