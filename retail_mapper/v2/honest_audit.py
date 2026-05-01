#!/usr/bin/env python3
"""Honest audit of the current full_corpus_audit.csv.

Pulls a stratified random sample (300 SKUs across 4 buckets), checks each
for title-vs-path coherence using conservative word-boundary matching, and
writes a review CSV the user can eyeball.

Three checks per row:
1. Title-noun-in-path: the title's primary noun (last meaningful word) must
   appear somewhere in the canonical_path family/leaf, OR the path's leaf
   words must appear in the title.
2. Family sanity: known crash patterns flagged (cheese-as-soup, ham-as-pasta,
   etc.).
3. Generic-fallback flag: row landed at a fallback bucket like "Pantry > Sauce"
   or "Snack > Candy" without sub-categorization.

Output: retail_mapper/v2/honest_audit_sample.csv
"""
from __future__ import annotations

import csv
import json
import random
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
AUDIT = V2 / "full_corpus_audit.csv"
DECISIONS = V2 / "path_describe_decisions.jsonl"
SNAP_LOG = V2 / "path_corrections_snap_log.csv"
DB = REPO / "data" / "master_products.db"
OUT = V2 / "honest_audit_sample.csv"

random.seed(42)
csv.field_size_limit(sys.maxsize)

WORD_RX = re.compile(r"[A-Za-z]+")
STOPWORDS = {
    "the", "and", "with", "for", "of", "in", "from", "this", "made",
    "natural", "premium", "fresh", "organic", "all", "100", "size",
    "oz", "lb", "lbs", "pack", "ct", "case", "box", "bag", "bottle",
    "can", "jar", "container", "package", "value", "family", "free",
    "gluten", "low", "fat", "high", "no", "added", "non", "gmo", "kosher",
    "vegan", "vegetarian", "real", "pure", "sugar", "salt",
}

GENERIC_FALLBACKS = {
    "Pantry > Sauces & Salsas > Sauce",
    "Pantry > Spices & Seasonings > Seasoning",
    "Pantry > Soup",
    "Snack > Candy",
    "Snack > Cookies",
    "Snack > Chips",
    "Snack > Crackers",
    "Snack > Bars",
    "Snack > Nuts",
    "Bakery > Bread",
    "Beverage > Juice",
    "Beverage > Soda",
    "Beverage > Tea",
    "Beverage > Coffee",
    "Dairy > Cheese",
    "Dairy > Milk",
    "Dairy > Yogurt",
    "Meat & Seafood > Beef",
    "Meat & Seafood > Pork",
    "Meat & Seafood > Chicken",
    "Meat & Seafood > Turkey",
    "Meat & Seafood > Sausage",
    "Meat & Seafood > Ham",
    "Meat & Seafood > Seafood",
}

# Crash-pattern detector: known bad combinations.
def known_bad(title: str, path: str) -> str:
    t = title.lower()
    p = path.lower()
    if "ham" in t and "pasta" in p and "ham" not in p:
        return "ham titled but path is pasta"
    if "cheese" in t and "soup" in p and "cheese" not in p:
        return "cheese titled but path is soup"
    if "dip" in t and "soup" in p and "dip" not in p:
        return "dip titled but path is soup"
    if any(x in t for x in ["cookie", "biscuit", "macaron"]) and "ice cream" in p:
        return "cookie titled but path is ice cream"
    if "ice cream" in t and any(x in p for x in ["cookie", "candy", "snack"]):
        return "ice cream titled but path is snack"
    if any(x in t for x in ["soda", "cola", "fruit punch"]) and "whiskey" in p:
        return "soft drink titled but path is whiskey"
    if "pretzel" in t and "ice cream" in p:
        return "pretzel titled but path is ice cream"
    return ""


def title_word_set(s: str) -> set[str]:
    return {w.lower() for w in WORD_RX.findall(s or "")
            if len(w) > 2 and w.lower() not in STOPWORDS}


