#!/usr/bin/env python3
"""A5 — FNDDS code agreement audit.

For each line in the FULL_v5 line CSV, we have hestia_fndds (Hestia's
per-recipe FNDDS attribution). We separately look up Hestia's
ingredient_lookup.json:fndds_code (per-ingredient ground truth) by the
ingredient_item / leaf token.

When hestia_fndds disagrees with ingredient_lookup's fndds_code, that's
a Hestia-internal inconsistency in their parser. When our_canonical_path's
HTC family disagrees with Hestia's fndds family (first 2 digits), that's
an OUR-side bridge issue.

Read-only. Outputs:
  recipe_pricing/audit_fndds_agreement.csv — top disagreement patterns
"""
from __future__ import annotations
import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**30)
ROOT = Path(__file__).resolve().parents[1]
LINES = ROOT / "planner" / "data" / "recipe_line_comparison_FULL_v5.csv"
ILU_PATH = Path("/Users/jamiebarton/Desktop/Hestia/api/data/ingredient_lookup.json")
OUT = ROOT / "recipe_pricing" / "audit_fndds_agreement.csv"


def main():
    print("loading ingredient_lookup…", file=sys.stderr)
    ilu = json.loads(ILU_PATH.read_text())
    name_to_fndds: dict[str, str] = {}
    for k, v in ilu.items():
        f = (v.get("fndds_code") or "").strip()
        if f:
            name_to_fndds[k.lower().strip()] = f
    print(f"  {len(name_to_fndds):,} ingredient → fndds mappings", file=sys.stderr)

    # Read FULL_v5 line CSV
    n_total = 0
    n_have_both = 0
    family_match = 0
    family_mismatch = 0
    code_match = 0
    code_mismatch = 0
    pair_counts: Counter = Counter()  # (ing_lookup_fndds, hes_fndds) → n
    samples: dict[tuple, list] = defaultdict(list)

    with LINES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            n_total += 1
            if n_total % 500_000 == 0:
                print(f"  {n_total:,} lines processed", file=sys.stderr)
            hes_fn = (row.get("hestia_fndds") or "").strip()
            if not hes_fn or hes_fn == "0": continue
            # Find ingredient name from the line
            ing_text = (row.get("fndds_desc") or "").strip().lower()
            # Try matching by ingredient_text first (more specific)
            ing_text2 = (row.get("ingredient_text") or "").strip().lower()
            lookup_fn = None
            for candidate in (ing_text, ing_text2):
                if not candidate: continue
                # Exact match
                if candidate in name_to_fndds:
                    lookup_fn = name_to_fndds[candidate]
                    break
                # Try the first noun-like word
                first_word = candidate.split(",")[0].strip()
                if first_word in name_to_fndds:
                    lookup_fn = name_to_fndds[first_word]
                    break
            if not lookup_fn: continue
            n_have_both += 1
            # Compare full code
            if lookup_fn == hes_fn:
                code_match += 1
            else:
                code_mismatch += 1
                key = (lookup_fn, hes_fn)
                pair_counts[key] += 1
                if len(samples[key]) < 3:
                    samples[key].append(f"{row.get('recipe_id','?')}: '{ing_text2[:40]}'")
            # Compare family (first 2 digits)
            if lookup_fn[:2] == hes_fn[:2]:
                family_match += 1
            else:
                family_mismatch += 1

    print(f"\nrows: {n_total:,}", file=sys.stderr)
    print(f"  have both lookup_fn + hes_fn: {n_have_both:,}", file=sys.stderr)
    print(f"  family agreement: {family_match:,}  ({family_match*100/max(1,n_have_both):.1f}%)", file=sys.stderr)
    print(f"  exact-code agreement: {code_match:,}  ({code_match*100/max(1,n_have_both):.1f}%)", file=sys.stderr)
    print(f"  exact-code mismatch: {code_mismatch:,}", file=sys.stderr)

    # Top disagreement patterns
    out_rows = []
    for (lookup_fn, hes_fn), n in pair_counts.most_common(50):
        out_rows.append({
            "ingredient_lookup_fndds": lookup_fn,
            "recipe_attributed_fndds": hes_fn,
            "lookup_family": lookup_fn[:2],
            "attributed_family": hes_fn[:2],
            "same_family": lookup_fn[:2] == hes_fn[:2],
            "n_lines": n,
            "sample": samples[(lookup_fn, hes_fn)][0] if samples[(lookup_fn, hes_fn)] else "",
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            for r in out_rows: w.writerow(r)

    print(f"\n→ {OUT}  ({len(out_rows)} top disagreement patterns)", file=sys.stderr)


if __name__ == "__main__":
    main()
