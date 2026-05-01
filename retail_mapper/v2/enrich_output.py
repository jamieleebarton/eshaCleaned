#!/usr/bin/env python3
"""Post-processing enrichment for retail_leaf_v2.csv.

Adds 4 categories of new columns so an LLM downstream has full context:

  INGREDIENTS:
    ing_full          - full ingredient list as written on packaging
    ing_top5          - first 5 ingredients pipe-delimited
    ing_categories    - ingredient TYPES (dairy | sweetener | mineral | ...)
    protein_source, dairy_source, grain_source, sweetener_source, oil_source
    has_cocoa, has_batter, has_hot_dog, has_breading

  TF-IDF DISTINCTIVE TOKENS:
    distinctive_tokens - top-5 tokens by TF-IDF score; tells the LLM which
                         words in this title are most informative
    distinctive_bigrams - top-3 bigrams by frequency

  CO-SIGNAL CHECKS:
    bfc_modal_super       - what supercategory most products with this BFC land in
    bfc_super_match       - does THIS row's supercategory match the modal? (TRUE/FALSE)
    fndds_modal_super     - what supercategory most products with this current_esha land in
    fndds_super_match     - does THIS row's supercategory match the modal? (TRUE/FALSE)
    brand_modal_super     - same for brand_owner
    brand_super_match     - same

  CONSISTENCY:
    siblings_same_leaf    - count of products with same current_esha that landed in same leaf
    siblings_same_super   - count with same current_esha and same supercategory
    siblings_total        - total products with same current_esha

Output: retail_leaf_v2_enriched.csv  (same row count, more columns)
"""
from __future__ import annotations
import csv, sys, time, re
import collections
import math
csv.field_size_limit(sys.maxsize)

REPO = "/Users/jamiebarton/Desktop/esha_audit_bundle"
IN_CSV  = f"{REPO}/retail_mapper/v2/retail_leaf_v2.csv"
ING_CSV = f"{REPO}/retail_mapper/parsed_titles_with_ingredients.csv"
AUDIT   = f"{REPO}/implementation/output/product_esha_fixy.csv"
OUT_CSV = f"{REPO}/retail_mapper/v2/retail_leaf_v2_enriched.csv"

print("--- 1. loading ingredients lookup ---")
t0 = time.time()
ing_idx = {}
with open(ING_CSV, errors='replace') as f:
    for r in csv.DictReader(f):
        fdc = r.get('fdc_id') or ''
        if not fdc: continue
        ing_idx[fdc] = {
            "ing_full":          (r.get('ing_full') or '')[:1000],
            "ing_top5":          (r.get('ing_top5') or '')[:300],
            "ing_categories":    r.get('ing_categories') or '',
            "protein_source":    r.get('protein_source') or '',
            "dairy_source":      r.get('dairy_source') or '',
            "grain_source":      r.get('grain_source') or '',
            "sweetener_source":  r.get('sweetener_source') or '',
            "oil_source":        r.get('oil_source') or '',
            "has_cocoa":         r.get('has_cocoa') or '',
            "has_batter":        r.get('has_batter') or '',
            "has_hot_dog":       r.get('has_hot_dog') or '',
            "has_breading":      r.get('has_breading') or '',
        }
print(f"  {len(ing_idx):,} ingredient records ({time.time()-t0:.1f}s)")

print("\n--- 2. loading audit (brand_owner, BFC) ---")
t0 = time.time()
brand_idx = {}
with open(AUDIT, errors='replace') as f:
    for r in csv.DictReader(f):
        fdc = r.get('fdc_id') or ''
        if fdc and fdc not in brand_idx:
            brand_idx[fdc] = {
                "brand_owner": r.get('brand_owner') or '',
                "brand_name":  r.get('brand_name') or '',
            }
print(f"  {len(brand_idx):,} brand records ({time.time()-t0:.1f}s)")

print("\n--- 3. computing TF-IDF over titles (one pass, sparse counts) ---")
t0 = time.time()
TOKEN = re.compile(r"[a-z0-9]+")
STOP = {"and","or","with","of","the","a","an","in","to","for","from","on","as","is","are",
        "less","than","plus","added","also","by","at","be","this","may","not","other","each",
        "per","new","oz","ml","ct","pk","pack","case","fl","g","kg","lb","lbs","count"}
def tok(s):
    return [t for t in TOKEN.findall((s or '').lower()) if t not in STOP and len(t) >= 3]

# pass 1: document frequency
df = collections.Counter()
n_docs = 0
title_by_fdc = {}
super_by_fdc = {}
bfc_by_fdc = {}
fndds_by_fdc = {}
with open(IN_CSV) as f:
    for r in csv.DictReader(f):
        n_docs += 1
        fdc = r['fdc_id']
        title_by_fdc[fdc] = r['title']
        super_by_fdc[fdc] = (r['retail_leaf'].split(' > ')[0] if r['retail_leaf'] else '')
        bfc_by_fdc[fdc] = r.get('branded_food_category') or ''
        fndds_by_fdc[fdc] = r.get('current_esha') or ''
        seen = set(tok(r['title']))
        for t in seen: df[t] += 1
print(f"  {n_docs:,} docs, vocab={len(df):,} ({time.time()-t0:.1f}s)")

# idf
idf = {t: math.log(n_docs / (1 + c)) for t, c in df.items()}

