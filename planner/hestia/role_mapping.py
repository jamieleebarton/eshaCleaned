"""
Role-based template matching tables.

Maps LLM-assigned roles (M.protein, S.vegetable, etc.) to template names
using fnmatch wildcards. These mappings ADD recipes to template pools —
they never remove category-based assignments.
"""

from fnmatch import fnmatch
from typing import Dict, List

# Maps main role → list of template name patterns where that role's recipes can be mains
MAIN_ROLE_TO_TEMPLATES: Dict[str, List[str]] = {
    "M.breakfast": ["breakfast_*"],
    "M.protein": [
        "dinner_chicken*", "dinner_steak_*", "dinner_beef_*",
        "dinner_pork*", "dinner_ham_*", "dinner_bacon_*",
        "dinner_sausages_*", "dinner_seafood*", "dinner_lamb",
        "dinner_kids_classics", "dinner_southern_comfort",
        "lunch_kids_classics", "lunch_burgers",
    ],
    "M.composite": [
        "dinner_soup_or_stew", "dinner_casseroles", "dinner_stir_fry*",
        "dinner_stuffed_vegetables", "dinner_curry_*", "dinner_thai_*",
        "dinner_burrito_bowl", "lunch_soup_salad_*", "lunch_stews_*",
        "soup_or_stew_one_dish", "lunch_mexican",
        "dinner_seafood_stews_one_dish",
    ],
    "M.grain": [
        "dinner_pasta*", "dinner_vegetarian_pasta", "dinner_grain_mains",
        "dinner_pasta_italian", "lunch_pasta_*",
    ],
    "M.sandwich": [
        "lunch_sandwiches_wraps", "lunch_wraps", "lunch_burgers",
        "dinner_burgers", "breakfast_sandwiches",
        "breakfast_breakfast_sandwiches",
    ],
    "M.salad": [
        "lunch_salads_as_main",
    ],
}

# Maps side role → list of side pool name patterns
SIDE_ROLE_TO_POOLS: Dict[str, List[str]] = {
    "S.vegetable": [
        "vegetables", "veg_side", "veg", "breakfast_veg_sides",
    ],
    "S.starch": [
        "grains", "rice", "potato*", "starchy_breakfast",
        "fries", "french_fries", "sweet_potato_fries",
        "pasta_sides", "mac_and_cheese",
    ],
    "S.bread": [
        "bread", "toast", "breadsticks", "garlic_bread",
        "pita", "biscuits", "cornbread",
    ],
    "S.salad": [
        "green_salad", "veg_salads", "salad",
        "protein_salads", "pasta_salads", "grain_salads",
        "legume_salads", "international_salads", "seafood_salads",
        "potato_salads", "slaw",
    ],
    "S.fruit": [
        "fruit", "fruit_sides",
    ],
    "S.legume": [
        "beans", "baked_beans",
    ],
    "S.beans": [
        "beans", "baked_beans",
    ],
    "S.pasta": [
        "pasta_sides", "mac_and_cheese",
    ],
}


def role_matches_template(role: str, template_name: str) -> bool:
    """Check if a main role matches a template name via MAIN_ROLE_TO_TEMPLATES."""
    patterns = MAIN_ROLE_TO_TEMPLATES.get(role, [])
    return any(fnmatch(template_name, pat) for pat in patterns)


def role_matches_pool(role: str, pool_name: str) -> bool:
    """Check if a side role matches a side pool name via SIDE_ROLE_TO_POOLS."""
    patterns = SIDE_ROLE_TO_POOLS.get(role, [])
    return any(fnmatch(pool_name, pat) for pat in patterns)
