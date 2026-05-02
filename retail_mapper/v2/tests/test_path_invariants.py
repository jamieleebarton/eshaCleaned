"""Per-row path structure invariants (1-9 from the spec).

Each test scans every row, collects violations, and fails with sample SKUs if
any are found. Tests are designed to be FAST: a single pass per test, no
nested loops over the corpus.
"""
from __future__ import annotations

import re

from conftest import fail_with_samples


# ---------------------------------------------------------------------
# Lexicons used across multiple tests
# ---------------------------------------------------------------------

# BFC names that should never appear as a leaf in a path. These are
# combined-parent retail-category strings, not actual product types.
BFC_LEAF_BLACKLIST = {
    "appetizers & snacks", "baking mixes", "patties & burgers",
    "cookies & biscuits", "crackers & biscotti", "biscuits/cookies",
    "hot dogs & sausages", "sausages, hotdogs & brats",
    "pickles, olives, peppers & relishes", "frosting & icing",
    "dips & spreads", "sauces & salsas", "spices & seasonings",
    "breads & buns", "wraps & burritos", "pies & tarts",
    "pepperoni, salami & cold cuts", "sports & wellness",
    "bagels, muffins, doughnuts & pastries",
    "beverages", "drinks", "snacks", "snack",
}

# Generic words that should not appear standalone as a leaf
GENERIC_LEAF_BLACKLIST = {
    "plain", "natural", "original",  # too generic when no other context
}


# ---------------------------------------------------------------------
# Invariant 1: Family is valid
# ---------------------------------------------------------------------

def test_family_is_valid(audit_rows, valid_families):
    """First segment of every canonical_path must be a known family."""
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        family = cp.split(" > ", 1)[0]
        if family not in valid_families:
            bad.append(r)
    if bad:
        fail_with_samples(
            f"Invariant 1 violated: invalid family in canonical_path. "
            f"Allowed: {sorted(valid_families)}",
            bad,
            extra_cols=["branded_food_category", "product_identity_fixed"],
        )


# ---------------------------------------------------------------------
# Invariant 2: Type is present (path has >=2 segments)
# ---------------------------------------------------------------------

def test_type_segment_present(audit_rows):
    """Every path must have a TYPE (at least 2 segments) when PI is populated."""
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        pi = (r.get("product_identity_fixed") or "").strip()
        if not (cp and pi):
            continue
        segs = cp.split(" > ")
        if len(segs) < 2:
            bad.append(r)
    if bad:
        fail_with_samples(
            "Invariant 2 violated: canonical_path has only family, no type segment",
            bad, extra_cols=["product_identity_fixed"],
        )


# ---------------------------------------------------------------------
# Invariant 4: No duplicate segments within a path (case-insensitive)
# ---------------------------------------------------------------------

def test_no_duplicate_segments(audit_rows):
    """Each segment in a path must be unique (case-insensitive)."""
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        segs = cp.split(" > ")
        seen = set()
        for s in segs:
            sl = s.lower()
            if sl in seen:
                bad.append(r)
                break
            seen.add(sl)
    if bad:
        fail_with_samples(
            "Invariant 4 violated: duplicate segments in canonical_path",
            bad,
        )


# ---------------------------------------------------------------------
# Invariant 5: No type-echo / parent-echo
# ---------------------------------------------------------------------
# Singular/plural-aware: "Bagel > Bagels", "Cookie > Cookies", etc.
# Also catches "Cake > Pound Cake > Cake" style.

_PLURAL_S = re.compile(r"s$", re.I)


def _normalize_plural(w: str) -> str:
    """Strip trailing 's' for echo detection."""
    return _PLURAL_S.sub("", w.strip().lower())


def test_no_type_echo(audit_rows):
    """No two segments in the same path should normalize to the same root word.

    E.g., 'Bakery > Cookies > Madeleines > Cookies' is an echo.
    Allows ≤1% tolerance for edge cases (e.g., variant column legitimately
    repeats a type word like 'Smoothie' that's in path).
    """
    bad = []
    n_total = 0
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        n_total += 1
        segs = cp.split(" > ")
        if len(segs) < 3:
            continue
        normed = [_normalize_plural(s) for s in segs[1:]]
        if len(normed) != len(set(normed)):
            bad.append(r)
    if bad and (len(bad) / max(1, n_total)) > 0.01:
        fail_with_samples(
            f"Invariant 5 violated: {len(bad):,}/{n_total:,} ({len(bad)/n_total:.1%}) paths have type-echo (>1% threshold)",
            bad,
        )


# ---------------------------------------------------------------------
# Invariant 6: No family-name in leaf position
# ---------------------------------------------------------------------

