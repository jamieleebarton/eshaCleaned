"""Canonical HTC group → semantics module.

The encoder (recipe_mapper/v1/htc/encoder.py group_from_canonical_path) is the
SINGLE source of truth for what an HTC code means. This module reads the first
character of an HTC code to derive:

  * food group (vegetables / fruits / dairy / protein / grains / fats / etc.)
  * protein source (beef / pork / poultry / fish / eggs / legumes-nuts) for
    protein-diversity scoring in the meal planner

NEVER use canonical_path string-matching for these classifications. HTC
position 1 tells us the broad group; for group 2, HTC position 2 separates
raw/processed pork from beef/lamb/other red meat.

Mappings (group code → name → sample foods at that group):
  0 unclassified           Pantry (quarantine like 00000000)
  1 Dairy + plant-milk      Cream, Mozzarella, Almond Milk, Oat Milk
  2 Red meat / plant analog Beef, Pork, Lamb, Bologna, Bacon, **Tofu**
  3 Poultry                Chicken, Turkey, Duck
  4 Fish / shellfish       Salmon, Tilapia, Mussel, Cod
  5 Eggs                   Eggs, Egg Whites, Egg Noodles
  6 Vegetables             Corn, Onions, Hash Browns, Edamame
  7 Fruit                  Apples, Prunes, Pineapple
  8 Grains / Bakery (raw)  Pasta, Spaghetti, Baking Mix, Flour
  9 Legumes                Pinto Beans, Black Beans, Garbanzo
  A Nuts                   Mixed Nuts, Almonds, Peanuts
  B Oils & fats            Olive Oil, Vegetable Oil, Fish Oil
  C Sweeteners             Honey, Maple Syrup, Sugar
  D Beverages              Juice, Soda, Coffee
  E Spices & seasonings    Cinnamon, Curry Powder, Salt
  F Sauces & condiments    Pasta Sauce, Ketchup, Pickles, Mayo
  G Sweet bakery / pastry  Cookies, Cake, Turnover
  H Prepared / Soup        Soup, Chowder, Meal Kit
  J Snacks                 Chocolate Bar, Granola Bar, Chips
  K Supplements            Protein Powder, Vitamins
  M Baby & toddler food    Baby Food, Formula, Baby Snacks
  N Non-food               Personal Care, Beauty
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Group code → human-readable name
# ---------------------------------------------------------------------------
HTC_GROUP_NAMES: dict[str, str] = {
    "0": "Unclassified",
    "1": "Dairy",
    "2": "Red Meat",
    "3": "Poultry",
    "4": "Fish & Seafood",
    "5": "Eggs",
    "6": "Vegetables",
    "7": "Fruit",
    "8": "Grains & Bakery (raw)",
    "9": "Legumes",
    "A": "Nuts & Seeds",
    "B": "Oils & Fats",
    "C": "Sweeteners",
    "D": "Beverages",
    "E": "Spices & Seasonings",
    "F": "Sauces & Condiments",
    "G": "Sweet Bakery / Pastry",
    "H": "Prepared / Soup",
    "J": "Snacks",
    "K": "Supplements",
    "M": "Baby & Toddler",
    "N": "Non-Food",
}


# ---------------------------------------------------------------------------
# Group code → planner protein-source bucket
# Planner uses: 0=beef/red meat, 1=pork, 2=poultry, 3=fish, 4=eggs,
#               5=legumes/nuts. -1 = "not a protein source" for diversity calc.
#
# NOTE: position 1 alone can't differentiate beef vs pork vs lamb (all under
# group 2). Position 2 carries the family for the major meat split:
#   20 beef/plant analog/other red meat, 21 pork cuts, 22 lamb,
#   24 processed pork/ham/bacon/sausage, 28 generic processed meat link.
# ---------------------------------------------------------------------------
HTC_GROUP_TO_PROTEIN: dict[str, int] = {
    "3":  2,  # poultry
    "4":  3,  # fish/shellfish
    "5":  4,  # eggs
    "9":  5,  # legumes
    "A":  5,  # nuts (planner buckets nuts with legumes)
}


# ---------------------------------------------------------------------------
# Group code → food group for compliance scoring
# ---------------------------------------------------------------------------
HTC_GROUP_TO_FOODGROUP: dict[str, str] = {
    "0": "other",
    "1": "dairy",
    "2": "protein",
    "3": "protein",
    "4": "protein",
    "5": "protein",
    "6": "vegetables",
    "7": "fruits",
    "8": "grains",
    "9": "protein",        # FNDDS classifies legumes as protein
    "A": "protein",        # nuts → protein
    "B": "fats",
    "C": "sweets",
    "D": "beverages",
    "E": "seasoning",
    "F": "condiment",
    "G": "grains",         # sweet bakery counts as grains
    "H": "meal",
    "J": "snack",
    "K": "supplement",
    "M": "baby",
    "N": "non_food",
}


# ---------------------------------------------------------------------------
# Public helpers — call these from planner / calculator / audit scripts
# ---------------------------------------------------------------------------
def _code(htc: str) -> str:
    """Return the HTC code from either a raw HTC or a concept key."""
    if not htc:
        return ""
    return str(htc).split("|")[-1].lstrip("~")


def _first(htc: str) -> str:
    """Return the first non-tilde character of an HTC code (group code)."""
    s = _code(htc)
    return s[0] if s else ""


def group_code(htc: str) -> str:
    """Group code (single char) for an HTC, e.g. '6' for vegetables."""
    return _first(htc)


def group_name(htc: str) -> str:
    """Human-readable group name."""
    return HTC_GROUP_NAMES.get(_first(htc), "Unknown")


def protein_source(htc: str) -> int:
    """Protein-diversity bucket the planner expects.
    Returns -1 if this isn't a protein source."""
    s = _code(htc)
    if not s:
        return -1
    if s[0] == "2":
        family = s[1] if len(s) > 1 else ""
        if family in {"1", "4", "8"}:
            return 1
        return 0
    return HTC_GROUP_TO_PROTEIN.get(s[0], -1)


