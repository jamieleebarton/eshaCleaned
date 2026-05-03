#!/usr/bin/env python3
"""Build shared Codex/Claude review queues for consensus v2 overrides.

This script creates inert todo queues from the right-place and reference audits.
It also creates empty active override files if they do not already exist. Active
override files are applied by apply_consensus_overrides.py only after reviewers
mark rows approved.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping


V2 = Path(__file__).resolve().parent
RIGHT_PLACE = V2 / "consensus_right_place_issue_inventory.csv"
REFERENCE_REMAP = V2 / "consensus_reference_remap_candidates.csv"

TAXONOMY_ACTIVE = V2 / "consensus_taxonomy_overrides.csv"
REFERENCE_ACTIVE = V2 / "consensus_reference_overrides.csv"
SOURCE_CONFLICT_ACTIVE = V2 / "consensus_source_conflicts.csv"

TAXONOMY_TODO = V2 / "consensus_taxonomy_overrides.todo.csv"
REFERENCE_TODO = V2 / "consensus_reference_overrides.todo.csv"
SOURCE_CONFLICT_TODO = V2 / "consensus_source_conflicts.todo.csv"
SUMMARY = V2 / "consensus_override_work_queues_summary.json"
MD = V2 / "consensus_override_workflow.md"

csv.field_size_limit(sys.maxsize)

TAXONOMY_ACTIVE_FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "issue_family",
    "reason",
    "title",
    "branded_food_category",
    "category_path_fixed",
    "product_identity_fixed",
    "canonical_path",
    "modifier",
    "retail_leaf_path",
    "retail_type",
    "canonical_label",
    "review_flags",
    "rationale",
]

REFERENCE_ACTIVE_FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "issue_family",
    "reason",
    "title",
    "branded_food_category",
    "fndds_code",
    "fndds_desc",
    "sr28_code",
    "sr28_desc",
    "esha_code",
    "esha_desc",
    "match_source",
    "match_score",
    "matched_key",
    "portions_json",
]

SOURCE_CONFLICT_ACTIVE_FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "issue_family",
    "reason",
    "title",
    "branded_food_category",
    "branded_food_category_corrected",
    "source_conflict_note",
    "source_conflict_action",
]

TAXONOMY_TODO_FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "issue_family",
    "severity",
    "confidence",
    "action_type",
    "likely_fix",
    "rationale",
    "title",
    "branded_food_category",
    "current_category_path_fixed",
    "current_product_identity_fixed",
    "current_canonical_path",
    "current_modifier",
    "current_retail_leaf_path",
    "fndds_desc",
    "sr28_desc",
    "esha_desc",
    "matched_key",
    "proposed_category_path_fixed",
    "proposed_product_identity_fixed",
    "proposed_canonical_path",
    "proposed_modifier",
    "proposed_retail_leaf_path",
    "notes",
]

REFERENCE_TODO_FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "issue_family",
    "severity",
    "confidence",
    "action_type",
    "suspect_reference_fields",
    "suspect_reference_values",
    "likely_fix",
    "rationale",
    "taxonomy_issue_families",
    "title",
    "branded_food_category",
    "canonical_path",
    "retail_leaf_path",
    "current_fndds_code",
    "current_fndds_desc",
    "current_sr28_code",
    "current_sr28_desc",
    "current_esha_code",
    "current_esha_desc",
    "current_match_source",
    "current_match_score",
    "current_matched_key",
    "proposed_fndds_code",
    "proposed_fndds_desc",
    "proposed_sr28_code",
    "proposed_sr28_desc",
    "proposed_esha_code",
    "proposed_esha_desc",
    "proposed_match_source",
    "proposed_match_score",
    "proposed_matched_key",
    "proposed_portions_json",
    "notes",
]

SOURCE_CONFLICT_TODO_FIELDS = [
    "fdc_id",
    "status",
    "owner",
    "issue_family",
    "severity",
    "confidence",
    "action_type",
    "likely_fix",
    "rationale",
    "title",
    "branded_food_category",
    "current_canonical_path",
    "current_retail_leaf_path",
    "branded_food_category_corrected",
    "source_conflict_note",
    "source_conflict_action",
    "notes",
]


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def create_active_file_if_missing(path: Path, fieldnames: list[str]) -> bool:
    if path.exists():
        return False
    write_csv(path, fieldnames, [])
    return True


def sort_key(row: Mapping[str, str]) -> tuple[str, str, tuple[int, int | str]]:
    fdc = (row.get("fdc_id") or "").strip()
    fdc_key: tuple[int, int | str] = (0, int(fdc)) if fdc.isdigit() else (1, fdc)
    return (row.get("issue_family", "") or "", row.get("title", "") or "", fdc_key)


def is_source_conflict(row: Mapping[str, str]) -> bool:
    family = (row.get("issue_family") or "").lower()
    action_type = (row.get("action_type") or "").strip()
    return action_type == "source_conflict_review" or "source_conflict" in family or "bfc_source_conflict" in family


def is_taxonomy_queue_row(row: Mapping[str, str]) -> bool:
    if is_source_conflict(row):
        return False
    return (row.get("action_type") or "").strip() in {
        "deterministic_fix_candidate",
        "manual_review",
        "policy_fix_candidate",
        "policy_decision",
    }


def taxonomy_owner(row: Mapping[str, str]) -> str:
    return "shared" if (row.get("action_type") or "").strip() == "policy_decision" else "claude"


def build_taxonomy_todo(right_rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in right_rows:
        if not is_taxonomy_queue_row(row):
            continue
        out.append({
            "fdc_id": row.get("fdc_id", "") or "",
            "status": "todo",
            "owner": taxonomy_owner(row),
            "issue_family": row.get("issue_family", "") or "",
            "severity": row.get("severity", "") or "",
            "confidence": row.get("confidence", "") or "",
            "action_type": row.get("action_type", "") or "",
            "likely_fix": row.get("likely_fix", "") or "",
            "rationale": row.get("rationale", "") or "",
            "title": row.get("title", "") or "",
            "branded_food_category": row.get("branded_food_category", "") or "",
            "current_category_path_fixed": row.get("category_path_fixed", "") or "",
            "current_product_identity_fixed": row.get("product_identity_fixed", "") or "",
            "current_canonical_path": row.get("canonical_path", "") or "",
            "current_modifier": row.get("modifier", "") or "",
            "current_retail_leaf_path": row.get("retail_leaf_path", "") or "",
            "fndds_desc": row.get("fndds_desc", "") or "",
            "sr28_desc": row.get("sr28_desc", "") or "",
            "esha_desc": row.get("esha_desc", "") or "",
            "matched_key": row.get("matched_key", "") or "",
            "proposed_category_path_fixed": "",
            "proposed_product_identity_fixed": "",
            "proposed_canonical_path": "",
            "proposed_modifier": "",
            "proposed_retail_leaf_path": "",
            "notes": "",
        })
    out.sort(key=sort_key)
    return out


def build_reference_todo(reference_rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in reference_rows:
        out.append({
            "fdc_id": row.get("fdc_id", "") or "",
            "status": "todo",
            "owner": "codex",
            "issue_family": row.get("issue_family", "") or "",
            "severity": row.get("severity", "") or "",
            "confidence": row.get("confidence", "") or "",
            "action_type": row.get("action_type", "") or "",
            "suspect_reference_fields": row.get("suspect_reference_fields", "") or "",
            "suspect_reference_values": row.get("suspect_reference_values", "") or "",
            "likely_fix": row.get("likely_fix", "") or "",
            "rationale": row.get("rationale", "") or "",
            "taxonomy_issue_families": row.get("taxonomy_issue_families", "") or "",
            "title": row.get("title", "") or "",
            "branded_food_category": row.get("branded_food_category", "") or "",
            "canonical_path": row.get("canonical_path", "") or "",
            "retail_leaf_path": row.get("retail_leaf_path", "") or "",
            "current_fndds_code": row.get("fndds_code", "") or "",
            "current_fndds_desc": row.get("fndds_desc", "") or "",
            "current_sr28_code": row.get("sr28_code", "") or "",
            "current_sr28_desc": row.get("sr28_desc", "") or "",
            "current_esha_code": row.get("esha_code", "") or "",
            "current_esha_desc": row.get("esha_desc", "") or "",
            "current_match_source": row.get("match_source", "") or "",
            "current_match_score": row.get("match_score", "") or "",
            "current_matched_key": row.get("matched_key", "") or "",
            "proposed_fndds_code": "",
            "proposed_fndds_desc": "",
            "proposed_sr28_code": "",
            "proposed_sr28_desc": "",
            "proposed_esha_code": "",
            "proposed_esha_desc": "",
            "proposed_match_source": "",
            "proposed_match_score": "",
            "proposed_matched_key": "",
            "proposed_portions_json": "",
            "notes": "",
        })
    out.sort(key=sort_key)
    return out


def build_source_conflict_todo(right_rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in right_rows:
        if not is_source_conflict(row):
            continue
        out.append({
            "fdc_id": row.get("fdc_id", "") or "",
            "status": "todo",
            "owner": "shared",
            "issue_family": row.get("issue_family", "") or "",
            "severity": row.get("severity", "") or "",
            "confidence": row.get("confidence", "") or "",
            "action_type": row.get("action_type", "") or "",
            "likely_fix": row.get("likely_fix", "") or "",
            "rationale": row.get("rationale", "") or "",
            "title": row.get("title", "") or "",
            "branded_food_category": row.get("branded_food_category", "") or "",
            "current_canonical_path": row.get("canonical_path", "") or "",
            "current_retail_leaf_path": row.get("retail_leaf_path", "") or "",
            "branded_food_category_corrected": "",
            "source_conflict_note": "",
            "source_conflict_action": "",
            "notes": "",
        })
    out.sort(key=sort_key)
    return out


def build_markdown(summary: Mapping[str, object]) -> str:
    lines = [
        "# Consensus Override Workflow",
        "",
        "Use `consensus_full_corpus_audit.csv` as the read-only integration base.",
        "Do not edit the generated consensus CSV by hand.",
        "",
        "## Ownership",
        "",
        "- Codex owns `consensus_reference_overrides.csv` and the reference remap todo queue.",
        "- Claude owns `consensus_taxonomy_overrides.csv` and the right-place taxonomy todo queue.",
        "- Source-category conflicts go through `consensus_source_conflicts.csv` and should be reviewed as shared decisions.",
        "",
        "## Apply Contract",
        "",
        "- Todo files are inert work queues.",
        "- Active override files are applied only when `status` is `approved`, `apply`, or `accepted`.",
        "- Blank cells mean no change. Use `<blank>` when a field must be intentionally cleared.",
        "- Running `python3 retail_mapper/v2/apply_consensus_overrides.py` writes `consensus_full_corpus_audit.v2.csv` plus a field-level decision log.",
        "",
        "## Queue Counts",
        "",
    ]
    for key, value in summary.items():
        if key.endswith("_rows") or key.endswith("_created"):
            lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        "",
        "## First Pass Priority",
        "",
        "1. Approve or reject the high-confidence reference remap rows where a proxy reference is clearly wrong.",
        "2. Approve deterministic taxonomy rows only when the proposed path is a true shopper shelf, not a title-token echo.",
        "3. Keep source BFC corrections separate from taxonomy/reference fixes unless the corrected source category is needed by a downstream rule.",
    ])
    return "\n".join(lines)


def build_work_queues(
    *,
    right_place: Path = RIGHT_PLACE,
    reference_remap: Path = REFERENCE_REMAP,
    taxonomy_active: Path = TAXONOMY_ACTIVE,
    reference_active: Path = REFERENCE_ACTIVE,
    source_conflict_active: Path = SOURCE_CONFLICT_ACTIVE,
    taxonomy_todo: Path = TAXONOMY_TODO,
    reference_todo: Path = REFERENCE_TODO,
    source_conflict_todo: Path = SOURCE_CONFLICT_TODO,
    summary_out: Path = SUMMARY,
    markdown_out: Path = MD,
) -> dict[str, object]:
    right_rows = load_rows(right_place)
    reference_rows = load_rows(reference_remap)

    taxonomy_rows = build_taxonomy_todo(right_rows)
    reference_todo_rows = build_reference_todo(reference_rows)
    conflict_rows = build_source_conflict_todo(right_rows)

    write_csv(taxonomy_todo, TAXONOMY_TODO_FIELDS, taxonomy_rows)
    write_csv(reference_todo, REFERENCE_TODO_FIELDS, reference_todo_rows)
    write_csv(source_conflict_todo, SOURCE_CONFLICT_TODO_FIELDS, conflict_rows)

    created = {
        "taxonomy_active_created": create_active_file_if_missing(taxonomy_active, TAXONOMY_ACTIVE_FIELDS),
        "reference_active_created": create_active_file_if_missing(reference_active, REFERENCE_ACTIVE_FIELDS),
        "source_conflict_active_created": create_active_file_if_missing(source_conflict_active, SOURCE_CONFLICT_ACTIVE_FIELDS),
    }
    taxonomy_counts = Counter(row.get("issue_family", "") or "unknown" for row in taxonomy_rows)
    reference_counts = Counter(row.get("issue_family", "") or "unknown" for row in reference_todo_rows)
    conflict_counts = Counter(row.get("issue_family", "") or "unknown" for row in conflict_rows)
    summary = {
        "right_place_source": str(right_place),
        "reference_remap_source": str(reference_remap),
        "taxonomy_todo": str(taxonomy_todo),
        "reference_todo": str(reference_todo),
        "source_conflict_todo": str(source_conflict_todo),
        "taxonomy_todo_rows": len(taxonomy_rows),
        "reference_todo_rows": len(reference_todo_rows),
        "source_conflict_todo_rows": len(conflict_rows),
        "taxonomy_issue_counts": dict(taxonomy_counts.most_common()),
        "reference_issue_counts": dict(reference_counts.most_common()),
        "source_conflict_issue_counts": dict(conflict_counts.most_common()),
        **created,
    }
    summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    markdown_out.write_text(build_markdown(summary), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--right-place", type=Path, default=RIGHT_PLACE)
    parser.add_argument("--reference-remap", type=Path, default=REFERENCE_REMAP)
    parser.add_argument("--summary-out", type=Path, default=SUMMARY)
    parser.add_argument("--markdown-out", type=Path, default=MD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_work_queues(
        right_place=args.right_place,
        reference_remap=args.reference_remap,
        summary_out=args.summary_out,
        markdown_out=args.markdown_out,
    )
    print(json.dumps({
        "taxonomy_todo_rows": summary["taxonomy_todo_rows"],
        "reference_todo_rows": summary["reference_todo_rows"],
        "source_conflict_todo_rows": summary["source_conflict_todo_rows"],
        "active_files_created": {
            "taxonomy": summary["taxonomy_active_created"],
            "reference": summary["reference_active_created"],
            "source_conflict": summary["source_conflict_active_created"],
        },
    }, indent=2))


if __name__ == "__main__":
    main()
