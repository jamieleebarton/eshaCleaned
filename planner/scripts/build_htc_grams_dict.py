#!/usr/bin/env python3
"""Build per-recipe htc_grams_dict from recipes_unified.csv.

For each recipe_id, sum grams_resolved per unique htc_code. Output a JSON file
recipe_id → {htc_code: grams}.

This replaces the fndds_grams_dict the original Hestia tensor cache builder
reads from recipes2.csv. The new HTC tensor cache will index ingredients by
htc_code instead.
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
OUT = ROOT / "planner" / "data" / "recipe_htc_grams.json"


def main():
    print(f"reading {UNIFIED}", file=sys.stderr)
    by_recipe: defaultdict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    titles: dict[str, str] = {}
    n_lines = 0
    n_skipped = 0
    with UNIFIED.open() as f:
        for row in csv.DictReader(f):
            n_lines += 1
            rid = (row.get("recipe_id") or "").strip()
            if not rid: continue
            title = (row.get("recipe_title") or "").strip()
            if title and rid not in titles:
                titles[rid] = title
            htc = (row.get("htc_code") or "").strip().lstrip("~")
            if not htc:
                n_skipped += 1; continue
            try:
                grams = float(row.get("grams_resolved") or 0)
            except (ValueError, TypeError):
                grams = 0.0
            if grams <= 0: continue
            by_recipe[rid][htc] += grams

    print(f"  {n_lines:,} ingredient lines, {len(by_recipe):,} recipes, {n_skipped:,} skipped (no htc)",
          file=sys.stderr)

    # Distribution of unique HTC codes per recipe
    sizes = [len(v) for v in by_recipe.values()]
    sizes.sort()
    if sizes:
        print(f"  htc_codes per recipe: min={min(sizes)}, p50={sizes[len(sizes)//2]}, "
              f"p90={sizes[int(len(sizes)*0.9)]}, max={max(sizes)}", file=sys.stderr)

    # Total unique HTC codes across the corpus
    all_htc = set()
    for d in by_recipe.values():
        all_htc.update(d.keys())
    print(f"  unique HTC codes corpus-wide: {len(all_htc):,}", file=sys.stderr)

    # Save: { recipe_id: {htc: grams} } and titles
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_obj = {
        "titles": titles,
        "htc_grams": {rid: dict(d) for rid, d in by_recipe.items()},
    }
    with OUT.open("w") as f:
        json.dump(out_obj, f)
    print(f"→ {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
