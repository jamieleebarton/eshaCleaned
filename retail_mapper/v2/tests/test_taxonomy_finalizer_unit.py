"""Unit tests for taxonomy_finalizer functions — independent of audit data.

These tests pin specific invariants directly to the finalizer logic so they
fail at IMMEDIATE level (function call), not after a full audit regen.

If a refactor or linter removes a critical guard, these tests fail fast.
"""
from __future__ import annotations

import sys
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))

from taxonomy_finalizer import _canonical_from_category_identity  # noqa: E402


def test_bfc_strip_replaces_combined_parent_ampersand():
    """BFC combined-parent name with '&' must be REPLACED with identity.
       'Pantry > Sauces & Salsas' + 'Salsa' → 'Pantry > Salsa'
       NOT 'Pantry > Sauces & Salsas > Salsa'.
    """
    result = _canonical_from_category_identity("Pantry > Sauces & Salsas", "Salsa")
    assert result == "Pantry > Salsa", (
        f"BFC strip removed/reverted. Got: {result!r}. "
        f"Re-add the [&,/] strip in _canonical_from_category_identity."
    )


def test_bfc_strip_replaces_combined_parent_comma():
    """BFC combined-parent with comma must be REPLACED.
       'Frozen > Pancakes, Waffles, French Toast & Crepes' + 'Pancakes'
       → 'Frozen > Pancakes' (NOT '... > Crepes > Pancakes')
    """
    result = _canonical_from_category_identity(
        "Frozen > Pancakes, Waffles, French Toast & Crepes", "Pancakes"
    )
    assert result == "Frozen > Pancakes", (
        f"BFC strip not handling comma-separated combined parents. Got: {result!r}"
    )


def test_bfc_strip_replaces_combined_parent_slash():
    """BFC combined-parent with '/' must be REPLACED.
       'Dairy > Milk/Milk Substitutes' + 'Whole Milk' → 'Dairy > Whole Milk'
    """
    result = _canonical_from_category_identity("Dairy > Milk/Milk Substitutes", "Whole Milk")
    assert result == "Dairy > Whole Milk", (
        f"BFC strip not handling slash-separated combined parents. Got: {result!r}"
    )


def test_clean_category_keeps_identity_appended():
    """When category last segment is NOT a combined-parent, identity gets
    appended normally. 'Bakery > Bagels' + 'Bagels' returns 'Bakery > Bagels'
    (identity already in category_keys → not re-appended).
    """
    result = _canonical_from_category_identity("Bakery > Bagels", "Bagels")
    assert result == "Bakery > Bagels"


def test_specific_identity_appended_to_clean_category():
    """'Dairy > Cheese' + 'Cheddar' → 'Dairy > Cheese > Cheddar'
    (Cheddar is more specific than Cheese, gets appended.)
    """
    result = _canonical_from_category_identity("Dairy > Cheese", "Cheddar")
    assert result == "Dairy > Cheese > Cheddar"


def test_empty_inputs():
    """Empty category or identity must not crash."""
    assert _canonical_from_category_identity("", "") == ""
    assert _canonical_from_category_identity("", "Cheese") == "Cheese"
    assert _canonical_from_category_identity("Dairy", "") == "Dairy"
