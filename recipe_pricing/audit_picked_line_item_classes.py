#!/usr/bin/env python3
"""Audit picked-recipe line CSVs for customer-visible wrong-class SKUs."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from planner.form_facet_audit import concept_sku_class_findings  # noqa: E402


def audit(csv_path: Path) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    counters = Counter()
    with csv_path.open(encoding="utf-8", errors="replace", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            concept_key = row.get("concept_key") or row.get("priced_concept_key") or ""
            sku = row.get("picked_sku") or row.get("selected_sku") or ""
            if not concept_key or not sku:
                continue
            counters["lines_scanned"] += 1
            for finding in concept_sku_class_findings(concept_key, [sku]):
                counters[finding.issue_type] += 1
                findings.append({
                    "csv_line": i,
                    "recipe_id": row.get("recipe_id", ""),
                    "recipe_name": row.get("recipe_name", "") or row.get("recipe_title", ""),
                    "concept_key": row.get("concept_key", ""),
                    "priced_concept_key": concept_key,
                    "resolution_tier": row.get("resolution_tier", ""),
                    "picked_sku": sku,
                    "issue_type": finding.issue_type,
                    "severity": finding.severity,
                    "message": finding.message,
                    "expected": finding.expected,
                })
    summary = {
        "csv": str(csv_path),
        "lines_scanned": counters["lines_scanned"],
        "finding_count": len(findings),
        "by_issue_type": dict(sorted((k, v) for k, v in counters.items() if k != "lines_scanned")),
        "by_tier": dict(Counter(row.get("resolution_tier", "") for row in findings).most_common()),
    }
    return findings, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("picked_lines_csv", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-csv", type=Path)
    args = parser.parse_args()

    findings, summary = audit(args.picked_lines_csv)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps({"summary": summary, "findings": findings}, indent=2))
    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.out_csv.open("w", encoding="utf-8", newline="") as f:
            fieldnames = [
                "csv_line", "recipe_id", "recipe_name", "concept_key",
                "priced_concept_key", "resolution_tier", "picked_sku",
                "issue_type", "severity", "message", "expected",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(findings)

    print(
        f"{args.picked_lines_csv}: {summary['finding_count']} findings "
        f"across {summary['lines_scanned']} picked lines"
    )
    print(f"by issue: {summary['by_issue_type']}")
    print(f"by tier: {summary['by_tier']}")
    if args.out_json:
        print(f"-> {args.out_json}")
    if args.out_csv:
        print(f"-> {args.out_csv}")
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
