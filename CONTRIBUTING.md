# Contributing

Thank you for improving villa-floorplan-cad.

## Rules

- Keep all geometry and calculations metric.
- Preserve deterministic IDs, ordering, and output.
- Add or update automated tests for every behaviour change.
- Generate every export from the canonical `plan.json`.
- Keep local-code profiles separate from the global baseline.
- Cite the authority, edition, date, and scope for jurisdiction rules.
- Do not claim permit or code approval.
- Do not commit private client plans or personal addresses.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Run a complete sample build:

```bash
python scripts/create_project.py \
  --root /tmp \
  --project-dir villa-floorplan-cad-dev \
  --profile generic-metric \
  --generate
```

Before opening a pull request, inspect at least one SVG, PNG, PDF page, OpenSCAD model, validation report, and the local viewer.
