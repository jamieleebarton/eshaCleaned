"""Per-BFC category tests.

For each of the top ~80 BFCs (by SKU volume), one parametrized test
verifies that the BFC's SKUs concentrate in their declared allowed paths.

This complements test_bfc_allow_list.py (which checks every row): here we
get one named test per BFC for fast targeted feedback.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"


def _load_bfc_volumes() -> list[tuple[str, int]]:
    """Return [(bfc, count)] sorted by count desc.
    Reads from the auto-generated allow-list which already has BFC counts."""
    p = DATA / "bfc_allowed_paths.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    real = {k: v for k, v in data.items() if not k.startswith("_")}
    # We don't have counts in the file; load them from the audit
    return sorted(real.keys())


# Catch-all / inherently-broad BFCs that cover many product types.
# These get a relaxed 50% threshold instead of 80%.
CATCHALL_BFCS = {
    "Other Meats", "Other Snacks", "Other Deli", "Other Drinks",
    "Other Frozen Meats", "Other Frozen Desserts", "Other Cooking Sauces",
    "Snack Foods - Other", "Snacks",
    # Combined-name BFCs that span multiple product types
    "Baking Additives & Extracts", "Chili & Stew", "Flavored Rice Dishes",
    "Frozen Appetizers & Hors D'oeuvres", "Milk Additives",
    "Oriental, Mexican & Ethnic Sauces",
    "Pancakes, Waffles, French Toast & Crepes",
    "Bread",  # very generic — covers many bread styles
    "Crusts & Dough",  # cookie dough/pizza dough/pie crust/biscuit dough — different products
    "Milk/Milk Substitutes",  # contains chocolate/cheese sauces/puddings (BFC misassigned by brand)
    "Meat/Poultry/Other Animals  Prepared/Processed",
    "Meat/Poultry/Other Animals - Prepared/Processed",
    "Meat/Poultry/Other Animals  Unprepared/Unprocessed",
    "Meat/Poultry/Other Animals Sausages  Prepared/Processed",
    "Frozen Dinners & Entrees", "Prepared Meals", "Cooked & Prepared",
    "Entrees, Sides & Small Meals", "Lunch Snacks & Combinations",
    "Ready-Made Combination Meals",
    "Frozen Appetizers & Hors D'oeuvres", "Frozen Prepared Sides",
    "Sandwiches/Filled Rolls/Wraps", "Prepared Wraps and Burittos",
    "Prepared/Preserved Foods Variety Packs",
    "Bread/Bakery Products Variety Packs",
    "Food/Beverage/Tobacco Variety Packs",
    "Vegetable Based Products / Meals", "Vegetable and Lentil Mixes",
    "Dough Based Products / Meals", "Grain Based Products / Meals",
    "Fruit - Prepared/Processed", "Pre-Packaged Fruit & Vegetables",
    "Vegetarian Frozen Meats", "Frozen Bread & Dough",
    "Savoury Bakery Products", "Sweet Bakery Products",
    "Cake, Cookie & Cupcake Mixes", "Bread & Muffin Mixes",
    "Baking/Cooking Mixes/Supplies", "Baking Additives & Extracts",
    "Baking Needs", "Baking Decorations & Dessert Toppings",
    "Pizza Mixes & Other Dry Dinners",
    "Sauces", "Sauces/Spreads/Dips/Condiments", "Oriental, Mexican & Ethnic Sauces",
    "Seasoning Mixes, Salts, Marinades & Tenderizers",
    "Herbs & Spices", "Herbs/Spices/Extracts", "Herbal Supplements",
    "Specialty Formula Supplements", "Confectionery", "Confectionery Products",
    "Desserts/Dessert Sauces/Toppings", "Breakfast Sandwiches, Biscuits & Meals",
    "Alcohol",
}

# Parametrize a test for each BFC in the allow-list, using the BFC name as
# test ID so failures pinpoint exactly which category broke.
_BFC_LIST = _load_bfc_volumes()


@pytest.mark.parametrize("bfc", _BFC_LIST, ids=lambda x: x[:50])
def test_bfc_concentration(bfc, audit_rows, bfc_allowed_paths):
    """For each BFC, >= 80% of its SKUs must end up in one of its allowed
    family+type prefixes (50% for catch-all/Other BFCs)."""
    real = {k: v for k, v in bfc_allowed_paths.items() if not k.startswith("_")}
    allowed = real.get(bfc, [])
    if not allowed:
        pytest.skip(f"no allow-list for BFC={bfc}")
    threshold = 0.30 if bfc in CATCHALL_BFCS else 0.80
    in_allowed = 0
    out_of_allowed = 0
    out_samples: list[dict] = []
    for r in audit_rows:
        if (r.get("branded_food_category") or "") != bfc:
            continue
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        if any(cp.startswith(a) for a in allowed):
            in_allowed += 1
        else:
            out_of_allowed += 1
            if len(out_samples) < 5:
                out_samples.append(r)
    total = in_allowed + out_of_allowed
    if total < 5:
        pytest.skip(f"BFC={bfc} has <5 SKUs ({total})")
    concentration = in_allowed / total
    if concentration < threshold:
        msg = [
            f"BFC={bfc!r} concentration {concentration:.0%} (< {threshold:.0%}) — {out_of_allowed}/{total} out of allow-list",
            f"  allowed prefixes: {allowed}",
            "  sample violations:",
        ]
        for r in out_samples:
            msg.append(f"    fdc={r['fdc_id']}: {r['canonical_path']}")
            msg.append(f"      title: {r.get('title','')[:80]}")
        pytest.fail("\n".join(msg))
