"""
Bank the RFT routing wins as a clean replacement product → ESHA map.

Inputs:
  implementation/output/rft_v2/scale/full_corpus_routes.csv.gz (per-product RFT routes)
  implementation/output/product_to_best_esha_full_map.csv      (old pipeline map)

Outputs:
  implementation/output/rft_v2/rft_v2_product_to_esha.csv   one row per product, new map
  implementation/output/rft_v2/rft_v2_assignments_diff.csv   only rows where RFT changes assignment
  implementation/output/rft_v2/rft_v2_summary.json           change counts

Verdict tiers map to assignment behaviour:
  EXACT          auto_assigned    score=1.0
  STRONG         auto_assigned    score=0.85
  GENERIC        auto_assigned    score=0.70  (generic head match, no specific facet)
  WEAK           review           score=0.50  (best-available but flagged)
  NEEDS_NEW_LEAF unassigned       score=0.00  (taxonomy gap; no leaf yet)
  NO_IDENTITY    unassigned       score=0.00  (no identifiable food in input)
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
ROUTES = ROOT / "implementation/output/rft_v2/scale/full_corpus_routes.csv.gz"
OLD_MAP_CLEAN = ROOT / "implementation/output/product_to_best_esha_full_map.vIdentity.csv"
OLD_MAP = OLD_MAP_CLEAN if OLD_MAP_CLEAN.exists() else ROOT / "implementation/output/product_to_best_esha_full_map.csv"
OUT_DIR = ROOT / "implementation/output/rft_v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NEW_MAP = OUT_DIR / "rft_v2_product_to_esha.csv"
DIFF = OUT_DIR / "rft_v2_assignments_diff.csv"
SUMMARY = OUT_DIR / "rft_v2_summary.json"

csv.field_size_limit(sys.maxsize)

VERDICT_SCORE = {
    "EXACT": 1.0,
    "STRONG": 0.85,
    "GENERIC": 0.70,
    "WEAK": 0.50,
    "NEEDS_NEW_LEAF": 0.0,
    "NO_IDENTITY_NODE": 0.0,
}

VERDICT_STATUS = {
    "EXACT": "auto_assigned",
    "STRONG": "auto_assigned",
    "GENERIC": "auto_assigned",
    "WEAK": "review",
    "NEEDS_NEW_LEAF": "unassigned",
    "NO_IDENTITY_NODE": "unassigned",
}


def product_key(row: dict[str, str]) -> str:
    return (row.get("fdc_id") or "").strip() or (row.get("gtin_upc") or "").strip()


def main():
    print("Loading old pipeline map…", flush=True)
    old: dict[str, dict] = {}
    with OLD_MAP.open(encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            key = product_key(r)
            if key:
                old[key] = r
    print(f"  {len(old):,} old rows")

    print("Streaming routes and writing new map…", flush=True)
    counters = Counter()
    agree_by_status = Counter()
    disagree_by_status = Counter()
    fill_gap = 0           # RFT auto-assigned where old was empty
    unassigned_kept = 0    # RFT couldn't, old had something
    diff_rows = []
    n_written = 0

    with gzip.open(ROUTES, "rt") as fr, NEW_MAP.open("w", newline="") as fw:
        rin = csv.DictReader(fr)
        wout = csv.writer(fw)
        wout.writerow([
            "gtin_upc", "fdc_id", "product_description",
            "brand_owner", "brand_name", "branded_food_category",
            # New RFT assignment
            "rft_esha_code", "rft_esha_description", "rft_head",
            "rft_score", "rft_status",
            "rft_verdict", "rft_leaf_id", "rft_leaf_canonical",
            "rft_sr28_code", "rft_fndds_code",
            "rft_retail_attrs", "rft_brand_stripped",
            "rft_missing_from_leaf", "rft_leaf_extra_facets",
            # Old assignment (preserved for diffing / fallback)
            "old_esha_code", "old_esha_description",
            "old_score", "old_assignment_source",
            # Comparison
            "agreement",
        ])
        for r in rin:
            key = product_key(r)
            old_row = old.get(key, {})
            verdict = r["verdict"]
            counters[verdict] += 1

            rft_code = r.get("esha_code") or ""
            rft_desc = r.get("esha_desc") or ""
            score = VERDICT_SCORE.get(verdict, 0.0)
            status = VERDICT_STATUS.get(verdict, "unassigned")

            old_code = (old_row.get("best_esha_code") or "").strip()
            old_desc = (old_row.get("best_esha_description") or "").strip()
            old_src = (old_row.get("assignment_source") or "").strip()
            old_score = (old_row.get("score_num") or "").strip()

            # Agreement classification
            if rft_code and old_code:
                if rft_code == old_code:
                    agreement = "AGREE"
                    agree_by_status[status] += 1
                else:
                    agreement = "DISAGREE"
                    disagree_by_status[status] += 1
            elif rft_code and not old_code:
                agreement = "RFT_FILL"
                fill_gap += 1
            elif old_code and not rft_code:
                agreement = "OLD_KEPT"
                unassigned_kept += 1
            else:
                agreement = "BOTH_EMPTY"

            wout.writerow([
                r.get("gtin_upc", ""), r.get("fdc_id", ""),
                r.get("input_raw") or old_row.get("product_description", ""),
                old_row.get("brand_owner", ""),
                old_row.get("brand_name", ""),
                old_row.get("branded_food_category", ""),
                rft_code, rft_desc, r.get("head", ""),
                f"{score:.2f}", status,
                verdict,
                r.get("leaf_id", ""), r.get("leaf_canonical", ""),
                r.get("sr28_code", ""), r.get("fndds_code", ""),
                r.get("retail_attrs", ""), r.get("stripped_brands", ""),
                r.get("missing_from_leaf", ""), r.get("leaf_extra_facets", ""),
                old_code, old_desc, old_score, old_src,
                agreement,
            ])

            # Capture diffs (only changes worth reviewing)
            if agreement in ("DISAGREE", "RFT_FILL", "OLD_KEPT"):
                if len(diff_rows) < 100000:  # cap for the diff CSV
                    diff_rows.append({
                        "gtin_upc": r.get("gtin_upc", ""),
                        "fdc_id":   r.get("fdc_id", ""),
                        "product_description": r.get("input_raw", ""),
                        "verdict": verdict,
                        "rft_status": status,
                        "rft_esha":  f"{rft_code} {rft_desc[:50]}",
                        "old_esha":  f"{old_code} {old_desc[:50]}",
                        "agreement": agreement,
                    })
            n_written += 1

    with DIFF.open("w", newline="") as f:
        if diff_rows:
            w = csv.DictWriter(f, fieldnames=list(diff_rows[0].keys()))
            w.writeheader()
            w.writerows(diff_rows)

    n_total = n_written
    n_auto = sum(counters[v] for v in ("EXACT", "STRONG", "GENERIC"))
    n_review = counters["WEAK"]
    n_unassigned = counters["NEEDS_NEW_LEAF"] + counters["NO_IDENTITY_NODE"]

    summary = {
        "n_products": n_total,
        "by_verdict": dict(counters),
        "by_status": {
            "auto_assigned": n_auto,
            "review": n_review,
            "unassigned": n_unassigned,
        },
        "agree_with_old": dict(agree_by_status),
        "disagree_with_old": dict(disagree_by_status),
        "rft_filled_gap": fill_gap,
        "old_kept_rft_blank": unassigned_kept,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2))

    print(f"\n{'='*70}")
    print(f"BANK-WINS SUMMARY  ({n_total:,} products)")
    print(f"{'='*70}")
    print(f"\nBy status:")
    print(f"  auto_assigned   {n_auto:>8,}  ({100*n_auto/n_total:5.1f}%)  "
          "EXACT + STRONG + GENERIC")
    print(f"  review          {n_review:>8,}  ({100*n_review/n_total:5.1f}%)  "
          "WEAK")
    print(f"  unassigned      {n_unassigned:>8,}  ({100*n_unassigned/n_total:5.1f}%)  "
          "NEEDS_NEW_LEAF + NO_IDENTITY_NODE")

    print(f"\nAgreement vs old pipeline:")
    print(f"  agree (auto)        {agree_by_status['auto_assigned']:>8,}")
    print(f"  agree (review)      {agree_by_status['review']:>8,}")
    print(f"  disagree (auto)     {disagree_by_status['auto_assigned']:>8,}  ← review these for correctness")
    print(f"  disagree (review)   {disagree_by_status['review']:>8,}")
    print(f"  rft filled empty    {fill_gap:>8,}  ← new wins")
    print(f"  old kept (rft NA)   {unassigned_kept:>8,}  ← keep old for these or mark for review")

    print(f"\nFiles:")
    print(f"  {NEW_MAP.relative_to(ROOT)}     ({n_total:,} rows, the replacement map)")
    print(f"  {DIFF.relative_to(ROOT)} ({len(diff_rows):,} rows, just the diffs)")
    print(f"  {SUMMARY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
