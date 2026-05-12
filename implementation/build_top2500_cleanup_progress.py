from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COVERAGE_CSV = ROOT / "implementation" / "output" / "top2500_ingredient_coverage_audit.csv"
OUT_CSV = ROOT / "implementation" / "output" / "top2500_cleanup_progress.csv"
OUT_MD = ROOT / "implementation" / "output" / "top2500_cleanup_progress_summary.md"
TERMINAL_STATUSES = {"done", "reviewed_terminal"}
BASE_STATUSES = TERMINAL_STATUSES | {"todo"}


FIELDS = [
    "rank",
    "normalized_item",
    "occurrence_count",
    "issue_priority",
    "check_status",
    "issue_class",
    "esha_code",
    "esha_description",
    "selected_canonical_surface",
    "product_contract_status",
    "pack_path",
    "recommended_action",
]


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def validate_coverage_rows(rows: list[dict[str, str]], path: Path) -> None:
    if rows:
        return
    raise ValueError(
        "top2500 cleanup progress cannot be rebuilt from an empty coverage audit; "
        f"source={path}"
    )


def int_value(value: str) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def derived_check_status(row: dict[str, str]) -> str:
    priority = row.get("issue_priority", "")
    if priority == "OK":
        return "done"
    if priority == "P3":
        return "reviewed_terminal"
    return "todo"


def row_key(row: dict[str, str]) -> tuple[str, str]:
    return (str(row.get("rank", "")).strip(), str(row.get("normalized_item", "")).strip().lower())


def preserved_check_status(existing_row: dict[str, str] | None, derived_status: str) -> str:
    if not existing_row:
        return derived_status
    existing_status = str(existing_row.get("check_status", "")).strip()
    if existing_status and existing_status not in BASE_STATUSES:
        return existing_status
    return derived_status


def build_progress(rows: list[dict[str, str]], existing_rows: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    existing_by_key = {row_key(row): row for row in existing_rows or []}
    out: list[dict[str, str]] = []
    for row in rows:
        derived = derived_check_status(row)
        out.append({field: row.get(field, "") for field in FIELDS})
        out[-1]["check_status"] = preserved_check_status(existing_by_key.get(row_key(row)), derived)
    return out


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, str]], path: Path) -> None:
    status_counts = Counter(row["check_status"] for row in rows)
    status_occurrences = Counter()
    priority_counts = Counter(row["issue_priority"] for row in rows)
    unresolved_rows = [row for row in rows if derived_check_status(row) == "todo"]
    issue_counts = Counter(row["issue_class"] for row in unresolved_rows)
    for row in rows:
        status_occurrences[row["check_status"]] += int_value(row["occurrence_count"])
    ordered_statuses = [
        *[status for status in ("done", "reviewed_terminal", "todo") if status in status_counts],
        *sorted(status for status in status_counts if status not in {"done", "reviewed_terminal", "todo"}),
    ]

    lines = [
        "# Top 2500 Cleanup Progress",
        "",
        "This is the checkoff view. `issue_priority` is the current audit state; `check_status` preserves named work states when a row is being actively remapped or held for re-audit.",
        "",
        f"- total_rows: {len(rows)}",
        "",
        "## Check Status",
        "",
        "| status | rows | occurrences |",
        "| --- | ---: | ---: |",
    ]
    for status in ordered_statuses:
        lines.append(f"| {status} | {status_counts[status]} | {status_occurrences[status]:,} |")

    lines.extend(["", "## Priority Counts", "", "| priority | rows |", "| --- | ---: |"])
    for priority, count in priority_counts.most_common():
        lines.append(f"| {priority} | {count} |")

    lines.extend(["", "## Remaining Unresolved Classes", "", "| rows | issue_class |", "| ---: | --- |"])
    for issue, count in issue_counts.most_common():
        lines.append(f"| {count} | {issue} |")

    lines.extend(
        [
            "",
            "## First 50 Unresolved Rows",
            "",
            "| rank | occurrences | item | issue | ESHA |",
            "| ---: | ---: | --- | --- | --- |",
        ]
    )
    for row in unresolved_rows[:50]:
        esha = row["esha_code"] or "(blank)"
        if row["esha_description"]:
            esha = f"{esha} {row['esha_description']}"
        lines.append(
            f"| {row['rank']} | {int_value(row['occurrence_count']):,} | "
            f"{row['normalized_item'].replace('|', '/')} | {row['issue_class']} | {esha.replace('|', '/')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-csv", type=Path, default=COVERAGE_CSV)
    parser.add_argument("--existing-progress-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()

    coverage_rows = load_rows(args.coverage_csv)
    validate_coverage_rows(coverage_rows, args.coverage_csv)
    existing_rows = load_rows(args.existing_progress_csv) if args.existing_progress_csv.exists() else []
    rows = build_progress(coverage_rows, existing_rows=existing_rows)
    write_csv(rows, args.out_csv)
    write_summary(rows, args.out_md)
    print(f"progress_rows={len(rows)} out_csv={args.out_csv} out_md={args.out_md}")


if __name__ == "__main__":
    main()
