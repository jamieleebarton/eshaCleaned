"""Display-aware recipe-line canonical path overrides.

These are for cases where the base food name is too broad but the recipe
display carries the purchasable form.  They keep the correction at the identity
layer instead of relying on picker blocklists.
"""
from __future__ import annotations

import re
import unicodedata


def norm(text: str | None) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    hay = f" {text} "
    return any(f" {norm(phrase)} " in hay for phrase in phrases)


def line_canonical_path_override(item: str, display: str) -> str | None:
    item_norm = norm(item)
    text = norm(f"{item} {display}")

    if item_norm in {"neufchatel cheese", "neufchatel"} or "neufchatel" in text:
        return "Dairy > Cheese > Neufchatel"

    if "lettuce" in text:
        if has_phrase(text, ("shredded lettuce", "lettuce shredded")):
            return "Produce > Vegetables > Shredded Lettuce"
        if has_phrase(text, ("head lettuce", "lettuce head", "lettuce leaf", "lettuce leaves")):
            return "Produce > Vegetables > Lettuce"

    cut_terms = (
        "ham steak", "whole ham", "spiral ham", "bone in ham", "bone-in ham",
        "ham roast", "ham hock", "picnic ham", "shank ham",
    )
    ham_lunch_terms = (
        "deli ham", "ham slices", "slices ham", "sliced ham",
        "thinly sliced ham", "sandwich ham",
    )
    if "ham" in text and not has_phrase(text, cut_terms) and has_phrase(text, ham_lunch_terms):
        return "Meal > Sandwiches > Lunch Meat"

    corned_beef_lunch_terms = (
        "deli corned beef", "thinly sliced corned beef",
        "sliced cooked corned beef", "sliced corned beef",
        "corned beef lunch meat", "corned beef lunchmeat",
    )
    corned_beef_cut_terms = (
        "corned beef brisket", "corned beef hash", "canned corned beef",
        "can corned beef",
    )
    if (
        "corned beef" in text
        and not has_phrase(text, corned_beef_cut_terms)
        and has_phrase(text, corned_beef_lunch_terms)
    ):
        return "Meal > Sandwiches > Lunch Meat"

    return None
