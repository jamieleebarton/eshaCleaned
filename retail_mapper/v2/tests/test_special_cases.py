"""Invariants 21-24: special-case rules surfaced from real bug reports.

  21. Plant milks include the specific plant type (Oat/Almond/Soy/etc.)
  22. Sandwiches don't contain Peanut Butter leaf when title doesn't say "peanut"
  23. Concatenated leaves split — no segment with " & " or " and " connecting
      what should be separate variant/flavor leaves
  24. Same-fndds_code SKUs grouped by (claims, form) cluster — same family+type

Plus: title-vs-leaf consistency for nut butters and key flavors.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from conftest import fail_with_samples


# ---------------------------------------------------------------------
# I21: Plant milks must include specific plant type
# ---------------------------------------------------------------------

PLANT_TYPES = {
    "almond milk", "oat milk", "soy milk", "coconut milk", "rice milk",
    "cashew milk", "hemp milk", "pea milk", "macadamia milk", "flax milk",
    "hazelnut milk", "walnut milk", "quinoa milk",
}


def test_plant_milk_has_plant_type(audit_rows):
    """Any path under 'Beverage > Plant Milk' must include the specific
    plant type (e.g., 'Oat Milk') as the third segment."""
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp.startswith("Beverage > Plant Milk"):
            continue
        segs = cp.split(" > ")
        if len(segs) < 3:
            r2 = dict(r); r2["_issue"] = "no plant type after Plant Milk"
            bad.append(r2)
            continue
        third = segs[2].lower()
        # Allow: 'Oat Milk', 'Almond Milk', etc. OR a brand-specific name + Milk
        if third in PLANT_TYPES or third.endswith(" milk"):
            continue
        # Sometimes the third segment is a generic variant ("Original", "Plain")
        # without a plant-type leaf — that's the bug we're catching.
        r2 = dict(r); r2["_issue"] = f"3rd segment {third!r} is not a plant-milk type"
        bad.append(r2)
    if bad:
        fail_with_samples(
            "Invariant 21 violated: Plant Milk path missing specific plant type (Oat/Almond/Soy/etc.)",
            bad, extra_cols=["product_identity_fixed", "_issue"],
        )


# ---------------------------------------------------------------------
# I22: Sandwich nut-butter leaf consistency with title
# ---------------------------------------------------------------------

NUT_BUTTERS = {
    "peanut butter": "peanut",
    "almond butter": "almond",
    "cashew butter": "cashew",
    "sunflower butter": "sunflower",
    "soy butter": "soy",
    "hazelnut butter": "hazelnut",
}


def test_sandwich_nut_butter_matches_title(audit_rows):
    """If a Sandwich path contains a nut-butter leaf (e.g., 'Peanut Butter'),
    the corresponding nut word must appear in the title.

    Catches the bug where FNDDS code 42303010 (Peanut butter and banana sandwich)
    drags 'Peanut Butter' onto an Almond Butter sandwich.
    """
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if "Sandwich" not in cp and "sandwiches" not in cp.lower():
            continue
        title_l = (r.get("title") or "").lower()
        segs_lower = [s.lower() for s in cp.split(" > ")]
        for nut_butter, nut_word in NUT_BUTTERS.items():
            if nut_butter in segs_lower and nut_word not in title_l:
                r2 = dict(r); r2["_wrong_nut"] = nut_butter
                bad.append(r2)
                break
    if bad:
        fail_with_samples(
            "Invariant 22 violated: Sandwich path contains nut-butter not in title",
            bad, extra_cols=["_wrong_nut"],
        )


# ---------------------------------------------------------------------
# I23: No concatenated leaves (segments containing " & " or " and " that
# should be separate)
# ---------------------------------------------------------------------

# Allow-list of legitimate compound-segment names (these stay)
ALLOWED_COMPOUND_SEGMENTS = {
    # Forms / processing
    "thaw and serve", "ready to eat", "ready to drink", "ready to bake",
    "on the go", "single serve",
    # Compound flavors that are genuinely one thing
    "peanut butter and jelly", "peanut butter & jelly",
    "salt and pepper", "salt & pepper",
    "macaroni and cheese", "mac and cheese",
    "fish and chips",
    "cookies and cream", "cookies & cream",
    "milk and cereal", "milk & cereal",
    "rice and beans", "rice & beans",
    "chicken and rice", "chicken & rice",
    "beef and broccoli", "beef & broccoli",
    "ham and cheese", "ham & cheese",
    "fruit and nut", "fruit & nut",
    "nuts and seeds", "nuts & seeds",
    "honey and oats", "honey & oats",
    "spinach and artichoke", "spinach & artichoke",
}


def test_no_concatenated_leaves(audit_rows):
    """Path segments containing ' & ' or ' and ' that aren't in the
    legitimate-compound allow-list are likely two leaves jammed together."""
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        segs = cp.split(" > ")
        for s in segs:
            sl = s.lower().strip()
            if " & " not in sl and " and " not in sl:
                continue
            if sl in ALLOWED_COMPOUND_SEGMENTS:
                continue
            r2 = dict(r); r2["_concat_seg"] = s
            bad.append(r2)
            break
    if bad:
        fail_with_samples(
            "Invariant 23 violated: concatenated/compound segment likely two leaves jammed together",
            bad, extra_cols=["_concat_seg"],
        )


# ---------------------------------------------------------------------
# I24: Same fndds_code → same family+type (loose, 80% concentration)
# Skip NFS catch-all codes
# ---------------------------------------------------------------------

def test_fndds_code_family_type_concentration(audit_rows):
    """For each non-NFS FNDDS code with >=5 SKUs, the family+type (top-2
    segments of canonical_path) must concentrate at >=80% in one prefix.

    NFS codes (Not Further Specified) legitimately span many products
    and are excluded.
    """
    fndds_groups: dict[str, Counter] = defaultdict(Counter)
    fndds_descs: dict[str, str] = {}
    for r in audit_rows:
        f = (r.get("fndds_code") or "").strip()
        cp = (r.get("canonical_path") or "").strip()
        if not (f and cp):
            continue
        desc = (r.get("fndds_desc") or "").strip()
        if "NFS" in desc.upper() or "NS AS TO" in desc.upper():
            continue
        segs = cp.split(" > ")
        top2 = " > ".join(segs[:2]) if len(segs) >= 2 else cp
        fndds_groups[f][top2] += 1
        fndds_descs[f] = desc

    scattered: list[tuple[str, str, int, list[tuple[str, int]]]] = []
    for code, paths in fndds_groups.items():
        total = sum(paths.values())
        if total < 5:
            continue
        top_path, top_n = paths.most_common(1)[0]
        if top_n / total >= 0.80:
            continue
        scattered.append((code, fndds_descs.get(code, ""), total, paths.most_common(3)))

    if scattered:
        scattered.sort(key=lambda x: -x[2])
        msg = [f"Invariant 24 violated: {len(scattered):,} FNDDS codes scatter across multiple family+type prefixes."]
        for code, desc, total, top3 in scattered[:20]:
            msg.append(f"\n  fndds={code} ({desc[:50]!r}, {total} SKUs)")
            for p, n in top3:
                msg.append(f"    [{n} = {n/total:.0%}]  {p}")
        import pytest
        pytest.fail("\n".join(msg))
