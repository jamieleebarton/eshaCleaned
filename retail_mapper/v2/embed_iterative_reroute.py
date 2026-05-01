#!/usr/bin/env python3
"""Iterative centroid-purification reroute.

Loop:
  1. Compute path centroids from current state.
  2. Find SKUs whose embedding is far from their assigned path's centroid
     AND much closer to a different path's centroid.
  3. Apply ONLY the highest-confidence moves (strict thresholds).
  4. Recompute centroids — they're now cleaner because the polluters left.
  5. Repeat until no more high-confidence moves are found.

Each iteration's centroids are tighter than the last. Borderline outliers
become clear outliers as their previous assigned-path centroid sharpens up.

Output: retail_mapper/v2/iterative_reroutes.csv (all moves across passes)
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
OUT = V2 / "iterative_reroutes.csv"

MIN_SKUS_PER_PATH = 10
SIM_FAR_FROM_CURRENT = 0.50    # current sim must be below this (clear outlier)
SIM_NEAR_NEW = 0.65            # new path's sim must be above this (clear fit)
MIN_IMPROVEMENT = 0.30          # gap must be at least this big
MAX_ITERATIONS = 8

csv.field_size_limit(sys.maxsize)


def main() -> None:
    print(f"  loading embeddings...")
    prod_emb = np.load(EMB)
    prod_ids = np.load(IDS, allow_pickle=True)
    fdc_to_idx = {str(fid): i for i, fid in enumerate(prod_ids)}

    print(f"  reading audit...")
    fdc_to_path: dict[str, str] = {}
    title_by_fdc: dict[str, str] = {}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = r.get("fdc_id", "")
            cp = r.get("canonical_path", "").strip()
            if not (fdc and cp): continue
            if fdc not in fdc_to_idx: continue
            fdc_to_path[fdc] = cp
            title_by_fdc[fdc] = r.get("title", "")[:100]

    all_moves: list[dict] = []
    seen_moves: set[str] = set()  # fdc_ids already moved (don't re-move)

    for iteration in range(1, MAX_ITERATIONS + 1):
        # Build path → list of indices
        path_to_idxs: dict[str, list[int]] = defaultdict(list)
        for fdc, cp in fdc_to_path.items():
            path_to_idxs[cp].append(fdc_to_idx[fdc])

        # Compute centroids
        path_names: list[str] = []
        centroids: list[np.ndarray] = []
        for path, idxs in path_to_idxs.items():
            if len(idxs) < MIN_SKUS_PER_PATH: continue
            members = prod_emb[idxs]
            c = members.mean(axis=0)
            n = np.linalg.norm(c)
            if n < 1e-6: continue
            path_names.append(path)
            centroids.append(c / n)
        centroid_matrix = np.stack(centroids)
        path_idx_lookup = {p: i for i, p in enumerate(path_names)}

        # Find moves
        n_moves_this_iter = 0
        moves_to_apply: list[tuple[str, str]] = []  # (fdc, new_path)
        for fdc, cp in fdc_to_path.items():
            if fdc in seen_moves: continue
            if cp not in path_idx_lookup: continue
            sku_vec = prod_emb[fdc_to_idx[fdc]]
            cur_idx = path_idx_lookup[cp]
            cur_sim = float(sku_vec @ centroid_matrix[cur_idx])
            if cur_sim >= SIM_FAR_FROM_CURRENT:
                continue
            # Find best alternative
            all_sims = centroid_matrix @ sku_vec
            all_sims[cur_idx] = -1
            best = int(np.argmax(all_sims))
            best_sim = float(all_sims[best])
            improvement = best_sim - cur_sim
            if best_sim >= SIM_NEAR_NEW and improvement >= MIN_IMPROVEMENT:
                new_path = path_names[best]
                moves_to_apply.append((fdc, new_path))
                all_moves.append({
                    "iteration": str(iteration),
                    "fdc_id": fdc,
                    "title": title_by_fdc.get(fdc, ""),
                    "old_path": cp,
                    "new_path": new_path,
                    "current_sim": f"{cur_sim:.3f}",
                    "proposed_sim": f"{best_sim:.3f}",
                    "improvement": f"{improvement:+.3f}",
                })
                seen_moves.add(fdc)
                n_moves_this_iter += 1
        if n_moves_this_iter == 0:
            print(f"  iter {iteration}: 0 moves — converged.")
            break
        # Apply the moves to fdc_to_path for next iteration
        for fdc, np_path in moves_to_apply:
            fdc_to_path[fdc] = np_path
        print(f"  iter {iteration}: {n_moves_this_iter:,} moves applied (centroids will be recomputed)")

    cols = ["iteration", "fdc_id", "title", "old_path", "new_path",
            "current_sim", "proposed_sim", "improvement"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(all_moves)
    print(f"\n  TOTAL MOVES: {len(all_moves):,}")
    print(f"  wrote {OUT.name}")


if __name__ == "__main__":
    main()
