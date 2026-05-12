#!/usr/bin/env python3
"""Pull a small, signal-diverse test pack of recipes from recipe_qa.db for
the buyability-classifier prompt design.

Targets recipes that exhibit each known problem class:

  A. alternation        — ingredient line contains " or "
  C. derivative items   — items like egg wash, simple syrup, dredging,
                          breading, <x> shells, <x> heads, <x> bones,
                          <x> cooking liquid
  D. ambiguous nouns    — bare noodles, cheese, stock, broth, wine, vinegar
  CLEAN                 — basic recipes (flour, sugar, butter, eggs only)
                          to confirm the model doesn't over-classify

Output:
  recipe_pricing/buyability_testpack.jsonl
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "recipe_qa.db"
OUT = ROOT / "recipe_pricing" / "buyability_testpack.jsonl"

# Each rule: a list of (label, [SQL LIKE patterns matched against full ingredients_json])
SIGNAL_RULES = [
    ("alternation",  [
        "%lemon juice or lime juice%",
        "% or fresh%",
        "% or frozen%",
        "% or dried%",
        "%bay bugs or lobster%",
        "%turkey, chicken, veal%",
        "%vodka or gin%",
        "%mashed potatoes or egg noodles%",
    ]),
    ("derivative_egg_wash", [
        "%\"item\": \"egg wash\"%",
        "%\"item\": \"beaten egg%",
    ]),
    ("derivative_simple_syrup", [
        "%\"item\": \"simple syrup\"%",
    ]),
    ("derivative_lobster_shells", [
        "%\"item\": \"lobster shells\"%",
        "%\"item\": \"shrimp shells\"%",
        "%\"item\": \"lobster head%",
    ]),
    ("derivative_cooking_liquid", [
        "%\"item\": \"%cooking liquid\"%",
        "%\"item\": \"%cooking water\"%",
        "%\"item\": \"reserved pasta water\"%",
    ]),
    ("derivative_breading", [
        "%\"item\": \"breading\"%",
        "%\"item\": \"dredging mixture\"%",
        "%\"item\": \"flour mixture\"%",
    ]),
    ("ambiguous_noodles", [
        "%\"item\": \"noodles\"%",
    ]),
    ("ambiguous_cheese", [
        "%\"item\": \"cheese\"%",
    ]),
    ("ambiguous_stock", [
        "%\"item\": \"stock\"%",
    ]),
    ("ambiguous_wine", [
        "%\"item\": \"wine\"%",
    ]),
    ("clean_baseline", [
        # recipes with all-common, all-buyable ingredients — control set
        # picking by simple title patterns
        "%chocolate chip cookies%",
        "%vanilla cake%",
        "%scrambled eggs%",
    ]),
]

PER_BUCKET = 3   # 3 recipes per signal class


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    selected: dict[str, list[dict]] = {}
    seen_ids: set[int] = set()
    for label, patterns in SIGNAL_RULES:
        rows = []
        for pat in patterns:
            if len(rows) >= PER_BUCKET:
                break
            field = "title" if label == "clean_baseline" else "ingredients_json"
            cur.execute(
                f"SELECT recipe_id, title, ingredients_json, steps_json "
                f"FROM recipe_cleaned WHERE {field} LIKE ? "
                f"AND length(steps_json) > 100 AND length(ingredients_json) > 100 "
                f"LIMIT 5",
                (pat,),
            )
            for r in cur.fetchall():
                if r["recipe_id"] in seen_ids:
                    continue
                rows.append(dict(r))
                seen_ids.add(r["recipe_id"])
                if len(rows) >= PER_BUCKET:
                    break
        selected[label] = rows
        print(f"  {label:<32} {len(rows)} recipes", file=sys.stderr)

    # Emit JSONL — one recipe per line, with the signal label
    with OUT.open("w") as f:
        for label, rows in selected.items():
            for r in rows:
                # Parse ingredients/steps to clean form
                try:
                    ings = json.loads(r["ingredients_json"])
                except json.JSONDecodeError:
                    ings = []
                try:
                    steps = json.loads(r["steps_json"])
                except json.JSONDecodeError:
                    steps = []
                f.write(json.dumps({
                    "recipe_id": r["recipe_id"],
                    "signal_label": label,
                    "title": r["title"],
                    "ingredients": [
                        {
                            "line_index": i,
                            "display": ing.get("display", ""),
                            "item": ing.get("item", ""),
                        }
                        for i, ing in enumerate(ings) if isinstance(ing, dict)
                    ],
                    "steps": steps if isinstance(steps, list) else [],
                }) + "\n")

    total = sum(len(v) for v in selected.values())
    print(f"\nwrote {total} recipes → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
