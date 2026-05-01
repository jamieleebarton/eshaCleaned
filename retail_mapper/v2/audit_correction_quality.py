#!/usr/bin/env python3
"""Quality scorecard for DeepSeek FNDDS corrections.

Read-only. Run after build_audit_csv.py to see how many corrections are
clean and where the failures concentrate.

Three metrics:
  1. FNDDS-desc-vs-title agreement — for each corrected row, does the
     new FNDDS desc share at least one meaningful word with the title?
     Catches LLM hallucinations where DeepSeek picked a code that doesn't
     match the product.
  2. FNDDS-family-vs-canonical-path family — does the FNDDS desc's
     implied family match the canonical_path's top-level? E.g., FNDDS
     "Cookie, NFS" → Snack family; if path is at "Dairy > ..." that's
     a leak from a stale FNDDS_CANONICAL_PATH_MAP entry or normalizer
     mis-route.
  3. Master-agreement after correction — same as before, but on the
     corrected set: how many corrections align with master?

Output: console report + retail_mapper/v2/correction_quality_report.csv
        (one row per "suspect" correction with the reason).
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
CORRECTIONS = V2 / "fndds_corrections.csv"
AUDIT = V2 / "full_corpus_audit.csv"
DB = REPO / "data" / "master_products.db"
OUT = V2 / "correction_quality_report.csv"

csv.field_size_limit(sys.maxsize)

# Map FNDDS desc keywords to expected top-level family.
# Used to detect path-family mismatches.
FNDDS_FAMILY_HINTS = [
    (("ice cream", "frozen yogurt", "sherbet", "sorbet", "gelato",
      "ice pop", "popsicle", "frozen dessert"), "Frozen"),
    (("cookie", "biscuit", "macaron", "wafer", "biscotti", "shortbread",
      "candy", "chocolate", "gummy", "lollipop", "marshmallow",
      "popcorn", "pretzel", "chip", "cracker", "trail mix", "granola",
      "nut", "almond", "cashew", "peanut", "pistachio", "snack", "bar"),
     "Snack"),
    (("bread", "bagel", "muffin", "doughnut", "donut", "croissant",
      "danish", "scone", "tortilla", "naan", "flatbread", "cornbread",
      "pita", "cake", "brownie", "cupcake", "pie", "rolls", "buns"),
     "Bakery"),
    (("milk", "cheese", "yogurt", "butter", "cream", "kefir",
      "cottage cheese", "sour cream"), "Dairy"),
    (("juice", "soda", "soft drink", "water", "tea", "coffee",
      "lemonade", "kombucha", "energy drink", "sports drink",
      "protein shake", "sparkling", "cola"), "Beverage"),
    (("beef", "pork", "chicken", "turkey", "ham", "sausage", "bacon",
      "salmon", "tuna", "shrimp", "crab", "fish", "lobster", "seafood",
      "deli", "salami", "prosciutto", "meatball"), "Meat & Seafood"),
    (("apple", "banana", "orange", "lemon", "lime", "carrot", "tomato",
      "potato", "onion", "lettuce", "spinach", "broccoli", "cucumber",
      "pepper", "avocado", "grape", "berry", "strawberry", "blueberry",
      "fresh", "produce", "fruit", "vegetable"), "Produce"),
    (("frozen entree", "frozen dinner", "tv dinner", "pot pie", "burrito",
      "lasagna", "frozen pizza"), "Frozen"),
    (("pasta", "noodle", "sauce", "salsa", "pesto", "soup", "broth",
      "stock", "bouillon", "salad dressing", "vinegar", "oil",
      "spice", "seasoning", "salt", "pepper", "cinnamon", "vanilla",
      "rice", "oat", "quinoa", "barley", "bean", "lentil", "flour",
      "sugar", "honey", "syrup", "pickle", "olive", "mustard",
      "ketchup", "mayonnaise", "jam", "jelly", "preserve",
      "baking mix", "cake mix", "pancake mix"), "Pantry"),
    (("pizza", "sandwich", "wrap", "burrito", "burger", "hot dog",
      "lasagna", "mac and cheese", "salad"), "Meal"),
]


def implied_family(desc: str) -> str | None:
    """Pick the most-likely top-level family from FNDDS desc text.
    Uses WORD-BOUNDARY matching so 'ham' doesn't match 'hamburger',
    'cream' doesn't match 'cream soda' is fine but 'cream' shouldn't
    match 'cream of mushroom soup' for Dairy if soup is in the desc.
    """
    if not desc:
        return None
    d = " " + desc.lower().replace(",", " ").replace("/", " ").replace("(", " ").replace(")", " ") + " "
    for keywords, family in FNDDS_FAMILY_HINTS:
        for kw in keywords:
            # Word-boundary match: keyword surrounded by spaces/punctuation
            kw_lower = kw.lower()
            if f" {kw_lower} " in d or f" {kw_lower}s " in d or f" {kw_lower}-" in d:
                return family
    return None


WORD_RX = re.compile(r"[A-Za-z]+")
STOPWORDS = {"the", "and", "with", "for", "from", "this", "that", "nfs",
             "ns", "as", "to", "fat", "eaten", "added", "without", "made"}


def title_words(s: str) -> set[str]:
    return {w.lower() for w in WORD_RX.findall(s or "")
            if len(w) > 2 and w.lower() not in STOPWORDS}


def main() -> None:
    if not CORRECTIONS.exists():
        raise SystemExit(f"missing {CORRECTIONS}")
    if not AUDIT.exists():
        raise SystemExit(f"missing {AUDIT}")

    # 1. Load corrections
    corrections: dict[str, dict] = {}
    with CORRECTIONS.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            corrections[r["fdc_id"]] = r
    print(f"  corrections to evaluate: {len(corrections):,}")

    # 2. Load corresponding audit rows (current state)
    audit_rows: dict[str, dict] = {}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = r.get("fdc_id", "")
            if fdc in corrections:
                audit_rows[fdc] = {
                    "title": r.get("title", ""),
                    "canonical_path": r.get("canonical_path", ""),
                    "fndds_code": r.get("fndds_code", ""),
                    "fndds_desc": r.get("fndds_desc", ""),
                }

    # 3. Load master FNDDS for agreement check
    master_fndds: dict[str, str] = {}
    if DB.exists():
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("""SELECT p.fdc_id, t.fndds_code FROM products p
                     JOIN product_fndds_tag t ON p.gtin_upc = t.gtin_upc
                     WHERE t.fndds_code IS NOT NULL""")
        for f, code in c.fetchall():
            master_fndds[str(f)] = str(code).strip()
        conn.close()

    # Run checks
    n_total = 0
    n_title_mismatch = 0
    n_family_mismatch = 0
    n_master_match = 0
    n_master_other = 0
    n_master_unknown = 0
    suspects: list[dict] = []

    for fdc, corr in corrections.items():
        n_total += 1
        a = audit_rows.get(fdc)
        if not a:
            continue
        title = a["title"]
        path = a["canonical_path"]
        new_code = corr["new_code"]
        new_desc = corr["new_desc"] or a.get("fndds_desc", "")

        # Check 1: title-vs-desc word overlap
        twords = title_words(title)
        dwords = title_words(new_desc)
        # Remove generic noise
        dwords -= {"food", "kind", "type", "general", "mills"}
        overlap = len(twords & dwords)
        title_match = overlap >= 1 or len(dwords) <= 1

        # Check 2: family match
        expected_family = implied_family(new_desc)
        actual_family = path.split(" > ")[0] if " > " in path else path
        family_match = (expected_family is None
                        or expected_family == actual_family)

        # Check 3: agreement with master
        m = master_fndds.get(fdc, "")
        if not m:
            n_master_unknown += 1
        elif m == new_code:
            n_master_match += 1
        else:
            n_master_other += 1

        if not title_match:
            n_title_mismatch += 1
        if not family_match:
            n_family_mismatch += 1

        if not title_match or not family_match:
            suspects.append({
                "fdc_id": fdc,
                "title": title[:80],
                "new_code": new_code,
                "new_desc": new_desc[:50],
                "current_path": path[:80],
                "expected_family": expected_family or "?",
                "actual_family": actual_family,
                "issue": ("title_mismatch" if not title_match else "")
                    + (" family_mismatch" if not family_match else ""),
                "confidence": corr.get("confidence", ""),
            })

    print()
    print("=== Quality scorecard ===")
    print(f"  total corrections evaluated: {n_total:,}")
    print()
    print(f"  Title vs new FNDDS desc word overlap:")
    print(f"    PASS: {n_total - n_title_mismatch:,} "
          f"({100*(n_total-n_title_mismatch)/max(n_total,1):.1f}%)")
    print(f"    FAIL: {n_title_mismatch:,} "
          f"({100*n_title_mismatch/max(n_total,1):.1f}%)")
    print()
    print(f"  Path top-level vs FNDDS-implied family:")
    print(f"    PASS: {n_total - n_family_mismatch:,} "
          f"({100*(n_total-n_family_mismatch)/max(n_total,1):.1f}%)")
    print(f"    FAIL: {n_family_mismatch:,} "
          f"({100*n_family_mismatch/max(n_total,1):.1f}%)")
    print()
    print(f"  Agreement with master_products.db FNDDS:")
    print(f"    MATCH: {n_master_match:,}")
    print(f"    OTHER: {n_master_other:,} (DeepSeek picked a third code)")
    print(f"    UNKNOWN: {n_master_unknown:,} (no master tag)")
    pct = 100*n_master_match/max(n_master_match+n_master_other,1)
    print(f"    Match rate: {pct:.1f}%")
    print()
    # Family-mismatch breakdown
    if n_family_mismatch:
        family_misses = Counter(
            (s["expected_family"], s["actual_family"]) for s in suspects
            if "family_mismatch" in s["issue"])
        print(f"  Top family mismatches (expected → actual):")
        for (exp, act), n in family_misses.most_common(10):
            print(f"    {n:>5}  {exp} → {act}")

    # Write suspect CSV (sorted by confidence ascending so iffy ones first)
    if suspects:
        suspects.sort(key=lambda x: float(x.get("confidence") or 0))
        cols = list(suspects[0].keys())
        with OUT.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(suspects)
        print()
        print(f"  wrote {OUT.name} ({len(suspects):,} suspect corrections to review)")


if __name__ == "__main__":
    main()
