#!/usr/bin/env python3
"""Apply identity codes back to actual recipes.

Loads recipe_qa.db, joins each parsed ingredient line to its identity code
(from recipe_ingredient_identity_codes.csv), and emits:

  - recipe_ingredient_lines_coded.csv  (one row per ingredient line)
  - recipe_coverage.csv                 (one row per recipe)
  - recipe_coverage_summary.json        (corpus-level coverage)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "recipe_qa.db"
HERE = Path(__file__).resolve().parent
DEFAULT_CODES = HERE / "output" / "recipe_ingredient_identity_codes.csv"
OUT_LINES = HERE / "output" / "recipe_ingredient_lines_coded.csv"
OUT_RECIPES = HERE / "output" / "recipe_coverage.csv"
OUT_SUMMARY = HERE / "output" / "recipe_coverage_summary.json"

WS = re.compile(r"\s+")


def normalize_item(s: str) -> str:
    s = (s or "").strip().lower()
    return WS.sub(" ", s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", type=Path, default=DEFAULT_CODES)
    ap.add_argument("--limit-recipes", type=int, default=0)
    ap.add_argument("--sim-threshold", type=float, default=0.60,
                    help="threshold below which a line is counted as 'unmatched'")
    args = ap.parse_args()

    t0 = time.time()
    OUT_LINES.parent.mkdir(parents=True, exist_ok=True)

    print(f"[{time.time()-t0:6.1f}s] loading codes from {args.codes.name}")
    codes = pd.read_csv(args.codes).fillna("")
    code_lookup: dict[str, dict] = {}
    for _, r in codes.iterrows():
        key = normalize_item(str(r["item"]))
        code_lookup[key] = {
            "identity_code": r["identity_code"],
            "rule": r["rule"],
            "canonical_path": r["canonical_path"],
            "modal_fndds_code": r["modal_fndds_code"],
            "modal_fndds_desc": r["modal_fndds_desc"],
            "modal_sr28_code": r["modal_sr28_code"],
            "modal_sr28_desc": r["modal_sr28_desc"],
            "has_portions": r["has_portions"],
            "similarity": float(r["similarity"]) if r["similarity"] else 0.0,
        }
    print(f"  {len(code_lookup):,} unique items in code table")

    print(f"[{time.time()-t0:6.1f}s] streaming recipes from {DB.name}")
    con = sqlite3.connect(str(DB))
    sql = """SELECT recipe_id, COALESCE(clean_title, recipe_name) AS title, ingredients_json
             FROM recipe_verdicts
             WHERE ingredients_json IS NOT NULL AND ingredients_json != ''"""
    if args.limit_recipes > 0:
        sql += f" LIMIT {args.limit_recipes}"

    line_w = OUT_LINES.open("w", newline="")
    line_writer = csv.writer(line_w)
    line_writer.writerow([
        "recipe_id", "recipe_title", "ingredient_item", "display", "grams",
        "identity_code", "rule", "canonical_path",
        "fndds_code", "fndds_desc", "sr28_code", "sr28_desc",
        "has_portions", "similarity", "match_status",
    ])

    rec_w = OUT_RECIPES.open("w", newline="")
    rec_writer = csv.writer(rec_w)
    rec_writer.writerow([
        "recipe_id", "title", "n_ingredients",
        "n_coded", "n_high_conf", "n_with_portions", "n_with_fndds",
        "pct_coded", "pct_high_conf", "pct_with_fndds", "pct_with_portions",
        "median_similarity", "all_calculable",
    ])

    n_rec = 0
    n_lines = 0
    n_coded = 0
    n_high = 0
    n_fndds = 0
    n_port = 0
    n_unmatched = 0
    n_recipes_full_calc = 0

    code_freq: Counter[str] = Counter()

    for rid, title, blob in con.execute(sql):
        n_rec += 1
        try:
            items = json.loads(blob)
        except Exception:
            continue
        if not isinstance(items, list):
            continue

        ing_lines = []
        sims = []
        n_ing = 0
        n_ing_coded = 0
        n_ing_high = 0
        n_ing_port = 0
        n_ing_fndds = 0
        all_calc = True

        for it in items:
            if not isinstance(it, dict):
                continue
            n_ing += 1
            n_lines += 1
            raw = it.get("item") or ""
            disp = it.get("display") or ""
            grams = it.get("grams") or ""
            key = normalize_item(raw)
            entry = code_lookup.get(key)
            if entry is None:
                n_unmatched += 1
                line_writer.writerow([
                    rid, title, raw, disp, grams,
                    "", "", "", "", "", "", "", "", "", "no_match"
                ])
                all_calc = False
                continue

            sim = entry["similarity"]
            sims.append(sim)
            status = "high_conf" if sim >= args.sim_threshold else "low_conf"
            n_ing_coded += 1
            n_coded += 1
            if sim >= args.sim_threshold:
                n_ing_high += 1
                n_high += 1
            else:
                all_calc = False
            if entry["modal_fndds_code"]:
                n_ing_fndds += 1
                n_fndds += 1
            else:
                all_calc = False
            if entry["has_portions"] in (True, "True", "true", 1, "1"):
                n_ing_port += 1
                n_port += 1
            code_freq[entry["identity_code"]] += 1
            line_writer.writerow([
                rid, title, raw, disp, grams,
                entry["identity_code"], entry["rule"], entry["canonical_path"],
                entry["modal_fndds_code"], entry["modal_fndds_desc"],
                entry["modal_sr28_code"], entry["modal_sr28_desc"],
                entry["has_portions"], f"{sim:.3f}", status
            ])

        if n_ing == 0:
            continue

        med_sim = sorted(sims)[len(sims)//2] if sims else 0.0
        if all_calc:
            n_recipes_full_calc += 1
        rec_writer.writerow([
            rid, title, n_ing,
            n_ing_coded, n_ing_high, n_ing_port, n_ing_fndds,
            f"{n_ing_coded/n_ing:.3f}",
            f"{n_ing_high/n_ing:.3f}",
            f"{n_ing_fndds/n_ing:.3f}",
            f"{n_ing_port/n_ing:.3f}",
            f"{med_sim:.3f}",
            int(all_calc),
        ])

        if n_rec % 50000 == 0:
            print(f"[{time.time()-t0:6.1f}s] {n_rec:,} recipes, {n_lines:,} lines")

    line_w.close()
    rec_w.close()

    summary = {
        "n_recipes": n_rec,
        "n_ingredient_lines": n_lines,
        "n_lines_coded": n_coded,
        "n_lines_high_conf": n_high,
        "n_lines_with_fndds": n_fndds,
        "n_lines_with_portions": n_port,
        "n_lines_unmatched": n_unmatched,
        "pct_coded": round(n_coded / n_lines, 4) if n_lines else 0,
        "pct_high_conf": round(n_high / n_lines, 4) if n_lines else 0,
        "pct_with_fndds": round(n_fndds / n_lines, 4) if n_lines else 0,
        "pct_with_portions": round(n_port / n_lines, 4) if n_lines else 0,
        "n_recipes_fully_calculable": n_recipes_full_calc,
        "pct_recipes_fully_calculable": round(n_recipes_full_calc / n_rec, 4) if n_rec else 0,
        "top_codes": code_freq.most_common(25),
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))

    print()
    print(f"recipes:           {n_rec:,}")
    print(f"ingredient lines:  {n_lines:,}")
    print(f"  coded:           {n_coded:,}  ({summary['pct_coded']:.1%})")
    print(f"  high_conf>=.60:  {n_high:,}  ({summary['pct_high_conf']:.1%})")
    print(f"  with FNDDS:      {n_fndds:,}  ({summary['pct_with_fndds']:.1%})")
    print(f"  with portions:   {n_port:,}  ({summary['pct_with_portions']:.1%})")
    print(f"  unmatched:       {n_unmatched:,}")
    print(f"recipes fully-calculable (all lines high_conf+fndds): "
          f"{n_recipes_full_calc:,}  ({summary['pct_recipes_fully_calculable']:.1%})")
    print(f"  -> {OUT_LINES}")
    print(f"  -> {OUT_RECIPES}")
    print(f"  -> {OUT_SUMMARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
