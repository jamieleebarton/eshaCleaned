#!/usr/bin/env python3
"""
No-LLM outlier scan: for each ESHA code with N>=5 products, find products that
look out of place using three free signals:

  1. INGREDIENT DISTANCE: TF-IDF on the ingredient list, cohort centroid,
     cosine distance per product. High distance == ingredients differ from peers.
  2. CATEGORY DISAGREEMENT: branded_food_category mismatch with cohort majority.
  3. FNDDS DISAGREEMENT: rft_fndds_code mismatch with cohort majority (when available).

Composite outlier score:
    score = 1.0 * ingredient_distance_zscore
          + 0.7 * (1 if category_mismatch else 0)
          + 0.7 * (1 if fndds_mismatch else 0)
          + 0.3 * (1 if rft_verdict in {NEEDS_NEW_CONCEPT, WEAK, NO_MATCH} else 0)

Outliers = score > 1.5 (tuned on small cohorts).

Output:
  cohort_outliers_per_code.csv   — one row per flagged outlier with all signals
  cohort_outlier_summary.md      — code-level rollup (top dumping grounds by % outlier)
"""
import csv, sys, os, time
from collections import Counter, defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy import sparse

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v2.csv"
DB = f"{ROOT}/data/master_products.db"
OUT_CSV = f"{ROOT}/implementation/output/cohort_outliers_per_code.csv"
OUT_MD = f"{ROOT}/implementation/output/cohort_outlier_summary.md"

MIN_COHORT_SIZE = 5
SCORE_THRESHOLD = 1.5

