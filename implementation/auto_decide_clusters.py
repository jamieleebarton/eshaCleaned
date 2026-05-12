#!/usr/bin/env python3
"""
Auto-decide on the 381 outlier clusters using multiple deterministic signals.
NO LLM. NO USER REVIEW. JUST DECISIONS.

For each cluster of 5+ outliers:
  1. Extract "concept tokens" — content words that appear in >=50% of member
     product descriptions (e.g., "KIMCHI" in 79/79 kimchi products).
  2. Search the ENTIRE ESHA tree (39,691 codes) for descriptions matching those
     concept tokens. Score by token overlap and embedding similarity.
  3. Compute cluster centroid embedding and rank tree codes by:
       score = 0.5 * embedding_sim_to_tree_desc
             + 0.5 * (concept_token_overlap / cluster_concept_size)
  4. DECISION RULES (deterministic, no human input):
       - If top score >= 0.55 AND embedding_sim >= 0.55 → AUTO-APPLY
       - If top score < 0.55 but cluster has strong concept tokens → NEW_LEAF
       - Otherwise → SKIP

Output:
  vIdentity.fixed_v4.csv               (canonical v4)
  v4_changelog.csv                     (audit trail of every change)
  v4_new_leaf_proposals.csv            (clusters needing new ESHA codes)
  v4_summary.md
"""
import csv, pickle, re, sys
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

OUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v4.csv"
OUT_LOG = f"{ROOT}/implementation/output/v4_changelog.csv"
OUT_LEAVES = f"{ROOT}/implementation/output/v4_new_leaf_proposals.csv"
OUT_SUMMARY = f"{ROOT}/implementation/output/v4_summary.md"

NEW_SOURCE = "auto_cluster_decision_v4"
MIN_CLUSTER = 5
MIN_CONCEPT_FREQ = 0.5      # token must appear in 50% of cluster members
MIN_SCORE_APPLY = 0.55
MIN_EMB_SIM_APPLY = 0.55

