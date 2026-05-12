from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "implementation" / "output" / "esha_code_category_aggregation.csv"
OUT_CSV = ROOT / "implementation" / "output" / "esha_single_category_fix_queue.csv"
OUT_MD = ROOT / "implementation" / "output" / "esha_single_category_fix_queue_summary.md"

FIELDS = [
    "esha_code",
    "description",
    "family",
    "query",
    "distinct_category_count",
    "total_rows_seen",
    "dominant_category",
    "dominant_count",
    "dominant_share",
    "off_category_count",
    "off_category_share",
    "top_off_categories",
    "dominant_sample_titles",
    "needs_fix",
]


def main() -> None:
    by_code: dict[str, list[dict[str, str]]] = defaultdict(list)
    with SRC.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            by_code[row["esha_code"]].append(row)

    out_rows: list[dict[str, str]] = []
    for code, rows in by_code.items():
        rows = sorted(rows, key=lambda row: (-int(row["category_count"] or 0), row["category"]))
        total_rows_seen = sum(int(row["category_count"] or 0) for row in rows)
        dominant = rows[0] if rows else None
        dominant_count = int(dominant["category_count"] or 0) if dominant else 0
        dominant_share = dominant_count / total_rows_seen if total_rows_seen else 0.0
        off_count = total_rows_seen - dominant_count
        off_share = off_count / total_rows_seen if total_rows_seen else 0.0
        off_categories = [
            f"{row['category']} ({row['category_count']})"
            for row in rows[1:6]
            if int(row["category_count"] or 0) > 0
        ]
        needs_fix = (
            len(rows) > 1
            and (
                dominant_share < 0.95
                or off_count >= 5
                or len(rows) > 3
            )
        )
        out_rows.append(
            {
                "esha_code": code,
                "description": rows[0]["description"],
                "family": rows[0]["family"],
                "query": rows[0]["query"],
                "distinct_category_count": rows[0]["distinct_category_count"],
                "total_rows_seen": str(total_rows_seen),
                "dominant_category": dominant["category"] if dominant else "",
                "dominant_count": str(dominant_count),
                "dominant_share": f"{dominant_share:.4f}",
                "off_category_count": str(off_count),
                "off_category_share": f"{off_share:.4f}",
                "top_off_categories": " | ".join(off_categories),
                "dominant_sample_titles": dominant.get("sample_titles", "") if dominant else "",
                "needs_fix": "1" if needs_fix else "0",
            }
        )

    out_rows.sort(
        key=lambda row: (
            row["needs_fix"] != "1",
            -int(row["distinct_category_count"] or 0),
            float(row["dominant_share"]),
            -int(row["off_category_count"] or 0),
            row["esha_code"],
        )
    )

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    needs_fix_rows = [row for row in out_rows if row["needs_fix"] == "1"]
    whole_milk = next((row for row in out_rows if row["esha_code"] == "1"), None)
    summary = [
        "# Single-Category Fix Queue",
        "",
        f"- codes scanned: {len(out_rows)}",
        f"- codes flagged for fix: {len(needs_fix_rows)}",
        "",
    ]
    if whole_milk:
        summary.extend(
            [
                "## Whole Milk Example",
                "",
                f"- ESHA `1`: {whole_milk['description']}",
                f"- query: `{whole_milk['query']}`",
                f"- distinct categories: {whole_milk['distinct_category_count']}",
                f"- dominant category: `{whole_milk['dominant_category']}` ({whole_milk['dominant_count']} / share {whole_milk['dominant_share']})",
                f"- off-category count: {whole_milk['off_category_count']} / share {whole_milk['off_category_share']}",
                f"- top off-categories: {whole_milk['top_off_categories']}",
                "",
            ]
        )
    summary.extend(
        [
            "## Top Fix Queue",
            "",
            "| esha_code | family | spread | dominant_share | dominant_category | off_category_count | description | query | top_off_categories |",
            "| --- | --- | ---: | ---: | --- | ---: | --- | --- | --- |",
        ]
    )
    for row in needs_fix_rows[:100]:
        summary.append(
            f"| {row['esha_code']} | {row['family']} | {row['distinct_category_count']} | {row['dominant_share']} | {row['dominant_category']} | {row['off_category_count']} | {row['description']} | `{row['query']}` | {row['top_off_categories']} |"
        )

    OUT_MD.write_text("\n".join(summary) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
