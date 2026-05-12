#!/usr/bin/env python3
"""Wire ingredient signatures into the parsed output.

Reads:
  retail_mapper/parsed_titles.csv             (462,646 rows from title parser)
  retail_mapper/axes/ingredient_centroids.tsv (5,191 FNDDS centroids, TF-IDF)
  fixy_done/*.csv                              (1.03M fdc_id -> ingredients)

Writes:
  retail_mapper/parsed_titles_enriched.csv     (parsed rows + ingredient-match columns)

New columns appended:
  ing_signature_n        — count of ingredient tokens we extracted
  ing_top1_fndds         — best matching FNDDS code by cosine similarity
  ing_top1_desc          — that FNDDS description
  ing_top1_score         — cosine score
  ing_top3               — top-3 fndds:score|fndds:score|fndds:score
  ing_agrees_v6          — does ing_top1_fndds match v6_fndds_code? (Y/N/?)

Heuristics:
  - product token weight = stemmed-token-count × global-idf
  - matching uses cosine on shared tokens
  - centroid filtering: only score against FNDDS with n>=10 products
"""
from __future__ import annotations
import os, csv, sys, re, math, glob, time
from collections import Counter, defaultdict

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
FIXY = os.path.join(ROOT, 'fixy_done')

PARSED  = os.path.join(RM, 'parsed_titles.csv')
V6_MAIN = os.path.join(RM, 'product_esha_fixy.v6.csv')   # for v6_fndds_code lookup by fdc_id
CENTROIDS = os.path.join(RM, 'axes/ingredient_centroids.tsv')
OUT = os.path.join(RM, 'parsed_titles_enriched.csv')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

# ---- Tokenization (must match the centroid builder) ----
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
STEMS = {
    'frankfurter': 'frank', 'frankfurters': 'frank', 'franks': 'frank',
    'wieners': 'wiener', 'sausages': 'sausage', 'patties': 'patty',
    'almonds': 'almond', 'cashews': 'cashew', 'walnuts': 'walnut',
    'pecans': 'pecan', 'hazelnuts': 'hazelnut', 'pistachios': 'pistachio',
    'crackers': 'cracker', 'cookies': 'cookie', 'biscuits': 'biscuit',
    'tomatoes': 'tomato', 'beans': 'bean', 'peas': 'pea', 'oats': 'oat',
    'olives': 'olive', 'eggs': 'egg', 'spices': 'spice',
    'ingredients': 'ingredient', 'oils': 'oil', 'syrups': 'syrup',
    'flours': 'flour', 'meats': 'meat', 'seeds': 'seed', 'breads': 'bread',
    'cheeses': 'cheese', 'fruits': 'fruit', 'vegetables': 'vegetable',
}
def stem(t): return STEMS.get(t, t)
def signature(ing: str) -> Counter:
    s = (ing or '').lower()
    s = re.sub(r'\([^)]*\)', ' ', s)
    raw = (stem(t) for t in TOK.findall(s) if len(t) > 3 and t not in NOISE)
    return Counter(raw)

# ---- Load centroids ----
log("Loading centroids...")
centroids = {}
with open(CENTROIDS) as fh:
    for line in fh:
        if line.startswith('#'): continue
        parts = line.rstrip('\n').split('\t')
        if len(parts) < 4: continue
        fc, desc, n_str, toks = parts[:4]
        try:
            n = int(n_str)
        except ValueError:
            continue
        if n < 10: continue
        d = {}
        for t in toks.split('|'):
            if ':' in t:
                k, v = t.rsplit(':', 1)
                try:
                    # stem the centroid tokens too, accumulating if collision
                    sk = stem(k)
                    d[sk] = d.get(sk, 0) + float(v)
                except ValueError:
                    pass
        if d:
            centroids[fc] = (desc, n, d)
log(f"  centroids loaded: {len(centroids):,}")

cent_norm = {fc: math.sqrt(sum(v*v for v in d.values())) for fc, (_, _, d) in centroids.items()}

# ---- Load fixy_done: fdc_id -> ingredients (string), plus build global IDF ----
log("Loading ingredients from fixy_done & computing IDF...")
fdc_ing: dict[str, str] = {}
df = Counter()
N = 0
files = glob.glob(os.path.join(FIXY, '*.csv'))
files = [f for f in files if os.path.basename(f)[0].isdigit()]
for f in files:
    try:
        with open(f, newline='') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                fid = (row.get('fdc_id') or '').strip()
                ing = row.get('ingredients') or ''
                if fid and ing and fid not in fdc_ing:
                    fdc_ing[fid] = ing
                sig = signature(ing)
                if sig:
                    N += 1
                    for t in sig:
                        df[t] += 1
    except Exception as e:
        log(f"  ! {f}: {e}")
