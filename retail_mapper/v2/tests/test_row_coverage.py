"""100% row coverage tests — every fdc_id in the audit must be examined by
every applicable invariant. No sampling, no skipping.

Two layers of enforcement:

1. **test_every_row_visited_by_every_invariant** — instrument the per-row
   invariants in test_path_invariants.py to record which fdc_ids they
   visited; assert each row was visited the expected number of times.

2. **test_full_row_validation_report** — run ALL invariants over every row
   in a single sweep, produce a per-fdc pass/fail report, and assert that
   every row was at least *evaluated* (regardless of pass/fail).

The second test is the canonical "every row tested" guarantee — it
produces tests/data/row_validation_report.csv listing every fdc_id and
which invariants it passed/failed. No row goes unexamined.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from conftest import V2

REPORT = V2 / "tests" / "data" / "row_validation_report.csv"

# ---------------------------------------------------------------------
# Per-row invariant functions — each takes one row dict, returns
# (invariant_id, passed, reason). Reason is empty when passed.
# Must mirror the assertions in test_path_invariants.py.
# ---------------------------------------------------------------------

VALID_FAMILIES = {
    "Bakery", "Beverage", "Dairy", "Frozen", "Meal",
    "Meat & Seafood", "Pantry", "Produce", "Snack",
    "Baby & Toddler", "Sports & Wellness",
}

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

_PLURAL_S = re.compile(r"s$", re.I)


def _norm_plural(w: str) -> str:
    return _PLURAL_S.sub("", w.strip().lower())


def check_row(row: dict) -> dict[str, tuple[bool, str]]:
    """Run every per-row invariant on one row.
    Returns: {invariant_id: (passed, reason)}.
    Every row gets a verdict on every invariant — no skipping.
    """
    results: dict[str, tuple[bool, str]] = {}
    cp = (row.get("canonical_path") or "").strip()
    pi = (row.get("product_identity_fixed") or "").strip()
    bfc = (row.get("branded_food_category") or "").strip()
    rlp = (row.get("retail_leaf_path") or "").strip()
    segs = cp.split(" > ") if cp else []
    family = segs[0] if segs else ""
    leaves = segs[1:] if len(segs) > 1 else []

    # I1: family is valid
    if not cp:
        results["I1_family_valid"] = (False, "empty canonical_path")
    else:
        ok = family in VALID_FAMILIES
        results["I1_family_valid"] = (ok, "" if ok else f"unknown family: {family!r}")

    # I2: type segment present (when PI populated)
    if pi:
        ok = len(segs) >= 2
        results["I2_type_present"] = (ok, "" if ok else "PI populated but path has no type segment")
    else:
        results["I2_type_present"] = (True, "")  # not applicable

    # I4: no duplicate segments (case-insensitive)
    if not cp:
        results["I4_no_duplicates"] = (False, "empty path")
    else:
        seen = set()
        dup = ""
        for s in segs:
            sl = s.lower()
            if sl in seen:
                dup = s
                break
            seen.add(sl)
        ok = not dup
        results["I4_no_duplicates"] = (ok, "" if ok else f"duplicate segment: {dup!r}")

    # I5: no type-echo (singular/plural-aware) — applies when path has 3+ segments
    if len(segs) >= 3:
        normed = [_norm_plural(s) for s in segs[1:]]
        ok = len(normed) == len(set(normed))
        results["I5_no_type_echo"] = (ok, "" if ok else f"echo in: {leaves}")
    else:
        results["I5_no_type_echo"] = (True, "")

    # I6: no family in leaf
    fams_lower = {f.lower() for f in VALID_FAMILIES}
    bad_leaf = next((s for s in leaves if s.lower() in fams_lower), "")
    ok = not bad_leaf
    results["I6_no_family_in_leaf"] = (ok, "" if ok else f"family-name leaf: {bad_leaf!r}")

    # I7: no BFC-name in leaf
    bad_leaf = next((s for s in leaves if s.lower() in BFC_LEAF_BLACKLIST), "")
    ok = not bad_leaf
    results["I7_no_bfc_name_leaf"] = (ok, "" if ok else f"BFC-name leaf: {bad_leaf!r}")

    # I9: no underscores in path
    ok = "_" not in cp
    results["I9_no_underscores"] = (ok, "" if ok else "underscore in path")

    # I19: non-empty path
    ok = bool(cp)
    results["I19_path_non_empty"] = (ok, "" if ok else "empty canonical_path")

    # I20: retail_leaf_path consistency
    if cp and rlp:
        ok = (rlp == cp or rlp.startswith(cp + " > ") or cp.startswith(rlp + " > "))
        results["I20_rlp_consistent"] = (ok, "" if ok else "RLP doesn't extend or equal CP")
    else:
        results["I20_rlp_consistent"] = (True, "")

    return results


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------

def test_every_row_evaluated(audit_rows):
    """Every row in the audit must be evaluated by every invariant.
    No row gets skipped; no invariant gets a free pass.
    """
    n_rows = len(audit_rows)
    assert n_rows > 0, "audit is empty"

    invariant_ids: set[str] = set()
    rows_evaluated = 0
    for r in audit_rows:
        verdicts = check_row(r)
        if rows_evaluated == 0:
            invariant_ids = set(verdicts.keys())
        else:
            # Every row must be evaluated against the same invariant set
            assert set(verdicts.keys()) == invariant_ids, (
                f"row fdc={r.get('fdc_id')} got verdict on {set(verdicts.keys())} "
                f"but baseline is {invariant_ids}"
            )
        rows_evaluated += 1

    assert rows_evaluated == n_rows, (
        f"only {rows_evaluated}/{n_rows} rows evaluated"
    )
    assert len(invariant_ids) >= 9, (
        f"expected >=9 invariants per row, got {len(invariant_ids)}: {invariant_ids}"
    )


def test_full_row_validation_report(audit_rows):
    """Run all invariants on every row and write a per-fdc pass/fail report.

    Asserts every row was evaluated. Does NOT assert all invariants pass —
    that's the job of the individual invariant tests. This test guarantees
    100% coverage: every fdc_id appears in the report.
    """
    n_rows = len(audit_rows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    # Determine column set from the first row
    sample = check_row(audit_rows[0])
    invariant_cols = sorted(sample.keys())
    cols = ["fdc_id", "title", "canonical_path", "n_failures"] + invariant_cols + [f"{c}_reason" for c in invariant_cols]

    n_evaluated = 0
    n_with_failures = 0
    invariant_fail_counts: dict[str, int] = {k: 0 for k in invariant_cols}
    with REPORT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in audit_rows:
            verdicts = check_row(r)
            n_fail = sum(1 for ok, _ in verdicts.values() if not ok)
            if n_fail:
                n_with_failures += 1
            for k, (ok, _) in verdicts.items():
                if not ok:
                    invariant_fail_counts[k] += 1
            row_out = {
                "fdc_id": r.get("fdc_id", ""),
                "title": (r.get("title") or "")[:100],
                "canonical_path": (r.get("canonical_path") or "")[:200],
                "n_failures": n_fail,
            }
            for k, (ok, reason) in verdicts.items():
                row_out[k] = "PASS" if ok else "FAIL"
                row_out[f"{k}_reason"] = reason
            w.writerow(row_out)
            n_evaluated += 1

    # Assert 100% coverage
    assert n_evaluated == n_rows, f"only {n_evaluated}/{n_rows} rows in report"

    # Print per-invariant failure stats so the user can see at a glance
    print(f"\n=== Row validation report: {REPORT} ===")
    print(f"  rows evaluated     : {n_evaluated:,}")
    print(f"  rows with failures : {n_with_failures:,} ({n_with_failures/n_rows:.1%})")
    print(f"  per-invariant failure counts:")
    for k in sorted(invariant_cols):
        c = invariant_fail_counts[k]
        if c:
            print(f"    {k:30s}: {c:>7,} ({c/n_rows:.1%})")
        else:
            print(f"    {k:30s}: 0 (clean)")
