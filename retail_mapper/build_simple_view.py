#!/usr/bin/env python3
"""Build a human-readable view of the consensus taxonomy.

Two files:
  simple_view.csv   — one row per product, just 7 columns:
      gtin_upc, product_title, brand, supercategory, retail_leaf, confidence, ingredients_top5
  leaf_catalog.csv  — one row per unique leaf:
      supercategory, retail_leaf, n_products, top_brands, sample_products
"""
from __future__ import annotations
import os, csv, sys, sqlite3, json, time
from collections import Counter, defaultdict

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')
IN   = os.path.join(RM, 'consensus_taxonomy_v2.csv')
OUT_SIMPLE  = os.path.join(RM, 'simple_view.csv')
OUT_CATALOG = os.path.join(RM, 'leaf_catalog.csv')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

# Map technical supercategory keys to human-readable names
SUPER_LABEL = {
    'candy_or_chocolate':'Candy & Chocolate',
    'snack_bar':'Snack Bars',
    'bakery_dessert':'Bakery & Desserts',
    'cheese':'Cheese',
    'unknown':'Uncategorized',
    'chips_popcorn':'Chips & Popcorn',
    'spice_seasoning':'Spices & Seasonings',
    'dairy_milk_or_cream':'Dairy Milk & Cream',
    'cracker_pretzel':'Crackers & Pretzels',
    'frozen_meal':'Frozen Meals',
    'bakery_bread':'Bread & Buns',
    'juice':'Juice',
    'vegetable':'Vegetables',
    'fresh_meat':'Fresh Meat',
    'cereal':'Cereal',
    'deli_meat':'Deli Meat',
    'pasta':'Pasta',
    'butter_spread':'Butter & Spreads',
    'seafood':'Seafood',
    'soup_broth':'Soup & Broth',
    'soda':'Soda',
    'pizza':'Pizza',
    'yogurt':'Yogurt',
    'water':'Water',
    'hotdog_sausage':'Hot Dogs & Sausage',
    'salsa_dip':'Salsa & Dips',
    'pre_packaged_fruit_veg':'Pre-Packaged Produce',
    'dressing_mayo':'Dressings & Mayo',
    'sweetener':'Sweeteners',
    'pet_food':'Pet Food',
    'condiment':'Condiments',
    'cooking_sauce':'Cooking Sauces',
    'jam_jelly':'Jam & Jelly',
    'ice_cream':'Ice Cream',
    'plant_milk':'Plant-Based Milk',
    'oil':'Cooking Oils',
    'pasta':'Pasta',
    'gravy':'Gravy',
    'fruit':'Fresh Fruit',
    'tea':'Tea',
    'coffee':'Coffee',
    'flour':'Flour',
    'grain':'Grains & Rice',
    'bacon':'Bacon',
    'pickled_olive':'Pickled & Olives',
    'sport_drink':'Sport Drinks',
    'energy_protein_drink':'Energy & Protein Drinks',
    'alcohol':'Alcohol',
    'baby_food':'Baby Food',
    'nuts_seeds':'Nuts & Seeds',
    'vinegar':'Vinegar',
}

# Load ingredient_top5 for each product (top 5 ingredients)
log("Loading ingredients_parsed...")
con = sqlite3.connect(DB)
ing_top5_by_gtin: dict[str, str] = {}
ing_top5_by_fdc:  dict[str, str] = {}
for r in con.execute("SELECT gtin_upc, fdc_id, ingredients_parsed FROM products WHERE ingredients_parsed IS NOT NULL"):
    try:
        items = json.loads(r[2]) if r[2] else []
    except: items = []
    names = [it.get('name','')[:25] for it in items[:5] if isinstance(it, dict)]
    s = ' | '.join(names)
    if r[0]: ing_top5_by_gtin[r[0]] = s
    if r[1]: ing_top5_by_fdc[str(r[1])] = s
log(f"  ingredients_top5 by_gtin={len(ing_top5_by_gtin):,}")

log(f"Reading {IN}...")
n = 0
leaf_stats: dict[tuple[str,str], dict] = defaultdict(lambda: {
    'n':0, 'brands':Counter(), 'samples':[]
})

with open(IN, newline='') as src, open(OUT_SIMPLE, 'w', newline='') as out:
    reader = csv.DictReader(src)
    cols = ['gtin_upc','product_title','brand','supercategory','retail_leaf',
            'confidence','ingredients_top5']
    w = csv.writer(out); w.writerow(cols)
    for r in reader:
        gtin = r.get('gtin_upc','')
        title = r.get('product_description','')
        brand = r.get('brand_name','') or r.get('brand_owner','')
        super_key = r.get('consensus_supercategory','')
        super_lbl = SUPER_LABEL.get(super_key, super_key.replace('_',' ').title())
        leaf = r.get('canonical_leaf','') or 'Unclassified'
        conf = r.get('confidence_v2','')
        # ingredients_top5
        ing = ing_top5_by_gtin.get(gtin) or ing_top5_by_fdc.get(r.get('fdc_id','')) or ''
        w.writerow([gtin, title, brand, super_lbl, leaf, conf, ing])

        # accumulate leaf stats
        key = (super_lbl, leaf)
        leaf_stats[key]['n'] += 1
        if brand: leaf_stats[key]['brands'][brand] += 1
        if len(leaf_stats[key]['samples']) < 4:
            leaf_stats[key]['samples'].append(title[:55])
        n += 1
        if n % 100000 == 0: log(f"  ...{n:,}")

log(f"Writing leaf_catalog.csv ({len(leaf_stats):,} unique leaves)...")
with open(OUT_CATALOG, 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['supercategory','retail_leaf','n_products','top_brands','sample_products'])
    for (sup, leaf), s in sorted(leaf_stats.items(), key=lambda kv: -kv[1]['n']):
        top_brands = ' | '.join(f"{b}({c})" for b, c in s['brands'].most_common(3))
        samples = ' || '.join(s['samples'])
        w.writerow([sup, leaf, s['n'], top_brands, samples])

log(f"DONE  — products: {n:,}  unique leaves: {len(leaf_stats):,}")
print(f"\nFiles:\n  {OUT_SIMPLE}\n  {OUT_CATALOG}")
