#!/usr/bin/env python3
"""
Embedding-based outlier detection. PURE IDENTIFICATION, NO FIX.

For each ESHA code with N>=5 products:
  1. Embed each product (description + brand) using all-MiniLM-L6-v2 (384-dim).
  2. Compute the cohort centroid (mean of normalized embeddings).
  3. Score each product = 1 - cosine(product_embedding, cohort_centroid)
  4. Z-score within cohort. Products with z >= THRESHOLD are outliers.
  5. Also score similarity to the ESHA tree description embedding for context.

Outputs:
  embed_outliers.csv          — ranked outliers with all signals
  embed_outliers_summary.md   — top dumping grounds by outlier % and count

Caching:
  Product embeddings cached to /tmp/.../prod_embeddings.npy + .ids.npy so
  reruns skip the 8-min embed step.
"""
import csv, os, sys, time, hashlib, pickle
from collections import Counter, defaultdict
import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v2.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
CACHE_DIR = f"{ROOT}/implementation/.embed_cache"
OUT_CSV = f"{ROOT}/implementation/output/embed_outliers.csv"
OUT_MD = f"{ROOT}/implementation/output/embed_outliers_summary.md"

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MIN_COHORT = 5
ZSCORE_THRESHOLD = 1.5
BATCH = 256

os.makedirs(CACHE_DIR, exist_ok=True)
PROD_EMB = f"{CACHE_DIR}/prod_emb.npy"
PROD_IDS = f"{CACHE_DIR}/prod_ids.npy"
TREE_EMB = f"{CACHE_DIR}/tree_emb.npy"
TREE_CODES = f"{CACHE_DIR}/tree_codes.pkl"

