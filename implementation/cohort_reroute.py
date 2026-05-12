#!/usr/bin/env python3
"""
No-LLM re-route: for each flagged outlier, find the ESHA cohort whose
ingredient centroid is closest, filtered by branded_food_category match.
Auto-apply when confidence rules pass; otherwise queue for review.

Confidence rules (all must hold to auto-apply):
  - Outlier's branded_food_category matches alt cohort majority category
    (alt cohort majority share >= 0.4)
  - Alt cohort cosine similarity to outlier ingredients >= 0.25
  - Alt cohort similarity > current cohort similarity by margin >= 0.10
  - Alt cohort size >= 5

Outputs:
  vIdentity.fixed_v3.csv             (full map with re-routes applied)
  cohort_reroute_applied.csv         (audit trail of applied re-routes)
  cohort_reroute_review_queue.csv    (outliers we couldn't confidently fix)
  cohort_reroute_summary.md
"""
import csv, sqlite3, time, os
from collections import Counter, defaultdict
from datetime import datetime
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy import sparse

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v2.csv"
OUTLIERS = f"{ROOT}/implementation/output/cohort_outliers_per_code.csv"
DB = f"{ROOT}/data/master_products.db"
OUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v3.csv"
OUT_APPLIED = f"{ROOT}/implementation/output/cohort_reroute_applied.csv"
OUT_REVIEW = f"{ROOT}/implementation/output/cohort_reroute_review_queue.csv"
OUT_SUMMARY = f"{ROOT}/implementation/output/cohort_reroute_summary.md"

NEW_SOURCE = "cohort_reroute_v3"
MIN_COHORT = 5
MIN_ALT_SIM = 0.25
MIN_MARGIN = 0.10
MIN_MAJORITY_SHARE = 0.4

