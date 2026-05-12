#!/usr/bin/env python3
"""Build human-readable audit views of the funnel output.

Outputs:
  retail_mapper/audit/cluster_1463_almond_milk.csv  — every product in the almond-milk cluster
  retail_mapper/audit/cluster_799_egg_nog.csv       — every product in the eggnog cluster
  retail_mapper/audit/cluster_1917_hummus.csv       — the cluster that swallowed hummus + flatbread
  retail_mapper/audit/cluster_2320_mayo.csv         — the lime mayo cluster
  retail_mapper/audit/cluster_1590_corn_dog.csv     — the corn dog cluster
  retail_mapper/audit/other_dump_top20.csv          — products dumped to "other" in 20 worst clusters
  retail_mapper/audit/summary.md                    — what to look at and what to look for

Each cluster CSV has columns optimized for eyeballing:
  cluster_id, sub_leaf_label, product_description, branded_food_category, brand_name,
  best_esha_description, ingredients_top5, has_cocoa, has_milk, has_egg, has_cream,
  what_should_it_be (a heuristic guess based on signals)
"""
from __future__ import annotations
import os, sys, csv, json, sqlite3, time
from collections import Counter, defaultdict

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')
PATH_FUNNEL = os.path.join(RM, 'funnel_product_path.csv')
AUDIT_DIR = os.path.join(RM, 'audit')
os.makedirs(AUDIT_DIR, exist_ok=True)

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

# Clusters of interest
TARGETS = {
    '1463': 'almond_milk',
    '662':  'almond_milk_alt',
    '799':  'egg_nog',
    '1917': 'salsa_swallowed_hummus',
    '2320': 'mayo_lime',
    '1590': 'corn_dog',
    '1912': 'chicken_nuggets',
    '20':   'ice_cream_sandwich',
    '2586': 'milk_chocolate',
    '1947': 'chocolate_milk',
    '1344': 'chunky_monkey',
}

log("Loading master_products ingredients...")
con = sqlite3.connect(DB)
ing_by_gtin = {}
ing_by_fdc  = {}
for r in con.execute("""
    SELECT gtin_upc, fdc_id, ingredients_clean, ingredients_parsed
    FROM products
"""):
    rec = (r[2] or '', r[3] or '')
    if r[0]: ing_by_gtin[r[0]] = rec
    if r[1]: ing_by_fdc[str(r[1])] = rec

def parse_top5(ip_json: str) -> tuple[str,str]:
    """Return (top5_names_str, has_flags_dict)."""
    try:
        items = json.loads(ip_json) if ip_json else []
    except:
        items = []
    names = []
    cats = []
    for it in items[:5]:
        if isinstance(it, dict):
            names.append(it.get('name','')[:25])
            cats.append(it.get('category','')[:12])
    return ' | '.join(names), ' | '.join(cats)

def has_signals(ing_clean: str) -> dict:
    t = (ing_clean or '').lower()
    return {
        'has_cocoa': 'Y' if ('cocoa' in t or 'chocolate' in t) else '',
        'has_milk':  'Y' if 'milk' in t else '',
        'has_egg':   'Y' if (' egg ' in t or 'eggs' in t) else '',
        'has_cream': 'Y' if 'cream' in t else '',
        'has_batter': 'Y' if 'batter' in t else '',
        'has_hot_dog': 'Y' if ('hot dog' in t or 'frankfurter' in t or 'wiener' in t) else '',
        'has_almond': 'Y' if 'almond' in t else '',
        'has_lime': 'Y' if 'lime' in t else '',
        'has_lemon': 'Y' if 'lemon' in t else '',
        'has_chipotle': 'Y' if 'chipotle' in t else '',
        'has_pumpkin': 'Y' if 'pumpkin' in t else '',
    }

