#!/usr/bin/env python3
"""Fail rebuilt planner artifacts when concept pools contain wrong-class SKUs.

This is an audit gate, not picker filtering. A failure means the SKU or recipe
concept belongs in a different canonical path/HTC code before the planner runs.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from planner.form_facet_audit import concept_sku_class_findings  # noqa: E402


BANNED_RESOLUTION_PAIRS = [
    ("Produce > Vegetables > Avocado", "Grape Leaves"),
    ("Produce > Vegetables > Baby Carrots", "Peas"),
    ("Dairy > Cheese > Cheddar", "Snack Stick"),
    ("Dairy > Cheese > Cheddar", "String Cheese"),
    ("Pantry > Oil > Vegetable Oil", "Vegetable Oil Stick"),
    ("Pantry > Oil > Vegetable Oil", "Margarine"),
    ("Pantry > Sweeteners > Sugar > Brown", "Agave"),
    ("Pantry > Spices & Seasonings > Oregano", "Bay Leaves"),
    ("Pantry > Spices & Seasonings > Cumin", "Bay Leaves"),
    ("Dairy > Cream", "Finishing Sugar"),
    ("Meat & Seafood > Bacon", "Veggie"),
    ("Meat & Seafood > Bacon", "MorningStar"),
    ("Meat & Seafood > Bacon", "Meatless"),
    ("Produce > Fruit > Limes", "Citrus Splash"),
    ("Frozen > Vegetables > Pierogies", "Mashed Potatoes"),
    ("Pantry > Sauces & Salsas > Hot Pepper", "Hollandaise"),
]


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def package_names(row: dict) -> list[str]:
    return [pkg.get("name", "") for pkg in row.get("packages", []) if pkg.get("name")]


def audit_concept_index(concept_index: dict) -> list[dict]:
    findings: list[dict] = []
    for concept_key, row in concept_index.items():
        names = package_names(row)
        for finding in concept_sku_class_findings(concept_key, names):
            findings.append({
                "gate": "concept_package_class",
                "concept_key": concept_key,
                "issue_type": finding.issue_type,
                "severity": finding.severity,
                "message": finding.message,
                "expected": finding.expected,
                "actual": finding.actual,
            })
    return findings


def audit_known_resolutions(concept_resolution: dict, concept_index: dict) -> list[dict]:
    findings: list[dict] = []
    for concept_fragment, sku_fragment in BANNED_RESOLUTION_PAIRS:
        concept_fragment_l = concept_fragment.lower()
        sku_fragment_l = sku_fragment.lower()
        for recipe_key, resolution in concept_resolution.items():
            if concept_fragment_l not in recipe_key.lower():
                continue
            priced_key = resolution.get("priced_key")
            if not priced_key:
                continue
            priced = concept_index.get(priced_key) or {}
            priced_path = priced.get("canonical_path", "")
            package_blob = " || ".join(package_names(priced))
            if sku_fragment_l in priced_path.lower() or sku_fragment_l in package_blob.lower():
                findings.append({
                    "gate": "known_resolution_misroute",
                    "recipe_concept_key": recipe_key,
                    "priced_concept_key": priced_key,
                    "resolution_tier": resolution.get("tier", ""),
                    "banned_concept_fragment": concept_fragment,
                    "banned_sku_fragment": sku_fragment,
                    "actual": priced_path or package_blob,
                })
                break
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concept-index", type=Path, default=ROOT / "planner/data/concept_index.json")
    parser.add_argument("--concept-resolution", type=Path, default=ROOT / "planner/data/concept_resolution.json")
    parser.add_argument("--out-json", type=Path)
    args = parser.parse_args()

    concept_index = load_json(args.concept_index)
    concept_resolution = load_json(args.concept_resolution)
    findings = audit_concept_index(concept_index)
    findings.extend(audit_known_resolutions(concept_resolution, concept_index))

    by_gate = Counter(row["gate"] for row in findings)
    summary = {
        "concept_index": str(args.concept_index),
        "concept_resolution": str(args.concept_resolution),
        "concept_keys_scanned": len(concept_index),
        "package_rows_scanned": sum(len(package_names(row)) for row in concept_index.values()),
        "finding_count": len(findings),
        "by_gate": dict(sorted(by_gate.items())),
    }

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps({"summary": summary, "findings": findings}, indent=2))

    print(
        f"concept package class audit: {summary['finding_count']} findings "
        f"across {summary['concept_keys_scanned']} concepts / "
        f"{summary['package_rows_scanned']} package rows"
    )
    print(f"by gate: {summary['by_gate']}")
    if args.out_json:
        print(f"-> {args.out_json}")
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
