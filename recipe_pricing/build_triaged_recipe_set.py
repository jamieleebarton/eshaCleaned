#!/usr/bin/env python3
"""Build the triaged recipe set for buyability classification — recipes
that contain at least one signal of a problem ingredient. Skip recipes
where every line is mainstream-buyable already; those don't need the LLM.

Triage signals (any of):
  - Ingredient line contains " or " or " optionally " or " alternatively "
  - Ingredient item matches problem regex: wash, syrup, dredg, breading,
    shells?, heads?, bones?, cooking liquid, cooking water, reserved pasta,
    glaze, drippings, marinade, brine, broth, stock, base, paste, slurry
  - Ingredient item is an ambiguous bare noun: noodles, cheese, stock,
    broth, wine, vinegar, oil, milk, flour, sugar, mixed vegetables, herbs
  - Ingredient line ends with: for serving, for garnish, for topping,
    for sprinkling, to taste, as needed, optional, divided, separated
  - Title contains alternation (Crawfish or Shrimp Cocktail, etc.)

Output:
  recipe_pricing/buyability_input.jsonl  (recipes ready for the classifier)
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "recipe_qa.db"
OUT = ROOT / "recipe_pricing" / "buyability_input.jsonl"


ALTERNATION_RE = re.compile(r"\b(?:or|optionally|alternatively)\b", re.I)

PROBLEM_ITEM_RE = re.compile(
    r"\b(?:wash|syrup|dredg|breading|shells?|heads?|bones?|cooking liquid|"
    r"cooking water|reserved pasta|glaze|drippings|marinade|brine|"
    r"slurry|ravioli|tetrazzini)\b",
    re.I,
)

AMBIGUOUS_BARE_ITEMS = {
    "noodles", "cheese", "stock", "broth", "wine", "vinegar", "oil",
    "milk", "flour", "sugar", "mixed vegetables", "herbs", "cream",
    "pepper", "rice", "beans",
}

USAGE_TRAILER_RE = re.compile(
    r"\b(?:for\s+(?:serving|garnish|topping|sprinkling|drizzling|"
    r"decorating|frying|dusting|coating)|"
    r"to\s+taste|as\s+needed|to\s+coat|to\s+drizzle|"
    r"\(optional\)|divided|separated)\b",
    re.I,
)


def is_problem_recipe(ings: list[dict], title: str) -> bool:
    if ALTERNATION_RE.search(title):
        return True
    for ing in ings:
        if not isinstance(ing, dict):
            continue
        display = (ing.get("display") or "").lower()
        item = (ing.get("item") or "").lower().strip()
        if ALTERNATION_RE.search(display):
            return True
        if PROBLEM_ITEM_RE.search(item):
            return True
        if item in AMBIGUOUS_BARE_ITEMS:
            return True
        if USAGE_TRAILER_RE.search(display):
            return True
    return False


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT recipe_id, title, ingredients_json, steps_json "
        "FROM recipe_cleaned "
        "WHERE length(ingredients_json) > 50"
    )
    n_total = 0
    n_kept = 0
    with OUT.open("w") as f:
        while True:
            rows = cur.fetchmany(2000)
            if not rows:
                break
            for r in rows:
                n_total += 1
                try:
                    ings = json.loads(r["ingredients_json"])
                except Exception:
                    continue
                if not isinstance(ings, list):
                    continue
                if not is_problem_recipe(ings, r["title"] or ""):
                    continue
                try:
                    steps = json.loads(r["steps_json"]) if r["steps_json"] else []
                except Exception:
                    steps = []
                f.write(json.dumps({
                    "recipe_id": r["recipe_id"],
                    "title": r["title"] or "",
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
                n_kept += 1
            if n_total % 50_000 == 0:
                print(f"  scanned {n_total:,} recipes, kept {n_kept:,}", file=sys.stderr)
    print(f"\nfinal: scanned {n_total:,}, kept {n_kept:,} ({n_kept/max(n_total,1):.1%})", file=sys.stderr)
    print(f"  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
