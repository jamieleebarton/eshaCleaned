"""
Gluten-free substitution engine.

Pure Python module - no Hestia imports, no side effects.
Takes ingredient dicts in, returns substituted dicts out.

Usage:
    from hestia.gluten_substitutions import apply_gluten_substitutions

    new_grams, notes = apply_gluten_substitutions(
        fndds_grams={"50000000": 30.0, "55101000": 200.0, "20000000": 300.0},
        recipe_category="1.12",
        recipe_name="Chicken Pasta",
    )
"""

from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------
# Section 1: Gluten FNDDS Classification
# ---------------------------------------------------------------

# FNDDS prefixes that ARE gluten-containing products.
# These are SPECIFIC wheat sub-ranges within broader categories.
GLUTEN_FNDDS_PREFIXES = (
    # 50xxx - Flours (ONLY wheat flours, not rice/corn/oat/almond)
    "5000",     # All-purpose, bread, whole wheat, self-rising, cake, pastry flour
    "5001",     # Whole wheat flour variants
    "5002",     # Self-rising flour
    "5005",     # Cake/pastry flour

    # 51xxx - Yeast breads, rolls, buns (virtually all wheat-based)
    "51",

    # 52xxx - Quick breads (pancakes, waffles, muffins, biscuits)
    # NOTE: 522xx is corn tortilla - excluded below
    "52",

    # 53xxx - Cakes, cookies, pastries, pies (wheat flour base)
    "53",

    # 55xxx - Pasta, noodles (wheat-based)
    # NOTE: rice noodles/GF pasta have distinct codes - excluded below
    "55",
)

# Prefixes within gluten ranges that are NOT gluten.
# Checked BEFORE inclusion prefixes.
NON_GLUTEN_PREFIX_OVERRIDES = (
    "5020",     # Rice flour
    "5030",     # Corn flour, masa
    "5040",     # Cornstarch, tapioca starch, arrowroot
    "5050",     # Oat flour (certified GF oats)
    "5060",     # Almond flour, nut flours
    "5070",     # Coconut flour
    "5080",     # Other GF flours (buckwheat, chickpea, etc.)
    "522",      # Corn tortilla, corn-based quick breads
)

# Specific codes that are NOT gluten despite matching a gluten prefix.
NON_GLUTEN_CODE_OVERRIDES = frozenset({
    "52210000",  # Corn tortilla
    "55301000",  # Rice noodles
    "55302000",  # Rice vermicelli
    "55400000",  # GF pasta (if coded under 55)
})


def is_gluten_fndds(fpid: str) -> bool:
    """Check if an FNDDS code represents a gluten-containing product."""
    fpid = str(fpid).strip()
    # Specific code exclusions first
    if fpid in NON_GLUTEN_CODE_OVERRIDES:
        return False
    # Prefix exclusions second
    for prefix in NON_GLUTEN_PREFIX_OVERRIDES:
        if fpid.startswith(prefix):
            return False
    # Inclusion check
    for prefix in GLUTEN_FNDDS_PREFIXES:
        if fpid.startswith(prefix):
            return True
    return False


def classify_gluten_ingredient(fpid: str) -> Optional[str]:
    """
    Classify a gluten FNDDS code into a functional category.

    Returns one of: "flour", "bread", "quick_bread", "pastry",
    "pasta", "tortilla", or None (not gluten).
    """
    if not is_gluten_fndds(fpid):
        return None

    fpid = str(fpid).strip()

    # -- Flour (50xx wheat flour codes) --
    if fpid.startswith("500"):
        return "flour"

    # -- Tortilla (wheat tortilla within 51xxx) --
    if fpid.startswith("5118"):
        return "tortilla"

    # -- Bread (51xxx) --
    if fpid.startswith("51"):
        return "bread"

    # -- Quick bread (52xxx - pancakes, waffles, muffins, biscuits) --
    if fpid.startswith("52"):
        return "quick_bread"

    # -- Pastry (53xxx - cakes, cookies, pies) --
    if fpid.startswith("53"):
        return "pastry"

    # -- Pasta (55xxx) --
    if fpid.startswith("55"):
        return "pasta"

    return None


