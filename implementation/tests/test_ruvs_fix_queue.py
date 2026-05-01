import csv
from pathlib import Path
from ruvs.schemas import LineVerdict, FACETS
from ruvs_fix_queue import build_fix_queue


def _bad_verdict(rid, fix_canonical, deny_form):
    facets = {f: ("none" if f == "ambiguity_flagged" else "n/a" if f in {"form_correct", "cook_state_handled"} else "ok") for f in FACETS}
    facets["form_correct"] = "wrong_form"
    return LineVerdict(
        recipe_id=rid, line_idx=4, config_bucket="x", model="m", run_id="r1",
        facets=facets, evidence={},
        fix_proposed={"patch_type": "wishlist", "canonical": fix_canonical,
                      "delta": {"deny_form": deny_form}},
        ts="2026-05-01T00:00:00Z",
    )


def test_groups_by_canonical_and_ranks(tmp_path: Path):
    verdicts = [
        _bad_verdict(506745, "beef gravy", ["dry", "instant"]),
        _bad_verdict(506800, "beef gravy", ["dry", "instant"]),
        _bad_verdict(506900, "beef gravy", ["dry"]),
        _bad_verdict(507000, "mayonnaise", ["chipotle", "lime"]),
    ]
    out = tmp_path / "fix_queue.csv"
    build_fix_queue(verdicts, out)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["canonical"] == "beef gravy"           # most affected first
    assert rows[0]["affected_recipes_count"] == "3"
    assert rows[1]["canonical"] == "mayonnaise"
    assert rows[0]["review_status"] == "pending"
