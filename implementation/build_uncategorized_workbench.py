from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

import build_category_workbench as category_workbench
import build_esha_code_query_packs as packs
import summarize_retail_query_baseline as baseline


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN_CSV = baseline.DEFAULT_PLAN_CSV
DEFAULT_OUT_DIR = ROOT / "implementation" / "output" / "uncategorized_workbench"


def significant_query_terms(row: dict[str, str], limit: int = 3) -> tuple[str, ...]:
    raw_terms = category_workbench.split_terms(row.get("query_terms_before", ""))
    filtered = [
        term
        for term in raw_terms
        if term
        and term not in packs.GENERIC_QUERY_TERMS
        and term not in packs.STATE_OR_PROCESS_TERMS
    ]
    chosen = filtered or raw_terms
    return tuple(chosen[:limit]) if chosen else ("no_query_terms",)


def bucket_key_for_row(row: dict[str, str]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    family = str(row.get("family") or "unknown").strip() or "unknown"
    query_terms = significant_query_terms(row)
    semantic_filters = tuple(category_workbench.split_terms(row.get("semantic_filter_terms", ""))[:2])
    return family, query_terms, semantic_filters


def bucket_label(query_terms: tuple[str, ...], semantic_filters: tuple[str, ...]) -> str:
    left = " | ".join(query_terms) if query_terms else "no_query_terms"
    if semantic_filters:
        return f"{left} :: {' | '.join(semantic_filters)}"
    return left


def summarize_bucket_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[bucket_key_for_row(row)].append(row)
    out: list[dict[str, object]] = []
    for (family, query_terms, semantic_filters), bucket_rows in sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), item[0][0], item[0][1], item[0][2]),
    ):
        out.append(
            {
                "family": family,
                "bucket_slug": category_workbench.category_slug(
                    f"{family}__{bucket_label(query_terms, semantic_filters)}"
                ),
                "bucket_label": bucket_label(query_terms, semantic_filters),
                "rows": len(bucket_rows),
                "query_terms": " | ".join(query_terms),
                "semantic_filters": " | ".join(semantic_filters),
                "example_codes": " | ".join(row["esha_code"] for row in bucket_rows[:5]),
                "example_descriptions": " | ".join(row["description"] for row in bucket_rows[:3]),
            }
        )
    return out


def write_family_summary(path: Path, family: str, rows: list[dict[str, str]], bucket_rows: list[dict[str, object]]) -> None:
    reason_counts = Counter(row.get("reason", "") for row in rows)
    semantic_filters = Counter()
    query_terms = Counter()
    for row in rows:
        semantic_filters.update(category_workbench.split_terms(row.get("semantic_filter_terms", "")))
        query_terms.update(significant_query_terms(row))
    lines = [
        f"# Uncategorized Family Workbench: {family}",
        "",
        f"- rows: {len(rows)}",
        f"- top buckets: {min(len(bucket_rows), 25)} shown",
        "",
        "## Top Reasons",
        "",
        "| reason | count |",
        "| --- | ---: |",
    ]
    for reason, count in reason_counts.most_common(10):
        lines.append(f"| {reason or 'unknown'} | {count} |")
    lines.extend(
        [
            "",
            "## Frequent Query Terms",
            "",
            "| term | count |",
            "| --- | ---: |",
        ]
    )
    for term, count in query_terms.most_common(20):
        lines.append(f"| {term} | {count} |")
    lines.extend(
        [
            "",
            "## Frequent Semantic Filters",
            "",
            "| term | count |",
            "| --- | ---: |",
        ]
    )
    for term, count in semantic_filters.most_common(20):
        lines.append(f"| {term} | {count} |")
    lines.extend(
        [
            "",
            "## Top Buckets",
            "",
            "| rows | query terms | semantic filters | example codes | example descriptions |",
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    for bucket in bucket_rows[:25]:
        lines.append(
            f"| {bucket['rows']} | {bucket['query_terms']} | {bucket['semantic_filters']} | "
            f"{bucket['example_codes']} | {bucket['example_descriptions']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_outputs(rows: list[dict[str, str]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    category_workbench.write_rows(out_dir / "rows.csv", fieldnames, rows)

    family_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        family_groups[str(row.get("family") or "unknown").strip() or "unknown"].append(row)

    family_index: list[dict[str, object]] = []
    all_bucket_rows: list[dict[str, object]] = []
    for family, family_rows in sorted(family_groups.items(), key=lambda item: (-len(item[1]), item[0])):
        family_dir = out_dir / category_workbench.category_slug(family)
        family_dir.mkdir(parents=True, exist_ok=True)
        category_workbench.write_rows(family_dir / "rows.csv", fieldnames, family_rows)
        bucket_rows = summarize_bucket_rows(family_rows)
        category_workbench.write_rows(
            family_dir / "bucket_index.csv",
            [
                "family",
                "bucket_slug",
                "bucket_label",
                "rows",
                "query_terms",
                "semantic_filters",
                "example_codes",
                "example_descriptions",
            ],
            bucket_rows,
        )
        write_family_summary(family_dir / "summary.md", family, family_rows, bucket_rows)
        family_index.append(
            {
                "family": family,
                "rows": len(family_rows),
                "bucket_count": len(bucket_rows),
                "top_bucket": bucket_rows[0]["bucket_label"] if bucket_rows else "",
                "top_bucket_rows": bucket_rows[0]["rows"] if bucket_rows else 0,
            }
        )
        all_bucket_rows.extend(bucket_rows)

    category_workbench.write_rows(
        out_dir / "family_index.csv",
        ["family", "rows", "bucket_count", "top_bucket", "top_bucket_rows"],
        family_index,
    )
    category_workbench.write_rows(
        out_dir / "bucket_index.csv",
        [
            "family",
            "bucket_slug",
            "bucket_label",
            "rows",
            "query_terms",
            "semantic_filters",
            "example_codes",
            "example_descriptions",
        ],
        sorted(all_bucket_rows, key=lambda row: (-int(row["rows"]), str(row["family"]), str(row["bucket_label"]))),
    )

    lines = [
        "# Uncategorized Workbench",
        "",
        f"- rows: {len(rows)}",
        f"- families: {len(family_index)}",
        f"- buckets: {len(all_bucket_rows)}",
        "",
        "## Top Families",
        "",
        "| family | rows | bucket count | top bucket |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in family_index[:25]:
        lines.append(f"| {row['family']} | {row['rows']} | {row['bucket_count']} | {row['top_bucket']} |")
    lines.extend(
        [
            "",
            "## Top Buckets",
            "",
            "| family | rows | query terms | semantic filters | example descriptions |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for row in sorted(all_bucket_rows, key=lambda item: (-int(item["rows"]), str(item["family"])))[:40]:
        lines.append(
            f"| {row['family']} | {row['rows']} | {row['query_terms']} | {row['semantic_filters']} | {row['example_descriptions']} |"
        )
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Break the Uncategorized retail-query rows into family and query-signature buckets")
    parser.add_argument("--plan-csv", type=Path, default=DEFAULT_PLAN_CSV)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    rows = baseline.load_rows(args.plan_csv)
    uncategorized_rows = [
        row
        for row in rows
        if category_workbench.top_category_name(row) == "Uncategorized"
    ]
    if not uncategorized_rows:
        raise SystemExit("uncategorized_has_no_rows")
    build_outputs(uncategorized_rows, args.out_dir)


if __name__ == "__main__":
    main()