# ---------------------------------------------------------------
# Section 2: Cooking Context Inference
# ---------------------------------------------------------------

# Maps recipe category prefixes to cooking context.
# Matched by longest prefix first.
CATEGORY_COOKING_CONTEXT: Dict[str, str] = {
    # Baking
    "1.3":  "baking",      # Bread
    "1.22": "baking",      # Pie / pastry
    "1.23": "baking",      # Cookie / baked goods

    # Coating / frying
    "1.9":  "coating",     # Meat / protein (flour for dredging)
    "1.10": "coating",     # Shellfish
    "1.11": "coating",     # Fish

    # Sauce / soup (flour as thickener)
    "1.15": "thickening",  # Soup / stew
    "1.17": "thickening",  # Stew / casserole

    # Stir fry / mixed
    "1.12": "stir_fry",    # Mixed / stir-fry

    # Pasta dishes
    "1.18": "pasta",       # Pasta category

    # Sandwich / wrap
    "1.21": "wrap",        # Burger / sandwich

    # Pizza
    "1.20": "pizza",       # Pizza

    # Breakfast
    "1.1":  "breakfast",   # Eggs / breakfast
}

# Recipe name keyword detection for context.
_BAKING_NAME_KEYWORDS = (
    "cake", "cookie", "cookies", "muffin", "brownie", "brownies",
    "scone", "biscuit", "cupcake", "pastry", "tart ",
    "waffle", "pancake", "cobbler", "cornbread", "shortbread",
    "doughnut", "donut", "banana bread", "zucchini bread",
    "coffee cake", "pound cake", "crumble", "galette",
    "pie ", " pie", "pies", "loaf", "batter", "dough",
    "flapjack", "crepe",
)

_SAUCE_NAME_KEYWORDS = (
    " sauce", "gravy", " soup", "chowder", "bisque",
    "stew", "curry", "gumbo",
)

_PASTA_NAME_KEYWORDS = (
    "spaghetti", "fettuccine", "penne", "linguine", "rigatoni",
    "macaroni", "lasagna", "ziti", "orzo", "rotini",
    "noodle", "pasta",
)

_STIR_FRY_NAME_KEYWORDS = (
    "stir fry", "stir-fry", "teriyaki", "lo mein", "chow mein",
    "kung pao", "general tso",
)


def _match_category_context(recipe_category: str) -> Optional[str]:
    """Find the cooking context for a recipe category using longest prefix match."""
    if not recipe_category:
        return None
    for length in range(len(recipe_category), 0, -1):
        prefix = recipe_category[:length]
        if prefix in CATEGORY_COOKING_CONTEXT:
            return CATEGORY_COOKING_CONTEXT[prefix]
    return None


def _detect_recipe_context(
    recipe_category: str,
    recipe_name: str,
    fndds_codes: set,
) -> Optional[str]:
    """
    Determine the overall cooking context using all available signals.

    Priority: recipe name (strongest) > category prefix > ingredient co-occurrence.
    """
    name_lower = recipe_name.lower() if recipe_name else ""

    # Signal 1 (strongest): Recipe name keywords
    if name_lower:
        for keyword in _BAKING_NAME_KEYWORDS:
            if keyword in name_lower:
                return "baking"
        for keyword in _PASTA_NAME_KEYWORDS:
            if keyword in name_lower:
                return "pasta"
        for keyword in _STIR_FRY_NAME_KEYWORDS:
            if keyword in name_lower:
                return "stir_fry"
        for keyword in _SAUCE_NAME_KEYWORDS:
            if keyword in name_lower:
                return "thickening"

    # Signal 2: Category prefix mapping
    cat_context = _match_category_context(recipe_category)
    if cat_context:
        return cat_context

    return None


