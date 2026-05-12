"""Household-free recipe concepts.

These are recipe-side concepts that should contribute zero shopping cost and
must never become cart or pantry inventory.  Keep this exact-path based:
"watermelon" and "water chestnuts" are foods, not tap water.
"""
from __future__ import annotations

from dataclasses import dataclass


HOUSEHOLD_FREE_RECIPE_PATHS = frozenset(
    {
        "Beverage > Water",
        "Beverage > Water > Tap Water",
        "Beverage > Ice",
    }
)


@dataclass(frozen=True)
class HouseholdFreeDecision:
    is_free: bool
    reason: str = ""


def canonical_path_from_concept_key(concept_key: str | None) -> str:
    """Return the canonical_path part of a `canonical_path|htc_form` key."""
    if not concept_key:
        return ""
    return concept_key.split("|", 1)[0].strip()


def household_free_decision(
    recipe_concept_key: str | None,
    priced_concept_key: str | None = None,
) -> HouseholdFreeDecision:
    """Classify a recipe line as household-free only from recipe identity.

    The priced key is accepted for audit context, but it is intentionally not
    used to turn specific purchasable water-like foods into free tap water.
    A recipe-side `Beverage > Water` line may resolve to any plain-water SKU;
    it is still household tap water for planning.  A recipe-side
    `Beverage > Water > Tonic Water`, `Produce > Fruit > Watermelon`, or
    `Pantry > Canned Vegetables > Water Chestnuts` line is not.
    """
    del priced_concept_key
    recipe_path = canonical_path_from_concept_key(recipe_concept_key)
    if recipe_path in HOUSEHOLD_FREE_RECIPE_PATHS:
        return HouseholdFreeDecision(True, f"recipe_path:{recipe_path}")
    return HouseholdFreeDecision(False)


def is_household_free_recipe_concept(recipe_concept_key: str | None) -> bool:
    return household_free_decision(recipe_concept_key).is_free
