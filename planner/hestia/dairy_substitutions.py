"""
Dairy-free substitution engine.

Pure Python module — no Hestia imports, no side effects.
Takes ingredient dicts in, returns substituted dicts out.

Usage:
    from hestia.dairy_substitutions import apply_dairy_substitutions

    new_grams, notes = apply_dairy_substitutions(
        fndds_grams={"81100500": 28.0, "11111000": 240.0, "21102150": 680.0},
        recipe_category="1.9.1.1.10.1",
    )
"""

from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────
# Section 1: Dairy FNDDS Classification
# ─────────────────────────────────────────────────────────────

# FNDDS prefixes that ARE dairy products.
# Checked via str.startswith() against 8-digit FNDDS codes.
DAIRY_FNDDS_PREFIXES = (
    "111",    # Milk (whole, skim, reduced fat, lactose-free, buttermilk, kefir)
    "112",    # Evaporated / condensed milk
    "114",    # Yogurt, frozen yogurt, yogurt dips
    "115",    # Flavored milk, chocolate milk, eggnog, smoothies
    "117",    # Infant formula (dairy-based)
    "118",    # Milk-based drinks
    "121",    # Cream (light, half-and-half, heavy, whipped)
    "122",    # Coffee creamer, whipped topping
    "123",    # Sour cream, dips
    "131",    # Ice cream, sherbet, gelato
    "132",    # Pudding, custard, mousse
    "14",     # Cheese (all types), cheese dishes
    "81100",  # Table fat, butter
    "81101",  # Butter stick, whipped, salted, ghee
    "81104",  # Butter-oil blend
)

# Prefixes within dairy ranges that are NOT dairy.
# Checked BEFORE inclusion prefixes.
NON_DAIRY_PREFIX_OVERRIDES = (
    "113",      # Plant milks (soy, almond, rice, coconut, oat, hemp, flax)
    "1148",     # Baby/toddler food (generic category, not all dairy)
    "81102",    # Margarine
    "81103",    # Margarine-oil blends, butter replacement liquid
    "8110401",  # Margarine-oil blend tub light
    "8110402",  # Margarine-oil blend stick light
    "81106",    # Butter replacement powder (Butter Buds, Molly McButter)
)

# Specific codes that are NOT dairy despite matching a dairy prefix.
NON_DAIRY_CODE_OVERRIDES = frozenset({
    "11519215",  # Strawberry milk non-dairy
    "11519216",  # Banana milk non-dairy
    "12210520",  # Coffee creamer soy liquid
    "12210525",  # Coconut milk creamer
    "12320100",  # Sour cream imitation
    "13100277",  # Oat milk
    "14502000",  # Imitation cheese
})


def is_dairy_fndds(fpid: str) -> bool:
    """Check if an FNDDS code represents a dairy product."""
    fpid = str(fpid).strip()
    # Specific code exclusions first
    if fpid in NON_DAIRY_CODE_OVERRIDES:
        return False
    # Prefix exclusions second
    for prefix in NON_DAIRY_PREFIX_OVERRIDES:
        if fpid.startswith(prefix):
            return False
    # Inclusion check
    for prefix in DAIRY_FNDDS_PREFIXES:
        if fpid.startswith(prefix):
            return True
    return False


# Codes/prefixes for buttermilk (checked before generic milk)
_BUTTERMILK_CODES = frozenset({"11111088"})
_BUTTERMILK_PREFIXES = ("111150", "111153")  # fat free, whole buttermilk


def classify_dairy_ingredient(fpid: str) -> Optional[str]:
    """
    Classify a dairy FNDDS code into a functional category.

    Returns one of: "butter", "ghee", "milk", "buttermilk", "yogurt",
    "cream", "sour_cream", "cheese", "ice_cream", or None (not dairy).
    """
    if not is_dairy_fndds(fpid):
        return None

    fpid = str(fpid).strip()

    # ── Butter / ghee (811xx range) ──
    if fpid.startswith("811"):
        if fpid == "81101003":  # butter oil ghee
            return "ghee"
        return "butter"

    # ── Buttermilk (before generic milk) ──
    if fpid in _BUTTERMILK_CODES:
        return "buttermilk"
    for bp in _BUTTERMILK_PREFIXES:
        if fpid.startswith(bp):
            return "buttermilk"

    # ── Yogurt (114xx) ──
    if fpid.startswith("114"):
        # Frozen yogurt is still functionally yogurt for substitution
        return "yogurt"

    # ── Ice cream (131xx) ──
    if fpid.startswith("131"):
        return "ice_cream"

    # ── Cream (121xx) ──
    if fpid.startswith("121"):
        return "cream"

    # ── Coffee creamer / whipped topping (122xx) ──
    if fpid.startswith("122"):
        return "cream"

    # ── Sour cream (123xx) ──
    if fpid.startswith("123"):
        return "sour_cream"

    # ── Pudding / custard (132xx) — cream-based desserts ──
    if fpid.startswith("132"):
        return "cream"

    # ── Cheese (14xxxx) ──
    if fpid.startswith("14"):
        return "cheese"

    # ── Milk catch-all (111, 112, 115, 117, 118) ──
    if fpid.startswith(("111", "112", "115", "117", "118")):
        return "milk"

    return None


