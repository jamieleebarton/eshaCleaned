#!/usr/bin/env python3
"""Promote rows from consensus_taxonomy_overrides.todo.csv to the active
override file (consensus_taxonomy_overrides.csv) with proposed_* columns
filled and status=approved for deterministic families.

Per Codex's apply contract:
- Approved rows have status ∈ {approved, apply, accepted}.
- Each row supplies proposed_canonical_path + proposed_product_identity_fixed.
- proposed_category_path_fixed = first 2 segments of proposed_canonical_path.
- proposed_retail_leaf_path is left blank — apply script derives it from
  category + identity + existing modifier.

Manual-review and policy-decision rows are written WITHOUT a status so
they remain inert until human review.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

V2 = Path(__file__).resolve().parent
TODO = V2 / "consensus_taxonomy_overrides.todo.csv"
ACTIVE = V2 / "consensus_taxonomy_overrides.csv"

csv.field_size_limit(sys.maxsize)


def family_to_target(family: str, row: dict) -> tuple[str, str, str] | None:
    """Map (family, row) → (canonical_path, identity, reason). None = skip."""
    title = (row.get("title") or "").lower()

    if family == "sandwich_cookie_or_cracker_routed_as_meal_sandwich":
        if "cracker" in title:
            return "Snack > Crackers", "Sandwich Crackers", \
                   "Sandwich-style cracker product (e.g., peanut butter crackers); not a deli sandwich"
        return "Bakery > Cookies", "Sandwich Cookies", \
               "Sandwich-style cookie product (e.g., Oreos); not a deli sandwich"

    if family == "frozen_appetizer_sandwich_not_frozen":
        if any(w in title for w in ("appetizer", "slider", "bite", "mini")):
            return "Frozen > Appetizers", "Sandwich Appetizers", \
                   "Frozen sandwich appetizers/sliders/bites belong in Frozen > Appetizers"
        if "pocket" in title:
            return "Frozen > Sandwiches", "Sandwich Pockets", \
                   "Frozen sandwich pockets belong in Frozen > Sandwiches"
        return "Frozen > Sandwiches", "Frozen Sandwich", \
               "Frozen sandwich product; keep Frozen prefix"

    if family == "soup_chowder_or_bisque_routed_as_seafood":
        if "chowder" in title:
            return "Pantry > Soup > Chowder", "Chowder", \
                   "Seafood chowder belongs in Pantry > Soup, not Meat & Seafood"
        if "bisque" in title:
            return "Pantry > Soup > Bisque", "Bisque", \
                   "Seafood bisque belongs in Pantry > Soup, not Meat & Seafood"
        return "Pantry > Soup", "Soup", \
               "Seafood soup belongs in Pantry > Soup, not Meat & Seafood"

    if family == "dip_salsa_or_cocktail_sauce_routed_as_seafood":
        if "salsa" in title:
            return "Pantry > Sauces & Salsas > Salsa", "Salsa", \
                   "Salsa with seafood ingredient; route to Pantry > Sauces & Salsas"
        if "cocktail sauce" in title:
            return "Pantry > Sauces & Salsas > Cocktail Sauce", "Cocktail Sauce", \
                   "Cocktail sauce → Pantry > Sauces & Salsas"
        if "dip" in title:
            return "Pantry > Dips & Spreads > Dip", "Dip", \
                   "Seafood-flavored dip → Pantry > Dips & Spreads"
        return "Pantry > Sauces & Salsas", "Sauce", \
               "Seafood-flavored sauce → Pantry > Sauces & Salsas"

    if family == "pickle_sandwich_slices_routed_as_meal_sandwich":
        return "Pantry > Pickles > Pickle Slices", "Pickle Slices", \
               "Pickle slices, not a sandwich"

    if family == "seasoning_marinade_routed_as_meat_or_seafood":
        if "rub" in title:
            return "Pantry > Spices & Seasonings > Rub", "Rub", \
                   "Rub/seasoning, not the protein"
        if "marinade" in title:
            return "Pantry > Sauces & Salsas > Marinade", "Marinade", \
                   "Marinade, not the protein"
        if "seasoning" in title:
            return "Pantry > Spices & Seasonings", "Seasoning", \
                   "Seasoning, not the protein"
        return "Pantry > Spices & Seasonings", "Seasoning", \
               "Seasoning/marinade, not the protein"

    if family == "cheese_slices_routed_as_meal_sandwich":
        return "Dairy > Cheese > Slices", "Cheese Slices", \
               "Cheese slices/singles, not a deli sandwich"

    if family == "mexican_dinner_mix_left_in_baking_mixes":
        return "Pantry > Mexican Dinner Mixes", "Mexican Dinner Mix", \
               "Mexican meal kit, not baking mix"

    if family == "cracker_title_still_under_bakery_cookies":
        return "Snack > Crackers", "Crackers", \
               "Title says cracker, not cookie"

    if family == "biscotti_product_routed_as_meal_sandwich":
        return "Bakery > Biscotti", "Biscotti", \
               "Biscotti, not a sandwich"

    if family == "salad_topping_routed_as_finished_salad":
        return "Pantry > Salad Toppings", "Salad Topping", \
               "Salad topping/component, not a finished salad"

    if family == "salad_kit_not_on_produce_salad_kit_shelf":
        return "Produce > Salad Kits", "Salad Kit", \
               "Salad kit belongs in Produce > Salad Kits"

    if family == "cake_or_cupcake_product_routed_as_cookie":
        if "cupcake" in title:
            return "Bakery > Cake > Cupcake", "Cupcake", "Cupcake, not cookie"
        return "Bakery > Cake", "Cake", "Cake, not cookie"

    if family == "ice_cream_title_left_under_bakery_review":
        return "Frozen > Ice Cream", "Ice Cream", \
               "Ice cream → Frozen > Ice Cream"

    if family == "candy_bfc_routed_outside_snack_candy":
        if "chocolate" in title:
            return "Snack > Chocolate Candy", "Chocolate Candy", \
                   "BFC=Candy + chocolate title → Snack > Chocolate Candy"
        if "gum" in title or "mint" in title:
            return "Snack > Candy > Gum", "Gum", \
                   "BFC=Candy chewing gum → Snack > Candy"
        return "Snack > Candy", "Candy", \
               "BFC=Candy must be in Snack family"

    if family == "alcohol_bfc_routed_outside_beverage":
        return "Beverage > Alcohol", "Alcohol", \
               "BFC=Alcohol must be in Beverage"

    if family == "beverage_bfc_left_in_baking_mixes":
        return "Beverage > Mixes", "Drink Mix", \
               "Beverage BFC, not Pantry > Baking Mixes"

    if family == "prepared_sandwich_routed_to_bakery_carrier":
        return "Meal > Sandwiches", "Prepared Sandwich", \
               "Prepared sandwich, not just bread"

    return None


def main() -> None:
    if not TODO.exists():
        print(f"missing {TODO}", file=sys.stderr); sys.exit(1)

    rows_in: list[dict] = []
    with TODO.open() as fh:
        reader = csv.DictReader(fh)
        in_fields = list(reader.fieldnames or [])
        rows_in = [dict(r) for r in reader]

    fields_out = [
        "fdc_id", "status", "owner", "issue_family", "severity",
        "confidence", "action_type", "title", "branded_food_category",
        "current_canonical_path", "proposed_canonical_path",
        "proposed_category_path_fixed", "proposed_product_identity_fixed",
        "reason",
    ]

    # Also pass-through standard taxonomy field columns for the apply script
    # (apply reads category_path_fixed, product_identity_fixed, canonical_path)
    fields_out += ["category_path_fixed", "product_identity_fixed", "canonical_path"]

    out_rows = []
    fam_counts: Counter = Counter()
    approved_counts: Counter = Counter()

    for r in rows_in:
        fam = r.get("issue_family", "")
        action = r.get("action_type", "")
        fam_counts[fam] += 1
        target = family_to_target(fam, r)

        # Skip families without a deterministic mapping (manual_review,
        # policy_decision-only, source-conflict). They stay in the todo
        # queue without a status.
        if target is None:
            continue
        if action not in {"deterministic_fix_candidate", "policy_fix_candidate"}:
            continue

        new_cp, new_identity, reason = target
        new_cat = " > ".join(new_cp.split(" > ")[:2])

        out_rows.append({
            "fdc_id": r["fdc_id"],
            "status": "approved",
            "owner": "claude",
            "issue_family": fam,
            "severity": r.get("severity", ""),
            "confidence": r.get("confidence", ""),
            "action_type": action,
            "title": r.get("title", "")[:120],
            "branded_food_category": r.get("branded_food_category", ""),
            "current_canonical_path": r.get("current_canonical_path", ""),
            "proposed_canonical_path": new_cp,
            "proposed_category_path_fixed": new_cat,
            "proposed_product_identity_fixed": new_identity,
            "reason": reason,
            "category_path_fixed": new_cat,
            "product_identity_fixed": new_identity,
            "canonical_path": new_cp,
        })
        approved_counts[fam] += 1

    with ACTIVE.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields_out, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    print(f"  wrote {len(out_rows):,} approved taxonomy overrides → {ACTIVE.name}")
    print()
    print("=== approved by family ===")
    for fam, total in fam_counts.most_common():
        approved = approved_counts.get(fam, 0)
        pct = approved / total if total else 0
        print(f"  [{approved:>4}/{total:<4} = {pct:>4.0%}]  {fam}")


if __name__ == "__main__":
    main()
