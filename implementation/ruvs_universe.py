"""A1: discover the planner's recipe universe over a config matrix."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Any


def _parse_yaml(text: str) -> dict:
    """Minimal YAML reader for our specific config_matrix shape (avoids PyYAML dep)."""
    obj: dict[str, Any] = {}
    cells: list[dict[str, Any]] = []
    cur_cell: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("cells:"):
            obj["cells"] = cells
            continue
        if line.lstrip().startswith("- "):
            if cur_cell is not None:
                cells.append(cur_cell)
            cur_cell = {}
            kv = line.lstrip()[2:]
            if ":" in kv:
                k, v = kv.split(":", 1)
                cur_cell[k.strip()] = _coerce(v.strip())
            continue
        if line.startswith("    ") and cur_cell is not None:
            kv = line.strip()
            k, v = kv.split(":", 1)
            cur_cell[k.strip()] = _coerce(v.strip())
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            obj[k.strip()] = _coerce(v.strip())
    if cur_cell is not None:
        cells.append(cur_cell)
    if "cells" not in obj:
        obj["cells"] = cells
    return obj


def _coerce(s: str):
    s = s.strip().strip('"').strip("'")
    if s.isdigit():
        return int(s)
    try:
        return float(s)
    except ValueError:
        return s


def load_config_matrix(path: Path) -> dict:
    return _parse_yaml(Path(path).read_text(encoding="utf-8"))


def discover_universe(config_path: Path, out_path: Path) -> None:
    cfg = load_config_matrix(Path(config_path))
    weeks = int(cfg.get("weeks", 50))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for cell in cfg.get("cells", []):
            for plan_row in _run_one_cell(cell, weeks):
                f.write(json.dumps(plan_row) + "\n")


def _run_one_cell(cell: dict, weeks: int):
    if os.environ.get("RUVS_UNIVERSE_STUB") == "1":
        # deterministic fake plans for tests
        slots = ("breakfast", "lunch", "dinner")
        for week in range(weeks):
            for slot in slots:
                yield {
                    "recipe_id": 500000 + week * 3 + slots.index(slot),
                    "config_id": cell["id"],
                    "week": week,
                    "slot": slot,
                    "count": 1,
                }
        return
    # real mode: import Hestia sparse_cascade. The exact call signature is a
    # placeholder; iterate on this when running against the live planner.
    # Actual Hestia signature (api/hestia/sparse_cascade.py ~L4240):
    #     SparseCascadePlanner.plan(initial_pantry: Optional[torch.Tensor]=None) -> Dict
    # Multi-week / household / dietary / pattern / pantry_seed are not direct
    # plan() args — they require constructing the planner with appropriate
    # config and looping weeks via start_session().plan_next_week(). Real-mode
    # adaptation lives in the cell-runner script (Task 16).
    sys.path.insert(0, "/Users/jamiebarton/Desktop/Hestia/api")
    from hestia import sparse_cascade  # type: ignore
    planner = sparse_cascade.SparseCascadePlanner.from_defaults()  # type: ignore[attr-defined]
    plan = planner.plan(weeks=weeks, household=cell["household"],
                        dietary=cell.get("dietary", "none"),
                        pattern=cell.get("pattern", "3meal"),
                        pantry_seed=cell.get("pantry_seed", "empty"))
    for entry in plan.flatten():
        yield {
            "recipe_id": entry.recipe_id,
            "config_id": cell["id"],
            "week": entry.week,
            "slot": entry.slot,
            "count": 1,
        }
