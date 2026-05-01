"""C1: read reviewed fix_queue.csv, emit patches/*.json by patch_type."""
from __future__ import annotations
import csv
import json
import re
from pathlib import Path

from ruvs.schemas import Patch


def generate_patches(fix_queue_path: Path, out_root: Path) -> list[Path]:
    written: list[Path] = []
    with fix_queue_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("review_status") != "approved":
                continue
            ptype = row["proposed_patch_type"]
            source_run_ids = json.loads(row["source_run_ids"])
            patch = Patch(
                patch_type=ptype,
                canonical=row["canonical"],
                delta=json.loads(row["delta_merged"]),
                affected_recipes=json.loads(row["affected_recipes_sample"]),
                source_run_id=source_run_ids[0] if source_run_ids else "",
                reviewed_by="T2",
            )
            sub = out_root / ptype
            sub.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^a-z0-9]+", "_", row["canonical"].lower()).strip("_") or "unknown"
            path = sub / f"{slug}.json"
            path.write_text(patch.to_json(), encoding="utf-8")
            written.append(path)
    return written
