#!/usr/bin/env python3
"""
Stage A — generate the human-review decision sheet for outlier clusters.

For each cluster of 5+ outliers (grouped by current_esha_code + category):
  - Compute cluster centroid embedding (mean of member product embeddings)
  - Find top-3 alternative ESHA cohorts whose centroid is closest, prioritizing
    cohorts whose majority category matches the cluster's category
  - Output one row per cluster with sample products and decision columns

User reviews ~381 rows in a spreadsheet, fills decision column → bulk apply.

Output:
  outlier_decision_sheet.csv
"""
import csv, pickle, sys
from collections import Counter, defaultdict
import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v3.csv"
OUTLIERS = f"{ROOT}/implementation/output/outliers_filtered.csv"
CACHE_DIR = f"{ROOT}/implementation/.embed_cache"
PROD_EMB = f"{CACHE_DIR}/prod_emb.npy"
PROD_IDS = f"{CACHE_DIR}/prod_ids.npy"
TREE_CODES = f"{CACHE_DIR}/tree_codes.pkl"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"

OUT = f"{ROOT}/implementation/output/outlier_decision_sheet.csv"
MIN_CLUSTER = 5

def main():
    print("Loading map...", flush=True)
    rows = list(csv.DictReader(open(INPUT_MAP)))
    print(f"  {len(rows):,} rows")

    print("Loading cached embeddings + tree...", flush=True)
    prod_emb = np.load(PROD_EMB)
    prod_ids = np.load(PROD_IDS, allow_pickle=True)
    fdc_to_idx = {str(p): i for i, p in enumerate(prod_ids)}
    with open(TREE_CODES, "rb") as f: tree_codes = pickle.load(f)
    code_to_desc = {c: d for c, d in tree_codes}

    # Build cohort centroids using current v3 cohorts
    print("Computing cohort centroids...", flush=True)
    code_to_idx = defaultdict(list)
    for i, r in enumerate(rows):
        if r["best_esha_code"]:
            code_to_idx[r["best_esha_code"]].append(i)
    clusterable = [c for c, idx in code_to_idx.items() if len(idx) >= MIN_CLUSTER]
    centroids = {}     # code -> normalized centroid
    maj_cat = {}; maj_share = {}
    for c in clusterable:
        idxs = code_to_idx[c]
        embs = [prod_emb[fdc_to_idx[rows[ri]["fdc_id"]]] for ri in idxs
                if rows[ri]["fdc_id"] in fdc_to_idx]
        if not embs: continue
        centroid = np.mean(embs, axis=0)
        n = np.linalg.norm(centroid) + 1e-12
        centroids[c] = centroid / n
        cats = Counter(rows[ri]["branded_food_category"] for ri in idxs)
        cat, cn = cats.most_common(1)[0]
        maj_cat[c] = cat
        maj_share[c] = cn / len(idxs)
    print(f"  centroids: {len(centroids):,} cohorts")

    # Pre-stack centroids for fast scoring
    code_list = [c for c in centroids]
    cent_mat = np.stack([centroids[c] for c in code_list])  # (n_codes, d)

    # Load outliers and group into clusters by (current_code, category)
    print("Loading outliers and clustering...", flush=True)
    outliers = list(csv.DictReader(open(OUTLIERS)))
    cluster_buckets = defaultdict(list)   # (code, cat) -> [outlier rows]
    for o in outliers:
        cluster_buckets[(o["esha_code"], o["branded_food_category"])].append(o)
    big_clusters = [(k, v) for k, v in cluster_buckets.items() if len(v) >= MIN_CLUSTER]
    big_clusters.sort(key=lambda kv: -len(kv[1]))
    print(f"  {len(big_clusters):,} clusters with N>={MIN_CLUSTER}")
    total_products_in_clusters = sum(len(v) for _, v in big_clusters)
    print(f"  total products in those clusters: {total_products_in_clusters:,}")

    # For each cluster: cluster centroid → top-3 alt cohorts (category-filtered + open)
    print("Scoring suggestions per cluster...", flush=True)
    decisions = []
    for (cur_code, cur_cat), members in big_clusters:
        # Cluster centroid
        embs = [prod_emb[fdc_to_idx[m["fdc_id"]]] for m in members
                if m["fdc_id"] in fdc_to_idx]
        if not embs: continue
        cluster_centroid = np.mean(embs, axis=0)
        n = np.linalg.norm(cluster_centroid) + 1e-12
        cluster_centroid /= n

        # Score against ALL cohort centroids
        sims = cent_mat @ cluster_centroid     # (n_codes,)

        # Mask out current code
        cur_mask = np.array([c != cur_code for c in code_list], dtype=bool)
        # Category-aligned candidates first
        cat_aligned = np.array([(maj_cat.get(c) == cur_cat and maj_share.get(c, 0) >= 0.4)
                                for c in code_list], dtype=bool)

        def topk(mask, k=3):
            scored = np.where(mask, sims, -2.0)
            top = np.argsort(-scored)[:k]
            return [(code_list[i], float(scored[i])) for i in top if scored[i] > -1.5]

        cat_top = topk(cat_aligned & cur_mask, 3)
        open_top = topk(cur_mask, 3)

        # Build row
        sample_prods = " | ".join(m["product_description"][:55] for m in members[:3])
        sample_ids = " | ".join(m["fdc_id"] for m in members[:5])

        row = {
            "cluster_size": len(members),
            "current_code": cur_code,
            "current_desc": members[0]["esha_desc"][:80],
            "current_category": cur_cat[:40],
            "sample_products": sample_prods,
            "sample_fdc_ids": sample_ids,

            "suggest1_code":   cat_top[0][0] if cat_top else "",
            "suggest1_desc":   code_to_desc.get(cat_top[0][0], "")[:60] if cat_top else "",
            "suggest1_sim":    f"{cat_top[0][1]:.3f}" if cat_top else "",

            "suggest2_code":   cat_top[1][0] if len(cat_top) > 1 else "",
            "suggest2_desc":   code_to_desc.get(cat_top[1][0], "")[:60] if len(cat_top) > 1 else "",
            "suggest2_sim":    f"{cat_top[1][1]:.3f}" if len(cat_top) > 1 else "",

            "suggest3_code":   cat_top[2][0] if len(cat_top) > 2 else "",
            "suggest3_desc":   code_to_desc.get(cat_top[2][0], "")[:60] if len(cat_top) > 2 else "",
            "suggest3_sim":    f"{cat_top[2][1]:.3f}" if len(cat_top) > 2 else "",

            "openTop_code":    open_top[0][0] if open_top else "",
            "openTop_desc":    code_to_desc.get(open_top[0][0], "")[:60] if open_top else "",
            "openTop_sim":     f"{open_top[0][1]:.3f}" if open_top else "",

            # ----- DECISION COLUMNS (you fill in) -----
            "decision":         "",     # accept|replace|new_leaf|skip
            "replace_code":     "",     # if decision=replace, put code here
            "notes":            "",
        }
        decisions.append(row)

    # Write
    cols = ["cluster_size","current_code","current_desc","current_category",
            "sample_products","sample_fdc_ids",
            "suggest1_code","suggest1_desc","suggest1_sim",
            "suggest2_code","suggest2_desc","suggest2_sim",
            "suggest3_code","suggest3_desc","suggest3_sim",
            "openTop_code","openTop_desc","openTop_sim",
            "decision","replace_code","notes"]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for d in decisions: w.writerow(d)

    print(f"\nWrote {OUT}")
    print(f"  {len(decisions):,} cluster decisions to make")
    print(f"  {sum(d['cluster_size'] for d in decisions):,} products covered by these decisions")

    # Quick preview of top 12 for stdout
    print(f"\nTop 12 clusters by size (preview):")
    for d in sorted(decisions, key=lambda x: -x["cluster_size"])[:12]:
        s1 = f"  → suggest [{d['suggest1_code']}] {d['suggest1_desc'][:40]} (sim={d['suggest1_sim']})" if d["suggest1_code"] else "  → no category-aligned suggestion"
        print(f"\n  cluster: {d['cluster_size']:>3}× in [{d['current_code']}] {d['current_desc'][:50]}")
        print(f"    cat:    {d['current_category']}")
        print(f"    examples: {d['sample_products']}")
        print(s1)

if __name__ == "__main__":
    main()
