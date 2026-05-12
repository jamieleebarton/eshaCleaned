#!/usr/bin/env python3
"""
Primary-identity sweep — for any weakly-routed product, find ESHA codes
whose description contains an actual food noun from the product description.

Works on the canonical vIdentity.csv (in place).

Catches:
  - BAGEL EVERYTHING → bagel codes (was wrongly in breadstick)
  - ASIAGO CIABATTA CROUTONS → crouton codes (was wrongly in breadstick)
  - HOMESTYLE WHITE BREAD → bread, white codes
  - BREAD & BUTTER PICKLES → pickle codes (the category mismatch was the giveaway)
  - CINNAMON BREAD → bread, cinnamon codes

Algorithm:
  1. For each product where rft_verdict ∈ {WEAK, NEEDS_NEW_CONCEPT, NO_MATCH,
     COMPOSITE, NO_IDENTITY, ""}, AND current code's description doesn't already
     match the product's primary noun:
  2. Extract content nouns from product_description (drop stopwords, brand,
     short tokens).
  3. Find ESHA codes whose lowercased description contains at least one of
     those nouns. Filter to category-compatible cohorts (cohort majority cat
     == product's branded_food_category) when possible.
  4. Score candidates by:
       - # matching nouns / total nouns
       - whether product category matches cohort majority category (huge boost)
       - embedding similarity to the candidate code's tree description
  5. Apply if score >= threshold AND new code != current.

Output written IN PLACE to vIdentity.csv. Audit trail in primary_identity_changelog.csv.
"""
import csv, os, pickle, re, sys, time
from collections import Counter, defaultdict
from datetime import datetime
import numpy as np

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
CANON = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
CACHE_DIR = f"{ROOT}/implementation/.embed_cache"
PROD_EMB = f"{CACHE_DIR}/prod_emb.npy"
PROD_IDS = f"{CACHE_DIR}/prod_ids.npy"
TREE_EMB = f"{CACHE_DIR}/tree_emb.npy"
TREE_CODES = f"{CACHE_DIR}/tree_codes.pkl"

CHANGELOG = f"{ROOT}/implementation/output/primary_identity_changelog.csv"
SUMMARY = f"{ROOT}/implementation/output/primary_identity_summary.md"
NEW_SOURCE = "primary_identity_fix"

WEAK_VERDICTS = {"WEAK", "NEEDS_NEW_CONCEPT", "NO_MATCH", "COMPOSITE", "NO_IDENTITY", ""}
MIN_SCORE = 0.55
MIN_EMB_SIM = 0.55
MIN_NOUN_LEN = 4

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

def tokenize(s):
    if not s: return []
    return [t for t in re.findall(r"[a-z][a-z]+", s.lower()) if len(t) >= MIN_NOUN_LEN and t not in STOP]

