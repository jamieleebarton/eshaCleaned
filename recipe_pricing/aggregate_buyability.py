#!/usr/bin/env python3
"""Aggregate buyability classifications into two planner-facing lookups.

Inputs:
  recipe_pricing/buyability_classifications.jsonl
    one record per recipe with per-line classifications

Outputs:
  recipe_pricing/buyability_per_line.csv
    per-(recipe_id, line_index) — what the planner reads at price time.
    Columns: recipe_id, line_index, item, display, buyability,
             canonical_buy_form, base_ingredients, usage, rationale

  recipe_pricing/buyability_per_item.csv
    per-unique-item modal classification (across all recipes that use it).
    Items that VARY by context (e.g. lobster shells: derivative in some,
    unbuyable in others) get is_context_dependent=1 — planner must use the
    per-line lookup for those.
    Columns: item, recipe_count, dominant_buyability, dominant_pct,
             dominant_buy_form, is_context_dependent, top_buy_forms,
             modes_seen

  recipe_pricing/buyability_recipe_health.csv
    per-recipe rollup: how many lines core/garnish/derivative/etc.
    Lets the planner mark a recipe as "ready", "needs-substitution",
    or "unfulfillable" up-front.
    Columns: recipe_id, title, n_lines, n_core, n_garnish, n_to_taste,
             n_optional, n_derivative, n_alternation, n_specialty,
             n_unbuyable, n_nonsense, health_status

Reads the file streaming so it can run on partial output while the
classifier is still going.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "recipe_pricing" / "buyability_classifications.jsonl"
OUT_LINE = ROOT / "recipe_pricing" / "buyability_per_line.csv"
OUT_ITEM = ROOT / "recipe_pricing" / "buyability_per_item.csv"
OUT_RECIPE = ROOT / "recipe_pricing" / "buyability_recipe_health.csv"


def derive_recipe_health(counts: Counter) -> str:
    """Roll a recipe's per-line counts into a single status."""
    if counts.get("nonsense", 0) > 0 or counts.get("unbuyable", 0) > 0:
        return "needs_review"
    if counts.get("specialty", 0) > 0:
        return "specialty_required"
    if counts.get("alternation", 0) > 0 or counts.get("derivative", 0) > 0:
        return "ready_with_substitutions"
    return "ready"


