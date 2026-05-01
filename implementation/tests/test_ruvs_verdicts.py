import json
from pathlib import Path
from ruvs.schemas import LineVerdict, FACETS
from ruvs_verdicts import append_verdict, load_verdicts


def _v(recipe_id=506745, line_idx=4, run_id="r1"):
    facets = {f: ("none" if f == "ambiguity_flagged" else "n/a" if f in {"form_correct", "cook_state_handled"} else "ok")
              for f in FACETS}
    return LineVerdict(recipe_id=recipe_id, line_idx=line_idx, config_bucket="x",
                       model="m", run_id=run_id, facets=facets, evidence={},
                       fix_proposed=None, ts="2026-05-01T00:00:00Z")


def test_append_and_load(tmp_path: Path):
    p = tmp_path / "verdicts.jsonl"
    append_verdict(_v(line_idx=4), p)
    append_verdict(_v(line_idx=5), p)
    rows = load_verdicts(p)
    assert len(rows) == 2
    assert rows[0].line_idx == 4 and rows[1].line_idx == 5


def test_idempotent_on_key(tmp_path: Path):
    p = tmp_path / "verdicts.jsonl"
    append_verdict(_v(), p)
    append_verdict(_v(), p)  # same key, should dedupe
    rows = load_verdicts(p)
    assert len(rows) == 1
