#!/usr/bin/env python3
"""Apply the 2,939 structural-duplicate-group reroutes to full_corpus_audit.csv.

For each duplicate group in structural_duplicate_groups.csv, all SKUs
sitting in a non-canonical path get moved to the canonical path. The
column (canonical_path or retail_leaf_path) is determined per-group.

Skips groups where the canonical itself looks suspect (last segment ends
in 'And', 'N', '&' — truncation artifacts like 'Cookies And').
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
GROUPS = V2 / "structural_duplicate_groups.csv"
LOG = V2 / "apply_structural_duplicates_log.csv"

csv.field_size_limit(sys.maxsize)

# Refuse to use a canonical path with these red flags:
SUSPECT_LEAF_RX = re.compile(r"\b(And|N|&|To|For|Of|With|The)$", re.I)


def parse_others(others_str: str) -> list[str]:
    """Parse the 'other_paths' column: 'Path1 [n] | Path2 [n]' -> [Path1, Path2]."""
    out: list[str] = []
    for chunk in others_str.split(" | "):
        if not chunk.strip():
            continue
        # Strip trailing [count]
        m = re.match(r"^(.*?)\s*\[\d+\]\s*$", chunk)
        out.append(m.group(1) if m else chunk.strip())
    return out


def main() -> None:
    # Build per-column rewrite maps: column -> {old_path: new_path}
    rewrite: dict[str, dict[str, str]] = {
        "canonical_path": {},
        "retail_leaf_path": {},
    }
    n_groups_read = 0
    n_groups_skipped = 0
    n_groups_applied = 0

    with GROUPS.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            n_groups_read += 1
            col = r["column"]
            canonical = r["canonical_path"]
            others = parse_others(r["other_paths"])
            if not others:
                continue
            leaf = canonical.split(" > ")[-1]
            if SUSPECT_LEAF_RX.search(leaf):
                n_groups_skipped += 1
                continue
            n_groups_applied += 1
            for other in others:
                # Avoid mapping a path to itself or a longer path back to a prefix
                if other == canonical: continue
                if rewrite[col].get(other) and rewrite[col][other] != canonical:
                    # Conflict: keep the first one (top-impact group wins because
                    # we read groups sorted by rerouteable desc)
                    continue
                rewrite[col][other] = canonical

    print(f"  groups read     : {n_groups_read:,}")
    print(f"  groups applied  : {n_groups_applied:,}")
    print(f"  groups skipped  : {n_groups_skipped:,} (suspect canonical)")
    print(f"  rewrite size    : canonical_path={len(rewrite['canonical_path']):,} "
          f"retail_leaf_path={len(rewrite['retail_leaf_path']):,}")

    # Apply
    tmp = AUDIT.with_suffix(".applying.csv")
    log_rows: list[dict] = []
    n_total = 0
    n_changed_cp = 0
    n_changed_rlp = 0
    with AUDIT.open(encoding="utf-8", newline="") as fin, \
         tmp.open("w", encoding="utf-8", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames)
        wtr.writeheader()
        for row in rdr:
            n_total += 1
            old_cp = row.get("canonical_path", "") or ""
            old_rlp = row.get("retail_leaf_path", "") or ""
            new_cp = rewrite["canonical_path"].get(old_cp, old_cp)
            new_rlp = rewrite["retail_leaf_path"].get(old_rlp, old_rlp)
            cp_changed = new_cp != old_cp
            rlp_changed = new_rlp != old_rlp
            if cp_changed or rlp_changed:
                if cp_changed: n_changed_cp += 1
                if rlp_changed: n_changed_rlp += 1
                row["canonical_path"] = new_cp
                row["retail_leaf_path"] = new_rlp
                log_rows.append({
                    "fdc_id": row.get("fdc_id", ""),
                    "title": (row.get("title", "") or "")[:60],
                    "old_canonical": old_cp,
                    "new_canonical": new_cp,
                    "old_retail_leaf": old_rlp,
                    "new_retail_leaf": new_rlp,
                })
            wtr.writerow(row)

    shutil.move(str(tmp), str(AUDIT))
    print()
    print(f"  total rows        : {n_total:,}")
    print(f"  canonical_path rewrites : {n_changed_cp:,}")
    print(f"  retail_leaf rewrites    : {n_changed_rlp:,}")
    print(f"  rows touched (any column): {len(log_rows):,}")

    if log_rows:
        cols = list(log_rows[0].keys())
        with LOG.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"  wrote {LOG.name}")


if __name__ == "__main__":
    main()
