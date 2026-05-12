#!/usr/bin/env python3
"""
Per-product tree matching — every outlier scored individually against the
ESHA TREE DESCRIPTION embeddings (not noisy cohort centroids). The tree
description is the "platonic ideal" of each ESHA code, so matching against
it directly avoids cohort pollution.

For each outlier:
  1. Get product embedding (cached).
  2. Score against all 39,691 tree-description embeddings.
  3. Optionally filter to "category-compatible" codes (codes whose existing
     cohort majority category matches the product's category — when such
     a category mapping exists).
  4. Apply if top-1 tree similarity >= MIN_APPLY_SIM and beats current sim
     by MIN_MARGIN.

Apply path: produces vIdentity.fixed_v5.csv (replacing v4 since v4 had
cluster-level coupling errors).

Outputs:
  vIdentity.fixed_v5.csv
  v5_changelog.csv
  v5_review_queue.csv      (didn't meet thresholds)
  v5_summary.md
"""
import csv, pickle
from collections import Counter, defaultdict
from datetime import datetime
import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v3.csv"
OUTLIERS = f"{ROOT}/implementation/output/outliers_filtered.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
CACHE_DIR = f"{ROOT}/implementation/.embed_cache"
PROD_EMB = f"{CACHE_DIR}/prod_emb.npy"
PROD_IDS = f"{CACHE_DIR}/prod_ids.npy"
TREE_EMB = f"{CACHE_DIR}/tree_emb.npy"
TREE_CODES = f"{CACHE_DIR}/tree_codes.pkl"

OUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v5.csv"
OUT_LOG = f"{ROOT}/implementation/output/v5_changelog.csv"
OUT_REVIEW = f"{ROOT}/implementation/output/v5_review_queue.csv"
OUT_SUMMARY = f"{ROOT}/implementation/output/v5_summary.md"

NEW_SOURCE = "tree_match_v5"
MIN_APPLY_SIM = 0.70       # top-1 tree sim threshold (tightened from 0.65)
MIN_MARGIN = 0.10          # must beat current tree sim by this much
MIN_COHORT = 5             # for the category-compatibility step

