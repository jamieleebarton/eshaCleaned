from __future__ import annotations

import argparse
import csv
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path

import summarize_retail_query_baseline as baseline


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN_CSV = baseline.DEFAULT_PLAN_CSV
DEFAULT_OUT_DIR = ROOT / "implementation" / "output" / "category_workbench"


def category_slug(value: str) -> str:
    cleaned = value.strip().lower().replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    slug = cleaned.strip("_") or "uncategorized"
    if len(slug) <= 96:
        return slug
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:85].rstrip('_')}_{digest}"


def normalize_category(value: str) -> str:
    return value.strip().casefold()


def split_terms(raw: str) -> list[str]:
    return [term.strip() for term in str(raw or "").split("|") if term.strip()]


def top_category_name(row: dict[str, str]) -> str:
    categories = baseline.parse_top_categories(row.get("top_categories_json", "[]"))
    if not categories:
        return "Uncategorized"
    return str(categories[0].get("category") or "").strip() or "Uncategorized"


def selected_rewrite_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for row in rows:
        after = row.get("selected_attempt_after", "")
        before = row.get("selected_attempt_before", "")
        if row.get("exactness_status") == "strong" and after and after != before:
            out.append(row)
    return out


def category_index_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[top_category_name(row)].append(row)
    out: list[dict[str, object]] = []
    for category, group in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        status_counts = Counter(row["exactness_status"] for row in group)
        family_counts = Counter(row["family"] for row in group)
        reason_counts = Counter(row["reason"] for row in group)
        out.append(
            {
                "category_slug": category_slug(category),
                "branded_food_category": category,
                "rows": len(group),
                "strong": status_counts.get("strong", 0),
                "uncertain": status_counts.get("uncertain", 0),
                "unresolved": status_counts.get("unresolved", 0),
                "auto_rewrites": len(selected_rewrite_rows(group)),
                "top_families": " | ".join(f"{name}:{count}" for name, count in family_counts.most_common(5)),
                "top_reasons": " | ".join(f"{name}:{count}" for name, count in reason_counts.most_common(5)),
            }
        )
    return out


