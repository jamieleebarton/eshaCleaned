#!/usr/bin/env python3
"""For each Branded Food Category (BFC), find where its SKUs are concentrated
in canonical_path. The dominant family root is the "right" home; any SKU
outside that root is mis-routed.

Read-only audit. Writes:
  retail_mapper/v2/bfc_alignment_audit.csv
    For every BFC: dominant root, % concentration, # mis-routed SKUs.

Console: top 30 worst-offender BFCs by mis-routed-SKU count.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "bfc_alignment_audit.csv"

csv.field_size_limit(sys.maxsize)


def main() -> None:
    bfc_to_paths: dict[str, Counter] = defaultdict(Counter)  # BFC → Counter(top-2-segments-of-canonical_path)
    bfc_to_total: dict[str, int] = defaultdict(int)

    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            bfc = (r.get("branded_food_category") or "").strip()
            cp = (r.get("canonical_path") or "").strip()
            if not (bfc and cp): continue
            segs = cp.split(" > ")
            top2 = " > ".join(segs[:2])
            bfc_to_paths[bfc][top2] += 1
            bfc_to_total[bfc] += 1

    rows = []
    for bfc, path_counter in bfc_to_paths.items():
        total = bfc_to_total[bfc]
        if total < 5: continue  # ignore tiny BFCs
        dominant_path, dom_count = path_counter.most_common(1)[0]
        misrouted = total - dom_count
        concentration = dom_count / total
        # List up to 5 minor destinations
        others = path_counter.copy()
        del others[dominant_path]
        rows.append({
            "bfc": bfc,
            "total_skus": total,
            "dominant_family": dominant_path,
            "dominant_count": dom_count,
            "concentration_pct": f"{concentration:.0%}",
            "misrouted_skus": misrouted,
            "top_other_destinations": " | ".join(f"{p} [{n}]" for p, n in others.most_common(5)),
        })

    rows.sort(key=lambda r: -r["misrouted_skus"])

    cols = ["bfc", "total_skus", "dominant_family", "dominant_count",
            "concentration_pct", "misrouted_skus", "top_other_destinations"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"  scanned {sum(bfc_to_total.values()):,} SKUs across {len(bfc_to_total):,} BFCs")
    print(f"  wrote {OUT.name}")
    print()
    print("=" * 100)
    print("TOP 30 WORST-OFFENDER BFCs (most misrouted SKUs)")
    print("=" * 100)
    for r in rows[:30]:
        print(f"\n  BFC='{r['bfc']}'  total_skus={r['total_skus']}  conc={r['concentration_pct']}")
        print(f"    DOMINANT  : {r['dominant_family']} ({r['dominant_count']} SKUs)")
        print(f"    misrouted : {r['misrouted_skus']} SKUs scattered across:")
        for chunk in r['top_other_destinations'].split(" | ")[:5]:
            print(f"      - {chunk}")


if __name__ == "__main__":
    main()
