import json
from pathlib import Path
from ruvs_universe import discover_universe, load_config_matrix


def test_load_config_matrix(tmp_path):
    p = tmp_path / "cfg.yaml"
    p.write_text("weeks: 5\nseed: 1\ncells:\n  - id: x\n    household: 4\n    dietary: none\n    pattern: 3meal\n    pantry_seed: empty\n")
    cfg = load_config_matrix(p)
    assert cfg["weeks"] == 5
    assert cfg["cells"][0]["id"] == "x"


def test_discover_universe_stub_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("RUVS_UNIVERSE_STUB", "1")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("weeks: 2\nseed: 1\ncells:\n  - id: a\n    household: 1\n    dietary: none\n    pattern: 3meal\n    pantry_seed: empty\n")
    out = tmp_path / "universe.jsonl"
    discover_universe(cfg, out)
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert rows
    assert all("recipe_id" in r and "config_id" in r and "week" in r for r in rows)
