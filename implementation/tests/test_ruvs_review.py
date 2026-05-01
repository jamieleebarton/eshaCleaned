from unittest.mock import MagicMock
import json
import csv
from pathlib import Path
from ruvs.nebius import MessageResult
from ruvs_review import review_fix_queue


def _write_queue(path: Path, rows):
    headers = ["canonical","facet","proposed_patch_type","delta_merged","affected_recipes_count","affected_recipes_sample","source_run_ids","review_status"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers); w.writeheader()
        for r in rows: w.writerow(r)


def test_review_marks_approved(tmp_path):
    q = tmp_path / "fix_queue.csv"
    _write_queue(q, [{
        "canonical":"beef gravy","facet":"form_correct","proposed_patch_type":"wishlist",
        "delta_merged":json.dumps({"deny_form":["dry"]}),
        "affected_recipes_count":"3","affected_recipes_sample":json.dumps([506745,506800,506900]),
        "source_run_ids":json.dumps(["r1"]),"review_status":"pending",
    }])
    client = MagicMock()
    client.chat.return_value = MessageResult(content=json.dumps({"decision":"approve","reason":"clear form mismatch"}), tool_calls=[], usage={"prompt_tokens":50,"completion_tokens":10}, cost_usd=0.0001)
    review_fix_queue(q, client=client, packets_by_recipe={})
    rows = list(csv.DictReader(q.open()))
    assert rows[0]["review_status"] == "approved"


def test_review_escalates_high_blast_radius(tmp_path):
    q = tmp_path / "fix_queue.csv"
    _write_queue(q, [{
        "canonical":"butter","facet":"granularity_correct","proposed_patch_type":"wishlist",
        "delta_merged":json.dumps({"deny_flavor":["honey"]}),
        "affected_recipes_count":"250","affected_recipes_sample":json.dumps([1,2,3]),
        "source_run_ids":json.dumps(["r1"]),"review_status":"pending",
    }])
    client = MagicMock()
    review_fix_queue(q, client=client, packets_by_recipe={}, escalate_above=100)
    rows = list(csv.DictReader(q.open()))
    assert rows[0]["review_status"] == "escalated"
    client.chat.assert_not_called()
