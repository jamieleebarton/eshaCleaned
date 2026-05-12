#!/usr/bin/env python3
"""Identify duplicate canonical_paths using existing classification signals.

The thesis: two SKUs with the same FNDDS code (or ESHA code, or branded_food_category)
ARE the same food. If they sit in different canonical_paths, those paths are
duplicates by definition.

For each grouping signal, we:
  1. Bucket SKUs by the signal value
  2. List the distinct canonical_paths each bucket spans
  3. If >1 path → that bucket reveals duplicate paths
  4. Recommend canonical = most-common path; reroute the rest

Output: retail_mapper/v2/duplicates_by_classification.csv
   columns: signal | signal_value | n_skus | n_paths | canonical_path | rerouteable_skus | other_paths
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "duplicates_by_classification.csv"

csv.field_size_limit(sys.maxsize)

SIGNALS = ["fndds_code", "esha_code", "branded_food_category"]

# Minimum cluster size — ignore tiny groupings (likely noise)
MIN_GROUP = 5
# Don't flag groups whose dominant path is >=80% — those are basically uniform
MIN_DUP_FRACTION = 0.20


def main() -> None:
    # group[signal][value] = Counter(canonical_path)
    groups: dict[str, dict[str, Counter]] = {s: defaultdict(Counter) for s in SIGNALS}
    cols_seen: set[str] = set()

    with AUDIT.open(encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        cols_seen = set(rdr.fieldnames or [])
        for r in rdr:
            cp = (r.get("canonical_path") or "").strip()
            if not cp: continue
            for s in SIGNALS:
                v = (r.get(s) or "").strip()
                if not v: continue
                groups[s][v][cp] += 1

    # Verify all signal columns existed
    for s in SIGNALS:
        if s not in cols_seen:
            print(f"  WARNING: column '{s}' not in audit CSV")

    out_rows: list[dict] = []
    print()
    summary = {}
    for sig in SIGNALS:
        n_groups_total = 0
        n_groups_with_dups = 0
        n_skus_in_dup_groups = 0
        n_reroutable_skus = 0
        for value, path_counter in groups[sig].items():
            total = sum(path_counter.values())
            if total < MIN_GROUP:
                continue
            n_groups_total += 1
            if len(path_counter) < 2:
                continue
            # Determine canonical = highest-count path
            canonical, can_count = path_counter.most_common(1)[0]
            non_canonical = total - can_count
            if non_canonical / total < MIN_DUP_FRACTION:
                continue
            n_groups_with_dups += 1
            n_skus_in_dup_groups += total
            n_reroutable_skus += non_canonical
            others = path_counter.copy()
            del others[canonical]
            out_rows.append({
                "signal": sig,
                "signal_value": value,
                "n_skus": total,
                "n_paths": len(path_counter),
                "canonical_path": canonical,
                "canonical_skus": can_count,
                "rerouteable_skus": non_canonical,
                "other_paths_with_counts": " | ".join(f"{p} [{n}]" for p, n in others.most_common()[:6]),
            })
        summary[sig] = (n_groups_total, n_groups_with_dups, n_skus_in_dup_groups, n_reroutable_skus)

    print(f"  signal                    | groups>=5 | with-dups | dup-skus  | rerouteable")
    print(f"  --------------------------+-----------+-----------+-----------+-----------")
    for sig, (g, gd, ds, rr) in summary.items():
        print(f"  {sig:<25} | {g:>9,} | {gd:>9,} | {ds:>9,} | {rr:>9,}")

    out_rows.sort(key=lambda r: -r["rerouteable_skus"])
    cols = ["signal", "signal_value", "n_skus", "n_paths", "canonical_path",
            "canonical_skus", "rerouteable_skus", "other_paths_with_counts"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    print(f"\n  wrote {OUT.name} ({len(out_rows):,} duplicate groups)")

    print()
    print("=" * 90)
    print("TOP 30 DUPLICATE GROUPS BY REROUTEABLE-SKU COUNT")
    print("=" * 90)
    for r in out_rows[:30]:
        print(f"  signal={r['signal']:<22} value={r['signal_value']:<35} "
              f"skus={r['n_skus']} paths={r['n_paths']} reroute={r['rerouteable_skus']}")
        print(f"    canonical : {r['canonical_path']} [{r['canonical_skus']}]")
        print(f"    others    : {r['other_paths_with_counts'][:200]}")


if __name__ == "__main__":
    main()
