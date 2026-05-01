"""B3: append verdicts to JSONL with key-based dedup."""
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path

from ruvs.schemas import LineVerdict


def _key(v: LineVerdict) -> tuple:
    return (v.recipe_id, v.line_idx, v.config_bucket, v.model, v.run_id)


def load_verdicts(path: Path) -> list[LineVerdict]:
    if not path.exists():
        return []
    out: list[LineVerdict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out.append(LineVerdict(**d))
    return out


def append_verdict(v: LineVerdict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_verdicts(path)
    if any(_key(e) == _key(v) for e in existing):
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(v)) + "\n")
