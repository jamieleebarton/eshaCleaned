#!/usr/bin/env python3
"""Build retail taxonomy using existing 384-dim sentence-transformer embeddings.

Inputs:
  implementation/.embed_cache/prod_ids.npy   — 462,646 product ids (fdc_id-like)
  implementation/.embed_cache/prod_emb.npy   — (462646, 384) product embeddings
  implementation/.embed_cache/tree_codes.pkl — (esha_code, description) for 39,691 tree nodes
  implementation/.embed_cache/tree_emb.npy   — (39691, 384) tree-node embeddings
  data/master_products.db                    — full product metadata
  retail_mapper/product_esha_fixy.v6.csv     — v6 ESHA/FNDDS labels

Pipeline:
  1. Load product embeddings + map ids → master_products rows
  2. MiniBatchKMeans on the 462K × 384 matrix (k=20,000)
  3. For each cluster:
     - Compute cluster centroid in embedding space
     - Find nearest ESHA tree nodes to the centroid (top-3) — use their descriptions for the leaf label
     - Combine with modal BFC + most common ingredient categories for the full leaf path
  4. Per-product disagreement check:
     - Does cluster's modal_bfc match this product's BFC?
     - Does cluster's nearest-tree-node ESHA agree with v6_best_esha_code?
     - Flag disagreements with reason

Outputs:
  retail_mapper/retail_taxonomy_embed.csv
  retail_mapper/product_to_leaf_embed.csv
  retail_mapper/taxonomy_disagreements_embed.csv
  retail_mapper/probe_embed.txt    (regression test: nearest neighbors for known queries)
"""
from __future__ import annotations
import os, sys, csv, sqlite3, json, time, pickle, re
from collections import Counter, defaultdict
import numpy as np

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')
EMB  = os.path.join(ROOT, 'implementation/.embed_cache')

OUT_TAX = os.path.join(RM, 'retail_taxonomy_embed.csv')
OUT_MAP = os.path.join(RM, 'product_to_leaf_embed.csv')
OUT_DIS = os.path.join(RM, 'taxonomy_disagreements_embed.csv')
OUT_PROBE = os.path.join(RM, 'probe_embed.txt')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

