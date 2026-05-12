#!/usr/bin/env python3
"""Build the corpus-learned HTC ingredient pricing bridge.

Outputs:
  htc_ingredient_candidates_v1.csv
  htc_learned_contracts_v1.jsonl
  htc_product_offer_bridge_v1.csv
  htc_coverage_summary_v1.json
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path

from htc_learned_bridge_v1 import (
    DEFAULT_AUDIT,
    DEFAULT_CONSENSUS_HTC,
    DEFAULT_INGREDIENT_HTC,
    DEFAULT_INGREDIENT_SR28,
    DEFAULT_PRICED_DB,
    DEFAULT_PRODUCT_EVIDENCE,
    bridge_row,
    candidate_row,
    generate_candidates,
    learn_contract,
    load_evidence_index,
    load_ingredient_profiles,
    load_product_records,
    pick_product_for_contract,
    product_index,
    summary_from_rows,
)

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "output"
OUT_CANDIDATES = OUT_DIR / "htc_ingredient_candidates_v1.csv"
OUT_CONTRACTS = OUT_DIR / "htc_learned_contracts_v1.jsonl"
OUT_BRIDGE = OUT_DIR / "htc_product_offer_bridge_v1.csv"
OUT_SUMMARY = OUT_DIR / "htc_coverage_summary_v1.json"


def write_candidates(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "ingredient_item",
        "recipe_count",
        "ingredient_htc_code",
        "ingredient_identity_terms",
        "candidate_rank",
        "candidate_pid",
        "candidate_canonical",
        "candidate_modifier",
        "candidate_count",
        "candidate_htc_prefixes",
        "score",
        "margin_to_next",
        "identity_score",
        "reference_score",
        "htc_score",
        "path_score",
        "provenance_score",
        "source",
        "hard_vetoes",
        "evidence",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_contracts(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_bridge(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "ingredient_item",
        "recipe_count",
        "contract_status",
        "offer_status",
        "terminal_status",
        "concept_pid",
        "canonical_path",
        "modifier",
        "required_terms",
        "forbidden_terms",
        "allowed_paths",
        "allowed_htc_prefixes",
        "contract_confidence",
        "review_reason",
        "product_rowid",
        "source",
        "upc",
        "name",
        "grams",
        "cents",
        "cpg",
        "product_identity",
        "product_canonical_path",
        "product_modifier",
        "product_score",
        "product_taxonomy_status",
        "product_evidence_score",
        "reject_reason",
        "rejected_summary",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build(args: argparse.Namespace) -> dict[str, object]:
    t0 = time.time()
    print(f"loading ingredient HTC tags: {args.ingredients}")
    profiles = load_ingredient_profiles(args.ingredients, args.sr28, top_n=args.top_n)
    total_recipe_lines = sum(profile.recipe_count for profile in load_ingredient_profiles(args.ingredients, args.sr28, top_n=0))
    print(f"  {len(profiles):,} ingredient profiles selected")

    print(f"loading consensus evidence index: {args.audit}")
    evidence_index = load_evidence_index(args.audit, args.consensus_htc)
    print(f"  {len(evidence_index.concepts):,} concept evidence groups")

    print(f"loading priced products: {args.priced_db}")
    products = load_product_records(
        args.priced_db,
        args.product_evidence,
        include_quarantine_without_veto=args.include_quarantine_without_veto,
        limit=args.product_limit,
    )
    product_idx = product_index(products)
    print(f"  {len(products):,} priced products indexed")

    candidate_rows: list[dict[str, object]] = []
    contract_rows: list[dict[str, object]] = []
    bridge_rows: list[dict[str, object]] = []
    contract_status_counts: Counter[str] = Counter()

    for i, profile in enumerate(profiles, 1):
        candidates = generate_candidates(profile, evidence_index, limit=args.candidate_limit)
        for rank, candidate in enumerate(candidates, 1):
            runner = candidates[rank] if rank < len(candidates) else None
            margin = candidate.total() - runner.total() if runner else 999.0
            candidate_rows.append(candidate_row(profile, candidate, rank, margin))

        contract = learn_contract(profile, candidates, evidence_index)
        contract_rows.append(contract.to_dict())
        contract_status_counts[contract.status] += 1
        match = pick_product_for_contract(contract, product_idx, cap=args.max_products_per_ingredient)
        bridge_rows.append(bridge_row(contract, match))

        if i % 250 == 0:
            print(f"  bridged {i:,}/{len(profiles):,} ingredients", flush=True)

    summary = summary_from_rows(bridge_rows, total_recipe_lines=total_recipe_lines)
    summary.update({
        "elapsed_s": round(time.time() - t0, 1),
        "top_n": args.top_n,
        "concept_evidence_groups": len(evidence_index.concepts),
        "priced_products_indexed": len(products),
        "candidate_rows": len(candidate_rows),
        "contract_status_counts": dict(contract_status_counts.most_common()),
        "inputs": {
            "audit": str(args.audit),
            "consensus_htc": str(args.consensus_htc),
            "ingredients": str(args.ingredients),
            "sr28": str(args.sr28),
            "priced_db": str(args.priced_db),
            "product_evidence": str(args.product_evidence),
        },
    })

    write_candidates(args.candidates_out, candidate_rows)
    write_contracts(args.contracts_out, contract_rows)
    write_bridge(args.bridge_out, bridge_rows)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(f"wrote {args.candidates_out}")
    print(f"wrote {args.contracts_out}")
    print(f"wrote {args.bridge_out}")
    print(f"wrote {args.summary_out}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--consensus-htc", type=Path, default=DEFAULT_CONSENSUS_HTC)
    parser.add_argument("--ingredients", type=Path, default=DEFAULT_INGREDIENT_HTC)
    parser.add_argument("--sr28", type=Path, default=DEFAULT_INGREDIENT_SR28)
    parser.add_argument("--priced-db", type=Path, default=DEFAULT_PRICED_DB)
    parser.add_argument("--product-evidence", type=Path, default=DEFAULT_PRODUCT_EVIDENCE)
    parser.add_argument("--top-n", type=int, default=2500)
    parser.add_argument("--candidate-limit", type=int, default=20)
    parser.add_argument("--product-limit", type=int, default=0)
    parser.add_argument("--max-products-per-ingredient", type=int, default=2500)
    parser.add_argument("--include-quarantine-without-veto", action="store_true")
    parser.add_argument("--candidates-out", type=Path, default=OUT_CANDIDATES)
    parser.add_argument("--contracts-out", type=Path, default=OUT_CONTRACTS)
    parser.add_argument("--bridge-out", type=Path, default=OUT_BRIDGE)
    parser.add_argument("--summary-out", type=Path, default=OUT_SUMMARY)
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
