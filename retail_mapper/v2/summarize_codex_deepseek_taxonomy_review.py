#!/usr/bin/env python3
"""Summarize DeepSeek taxonomy adjudications into review artifacts.

Reads:
  - codex_deepseek_taxonomy_review_decisions.jsonl

Writes:
  - codex_deepseek_taxonomy_review_summary.json
  - codex_deepseek_taxonomy_wrong_rows.csv
  - codex_deepseek_taxonomy_rule_candidates.csv
  - codex_deepseek_taxonomy_ambiguous_rows.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
DEFAULT_SRC = V2 / "codex_deepseek_taxonomy_review_decisions.jsonl"
OUT_SUMMARY = V2 / "codex_deepseek_taxonomy_review_summary.json"
OUT_WRONG = V2 / "codex_deepseek_taxonomy_wrong_rows.csv"
OUT_RULES = V2 / "codex_deepseek_taxonomy_rule_candidates.csv"
OUT_AMBIG = V2 / "codex_deepseek_taxonomy_ambiguous_rows.csv"


ROW_FIELDS = [
    "fdc_id",
    "title",
    "branded_food_category",
    "current_canonical_path",
    "current_retail_leaf_path",
    "verdict",
    "confidence",
    "reason_code",
    "product_type",
    "proposed_category_path",
    "proposed_product_identity",
    "proposed_modifier_policy",
    "rule_candidate",
    "rule_pattern",
    "nearby_false_positive_risk",
    "rationale",
    "priority_score",
    "reason_codes",
]

RULE_FIELDS = [
    "rule_pattern",
    "proposed_category_path",
    "proposed_product_identity",
    "rows",
    "avg_confidence",
    "reason_codes",
    "sample_fdcs",
    "sample_titles",
    "sample_current_paths",
]


def load_decisions(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        raise SystemExit(f"missing {path}; run call_deepseek_codex_taxonomy_review.py first")
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def flatten(record: dict[str, Any]) -> dict[str, Any]:
    decision = record.get("decision") or {}
    current = record.get("current_taxonomy") or {}
    return {
        "fdc_id": record.get("fdc_id", ""),
        "title": record.get("title", ""),
        "branded_food_category": record.get("branded_food_category", ""),
        "current_canonical_path": current.get("canonical_path", ""),
        "current_retail_leaf_path": current.get("retail_leaf_path", ""),
        "verdict": decision.get("verdict", ""),
        "confidence": decision.get("confidence", ""),
        "reason_code": decision.get("reason_code", ""),
        "product_type": decision.get("product_type", ""),
        "proposed_category_path": decision.get("proposed_category_path", ""),
        "proposed_product_identity": decision.get("proposed_product_identity", ""),
        "proposed_modifier_policy": decision.get("proposed_modifier_policy", ""),
        "rule_candidate": decision.get("rule_candidate", ""),
        "rule_pattern": decision.get("rule_pattern", ""),
        "nearby_false_positive_risk": decision.get("nearby_false_positive_risk", ""),
        "rationale": decision.get("rationale", ""),
        "priority_score": record.get("priority_score", ""),
        "reason_codes": "|".join(record.get("reason_codes") or []),
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ROW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_rule_candidates(rows: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if str(row.get("rule_candidate", "")).lower() != "true":
            continue
        if row.get("verdict") != "wrong":
            continue
        try:
            confidence = float(row.get("confidence") or 0)
        except ValueError:
            confidence = 0.0
        if confidence < 0.85:
            continue
        key = (
            row.get("rule_pattern", ""),
            row.get("proposed_category_path", ""),
            row.get("proposed_product_identity", ""),
        )
        if not any(key):
            continue
        grouped.setdefault(key, []).append(row)

    with OUT_RULES.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RULE_FIELDS)
        writer.writeheader()
        for (pattern, category_path, identity), group in sorted(
            grouped.items(),
            key=lambda kv: (-len(kv[1]), kv[0]),
        ):
            confidences = []
            reason_codes: Counter[str] = Counter()
            for row in group:
                try:
                    confidences.append(float(row.get("confidence") or 0))
                except ValueError:
                    pass
                reason_codes.update((row.get("reason_codes") or "").split("|"))
            writer.writerow({
                "rule_pattern": pattern,
                "proposed_category_path": category_path,
                "proposed_product_identity": identity,
                "rows": len(group),
                "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else "",
                "reason_codes": " | ".join(f"{k}:{v}" for k, v in reason_codes.most_common() if k),
                "sample_fdcs": " | ".join(row["fdc_id"] for row in group[:8]),
                "sample_titles": " | ".join(row["title"][:90] for row in group[:5]),
                "sample_current_paths": " | ".join(row["current_canonical_path"] for row in group[:5]),
            })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    args = parser.parse_args()

    records = load_decisions(args.src)
    rows = [flatten(record) for record in records]
    wrong = [row for row in rows if row.get("verdict") == "wrong"]
    ambiguous = [row for row in rows if row.get("verdict") == "ambiguous"]

    write_rows(OUT_WRONG, wrong)
    write_rows(OUT_AMBIG, ambiguous)
    write_rule_candidates(rows)

    verdict_counts = Counter(row.get("verdict", "") for row in rows)
    reason_counts = Counter(row.get("reason_code", "") for row in rows)
    bfc_wrong_counts = Counter(row.get("branded_food_category", "") for row in wrong)
    summary = {
        "input": str(args.src),
        "rows": len(rows),
        "verdict_counts": dict(verdict_counts.most_common()),
        "reason_counts": dict(reason_counts.most_common()),
        "wrong_rows": len(wrong),
        "ambiguous_rows": len(ambiguous),
        "top_wrong_bfcs": dict(bfc_wrong_counts.most_common(30)),
        "outputs": {
            "summary": str(OUT_SUMMARY),
            "wrong_rows": str(OUT_WRONG),
            "rule_candidates": str(OUT_RULES),
            "ambiguous_rows": str(OUT_AMBIG),
        },
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