# co-signal modal supercategories
print("\n--- 4. computing co-signal modal supercategories ---")
t0 = time.time()
bfc_super = collections.defaultdict(collections.Counter)
fndds_super = collections.defaultdict(collections.Counter)
brand_super = collections.defaultdict(collections.Counter)
fndds_total = collections.Counter()
fndds_leaf  = collections.defaultdict(collections.Counter)
with open(IN_CSV) as f:
    for r in csv.DictReader(f):
        fdc = r['fdc_id']
        s = super_by_fdc.get(fdc, '')
        if not s: continue
        if bfc_by_fdc.get(fdc):    bfc_super[bfc_by_fdc[fdc].lower()][s] += 1
        if fndds_by_fdc.get(fdc):
            fc = fndds_by_fdc[fdc]
            fndds_super[fc][s] += 1
            fndds_total[fc] += 1
            fndds_leaf[fc][r['retail_leaf']] += 1
        bo = brand_idx.get(fdc, {}).get('brand_owner', '').lower()
        if bo: brand_super[bo][s] += 1

bfc_modal   = {k: c.most_common(1)[0][0] for k, c in bfc_super.items()}
fndds_modal = {k: c.most_common(1)[0][0] for k, c in fndds_super.items()}
brand_modal = {k: c.most_common(1)[0][0] for k, c in brand_super.items() if sum(c.values()) >= 5}
print(f"  bfc-modal: {len(bfc_modal):,}  fndds-modal: {len(fndds_modal):,}  brand-modal: {len(brand_modal):,}")

# 5. write enriched output
print(f"\n--- 5. writing enriched output ---")
t0 = time.time()
with open(IN_CSV) as fin, open(OUT_CSV, 'w', newline='') as fout:
    reader = csv.DictReader(fin)
    out_cols = list(reader.fieldnames) + [
        # ingredients
        "ing_full","ing_top5","ing_categories",
        "protein_source","dairy_source","grain_source","sweetener_source","oil_source",
        # brand
        "brand_owner","brand_name",
        # tf-idf
        "distinctive_tokens","distinctive_bigrams",
        # co-signal modals
        "bfc_modal_super","bfc_super_match",
        "fndds_modal_super","fndds_super_match",
        "brand_modal_super","brand_super_match",
        # consistency
        "siblings_same_leaf","siblings_same_super","siblings_total",
    ]
    w = csv.DictWriter(fout, fieldnames=out_cols)
    w.writeheader()
    n_written = 0
    for r in reader:
        fdc = r['fdc_id']
        s = super_by_fdc.get(fdc, '')
        # tf-idf top tokens
        tokens = tok(r['title'])
        if tokens:
            scores = [(t, tokens.count(t) * idf.get(t, 0)) for t in set(tokens)]
            scores.sort(key=lambda x: -x[1])
            distinctive = " | ".join(t for t, _ in scores[:5])
            # bigrams
            bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
            bg = collections.Counter(bigrams).most_common(3)
            distinctive_bg = " | ".join(b for b, _ in bg)
        else:
            distinctive = distinctive_bg = ""

        # co-signal modals + match
        bfc_lc = (r.get('branded_food_category') or '').lower()
        fc = r.get('current_esha') or ''
        bo = brand_idx.get(fdc, {}).get('brand_owner', '').lower()
        bfc_m  = bfc_modal.get(bfc_lc, '')
        fndds_m= fndds_modal.get(fc, '')
        brand_m= brand_modal.get(bo, '')

        # consistency: how many same-fndds products land in same leaf vs same super
        same_leaf = fndds_leaf.get(fc, {}).get(r['retail_leaf'], 0)
        same_super_count = sum(c for sup, c in fndds_super.get(fc, {}).items() if sup == s)
        total_fndds = fndds_total.get(fc, 0)

        ing = ing_idx.get(fdc, {})
        b   = brand_idx.get(fdc, {})

        out = dict(r)
        out.update({
            "ing_full":          ing.get("ing_full",""),
            "ing_top5":          ing.get("ing_top5",""),
            "ing_categories":    ing.get("ing_categories",""),
            "protein_source":    ing.get("protein_source",""),
            "dairy_source":      ing.get("dairy_source",""),
            "grain_source":      ing.get("grain_source",""),
            "sweetener_source":  ing.get("sweetener_source",""),
            "oil_source":        ing.get("oil_source",""),
            "brand_owner":       b.get("brand_owner",""),
            "brand_name":        b.get("brand_name",""),
            "distinctive_tokens":distinctive,
            "distinctive_bigrams":distinctive_bg,
            "bfc_modal_super":   bfc_m,
            "bfc_super_match":   "TRUE" if (bfc_m and bfc_m == s) else ("FALSE" if bfc_m else ""),
            "fndds_modal_super": fndds_m,
            "fndds_super_match": "TRUE" if (fndds_m and fndds_m == s) else ("FALSE" if fndds_m else ""),
            "brand_modal_super": brand_m,
            "brand_super_match": "TRUE" if (brand_m and brand_m == s) else ("FALSE" if brand_m else ""),
            "siblings_same_leaf": same_leaf,
            "siblings_same_super": same_super_count,
            "siblings_total":    total_fndds,
        })
        w.writerow(out)
        n_written += 1
        if n_written % 50000 == 0:
            print(f"  {n_written:>7,}  ({(time.time()-t0)/60:.1f}m)")
print(f"\nwrote {OUT_CSV}  ({n_written} rows, {(time.time()-t0)/60:.1f}m)")
