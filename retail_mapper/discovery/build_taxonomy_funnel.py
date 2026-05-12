#!/usr/bin/env python3
"""Funnel taxonomy build:
  STAGE 1 — broad clusters on existing 384-dim embeddings (title+brand+category)
            kMeans k=3000  → ~150 products/cluster, named "product families"
  STAGE 2 — within-cluster TF-IDF on 1-3 grams → dominant sub-leaf names
  STAGE 3 — ingredient signature per sub-leaf (modal cats + has_flags)
            outliers = products whose signature contradicts their sub-leaf

Outputs:
  retail_mapper/funnel_l1_clusters.csv     — broad clusters with top n-grams
  retail_mapper/funnel_l2_sub_leaves.csv   — sub-leaves discovered per cluster
  retail_mapper/funnel_product_path.csv    — per-product full path through funnel
  retail_mapper/funnel_outliers.csv        — flagged mistakes
  retail_mapper/funnel_probe.txt           — regression queries (almond milk, corn dog, etc.)
"""
from __future__ import annotations
import os, sys, csv, sqlite3, json, time, pickle, re
from collections import Counter, defaultdict
import numpy as np

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')
EMB  = os.path.join(ROOT, 'implementation/.embed_cache')

OUT_L1     = os.path.join(RM, 'funnel_l1_clusters.csv')
OUT_L2     = os.path.join(RM, 'funnel_l2_sub_leaves.csv')
OUT_MAP    = os.path.join(RM, 'funnel_product_path.csv')
OUT_OUTLR  = os.path.join(RM, 'funnel_outliers.csv')
OUT_PROBE  = os.path.join(RM, 'funnel_probe.txt')
OUT_AXIS_HIT  = os.path.join(RM, 'funnel_ngrams_axis_hit.csv')      # n-grams we successfully slotted into axes
OUT_AXIS_DISC = os.path.join(RM, 'funnel_ngrams_axis_discovery.csv')  # n-grams that don't match — proposed missing facets

K_LEVEL_1 = 3000   # broad family clusters
NGRAMS_PER_CLUSTER = 12

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

WORD_RE = re.compile(r"[a-z][a-z0-9]+")
NONALPHA = re.compile(r"[^a-z0-9 ]+")
STOPISH = {
    'the','a','an','and','or','of','for','to','in','on','at','by','with','from',
    'organic','natural','flavor','flavors','pack','count','oz','fl','lb','lbs',
    'family','size','large','small','mini','jumbo','single','double','plus','new',
    'made','contains','less','than','original','each',
}

def normalize(s: str) -> str:
    s = (s or '').lower()
    s = NONALPHA.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def title_tokens(s: str) -> list[str]:
    return [t for t in WORD_RE.findall(normalize(s)) if t not in STOPISH and len(t) > 1]

def ngrams(tokens: list[str], n_max: int = 3) -> list[str]:
    """Return all 1-grams + 2-grams + 3-grams from tokens."""
    out = []
    for n in range(1, n_max+1):
        for i in range(len(tokens)-n+1):
            gram = ' '.join(tokens[i:i+n])
            out.append(gram)
    return out

# ----- Axis-matching: classify a phrase against existing axis vocabularies -----
def load_axis_vocabs() -> dict[str, set[str]]:
    """Load axes/*.tsv files; return {axis_name -> {phrase, ...}}.
    Phrase = first column, lowercased & space-separated for compounds where the
    seed used underscore-joined tokens we'll handle by taking the raw text.
    """
    AXES_DIR = os.path.join(RM, 'axes')
    files = {
        'CATEGORY':         'category.tsv',
        'FORM':             'form.tsv',
        'CUT':              'cut.tsv',
        'STORAGE':          'storage.tsv',
        'PREPARATION_STATE':'preparation_state.tsv',
        'SWEETENER':        'sweetener.tsv',
        'FAT':              'fat.tsv',
        'SODIUM':           'sodium.tsv',
        'DIET':             'diet.tsv',
        'AUDIENCE':         'audience.tsv',
        'COLOR':            'color.tsv',
        'CUISINE':          'cuisine.tsv',
        'COMBO_FORMAT':     'combo_format.tsv',
        'DISH_TYPE':        'dish_type.tsv',
        'FLAVOR_UNIVERSAL': 'flavor_universal.tsv',
        'BRAND_NOISE':      'brand_noise.tsv',
        'STOPWORD':         'stopwords.tsv',
    }
    out: dict[str, set[str]] = {}
    for axis, fn in files.items():
        p = os.path.join(AXES_DIR, fn)
        if not os.path.exists(p): continue
        terms: set[str] = set()
        with open(p) as fh:
            for line in fh:
                line = line.rstrip('\n')
                if not line or line.startswith('#'): continue
                first = line.split('\t')[0].strip().lower()
                if first:
                    # support both 'almondmilk' and 'almond milk' style — normalize underscore variants
                    terms.add(first)
                    if '_' in first: terms.add(first.replace('_', ' '))
        out[axis] = terms
    return out

