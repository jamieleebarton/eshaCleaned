#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from build_hestia_esha_native_artifacts import _esha_identity_gate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "implementation" / "output" / "product_esha_fixy.csv"
DEFAULT_OUTPUT = ROOT / "implementation" / "output" / "product_esha_fixy.identity_gated.csv"
DEFAULT_REJECTS = ROOT / "implementation" / "output" / "product_esha_fixy.identity_rejects.csv"
DEFAULT_SUMMARY = ROOT / "implementation" / "output" / "product_esha_fixy.identity_gated.summary.json"

ADDED_COLUMNS = [
    "identity_gate_action",
    "identity_gate_reason",
    "identity_gate_product_reason",
    "identity_gate_fndds_reason",
    "identity_gate_accept_source",
    "identity_gate_original_best_esha_code",
    "identity_gate_original_best_esha_description",
]


def _gate_text(text: str, esha_description: str) -> tuple[bool, str]:
    text = (text or "").strip()
    if not text:
        return False, "missing_text"
    return _esha_identity_gate(text, esha_description)


def gate_row(row: dict[str, str]) -> tuple[str, dict[str, str]]:
    esha_code = (row.get("best_esha_code") or "").strip()
    esha_description = (row.get("best_esha_description") or "").strip()
    if not esha_code or not esha_description:
        return "keep_unassigned", {
            "identity_gate_action": "keep_unassigned",
            "identity_gate_reason": "no_best_esha",
            "identity_gate_product_reason": "",
            "identity_gate_fndds_reason": "",
            "identity_gate_accept_source": "",
            "identity_gate_original_best_esha_code": esha_code,
            "identity_gate_original_best_esha_description": esha_description,
        }

    product_ok, product_reason = _gate_text(row.get("product_description") or "", esha_description)
    fndds_ok, fndds_reason = _gate_text(row.get("fndds_main_description") or "", esha_description)

    accept_sources: list[str] = []
    if product_ok:
        accept_sources.append("product")
    if fndds_ok:
        accept_sources.append("fndds")

    if accept_sources:
        return "keep", {
            "identity_gate_action": "keep",
            "identity_gate_reason": "identity_overlap:" + ",".join(accept_sources),
            "identity_gate_product_reason": product_reason,
            "identity_gate_fndds_reason": fndds_reason,
            "identity_gate_accept_source": ",".join(accept_sources),
            "identity_gate_original_best_esha_code": esha_code,
            "identity_gate_original_best_esha_description": esha_description,
        }

    return "blank", {
        "identity_gate_action": "blank",
        "identity_gate_reason": "product_and_fndds_reject_best_esha",
        "identity_gate_product_reason": product_reason,
        "identity_gate_fndds_reason": fndds_reason,
        "identity_gate_accept_source": "",
        "identity_gate_original_best_esha_code": esha_code,
        "identity_gate_original_best_esha_description": esha_description,
    }


def build_gated_map(input_csv: Path, output_csv: Path, rejects_csv: Path, summary_json: Path) -> dict[str, Any]:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    rejects_csv.parent.mkdir(parents=True, exist_ok=True)
    stats: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    reject_examples: list[dict[str, str]] = []

    with input_csv.open(newline="", encoding="utf-8-sig", errors="replace") as in_handle:
        reader = csv.DictReader(in_handle)
        if not reader.fieldnames:
            raise ValueError(f"{input_csv} has no header")
        fieldnames = list(reader.fieldnames)
        for column in ADDED_COLUMNS:
            if column not in fieldnames:
                fieldnames.append(column)

        reject_fieldnames = [
            "gtin_upc",
            "fdc_id",
            "product_description",
            "branded_food_category",
            "brand_owner",
            "brand_name",
            "best_esha_code",
            "best_esha_description",
            "fndds_main_code",
            "fndds_main_description",
            "audit_bucket",
            *ADDED_COLUMNS,
        ]

        tmp_output = output_csv.with_suffix(output_csv.suffix + ".tmp")
        tmp_rejects = rejects_csv.with_suffix(rejects_csv.suffix + ".tmp")
        with tmp_output.open("w", newline="", encoding="utf-8") as out_handle, tmp_rejects.open(
            "w", newline="", encoding="utf-8"
        ) as reject_handle:
            writer = csv.DictWriter(out_handle, fieldnames=fieldnames, extrasaction="ignore")
            reject_writer = csv.DictWriter(reject_handle, fieldnames=reject_fieldnames, extrasaction="ignore")
            writer.writeheader()
            reject_writer.writeheader()

            for row in reader:
                stats["rows"] += 1
                action, annotations = gate_row(row)
                stats[action] += 1
                reason_counts[annotations["identity_gate_reason"]] += 1

                original_code = row.get("best_esha_code", "")
                original_description = row.get("best_esha_description", "")
                row.update(annotations)
                if action == "blank":
                    row["best_esha_code"] = ""
                    row["best_esha_description"] = ""
                    row["fixy_cluster_fix_action"] = row.get("fixy_cluster_fix_action") or "blank"
                    row["fixy_cluster_fix_reason"] = (
                        row.get("fixy_cluster_fix_reason") or "identity_gate_product_and_fndds_reject_best_esha"
                    )
                    reject_row = dict(row)
                    reject_row["best_esha_code"] = original_code
                    reject_row["best_esha_description"] = original_description
                    reject_writer.writerow(reject_row)
                    if len(reject_examples) < 25:
                        reject_examples.append({key: str(reject_row.get(key, "")) for key in reject_fieldnames})
                writer.writerow(row)

        tmp_output.replace(output_csv)
        tmp_rejects.replace(rejects_csv)

    summary = {
        "input_csv": str(input_csv),
        "output_csv": str(output_csv),
        "rejects_csv": str(rejects_csv),
        "stats": dict(stats),
        "top_reasons": reason_counts.most_common(25),
        "reject_examples": reject_examples,
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blank product->ESHA rows that fail product/FNDDS identity gating.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rejects-csv", type=Path, default=DEFAULT_REJECTS)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_gated_map(
        args.input_csv.expanduser(),
        args.output_csv.expanduser(),
        args.rejects_csv.expanduser(),
        args.summary_json.expanduser(),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
