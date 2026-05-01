import csv
import json
from pathlib import Path
from ruvs_patches import generate_patches


def _write_queue(path: Path, rows):
    headers = ["canonical","facet","proposed_patch_type","delta_merged","affected_recipes_count","affected_recipes_sample","source_run_ids","review_status"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows: w.writerow(r)


def test_generate_emits_only_approved(tmp_path: Path):
    q = tmp_path / "fix_queue.csv"
    _write_queue(q, [
        {"canonical":"beef gravy","facet":"form_correct","proposed_patch_type":"wishlist",
         "delta_merged":json.dumps({"deny_form":["dry","instant"],"require_form":["liquid","jarred"]}),
         "affected_recipes_count":"3","affected_recipes_sample":json.dumps([506745,506800,506900]),
         "source_run_ids":json.dumps(["r1"]),"review_status":"approved"},
        {"canonical":"mayonnaise","facet":"granularity_correct","proposed_patch_type":"wishlist",
         "delta_merged":json.dumps({"deny_flavor":["chipotle","lime"]}),
         "affected_recipes_count":"1","affected_recipes_sample":json.dumps([507000]),
         "source_run_ids":json.dumps(["r1"]),"review_status":"pending"},
    ])
    out_dir = tmp_path / "patches"
    paths = generate_patches(q, out_dir)
    assert len(paths) == 1
    assert paths[0].parent.name == "wishlist"
    assert "beef" in paths[0].stem
    body = json.loads(paths[0].read_text())
    assert body["patch_type"] == "wishlist"
    assert body["delta"]["deny_form"] == ["dry", "instant"]
    assert 506745 in body["affected_recipes"]
