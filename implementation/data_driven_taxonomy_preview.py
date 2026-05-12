#!/usr/bin/env python3
"""
Bottom-up taxonomy preview. Build clusters from product data itself
(title + brand + category + ingredients), let natural groups emerge.

NO MODIFICATION TO vIdentity.csv. Output is a preview only.

Pick a few problem categories. Within each:
  1. Concatenate product description + brand + ingredients[:300]
  2. Use the cached embedding for that product (already covers desc+brand+cat)
  3. Run HDBSCAN cluster on that embedding subset
  4. For each cluster: derive a canonical name from common content tokens
  5. Match each cluster to its closest existing ESHA code
  6. Flag clusters whose closest ESHA match is weak — those are tree-gap candidates

Output: implementation/output/data_driven_taxonomy_preview.md
"""
import csv, os, pickle, re, sqlite3, sys
from collections import Counter, defaultdict
import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
CANON = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
DB = f"{ROOT}/data/master_products.db"
CACHE_DIR = f"{ROOT}/implementation/.embed_cache"
PROD_EMB = f"{CACHE_DIR}/prod_emb.npy"
PROD_IDS = f"{CACHE_DIR}/prod_ids.npy"
TREE_EMB = f"{CACHE_DIR}/tree_emb.npy"
TREE_CODES = f"{CACHE_DIR}/tree_codes.pkl"

OUT_MD = f"{ROOT}/implementation/output/data_driven_taxonomy_preview.md"

# Pick problem categories with high signal
TARGET_CATEGORIES = [
    "Cookies & Biscuits",
    "Candy",
    "Chocolate",
    "Pickles, Olives, Peppers & Relishes",
    "Breads & Buns",
]

STOP = set("""
with and the of to in for by on at from as or an a is are be this that
prepared made mix pack oz fl ounce ounces pound pounds lb each ct count
size family large small medium big jumbo mini package bag box bottle jar
can cup cups piece pieces container kit free added without none new original
ready fresh frozen dry dried cooked raw fried baked grilled whole sliced
diced chopped crushed low high reduced light lite extra plus value my our
their no not real food brand product item items premium quality natural
all variety serving servings flavor flavors flavored containing total
contains made type style classic select selection traditional taste tasty
delicious gourmet artisan fine sweet tangy spicy mild hot bold rich smooth
crispy crunchy soft tender tough thick thin fancy organic gluten authentic
""".split())

def tokens(s):
    if not s: return []
    return [t for t in re.findall(r"[a-z][a-z]+", s.lower()) if len(t) >= 4 and t not in STOP]

