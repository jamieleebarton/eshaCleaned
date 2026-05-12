#!/usr/bin/env python3
"""Multi-signal voting taxonomy.

For each of 462,646 products, derive a leaf from EVERY signal we've built,
then vote.  Where signals agree → high confidence consensus.  Where they
disagree → flag for review with every signal visible.

Signals collected per product:
  S1  v6_fndds              v6 marry → FNDDS code+desc
  S2  v6_esha               v6 best_esha
  S3  wweia                 broad WWEIA supercategory (with fndds fill)
  S4  bfc                   branded_food_category (the retailer's bucket)
  S5  funnel_l1_cluster     embedding-cluster id (3000 buckets)
  S6  funnel_l1_tree_label  the cluster's nearest ESHA tree node
  S7  funnel_subleaf        n-gram sub-leaf within cluster
  S8  parser_category       from parsed_titles.csv (axis-based)
  S9  parser_form           from parsed_titles.csv
  S10 parser_flavor         from parsed_titles.csv
  S11 parser_retail_leaf    from parsed_titles.csv (full leaf path)
  S12 embed_top_esha        nearest ESHA tree node to product embedding
  S13 ingredient_top_fndds  best FNDDS centroid match by ingredient cosine
  S14 ingredient_categories ordered list of categories from ingredients_parsed

Then for each product:
  - consensus_supercategory = mode(WWEIA, BFC head, funnel_l1, parser_supercat)
  - consensus_leaf         = the most-voted leaf-level label
  - agreement_score        = count of distinct signals agreeing on the consensus
  - disagreement_flags     = list of signals that DISAGREE with consensus

Outputs:
  retail_mapper/consensus_taxonomy.csv         — one row per product, all signals + consensus
  retail_mapper/consensus_disagreements.csv    — products where ≥3 signals disagree (the audit pile)
  retail_mapper/consensus_taxonomy_summary.txt — top-line stats
"""
from __future__ import annotations
import os, sys, csv, json, sqlite3, time, pickle, re
from collections import Counter, defaultdict
import numpy as np

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')
EMB  = os.path.join(ROOT, 'implementation/.embed_cache')

V6        = os.path.join(RM, 'product_esha_fixy.v6.csv')
PARSED    = os.path.join(RM, 'parsed_titles.csv')
FUNNEL_PATH = os.path.join(RM, 'funnel_product_path.csv')
ING_CENTROIDS = os.path.join(RM, 'axes/ingredient_centroids.tsv')

OUT_MAIN  = os.path.join(RM, 'consensus_taxonomy.csv')
OUT_DIS   = os.path.join(RM, 'consensus_disagreements.csv')
OUT_SUMM  = os.path.join(RM, 'consensus_taxonomy_summary.txt')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

# -------------------- helpers --------------------
WORD_RE = re.compile(r'[a-z][a-z0-9]+')
NOISE = {
    'and','of','the','a','with','to','from','for','for','no','non','organic','natural',
    'flavor','flavors','original','classic','new','family','size','large','small','mini',
    'pack','count','oz','fl','lb','lbs','contains','less','than','enriched','filtered',
}
def tokens(s: str) -> set[str]:
    return set(t for t in WORD_RE.findall((s or '').lower()) if t not in NOISE)

def head_token(s: str) -> str:
    s = (s or '').lower()
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    parts = s.split()
    return parts[0] if parts else ''

