"""Classify every no-candidates pack with a retrieval-root-cause bucket.

Reads the sweep CSV, the pack index, and the existing retail_query_rewrite_plan
to emit one row per no-candidates pack with the specific reason it failed to
produce any Candidate Clean Products. Buckets teed up for action:

- ``zero_matches_rewrite_available``: retrieval returned 0 rows and the rewrite
  plan proposes a different query (run `build_esha_code_query_packs.py` against
  the recommended query and re-sweep; most should land).
- ``zero_matches_no_rewrite``: genuinely no retail equivalent.
- ``classifier_too_aggressive``: retrieval returned 1-99 rows but the pack
  builder pushed every row to the cleanup table. Needs pack-builder loosening.
- ``retrieval_category_mismatch``: retrieval returned 100+ rows but the top
  category is wrong for the ESHA concept. Needs category-scoped re-query.

Outputs ``implementation/output/no_candidates_diagnostic.csv`` and a short
summary MD beside it.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "implementation" / "output"
SWEEP_CSV = OUT / "pack_builder_sweep.csv"
INDEX_CSV = OUT / "esha_code_query_pack_index.csv"
PLAN_CSV = OUT / "retail_query_rewrite_plan.csv"
OUT_CSV = OUT / "no_candidates_diagnostic.csv"
OUT_SUMMARY = OUT / "no_candidates_diagnostic_summary.md"


def classify(total_matches: int, rewrite_plan_row: dict[str, str]) -> tuple[str, str]:
    query_before = (rewrite_plan_row.get("query_before") or "").strip()
    recommended = (rewrite_plan_row.get("recommended_query") or "").strip()
    rewrite_differs = bool(recommended) and recommended != query_before
    if total_matches == 0:
        if rewrite_differs:
            return (
                "zero_matches_rewrite_available",
                "retrieval returned 0 rows; rewrite plan proposes a new query (re-run pack generator)",
            )
        return (
            "zero_matches_no_rewrite",
            "retrieval returned 0 rows and no better query is known (likely no retail equivalent)",
        )
    if 1 <= total_matches <= 99:
        return (
            "classifier_too_aggressive",
            f"retrieval returned {total_matches} rows but pack builder pushed all to cleanup",
        )
    return (
        "retrieval_category_mismatch",
        f"retrieval returned {total_matches} rows across the wrong categories (need category-scoped re-query)",
    )


def main() -> None:
    sweep = {r["esha_code"]: r for r in csv.DictReader(SWEEP_CSV.open(encoding="utf-8"))}
    index = {r["esha_code"]: r for r in csv.DictReader(INDEX_CSV.open(encoding="utf-8"))}
    plan = {r["esha_code"]: r for r in csv.DictReader(PLAN_CSV.open(encoding="utf-8"))}

    fieldnames = [
        "esha_code", "description", "family", "top_category",
        "total_product_matches", "exactness_status",
        "bucket", "suggested_action",
        "query_before", "recommended_query",
    ]
    bucket_counts: Counter[str] = Counter()
    family_bucket: Counter[tuple[str, str]] = Counter()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for code, sweep_row in sweep.items():
            if sweep_row["status"] != "no_candidates":
                continue
            idx_row = index.get(code, {})
            plan_row = plan.get(code, {})
            total = int(idx_row.get("total_product_matches") or 0)
            bucket, suggestion = classify(total, plan_row)
            bucket_counts[bucket] += 1
            family_bucket[(idx_row.get("family") or "(none)", bucket)] += 1
            writer.writerow({
                "esha_code": code,
                "description": idx_row.get("description") or sweep_row.get("description") or "",
                "family": idx_row.get("family") or "",
                "top_category": idx_row.get("top_category") or "",
                "total_product_matches": total,
                "exactness_status": plan_row.get("exactness_status") or "",
                "bucket": bucket,
                "suggested_action": suggestion,
                "query_before": plan_row.get("query_before") or "",
                "recommended_query": plan_row.get("recommended_query") or "",
            })

    total = sum(bucket_counts.values())
    lines = [
        "# No-candidates pack diagnostic",
        "",
        f"- total no-candidates packs: {total}",
        f"- CSV: {OUT_CSV.relative_to(ROOT)}",
        "",
        "## Bucket distribution",
        "",
        "| bucket | count | % |",
        "| --- | ---: | ---: |",
    ]
    for bucket, n in bucket_counts.most_common():
        lines.append(f"| {bucket} | {n} | {n/total*100:.1f}% |")
    lines.extend([
        "",
        "## By family × bucket (top 40)",
        "",
        "| family | bucket | count |",
        "| --- | --- | ---: |",
    ])
    for (family, bucket), count in sorted(family_bucket.items(), key=lambda kv: -kv[1])[:40]:
        lines.append(f"| {family} | {bucket} | {count} |")
    OUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"wrote {OUT_CSV.relative_to(ROOT)}  and {OUT_SUMMARY.relative_to(ROOT)}")
    print(f"bucket counts: {dict(bucket_counts)}")


if __name__ == "__main__":
    main()