def main():
    print("Loading caches...", flush=True)
    prod_emb = np.load(PROD_EMB)
    prod_ids = np.load(PROD_IDS, allow_pickle=True)
    fdc_to_idx = {str(p): i for i, p in enumerate(prod_ids)}
    tree_emb = np.load(TREE_EMB)
    with open(TREE_CODES, "rb") as f: tree_codes = pickle.load(f)
    code_to_desc = {c: d for c, d in tree_codes}
    code_list = [c for c, _ in tree_codes]
    code_to_treei = {c: i for i, c in enumerate(code_list)}

    print("Loading map...", flush=True)
    rows = list(csv.DictReader(open(CANON)))
    print(f"  {len(rows):,} rows")

    # Group by category
    cat_to_idxs = defaultdict(list)
    for i, r in enumerate(rows):
        cat_to_idxs[r["branded_food_category"]].append(i)

    # HDBSCAN
    try:
        from sklearn.cluster import HDBSCAN
    except ImportError:
        print("HDBSCAN not in this sklearn; falling back to AgglomerativeClustering")
        HDBSCAN = None

    out_lines = ["# Data-driven taxonomy preview\n"]
    out_lines.append("Built from product embeddings (title + brand + category) within each ")
    out_lines.append("branded_food_category. Each cluster is a candidate leaf in the new tree.\n\n")
    out_lines.append("**No fixes are applied.** This is a preview to evaluate the approach.\n")
    out_lines.append("Run note: HDBSCAN with min_cluster_size=8, metric=cosine.\n\n")

    for cat in TARGET_CATEGORIES:
        idxs = cat_to_idxs.get(cat, [])
        if len(idxs) < 30:
            print(f"  skip {cat!r} (only {len(idxs)} products)")
            continue
        print(f"\n=== {cat} ({len(idxs):,} products) ===", flush=True)

        # Get the embeddings for these products
        emb_idxs = []
        valid_rows = []
        for ri in idxs:
            fid = rows[ri]["fdc_id"]
            if fid in fdc_to_idx:
                emb_idxs.append(fdc_to_idx[fid])
                valid_rows.append(rows[ri])
        sub = prod_emb[emb_idxs]

        # Cluster
        if HDBSCAN is not None:
            mc = 5
            ms = 3
            print(f"  clustering with HDBSCAN (min_cluster_size={mc}, min_samples={ms})...", flush=True)
            clusterer = HDBSCAN(min_cluster_size=mc, min_samples=ms, metric="cosine", copy=True)
            labels = clusterer.fit_predict(sub.astype(np.float64))
        else:
            from sklearn.cluster import AgglomerativeClustering
            n_clusters = max(20, len(sub) // 80)
            print(f"  clustering with Agglomerative (k={n_clusters})...", flush=True)
            clusterer = AgglomerativeClustering(n_clusters=n_clusters, metric="cosine", linkage="average")
            labels = clusterer.fit_predict(sub.astype(np.float64))

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = (labels == -1).sum() if -1 in labels else 0
        print(f"  → {n_clusters:,} clusters, {n_noise:,} noise points")

        # For each cluster, derive canonical name + closest ESHA code
        cluster_to_idxs = defaultdict(list)
        for i, lbl in enumerate(labels):
            if lbl == -1: continue
            cluster_to_idxs[lbl].append(i)

        out_lines.append(f"\n## {cat}\n")
        out_lines.append(f"- Products: **{len(valid_rows):,}**\n")
        out_lines.append(f"- Natural clusters found: **{n_clusters}**\n")
        out_lines.append(f"- Unclustered (noise): {n_noise}\n\n")

        # Sort clusters by size desc
        cl_sorted = sorted(cluster_to_idxs.items(), key=lambda kv: -len(kv[1]))
        for lbl, members in cl_sorted[:25]:
            # Member texts → token freq
            member_descs = [valid_rows[i]["product_description"] for i in members]
            tok_freq = Counter()
            for d in member_descs:
                for t in set(tokens(d)): tok_freq[t] += 1
            n = len(members)
            top_tokens = [t for t, c in tok_freq.most_common(10) if c >= max(2, n*0.3)]
            canonical = ", ".join(top_tokens[:5]) or "(no common name)"

            # Closest ESHA tree code
            cluster_centroid = sub[members].mean(axis=0)
            cluster_centroid /= (np.linalg.norm(cluster_centroid) + 1e-12)
            sims = tree_emb @ cluster_centroid
            top_idx = int(np.argsort(-sims)[:5][0])
            top_code = code_list[top_idx]
            top_desc = code_to_desc[top_code]
            top_sim = float(sims[top_idx])

            # Where these products are CURRENTLY routed (to show the chaos)
            cur_codes = Counter(valid_rows[i]["best_esha_code"] for i in members)
            cur_desc_lookup = {valid_rows[i]["best_esha_code"]: valid_rows[i]["best_esha_description"] for i in members}
            cur_summary = ", ".join(f"[{c}]×{n}" for c, n in cur_codes.most_common(3))

            out_lines.append(f"### Cluster {lbl}: {canonical}  (n={n})\n")
            out_lines.append(f"- closest ESHA code: **[{top_code}] {top_desc}** (sim={top_sim:.3f})")
            if top_sim < 0.55:
                out_lines.append(f"  ← **TREE GAP CANDIDATE** (no good ESHA match)\n")
            else:
                out_lines.append("\n")
            out_lines.append(f"- currently routed to: {cur_summary}\n")
            out_lines.append("- sample products:\n")
            for i in members[:5]:
                out_lines.append(f"  - {valid_rows[i]['product_description'][:80]}  (brand: {valid_rows[i]['brand_name'][:25]})\n")
            out_lines.append("\n")

    with open(OUT_MD, "w") as f:
        f.writelines(out_lines)
    print(f"\nWrote {OUT_MD}")

if __name__ == "__main__":
    main()