def main() -> int:
    if not IN.exists():
        raise SystemExit(f"missing {IN}")

    # Per-item aggregation buffers
    item_buyability: defaultdict[str, Counter] = defaultdict(Counter)
    item_buy_forms: defaultdict[str, Counter] = defaultdict(Counter)
    item_recipes: defaultdict[str, set] = defaultdict(set)

    n_records = 0
    n_lines = 0
    n_recipes_health = Counter()

    with IN.open() as fin, \
         OUT_LINE.open("w", newline="") as fline, \
         OUT_RECIPE.open("w", newline="") as frecipe:
        wline = csv.DictWriter(fline, fieldnames=[
            "recipe_id", "line_index", "item", "display",
            "buyability", "canonical_buy_form", "base_ingredients",
            "usage", "rationale",
        ])
        wline.writeheader()

        wrecipe = csv.DictWriter(frecipe, fieldnames=[
            "recipe_id", "title", "n_lines",
            "n_core", "n_garnish", "n_to_taste", "n_optional",
            "n_derivative", "n_alternation", "n_specialty",
            "n_unbuyable", "n_nonsense",
            "health_status",
        ])
        wrecipe.writeheader()

        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_records += 1
            rid = r.get("recipe_id")
            title = r.get("title", "")
            ings = {ing["line_index"]: ing for ing in r.get("ingredients", [])
                    if isinstance(ing, dict)}
            cls_list = r.get("classifications", [])
            if r.get("error") or not cls_list:
                # Emit the recipe with no per-line rows; mark health=needs_review
                wrecipe.writerow({
                    "recipe_id": rid, "title": title, "n_lines": len(ings),
                    "n_core": 0, "n_garnish": 0, "n_to_taste": 0, "n_optional": 0,
                    "n_derivative": 0, "n_alternation": 0, "n_specialty": 0,
                    "n_unbuyable": 0, "n_nonsense": 0,
                    "health_status": "classifier_error",
                })
                n_recipes_health["classifier_error"] += 1
                continue

            buy_counts: Counter = Counter()
            use_counts: Counter = Counter()
            for c in cls_list:
                idx = c.get("line_index")
                if idx is None:
                    continue
                ing = ings.get(idx, {})
                item = ing.get("item", "")
                bu = c.get("buyability", "")
                bf = c.get("canonical_buy_form") or ""
                bi = c.get("base_ingredients") or []
                us = c.get("usage", "")
                rat = c.get("rationale", "")
                buy_counts[bu] += 1
                use_counts[us] += 1
                wline.writerow({
                    "recipe_id": rid,
                    "line_index": idx,
                    "item": item,
                    "display": ing.get("display", ""),
                    "buyability": bu,
                    "canonical_buy_form": bf,
                    "base_ingredients": " | ".join(bi),
                    "usage": us,
                    "rationale": rat,
                })
                n_lines += 1
                if item:
                    key = item.lower().strip()
                    item_buyability[key][bu] += 1
                    if bf:
                        item_buy_forms[key][bf] += 1
                    item_recipes[key].add(rid)

            health = derive_recipe_health(buy_counts)
            n_recipes_health[health] += 1
            wrecipe.writerow({
                "recipe_id": rid, "title": title, "n_lines": len(ings),
                "n_core": use_counts.get("core", 0),
                "n_garnish": use_counts.get("garnish", 0),
                "n_to_taste": use_counts.get("to_taste", 0),
                "n_optional": use_counts.get("optional", 0),
                "n_derivative": buy_counts.get("derivative", 0),
                "n_alternation": buy_counts.get("alternation", 0),
                "n_specialty": buy_counts.get("specialty", 0),
                "n_unbuyable": buy_counts.get("unbuyable", 0),
                "n_nonsense": buy_counts.get("nonsense", 0),
                "health_status": health,
            })

    # Per-item modal classification
    with OUT_ITEM.open("w", newline="") as fitem:
        witem = csv.DictWriter(fitem, fieldnames=[
            "item", "recipe_count", "dominant_buyability", "dominant_pct",
            "dominant_buy_form", "is_context_dependent",
            "top_buy_forms", "modes_seen",
        ])
        witem.writeheader()
        rows = []
        for item, bc in item_buyability.items():
            total = sum(bc.values())
            dom_b, dom_n = bc.most_common(1)[0]
            dom_pct = dom_n / total
            modes = sorted(bc.keys())
            ctx = "1" if (len(modes) > 1 and dom_pct < 0.85) else ""
            forms = item_buy_forms.get(item, Counter())
            top_forms = " | ".join(f"{f}({n})" for f, n in forms.most_common(3))
            dom_form = forms.most_common(1)[0][0] if forms else ""
            rows.append({
                "item": item,
                "recipe_count": len(item_recipes[item]),
                "dominant_buyability": dom_b,
                "dominant_pct": f"{dom_pct:.0%}",
                "dominant_buy_form": dom_form,
                "is_context_dependent": ctx,
                "top_buy_forms": top_forms,
                "modes_seen": " | ".join(modes),
            })
        rows.sort(key=lambda r: -r["recipe_count"])
        witem.writerows(rows)

    print(f"recipes processed: {n_records:,}", file=sys.stderr)
    print(f"per-line rows:     {n_lines:,}", file=sys.stderr)
    print(f"unique items:      {len(item_buyability):,}", file=sys.stderr)
    print(f"\nRecipe health distribution:", file=sys.stderr)
    for k in ("ready", "ready_with_substitutions", "specialty_required",
              "needs_review", "classifier_error"):
        v = n_recipes_health.get(k, 0)
        if n_records:
            print(f"  {k:<26} {v:>7,}  ({v/n_records:.1%})", file=sys.stderr)
    print(f"\n  → {OUT_LINE}", file=sys.stderr)
    print(f"  → {OUT_ITEM}", file=sys.stderr)
    print(f"  → {OUT_RECIPE}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
