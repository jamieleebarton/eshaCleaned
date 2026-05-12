#!/usr/bin/env python3
"""Build OUR retail taxonomy by clustering all 462K products on a fused
fingerprint (title + ingredients + branded_food_category + brand + parsed
ingredient categories + has-flags), with bigrams up-weighted.

Outputs:
  retail_mapper/retail_taxonomy_v1.csv     — one row per cluster:
      cluster_id, leaf_label, n_members, sample_products,
      modal_bfc, modal_esha_desc, modal_fndds_code,
      top_terms, top_ingredient_cats
  retail_mapper/product_to_leaf.csv        — per-product assignment:
      gtin_upc, fdc_id, product_description, branded_food_category,
      best_esha_code, best_esha_description, v6_fndds_code, v6_fndds_description,
      cluster_id, leaf_label
  retail_mapper/taxonomy_disagreements.csv — mistakes: rows where the cluster
      label disagrees strongly with at least one of the existing signals.
"""
from __future__ import annotations
import os, sys, csv, sqlite3, json, re, time, math
from collections import Counter, defaultdict

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')
V6   = os.path.join(RM, 'product_esha_fixy.v6.csv')

OUT_TAX = os.path.join(RM, 'retail_taxonomy_v1.csv')
OUT_MAP = os.path.join(RM, 'product_to_leaf.csv')
OUT_DIS = os.path.join(RM, 'taxonomy_disagreements.csv')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

# ---- Tokenization & feature extraction ----
WORD_RE  = re.compile(r"[a-z][a-z0-9]+")
NONALPHA = re.compile(r"[^a-z0-9 ]+")
STEMS = {
    'almonds':'almond','cashews':'cashew','walnuts':'walnut','pecans':'pecan',
    'hazelnuts':'hazelnut','pistachios':'pistachio','macadamias':'macadamia',
    'frankfurter':'frank','frankfurters':'frank','franks':'frank',
    'wieners':'wiener','sausages':'sausage','patties':'patty',
    'cookies':'cookie','crackers':'cracker','tomatoes':'tomato',
    'beans':'bean','peas':'pea','oats':'oat','olives':'olive',
    'eggs':'egg','spices':'spice','breads':'bread','cheeses':'cheese',
    'flours':'flour','oils':'oil','seeds':'seed','syrups':'syrup',
    'fruits':'fruit','vegetables':'vegetable',
}
def stem(t): return STEMS.get(t, t)

# Tokens we DO NOT want to dominate the fingerprint — common filler
NOISE_TITLE = {'and','of','the','a','with','from','for','to','in','at','on','by',
               'organic','natural','flavor','flavors','original','classic','new',
               'family','size','large','small','mini','jumbo','pack','count','oz','fl','lb','lbs'}

