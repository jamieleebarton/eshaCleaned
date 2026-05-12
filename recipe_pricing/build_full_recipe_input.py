#!/usr/bin/env python3
"""Build the FULL recipe input for buyability classification — every recipe
in recipe_qa.db with title + ingredients + steps. No triage filter.

This is the one-shot run. Output:
  recipe_pricing/buyability_input_full.jsonl
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "recipe_qa.db"
OUT = ROOT / "recipe_pricing" / "buyability_input_full.jsonl"


def main() -> int:
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
                if not isinstance(ings, list) or not ings:
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
            if n_total % 100_000 == 0:
                print(f"  scanned {n_total:,}", file=sys.stderr)
    print(f"\nfinal: {n_kept:,} recipes → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
