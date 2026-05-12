#!/usr/bin/env python3
"""Find pids that are SEMANTIC DUPLICATES of each other in
priced_products_v2.db. The bridge LLM ran per-product and produced
near-identical strings for the same identity:

  'Cornstarch' vs 'Corn Starch'      (whitespace)
  'Bay Leaf'   vs 'Bay Leaves'       (plural)
  'Cilantro'   vs 'Coriander'        (regional synonym)
  'Greek Yogurt' vs 'Greek-Yogurt'   (hyphenation)

Output:
  recipe_pricing/pid_semantic_duplicate_groups.csv
    columns: canonical_pid (the dominant), variant_pid, n_products_variant,
             n_products_canonical, normalized_key, paths

The canonical is the variant with the most products. Variants get remapped
to canonical_pid + canonical's canonical_path in a follow-up consolidation.
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
OUT = ROOT / "recipe_pricing" / "pid_semantic_duplicate_groups.csv"


# Curated cross-language / regional synonym pairs (canonical first)
SYNONYM_PAIRS = [
    ("cilantro",        "coriander"),
    ("scallion",        "green onion"),
    ("scallion",        "spring onion"),
    ("garbanzo bean",   "chickpea"),
    ("zucchini",        "courgette"),
    ("eggplant",        "aubergine"),
    ("arugula",         "rocket"),
    ("ground beef",     "minced beef"),
    ("baking powder",   "baking soda"),  # NO — these are different. Don't add.
    ("powdered sugar",  "confectioners sugar"),
    ("powdered sugar",  "icing sugar"),
    ("brown sugar",     "demerara sugar"),  # close, debatable
]
SYNONYM_PAIRS = [s for s in SYNONYM_PAIRS if s[0] != "baking powder"]


def normalize_pid(pid: str) -> str:
    """Aggressively normalize pid to detect duplicates. Catches:
       - 'Corn Meal' vs 'Cornmeal'      (whitespace)
       - 'Corn Starch' vs 'Cornstarch'
       - 'Bay Leaf' vs 'Bay Leaves'     (plural)
       - 'Cilantro' vs 'Coriander'      (synonym)
    """
    s = pid.lower().strip()
    s = re.sub(r"[-_]+", " ", s)
    s = re.sub(r"[^\w\s]", "", s)
    # CRITICAL: strip ALL whitespace so 'corn meal' == 'cornmeal'
    s_nospace = re.sub(r"\s+", "", s)
    # Singularize: drop trailing 's' but not 'ss'
    if s_nospace.endswith("s") and not s_nospace.endswith("ss") and len(s_nospace) > 3:
        s_nospace = s_nospace[:-1]
    # Apply synonym map (operates on collapsed form)
    for canonical, variant in SYNONYM_PAIRS:
        v = variant.replace(" ", "")
        if s_nospace == v or s_nospace == v + "s":
            return canonical.replace(" ", "")
    return s_nospace


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    print("loading pids...", file=sys.stderr)
    cur.execute("""
        SELECT consensus_pid, consensus_canonical, COUNT(*)
        FROM priced_products
        WHERE consensus_pid IS NOT NULL AND consensus_pid != ''
          AND consensus_canonical IS NOT NULL AND consensus_canonical != ''
          AND available = 1 AND grams > 0 AND cents > 0
        GROUP BY consensus_pid, consensus_canonical
    """)
    rows = cur.fetchall()
    print(f"  {len(rows):,} (pid × path) pairs", file=sys.stderr)

    # Group by normalized key
    groups: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for pid, cp, n in rows:
        key = normalize_pid(pid)
        groups[key].append((pid, cp, n))

    # Only keep groups with multiple distinct pids
    duplicate_groups = []
    for key, members in groups.items():
        distinct_pids = set(p for p, _, _ in members)
        if len(distinct_pids) >= 2:
            # Tally per-pid total
            pid_totals: dict[str, int] = defaultdict(int)
            for pid, _, n in members:
                pid_totals[pid] += n
            # Canonical = pid with most total products
            sorted_pids = sorted(pid_totals.keys(), key=lambda p: -pid_totals[p])
            canonical = sorted_pids[0]
            for variant in sorted_pids[1:]:
                duplicate_groups.append({
                    "canonical_pid": canonical,
                    "variant_pid": variant,
                    "n_products_canonical": pid_totals[canonical],
                    "n_products_variant": pid_totals[variant],
                    "normalized_key": key,
                    "paths": " | ".join(sorted({cp for p, cp, _ in members})),
                })

    # Sort by variant_n descending — fixing high-volume duplicates first matters most
    duplicate_groups.sort(key=lambda r: -r["n_products_variant"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "canonical_pid", "variant_pid", "n_products_variant",
            "n_products_canonical", "normalized_key", "paths",
        ])
        w.writeheader()
        w.writerows(duplicate_groups)

    print(f"\nfound {len(duplicate_groups):,} duplicate (canonical, variant) pairs", file=sys.stderr)
    print(f"total products at variant pids: {sum(r['n_products_variant'] for r in duplicate_groups):,}", file=sys.stderr)
    print(f"\nTop 25 by variant product count (fixes here yield most coverage):", file=sys.stderr)
    for r in duplicate_groups[:25]:
        print(f"  [{r['n_products_variant']:>4}→canon {r['n_products_canonical']:>5}] "
              f"{r['variant_pid']:<28} → {r['canonical_pid']:<28}  ({r['normalized_key']})", file=sys.stderr)
    print(f"\n  → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
