"""Run every retail product through every shipped ESHA contract.

For each branded product in master_products.db, build a ProductFacts and
evaluate it against the subset of contracts whose allowed_categories overlap
the product's category. Emits a CSV of (gtin, product_description, category,
brand_owner, esha_code, esha_description) for each accept decision.

Pre-indexes contracts by category-token so we don't run all 26,918 contracts
against every product. Typical product checks ~50-200 contracts.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPL = ROOT / "implementation"
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

import esha_contracts.reviewed_nebius_generated as mod
from esha_contracts.contract_base import ProductFacts
from match_esha_to_products import normalize_text, tokens_for

PRODUCTS_DB = ROOT / "data" / "master_products.db"
OUT = ROOT / "implementation" / "output" / "product_inference_to_esha.csv"


def build_category_index(specs: dict) -> dict[str, list[str]]:
    """Map each category token / normalized-phrase to contract codes that allow it."""
    index: dict[str, list[str]] = defaultdict(list)
    for code, spec in specs.items():
        for cat in spec.get("allowed_categories") or []:
            for tok in tokens_for(cat):
                index[tok].append(code)
            index["__phrase__::" + normalize_text(cat)].append(code)
    return index


def candidates_for_product(category: str, index: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    cat_norm = normalize_text(category)
    for tok in tokens_for(category):
        if tok in index:
            out.update(index[tok])
    phrase_key = "__phrase__::" + cat_norm
    if phrase_key in index:
        out.update(index[phrase_key])
    return out


def main() -> None:
    print(f"loaded {len(mod.GENERATED_CONTRACT_SPECS):,} contracts")
    index = build_category_index(mod.GENERATED_CONTRACT_SPECS)
    print(f"category index: {len(index):,} tokens/phrases")
    contracts = mod.CONTRACTS

    OUT.parent.mkdir(parents=True, exist_ok=True)
    accept_rows = 0
    product_count = 0
    t0 = time.time()
    with sqlite3.connect(PRODUCTS_DB) as con, OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["gtin_upc", "product_description", "branded_food_category", "brand_owner", "esha_code", "esha_description"])
        cursor = con.execute(
            "SELECT gtin_upc, description, branded_food_category, brand_owner, ingredients FROM products"
        )
        for gtin, desc, cat, brand, ingredients in cursor:
            if not gtin or not desc:
                continue
            product_count += 1
            cat = cat or ""
            try:
                pf = ProductFacts.from_components(desc, cat, ingredients or "")
            except Exception:
                continue
            for code in candidates_for_product(cat, index):
                contract = contracts.get(code)
                if contract is None:
                    continue
                decision = contract(pf)
                if decision.status != "accept":
                    continue
                spec = mod.GENERATED_CONTRACT_SPECS[code]
                writer.writerow([gtin, desc, cat, brand or "", code, spec.get("esha_description", "")])
                accept_rows += 1
            if product_count % 50000 == 0:
                print(f"  {product_count:,} products / {accept_rows:,} accepts in {time.time()-t0:.1f}s")

    print(f"\nwrote {accept_rows:,} accepts across {product_count:,} products in {time.time()-t0:.1f}s")
    print(f"  {OUT}")


if __name__ == "__main__":
    main()
