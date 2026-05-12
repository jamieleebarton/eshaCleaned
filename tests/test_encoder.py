#!/usr/bin/env python3
"""Encoder ground-truth test runner.

For each row of tests/encoder_truth.csv:
  - Run the recipe-side encoder via encode(category="", description=item, food_name=item)
  - Assert h.group == expected_group
  - Replicate the build_recipe_concept_grams.py cp derivation:
      cp = item_overrides[item] OR htc_to_path[htc_form] OR title_to_path[item]
  - Assert expected_cp_contains is a substring of derived cp

Run after ANY change to:
  - recipe_mapper/v1/htc/encoder.py
  - recipe_mapper/v1/htc/food_slots.py
  - recipe_mapper/v1/htc/food_slot_registry.csv
  - recipe_pricing/htc_cp_overrides.csv
  - recipe_mapper/v1/output/consensus_htc_tagged.csv (if its tagging changes)

Exit non-zero on any failure. Suitable for pre-commit / CI gate.
"""
from __future__ import annotations
import csv, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recipe_mapper" / "v1"))
csv.field_size_limit(2**30)

from htc.encoder import encode  # noqa: E402

TRUTH_CSV = Path(__file__).parent / "encoder_truth.csv"
HTC_TAGGED = ROOT / "recipe_mapper" / "v1" / "output" / "consensus_htc_tagged.csv"
V2_TAXONOMY = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
OVERRIDES = ROOT / "recipe_pricing" / "htc_cp_overrides.csv"

RAW_TOPS = {"Pantry", "Produce", "Dairy", "Meat & Seafood",
            "Bakery", "Frozen", "Beverage"}
MIN_FDC_AGREE = 2


def load_htc_to_path() -> dict[str, str]:
    htc_cp_counts: dict[str, Counter] = {}
    with HTC_TAGGED.open() as f:
        for row in csv.DictReader(f):
            h = (row.get("htc_code") or "").strip().lstrip("~")
            cp = (row.get("canonical_path") or "").strip()
            if not (h and cp): continue
            if cp == "Pantry" or cp.startswith("Non-Food"): continue
            htc_cp_counts.setdefault(h, Counter())[cp] += 1
    out: dict[str, str] = {}
    for h, c in htc_cp_counts.items():
        raw = [(cp, n) for cp, n in c.items()
               if (cp.split(" > ")[0] if cp else "") in RAW_TOPS]
        if raw:
            raw.sort(key=lambda x: -x[1]); top_cp, top_n = raw[0]
        else:
            top_cp, top_n = c.most_common(1)[0]
        if top_n >= MIN_FDC_AGREE:
            out[h] = top_cp
    return out


def load_title_to_path() -> dict[str, str]:
    out: dict[str, str] = {}
    with V2_TAXONOMY.open() as f:
        for row in csv.DictReader(f):
            t = (row.get("title") or "").strip().lower()
            cp = (row.get("canonical_path") or "").strip()
            if t and cp: out[t] = cp
    return out


def load_overrides() -> dict[str, str]:
    out: dict[str, str] = {}
    with OVERRIDES.open() as f:
        for row in csv.DictReader(f):
            t = (row.get("item") or "").strip().lower()
            cp = (row.get("canonical_path") or "").strip()
            if t and cp: out[t] = cp
    return out


def derive_cp(item: str, htc_code: str, overrides, htc_to_path, title_to_path) -> str:
    return (overrides.get(item) or htc_to_path.get(htc_code) or title_to_path.get(item, ""))


def main() -> int:
    htc_to_path = load_htc_to_path()
    title_to_path = load_title_to_path()
    overrides = load_overrides()

    truth: list[dict] = []
    with TRUTH_CSV.open() as f:
        for row in csv.DictReader(f):
            truth.append(row)

    passed = group_failed = cp_failed = 0
    failures: list[tuple[str, str, str]] = []  # (item, type, message)

    for row in truth:
        item = (row["item"] or "").strip().lower()
        exp_group = (row["expected_group"] or "").strip()
        exp_cp_contains = (row["expected_cp_contains"] or "").strip()
        if not item: continue

        h = encode(category="", description=item, extra="", food_name=item)
        ok = True

        # Group check
        if exp_group and h.group != exp_group:
            group_failed += 1
            failures.append((item, "GROUP",
                             f"expected g{exp_group}, got g{h.group}"))
            ok = False

        # CP-contains check (uses downstream pipeline derivation)
        derived_cp = derive_cp(item, h.code, overrides, htc_to_path, title_to_path)
        if exp_cp_contains and exp_cp_contains.lower() not in derived_cp.lower():
            cp_failed += 1
            failures.append((item, "CP",
                             f"expected cp containing {exp_cp_contains!r}, got {derived_cp!r}"))
            ok = False

        if ok:
            passed += 1

    total = len(truth)
    print(f"\n=== Encoder ground-truth tests ===")
    print(f"  Truth set:  {total} rows")
    print(f"  Passed:     {passed}  ({100*passed/total:.1f}%)")
    print(f"  Failed:     {total-passed}")
    print(f"    — wrong group:   {group_failed}")
    print(f"    — wrong cp:      {cp_failed}")

    if failures:
        print(f"\n  Failures (first 30):")
        for item, kind, msg in failures[:30]:
            print(f"    [{kind}] {item:<35s} {msg}")
        if len(failures) > 30:
            print(f"    ... +{len(failures)-30} more")
        return 1
    print("\n  ALL PASS ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
