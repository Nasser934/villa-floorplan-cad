#!/usr/bin/env python3
"""Create a world-ready villa-floorplan-cad project inside the current repository."""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = SKILL_ROOT / "assets" / "profiles"


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_profile(value: str) -> dict[str, Any]:
    candidate = Path(value).expanduser()
    if candidate.exists():
        path = candidate.resolve()
    else:
        path = PROFILE_DIR / f"{value}.json"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in PROFILE_DIR.glob("*.json")))
        raise SystemExit(f"Unknown profile: {value}. Available packaged profiles: {available}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Current repository root")
    parser.add_argument("--project-dir", default="villa-floorplan", help="Relative folder created inside the repository")
    parser.add_argument("--profile", default="generic-metric", help="Packaged profile name or path to a custom JSON profile")
    parser.add_argument("--location", default=None, help="Project location written into program.json")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--generate", action="store_true", help="Run the full generation pipeline")
    args = parser.parse_args()

    repo = Path(args.root).expanduser().resolve()
    target = (repo / args.project_dir).resolve()
    if repo not in target.parents and target != repo:
        raise SystemExit("project-dir must remain inside root")
    if target.exists() and any(target.iterdir()) and not args.force:
        raise SystemExit(f"Target is not empty: {target}. Use --force to replace generated scaffold files.")

    target.mkdir(parents=True, exist_ok=True)
    (target / "output").mkdir(exist_ok=True)
    (target / "viewer").mkdir(exist_ok=True)

    base = json.loads((SKILL_ROOT / "assets" / "sample-villa-program.json").read_text(encoding="utf-8"))
    profile = load_profile(args.profile)
    program = deep_merge(base, {k: v for k, v in profile.items() if k != "profile_id"})
    program.setdefault("project", {})["standards_profile"] = profile.get("profile_id", args.profile)
    if args.location:
        program["project"]["location"] = args.location

    (target / "program.json").write_text(json.dumps(program, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    config = {
        "schema_version": "villa-floorplan-cad.project.v1",
        "program": "program.json",
        "output_dir": "output",
        "viewer_dir": "viewer",
        "metric_only": True,
        "profile": profile.get("profile_id", args.profile),
    }
    (target / "villa-cad.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copy2(SKILL_ROOT / "requirements.txt", target / "requirements.txt")
    print(target)
    if args.generate:
        subprocess.run([sys.executable, str(SKILL_ROOT / "scripts" / "generate_report.py"), str(target)], check=True)


if __name__ == "__main__":
    main()
