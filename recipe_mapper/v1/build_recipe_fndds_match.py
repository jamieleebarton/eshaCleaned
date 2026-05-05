#!/usr/bin/env python3
"""Match recipe ingredient items to FNDDS food codes.

FNDDS is the right anchor (not ESHA): the 9-digit food code IS the hierarchy,
and FNDDSSRLinks gives gram weights / SR-28 nutrient links per code.

Pipeline:
  1. Load unique recipe ingredient items.
  2. Load FNDDS MainFoodDesc16.csv -> 10,585 (food_code, main_description,
     wweia_category_code, wweia_category_description).
  3. Embed FNDDS descriptions and ingredient items with the same ST model.
  4. kNN: for each ingredient -> top-K FNDDS food codes by cosine.
  5. Join FNDDSSRLinks for gram weight presence.
  6. Emit recipe_ingredient_fndds.csv (top-1 + top-5 detail).
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FNDDS_MAIN = ROOT / "data" / "fndds" / "MainFoodDesc16.csv"
FNDDS_SR = ROOT / "data" / "fndds" / "FNDDSSRLinks.csv"
HERE = Path(__file__).resolve().parent
DEFAULT_IN = HERE / "output" / "recipe_ingredient_items.csv"
DEFAULT_OUT = HERE / "output" / "recipe_ingredient_fndds.csv"

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def log(t0: float, msg: str) -> None:
    print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)


def l2(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


def load_fndds() -> pd.DataFrame:
    df = pd.read_csv(FNDDS_MAIN, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={
        "Food code": "fndds_code",
        "Main food description": "fndds_description",
        "WWEIA Category code": "wweia_code",
        "WWEIA Category description": "wweia_description",
    })
    return df[["fndds_code", "fndds_description", "wweia_code", "wweia_description"]]


def load_sr_weights() -> dict[str, str]:
    """Return {food_code: 'best_sr_description (Weight g)'} for primary link."""
    out: dict[str, tuple[str, str]] = {}
    with open(FNDDS_SR, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            fc = (row.get("Food code") or "").strip()
            seq = (row.get("Seq num") or "").strip()
            sr_desc = (row.get("SR description") or "").strip()
            wt = (row.get("Weight") or "").strip()
            if not fc:
                continue
            # keep seq=1 (primary) if available, else first seen
            if seq == "1" or fc not in out:
                out[fc] = (sr_desc, wt)
    return {k: f"{v[0]} ({v[1]} g)" for k, v in out.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    t0 = time.time()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    df_in = pd.read_csv(args.inp)
    if args.limit > 0:
        df_in = df_in.head(args.limit).copy()
    log(t0, f"loaded {len(df_in):,} ingredient items")

    fndds = load_fndds()
    log(t0, f"FNDDS food codes: {len(fndds):,}")

    sr = load_sr_weights()
    log(t0, f"FNDDS codes with SR/weight links: {len(sr):,}")

    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(args.model)

    log(t0, "embedding FNDDS descriptions")
    fndds_emb = l2(m.encode(fndds["fndds_description"].tolist(),
                            batch_size=512, show_progress_bar=False,
                            convert_to_numpy=True).astype(np.float32))

    log(t0, f"embedding {len(df_in):,} ingredient items")
    ing_emb = l2(m.encode(df_in["item"].astype(str).tolist(),
                          batch_size=512, show_progress_bar=False,
                          convert_to_numpy=True).astype(np.float32))

    log(t0, "computing cosine top-k")
    sims = ing_emb @ fndds_emb.T
    k = args.top_k
    top_idx = np.argpartition(-sims, kth=min(k, sims.shape[1] - 1), axis=1)[:, :k]
    rows = np.arange(sims.shape[0])[:, None]
    top_scores = sims[rows, top_idx]
    order = np.argsort(-top_scores, axis=1)
    top_idx = top_idx[rows, order]
    top_scores = top_scores[rows, order]

    fcodes = fndds["fndds_code"].values
    fdescs = fndds["fndds_description"].values
    wweia = fndds["wweia_description"].values

    df_in["fndds_code"] = [fcodes[i] for i in top_idx[:, 0]]
    df_in["fndds_description"] = [fdescs[i] for i in top_idx[:, 0]]
    df_in["wweia_category"] = [wweia[i] for i in top_idx[:, 0]]
    df_in["similarity"] = top_scores[:, 0]
    df_in["sr_link"] = [sr.get(c, "") for c in df_in["fndds_code"]]
    df_in["has_weight"] = [bool(sr.get(c)) for c in df_in["fndds_code"]]

    def fmt(r: int) -> str:
        return " || ".join(
            f"{fcodes[top_idx[r, j]]}::{fdescs[top_idx[r, j]]}::{top_scores[r, j]:.3f}"
            for j in range(k)
        )
    df_in["top_k"] = [fmt(r) for r in range(len(df_in))]

    df_in.to_csv(args.out, index=False, quoting=csv.QUOTE_MINIMAL)
    log(t0, f"wrote {args.out} ({len(df_in):,} rows)")

    sims_arr = df_in["similarity"]
    print(f"  median sim={sims_arr.median():.3f}  "
          f"share>=0.50={(sims_arr>=0.50).mean():.1%}  "
          f"share>=0.75={(sims_arr>=0.75).mean():.1%}  "
          f"with_weight={df_in['has_weight'].mean():.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
