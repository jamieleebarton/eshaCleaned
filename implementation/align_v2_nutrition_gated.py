"""Engine A — confident assignment.

For every product:
  1. Pull text embedding from the v1 cache.
  2. Pull identity_terms from self_heal/product_facts.csv (already extracted).
  3. Pull nutrition vector from products table (cal/protein/fat/carb/fiber/sugar/sodium per 100g).
  4. Retrieve top-50 leaf candidates from rft_v2/leaves.csv by text similarity.
  5. Identity-token gate: reject candidates whose head/canonical_name share no identity token with the product.
  6. Nutrition gate: reject candidates whose FNDDS nutrition differs by >30% on any present macro.
     (If candidate has no FNDDS code, nutrition gate is N/A — text-only scoring.)
  7. Score survivors: 0.4*text + 0.4*nutrition_proximity + 0.2*ingredient_jaccard.
  8. Pick best surviving candidate. Classify CONFIDENT / LOW_CONFIDENCE / IDENTITY_GATE_FAILED / NEEDS_NEW_CONCEPT.

Output: implementation/output/align_v2/product_to_anchor_v2.csv with all three sources from the chosen leaf.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
OUT = ROOT / "implementation" / "output" / "align_v2"
OUT.mkdir(parents=True, exist_ok=True)

PRODUCTS_DB = ROOT / "data" / "master_products.db"
PRODUCT_FACTS = ROOT / "implementation" / "output" / "self_heal" / "product_facts.csv"
LEAVES = ROOT / "implementation" / "output" / "rft_v2" / "leaves.csv"
FNDDS_NUTR = ROOT / "data" / "fndds" / "fndds_nutrient_lookup.csv"
PRODUCT_EMB_CACHE = (
    ROOT / "implementation" / "output" / "embed_cluster_v1_products_only" / "embeddings.npy"
)
PRODUCT_CORPUS = (
    ROOT / "implementation" / "output" / "embed_cluster_v1_products_only" / "corpus.parquet"
)

EMBED_MODEL = "all-MiniLM-L6-v2"
KNN_K = 50

# Nutrition gate: per-100g, reject if any present macro deviates by more than this fraction
NUTR_TOLERANCE = 0.30
# Macros we compare on
MACROS = ("calories", "protein_g", "fat_g", "carbs_g", "fiber_g", "sugar_g", "sodium_mg")
# FNDDS column names map (fndds_nutrient_lookup uses different naming)
FNDDS_MACRO_MAP = {
    "calories": "energy_kcal",
    "protein_g": "protein_g",
    "fat_g": "fat_g",
    "carbs_g": "carbs_g",
    "fiber_g": "fiber_g",
    "sugar_g": "sugar_g",
    "sodium_mg": "sodium_mg",
}

# Identity gate config — minimum identity token overlap
GENERIC_TOKENS = {
    "and", "or", "with", "the", "in", "of", "for", "from", "to", "a",
    "made", "style", "type", "without", "organic", "natural", "premium",
    "select", "original", "classic", "lower", "reduced", "free",
    "flavored", "flavoured", "mini", "large", "small", "count", "oz",
    "fl", "lb", "pack", "package", "box", "bag", "ct", "fresh",
    "all", "no", "added", "less", "than", "more", "low", "high",
    "fat", "sodium", "sugar", "calorie", "calories",
}

CONFIDENT_THRESHOLD = 0.75
LOW_CONFIDENCE_THRESHOLD = 0.55


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def tokenize(text: str) -> set[str]:
    if not isinstance(text, str):
        return set()
    return {t for t in text.lower().replace(",", " ").replace("|", " ").split() if t and t not in GENERIC_TOKENS and len(t) > 1}


# ---------- load ----------


def load_products() -> pd.DataFrame:
    log("loading products + nutrition from master_products.db")
    con = sqlite3.connect(PRODUCTS_DB)
    df = pd.read_sql_query(
        f"""
        SELECT gtin_upc, fdc_id, description, brand_name,
               branded_food_category, ingredients,
               serving_size, serving_size_unit,
               {','.join(MACROS)}
        FROM products
        WHERE description IS NOT NULL AND description != ''
        """,
        con,
    )
    con.close()
    log(f"  {len(df):,} products")

    # normalize nutrition to per-100g where serving size is in grams
    log("  normalizing nutrition per-100g")
    is_g = df["serving_size_unit"].astype(str).str.lower().isin(["g", "gm", "grm"])
    factor = pd.Series(np.nan, index=df.index)
    factor[is_g] = 100.0 / df.loc[is_g, "serving_size"].replace(0, np.nan)
    for m in MACROS:
        df[f"{m}_per100g"] = df[m] * factor

    # join product facts (identity_terms etc.)
    log("loading product_facts (identity_terms)")
    facts = pd.read_csv(
        PRODUCT_FACTS,
        usecols=["gtin_upc", "category_lane", "product_form", "identity_terms", "target_heads"],
        dtype=str,
        low_memory=False,
    )
    facts["identity_terms"] = facts["identity_terms"].fillna("")
    df = df.merge(facts, on="gtin_upc", how="left")
    log(f"  facts joined; {df['identity_terms'].notna().sum():,} have identity_terms")

    # parse ingredients into a token set (top-N)
    log("  parsing ingredient tokens")
    df["ingredient_tokens"] = df["ingredients"].fillna("").astype(str).apply(
        lambda s: tokenize(s[:300])
    )
    df["title_tokens"] = df["description"].fillna("").astype(str).apply(tokenize)
    df["identity_set"] = df["identity_terms"].fillna("").astype(str).apply(
        lambda s: {t for t in s.split() if t}
    )
    return df


def load_leaves_with_nutrition() -> pd.DataFrame:
    log("loading leaves catalog")
    leaves = pd.read_csv(LEAVES, dtype=str, low_memory=False)
    log(f"  {len(leaves):,} leaves; {leaves['head'].nunique():,} unique heads")

    log("loading FNDDS nutrient lookup")
    fndds = pd.read_csv(FNDDS_NUTR, dtype={"fndds_code": str})
    # Map to our macro names
    nutr = pd.DataFrame()
    nutr["fndds_code"] = fndds["fndds_code"]
    for m in MACROS:
        col = FNDDS_MACRO_MAP[m]
        nutr[f"{m}_per100g"] = pd.to_numeric(fndds.get(col), errors="coerce")

    leaves = leaves.merge(nutr, left_on="fndds_code", right_on="fndds_code", how="left")
    have = leaves[f"calories_per100g"].notna().sum()
    log(f"  leaves with FNDDS nutrition: {have:,} / {len(leaves):,}")

    # Build leaf text for embedding
    leaves["leaf_text"] = (
        leaves["canonical_name"].fillna("")
        + " | "
        + leaves["head"].fillna("")
        + " | "
        + leaves["key_facets"].fillna("").str.replace("|", " ", regex=False)
    )
    leaves["head_token"] = leaves["head"].fillna("").str.lower()
    leaves["leaf_token_set"] = leaves["leaf_text"].apply(tokenize)
    return leaves


# ---------- embed leaves ----------


def embed_leaves(leaves: pd.DataFrame) -> np.ndarray:
    log(f"embedding {len(leaves):,} leaves on MPS")
    from sentence_transformers import SentenceTransformer
    import torch

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(EMBED_MODEL, device=device)
    emb = model.encode(
        leaves["leaf_text"].astype(str).tolist(),
        batch_size=512,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)
    np.save(OUT / "leaves_embeddings.npy", emb)
    log(f"  saved leaves embeddings: {emb.shape}")
    return emb


# ---------- align ----------


def gate_identity(prod_set: set[str], head_token: str, leaf_token_set: set[str]) -> bool:
    """Return True if identity gate passes."""
    if not prod_set:
        # Fallback: at least head must overlap title tokens
        return False
    # Strong rule: head token must appear in product identity OR title.
    if head_token and head_token in prod_set:
        return True
    # Weaker rule: identity ∩ leaf_text must be non-empty AND share a non-generic token
    return bool(prod_set & leaf_token_set)


def gate_nutrition(p_n: dict[str, float], l_n: dict[str, float]) -> tuple[bool, float]:
    """Return (passes_gate, nutrition_proximity_score 0..1).

    Both passed nutrition dicts are per-100g. Compare on macros where BOTH have a value.
    """
    diffs: list[float] = []
    macros_compared = 0
    for m in MACROS:
        pv = p_n.get(m)
        lv = l_n.get(m)
        if pv is None or lv is None or not np.isfinite(pv) or not np.isfinite(lv):
            continue
        # absolute and relative comparison; use a small floor so 0/0 doesn't blow up
        denom = max(abs(pv), abs(lv), 1.0)
        rel_diff = abs(pv - lv) / denom
        diffs.append(rel_diff)
        macros_compared += 1
    if macros_compared < 3:
        # not enough nutrition signal — passes by default but proximity = NaN
        return True, float("nan")
    avg_diff = float(np.mean(diffs))
    # any macro >NUTR_TOLERANCE → reject
    fails = any(d > NUTR_TOLERANCE for d in diffs)
    proximity = max(0.0, 1.0 - avg_diff)
    return (not fails), proximity


def score_candidate(
    text_sim: float,
    nutr_prox: float,
    ing_jaccard: float,
) -> float:
    if not np.isfinite(nutr_prox):
        # No nutrition — fall back to pure text + ingredient
        return 0.7 * text_sim + 0.3 * ing_jaccard
    return 0.4 * text_sim + 0.4 * nutr_prox + 0.2 * ing_jaccard


def align_one(
    p_idx: int,
    products: pd.DataFrame,
    leaves: pd.DataFrame,
    cand_idx: np.ndarray,
    cand_score: np.ndarray,
) -> dict:
    p = products.iloc[p_idx]
    p_set = p["identity_set"] | p["title_tokens"]
    p_ing = p["ingredient_tokens"]
    p_n = {m: p.get(f"{m}_per100g", np.nan) for m in MACROS}

    survivors: list[tuple[float, int, float, float]] = []
    id_failed = 0
    nut_failed = 0

    for j_pos in range(len(cand_idx)):
        j = int(cand_idx[j_pos])
        if j < 0:
            continue
        leaf = leaves.iloc[j]
        head_tok = leaf.get("head_token", "")
        leaf_tok = leaf.get("leaf_token_set", set())

        if not gate_identity(p_set, head_tok, leaf_tok):
            id_failed += 1
            continue

        l_n = {m: leaf.get(f"{m}_per100g", np.nan) for m in MACROS}
        nut_ok, nut_prox = gate_nutrition(p_n, l_n)
        if not nut_ok:
            nut_failed += 1
            continue

        ing_jac = 0.0
        if p_ing and leaf_tok:
            inter = len(p_ing & leaf_tok)
            union = len(p_ing | leaf_tok)
            ing_jac = inter / max(union, 1)

        text_sim = float(cand_score[j_pos])
        s = score_candidate(text_sim, nut_prox, ing_jac)
        survivors.append((s, j, text_sim, nut_prox))

    if not survivors:
        # No survivor — classify
        if id_failed > 0 and nut_failed == 0:
            status = "IDENTITY_GATE_FAILED"
        elif nut_failed > 0:
            status = "NUTRITION_GATE_FAILED"
        else:
            status = "NEEDS_NEW_CONCEPT"
        return {
            "status": status,
            "leaf_idx": -1,
            "score": 0.0,
            "id_rejects": id_failed,
            "nut_rejects": nut_failed,
        }

    survivors.sort(reverse=True)
    s, j, text_sim, nut_prox = survivors[0]
    if s >= CONFIDENT_THRESHOLD:
        status = "CONFIDENT"
    elif s >= LOW_CONFIDENCE_THRESHOLD:
        status = "LOW_CONFIDENCE"
    else:
        status = "BELOW_THRESHOLD"
    return {
        "status": status,
        "leaf_idx": j,
        "score": s,
        "text_sim": text_sim,
        "nut_prox": nut_prox if np.isfinite(nut_prox) else None,
        "id_rejects": id_failed,
        "nut_rejects": nut_failed,
        "n_survivors": len(survivors),
    }


# ---------- run ----------


def main() -> int:
    products = load_products()
    leaves = load_leaves_with_nutrition()

    # align row order to embedding cache
    log("loading product embeddings cache")
    p_emb = np.load(PRODUCT_EMB_CACHE)
    corpus = pd.read_parquet(PRODUCT_CORPUS, columns=["gtin_upc", "row_id"])
    log(f"  cache shape {p_emb.shape}; corpus {len(corpus):,}")

    # rebuild products in cache row order — dedup to match cache shape exactly
    products = (
        corpus.merge(products.drop_duplicates(subset=["gtin_upc"]), on="gtin_upc", how="left")
        .drop_duplicates(subset=["row_id"])
        .reset_index(drop=True)
    )
    assert len(products) == len(p_emb), f"product/emb mismatch {len(products)} vs {len(p_emb)}"
    log(f"  aligned products to cache order: {len(products):,}")

    leaf_emb = embed_leaves(leaves)

    knn_idx_path = OUT / "knn_idx.npy"
    knn_sc_path = OUT / "knn_scores.npy"
    if knn_idx_path.exists() and knn_sc_path.exists():
        log("loading cached kNN tables")
        all_idx = np.load(knn_idx_path)
        all_scores = np.load(knn_sc_path)
        n = len(p_emb)
        # skip the search loop
        log(f"  cached kNN: {all_idx.shape}")
        # need a no-op replacement for the loop below
        skip_knn = True
    else:
        skip_knn = False

    import gc

    # free memory before the big search
    del corpus
    gc.collect()

    if not skip_knn:
        log(f"manual numpy kNN k={KNN_K} products → leaves")
        leaf_emb_T = np.ascontiguousarray(leaf_emb.T)
        chunk = 256
        n = len(p_emb)
        all_scores = np.empty((n, KNN_K), dtype=np.float32)
        all_idx = np.empty((n, KNN_K), dtype=np.int32)
        t0 = time.time()
        for i0 in range(0, n, chunk):
            i1 = min(i0 + chunk, n)
            sims = p_emb[i0:i1] @ leaf_emb_T
            part = np.argpartition(-sims, KNN_K, axis=1)[:, :KNN_K]
            rows = np.arange(part.shape[0])[:, None]
            part_scores = sims[rows, part]
            order = np.argsort(-part_scores, axis=1)
            all_idx[i0:i1] = part[rows, order]
            all_scores[i0:i1] = part_scores[rows, order]
            del sims, part, part_scores, order
            if (i0 // chunk) % 100 == 0:
                log(f"  kNN {i1:>8,}/{n:,} ({100*i1/n:.1f}%) elapsed {(time.time()-t0)/60:.1f} min")
        log(f"  kNN done in {(time.time()-t0)/60:.1f} min")
        np.save(knn_idx_path, all_idx)
        np.save(knn_sc_path, all_scores)
        log(f"  saved kNN tables to disk for resume")

    align_pkl = OUT / "align_results.pkl"
    if align_pkl.exists():
        log(f"loading cached align results from {align_pkl}")
        import pickle

        with open(align_pkl, "rb") as f:
            results = pickle.load(f)
    else:
        log("aligning per-product with identity + nutrition gates")
        results = []
        t0 = time.time()
        for p_idx in range(n):
            r = align_one(p_idx, products, leaves, all_idx[p_idx], all_scores[p_idx])
            r["p_idx"] = p_idx
            results.append(r)
            if p_idx and p_idx % 20000 == 0:
                log(f"  align {p_idx:>8,}/{n:,} ({100*p_idx/n:.1f}%) elapsed {(time.time()-t0)/60:.1f} min")
        log(f"  align done in {(time.time()-t0)/60:.1f} min")
        import pickle

        with open(align_pkl, "wb") as f:
            pickle.dump(results, f)
        log(f"  cached align results to {align_pkl}")

    log("building output dataframe")
    res_df = pd.DataFrame(results)
    res_df = res_df.merge(
        products.reset_index(drop=True)[
            [
                "gtin_upc",
                "fdc_id",
                "description",
                "brand_name",
                "branded_food_category",
                "identity_terms",
            ]
        ].assign(p_idx=range(n)),
        on="p_idx",
        how="left",
    )

    # attach leaf info
    leaf_keep = leaves[["leaf_id", "head", "canonical_name", "esha_code", "esha_desc", "fndds_code", "fndds_desc", "sr28_code", "sr28_desc"]].reset_index().rename(columns={"index": "leaf_idx"})
    res_df = res_df.merge(leaf_keep, on="leaf_idx", how="left")

    out_cols = [
        "gtin_upc",
        "fdc_id",
        "description",
        "brand_name",
        "branded_food_category",
        "identity_terms",
        "status",
        "score",
        "text_sim",
        "nut_prox",
        "id_rejects",
        "nut_rejects",
        "n_survivors",
        "leaf_id",
        "head",
        "canonical_name",
        "esha_code",
        "esha_desc",
        "fndds_code",
        "fndds_desc",
        "sr28_code",
        "sr28_desc",
    ]
    res_df[out_cols].to_csv(OUT / "product_to_anchor_v2.csv", index=False)
    log(f"  wrote {OUT / 'product_to_anchor_v2.csv'}  rows={len(res_df):,}")

    # summary
    summary = {
        "n_products": int(n),
        "status_counts": res_df["status"].value_counts().to_dict(),
        "score_describe": {k: float(v) for k, v in res_df["score"].describe().to_dict().items()},
        "n_with_esha": int(res_df["esha_code"].notna().sum()),
        "n_with_fndds": int(res_df["fndds_code"].notna().sum()),
        "n_with_sr28": int(res_df["sr28_code"].notna().sum()),
        "n_with_all_three": int(
            (res_df["esha_code"].notna() & res_df["fndds_code"].notna() & res_df["sr28_code"].notna()).sum()
        ),
    }
    (OUT / "summary_v2.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))

    # auto-audit known-bad cases
    log("auto-audit on user's hand-found failures")
    audit_queries = [
        "EGG NOG",
        "ULTRA-FILTERED NONFAT MILK",
        "HALF & HALF",
        "GRACE EVAPORATED FILLED MILK",
        "CHICKEN SALAD",
        "TUNA SALAD",
        "Apple Jacks",
        "Froot Loops",
        "All-Bran",
        "HABANERO PEPPER JELLY",
        "BABY KALE",
        "NEW YORK STYLE CHEESECAKE",
        "STRAWBERRY CHEESECAKE",
        "CHERRY PIE",
    ]
    audit = {}
    for q in audit_queries:
        mask = res_df["description"].astype(str).str.contains(q, case=False, na=False)
        rows = res_df[mask].head(3)
        audit[q] = rows[
            [
                "description",
                "status",
                "score",
                "head",
                "canonical_name",
                "esha_code",
                "esha_desc",
                "fndds_code",
                "fndds_desc",
            ]
        ].to_dict(orient="records")
        print(f"\n--- {q} ---")
        for r in audit[q]:
            print(
                f"  {r['description'][:80]!r}\n"
                f"    status={r['status']} score={r['score']:.3f}"
                f"\n    head={r['head']!r}  canonical={r['canonical_name']!r}"
                f"\n    esha={r['esha_code']}/{r['esha_desc']!r}"
                f"\n    fndds={r['fndds_code']}/{r['fndds_desc']!r}"
            )
    (OUT / "audit_v2.json").write_text(json.dumps(audit, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
