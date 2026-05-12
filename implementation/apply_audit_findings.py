#!/usr/bin/env python3
"""
Apply LLM audit findings (llm_full_audit.jsonl) to produce vIdentity.fixed_v2.csv.

Filter rules:
  APPLY when: verdict=WRONG AND suggested_code != "" AND suggested_code != "NONE"
              AND suggested_code exists in ESHA tree
              AND suggested_code != current_esha_code
              AND token-overlap confidence guard passes (>=1 meaningful word from
              product description appears in suggested ESHA description, OR
              brand_name appears in suggested description)

  SKIP (logged to low_confidence_fixes.csv) when:
              verdict=WRONG with suggestion but no token overlap (avoids
              "Pepperidge stuffing → Flour, bread" type mistakes).

  LEAVE UNCHANGED:
              verdict=CORRECT, UNCERTAIN, WRONG-with-NONE, errors.

Outputs:
  vIdentity.fixed_v2.csv
  audit_apply_changelog.csv     (one row per applied fix)
  low_confidence_fixes.csv      (one row per skipped low-confidence fix)
  audit_apply_summary.md
"""
import csv, json, os, re, sys
from collections import Counter, defaultdict
from datetime import datetime

ROOT = "/Users/jamiebarton/Desktop/esha_audit_bundle"
INPUT_MAP = f"{ROOT}/implementation/output/product_to_best_esha_full_map.vIdentity.fixed_v1.csv"
JSONL = f"{ROOT}/implementation/output/llm_full_audit.jsonl"
TREE = f"{ROOT}/esha_cleaned_canonical.csv"
OUT_DIR = f"{ROOT}/implementation/output"
OUT_MAP = f"{OUT_DIR}/product_to_best_esha_full_map.vIdentity.fixed_v2.csv"
CHANGELOG = f"{OUT_DIR}/audit_apply_changelog.csv"
LOW_CONF = f"{OUT_DIR}/low_confidence_fixes.csv"
SUMMARY = f"{OUT_DIR}/audit_apply_summary.md"

NEW_SOURCE = "llm_full_audit_v2"

STOPWORDS = {
    "with","and","the","of","to","in","for","by","on","at","from","as","or","an","a","is","are",
    "be","this","that","prepared","made","mix","pack","oz","fl","ounce","ounces","pound","pounds",
    "lb","each","ct","count","size","family","large","small","medium","big","jumbo","mini",
    "package","bag","box","bottle","jar","can","cup","cups","piece","pieces","container","kit",
    "free","added","without","none","new","original","ready","fresh","frozen","dry","dried","cooked",
    "raw","fried","baked","grilled","whole","sliced","diced","chopped","crushed",
    "low","high","reduced","light","lite","extra","plus","value","my","our","their",
    "no","not","one","two","three","four","five","six","seven","eight","nine","ten",
    "real","food","brand","product","item","item","items",
}

def tokenize(s):
    if not s: return set()
    return {t for t in re.findall(r"[a-z][a-z]+", s.lower()) if len(t) >= 4 and t not in STOPWORDS}

def confidence_ok(product_desc, brand, suggested_desc):
    pt = tokenize(product_desc)
    st = tokenize(suggested_desc)
    if pt & st:
        return True, sorted(pt & st)
    if brand:
        bt = tokenize(brand)
        if bt and bt & set(re.findall(r"[a-z][a-z]+", suggested_desc.lower())):
            return True, sorted(bt & set(re.findall(r"[a-z][a-z]+", suggested_desc.lower())))
    return False, []