def main():
    print("Loading caches...", flush=True)
    prod_emb = np.load(PROD_EMB)
    prod_ids = np.load(PROD_IDS, allow_pickle=True)
    fdc_to_idx = {str(p): i for i, p in enumerate(prod_ids)}
    tree_emb = np.load(TREE_EMB)
    with open(TREE_CODES, "rb") as f: tree_codes = pickle.load(f)
    code_list = [c for c, _ in tree_codes]
    code_to_treei = {c: i for i, c in enumerate(code_list)}
    code_to_desc = {c: d for c, d in tree_codes}

    print("Building tree word-index...", flush=True)
    tree_token_to_codes = defaultdict(set)
    for c, d in tree_codes:
        for t in set(tokenize(d)):
            tree_token_to_codes[t].add(c)
    print(f"  vocabulary: {len(tree_token_to_codes):,}")

    print("Reading canonical map...", flush=True)
    rows = list(csv.DictReader(open(CANON)))
    print(f"  {len(rows):,} rows")

    # Compute per-cohort majority categories for category-compat scoring
    print("Cohort majority categories...", flush=True)
    code_to_idx = defaultdict(list)
    for i, r in enumerate(rows):
        if r["best_esha_code"]: code_to_idx[r["best_esha_code"]].append(i)
    code_majority_cat = {}
    code_majority_share = {}
    for c, idx in code_to_idx.items():
        if len(idx) < 5: continue
        cats = Counter(rows[i]["branded_food_category"] for i in idx)
        cat, n = cats.most_common(1)[0]
        code_majority_cat[c] = cat
        code_majority_share[c] = n / len(idx)
    print(f"  category-confident codes: {len(code_majority_cat):,}")

    # Decide
    print("Scanning weak-verdict rows for primary-identity fixes...", flush=True)
    fixes = {}
    skipped_strong = 0
    skipped_no_nouns = 0
    skipped_no_candidates = 0
    skipped_below_thresh = 0
    skipped_no_change = 0

    for r in rows:
        v = r.get("rft_verdict","")
        if v not in WEAK_VERDICTS:
            skipped_strong += 1; continue
        cur = r["best_esha_code"]
        cur_desc = (r.get("best_esha_description","") or "").lower()
        product_desc = r.get("product_description","")
        prod_cat = r.get("branded_food_category","")
        brand = r.get("brand_name","") or ""

        nouns = set(tokenize(product_desc))
        # Drop brand words
        for bt in tokenize(brand): nouns.discard(bt)
        # Drop nouns that already appear in current description (already routed correctly on those)
        cur_tokens = set(tokenize(cur_desc))
        primary_nouns = nouns - cur_tokens
        if not primary_nouns:
            skipped_no_nouns += 1; continue
        # If primary nouns set is empty after drop, but full nouns exist, fall back to all nouns
        # (still useful for catching wrong-category cases)
        anchor_nouns = primary_nouns or nouns
        if not anchor_nouns:
            skipped_no_nouns += 1; continue

        # Candidate codes: union of codes containing any anchor noun
        candidates = set()
        for n in anchor_nouns:
            candidates |= tree_token_to_codes.get(n, set())
        candidates.discard(cur)
        if not candidates:
            skipped_no_candidates += 1; continue

        # Pre-filter by category compatibility when possible (huge precision boost)
        cat_compat = [c for c in candidates
                      if code_majority_cat.get(c) == prod_cat
                      and code_majority_share.get(c, 0) >= 0.4]
        pool = cat_compat or list(candidates)

        # Score each candidate
        prod_emb_v = prod_emb[fdc_to_idx[r["fdc_id"]]] if r["fdc_id"] in fdc_to_idx else None
        best = None; best_score = -1; best_emb = 0; best_overlap = 0
        for c in pool:
            tree_tokens = set(tokenize(code_to_desc.get(c, "")))
            overlap = len(anchor_nouns & tree_tokens) / max(len(anchor_nouns), 1)
            cat_match = (code_majority_cat.get(c) == prod_cat
                         and code_majority_share.get(c, 0) >= 0.4)
            if prod_emb_v is not None and c in code_to_treei:
                emb_sim = float(tree_emb[code_to_treei[c]] @ prod_emb_v)
            else:
                emb_sim = 0.0
            # Heavy weight on category match + token overlap; emb_sim as tiebreaker
            score = 0.4 * overlap + 0.4 * (1.0 if cat_match else 0.0) + 0.2 * max(emb_sim, 0)
            if score > best_score:
                best_score = score; best = c; best_emb = emb_sim; best_overlap = overlap

        if best is None or best_score < MIN_SCORE or best_emb < MIN_EMB_SIM:
            skipped_below_thresh += 1; continue
        if best == cur:
            skipped_no_change += 1; continue

        fixes[r["fdc_id"]] = {
            "fdc_id": r["fdc_id"],
            "old_code": cur, "old_desc": r.get("best_esha_description",""),
            "new_code": best, "new_desc": code_to_desc.get(best, ""),
            "score": round(best_score, 3),
            "noun_overlap": round(best_overlap, 3),
            "emb_sim": round(best_emb, 3),
            "anchor_nouns": "|".join(sorted(anchor_nouns)[:8]),
            "category_match": int(code_majority_cat.get(best) == prod_cat),
            "rft_verdict": v,
            "product_description": product_desc,
            "brand_name": brand,
            "branded_food_category": prod_cat,
        }

    print(f"\nDecisions:")
    print(f"  ELIGIBLE FIXES:                {len(fixes):,}")
    print(f"  skipped (rft STRONG/EXACT):    {skipped_strong:,}")
    print(f"  skipped (no anchor nouns):     {skipped_no_nouns:,}")
    print(f"  skipped (no tree candidates):  {skipped_no_candidates:,}")
    print(f"  skipped (below threshold):     {skipped_below_thresh:,}")
    print(f"  skipped (no-op same code):     {skipped_no_change:,}")

    # Apply in place
    print(f"\nApplying {len(fixes):,} fixes IN PLACE...", flush=True)
    ts = datetime.now().isoformat(timespec="seconds")
    n_changed = 0
    by_dest = Counter(); by_source = Counter()
    tmp = CANON + ".tmp"
    with open(CANON) as fin, open(tmp, "w", newline="") as fout, \
         open(CHANGELOG, "w", newline="") as flog:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames, extrasaction="ignore")
        wtr.writeheader()
        log_cols = ["fdc_id","gtin_upc","product_description","brand_name","branded_food_category",
                    "old_code","old_desc","new_code","new_desc","score","noun_overlap",
                    "emb_sim","category_match","anchor_nouns","rft_verdict","applied_at"]
        log = csv.DictWriter(flog, fieldnames=log_cols)
        log.writeheader()
        for r in rdr:
            fid = r["fdc_id"]
            if fid in fixes:
                fx = fixes[fid]
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
    import shutil
    shutil.move(tmp, CANON)

    # Summary
    with open(SUMMARY, "w") as f:
        f.write(f"# Primary-identity fix\n\n")
        f.write(f"Run: {ts}\n\n")
        f.write(f"## Method\n\nFor each WEAK/NEEDS_NEW/COMPOSITE row, extract content nouns from "
                f"the product description, find tree codes containing those nouns, score by "
                f"noun overlap + category compatibility + embedding similarity, apply when "
                f"score>={MIN_SCORE} and emb_sim>={MIN_EMB_SIM}.\n\n")
        f.write(f"## Result\n\n- Rows changed: **{n_changed:,}**\n\n")
        f.write(f"## Top 25 source codes\n\n| code | description | n |\n|---|---|---:|\n")
        for code, n in by_source.most_common(25):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")
        f.write(f"\n## Top 25 destinations\n\n| code | description | n |\n|---|---|---:|\n")
        for code, n in by_dest.most_common(25):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")

    print(f"\nWrote:")
    print(f"  {CANON}  ({n_changed:,} rows changed in place)")
    print(f"  {CHANGELOG}")
    print(f"  {SUMMARY}")

if __name__ == "__main__":
    main()
