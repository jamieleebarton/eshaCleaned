#!/usr/bin/env python3
"""Fix pid/path inconsistency in priced_products_v2.db.

For products where consensus_canonical's path is MORE SPECIFIC than
consensus_pid (e.g. pid='Cheese' but path='Dairy > Cheese > Mozzarella'),
update pid to match the path leaf (Mozzarella). This brings identity
consistency to the bridge — pid and path agree, and htc_code derived
from path is now in sync.

Updates priced_products_v2.db IN PLACE. Logs every change to a sidecar
CSV so we can roll back if needed.

Outputs:
  recipe_pricing/pid_consolidation_log.csv  — every row updated

After running, re-run:
  recipe_pricing/build_buy_form_lookup.py
  recipe_pricing/calculator_coverage_report.py
to see coverage gain.
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
LOG = ROOT / "recipe_pricing" / "pid_consolidation_log.csv"
BACKUP = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db.before_pid_consolidation"


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")

    # Backup before mutating
    if not BACKUP.exists():
        print(f"backing up to {BACKUP}...", file=sys.stderr)
        shutil.copy(str(DB), str(BACKUP))
    else:
        print(f"backup already exists: {BACKUP}", file=sys.stderr)

    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    # Find rows to update — path is more specific than pid
    print("scanning for pid/path inconsistencies...", file=sys.stderr)
    cur.execute("""
        SELECT rowid, consensus_pid, consensus_canonical, name
        FROM priced_products
        WHERE consensus_pid IS NOT NULL AND consensus_pid != ''
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
          AND available = 1
    """)

    updates: list[tuple[int, str, str, str, str]] = []
    n_total = 0
    n_already_clean = 0
    n_path_specific = 0
    n_pid_not_in_path = 0
    for rowid, pid, cp, name in cur.fetchall():
        n_total += 1
        leaf = cp.split(" > ")[-1]
        path_segments = cp.split(" > ")
        if leaf == pid:
            n_already_clean += 1
        elif pid in path_segments:
            # path is more specific — update pid to leaf
            updates.append((rowid, pid, leaf, cp, name or ""))
            n_path_specific += 1
        else:
            n_pid_not_in_path += 1

    print(f"\nscanned {n_total:,} products", file=sys.stderr)
    print(f"  already clean (pid == leaf):          {n_already_clean:,}", file=sys.stderr)
    print(f"  path more specific than pid:          {n_path_specific:,}  (will update)", file=sys.stderr)
    print(f"  pid not in path (bridge errors):      {n_pid_not_in_path:,}  (skipped — manual review needed)", file=sys.stderr)

    if not updates:
        print("nothing to update", file=sys.stderr)
        return 0

    # Write log + apply updates
    print(f"\napplying {len(updates):,} updates...", file=sys.stderr)
    with LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "rowid", "old_pid", "new_pid", "consensus_canonical", "name",
        ])
        w.writeheader()
        for rowid, old_pid, new_pid, cp, name in updates:
            w.writerow({
                "rowid": rowid, "old_pid": old_pid, "new_pid": new_pid,
                "consensus_canonical": cp, "name": name[:120],
            })
            cur.execute("UPDATE priced_products SET consensus_pid = ? WHERE rowid = ?",
                        (new_pid, rowid))
    con.commit()
    print(f"  done.", file=sys.stderr)
    print(f"  → backup at {BACKUP}", file=sys.stderr)
    print(f"  → change log at {LOG}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
