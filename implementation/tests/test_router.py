"""
Router regression test harness.

Reads tests/router_golden.csv: each row is `surface, min_verdict,
canonical_contains, note`. Runs route() on the surface and verifies:
  1. Verdict tier ≥ min_verdict (EXACT > STRONG > COMPOSITE > WEAK >
     NEEDS_NEW_CONCEPT > NO_MATCH > NO_IDENTITY)
  2. canonical_name (or composite primary canonical) contains the
     case-insensitive substring `canonical_contains`.

Exit nonzero on any failure. Prints PASS/FAIL per row plus a summary.
Use BEFORE and AFTER any router change.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rft_concept import build_concept_index, build_token_to_concepts, route

VERDICT_RANK = {
    "EXACT": 6,
    "STRONG": 5,
    "COMPOSITE": 4,
    "WEAK": 3,
    "NEEDS_NEW_CONCEPT": 2,
    "NO_MATCH": 1,
    "NO_IDENTITY": 0,
}


def main():
    here = Path(__file__).resolve().parent
    golden = here / "router_golden.csv"
    if not golden.exists():
        sys.exit(f"missing golden file: {golden}")

    print("Building concept index…", flush=True)
    concepts = build_concept_index()
    tidx = build_token_to_concepts(concepts)
    print(f"  {len(concepts):,} concepts\n")

    n_pass = 0
    n_fail = 0
    fails: list[dict] = []

    with golden.open() as f:
        for row in csv.DictReader(f):
            surface = row["surface"].strip()
            min_verdict = row["min_verdict"].strip()
            wanted = row["canonical_contains"].strip().lower()
            note = row.get("note", "").strip()

            res = route(surface, concepts, tidx)
            v = res["verdict"]
            c = res.get("concept")
            cname = (c.canonical_name if c else "") or ""
            comp = res.get("composite") or {}
            primary_cname = comp.get("primary_canonical", "") or ""
            cname_check = (cname + " | " + primary_cname).lower()

            verdict_ok = VERDICT_RANK.get(v, -1) >= VERDICT_RANK.get(min_verdict, 99)
            canon_ok = wanted in cname_check if wanted else True
            ok = verdict_ok and canon_ok

            if ok:
                n_pass += 1
                print(f"  PASS  {surface[:50]:50s} → {v:18s} {cname[:45]}")
            else:
                n_fail += 1
                fails.append({
                    "surface": surface,
                    "expected": f"{min_verdict}+ canonical~{wanted!r}",
                    "actual": f"{v} canonical={cname!r}",
                    "note": note,
                })
                print(f"  FAIL  {surface[:50]:50s} → {v:18s} {cname[:45]}"
                      f"  (wanted {min_verdict}+ ~{wanted!r})")

    total = n_pass + n_fail
    print(f"\n{n_pass}/{total} passed  ({n_fail} failed)")
    if fails:
        print("\nFailures:")
        for f in fails:
            print(f"  {f['surface']!r}")
            print(f"    expected: {f['expected']}")
            print(f"    actual:   {f['actual']}")
            if f["note"]:
                print(f"    note:     {f['note']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
