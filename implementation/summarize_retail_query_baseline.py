from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN_CSV = ROOT / "implementation" / "output" / "retail_query_rewrite_plan.csv"
DEFAULT_SUMMARY_MD = ROOT / "implementation" / "output" / "retail_query_baseline_summary.md"
DEFAULT_FAMILY_CSV = ROOT / "implementation" / "output" / "retail_query_baseline_by_family.csv"
DEFAULT_CATEGORY_CSV = ROOT / "implementation" / "output" / "retail_query_baseline_by_category.csv"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def parse_top_categories(raw: str) -> list[dict[str, object]]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, object]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "category": str(row.get("category") or ""),
                "count": int(row.get("count") or 0),
                "signal": str(row.get("signal") or ""),
            }
        )
    return out


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def family_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        grouped[row["family"]][row["exactness_status"]] += 1
        grouped[row["family"]]["total"] += 1
    out: list[dict[str, object]] = []
    for family, counts in sorted(grouped.items()):
        out.append(
            {
                "family": family,
                "total": counts["total"],
                "strong": counts["strong"],
                "uncertain": counts["uncertain"],
                "unresolved": counts["unresolved"],
            }
        )
    return out


def category_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    families_by_category: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        status = row["exactness_status"]
        categories = parse_top_categories(row.get("top_categories_json", "[]"))
        if not categories:
            continue
        top = categories[0]
        category = str(top["category"])
        signal = str(top["signal"])
        grouped[category]["rows"] += 1
        grouped[category][status] += 1
        grouped[category][f"signal_{signal}"] += 1
        grouped[category]["top_slot_count_sum"] += int(top["count"])
        families_by_category[category][row["family"]] += 1
    out: list[dict[str, object]] = []
    for category, counts in sorted(grouped.items(), key=lambda item: (-item[1]["rows"], item[0])):
        top_families = " | ".join(
            f"{family}:{n}" for family, n in families_by_category[category].most_common(5)
        )
        out.append(
            {
                "branded_food_category": category,
                "rows": counts["rows"],
                "strong": counts["strong"],
                "uncertain": counts["uncertain"],
                "unresolved": counts["unresolved"],
                "top_slot_count_sum": counts["top_slot_count_sum"],
                "signal_in_scope": counts["signal_in_scope_category"],
                "signal_noise": counts["signal_category_noise"],
                "signal_review": counts["signal_review"],
                "top_families": top_families,
            }
        )
    return out


def write_summary(path: Path, rows: list[dict[str, str]], family_stats: list[dict[str, object]], category_stats: list[dict[str, object]]) -> None:
    status_counts = Counter(row["exactness_status"] for row in rows)
    top_unresolved = [row for row in rows if row["exactness_status"] == "unresolved"][:30]
    lines = [
        "# Retail Query Baseline",
        "",
        f"- rows: {len(rows)}",
        f"- strong: {status_counts.get('strong', 0)}",
        f"- uncertain: {status_counts.get('uncertain', 0)}",
        f"- unresolved: {status_counts.get('unresolved', 0)}",
        "",
        "## By Family",
        "",
        "| family | total | strong | uncertain | unresolved |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in family_stats:
        lines.append(
            f"| {row['family']} | {row['total']} | {row['strong']} | {row['uncertain']} | {row['unresolved']} |"
        )
    lines.extend(
        [
            "",
            "## Top Branded Food Categories",
            "",
            "| category | rows | strong | uncertain | unresolved | top families |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in category_stats[:30]:
        lines.append(
            f"| {row['branded_food_category']} | {row['rows']} | {row['strong']} | {row['uncertain']} | {row['unresolved']} | {row['top_families']} |"
        )
    lines.extend(
        [
            "",
            "## Sample Unresolved",
            "",
            "| esha_code | family | recommended | query | description |",
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    for row in top_unresolved:
        lines.append(
            f"| {row['esha_code']} | {row['family']} | {row['recommended_attempt']} | {row['recommended_query']} | {row['description']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize full-corpus retail query rewrite baseline")
    parser.add_argument("--plan-csv", type=Path, default=DEFAULT_PLAN_CSV)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_MD)
    parser.add_argument("--family-out", type=Path, default=DEFAULT_FAMILY_CSV)
    parser.add_argument("--category-out", type=Path, default=DEFAULT_CATEGORY_CSV)
    args = parser.parse_args()

    rows = load_rows(args.plan_csv)
    families = family_rows(rows)
    categories = category_rows(rows)
    write_csv(args.family_out, ["family", "total", "strong", "uncertain", "unresolved"], families)
    write_csv(
        args.category_out,
        [
            "branded_food_category",
            "rows",
            "strong",
            "uncertain",
            "unresolved",
            "top_slot_count_sum",
            "signal_in_scope",
            "signal_noise",
            "signal_review",
            "top_families",
        ],
        categories,
    )
    write_summary(args.summary_out, rows, families, categories)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "family_out": str(args.family_out),
                "category_out": str(args.category_out),
                "summary_out": str(args.summary_out),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
