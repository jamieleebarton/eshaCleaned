"""Embed + graph-cluster pipeline for ESHA proxy alignment.

Pipeline stages:
  load   -> assemble corpus (products and reference items) into parquet/csv
  embed  -> sentence-transformer encode -> .npy (MPS-accelerated when available)
  graph  -> FAISS kNN -> sparse edge list above cosine threshold
  cluster-> Leiden community detection, brand-split, write cluster table
  align  -> per-cluster centroid kNN against SR28/FNDDS/ESHA -> single path
  report -> summary JSON + cluster preview CSV
  all    -> run every stage in order

Two modes are supported:
  --mode products_only  primary: cluster only products, align references post-hoc
  --mode joint          secondary: products + references in one corpus + cluster

Outputs go under implementation/output/embed_cluster_v1_<mode>/.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DATA = ROOT / "data"
OUT_BASE = ROOT / "implementation" / "output"

PRODUCTS_DB = DATA / "master_products.db"
ESHA_CANONICAL = ROOT / "esha_cleaned_canonical.csv"
SR28_FOOD_CSV = DATA / "sr28_csv" / "food.csv"
FNDDS_MAIN_CSV = DATA / "fndds" / "MainFoodDesc16.csv"

EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM = 384
EMBED_BATCH = 512
KNN_K = 15
COSINE_THRESHOLD = 0.88


def out_dir(mode: str) -> Path:
    d = OUT_BASE / f"embed_cluster_v1_{mode}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


@dataclass
class Corpus:
    df: pd.DataFrame
    text_col: str = "embed_text"


def _truncate_ingredients(s, max_items: int = 5) -> str:
    if not s or pd.isna(s):
        return ""
    parts = [p.strip() for p in str(s).split(",")]
    return ", ".join(parts[:max_items])


def load_products() -> pd.DataFrame:
    log("loading products from master_products.db")
    con = sqlite3.connect(PRODUCTS_DB)
    df = pd.read_sql_query(
        """
        SELECT gtin_upc, fdc_id, description, brand_name,
               branded_food_category, ingredients
        FROM products
        WHERE description IS NOT NULL AND description != ''
        """,
        con,
    )
    con.close()
    df["ingredients_short"] = df["ingredients"].map(_truncate_ingredients)
    parts = [
        df["description"].fillna(""),
        df["brand_name"].fillna(""),
        df["branded_food_category"].fillna(""),
        df["ingredients_short"].fillna(""),
    ]
    df["embed_text"] = parts[0].str.cat(parts[1:], sep=" | ", na_rep="")
    df["row_id"] = "p:" + df.index.astype(str)
    df["source"] = "product"
    df["ref_label"] = ""
    df["ref_code"] = ""
    df["row_id"] = df["row_id"].astype(str)
    df["ref_code"] = df["ref_code"].astype(str)
    log(f"  products loaded: {len(df):,}")
    return df[
        [
            "row_id",
            "source",
            "gtin_upc",
            "fdc_id",
            "description",
            "brand_name",
            "branded_food_category",
            "embed_text",
            "ref_label",
            "ref_code",
        ]
    ]


def load_esha() -> pd.DataFrame:
    log("loading ESHA canonical")
    df = pd.read_csv(ESHA_CANONICAL)
    df = df.rename(
        columns={
            "Description": "description",
            "EshaCode": "ref_code",
            "canonical_shopping_item": "ref_label",
        }
    )
    df["ref_code"] = df["ref_code"].astype(str)
    df["row_id"] = "esha:" + df["ref_code"]
    df["source"] = "esha"
    df["gtin_upc"] = ""
    df["fdc_id"] = pd.NA
    df["brand_name"] = ""
    df["branded_food_category"] = ""
    df["embed_text"] = df["description"].fillna("")
    log(f"  esha rows: {len(df):,}")
    return df[
        [
            "row_id",
            "source",
            "gtin_upc",
            "fdc_id",
            "description",
            "brand_name",
            "branded_food_category",
            "embed_text",
            "ref_label",
            "ref_code",
        ]
    ]


def load_sr28() -> pd.DataFrame:
    log("loading SR28")
    df = pd.read_csv(SR28_FOOD_CSV, dtype=str)
    df = df.rename(columns={"description": "description", "fdc_id": "ref_code"})
    df["row_id"] = "sr28:" + df["ref_code"].astype(str)
    df["source"] = "sr28"
    df["gtin_upc"] = ""
    df["fdc_id"] = pd.NA
    df["brand_name"] = ""
    df["branded_food_category"] = df.get("food_category_id", "")
    df["ref_label"] = df["description"].fillna("")
    df["embed_text"] = df["description"].fillna("")
    log(f"  sr28 rows: {len(df):,}")
    return df[
        [
            "row_id",
            "source",
            "gtin_upc",
            "fdc_id",
            "description",
            "brand_name",
            "branded_food_category",
            "embed_text",
            "ref_label",
            "ref_code",
        ]
    ]


def load_fndds() -> pd.DataFrame:
    log("loading FNDDS")
    df = pd.read_csv(FNDDS_MAIN_CSV, dtype=str)
    df = df.rename(
        columns={
            "Food code": "ref_code",
            "Main food description": "description",
            "WWEIA Category description": "branded_food_category",
        }
    )
    df = df.dropna(subset=["description"]).copy()
    df = df.drop_duplicates(subset=["ref_code"])
    df["row_id"] = "fndds:" + df["ref_code"].astype(str)
    df["source"] = "fndds"
    df["gtin_upc"] = ""
    df["fdc_id"] = pd.NA
    df["brand_name"] = ""
    df["ref_label"] = df["description"].fillna("")
    df["embed_text"] = df["description"].fillna("")
    log(f"  fndds rows: {len(df):,}")
    return df[
        [
            "row_id",
            "source",
            "gtin_upc",
            "fdc_id",
            "description",
            "brand_name",
            "branded_food_category",
            "embed_text",
            "ref_label",
            "ref_code",
        ]
    ]


def stage_load(mode: str, sample: int | None = None) -> Path:
    od = out_dir(mode)
    products = load_products()
    if sample:
        products = products.head(sample).copy()
        log(f"  SAMPLE MODE: capped products to {sample:,}")
    if mode == "joint":
        corpus = pd.concat(
            [products, load_esha(), load_sr28(), load_fndds()],
            ignore_index=True,
        )
    else:
        corpus = products
    corpus_path = od / "corpus.parquet"
    corpus.to_parquet(corpus_path, index=False)
    log(f"  wrote {corpus_path} ({len(corpus):,} rows)")

    refs_dir = od / "refs"
    refs_dir.mkdir(exist_ok=True)
    load_esha().to_parquet(refs_dir / "esha.parquet", index=False)
    load_sr28().to_parquet(refs_dir / "sr28.parquet", index=False)
    load_fndds().to_parquet(refs_dir / "fndds.parquet", index=False)
    log(f"  wrote refs/{{esha,sr28,fndds}}.parquet")
    return corpus_path


def _device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def stage_embed(mode: str) -> Path:
    od = out_dir(mode)
    corpus_path = od / "corpus.parquet"
    df = pd.read_parquet(corpus_path)
    texts = df["embed_text"].astype(str).tolist()

    from sentence_transformers import SentenceTransformer

    device = _device()
    log(f"loading {EMBED_MODEL} on {device}")
    model = SentenceTransformer(EMBED_MODEL, device=device)

    log(f"encoding {len(texts):,} texts (batch={EMBED_BATCH})")
    t0 = time.time()
    emb = model.encode(
        texts,
        batch_size=EMBED_BATCH,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    dt = time.time() - t0
    log(f"  encoded in {dt/60:.1f} min  shape={emb.shape}")

    emb_path = od / "embeddings.npy"
    np.save(emb_path, emb.astype(np.float32))
    log(f"  saved {emb_path}")

    refs_dir = od / "refs"
    if mode == "products_only":
        for src in ("esha", "sr28", "fndds"):
            rdf = pd.read_parquet(refs_dir / f"{src}.parquet")
            t0 = time.time()
            re = model.encode(
                rdf["embed_text"].astype(str).tolist(),
                batch_size=EMBED_BATCH,
                show_progress_bar=True,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            np.save(refs_dir / f"{src}.npy", re.astype(np.float32))
            log(
                f"  ref:{src} encoded {len(rdf):,} in {(time.time()-t0)/60:.1f} min"
            )
    return emb_path


def stage_graph(mode: str) -> Path:
    import faiss

    od = out_dir(mode)
    emb = np.load(od / "embeddings.npy")
    n, d = emb.shape
    log(f"FAISS IndexFlatIP  d={d}  n={n:,}")
    index = faiss.IndexFlatIP(d)
    index.add(emb)

    chunk = int(os.environ.get("EMBED_CHUNK", "256"))
    log(f"  chunked kNN search k={KNN_K}  chunk={chunk}")
    t0 = time.time()
    src_chunks: list[np.ndarray] = []
    dst_chunks: list[np.ndarray] = []
    w_chunks: list[np.ndarray] = []
    for i0 in range(0, n, chunk):
        i1 = min(i0 + chunk, n)
        sc, ix = index.search(emb[i0:i1], KNN_K)
        rows = np.repeat(np.arange(i0, i1), KNN_K)
        cols = ix.reshape(-1)
        sims = sc.reshape(-1).astype(np.float32)
        m = (cols >= 0) & (cols != rows) & (sims >= COSINE_THRESHOLD)
        rows = rows[m]
        cols = cols[m]
        sims = sims[m]
        # store undirected with src<dst
        lo = np.minimum(rows, cols)
        hi = np.maximum(rows, cols)
        src_chunks.append(lo.astype(np.int32))
        dst_chunks.append(hi.astype(np.int32))
        w_chunks.append(sims)
        if (i0 // chunk) % 50 == 0:
            log(
                f"    progress {i1:>8,}/{n:,}  "
                f"({100*i1/n:5.1f}%)  elapsed {(time.time()-t0)/60:.1f} min"
            )
    log(f"  search took {(time.time()-t0)/60:.1f} min")

    src = np.concatenate(src_chunks)
    dst = np.concatenate(dst_chunks)
    w = np.concatenate(w_chunks)
    log(f"  raw directed-pair count {len(src):,}; deduping undirected")
    edges = pd.DataFrame({"src": src, "dst": dst, "weight": w})
    edges = edges.drop_duplicates(subset=["src", "dst"]).reset_index(drop=True)
    edges_path = od / "edges.parquet"
    edges.to_parquet(edges_path, index=False)
    log(f"  edges: {len(edges):,}  -> {edges_path}")
    return edges_path


def stage_cluster(mode: str) -> Path:
    import igraph as ig
    import leidenalg as la

    od = out_dir(mode)
    df = pd.read_parquet(od / "corpus.parquet")
    edges = pd.read_parquet(od / "edges.parquet")
    n = len(df)

    log(f"building igraph: n={n:,}  edges={len(edges):,}")
    g = ig.Graph(n=n, edges=list(zip(edges["src"], edges["dst"])), directed=False)
    g.es["weight"] = edges["weight"].tolist()

    log("Leiden community detection")
    t0 = time.time()
    part = la.find_partition(
        g, la.ModularityVertexPartition, weights="weight", seed=42
    )
    log(f"  done in {(time.time()-t0)/60:.1f} min  clusters={len(part):,}")
    df["raw_cluster"] = part.membership

    # singletons keep raw cluster id but get tagged
    sizes = df.groupby("raw_cluster").size()
    df["raw_cluster_size"] = df["raw_cluster"].map(sizes)

    # brand-split inside each cluster (products only, hard constraint)
    log("brand-splitting clusters with mixed brand_name")
    df["brand_key"] = df.apply(
        lambda r: r["brand_name"] if r["source"] == "product" else "_REF_",
        axis=1,
    )
    df["cluster_id"] = (
        df["raw_cluster"].astype(str) + "::" + df["brand_key"].fillna("").astype(str)
    )
    cmap = {c: i for i, c in enumerate(sorted(df["cluster_id"].unique()))}
    df["cluster_id"] = df["cluster_id"].map(cmap)

    sizes2 = df.groupby("cluster_id").size()
    df["cluster_size"] = df["cluster_id"].map(sizes2)

    log(
        f"  raw clusters {len(part):,} -> brand-split clusters {df['cluster_id'].nunique():,}"
    )
    out_path = od / "product_clusters.parquet"
    df.to_parquet(out_path, index=False)
    log(f"  wrote {out_path}")
    return out_path


def _agg_examples(s: pd.Series, k: int = 5) -> str:
    return " || ".join(s.head(k).astype(str).tolist())


def stage_align(mode: str) -> Path:
    import faiss

    od = out_dir(mode)
    df = pd.read_parquet(od / "product_clusters.parquet")
    emb = np.load(od / "embeddings.npy")

    log("computing cluster centroids")
    centroids = []
    cluster_ids = sorted(df["cluster_id"].unique())
    for cid in cluster_ids:
        rows = df.index[df["cluster_id"] == cid].to_numpy()
        c = emb[rows].mean(axis=0)
        c /= max(np.linalg.norm(c), 1e-9)
        centroids.append(c)
    cent_arr = np.vstack(centroids).astype(np.float32)

    refs_dir = od / "refs"
    align_rows = []

    if mode == "joint":
        # anchors are inside the clusters already; pull them from df
        log("collecting anchors from joint corpus clusters")
        for cid in cluster_ids:
            sub = df[df["cluster_id"] == cid]
            prod_count = (sub["source"] == "product").sum()
            esha = sub[sub["source"] == "esha"].head(1)
            fndds = sub[sub["source"] == "fndds"].head(1)
            sr28 = sub[sub["source"] == "sr28"].head(1)
            align_rows.append(
                {
                    "cluster_id": cid,
                    "n_products": int(prod_count),
                    "esha_code": esha["ref_code"].iloc[0] if len(esha) else "",
                    "esha_label": esha["ref_label"].iloc[0] if len(esha) else "",
                    "esha_score": 1.0 if len(esha) else 0.0,
                    "fndds_code": fndds["ref_code"].iloc[0] if len(fndds) else "",
                    "fndds_label": fndds["ref_label"].iloc[0] if len(fndds) else "",
                    "fndds_score": 1.0 if len(fndds) else 0.0,
                    "sr28_code": sr28["ref_code"].iloc[0] if len(sr28) else "",
                    "sr28_label": sr28["ref_label"].iloc[0] if len(sr28) else "",
                    "sr28_score": 1.0 if len(sr28) else 0.0,
                }
            )
    else:
        log("kNN cluster-centroid -> reference indexes")
        for src in ("esha", "fndds", "sr28"):
            rdf = pd.read_parquet(refs_dir / f"{src}.parquet")
            re = np.load(refs_dir / f"{src}.npy")
            idx = faiss.IndexFlatIP(re.shape[1])
            idx.add(re)
            sc, ix = idx.search(cent_arr, 1)
            for cid, score, ridx in zip(cluster_ids, sc[:, 0], ix[:, 0]):
                align_rows.append(
                    {
                        "cluster_id": cid,
                        "src": src,
                        "ref_code": rdf.iloc[int(ridx)]["ref_code"],
                        "ref_label": rdf.iloc[int(ridx)]["ref_label"],
                        "score": float(score),
                    }
                )

        # pivot to one row per cluster
        log("pivoting alignment to one path per cluster")
        long = pd.DataFrame(align_rows)
        wide = long.pivot(
            index="cluster_id", columns="src", values=["ref_code", "ref_label", "score"]
        )
        wide.columns = [f"{c}_{s}" for c, s in wide.columns]
        wide = wide.reset_index().rename(
            columns={
                "ref_code_esha": "esha_code",
                "ref_label_esha": "esha_label",
                "score_esha": "esha_score",
                "ref_code_fndds": "fndds_code",
                "ref_label_fndds": "fndds_label",
                "score_fndds": "fndds_score",
                "ref_code_sr28": "sr28_code",
                "ref_label_sr28": "sr28_label",
                "score_sr28": "sr28_score",
            }
        )
        # n_products per cluster
        nprod = (
            df[df["source"] == "product"]
            .groupby("cluster_id")
            .size()
            .rename("n_products")
        )
        wide = wide.merge(nprod, on="cluster_id", how="left").fillna({"n_products": 0})
        align_rows = wide.to_dict(orient="records")

    align_df = pd.DataFrame(align_rows)

    # agreement guard
    log("applying alignment agreement guard")

    def _status(r):
        if r.get("esha_score", 0) < 0.6:
            return "ALIGN_DISAGREE_low_score"
        return "ALIGNED"

    align_df["align_status"] = align_df.apply(_status, axis=1)
    if "n_products" not in align_df.columns:
        align_df["n_products"] = 0
    align_df["needs_new_concept"] = (align_df["esha_score"].fillna(0) < 0.6).astype(int)

    # cluster previews
    log("attaching cluster previews")
    prods = df[df["source"] == "product"].copy()
    def _mode_or_empty(s: pd.Series) -> str:
        m = s.dropna().astype(str).replace("", pd.NA).dropna().mode()
        return str(m.iat[0]) if not m.empty else ""

    cluster_meta = (
        prods.groupby("cluster_id")
        .agg(
            n_products=("row_id", "count"),
            top_brand=("brand_name", _mode_or_empty),
            top_category=("branded_food_category", _mode_or_empty),
            examples=("description", _agg_examples),
        )
        .reset_index()
    )
    align_df = align_df.drop(columns=["n_products"], errors="ignore").merge(
        cluster_meta, on="cluster_id", how="left"
    )

    out_path = od / "cluster_alignment.csv"
    align_df.to_csv(out_path, index=False)
    log(f"  wrote {out_path}  rows={len(align_df):,}")

    # also write product->cluster->anchor map
    pmap = prods.merge(
        align_df[
            [
                "cluster_id",
                "esha_code",
                "esha_label",
                "esha_score",
                "fndds_code",
                "fndds_label",
                "fndds_score",
                "sr28_code",
                "sr28_label",
                "sr28_score",
                "align_status",
                "needs_new_concept",
            ]
        ],
        on="cluster_id",
        how="left",
    )
    pmap_path = od / "product_to_anchor.csv"
    pmap[
        [
            "gtin_upc",
            "fdc_id",
            "description",
            "brand_name",
            "branded_food_category",
            "cluster_id",
            "esha_code",
            "esha_label",
            "esha_score",
            "fndds_code",
            "fndds_label",
            "fndds_score",
            "sr28_code",
            "sr28_label",
            "sr28_score",
            "align_status",
            "needs_new_concept",
        ]
    ].to_csv(pmap_path, index=False)
    log(f"  wrote {pmap_path}  rows={len(pmap):,}")

    return out_path


def stage_report(mode: str) -> Path:
    od = out_dir(mode)
    align = pd.read_csv(od / "cluster_alignment.csv")
    pmap = pd.read_csv(od / "product_to_anchor.csv")

    summary = {
        "mode": mode,
        "embed_model": EMBED_MODEL,
        "knn_k": KNN_K,
        "cosine_threshold": COSINE_THRESHOLD,
        "n_clusters": int(align["cluster_id"].nunique()),
        "n_products": int(len(pmap)),
        "n_singletons": int((align["n_products"] == 1).sum()),
        "needs_new_concept_clusters": int(align["needs_new_concept"].sum()),
        "needs_new_concept_products": int(pmap["needs_new_concept"].sum()),
        "align_status_counts": align["align_status"].value_counts().to_dict(),
        "cluster_size_describe": align["n_products"].describe().to_dict(),
        "esha_score_describe": align["esha_score"]
        .dropna()
        .describe()
        .to_dict(),
    }
    sp = od / "summary.json"
    sp.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    return sp


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["products_only", "joint"], required=True)
    p.add_argument(
        "--stage",
        choices=["load", "embed", "graph", "cluster", "align", "report", "all"],
        default="all",
    )
    p.add_argument(
        "--sample", type=int, default=None, help="cap products to N for smoke test"
    )
    args = p.parse_args()

    stages = (
        ["load", "embed", "graph", "cluster", "align", "report"]
        if args.stage == "all"
        else [args.stage]
    )
    for s in stages:
        log(f"=== stage: {s} (mode={args.mode}) ===")
        if s == "load":
            stage_load(args.mode, sample=args.sample)
        elif s == "embed":
            stage_embed(args.mode)
        elif s == "graph":
            stage_graph(args.mode)
        elif s == "cluster":
            stage_cluster(args.mode)
        elif s == "align":
            stage_align(args.mode)
        elif s == "report":
            stage_report(args.mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
