#!/usr/bin/env python3
"""
1) FILE CONSOLIDATION
   - Move existing canonical map → vIdentity.baseline.csv (preserve original)
   - Move v5 → vIdentity.csv (canonical, in-place going forward)
   - Delete v1, v2, v3, v3_embed, v3_tfidf_DEPRECATED, v4 (free ~1 GB)

2) FNDDS-DRIVEN FIX (deterministic, signal already in data)
   For each product:
     - skip if rft_fndds_desc empty
     - skip if rft_fndds_level != "exact"  (only use highest-confidence FNDDS matches)
     - find ESHA code whose lowercased Description == rft_fndds_desc lowercased
     - skip if no match, or new == current
     - skip if rft_verdict in (STRONG, EXACT)  (don't override high-confidence)
     - apply for rft_verdict in (WEAK, NEEDS_NEW_CONCEPT, NO_MATCH, COMPOSITE,
       NO_IDENTITY)

   This uses a signal that was sitting in the data: when FNDDS says "exact"
   for a description that maps directly to an ESHA leaf, trust it for the
   weak/needs_new_concept cohort.

Outputs (after consolidation):
  vIdentity.csv               (new canonical, with FNDDS fixes applied)
  vIdentity.baseline.csv      (original, preserved)
  fndds_fix_changelog.csv     (per-fix audit trail)
  fndds_fix_summary.md
"""
import csv, os, shutil, sys
from collections import Counter, defaultdict
from datetime import datetime

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
OUT_DIR = f"{ROOT}/implementation/output"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"

CANON = f"{OUT_DIR}/product_to_best_esha_full_map.vIdentity.csv"
V5 = f"{OUT_DIR}/product_to_best_esha_full_map.vIdentity.fixed_v5.csv"
BASELINE = f"{OUT_DIR}/product_to_best_esha_full_map.vIdentity.baseline.csv"
NEW_CANON = CANON   # we keep the same canonical name and write into it

DELETE = [
    "product_to_best_esha_full_map.vIdentity.fixed_v1.csv",
    "product_to_best_esha_full_map.vIdentity.fixed_v2.csv",
    "product_to_best_esha_full_map.vIdentity.fixed_v3.csv",
    "product_to_best_esha_full_map.vIdentity.fixed_v3_embed.csv",
    "product_to_best_esha_full_map.vIdentity.fixed_v3_tfidf_DEPRECATED.csv",
    "product_to_best_esha_full_map.vIdentity.fixed_v4.csv",
]

CHANGELOG = f"{OUT_DIR}/fndds_fix_changelog.csv"
SUMMARY = f"{OUT_DIR}/fndds_fix_summary.md"
NEW_SOURCE = "fndds_exact_fix"

WEAK_VERDICTS = {"WEAK", "NEEDS_NEW_CONCEPT", "NO_MATCH", "COMPOSITE", "NO_IDENTITY", ""}

def consolidate():
    print("=== STAGE 1: file consolidation ===\n", flush=True)
    # 1a. preserve original as baseline if not already
    if not os.path.exists(BASELINE) and os.path.exists(CANON):
        # the current CANON is the "original" (predates our fix passes)
        shutil.copy2(CANON, BASELINE)
        print(f"  preserved → {os.path.basename(BASELINE)}")
    # 1b. promote v5 into canonical position
    if os.path.exists(V5):
        shutil.move(V5, NEW_CANON)
        print(f"  promoted v5 → {os.path.basename(NEW_CANON)}")
    # 1c. delete intermediate versions
    freed = 0
    for f in DELETE:
        p = f"{OUT_DIR}/{f}"
        if os.path.exists(p):
            sz = os.path.getsize(p)
            os.remove(p)
            freed += sz
            print(f"  deleted {f} ({sz/1024/1024:.0f} MB)")
    print(f"\n  freed {freed/1024/1024:.0f} MB total")