def super_from_bfc(bfc: str) -> str:
    """Map BFC string to one of ~12 broad retail families."""
    b = (bfc or '').lower()
    if 'plant based milk' in b or 'milk additive' in b: return 'plant_milk'
    if b == 'milk' or 'cream' in b: return 'dairy_milk_or_cream'
    if 'cheese' in b: return 'cheese'
    if 'yogurt' in b: return 'yogurt'
    if 'ice cream' in b or 'frozen yogurt' in b or 'frozen dessert' in b: return 'ice_cream'
    if 'water' in b: return 'water'
    if 'tea' in b: return 'tea'
    if 'coffee' in b: return 'coffee'
    if 'soda' in b: return 'soda'
    if 'juice' in b: return 'juice'
    if 'sport drink' in b: return 'sport_drink'
    if 'energy' in b and 'protein' in b: return 'energy_protein_drink'
    if 'beer' in b or 'alcohol' in b: return 'alcohol'
    if 'candy' in b or 'chocolate' in b or 'gum' in b or 'mint' in b: return 'candy_or_chocolate'
    if 'cookie' in b or 'biscoti' in b or 'cake' in b or 'pie' in b or 'donut' in b or 'pastry' in b: return 'bakery_dessert'
    if 'bread' in b or 'bun' in b or 'tortilla' in b or 'bagel' in b: return 'bakery_bread'
    if 'cracker' in b or 'pretzel' in b: return 'cracker_pretzel'
    if 'chip' in b or 'popcorn' in b: return 'chips_popcorn'
    if 'snack' in b or 'granola bar' in b or 'energy bar' in b or 'protein bar' in b: return 'snack_bar'
    if 'nut' in b and 'butter' not in b: return 'nuts_seeds'
    if 'butter' in b or 'spread' in b: return 'butter_spread'
    if 'pizza' in b: return 'pizza'
    if 'frozen dinner' in b or 'entree' in b or 'meal' in b or 'pot pie' in b: return 'frozen_meal'
    if 'sausage' in b or 'hotdog' in b or 'brat' in b: return 'hotdog_sausage'
    if 'pepperoni' in b or 'salami' in b or 'cold cut' in b or 'deli' in b: return 'deli_meat'
    if 'bacon' in b: return 'bacon'
    if 'beef' in b or 'pork' in b or 'chicken' in b or 'turkey' in b or 'meat' in b or 'poultry' in b: return 'fresh_meat'
    if 'fish' in b or 'seafood' in b or 'shellfish' in b or 'shrimp' in b or 'tuna' in b: return 'seafood'
    if 'pasta' in b or 'noodle' in b: return 'pasta'
    if 'rice' in b or 'grain' in b: return 'grain'
    if 'cereal' in b: return 'cereal'
    if 'flour' in b: return 'flour'
    if 'oil' in b: return 'oil'
    if 'vinegar' in b: return 'vinegar'
    if 'sugar' in b or 'sweetener' in b or 'honey' in b or 'syrup' in b or 'molasses' in b: return 'sweetener'
    if 'jam' in b or 'jelly' in b or 'spread' in b: return 'jam_jelly'
    if 'salad dressing' in b or 'mayonnaise' in b: return 'dressing_mayo'
    if 'ketchup' in b or 'mustard' in b or 'bbq' in b or 'cheese sauce' in b or 'condiment' in b: return 'condiment'
    if 'salsa' in b or 'dip' in b: return 'salsa_dip'
    if 'pasta sauce' in b or 'pizza sauce' in b or 'cooking sauce' in b: return 'cooking_sauce'
    if 'soup' in b or 'broth' in b or 'stock' in b or 'chili' in b or 'stew' in b: return 'soup_broth'
    if 'gravy' in b: return 'gravy'
    if 'spice' in b or 'seasoning' in b or 'salt' in b or 'pepper' in b or 'herb' in b: return 'spice_seasoning'
    if 'pickled' in b or 'pickle' in b or 'olive' in b: return 'pickled_olive'
    if 'fruit' in b and 'vegetable' in b: return 'pre_packaged_fruit_veg'
    if 'fruit' in b: return 'fruit'
    if 'vegetable' in b: return 'vegetable'
    if 'baby' in b or 'infant' in b: return 'baby_food'
    if 'pet' in b: return 'pet_food'
    return 'other'

# -------------------- load all signals --------------------
log("Loading v6 (S1, S2, S3) ...")
v6_by_gtin: dict[str, dict] = {}
v6_by_fdc: dict[str, dict] = {}
with open(V6, newline='') as fh:
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
log(f"  v6 by_gtin={len(v6_by_gtin):,} by_fdc={len(v6_by_fdc):,}")

log("Loading master_products (S4 + ingredients_parsed) ...")
con = sqlite3.connect(DB)
mp_by_gtin: dict[str, dict] = {}
mp_by_fdc: dict[str, dict] = {}
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
    if rec['gtin_upc']: mp_by_gtin[rec['gtin_upc']] = rec
    if rec['fdc_id']: mp_by_fdc[rec['fdc_id']] = rec
log(f"  master_products by_gtin={len(mp_by_gtin):,} by_fdc={len(mp_by_fdc):,}")

log("Loading parsed_titles (S8-S11) ...")
parsed_by_gtin: dict[str, dict] = {}
parsed_by_fdc: dict[str, dict] = {}
PARSE_COLS = ['supercategory','category_group','category','form','flavor','retail_leaf','primary_food']
with open(PARSED, newline='') as fh:
    for r in csv.DictReader(fh):
        slim = {k: r.get(k, '') for k in PARSE_COLS}
        g = (r.get('gtin_upc') or '').strip()
        f = (r.get('fdc_id') or '').strip()
        if g: parsed_by_gtin[g] = slim
        if f: parsed_by_fdc[f] = slim
