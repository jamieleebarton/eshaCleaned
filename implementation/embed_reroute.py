#!/usr/bin/env python3
"""
Stage 3 (no-LLM, embedding-based) — re-route outliers using cached MiniLM
product embeddings. NO API CALLS. NO HALLUCINATION.

For each filtered outlier:
  1. Score its product embedding against all clusterable ESHA cohort centroids
     (mean of product embeddings in each code).
  2. Filter candidate cohorts to those whose MAJORITY category matches the
     outlier's branded_food_category (kills nonsense suggestions).
  3. Pick the top-1 alternative cohort.
  4. Apply if:
       - top-1 similarity >= MIN_ABS_SIM (0.50)
       - top-1 sim - current sim >= MIN_MARGIN (0.10)
       - top-1 cohort size >= 5 (statistical sanity)

Also produces a review queue for outliers that didn't meet the threshold.

Outputs:
  vIdentity.fixed_v3_embed.csv   (real v3, replacing the bad TF-IDF reroute)
  embed_reroute_applied.csv      (per-fix audit trail)
  embed_reroute_review.csv       (didn't apply, for human triage / new leaves)
  embed_reroute_summary.md
"""
import csv, os, sys, time, pickle
from collections import Counter, defaultdict
from datetime import datetime
import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v2.csv"
OUTLIERS = f"{ROOT}/implementation/output/outliers_filtered.csv"
CACHE_DIR = f"{ROOT}/implementation/.embed_cache"
PROD_EMB = f"{CACHE_DIR}/prod_emb.npy"
PROD_IDS = f"{CACHE_DIR}/prod_ids.npy"
TREE_EMB = f"{CACHE_DIR}/tree_emb.npy"
TREE_CODES = f"{CACHE_DIR}/tree_codes.pkl"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"

OUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v3_embed.csv"
OUT_APPLIED = f"{ROOT}/implementation/output/embed_reroute_applied.csv"
OUT_REVIEW = f"{ROOT}/implementation/output/embed_reroute_review.csv"
OUT_SUMMARY = f"{ROOT}/implementation/output/embed_reroute_summary.md"

NEW_SOURCE = "embed_reroute_v3"
MIN_COHORT = 5
MIN_ABS_SIM = 0.50         # top-1 must be at least this similar
MIN_MARGIN = 0.10          # top-1 must beat current by this much
MAJORITY_SHARE_REQUIRED = 0.4  # cohort needs a clear majority category to be a candidate

