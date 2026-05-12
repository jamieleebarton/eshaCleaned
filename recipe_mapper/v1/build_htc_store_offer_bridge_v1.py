#!/usr/bin/env python3
"""Build store-separated learned HTC offer coverage.

The main bridge chooses one best offer across all retailers. This audit keeps
Kroger and Walmart separate so PLU/fresh coverage and retailer-specific gaps are
visible instead of being collapsed into one product choice.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path

from htc_learned_bridge_v1 import (
    DEFAULT_INGREDIENT_HTC,
    DEFAULT_INGREDIENT_SR28,
    DEFAULT_PRICED_DB,
    DEFAULT_PRODUCT_EVIDENCE,
    LearnedContract,
    bridge_row,
    load_ingredient_profiles,
    load_product_records,
    pick_product_for_contract,
    product_index,
    summary_from_rows,
)

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "output"
DEFAULT_CONTRACTS = OUT_DIR / "htc_learned_contracts_v1.jsonl"
OUT_BRIDGE = OUT_DIR / "htc_store_offer_bridge_v1.csv"
OUT_SUMMARY = OUT_DIR / "htc_store_coverage_summary_v1.json"

BRIDGE_FIELDS = [
    "store_scope",
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


def tuple_field(row: dict[str, object], key: str) -> tuple[str, ...]:
    value = row.get(key)
    if isinstance(value, list):
        return tuple(str(v) for v in value if str(v))
    if isinstance(value, str) and value:
        return tuple(v for v in value.split("|") if v)
    return ()


def load_contracts(path: Path) -> list[LearnedContract]:
    contracts: list[LearnedContract] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            contracts.append(LearnedContract(
                ingredient_item=str(row.get("ingredient_item") or ""),
                recipe_count=int(float(row.get("recipe_count") or 0)),
                status=str(row.get("status") or ""),
                concept_pid=str(row.get("shopping_concept") or ""),
                canonical=str(row.get("canonical_path") or ""),
                modifier=str(row.get("modifier") or ""),
                htc_code=str(row.get("htc_code") or ""),
                allowed_htc_prefixes=tuple_field(row, "allowed_htc_prefixes"),
                required_terms=tuple_field(row, "required_terms"),
                forbidden_terms=tuple_field(row, "forbidden_terms"),
                allowed_paths=tuple_field(row, "allowed_paths"),
                allowed_forms=tuple_field(row, "allowed_forms"),
                proxy_policy=str(row.get("proxy_policy") or "none"),
                confidence=float(row.get("confidence") or 0),
                evidence=tuple_field(row, "evidence"),
                review_reason=str(row.get("review_reason") or ""),
            ))
    return contracts


def write_bridge(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BRIDGE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def safe_status(status: str) -> bool:
    return status in {"safe_priced", "safe_tap_water"}


def cross_store_summary(
    contracts: list[LearnedContract],
    rows_by_store: dict[str, list[dict[str, object]]],
    stores: list[str],
    *,
    total_recipe_lines: int,
) -> dict[str, object]:
    by_store_item = {
        store: {str(row["ingredient_item"]): row for row in rows}
        for store, rows in rows_by_store.items()
    }
    either_lines = 0
    both_lines = 0
    either_items = 0
    both_items = 0
    unresolved_line_counts: Counter[str] = Counter()
    for contract in contracts:
        statuses = [
            str(by_store_item.get(store, {}).get(contract.ingredient_item, {}).get("terminal_status") or "")
            for store in stores
        ]
        if any(safe_status(status) for status in statuses):
            either_items += 1
            either_lines += contract.recipe_count
        else:
            unresolved_line_counts[contract.status] += contract.recipe_count
        if statuses and all(safe_status(status) for status in statuses):
            both_items += 1
            both_lines += contract.recipe_count
    scored_lines = sum(contract.recipe_count for contract in contracts)
    return {
        "either_store_safe_items": either_items,
        "both_store_safe_items": both_items,
        "either_store_safe_recipe_lines": either_lines,
        "both_store_safe_recipe_lines": both_lines,
        "either_store_safe_line_pct_of_scored": round(either_lines / scored_lines * 100, 2) if scored_lines else 0.0,
        "both_store_safe_line_pct_of_scored": round(both_lines / scored_lines * 100, 2) if scored_lines else 0.0,
        "either_store_safe_lower_bound_pct_of_full_corpus": round(either_lines / total_recipe_lines * 100, 2) if total_recipe_lines else 0.0,
        "both_store_safe_lower_bound_pct_of_full_corpus": round(both_lines / total_recipe_lines * 100, 2) if total_recipe_lines else 0.0,
        "neither_store_unresolved_line_counts_by_contract_status": dict(unresolved_line_counts.most_common()),
    }


def build(args: argparse.Namespace) -> dict[str, object]:
    t0 = time.time()
    stores = [store.strip().lower() for store in args.store if store.strip()]
    contracts = load_contracts(args.contracts)
    total_recipe_lines = sum(
        profile.recipe_count
        for profile in load_ingredient_profiles(args.ingredients, args.sr28, top_n=0)
    )
    products = load_product_records(
        args.priced_db,
        args.product_evidence,
        include_quarantine_without_veto=args.include_quarantine_without_veto,
        limit=args.product_limit,
    )

    rows: list[dict[str, object]] = []
    rows_by_store: dict[str, list[dict[str, object]]] = {}
    indexed_counts: dict[str, int] = {}
    for store in stores:
        store_products = [product for product in products if product.source.lower() == store]
        indexed_counts[store] = len(store_products)
        idx = product_index(store_products)
        store_rows: list[dict[str, object]] = []
        for contract in contracts:
            match = pick_product_for_contract(contract, idx, cap=args.max_products_per_ingredient)
            row = bridge_row(contract, match)
            row["store_scope"] = store
            store_rows.append(row)
            rows.append(row)
        rows_by_store[store] = store_rows

    per_store = {
        store: summary_from_rows(store_rows, total_recipe_lines=total_recipe_lines)
        for store, store_rows in rows_by_store.items()
    }
    summary = {
        "elapsed_s": round(time.time() - t0, 1),
        "stores": stores,
        "contracts": len(contracts),
        "priced_products_indexed_by_store": indexed_counts,
        "per_store": per_store,
        "cross_store": cross_store_summary(
            contracts,
            rows_by_store,
            stores,
            total_recipe_lines=total_recipe_lines,
        ),
        "inputs": {
            "contracts": str(args.contracts),
            "ingredients": str(args.ingredients),
            "sr28": str(args.sr28),
            "priced_db": str(args.priced_db),
            "product_evidence": str(args.product_evidence),
        },
    }

    write_bridge(args.bridge_out, rows)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {args.bridge_out}")
    print(f"wrote {args.summary_out}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS)
    parser.add_argument("--ingredients", type=Path, default=DEFAULT_INGREDIENT_HTC)
    parser.add_argument("--sr28", type=Path, default=DEFAULT_INGREDIENT_SR28)
    parser.add_argument("--priced-db", type=Path, default=DEFAULT_PRICED_DB)
    parser.add_argument("--product-evidence", type=Path, default=DEFAULT_PRODUCT_EVIDENCE)
    parser.add_argument("--store", action="append", default=None)
    parser.add_argument("--product-limit", type=int, default=0)
    parser.add_argument("--max-products-per-ingredient", type=int, default=2500)
    parser.add_argument("--include-quarantine-without-veto", action="store_true", default=True)
    parser.add_argument("--bridge-out", type=Path, default=OUT_BRIDGE)
    parser.add_argument("--summary-out", type=Path, default=OUT_SUMMARY)
    args = parser.parse_args()
    if args.store is None:
        args.store = ["kroger", "walmart"]
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