def what_should_it_be(title: str, bfc: str, sigs: dict) -> str:
    title_l = title.lower()
    # Almond milk variants
    if 'almond' in title_l and ('milk' in title_l or 'beverage' in title_l) and 'plant based milk' in bfc.lower():
        if 'chocolate' in title_l or sigs['has_cocoa'] == 'Y':
            return 'almond_milk > chocolate'
        if 'vanilla' in title_l: return 'almond_milk > vanilla'
        if 'pumpkin' in title_l or 'spice' in title_l: return 'almond_milk > pumpkin_spice'
        if 'unsweet' in title_l: return 'almond_milk > unsweetened'
        if 'original' in title_l: return 'almond_milk > original'
        return 'almond_milk > plain'
    if 'eggnog' in title_l or 'egg nog' in title_l:
        if 'almond' in title_l: return 'plant_milk_nog > almond'
        return 'eggnog'
    if 'corn dog' in title_l: return 'corn_dog'
    if 'hot dog' in title_l and 'corn' not in title_l: return 'hot_dog'
    if 'chicken nugget' in title_l: return 'chicken_nuggets'
    if 'ice cream sandwich' in title_l or 'cream sandwich' in title_l: return 'ice_cream_sandwich'
    if 'milk chocolate' in title_l and 'milk' not in bfc.lower(): return 'chocolate > milk_chocolate'
    if 'chocolate milk' in title_l or ('chocolate' in title_l and 'milk' in bfc.lower()): return 'milk > chocolate'
    if 'chunky monkey' in title_l: return 'ice_cream > chunky_monkey'
    if 'hummus' in title_l:
        if 'cracker' in title_l or 'flatbread' in title_l or 'pita' in title_l or 'chip' in title_l:
            return 'combo > hummus + cracker/chip'
        return 'hummus'
    if 'mayo' in title_l or 'mayonnaise' in title_l:
        if 'chipotle' in title_l: return 'mayonnaise > chipotle'
        if 'lime' in title_l or 'lemon' in title_l: return 'mayonnaise > citrus'
        if 'avocado' in title_l: return 'mayonnaise > avocado'
        return 'mayonnaise > plain'
    return ''

log("Walking funnel_product_path.csv and emitting per-cluster audit views...")
cluster_rows: dict[str, list[dict]] = defaultdict(list)
other_rows_by_cluster: dict[str, list[dict]] = defaultdict(list)
cluster_other_count: Counter = Counter()
cluster_total: Counter = Counter()

with open(PATH_FUNNEL, newline='') as fh:
    reader = csv.DictReader(fh)
    for r in reader:
        cid = r['l1_cluster']
        cluster_total[cid] += 1
        sl_label = r['sub_leaf_label']
        if sl_label == 'other':
            cluster_other_count[cid] += 1
        if cid in TARGETS:
            ing = ing_by_gtin.get(r['gtin_upc']) or ing_by_fdc.get(r['fdc_id']) or ('','')
            top5, top5_cats = parse_top5(ing[1])
            sigs = has_signals(ing[0])
            should = what_should_it_be(r['product_description'] or '', r['branded_food_category'] or '', sigs)
            cluster_rows[cid].append({
                'cluster_id': cid,
                'sub_leaf_label': sl_label,
                'product_description': r['product_description'],
                'branded_food_category': r['branded_food_category'],
                'best_esha_description': r['best_esha_description'],
                'l1_tree_label': r['l1_tree_label'],
                'l1_modal_bfc': r['l1_modal_bfc'],
                'ingredients_top5': top5,
                'ingredients_top5_cats': top5_cats,
                **sigs,
                'what_should_it_be': should,
            })
        if sl_label == 'other':
            ing = ing_by_gtin.get(r['gtin_upc']) or ing_by_fdc.get(r['fdc_id']) or ('','')
            top5, _ = parse_top5(ing[1])
            sigs = has_signals(ing[0])
            should = what_should_it_be(r['product_description'] or '', r['branded_food_category'] or '', sigs)
            if len(other_rows_by_cluster[cid]) < 15:
                other_rows_by_cluster[cid].append({
                    'cluster_id': cid,
                    'l1_tree_label': r['l1_tree_label'],
                    'l1_modal_bfc': r['l1_modal_bfc'],
                    'product_description': r['product_description'],
                    'branded_food_category': r['branded_food_category'],
                    'ingredients_top5': top5,
                    'has_cocoa': sigs['has_cocoa'], 'has_milk': sigs['has_milk'],
                    'has_egg': sigs['has_egg'], 'has_almond': sigs['has_almond'],
                    'what_should_it_be': should,
                })

