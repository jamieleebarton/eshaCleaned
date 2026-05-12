"""Deterministic non-food product filter applied in price_resolver.

Two rules:
1. DROP_SEARCH_FALLBACK_AT_Q1 — products whose tag_trust starts with
   `search_term_fallback` were tagged by "we searched for X, so canonical=X"
   with no product-name confirmation. At quality=1 this pulls in junk the
   retailer returned (Water Softener Salt for search_term='salt'). Drop.
2. NON_FOOD_PATTERNS — regex patterns with \\b word boundaries; a product
   name matching any pattern is rejected for food canonicals.
"""
from __future__ import annotations
import re

_PATTERNS = [
    # feed / agriculture
    r"\bfeed\b(?! me)",                  # "Egg Layer Feed" but not "feed me"
    r"\blivestock\b",
    r"\blayer\s+pellet",
    r"\blayer\s+\+\s*omega\b",
    r"\bwaterfowl\b",
    r"\bpoultry\s+feed\b",
    r"\bchick\s+starter\b",
    r"\banimal\s+feed\b",
    r"\bpellets?\b",
    # industrial salt / softener
    r"\bwater\s+softener\b",
    r"\bsoftener\s+(?:pellets|salt)\b",
    r"\bice\s+melt\b",
    # personal care — bounded to avoid matching bleached/conditioned etc
    r"\bmousse\b",
    r"\bstyling\b",
    r"\bshampoo\b",
    r"\bhair\s+conditioner\b",
    r"\bhair\s+care\b",
    r"\bbody\s+wash\b",
    # cleaning (bounded)
    r"\bdetergent\b",
    r"\bdisinfect\w*\b",
    # paper / craft
    r"\bmailer\b",
    r"\benvelope\b",
    # processed confusers we don't want as the canonical-of-record
    r"\bhushpuppy\b",
    r"\bhush\s+pupp(?:y|ies)\b",
    r"\bpierogies?\b",
    # drink confusers for 'sugar'
    r"\btonic\b",
    r"\benergy\s+drink\b",
    # pancake syrups pretending to be butter
    r"\bbutter\s+rich\s+syu?rp\b",
    r"\bpancake\s+syrup\b",
    # prepared-meat confusers
    r"\bbreaded\s+chicken\s+breast\b",
    r"\bfully\s+cooked\s+chicken\b",
    r"\bchicken\s+nuggets?\b",
    r"\bchicken\s+patt(?:y|ies)\b",
]

_NON_FOOD_RE = re.compile("|".join(_PATTERNS), re.I)


def is_non_food(name: str) -> bool:
    return bool(_NON_FOOD_RE.search(name or ""))


def is_search_term_fallback(tag_trust: str) -> bool:
    return (tag_trust or "").startswith("search_term_fallback")
