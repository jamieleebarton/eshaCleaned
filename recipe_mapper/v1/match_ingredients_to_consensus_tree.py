#!/usr/bin/env python3
"""Match recipe ingredients into the consensus retail taxonomy tree.

Anchor = consensus_tree_nodes.csv (10,525 unique tree nodes from
consensus_full_corpus_audit.csv). Each node carries product_identity_fixed,
canonical_path, modal_fndds_code, modal_sr28_code, portions_json — i.e.
the gram-weight + nutrient calculation handle the user actually needs.

For each unique recipe ingredient `item`:
  1. Encode the ingredient.
  2. Encode each tree node using a richer text:
       "<product_identity_fixed> | <canonical_path tail> | <modal_branded_food_category>"
     plus the modal FNDDS desc as a secondary anchor.
  3. Cosine top-K against the node embedding matrix.
  4. Output: ingredient -> canonical_path, product_identity_fixed,
     modal_fndds_code/desc, modal_sr28_code/desc, has_portions, similarity,
     plus top_k for inspection.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_NODES = HERE / "output" / "consensus_tree_nodes.csv"
DEFAULT_ITEMS = HERE / "output" / "recipe_ingredient_items.csv"
DEFAULT_OUT = HERE / "output" / "recipe_ingredient_consensus_match.csv"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def log(t0: float, m: str) -> None:
    print(f"[{time.time() - t0:6.1f}s] {m}", flush=True)


def l2(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


def node_text(row: pd.Series) -> str:
    pid = str(row.get("product_identity_fixed") or "")
    cp = str(row.get("canonical_path") or "")
    bfc = str(row.get("modal_branded_food_category") or "")
    fdesc = str(row.get("modal_fndds_desc") or "")
    # canonical_path tail (last 2 segments) gives the local context
    tail = " ".join(cp.split(" > ")[-2:]) if cp else ""
    parts = [pid, tail, bfc, fdesc]
    return " | ".join(p for p in parts if p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=Path, default=DEFAULT_NODES)
    ap.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    t0 = time.time()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    nodes = pd.read_csv(args.nodes).fillna("")
    items = pd.read_csv(args.items).fillna("")
    if args.limit > 0:
        items = items.head(args.limit).copy()
    log(t0, f"nodes={len(nodes):,}  items={len(items):,}")

    node_texts = nodes.apply(node_text, axis=1).tolist()
    item_texts = items["item"].astype(str).tolist()

    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(args.model)
    log(t0, "embedding tree nodes")
    node_emb = l2(m.encode(node_texts, batch_size=512, show_progress_bar=False,
                           convert_to_numpy=True).astype(np.float32))
    log(t0, "embedding ingredient items")
    ing_emb = l2(m.encode(item_texts, batch_size=512, show_progress_bar=False,
                          convert_to_numpy=True).astype(np.float32))

    log(t0, "cosine top-k")
    sims = ing_emb @ node_emb.T
    k = args.top_k
    top_idx = np.argpartition(-sims, kth=min(k, sims.shape[1] - 1), axis=1)[:, :k]
    rs = np.arange(sims.shape[0])[:, None]
    top_scores = sims[rs, top_idx]
    order = np.argsort(-top_scores, axis=1)
    top_idx = top_idx[rs, order]
    top_scores = top_scores[rs, order]

    cp = nodes["canonical_path"].values
    pid = nodes["product_identity_fixed"].values
    fc = nodes["modal_fndds_code"].values
    fd = nodes["modal_fndds_desc"].values
    sc = nodes["modal_sr28_code"].values
    sd = nodes["modal_sr28_desc"].values
    rl = nodes["modal_retail_leaf_path"].values
    pj = nodes["portions_json"].values
    skn = nodes["sku_count"].values

    items["canonical_path"] = cp[top_idx[:, 0]]
    items["product_identity_fixed"] = pid[top_idx[:, 0]]
    items["modal_retail_leaf_path"] = rl[top_idx[:, 0]]
    items["modal_fndds_code"] = fc[top_idx[:, 0]]
    items["modal_fndds_desc"] = fd[top_idx[:, 0]]
    items["modal_sr28_code"] = sc[top_idx[:, 0]]
    items["modal_sr28_desc"] = sd[top_idx[:, 0]]
    items["node_sku_count"] = skn[top_idx[:, 0]]
    items["has_portions"] = [bool(pj[i]) for i in top_idx[:, 0]]
    items["similarity"] = top_scores[:, 0]

    def fmt(r: int) -> str:
        return " || ".join(
            f"{cp[top_idx[r,j]]} > {pid[top_idx[r,j]]} :: fndds={fc[top_idx[r,j]]} sr28={sc[top_idx[r,j]]} sim={top_scores[r,j]:.3f}"
            for j in range(k)
        )
    items["top_k"] = [fmt(r) for r in range(len(items))]

    items.to_csv(args.out, index=False, quoting=csv.QUOTE_MINIMAL)
    log(t0, f"wrote {args.out} ({len(items):,} rows)")

    s = items["similarity"]
    print(f"  median sim={s.median():.3f}  >=0.50={(s>=0.50).mean():.1%}  "
          f">=0.75={(s>=0.75).mean():.1%}  has_portions={items['has_portions'].mean():.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
