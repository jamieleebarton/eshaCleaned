#!/usr/bin/env python3
"""Vector-based outlier detection for canonical_path placements.

For each canonical_path with ≥ 10 SKUs:
  1. Compute centroid = mean of member embeddings (re-L2-normalized)
  2. For each member, compute cosine similarity to centroid
  3. Within that path's distribution, compute z-score (how many σ below mean)
  4. Flag rows whose similarity is below an absolute threshold OR z-score < -2

These are SKUs that don't fit semantically with their assigned category —
strong signal of mis-categorization.

Output: retail_mapper/v2/embed_outliers.csv (sorted worst-first)
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
EMB = REPO / "implementation" / ".embed_cache" / "prod_emb.npy"
IDS = REPO / "implementation" / ".embed_cache" / "prod_ids.npy"
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "embed_outliers.csv"

MIN_SKUS_PER_PATH = 10
ABS_SIM_THRESHOLD = 0.45  # similarity below this = clear outlier
Z_THRESHOLD = -2.0         # z-score below this = relative outlier within its path

csv.field_size_limit(sys.maxsize)


def main() -> None:
    print(f"  loading embeddings...")
    prod_emb = np.load(EMB)
    prod_ids = np.load(IDS, allow_pickle=True)
    fdc_to_idx: dict[str, int] = {str(fid): i for i, fid in enumerate(prod_ids)}
    print(f"    {len(prod_ids):,} embeddings, dim={prod_emb.shape[1]}")

    # Index audit by canonical_path
    print(f"  reading audit CSV...")
    path_to_fdcs: dict[str, list[str]] = defaultdict(list)
    title_by_fdc: dict[str, str] = {}
    path_by_fdc: dict[str, str] = {}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = r.get("fdc_id", "")
            cp = r.get("canonical_path", "").strip()
            if not (fdc and cp): continue
            if fdc not in fdc_to_idx: continue
            path_to_fdcs[cp].append(fdc)
            title_by_fdc[fdc] = r.get("title", "")[:100]
            path_by_fdc[fdc] = cp
    print(f"    {len(path_to_fdcs):,} distinct paths")

    # Outlier detection
    print(f"  computing centroids + similarities for paths with >= {MIN_SKUS_PER_PATH} SKUs...")
    out_rows: list[dict] = []
    n_paths_processed = 0
    n_outliers = 0
    for path, fdcs in path_to_fdcs.items():
        if len(fdcs) < MIN_SKUS_PER_PATH:
            continue
        n_paths_processed += 1
        idxs = np.array([fdc_to_idx[f] for f in fdcs])
        members = prod_emb[idxs]                      # (N, 384)
        centroid = members.mean(axis=0)
        c_norm = np.linalg.norm(centroid)
        if c_norm < 1e-6:
            continue
        centroid = centroid / c_norm                  # re-normalize
        sims = members @ centroid                     # cosine sims (L2-normalized)
        mean_sim = sims.mean()
        std_sim = sims.std()
        if std_sim < 1e-6:
            continue
        for fdc, sim in zip(fdcs, sims):
            z = (sim - mean_sim) / std_sim
            if sim < ABS_SIM_THRESHOLD or z < Z_THRESHOLD:
                n_outliers += 1
                out_rows.append({
                    "fdc_id": fdc,
                    "title": title_by_fdc.get(fdc, ""),
                    "current_path": path,
                    "path_n_skus": len(fdcs),
                    "sim_to_centroid": f"{sim:.3f}",
                    "z_score": f"{z:.2f}",
                    "path_mean_sim": f"{mean_sim:.3f}",
                })

    print(f"    paths processed: {n_paths_processed:,}")
    print(f"    outliers flagged: {n_outliers:,}")
    print()

    # Sort worst-first (lowest similarity)
    out_rows.sort(key=lambda r: float(r["sim_to_centroid"]))

    cols = ["fdc_id", "title", "current_path", "path_n_skus",
            "sim_to_centroid", "z_score", "path_mean_sim"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    print(f"  wrote {OUT.name}")
    print()
    print("=== top 25 outliers (lowest similarity to path centroid) ===")
    for r in out_rows[:25]:
        print(f"  sim={r['sim_to_centroid']}  z={r['z_score']}  {r['title'][:50]}")
        print(f"    in: {r['current_path'][:75]}")


if __name__ == "__main__":
    main()