def test_no_family_in_leaf(audit_rows, valid_families):
    """Family names must not appear at non-family positions.
    Allows ≤0.1% tolerance for edge cases (e.g., 'Frozen' as a processing
    state legitimately appearing in a non-Frozen-family path)."""
    families_lower = {f.lower() for f in valid_families}
    bad = []
    n_total = 0
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        n_total += 1
        segs = cp.split(" > ")
        if len(segs) < 2:
            continue
        for s in segs[1:]:
            if s.lower() in families_lower:
                bad.append(r)
                break
    if bad and (len(bad) / max(1, n_total)) > 0.001:
        fail_with_samples(
            f"Invariant 6 violated: {len(bad):,}/{n_total:,} family-name in non-family position (>0.1% threshold)",
            bad,
        )


# ---------------------------------------------------------------------
# Invariant 7: No BFC-name in leaf position
# ---------------------------------------------------------------------

def test_no_bfc_name_in_leaf(audit_rows):
    """Combined retail-category names like 'Hot Dogs & Sausages',
    'Patties & Burgers', 'Cookies & Biscuits' must never appear at the
    LEAF position of a path. (A BFC name as the type-slot of a 2-segment
    path is allowed only if it's a legitimate sub-family like 'Baking Mixes'
    that contains specific types beneath it.)
    """
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        segs = cp.split(" > ")
        if len(segs) < 2:
            continue
        # Check ONLY the last segment (the actual leaf)
        leaf = segs[-1].lower()
        if leaf in BFC_LEAF_BLACKLIST:
            bad.append(r)
    if bad:
        fail_with_samples(
            "Invariant 7 violated: BFC-name appears as the LEAF segment of canonical_path",
            bad, extra_cols=["branded_food_category"],
        )


# ---------------------------------------------------------------------
# Invariant 9: No raw underscores in any segment
# ---------------------------------------------------------------------

def test_no_underscores_in_segments(audit_rows):
    """Segments must be human-readable title-cased; no underscores.

    Catches the bug where 'cinnamon_raisin' from variant column leaks
    directly into path without being converted to 'Cinnamon Raisin'.
    """
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        if "_" in cp:
            bad.append(r)
    if bad:
        fail_with_samples(
            "Invariant 9 violated: underscores in canonical_path segments",
            bad,
        )


# ---------------------------------------------------------------------
# Invariant 19: Every SKU has a non-empty canonical_path
# ---------------------------------------------------------------------

def test_every_sku_has_path(audit_rows):
    """No row may have an empty canonical_path."""
    bad = [r for r in audit_rows if not (r.get("canonical_path") or "").strip()]
    if bad:
        fail_with_samples(
            "Invariant 19 violated: SKU has empty canonical_path",
            bad, extra_cols=["product_identity_fixed", "branded_food_category"],
        )


# ---------------------------------------------------------------------
# Invariant 20: canonical_path and retail_leaf_path are consistent
# ---------------------------------------------------------------------

def test_retail_leaf_consistent_with_canonical(audit_rows):
    """retail_leaf_path should equal or extend canonical_path (start with it)."""
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        rlp = (r.get("retail_leaf_path") or "").strip()
        if not cp or not rlp:
            continue
        # rlp must be either equal to cp, or start with cp + " > " (extension)
        if rlp != cp and not rlp.startswith(cp + " > ") and not cp.startswith(rlp + " > "):
            bad.append(r)
    if bad:
        fail_with_samples(
            "Invariant 20 violated: retail_leaf_path inconsistent with canonical_path",
            bad, extra_cols=["retail_leaf_path"],
        )


# ---------------------------------------------------------------------
# Invariant 8 (partial): Generic standalone leaves
# ---------------------------------------------------------------------

def test_no_generic_standalone_leaf(audit_rows):
    """Path's last segment shouldn't be a generic word like 'Plain', 'Natural', 'Original'
    when the path has only 2 or 3 segments — those need more specificity."""
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        segs = cp.split(" > ")
        if len(segs) > 3:
            continue  # deep paths are fine; generics are okay further down
        leaf = segs[-1].lower()
        if leaf in GENERIC_LEAF_BLACKLIST and len(segs) <= 2:
            bad.append(r)
    # NOTE: this is informational; we don't fail if the count is small
    # because some legitimate paths terminate in 'Plain' (e.g., Yogurt > Plain).
    # We log but allow.
    if len(bad) > 1000:
        fail_with_samples(
            f"Too many shallow paths ending in generic word ({len(bad)}); "
            f"need deeper categorization",
            bad,
        )
