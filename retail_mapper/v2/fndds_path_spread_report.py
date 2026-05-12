#!/usr/bin/env python3
"""For each FNDDS code, count how many distinct canonical_paths it spans.

Ground truth: SKUs with the same FNDDS code ARE the same food. If they sit
in multiple paths, those paths are duplicates by definition.

Output: retail_mapper/v2/fndds_path_spread.csv
  columns: fndds_code | fndds_desc | n_skus | n_paths | top_path [skus] | other_paths [skus] ...

Console: distribution histogram + worst offenders.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "fndds_path_spread.csv"
FNDDS_DESC = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/data/fndds/MainFoodDesc16.csv")

csv.field_size_limit(sys.maxsize)


def main() -> None:
    # Optional: load FNDDS descriptions if available
    desc_by_code: dict[str, str] = {}
    if FNDDS_DESC.exists():
        with FNDDS_DESC.open(encoding="utf-8") as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and row[0].strip().isdigit():
                    desc_by_code[row[0].strip()] = row[1].strip()
        print(f"  loaded {len(desc_by_code):,} FNDDS descriptions")

    # Group canonical paths by fndds_code
    code_to_paths: dict[str, Counter] = defaultdict(Counter)
    n_total = 0
    n_with_code = 0

    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            n_total += 1
            code = (r.get("fndds_code") or "").strip()
            cp = (r.get("canonical_path") or "").strip()
            if not (code and cp): continue
            n_with_code += 1
            code_to_paths[code][cp] += 1

    print(f"  total rows: {n_total:,}")
    print(f"  rows with fndds_code: {n_with_code:,}")
    print(f"  distinct fndds_codes: {len(code_to_paths):,}")

    # Histogram: # of distinct paths per code
    spread_dist = Counter(len(pc) for pc in code_to_paths.values())
    print()
    print("  distribution of (paths-per-fndds-code):")
    print(f"    paths_per_code | n_codes | cumulative_skus")
    cumulative = 0
    for n_paths in sorted(spread_dist):
        n_codes = spread_dist[n_paths]
        # SKUs in codes with this many paths
        skus = sum(sum(pc.values()) for pc in code_to_paths.values() if len(pc) == n_paths)
        cumulative += skus
        print(f"    {n_paths:>14} | {n_codes:>7,} | {skus:>9,}")

    # Build output rows: one row per FNDDS code with >=2 paths
    out_rows: list[dict] = []
    for code, pc in code_to_paths.items():
        if len(pc) < 2: continue
        total = sum(pc.values())
        ranked = pc.most_common()
        top_path, top_n = ranked[0]
        out_rows.append({
            "fndds_code": code,
            "fndds_desc": desc_by_code.get(code, ""),
            "n_skus": total,
            "n_paths": len(pc),
            "top_path": top_path,
            "top_path_skus": top_n,
            "fragmentation": f"{(total - top_n) / total:.1%}",
            "other_paths": " | ".join(f"{p} [{n}]" for p, n in ranked[1:11]),
        })

    out_rows.sort(key=lambda r: -(r["n_skus"] - r["top_path_skus"]))

    cols = list(out_rows[0].keys()) if out_rows else []
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        if cols:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(out_rows)
    print(f"\n  wrote {OUT.name} ({len(out_rows):,} multi-path FNDDS codes)")

    # Console: top 25 worst offenders
    print()
    print("=" * 90)
    print("TOP 25 FNDDS CODES BY PATH-FRAGMENTATION (most SKUs spread across multiple paths)")
    print("=" * 90)
    for r in out_rows[:25]:
        print(f"  fndds={r['fndds_code']}  desc=\"{r['fndds_desc'][:60]}\"  n_skus={r['n_skus']}  n_paths={r['n_paths']}  frag={r['fragmentation']}")
        print(f"    top   : {r['top_path']} [{r['top_path_skus']}]")
        print(f"    others: {r['other_paths'][:240]}")
        print()


if __name__ == "__main__":
    main()
