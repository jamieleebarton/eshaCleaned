from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PIPELINE_QUEUE_CSV = ROOT / "implementation" / "pipeline_work_queue.csv"
OUT_CSV = ROOT / "implementation" / "output" / "wrong_product_accepted_queue.csv"
OUT_MD = ROOT / "implementation" / "output" / "wrong_product_accepted_queue_summary.md"

TARGET_WORK_IDS = (
    "product_contract_failed_candidates",
    "product_covered_needs_contract_audit",
)

OUT_FIELDS = [
    "source_work_id",
    "priority",
    "risk_level",
    "aggregate_row_count",
    "aggregate_occurrence_count",
    "example_occurrence_count",
    "normalized_item",
    "qualifier",
    "observed_bad_product",
    "queue_class",
    "source_artifact",
    "notes",
    "raw_example",
]

EXAMPLE_RE = re.compile(r"^\s*(\d+):\s*(.+?)\s*$")


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def split_examples(text: str) -> list[str]:
    return [piece.strip() for piece in str(text or "").split(" | ") if piece.strip()]


def split_item_and_qualifier(text: str) -> tuple[str, str]:
    if "|||" in text:
        item, qualifier = text.split("|||", 1)
    elif "||" in text:
        item, qualifier = text.split("||", 1)
    else:
        item, qualifier = text, ""
    return item.strip(), qualifier.strip(" |")


def parse_example(example: str) -> dict[str, str]:
    match = EXAMPLE_RE.match(example)
    if not match:
        return {
            "example_occurrence_count": "",
            "normalized_item": "",
            "qualifier": "",
            "observed_bad_product": "",
            "raw_example": example,
        }
    occurrence_count, payload = match.groups()
    if " -> " in payload:
        left, observed_bad_product = payload.split(" -> ", 1)
    else:
        left, observed_bad_product = payload, ""
    normalized_item, qualifier = split_item_and_qualifier(left)
    return {
        "example_occurrence_count": occurrence_count,
        "normalized_item": normalized_item,
        "qualifier": qualifier,
        "observed_bad_product": observed_bad_product.strip(),
        "raw_example": example,
    }


def build_queue(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = [row for row in rows if row.get("work_id") in TARGET_WORK_IDS and (row.get("status") or "").strip() == "todo"]
    out: list[dict[str, str]] = []
    for row in selected:
        queue_class = "wrong_product_accepted" if row["work_id"] == "product_contract_failed_candidates" else "covered_product_contract_needs_audit"
        for example in split_examples(row.get("examples", "")):
            parsed = parse_example(example)
            out.append(
                {
                    "source_work_id": row["work_id"],
                    "priority": row.get("priority", ""),
                    "risk_level": row.get("risk_level", ""),
                    "aggregate_row_count": row.get("row_count", ""),
                    "aggregate_occurrence_count": row.get("occurrence_count", ""),
                    "example_occurrence_count": parsed["example_occurrence_count"],
                    "normalized_item": parsed["normalized_item"],
                    "qualifier": parsed["qualifier"],
                    "observed_bad_product": parsed["observed_bad_product"],
                    "queue_class": queue_class,
                    "source_artifact": row.get("source_artifact", ""),
                    "notes": row.get("notes", ""),
                    "raw_example": parsed["raw_example"],
                }
            )
    out.sort(
        key=lambda row: (
            row["source_work_id"] != "product_contract_failed_candidates",
            -int(row["example_occurrence_count"] or 0),
            row["normalized_item"],
        )
    )
    return out


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, str]], path: Path) -> None:
    by_work_id = Counter(row["source_work_id"] for row in rows)
    by_queue_class = Counter(row["queue_class"] for row in rows)
    by_item = Counter(row["normalized_item"] for row in rows if row["normalized_item"])
    lines = [
        "# Wrong Product Accepted Queue",
        "",
        "This queue is the explicit false-accept ledger built from the current pipeline work queue. It is not yet a full live recipe/store join, but it turns the known wrong-buy backlog into a concrete artifact instead of leaving it implicit.",
        "",
        f"- rows: `{len(rows)}`",
        "",
        "## By Source Work ID",
        "",
        "| work_id | rows |",
        "| --- | ---: |",
    ]
    for work_id, count in by_work_id.most_common():
        lines.append(f"| {work_id} | {count} |")

    lines.extend(["", "## By Queue Class", "", "| queue_class | rows |", "| --- | ---: |"])
    for queue_class, count in by_queue_class.most_common():
        lines.append(f"| {queue_class} | {count} |")

    lines.extend(["", "## Top Normalized Items", "", "| item | rows |", "| --- | ---: |"])
    for item, count in by_item.most_common(20):
        lines.append(f"| {item.replace('|', '/')} | {count} |")

    lines.extend(
        [
            "",
            "## First 50 Rows",
            "",
            "| work_id | item | qualifier | observed_bad_product | example_occurrence_count |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    for row in rows[:50]:
        lines.append(
            f"| {row['source_work_id']} | {row['normalized_item'].replace('|', '/')} | "
            f"{row['qualifier'].replace('|', '/')} | {row['observed_bad_product'].replace('|', '/')} | "
            f"{row['example_occurrence_count'] or '(blank)'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = build_queue(load_rows(PIPELINE_QUEUE_CSV))
    write_csv(rows, OUT_CSV)
    write_summary(rows, OUT_MD)
    print(f"rows={len(rows)} out_csv={OUT_CSV} out_md={OUT_MD}")


if __name__ == "__main__":
    main()
