#!/usr/bin/env python3
"""
Rebuild vIdentity.csv from baseline + trusted changelogs only.

Rolls back the bad primary_identity_fix (38% regression rate per audit) and
the abandoned experiments (cohort_reroute v3 TF-IDF, v4 cluster-coupling).

Replays only trusted changelogs in chronological order:
  1. preliminary_fix_changelog.csv         (2,861 — 4-dumping-ground LLM)
  2. audit_apply_changelog.csv             (3,815 — partial LLM audit)
  3. embed_v3_applied.csv                  (6,523 — embedding reroute, tightened)
  4. v5_changelog.csv                      (2,024 — per-product tree match)
  5. fndds_fix_changelog.csv               (8,687 — FNDDS exact match)

Total preserved fixes: ~23,910 (vs 183k bad batch we're throwing out).

Each fix preserves audit trail in best_esha_original_code/_description and
stamps best_esha_change_reason + assignment_source.
"""
import csv, os, shutil
from collections import OrderedDict

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
OUT_DIR = f"{ROOT}/implementation/output"
BASELINE = f"{OUT_DIR}/product_to_best_esha_full_map.vIdentity.baseline.csv"
CANON = f"{OUT_DIR}/product_to_best_esha_full_map.vIdentity.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"

CHANGELOG_ORDER = [
    ("preliminary_fix_changelog.csv",     "llm_preliminary_fix_v1"),
    ("audit_apply_changelog.csv",         "llm_full_audit_v2"),
    ("embed_v3_applied.csv",              "embed_v3_tightened"),
    ("v5_changelog.csv",                  "tree_match_v5"),
    ("fndds_fix_changelog.csv",           "fndds_exact_fix"),
]

def main():
    print("Loading tree...", flush=True)
    code_to_desc = {}
    for r in csv.DictReader(open(TREE)):
        code_to_desc[r["EshaCode"]] = r["Description"]
    print(f"  {len(code_to_desc):,} codes")

    if not os.path.exists(BASELINE):
        print(f"ERROR: {BASELINE} missing — cannot rebuild")
        return
    print(f"\nStarting from baseline: {os.path.basename(BASELINE)}")
    shutil.copy2(BASELINE, CANON)
    print(f"  → reset {os.path.basename(CANON)} to baseline")

    # Apply each changelog in turn
    for fname, source in CHANGELOG_ORDER:
        path = f"{OUT_DIR}/{fname}"
        if not os.path.exists(path):
            print(f"  WARN: missing {fname} — skipping")
            continue
        # Load changelog into dict: fdc_id → new_code
        fixes = OrderedDict()
        with open(path) as f:
            for r in csv.DictReader(f):
                fid = r.get("fdc_id")
                if not fid: continue
                new_code = r.get("new_code","")
                if not new_code or new_code == "NONE": continue
                fixes[fid] = new_code
        print(f"\nApplying {len(fixes):,} fixes from {fname} (source={source})...")

        tmp = CANON + ".tmp"
        n_changed = 0
        with open(CANON) as fin, open(tmp, "w", newline="") as fout:
            rdr = csv.DictReader(fin)
            wtr = csv.DictWriter(fout, fieldnames=rdr.fieldnames, extrasaction="ignore")
            wtr.writeheader()
            for r in rdr:
                fid = r["fdc_id"]
                if fid in fixes:
                    new_code = fixes[fid]
                    new_desc = code_to_desc.get(new_code, "")
                    if new_code != r["best_esha_code"]:
                        if not r.get("best_esha_original_code"):
                            r["best_esha_original_code"] = r["best_esha_code"]
                            r["best_esha_original_description"] = r["best_esha_description"]
                        r["best_esha_code"] = new_code
                        r["best_esha_description"] = new_desc
                        r["best_esha_change_reason"] = source
                        r["assignment_source"] = source
                        n_changed += 1
                wtr.writerow(r)
        shutil.move(tmp, CANON)
        print(f"  applied {n_changed:,} changes")

    # Final sanity
    print("\n--- Verifying final state ---")
    counts_by_source = {}
    total = 0
    with open(CANON) as f:
        for r in csv.DictReader(f):
            total += 1
            s = r.get("assignment_source","")
            counts_by_source[s] = counts_by_source.get(s, 0) + 1
    print(f"Total rows: {total:,}")
    print("Top assignment_source values:")
    for s, n in sorted(counts_by_source.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {s or '(empty)':40s}  {n:>8,}")

if __name__ == "__main__":
    main()