# ─────────────────────────────────────────────────────────────
# Section 2: Cooking Context Inference
# ─────────────────────────────────────────────────────────────

# Maps recipe category prefixes → cooking context.
# Matched by longest prefix first (dict ordered by specificity).
CATEGORY_COOKING_CONTEXT: Dict[str, str] = {
    # Baking
    "1.3":  "baking",      # Bread
    "1.22": "baking",      # Pie / pastry
    "1.23": "baking",      # Cookie / baked goods

    # Sauteing / frying
    "1.9":  "saute",       # Meat / protein
    "1.10": "saute",       # Shellfish
    "1.11": "saute",       # Fish
    "1.12": "saute",       # Mixed / stir-fry
    "1.18": "saute",       # Pasta (butter in pasta = saute/finishing)

    # Sauce / soup
    "1.15": "sauce",       # Soup / stew
    "1.17": "sauce",       # Stew / casserole

    # Topping
    "1.14": "topping",     # Salad
    "1.20": "topping",     # Pizza (cheese = topping)
    "1.21": "topping",     # Burger / sandwich (cheese = topping)

    # Breakfast
    "1.1":  "breakfast",   # Eggs / breakfast

    # Dessert (ice cream, pudding contexts)
    "1.16": "dessert",     # Fruit / dessert
}

# ── Recipe name keyword detection ──
# Substrings in recipe names that strongly indicate baking context.
# Checked against lowercased recipe name via `in` (substring match).
_BAKING_NAME_KEYWORDS = (
    "cake", "cookie", "cookies", "muffin", "brownie", "brownies",
    "scone", "biscuit", "cupcake", "pastry", "tart ",
    "waffle", "pancake", "cobbler", "cornbread", "shortbread",
    "doughnut", "donut", "frosting", "icing", "meringue",
    "cinnamon roll", "sweet roll", "crescent roll",
    "banana bread", "zucchini bread", "pumpkin bread",
    "coffee cake", "pound cake", "angel food",
    "crumble", "galette", "strudel", "baklava",
    "bread pudding", "pie ", " pie", "pies",
    "quick bread", "yeast bread",
    "loaf", "batter", "dough",
    "flapjack", "crepe",
)

# Substrings that indicate sauce/soup context.
_SAUCE_NAME_KEYWORDS = (
    " sauce", "gravy", " soup", "chowder", "bisque",
    "stew", "curry", "korma", "tikka masala",
)

# FNDDS prefixes for flour/grain products (baking co-indicator).
# Only used when no stronger signal (name/category) provides context.
_FLOUR_FNDDS_PREFIXES = ("50", "51", "52", "53", "54")


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
        for keyword in _SAUCE_NAME_KEYWORDS:
            if keyword in name_lower:
                return "sauce"

    # Signal 2: Category prefix mapping
    cat_context = _match_category_context(recipe_category)
    if cat_context:
        return cat_context

    # Signal 3 (weakest): Ingredient co-occurrence
    # Flour/grains + no other context → likely baking
    has_flour = any(
        code.startswith(prefix)
        for code in fndds_codes
        for prefix in _FLOUR_FNDDS_PREFIXES
    )
    if has_flour:
        return "baking"

    return None