def tokens_with_bigrams(s: str) -> tuple[list[str], list[str]]:
    """Returns (unigrams, bigrams) — bigrams will be up-weighted."""
    s = (s or '').lower()
    s = NONALPHA.sub(' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    raw = [stem(t) for t in WORD_RE.findall(s) if len(t) >= 2 and t not in NOISE_TITLE]
    bigrams = [raw[i] + '_' + raw[i+1] for i in range(len(raw)-1)]
    return raw, bigrams

def parsed_signals(ip_json: str) -> tuple[list[str], list[str]]:
    cats: list[str] = []
    names: list[str] = []
    if not ip_json: return cats, names
    try:
        items = json.loads(ip_json)
    except Exception:
        return cats, names
    for it in items[:25]:
        if not isinstance(it, dict): continue
        c = it.get('category') or ''
        nm = it.get('name') or ''
        if c: cats.append('cat_' + c)
        if nm:
            ng_uni, _ = tokens_with_bigrams(nm)
            names.extend('ing_' + t for t in ng_uni[:5])
    return cats, names

def has_flags(ing: str) -> list[str]:
    text = (ing or '').lower()
    flags = []
    for flag, kws in [
        ('has_batter', ['batter']),
        ('has_breading', ['breading','bread crumb','panko']),
        ('has_cocoa', ['cocoa','chocolate liquor']),
        ('has_hot_dog', ['hot dog','frankfurter','wiener']),
        ('has_chicken', ['chicken']),
        ('has_pork', ['pork']),
        ('has_beef', ['beef']),
        ('has_tomato', ['tomato']),
        ('has_egg', ['egg ','eggs',' egg,']),
        ('has_milk', ['milk']),
        ('has_cream', ['cream']),
        ('has_cheese', ['cheese']),
        ('has_wheat', ['wheat']),
        ('has_corn', ['corn meal','corn flour','cornmeal']),
        ('has_sugar', ['sugar']),
        ('has_sweetener_artificial', ['aspartame','sucralose','stevia','acesulfame']),
    ]:
        if any(k in text for k in kws):
            flags.append(flag)
    return flags

def fingerprint(row: dict) -> Counter:
    """Returns Counter[feature -> weight] — bigrams get 2x weight, has-flags 3x."""
    feats = Counter()
    title = row.get('description') or ''
    bfc   = row.get('branded_food_category') or ''
    brand = (row.get('brand_owner') or '') + ' ' + (row.get('brand_name') or '')
    ing   = row.get('ingredients_clean') or row.get('ingredients') or ''
    ipar  = row.get('ingredients_parsed') or ''

    # Title: unigrams 1x, bigrams 2x
    t_uni, t_bi = tokens_with_bigrams(title)
    for t in t_uni: feats['t_' + t] += 1
    for t in t_bi:  feats['t_' + t] += 2

    # BFC: unigrams 1.5x (BFC is a strong prior)
    b_uni, b_bi = tokens_with_bigrams(bfc)
    for t in b_uni: feats['b_' + t] += 1.5
    for t in b_bi:  feats['b_' + t] += 2

    # Brand: unigrams 0.5x (avoid letting brand dominate)
    br_uni, _ = tokens_with_bigrams(brand)
    for t in br_uni: feats['br_' + t] += 0.5

    # Ingredient text: unigrams 0.5x, bigrams 1x
    i_uni, i_bi = tokens_with_bigrams(ing)
    for t in i_uni: feats['i_' + t] += 0.5
    for t in i_bi:  feats['i_' + t] += 1

    # Parsed ingredient categories (3x — strong taxonomic signal)
    cats, names = parsed_signals(ipar)
    for c in cats: feats[c] += 3
    for n in names: feats[n] += 0.5

    # Has-flags (3x — strong product-type signal)
    for f in has_flags(ing): feats[f] += 3
    return feats

def main():
    log("Loading sklearn...")
    try:
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.feature_extraction.text import TfidfTransformer
        from sklearn.cluster import MiniBatchKMeans
        from sklearn.preprocessing import normalize
    except ImportError:
        log("ERROR: sklearn not available — aborting.")
        return 1

    log("Loading products from master_products.db...")
    con = sqlite3.connect(DB)
    rows: list[dict] = []
    for r in con.execute("""
        SELECT gtin_upc, fdc_id, description, brand_owner, brand_name,
               branded_food_category, ingredients, ingredients_clean,
               ingredients_parsed
        FROM products
    """):
        rows.append({
            'gtin_upc': r[0] or '', 'fdc_id': r[1] or '',
            'description': r[2] or '', 'brand_owner': r[3] or '',
            'brand_name': r[4] or '', 'branded_food_category': r[5] or '',
            'ingredients': r[6] or '', 'ingredients_clean': r[7] or '',
            'ingredients_parsed': r[8] or '',
        })
    log(f"  loaded {len(rows):,} rows")

    log("Building fingerprints...")
    fps: list[dict] = []
    for i, r in enumerate(rows):
        fps.append(dict(fingerprint(r)))
        if (i+1) % 100000 == 0:
            log(f"  ...{i+1:,}")
    log("  done")

    log("Vectorizing (DictVectorizer)...")
    dv = DictVectorizer(sparse=True)
    X = dv.fit_transform(fps)
    log(f"  X: {X.shape}, nnz={X.nnz:,}")

    log("TF-IDF transform...")
    tfidf = TfidfTransformer(sublinear_tf=True)
    X = tfidf.fit_transform(X)
    X = normalize(X, norm='l2', copy=False)
    log(f"  X normalized")

    K = 20000
    log(f"MiniBatchKMeans(n_clusters={K}, batch_size=4096)...")
    mbk = MiniBatchKMeans(n_clusters=K, batch_size=4096, max_iter=80,
                          n_init=3, random_state=42, reassignment_ratio=0.005,
                          init='k-means++', verbose=0)
    mbk.fit(X)
    labels = mbk.labels_
    log(f"  labels: {len(labels):,}; unique used: {len(set(labels)):,}")

    # ---- Auto-label clusters ----
    log("Auto-labeling clusters...")
    feat_names = dv.get_feature_names_out()
    cluster_members = defaultdict(list)  # cluster -> [row_idx]
    for i, c in enumerate(labels):
        cluster_members[int(c)].append(i)

    # Per-cluster stats
    cluster_meta: dict[int, dict] = {}
    for c, idxs in cluster_members.items():
        sample = idxs[:5]
        # Modal BFC
        bfc_c = Counter(rows[i]['branded_food_category'] for i in idxs if rows[i]['branded_food_category'])
        modal_bfc = bfc_c.most_common(1)[0][0] if bfc_c else ''
        # Top distinguishing terms: take centroid of cluster, find top-K features
        # mbk.cluster_centers_[c] is a dense vector of size n_features — use it
        center = mbk.cluster_centers_[c]
        # top features by weight
        top_idx = center.argsort()[-12:][::-1]
        top_terms = [feat_names[i] for i in top_idx if center[i] > 0][:10]
        # Majority ingredient cats
        cats = Counter()
        for i in idxs[:200]:
            ip = rows[i]['ingredients_parsed']
            if ip:
                try:
                    items = json.loads(ip)
                    for it in items:
                        if isinstance(it, dict) and it.get('category'):
                            cats[it['category']] += 1
                except: pass
        top_cats = [c for c,_ in cats.most_common(5)]
        # Construct a leaf label heuristically:
        # Use modal_bfc + most distinctive title/bfc/bigram tokens
        leaf_terms: list[str] = []
        for t in top_terms:
            label = t
            if t.startswith('t_'):    label = t[2:]
            elif t.startswith('b_'):  label = t[2:]
            elif t.startswith('i_'):  label = t[2:]
            elif t.startswith('cat_'): label = '['+t[4:]+']'
            elif t.startswith('has_'): label = '['+t[4:]+']'
            elif t.startswith('br_'):  continue
            else: continue
            label = label.replace('_', ' ')
            if label and label not in leaf_terms:
                leaf_terms.append(label)
            if len(leaf_terms) >= 5:
                break
        leaf_label_short = ' / '.join(leaf_terms[:3]) or '(unnamed)'
        sample_titles = [rows[i]['description'][:50] for i in sample]
        cluster_meta[c] = {
            'cluster_id': c,
            'n_members': len(idxs),
            'leaf_label': leaf_label_short,
            'modal_bfc': modal_bfc,
            'top_terms': ' | '.join(top_terms[:8]),
            'top_ing_cats': ' | '.join(top_cats),
            'sample_products': ' || '.join(sample_titles),
        }
    log(f"  meta computed for {len(cluster_meta):,} clusters")

    # ---- Pull v6_fndds + ESHA from v6 file (so we can compare) ----
    log("Loading v6 ESHA/FNDDS for disagreement check...")
    by_gtin = {}
    by_fdc  = {}
    with open(V6, newline='') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            gtin = (r.get('gtin_upc') or '').strip()
            fdc  = (r.get('fdc_id')   or '').strip()
            slim = {
                'best_esha_code': r.get('best_esha_code',''),
                'best_esha_description': r.get('best_esha_description',''),
                'v6_fndds_code': r.get('v6_fndds_code',''),
                'v6_fndds_description': r.get('v6_fndds_description',''),
                'wweia_category_description': r.get('wweia_category_description',''),
            }
            if gtin: by_gtin[gtin] = slim
            if fdc:  by_fdc[fdc] = slim
    log(f"  v6 by gtin: {len(by_gtin):,} by fdc: {len(by_fdc):,}")

    # ---- Write outputs ----
    log("Writing retail_taxonomy_v1.csv...")
    with open(OUT_TAX, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['cluster_id','leaf_label','n_members','modal_bfc',
                    'top_terms','top_ing_cats','sample_products'])
        for c, m in sorted(cluster_meta.items(), key=lambda kv: -kv[1]['n_members']):
            w.writerow([m['cluster_id'], m['leaf_label'], m['n_members'],
                        m['modal_bfc'], m['top_terms'], m['top_ing_cats'],
                        m['sample_products']])

    log("Writing product_to_leaf.csv...")
    n_dis = 0
    with open(OUT_MAP, 'w', newline='') as fh, open(OUT_DIS, 'w', newline='') as dfh:
        w = csv.writer(fh)
        d = csv.writer(dfh)
        cols = ['gtin_upc','fdc_id','product_description','branded_food_category',
                'best_esha_code','best_esha_description','v6_fndds_code','v6_fndds_description',
                'wweia_category_description','cluster_id','leaf_label','modal_bfc']
        w.writerow(cols)
        d.writerow(cols + ['disagreement'])
        for i, r in enumerate(rows):
            c = int(labels[i])
            m = cluster_meta[c]
            v6_info = by_gtin.get(r['gtin_upc']) or by_fdc.get(r['fdc_id']) or {}
            row = [r['gtin_upc'], r['fdc_id'], r['description'], r['branded_food_category'],
                   v6_info.get('best_esha_code',''), v6_info.get('best_esha_description',''),
                   v6_info.get('v6_fndds_code',''), v6_info.get('v6_fndds_description',''),
                   v6_info.get('wweia_category_description',''),
                   c, m['leaf_label'], m['modal_bfc']]
            w.writerow(row)
            # Disagreement: row's BFC is meaningfully different from cluster's modal BFC
            row_bfc = (r['branded_food_category'] or '').lower()
            mod_bfc = (m['modal_bfc'] or '').lower()
            disagree_reasons = []
            if row_bfc and mod_bfc and row_bfc != mod_bfc:
                # Same supercategory like "Frozen" prefix? skip if shared head word
                row_head = row_bfc.split()[0] if row_bfc.split() else ''
                mod_head = mod_bfc.split()[0] if mod_bfc.split() else ''
                if row_head and mod_head and row_head != mod_head:
                    disagree_reasons.append(f'bfc_head:{row_head}!={mod_head}')
            # Disagreement: ESHA description vs leaf label have no overlap
            esha_desc = (v6_info.get('best_esha_description') or '').lower()
            leaf_low  = (m['leaf_label'] or '').lower()
            if esha_desc and leaf_low:
                esha_toks = set(re.findall(r'[a-z]+', esha_desc))
                leaf_toks = set(re.findall(r'[a-z]+', leaf_low))
                if esha_toks and leaf_toks and not (esha_toks & leaf_toks):
                    disagree_reasons.append('no_token_overlap_esha')
            if disagree_reasons:
                n_dis += 1
                d.writerow(row + ['; '.join(disagree_reasons)])
    log(f"DONE — disagreements flagged: {n_dis:,} ({100*n_dis/len(rows):.1f}%)")
    print(f"\nFiles:\n  {OUT_TAX}\n  {OUT_MAP}\n  {OUT_DIS}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
