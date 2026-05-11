#!/usr/bin/env python3
"""Run the authoritative pricing/planner rebuild in the required order."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

COMMANDS = [
    ["python3", "recipe_pricing/consolidate_reviewed_portions.py"],
    ["python3", "recipe_pricing/reclassify_canonical_paths.py"],
    ["python3", "recipe_pricing/reencode_after_reclassify.py"],
    ["python3", "recipe_pricing/retag_recipes_unified.py"],
    ["python3", "recipe_pricing/repair_total_weight_range_grams.py"],
    ["python3", "recipe_pricing/normalize_grams_to_sr28.py"],
    ["python3", "recipe_pricing/normalize_grams_modal_deterministic.py", "--all-deterministic-drift"],
    [
        "python3",
        "recipe_pricing/audit_gram_determinism.py",
        "--fail-on-drift",
        "--max-drift-tuples",
        "0",
        "--max-high-ratio-tuples",
        "0",
    ],
    ["python3", "recipe_pricing/preflight_data_contract.py"],
    ["python3", "planner/scripts/build_concept_index.py"],
    ["python3", "planner/scripts/build_recipe_concept_grams.py"],
    ["python3", "planner/scripts/build_concept_resolution.py"],
    ["python3", "recipe_pricing/audit_concept_package_classes.py"],
    ["python3", "planner/build_concept_tensor_cache.py"],
    ["python3", "recipe_pricing/preflight_data_contract.py"],
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print commands without running")
    args = parser.parse_args()

    for index, command in enumerate(COMMANDS, start=1):
        printable = " ".join(command)
        print(f"\n[{index}/{len(COMMANDS)}] {printable}", flush=True)
        if args.dry_run:
            continue
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
