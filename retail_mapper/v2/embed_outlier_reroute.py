#!/usr/bin/env python3
"""For each severe outlier (sim < 0.40 to current path's centroid), find
the path whose centroid is the CLOSEST in embedding space. That's where
the SKU actually belongs.

Output: retail_mapper/v2/embed_outlier_reroutes.csv
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
OUT = V2 / "embed_outlier_reroutes.csv"

MIN_SKUS_PER_PATH = 10
SEVERE_THRESHOLD = 0.60  # widen analysis: anything below 0.60 gets reroute proposal
                          # (auto-apply filter still requires proposed_sim ≥ 0.55 + improvement ≥ 0.20)

csv.field_size_limit(sys.maxsize)


def main() -> None:
    print(f"  loading embeddings...")
    prod_emb = np.load(EMB)
    prod_ids = np.load(IDS, allow_pickle=True)
    fdc_to_idx = {str(fid): i for i, fid in enumerate(prod_ids)}

    # Index audit
    print(f"  reading audit CSV...")
    path_to_idxs: dict[str, list[int]] = defaultdict(list)
    fdc_to_path: dict[str, str] = {}
    title_by_fdc: dict[str, str] = {}
    with AUDIT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fdc = r.get("fdc_id", "")
            cp = r.get("canonical_path", "").strip()
            if not (fdc and cp): continue
            if fdc not in fdc_to_idx: continue
            idx = fdc_to_idx[fdc]
            path_to_idxs[cp].append(idx)
            fdc_to_path[fdc] = cp
            title_by_fdc[fdc] = r.get("title", "")[:100]

    # Compute centroid per qualifying path
    print(f"  computing path centroids ({sum(1 for v in path_to_idxs.values() if len(v) >= MIN_SKUS_PER_PATH):,} qualifying paths)...")
    path_names: list[str] = []
    centroids: list[np.ndarray] = []
    for path, idxs in path_to_idxs.items():
        if len(idxs) < MIN_SKUS_PER_PATH:
            continue
        members = prod_emb[idxs]
        c = members.mean(axis=0)
        n = np.linalg.norm(c)
        if n < 1e-6:
            continue
        path_names.append(path)
        centroids.append(c / n)
    centroid_matrix = np.stack(centroids)  # (P, 384)
    centroid_norms = np.linalg.norm(centroid_matrix, axis=1, keepdims=True)
    centroid_matrix /= centroid_norms  # normalize again to be safe
    print(f"    centroid matrix: {centroid_matrix.shape}")

    # For each SKU, get its similarity to its current path's centroid.
    # If below SEVERE_THRESHOLD, find the closest centroid and propose reroute.
    print(f"  scanning for severe outliers (sim < {SEVERE_THRESHOLD})...")
    path_idx_lookup = {p: i for i, p in enumerate(path_names)}
    n_severe = 0
    out_rows: list[dict] = []
    for fdc, cp in fdc_to_path.items():
        if cp not in path_idx_lookup:
            continue
        sku_idx = fdc_to_idx[fdc]
        sku_vec = prod_emb[sku_idx]
        cur_centroid_idx = path_idx_lookup[cp]
        cur_sim = float(sku_vec @ centroid_matrix[cur_centroid_idx])
        if cur_sim >= SEVERE_THRESHOLD:
            continue
        n_severe += 1
        # Find closest centroid (vectorized)
        all_sims = centroid_matrix @ sku_vec  # (P,)
        # Mask out current path so we don't pick it back
        all_sims[cur_centroid_idx] = -1
        best_idx = int(np.argmax(all_sims))
        best_sim = float(all_sims[best_idx])
        best_path = path_names[best_idx]
        out_rows.append({
            "fdc_id": fdc,
            "title": title_by_fdc.get(fdc, ""),
            "current_path": cp,
            "current_sim": f"{cur_sim:.3f}",
            "proposed_path": best_path,
            "proposed_sim": f"{best_sim:.3f}",
            "improvement": f"{best_sim - cur_sim:+.3f}",
        })

    out_rows.sort(key=lambda r: float(r["current_sim"]))  # worst-first

    cols = ["fdc_id", "title", "current_path", "current_sim",
            "proposed_path", "proposed_sim", "improvement"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    print(f"  severe outliers: {n_severe:,}")
    print(f"  wrote {OUT.name}")
    print()
    print("=== top 30 reroute proposals (worst-first) ===")
    for r in out_rows[:30]:
        print(f"  cur={r['current_sim']} → new={r['proposed_sim']}  {r['title'][:48]}")
        print(f"    FROM: {r['current_path'][:75]}")
        print(f"    TO:   {r['proposed_path'][:75]}")


if __name__ == "__main__":
    main()