def infer_gluten_function(
    gluten_category: str,
    context: Optional[str],
    grams: float,
    total_grams: float,
) -> str:
    """
    Determine the functional role of a gluten ingredient in a recipe.

    Returns: "baking", "coating", "thickening", "pasta", "bread",
             "wrap", "breakfast", or "default".
    """
    proportion = grams / max(total_grams, 1.0)

    # -- Flour: most context-dependent --
    if gluten_category == "flour":
        if context in ("baking", "breakfast"):
            return "baking"
        if context == "thickening":
            return "thickening"
        if context in ("coating", "stir_fry"):
            return "coating"
        if context == "pizza":
            return "baking"
        # Small amount of flour = likely coating or thickening
        if proportion < 0.08:
            return "thickening"
        return "baking"  # default for flour

    # -- Bread: always bread substitution --
    if gluten_category == "bread":
        if context == "wrap":
            return "bread"
        return "bread"

    # -- Tortilla: always wrap substitution --
    if gluten_category == "tortilla":
        return "wrap"

    # -- Quick bread: baking context --
    if gluten_category == "quick_bread":
        return "breakfast" if context == "breakfast" else "baking"

    # -- Pastry: always baking --
    if gluten_category == "pastry":
        return "baking"

    # -- Pasta: always pasta substitution --
    if gluten_category == "pasta":
        return "pasta"

    return "default"


# ---------------------------------------------------------------
# Section 3: Substitution Rules
# ---------------------------------------------------------------

# Each rule: (substitute_id, display_name, gram_ratio)
# gram_ratio: multiply original grams by this to get substitute grams.

SubRule = Tuple[str, str, float]

SUBSTITUTION_RULES: Dict[str, Dict[str, SubRule]] = {
    "flour": {
        "baking":      ("gf_flour_blend", "GF flour blend (1:1)", 1.0),
        "coating":     ("rice_flour",     "Rice flour",           1.0),
        "thickening":  ("cornstarch",     "Cornstarch",           0.5),
        "breakfast":   ("gf_flour_blend", "GF flour blend (1:1)", 1.0),
        "default":     ("gf_flour_blend", "GF flour blend (1:1)", 1.0),
    },
    "bread": {
        "bread":       ("gf_bread",       "Gluten-free bread",    1.0),
        "default":     ("gf_bread",       "Gluten-free bread",    1.0),
    },
    "tortilla": {
        "wrap":        ("corn_tortilla",   "Corn tortilla",        1.0),
        "default":     ("corn_tortilla",   "Corn tortilla",        1.0),
    },
    "quick_bread": {
        "baking":      ("gf_flour_blend", "GF flour blend (1:1)", 1.0),
        "breakfast":   ("gf_flour_blend", "GF flour blend (1:1)", 1.0),
        "default":     ("gf_flour_blend", "GF flour blend (1:1)", 1.0),
    },
    "pastry": {
        "baking":      ("gf_flour_blend", "GF flour blend (1:1)", 1.0),
        "default":     ("gf_flour_blend", "GF flour blend (1:1)", 1.0),
    },
    "pasta": {
        "pasta":       ("gf_pasta",       "Gluten-free pasta",    1.0),
        "default":     ("gf_pasta",       "Gluten-free pasta",    1.0),
    },
}


# ---------------------------------------------------------------
# Section 4: Structural Gluten Detection
# ---------------------------------------------------------------

# Recipe name patterns where gluten is structural (not substitutable).
# These are recipes where wheat IS the dish, not an ingredient in it.
_STRUCTURAL_NAME_PATTERNS = (
    "sourdough",
    "focaccia",
    "pretzel",
    "bagel",
    "croissant",
    "naan",
    "pita",
    "ciabatta",
    "baguette",
    "brioche",
    "challah",
    "ramen noodle",
    "udon",
    "soba",
    "fresh pasta",
    "homemade pasta",
    "egg noodle",
    "dumpling",
    "wonton",
    "gyoza",
    "pierogi",
    "phyllo",
    "puff pastry",
    "danish",
    "eclair",
    "cream puff",
    "strudel",
    "baklava",
    "cinnamon roll",
    "pizza dough",
    "calzone",
    "stromboli",
    "panini",
    "flatbread",
)


