#!/usr/bin/env python3
"""Pull a small testpack of recipes that contain bare ambiguous nouns
(bread, milk, sugar, vinegar, cheese, etc.) so we can validate the prompt
fix that pushes the model to pick a specific default form.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "recipe_qa.db"
OUT = ROOT / "recipe_pricing" / "bare_noun_testpack.jsonl"

# Each ambiguous noun → list of LIKE patterns matched against ingredients_json
BARE_NOUN_PATTERNS = {
    "milk": ['%"item": "milk"%'],
    "sugar": ['%"item": "sugar"%'],
    "bread": ['%"item": "bread"%'],
    "vinegar": ['%"item": "vinegar"%'],
    "cheese": ['%"item": "cheese"%'],
    "rice": ['%"item": "rice"%'],
    "pasta": ['%"item": "pasta"%'],
    "wine": ['%"item": "wine"%'],
    "nuts": ['%"item": "nuts"%'],
    "broth": ['%"item": "broth"%'],
    "butter": ['%"item": "butter"%'],
    "oil": ['%"item": "oil"%'],
    "flour": ['%"item": "flour"%'],
    "eggs": ['%"item": "eggs"%'],
}

PER_BUCKET = 3


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    seen_ids: set[int] = set()
    with OUT.open("w") as f:
        for label, patterns in BARE_NOUN_PATTERNS.items():
            kept = 0
            for pat in patterns:
                if kept >= PER_BUCKET:
                    break
                cur.execute(
                    "SELECT recipe_id, title, ingredients_json, steps_json "
                    "FROM recipe_cleaned WHERE ingredients_json LIKE ? "
                    "AND length(steps_json) > 100 LIMIT 10",
                    (pat,),
                )
                for r in cur.fetchall():
                    if r["recipe_id"] in seen_ids:
                        continue
                    seen_ids.add(r["recipe_id"])
                    try:
                        ings = json.loads(r["ingredients_json"])
                    except Exception:
                        continue
                    try:
                        steps = json.loads(r["steps_json"]) if r["steps_json"] else []
                    except Exception:
                        steps = []
                    f.write(json.dumps({
                        "recipe_id": r["recipe_id"],
                        "signal_label": f"bare_{label}",
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
                    kept += 1
                    if kept >= PER_BUCKET:
                        break
            print(f"  bare_{label:<12} {kept} recipes", file=sys.stderr)

    print(f"\ntotal: {len(seen_ids)} recipes → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
