#!/usr/bin/env python3
"""Cross-reference title-based vs ingredient-based outlier flags.

Outputs:
  retail_mapper/v2/outlier_comparison.csv  — every SKU flagged by either pass,
                                              with both sims/zs and a 'caught_by' label
  console: rate of overlap, top-20 ingredient-only catches (titles missed),
           top-20 title-only catches (ingredients missed)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
TITLE_OUT = V2 / "embed_outliers.csv"
ING_OUT = V2 / "ingredient_outliers.csv"
COMP = V2 / "outlier_comparison.csv"
AUDIT = V2 / "full_corpus_audit.csv"

csv.field_size_limit(sys.maxsize)


def load(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["fdc_id"]] = r
    return out


def main() -> None:
    title = load(TITLE_OUT)
    ing = load(ING_OUT)
    title_set, ing_set = set(title), set(ing)

    print(f"  title-based outliers      : {len(title_set):,}")
    print(f"  ingredient-based outliers : {len(ing_set):,}")
    print(f"  overlap (both flagged)    : {len(title_set & ing_set):,}")
    print(f"  title-only                : {len(title_set - ing_set):,}")
    print(f"  ingredient-only           : {len(ing_set - title_set):,}")

    # Audit lookup for context
    fdcs_of_interest = title_set | ing_set
    audit: dict[str, dict] = {}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("fdc_id") in fdcs_of_interest:
                audit[r["fdc_id"]] = {
                    "title": (r.get("title", "") or "")[:80],
                    "canonical_path": r.get("canonical_path", ""),
                    "ingredients": (r.get("ingredients_clean") or r.get("ingredients") or "")[:120],
                }

    # Build comparison rows
    cols = ["fdc_id", "title", "canonical_path", "caught_by",
            "title_sim", "title_z", "ingredient_sim", "ingredient_z",
            "ingredients_snippet"]
    rows: list[dict] = []
    for fdc in title_set | ing_set:
        info = audit.get(fdc, {})
        ti = title.get(fdc, {})
        ig = ing.get(fdc, {})
        in_both = fdc in title_set and fdc in ing_set
        caught = "both" if in_both else ("title-only" if fdc in title_set else "ingredient-only")
        rows.append({
            "fdc_id": fdc,
            "title": info.get("title", ""),
            "canonical_path": info.get("canonical_path", ""),
            "caught_by": caught,
            "title_sim": ti.get("sim", ti.get("title_sim", "")),
            "title_z": ti.get("z_score", ""),
            "ingredient_sim": ig.get("ingredient_sim", ""),
            "ingredient_z": ig.get("z_score", ""),
            "ingredients_snippet": info.get("ingredients", ""),
        })

    # Sort by 'most divergent overall' = lowest min(title_sim, ingredient_sim)
    def divergence_score(r: dict) -> float:
        sims = []
        for k in ("title_sim", "ingredient_sim"):
            v = r[k]
            if v:
                try: sims.append(float(v))
                except ValueError: pass
        return min(sims) if sims else 1.0

    rows.sort(key=divergence_score)
    with COMP.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {COMP.name}")

    # Show the most interesting ingredient-only catches
    print()
    print("=" * 80)
    print("TOP 25 INGREDIENT-ONLY OUTLIERS (titles missed these — ingredients caught them)")
    print("=" * 80)
    ing_only = [r for r in rows if r["caught_by"] == "ingredient-only"]
    ing_only.sort(key=lambda r: float(r["ingredient_sim"]) if r["ingredient_sim"] else 1.0)
    for r in ing_only[:25]:
        print(f"  ing_sim={r['ingredient_sim']}  {r['title'][:55]}")
        print(f"    in: {r['canonical_path']}")
        print(f"    ingredients: {r['ingredients_snippet'][:100]}")
        print()

    print("=" * 80)
    print("TOP 15 TITLE-ONLY OUTLIERS (ingredients agree, but title disagrees with cluster)")
    print("=" * 80)
    title_only = [r for r in rows if r["caught_by"] == "title-only"]
    title_only.sort(key=lambda r: float(r["title_sim"]) if r["title_sim"] else 1.0)
    for r in title_only[:15]:
        print(f"  title_sim={r['title_sim']}  {r['title'][:55]}")
        print(f"    in: {r['canonical_path']}")
        print()


if __name__ == "__main__":
    main()
