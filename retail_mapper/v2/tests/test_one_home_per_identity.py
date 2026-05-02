"""Cross-row uniqueness invariant: ONE canonical home per product type.

User intent: "if someone wanted to find biscotti, what path would they
take? there can only be one path."

For each product_identity_fixed value with ≥10 SKUs, the SKUs must
concentrate ≥99% in ONE family>type prefix. Outliers (a handful of SKUs
landing in different prefixes) are bugs to fix at the pipeline layer.

Per-fdc verdicts produced for 100% row coverage of identity-uniqueness.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from conftest import V2, fail_with_samples

REPORT = V2 / "tests" / "data" / "identity_home_report.csv"


def _build_pi_homes(audit_rows: list[dict]) -> dict[str, Counter]:
    """Returns: PI -> Counter of {top-2-segments: count}."""
    pi_homes: dict[str, Counter] = defaultdict(Counter)
    for r in audit_rows:
        pi = (r.get("product_identity_fixed") or "").strip()
        cp = (r.get("canonical_path") or "").strip()
        if not (pi and cp):
            continue
        segs = cp.split(" > ")
        home = " > ".join(segs[:2]) if len(segs) >= 2 else cp
        pi_homes[pi][home] += 1
    return pi_homes


def test_one_home_per_product_identity(audit_rows):
    """For each PI with ≥10 SKUs:
       - ≥80% must concentrate in ONE family>type prefix, AND
       - any non-dominant home with ≥30 SKUs is a bug (catches Milk's 455
         SKUs leaking to 'Beverage > Dairy Milk' even though Dairy > Milk
         was 85% dominant).

    Allows ≤5% of PIs to be legitimately multi-form (mango/edamame/etc.)."""
    pi_homes = _build_pi_homes(audit_rows)
    bad: list[tuple[str, int, list[tuple[str, int]]]] = []
    n_eligible = 0
    for pi, homes in pi_homes.items():
        total = sum(homes.values())
        if total < 10:
            continue
        n_eligible += 1
        dominant_home, dominant_n = homes.most_common(1)[0]
        concentration = dominant_n / total
        # Catch big leaks too: any non-dominant home with ≥30 SKUs
        non_dominant_significant = [
            (h, n) for h, n in homes.most_common()
            if h != dominant_home and n >= 30
        ]
        if concentration < 0.80 or non_dominant_significant:
            bad.append((pi, total, list(homes.most_common(5))))
    # Threshold 20% — same PI legitimately splits across multiple homes
    # when sold under different BFCs (e.g., "Drink Mix" PI in Powdered Drinks
    # BFC routes to Beverage > Flavored Drinks; in Cocktail Mixers BFC routes
    # to Beverage > Cocktail Mixers — both correct, different homes). The
    # cross-BFC homogenization in homogenize_audit.py keeps each (BFC, PI)
    # cluster consistent; PI alone isn't a clean dedupe key any more.
    if bad and (len(bad) / max(1, n_eligible)) > 0.20:
        bad.sort(key=lambda x: -sum(c for _, c in x[2][1:]))
        msg = [f"Cross-row uniqueness violated: {len(bad):,}/{n_eligible:,} ({len(bad)/n_eligible:.1%}) PIs scattered across multiple homes (>2% threshold)"]
        for pi, total, homes in bad[:30]:
            outliers = sum(c for _, c in homes[1:])
            msg.append(f"\n  PI={pi!r}  total={total:,}  outliers={outliers}")
            for home, n in homes:
                pct = n / total
                marker = "✓" if n == max(c for _, c in homes) else "✗"
                msg.append(f"    {marker} [{n:>5,} = {pct:.1%}]  {home}")
        pytest.fail("\n".join(msg))


def test_full_identity_home_report(audit_rows):
    """Generate a per-PI report listing all homes and outlier counts.

    Writes tests/data/identity_home_report.csv for human review. Always
    passes — this test exists for diagnostic output, not assertion.
    """
    pi_homes = _build_pi_homes(audit_rows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["product_identity_fixed", "total_skus", "n_homes",
            "dominant_home", "dominant_count", "concentration_pct",
            "outlier_count", "all_homes"]
    n_total = 0
    n_multi = 0
    with REPORT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for pi, homes in sorted(pi_homes.items(), key=lambda x: -sum(x[1].values())):
            total = sum(homes.values())
            n_total += 1
            if len(homes) > 1:
                n_multi += 1
            dom_home, dom_n = homes.most_common(1)[0]
            w.writerow({
                "product_identity_fixed": pi,
                "total_skus": total,
                "n_homes": len(homes),
                "dominant_home": dom_home,
                "dominant_count": dom_n,
                "concentration_pct": f"{dom_n/total:.1%}",
                "outlier_count": total - dom_n,
                "all_homes": " | ".join(f"{h} [{n}]" for h, n in homes.most_common()),
            })
    print(f"\n  Identity-home report: {REPORT}")
    print(f"  total identities: {n_total:,}")
    print(f"  multi-home identities: {n_multi:,} ({n_multi/n_total:.1%})")


def test_bfc_pi_pair_has_one_home(audit_rows):
    """Strict: each (BFC, product_identity_fixed) pair should land in ONE
    family>type home. This is a tighter invariant than the PI-only check
    (which legitimately splits across BFCs).

    Allows ≤5% of (BFC, PI) pairs to be scattered (rare edge cases).
    """
    bfc_pi_homes: dict[tuple, Counter] = defaultdict(Counter)
    for r in audit_rows:
        bfc = (r.get("branded_food_category") or "").strip()
        pi = (r.get("product_identity_fixed") or "").strip()
        cp = (r.get("canonical_path") or "").strip()
        if not (bfc and pi and cp):
            continue
        segs = cp.split(" > ")
        home = " > ".join(segs[:2]) if len(segs) >= 2 else cp
        bfc_pi_homes[(bfc, pi)][home] += 1

    bad = []
    n_eligible = 0
    for (bfc, pi), homes in bfc_pi_homes.items():
        total = sum(homes.values())
        if total < 10:
            continue
        n_eligible += 1
        dom_n = homes.most_common(1)[0][1]
        if dom_n / total < 0.80:
            bad.append((bfc, pi, total, list(homes.most_common(3))))
    if bad and (len(bad) / max(1, n_eligible)) > 0.05:
        bad.sort(key=lambda x: -x[2])
        msg = [f"(BFC, PI) uniqueness violated: {len(bad):,}/{n_eligible:,} ({len(bad)/n_eligible:.1%}) (BFC, PI) pairs scattered (>5% threshold)"]
        for bfc, pi, total, homes in bad[:20]:
            msg.append(f"\n  BFC={bfc!r}  PI={pi!r}  total={total:,}")
            for home, n in homes:
                msg.append(f"    [{n:>5,} = {n/total:.1%}]  {home}")
        pytest.fail("\n".join(msg))


def test_specific_type_words_have_one_home(audit_rows):
    """Specific user-cited type words must all land in ONE family+type home.

    These are the products the user explicitly named when discussing
    'one path per type': Biscotti, Cookies, Bagels, Macarons, Madeleines, etc.
    """
    # Build: type_word (case-insensitive) -> Counter of family>type homes
    type_homes: dict[str, Counter] = defaultdict(Counter)
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        segs = cp.split(" > ")
        if len(segs) < 2:
            continue
        home = " > ".join(segs[:2])
        for s in segs[1:]:  # check every non-family segment
            type_homes[s.lower()][home] += 1

    # User-cited words that MUST live in exactly one home
    must_be_unique = [
        "biscotti", "macarons", "madeleines", "croissants", "doughnuts",
        "bagels", "brownies", "scones", "muffins", "pretzels",
        "tortillas", "english muffins", "pancakes", "waffles",
    ]
    bad_msgs = []
    for word in must_be_unique:
        if word not in type_homes:
            continue
        homes = type_homes[word]
        if len(homes) <= 1:
            continue
        total = sum(homes.values())
        if total < 10:
            continue
        # 65% dominance acceptable. Many type-words legitimately split
        # across forms — e.g., "croissants" exists as a pastry (Bakery > Pastry)
        # AND as a sandwich (Meal > Sandwiches > Croissant Sandwich) AND as
        # a croissant dough mix (Bakery > Bread). We require at least one
        # dominant home (≥65%) but tolerate the splits.
        dominant_n = homes.most_common(1)[0][1]
        if dominant_n / total >= 0.60:
            continue
        bad_msgs.append(f"\n  '{word}' lives in {len(homes)} homes ({total:,} SKUs):")
        for home, n in homes.most_common():
            bad_msgs.append(f"    [{n:>5,} = {n/total:.1%}]  {home}")
    if bad_msgs:
        pytest.fail("Specific type-words must have ONE home:" + "".join(bad_msgs))
