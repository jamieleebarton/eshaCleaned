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


# Phase A1 (Codex insight): BFC sub-family hierarchy is now PRESERVED at
# intermediate positions (Pantry > Sauces & Salsas > Sauce is shopper-friendly).
# The strip only fires on:
#   (a) verbose 3+ item BFC labels (Pancakes, Waffles, French Toast & Crepes)
#   (b) BFC labels that would otherwise become the LEAF
# The strip lives in homogenize_audit.py Pass 4.7 (linter kept reverting it
# in taxonomy_finalizer.py, so we apply it post-finalize).


def test_intermediate_bfc_subfamily_kept():
    """When category last segment is a BFC retail sub-family ('Sauces & Salsas')
    and identity is more specific ('Salsa'), the sub-family stays as an
    intermediate segment per Codex feedback.

    Result: 'Pantry > Sauces & Salsas > Salsa' (NOT 'Pantry > Salsa').
    """
    result = _canonical_from_category_identity("Pantry > Sauces & Salsas", "Salsa")
    assert result == "Pantry > Sauces & Salsas > Salsa", (
        f"Intermediate BFC sub-family was wrongly stripped. Got: {result!r}"
    )


def test_intermediate_milk_substitutes_kept():
    """'Dairy > Milk/Milk Substitutes' + 'Whole Milk' → keep the slash-segment
    as intermediate sub-family.
    """
    result = _canonical_from_category_identity("Dairy > Milk/Milk Substitutes", "Whole Milk")
    assert result == "Dairy > Milk/Milk Substitutes > Whole Milk"


def test_verbose_bfc_label_handled_by_homogenize():
    """The verbose 'Pancakes, Waffles, French Toast & Crepes' is too long
    to be useful in a path. It's stripped by homogenize_audit.py Pass 4.7
    (not by _canonical_from_category_identity directly). This unit test
    just documents the contract; the actual strip happens at audit-build time.
    """
    # finalize keeps it as an intermediate; homogenize strips it later
    result = _canonical_from_category_identity(
        "Frozen > Pancakes, Waffles, French Toast & Crepes", "Pancakes"
    )
    # Either pre-strip or post-strip is acceptable here; verify final-form
    # behavior in test_homogenize_audit_smoke instead.
    assert result in (
        "Frozen > Pancakes, Waffles, French Toast & Crepes > Pancakes",
        "Frozen > Pancakes",
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
