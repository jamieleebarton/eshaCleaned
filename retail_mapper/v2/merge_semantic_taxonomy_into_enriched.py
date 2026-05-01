#!/usr/bin/env python3
"""Append semantic taxonomy outputs to the enriched retail leaf CSV.

The enriched file contains the evidence block intended for LLM review. The
semantic taxonomy file contains the deterministic answer we can produce from
that evidence. This merge keeps the original evidence columns intact and adds a
prefixed, repeatable taxonomy layer:

    semantic_product_identity
    semantic_canonical_path
    semantic_canonical_label
    semantic_node_id
    semantic_flavor / semantic_claims / ...

The source CSV has quoted multiline evidence fields, so this script must use
``csv`` instead of line-oriented tools.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


csv.field_size_limit(sys.maxsize)

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"

DEFAULT_ENRICHED = V2 / "retail_leaf_v2_enriched_v2.csv"
DEFAULT_SEMANTIC = V2 / "semantic_product_taxonomy.csv"
DEFAULT_ASSIGNMENTS = V2 / "semantic_taxonomy_product_assignments.csv"
DEFAULT_SUMMARY = V2 / "retail_leaf_v2_enriched_v2.semantic_merge_summary.json"

SEMANTIC_FIELD_MAP = [
    ("source_clean_retail_leaf", "semantic_source_clean_retail_leaf"),
    ("source_parser_primary_food", "semantic_source_parser_primary_food"),
    ("source_parser_form", "semantic_source_parser_form"),
    ("source_parser_flavor", "semantic_source_parser_flavor"),
    ("retail_type", "semantic_retail_type"),
    ("category_path", "semantic_category_path"),
    ("taxonomy_head", "semantic_taxonomy_head"),
    ("base_identity", "semantic_base_identity"),
    ("product_identity", "semantic_product_identity"),
    ("variant", "semantic_variant"),
    ("flavor", "semantic_flavor"),
    ("form_texture_cut", "semantic_form_texture_cut"),
    ("processing_storage", "semantic_processing_storage"),
    ("claims", "semantic_claims"),
    ("canonical_path", "semantic_canonical_path"),
    ("existing_taxonomy_path", "semantic_existing_taxonomy_path"),
    ("canonical_label", "semantic_canonical_label"),
    ("identity_source", "semantic_identity_source"),
    ("confidence", "semantic_confidence"),
    ("mint_required", "semantic_mint_required"),
    ("review_flags", "semantic_review_flags"),
    ("notes", "semantic_notes"),
    ("attributes_json", "semantic_attributes_json"),
]

SEMANTIC_OUTPUT_FIELDS = ["semantic_node_id"] + [target for _source, target in SEMANTIC_FIELD_MAP]


def load_index(path: Path, fields: Iterable[str] | None = None) -> tuple[dict[str, dict[str, str]], Counter[str]]:
    """Load a CSV keyed by fdc_id and keep only requested fields."""
    index: dict[str, dict[str, str]] = {}
    stats: Counter[str] = Counter()
    wanted = set(fields or [])

    with path.open(newline="", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stats["rows"] += 1
            fdc_id = row.get("fdc_id", "")
            if not fdc_id:
                stats["blank_fdc_id"] += 1
                continue
            if fdc_id in index:
                stats["duplicate_fdc_id"] += 1
            if wanted:
                index[fdc_id] = {field: row.get(field, "") for field in wanted}
            else:
                index[fdc_id] = dict(row)

    stats["unique_fdc_id"] = len(index)
    return index, stats


def semantic_values(
    fdc_id: str,
    semantic_index: dict[str, dict[str, str]],
    assignment_index: dict[str, dict[str, str]],
) -> dict[str, str]:
    semantic = semantic_index.get(fdc_id, {})
    assignment = assignment_index.get(fdc_id, {})
    values = {"semantic_node_id": assignment.get("node_id", "")}
    for source, target in SEMANTIC_FIELD_MAP:
        values[target] = semantic.get(source, "")
    return values


def merge_rows(
    rows: Iterable[dict[str, str]],
    base_fields: list[str],
    semantic_index: dict[str, dict[str, str]],
    assignment_index: dict[str, dict[str, str]],
) -> tuple[list[dict[str, str]], Counter[str]]:
    """Small in-memory merge helper used by tests."""
    stats: Counter[str] = Counter()
    merged: list[dict[str, str]] = []
    for row in rows:
        stats["rows_read"] += 1
        fdc_id = row.get("fdc_id", "")
        out = {field: row.get(field, "") for field in base_fields}
        out.update(semantic_values(fdc_id, semantic_index, assignment_index))
        if fdc_id in semantic_index:
            stats["semantic_matched"] += 1
        else:
            stats["semantic_missing"] += 1
        if fdc_id in assignment_index:
            stats["assignment_matched"] += 1
        else:
            stats["assignment_missing"] += 1
        merged.append(out)
    stats["rows_written"] = len(merged)
    return merged, stats


def output_fields(input_fields: list[str]) -> list[str]:
    base_fields = [field for field in input_fields if field not in SEMANTIC_OUTPUT_FIELDS]
    return base_fields + SEMANTIC_OUTPUT_FIELDS


def write_summary(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def merge(args: argparse.Namespace) -> dict[str, object]:
    semantic_fields = [source for source, _target in SEMANTIC_FIELD_MAP]
    print(f"loading semantic rows: {args.semantic}", flush=True)
    semantic_index, semantic_stats = load_index(args.semantic, fields=semantic_fields)
    print(f"  semantic rows: {semantic_stats['rows']:,}", flush=True)

    print(f"loading taxonomy assignments: {args.assignments}", flush=True)
    assignment_index, assignment_stats = load_index(args.assignments, fields=["node_id"])
    print(f"  assignment rows: {assignment_stats['rows']:,}", flush=True)

    output_path = args.output or args.enriched
    replace_input = output_path == args.enriched
    temp_path = output_path.with_name(f".{output_path.name}.semantic_merge.{os.getpid()}.tmp")

    stats: Counter[str] = Counter()
    print(f"merging enriched rows: {args.enriched}", flush=True)
    with args.enriched.open(newline="", errors="replace") as fin:
        reader = csv.DictReader(fin)
        if reader.fieldnames is None:
            raise ValueError(f"{args.enriched} has no CSV header")
        fieldnames = output_fields(reader.fieldnames)
        base_fields = [field for field in fieldnames if field not in SEMANTIC_OUTPUT_FIELDS]

        with temp_path.open("w", newline="") as fout:
            writer = csv.DictWriter(fout, fieldnames=fieldnames)
            writer.writeheader()
            for row in reader:
                stats["rows_read"] += 1
                fdc_id = row.get("fdc_id", "")
                out = {field: row.get(field, "") for field in base_fields}
                out.update(semantic_values(fdc_id, semantic_index, assignment_index))

                if fdc_id in semantic_index:
                    stats["semantic_matched"] += 1
                else:
                    stats["semantic_missing"] += 1
                if fdc_id in assignment_index:
                    stats["assignment_matched"] += 1
                else:
                    stats["assignment_missing"] += 1

                writer.writerow(out)
                stats["rows_written"] += 1
                if args.limit and stats["rows_written"] >= args.limit:
                    break
                if stats["rows_written"] % 50000 == 0:
                    print(f"  wrote {stats['rows_written']:,}", flush=True)

    if not args.limit and stats["rows_read"] != stats["rows_written"]:
        raise RuntimeError(f"read {stats['rows_read']:,} rows but wrote {stats['rows_written']:,}")

    if replace_input:
        temp_path.replace(args.enriched)
        final_output = args.enriched
    else:
        temp_path.replace(output_path)
        final_output = output_path

    payload: dict[str, object] = {
        "input": str(args.enriched),
        "output": str(final_output),
        "semantic_input": str(args.semantic),
        "assignment_input": str(args.assignments),
        "rows_read": stats["rows_read"],
        "rows_written": stats["rows_written"],
        "semantic_matched": stats["semantic_matched"],
        "semantic_missing": stats["semantic_missing"],
        "assignment_matched": stats["assignment_matched"],
        "assignment_missing": stats["assignment_missing"],
        "semantic_stats": dict(semantic_stats),
        "assignment_stats": dict(assignment_stats),
        "appended_fields": SEMANTIC_OUTPUT_FIELDS,
    }
    write_summary(args.summary, payload)
    print(f"wrote {final_output}", flush=True)
    print(f"wrote {args.summary}", flush=True)
    print(json.dumps({key: payload[key] for key in ("rows_written", "semantic_missing", "assignment_missing")}, sort_keys=True), flush=True)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge semantic taxonomy fields into the enriched retail leaf CSV.")
    parser.add_argument("--enriched", type=Path, default=DEFAULT_ENRICHED)
    parser.add_argument("--semantic", type=Path, default=DEFAULT_SEMANTIC)
    parser.add_argument("--assignments", type=Path, default=DEFAULT_ASSIGNMENTS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=None, help="Optional alternate output path. Defaults to replacing --enriched.")
    parser.add_argument("--limit", type=int, default=0, help="Testing only: write at most this many enriched rows.")
    return parser.parse_args()


if __name__ == "__main__":
    merge(parse_args())
