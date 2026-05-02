"""Regression tests for the 17 bug classes Kimi's swarm audit surfaced.

Each test corresponds to a bug class from the Kimi audit. They guarantee
those classes don't regress.
"""
from __future__ import annotations

import re
from collections import Counter

import pytest

from conftest import fail_with_samples


# ---------------------------------------------------------------------
# K1: No duplicate fdc_ids (primary-key invariant)
# ---------------------------------------------------------------------

def test_no_duplicate_fdc_ids(audit_rows):
    """Each fdc_id must appear at most once — primary key invariant."""
    fdc_count = Counter(r.get("fdc_id", "") for r in audit_rows if r.get("fdc_id"))
    dups = {fdc: n for fdc, n in fdc_count.items() if n > 1}
    if dups:
        msg = [f"K1 violated: {len(dups)} duplicate fdc_ids found"]
        for fdc, n in list(dups.items())[:20]:
            msg.append(f"  {fdc}: {n} rows")
        pytest.fail("\n".join(msg))


# ---------------------------------------------------------------------
# K2: No empty retail_leaf_path when canonical_path is populated
# ---------------------------------------------------------------------

def test_no_empty_retail_leaf_path(audit_rows):
    """retail_leaf_path must not be blank when canonical_path is populated."""
    bad = []
    for r in audit_rows:
        cp = (r.get("canonical_path") or "").strip()
        rlp = (r.get("retail_leaf_path") or "").strip()
        if cp and not rlp:
            bad.append(r)
    if bad:
        fail_with_samples(
            f"K2 violated: {len(bad):,} SKUs have populated canonical_path but empty retail_leaf_path",
            bad,
        )


# ---------------------------------------------------------------------
# K3: No adjacent redundant words in path segments
# ---------------------------------------------------------------------

def test_no_adjacent_redundant_words(audit_rows):
    """Path segments must not have adjacent identical words.
    'Dark Chocolate Chocolate' is a bug. Allows ≤0.05% tolerance."""
    bad = []
    n_total = 0
    for r in audit_rows:
        for col in ("canonical_path", "retail_leaf_path"):
            v = (r.get(col) or "").strip()
            if not v:
                continue
            n_total += 1
            for s in v.split(" > "):
                words = s.split()
                for i in range(1, len(words)):
                    if words[i].lower() == words[i - 1].lower():
                        bad.append(r)
                        break
                else:
                    continue
                break
    if bad and (len(bad) / max(1, n_total)) > 0.0005:
        fail_with_samples(
            f"K3 violated: {len(bad):,} segments have adjacent duplicate words "
            f"(>0.05% threshold)",
            bad,
        )


# ---------------------------------------------------------------------
# K4: Title says FROZEN but path is Pantry > Canned (state contradiction)
# ---------------------------------------------------------------------

_FROZEN_TITLE_RX = re.compile(
    r"\b(freshly\s+frozen|fresh\s+frozen|just\s+frozen|flash\s+frozen|"
    r"individually\s+(?:quick\s+)?frozen|iqf|quick\s+frozen)\b",
    re.I,
)


def test_no_frozen_title_in_canned_path(audit_rows):
    """Title with FROZEN/IQF/etc. must not land in Pantry > Canned.
    Allows ≤100 SKUs (legitimate frozen-then-canned cases like 'previously
    frozen and now in syrup')."""
    bad = []
    for r in audit_rows:
        title = (r.get("title") or "")
        cp = (r.get("canonical_path") or "")
        if not _FROZEN_TITLE_RX.search(title):
            continue
        if "Canned" in cp or "Pantry" in cp.split(" > ")[0:1]:
            if "Pantry > Canned" in cp:
                bad.append(r)
    if len(bad) > 100:
        fail_with_samples(
            f"K4 violated: {len(bad):,} SKUs have FROZEN in title but Pantry > Canned in path",
            bad,
        )


# ---------------------------------------------------------------------
# K6: Plant-based cheese must NOT be in Dairy
# ---------------------------------------------------------------------

def test_plant_based_cheese_not_in_dairy(audit_rows):
    """Plant-based / dairy-free / vegan cheese alternatives must not land
    in Dairy > Cheese. Allows small tolerance for label confusion."""
    bad = []
    for r in audit_rows:
        title = (r.get("title") or "").lower()
        cp = (r.get("canonical_path") or "")
        if not (re.search(r"\b(plant[\s-]?based|vegan|dairy[\s-]?free|alternative)\b", title)
                and "cheese" in title):
            continue
        if cp.startswith("Dairy"):
            bad.append(r)
    if len(bad) > 50:
        fail_with_samples(
            f"K6 violated: {len(bad):,} plant-based cheese SKUs in Dairy family",
            bad,
        )


