"""Deterministic defaults for recipe-side gram calculation.

Every policy class that Nebius can emit has a documented numeric default here.
The calculator dispatches on the policy class, never on substrings of the
ingredient name. Substring lookups inside this module are sub-classifiers
within a class (e.g. distinguishing deep-fry from sauté inside uptake).
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# yield_policy_required
# ---------------------------------------------------------------------------

BONE_IN_PORK = {
    "ham bone", "ham hock", "pork shoulder bone", "pork shank bone",
    "pork rib bone", "pork bone", "smoked ham bone",
}
BONE_IN_POULTRY = {
    "bone-in chicken", "bone in chicken", "chicken pieces", "chicken thigh",
    "chicken thighs", "chicken drumstick", "drumsticks", "chicken wing",
    "chicken wings", "whole chicken", "whole turkey", "bone-in turkey",
    "turkey pieces", "turkey thigh", "turkey drumstick", "chicken back",
    "chicken neck", "chicken carcass",
}
BONE_IN_BEEF_LAMB = {
    "oxtail", "short rib", "short ribs", "beef shank", "beef bone",
    "lamb shank", "lamb bone", "bone-in lamb", "bone-in beef",
    "bone in beef", "bone in lamb", "marrow bone",
}
SHELL_ON_SHELLFISH = {
    "shell-on shrimp", "shell on shrimp", "whole shrimp", "head-on shrimp",
    "whole crab", "whole lobster", "shell-on prawn", "shell on prawn",
    "whole prawn",
}
WHOLE_FISH = {
    "whole fish", "whole trout", "whole salmon", "whole snapper",
    "whole mackerel", "whole sea bass", "fish with head",
}
PEEL_ON_PRODUCE = {
    "unpeeled", "peel-on", "peel on", "rind-on", "rind on",
    "with rind", "with peel", "skin-on potato",
}

YIELD_CLASSES: list[tuple[set[str], float, str]] = [
    (BONE_IN_PORK, 0.25, "bone_in_pork_yield_25pct_applied"),
    (BONE_IN_POULTRY, 0.70, "bone_in_poultry_yield_70pct_applied"),
    (BONE_IN_BEEF_LAMB, 0.60, "bone_in_beef_lamb_yield_60pct_applied"),
    (SHELL_ON_SHELLFISH, 0.50, "shell_on_shellfish_yield_50pct_applied"),
    (WHOLE_FISH, 0.55, "whole_fish_yield_55pct_applied"),
    (PEEL_ON_PRODUCE, 0.70, "peel_on_produce_yield_70pct_applied"),
]
YIELD_FALLBACK: tuple[float, str] = (0.50, "yield_policy_default_50pct_applied")


# ---------------------------------------------------------------------------
# retention_policy_required
# ---------------------------------------------------------------------------

REMOVED_AROMATIC = {
    "bay leaf", "cinnamon stick", "whole spice", "whole spices",
    "peppercorn", "peppercorns", "cheesecloth", "kombu", "herb stem",
    "tea bag", "spice bag", "bouquet garni", "star anise", "cardamom pod",
    "cardamom pods", "clove pod", "whole clove", "whole cloves",
}
COATING = {
    "dredge", "dredging", "for dredging", "for coating", "for breading",
    "breading", "to coat", "for the coating",
}
DUSTING = {
    "for dusting", "dusting", "to dust", "for sprinkling",
}

RETENTION_CLASSES: list[tuple[set[str], float, str]] = [
    (REMOVED_AROMATIC, 0.0, "removed_aromatic_zero_consumption_applied"),
    (COATING, 0.25, "coating_retention_25pct_applied"),
    (DUSTING, 0.10, "dusting_retention_10pct_applied"),
]
RETENTION_FALLBACK: tuple[float, str] = (0.0, "retention_policy_default_zero_applied")


# ---------------------------------------------------------------------------
# uptake_policy_required
# ---------------------------------------------------------------------------

DEEP_FRY = {
    "for frying", "deep fry", "deep-fry", "deep frying",
    "for deep frying", "for deep-frying",
}
SHALLOW_FRY = {
    "shallow fry", "shallow-fry", "pan fry", "pan-fry", "pan frying",
}
SAUTE = {
    "saute", "sauté", "sautéing", "sauteing", "sweat",
    "to coat the pan", "for sautéing", "for sauteing", "for cooking",
    "for the pan",
}

UPTAKE_CLASSES: list[tuple[set[str], float, str]] = [
    (DEEP_FRY, 0.10, "deep_fry_uptake_10pct_applied"),
    (SHALLOW_FRY, 0.50, "shallow_fry_uptake_50pct_applied"),
    (SAUTE, 0.25, "saute_uptake_25pct_applied"),
]
UPTAKE_FALLBACK: tuple[float, str] = (0.25, "uptake_policy_default_25pct_applied")


# ---------------------------------------------------------------------------
# sodium_absorption_policy_required
# ---------------------------------------------------------------------------

PASTA_WATER = {
    "pasta water", "boiling water", "for boiling", "for blanching",
    "blanching water", "salting the water", "salted water",
}
BRINE = {"brine", "brining", "brining liquid"}

SODIUM_CLASSES: list[tuple[set[str], float, str]] = [
    (PASTA_WATER, 0.10, "pasta_water_sodium_10pct_applied"),
    (BRINE, 0.15, "brine_sodium_15pct_applied"),
]
SODIUM_FALLBACK: tuple[float, str] = (0.10, "sodium_absorption_default_10pct_applied")


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def _lookup(
    haystack: str,
    classes: list[tuple[set[str], float, str]],
    fallback: tuple[float, str],
) -> tuple[float, str]:
    for keywords, factor, tag in classes:
        for keyword in keywords:
            if keyword in haystack:
                return factor, tag
    return fallback


def lookup_yield(haystack: str) -> tuple[float, str]:
    return _lookup(haystack, YIELD_CLASSES, YIELD_FALLBACK)


def lookup_retention(haystack: str) -> tuple[float, str]:
    return _lookup(haystack, RETENTION_CLASSES, RETENTION_FALLBACK)


def lookup_uptake(haystack: str) -> tuple[float, str]:
    return _lookup(haystack, UPTAKE_CLASSES, UPTAKE_FALLBACK)


def lookup_sodium(haystack: str) -> tuple[float, str]:
    return _lookup(haystack, SODIUM_CLASSES, SODIUM_FALLBACK)
