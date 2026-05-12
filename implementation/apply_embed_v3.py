#!/usr/bin/env python3
"""
Apply tightened embedding reroute to v2 -> produces canonical v3.

Filters embed_reroute_applied.csv with stricter confidence rules:
  KEEP only when:  alt_sim >= 0.75
                OR (alt_sim >= 0.65 AND margin >= 0.15)
  Otherwise: send to review queue.

Outputs:
  vIdentity.fixed_v3.csv             (canonical v3)
  embed_v3_applied.csv               (tightened changelog)
  embed_v3_review_queue.csv          (rows that didn't make the cut)
  embed_v3_summary.md
"""
import csv, os, shutil
from collections import Counter
from datetime import datetime

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v2.csv"
APPLIED_LOG = f"{ROOT}/implementation/output/embed_reroute_applied.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
OUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v3.csv"
OUT_APPLIED = f"{ROOT}/implementation/output/embed_v3_applied.csv"
OUT_REVIEW = f"{ROOT}/implementation/output/embed_v3_review_queue.csv"
OUT_SUMMARY = f"{ROOT}/implementation/output/embed_v3_summary.md"

# Move the bad TF-IDF reroute v3 out of the way (it had ~33% regression rate)
BAD_V3 = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v3_tfidf_DEPRECATED.csv"
PREV_V3 = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v3_embed.csv"

NEW_SOURCE = "embed_v3_tightened"

# Tightened rules
SIM_HIGH = 0.75       # absolute similarity threshold (sole rule)
SIM_MID = 0.65        # combined with margin
MARGIN_REQ = 0.15     # required when alt_sim is in 0.65-0.75 band

def keep(alt_sim, margin):
    if alt_sim >= SIM_HIGH:
        return True
    if alt_sim >= SIM_MID and margin >= MARGIN_REQ:
        return True
    return False

def main():
    # Move the bad TF-IDF reroute v3 out of the way if present
    old_tfidf_v3 = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v3.csv.OLD_TFIDF"
    # Note: the old TF-IDF v3 was already overwritten by embed_reroute.py? No — embed went to fixed_v3_embed.csv.
    # The original cohort_reroute.py wrote vIdentity.fixed_v3.csv from cohort_reroute, that one had regressions.
    src_tfidf = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v3.csv"
    if os.path.exists(src_tfidf):
        if os.path.exists(BAD_V3):
            os.remove(BAD_V3)
        shutil.move(src_tfidf, BAD_V3)
        print(f"  Moved old TF-IDF v3 → {os.path.basename(BAD_V3)} (deprecated, kept for audit)")

    # Read tree for lookup
    code_to_desc = {}
    with open(TREE) as f:
        for r in csv.DictReader(f):
            code_to_desc[r["EshaCode"]] = r["Description"]

    # Filter applied log
    print(f"\nReading {APPLIED_LOG}...")
    candidates = list(csv.DictReader(open(APPLIED_LOG)))
    print(f"  {len(candidates):,} candidate fixes from embed_reroute")

    keep_set = {}
    review = []
    for c in candidates:
        alt = float(c["alt_sim"]); marg = float(c["margin"])
        if keep(alt, marg):
            keep_set[c["fdc_id"]] = c
        else:
            review.append(c)

    print(f"\nFilter (alt_sim>={SIM_HIGH} OR (alt_sim>={SIM_MID} AND margin>={MARGIN_REQ})):")
    print(f"  KEEP:   {len(keep_set):,}")
    print(f"  REVIEW: {len(review):,}")

    # Stream rewrite v2 -> v3
    print(f"\nWriting v3 map...")
    ts = datetime.now().isoformat(timespec="seconds")
    n_changed = 0
    by_dest = Counter(); by_source = Counter()
    with open(INPUT_MAP) as fin, open(OUT_MAP, "w", newline="") as fout, \
         open(OUT_APPLIED, "w", newline="") as flog:
        rdr = csv.DictReader(fin)
        out_fields = list(rdr.fieldnames)
        wtr = csv.DictWriter(fout, fieldnames=out_fields, extrasaction="ignore")
        wtr.writeheader()
        log_cols = ["fdc_id","gtin_upc","product_description","brand_name","branded_food_category",
                    "old_code","old_desc","new_code","new_desc",
                    "current_sim","alt_sim","margin","outlier_score","centroid_zscore","applied_at"]
        log = csv.DictWriter(flog, fieldnames=log_cols)
        log.writeheader()
        for r in rdr:
            fid = r["fdc_id"]
            if fid in keep_set:
                fx = keep_set[fid]
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
    if review:
        with open(OUT_REVIEW, "w", newline="") as f:
            cols = list(review[0].keys())
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in review: w.writerow(r)

    # Summary
    with open(OUT_SUMMARY, "w") as f:
        f.write(f"# Embedding v3 (tightened) — canonical v3\n\n")
        f.write(f"Run: {ts}\n\n")
        f.write(f"## Filter rules\n")
        f.write(f"- KEEP if alt_sim >= {SIM_HIGH}, OR\n")
        f.write(f"- KEEP if alt_sim >= {SIM_MID} AND margin >= {MARGIN_REQ}\n\n")
        f.write(f"## Result\n")
        f.write(f"- Candidates from embed_reroute_applied.csv: **{len(candidates):,}**\n")
        f.write(f"- KEPT (applied to v3):                       **{len(keep_set):,}**\n")
        f.write(f"- Sent to review:                             **{len(review):,}**\n\n")
        f.write(f"- Source: vIdentity.fixed_v2.csv\n")
        f.write(f"- Output: vIdentity.fixed_v3.csv\n\n")
        f.write(f"## Top 20 source codes (rerouted FROM)\n\n")
        f.write("| code | description | n |\n|---|---|---:|\n")
        for code, n in by_source.most_common(20):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")
        f.write(f"\n## Top 20 destinations (rerouted TO)\n\n")
        f.write("| code | description | n |\n|---|---|---:|\n")
        for code, n in by_dest.most_common(20):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")

    print(f"\nWrote:")
    print(f"  {OUT_MAP}  ({n_changed:,} rows changed)")
    print(f"  {OUT_APPLIED}")
    print(f"  {OUT_REVIEW}  ({len(review):,} rows)")
    print(f"  {OUT_SUMMARY}")

if __name__ == "__main__":
    main()