def main():
    print("Loading map...", flush=True)
    rows = list(csv.DictReader(open(INPUT_MAP)))
    print(f"  {len(rows):,} rows")

    print("Loading caches...", flush=True)
    prod_emb = np.load(PROD_EMB)
    prod_ids = np.load(PROD_IDS, allow_pickle=True)
    fdc_to_idx = {str(p): i for i, p in enumerate(prod_ids)}
    tree_emb = np.load(TREE_EMB)
    with open(TREE_CODES, "rb") as f: tree_codes = pickle.load(f)
    code_list = [c for c, _ in tree_codes]
    code_to_idx_in_tree = {c: i for i, c in enumerate(code_list)}
    code_to_desc = {c: d for c, d in tree_codes}
    print(f"  prod_emb {prod_emb.shape}, tree_emb {tree_emb.shape}")

    # Compute majority category per ESHA code (so we can filter)
    print("Computing per-code majority categories...", flush=True)
    code_to_idx = defaultdict(list)
    for i, r in enumerate(rows):
        if r["best_esha_code"]: code_to_idx[r["best_esha_code"]].append(i)
    code_majority_cat = {}
    code_majority_share = {}
    for c, idx in code_to_idx.items():
        if len(idx) < MIN_COHORT: continue
        cats = Counter(rows[i]["branded_food_category"] for i in idx)
        cat, n = cats.most_common(1)[0]
        code_majority_cat[c] = cat
        code_majority_share[c] = n / len(idx)
    print(f"  cats computed for {len(code_majority_cat):,} codes")

    # Index tree codes by majority category (when known)
    cat_to_tree_idxs = defaultdict(list)
    for c in code_list:
        if c in code_majority_cat and code_majority_share[c] >= 0.4:
            cat_to_tree_idxs[code_majority_cat[c]].append(code_to_idx_in_tree[c])
    cat_to_tree_idxs = {cat: np.array(v, dtype=np.int64) for cat, v in cat_to_tree_idxs.items()}
    print(f"  category-aligned tree groups: {len(cat_to_tree_idxs):,}")

    # Read outliers
    outliers = list(csv.DictReader(open(OUTLIERS)))
    print(f"\nProcessing {len(outliers):,} outliers...")

    applied = {}  # fdc_id -> dict
    review = []
    no_emb = 0
    by_category_path = Counter()

    for o in outliers:
        fid = o["fdc_id"]
        if fid not in fdc_to_idx:
            no_emb += 1; continue
        v = prod_emb[fdc_to_idx[fid]]
        cur_code = o["esha_code"]
        cur_cat = o["branded_food_category"]
        # Current tree sim
        cur_tree_idx = code_to_idx_in_tree.get(cur_code)
        cur_sim = float(tree_emb[cur_tree_idx] @ v) if cur_tree_idx is not None else 0.0

        # Path 1: category-aligned tree codes (preferred)
        chose_path = None
        best_code = None; best_sim = -1.0
        if cur_cat in cat_to_tree_idxs:
            cand_idxs = cat_to_tree_idxs[cur_cat]
            sims = tree_emb[cand_idxs] @ v
            # Mask out current
            mask = np.array([code_list[i] != cur_code for i in cand_idxs], dtype=bool)
            sims_alt = np.where(mask, sims, -2.0)
            best_pos = int(sims_alt.argmax())
            best_sim_cat = float(sims_alt[best_pos])
            best_code_cat = code_list[cand_idxs[best_pos]]
            if best_sim_cat >= MIN_APPLY_SIM and (best_sim_cat - cur_sim) >= MIN_MARGIN:
                best_code = best_code_cat; best_sim = best_sim_cat
                chose_path = "category_aligned"

        # Path 2: open tree search if path 1 didn't find anything good
        if best_code is None:
            sims_full = tree_emb @ v
            # Mask current
            mask = np.array([c != cur_code for c in code_list], dtype=bool)
            sims_full = np.where(mask, sims_full, -2.0)
            best_pos = int(sims_full.argmax())
            best_sim_open = float(sims_full[best_pos])
            best_code_open = code_list[best_pos]
            # Open path requires HIGHER threshold to compensate for not having category constraint
            if best_sim_open >= 0.75 and (best_sim_open - cur_sim) >= MIN_MARGIN:
                best_code = best_code_open; best_sim = best_sim_open
                chose_path = "open_tree"

        if best_code:
            applied[fid] = {
                "fdc_id": fid, "old_code": cur_code, "old_desc": o["esha_desc"],
                "new_code": best_code, "new_desc": code_to_desc.get(best_code, ""),
                "tree_sim": round(best_sim, 4),
                "current_tree_sim": round(cur_sim, 4),
                "margin": round(best_sim - cur_sim, 4),
                "path": chose_path,
                "product_description": o["product_description"],
                "brand_name": o["brand_name"],
                "branded_food_category": cur_cat,
            }
            by_category_path[chose_path] += 1
        else:
            review.append({
                **o, "best_open_code": "", "best_open_desc": "", "best_open_sim": "",
                "current_tree_sim": round(cur_sim, 4),
                "decision": "below_threshold",
            })

    print(f"\nDecisions:")
    print(f"  applied: {len(applied):,}  ({dict(by_category_path)})")
    print(f"  review:  {len(review):,}")
    print(f"  no embedding: {no_emb}")

    # Apply to map
    print(f"\nWriting v5...", flush=True)
    ts = datetime.now().isoformat(timespec="seconds")
    n_changed = 0
    by_dest = Counter(); by_source = Counter()
    with open(INPUT_MAP) as fin, open(OUT_MAP, "w", newline="") as fout, \
         open(OUT_LOG, "w", newline="") as flog:
        rdr = csv.DictReader(fin)
        out_fields = list(rdr.fieldnames)
        wtr = csv.DictWriter(fout, fieldnames=out_fields, extrasaction="ignore")
        wtr.writeheader()
        log_cols = ["fdc_id","gtin_upc","product_description","brand_name","branded_food_category",
                    "old_code","old_desc","new_code","new_desc","tree_sim","current_tree_sim",
                    "margin","path","applied_at"]
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

    if review:
        with open(OUT_REVIEW, "w", newline="") as f:
            cols = list(review[0].keys())
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in review: w.writerow(r)

    with open(OUT_SUMMARY, "w") as f:
        f.write(f"# v5 — per-product tree match (no LLM, deterministic)\n\n")
        f.write(f"Run: {ts}\n\n")
        f.write(f"## Method\n")
        f.write(f"Each outlier scored individually against ALL 39,691 ESHA tree description embeddings.\n")
        f.write(f"Path 1: category-aligned tree codes only. Threshold: tree_sim >= {MIN_APPLY_SIM}, margin >= {MIN_MARGIN}.\n")
        f.write(f"Path 2: open tree search if category path failed. Higher bar: tree_sim >= 0.75.\n\n")
        f.write(f"## Result\n")
        f.write(f"- Outliers processed:  **{len(outliers):,}**\n")
        f.write(f"- Applied:             **{len(applied):,}**\n")
        f.write(f"- Review queue:        **{len(review):,}**\n")
        f.write(f"- Path breakdown: {dict(by_category_path)}\n\n")
        f.write(f"## Top 25 source codes\n\n")
        f.write("| code | description | n |\n|---|---|---:|\n")
        for code, n in by_source.most_common(25):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")
        f.write(f"\n## Top 25 destinations\n\n")
        f.write("| code | description | n |\n|---|---|---:|\n")
        for code, n in by_dest.most_common(25):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")

    print(f"\nWrote:")
    print(f"  {OUT_MAP}  ({n_changed:,} rows changed)")
    print(f"  {OUT_LOG}")
    print(f"  {OUT_REVIEW}")
    print(f"  {OUT_SUMMARY}")

if __name__ == "__main__":
    main()