def infer_dairy_function(
    dairy_category: str,
    context: Optional[str],
    grams: float,
    total_grams: float,
) -> str:
    """
    Determine the functional role of a dairy ingredient in a recipe.

    Combines dairy type + pre-computed recipe context + proportion to return
    a cooking function string that maps to a substitution rule key.

    Args:
        dairy_category: One of "butter", "ghee", "milk", etc.
        context: Pre-computed recipe context from _detect_recipe_context(),
                 or None if no context could be determined.
        grams: Grams of this dairy ingredient.
        total_grams: Total grams in the recipe.

    Returns: "baking", "saute", "saute_high_heat", "finishing", "sauce",
             "topping", "breakfast", "whipping", or "default".
    """
    proportion = grams / max(total_grams, 1.0)

    # ── Butter: context-dependent ──
    if dairy_category == "butter":
        if context in ("baking", "dessert"):
            return "baking"  # dessert butter is almost always baking
        if context == "breakfast":
            return "breakfast" if proportion > 0.05 else "finishing"
        if context == "sauce":
            return "sauce"
        if context == "topping":
            return "finishing"
        if context == "saute" or context is None:
            if proportion < 0.03 and total_grams > 200:
                return "finishing"
            return "saute"
        return "default"

    # ── Ghee: always high-heat or finishing ──
    if dairy_category == "ghee":
        if context in ("baking", "dessert"):
            return "baking"
        if proportion < 0.03 and total_grams > 200:
            return "finishing"
        return "saute"

    # ── Milk: baking vs breakfast vs general ──
    if dairy_category == "milk":
        if context in ("baking", "dessert"):
            return "baking"
        if context == "breakfast":
            return "breakfast"
        if context == "sauce":
            return "sauce"
        return "default"

    # ── Buttermilk: always same substitution ──
    if dairy_category == "buttermilk":
        return "default"

    # ── Cream: sauce vs whipping ──
    if dairy_category == "cream":
        if context == "sauce":
            return "sauce"
        if context == "saute":
            return "saute"
        if context in ("baking", "dessert"):
            return "whipping"
        return "default"

    # ── Sour cream ──
    if dairy_category == "sour_cream":
        if context == "sauce":
            return "sauce"
        if context in ("topping", "breakfast"):
            return "topping"
        return "default"

    # ── Yogurt ──
    if dairy_category == "yogurt":
        return "default"

    # ── Cheese: topping vs melted ──
    if dairy_category == "cheese":
        if context == "topping":
            return "topping"
        if proportion < 0.08:
            return "topping"
        return "default"

    # ── Ice cream ──
    if dairy_category == "ice_cream":
        return "default"

    return "default"


# ─────────────────────────────────────────────────────────────
# Section 3: Substitution Rules
# ─────────────────────────────────────────────────────────────

# Each rule: (substitute_id, display_name, gram_ratio)
# gram_ratio: multiply original grams by this to get substitute grams.
# e.g. butter → olive oil at 0.85 ratio (less oil needed than butter by weight).

SubRule = Tuple[str, str, float]

SUBSTITUTION_RULES: Dict[str, Dict[str, SubRule]] = {
    "butter": {
        "saute_high_heat": ("avocado_oil",  "Avocado oil",   0.85),
        "saute":           ("olive_oil",    "Olive oil",     0.85),
        "baking":          ("vegan_butter", "Vegan butter",  1.0),
        "finishing":       ("vegan_butter", "Vegan butter",  1.0),
        "sauce":           ("vegan_butter", "Vegan butter",  1.0),
        "breakfast":       ("vegan_butter", "Vegan butter",  1.0),
        "default":         ("olive_oil",    "Olive oil",     0.85),
    },
    "ghee": {
        "saute":           ("avocado_oil",  "Avocado oil",   1.0),
        "baking":          ("vegan_butter", "Vegan butter",  1.0),
        "finishing":       ("vegan_butter", "Vegan butter",  1.0),
        "default":         ("avocado_oil",  "Avocado oil",   1.0),
    },
    "milk": {
        "baking":          ("soy_milk",     "Soy milk",      1.0),
        "breakfast":       ("oat_milk",     "Oat milk",      1.0),
        "sauce":           ("oat_milk",     "Oat milk",      1.0),
        "default":         ("oat_milk",     "Oat milk",      1.0),
    },
    "buttermilk": {
        "default":         ("soy_milk",     "Soy milk + 1 tbsp lemon juice per cup", 1.0),
    },
    "cream": {
        "sauce":           ("cashew_cream", "Cashew cream",                1.0),
        "saute":           ("cashew_cream", "Cashew cream",                1.0),
        "whipping":        ("coconut_cream", "Coconut cream (chilled)",    1.0),
        "default":         ("cashew_cream", "Cashew cream",                1.0),
    },
    "sour_cream": {
        "topping":         ("df_yogurt",    "Dairy-free yogurt",           1.0),
        "sauce":           ("cashew_cream", "Cashew cream + lemon",        1.0),
        "default":         ("df_yogurt",    "Dairy-free yogurt",           1.0),
    },
    "yogurt": {
        "default":         ("df_yogurt",    "Dairy-free yogurt",           1.0),
    },
    "cheese": {
        "topping":         ("nutr_yeast",   "Nutritional yeast",           0.25),
        "default":         ("vegan_shreds", "Vegan cheese shreds",         1.0),
    },
    "ice_cream": {
        "default":         ("df_ice_cream", "Dairy-free ice cream",        1.0),
    },
}