log(f"  parsed_titles loaded: {len(parsed_by_gtin):,}")

log("Loading funnel output (S5, S6, S7) ...")
funnel_by_gtin: dict[str, dict] = {}
funnel_by_fdc: dict[str, dict] = {}
F_COLS = ['l1_cluster','l1_tree_label','l1_modal_bfc','sub_leaf','sub_leaf_label','sub_leaf_modal_bfc']
with open(FUNNEL_PATH, newline='') as fh:
    for r in csv.DictReader(fh):
        slim = {k: r.get(k, '') for k in F_COLS}
        g = (r.get('gtin_upc') or '').strip()
        f = (r.get('fdc_id') or '').strip()
        if g: funnel_by_gtin[g] = slim
        if f: funnel_by_fdc[f] = slim
log(f"  funnel loaded: {len(funnel_by_gtin):,}")

log("Loading product embeddings + ESHA tree embeddings (S12) ...")
prod_ids = np.load(os.path.join(EMB, 'prod_ids.npy'), allow_pickle=True)
prod_emb = np.load(os.path.join(EMB, 'prod_emb.npy'), allow_pickle=True).astype(np.float32)
tree_emb = np.load(os.path.join(EMB, 'tree_emb.npy'), allow_pickle=True).astype(np.float32)
with open(os.path.join(EMB, 'tree_codes.pkl'), 'rb') as fh:
    tree_codes = pickle.load(fh)
pn = np.linalg.norm(prod_emb, axis=1, keepdims=True); pn[pn==0]=1; prod_emb /= pn
tn = np.linalg.norm(tree_emb, axis=1, keepdims=True); tn[tn==0]=1; tree_emb /= tn
log(f"  prod_emb: {prod_emb.shape}  tree_emb: {tree_emb.shape}")

log("Computing embedding → top-1 ESHA tree node (one matrix multiply) ...")
sim = prod_emb @ tree_emb.T  # (462646, 39691)
top1_idx = np.argmax(sim, axis=1)
top1_score = np.max(sim, axis=1)
embed_by_pid: dict[str, tuple[str,str,float]] = {}
for i, pid in enumerate(prod_ids):
    code, desc = tree_codes[int(top1_idx[i])]
    embed_by_pid[str(pid)] = (code, desc, float(top1_score[i]))
log(f"  embed_by_pid: {len(embed_by_pid):,}")

log("Loading ingredient centroids (S13) ...")
centroids = {}  # fndds -> (desc, n, dict[token->score])
with open(ING_CENTROIDS) as fh:
    for line in fh:
        if line.startswith('#'): continue
        parts = line.rstrip('\n').split('\t')
        if len(parts) < 4: continue
        fc, desc, n, toks = parts[:4]
        try: n_int = int(n)
        except: continue
        if n_int < 30: continue  # filter small / unstable centroids
        d = {}
        for t in toks.split('|'):
            if ':' in t:
                k, v = t.rsplit(':', 1)
                try: d[k] = float(v)
                except: pass
        if d: centroids[fc] = (desc, n_int, d)
import math
cent_norm = {fc: math.sqrt(sum(v*v for v in d.values())) for fc, (_,_,d) in centroids.items()}
log(f"  centroids (n>=30): {len(centroids):,}")

# Tokenizer for ingredient signature
TOK = re.compile(r"[a-z][a-z]+")
ING_NOISE = {
    'and','of','the','a','with','to','from','for','contains','less','than',
    'enriched','natural','flavor','flavors','color','colors','water','salt','sugar',
    'soybean','vegetable','spices','spice','preservative','preservatives','citric','acid',
    'modified','starch','vinegar','dried','powder','extract','solids','organic','sea',
    'thiamine','niacin','riboflavin','folic','iron','vitamin','mononitrate','cellulose',
    'potassium','calcium','phosphate','lactic','malic','monoglycerides','diglycerides',
    'lecithin','xanthan','guar','locust','bean','gum','annatto','turmeric','paprika',
    'silicon','dioxide','sucralose','aspartame','made','from','ingredients','distilled',
}
def ing_signature(ing: str) -> Counter:
    s = (ing or '').lower()
    s = re.sub(r'\([^)]*\)', ' ', s)
    return Counter(t for t in TOK.findall(s) if len(t) > 3 and t not in ING_NOISE)

def best_ing_centroid(ing: str) -> tuple[str,str,float]:
    sig = ing_signature(ing)
    if not sig: return ('','',0.0)
    sn = math.sqrt(sum(v*v for v in sig.values())) or 1.0
    best = (0.0, '', '')
    for fc, (desc, _n, cd) in centroids.items():
        cn = cent_norm[fc]
        if cn == 0: continue
        dot = 0.0
        for t, w in cd.items():
            sw = sig.get(t)
            if sw: dot += w * sw
        if dot == 0: continue
        cos = dot / (sn * cn)
        if cos > best[0]: best = (cos, fc, desc)
    return (best[1], best[2], best[0])