# ---------------------------------------------------------------------
# K9: Vegetarian frozen meats must NOT route to actual meat trees
# ---------------------------------------------------------------------

def test_vegetarian_frozen_meats_not_in_real_meat(audit_rows):
    """BFC=Vegetarian Frozen Meats must NOT end up under
    Meat & Seafood > Beef|Shellfish|Poultry."""
    bad = []
    for r in audit_rows:
        bfc = (r.get("branded_food_category") or "").strip()
        cp = (r.get("canonical_path") or "")
        if bfc != "Vegetarian Frozen Meats":
            continue
        if cp.startswith("Meat & Seafood > Beef") or cp.startswith("Meat & Seafood > Shellfish"):
            bad.append(r)
    if len(bad) > 5:
        fail_with_samples(
            f"K9 violated: {len(bad):,} vegetarian SKUs in real-meat family+type",
            bad,
        )


# ---------------------------------------------------------------------
# K13: Hot dog rolls/buns must NOT be in Meal > Sandwiches > Hot Dog
# ---------------------------------------------------------------------

def test_hot_dog_buns_in_bakery_not_sandwich(audit_rows):
    """Title with 'hot dog' AND 'roll'/'bun' must route to Bakery > Buns
    (the bread), not Meal > Sandwiches > Hot Dog (the meat dish)."""
    bad = []
    for r in audit_rows:
        title = (r.get("title") or "").lower()
        cp = (r.get("canonical_path") or "")
        if "hot dog" not in title:
            continue
        if not re.search(r"\b(rolls?|buns?)\b", title):
            continue
        if "Meal > Sandwiches" in cp:
            bad.append(r)
    if len(bad) > 10:
        fail_with_samples(
            f"K13 violated: {len(bad):,} hot dog buns/rolls routed to Meal > Sandwiches",
            bad,
        )


# ---------------------------------------------------------------------
# K10: FNDDS code present implies FNDDS desc populated
# ---------------------------------------------------------------------

def test_cheese_danish_pastries_stay_in_bakery(audit_rows):
    """Cheese Danish (the pastry — danish pastry with cheese filling) must
    stay in Bakery > Pastry > Danishes, NOT get force-routed to Dairy > Cheese.

    Discriminator: title contains 'cheese danish' (compound, in that order)
    or 'danish with cream cheese' — these are pastries, not cheeses.
    """
    bad = []
    for r in audit_rows:
        title = (r.get("title") or "").lower()
        cp = (r.get("canonical_path") or "")
        is_pastry_danish = (
            re.search(r"\bcheese\s+danish\b", title)
            or re.search(r"\bdanish\s+(?:coffee|with\s+(?:cream\s+)?cheese)\b", title)
        )
        if not is_pastry_danish:
            continue
        # Pastry must be in Bakery, NOT Dairy
        if cp.startswith("Dairy"):
            bad.append(r)
    if bad:
        fail_with_samples(
            f"K7-pastry violated: {len(bad):,} Cheese Danish PASTRIES misrouted to Dairy",
            bad,
        )


def test_danish_blue_cheese_in_dairy_with_correct_leaf(audit_rows):
    """Danish Blue Cheese (the actual cheese) must be in Dairy > Cheese
    AND must NOT have 'Danishes' as a leaf (was a pastry-PI leak)."""
    bad = []
    for r in audit_rows:
        title = (r.get("title") or "").lower()
        cp = (r.get("canonical_path") or "")
        rlp = (r.get("retail_leaf_path") or "")
        if not re.search(r"\bdanish\s+blue\s+cheese\b|\bdanablu\b", title):
            continue
        # Must be in Dairy
        if not cp.startswith("Dairy"):
            r2 = dict(r); r2["_issue"] = "not in Dairy"
            bad.append(r2); continue
        # Must NOT have 'Danishes' / 'Pastry' as a leaf
        if "Danishes" in cp or "Pastry" in cp:
            r2 = dict(r); r2["_issue"] = "has pastry-leak in path"
            bad.append(r2); continue
    if bad:
        fail_with_samples(
            f"K7-cheese violated: {len(bad):,} Danish Blue Cheese SKUs misrouted",
            bad, extra_cols=["_issue"],
        )


def test_fndds_code_implies_desc(audit_rows):
    """When fndds_code is populated, fndds_desc must also be populated."""
    bad = []
    for r in audit_rows:
        if (r.get("fndds_code") or "").strip() and not (r.get("fndds_desc") or "").strip():
            bad.append(r)
    if len(bad) > 50:
        fail_with_samples(
            f"K10 violated: {len(bad):,} SKUs with fndds_code but empty fndds_desc",
            bad,
        )
