#!/usr/bin/env python3
"""Coverage regression detector.

Run after build_concept_resolution.py / build_recipe_concept_grams.py changes
to verify recipe-level calculability hasn't dropped from baseline.

Baseline lives in tests/coverage_baseline.json. Tolerance is 1% by default —
change there if intentional. This test catches the class of bug where an
encoder rule change shifts concept_keys to ones that don't have priced
pools, dropping coverage silently.

Run:
    python3 tests/test_planner_coverage.py

Exits 0 on pass, non-zero on coverage drop > tolerance. Suitable for
pre-build / pre-commit gate. PRINT-only; doesn't mutate state.

Reading order to investigate failures:
  1. Compare current top NO_MATCH concept_keys to those in baseline
  2. Run picked_recipe_audit.py to see which recipes lost matches
  3. Roll back the most-recent encoder/registry change and re-test
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "planner" / "data" / "concept_resolution.json"
RCG = ROOT / "planner" / "data" / "recipe_concept_grams.json"
BASELINE = Path(__file__).parent / "coverage_baseline.json"


def measure_current() -> dict:
    """Compute current calculability metrics from on-disk artifacts."""
    res = json.loads(RES.read_text())
    rcg = json.loads(RCG.read_text())["concept_grams"]
    no_match = {k for k, v in res.items()
                if v.get("tier") in ("no_match", "NO_MATCH")}
    total = len(rcg)
    fully = sum(
        1 for _rid, ings in rcg.items()
        if not (any(k in no_match for k in ings)
                or any(k not in res for k in ings))
    )
    return {
        "recipes_total": total,
        "recipes_fully_calculable": fully,
        "calculable_pct": round(100.0 * fully / max(total, 1), 2),
        "concept_keys_total": len(res),
        "concept_keys_no_match": len(no_match),
        "no_match_pct": round(100.0 * len(no_match) / max(len(res), 1), 2),
    }


def main() -> int:
    if not BASELINE.exists():
        print(f"ERROR: baseline not found at {BASELINE}")
        return 2
    baseline = json.loads(BASELINE.read_text())
    current = measure_current()
    tol = baseline.get("tolerance_pct", 1.0)

    print(f"=== test_planner_coverage ===")
    print(f"  baseline ({baseline.get('version','?')} @ {baseline.get('date','?')}):")
    print(f"    calculable: {baseline['calculable_pct']:.2f}% "
          f"({baseline['recipes_fully_calculable']:,} / {baseline['recipes_total']:,})")
    print(f"    NO_MATCH concept_keys: {baseline['concept_keys_no_match']} "
          f"({baseline['no_match_pct']:.2f}%)")
    print(f"  current:")
    print(f"    calculable: {current['calculable_pct']:.2f}% "
          f"({current['recipes_fully_calculable']:,} / {current['recipes_total']:,})")
    print(f"    NO_MATCH concept_keys: {current['concept_keys_no_match']} "
          f"({current['no_match_pct']:.2f}%)")

    failures = []
    drift_calc = current["calculable_pct"] - baseline["calculable_pct"]
    drift_nm = current["no_match_pct"] - baseline["no_match_pct"]
    print(f"  drift: calculable {drift_calc:+.2f}pp, no_match {drift_nm:+.2f}pp "
          f"(tolerance ±{tol}pp)")

    if drift_calc < -tol:
        failures.append(
            f"calculability dropped {abs(drift_calc):.2f}pp "
            f"(baseline {baseline['calculable_pct']:.2f}% → "
            f"current {current['calculable_pct']:.2f}%); "
            f"tolerance is {tol}pp")
    if drift_nm > tol * 5:  # NO_MATCH count is more volatile than calculability; allow 5x tolerance
        failures.append(
            f"NO_MATCH concept_keys grew {drift_nm:.2f}pp; tolerance is {tol*5}pp")

    if failures:
        print(f"\nFAILURES:")
        for f_ in failures: print(f"  {f_}")
        print(f"\nNext steps to investigate:")
        print(f"  1. python3 recipe_pricing/picked_recipe_audit.py")
        print(f"  2. Compare top NO_MATCH concept_keys to baseline's "
              f"(check git diff on planner/data/concept_resolution.json)")
        print(f"  3. If a recent encoder/registry change caused this, "
              f"narrow the guard or revert it.")
        return 1

    # Rises beyond tolerance — informational
    if drift_calc > tol:
        print(f"\nINFO: calculability rose {drift_calc:+.2f}pp. "
              f"Verify this isn't from new false-positive substitutions.")
        print(f"  If verified real, update tests/coverage_baseline.json with "
              f"the new numbers.")

    print(f"\n  PASS ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
