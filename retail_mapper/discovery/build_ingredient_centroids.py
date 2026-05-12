#!/usr/bin/env python3
"""Build ingredient TF-IDF centroids per FNDDS code from fixy_done/.

Output: retail_mapper/axes/ingredient_centroids.tsv
Columns: fndds_code, fndds_description, n_products, top_tokens (token:score|...)

Each product's ingredient signature is the SET of normalized ingredient tokens.
TF per FNDDS = doc count of token in that FNDDS bucket.
DF / IDF = computed across all FNDDS buckets.
top_tokens = top 25 by tf*idf.
"""
from __future__ import annotations
import os, csv, re, math, sys, glob, time
from collections import Counter, defaultdict

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
FIXY = os.path.join(ROOT, 'fixy_done')
OUT = os.path.join(ROOT, 'retail_mapper/axes/ingredient_centroids.tsv')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

NOISE = {
    'and','of','the','a','with','to','from','for','contains','less','than',
    'enriched','natural','flavor','flavors','food','color','colors',
    'water','salt','sugar','soybean','vegetable','spices','spice',
    'preservative','preservatives','citric','acid','calcium','sodium',
    'modified','starch','vinegar','dried','powder','extract','solids',
    'product','products','organic','sea','contains','contain','contained',
    'less','more','these','this','that','those','some','additional',
    'fresh','frozen','liquid','distilled','reduced','enriched','filtered',
    'thiamine','niacin','riboflavin','folic','iron','vitamin','mononitrate',
    'cellulose','potassium','calcium','phosphate','citric','lactic','malic',
    'monoglycerides','diglycerides','lecithin','xanthan','guar','locust','bean',
    'gum','annatto','turmeric','paprika','silicon','dioxide','sucralose','aspartame',
    'made','from','smaller','amount','contain','present','trace','traces',
}

TOK = re.compile(r"[a-z][a-z]+")

def signature(ingredients: str) -> set[str]:
    s = (ingredients or '').lower()
    s = re.sub(r'\([^)]*\)', ' ', s)  # drop parenthetical sub-ingredients
    return {t for t in TOK.findall(s) if len(t) > 3 and t not in NOISE}

# ---- Pass 1: per-FNDDS doc count of each token (TF) and overall N ----
log("Scanning fixy_done...")
files = glob.glob(os.path.join(FIXY, '*.csv'))
files = [f for f in files if os.path.basename(f)[0].isdigit()]  # only FNDDS-named files
log(f"  files: {len(files):,}")

per_fndds_tf = defaultdict(Counter)   # fndds -> Counter(token -> doc_count_in_bucket)
per_fndds_n  = Counter()              # fndds -> doc count
fndds_desc   = {}                     # fndds -> sample description
df_global    = Counter()              # token -> doc count across all FNDDS combined

for i, f in enumerate(files, 1):
    fndds_code = os.path.splitext(os.path.basename(f))[0]
    try:
        with open(f, newline='') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ing = row.get('ingredients') or ''
                sig = signature(ing)
                if not sig:
                    continue
                per_fndds_n[fndds_code] += 1
                for tok in sig:
                    per_fndds_tf[fndds_code][tok] += 1
                    df_global[tok] += 1
                if fndds_code not in fndds_desc:
                    d = row.get('fndds_descripton') or row.get('fndds_description') or ''
                    if d:
                        fndds_desc[fndds_code] = d
    except Exception as e:
        log(f"  ! {f}: {e}")
    if i % 1000 == 0:
        log(f"  ...{i:,} files / {sum(per_fndds_n.values()):,} docs")

log(f"  total products with ingredients: {sum(per_fndds_n.values()):,}")
log(f"  FNDDS buckets with data: {len(per_fndds_tf):,}")
log(f"  unique ingredient tokens: {len(df_global):,}")

# ---- Pass 2: compute IDF and per-FNDDS top tokens ----
N_total = sum(per_fndds_n.values())
idf = {tok: math.log((N_total + 1) / (df_global[tok] + 1)) + 1 for tok in df_global}

log("Writing ingredient_centroids.tsv...")
with open(OUT, 'w', newline='') as fh:
    fh.write("#fndds_code\tfndds_description\tn_products\ttop_tokens\n")
    for fndds in sorted(per_fndds_tf, key=lambda k: -per_fndds_n[k]):
        n = per_fndds_n[fndds]
        if n < 3: continue
        tf = per_fndds_tf[fndds]
        score = {tok: (tf[tok] / n) * idf.get(tok, 1.0) for tok in tf if tf[tok] >= 2}
        top = sorted(score.items(), key=lambda kv: -kv[1])[:25]
        token_str = '|'.join(f"{tok}:{s:.2f}" for tok, s in top)
        fh.write(f"{fndds}\t{fndds_desc.get(fndds,'')}\t{n}\t{token_str}\n")

log(f"DONE — wrote {OUT}")
