from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from category_walk_excludes import parse_md_tables


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "implementation" / "output"
INDEX_CSV = OUT / "esha_code_query_pack_index.csv"
OUT_CSV = OUT / "esha_code_category_aggregation.csv"
OUT_MD = OUT / "esha_code_category_aggregation_summary.md"

FIELDS = [
    "esha_code",
    "description",
    "family",
    "query",
    "distinct_category_count",
    "category",
    "category_count",
    "signal",
    "sample_row_count",
    "sample_titles",
    "sample_gtins",
    "pack_path",
]


def parse_category_table(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    section = False
    header: list[str] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            section = line == "## Categories Returned By Query"
            header = None
            continue
        if not section or not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= {"-", ":"} for c in cells if c):
            continue
        if header is None:
            header = cells
            continue
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def main() -> None:
    per_code_rows: list[dict[str, str]] = []
    category_hist = Counter()
    top_spread: list[tuple[int, str, str, str]] = []

    with INDEX_CSV.open(newline="", encoding="utf-8", errors="replace") as handle:
        for index_row in csv.DictReader(handle):
            pack_path = Path(index_row["pack_path"])
            if not pack_path.exists():
                continue
            text = pack_path.read_text(encoding="utf-8", errors="replace")
            category_rows = parse_category_table(text)
            tables = parse_md_tables(text)

            sample_titles_by_category: dict[str, list[str]] = defaultdict(list)
            sample_gtins_by_category: dict[str, list[str]] = defaultdict(list)
            sample_row_count: Counter[str] = Counter()

            for section in ("candidate", "cleanup"):
                for row in tables[section]:
                    category = (row.get("category") or "").strip()
                    if not category:
                        continue
                    sample_row_count[category] += 1
                    title = (row.get("description") or "").strip()
                    gtin = (row.get("gtin_upc") or "").strip()
                    if title and title not in sample_titles_by_category[category] and len(sample_titles_by_category[category]) < 5:
                        sample_titles_by_category[category].append(title)
                    if gtin and gtin not in sample_gtins_by_category[category] and len(sample_gtins_by_category[category]) < 5:
                        sample_gtins_by_category[category].append(gtin)

            distinct_categories = len(category_rows)
            category_hist[distinct_categories] += 1
            top_spread.append(
                (
                    distinct_categories,
                    index_row["esha_code"],
                    index_row["description"],
                    index_row["query"],
                )
            )

            for category_row in category_rows:
                category = (category_row.get("category") or "").strip()
                per_code_rows.append(
                    {
                        "esha_code": index_row["esha_code"],
                        "description": index_row["description"],
                        "family": index_row["family"],
                        "query": index_row["query"],
                        "distinct_category_count": str(distinct_categories),
                        "category": category,
                        "category_count": category_row.get("count", ""),
                        "signal": category_row.get("signal", ""),
                        "sample_row_count": str(sample_row_count.get(category, 0)),
                        "sample_titles": " || ".join(sample_titles_by_category.get(category, [])),
                        "sample_gtins": " | ".join(sample_gtins_by_category.get(category, [])),
                        "pack_path": index_row["pack_path"],
                    }
                )

    per_code_rows.sort(
        key=lambda row: (
            -int(row["distinct_category_count"] or 0),
            row["esha_code"],
            -int(row["category_count"] or 0),
            row["category"],
        )
    )

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(per_code_rows)

    top_spread.sort(reverse=True)
    summary_lines = [
        "# ESHA Code Category Aggregation",
        "",
        f"- code/category rows: {len(per_code_rows)}",
        f"- codes scanned: {sum(category_hist.values())}",
        "",
        "## Distinct Category Count Distribution",
        "",
        "| distinct_category_count | code_count |",
        "| ---: | ---: |",
    ]
    for distinct_count, code_count in sorted(category_hist.items()):
        summary_lines.append(f"| {distinct_count} | {code_count} |")

    summary_lines.extend(
        [
            "",
            "## Highest Spread Codes",
            "",
            "| esha_code | distinct_category_count | description | query |",
            "| --- | ---: | --- | --- |",
        ]
    )
    seen_codes: set[str] = set()
    for distinct_count, esha_code, description, query in top_spread:
        if esha_code in seen_codes:
            continue
        seen_codes.add(esha_code)
        summary_lines.append(f"| {esha_code} | {distinct_count} | {description} | `{query}` |")
        if len(seen_codes) >= 50:
            break

    OUT_MD.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
