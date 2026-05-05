#!/usr/bin/env python3
"""Recipe-ingredient taxonomy builder — mirrors retail_mapper/v2 approach.

Pipeline:
  1. Load unique ingredient items (from extract_unique_ingredients.py).
  2. Embed each item with sentence-transformers (same model family as retail).
  3. kNN-anchor each item against the existing ESHA tree embedding cache
     (implementation/.embed_cache/tree_emb.npy + tree_codes.pkl) — top-k.
  4. (Optional) MiniBatchKMeans over ingredient embeddings; per-cluster modal
     ESHA anchor becomes the cluster's "dominant home" (post-hoc anchor align).
  5. Emit recipe_ingredient_taxonomy.csv with esha_code, esha_description,
     similarity, cluster_id, cluster_dominant_esha_code.

This is the products-only-clustering + post-hoc kNN anchor pattern that won
in retail v1.
"""
from __future__ import annotations

import argparse
import csv
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EMB_CACHE = ROOT / "implementation" / ".embed_cache"
DEFAULT_IN = Path(__file__).resolve().parent / "output" / "recipe_ingredient_items.csv"
DEFAULT_OUT = Path(__file__).resolve().parent / "output" / "recipe_ingredient_taxonomy.csv"

# Same model family used to build the cached tree embeddings (384-dim ST).
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def log(t0: float, msg: str) -> None:
    print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)


def l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0,
                    help="0 = all rows; else cap for smoke run")
    ap.add_argument("--n-clusters", type=int, default=0,
                    help="0 = skip clustering; else k for MiniBatchKMeans")
    ap.add_argument("--batch-size", type=int, default=512)
    args = ap.parse_args()

    t0 = time.time()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.inp)
    if args.limit > 0:
        df = df.head(args.limit).copy()
    log(t0, f"loaded {len(df):,} ingredient items from {args.inp.name}")

    # --- load tree cache ---
    tree_emb = np.load(EMB_CACHE / "tree_emb.npy", allow_pickle=True).astype(np.float32)
    with open(EMB_CACHE / "tree_codes.pkl", "rb") as f:
        tree_codes = pickle.load(f)
    tree_emb = l2_normalize(tree_emb)
    tree_codes_arr = np.array(tree_codes, dtype=object)  # (N, 2): (code, desc)
    log(t0, f"tree: {tree_emb.shape}  nodes={len(tree_codes):,}")

    # --- embed ingredient items ---
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    items = df["item"].astype(str).tolist()
    log(t0, f"embedding {len(items):,} items with {args.model}")
    ing_emb = model.encode(
        items,
        batch_size=args.batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=False,
    ).astype(np.float32)
    ing_emb = l2_normalize(ing_emb)
    log(t0, f"ingredient embeddings: {ing_emb.shape}")

    # --- kNN against tree (cosine = dot on L2-normalized) ---
    log(t0, "computing top-k against ESHA tree")
    sims = ing_emb @ tree_emb.T  # (n_items, n_tree)
    k = args.top_k
    top_idx = np.argpartition(-sims, kth=min(k, sims.shape[1] - 1), axis=1)[:, :k]
    # sort the top-k by score desc
    row_arange = np.arange(sims.shape[0])[:, None]
    top_scores = sims[row_arange, top_idx]
    order = np.argsort(-top_scores, axis=1)
    top_idx = top_idx[row_arange, order]
    top_scores = top_scores[row_arange, order]

    best_code = [tree_codes_arr[i, 0] for i in top_idx[:, 0]]
    best_desc = [tree_codes_arr[i, 0] and tree_codes_arr[i, 1] for i in top_idx[:, 0]]
    best_sim = top_scores[:, 0]
    top_codes_csv = [
        " || ".join(
            f"{tree_codes_arr[idx, 0]}::{tree_codes_arr[idx, 1]}::{score:.3f}"
            for idx, score in zip(top_idx[r], top_scores[r])
        )
        for r in range(len(items))
    ]

    df["esha_code"] = best_code
    df["esha_description"] = best_desc
    df["similarity"] = best_sim
    df["top_k"] = top_codes_csv

    # --- optional clustering: dominant home ---
    if args.n_clusters and args.n_clusters > 1:
        from sklearn.cluster import MiniBatchKMeans
        log(t0, f"clustering ingredient embeddings k={args.n_clusters}")
        km = MiniBatchKMeans(
            n_clusters=args.n_clusters,
            random_state=7,
            batch_size=4096,
            n_init=3,
        )
        cluster_id = km.fit_predict(ing_emb)
        df["cluster_id"] = cluster_id

        # cluster's modal best_code = "dominant home"
        from collections import Counter
        modal = {}
        for cid, code in zip(cluster_id, best_code):
            modal.setdefault(cid, Counter())[code] += 1
        dom_code = {cid: c.most_common(1)[0][0] for cid, c in modal.items()}
        # map dom_code → desc via lookup
        code_to_desc = {c: d for c, d in tree_codes}
        df["cluster_dominant_esha_code"] = df["cluster_id"].map(dom_code)
        df["cluster_dominant_esha_description"] = df["cluster_dominant_esha_code"].map(code_to_desc)
        log(t0, f"clusters formed; dominant-home assigned")
    else:
        df["cluster_id"] = ""
        df["cluster_dominant_esha_code"] = ""
        df["cluster_dominant_esha_description"] = ""

    df.to_csv(args.out, index=False, quoting=csv.QUOTE_MINIMAL)
    log(t0, f"wrote {args.out} ({len(df):,} rows)")


if __name__ == "__main__":
    sys.exit(main())
