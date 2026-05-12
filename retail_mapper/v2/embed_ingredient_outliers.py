#!/usr/bin/env python3
"""Outlier detection using INGREDIENT centroids.

Same as embed_outlier_audit.py but using ingredient embeddings (built by
build_ingredient_embeddings.py). Catches mis-categorizations that the
title-based pass missed because the title alone is misleading.

Output: retail_mapper/v2/ingredient_outliers.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "retail_mapper" / "v2"
EMB = V2 / ".cache" / "ingredient_emb.npy"
IDS = V2 / ".cache" / "ingredient_ids.npy"
AUDIT = V2 / "full_corpus_audit.csv"
OUT = V2 / "ingredient_outliers.csv"

MIN_SKUS_PER_PATH = 10
ABS_SIM_THRESHOLD = 0.45
Z_THRESHOLD = -2.0

csv.field_size_limit(sys.maxsize)


def main() -> None:
    print("  loading ingredient embeddings...")
    emb = np.load(EMB)
    ids = np.load(IDS, allow_pickle=True)
    fdc_to_idx = {str(f): i for i, f in enumerate(ids)}
    print(f"    {len(ids):,} embeddings, dim={emb.shape[1]}")

    print("  reading audit CSV...")
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
    print(f"    paths with ingredient embeddings: {len(path_to_fdcs):,}")

    print(f"  computing centroids + flagging outliers (sim<{ABS_SIM_THRESHOLD} OR z<{Z_THRESHOLD})...")
    out_rows: list[dict] = []
    n_paths = 0; n_outliers = 0
    for path, fdcs in path_to_fdcs.items():
        if len(fdcs) < MIN_SKUS_PER_PATH: continue
        n_paths += 1
        idxs = np.array([fdc_to_idx[f] for f in fdcs])
        members = emb[idxs]
        centroid = members.mean(axis=0)
        n = np.linalg.norm(centroid)
        if n < 1e-6: continue
        centroid /= n
        sims = members @ centroid
        m_sim = sims.mean()
        s_sim = sims.std()
        if s_sim < 1e-6: continue
        for fdc, sim in zip(fdcs, sims):
            z = (sim - m_sim) / s_sim
            if sim < ABS_SIM_THRESHOLD or z < Z_THRESHOLD:
                n_outliers += 1
                out_rows.append({
                    "fdc_id": fdc,
                    "title": title_by_fdc.get(fdc, ""),
                    "current_path": path,
                    "path_n_skus": len(fdcs),
                    "ingredient_sim": f"{sim:.3f}",
                    "z_score": f"{z:.2f}",
                    "path_mean_sim": f"{m_sim:.3f}",
                })

    print(f"    paths processed: {n_paths:,}")
    print(f"    outliers flagged: {n_outliers:,}")

    out_rows.sort(key=lambda r: float(r["ingredient_sim"]))
    cols = ["fdc_id", "title", "current_path", "path_n_skus",
            "ingredient_sim", "z_score", "path_mean_sim"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    print(f"  wrote {OUT.name}")
    print()
    print("=== top 20 ingredient-based outliers ===")
    for r in out_rows[:20]:
        print(f"  sim={r['ingredient_sim']} z={r['z_score']}  {r['title'][:50]}")
        print(f"    in: {r['current_path'][:75]}")


if __name__ == "__main__":
    main()