def counter_rows(counter: Counter[str], key_name: str, count_name: str = "count") -> list[dict[str, object]]:
    return [{key_name: value, count_name: count} for value, count in counter.most_common()]


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, category: str, rows: list[dict[str, str]]) -> None:
    status_counts = Counter(row["exactness_status"] for row in rows)
    family_counts = Counter(row["family"] for row in rows)
    reason_counts = Counter(row["reason"] for row in rows)
    unresolved_query_terms = Counter()
    demoted_terms = Counter()
    semantic_filters = Counter()
    for row in rows:
        if row["exactness_status"] == "unresolved":
            unresolved_query_terms.update(split_terms(row.get("query_terms_before", "")))
        demoted_terms.update(split_terms(row.get("demoted_query_terms", "")))
        semantic_filters.update(split_terms(row.get("semantic_filter_terms", "")))
    rewrites = selected_rewrite_rows(rows)[:25]
    unresolved = [row for row in rows if row["exactness_status"] == "unresolved"][:25]
    lines = [
        f"# Category Workbench: {category}",
        "",
        f"- rows: {len(rows)}",
        f"- strong: {status_counts.get('strong', 0)}",
        f"- uncertain: {status_counts.get('uncertain', 0)}",
        f"- unresolved: {status_counts.get('unresolved', 0)}",
        f"- auto-selected rewrites: {len(selected_rewrite_rows(rows))}",
        "",
        "## Top Families",
        "",
        "| family | count |",
        "| --- | ---: |",
    ]
    for family, count in family_counts.most_common(15):
        lines.append(f"| {family} | {count} |")
    lines.extend(
        [
            "",
            "## Top Reasons",
            "",
            "| reason | count |",
            "| --- | ---: |",
        ]
    )
    for reason, count in reason_counts.most_common(15):
        lines.append(f"| {reason} | {count} |")
    lines.extend(
        [
            "",
            "## Frequent Query Terms In Unresolved Rows",
            "",
            "| term | count |",
            "| --- | ---: |",
        ]
    )
    for term, count in unresolved_query_terms.most_common(20):
        lines.append(f"| {term} | {count} |")
    lines.extend(
        [
            "",
            "## Frequent Demoted Terms",
            "",
            "| term | count |",
            "| --- | ---: |",
        ]
    )
    for term, count in demoted_terms.most_common(20):
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
            "## Sample Strong Rewrites",
            "",
            "| esha_code | before | after | reason | description |",
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    for row in rewrites:
        lines.append(
            f"| {row['esha_code']} | {row['selected_attempt_before']} | {row['selected_attempt_after']} | "
            f"{row['reason']} | {row['description']} |"
        )
    lines.extend(
        [
            "",
            "## Sample Unresolved",
            "",
            "| esha_code | recommended | query terms | semantic filters | description |",
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    for row in unresolved:
        lines.append(
            f"| {row['esha_code']} | {row['recommended_attempt']} | {row['query_terms_before']} | "
            f"{row['semantic_filter_terms']} | {row['description']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_category_outputs(out_dir: Path, category: str, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    unresolved = [row for row in rows if row["exactness_status"] == "unresolved"]
    uncertain = [row for row in rows if row["exactness_status"] == "uncertain"]
    rewrites = selected_rewrite_rows(rows)
    family_counts = Counter(row["family"] for row in rows)
    reason_counts = Counter(row["reason"] for row in rows)
    unresolved_query_terms = Counter()
    demoted_terms = Counter()
    semantic_filters = Counter()
    for row in rows:
        if row["exactness_status"] == "unresolved":
            unresolved_query_terms.update(split_terms(row.get("query_terms_before", "")))
        demoted_terms.update(split_terms(row.get("demoted_query_terms", "")))
        semantic_filters.update(split_terms(row.get("semantic_filter_terms", "")))
    write_rows(out_dir / "cards.csv", fieldnames, rows)
    write_rows(out_dir / "unresolved.csv", fieldnames, unresolved)
    write_rows(out_dir / "uncertain.csv", fieldnames, uncertain)
    write_rows(out_dir / "strong_rewrites.csv", fieldnames, rewrites)
    write_rows(out_dir / "family_counts.csv", ["family", "count"], counter_rows(family_counts, "family"))
    write_rows(out_dir / "reason_counts.csv", ["reason", "count"], counter_rows(reason_counts, "reason"))
    write_rows(
        out_dir / "unresolved_query_terms.csv",
        ["term", "count"],
        counter_rows(unresolved_query_terms, "term"),
    )
    write_rows(out_dir / "demoted_terms.csv", ["term", "count"], counter_rows(demoted_terms, "term"))
    write_rows(
        out_dir / "semantic_filter_terms.csv",
        ["term", "count"],
        counter_rows(semantic_filters, "term"),
    )
    write_summary(out_dir / "summary.md", category, rows)


def filter_categories(index_rows: list[dict[str, object]], categories: set[str], limit: int | None) -> list[dict[str, object]]:
    filtered = [
        row for row in index_rows
        if not categories or normalize_category(str(row["branded_food_category"])) in categories
    ]
    if limit is not None:
        return filtered[: max(0, limit)]
    return filtered


def main() -> None:
    parser = argparse.ArgumentParser(description="Build per-category retail rewrite workbench outputs")
    parser.add_argument("--plan-csv", type=Path, default=DEFAULT_PLAN_CSV)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--limit-categories", type=int, default=None)
    args = parser.parse_args()

    rows = baseline.load_rows(args.plan_csv)
    if not rows:
        raise SystemExit("plan_csv_has_no_rows")
    fieldnames = list(rows[0].keys())
    index_rows = category_index_rows(rows)
    wanted = {normalize_category(category) for category in args.category if category.strip()}
    selected = filter_categories(index_rows, wanted, args.limit_categories)
    grouped = defaultdict(list)
    for row in rows:
        grouped[top_category_name(row)].append(row)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for index_row in selected:
        category = str(index_row["branded_food_category"])
        slug = str(index_row["category_slug"])
        write_category_outputs(args.out_dir / slug, category, grouped[category], fieldnames)
    write_rows(
        args.out_dir / "category_index.csv",
        [
            "category_slug",
            "branded_food_category",
            "rows",
            "strong",
            "uncertain",
            "unresolved",
            "auto_rewrites",
            "top_families",
            "top_reasons",
        ],
        selected,
    )
    print(
        {
            "categories": len(selected),
            "out_dir": str(args.out_dir),
            "index_csv": str(args.out_dir / "category_index.csv"),
        }
    )


if __name__ == "__main__":
    main()
