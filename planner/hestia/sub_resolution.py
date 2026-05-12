"""
SUB key resolution - maps SUB_* keys from substitution engines to either:
- A real FNDDS code (for package/pricing lookup via food_packages.db)
- A hardcoded display item (for substitutes with no FNDDS equivalent)

Shared module for all substitution pipelines (dairy, gluten, etc.).
Pure module - no external dependencies.
"""

from typing import Optional


# SUB_ID -> 8-digit FNDDS code (resolvable via package index)
SUB_TO_FNDDS: dict[str, str] = {
    # -- Gluten-free substitutes --
    "cornstarch":     "50400000",   # Cornstarch (thickener)
    "rice_flour":     "50200000",   # Rice flour (coating, baking)
    "corn_tortilla":  "52210000",   # Corn tortilla

    # -- Dairy substitutes --
    "oat_milk":       "11300000",   # Oat milk
    "soy_milk":       "11200000",   # Soy milk
    "olive_oil":      "04060000",   # Olive oil
    "avocado_oil":    "04060800",   # Avocado oil
    "coconut_cream":  "14201100",   # Coconut cream
    "df_yogurt":      "11400000",   # Plant-based yogurt
}

# SUB_ID -> hardcoded display item (no suitable FNDDS code exists)
# These appear in substitution_notes and as manual shopping list additions.
SUB_HARDCODED: dict[str, dict] = {
    # -- Gluten-free substitutes --
    "gf_flour_blend": {
        "name": "GF flour blend (1:1)",
        "aisle": "Baking",
        "price_low_cents": 450,
        "price_high_cents": 700,
        "package_label": "24 oz bag",
    },
    "gf_pasta": {
        "name": "Gluten-free pasta",
        "aisle": "Natural Foods",
        "price_low_cents": 300,
        "price_high_cents": 500,
        "package_label": "12 oz box",
    },
    "gf_bread": {
        "name": "Gluten-free bread",
        "aisle": "Bakery / Natural Foods",
        "price_low_cents": 550,
        "price_high_cents": 800,
        "package_label": "1 loaf",
    },
    "gf_breadcrumbs": {
        "name": "GF breadcrumbs",
        "aisle": "Baking",
        "price_low_cents": 350,
        "price_high_cents": 500,
        "package_label": "10 oz canister",
    },
    "tamari": {
        "name": "Tamari (wheat-free soy sauce)",
        "aisle": "International",
        "price_low_cents": 400,
        "price_high_cents": 600,
        "package_label": "10 fl oz",
    },

    # -- Dairy substitutes --
    "vegan_butter": {
        "name": "Vegan butter",
        "aisle": "Natural Foods",
        "price_low_cents": 400,
        "price_high_cents": 600,
        "package_label": "1 stick (4 oz)",
    },
    "cashew_cream": {
        "name": "Cashew cream",
        "aisle": "Natural Foods",
        "price_low_cents": 250,
        "price_high_cents": 350,
        "package_label": "1 cup",
    },
    "vegan_shreds": {
        "name": "Vegan cheese shreds",
        "aisle": "Natural Foods",
        "price_low_cents": 450,
        "price_high_cents": 600,
        "package_label": "8 oz bag",
    },
    "nutr_yeast": {
        "name": "Nutritional yeast",
        "aisle": "Natural Foods",
        "price_low_cents": 700,
        "price_high_cents": 950,
        "package_label": "8 oz",
    },
    "df_ice_cream": {
        "name": "Dairy-free ice cream",
        "aisle": "Frozen",
        "price_low_cents": 550,
        "price_high_cents": 750,
        "package_label": "1 pint",
    },
}


def resolve_sub_key(sub_key: str) -> tuple[Optional[str], Optional[dict]]:
    """
    Resolve a SUB_* key to either a FNDDS code or a hardcoded display item.

    Args:
        sub_key: Key from substitution engine, e.g. "SUB_gf_pasta"
                 or "gf_pasta" (SUB_ prefix is stripped if present).

    Returns:
        (fndds_code, None)  - if FNDDS-mapped; use for package/price lookup
        (None, hardcoded)   - if hardcoded display item; use for manual list adds
        (None, None)        - if unknown; caller should use sub_name from notes
    """
    sub_id = sub_key.removeprefix("SUB_")
    fndds = SUB_TO_FNDDS.get(sub_id)
    if fndds:
        return fndds, None
    hardcoded = SUB_HARDCODED.get(sub_id)
    if hardcoded:
        return None, hardcoded
    return None, None
