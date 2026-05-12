#!/usr/bin/env python3
"""Apply reviewed consensus overrides without mutating the consensus source.

The active override files are intentionally small, human-reviewable layers on
top of consensus_full_corpus_audit.csv. Rows are applied only when status is an
approved value. Candidate/todo rows stay inert so Codex and Claude can share
queues without accidentally changing the corpus.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

from taxonomy_finalizer import (
    PATH_SEP,
    _canonical_from_category_identity,
    dedupe_segments,
    normalize_path,
    path_defects,
    split_path,
)


V2 = Path(__file__).resolve().parent
DEFAULT_SOURCE = V2 / "consensus_full_corpus_audit.csv"
DEFAULT_TAXONOMY_OVERRIDES = V2 / "consensus_taxonomy_overrides.csv"
DEFAULT_STORAGE_TAXONOMY_OVERRIDES = V2 / "consensus_storage_taxonomy_overrides.csv"
DEFAULT_SHAPE_TAXONOMY_OVERRIDES = V2 / "consensus_shape_taxonomy_overrides.csv"
DEFAULT_SNACK_TAXONOMY_OVERRIDES = V2 / "consensus_snack_taxonomy_overrides.csv"
DEFAULT_REFERENCE_OVERRIDES = V2 / "consensus_reference_overrides.csv"
DEFAULT_SOURCE_CONFLICTS = V2 / "consensus_source_conflicts.csv"
DEFAULT_OUT = V2 / "consensus_full_corpus_audit.v2.csv"
DEFAULT_DECISIONS = V2 / "consensus_full_corpus_audit.v2_decisions.csv"
DEFAULT_SUMMARY_DECISIONS = V2 / "consensus_apply_decision_log.csv"
DEFAULT_REPORT = V2 / "consensus_full_corpus_audit.v2_report.json"
DEFAULT_MD = V2 / "consensus_full_corpus_audit.v2.md"

csv.field_size_limit(sys.maxsize)

APPROVED_STATUSES = {"approved", "apply", "accepted"}
BLANK_SENTINELS = {"<blank>", "__blank__", "__empty__", "∅"}

TAXONOMY_FIELDS = [
    "retail_type",
    "category_path_fixed",
    "product_identity_fixed",
    "canonical_path",
    "canonical_label",
    "variant",
    "flavor",
    "form_texture_cut",
    "processing_storage",
    "claims",
    "components_count",
    "components",
    "confidence",
    "mint_required",
    "review_flags",
    "rationale",
    "modifier",
    "retail_leaf_path",
]

REFERENCE_FIELDS = [
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

SOURCE_CONFLICT_FIELDS = [
    "branded_food_category_corrected",
    "source_conflict_note",
    "source_conflict_action",
]

EXTRA_OUTPUT_FIELDS = [
    "override_source",
    "override_reason",
    "branded_food_category_corrected",
    "source_conflict_note",
    "source_conflict_action",
]

DECISION_FIELDS = [
    "override_type",
    "fdc_id",
    "owner",
    "issue_family",
    "status",
    "reason",
    "field",
    "old_value",
    "new_value",
]

SUMMARY_DECISION_FIELDS = [
    "fdc_id",
    "title",
    "change_type",
    "owner",
    "issue_family",
    "status",
    "old_category_path",
    "new_category_path",
    "old_product_identity",
    "new_product_identity",
    "old_canonical_path",
    "new_canonical_path",
    "old_retail_leaf_path",
    "new_retail_leaf_path",
    "old_matched_key",
    "new_matched_key",
    "source_conflict_action",
    "reason",
]


def sort_fdc(value: str) -> tuple[int, int | str]:
    value = (value or "").strip()
    return (0, int(value)) if value.isdigit() else (1, value)


def normalized_status(value: str) -> str:
    return (value or "").strip().lower()


def should_apply(row: Mapping[str, str], *, apply_draft: bool = False) -> bool:
    status = normalized_status(row.get("status", ""))
    if status in APPROVED_STATUSES:
        return True
    if apply_draft and status in {"candidate", "todo", "draft", "reviewed"}:
        return True
    return False


def override_value(raw: str) -> str:
    value = (raw or "").strip()
    return "" if value.lower() in BLANK_SENTINELS else value


def has_override_value(row: Mapping[str, str], field: str) -> bool:
    return field in row and (row.get(field) or "").strip() != ""


def normalize_legacy_override(override_type: str, override: Mapping[str, str], stats: Counter[str]) -> dict[str, str]:
    """Map earlier review CSV shapes into the active override schema.

    Legacy rows still require an approved status before they apply. This only
    prevents an approved old-schema row from becoming an accidental no-op.
    """
    row = dict(override)
    mapped = False
    if override_type in {"taxonomy", "storage_taxonomy", "shape_taxonomy", "snack_taxonomy"}:
        if has_override_value(row, "new_product_identity") and not has_override_value(row, "product_identity_fixed"):
            row["product_identity_fixed"] = row.get("new_product_identity", "") or ""
            mapped = True
        if has_override_value(row, "new_canonical_path"):
            if has_override_value(row, "category_path_fixed") and has_override_value(row, "product_identity_fixed"):
                # Current active rows keep new_canonical_path as a compatibility
                # alias for the target shelf. Let repair_taxonomy_after_override
                # derive the actual canonical_path from category + identity.
                pass
            elif has_override_value(row, "product_identity_fixed") and not has_override_value(row, "category_path_fixed"):
                row["category_path_fixed"] = row.get("new_canonical_path", "") or ""
                mapped = True
            elif not has_override_value(row, "canonical_path"):
                row["canonical_path"] = row.get("new_canonical_path", "") or ""
                mapped = True
    elif override_type == "source_conflict":
        if has_override_value(row, "likely_fix") and not has_override_value(row, "source_conflict_note"):
            row["source_conflict_note"] = row.get("likely_fix", "") or ""
            mapped = True
    if not has_override_value(row, "reason"):
        for fallback in ("reason", "likely_fix", "rationale"):
            if has_override_value(row, fallback):
                row["reason"] = row.get(fallback, "") or ""
                mapped = True
                break
    if mapped:
        stats[f"{override_type}:legacy_schema_mapped"] += 1
    return row


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def load_override_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    return load_csv_rows(path)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def ensure_fields(fieldnames: list[str], extra_fields: Iterable[str]) -> list[str]:
    out = list(fieldnames)
    for field in extra_fields:
        if field not in out:
            out.append(field)
    return out


def build_index(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        fdc = (row.get("fdc_id") or "").strip()
        if fdc and fdc not in index:
            index[fdc] = row
    return index


def current_modifier_tail(row: Mapping[str, str]) -> str:
    modifier = normalize_path(row.get("modifier", "") or "")
    if modifier:
        return modifier
    canonical = normalize_path(row.get("canonical_path", "") or "")
    leaf = normalize_path(row.get("retail_leaf_path", "") or "")
    if canonical and leaf.startswith(canonical + PATH_SEP):
        return leaf[len(canonical + PATH_SEP) :]
    return ""


def repair_taxonomy_after_override(row: dict[str, str], provided_fields: set[str]) -> None:
    """Keep path contract coherent after partial taxonomy overrides.

    If a reviewer provides only category/identity, derive canonical_path and
    retail_leaf_path from those reviewed fields plus the existing modifier.
    Explicit canonical_path or retail_leaf_path override values always win.
    """
    category_changed = bool({"category_path_fixed", "product_identity_fixed"} & provided_fields)
    canonical_changed = "canonical_path" in provided_fields
    leaf_changed = "retail_leaf_path" in provided_fields
    modifier_changed = "modifier" in provided_fields

    if category_changed and not canonical_changed:
        row["canonical_path"] = _canonical_from_category_identity(
            row.get("category_path_fixed", "") or "",
            row.get("product_identity_fixed", "") or "",
        )
        canonical_changed = True

    if (category_changed or canonical_changed or modifier_changed) and not leaf_changed:
        canonical = normalize_path(row.get("canonical_path", "") or "")
        modifier = normalize_path(row.get("modifier", "") or "") if modifier_changed else current_modifier_tail(row)
        if canonical and modifier:
            row["retail_leaf_path"] = PATH_SEP.join(dedupe_segments(split_path(canonical) + split_path(modifier)))
        else:
            row["retail_leaf_path"] = canonical

    for field in ("category_path_fixed", "canonical_path", "modifier", "retail_leaf_path"):
        if row.get(field):
            row[field] = normalize_path(row.get(field, "") or "")

    canonical = row.get("canonical_path", "") or ""
    leaf = row.get("retail_leaf_path", "") or ""
    if canonical and leaf == canonical:
        row["modifier"] = ""
    elif canonical and leaf.startswith(canonical + PATH_SEP):
        row["modifier"] = leaf[len(canonical + PATH_SEP) :]

    canonical_parts = split_path(row.get("canonical_path", "") or "")
    category = row.get("category_path_fixed", "") or ""
    if canonical_parts and category and not row["canonical_path"].startswith(category + PATH_SEP) and row["canonical_path"] != category:
        row["category_path_fixed"] = PATH_SEP.join(canonical_parts[:-1])
        row["product_identity_fixed"] = canonical_parts[-1]


def apply_field_updates(
    row: dict[str, str],
    override: Mapping[str, str],
    fields: Iterable[str],
) -> tuple[list[tuple[str, str, str]], set[str]]:
    changes: list[tuple[str, str, str]] = []
    provided: set[str] = set()
    for field in fields:
        if not has_override_value(override, field):
            continue
        new_value = override_value(override.get(field, "") or "")
        old_value = row.get(field, "") or ""
        provided.add(field)
        if old_value != new_value:
            row[field] = new_value
            changes.append((field, old_value, new_value))
    return changes, provided


def append_decisions(
    decisions: list[dict[str, str]],
    *,
    override_type: str,
    override: Mapping[str, str],
    changes: Iterable[tuple[str, str, str]],
) -> None:
    for field, old_value, new_value in changes:
        decisions.append({
            "override_type": override_type,
            "fdc_id": (override.get("fdc_id") or "").strip(),
            "owner": override.get("owner", "") or "",
            "issue_family": override.get("issue_family", "") or "",
            "status": override.get("status", "") or "",
            "reason": override.get("reason", "") or "",
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
        })


def append_summary_decision(
    summaries: list[dict[str, str]],
    *,
    override_type: str,
    override: Mapping[str, str],
    before: Mapping[str, str],
    after: Mapping[str, str],
) -> None:
    summaries.append({
        "fdc_id": (override.get("fdc_id") or "").strip(),
        "title": after.get("title", "") or override.get("title", "") or "",
        "change_type": override_type,
        "owner": override.get("owner", "") or "",
        "issue_family": override.get("issue_family", "") or "",
        "status": override.get("status", "") or "",
        "old_category_path": before.get("category_path_fixed", "") or "",
        "new_category_path": after.get("category_path_fixed", "") or "",
        "old_product_identity": before.get("product_identity_fixed", "") or "",
        "new_product_identity": after.get("product_identity_fixed", "") or "",
        "old_canonical_path": before.get("canonical_path", "") or "",
        "new_canonical_path": after.get("canonical_path", "") or "",
        "old_retail_leaf_path": before.get("retail_leaf_path", "") or "",
        "new_retail_leaf_path": after.get("retail_leaf_path", "") or "",
        "old_matched_key": before.get("matched_key", "") or "",
        "new_matched_key": after.get("matched_key", "") or "",
        "source_conflict_action": after.get("source_conflict_action", "") or "",
        "reason": override.get("reason", "") or override.get("likely_fix", "") or "",
    })


def apply_override_rows(
    rows_by_fdc: dict[str, dict[str, str]],
    override_rows: Iterable[Mapping[str, str]],
    *,
    override_type: str,
    fields: list[str],
    apply_draft: bool,
    decisions: list[dict[str, str]],
    summaries: list[dict[str, str]],
    stats: Counter[str],
) -> None:
    for raw_override in override_rows:
        override = normalize_legacy_override(override_type, raw_override, stats)
        stats[f"{override_type}:loaded"] += 1
        status = normalized_status(override.get("status", ""))
        if not should_apply(override, apply_draft=apply_draft):
            stats[f"{override_type}:skipped_status:{status or 'blank'}"] += 1
            continue
        fdc = (override.get("fdc_id") or "").strip()
        row = rows_by_fdc.get(fdc)
        if row is None:
            stats[f"{override_type}:skipped_missing_fdc"] += 1
            continue

        before = dict(row)
        changes, provided = apply_field_updates(row, override, fields)
        if override_type in {"taxonomy", "storage_taxonomy", "shape_taxonomy", "snack_taxonomy"} and provided:
            repair_taxonomy_after_override(row, provided)
            for field in TAXONOMY_FIELDS:
                if before.get(field, "") != row.get(field, "") and all(change[0] != field for change in changes):
                    changes.append((field, before.get(field, "") or "", row.get(field, "") or ""))
        if override_type == "source_conflict" and has_override_value(override, "branded_food_category_corrected"):
            action = normalized_status(override.get("source_conflict_action", ""))
            if action in {"replace_branded_food_category", "replace_bfc"}:
                new_bfc = override_value(override.get("branded_food_category_corrected", "") or "")
                old_bfc = row.get("branded_food_category", "") or ""
                if old_bfc != new_bfc:
                    row["branded_food_category"] = new_bfc
                    changes.append(("branded_food_category", old_bfc, new_bfc))

        if changes:
            tag = f"{override_type}:{override.get('issue_family', '') or 'manual'}"
            row["override_source"] = tag
            row["override_reason"] = override.get("reason", "") or override.get("likely_fix", "") or ""
            changes.append(("override_source", before.get("override_source", "") or "", row["override_source"]))
            if before.get("override_reason", "") != row.get("override_reason", ""):
                changes.append(("override_reason", before.get("override_reason", "") or "", row["override_reason"]))
            append_summary_decision(
                summaries,
                override_type=override_type,
                override=override,
                before=before,
                after=row,
            )
            append_decisions(decisions, override_type=override_type, override=override, changes=changes)
            stats[f"{override_type}:applied"] += 1
            stats[f"{override_type}:changed_fields"] += len(changes)
        else:
            stats[f"{override_type}:applied_noop"] += 1


def quality_metrics(rows: list[dict[str, str]]) -> dict[str, object]:
    fdc_counts = Counter((row.get("fdc_id") or "").strip() for row in rows)
    defects: Counter[str] = Counter()
    empty_leaf = 0
    for row in rows:
        if not (row.get("retail_leaf_path") or "").strip():
            empty_leaf += 1
        for defect in path_defects(row):
            defects[defect] += 1
    return {
        "rows": len(rows),
        "unique_fdc_ids": len(fdc_counts),
        "duplicate_extra_rows": sum(count - 1 for count in fdc_counts.values() if count > 1),
        "empty_retail_leaf_path_rows": empty_leaf,
        "path_defect_rows": sum(defects.values()),
        "path_defects": dict(defects.most_common()),
    }


def build_markdown(report: Mapping[str, object]) -> str:
    metrics = report["quality_metrics"]  # type: ignore[index]
    stats = report["override_stats"]  # type: ignore[index]
    lines = [
        "# Consensus Full Corpus Audit v2",
        "",
        "Generated from `consensus_full_corpus_audit.csv` plus approved override layers.",
        "",
        f"Rows: `{metrics['rows']:,}`",
        f"Unique FDC ids: `{metrics['unique_fdc_ids']:,}`",
        f"Duplicate extra rows: `{metrics['duplicate_extra_rows']:,}`",
        f"Empty retail leaf rows: `{metrics['empty_retail_leaf_path_rows']:,}`",
        f"Path defect rows: `{metrics['path_defect_rows']:,}`",
        "",
        "## Override Stats",
        "",
    ]
    if stats:
        for key, value in sorted(stats.items()):
            lines.append(f"- `{key}`: `{value:,}`")
    else:
        lines.append("- No override files loaded.")
    lines.extend([
        "",
        "## Workflow",
        "",
        "- Only rows with `status` in `approved`, `apply`, or `accepted` are applied by default.",
        "- Blank override cells mean no change. Use `<blank>` to intentionally clear a field.",
        "- Reviewer todo queues are separate from active override files.",
        "- `consensus_apply_decision_log.csv` is per-FDC; `consensus_full_corpus_audit.v2_decisions.csv` is field-level.",
    ])
    return "\n".join(lines)


def apply_overrides(
    *,
    source: Path = DEFAULT_SOURCE,
    taxonomy_overrides: Path = DEFAULT_TAXONOMY_OVERRIDES,
    storage_taxonomy_overrides: Path = DEFAULT_STORAGE_TAXONOMY_OVERRIDES,
    shape_taxonomy_overrides: Path = DEFAULT_SHAPE_TAXONOMY_OVERRIDES,
    snack_taxonomy_overrides: Path = DEFAULT_SNACK_TAXONOMY_OVERRIDES,
    reference_overrides: Path = DEFAULT_REFERENCE_OVERRIDES,
    source_conflicts: Path = DEFAULT_SOURCE_CONFLICTS,
    out: Path = DEFAULT_OUT,
    decisions_out: Path = DEFAULT_DECISIONS,
    summary_decisions_out: Path | None = None,
    report_out: Path = DEFAULT_REPORT,
    markdown_out: Path = DEFAULT_MD,
    apply_draft: bool = False,
) -> dict[str, object]:
    if summary_decisions_out is None:
        summary_decisions_out = decisions_out.with_name("consensus_apply_decision_log.csv")
    source_fields, rows = load_csv_rows(source)
    output_fields = ensure_fields(source_fields, EXTRA_OUTPUT_FIELDS)
    rows_by_fdc = build_index(rows)
    decisions: list[dict[str, str]] = []
    summaries: list[dict[str, str]] = []
    stats: Counter[str] = Counter()

    _, taxonomy_rows = load_override_rows(taxonomy_overrides)
    _, storage_taxonomy_rows = load_override_rows(storage_taxonomy_overrides)
    _, shape_taxonomy_rows = load_override_rows(shape_taxonomy_overrides)
    _, snack_taxonomy_rows = load_override_rows(snack_taxonomy_overrides)
    _, reference_rows = load_override_rows(reference_overrides)
    _, conflict_rows = load_override_rows(source_conflicts)

    apply_override_rows(
        rows_by_fdc,
        taxonomy_rows,
        override_type="taxonomy",
        fields=TAXONOMY_FIELDS,
        apply_draft=apply_draft,
        decisions=decisions,
        summaries=summaries,
        stats=stats,
    )
    apply_override_rows(
        rows_by_fdc,
        storage_taxonomy_rows,
        override_type="storage_taxonomy",
        fields=TAXONOMY_FIELDS,
        apply_draft=apply_draft,
        decisions=decisions,
        summaries=summaries,
        stats=stats,
    )
    apply_override_rows(
        rows_by_fdc,
        shape_taxonomy_rows,
        override_type="shape_taxonomy",
        fields=TAXONOMY_FIELDS,
        apply_draft=apply_draft,
        decisions=decisions,
        summaries=summaries,
        stats=stats,
    )
    apply_override_rows(
        rows_by_fdc,
        snack_taxonomy_rows,
        override_type="snack_taxonomy",
        fields=TAXONOMY_FIELDS,
        apply_draft=apply_draft,
        decisions=decisions,
        summaries=summaries,
        stats=stats,
    )
    apply_override_rows(
        rows_by_fdc,
        reference_rows,
        override_type="reference",
        fields=REFERENCE_FIELDS,
        apply_draft=apply_draft,
        decisions=decisions,
        summaries=summaries,
        stats=stats,
    )
    apply_override_rows(
        rows_by_fdc,
        conflict_rows,
        override_type="source_conflict",
        fields=SOURCE_CONFLICT_FIELDS,
        apply_draft=apply_draft,
        decisions=decisions,
        summaries=summaries,
        stats=stats,
    )

    rows.sort(key=lambda row: sort_fdc(row.get("fdc_id", "")))
    summaries.sort(key=lambda row: sort_fdc(row.get("fdc_id", "")))
    write_csv(out, output_fields, rows)
    write_csv(decisions_out, DECISION_FIELDS, decisions)
    write_csv(summary_decisions_out, SUMMARY_DECISION_FIELDS, summaries)

    changed_fdc_ids = {decision["fdc_id"] for decision in decisions if decision.get("fdc_id")}
    issue_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for decision in decisions:
        issue_counts[decision["override_type"]][decision.get("issue_family", "") or "manual"] += 1

    report = {
        "sources": {
            "consensus": str(source),
            "taxonomy_overrides": str(taxonomy_overrides),
            "storage_taxonomy_overrides": str(storage_taxonomy_overrides),
            "shape_taxonomy_overrides": str(shape_taxonomy_overrides),
            "snack_taxonomy_overrides": str(snack_taxonomy_overrides),
            "reference_overrides": str(reference_overrides),
            "source_conflicts": str(source_conflicts),
        },
        "outputs": {
            "csv": str(out),
            "decisions": str(decisions_out),
            "summary_decisions": str(summary_decisions_out),
            "report": str(report_out),
            "markdown": str(markdown_out),
        },
        "apply_draft": apply_draft,
        "override_stats": dict(stats),
        "changed_fdc_ids": len(changed_fdc_ids),
        "summary_decision_rows": len(summaries),
        "changed_field_decisions": len(decisions),
        "changed_issue_counts": {key: dict(counter.most_common()) for key, counter in issue_counts.items()},
        "quality_metrics": quality_metrics(rows),
    }
    report_out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_out.write_text(build_markdown(report), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--taxonomy-overrides", type=Path, default=DEFAULT_TAXONOMY_OVERRIDES)
    parser.add_argument("--storage-taxonomy-overrides", type=Path, default=DEFAULT_STORAGE_TAXONOMY_OVERRIDES)
    parser.add_argument("--shape-taxonomy-overrides", type=Path, default=DEFAULT_SHAPE_TAXONOMY_OVERRIDES)
    parser.add_argument("--snack-taxonomy-overrides", type=Path, default=DEFAULT_SNACK_TAXONOMY_OVERRIDES)
    parser.add_argument("--reference-overrides", type=Path, default=DEFAULT_REFERENCE_OVERRIDES)
    parser.add_argument("--source-conflicts", type=Path, default=DEFAULT_SOURCE_CONFLICTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--decisions-out", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--summary-decisions-out", type=Path, default=DEFAULT_SUMMARY_DECISIONS)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MD)
    parser.add_argument(
        "--apply-draft",
        action="store_true",
        help="Also apply todo/candidate/draft rows. Intended only for local experiments.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = apply_overrides(
        source=args.source,
        taxonomy_overrides=args.taxonomy_overrides,
        storage_taxonomy_overrides=args.storage_taxonomy_overrides,
        shape_taxonomy_overrides=args.shape_taxonomy_overrides,
        snack_taxonomy_overrides=args.snack_taxonomy_overrides,
        reference_overrides=args.reference_overrides,
        source_conflicts=args.source_conflicts,
        out=args.out,
        decisions_out=args.decisions_out,
        summary_decisions_out=args.summary_decisions_out,
        report_out=args.report_out,
        markdown_out=args.markdown_out,
        apply_draft=args.apply_draft,
    )
    print(json.dumps({
        "rows": report["quality_metrics"]["rows"],  # type: ignore[index]
        "changed_fdc_ids": report["changed_fdc_ids"],
        "changed_field_decisions": report["changed_field_decisions"],
        "quality_metrics": report["quality_metrics"],
        "outputs": report["outputs"],
    }, indent=2))


if __name__ == "__main__":
    main()
