# Jurisdiction profiles

A profile is a JSON file that overlays project metadata and validator thresholds onto the sample program.

## Packaged profiles

- `generic-metric`: worldwide starting point with no code-compliance claim.
- `saudi-arabia`: Saudi-specific review metadata and planning notes.

Create a project with a packaged profile:

```bash
python scripts/create_project.py --root . --project-dir my-villa --profile generic-metric
```

Use a custom profile file:

```bash
python scripts/create_project.py --root . --project-dir my-villa --profile ./profiles/france-house.json
```

## Profile format

```json
{
  "profile_id": "france-house",
  "project": {
    "country_code": "FR",
    "jurisdiction": "France"
  },
  "standards": {
    "minimum_corridor_width_m": 1.20
  },
  "review": {
    "authority": "Set the current authority",
    "code_sources": [],
    "notes": []
  }
}
```

Profiles merge deterministically. Project values and profile standards are written into `program.json`, then copied into the canonical `plan.json`. The profile does not certify compliance.
