from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INDEX_CSV = ROOT / "implementation" / "output" / "esha_code_query_pack_index.csv"
OUT_CSV = ROOT / "implementation" / "output" / "esha_code_category_spread.csv"
OUT_MD = ROOT / "implementation" / "output" / "esha_code_category_spread_summary.md"

FIELDS = [
    "esha_code",
    "description",
    "family",
    "query",
    "total_product_matches",
    "category_count",
    "top_category",
    "top_category_count",
    "top_category_share",
    "suspicion_score",
    "flags",
]


def flags_for(query: str, category_count: int, top_share: float, total_matches: int) -> list[str]:
    flags: list[str] = []
    if query.count("AND") == 0:
        flags.append("single_clause_query")
    if category_count >= 20:
        flags.append("very_high_category_spread")
    if top_share <= 0.2 and total_matches >= 100:
        flags.append("weak_dominant_category")
    if total_matches >= 1000:
        flags.append("huge_result_set")
    return flags


def suspicion_score(category_count: int, top_share: float, total_matches: int) -> float:
    if total_matches <= 0 or category_count <= 1:
        return 0.0
    return category_count * (1.0 - top_share) * math.log10(total_matches + 1.0)


def main() -> None:
    rows: list[dict[str, str]] = []
    category_hist = Counter()
    flagged = 0

    with INDEX_CSV.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            total_matches = int(row.get("total_product_matches") or 0)
            category_count = int(row.get("category_count") or 0)
            top_category_count = int(row.get("top_category_count") or 0)
            top_share = (top_category_count / total_matches) if total_matches else 0.0
            flags = flags_for(row.get("query", ""), category_count, top_share, total_matches)
            score = suspicion_score(category_count, top_share, total_matches)
            if flags:
                flagged += 1
            category_hist[category_count] += 1
            rows.append(
                {
                    "esha_code": row.get("esha_code", ""),
                    "description": row.get("description", ""),
                    "family": row.get("family", ""),
                    "query": row.get("query", ""),
                    "total_product_matches": str(total_matches),
                    "category_count": str(category_count),
                    "top_category": row.get("top_category", ""),
                    "top_category_count": str(top_category_count),
                    "top_category_share": f"{top_share:.4f}",
                    "suspicion_score": f"{score:.4f}",
                    "flags": "|".join(flags),
                }
            )

    rows.sort(
        key=lambda row: (
            -float(row["suspicion_score"]),
            -int(row["category_count"]),
            -int(row["total_product_matches"]),
            row["esha_code"],
        )
    )

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    top = rows[:25]
    max_spread = sum(1 for row in rows if int(row["category_count"]) >= 20)
    single_clause = sum(1 for row in rows if "single_clause_query" in row["flags"].split("|"))
    weak_top = sum(1 for row in rows if "weak_dominant_category" in row["flags"].split("|"))

    summary_lines = [
        "# ESHA Code Category Spread Audit",
        "",
        f"- codes scanned: {len(rows)}",
        f"- codes flagged: {flagged}",
        f"- codes with >=20 branded categories: {max_spread}",
        f"- codes with single-clause query: {single_clause}",
        f"- codes with weak dominant category: {weak_top}",
        "",
        "## Category Count Distribution",
        "",
        "| category_count | code_count |",
        "| ---: | ---: |",
    ]
    for category_count, code_count in sorted(category_hist.items()):
        summary_lines.append(f"| {category_count} | {code_count} |")

    summary_lines.extend(
        [
            "",
            "## Top Suspect Codes",
            "",
            "| esha_code | family | category_count | top_share | total_matches | top_category | flags | description | query |",
            "| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for row in top:
        summary_lines.append(
            "| {esha_code} | {family} | {category_count} | {top_category_share} | {total_product_matches} | {top_category} | {flags} | {description} | `{query}` |".format(
                **row
            )
        )

    OUT_MD.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