def main() -> None:
    if not AUDIT.exists():
        raise SystemExit(f"missing {AUDIT}")

    # Load DeepSeek-touched fdc set
    deepseek_touched = set()
    if DECISIONS.exists():
        with DECISIONS.open() as fh:
            for line in fh:
                try:
                    deepseek_touched.add(json.loads(line).get("fdc_id", ""))
                except Exception:
                    pass

    # Load snap action per fdc
    snap_action: dict[str, str] = {}
    if SNAP_LOG.exists():
        with SNAP_LOG.open() as fh:
            for r in csv.DictReader(fh):
                snap_action[r["fdc_id"]] = r.get("snap_action", "")

    # Index ingredients from master DB
    print("  loading ingredients from master DB...")
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    ingredients_by_fdc: dict[str, str] = {}
    c.execute("SELECT fdc_id, ingredients_clean, ingredients FROM products")
    for fdc, ic, ir in c.fetchall():
        ingredients_by_fdc[str(fdc)] = (ic or ir or "")[:300]
    conn.close()

    # Bucket every audit row
    buckets: dict[str, list[dict]] = {
        "deepseek_kept": [],
        "deepseek_reverted": [],
        "never_touched": [],
        "plu_stub": [],
    }
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = r.get("fdc_id", "")
            if r.get("match_source") == "ifps_plu_seed":
                buckets["plu_stub"].append(r)
            elif fdc in deepseek_touched:
                action = snap_action.get(fdc, "")
                if action == "revert":
                    buckets["deepseek_reverted"].append(r)
                else:
                    buckets["deepseek_kept"].append(r)
            else:
                buckets["never_touched"].append(r)

    print(f"  bucket sizes:")
    for k, v in buckets.items():
        print(f"    {k:25s}  {len(v):>8,}")

    # Sample 75 from each bucket (300 total)
    sample_rows: list[dict] = []
    for bucket_name, rows in buckets.items():
        n_to_take = min(75, len(rows))
        if n_to_take == 0:
            continue
        chosen = random.sample(rows, n_to_take)
        for r in chosen:
            fdc = r.get("fdc_id", "")
            title = r.get("title", "")[:120]
            path = r.get("canonical_path", "")
            ing = ingredients_by_fdc.get(fdc, "")[:200]
            t_words = title_word_set(title)
            p_words = title_word_set(path)
            shared = t_words & p_words
            # Quick verdicts
            verdict = ""
            note = ""
            bad = known_bad(title, path)
            if bad:
                verdict = "WRONG"
                note = bad
            elif path in GENERIC_FALLBACKS:
                verdict = "BORDERLINE"
                note = "landed at generic fallback (no sub-type)"
            elif not shared and len(p_words) > 1:
                verdict = "CHECK"
                note = "no title-path word overlap"
            else:
                verdict = "OK"
                note = f"shared: {','.join(sorted(shared))[:50]}"
            sample_rows.append({
                "bucket": bucket_name,
                "fdc_id": fdc,
                "title": title[:80],
                "ingredients": ing[:120],
                "canonical_path": path,
                "verdict": verdict,
                "note": note,
            })

    # Write CSV
    cols = ["bucket", "fdc_id", "title", "ingredients", "canonical_path",
            "verdict", "note"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        sample_rows.sort(key=lambda r: (r["verdict"], r["bucket"]))
        w.writerows(sample_rows)

    # Tally per bucket
    print()
    print("=== AUDIT VERDICT BY BUCKET ===")
    print(f"{'bucket':25s}  {'OK':>5s}  {'BORDERLINE':>10s}  {'CHECK':>5s}  {'WRONG':>5s}  {'TOTAL':>5s}  {'OK%':>5s}")
    for bucket_name in buckets:
        rows = [r for r in sample_rows if r["bucket"] == bucket_name]
        if not rows:
            continue
        cnt = Counter(r["verdict"] for r in rows)
        total = len(rows)
        ok_pct = 100 * cnt["OK"] / total if total else 0
        print(f"{bucket_name:25s}  {cnt['OK']:>5}  {cnt['BORDERLINE']:>10}  "
              f"{cnt['CHECK']:>5}  {cnt['WRONG']:>5}  {total:>5}  {ok_pct:>4.0f}%")

    print()
    print(f"  wrote review file: {OUT.name} ({len(sample_rows)} samples)")


if __name__ == "__main__":
    main()
