#!/usr/bin/env python3
"""For each canonical_label that's filed at multiple consensus_canonical
paths, move all minority-path products to the dominant path.

This catches:
  Broccoli (Frozen) at both Frozen > Vegetables > Broccoli (135) and
                            Produce > Vegetables > Broccoli (35)
    → all 35 minorities move to Frozen (label says Frozen)

  Cheese (Mozzarella, Shredded) at Dairy > Cheese > Mozzarella (71)
                                AND Dairy > Cheese > Shredded Cheese (64)
    → tighter case; pick the more populous

Outputs:
  recipe_pricing/label_path_consolidation_log.csv  — every change

Backup of priced_products: *.before_label_path_consolidation
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
LOG = ROOT / "recipe_pricing" / "label_path_consolidation_log.csv"


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")

    backup = DB.with_suffix(".db.before_label_path_consolidation")
    if not backup.exists():
        print(f"backup → {backup}", file=sys.stderr)
        shutil.copy(str(DB), str(backup))

    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    # Build label → list of (path, n)
    cur.execute("""
        SELECT canonical_label, consensus_canonical, COUNT(*)
        FROM priced_products
        WHERE canonical_label IS NOT NULL AND canonical_label != ''
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
          AND available = 1 AND grams > 0 AND cents > 0
        GROUP BY canonical_label, consensus_canonical
    """)
    label_paths: defaultdict[str, list[tuple[str, int]]] = defaultdict(list)
    for label, cp, n in cur.fetchall():
        label_paths[label].append((cp, n))

    # For each split label, build the path-remap rule
    remaps: list[dict] = []
    for label, paths in label_paths.items():
        if len(paths) < 2:
            continue
        sorted_paths = sorted(paths, key=lambda x: -x[1])
        dominant_path = sorted_paths[0][0]
        for minority_path, minority_n in sorted_paths[1:]:
            remaps.append({
                "canonical_label": label,
                "minority_path": minority_path,
                "dominant_path": dominant_path,
                "minority_n": minority_n,
            })

    print(f"label-path duplicates to consolidate: {len(remaps):,}", file=sys.stderr)
    print(f"products affected: {sum(r['minority_n'] for r in remaps):,}", file=sys.stderr)

    # Apply
    n_updated = 0
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "canonical_label", "minority_path", "dominant_path",
            "minority_n",
        ])
        w.writeheader()
        for r in remaps:
            cur.execute("""
                UPDATE priced_products
                SET consensus_canonical = ?
                WHERE canonical_label = ?
                  AND consensus_canonical = ?
            """, (r["dominant_path"], r["canonical_label"], r["minority_path"]))
            n_updated += cur.rowcount
            w.writerow(r)
    con.commit()
    print(f"updated {n_updated:,} priced_products rows", file=sys.stderr)
    print(f"  → {LOG}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
