from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
QUEUE_CSV = ROOT / "implementation" / "output" / "top2500_cleanup_queue.csv"
OUT_CSV = ROOT / "implementation" / "output" / "top2500_cleanup_checklist.csv"
OUT_MD = ROOT / "implementation" / "output" / "top2500_cleanup_checklist_summary.md"


FIELDS = [
    "queue_rank",
    "issue_priority",
    "normalized_item",
    "occurrence_count",
    "esha_code",
    "esha_description",
    "issue_class",
    "recommended_action",
    "fix_lane",
    "target_fix_file",
    "regression_test",
    "lab_probe_command",
    "queue_rebuild_command",
    "proof_artifact",
    "status",
    "owner",
    "batch_id",
    "verified_at",
    "notes",
]


def int_value(value: str) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def classify_lane(row: dict[str, str]) -> str:
    issue_class = row.get("issue_class", "")
    if issue_class in {"canonical_gap", "canonical_surface_gap", "canonical_surface_missing"}:
        return "canonical_identity"
    if not (row.get("esha_code") or "").strip():
        return "canonical_identity"
    if issue_class in {"md_card_or_query_gap", "esha_assignment_suspicious"}:
        return "esha_card_query"
    if "contract" in (row.get("product_contract_status") or "").lower():
        return "product_contract"
    return "review_hold"


def target_fix_file(row: dict[str, str], lane: str) -> str:
    if lane == "canonical_identity":
        return "canonical_surface_normalized_with_product_proxies.csv"
    if lane == "esha_card_query":
        return "implementation/output/esha_code_query_packs/*"
    if lane == "product_contract":
        return "implementation/approved_product_contracts.csv"
    return "implementation/surface_lab_calculator.py"


def build_checklist(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    per_priority = defaultdict(int)
    rebuild_cmd = (
        "python3 implementation/build_top_ingredient_coverage_audit.py ; "
        "python3 implementation/build_top2500_cleanup_queue.py ; "
        "python3 implementation/build_top2500_cleanup_checklist.py"
    )
    for row in rows:
        priority = row.get("issue_priority", "")
        per_priority[priority] += 1
        lane = classify_lane(row)
        item = row.get("normalized_item", "")
        out.append(
            {
                "queue_rank": row.get("queue_rank", ""),
                "issue_priority": priority,
                "normalized_item": item,
                "occurrence_count": row.get("occurrence_count", ""),
                "esha_code": row.get("esha_code", ""),
                "esha_description": row.get("esha_description", ""),
                "issue_class": row.get("issue_class", ""),
                "recommended_action": row.get("recommended_action", ""),
                "fix_lane": lane,
                "target_fix_file": target_fix_file(row, lane),
                "regression_test": "implementation.tests.test_top2500_cleanup_regressions",
                "lab_probe_command": (
                    f'python3 implementation/surface_lab_calculator.py --display "{item}" --item "{item}" --grams 100'
                ),
                "queue_rebuild_command": rebuild_cmd,
                "proof_artifact": "implementation/output/top2500_cleanup_queue.csv",
                "status": row.get("audit_status", "") or "todo",
                "owner": "",
                "batch_id": f"{priority}-{per_priority[priority]:04d}",
                "verified_at": "",
                "notes": row.get("audit_notes", ""),
            }
        )
    return out


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, str]], path: Path) -> None:
    lane_counts = Counter(row["fix_lane"] for row in rows)
    lane_occurrences = Counter()
    status_counts = Counter(row["status"] for row in rows)
    for row in rows:
        lane_occurrences[row["fix_lane"]] += int_value(row["occurrence_count"])

    lines = [
        "# Top 2500 Cleanup Checklist",
        "",
        "This checklist is the execution surface for the top-2500 queue.",
        "",
        f"- total_rows: {len(rows)}",
        "",
        "## Fix Lanes",
        "",
        "| lane | rows | occurrences |",
        "| --- | ---: | ---: |",
    ]
    for lane, count in lane_counts.most_common():
        lines.append(f"| {lane} | {count} | {lane_occurrences[lane]:,} |")

    lines.extend(["", "## Status Totals", "", "| status | rows |", "| --- | ---: |"])
    for status, count in status_counts.most_common():
        lines.append(f"| {status} | {count} |")

    lines.extend(
        [
            "",
            "## First 100",
            "",
            "| batch_id | priority | queue_rank | item | lane | target_fix_file |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for row in rows[:100]:
        lines.append(
            f"| {row['batch_id']} | {row['issue_priority']} | {row['queue_rank']} | "
            f"{row['normalized_item'].replace('|', '/')} | {row['fix_lane']} | {row['target_fix_file']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-csv", type=Path, default=QUEUE_CSV)
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()

    queue_rows = load_rows(args.queue_csv)
    checklist = build_checklist(queue_rows)
    write_csv(checklist, args.out_csv)
    write_summary(checklist, args.out_md)
    print(f"checklist_rows={len(checklist)} out_csv={args.out_csv} out_md={args.out_md}")


if __name__ == "__main__":
    main()
