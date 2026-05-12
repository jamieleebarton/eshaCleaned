#!/usr/bin/env python3
"""
Apply preliminary LLM fix proposals back to product_to_best_esha_full_map.vIdentity.csv.

Only applies HIGH-CONFIDENCE fixes:
  - llm_verdict == "WRONG"
  - suggested_code is non-empty and != "NONE"
  - suggested_code exists in the ESHA tree

Produces:
  - product_to_best_esha_full_map.vIdentity.fixed_v1.csv  (full map, with rows fixed)
  - preliminary_fix_changelog.csv                          (one row per change)
  - preliminary_fix_summary.md                             (human-readable summary)

Original file is left untouched.
"""
import csv, json, os, sys
from collections import Counter, defaultdict
from datetime import datetime

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.csv"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
OUT_DIR = f"{ROOT}/implementation/output"

FIX_FILES = [
    ("38579", "preliminary_fix_38579_pasta_macaroni_elbow.csv",                   "Pasta dumping ground"),
    ("91074", "preliminary_fix_91074_candy_corn.csv",                             "Candy corn dumping ground"),
    ("8361",  "preliminary_fix_8361_olive_oil_evoo.csv",                          "Olive oil over-merging"),
    ("807",   "preliminary_fix_807_flavored_water_strawberry_watermelon.csv",     "Flavored water dumping ground"),
]

NEW_ASSIGNMENT_SOURCE = "llm_preliminary_fix_v1"

