#!/usr/bin/env python3
"""Build a side-by-side finalized retail taxonomy corpus.

This is intentionally non-destructive: it reads full_corpus_cleaned.csv plus
reference matches from full_corpus_enriched.csv, applies taxonomy_finalizer.py,
and writes:

  - full_corpus_finalized.csv
  - full_corpus_finalized_report.json
"""
from __future__ import annotations

import csv
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from taxonomy_finalizer import apply_finalized_taxonomy, path_defects


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
CLEANED = V2 / "full_corpus_cleaned.csv"
ENRICHED = V2 / "full_corpus_enriched.csv"
OUT = V2 / "full_corpus_finalized.csv"
REPORT = V2 / "full_corpus_finalized_report.json"

csv.field_size_limit(sys.maxsize)


REFERENCE_COLUMNS = [
    "fndds_code",
    "sr28_code",
    "esha_code",
    "match_source",
    "match_score",
    "portions_json",
    "matched_key",
]

OUT_COLUMNS = [
    "fdc_id",
    "title",
    "branded_food_category",
    "category_path_fixed",
    "product_identity_fixed",
    "canonical_path",
    "variant",
    "flavor",
    "claims",
    "form_texture_cut",
    "modifier",
    "retail_leaf_path",
    *REFERENCE_COLUMNS,
]

ENRICHED_COLUMNS = [
    "fdc_id",
    "title",
    "branded_food_category",
    "category_path_fixed",
    "product_identity_fixed",
    "canonical_path",
    "variant",
    "flavor",
    "modifier",
    "retail_leaf_path",
    "fndds_code",
    "sr28_code",
    "esha_code",
    "match_source",
    "match_score",
    "portions_json",
    "matched_key",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--replace-enriched",
        action="store_true",
        help="also rewrite full_corpus_enriched.csv with the finalized enriched schema",
    )
    return parser.parse_args()


def load_enriched() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with ENRICHED.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            fdc = (row.get("fdc_id") or "").strip()
            if not fdc:
                continue
            out[fdc] = {
                "category_path_fixed": row.get("category_path_fixed", ""),
                "product_identity_fixed": row.get("product_identity_fixed", ""),
                "canonical_path": row.get("canonical_path", ""),
                "modifier": row.get("modifier", ""),
                "retail_leaf_path": row.get("retail_leaf_path", ""),
                **{col: row.get(col, "") for col in REFERENCE_COLUMNS},
            }
    return out


def add_defects(counter: Counter, defects: list[str]) -> None:
    if not defects:
        counter["clean_rows"] += 1
        return
    counter["defect_rows"] += 1
    for defect in defects:
        counter[defect] += 1


def main() -> None:
    args = parse_args()
    if not CLEANED.exists():
        raise SystemExit(f"missing {CLEANED}")
    if not ENRICHED.exists():
        raise SystemExit(f"missing {ENRICHED}")

    enriched = load_enriched()
    row_count = 0
    fdc_counts: Counter = Counter()
    before_defects: Counter = Counter()
    after_defects: Counter = Counter()
    before_canonical: Counter = Counter()
    after_canonical: Counter = Counter()
    after_retail_leaf: Counter = Counter()
    changed_examples: list[dict[str, str]] = []

    with CLEANED.open(encoding="utf-8") as src, OUT.open("w", encoding="utf-8", newline="") as dst:
        rdr = csv.DictReader(src)
        wtr = csv.DictWriter(dst, fieldnames=OUT_COLUMNS)
        wtr.writeheader()

        for row in rdr:
            row_count += 1
            fdc = (row.get("fdc_id") or "").strip()
            fdc_counts[fdc] += 1
            extra = enriched.get(fdc, {})

            before = dict(row)
            before.update({
                "canonical_path": extra.get("canonical_path", row.get("canonical_path", "")),
                "modifier": extra.get("modifier", ""),
                "retail_leaf_path": extra.get("retail_leaf_path", ""),
            })
            add_defects(before_defects, path_defects(before))
            before_canonical[before.get("canonical_path", "")] += 1

            finalized = dict(row)
            for col in REFERENCE_COLUMNS:
                finalized[col] = extra.get(col, "")
            old_path = before.get("canonical_path", "")
            old_leaf = before.get("retail_leaf_path", "")
            apply_finalized_taxonomy(finalized)

            add_defects(after_defects, path_defects(finalized))
            after_canonical[finalized["canonical_path"]] += 1
            after_retail_leaf[finalized["retail_leaf_path"]] += 1

            if len(changed_examples) < 50 and (
                finalized["canonical_path"] != old_path
                or finalized["retail_leaf_path"] != old_leaf
            ):
                changed_examples.append({
                    "fdc_id": fdc,
                    "title": finalized.get("title", ""),
                    "old_canonical_path": old_path,
                    "new_canonical_path": finalized["canonical_path"],
                    "old_retail_leaf_path": old_leaf,
                    "new_retail_leaf_path": finalized["retail_leaf_path"],
                })

            wtr.writerow({col: finalized.get(col, "") for col in OUT_COLUMNS})

    report = {
        "rows": row_count,
        "unique_fdc_ids": len([k for k in fdc_counts if k]),
        "duplicate_fdc_extra_rows": sum(max(0, count - 1) for count in fdc_counts.values()),
        "distinct_canonical_paths_before": len(before_canonical),
        "distinct_canonical_paths_after": len(after_canonical),
        "distinct_retail_leaf_paths_after": len(after_retail_leaf),
        "before_defects": dict(before_defects),
        "after_defects": dict(after_defects),
        "top_after_canonical_paths": after_canonical.most_common(25),
        "changed_examples": changed_examples,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.replace_enriched:
        with OUT.open(encoding="utf-8") as src, ENRICHED.open("w", encoding="utf-8", newline="") as dst:
            rdr = csv.DictReader(src)
            wtr = csv.DictWriter(dst, fieldnames=ENRICHED_COLUMNS)
            wtr.writeheader()
            for row in rdr:
                wtr.writerow({col: row.get(col, "") for col in ENRICHED_COLUMNS})
        print(f"rewrote {ENRICHED} from finalized taxonomy")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"wrote {REPORT}")
    print(json.dumps({
        "rows": report["rows"],
        "distinct_canonical_paths_before": report["distinct_canonical_paths_before"],
        "distinct_canonical_paths_after": report["distinct_canonical_paths_after"],
        "before_defect_rows": before_defects.get("defect_rows", 0),
        "after_defect_rows": after_defects.get("defect_rows", 0),
    }, indent=2))


if __name__ == "__main__":
    main()