def fndds_fix():
    print("\n=== STAGE 2: FNDDS-driven fix ===\n", flush=True)

    # Build ESHA tree lookup: lowercase description → code
    print("Loading ESHA tree...", flush=True)
    desc_to_code = {}
    code_to_desc = {}
    for r in csv.DictReader(open(TREE)):
        d = r["Description"].lower().strip()
        if d not in desc_to_code:
            desc_to_code[d] = r["EshaCode"]
        code_to_desc[r["EshaCode"]] = r["Description"]
    print(f"  {len(desc_to_code):,} unique descriptions in tree", flush=True)

    # Read current canonical, decide fixes
    print("Reading canonical map and finding fixes...", flush=True)
    rows = list(csv.DictReader(open(NEW_CANON)))
    fields = list(rows[0].keys()) if rows else []
    print(f"  {len(rows):,} rows", flush=True)

    fixes = {}        # fdc_id -> dict
    skip_no_fndds = 0
    skip_not_exact = 0
    skip_no_tree_match = 0
    skip_no_change = 0
    skip_strong = 0

    for r in rows:
        fd = (r.get("rft_fndds_desc") or "").strip().lower()
        lv = (r.get("rft_fndds_level") or "").strip().lower()
        cur = r.get("best_esha_code", "")
        v = r.get("rft_verdict", "")
        if not fd:
            skip_no_fndds += 1; continue
        if lv != "exact":
            skip_not_exact += 1; continue
        if fd not in desc_to_code:
            skip_no_tree_match += 1; continue
        new_code = desc_to_code[fd]
        if new_code == cur:
            skip_no_change += 1; continue
        if v not in WEAK_VERDICTS:
            skip_strong += 1; continue
        fixes[r["fdc_id"]] = {
            "fdc_id": r["fdc_id"],
            "old_code": cur,
            "old_desc": r.get("best_esha_description", ""),
            "new_code": new_code,
            "new_desc": code_to_desc[new_code],
            "rft_verdict": v,
            "rft_fndds_desc": fd,
            "rft_fndds_level": lv,
            "product_description": r.get("product_description", ""),
            "brand_name": r.get("brand_name", ""),
            "branded_food_category": r.get("branded_food_category", ""),
        }

    print(f"\nFNDDS fix decisions:")
    print(f"  ELIGIBLE FIXES:                 {len(fixes):,}")
    print(f"  skipped no FNDDS:               {skip_no_fndds:,}")
    print(f"  skipped FNDDS level != exact:   {skip_not_exact:,}")
    print(f"  skipped no tree match:          {skip_no_tree_match:,}")
    print(f"  skipped already-correct:        {skip_no_change:,}")
    print(f"  skipped (rft was STRONG/EXACT): {skip_strong:,}  (preserved)")

    # Apply in-place: read canonical, rewrite to temp, replace
    print(f"\nApplying {len(fixes):,} fixes IN PLACE to {os.path.basename(NEW_CANON)}...", flush=True)
    ts = datetime.now().isoformat(timespec="seconds")
    n_changed = 0
    by_dest = Counter(); by_source = Counter()
    tmp = NEW_CANON + ".tmp"
    with open(NEW_CANON) as fin, open(tmp, "w", newline="") as fout, \
         open(CHANGELOG, "w", newline="") as flog:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames, extrasaction="ignore")
        wtr.writeheader()
        log_cols = ["fdc_id","gtin_upc","product_description","brand_name","branded_food_category",
                    "old_code","old_desc","new_code","new_desc","rft_verdict",
                    "rft_fndds_desc","rft_fndds_level","applied_at"]
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
    shutil.move(tmp, NEW_CANON)
    print(f"  {n_changed:,} rows changed in place")

    # Summary
    with open(SUMMARY, "w") as f:
        f.write(f"# FNDDS-driven fix\n\n")
        f.write(f"Run: {ts}\n\n")
        f.write(f"## Method\n\n")
        f.write(f"For each product, when `rft_fndds_level == 'exact'` AND `rft_fndds_desc` "
                f"matches an ESHA tree description AND current `rft_verdict` is WEAK, "
                f"NEEDS_NEW_CONCEPT, NO_MATCH, COMPOSITE, or NO_IDENTITY → reroute to "
                f"the FNDDS-suggested code.\n\n")
        f.write(f"Note: STRONG and EXACT rft_verdicts are preserved (the signal was "
                f"already trusted).\n\n")
        f.write(f"## Result\n\n")
        f.write(f"- Rows changed: **{n_changed:,}**\n\n")
        f.write(f"## Top 25 source codes (rerouted FROM)\n\n")
        f.write("| code | description | n |\n|---|---|---:|\n")
        for code, n in by_source.most_common(25):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")
        f.write(f"\n## Top 25 destination codes (rerouted TO)\n\n")
        f.write("| code | description | n |\n|---|---|---:|\n")
        for code, n in by_dest.most_common(25):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:60]} | {n:,} |\n")

    print(f"\nWrote:")
    print(f"  {NEW_CANON}  (canonical, in-place)")
    print(f"  {CHANGELOG}")
    print(f"  {SUMMARY}")

if __name__ == "__main__":
    consolidate()
    fndds_fix()
    print("\n=== DONE ===")
    print(f"Going forward: edit {os.path.basename(NEW_CANON)} in place. "
          "All baseline preserved in {os.path.basename(BASELINE)}.")