def foodgroup(htc: str) -> str:
    """Food group label (vegetables/fruits/dairy/protein/grains/etc.)."""
    return HTC_GROUP_TO_FOODGROUP.get(_first(htc), "other")


def is_non_food(htc: str) -> bool:
    """True if the HTC's group is non-food (Personal Care / Baby / Supplement
    or unclassified). Use for hard quarantine."""
    g = _first(htc)
    return g in {"M", "N", "0"} or htc == "00000000"


def is_protein_source(htc: str) -> bool:
    return protein_source(htc) != -1


# ---------------------------------------------------------------------------
# Perishability — by HTC group code
# Calibrated against Hestia's perishability_map.json category buckets.
# (shelf_days, can_freeze, loss_rate_per_week)
# ---------------------------------------------------------------------------
HTC_GROUP_PERISHABILITY: dict[str, tuple[int, bool, float]] = {
    "0": (90,   False, 0.05),  # unclassified — default
    "1": (14,   True,  0.10),  # Dairy: cheese/milk/yogurt — freezable
    "2": (4,    True,  0.35),  # Red meat / tofu — fresh, freezable
    "3": (4,    True,  0.35),  # Poultry — fresh, freezable
    "4": (3,    True,  0.40),  # Fish — most perishable, freezable
    "5": (25,   False, 0.05),  # Eggs (in shell) — not frozen
    "6": (10,   True,  0.15),  # Vegetables — fresh, mostly freezable
    "7": (7,    True,  0.20),  # Fruit — perishable, mostly freezable
    "8": (180,  True,  0.02),  # Grains/Bakery raw (flour/pasta/rice) — long shelf, freezable bread
    "9": (730,  False, 0.005), # Legumes — dry shelf-stable
    "A": (180,  True,  0.02),  # Nuts/seeds — long shelf, freezable
    "B": (365,  False, 0.01),  # Oils — pantry
    "C": (365,  False, 0.01),  # Sweeteners — pantry
    "D": (180,  True,  0.02),  # Beverages — juice freezable, others not really
    "E": (730,  False, 0.005), # Spices — pantry
    "F": (365,  False, 0.02),  # Sauces — pantry
    "G": (6,    True,  0.18),  # Sweet bakery (cookies/cakes) — perishable, freezable
    "H": (5,    True,  0.20),  # Prepared/soup — fridge, freezable
    "J": (180,  False, 0.02),  # Snacks (chips/bars) — pantry
    "K": (365,  False, 0.01),  # Supplements — pantry
    "M": (60,   False, 0.05),  # Baby food — varies, jarred long
    "N": (365,  False, 0.01),  # Non-food — N/A
}


def perishability(htc: str) -> tuple[int, bool, float]:
    """Return (shelf_days, can_freeze, loss_rate_per_week) for an HTC code."""
    return HTC_GROUP_PERISHABILITY.get(_first(htc), (90, False, 0.05))


def can_freeze(htc: str) -> bool:
    return perishability(htc)[1]


def shelf_days(htc: str) -> int:
    return perishability(htc)[0]


def loss_rate(htc: str) -> float:
    return perishability(htc)[2]


def htc_from_concept_key(key: str) -> str:
    """Extract htc_form from a concept_key 'canonical_path|modifier|htc_form'."""
    if not key: return ""
    parts = key.split("|")
    return parts[-1] if len(parts) >= 2 else key


def patch_perishability_index(ds_module) -> None:
    """Monkey-patch ds.PerishabilityIndex.classify_fpid so it falls back to
    HTC-positional perishability when the lookup key is a concept_key (not a
    FNDDS code). Call ONCE at process start, before SparseCascadePlanner."""
    import json
    PI = ds_module.PerishabilityIndex
    if getattr(PI, "_htc_patched", False): return
    _orig = PI.classify_fpid

    def classify_fpid(self, fpid):
        # Try the original FNDDS-prefix logic first
        try:
            cat, info = _orig(self, fpid)
            if cat != "unknown":
                return cat, info
        except Exception:
            pass
        # Fall back: assume fpid is a concept_key; pull its htc_form, look up HTC group
        htc = htc_from_concept_key(str(fpid))
        if not htc: return "unknown", self.default
        sd, cf, lr = perishability(htc)
        return f"htc_group_{_first(htc) or '?'}", {
            "shelf_days": sd, "can_freeze": cf, "loss_rate_per_week": lr,
            "examples": [f"HTC group {_first(htc)} via fallback"],
        }
    PI.classify_fpid = classify_fpid
    PI._htc_patched = True


__all__ = [
    "HTC_GROUP_NAMES", "HTC_GROUP_TO_PROTEIN", "HTC_GROUP_TO_FOODGROUP",
    "group_code", "group_name", "protein_source",
    "foodgroup", "is_non_food", "is_protein_source",
]
