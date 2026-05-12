#!/usr/bin/env python3
"""R12.6 — Freeze priced_products consensus_canonical under a hash file.

Snapshots (upc → consensus_canonical) to canonical_path_freeze.csv. Future
runs of build_concept_index.py compare current SKU placement to the freeze;
any drift logs to canonical_path_drift.csv. Used as a CI signal — silent
LLM re-categorization breaking our fixes is detectable.

Use:
  python3 recipe_pricing/freeze_canonical_paths.py            # snapshot
  python3 recipe_pricing/freeze_canonical_paths.py --check    # drift check
"""
from __future__ import annotations
import argparse, csv, hashlib, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
FREEZE = ROOT / "recipe_pricing" / "canonical_path_freeze.csv"
DRIFT = ROOT / "recipe_pricing" / "canonical_path_drift.csv"


def current_snapshot() -> dict[str, str]:
    out: dict[str, str] = {}
    con = sqlite3.connect(str(DB))
    for upc, cp in con.execute(
        "SELECT upc, consensus_canonical FROM priced_products "
        "WHERE upc IS NOT NULL AND consensus_canonical IS NOT NULL"):
        out[upc] = cp
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare current DB to freeze; non-zero exit on drift")
    args = ap.parse_args()

    if not args.check:
        snap = current_snapshot()
        with FREEZE.open("w", newline="") as f:
            w = csv.writer(f); w.writerow(["upc", "canonical_path"])
            for upc, cp in sorted(snap.items()): w.writerow([upc, cp])
        h = hashlib.sha256(FREEZE.read_bytes()).hexdigest()[:16]
        print(f"snapshotted {len(snap):,} UPCs → {FREEZE.name}  sha={h}",
              file=sys.stderr)
        return

    if not FREEZE.exists():
        print(f"no freeze at {FREEZE}; run without --check first to snapshot",
              file=sys.stderr); sys.exit(1)
    frozen: dict[str, str] = {}
    with FREEZE.open() as f:
        for row in csv.DictReader(f):
            frozen[row["upc"]] = row["canonical_path"]
    current = current_snapshot()

    drift = []
    for upc in set(frozen) | set(current):
        old = frozen.get(upc, "")
        new = current.get(upc, "")
        if old != new:
            drift.append({"upc": upc, "frozen_path": old, "current_path": new})

    if drift:
        with DRIFT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(drift[0].keys()))
            w.writeheader()
            for r in drift: w.writerow(r)
    print(f"drifted UPCs: {len(drift):,}", file=sys.stderr)
    if drift:
        print(f"\nTop 20 drifted:", file=sys.stderr)
        for d in drift[:20]:
            print(f"  {d['upc']:<14} '{d['frozen_path'][:38]}' → '{d['current_path'][:38]}'",
                  file=sys.stderr)
        print(f"\n→ {DRIFT}", file=sys.stderr)
    sys.exit(0 if not drift else 1)


if __name__ == "__main__":
    main()
