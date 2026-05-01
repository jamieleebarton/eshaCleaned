"""B4: aggregate verdicts -> canonical-grouped fix queue."""
from __future__ import annotations
import csv
import json
from pathlib import Path

from ruvs.schemas import LineVerdict


def build_fix_queue(verdicts: list[LineVerdict], out_path: Path) -> None:
    groups: dict[tuple[str, str, str], dict] = {}
    for v in verdicts:
        if v.is_clean() or not v.fix_proposed:
            continue
        canonical = v.fix_proposed.get("canonical") or ""
        ptype = v.fix_proposed.get("patch_type") or ""
        # which facet triggered
        facet = next((f for f, val in v.facets.items() if val not in {"ok", "n/a", "none"}), "unknown")
        key = (canonical, facet, ptype)
        g = groups.setdefault(key, {
            "canonical": canonical, "facet": facet, "proposed_patch_type": ptype,
            "delta_samples": [], "affected_recipes": set(), "source_run_ids": set(),
        })
        g["delta_samples"].append(v.fix_proposed.get("delta") or {})
        g["affected_recipes"].add(v.recipe_id)
        g["source_run_ids"].add(v.run_id)

    rows = []
    for g in groups.values():
        rows.append({
            "canonical": g["canonical"],
            "facet": g["facet"],
            "proposed_patch_type": g["proposed_patch_type"],
            "delta_merged": json.dumps(_merge_deltas(g["delta_samples"])),
            "affected_recipes_count": len(g["affected_recipes"]),
            "affected_recipes_sample": json.dumps(sorted(list(g["affected_recipes"]))[:10]),
            "source_run_ids": json.dumps(sorted(g["source_run_ids"])),
            "review_status": "pending",
        })
    rows.sort(key=lambda r: (-int(r["affected_recipes_count"]), r["canonical"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        if not rows:
            f.write("canonical,facet,proposed_patch_type,delta_merged,affected_recipes_count,affected_recipes_sample,source_run_ids,review_status\n")
            return
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            r["affected_recipes_count"] = str(r["affected_recipes_count"])
            w.writerow(r)


def _merge_deltas(samples: list[dict]) -> dict:
    merged: dict = {}
    for d in samples:
        for k, v in d.items():
            if isinstance(v, list):
                merged.setdefault(k, [])
                for item in v:
                    if item not in merged[k]:
                        merged[k].append(item)
            else:
                merged[k] = v
    return merged