def main():
    print("Loading map...", flush=True)
    rows = []
    with open(INPUT) as f:
        for r in csv.DictReader(f):
            rows.append(r)
    print(f"  {len(rows):,} rows", flush=True)

    print("Loading ingredients...", flush=True)
    con = sqlite3.connect(DB)
    ing_map = {}
    for fdc_id, ing in con.execute("SELECT fdc_id, ingredients FROM products"):
        if ing: ing_map[str(fdc_id)] = ing.lower()
    con.close()
    print(f"  ingredients for {len(ing_map):,} products", flush=True)

    # Group by ESHA code
    groups = defaultdict(list)  # code -> [row_idx]
    for i, r in enumerate(rows):
        c = r["best_esha_code"]
        if c: groups[c].append(i)
    clusterable_codes = [c for c, g in groups.items() if len(g) >= MIN_COHORT]
    print(f"  clusterable cohorts (n>={MIN_COHORT}): {len(clusterable_codes):,}", flush=True)

    # Build TF-IDF on ingredients of all clusterable rows
    indexed_idx = []      # row_idx in rows[]
    docs = []
    for c in clusterable_codes:
        for i in groups[c]:
            indexed_idx.append(i)
            docs.append(ing_map.get(rows[i]["fdc_id"], ""))
    print(f"Building ingredient TF-IDF over {len(docs):,} docs...", flush=True)
    t0 = time.time()
    vec = TfidfVectorizer(analyzer="word", ngram_range=(1,1), min_df=5, max_df=0.5,
                          max_features=20000, sublinear_tf=True,
                          token_pattern=r"[A-Za-z][A-Za-z]{2,}")
    X = vec.fit_transform(docs)
    print(f"  matrix {X.shape}, {time.time()-t0:.1f}s", flush=True)
    pos_of_row = {ri: pos for pos, ri in enumerate(indexed_idx)}

    # Compute cohort centroids and metadata
    print("Computing cohort centroids and metadata...", flush=True)
    code_centroid = {}     # code -> sparse 1xF
    code_centroid_norm = {}
    code_majority_cat = {}
    code_majority_share = {}
    for c in clusterable_codes:
        positions = [pos_of_row[i] for i in groups[c]]
        sub = X[positions]
        centroid = sparse.csr_matrix(sub.mean(axis=0))
        code_centroid[c] = centroid
        code_centroid_norm[c] = float(np.sqrt(centroid.multiply(centroid).sum())) + 1e-12
        cats = Counter(rows[i]["branded_food_category"] for i in groups[c])
        cat_majority, cat_n = cats.most_common(1)[0]
        code_majority_cat[c] = cat_majority
        code_majority_share[c] = cat_n / len(positions)
    print(f"  {len(code_centroid):,} centroids ready", flush=True)

    # Index cohorts BY majority category (so for each outlier we only score same-category cohorts)
    cat_to_codes = defaultdict(list)
    for c in clusterable_codes:
        if code_majority_share[c] >= MIN_MAJORITY_SHARE:
            cat_to_codes[code_majority_cat[c]].append(c)
    print(f"  category groups: {len(cat_to_codes):,}", flush=True)

    # Read outliers
    print("Reading outliers...", flush=True)
    outliers = list(csv.DictReader(open(OUTLIERS)))
    print(f"  {len(outliers):,} outliers to consider", flush=True)

    # For each outlier, find its best alt cohort within its category
    print("Re-routing outliers...", flush=True)
    applied = {}      # fdc_id -> dict
    review = []
    skipped_no_ing = 0
    skipped_no_cat_cohort = 0
    no_better = 0
    rerouted_to_self = 0   # current code is best — don't move
    fdc_to_row_idx = {rows[i]["fdc_id"]: i for i in range(len(rows))}
    t0 = time.time()
    for k, o in enumerate(outliers):
        fdc_id = o["fdc_id"]
        if fdc_id not in fdc_to_row_idx:
            continue
        ri = fdc_to_row_idx[fdc_id]
        cur_code = o["esha_code"]
        cat = o["branded_food_category"]
        if cat not in cat_to_codes:
            skipped_no_cat_cohort += 1
            review.append({**o, "alt_code":"", "alt_desc":"", "alt_sim":"",
                           "current_sim":"", "decision":"no_category_cohorts"})
            continue
        if ri not in pos_of_row:
            continue
        v = X[pos_of_row[ri]]
        v_norm = float(np.sqrt(v.multiply(v).sum())) + 1e-12
        if v_norm < 1e-9:
            skipped_no_ing += 1
            continue
        # Score against each cohort in same category
        candidates = cat_to_codes[cat]
        cur_sim = None
        best_alt_code = None
        best_alt_sim = -1.0
        for c in candidates:
            cen = code_centroid[c]
            sim = float((v @ cen.T).toarray()[0,0]) / (v_norm * code_centroid_norm[c])
            if c == cur_code:
                cur_sim = sim
                continue
            if sim > best_alt_sim:
                best_alt_sim = sim
                best_alt_code = c
        if cur_sim is None and cur_code in code_centroid:
            cen = code_centroid[cur_code]
            cur_sim = float((v @ cen.T).toarray()[0,0]) / (v_norm * code_centroid_norm[cur_code])
        # Decision
        if best_alt_code is None:
            review.append({**o, "alt_code":"", "alt_desc":"", "alt_sim":"",
                           "current_sim": round(cur_sim or 0,4), "decision":"no_alt_in_category"})
            continue
        margin = best_alt_sim - (cur_sim or 0.0)
        alt_desc_row = rows[groups[best_alt_code][0]]
        alt_desc = alt_desc_row["best_esha_description"]
        if best_alt_sim >= MIN_ALT_SIM and margin >= MIN_MARGIN:
            applied[fdc_id] = {
                "fdc_id": fdc_id, "old_code": cur_code, "old_desc": o["esha_desc"],
                "new_code": best_alt_code, "new_desc": alt_desc,
                "alt_sim": round(best_alt_sim, 4), "current_sim": round(cur_sim or 0, 4),
                "margin": round(margin, 4),
                "outlier_score": o["outlier_score"],
                "category_mismatch": o["category_mismatch"],
                "fndds_mismatch": o["fndds_mismatch"],
                "rft_flag": o["rft_flag"],
                "ingredient_zscore": o["ingredient_zscore"],
                "product_description": o["product_description"],
                "brand_name": o["brand_name"],
                "branded_food_category": cat,
            }
        else:
            no_better += 1
            review.append({**o, "alt_code": best_alt_code, "alt_desc": alt_desc[:80],
                           "alt_sim": round(best_alt_sim,4),
                           "current_sim": round(cur_sim or 0,4),
                           "decision": "below_threshold"})
        if (k+1) % 5000 == 0:
            print(f"  {k+1:,}/{len(outliers):,} processed, {len(applied):,} applied, {time.time()-t0:.0f}s",
                  flush=True)
    print(f"\nDone scoring in {time.time()-t0:.0f}s", flush=True)
    print(f"  applied:                 {len(applied):,}")
    print(f"  reviewed (below thresh): {no_better:,}")
    print(f"  no category cohorts:     {skipped_no_cat_cohort:,}")
    print(f"  no ingredients:          {skipped_no_ing:,}")

    # Stream-rewrite map
    print("\nWriting v3 map...", flush=True)
    ts = datetime.now().isoformat(timespec="seconds")
    by_dest = Counter(); by_source = Counter()
    n_changed = 0
    code_to_desc_lookup = {}
    for c in clusterable_codes:
        sample = rows[groups[c][0]]
        code_to_desc_lookup[c] = sample["best_esha_description"]
    with open(INPUT) as fin, open(OUT_MAP, "w", newline="") as fout, \
         open(OUT_APPLIED, "w", newline="") as flog:
        rdr = csv.DictReader(fin)
        out_fields = list(rdr.fieldnames)
        wtr = csv.DictWriter(fout, fieldnames=out_fields, extrasaction="ignore")
        wtr.writeheader()
        log_cols = ["fdc_id","gtin_upc","product_description","brand_name","branded_food_category",
                    "old_code","old_desc","new_code","new_desc","outlier_score",
                    "ingredient_zscore","category_mismatch","fndds_mismatch","rft_flag",
                    "current_sim","alt_sim","margin","applied_at"]
        log = csv.DictWriter(flog, fieldnames=log_cols)
        log.writeheader()
        for r in rdr:
            fdc_id = r["fdc_id"]
            if fdc_id in applied:
                fx = applied[fdc_id]
                if not r.get("best_esha_original_code"):
                    r["best_esha_original_code"] = fx["old_code"]
                    r["best_esha_original_description"] = fx["old_desc"]
                r["best_esha_code"] = fx["new_code"]
                r["best_esha_description"] = fx["new_desc"]
                r["best_esha_change_reason"] = NEW_SOURCE
                r["assignment_source"] = NEW_SOURCE
                n_changed += 1
                by_dest[fx["new_code"]] += 1
                by_source[fx["old_code"]] += 1
                log.writerow({**fx, "gtin_upc": r.get("gtin_upc",""), "applied_at": ts})
            wtr.writerow(r)

    # Review queue
    with open(OUT_REVIEW, "w", newline="") as f:
        if review:
            cols = list(review[0].keys())
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in review: w.writerow(r)

    # Summary
    with open(OUT_SUMMARY, "w") as f:
        f.write(f"# Cohort re-route summary (no-LLM)\n\n")
        f.write(f"Run: {ts}\n\n")
        f.write(f"- Outliers considered: **{len(outliers):,}**\n")
        f.write(f"- Applied: **{n_changed:,}**\n")
        f.write(f"- Sent to review queue: **{len(review):,}**\n")
        f.write(f"- Source map: vIdentity.fixed_v2.csv\n")
        f.write(f"- Output map: vIdentity.fixed_v3.csv\n\n")
        f.write(f"## Top 20 source codes (where re-routes left)\n\n")
        f.write("| code | description | rerouted |\n|---|---|---:|\n")
        for code, n in by_source.most_common(20):
            f.write(f"| {code} | {code_to_desc_lookup.get(code,'')[:60]} | {n:,} |\n")
        f.write(f"\n## Top 20 destination codes (where re-routes went)\n\n")
        f.write("| code | description | received |\n|---|---|---:|\n")
        for code, n in by_dest.most_common(20):
            f.write(f"| {code} | {code_to_desc_lookup.get(code,'')[:60]} | {n:,} |\n")

    print(f"\nWrote:")
    print(f"  {OUT_MAP} ({n_changed:,} rows changed)")
    print(f"  {OUT_APPLIED}")
    print(f"  {OUT_REVIEW} ({len(review):,} rows)")
    print(f"  {OUT_SUMMARY}")

if __name__ == "__main__":
    main()