def main():
    # Load tree
    code_to_desc = {}
    with open(TREE) as f:
        for r in csv.DictReader(f):
            code_to_desc[r["EshaCode"]] = r["Description"]
    print(f"Tree: {len(code_to_desc):,} codes")

    # Load product map (we need product_description + brand for the confidence check)
    print("Loading input map...")
    products = {}
    with open(INPUT_MAP) as f:
        for r in csv.DictReader(f):
            products[r["fdc_id"]] = r
    print(f"  {len(products):,} products in map")

    # Read JSONL findings
    print(f"Reading {JSONL}...")
    findings = []
    err = 0
    with open(JSONL) as f:
        for line in f:
            try:
                rec = json.loads(line)
                if "error" in rec: err += 1; continue
                findings.append(rec)
            except Exception:
                err += 1
    print(f"  {len(findings):,} findings ({err} errors skipped)")

    # Build fix map with confidence filter
    fixes = {}
    low_conf = []
    skipped_no_change = 0
    skipped_invalid = 0
    skipped_not_wrong = 0
    skipped_no_suggestion = 0
    verdict_counts = Counter()
    for rec in findings:
        verdict_counts[rec["llm_verdict"]] += 1
        if rec["llm_verdict"] != "WRONG":
            skipped_not_wrong += 1; continue
        sug = (rec.get("suggested_code") or "").strip()
        cur = (rec.get("current_esha_code") or "").strip()
        if not sug or sug == "NONE":
            skipped_no_suggestion += 1; continue
        if sug not in code_to_desc:
            skipped_invalid += 1; continue
        if sug == cur:
            skipped_no_change += 1; continue
        fdc_id = rec["fdc_id"]
        p = products.get(fdc_id, {})
        ok, overlap = confidence_ok(p.get("product_description",""), p.get("brand_name",""),
                                     code_to_desc[sug])
        entry = {
            "fdc_id": fdc_id, "old_code": cur, "old_desc": rec["current_esha_desc"],
            "new_code": sug, "new_desc": code_to_desc[sug],
            "mismatch_type": rec.get("mismatch_type",""), "reason": rec.get("reason",""),
            "fix_pattern": rec.get("fix_pattern",""), "rft_verdict": rec.get("rft_verdict",""),
            "overlap_words": "|".join(overlap),
        }
        if ok:
            fixes[fdc_id] = entry
        else:
            low_conf.append(entry)

    print(f"\nFiltering summary:")
    print(f"  total findings:               {len(findings):,}")
    print(f"  verdict counts:               {dict(verdict_counts)}")
    print(f"  skipped (not WRONG):          {skipped_not_wrong:,}")
    print(f"  skipped (no suggestion):      {skipped_no_suggestion:,}")
    print(f"  skipped (invalid code):       {skipped_invalid:,}")
    print(f"  skipped (no-op same as cur):  {skipped_no_change:,}")
    print(f"  low-confidence (logged):      {len(low_conf):,}")
    print(f"  HIGH-CONFIDENCE FIXES:        {len(fixes):,}")

    # Stream-rewrite map
    n_total = n_changed = 0
    by_old_code = defaultdict(int)
    by_type = Counter()
    by_new_code = Counter()
    ts = datetime.now().isoformat(timespec="seconds")
    with open(INPUT_MAP) as fin, open(OUT_MAP, "w", newline="") as fout, open(CHANGELOG, "w", newline="") as flog:
        rdr = csv.DictReader(fin)
        out_fields = list(rdr.fieldnames)
        if "llm_fix_applied" not in out_fields: out_fields.append("llm_fix_applied")
        wtr = csv.DictWriter(fout, fieldnames=out_fields, extrasaction="ignore")
        wtr.writeheader()

        log_fields = ["fdc_id","gtin_upc","product_description","brand_name","branded_food_category",
                      "old_code","old_desc","new_code","new_desc","mismatch_type","reason",
                      "fix_pattern","rft_verdict","overlap_words","applied_at"]
        log = csv.DictWriter(flog, fieldnames=log_fields)
        log.writeheader()

        for r in rdr:
            n_total += 1
            r["llm_fix_applied"] = r.get("llm_fix_applied","")
            fdc_id = r["fdc_id"]
            if fdc_id in fixes:
                fx = fixes[fdc_id]
                if not r.get("best_esha_original_code"):
                    r["best_esha_original_code"] = fx["old_code"]
                    r["best_esha_original_description"] = fx["old_desc"]
                r["best_esha_code"] = fx["new_code"]
                r["best_esha_description"] = fx["new_desc"]
                r["best_esha_change_reason"] = NEW_SOURCE
                r["assignment_source"] = NEW_SOURCE
                r["llm_fix_applied"] = fx["mismatch_type"]
                n_changed += 1
                by_old_code[fx["old_code"]] += 1
                by_type[fx["mismatch_type"]] += 1
                by_new_code[fx["new_code"]] += 1
                log.writerow({
                    "fdc_id": fdc_id, "gtin_upc": r.get("gtin_upc",""),
                    "product_description": r.get("product_description",""),
                    "brand_name": r.get("brand_name",""),
                    "branded_food_category": r.get("branded_food_category",""),
                    "old_code": fx["old_code"], "old_desc": fx["old_desc"],
                    "new_code": fx["new_code"], "new_desc": fx["new_desc"],
                    "mismatch_type": fx["mismatch_type"], "reason": fx["reason"],
                    "fix_pattern": fx["fix_pattern"], "rft_verdict": fx["rft_verdict"],
                    "overlap_words": fx["overlap_words"], "applied_at": ts,
                })
            wtr.writerow(r)

    # Write low-confidence log for manual review
    with open(LOW_CONF, "w", newline="") as f:
        cols = ["fdc_id","old_code","old_desc","suggested_code","suggested_desc",
                "mismatch_type","reason","fix_pattern","rft_verdict",
                "product_description","brand_name","branded_food_category"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for fx in low_conf:
            p = products.get(fx["fdc_id"], {})
            w.writerow({
                "fdc_id": fx["fdc_id"], "old_code": fx["old_code"], "old_desc": fx["old_desc"],
                "suggested_code": fx["new_code"], "suggested_desc": fx["new_desc"],
                "mismatch_type": fx["mismatch_type"], "reason": fx["reason"],
                "fix_pattern": fx["fix_pattern"], "rft_verdict": fx["rft_verdict"],
                "product_description": p.get("product_description",""),
                "brand_name": p.get("brand_name",""),
                "branded_food_category": p.get("branded_food_category",""),
            })

    print(f"\nWrote: {OUT_MAP}  ({n_total:,} rows, {n_changed:,} changed)")
    print(f"Wrote: {CHANGELOG}")
    print(f"Wrote: {LOW_CONF}  ({len(low_conf):,} skipped low-confidence fixes)")

    # Markdown summary
    with open(SUMMARY, "w") as f:
        f.write(f"# Audit findings applied — v2 fixes\n\n")
        f.write(f"Run: {ts}\n\n")
        f.write(f"- Source map: `vIdentity.fixed_v1.csv`\n")
        f.write(f"- Output map: `vIdentity.fixed_v2.csv`\n")
        f.write(f"- Changelog: `audit_apply_changelog.csv`\n")
        f.write(f"- Low-confidence skipped: `low_confidence_fixes.csv`\n\n")
        f.write(f"## Findings\n\n")
        f.write(f"- LLM judgments processed: **{len(findings):,}**\n")
        f.write(f"- Verdicts: {dict(verdict_counts)}\n\n")
        f.write(f"## Applied\n\n")
        f.write(f"- High-confidence fixes applied: **{n_changed:,}**\n")
        f.write(f"- Low-confidence (no token overlap, skipped): **{len(low_conf):,}**\n\n")
        f.write(f"## Top 15 source ESHA codes (where fixes came from)\n\n")
        f.write("| Old code | Old description | Fixes |\n|------|------|---:|\n")
        for code, n in Counter(by_old_code).most_common(15):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:80]} | {n:,} |\n")
        f.write(f"\n## Top 15 destination ESHA codes\n\n")
        f.write("| New code | Description | Fixes |\n|------|------|---:|\n")
        for code, n in by_new_code.most_common(15):
            f.write(f"| {code} | {code_to_desc.get(code,'')[:80]} | {n:,} |\n")
        f.write(f"\n## Mismatch type breakdown\n\n")
        f.write("| Type | Count |\n|------|---:|\n")
        for t, n in by_type.most_common():
            f.write(f"| {t} | {n:,} |\n")
    print(f"Wrote: {SUMMARY}")

if __name__ == "__main__":
    main()
