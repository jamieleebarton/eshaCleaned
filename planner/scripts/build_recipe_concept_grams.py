#!/usr/bin/env python3
"""For each recipe, aggregate grams_resolved by concept_key.

concept_key = (canonical_path | modifier | htc_form)

Sources:
  - recipe_ingredient_taxonomy_v2.csv → title → (canonical_path, modifier)
  - recipes_unified.csv               → recipe_id, ingredient_item, grams_resolved
  - current HTC encoder               → recipe-side htc_form for chosen path
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from planner.concept_routing import (  # noqa: E402
    choose_recipe_canonical_path,
    encode_recipe_line_htc,
    load_form_path_authority,
    load_htc_to_path,
    load_item_overrides,
    load_title_maps,
    valid_htc_form,
)

UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
OUT = ROOT / "planner" / "data" / "recipe_concept_grams.json"


def main():
    # Build a fallback htc_code → canonical_path map from the product corpus.
    # Recipe-line identity is chosen later from display overrides, item
    # overrides, and recipe taxonomy before this product-derived fallback.
    print("loading htc_code → canonical_path from consensus_htc_tagged…",
          file=sys.stderr)
    htc_to_path = load_htc_to_path()
    print(f"  {len(htc_to_path):,} htc→path fallback mappings", file=sys.stderr)

    print("loading htc_form → canonical_path authority from concept_index…",
          file=sys.stderr)
    form_path_authority = load_form_path_authority()
    print(f"  {len(form_path_authority):,} htc_form→path authoritative mappings",
          file=sys.stderr)

    print("loading title → (canonical_path, modifier) from v2 taxonomy (fallback)…",
          file=sys.stderr)
    title_to_path, title_to_mod = load_title_maps()
    print(f"  {len(title_to_path):,} title→path fallback mappings", file=sys.stderr)

    # Manual overrides for items where BOTH golden files have wrong cps
    # (e.g., nutmeg htc encoded under "Spice Blend" upstream).
    item_overrides = load_item_overrides()
    print(f"  {len(item_overrides):,} item→cp manual overrides", file=sys.stderr)

    print("scanning recipes_unified, aggregating by concept_key…", file=sys.stderr)
    by_recipe: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    titles: dict[str, str] = {}
    htc_encode_cache: dict[tuple[str, str, str], str] = {}
    intent_encode_cache: dict[tuple[str, str], str] = {}
    n_lines = 0; n_no_path = 0; n_no_htc = 0
    with UNIFIED.open() as f:
        for row in csv.DictReader(f):
            n_lines += 1
            rid = (row.get("recipe_id") or "").strip()
            if not rid: continue
            t = (row.get("recipe_title") or "").strip()
            if t and rid not in titles: titles[rid] = t
            item = (row.get("ingredient_item") or "").strip().lower()
            source_htc = (row.get("htc_code") or "").strip().lstrip("~")
            display = row.get("display") or ""
            title_path = title_to_path.get(item, "")
            # Recipe-side path comes from recipe intent first. Product-corpus
            # htc→path is only a fallback because it can encode retail package
            # form (fresh tomatoes filed as canned tomatoes, generic cheese,
            # etc.) instead of the recipe line's requested food.
            cp = choose_recipe_canonical_path(
                item=item,
                display=display,
                source_htc=source_htc,
                title_path=title_path,
                item_overrides=item_overrides,
                htc_to_path=htc_to_path,
                form_path_authority=form_path_authority,
                intent_cache=intent_encode_cache,
            )
            mod = title_to_mod.get(item, "Plain")
            if not cp:
                n_no_path += 1; continue
            if cp.startswith("Non-Food"):
                n_no_path += 1; continue
            htc_form = encode_recipe_line_htc(item, display, cp, source_htc, htc_encode_cache)
            if not valid_htc_form(htc_form):
                n_no_htc += 1; continue
            try:
                grams = float(row.get("grams_resolved") or 0)
            except (ValueError, TypeError):
                grams = 0.0
            if grams <= 0: continue
            # NEW SCHEMA: drop modifier from concept_key (matches build_concept_index)
            concept_key = f"{cp}|{htc_form}"
            by_recipe[rid][concept_key] += grams
            if n_lines % 500_000 == 0:
                print(f"  {n_lines:,} lines processed", file=sys.stderr)

    print(f"\ntotal lines: {n_lines:,}", file=sys.stderr)
    print(f"  no canonical_path: {n_no_path:,}", file=sys.stderr)
    print(f"  no htc/00000000:   {n_no_htc:,}", file=sys.stderr)
    print(f"  recipes with data: {len(by_recipe):,}", file=sys.stderr)

    sizes = [len(v) for v in by_recipe.values()]
    if sizes:
        sizes.sort()
        print(f"  concepts/recipe: min={min(sizes)}, p50={sizes[len(sizes)//2]}, "
              f"p90={sizes[int(len(sizes)*0.9)]}, max={max(sizes)}", file=sys.stderr)

    all_concepts = set()
    for d in by_recipe.values(): all_concepts.update(d.keys())
    print(f"  unique concept_keys corpus-wide: {len(all_concepts):,}", file=sys.stderr)
    print(f"  current HTC encoder cache entries: "
          f"{len(htc_encode_cache) + len(intent_encode_cache):,}", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_obj = {
        "titles": titles,
        "concept_grams": {rid: dict(d) for rid, d in by_recipe.items()},
    }
    with OUT.open("w") as f:
        json.dump(out_obj, f)
    print(f"\n→ {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