def main():
    print(f"Reading {INPUT}...", flush=True)
    rows = []
    with open(INPUT) as f:
        for r in csv.DictReader(f):
            rows.append(r)
    print(f"  {len(rows):,} rows", flush=True)

    # Build the text we'll embed per product
    # description + brand → semantic identity
    def text_for(r):
        desc = r["product_description"] or ""
        brand = r["brand_name"] or ""
        cat = r["branded_food_category"] or ""
        # category provides class context the LLM also gets
        s = f"{desc} {brand} ({cat})".strip()
        return s if s else "unknown"
    texts = [text_for(r) for r in rows]
    fdc_ids = [r["fdc_id"] for r in rows]

    # ---- 1. Embed products (with cache)
    if os.path.exists(PROD_EMB) and os.path.exists(PROD_IDS):
        cached_ids = np.load(PROD_IDS, allow_pickle=True)
        if len(cached_ids) == len(fdc_ids) and (cached_ids == np.array(fdc_ids)).all():
            print("Loading cached product embeddings...", flush=True)
            prod_emb = np.load(PROD_EMB)
        else:
            cached_ids = None
            prod_emb = None
    else:
        prod_emb = None

    if prod_emb is None:
        print(f"Embedding {len(texts):,} products with {MODEL}...", flush=True)
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL, device="cpu")
        t0 = time.time()
        prod_emb = model.encode(
            texts, batch_size=BATCH, show_progress_bar=True,
            convert_to_numpy=True, normalize_embeddings=True
        )
        print(f"  done in {time.time()-t0:.0f}s, shape={prod_emb.shape}", flush=True)
        np.save(PROD_EMB, prod_emb)
        np.save(PROD_IDS, np.array(fdc_ids, dtype=object), allow_pickle=True)
        print(f"  cached to {PROD_EMB}", flush=True)

    # ---- 2. Embed tree descriptions (with cache)
    print(f"Loading ESHA tree...", flush=True)
    tree = []
    with open(TREE) as f:
        for r in csv.DictReader(f):
            tree.append((r["EshaCode"], r["Description"]))
    if os.path.exists(TREE_EMB) and os.path.exists(TREE_CODES):
        with open(TREE_CODES, "rb") as f: cached_codes = pickle.load(f)
        if cached_codes == tree:
            tree_emb = np.load(TREE_EMB)
        else:
            tree_emb = None
    else:
        tree_emb = None

    if tree_emb is None:
        print(f"Embedding {len(tree):,} ESHA tree descriptions...", flush=True)
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL, device="cpu")
        descs = [d for _, d in tree]
        tree_emb = model.encode(descs, batch_size=BATCH, show_progress_bar=True,
                                convert_to_numpy=True, normalize_embeddings=True)
        np.save(TREE_EMB, tree_emb)
        with open(TREE_CODES, "wb") as f: pickle.dump(tree, f)
    code_to_idx_in_tree = {c: i for i, (c, _) in enumerate(tree)}

    # ---- 3. Group rows by ESHA code
    print("Grouping by ESHA code...", flush=True)
    code_to_idx = defaultdict(list)
    for i, r in enumerate(rows):
        c = r["best_esha_code"]
        if c: code_to_idx[c].append(i)
    clusterable = {c: idx for c, idx in code_to_idx.items() if len(idx) >= MIN_COHORT}
    print(f"  {len(clusterable):,} cohorts with N>={MIN_COHORT}", flush=True)

    # ---- 4. Per-cohort centroids and scoring
    print("Scoring outliers...", flush=True)
    outliers = []
    code_stats = {}
    t0 = time.time()
    n_done = 0
    for code, idxs in clusterable.items():
        n_done += 1
        emb = prod_emb[idxs]                      # (n, d)
        centroid = emb.mean(axis=0)
        cnorm = np.linalg.norm(centroid) + 1e-12
        centroid_n = centroid / cnorm
        # cosine similarity (embeddings already normalized → just dot)
        sim_to_centroid = emb @ centroid_n         # (n,)
        dist = 1.0 - sim_to_centroid
        mu = dist.mean(); sd = dist.std() + 1e-9
        z = (dist - mu) / sd

        # Tree description similarity (if tree code exists)
        sim_to_tree = None
        if code in code_to_idx_in_tree:
            t_emb = tree_emb[code_to_idx_in_tree[code]]
            sim_to_tree = emb @ t_emb              # (n,)

        # Cohort majority category for human readability
        cat_ctr = Counter(rows[i]["branded_food_category"] for i in idxs)
        majority_cat, mc_n = cat_ctr.most_common(1)[0]
        majority_share = mc_n / len(idxs)

        n_out = 0
        for j, i in enumerate(idxs):
            if z[j] < ZSCORE_THRESHOLD:
                continue
            r = rows[i]
            cat_mismatch = (r["branded_food_category"] != majority_cat) and (majority_share >= 0.4)
            outliers.append({
                "esha_code": code,
                "esha_desc": r["best_esha_description"],
                "fdc_id": r["fdc_id"],
                "product_description": r["product_description"],
                "brand_name": r["brand_name"],
                "branded_food_category": r["branded_food_category"],
                "rft_verdict": r.get("rft_verdict",""),
                "cohort_size": len(idxs),
                "cohort_majority_category": majority_cat,
                "cohort_majority_share": round(majority_share, 2),
                "category_mismatch": int(cat_mismatch),
                "sim_to_cohort_centroid": round(float(sim_to_centroid[j]), 4),
                "centroid_distance": round(float(dist[j]), 4),
                "centroid_zscore": round(float(z[j]), 2),
                "sim_to_tree_description": (round(float(sim_to_tree[j]), 4) if sim_to_tree is not None else ""),
                "outlier_score": round(float(z[j]) + (0.5 if cat_mismatch else 0), 2),
            })
            n_out += 1
        code_stats[code] = {
            "n": len(idxs), "n_out": n_out,
            "pct": round(n_out/len(idxs)*100, 1),
            "esha_desc": rows[idxs[0]]["best_esha_description"],
            "majority_cat": majority_cat,
        }
        if n_done % 1000 == 0 or n_done == len(clusterable):
            print(f"  scored {n_done:,}/{len(clusterable):,} cohorts ({len(outliers):,} outliers)",
                  flush=True)
    print(f"\nDone in {time.time()-t0:.0f}s. Total outliers: {len(outliers):,}", flush=True)

    # Write outliers CSV
    print(f"Writing {OUT_CSV}...", flush=True)
    cols = ["esha_code","esha_desc","fdc_id","product_description","brand_name",
            "branded_food_category","rft_verdict",
            "cohort_size","cohort_majority_category","cohort_majority_share",
            "category_mismatch",
            "sim_to_cohort_centroid","centroid_distance","centroid_zscore",
            "sim_to_tree_description","outlier_score"]
    outliers.sort(key=lambda o: -o["outlier_score"])
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for o in outliers: w.writerow(o)

    # Summary
    by_pct = sorted(code_stats.items(), key=lambda kv: (-kv[1]["pct"], -kv[1]["n_out"]))
    by_n   = sorted(code_stats.items(), key=lambda kv: -kv[1]["n_out"])
    with open(OUT_MD, "w") as f:
        f.write(f"# Embedding-based outlier scan summary\n\n")
        f.write(f"- Model: {MODEL}\n")
        f.write(f"- Cohorts: **{len(code_stats):,}**\n")
        f.write(f"- Outliers flagged: **{len(outliers):,}**\n")
        f.write(f"- Z-score threshold: {ZSCORE_THRESHOLD}\n\n")
        f.write(f"## Top 30 cohorts by % outlier (size>=20)\n\n")
        f.write("| code | description | size | outliers | % | majority cat |\n|---|---|---:|---:|---:|---|\n")
        big = [(c, s) for c, s in by_pct if s["n"] >= 20]
        for code, s in big[:30]:
            f.write(f"| {code} | {s['esha_desc'][:55]} | {s['n']:,} | {s['n_out']:,} | {s['pct']}% | {s['majority_cat'][:25]} |\n")
        f.write(f"\n## Top 20 by absolute outlier count\n\n")
        f.write("| code | description | size | outliers | % |\n|---|---|---:|---:|---:|\n")
        for code, s in by_n[:20]:
            f.write(f"| {code} | {s['esha_desc'][:55]} | {s['n']:,} | {s['n_out']:,} | {s['pct']}% |\n")
    print(f"Wrote {OUT_MD}")

if __name__ == "__main__":
    main()
