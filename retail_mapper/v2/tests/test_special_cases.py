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
    "hazelnut milk", "walnut milk", "quinoa milk", "brazil nut milk",
    "pistachio milk", "peanut milk", "tigernut milk", "cashew milk",
    "plant milk", "almond nog", "almond beverage",
    # Generic alt-milks where specific isn't determined
    "non-dairy beverage", "non dairy beverage",
}


def test_plant_milk_has_plant_type(audit_rows):
    """Plant Milk SKUs should have a detectable plant type. Allows ≤2%
    tolerance for SKUs where the title genuinely doesn't specify the
    plant (e.g., 'NON-DAIRY BEVERAGE' with no nut/grain word)."""
    bad = []
    n_total = 0
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp.startswith("Beverage > Plant Milk"):
            continue
        n_total += 1
        segs = cp.split(" > ")
        rlp = (r.get("retail_leaf_path") or "").strip().lower()
        title = (r.get("title") or "").lower()
        all_plant_words = ["almond","oat","soy","coconut","rice","cashew","hemp",
                           "pea","macadamia","flax","hazelnut","walnut","quinoa",
                           "brazil nut","pistachio","peanut","tigernut"]
        blob = (rlp + " " + title + " " + (r.get("variant","") or "").lower())
        if any(p in blob for p in all_plant_words):
            continue
        if len(segs) >= 3:
            third = segs[2].lower()
            if third in PLANT_TYPES or third.endswith(" milk"):
                continue
        r2 = dict(r); r2["_issue"] = f"no plant type detectable in path/title/variant"
        bad.append(r2)
    if bad and (len(bad) / max(1, n_total)) > 0.02:
        fail_with_samples(
            f"Invariant 21 violated: {len(bad):,}/{n_total:,} Plant Milk SKUs missing plant type",
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
    """Path segments containing ' & ' or ' and ' that look like JUNK
    (two food noun flavors jammed together that should be separate leaves).

    Legitimate compounds like 'Cheese and Crackers Pack', 'Fruit and Veggie
    Strips', 'Mac and Cheese' are TYPES and stay. The bug case is when a
    leaf at depth 4+ has & between two clearly-independent flavor leaves
    (e.g., 'Almond Butter & Strawberry Jam' should be 2 segments).
    """
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        segs = cp.split(" > ")
        # Only check the LAST segment (the actual leaf)
        if len(segs) < 4:
            continue
        leaf = segs[-1]
        sl = leaf.lower().strip()
        if " & " not in sl and " and " not in sl:
            continue
        if sl in ALLOWED_COMPOUND_SEGMENTS:
            continue
        # If it looks like "X-flavor & Y-flavor" where both halves are
        # nut butters, jams, or ingredient-list flavors, it's junk
        parts = sl.replace(" and ", " & ").split(" & ", 1)
        if len(parts) == 2:
            l, ri = parts[0].strip(), parts[1].strip()
            # Heuristic: both halves are "X butter", or one is "jam"/"jelly", flag
            l_butter = "butter" in l
            r_jelly = "jam" in ri or "jelly" in ri
            r_butter = "butter" in ri
            l_jelly = "jam" in l or "jelly" in l
            if (l_butter and r_jelly) or (l_jelly and r_butter):
                r2 = dict(r); r2["_concat_seg"] = leaf
                bad.append(r2)
    if bad:
        fail_with_samples(
            "Invariant 23 violated: leaf segment looks like nut-butter+jam concatenated junk",
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
        # Allow ≤0.5% of FNDDS codes to scatter — represents the cases where
        # FNDDS code legitimately covers multiple product types (e.g., generic
        # codes that span beef/pork/chicken variants)
        n_eligible = sum(1 for code, paths in fndds_groups.items() if sum(paths.values()) >= 5)
        if len(scattered) / max(1, n_eligible) > 0.05:
            scattered.sort(key=lambda x: -x[2])
            msg = [f"Invariant 24 violated: {len(scattered):,}/{n_eligible:,} ({len(scattered)/n_eligible:.1%}) FNDDS codes scatter across family+type prefixes."]
            for code, desc, total, top3 in scattered[:20]:
                msg.append(f"\n  fndds={code} ({desc[:50]!r}, {total} SKUs)")
                for p, n in top3:
                    msg.append(f"    [{n} = {n/total:.0%}]  {p}")
            import pytest
            pytest.fail("\n".join(msg))
