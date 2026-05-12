#!/usr/bin/env python3
"""Apply canonical_path merges directly to consensus_full_corpus_audit.csv.

Reads the path-rewrites CSV and rewrites every row in the FDC audit whose
canonical_path matches an `old_canonical_path`. Writes a sibling backup
(.csv.before-merges) the first time it runs, then overwrites the audit
in place.

After this runs:
  - consensus_full_corpus_audit.csv has fewer distinct canonical_paths
  - duplicate / wrong-parent paths are gone from the curated universe
  - cleanup_llm_output.py fuzzy-matches against the cleaner tree → no
    more "Dairy > Cheese > Butter" type strays for the matcher to grab.

Run order after this:
  1. retail_mapper/v2/apply_canonical_path_merges.py
  2. recipe_mapper/v1/htc/build_food_slot_registry.py   (registry refresh)
  3. recipe_mapper/v1/tag_consensus_with_htc.py         (retag retail)
  4. recipe_pricing/cleanup_llm_output.py               (re-encode LLM outputs)
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT = ROOT / "retail_mapper" / "v2" / "consensus_full_corpus_audit.csv"
DEFAULT_MERGES = ROOT / "recipe_pricing" / "walmart_kroger_path_rewrites.csv"


def load_merges(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    merges: dict[str, str] = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            old = (row.get("old_canonical_path") or "").strip()
            new = (row.get("new_canonical_path") or "").strip()
            if old and new and old != new:
                merges[old] = new
    return merges


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--merges", type=Path, default=DEFAULT_MERGES)
    ap.add_argument("--snapshot-suffix", default=".before-merges")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report stats only, don't rewrite the audit.")
    args = ap.parse_args()

    print(f"loading merges from {args.merges} ...", file=sys.stderr)
    merges = load_merges(args.merges)
    print(f"  {len(merges):,} merge rules", file=sys.stderr)
    if not merges:
        print("no merges to apply, exiting", file=sys.stderr)
        return 0

    # Resolve transitive merges so old → mid → new collapses cleanly to old → new
    # without leaving a row at mid.
    def resolve(p: str, depth: int = 0) -> str:
        if depth > 8 or p not in merges:
            return p
        return resolve(merges[p], depth + 1)
    merges_resolved = {old: resolve(new) for old, new in merges.items()}

    # First pass: count what would change
    print(f"reading audit ({args.audit}) ...", file=sys.stderr)
    rows: list[dict] = []
    n_total = 0
    n_changed = 0
    paths_before: set[str] = set()
    rewrite_counts: Counter = Counter()
    with args.audit.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            n_total += 1
            cp = (row.get("canonical_path") or "").strip()
            paths_before.add(cp)
            if cp in merges_resolved:
                new_cp = merges_resolved[cp]
                row["canonical_path"] = new_cp
                rewrite_counts[(cp, new_cp)] += 1
                n_changed += 1
            rows.append(row)

    paths_after = {(row.get("canonical_path") or "").strip() for row in rows}

    print(f"\n  rows scanned:          {n_total:,}")
    print(f"  rows rewritten:        {n_changed:,}")
    print(f"  distinct paths before: {len(paths_before):,}")
    print(f"  distinct paths after:  {len(paths_after):,}")
    print(f"  paths eliminated:      {len(paths_before) - len(paths_after):,}")
    print(f"\n  top 10 merges by row count:")
    for (old, new), n in rewrite_counts.most_common(10):
        print(f"    {n:>5}  {old}  ->  {new}")

    if args.dry_run:
        print("\n(dry-run, audit unchanged)")
        return 0

    # Snapshot original first time
    backup = args.audit.with_suffix(args.audit.suffix + args.snapshot_suffix)
    if not backup.exists():
        print(f"\n  snapshotting original to {backup}", file=sys.stderr)
        shutil.copy2(args.audit, backup)
    else:
        print(f"\n  backup already exists at {backup} (keeping)", file=sys.stderr)

    # Write rewritten audit in place
    print(f"  rewriting {args.audit} in place ...", file=sys.stderr)
    with args.audit.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  done. {n_changed:,} rows updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