# ─────────────────────────────────────────────────────────────
# Section 4: Structural Dairy Detection
# ─────────────────────────────────────────────────────────────

# Recipe name patterns where dairy is structural (not substitutable)
_STRUCTURAL_NAME_PATTERNS = (
    "cheese pizza",
    "mac and cheese",
    "macaroni and cheese",
    "alfredo",
    "fondue",
    "cream of ",        # cream of mushroom soup, etc.
    "yogurt parfait",
    "cheesecake",
    "grilled cheese",
    "queso",
    "cream cheese frosting",
    "cheese souffle",
    "welsh rarebit",
    "cheese fondue",
    "baked brie",
    "cheese ball",
    "cheese dip",
    "cheese sauce",
    "cream sauce",
    "bechamel",
    "mornay",
)


def is_structural_dairy(
    dairy_g: float,
    total_g: float,
    recipe_category: str,
    recipe_name: str,
) -> bool:
    """
    Check if dairy is a structural (non-substitutable) component of a recipe.

    Returns True if:
    - Dairy is >30% of recipe mass
    - Recipe name matches a dairy-primary pattern
    - Recipe is in a dairy-primary category (1.2.x)
    """
    # High proportion of dairy
    if total_g > 0 and dairy_g / total_g > 0.30:
        return True

    # Recipe name patterns
    name_lower = recipe_name.lower()
    for pattern in _STRUCTURAL_NAME_PATTERNS:
        if pattern in name_lower:
            return True

    # Dairy-primary category (1.2.x = dairy category in FNDDS recipe classification)
    if recipe_category.startswith("1.2"):
        return True

    return False


# ─────────────────────────────────────────────────────────────
# Section 5: Main Entry Point
# ─────────────────────────────────────────────────────────────

def apply_dairy_substitutions(
    fndds_grams: Dict[str, float],
    recipe_category: str,
    food_descriptions: Optional[Dict[str, str]] = None,
    recipe_name: str = "",
) -> Tuple[Dict[str, float], List[str]]:
    """
    Replace dairy ingredients with non-dairy substitutes.

    Args:
        fndds_grams: Dict of FNDDS code → grams (total recipe amounts).
        recipe_category: Recipe category string (e.g. "1.9.1.1.10.1").
        food_descriptions: Optional dict of FNDDS code → description (for notes).
        recipe_name: Recipe name (used for context inference — e.g. detecting
                     "cake" → baking context so butter becomes vegan butter, not oil).

    Returns:
        (new_grams, notes):
        - new_grams: New ingredient dict with dairy codes replaced by SUB_* keys.
          Non-dairy ingredients are kept with their original FNDDS codes.
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
        dairy_cat = classify_dairy_ingredient(fpid)

        if dairy_cat is None:
            # Not dairy — keep as-is
            new_grams[fpid] = grams
            continue

        # Dairy ingredient — find substitution
        cooking_fn = infer_dairy_function(dairy_cat, context, grams, total_grams)
        rules = SUBSTITUTION_RULES.get(dairy_cat, {})
        rule = rules.get(cooking_fn) or rules.get("default")

        if rule:
            sub_id, sub_name, ratio = rule
            sub_grams = round(grams * ratio, 2)
            sub_key = f"SUB_{sub_id}"
            # Aggregate if multiple dairy ingredients map to the same substitute
            new_grams[sub_key] = round(new_grams.get(sub_key, 0) + sub_grams, 2)

            orig_desc = food_descriptions.get(fpid, fpid)
            notes.append(
                f"{orig_desc} ({grams:.0f}g) → {sub_name} ({sub_grams:.0f}g) "
                f"[{dairy_cat}/{cooking_fn}]"
            )
        else:
            # Unknown dairy with no matching rule — REMOVE for safety
            orig_desc = food_descriptions.get(fpid, fpid)
            notes.append(f"{orig_desc} ({grams:.0f}g) → REMOVED (unknown dairy, no rule)")

    return new_grams, notes


def get_dairy_summary(fndds_grams: Dict[str, float]) -> Dict[str, float]:
    """
    Summarize dairy content by category.

    Returns dict like {"butter": 28.0, "milk": 240.0, "cheese": 56.0}.
    """
    summary: Dict[str, float] = {}
    for fpid, grams in fndds_grams.items():
        cat = classify_dairy_ingredient(fpid)
        if cat:
            summary[cat] = summary.get(cat, 0) + grams
    return summary
