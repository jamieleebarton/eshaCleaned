#!/usr/bin/env python3
"""Build product_esha_fixy.v7preview.csv — a merged view of the original
product_esha_fixy.v6.csv columns plus parsed_titles.csv axis columns,
joined on (gtin_upc, fdc_id). One row per source product.
"""
import csv, sys, os, json, time
from collections import Counter

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle/retail_mapper'
SRC  = os.path.join(ROOT, 'product_esha_fixy.v6.csv')
PARSED = os.path.join(ROOT, 'parsed_titles.csv')
OUT  = os.path.join(ROOT, 'product_esha_fixy.v7preview.csv')
SUMM = os.path.join(ROOT, 'v7preview_summary.txt')
BUGS = os.path.join(ROOT, 'v7preview_bug_samples.csv')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

PARSE_COLS = ['retail_type','supercategory','category_group','category','primary_food',
              'form','cut','prep_state','storage','flavor','flavor_blend','inclusions',
              'claims','dish_type','pack_format','components','retail_leaf','confidence',
              'needs_review']

# ---- load parsed by (gtin, fdc) and by fdc, by gtin (fallbacks) ----
log("Loading parsed_titles.csv...")
parsed_by_pair = {}
parsed_by_fdc  = {}
parsed_by_gtin = {}
with open(PARSED, newline='') as fh:
    reader = csv.DictReader(fh)
    for r in reader:
        gtin = (r.get('gtin_upc') or '').strip()
        fdc  = (r.get('fdc_id') or '').strip()
        slim = {k: r.get(k, '') for k in PARSE_COLS}
        if gtin and fdc:
            parsed_by_pair[(gtin, fdc)] = slim
        if fdc:
            parsed_by_fdc[fdc] = slim
        if gtin:
            parsed_by_gtin[gtin] = slim
log(f"  pair index: {len(parsed_by_pair):,}  fdc: {len(parsed_by_fdc):,}  gtin: {len(parsed_by_gtin):,}")

# ---- merge ----
log("Merging into v7preview...")
src_rows = 0
matched = 0
type_counter = Counter()
sup_counter = Counter()
leaf_counter = Counter()
review_total = 0
bug_samples = []  # collect 200 rows where review flagged or where category missing

with open(SRC, newline='') as src_fh, open(OUT, 'w', newline='') as out_fh:
    reader = csv.DictReader(src_fh)
    in_fields = reader.fieldnames[:]
    out_fields = in_fields + ['v7_' + c for c in PARSE_COLS]
    writer = csv.DictWriter(out_fh, fieldnames=out_fields)
    writer.writeheader()
    for r in reader:
        src_rows += 1
        gtin = (r.get('gtin_upc') or '').strip()
        fdc  = (r.get('fdc_id') or '').strip()
        p = parsed_by_pair.get((gtin, fdc)) or parsed_by_fdc.get(fdc) or parsed_by_gtin.get(gtin)
        if p:
            matched += 1
            for c in PARSE_COLS:
                r['v7_' + c] = p.get(c, '')
            type_counter[p.get('retail_type','')] += 1
            sup_counter[p.get('supercategory','')] += 1
            leaf_counter[p.get('retail_leaf','')] += 1
            nr = p.get('needs_review','[]')
            if nr and nr != '[]':
                review_total += 1
                if len(bug_samples) < 200:
                    bug_samples.append(r.copy())
        else:
            for c in PARSE_COLS:
                r['v7_' + c] = ''
        writer.writerow({k: r.get(k,'') for k in out_fields})

log(f"Source rows: {src_rows:,}, matched: {matched:,} ({100*matched/src_rows:.1f}%)")

# ---- summary ----
log("Writing summary...")
with open(SUMM, 'w') as fh:
    fh.write(f"=== v7 preview summary  ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===\n\n")
    fh.write(f"Source rows:         {src_rows:>10,}\n")
    fh.write(f"Matched to parsed:   {matched:>10,}  ({100*matched/src_rows:.1f}%)\n")
    fh.write(f"Needs review:        {review_total:>10,}  ({100*review_total/matched:.1f}% of matched)\n\n")
    fh.write("retail_type distribution:\n")
    for k, v in type_counter.most_common():
        fh.write(f"  {k:<18s} {v:>10,}\n")
    fh.write(f"\nUnique retail_leaves: {len(leaf_counter):,}\n\n")
    fh.write("Top 50 supercategories:\n")
    for k, v in sup_counter.most_common(20):
        fh.write(f"  {v:>10,}  {k!r}\n")
    fh.write(f"\nTop 100 retail_leaves:\n")
    for leaf, n in leaf_counter.most_common(100):
        fh.write(f"  {n:>6,}  {leaf}\n")

# ---- bug samples (200 rows where needs_review flagged) ----
log("Writing bug samples...")
if bug_samples:
    with open(BUGS, 'w', newline='') as fh:
        sample_cols = ['gtin_upc','fdc_id','product_description','branded_food_category','brand_owner',
                       'best_esha_code','best_esha_description','v6_fndds_code','v6_fndds_description',
                       'v7_retail_type','v7_supercategory','v7_category_group','v7_category',
                       'v7_primary_food','v7_form','v7_flavor','v7_retail_leaf','v7_needs_review']
        # Use only cols that exist
        ex_cols = [c for c in sample_cols if c in bug_samples[0]]
        w = csv.DictWriter(fh, fieldnames=ex_cols)
        w.writeheader()
        for r in bug_samples:
            w.writerow({k: r.get(k,'') for k in ex_cols})

log("DONE")
print(f"\nFiles:\n  {OUT}\n  {SUMM}\n  {BUGS}")