def main():
    log("Loading embeddings...")
    prod_ids = np.load(os.path.join(EMB, 'prod_ids.npy'), allow_pickle=True)
    prod_emb = np.load(os.path.join(EMB, 'prod_emb.npy'), allow_pickle=True)
    tree_emb = np.load(os.path.join(EMB, 'tree_emb.npy'), allow_pickle=True)
    with open(os.path.join(EMB, 'tree_codes.pkl'), 'rb') as f:
        tree_codes = pickle.load(f)
    log(f"  prod: {prod_emb.shape}  tree: {tree_emb.shape}")
    log(f"  tree_codes[:2]: {tree_codes[:2]}")

    # Normalize embeddings (cosine = dot when L2-normalized)
    log("Normalizing embeddings...")
    prod_emb = prod_emb.astype(np.float32)
    tree_emb = tree_emb.astype(np.float32)
    pn = np.linalg.norm(prod_emb, axis=1, keepdims=True); pn[pn==0] = 1
    prod_emb = prod_emb / pn
    tn = np.linalg.norm(tree_emb, axis=1, keepdims=True); tn[tn==0] = 1
    tree_emb = tree_emb / tn

    # Map prod_ids -> master_products row
    log("Loading master_products metadata...")
    con = sqlite3.connect(DB)
    by_fdc = {}
    by_gtin = {}
    for row in con.execute("""
        SELECT gtin_upc, fdc_id, description, brand_owner, brand_name,
               branded_food_category, ingredients_clean, ingredients_parsed
        FROM products
    """):
        rec = {
            'gtin_upc': row[0] or '', 'fdc_id': str(row[1]) if row[1] else '',
            'description': row[2] or '', 'brand_owner': row[3] or '',
            'brand_name': row[4] or '', 'branded_food_category': row[5] or '',
            'ingredients_clean': row[6] or '', 'ingredients_parsed': row[7] or '',
        }
        if rec['fdc_id']:  by_fdc[rec['fdc_id']] = rec
        if rec['gtin_upc']: by_gtin[rec['gtin_upc']] = rec
    log(f"  by_fdc: {len(by_fdc):,}  by_gtin: {len(by_gtin):,}")

    # Resolve each prod_id to a metadata row
    log("Resolving prod_ids -> products...")
    rows: list[dict | None] = []
    n_resolved = 0
    for pid in prod_ids:
        ps = str(pid)
        rec = by_fdc.get(ps) or by_gtin.get(ps)
        if rec:
            rows.append(rec); n_resolved += 1
        else:
            rows.append(None)
    log(f"  resolved {n_resolved:,} of {len(rows):,}")

    # Load v6 for ESHA/FNDDS comparison
    log("Loading v6 ESHA/FNDDS...")
    v6_by_gtin = {}
    v6_by_fdc = {}
    v6_path = os.path.join(RM, 'product_esha_fixy.v6.csv')
    with open(v6_path, newline='') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
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
    log(f"  v6 loaded")

    # Cluster
    log("Importing sklearn / clustering...")
    from sklearn.cluster import MiniBatchKMeans
    K = 20000
    log(f"MiniBatchKMeans(n_clusters={K})...")
    mbk = MiniBatchKMeans(n_clusters=K, batch_size=8192, max_iter=80,
                          n_init=3, random_state=42, init='k-means++',
                          reassignment_ratio=0.005, verbose=0)
    mbk.fit(prod_emb)
    labels = mbk.labels_
    log(f"  clustered. unique used: {len(set(labels)):,}")

    # Cluster centers (unit-norm them)
    centers = mbk.cluster_centers_.astype(np.float32)
    cn = np.linalg.norm(centers, axis=1, keepdims=True); cn[cn==0]=1
    centers /= cn

    # Find top-3 nearest tree nodes to each cluster centroid (batched)
    log("Matching cluster centroids to ESHA tree nodes...")
    # similarity = centers @ tree_emb.T -> (K, 39691)
    sim = centers @ tree_emb.T
    top3 = np.argsort(-sim, axis=1)[:, :3]

    # Aggregate cluster members
    log("Aggregating cluster members...")
    members: dict[int, list[int]] = defaultdict(list)
    for i, c in enumerate(labels):
        members[int(c)].append(i)

    # Build cluster meta
    log("Auto-labeling clusters...")
    NOISE = {'and','of','the','a','with','from','for','to','in','at','on','by',
             'organic','natural','flavor','flavors','original','classic','new','100',
             'family','size','large','small','mini','jumbo','pack','count','oz','fl','lb','lbs'}
    WORD_RE = re.compile(r'[a-z][a-z0-9]+')
    cluster_meta: dict[int, dict] = {}
    for c, idxs in members.items():
        # Modal BFC
        bfc_c = Counter()
        title_terms = Counter()
        ing_cats = Counter()
        sample_titles = []
        for i in idxs[:300]:
            r = rows[i]
            if not r: continue
            if r['branded_food_category']:
                bfc_c[r['branded_food_category']] += 1
            for tok in WORD_RE.findall((r['description'] or '').lower()):
                if tok not in NOISE and len(tok) > 2:
                    title_terms[tok] += 1
            ip = r['ingredients_parsed']
            if ip:
                try:
                    items = json.loads(ip)
                    for it in items[:10]:
                        if isinstance(it, dict) and it.get('category'):
                            ing_cats[it['category']] += 1
                except: pass
        for i in idxs[:5]:
            if rows[i]: sample_titles.append((rows[i]['description'] or '')[:60])
        modal_bfc = bfc_c.most_common(1)[0][0] if bfc_c else ''
        # Tree-derived label: take top-1 nearest tree node's description
        t_top1 = top3[c][0]
        tree_label_1 = tree_codes[t_top1][1] if t_top1 < len(tree_codes) else ''
        tree_label_1_score = float(sim[c, t_top1])
        tree_top3_str = ' || '.join(
            f"{tree_codes[j][0]}:{tree_codes[j][1][:35]} ({sim[c,j]:.2f})"
            for j in top3[c] if j < len(tree_codes)
        )
        # Leaf label: combine BFC + top tree label
        leaf_label = tree_label_1 or modal_bfc or '(unnamed)'
        # Top distinguishing terms
        top_terms = [t for t,_ in title_terms.most_common(8)]
        cluster_meta[c] = {
            'cluster_id': c,
            'leaf_label': leaf_label,
            'n_members': len(idxs),
            'modal_bfc': modal_bfc,
            'tree_top1_code': tree_codes[t_top1][0] if t_top1 < len(tree_codes) else '',
            'tree_top1_desc': tree_label_1,
            'tree_top1_score': round(tree_label_1_score, 3),
            'tree_top3': tree_top3_str,
            'top_terms': ' | '.join(top_terms),
            'top_ing_cats': ' | '.join(c for c,_ in ing_cats.most_common(5)),
            'sample_products': ' || '.join(sample_titles),
        }

    # Probe — for these queries find nearest products by embedding
    QUERIES = [
        'ALMOND BREEZE ORIGINAL', 'ALMOND BREEZE CHOCOLATE', 'ALMOND BREEZE PUMPKIN SPICE',
        'ALMOND NOG', 'EGG NOG', 'CORN DOG', 'HOT DOG', 'CHICKEN NUGGETS',
        'ICE CREAM SANDWICH', 'PEANUT BUTTER', 'CHOCOLATE MILK', 'MILK CHOCOLATE',
        'GREEK YOGURT VANILLA', 'APPLE NOODLE KUGEL', 'FRIED APPLES', 'CHIPOTLE MAYO',
        'CHUNKY MONKEY ICE CREAM',
    ]
    log("Running embedding probe queries...")
    # Build lower-title -> first-resolved-row index map for anchor lookup
    title_to_idx: dict[str, int] = {}
    for i, r in enumerate(rows):
        if not r: continue
        t = (r['description'] or '').lower()
        if t and t not in title_to_idx:
            title_to_idx[t] = i
    def find_idx(q: str) -> int | None:
        ql = q.lower()
        if ql in title_to_idx: return title_to_idx[ql]
        # phrase substring
        for t, i in title_to_idx.items():
            if ql in t: return i
        return None

    with open(OUT_PROBE, 'w') as pfh:
        pfh.write(f"=== Embedding probes  ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===\n\n")
        for q in QUERIES:
            qi = find_idx(q)
            pfh.write(f"\n=== Query: {q!r} ===\n")
            if qi is None:
                pfh.write("  (anchor not found)\n"); continue
            r = rows[qi]
            pfh.write(f"  anchor: {(r['description'] or '')[:60]}\n")
            pfh.write(f"     bfc: {r['branded_food_category']}\n")
            ing = (r.get('ingredients_clean') or '')[:120]
            pfh.write(f"     ing: {ing}\n")
            # cosine vs all
            qv = prod_emb[qi]
            sims = prod_emb @ qv
            top = np.argsort(-sims)[:10]
            for j in top:
                if int(j) == qi: continue
                rr = rows[int(j)]
                if not rr: continue
                pfh.write(f"  {sims[j]:.3f}  {(rr['description'] or '')[:55]:<55s}  bfc={rr['branded_food_category'][:25]}\n")
            # cluster of this anchor
            ac = int(labels[qi])
            m = cluster_meta.get(ac, {})
            pfh.write(f"  cluster {ac}: leaf={m.get('leaf_label','')!r}  modal_bfc={m.get('modal_bfc','')!r}  n={m.get('n_members')}\n")
    log(f"  wrote {OUT_PROBE}")

    # Write taxonomy summary
    log("Writing retail_taxonomy_embed.csv...")
    with open(OUT_TAX, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['cluster_id','leaf_label','n_members','modal_bfc',
                    'tree_top1_code','tree_top1_desc','tree_top1_score',
                    'tree_top3','top_terms','top_ing_cats','sample_products'])
        for m in sorted(cluster_meta.values(), key=lambda x: -x['n_members']):
            w.writerow([m['cluster_id'], m['leaf_label'], m['n_members'], m['modal_bfc'],
                        m['tree_top1_code'], m['tree_top1_desc'], m['tree_top1_score'],
                        m['tree_top3'], m['top_terms'], m['top_ing_cats'], m['sample_products']])

    # Write per-product map + disagreements
    log("Writing product_to_leaf_embed.csv + disagreements...")
    cols = ['gtin_upc','fdc_id','product_description','branded_food_category',
            'best_esha_code','best_esha_description','v6_fndds_code','v6_fndds_description',
            'wweia_category_description','cluster_id','cluster_leaf','cluster_modal_bfc',
            'cluster_tree_top1_code','cluster_tree_top1_desc','cluster_tree_top1_score']
    n_dis = 0
    with open(OUT_MAP, 'w', newline='') as fh, open(OUT_DIS, 'w', newline='') as dfh:
        w = csv.writer(fh); w.writerow(cols)
        d = csv.writer(dfh); d.writerow(cols + ['disagreement'])
        for i in range(len(rows)):
            r = rows[i]
            if not r: continue
            c = int(labels[i])
            m = cluster_meta[c]
            v6 = v6_by_gtin.get(r['gtin_upc']) or v6_by_fdc.get(r['fdc_id']) or {}
            row = [r['gtin_upc'], r['fdc_id'], r['description'], r['branded_food_category'],
                   v6.get('best_esha_code',''), v6.get('best_esha_description',''),
                   v6.get('v6_fndds_code',''), v6.get('v6_fndds_description',''),
                   v6.get('wweia_category_description',''),
                   c, m['leaf_label'], m['modal_bfc'],
                   m['tree_top1_code'], m['tree_top1_desc'], m['tree_top1_score']]
            w.writerow(row)
            # Disagreement: ESHA code says X but cluster's nearest tree node says Y
            esha_code = (v6.get('best_esha_code') or '').strip()
            tree_code = m['tree_top1_code']
            esha_desc = (v6.get('best_esha_description') or '').lower()
            tree_desc = (m['tree_top1_desc'] or '').lower()
            row_bfc = (r['branded_food_category'] or '').lower()
            mod_bfc = (m['modal_bfc'] or '').lower()
            reasons = []
            if esha_code and tree_code and esha_code != tree_code:
                # Heuristic: if descriptions don't share a common token, it's a real disagreement
                if esha_desc and tree_desc:
                    et = set(re.findall(r'[a-z]+', esha_desc))
                    tt = set(re.findall(r'[a-z]+', tree_desc))
                    et -= NOISE; tt -= NOISE
                    if et and tt and not (et & tt):
                        reasons.append(f'esha_vs_tree:{esha_code}!={tree_code}')
            if row_bfc and mod_bfc and row_bfc != mod_bfc:
                row_h = row_bfc.split(',')[0].split('&')[0].strip()
                mod_h = mod_bfc.split(',')[0].split('&')[0].strip()
                if row_h and mod_h and row_h != mod_h:
                    reasons.append(f'bfc:{row_h}!={mod_h}')
            if reasons:
                n_dis += 1
                d.writerow(row + ['; '.join(reasons)])
    log(f"DONE — disagreements flagged: {n_dis:,}")
    print(f"\nFiles:\n  {OUT_TAX}\n  {OUT_MAP}\n  {OUT_DIS}\n  {OUT_PROBE}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
