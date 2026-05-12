#!/usr/bin/env python3
"""Find ALL structural-duplicate paths systematically.

Detects:
  Pattern A — modifier+base compound segment vs base+modifier hierarchy
    'Dairy > Cheese > Fresh Mozzarella' == 'Dairy > Cheese > Mozzarella > Fresh'
    'Dairy > Yogurt > Greek Yogurt > Whole Milk' == 'Dairy > Yogurt > Greek > Whole'
    'Dairy > Milk > Whole Milk' == 'Dairy > Milk > Whole'  (already fixed earlier)

  Pattern B — same token bag, different structure (within same top-2 family)
    Two paths whose multiset of tokens matches but are arranged differently

Strategy: for each parent (top-2 segments), compute a per-path "token-multiset
signature" excluding the parent tokens themselves. Duplicate groups are paths
that share the same signature.

Output:
  retail_mapper/v2/structural_duplicate_groups.csv
  Console: top-30 highest-impact groups + apply-rules suggested.

Operates read-only — no audit changes here. A separate apply step uses the
output to reroute via canonical_path + retail_leaf_path rewrites.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper/v2")
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "structural_duplicate_groups.csv"

csv.field_size_limit(sys.maxsize)
WORD_RX = re.compile(r"[A-Za-z0-9]+")
STOPWORDS = {"and", "the", "of", "a", "an", "in", "on", "with", "by", "for"}


def tokens_of(seg: str) -> tuple[str, ...]:
    return tuple(sorted(
        w.lower() for w in WORD_RX.findall(seg)
        if w.lower() not in STOPWORDS and len(w) > 1
    ))


def signature(path: str, parent_depth: int = 2) -> tuple:
    """Sorted multiset of meaningful tokens in segments AFTER parent_depth.
    Returns (parent_path, signature_token_tuple).
    """
    segs = path.split(" > ")
    if len(segs) <= parent_depth:
        return tuple(segs), ()
    parent = tuple(segs[:parent_depth])
    bag: list[str] = []
    for s in segs[parent_depth:]:
        bag.extend(tokens_of(s))
    return parent, tuple(sorted(bag))


def main() -> None:
    # Map (parent, signature) -> Counter(canonical_path -> sku_count) for both columns
    sig_to_paths_cp: dict[tuple, Counter] = defaultdict(Counter)
    sig_to_paths_rlp: dict[tuple, Counter] = defaultdict(Counter)

    n_total = 0
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            n_total += 1
            cp = r.get("canonical_path", "") or ""
            rlp = r.get("retail_leaf_path", "") or ""
            if cp:
                sig = signature(cp)
                if sig[1]:  # non-empty signature
                    sig_to_paths_cp[sig][cp] += 1
            if rlp:
                sig = signature(rlp)
                if sig[1]:
                    sig_to_paths_rlp[sig][rlp] += 1

    print(f"  scanned {n_total:,} rows")
    print(f"  distinct (parent, signature) keys [canonical]: {len(sig_to_paths_cp):,}")
    print(f"  distinct (parent, signature) keys [retail]   : {len(sig_to_paths_rlp):,}")

    # Find duplicate groups (signatures with >1 distinct path)
    dup_groups: list[dict] = []

    def collect(d: dict, col_name: str):
        for (parent, sig), pc in d.items():
            if len(pc) < 2: continue
            total = sum(pc.values())
            if total < 5: continue  # ignore tiny noise
            # CANONICAL = most-hierarchical path. Score = (depth, sku_count).
            # Higher depth wins (top-down structure). SKU count is tiebreaker.
            ranked = sorted(
                pc.items(),
                key=lambda kv: (-len(kv[0].split(" > ")), -kv[1])
            )
            canonical, can_count = ranked[0]
            others = pc.copy()
            del others[canonical]
            dup_groups.append({
                "column": col_name,
                "parent": " > ".join(parent),
                "signature": " ".join(sig),
                "n_paths": len(pc),
                "n_skus": total,
                "rerouteable": total - can_count,
                "canonical_path": canonical,
                "canonical_skus": can_count,
                "other_paths": " | ".join(f"{p} [{n}]" for p, n in others.most_common()),
            })

    collect(sig_to_paths_cp, "canonical_path")
    collect(sig_to_paths_rlp, "retail_leaf_path")

    dup_groups.sort(key=lambda g: -g["rerouteable"])

    cols = ["column", "parent", "signature", "n_paths", "n_skus", "rerouteable",
            "canonical_path", "canonical_skus", "other_paths"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(dup_groups)
    print(f"  wrote {OUT.name} ({len(dup_groups):,} duplicate groups)")
    print()
    print("=" * 90)
    print("TOP 30 STRUCTURAL DUPLICATE GROUPS BY REROUTEABLE-SKU COUNT")
    print("=" * 90)
    for g in dup_groups[:30]:
        print(f"  [{g['column']:<17}] parent='{g['parent']}'  signature=({g['signature']})")
        print(f"    canonical : {g['canonical_path']}  [{g['canonical_skus']} SKUs]")
        print(f"    others    : {g['other_paths'][:200]}")
        print(f"    reroute   : {g['rerouteable']} SKUs to canonical")
        print()


if __name__ == "__main__":
    main()
