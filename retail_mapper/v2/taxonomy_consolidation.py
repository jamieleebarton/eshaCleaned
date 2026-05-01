#!/usr/bin/env python3
"""Measure taxonomy consolidation: how many distinct product_identities does
the model produce, and which categories are exploding into too many nodes?

Usage:
  python3 retail_mapper/v2/taxonomy_consolidation.py \
    --live retail_mapper/v2/llm_taxonomy_diabolical_v2_deepseek.live.jsonl \
    --gold retail_mapper/v2/llm_taxonomy_diabolical_v2_cases.jsonl

Outputs a per-category report:
  - distinct gold identities in this category
  - distinct LLM-emitted identities in this category
  - explosion ratio (LLM / gold) — 1.0 = perfect, >1.0 = explosion
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import sys
from pathlib import Path
from collections import defaultdict


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--cleanup", type=Path,
                        default=Path("retail_mapper/v2/llm_taxonomy_cleanup.py"))
    parser.add_argument("--apply-normalizer", action="store_true", default=True)
    args = parser.parse_args()

    sp = importlib.util.spec_from_file_location("ltc", args.cleanup)
    m = importlib.util.module_from_spec(sp); sys.modules["ltc"] = m
    sp.loader.exec_module(m)

    gold = {c["name"]: c for c in (json.loads(l) for l in args.gold.open())}
    live = {r["case"]: r for r in (json.loads(l) for l in args.live.open())}

    # Gold identities by category_path
    gold_ids_by_cat: dict[str, set[str]] = defaultdict(set)
    for c in gold.values():
        e = c["expected"]
        gold_ids_by_cat[e["category_path"]].add(e["product_identity"])

    # LLM (post-normalizer) identities by GOLD category_path (so we compare apples to apples)
    llm_ids_by_cat: dict[str, set[str]] = defaultdict(set)
    llm_categories: set[str] = set()
    case_count_by_cat: dict[str, int] = defaultdict(int)
    invalid_retail_types: list[str] = []
    for case_name, case in gold.items():
        out = live.get(case_name)
        if not out:
            continue
        rec = out.get("record", {})
        if "_parse_error" in rec or "_api_error" in rec:
            continue
        if args.apply_normalizer:
            rec = m.normalize_record(rec, case["source"])
        gold_cat = case["expected"]["category_path"]
        case_count_by_cat[gold_cat] += 1
        llm_ids_by_cat[gold_cat].add(str(rec.get("product_identity", "")))
        llm_categories.add(str(rec.get("category_path") or ""))
        rt = rec.get("retail_type", "")
        if rt not in m.RETAIL_TYPES:
            invalid_retail_types.append(f"{case_name}: retail_type={rt!r}")

    # Build report
    print("=" * 100)
    print("CONSOLIDATION REPORT")
    print("=" * 100)
    print(f"{'category':40s}  {'cases':>6s}  {'gold_ids':>9s}  {'llm_ids':>9s}  {'ratio':>7s}  status")
    print("-" * 100)
    total_cases = 0
    total_gold = 0
    total_llm = 0
    rows = sorted(gold_ids_by_cat.items())
    for cat, gold_set in rows:
        n_cases = case_count_by_cat.get(cat, 0)
        if n_cases == 0:
            continue
        n_gold = len(gold_set)
        n_llm = len(llm_ids_by_cat.get(cat, set()))
        ratio = n_llm / n_gold if n_gold else 0.0
        status = "OK" if n_llm == n_gold else (f"EXPLOSION (+{n_llm-n_gold})" if n_llm > n_gold else f"COLLAPSED (-{n_gold-n_llm})")
        print(f"{cat:40s}  {n_cases:>6d}  {n_gold:>9d}  {n_llm:>9d}  {ratio:>7.2f}  {status}")
        total_cases += n_cases
        total_gold += n_gold
        total_llm += n_llm
    print("-" * 100)
    print(f"{'TOTAL':40s}  {total_cases:>6d}  {total_gold:>9d}  {total_llm:>9d}")

    # Explosion details — LLM identities that aren't in gold
    print()
    print("=" * 100)
    print("LLM-INVENTED IDENTITIES (not in gold for that category)")
    print("=" * 100)
    for cat in sorted(gold_ids_by_cat):
        gold_set = gold_ids_by_cat[cat]
        llm_set = llm_ids_by_cat.get(cat, set())
        invented = sorted(llm_set - gold_set)
        if invented:
            print(f"\n{cat}:")
            print(f"  gold:     {sorted(gold_set)}")
            print(f"  invented: {invented}")

    if invalid_retail_types:
        print()
        print("=" * 100)
        print("INVALID retail_type VALUES (model emitted values outside enum)")
        print("=" * 100)
        for line in invalid_retail_types:
            print(f"  {line}")

    print()
    print("Distinct LLM category_paths emitted:", len(llm_categories))


if __name__ == "__main__":
    main()
