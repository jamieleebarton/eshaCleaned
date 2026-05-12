#!/usr/bin/env python3
"""Build the retail taxonomy directly from v6 — no new models, no clustering.

v6 already has, for ~98% of products:
  - WWEIA category (broad supercategory)
  - FNDDS code + description (retail-leaf level)
  - best_esha_code + description (brand-aware sub-leaf)
  - branded_food_category (retailer's bucket)

We aggregate those into:
  retail_mapper/retail_taxonomy_v8.csv      — one row per (wweia, fndds, esha_desc) leaf
  retail_mapper/product_to_retail_leaf_v8.csv  — one row per product, leaf assigned

Plus a quick fix: if WWEIA is missing, look it up from the FNDDS code's first 4
digits using the table built from v6's existing rows that DO have both.
"""
from __future__ import annotations
import os, sys, csv, time
from collections import Counter, defaultdict

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
V6   = os.path.join(RM, 'product_esha_fixy.v6.csv')
OUT_TAX = os.path.join(RM, 'retail_taxonomy_v8.csv')
OUT_MAP = os.path.join(RM, 'product_to_retail_leaf_v8.csv')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

log("PASS 1: build FNDDS-prefix → WWEIA lookup from rows that have both...")
fndds_to_wweia = defaultdict(Counter)  # fndds_code -> Counter(wweia_desc)
fndds_4_to_wweia = defaultdict(Counter)  # first 4 digits of fndds -> Counter(wweia_desc)
with open(V6, newline='') as fh:
    for r in csv.DictReader(fh):
        fc = (r.get('v6_fndds_code') or '').strip()
        wd = (r.get('wweia_category_description') or '').strip()
        if fc and wd:
            fndds_to_wweia[fc][wd] += 1
            fndds_4_to_wweia[fc[:4]][wd] += 1
log(f"  full-fndds wweia map: {len(fndds_to_wweia):,}")
log(f"  fndds-prefix-4 wweia map: {len(fndds_4_to_wweia):,}")

def lookup_wweia(fndds_code: str, fallback: str = '') -> str:
    if not fndds_code: return fallback
    if fndds_code in fndds_to_wweia:
        return fndds_to_wweia[fndds_code].most_common(1)[0][0]
    if fndds_code[:4] in fndds_4_to_wweia:
        return fndds_4_to_wweia[fndds_code[:4]].most_common(1)[0][0]
    return fallback

log("PASS 2: build leaves and write product→leaf...")
leaf_members: dict[tuple[str,str,str,str,str], list] = defaultdict(list)
n_total = 0; n_with_fndds = 0; n_with_wweia_filled = 0; n_with_wweia_orig = 0

with open(V6, newline='') as fh, open(OUT_MAP, 'w', newline='') as out:
    reader = csv.DictReader(fh)
    cols = ['gtin_upc','fdc_id','product_description','brand_name','branded_food_category',
            'wweia_category','fndds_code','fndds_description','esha_code','esha_description',
            'retail_leaf_name','supercategory']
    w = csv.writer(out)
    w.writerow(cols)
    for r in reader:
        n_total += 1
        gtin = r.get('gtin_upc') or ''
        fdc  = r.get('fdc_id') or ''
        desc = r.get('product_description') or ''
        brand = r.get('brand_name') or ''
        bfc  = r.get('branded_food_category') or ''
        fc = (r.get('v6_fndds_code') or '').strip()
        fd = (r.get('v6_fndds_description') or '').strip()
        ec = (r.get('best_esha_code') or '').strip()
        ed = (r.get('best_esha_description') or '').strip()
        wd = (r.get('wweia_category_description') or '').strip()

        if fc: n_with_fndds += 1
        if wd:
            n_with_wweia_orig += 1
        else:
            wd2 = lookup_wweia(fc)
            if wd2:
                wd = wd2
                n_with_wweia_filled += 1
        # retail leaf name = ESHA description if we have it (most granular and brand-aware)
        # else FNDDS description
        # else BFC
        leaf_name = ed or fd or bfc or 'Unclassified'
        # supercategory = WWEIA if we have it, else FNDDS first 2 digits give a coarse bucket
        super_cat = wd or 'Unclassified'

        # Group key: super → fndds → esha (collapsed)
        key = (super_cat, fc, fd, ec, ed)
        leaf_members[key].append((gtin, fdc, desc, brand, bfc))

        w.writerow([gtin, fdc, desc, brand, bfc, wd, fc, fd, ec, ed, leaf_name, super_cat])

log(f"  total: {n_total:,}")
log(f"  with v6_fndds: {n_with_fndds:,} ({100*n_with_fndds/n_total:.1f}%)")
log(f"  WWEIA original: {n_with_wweia_orig:,}, filled-from-fndds: {n_with_wweia_filled:,}")
log(f"  total WWEIA coverage: {(n_with_wweia_orig+n_with_wweia_filled):,} ({100*(n_with_wweia_orig+n_with_wweia_filled)/n_total:.1f}%)")
log(f"  unique leaves (super/fndds/esha): {len(leaf_members):,}")

log("PASS 3: write retail_taxonomy_v8.csv (one row per leaf)...")
with open(OUT_TAX, 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['supercategory','fndds_code','fndds_description','esha_code','esha_description',
                'n_members','sample_products','top_brands','top_bfcs'])
    for key, members in sorted(leaf_members.items(), key=lambda kv: -len(kv[1])):
        super_cat, fc, fd, ec, ed = key
        n = len(members)
        sample = ' || '.join(m[2][:55] for m in members[:5])
        brand_c = Counter(m[3] for m in members if m[3])
        bfc_c = Counter(m[4] for m in members if m[4])
        top_brands = ' | '.join(f"{b}({c})" for b, c in brand_c.most_common(3))
        top_bfcs = ' | '.join(f"{b}({c})" for b, c in bfc_c.most_common(3))
        w.writerow([super_cat, fc, fd, ec, ed, n, sample, top_brands, top_bfcs])

log(f"DONE")
print(f"\nFiles:\n  {OUT_TAX}\n  {OUT_MAP}")

# Quick stats summary
super_dist = Counter()
for key, members in leaf_members.items():
    super_dist[key[0]] += len(members)
print(f"\n=== Top 20 supercategories (WWEIA) ===")
for s, n in super_dist.most_common(20):
    print(f"  {n:>7,}  {s}")
