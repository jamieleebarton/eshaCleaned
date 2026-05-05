#!/usr/bin/env python3
"""Pull unique ingredient `item` values from recipe_qa.db.

Mirrors the retail v2 input contract: each row is a normalized identity string
(here, the parsed `item` from ingredients_json) plus aggregate context — recipe
count, total grams, sample raw `display` lines, sample recipe titles.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "recipe_qa.db"
OUT = Path(__file__).resolve().parent / "output" / "recipe_ingredient_items.csv"

WS = re.compile(r"\s+")


def normalize_item(s: str) -> str:
    s = (s or "").strip().lower()
    s = WS.sub(" ", s)
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-recipes", type=int, default=0,
                    help="0 = all recipes; else cap for smoke runs")
    ap.add_argument("--min-count", type=int, default=2,
                    help="drop ingredients seen in fewer than N recipes")
    ap.add_argument("--sample-displays", type=int, default=5)
    ap.add_argument("--sample-recipes", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB))
    sql = """SELECT recipe_id, COALESCE(clean_title, recipe_name) AS title, ingredients_json
             FROM recipe_verdicts
             WHERE ingredients_json IS NOT NULL AND ingredients_json != ''"""
    if args.limit_recipes > 0:
        sql += f" LIMIT {args.limit_recipes}"

    counts: Counter[str] = Counter()
    grams_total: dict[str, float] = defaultdict(float)
    displays: dict[str, list[str]] = defaultdict(list)
    recipes: dict[str, list[str]] = defaultdict(list)

    n_rec = 0
    n_lines = 0
    n_bad = 0
    for rid, title, blob in con.execute(sql):
        n_rec += 1
        try:
            items = json.loads(blob)
        except Exception:
            n_bad += 1
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            raw = it.get("item") or ""
            item = normalize_item(raw)
            if not item:
                continue
            n_lines += 1
            counts[item] += 1
            try:
                grams_total[item] += float(it.get("grams") or 0)
            except (TypeError, ValueError):
                pass
            disp = (it.get("display") or "").strip()
            if disp and len(displays[item]) < args.sample_displays \
                    and disp not in displays[item]:
                displays[item].append(disp)
            if title and len(recipes[item]) < args.sample_recipes \
                    and title not in recipes[item]:
                recipes[item].append(title)

    print(f"recipes_scanned={n_rec:,}  ingredient_lines={n_lines:,}  bad_blobs={n_bad}")
    print(f"unique_items_raw={len(counts):,}")

    rows = [(k, v) for k, v in counts.items() if v >= args.min_count]
    rows.sort(key=lambda kv: (-kv[1], kv[0]))
    print(f"unique_items_kept(min_count>={args.min_count})={len(rows):,}")

    with args.out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "recipe_count", "grams_total",
                    "sample_displays", "sample_recipes"])
        for item, cnt in rows:
            w.writerow([
                item, cnt, f"{grams_total[item]:.0f}",
                " || ".join(displays[item]),
                " || ".join(recipes[item]),
            ])
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