def main():
    # Load ESHA tree for code -> description lookup + validation
    code_to_desc = {}
    with open(TREE) as f:
        for r in csv.DictReader(f):
            code_to_desc[r["EshaCode"]] = r["Description"]
    print(f"Loaded {len(code_to_desc):,} ESHA codes from tree")

    # Build fix map: fdc_id -> (new_code, new_desc, source_reason, source_pattern, mismatch_type, original_code)
    fixes = {}
    skipped_invalid_code = 0
    skipped_low_confidence = 0
    skipped_no_change = 0
    by_source_code = defaultdict(int)

    for source_code, fname, _label in FIX_FILES:
        fp = f"{OUT_DIR}/{fname}"
        if not os.path.exists(fp):
            print(f"WARN: missing {fp}"); continue
        n_rows = n_applied = 0
        with open(fp) as f:
            for r in csv.DictReader(f):
                n_rows += 1
                if r.get("error"): continue
                v = r["llm_verdict"]
                sug = (r.get("suggested_code") or "").strip()
                cur = (r.get("current_esha_code") or "").strip()
                # High-confidence rule: WRONG + non-NONE suggestion
                if v != "WRONG" or not sug or sug == "NONE":
                    skipped_low_confidence += 1
                    continue
                # Validate suggested code exists in tree
                if sug not in code_to_desc:
                    skipped_invalid_code += 1
                    continue
                # Skip no-op
                if sug == cur:
                    skipped_no_change += 1
                    continue
                fixes[r["fdc_id"]] = {
                    "new_code": sug,
                    "new_desc": code_to_desc[sug],
                    "old_code": cur,
                    "old_desc": r.get("current_esha_desc",""),
                    "mismatch_type": r.get("mismatch_type",""),
                    "reason": r.get("reason",""),
                    "fix_pattern": r.get("fix_pattern",""),
                    "source_dumping_code": source_code,
                }
                n_applied += 1
                by_source_code[source_code] += 1
        print(f"  [{source_code}] {fname}: {n_applied:,}/{n_rows:,} applied")

    print(f"\nTotal fixes to apply: {len(fixes):,}")
    print(f"  skipped (low confidence / NONE):  {skipped_low_confidence:,}")
    print(f"  skipped (suggested code not in tree): {skipped_invalid_code:,}")
    print(f"  skipped (no-op, same as current):     {skipped_no_change:,}")

    # Stream the original map -> fixed_v1 map, applying fixes
    out_map = f"{OUT_DIR}/product_to_best_esha_full_map.vIdentity.fixed_v1.csv"
    changelog = f"{OUT_DIR}/preliminary_fix_changelog.csv"
    n_total = n_changed = 0

    with open(MAP) as fin, open(out_map, "w", newline="") as fout, open(changelog, "w", newline="") as flog:
        rdr = csv.DictReader(fin)
        # Add 1 new column to mark the LLM source
        out_fields = list(rdr.fieldnames) + (["llm_fix_applied"] if "llm_fix_applied" not in rdr.fieldnames else [])
        wtr = csv.DictWriter(fout, fieldnames=out_fields, extrasaction="ignore")
        wtr.writeheader()

        log_fields = ["fdc_id","gtin_upc","product_description","brand_name","branded_food_category",
                      "old_code","old_desc","new_code","new_desc","mismatch_type","reason",
                      "fix_pattern","source_dumping_code","applied_at"]
        log = csv.DictWriter(flog, fieldnames=log_fields)
        log.writeheader()
        ts = datetime.now().isoformat(timespec="seconds")

        for r in rdr:
            n_total += 1
            fdc_id = r["fdc_id"]
            r["llm_fix_applied"] = ""
            if fdc_id in fixes:
                fx = fixes[fdc_id]
                # Preserve original assignment in best_esha_original_* if not already populated
                if not r.get("best_esha_original_code"):
                    r["best_esha_original_code"] = fx["old_code"]
                    r["best_esha_original_description"] = fx["old_desc"]
                # Apply fix
                r["best_esha_code"] = fx["new_code"]
                r["best_esha_description"] = fx["new_desc"]
                r["best_esha_change_reason"] = "llm_preliminary_fix_v1"
                r["assignment_source"] = NEW_ASSIGNMENT_SOURCE
                r["llm_fix_applied"] = fx["mismatch_type"]
                n_changed += 1
                log.writerow({
                    "fdc_id": fdc_id, "gtin_upc": r.get("gtin_upc",""),
                    "product_description": r.get("product_description",""),
                    "brand_name": r.get("brand_name",""),
                    "branded_food_category": r.get("branded_food_category",""),
                    "old_code": fx["old_code"], "old_desc": fx["old_desc"],
                    "new_code": fx["new_code"], "new_desc": fx["new_desc"],
                    "mismatch_type": fx["mismatch_type"], "reason": fx["reason"],
                    "fix_pattern": fx["fix_pattern"],
                    "source_dumping_code": fx["source_dumping_code"],
                    "applied_at": ts,
                })
            wtr.writerow(r)

    print(f"\nWrote: {out_map}")
    print(f"  total rows:   {n_total:,}")
    print(f"  rows changed: {n_changed:,}  ({n_changed/n_total*100:.2f}%)")
    print(f"Wrote: {changelog}")

    # Distribution of new codes
    new_code_dist = Counter(fx["new_code"] for fx in fixes.values())
    type_dist = Counter(fx["mismatch_type"] for fx in fixes.values())

    # Summary markdown
    summary = f"{OUT_DIR}/preliminary_fix_summary.md"
    with open(summary, "w") as f:
        f.write(f"# Preliminary LLM Fix Summary\n\n")
        f.write(f"Run: {ts}\n\n")
        f.write(f"**Source map**: `{os.path.basename(MAP)}`\n")
        f.write(f"**Fixed map**: `{os.path.basename(out_map)}`\n")
        f.write(f"**Changelog**: `{os.path.basename(changelog)}`\n\n")
        f.write(f"**Total rows in map**: {n_total:,}\n")
        f.write(f"**Rows changed**: {n_changed:,}\n\n")
        f.write(f"## Fixes by source dumping-ground code\n\n")
        f.write("| Source code | Description | Fixes applied |\n|------|------|---:|\n")
        for code, _, label in FIX_FILES:
            f.write(f"| {code} | {label} | {by_source_code.get(code,0):,} |\n")
        f.write("\n## Fixes by mismatch type\n\n")
        f.write("| Mismatch type | Count |\n|------|---:|\n")
        for t, n in type_dist.most_common():
            f.write(f"| {t} | {n:,} |\n")
        f.write(f"\n## Top 20 destination ESHA codes\n\n")
        f.write("| New code | Description | Count |\n|------|------|---:|\n")
        for code, n in new_code_dist.most_common(20):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:80]} | {n:,} |\n")
        f.write(f"\n## Skipped (left unchanged)\n\n")
        f.write(f"- Low confidence (CORRECT/UNCERTAIN or NONE): {skipped_low_confidence:,}\n")
        f.write(f"- Suggested code not in ESHA tree:               {skipped_invalid_code:,}\n")
        f.write(f"- No-op (suggested == current):                  {skipped_no_change:,}\n")

    print(f"Wrote: {summary}")

if __name__ == "__main__":
    main()
