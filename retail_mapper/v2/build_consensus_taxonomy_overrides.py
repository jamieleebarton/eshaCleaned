#!/usr/bin/env python3
"""Build consensus_taxonomy_overrides.csv from Codex's right-place issue
inventory. Per-family rules decide the new canonical_path for each fdc_id.

Rules cover deterministic_fix_candidate and policy_fix_candidate families.
Source-conflict-review and manual-review families are NOT auto-routed —
they go to a separate file for human review.

Input:  retail_mapper/v2/consensus_right_place_issue_inventory.csv
Output: retail_mapper/v2/consensus_taxonomy_overrides.csv
        retail_mapper/v2/consensus_taxonomy_overrides_review.csv  (manual)
        retail_mapper/v2/consensus_source_conflicts.csv  (BFC dirty)
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from collections import Counter

V2 = Path(__file__).resolve().parent
SRC = V2 / "consensus_right_place_issue_inventory.csv"
OUT_OVERRIDES = V2 / "consensus_taxonomy_overrides.csv"
OUT_REVIEW = V2 / "consensus_taxonomy_overrides_review.csv"
OUT_CONFLICTS = V2 / "consensus_source_conflicts.csv"

csv.field_size_limit(sys.maxsize)

FAMILY_PRIORITY = {
    # More specific than the generic sandwich-cookie rule; these rows mention
    # sandwich but the product identity is still biscotti.
    "biscotti_product_routed_as_meal_sandwich": 100,
    "cracker_title_still_under_bakery_cookies": 90,
}

MANUAL_OR_POLICY_FAMILIES = {
    "cake_or_cupcake_product_routed_as_cookie",
    "ice_cream_title_left_under_bakery_review",
    "candy_bfc_routed_outside_snack_candy",
    "alcohol_bfc_routed_outside_beverage",
    "beverage_bfc_left_in_baking_mixes",
}

ACTIVE_SOURCE_CONFLICT_FAMILIES = {
    "pickle_bfc_salad_source_conflict",
}


def family_to_target(family: str, row: dict) -> tuple[str, str, str] | None:
    """Map (family, row) → (target_canonical_path, target_identity, reason).
    Returns None for families that need human review.
    """
    if family in MANUAL_OR_POLICY_FAMILIES:
        return None

    title = (row.get("title") or "").lower()
    cp = (row.get("canonical_path") or "").strip()

    if family == "sandwich_cookie_or_cracker_routed_as_meal_sandwich":
        # Sandwich cookies → Bakery > Cookies > Sandwich
        # Sandwich crackers → Snack > Crackers > Sandwich
        if "cracker" in title:
            return "Snack > Crackers", "Sandwich Crackers", "title contains cracker; route to Snack > Crackers"
        return "Bakery > Cookies", "Sandwich Cookies", "sandwich-style cookie product"

    if family == "frozen_appetizer_sandwich_not_frozen":
        # Keep Frozen prefix
        if "appetizer" in title or "slider" in title or "bites" in title or "mini" in title:
            return "Frozen > Appetizers", "Sandwich Appetizers", "frozen appetizer sandwich/slider"
        if "pocket" in title:
            return "Frozen > Sandwiches", "Sandwich Pockets", "frozen sandwich pocket"
        return "Frozen > Sandwiches", "Frozen Sandwich", "frozen sandwich product"

    if family == "soup_chowder_or_bisque_routed_as_seafood":
        if "chowder" in title:
            return "Pantry > Soup > Chowder", "Chowder", "seafood chowder belongs in Pantry > Soup"
        if "bisque" in title:
            return "Pantry > Soup > Bisque", "Bisque", "seafood bisque belongs in Pantry > Soup"
        return "Pantry > Soup", "Soup", "seafood soup belongs in Pantry > Soup"

    if family == "dip_salsa_or_cocktail_sauce_routed_as_seafood":
        if "salsa" in title:
            return "Pantry > Sauces & Salsas > Salsa", "Salsa", "salsa with seafood ingredient → Pantry"
        if "cocktail sauce" in title:
            return "Pantry > Sauces & Salsas > Cocktail Sauce", "Cocktail Sauce", "cocktail sauce → Pantry"
        if "dip" in title:
            return "Pantry > Dips & Spreads > Dip", "Dip", "seafood dip → Pantry > Dips"
        return "Pantry > Sauces & Salsas", "Sauce", "seafood-flavored sauce → Pantry"

    if family == "pickle_sandwich_slices_routed_as_meal_sandwich":
        return "Pantry > Pickles > Pickle Slices", "Pickle Slices", "pickle slices, not a sandwich"

    if family == "seasoning_marinade_routed_as_meat_or_seafood":
        if "rub" in title:
            return "Pantry > Spices & Seasonings > Rub", "Rub", "rub/seasoning, not the protein"
        if "marinade" in title:
            return "Pantry > Sauces & Salsas > Marinade", "Marinade", "marinade, not the protein"
        if "seasoning" in title:
            return "Pantry > Spices & Seasonings", "Seasoning", "seasoning, not the protein"
        return "Pantry > Spices & Seasonings", "Seasoning", "seasoning/marinade, not the protein"

    if family == "cheese_slices_routed_as_meal_sandwich":
        return "Dairy > Cheese > Slices", "Cheese Slices", "cheese slices, not a sandwich"

    if family == "mexican_dinner_mix_left_in_baking_mixes":
        return "Pantry > Mexican Dinner Mixes", "Mexican Dinner Mix", "Mexican meal kit, not baking mix"

    if family == "cracker_title_still_under_bakery_cookies":
        return "Snack > Crackers", "Crackers", "title says cracker, not cookie"

    if family == "biscotti_product_routed_as_meal_sandwich":
        return "Bakery > Biscotti", "Biscotti", "biscotti, not a sandwich"

    if family == "salad_topping_routed_as_finished_salad":
        return "Pantry > Salad Toppings", "Salad Topping", "salad topping/component, not finished salad"

    if family == "salad_kit_not_on_produce_salad_kit_shelf":
        return "Produce > Salad Kits", "Salad Kit", "salad kit goes to Produce > Salad Kits"

    if family == "prepared_sandwich_routed_to_bakery_carrier":
        return "Meal > Sandwiches", "Prepared Sandwich", "prepared sandwich, not just bread"

    # Policy decisions and source-conflict review fall through to manual
    return None


def override_priority(row: dict) -> int:
    return FAMILY_PRIORITY.get(row.get("issue_family", ""), 10)


def add_override(overrides_by_fdc: dict[str, dict], override: dict) -> bool:
    """Add or replace one deterministic override.

    A few SKUs are hit by a broad family and a narrower family. Keep only one
    applied override per fdc_id so the apply log is stable and the narrower
    rule wins.
    """
    fdc_id = override["fdc_id"]
    existing = overrides_by_fdc.get(fdc_id)
    if existing is None or override_priority(override) >= override_priority(existing):
        overrides_by_fdc[fdc_id] = override
        return existing is None
    return False


def main() -> None:
    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr); sys.exit(1)

    overrides_by_fdc: dict[str, dict] = {}
    review = []
    conflicts = []
    family_counts: Counter = Counter()

    with SRC.open() as fh:
        for r in csv.DictReader(fh):
            fam = r.get("issue_family", "")
            action = r.get("action_type", "")
            family_counts[fam] += 1

            target = family_to_target(fam, r)
            if target is None:
                # Branch by action_type for what review file to write to
                if action == "source_conflict_review" and fam in ACTIVE_SOURCE_CONFLICT_FAMILIES:
                    conflicts.append({
                        "fdc_id": r["fdc_id"],
                        "title": r["title"],
                        "issue_family": fam,
                        "branded_food_category": r.get("branded_food_category", ""),
                        "current_canonical_path": r.get("canonical_path", ""),
                        "rationale": r.get("rationale", ""),
                        "likely_fix": r.get("likely_fix", ""),
                    })
                else:
                    review.append({
                        "fdc_id": r["fdc_id"],
                        "title": r["title"],
                        "issue_family": fam,
                        "action_type": action,
                        "current_canonical_path": r.get("canonical_path", ""),
                        "rationale": r.get("rationale", ""),
                        "likely_fix": r.get("likely_fix", ""),
                    })
                continue

            new_cp, new_identity, reason = target
            add_override(overrides_by_fdc, {
                "fdc_id": r["fdc_id"],
                "status": "approved",
                "owner": "claude",
                "title": r["title"][:120],
                "current_canonical_path": r.get("canonical_path", ""),
                "category_path_fixed": new_cp,
                "product_identity_fixed": new_identity,
                # Keep Claude's original column names as compatibility aliases
                # for older scripts and spot-check reports.
                "new_canonical_path": new_cp,
                "new_product_identity": new_identity,
                "issue_family": fam,
                "reason": reason,
            })

    # Write outputs
    OUT_OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
    overrides = sorted(
        overrides_by_fdc.values(),
        key=lambda r: (0, int(r["fdc_id"])) if r["fdc_id"].isdigit() else (1, r["fdc_id"]),
    )
    auto_counts: Counter = Counter(r["issue_family"] for r in overrides)
    cols_overrides = ["fdc_id", "status", "owner", "title", "current_canonical_path",
                      "category_path_fixed", "product_identity_fixed",
                      "new_canonical_path", "new_product_identity",
                      "issue_family", "reason"]
    with OUT_OVERRIDES.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols_overrides)
        w.writeheader()
        for r in overrides:
            w.writerow(r)
    print(f"  wrote {len(overrides):,} taxonomy overrides → {OUT_OVERRIDES.name}")

    for r in review:
        r["status"] = "review"
        r["owner"] = "shared" if r.get("action_type") == "policy_decision" else "claude"
    cols_review = ["fdc_id", "status", "owner", "title", "issue_family", "action_type",
                   "current_canonical_path", "rationale", "likely_fix"]
    with OUT_REVIEW.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols_review)
        w.writeheader()
        for r in review:
            w.writerow(r)
    print(f"  wrote {len(review):,} manual-review rows → {OUT_REVIEW.name}")

    for r in conflicts:
        r["status"] = "approved"
        r["owner"] = "shared"
        r["reason"] = r.get("likely_fix", "")
        r["source_conflict_note"] = r.get("likely_fix", "")
        r["source_conflict_action"] = "flag_dirty_source_only"
    cols_conflicts = ["fdc_id", "status", "owner", "title", "issue_family",
                      "branded_food_category", "current_canonical_path",
                      "rationale", "likely_fix", "reason",
                      "source_conflict_note", "source_conflict_action"]
    with OUT_CONFLICTS.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols_conflicts)
        w.writeheader()
        for r in conflicts:
            w.writerow(r)
    print(f"  wrote {len(conflicts):,} source-conflict rows → {OUT_CONFLICTS.name}")

    print()
    print("=== auto-fix coverage by family ===")
    for fam, total in family_counts.most_common():
        auto = auto_counts.get(fam, 0)
        pct = auto / total if total else 0
        print(f"  [{auto:>4}/{total:<4} = {pct:>4.0%}]  {fam}")


if __name__ == "__main__":
    main()
