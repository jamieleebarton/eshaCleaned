#!/usr/bin/env python3
"""Audit priced_products: for each unique product_identity_fixed
(consensus_pid), show where its products are filed across consensus_canonical
paths.

If a pid appears at multiple paths, that's bridge inconsistency. The right
fix is path consolidation — pick the dominant or correct path for that pid,
remap the others.

Output:
  recipe_pricing/pid_path_distribution.csv
    one row per (consensus_pid, consensus_canonical, n_products)
    sorted: pids with more spread first

  recipe_pricing/pid_path_consolidation.csv
    suggested fixes — for pids with multiple paths, the dominant path
    becomes the canonical and the minorities can be remapped

Useful for:
  1. Generating canonical_path remappings to clean priced_products
  2. Building a better buy_form_to_canonical_path lookup (pick the
     dominant pid path)
  3. Surfacing bridge errors
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT_DIST = ROOT / "recipe_pricing" / "pid_path_distribution.csv"
OUT_CONSOL = ROOT / "recipe_pricing" / "pid_path_consolidation.csv"


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute("""
        SELECT consensus_pid, consensus_canonical, COUNT(*)
        FROM priced_products
        WHERE available = 1 AND grams > 0 AND cents > 0
          AND consensus_pid IS NOT NULL AND consensus_pid != ''
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
        GROUP BY consensus_pid, consensus_canonical
    """)
    rows = cur.fetchall()
    pid_to_paths: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for pid, cp, n in rows:
        pid_to_paths[pid].append((cp, n))

    # Output 1: full distribution sorted
    print(f"writing distribution ({len(rows):,} pid×path pairs)...", file=sys.stderr)
    with OUT_DIST.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "consensus_pid", "consensus_canonical", "n_products",
            "total_pid_products", "share",
        ])
        w.writeheader()
        # Sort: pids with more paths first (most-fragmented), then by total
        pid_totals = {pid: sum(n for _, n in pl) for pid, pl in pid_to_paths.items()}
        sorted_pids = sorted(pid_to_paths.keys(),
                             key=lambda p: (-len(pid_to_paths[p]), -pid_totals[p]))
        for pid in sorted_pids:
            total = pid_totals[pid]
            for cp, n in sorted(pid_to_paths[pid], key=lambda x: -x[1]):
                w.writerow({
                    "consensus_pid": pid,
                    "consensus_canonical": cp,
                    "n_products": n,
                    "total_pid_products": total,
                    "share": f"{n/total:.0%}",
                })

    # Output 2: consolidation suggestions for pids with multiple paths
    print(f"writing consolidation suggestions...", file=sys.stderr)
    consolidations = []
    for pid, paths in pid_to_paths.items():
        if len(paths) < 2:
            continue
        paths_sorted = sorted(paths, key=lambda x: -x[1])
        dominant_cp, dominant_n = paths_sorted[0]
        total = sum(n for _, n in paths)
        for cp, n in paths_sorted[1:]:
            consolidations.append({
                "consensus_pid": pid,
                "minority_path": cp,
                "minority_n": n,
                "minority_share": f"{n/total:.0%}",
                "dominant_path": dominant_cp,
                "dominant_n": dominant_n,
                "dominant_share": f"{dominant_n/total:.0%}",
                "total_products": total,
            })
    consolidations.sort(key=lambda r: -r["minority_n"])
    with OUT_CONSOL.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "consensus_pid", "minority_path", "minority_n", "minority_share",
            "dominant_path", "dominant_n", "dominant_share", "total_products",
        ])
        w.writeheader()
        w.writerows(consolidations)

    # Summary stats
    n_pids = len(pid_to_paths)
    n_pids_clean = sum(1 for paths in pid_to_paths.values() if len(paths) == 1)
    n_pids_split = n_pids - n_pids_clean
    print(f"\nunique pids: {n_pids:,}", file=sys.stderr)
    print(f"  filed at exactly 1 path:  {n_pids_clean:,}  ({n_pids_clean/n_pids:.1%})", file=sys.stderr)
    print(f"  split across multiple:    {n_pids_split:,}  ({n_pids_split/n_pids:.1%})", file=sys.stderr)
    print(f"  total minority products:  {sum(c['minority_n'] for c in consolidations):,}", file=sys.stderr)

    # Top 30 most-fragmented pids
    print(f"\n=== TOP 20 MOST-FRAGMENTED PIDS (split across paths) ===", file=sys.stderr)
    for pid in sorted_pids[:20]:
        paths = pid_to_paths[pid]
        if len(paths) < 2:
            continue
        total = pid_totals[pid]
        ps = sorted(paths, key=lambda x: -x[1])
        print(f"  pid={pid!r:<30} total={total:<5} paths={len(paths)}", file=sys.stderr)
        for cp, n in ps[:4]:
            print(f"     [{n:>3}] {cp[:80]}", file=sys.stderr)

    print(f"\n  → {OUT_DIST}", file=sys.stderr)
    print(f"  → {OUT_CONSOL}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