def classify_ngram(ng: str, axis_vocabs: dict[str, set[str]]) -> list[str]:
    """Return list of axes the phrase matches — '<phrase>' counts even if its tokens
    individually live in different axes. Returns axis names hit, or [] if no match.
    Priority: exact phrase match > all-tokens-from-one-axis > none.
    """
    ng = ng.strip().lower()
    if not ng: return []
    hits = []
    # Exact phrase hits first
    for axis, terms in axis_vocabs.items():
        if ng in terms:
            hits.append(axis)
    if hits: return hits
    # All-tokens-from-one-axis (every token in the n-gram is in the axis)
    toks = ng.split()
    for axis, terms in axis_vocabs.items():
        if all(t in terms for t in toks):
            hits.append(axis)
    return hits

def main():
    log("Loading embeddings + tree codes...")
    prod_ids = np.load(os.path.join(EMB, 'prod_ids.npy'), allow_pickle=True)
    prod_emb = np.load(os.path.join(EMB, 'prod_emb.npy'), allow_pickle=True).astype(np.float32)
    tree_emb = np.load(os.path.join(EMB, 'tree_emb.npy'), allow_pickle=True).astype(np.float32)
    with open(os.path.join(EMB, 'tree_codes.pkl'), 'rb') as f:
        tree_codes = pickle.load(f)
    log(f"  prod={prod_emb.shape} tree={tree_emb.shape}")

    # Normalize for cosine
    pn = np.linalg.norm(prod_emb, axis=1, keepdims=True); pn[pn==0]=1; prod_emb /= pn
    tn = np.linalg.norm(tree_emb, axis=1, keepdims=True); tn[tn==0]=1; tree_emb /= tn

    log("Loading master_products metadata...")
    con = sqlite3.connect(DB)
    by_fdc, by_gtin = {}, {}
    for r in con.execute("""
        SELECT gtin_upc, fdc_id, description, brand_owner, brand_name,
               branded_food_category, ingredients_clean, ingredients_parsed
        FROM products
    """):
        rec = {
            'gtin_upc': r[0] or '', 'fdc_id': str(r[1]) if r[1] else '',
            'description': r[2] or '', 'brand_owner': r[3] or '',
            'brand_name': r[4] or '', 'branded_food_category': r[5] or '',
            'ingredients_clean': r[6] or '', 'ingredients_parsed': r[7] or '',
        }
        if rec['fdc_id']: by_fdc[rec['fdc_id']] = rec
        if rec['gtin_upc']: by_gtin[rec['gtin_upc']] = rec
    log(f"  {len(by_fdc):,} by fdc, {len(by_gtin):,} by gtin")

    log("Resolving ids...")
    rows: list[dict | None] = []
    for pid in prod_ids:
        ps = str(pid)
        rows.append(by_fdc.get(ps) or by_gtin.get(ps))
    n_resolved = sum(1 for r in rows if r)
    log(f"  resolved {n_resolved:,}/{len(rows):,}")

    log("Loading v6 ESHA/FNDDS for outlier check...")
    v6_by_gtin, v6_by_fdc = {}, {}
    with open(os.path.join(RM, 'product_esha_fixy.v6.csv'), newline='') as fh:
        for r in csv.DictReader(fh):
            slim = {
                'best_esha_code': r.get('best_esha_code',''),
                'best_esha_description': r.get('best_esha_description',''),
                'v6_fndds_code': r.get('v6_fndds_code',''),
                'v6_fndds_description': r.get('v6_fndds_description',''),
                'wweia_category_description': r.get('wweia_category_description',''),
            }
            g = (r.get('gtin_upc') or '').strip()
            f = (r.get('fdc_id') or '').strip()
            if g: v6_by_gtin[g] = slim
            if f: v6_by_fdc[f] = slim

    # ============ STAGE 1 — broad embedding cluster ============
    log(f"STAGE 1 — MiniBatchKMeans(k={K_LEVEL_1}) on embeddings...")
    from sklearn.cluster import MiniBatchKMeans
    mbk = MiniBatchKMeans(n_clusters=K_LEVEL_1, batch_size=8192, max_iter=80,
                          n_init=3, random_state=42, init='k-means++',
                          reassignment_ratio=0.005, verbose=0)
    mbk.fit(prod_emb)
    labels_l1 = mbk.labels_
    log(f"  k_used={len(set(labels_l1)):,}")

    centers = mbk.cluster_centers_.astype(np.float32)
    cnorm = np.linalg.norm(centers, axis=1, keepdims=True); cnorm[cnorm==0]=1
    centers /= cnorm
    log("  finding nearest tree node per cluster centroid...")
    sim = centers @ tree_emb.T
    near_tree = np.argsort(-sim, axis=1)[:, :3]

    # Members per L1 cluster
    members_l1: dict[int, list[int]] = defaultdict(list)
    for i, c in enumerate(labels_l1):
        members_l1[int(c)].append(i)

    # ============ STAGE 2 — n-grams within each cluster ============
    log("STAGE 2 — n-gram discovery within each L1 cluster...")
    # First compute global DF for IDF
    global_df = Counter()
    N = 0
    for r in rows:
        if not r: continue
        toks = title_tokens(r['description'])
        for g in set(ngrams(toks, n_max=3)):
            global_df[g] += 1
        N += 1
    import math
    idf = {g: math.log((N+1)/(global_df[g]+1)) + 1 for g in global_df}

    log("  loading axis vocabularies for n-gram classification...")
    axis_vocabs = load_axis_vocabs()
    log(f"  axes: {', '.join(f'{a}={len(v)}' for a,v in axis_vocabs.items())}")

    # Aggregate axis-hit and discovery counters across all clusters
    axis_hit_rows: list[tuple] = []        # (cluster_id, ngram, count, axes_matched)
    axis_disc_global = Counter()           # ngram -> total count across clusters
    axis_disc_clusters: dict[str, list] = defaultdict(list)  # ngram -> list of (cluster_id, count, sample_title)

    cluster_meta_l1: dict[int, dict] = {}
    sub_leaves: list[dict] = []  # list of {cluster_id, label, member_idx_set, ingredient_sig...}
    sub_leaf_assignment: dict[int, str] = {}  # row_idx -> sub_leaf_label

    for c, idxs in members_l1.items():
        # collect tokens & n-grams
        tf = Counter()
        for i in idxs:
            r = rows[i]
            if not r: continue
            for g in ngrams(title_tokens(r['description']), n_max=3):
                tf[g] += 1
        # Score by tf*idf within cluster, with min count
        score = {g: tf[g] * idf.get(g, 1.0) for g in tf if tf[g] >= 2}
        top_ngrams = sorted(score.items(), key=lambda kv: -kv[1])[:NGRAMS_PER_CLUSTER]

        # Modal BFC + sample
        bfc_c = Counter()
        sample = []
        for i in idxs[:200]:
            if rows[i] and rows[i]['branded_food_category']:
                bfc_c[rows[i]['branded_food_category']] += 1
        for i in idxs[:5]:
            if rows[i]: sample.append((rows[i]['description'] or '')[:60])
        modal_bfc = bfc_c.most_common(1)[0][0] if bfc_c else ''

        t1 = near_tree[c][0]
        tree_label = tree_codes[t1][1] if t1 < len(tree_codes) else ''
        tree_code  = tree_codes[t1][0] if t1 < len(tree_codes) else ''
        tree_score = float(sim[c, t1])

        # Tag each top n-gram against existing axes; capture both hits and discoveries
        ngram_axis_tags: list[str] = []  # for the cluster summary column
        for g, _sc in top_ngrams:
            hits = classify_ngram(g, axis_vocabs)
            if hits:
                # filter out STOPWORD/BRAND_NOISE-only matches — those are noise
                meaningful = [h for h in hits if h not in {'STOPWORD','BRAND_NOISE'}]
                if meaningful:
                    axis_hit_rows.append((c, g, tf[g], '|'.join(meaningful)))
                    ngram_axis_tags.append(f"{g}→{','.join(meaningful)}")
                else:
                    ngram_axis_tags.append(f"{g}→noise")
            else:
                # unknown n-gram — emit to discovery
                axis_disc_global[g] += tf[g]
                # sample title from this cluster
                sample_title = ''
                for i in idxs[:80]:
                    if rows[i] and ' '+g+' ' in ' '+normalize(rows[i]['description'])+' ':
                        sample_title = (rows[i]['description'] or '')[:60]
                        break
                axis_disc_clusters[g].append((c, tf[g], modal_bfc, sample_title))
                ngram_axis_tags.append(f"{g}→?")

        cluster_meta_l1[c] = {
            'cluster_id': c, 'n_members': len(idxs), 'modal_bfc': modal_bfc,
            'tree_top1_code': tree_code, 'tree_top1_desc': tree_label, 'tree_top1_score': round(tree_score,3),
            'top_ngrams': ' | '.join(f"{g}({tf[g]})" for g, _ in top_ngrams),
            'top_ngrams_tagged': ' | '.join(ngram_axis_tags),
            'sample_products': ' || '.join(sample),
        }

        # Build sub-leaves: each top n-gram of length >=2 with significant frequency
        # becomes a candidate sub-leaf within this cluster.
        sub_leaf_terms = [g for g, _ in top_ngrams if len(g.split()) >= 2 and tf[g] >= max(3, len(idxs)//50)]
        # If no good multi-token n-grams, fall back to top unigram
        if not sub_leaf_terms:
            sub_leaf_terms = [top_ngrams[0][0]] if top_ngrams else []
        # Assign each cluster member to the LONGEST n-gram its title contains;
        # break ties by tf score
        ngram_priority = sorted(sub_leaf_terms,
                                key=lambda g: (-len(g.split()), -score[g]))
        # default sub-leaf = "Other" if nothing matches
        for i in idxs:
            r = rows[i]
            if not r:
                sub_leaf_assignment[i] = f"L1_{c}_unmatched"
                continue
            text = ' ' + normalize(r['description']) + ' '
            chosen = None
            for g in ngram_priority:
                if f' {g} ' in text:
                    chosen = g; break
            sub_leaf_assignment[i] = f"L1_{c}_" + (chosen.replace(' ','_') if chosen else 'other')
    log(f"  sub_leaf assignments computed")

    # Aggregate sub-leaves
    log("  aggregating sub-leaves...")
    sub_members: dict[str, list[int]] = defaultdict(list)
    for i, sl in sub_leaf_assignment.items():
        sub_members[sl].append(i)

    # Build sub-leaf metadata + ingredient signature
    log("STAGE 3 — ingredient signatures per sub-leaf...")
    def has_flag(text_low: str, kws: list[str]) -> bool:
        return any(k in text_low for k in kws)

    sub_leaf_meta: dict[str, dict] = {}
    for sl, idxs in sub_members.items():
        cat_count = Counter()
        flag_count = Counter()
        bfc_count = Counter()
        for i in idxs[:300]:
            r = rows[i]
            if not r: continue
            if r['branded_food_category']:
                bfc_count[r['branded_food_category']] += 1
            ip = r['ingredients_parsed']
            if ip:
                try:
                    items = json.loads(ip)
                    for it in items[:12]:
                        if isinstance(it, dict) and it.get('category'):
                            cat_count[it['category']] += 1
                except: pass
            t = (r.get('ingredients_clean') or r.get('ingredients') or '').lower()
            for f, kws in [
                ('has_batter', ['batter']),
                ('has_breading', ['breading','panko','bread crumb']),
                ('has_cocoa', ['cocoa','chocolate liquor']),
                ('has_hot_dog', ['hot dog','frankfurter','wiener']),
                ('has_chicken', ['chicken']),
                ('has_beef', ['beef']),
                ('has_pork', ['pork']),
                ('has_milk', ['milk']),
                ('has_cream', ['cream']),
                ('has_cheese', ['cheese']),
                ('has_egg', [' egg,',' eggs',' egg ']),
                ('has_corn_meal', ['corn meal','cornmeal','corn flour']),
            ]:
                if has_flag(t, kws):
                    flag_count[f] += 1
        n = max(len(idxs), 1)
        sub_leaf_meta[sl] = {
            'sub_leaf': sl,
            'n_members': len(idxs),
            'parent_cluster': int(sl.split('_')[1]) if sl.startswith('L1_') else -1,
            'ngram_label': sl.split('_', 2)[2].replace('_',' ') if sl.count('_') >= 2 else sl,
            'modal_bfc': bfc_count.most_common(1)[0][0] if bfc_count else '',
            'top_ing_cats': ' | '.join(c for c,_ in cat_count.most_common(5)),
            'flag_freq': ' | '.join(f"{f}={flag_count[f]}/{n} ({100*flag_count[f]//n}%)" for f in sorted(flag_count, key=lambda k: -flag_count[k])[:8]),
            'pct_has_batter': round(100*flag_count.get('has_batter',0)/n, 1),
            'pct_has_hot_dog': round(100*flag_count.get('has_hot_dog',0)/n, 1),
            'pct_has_cocoa': round(100*flag_count.get('has_cocoa',0)/n, 1),
            'pct_has_milk': round(100*flag_count.get('has_milk',0)/n, 1),
        }
    log(f"  {len(sub_leaf_meta):,} sub-leaves")

    # Probe queries
    log("Running probe queries...")
    QUERIES = [
        'ALMOND BREEZE ORIGINAL', 'ALMOND BREEZE CHOCOLATE', 'ALMOND BREEZE PUMPKIN SPICE',
        'ALMOND NOG', 'EGG NOG', 'CORN DOG', 'CHICKEN NUGGETS',
        'ICE CREAM SANDWICH', 'PEANUT BUTTER', 'CHOCOLATE MILK', 'MILK CHOCOLATE',
        'GREEK YOGURT VANILLA', 'FRIED APPLES', 'CHIPOTLE MAYO', 'CHUNKY MONKEY',
        'LIME MAYONNAISE',
    ]
    title_to_idx = {}
    for i, r in enumerate(rows):
        if not r: continue
        t = (r['description'] or '').lower()
        if t and t not in title_to_idx: title_to_idx[t] = i
    def find_idx(q):
        ql = q.lower()
        if ql in title_to_idx: return title_to_idx[ql]
        for t, i in title_to_idx.items():
            if ql in t: return i
        return None

    with open(OUT_PROBE, 'w') as pf:
        pf.write(f"=== Funnel probe  ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
        for q in QUERIES:
            qi = find_idx(q)
            pf.write(f"\n=== Query: {q!r} ===\n")
            if qi is None: pf.write("  (anchor not found)\n"); continue
            r = rows[qi]
            sl = sub_leaf_assignment[qi]
            l1 = labels_l1[qi]
            l1m = cluster_meta_l1[int(l1)]
            slm = sub_leaf_meta[sl]
            pf.write(f"  anchor: {(r['description'] or '')[:60]}\n")
            pf.write(f"     bfc: {r['branded_food_category']}\n")
            pf.write(f"  L1  cluster {l1}: '{l1m['tree_top1_desc']}'  (cosine={l1m['tree_top1_score']}, modal_bfc={l1m['modal_bfc']!r})\n")
            pf.write(f"     L1 top n-grams: {l1m['top_ngrams']}\n")
            pf.write(f"  L2  sub-leaf: {sl} ({slm['n_members']} members)\n")
            pf.write(f"     ingredient signature: {slm['flag_freq']}\n")
    log(f"  probe -> {OUT_PROBE}")

    # ---- Write outputs ----
    log("Writing funnel_l1_clusters.csv...")
    with open(OUT_L1, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['cluster_id','n_members','modal_bfc','tree_top1_code','tree_top1_desc',
                    'tree_top1_score','top_ngrams','top_ngrams_tagged','sample_products'])
        for c, m in sorted(cluster_meta_l1.items(), key=lambda kv: -kv[1]['n_members']):
            w.writerow([m['cluster_id'], m['n_members'], m['modal_bfc'],
                        m['tree_top1_code'], m['tree_top1_desc'], m['tree_top1_score'],
                        m['top_ngrams'], m['top_ngrams_tagged'], m['sample_products']])

    log("Writing funnel_ngrams_axis_hit.csv...")
    with open(OUT_AXIS_HIT, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['cluster_id','ngram','count_in_cluster','axes_matched'])
        for cid, ng, cnt, axes in sorted(axis_hit_rows, key=lambda r: -r[2]):
            w.writerow([cid, ng, cnt, axes])

    log("Writing funnel_ngrams_axis_discovery.csv (unmatched n-grams = missing facets)...")
    with open(OUT_AXIS_DISC, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['ngram','total_count','n_clusters_seen','top_clusters_with_modal_bfc','sample_title'])
        for ng, total in axis_disc_global.most_common(2000):
            entries = axis_disc_clusters[ng]
            entries.sort(key=lambda e: -e[1])
            top_3 = entries[:3]
            cluster_str = ' || '.join(f"c{c}(n={cnt}, bfc={bfc[:25]})" for c, cnt, bfc, _ in top_3)
            sample_title = next((e[3] for e in entries if e[3]), '')
            w.writerow([ng, total, len(entries), cluster_str, sample_title])

    log("Writing funnel_l2_sub_leaves.csv...")
    with open(OUT_L2, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['sub_leaf','parent_cluster','ngram_label','n_members','modal_bfc',
                    'top_ing_cats','pct_has_batter','pct_has_hot_dog','pct_has_cocoa','pct_has_milk',
                    'flag_freq'])
        for m in sorted(sub_leaf_meta.values(), key=lambda x: -x['n_members']):
            w.writerow([m['sub_leaf'], m['parent_cluster'], m['ngram_label'], m['n_members'],
                        m['modal_bfc'], m['top_ing_cats'],
                        m['pct_has_batter'], m['pct_has_hot_dog'], m['pct_has_cocoa'], m['pct_has_milk'],
                        m['flag_freq']])

    log("Writing funnel_product_path.csv + outliers...")
    n_outlier = 0
    map_cols = ['gtin_upc','fdc_id','product_description','branded_food_category',
                'best_esha_code','best_esha_description','v6_fndds_code','v6_fndds_description',
                'l1_cluster','l1_tree_label','l1_modal_bfc',
                'sub_leaf','sub_leaf_label','sub_leaf_modal_bfc',
                'pct_has_hot_dog','pct_has_batter','pct_has_cocoa']
    out_cols = map_cols + ['outlier_reason']
    with open(OUT_MAP, 'w', newline='') as fh, open(OUT_OUTLR, 'w', newline='') as ofh:
        w = csv.writer(fh); w.writerow(map_cols)
        ow = csv.writer(ofh); ow.writerow(out_cols)
        for i, r in enumerate(rows):
            if not r: continue
            sl = sub_leaf_assignment[i]
            l1 = int(labels_l1[i])
            l1m = cluster_meta_l1[l1]
            slm = sub_leaf_meta[sl]
            v6 = v6_by_gtin.get(r['gtin_upc']) or v6_by_fdc.get(r['fdc_id']) or {}
            row = [r['gtin_upc'], r['fdc_id'], r['description'], r['branded_food_category'],
                   v6.get('best_esha_code',''), v6.get('best_esha_description',''),
                   v6.get('v6_fndds_code',''), v6.get('v6_fndds_description',''),
                   l1, l1m['tree_top1_desc'], l1m['modal_bfc'],
                   sl, slm['ngram_label'], slm['modal_bfc'],
                   slm['pct_has_hot_dog'], slm['pct_has_batter'], slm['pct_has_cocoa']]
            w.writerow(row)
            # Outlier rules
            reasons = []
            text_ing = (r.get('ingredients_clean') or r.get('ingredients') or '').lower()
            # Sub-leaf says "corn dog" but this product has no batter or no hot dog
            slabel = slm['ngram_label'].lower()
            if 'corn dog' in slabel:
                if not any(k in text_ing for k in ['batter','breading']):
                    reasons.append('corn_dog_no_batter')
                if not any(k in text_ing for k in ['hot dog','frankfurter','wiener']):
                    reasons.append('corn_dog_no_hot_dog')
            if 'hot dog' in slabel and 'corn' not in slabel:
                if any(k in text_ing for k in ['batter','breading']):
                    reasons.append('hot_dog_with_batter (likely corn dog)')
            if 'almond milk' in slabel or 'almond beverage' in slabel:
                if 'almond' not in text_ing:
                    reasons.append('almond_milk_no_almond')
            if 'chocolate milk' in slabel:
                if not any(k in text_ing for k in ['cocoa','chocolate']):
                    reasons.append('chocolate_milk_no_cocoa')
            # BFC mismatch with cluster modal
            row_bfc = (r['branded_food_category'] or '').lower()
            l1_bfc = (l1m['modal_bfc'] or '').lower()
            if row_bfc and l1_bfc:
                row_h = re.split(r'[,&]', row_bfc)[0].strip()
                l1_h = re.split(r'[,&]', l1_bfc)[0].strip()
                if row_h and l1_h and row_h != l1_h and not (row_h in l1_h or l1_h in row_h):
                    reasons.append(f'bfc:{row_h}!={l1_h}')
            if reasons:
                n_outlier += 1
                ow.writerow(row + ['; '.join(reasons)])

    log(f"DONE — outliers flagged: {n_outlier:,}")
    print(f"\nFiles:\n  {OUT_L1}\n  {OUT_L2}\n  {OUT_MAP}\n  {OUT_OUTLR}\n  {OUT_PROBE}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