log("Writing per-cluster audit CSVs...")
for cid, alias in TARGETS.items():
    rows = cluster_rows.get(cid, [])
    if not rows:
        log(f"  cluster {cid} ({alias}): EMPTY")
        continue
    path = os.path.join(AUDIT_DIR, f'cluster_{cid}_{alias}.csv')
    with open(path, 'w', newline='') as fh:
        cols = list(rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        # Sort: 'other' rows first, then by sub_leaf_label
        rows.sort(key=lambda r: (r['sub_leaf_label'] != 'other', r['sub_leaf_label']))
        for r in rows: w.writerow(r)
    log(f"  cluster {cid} ({alias}): {len(rows)} rows -> {path}")

# Top 20 worst "other" clusters (by absolute count of 'other')
log("Building other_dump_top20.csv...")
worst = sorted(cluster_other_count.items(), key=lambda kv: -kv[1])[:20]
worst_ids = {cid for cid, _ in worst}
path = os.path.join(AUDIT_DIR, 'other_dump_top20.csv')
with open(path, 'w', newline='') as fh:
    cols = ['cluster_id','l1_tree_label','l1_modal_bfc','product_description',
            'branded_food_category','ingredients_top5','has_cocoa','has_milk',
            'has_egg','has_almond','what_should_it_be','cluster_other_pct',
            'cluster_other_count','cluster_total']
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    for cid, _ in worst:
        n_other = cluster_other_count[cid]
        n_total = cluster_total[cid]
        pct = round(100*n_other/max(n_total,1), 1)
        for s in other_rows_by_cluster[cid][:10]:
            row = {**s,
                   'cluster_other_pct': pct,
                   'cluster_other_count': n_other,
                   'cluster_total': n_total}
            w.writerow(row)
log(f"  -> {path}")

# Summary markdown
log("Writing summary.md...")
summary_path = os.path.join(AUDIT_DIR, 'summary.md')
with open(summary_path, 'w') as fh:
    fh.write("# Funnel audit — what to look at\n\n")
    fh.write(f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    fh.write("## Top-line numbers\n\n")
    fh.write(f"- Total products: {sum(cluster_total.values()):,}\n")
    fh.write(f"- Products with sub_leaf == 'other': {sum(cluster_other_count.values()):,} ({100*sum(cluster_other_count.values())/sum(cluster_total.values()):.1f}%)\n")
    fh.write(f"- Total L1 clusters: {len(cluster_total):,}\n")
    fh.write(f"- Clusters with >50% 'other': {sum(1 for c in cluster_total if cluster_other_count[c]/max(cluster_total[c],1) > 0.5):,}\n\n")
    fh.write("## Cluster-by-cluster audit files\n\n")
    fh.write("Open each in a spreadsheet. Sort by `sub_leaf_label`; the `other` rows are listed first.\n")
    fh.write("Compare `product_description` + `ingredients_top5` against `sub_leaf_label`. The `what_should_it_be` column is my heuristic guess for the right leaf.\n\n")
    for cid, alias in TARGETS.items():
        n = len(cluster_rows.get(cid, []))
        if n:
            n_other = sum(1 for r in cluster_rows[cid] if r['sub_leaf_label'] == 'other')
            fh.write(f"- **`audit/cluster_{cid}_{alias}.csv`** — {n} products, {n_other} ({100*n_other/n:.0f}%) in 'other'\n")
    fh.write("\n## Worst dumps\n\n")
    fh.write("`audit/other_dump_top20.csv` — for the 20 clusters with the most `other` products, 10 sample 'other' members per cluster, with what they should have been.\n\n")
    fh.write("## Top 20 worst clusters by 'other' count\n\n")
    fh.write("| cluster_id | tree_label | modal_bfc | n_total | n_other | pct |\n|---|---|---|---|---|---|\n")
    # need tree_label and modal_bfc — get from first member of each cluster
    # already in cluster_rows for TARGETS; for others, need a separate scan
    # quick: read funnel_l1_clusters.csv for tree label
    cl_meta = {}
    with open(os.path.join(RM, 'funnel_l1_clusters.csv'), newline='') as cfh:
        for r in csv.DictReader(cfh):
            cl_meta[r['cluster_id']] = (r['tree_top1_desc'], r['modal_bfc'])
    for cid, n_other in worst:
        n_total = cluster_total[cid]
        tree, bfc = cl_meta.get(cid, ('',''))
        fh.write(f"| {cid} | {tree[:50]} | {bfc[:30]} | {n_total} | {n_other} | {100*n_other/n_total:.0f}% |\n")
log(f"  -> {summary_path}")
log("DONE")
print(f"\nAudit folder: {AUDIT_DIR}")