def is_structural_gluten(
    gluten_g: float,
    total_g: float,
    recipe_category: str,
    recipe_name: str,
) -> bool:
    """
    Check if gluten is a structural (non-substitutable) component of a recipe.

    Returns True if:
    - Gluten is >40% of recipe mass (higher threshold than dairy's 30%
      because flour+water expansion means less flour by mass in bread)
    - Recipe name matches a wheat-primary pattern
    - Recipe is in bread category (1.3.x)
    """
    # High proportion of gluten
    if total_g > 0 and gluten_g / total_g > 0.40:
        return True

    # Recipe name patterns
    name_lower = recipe_name.lower()
    for pattern in _STRUCTURAL_NAME_PATTERNS:
        if pattern in name_lower:
            return True

    # Bread category (1.3.x = yeast breads, rolls)
    if recipe_category.startswith("1.3"):
        return True

    return False


# ---------------------------------------------------------------
# Section 5: Main Entry Point
# ---------------------------------------------------------------

def apply_gluten_substitutions(
    fndds_grams: Dict[str, float],
    recipe_category: str,
    food_descriptions: Optional[Dict[str, str]] = None,
    recipe_name: str = "",
) -> Tuple[Dict[str, float], List[str]]:
    """
    Replace gluten ingredients with gluten-free substitutes.

    Args:
        fndds_grams: Dict of FNDDS code -> grams (total recipe amounts).
        recipe_category: Recipe category string (e.g. "1.9.1.1.10.1").
        food_descriptions: Optional dict of FNDDS code -> description.
        recipe_name: Recipe name (used for context inference).

    Returns:
        (new_grams, notes):
        - new_grams: New ingredient dict with gluten codes replaced by SUB_* keys.
          Non-gluten ingredients kept with original FNDDS codes.
        - notes: List of human-readable substitution descriptions.
    """
    if food_descriptions is None:
        food_descriptions = {}

    new_grams: Dict[str, float] = {}
    notes: List[str] = []
    total_grams = sum(fndds_grams.values()) if fndds_grams else 0.0

    # Compute recipe context ONCE from all available signals
    context = _detect_recipe_context(
        recipe_category, recipe_name, set(fndds_grams.keys())
    )

    for fpid, grams in fndds_grams.items():
        gluten_cat = classify_gluten_ingredient(fpid)

        if gluten_cat is None:
            # Not gluten - keep as-is
            new_grams[fpid] = grams
            continue

        # Gluten ingredient - find substitution
        cooking_fn = infer_gluten_function(gluten_cat, context, grams, total_grams)
        rules = SUBSTITUTION_RULES.get(gluten_cat, {})
        rule = rules.get(cooking_fn) or rules.get("default")

        if rule:
            sub_id, sub_name, ratio = rule
            sub_grams = round(grams * ratio, 2)
            sub_key = f"SUB_{sub_id}"
            # Aggregate if multiple gluten ingredients map to same substitute
            new_grams[sub_key] = round(new_grams.get(sub_key, 0) + sub_grams, 2)

            orig_desc = food_descriptions.get(fpid, fpid)
            notes.append(
                f"{orig_desc} ({grams:.0f}g) -> {sub_name} ({sub_grams:.0f}g) "
                f"[{gluten_cat}/{cooking_fn}]"
            )
        else:
            # Unknown gluten with no matching rule - REMOVE for safety
            orig_desc = food_descriptions.get(fpid, fpid)
            notes.append(f"{orig_desc} ({grams:.0f}g) -> REMOVED (unknown gluten, no rule)")

    return new_grams, notes


def get_gluten_summary(fndds_grams: Dict[str, float]) -> Dict[str, float]:
    """
    Summarize gluten content by category.

    Returns dict like {"flour": 30.0, "pasta": 200.0, "bread": 60.0}.
    """
    summary: Dict[str, float] = {}
    for fpid, grams in fndds_grams.items():
        cat = classify_gluten_ingredient(fpid)
        if cat:
            summary[cat] = summary.get(cat, 0) + grams
    return summary
