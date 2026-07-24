from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_world_ready_repository_assets() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    banner = (ROOT / "assets" / "readme" / "villa-floorplan-cad-action.svg").read_text(encoding="utf-8")
    assert "World Ready" in readme
    assert "generic-metric" in readme
    assert "Saudi-ready" not in readme
    assert "<animate" in banner
    assert "world-ready metric" in banner