def main():
    print("Loading map...", flush=True)
    rows = []
    with open(INPUT_MAP) as f:
        for r in csv.DictReader(f):
            rows.append(r)
    print(f"  {len(rows):,} rows", flush=True)

    print("Loading cached product embeddings...", flush=True)
    prod_emb = np.load(PROD_EMB)
    prod_ids = np.load(PROD_IDS, allow_pickle=True)
    print(f"  shape: {prod_emb.shape}", flush=True)
    fdc_to_idx = {str(pid): i for i, pid in enumerate(prod_ids)}

    print("Loading cached ESHA tree embeddings...", flush=True)
    tree_emb = np.load(TREE_EMB)
    with open(TREE_CODES, "rb") as f: tree_codes = pickle.load(f)
    code_to_tree_idx = {c: i for i, (c, _) in enumerate(tree_codes)}
    code_to_desc = {c: d for c, d in tree_codes}
    print(f"  tree shape: {tree_emb.shape}", flush=True)

    # Group rows by ESHA code
    print("Grouping by code...", flush=True)
    code_to_idx = defaultdict(list)
    for i, r in enumerate(rows):
        c = r["best_esha_code"]
        if c: code_to_idx[c].append(i)
    clusterable_codes = [c for c, idx in code_to_idx.items() if len(idx) >= MIN_COHORT]
    print(f"  clusterable cohorts (n>={MIN_COHORT}): {len(clusterable_codes):,}", flush=True)

    # Build cohort centroids from product embeddings (semantic)
    print("Computing cohort centroids and majority categories...", flush=True)
    code_to_centroid_idx = {}   # code -> idx in centroids array
    centroids = np.zeros((len(clusterable_codes), prod_emb.shape[1]), dtype=np.float32)
    code_majority_cat = {}
    code_majority_share = {}
    for ci, code in enumerate(clusterable_codes):
        idxs = code_to_idx[code]
        # Get embedding indices for these rows
        emb_idxs = []
        for ri in idxs:
            fid = rows[ri]["fdc_id"]
            if fid in fdc_to_idx: emb_idxs.append(fdc_to_idx[fid])
        if not emb_idxs:
            continue
        c_emb = prod_emb[emb_idxs].mean(axis=0)
        norm = np.linalg.norm(c_emb) + 1e-12
        centroids[ci] = c_emb / norm
        code_to_centroid_idx[code] = ci

        cats = Counter(rows[ri]["branded_food_category"] for ri in idxs)
        cat_majority, cat_n = cats.most_common(1)[0]
        code_majority_cat[code] = cat_majority
        code_majority_share[code] = cat_n / len(idxs)
    print(f"  centroids: {centroids.shape}", flush=True)

    # Index cohorts BY majority category
    cat_to_codes = defaultdict(list)
    for c in clusterable_codes:
        if c in code_to_centroid_idx and code_majority_share[c] >= MAJORITY_SHARE_REQUIRED:
            cat_to_codes[code_majority_cat[c]].append(c)
    print(f"  category groups: {len(cat_to_codes):,}", flush=True)

    # Build category -> centroid matrix for fast scoring
    cat_to_cidxs = {}    # category -> ndarray of centroid indices
    cat_to_codelist = {}
    for cat, codes in cat_to_codes.items():
        cidxs = np.array([code_to_centroid_idx[c] for c in codes], dtype=np.int64)
        cat_to_cidxs[cat] = cidxs
        cat_to_codelist[cat] = codes

    # Read outliers
    print("Reading outliers...", flush=True)
    outliers = list(csv.DictReader(open(OUTLIERS)))
    print(f"  {len(outliers):,} outliers", flush=True)

    # Score each outlier
    print("Re-routing...", flush=True)
    applied = {}  # fdc_id -> dict
    review = []
    skipped_no_cat = 0
    skipped_no_emb = 0
    no_better = 0
    t0 = time.time()
    for k, o in enumerate(outliers):
        fdc_id = o["fdc_id"]
        if fdc_id not in fdc_to_idx:
            skipped_no_emb += 1; continue
        cur_code = o["esha_code"]
        cat = o["branded_food_category"]
        v = prod_emb[fdc_to_idx[fdc_id]]   # already normalized
        # Current sim (might not be in clusterable if cohort size < 5)
        cur_ci = code_to_centroid_idx.get(cur_code)
        cur_sim = float(centroids[cur_ci] @ v) if cur_ci is not None else 0.0
        if cat not in cat_to_cidxs:
            skipped_no_cat += 1
            review.append({**o, "alt_code":"", "alt_desc":"", "alt_sim":"",
                           "current_sim": round(cur_sim,4), "decision":"no_category_cohorts"})
            continue
        cidxs = cat_to_cidxs[cat]
        sims = centroids[cidxs] @ v        # (n_candidates,)
        # Mask out current cohort
        codelist = cat_to_codelist[cat]
        mask = np.array([c != cur_code for c in codelist], dtype=bool)
        if not mask.any():
            no_better += 1
            review.append({**o, "alt_code":"", "alt_desc":"", "alt_sim":"",
                           "current_sim": round(cur_sim,4), "decision":"only_current_in_category"})
            continue
        sims_alt = np.where(mask, sims, -1.0)
        best_idx = int(sims_alt.argmax())
        best_sim = float(sims_alt[best_idx])
        best_code = codelist[best_idx]
        margin = best_sim - cur_sim
        # Decision rules
        if best_sim >= MIN_ABS_SIM and margin >= MIN_MARGIN:
            applied[fdc_id] = {
                "fdc_id": fdc_id, "old_code": cur_code, "old_desc": o["esha_desc"],
                "new_code": best_code, "new_desc": code_to_desc.get(best_code, ""),
                "alt_sim": round(best_sim, 4),
                "current_sim": round(cur_sim, 4),
                "margin": round(margin, 4),
                "outlier_score": o["outlier_score"],
                "centroid_zscore": o["centroid_zscore"],
                "product_description": o["product_description"],
                "brand_name": o["brand_name"],
                "branded_food_category": cat,
            }
        else:
            no_better += 1
            review.append({**o,
                "alt_code": best_code, "alt_desc": code_to_desc.get(best_code, "")[:80],
                "alt_sim": round(best_sim, 4),
                "current_sim": round(cur_sim, 4),
                "decision": "below_threshold" if best_sim < MIN_ABS_SIM else "insufficient_margin",
            })
        if (k+1) % 2500 == 0 or (k+1) == len(outliers):
            print(f"  {k+1:,}/{len(outliers):,} processed, {len(applied):,} applied ({time.time()-t0:.0f}s)",
                  flush=True)

    print(f"\nDone scoring in {time.time()-t0:.0f}s")
    print(f"  applied:                 {len(applied):,}")
    print(f"  reviewed (below thresh): {no_better:,}")
    print(f"  no category cohorts:     {skipped_no_cat:,}")
    print(f"  no embedding:            {skipped_no_emb:,}")

    # Stream-rewrite map
    print("\nWriting v3...", flush=True)
    ts = datetime.now().isoformat(timespec="seconds")
    by_dest = Counter(); by_source = Counter()
    n_changed = 0
    with open(INPUT_MAP) as fin, open(OUT_MAP, "w", newline="") as fout, \
         open(OUT_APPLIED, "w", newline="") as flog:
        rdr = csv.DictReader(fin)
        out_fields = list(rdr.fieldnames)
        wtr = csv.DictWriter(fout, fieldnames=out_fields, extrasaction="ignore")
        wtr.writeheader()
        log_cols = ["fdc_id","gtin_upc","product_description","brand_name","branded_food_category",
                    "old_code","old_desc","new_code","new_desc","outlier_score",
                    "centroid_zscore","current_sim","alt_sim","margin","applied_at"]
        log = csv.DictWriter(flog, fieldnames=log_cols)
        log.writeheader()
        for r in rdr:
            fid = r["fdc_id"]
            if fid in applied:
                fx = applied[fid]
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
        f.write(f"# Embedding-based outlier reroute (no LLM)\n\n")
        f.write(f"Run: {ts}\n\n")
        f.write(f"- Outliers fed in:  **{len(outliers):,}**\n")
        f.write(f"- Applied:          **{n_changed:,}**\n")
        f.write(f"- Review queue:     **{len(review):,}**\n")
        f.write(f"- Source map: vIdentity.fixed_v2.csv\n")
        f.write(f"- Output map: vIdentity.fixed_v3_embed.csv\n\n")
        f.write(f"## Top 25 source codes (where re-routes left)\n\n")
        f.write("| code | description | rerouted |\n|---|---|---:|\n")
        for code, n in by_source.most_common(25):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")
        f.write(f"\n## Top 25 destination codes\n\n")
        f.write("| code | description | received |\n|---|---|---:|\n")
        for code, n in by_dest.most_common(25):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")

    print(f"\nWrote:")
    print(f"  {OUT_MAP}  ({n_changed:,} rows changed)")
    print(f"  {OUT_APPLIED}")
    print(f"  {OUT_REVIEW}  ({len(review):,} rows)")
    print(f"  {OUT_SUMMARY}")

if __name__ == "__main__":
    main()