# -------------------- consensus loop --------------------
log("Walking all 462,646 products and computing consensus ...")
total = 0
agree_dist = Counter()
super_dist = Counter()

OUT_COLS = [
    'gtin_upc','fdc_id','product_description','brand_owner','brand_name','branded_food_category',
    # raw signals
    'S1_v6_fndds_code','S1_v6_fndds_desc',
    'S2_v6_esha_code','S2_v6_esha_desc',
    'S3_wweia_category',
    'S4_bfc_super',
    'S5_funnel_cluster','S6_funnel_tree_label','S7_funnel_subleaf',
    'S8_parser_super','S9_parser_category','S10_parser_form','S11_parser_flavor','S11b_parser_retail_leaf',
    'S12_embed_top_esha_code','S12_embed_top_esha_desc','S12_embed_score',
    'S13_ingredient_top_fndds_code','S13_ingredient_top_fndds_desc','S13_ingredient_score',
    'S14_ingredient_categories',
    # consensus
    'consensus_supercategory','consensus_leaf','agreement_score','signal_count','disagreement_flags',
]

n_high = n_med = n_low = 0
n_dis = 0

with open(OUT_MAIN, 'w', newline='') as fhmain, open(OUT_DIS, 'w', newline='') as fhdis:
    w = csv.writer(fhmain); w.writerow(OUT_COLS)
    wd = csv.writer(fhdis); wd.writerow(OUT_COLS)
    for i, pid in enumerate(prod_ids):
        ps = str(pid)
        # Resolve metadata: try fdc_id first (prod_ids look like fdc_ids)
        mp = mp_by_fdc.get(ps) or mp_by_gtin.get(ps)
        if not mp:
            continue
        gtin = mp['gtin_upc']; fdc = mp['fdc_id']
        v6  = v6_by_gtin.get(gtin) or v6_by_fdc.get(fdc) or {}
        par = parsed_by_gtin.get(gtin) or parsed_by_fdc.get(fdc) or {}
        fun = funnel_by_gtin.get(gtin) or funnel_by_fdc.get(fdc) or {}
        emb_code, emb_desc, emb_score = embed_by_pid.get(ps, ('','',0.0))
        ing_fc, ing_fd, ing_score = best_ing_centroid(mp['ingredients_clean'])

        bfc = mp['branded_food_category']
        super_bfc = super_from_bfc(bfc)

        # Ingredient categories list
        ing_cats = []
        try:
            items = json.loads(mp['ingredients_parsed']) if mp['ingredients_parsed'] else []
            seen = set()
            for it in items[:15]:
                if isinstance(it, dict) and it.get('category'):
                    c = it['category']
                    if c not in seen:
                        seen.add(c); ing_cats.append(c)
        except: pass
        ing_cats_str = '|'.join(ing_cats[:8])

        # Compute consensus supercategory: vote among super_bfc, parser_super, wweia (mapped to super)
        supers = []
        if super_bfc and super_bfc != 'other':
            supers.append(super_bfc)
        ps_super = (par.get('supercategory') or '').lower()
        if ps_super:
            # map parser super to our key set
            k = super_from_bfc(ps_super.replace('|',' ')) if ps_super != 'unclassified' else 'other'
            if k != 'other':
                supers.append(k)
        wweia = (v6.get('wweia_category_description') or '')
        if wweia:
            k = super_from_bfc(wweia)
            if k != 'other':
                supers.append(k)
        consensus_super = Counter(supers).most_common(1)[0][0] if supers else 'unknown'

        # Consensus leaf: vote among the descriptive leaves
        leaf_candidates = []
        if v6.get('v6_fndds_description'): leaf_candidates.append(v6['v6_fndds_description'].lower())
        if v6.get('best_esha_description'): leaf_candidates.append(v6['best_esha_description'].lower())
        if fun.get('l1_tree_label'): leaf_candidates.append(fun['l1_tree_label'].lower())
        if par.get('retail_leaf'): leaf_candidates.append(par['retail_leaf'].lower())
        if emb_desc: leaf_candidates.append(emb_desc.lower())
        if ing_fd: leaf_candidates.append(ing_fd.lower())
        # Reduce each to a comparable signature: most distinctive non-noise tokens
        leaf_sigs = [' '.join(sorted(tokens(l))[:3]) for l in leaf_candidates if l]
        if leaf_sigs:
            leaf_consensus_sig, _ = Counter(leaf_sigs).most_common(1)[0]
        else:
            leaf_consensus_sig = ''
        # Pick the actual leaf string that produced that signature (prefer v6 fndds)
        consensus_leaf = ''
        for cand in [v6.get('v6_fndds_description',''), v6.get('best_esha_description',''),
                     par.get('retail_leaf',''), fun.get('l1_tree_label',''),
                     emb_desc, ing_fd]:
            if cand and ' '.join(sorted(tokens(cand))[:3]) == leaf_consensus_sig:
                consensus_leaf = cand; break
        if not consensus_leaf and leaf_candidates:
            consensus_leaf = leaf_candidates[0]

        # Agreement score = number of leaf signals matching the consensus signature
        agree = sum(1 for s in leaf_sigs if s == leaf_consensus_sig)
        signal_count = len(leaf_sigs)

        # Disagreement flags
        flags = []
        if v6.get('v6_fndds_description'):
            sig = ' '.join(sorted(tokens(v6['v6_fndds_description']))[:3])
            if sig != leaf_consensus_sig: flags.append('v6_fndds')
        if v6.get('best_esha_description'):
            sig = ' '.join(sorted(tokens(v6['best_esha_description']))[:3])
            if sig != leaf_consensus_sig: flags.append('v6_esha')
        if fun.get('l1_tree_label'):
            sig = ' '.join(sorted(tokens(fun['l1_tree_label']))[:3])
            if sig != leaf_consensus_sig: flags.append('funnel')
        if par.get('retail_leaf'):
            sig = ' '.join(sorted(tokens(par['retail_leaf']))[:3])
            if sig != leaf_consensus_sig: flags.append('parser')
        if emb_desc:
            sig = ' '.join(sorted(tokens(emb_desc))[:3])
            if sig != leaf_consensus_sig: flags.append('embed')
        if ing_fd:
            sig = ' '.join(sorted(tokens(ing_fd))[:3])
            if sig != leaf_consensus_sig: flags.append('ingredient')
        flags_str = '|'.join(flags)

        if signal_count == 0:
            conf = 'low'
        elif agree >= 4:
            conf = 'high'; n_high += 1
        elif agree >= 2:
            conf = 'medium'; n_med += 1
        else:
            conf = 'low'; n_low += 1
        if len(flags) >= 3:
            n_dis += 1

        agree_dist[(agree, signal_count)] += 1
        super_dist[consensus_super] += 1
        total += 1

        row = [gtin, fdc, mp['description'], mp['brand_owner'], mp['brand_name'], bfc,
               v6.get('v6_fndds_code',''), v6.get('v6_fndds_description',''),
               v6.get('best_esha_code',''), v6.get('best_esha_description',''),
               wweia, super_bfc,
               fun.get('l1_cluster',''), fun.get('l1_tree_label',''), fun.get('sub_leaf_label',''),
               par.get('supercategory',''), par.get('category',''), par.get('form',''),
               par.get('flavor',''), par.get('retail_leaf',''),
               emb_code, emb_desc, round(emb_score,3),
               ing_fc, ing_fd, round(ing_score,3),
               ing_cats_str,
               consensus_super, consensus_leaf, agree, signal_count, flags_str]
        w.writerow(row)
        if len(flags) >= 3:
            wd.writerow(row)

        if (i+1) % 50000 == 0:
            log(f"  ...{i+1:,}")

log("DONE")
log(f"\nTotal products: {total:,}")
log(f"Confidence: high={n_high:,}  medium={n_med:,}  low={n_low:,}")
log(f"Disagreements (>=3 conflicting signals): {n_dis:,}")

with open(OUT_SUMM, 'w') as fh:
    fh.write(f"=== Consensus taxonomy build  ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===\n\n")
    fh.write(f"Total products: {total:,}\n")
    fh.write(f"Confidence: high={n_high:,} medium={n_med:,} low={n_low:,}\n")
    fh.write(f"Disagreements (≥3 conflicting signals): {n_dis:,}\n\n")
    fh.write(f"Agreement distribution (n_agree, n_signals):\n")
    for k, c in sorted(agree_dist.items()):
        fh.write(f"  agree={k[0]} of {k[1]} signals  →  {c:>10,}\n")
    fh.write(f"\nConsensus supercategory distribution:\n")
    for s, c in super_dist.most_common(30):
        fh.write(f"  {c:>8,}  {s}\n")

print(f"\nFiles:\n  {OUT_MAIN}\n  {OUT_DIS}\n  {OUT_SUMM}")