# Stopwords stripped from descriptions
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
crispy crunchy soft tender tough thick thin fancy
""".split())

def tokenize(s):
    if not s: return []
    return [t for t in re.findall(r"[a-z][a-z]+", s.lower()) if len(t) >= 4 and t not in STOP]

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
    code_to_desc = {c: d for c, d in tree_codes}
    code_to_treei = {c: i for i, (c, _) in enumerate(tree_codes)}
    print(f"  prod_emb {prod_emb.shape}, tree_emb {tree_emb.shape}")

    # Build inverted index: token -> set of tree codes containing it
    print("Building tree token index...", flush=True)
    tree_token_idx = defaultdict(set)
    tree_token_set = {}
    for c, d in tree_codes:
        toks = set(tokenize(d))
        tree_token_set[c] = toks
        for t in toks: tree_token_idx[t].add(c)
    print(f"  tree token vocabulary: {len(tree_token_idx):,} tokens")

    # Group outliers into clusters
    print("Clustering outliers...", flush=True)
    outliers = list(csv.DictReader(open(OUTLIERS)))
    cluster_buckets = defaultdict(list)
    for o in outliers:
        cluster_buckets[(o["esha_code"], o["branded_food_category"])].append(o)
    big = [(k, v) for k, v in cluster_buckets.items() if len(v) >= MIN_CLUSTER]
    big.sort(key=lambda kv: -len(kv[1]))
    print(f"  {len(big):,} clusters with N>={MIN_CLUSTER}")

    # Per cluster: decide
    decisions = {}        # fdc_id -> dict (apply)
    new_leaves = []       # list of cluster summaries needing tree expansion
    skipped = []          # clusters we couldn't decide on
    by_decision = Counter()

    print("Deciding...", flush=True)
    for (cur_code, cur_cat), members in big:
        # Concept tokens: words appearing in >=50% of member descriptions
        n = len(members)
        token_freq = Counter()
        for m in members:
            for t in set(tokenize(m["product_description"])): token_freq[t] += 1
        concept_tokens = {t for t, c in token_freq.items() if c >= max(2, n * MIN_CONCEPT_FREQ)}
        # Drop the brand of the most common brand if it's in concept (e.g., "MAMA")
        brand_tokens = Counter()
        for m in members:
            for t in tokenize(m.get("brand_name","")): brand_tokens[t] += 1
        for t, c in brand_tokens.items():
            if c >= n * MIN_CONCEPT_FREQ:
                concept_tokens.discard(t)
        # Drop tokens that appear in current_desc (they were why it was misrouted)
        cur_tokens = set(tokenize(members[0]["esha_desc"]))
        # Don't necessarily drop these — they could still be the right concept

        # Cluster centroid embedding
        embs = [prod_emb[fdc_to_idx[m["fdc_id"]]] for m in members if m["fdc_id"] in fdc_to_idx]
        if not embs:
            skipped.append({"current_code":cur_code, "reason":"no_embeddings", "size":n}); continue
        cluster_cen = np.mean(embs, axis=0)
        cluster_cen /= (np.linalg.norm(cluster_cen) + 1e-12)

        # Tree-search: codes whose description shares tokens with concept
        candidate_codes = set()
        for t in concept_tokens:
            candidate_codes |= tree_token_idx.get(t, set())
        candidate_codes.discard(cur_code)

        if not candidate_codes:
            new_leaves.append({
                "current_code": cur_code, "current_desc": members[0]["esha_desc"],
                "current_category": cur_cat, "cluster_size": n,
                "concept_tokens": "|".join(sorted(concept_tokens)) if concept_tokens else "",
                "sample_products": " | ".join(m["product_description"][:55] for m in members[:5]),
                "sample_fdc_ids": " | ".join(m["fdc_id"] for m in members[:5]),
                "reason": "no_tree_codes_match_concept_tokens",
            })
            by_decision["NEW_LEAF (no tree match)"] += 1
            continue

        # Score candidates: token overlap + embedding similarity to tree desc
        best_code = None; best_score = -1; best_emb_sim = 0; best_overlap = 0
        for c in candidate_codes:
            tree_tokens = tree_token_set.get(c, set())
            overlap = len(concept_tokens & tree_tokens) / max(len(concept_tokens), 1)
            if c not in code_to_treei: continue
            emb_sim = float(tree_emb[code_to_treei[c]] @ cluster_cen)
            score = 0.5 * emb_sim + 0.5 * overlap
            if score > best_score:
                best_score = score; best_code = c; best_emb_sim = emb_sim; best_overlap = overlap

        if best_code and best_score >= MIN_SCORE_APPLY and best_emb_sim >= MIN_EMB_SIM_APPLY:
            # AUTO-APPLY this cluster
            for m in members:
                decisions[m["fdc_id"]] = {
                    "fdc_id": m["fdc_id"], "old_code": cur_code,
                    "old_desc": members[0]["esha_desc"],
                    "new_code": best_code, "new_desc": code_to_desc.get(best_code, ""),
                    "score": round(best_score, 3),
                    "emb_sim": round(best_emb_sim, 3),
                    "token_overlap": round(best_overlap, 3),
                    "concept_tokens": "|".join(sorted(concept_tokens)),
                    "cluster_size": n,
                    "product_description": m["product_description"],
                    "brand_name": m["brand_name"],
                    "branded_food_category": m["branded_food_category"],
                }
            by_decision["AUTO-APPLY"] += 1
        elif concept_tokens and len(concept_tokens) >= 1:
            new_leaves.append({
                "current_code": cur_code, "current_desc": members[0]["esha_desc"],
                "current_category": cur_cat, "cluster_size": n,
                "concept_tokens": "|".join(sorted(concept_tokens)),
                "best_tree_match_code": best_code or "",
                "best_tree_match_desc": code_to_desc.get(best_code or "", "")[:60],
                "best_tree_score": round(best_score, 3),
                "best_tree_emb_sim": round(best_emb_sim, 3),
                "sample_products": " | ".join(m["product_description"][:55] for m in members[:5]),
                "sample_fdc_ids": " | ".join(m["fdc_id"] for m in members[:5]),
                "reason": "tree_match_below_threshold",
            })
            by_decision["NEW_LEAF (no good tree match)"] += 1
        else:
            skipped.append({"current_code": cur_code, "size": n, "reason": "no_concept_tokens"})
            by_decision["SKIP"] += 1

    print(f"\nDecision summary:")
    for d, n in by_decision.most_common():
        print(f"  {d}: {n}")

    # Apply to map
    print(f"\nApplying {len(decisions):,} fdc_id changes to v4...", flush=True)
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
                    "old_code","old_desc","new_code","new_desc","score","emb_sim",
                    "token_overlap","concept_tokens","cluster_size","applied_at"]
        log = csv.DictWriter(flog, fieldnames=log_cols)
        log.writeheader()
        for r in rdr:
            fid = r["fdc_id"]
            if fid in decisions:
                fx = decisions[fid]
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

    # New-leaf proposals
    if new_leaves:
        cols = list(new_leaves[0].keys())
        with open(OUT_LEAVES, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in new_leaves: w.writerow(r)

    # Summary
    with open(OUT_SUMMARY, "w") as f:
        f.write(f"# v4 — auto-decided cluster fixes (no LLM, no user review)\n\n")
        f.write(f"Run: {ts}\n\n")
        f.write(f"## Decisions\n\n")
        for d, n in by_decision.most_common():
            f.write(f"- {d}: **{n}**\n")
        f.write(f"\n- Source: vIdentity.fixed_v3.csv\n")
        f.write(f"- Output: vIdentity.fixed_v4.csv\n")
        f.write(f"- Rows changed: **{n_changed:,}**\n")
        f.write(f"- Cluster decisions made: {sum(by_decision.values()):,}\n\n")
        f.write(f"## Top 25 destinations\n\n")
        f.write("| code | description | n |\n|---|---|---:|\n")
        for code, n in by_dest.most_common(25):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")

    print(f"\nWrote:")
    print(f"  {OUT_MAP}  ({n_changed:,} rows changed)")
    print(f"  {OUT_LOG}")
    print(f"  {OUT_LEAVES}  ({len(new_leaves):,} clusters need new leaves)")
    print(f"  {OUT_SUMMARY}")

if __name__ == "__main__":
    main()
