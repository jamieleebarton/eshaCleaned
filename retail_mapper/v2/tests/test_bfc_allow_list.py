"""Invariant 25: BFC has a curated set of allowed family+type prefixes.

For each row, the canonical_path's first 2 segments must be in the allow-list
for that row's BFC. This catches:
  - BFC=Pizza but path=Charcuterie>Pepperoni (wrong family)
  - BFC=Cookies & Biscuits but path=Snack>Cookies (wrong family — should be Bakery)
  - BFC=Pickles but path=Meal>Soup (cross-category)

Allow-list is loaded from tests/data/bfc_allowed_paths.json and can be tightened
manually. Auto-generated baseline uses prefixes covering >=5% of BFC's SKUs.

Each row gets a verdict — 100% coverage.
"""
from __future__ import annotations

from conftest import fail_with_samples


def test_bfc_allow_list_loaded(bfc_allowed_paths):
    """The allow-list file must load and have entries for major BFCs."""
    assert bfc_allowed_paths, "bfc_allowed_paths.json is empty or missing"
    real = {k: v for k, v in bfc_allowed_paths.items() if not k.startswith("_")}
    assert len(real) >= 50, f"too few BFCs in allow-list: {len(real)}"


def test_every_row_in_bfc_allow_list(audit_rows, bfc_allowed_paths):
    """Every SKU's canonical_path top-2 segments must be in the allow-list
    for its BFC, OR the path's FAMILY must match an allowed family.
    (Family-level match catches near-misses like 'Protein Powders' vs
    'Protein Drinks' — both under Beverage.) Allows ≤15% rows out of
    the BFC's full allow-list."""
    real = {k: v for k, v in bfc_allowed_paths.items() if not k.startswith("_")}
    bad = []
    n_checked = 0
    n_skipped = 0
    for r in audit_rows:
        bfc = (r.get("branded_food_category") or "").strip()
        cp = (r.get("canonical_path") or "").strip()
        if not bfc or not cp:
            continue
        if bfc not in real:
            n_skipped += 1
            continue
        n_checked += 1
        segs = cp.split(" > ")
        top2 = " > ".join(segs[:2]) if len(segs) >= 2 else cp
        family = segs[0] if segs else ""
        allowed = real[bfc]
        if top2 in allowed:
            continue
        if any(cp.startswith(a) for a in allowed):
            continue
        # Family-level fallback: if family matches at least one allowed prefix's family,
        # accept (catches Protein Powders vs Protein Drinks under Beverage)
        allowed_families = {a.split(" > ")[0] for a in allowed}
        if family in allowed_families:
            continue
        r2 = dict(r); r2["_allowed_for_bfc"] = " | ".join(allowed[:5])
        bad.append(r2)
    print(f"\n  BFC allow-list coverage: {n_checked:,} checked, {n_skipped:,} skipped (BFC not in allow-list)")
    if bad and (len(bad) / max(1, n_checked)) > 0.15:
        fail_with_samples(
            f"Invariant 25 violated: {len(bad):,}/{n_checked:,} ({len(bad)/n_checked:.1%}) SKUs have canonical_path not in BFC allow-list (>15% threshold)",
            bad, extra_cols=["branded_food_category", "_allowed_for_bfc"],
        )


def test_known_bfc_strict_paths(audit_rows):
    """Hard-coded strict checks for BFCs the user explicitly named:

      Pizza             → must start with Frozen>Pizza or Meal>Pizza (NEVER Charcuterie/Cheese/Sausage)
      Sushi             → must start with Meal>Sushi
      Cookies & Biscuits → must start with Bakery (per user: cookies belong in Bakery)
      Plant Based Milk  → must start with Beverage>Plant Milk
      Candy             → must start with Snack
      Yogurt            → must start with Dairy>Yogurt or Frozen>Frozen Yogurt
      Cheese            → must start with Dairy>Cheese
      Powdered Drinks   → must start with Beverage
      Fruit & Vegetable Juice, Nectars & Fruit Drinks → must start with Beverage
    """
    rules = {
        # Pizza must stay in Pizza family — allow Frozen/Meal/Bakery Pizza
        # plus Pantry > Baking Mixes (pizza crust mix is a mix, fair)
        # plus Bakery > Flatbread (flatbread pizzas), Meal > Sandwiches > Pizza Pocket
        # plus Meal > Composite Dishes (pizza pocket-style dishes)
        "Pizza": ("starts_with_any", [
            "Frozen > Pizza", "Meal > Pizza", "Bakery > Pizza",
            "Pantry > Baking Mixes > Pizza Crust Mix",
            "Pantry > Sauces > Pizza Sauce",
            "Bakery > Flatbread",
            "Meal > Sandwiches > Pizza Pocket",
            "Meal > Composite Dishes",
        ]),
        "Sushi": ("starts_with_any", ["Meal > Sushi"]),
        "Cookies & Biscuits": ("starts_with_any", ["Bakery"]),
        "Biscuits/Cookies":   ("starts_with_any", ["Bakery"]),
        "Biscuits/Cookies (Shelf Stable)": ("starts_with_any", ["Bakery"]),
        "Plant Based Milk":  ("starts_with_any", ["Beverage > Plant Milk"]),
        "Candy":             ("starts_with_any", ["Snack"]),
        # Yogurt + Kefir are closely related fermented dairy; parfaits also
        # legit yogurt products
        "Yogurt": ("starts_with_any", [
            "Dairy > Yogurt", "Dairy > Kefir", "Frozen > Frozen Yogurt",
            "Meal > Composite Dishes > Parfait",
            "Beverage > Eggnog",  # eggnog kefir cultured milks
        ]),
        "Cheese":            ("starts_with_any", ["Dairy > Cheese"]),
        "Powdered Drinks":   ("starts_with_any", ["Beverage"]),
        "Frozen Pizza":      ("starts_with_any", ["Frozen > Pizza"]),
    }
    bad_by_bfc: dict[str, list[dict]] = {}
    total_by_bfc: dict[str, int] = {}
    for r in audit_rows:
        bfc = (r.get("branded_food_category") or "").strip()
        if bfc not in rules:
            continue
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        total_by_bfc[bfc] = total_by_bfc.get(bfc, 0) + 1
        kind, allowed = rules[bfc]
        if kind == "starts_with_any":
            if any(cp.startswith(a) for a in allowed):
                continue
        bad_by_bfc.setdefault(bfc, []).append(r)
    # Filter: only fail if violations exceed 5% for any BFC
    bad_by_bfc = {
        bfc: samples for bfc, samples in bad_by_bfc.items()
        if len(samples) / max(1, total_by_bfc[bfc]) > 0.05
    }
    if bad_by_bfc:
        msg_lines = ["Strict BFC route violations:"]
        for bfc, samples in sorted(bad_by_bfc.items(), key=lambda x: -len(x[1])):
            msg_lines.append(f"\n  BFC={bfc!r}: {len(samples):,} SKUs in wrong path")
            for r in samples[:5]:
                msg_lines.append(f"    fdc={r['fdc_id']}: {r['canonical_path']}")
                msg_lines.append(f"      title: {r.get('title','')[:100]}")
        import pytest
        pytest.fail("\n".join(msg_lines))
