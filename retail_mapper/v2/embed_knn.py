#!/usr/bin/env python3
"""Stage B6 — k-nearest ESHA tree nodes per product, using the existing cache.

Loads:
  implementation/.embed_cache/prod_emb.npy   (462k × 384, sentence-transformers MiniLM)
  implementation/.embed_cache/prod_ids.npy   (parallel fdc_id array)
  implementation/.embed_cache/tree_emb.npy   (39k × 384 ESHA tree nodes)
  implementation/.embed_cache/tree_codes.pkl (esha_code, description) tuples

Emits parquet:  fdc_id, top_k_codes, top_k_descs, top_k_scores  (pipe-delimited)
"""
from __future__ import annotations
import argparse, os, pickle, sys, time
from pathlib import Path
import numpy as np

REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
CACHE = REPO / "implementation" / ".embed_cache"
V2 = REPO / "retail_mapper" / "v2"
OUT_PARQUET = V2 / ".cache" / "embed_knn.parquet"
TOPK = 30
BATCH = 4096

def load():
    print("loading cached embeddings...")
    t0 = time.time()
    prod_emb  = np.load(CACHE / "prod_emb.npy")           # (N_p, D)
    prod_ids  = np.load(CACHE / "prod_ids.npy", allow_pickle=True)
    tree_emb  = np.load(CACHE / "tree_emb.npy")           # (N_t, D)
    with open(CACHE / "tree_codes.pkl", "rb") as f:
        tree_codes = pickle.load(f)                        # list[(code, desc)]
    print(f"  prod {prod_emb.shape}  tree {tree_emb.shape}  ({time.time()-t0:.1f}s)")
    return prod_emb, prod_ids, tree_emb, tree_codes

def normalize(X):
    n = np.linalg.norm(X, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (X / n).astype(np.float32)

def run(limit: int | None = None):
    import pyarrow as pa, pyarrow.parquet as pq
    prod_emb, prod_ids, tree_emb, tree_codes = load()
    P = normalize(prod_emb)
    T = normalize(tree_emb)
    if limit: P = P[:limit]; prod_ids = prod_ids[:limit]
    N = P.shape[0]
    rows = []
    t0 = time.time()
    for s in range(0, N, BATCH):
        e = min(N, s + BATCH)
        sims = P[s:e] @ T.T                                # (b, N_t)
        idx = np.argpartition(-sims, TOPK, axis=1)[:, :TOPK]
        # sort within top-k by score desc
        for i in range(idx.shape[0]):
            row_idx = idx[i]
            order = np.argsort(-sims[i, row_idx])
            row_idx = row_idx[order]
            scores = sims[i, row_idx]
            codes  = [tree_codes[j][0] for j in row_idx]
            descs  = [tree_codes[j][1] for j in row_idx]
            rows.append({
                "fdc_id":     str(prod_ids[s+i]),
                "top_codes":  "|".join(map(str, codes)),
                "top_descs":  "||".join(descs),
                "top_scores": "|".join(f"{x:.4f}" for x in scores),
            })
        if (s + BATCH) % 50000 < BATCH:
            el = time.time() - t0
            done = s + BATCH
            print(f"  {done:>7}/{N}  ({el/60:.1f}m, {done/el:.0f}/s)", flush=True)
    el = time.time() - t0
    print(f"  done {N} ({el/60:.1f}m)")
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, OUT_PARQUET, compression="zstd")
    print(f"wrote {OUT_PARQUET}")

def probe():
    """Show top-5 ESHA neighbors for the first 8 products (sanity check)."""
    prod_emb, prod_ids, tree_emb, tree_codes = load()
    P = normalize(prod_emb[:8])
    T = normalize(tree_emb)
    sims = P @ T.T
    for i in range(8):
        idx = np.argsort(-sims[i])[:5]
        print(f"\n  fdc_id={prod_ids[i]}")
        for j in idx:
            print(f"    {sims[i,j]:.3f}  esha={tree_codes[j][0]}  {tree_codes[j][1][:60]}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--probe", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args()
    if a.probe: probe()
    elif a.run: run(a.limit)
    else: p.print_help()

if __name__ == "__main__":
    main()
