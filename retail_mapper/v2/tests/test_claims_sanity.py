"""Claims sanity invariants: claims at leaf end, no contradictory claim pairs,
and no claim-as-type bugs.

  - 'Sugar Free > Sugar' (contradiction)
  - 'Vegan > Beef' (contradiction)
  - 'Organic > Conventional' (contradiction)
  - Claims must come AFTER all type/variant/flavor/form/processing segments
"""
from __future__ import annotations

from conftest import fail_with_samples


# Recognized claim words/phrases — when these appear in a path, they must
# come at the end (after all type/variant/flavor/form/processing segments).
CLAIM_WORDS = frozenset({
    "organic", "natural", "all natural", "plant based", "gluten free",
    "dairy free", "sugar free", "fat free", "low fat", "reduced fat",
    "lowfat", "low sodium", "no salt added", "unsweetened", "sweetened",
    "no sugar added", "reduced sugar", "zero sugar", "low calorie",
    "reduced calorie", "zero calorie", "diet", "light", "lite",
    "fortified", "probiotic", "grass fed", "free range", "cage free",
    "wild caught", "fair trade", "kosher", "halal", "vegan", "keto",
    "paleo", "whole grain", "multi grain", "non gmo", "no preservatives",
    "no artificial flavors", "high protein", "high fiber", "caffeine free",
    "no caffeine", "decaffeinated", "decaf", "low carb", "keto friendly",
    "lactose free", "non dairy", "no fat", "no sodium", "wheat free",
    "shelf stable", "cold pressed",
})

# Contradictory pairs — if BOTH appear in same path, that's a logical bug
CONTRADICTIONS = [
    ("sugar free", "sugar"),
    ("sugar free", "sweetened"),
    ("zero sugar", "sweetened"),
    ("no sugar added", "sweetened"),
    ("vegan", "beef"),
    ("vegan", "chicken"),
    ("vegan", "pork"),
    ("vegan", "milk"),
    ("vegan", "cheese"),
    ("vegan", "egg"),
    ("vegan", "honey"),
    ("organic", "conventional"),
    ("dairy free", "milk"),
    ("dairy free", "cheese"),
    ("dairy free", "butter"),
    ("gluten free", "wheat"),
    ("caffeine free", "caffeine"),
    ("decaf", "caffeine"),
    ("fat free", "full fat"),
    ("low fat", "full fat"),
]


def _segs_lower(r: dict) -> list[str]:
    cp = (r.get("canonical_path") or "").strip()
    return [s.strip().lower() for s in cp.split(" > ")] if cp else []


def test_no_contradictory_claim_pairs(audit_rows):
    """Path must not contain both claims of a contradiction pair."""
    bad = []
    for r in audit_rows:
        segs = _segs_lower(r)
        seg_set = set(segs)
        for a, b in CONTRADICTIONS:
            # Match by exact segment OR sub-word containment for short terms
            has_a = a in seg_set or any(a == w for w in segs)
            has_b = b in seg_set or any(b == w for w in segs)
            # For words like "milk" that appear in compound segments, be stricter
            # — only flag when both are present as standalone segments
            if has_a and has_b:
                r2 = dict(r); r2["_contradiction"] = f"{a} + {b}"
                bad.append(r2)
                break
    if bad:
        fail_with_samples(
            "Claims sanity violated: contradictory claim/type pair in same path",
            bad, extra_cols=["_contradiction"],
        )


def test_claims_at_leaf_end(audit_rows):
    """Once a claim segment is encountered, no non-claim segment may follow.

    I.e., claims belong at the leaf end. If we see [..., 'Sugar Free', 'Strawberry'],
    that's wrong — the flavor 'Strawberry' should come BEFORE the claim.
    """
    bad = []
    for r in audit_rows:
        segs = _segs_lower(r)
        if len(segs) < 3:
            continue
        # Skip family (segs[0]) and look for first claim, then any non-claim after it
        seen_claim = False
        for s in segs[1:]:
            is_claim = s in CLAIM_WORDS
            if seen_claim and not is_claim:
                r2 = dict(r); r2["_claim_followed_by_non_claim"] = s
                bad.append(r2)
                break
            if is_claim:
                seen_claim = True
    if bad:
        fail_with_samples(
            "Claims sanity violated: non-claim segment appears AFTER a claim",
            bad, extra_cols=["_claim_followed_by_non_claim"],
        )


def test_claim_not_in_type_position(audit_rows):
    """Claims must not occupy the type position (segs[1])."""
    bad = []
    for r in audit_rows:
        segs = _segs_lower(r)
        if len(segs) < 2:
            continue
        if segs[1] in CLAIM_WORDS:
            r2 = dict(r); r2["_claim_as_type"] = segs[1]
            bad.append(r2)
    if bad:
        fail_with_samples(
            "Claims sanity violated: claim word in TYPE position (path segment 2)",
            bad, extra_cols=["_claim_as_type"],
        )