def main():
    print(f"Reading {INPUT}...", flush=True)
    rows = []
    with open(INPUT) as f:
        for r in csv.DictReader(f):
            rows.append(r)
    print(f"  {len(rows):,} rows", flush=True)

    # Pull ingredients from sqlite (faster than per-row joins)
    print("Loading ingredients from master_products.db...", flush=True)
    import sqlite3
    con = sqlite3.connect(DB)
    ing_map = {}
    for fdc_id, ing in con.execute("SELECT fdc_id, ingredients FROM products"):
        if ing: ing_map[str(fdc_id)] = ing
    con.close()
    print(f"  ingredients for {len(ing_map):,} products", flush=True)

    # Group by ESHA code
    groups = defaultdict(list)
    for r in rows:
        c = r["best_esha_code"]
        if c: groups[c].append(r)

    # Filter to clusterable cohorts
    clusterable = {c: g for c, g in groups.items() if len(g) >= MIN_COHORT_SIZE}
    print(f"  {len(clusterable):,} cohorts with N>={MIN_COHORT_SIZE}", flush=True)

    # Build a global TF-IDF on ingredients of clusterable rows only (memory)
    # Use word tokenization, drop stopwords/numbers; keeps signal strong.
    indexed_rows = []
    docs = []
    for c, grp in clusterable.items():
        for r in grp:
            ing = ing_map.get(r["fdc_id"], "")
            if not ing: ing = ""
            indexed_rows.append((c, r))
            docs.append(ing.lower())

    print(f"Building TF-IDF over {len(docs):,} ingredient strings...", flush=True)
    t0 = time.time()
    vec = TfidfVectorizer(
        analyzer="word", ngram_range=(1,1),
        min_df=5, max_df=0.5, max_features=20000, sublinear_tf=True,
        token_pattern=r"[A-Za-z][A-Za-z]{2,}",
    )
    X = vec.fit_transform(docs)
    print(f"  matrix: {X.shape}, dtype={X.dtype}, {time.time()-t0:.1f}s", flush=True)

    # Index rows by code
    print("Indexing cohort positions...", flush=True)
    code_to_positions = defaultdict(list)
    for i, (c, r) in enumerate(indexed_rows):
        code_to_positions[c].append(i)

    # For each cohort: centroid, distances, z-scores
    print("Scoring outliers per cohort...", flush=True)
    outliers = []
    code_stats = {}  # code -> (n, n_outliers, top_outlier_score)
    t0 = time.time()
    n_codes = len(code_to_positions)
    code_iter = sorted(code_to_positions.items(), key=lambda kv: -len(kv[1]))

    for idx, (code, positions) in enumerate(code_iter):
        sub = X[positions]                                      # (n, F)
        centroid = sparse.csr_matrix(sub.mean(axis=0))          # (1, F)
        # cosine similarity, then convert to distance
        # dot/(||sub||*||centroid||)
        sub_norm = np.sqrt(sub.multiply(sub).sum(axis=1)).A1 + 1e-12
        cen_norm = float(np.sqrt(centroid.multiply(centroid).sum())) + 1e-12
        dots = (sub @ centroid.T).toarray().ravel()
        sim = dots / (sub_norm * cen_norm)
        dist = 1.0 - sim
        # z-score within cohort
        mu = dist.mean(); sd = dist.std() + 1e-9
        z = (dist - mu) / sd

        # Cohort majority category and FNDDS code
        cat_ctr = Counter(indexed_rows[p][1]["branded_food_category"] for p in positions)
        cat_majority, cat_majority_n = cat_ctr.most_common(1)[0]
        cat_majority_share = cat_majority_n / len(positions)
        fndds_ctr = Counter(indexed_rows[p][1].get("rft_fndds_code","") for p in positions
                             if indexed_rows[p][1].get("rft_fndds_code"))
        fndds_majority = fndds_ctr.most_common(1)[0][0] if fndds_ctr else ""
        fndds_majority_share = (fndds_ctr.most_common(1)[0][1] / len(positions)) if fndds_ctr else 0

        n_out = 0
        for j, pos in enumerate(positions):
            r = indexed_rows[pos][1]
            cat = r["branded_food_category"]
            fndds = r.get("rft_fndds_code","")
            ing = ing_map.get(r["fdc_id"], "")
            cat_mis = (cat != cat_majority) and (cat_majority_share >= 0.4)
            fndds_mis = bool(fndds) and bool(fndds_majority) and (fndds != fndds_majority) \
                        and (fndds_majority_share >= 0.4)
            rft_v = r.get("rft_verdict","")
            rft_flag = rft_v in ("NEEDS_NEW_CONCEPT","WEAK","NO_MATCH","NO_IDENTITY")
            empty_ing = not ing.strip()

            score = (1.0 * max(z[j], 0)
                     + 0.7 * cat_mis
                     + 0.7 * fndds_mis
                     + 0.3 * rft_flag)

            if score > SCORE_THRESHOLD and not empty_ing:
                n_out += 1
                outliers.append({
                    "esha_code": code,
                    "esha_desc": r["best_esha_description"],
                    "fdc_id": r["fdc_id"],
                    "product_description": r["product_description"],
                    "brand_name": r["brand_name"],
                    "branded_food_category": cat,
                    "cohort_size": len(positions),
                    "ingredient_distance": round(float(dist[j]), 4),
                    "ingredient_zscore": round(float(z[j]), 2),
                    "cohort_majority_category": cat_majority,
                    "category_mismatch": int(cat_mis),
                    "rft_fndds_code": fndds,
                    "cohort_majority_fndds": fndds_majority,
                    "fndds_mismatch": int(fndds_mis),
                    "rft_verdict": rft_v,
                    "rft_flag": int(rft_flag),
                    "outlier_score": round(float(score), 3),
                    "ingredients_preview": ing[:120],
                })

        code_stats[code] = {
            "n": len(positions),
            "n_outliers": n_out,
            "pct_outlier": round(n_out/len(positions)*100, 1),
            "esha_desc": indexed_rows[positions[0]][1]["best_esha_description"],
            "majority_category": cat_majority,
            "majority_category_share": round(cat_majority_share, 2),
        }
        if (idx + 1) % 500 == 0 or (idx + 1) == n_codes:
            print(f"  scored {idx+1:,}/{n_codes:,} cohorts ({len(outliers):,} outliers so far)",
                  flush=True)

    print(f"\nScoring done in {time.time()-t0:.1f}s. {len(outliers):,} outliers flagged.", flush=True)

    # Write outliers CSV
    print(f"Writing {OUT_CSV}...", flush=True)
    cols = ["esha_code","esha_desc","fdc_id","product_description","brand_name",
            "branded_food_category","cohort_size",
            "ingredient_distance","ingredient_zscore",
            "cohort_majority_category","category_mismatch",
            "rft_fndds_code","cohort_majority_fndds","fndds_mismatch",
            "rft_verdict","rft_flag",
            "outlier_score","ingredients_preview"]
    outliers.sort(key=lambda o: -o["outlier_score"])
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for o in outliers:
            w.writerow(o)

    # Summary markdown
    print(f"Writing {OUT_MD}...", flush=True)
    by_pct = sorted(code_stats.items(), key=lambda kv: (-kv[1]["pct_outlier"], -kv[1]["n_outliers"]))
    with open(OUT_MD, "w") as f:
        f.write(f"# Cohort outlier scan summary\n\n")
        f.write(f"- Cohorts scored: **{len(code_stats):,}**\n")
        f.write(f"- Total outliers flagged: **{len(outliers):,}**\n")
        f.write(f"- Score threshold: **{SCORE_THRESHOLD}**\n\n")
        f.write(f"## Top 30 dumping-ground codes by % outlier (cohort size >= 20)\n\n")
        f.write("| code | description | size | outliers | % | majority category |\n")
        f.write("|---|---|---:|---:|---:|---|\n")
        big = [(c, s) for c, s in by_pct if s["n"] >= 20]
        for code, s in big[:30]:
            f.write(f"| {code} | {s['esha_desc'][:60]} | {s['n']:,} | {s['n_outliers']:,} | {s['pct_outlier']}% | {s['majority_category'][:30]} |\n")
        f.write(f"\n## Top 20 by absolute outlier count\n\n")
        f.write("| code | description | size | outliers | % |\n|---|---|---:|---:|---:|\n")
        by_n = sorted(code_stats.items(), key=lambda kv: -kv[1]["n_outliers"])
        for code, s in by_n[:20]:
            f.write(f"| {code} | {s['esha_desc'][:60]} | {s['n']:,} | {s['n_outliers']:,} | {s['pct_outlier']}% |\n")

    print(f"\nDone. Wrote:\n  {OUT_CSV}\n  {OUT_MD}", flush=True)

if __name__ == "__main__":
    main()