log(f"  fdc_id->ingredient: {len(fdc_ing):,}  global N={N:,}  unique tokens={len(df):,}")
idf = {t: math.log((N + 1) / (df[t] + 1)) + 1 for t in df}
default_idf = math.log(N + 1) + 1

def best_match(ing: str, top_k: int = 3):
    sig = signature(ing)
    if not sig:
        return 0, []
    weighted = {t: c * idf.get(t, default_idf) for t, c in sig.items()}
    sig_norm = math.sqrt(sum(v*v for v in weighted.values()))
    if sig_norm == 0:
        return len(sig), []
    scores = []
    for fc, (desc, n, cd) in centroids.items():
        cn = cent_norm[fc]
        if cn == 0: continue
        dot = 0.0
        for t, cv in cd.items():
            wv = weighted.get(t, 0)
            if wv:
                dot += wv * cv
        if dot == 0: continue
        cos = dot / (sig_norm * cn)
        scores.append((cos, fc, desc, n))
    scores.sort(reverse=True)
    return len(sig), scores[:top_k]

# ---- Load v6_fndds_code by fdc_id (for agreement check) ----
log("Loading v6 FNDDS codes by fdc_id...")
v6_by_fdc: dict[str, str] = {}
with open(V6_MAIN, newline='') as fh:
    reader = csv.DictReader(fh)
    for r in reader:
        fid = (r.get('fdc_id') or '').strip()
        if fid:
            v6_by_fdc[fid] = (r.get('v6_fndds_code') or '').strip()
log(f"  v6 codes: {len(v6_by_fdc):,}")

# ---- Walk parsed_titles, score, write enriched ----
log("Enriching parsed_titles.csv...")
new_cols = ['ing_signature_n','ing_top1_fndds','ing_top1_desc','ing_top1_score','ing_top3','ing_agrees_v6']

n_rows = 0
n_with_ing = 0
n_match = 0
n_agree = 0
n_disagree = 0
top1_freq = Counter()

with open(PARSED, newline='') as src, open(OUT, 'w', newline='') as dst:
    reader = csv.DictReader(src)
    in_fields = reader.fieldnames[:]
    out_fields = in_fields + new_cols
    writer = csv.DictWriter(dst, fieldnames=out_fields)
    writer.writeheader()
    for r in reader:
        n_rows += 1
        fid = (r.get('fdc_id') or '').strip()
        ing_str = fdc_ing.get(fid, '')
        ing_sig_n = 0
        top1_fc = top1_desc = ''
        top1_score = 0.0
        top3_str = ''
        agrees = '?'
        if ing_str:
            n_with_ing += 1
            ing_sig_n, scores = best_match(ing_str, top_k=3)
            if scores:
                n_match += 1
                top1_fc = scores[0][1]
                top1_desc = scores[0][2]
                top1_score = round(scores[0][0], 3)
                top3_str = '|'.join(f"{s[1]}:{round(s[0],3)}" for s in scores)
                top1_freq[top1_fc] += 1
                v6_fndds = v6_by_fdc.get(fid, '')
                if v6_fndds:
                    if v6_fndds == top1_fc:
                        agrees = 'Y'; n_agree += 1
                    else:
                        agrees = 'N'; n_disagree += 1
                else:
                    agrees = '?'
        r['ing_signature_n'] = ing_sig_n
        r['ing_top1_fndds']  = top1_fc
        r['ing_top1_desc']   = top1_desc
        r['ing_top1_score']  = top1_score if top1_fc else ''
        r['ing_top3']        = top3_str
        r['ing_agrees_v6']   = agrees
        writer.writerow({k: r.get(k, '') for k in out_fields})
        if n_rows % 100000 == 0:
            log(f"  ...{n_rows:,}")

log(f"DONE")
log(f"  Rows: {n_rows:,}")
log(f"  With ingredients (fdc_id matched): {n_with_ing:,} ({100*n_with_ing/n_rows:.1f}%)")
log(f"  Got an ingredient match: {n_match:,}")
log(f"  Agrees with v6_fndds: {n_agree:,}")
log(f"  Disagrees with v6_fndds: {n_disagree:,}")
log(f"\nTop FNDDS codes from ingredient matching:")
for fc, n in top1_freq.most_common(20):
    desc = centroids[fc][0] if fc in centroids else ''
    log(f"  {n:>6,}  {fc}  {desc[:40]}")

print(f"\nOutput: {OUT}")
