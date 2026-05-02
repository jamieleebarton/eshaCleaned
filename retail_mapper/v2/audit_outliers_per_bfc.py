#!/usr/bin/env python3
"""For each BFC, find outlier paths whose leaf-words have a dominant home
elsewhere in the corpus.

Concept: same leaf words (e.g. "Pina Colada") appear in:
  - Pantry > Baking Mixes > Mix > Pina Colada  (1 SKU = outlier)
  - Beverage > Cocktail Mixers > Cocktail Mix > Pina Colada  (50 SKUs = canonical home)
The 1-SKU path is likely a hijack — same product belongs in the dominant home.

Output: retail_mapper/v2/outlier_paths_report.csv
  Columns: bfc, current_path, current_count, leaf_signature, dominant_path,
           dominant_count, sample_fdcs, sample_titles, severity_ratio

Severity = dominant_count / current_count. Higher = more confident the
current path is wrong.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path(__file__).resolve().parent
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "outlier_paths_report.csv"

csv.field_size_limit(sys.maxsize)


def _leaf_signature(path: str) -> str:
    """Extract the most discriminating leaf words from a path.
    Drops the family + type, returns the rest joined as a sorted tuple key.
    """
    segs = [s.strip() for s in path.split(" > ") if s.strip()]
    if len(segs) <= 2:
        return ""
    leaves = segs[2:]
    # Lowercase + sort for stable matching
    words = []
    for s in leaves:
        for w in re.findall(r"[A-Za-z][A-Za-z']+", s):
            wl = w.lower()
            if wl in {"plain", "natural", "original", "the", "and", "or"}:
                continue
            if len(wl) <= 2:
                continue
            words.append(wl)
    return " ".join(sorted(set(words)))


def main() -> None:
    print(f"Reading {AUDIT.name}...")
    rows = []
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(r)
    print(f"  loaded {len(rows):,} rows")

    # 1. Count (BFC, full_path) → count + sample fdc_ids
    bfc_path_count: dict[tuple[str, str], int] = Counter()
    bfc_path_samples: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for r in rows:
        bfc = (r.get("branded_food_category") or "").strip()
        cp = (r.get("canonical_path") or "").strip()
        if not (bfc and cp):
            continue
        key = (bfc, cp)
        bfc_path_count[key] += 1
        if len(bfc_path_samples[key]) < 3:
            bfc_path_samples[key].append((r.get("fdc_id", ""), (r.get("title") or "")[:80]))

    # 2. For each leaf-signature, find the dominant FULL path across the corpus
    sig_to_paths: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        cp = (r.get("canonical_path") or "").strip()
        if not cp:
            continue
        sig = _leaf_signature(cp)
        if not sig:
            continue
        sig_to_paths[sig][cp] += 1

    sig_dominant: dict[str, tuple[str, int]] = {}
    for sig, paths in sig_to_paths.items():
        total = sum(paths.values())
        if total < 5:
            continue
        dom_path, dom_n = paths.most_common(1)[0]
        if dom_n / total >= 0.50:
            sig_dominant[sig] = (dom_path, dom_n)

    # 3. Find outliers: (BFC, path) pairs with low count where the leaf-sig
    # has a different dominant path elsewhere
    out_rows = []
    for (bfc, cp), n in bfc_path_count.items():
        sig = _leaf_signature(cp)
        if not sig or sig not in sig_dominant:
            continue
        dom_path, dom_n = sig_dominant[sig]
        if cp == dom_path:
            continue
        # Outlier: this BFC+path has fewer SKUs than the dominant
        if n >= dom_n:
            continue
        # Severity: dominant_count / current_count (ratio)
        severity = dom_n / max(1, n)
        if severity < 5:  # require dominant to be 5x more common
            continue
        samples = bfc_path_samples[(bfc, cp)]
        out_rows.append({
            "severity": severity,
            "bfc": bfc,
            "current_path": cp,
            "current_count": n,
            "leaf_signature": sig,
            "dominant_path": dom_path,
            "dominant_count": dom_n,
            "sample_fdcs": " | ".join(s[0] for s in samples),
            "sample_titles": " | ".join(s[1] for s in samples),
        })

    out_rows.sort(key=lambda r: -r["severity"])

    cols = ["severity", "bfc", "current_path", "current_count", "leaf_signature",
            "dominant_path", "dominant_count", "sample_fdcs", "sample_titles"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=cols)
        wtr.writeheader()
        for r in out_rows:
            r["severity"] = f"{r['severity']:.0f}x"
            wtr.writerow(r)

    print(f"\n  found {len(out_rows):,} outlier (BFC, path) pairs")
    print(f"  wrote {OUT.name}")
    print()
    print("=== Top 30 most-severe outliers ===")
    for r in out_rows[:30]:
        print(f"\n  {r['severity']}  bfc={r['bfc']!r}  ({r['current_count']:,} SKUs)")
        print(f"    current : {r['current_path']}")
        print(f"    dominant: {r['dominant_path']}  ({r['dominant_count']:,} SKUs)")
        if r["sample_titles"]:
            print(f"    sample  : {r['sample_titles'][:120]}")


if __name__ == "__main__":
    main()
