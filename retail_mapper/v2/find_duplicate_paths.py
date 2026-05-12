#!/usr/bin/env python3
"""Find duplicate canonical_paths — paths whose ingredient-centroids are
near-identical AND whose final segment (or last 2 segments) match closely.

Examples this should catch:
  - 'Dairy > Milk > Whole' vs 'Beverage > Dairy Milk > Milk > Whole'
  - 'Pantry > Soup' vs 'Pantry > Soups'
  - 'Snack > Granola Bars' vs 'Snack > Bars > Granola Bars'

Output: retail_mapper/v2/duplicate_path_pairs.csv (sorted by impact)
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
EMB = V2 / ".cache" / "ingredient_emb.npy"
IDS = V2 / ".cache" / "ingredient_ids.npy"
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "duplicate_path_pairs.csv"

MIN_SKUS = 5
SIM_DUPLICATE = 0.92          # centroid-cosine threshold for "same thing"
LEAF_TOKEN_OVERLAP = 0.50      # last-segment token overlap as a sanity filter

csv.field_size_limit(sys.maxsize)
WORD_RX = re.compile(r"[A-Za-z0-9]+")


def tokens(s: str) -> set[str]:
    return {w.lower() for w in WORD_RX.findall(s) if len(w) > 1}


def main() -> None:
    print("  loading ingredient embeddings...")
    emb = np.load(EMB)
    ids = np.load(IDS, allow_pickle=True)
    fdc_to_idx = {str(f): i for i, f in enumerate(ids)}

    print("  reading audit...")
    path_to_idxs: dict[str, list[int]] = defaultdict(list)
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = r.get("fdc_id", "")
            cp = r.get("canonical_path", "").strip()
            if not (fdc and cp): continue
            if fdc not in fdc_to_idx: continue
            path_to_idxs[cp].append(fdc_to_idx[fdc])

    # Compute centroid per qualifying path
    print(f"  computing centroids for paths with >= {MIN_SKUS} SKUs...")
    paths: list[str] = []
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    for path, idxs in path_to_idxs.items():
        if len(idxs) < MIN_SKUS: continue
        members = emb[np.array(idxs)]
        c = members.mean(axis=0)
        n = np.linalg.norm(c)
        if n < 1e-6: continue
        paths.append(path)
        centroids.append(c / n)
        counts.append(len(idxs))
    cm = np.stack(centroids)
    print(f"    {len(paths):,} paths qualify")

    # Pairwise sim: dot product of L2-normalized centroids
    print(f"  computing pairwise centroid similarities (this is O(P^2))...")
    sim = cm @ cm.T  # (P, P)
    # Find duplicate pairs
    pairs: list[tuple[int, int, float]] = []
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            s = sim[i, j]
            if s < SIM_DUPLICATE:
                continue
            # Sanity filter: last 2 segments must token-overlap meaningfully
            ai = paths[i].split(" > ")[-2:]
            aj = paths[j].split(" > ")[-2:]
            ti = tokens(" ".join(ai))
            tj = tokens(" ".join(aj))
            if not ti or not tj:
                continue
            jacc = len(ti & tj) / len(ti | tj)
            if jacc < LEAF_TOKEN_OVERLAP:
                continue
            pairs.append((i, j, float(s)))

    print(f"    candidate duplicate pairs: {len(pairs):,}")

    # Sort by total SKU count (impact) descending
    pairs.sort(key=lambda p: -(counts[p[0]] + counts[p[1]]))

    cols = ["sku_a", "path_a", "sku_b", "path_b", "centroid_sim",
            "leaf_overlap", "total_skus"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for i, j, s in pairs:
            ti = tokens(" ".join(paths[i].split(" > ")[-2:]))
            tj = tokens(" ".join(paths[j].split(" > ")[-2:]))
            jacc = len(ti & tj) / len(ti | tj)
            # Always put the LARGER bucket as 'a'
            if counts[j] > counts[i]:
                i, j = j, i
            w.writerow({
                "sku_a": counts[i], "path_a": paths[i],
                "sku_b": counts[j], "path_b": paths[j],
                "centroid_sim": f"{s:.3f}",
                "leaf_overlap": f"{jacc:.2f}",
                "total_skus": counts[i] + counts[j],
            })
    print(f"  wrote {OUT.name}")
    print()
    print("=== top 30 duplicate-path candidates by total SKU impact ===")
    for i, j, s in pairs[:30]:
        if counts[j] > counts[i]: i, j = j, i
        print(f"  sim={s:.3f} {counts[i]:>4}+{counts[j]:>4} SKUs")
        print(f"    A: {paths[i]}")
        print(f"    B: {paths[j]}")


if __name__ == "__main__":
    main()
