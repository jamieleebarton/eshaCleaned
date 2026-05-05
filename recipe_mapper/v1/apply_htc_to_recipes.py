#!/usr/bin/env python3
"""Apply HTC codes back to actual recipe ingredient lines.

Joins recipe_qa.db ingredients_json against recipe_ingredient_htc_tagged.csv
(item -> htc_code) so we can measure recipe-level HTC coverage.
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

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "recipe_qa.db"
HERE = Path(__file__).resolve().parent
DEFAULT_TAGS = HERE / "output" / "recipe_ingredient_htc_tagged.csv"
OUT_LINES = HERE / "output" / "recipe_lines_htc.csv"
OUT_SUMMARY = HERE / "output" / "recipe_htc_coverage_summary.json"

WS = re.compile(r"\s+")


def normalize_item(s: str) -> str:
    return WS.sub(" ", (s or "").strip().lower())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", type=Path, default=DEFAULT_TAGS)
    ap.add_argument("--limit-recipes", type=int, default=0)
    args = ap.parse_args()

    t0 = time.time()
    OUT_LINES.parent.mkdir(parents=True, exist_ok=True)

    print(f"[{time.time()-t0:6.1f}s] loading {args.tags.name}")
    htc_lookup: dict[str, dict] = {}
    with args.tags.open() as f:
        r = csv.DictReader(f)
        for row in r:
            key = normalize_item(row["item"])
            htc_lookup[key] = {
                "htc_code": row["htc_code"],
                "htc_group": row["htc_group"],
                "htc_family": row["htc_family"],
                "htc_form": row["htc_form"],
                "htc_processing": row["htc_processing"],
                "htc_ptype": row["htc_ptype"],
                "htc_source": row["htc_source"],
                "htc_confidence": float(row["htc_confidence"]),
            }
    print(f"  {len(htc_lookup):,} unique items in lookup")

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
        "htc_code", "htc_group", "htc_family", "htc_form",
        "htc_processing", "htc_ptype", "htc_source", "htc_confidence",
        "match_status",
    ])

    n_rec = n_lines = 0
    n_with_htc = n_high_conf = 0
    n_non_food = 0
    n_unmatched = 0
    n_recipes_full = 0
    by_group: Counter[str] = Counter()
    top_codes: Counter[str] = Counter()

    for rid, title, blob in con.execute(sql):
        n_rec += 1
        try:
            items = json.loads(blob)
        except Exception:
            continue
        if not isinstance(items, list):
            continue

        rec_lines = 0
        rec_coded = 0
        rec_high = 0
        all_calc = True

        for it in items:
            if not isinstance(it, dict):
                continue
            n_lines += 1
            rec_lines += 1
            raw = it.get("item") or ""
            disp = it.get("display") or ""
            grams = it.get("grams") or ""
            key = normalize_item(raw)
            entry = htc_lookup.get(key)
            if entry is None:
                n_unmatched += 1
                line_writer.writerow([
                    rid, title, raw, disp, grams,
                    "", "", "", "", "", "", "no_match", "",
                    "no_match"])
                all_calc = False
                continue
            grp = entry["htc_group"]
            if grp == "N":
                n_non_food += 1
                line_writer.writerow([
                    rid, title, raw, disp, grams,
                    entry["htc_code"], grp, entry["htc_family"], entry["htc_form"],
                    entry["htc_processing"], entry["htc_ptype"],
                    entry["htc_source"], entry["htc_confidence"],
                    "non_food"])
                continue
            if grp == "0":
                n_unmatched += 1
                line_writer.writerow([
                    rid, title, raw, disp, grams,
                    entry["htc_code"], grp, entry["htc_family"], entry["htc_form"],
                    entry["htc_processing"], entry["htc_ptype"],
                    entry["htc_source"], entry["htc_confidence"],
                    "unresolved_group"])
                all_calc = False
                continue
            n_with_htc += 1
            rec_coded += 1
            by_group[grp] += 1
            top_codes[entry["htc_code"]] += 1
            status = "tagged"
            if entry["htc_confidence"] >= 0.6:
                n_high_conf += 1
                rec_high += 1
                status = "high_conf"
            else:
                all_calc = False
            line_writer.writerow([
                rid, title, raw, disp, grams,
                entry["htc_code"], grp, entry["htc_family"], entry["htc_form"],
                entry["htc_processing"], entry["htc_ptype"],
                entry["htc_source"], entry["htc_confidence"],
                status])

        if rec_lines and all_calc:
            n_recipes_full += 1
        if n_rec % 50000 == 0:
            print(f"[{time.time()-t0:6.1f}s] {n_rec:,} recipes processed", flush=True)

    line_w.close()

    summary = {
        "n_recipes": n_rec,
        "n_ingredient_lines": n_lines,
        "n_lines_with_htc": n_with_htc,
        "n_lines_high_conf": n_high_conf,
        "n_lines_non_food": n_non_food,
        "n_lines_unmatched": n_unmatched,
        "pct_lines_with_htc": round(n_with_htc / n_lines, 4) if n_lines else 0,
        "pct_lines_high_conf": round(n_high_conf / n_lines, 4) if n_lines else 0,
        "pct_lines_non_food": round(n_non_food / n_lines, 4) if n_lines else 0,
        "n_recipes_fully_high_conf": n_recipes_full,
        "pct_recipes_fully_high_conf": round(n_recipes_full / n_rec, 4) if n_rec else 0,
        "by_group": dict(by_group),
        "top_codes": top_codes.most_common(25),
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))

    print()
    print(f"recipes:               {n_rec:,}")
    print(f"ingredient lines:      {n_lines:,}")
    print(f"  tagged with HTC:     {n_with_htc:,}  ({summary['pct_lines_with_htc']:.1%})")
    print(f"  high-conf (>=0.6):   {n_high_conf:,}  ({summary['pct_lines_high_conf']:.1%})")
    print(f"  non-food (group=N):  {n_non_food:,}  ({summary['pct_lines_non_food']:.1%})")
    print(f"  unmatched:           {n_unmatched:,}")
    print(f"recipes fully high-conf: {n_recipes_full:,}  "
          f"({summary['pct_recipes_fully_high_conf']:.1%})")
    print()
    print(f"top groups (real food only):")
    for g_, c in by_group.most_common():
        print(f"  {g_}: {c:>9,}")
    print()
    print(f"top 15 HTC codes:")
    for c, n in top_codes.most_common(15):
        print(f"  {n:>9,}  {c}")
    print(f"  -> {OUT_LINES}")
    print(f"  -> {OUT_SUMMARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
