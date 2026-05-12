#!/usr/bin/env python3
"""Join master_products.db ingredients into parsed_titles.csv.

Output: retail_mapper/parsed_titles_with_ingredients.csv
New columns added per row:
  ing_full          — full ingredient text (truncated at 400 chars for the CSV)
  ing_top5          — first 5 ingredients by weight (separated by | )
  ing_categories    — ordered list of distinct ingredient categories (protein|grain|sweetener|...)
  ing_top5_cats     — categories of the first 5 ingredients
  protein_source    — first protein-category ingredient (hot dog / chicken / beef / almond...)
  grain_source      — first grain-category ingredient (corn meal / wheat flour...)
  has_batter        — Y if 'batter' appears in ingredients (corn dog / nugget signal)
  has_breading      — Y if 'bread crumb', 'panko', 'breading' appears
  has_cocoa         — Y if cocoa/chocolate liquor in ingredients
  allergens         — from products.allergens column

The whole point: you can see the leaf next to the actual ingredients and judge
whether the leaf is correct. No FNDDS, no cosine, just signal.
"""
from __future__ import annotations
import os, csv, sys, json, sqlite3, time
from collections import Counter

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')
PARSED  = os.path.join(RM, 'parsed_titles.csv')
OUT     = os.path.join(RM, 'parsed_titles_with_ingredients.csv')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

# ---- Load ingredients keyed by gtin_upc (and a fallback by fdc_id) ----
log("Loading master_products.db ingredients...")
con = sqlite3.connect(DB)
ing_by_gtin: dict[str, dict] = {}
ing_by_fdc:  dict[str, dict] = {}
n = 0
for row in con.execute("""
    SELECT gtin_upc, fdc_id, ingredients, ingredients_clean, ingredients_parsed, allergens
    FROM products
    WHERE ingredients IS NOT NULL AND ingredients != ''
"""):
    gtin, fdc, ing, ing_clean, ing_parsed, allergens = row
    rec = {
        'ing': (ing or '')[:400],
        'ing_clean': (ing_clean or '')[:400],
        'ing_parsed': ing_parsed,
        'allergens': allergens or '',
    }
    if gtin: ing_by_gtin[gtin] = rec
    if fdc:  ing_by_fdc[str(fdc)] = rec
    n += 1
log(f"  loaded {n:,} ingredient records")
log(f"  by gtin: {len(ing_by_gtin):,}  by fdc_id: {len(ing_by_fdc):,}")

def parse_ing(rec: dict) -> dict:
    """Extract structured signals from ingredients_parsed JSON + raw text."""
    out = {
        'ing_full': rec['ing_clean'] or rec['ing'] or '',
        'ing_top5': '',
        'ing_categories': '',
        'ing_top5_cats': '',
        'protein_source': '',
        'grain_source': '',
        'dairy_source': '',
        'sweetener_source': '',
        'oil_source': '',
        'has_batter': '',
        'has_breading': '',
        'has_cocoa': '',
        'has_hot_dog': '',
        'allergens': rec.get('allergens',''),
    }
    parsed = []
    try:
        if rec['ing_parsed']:
            parsed = json.loads(rec['ing_parsed'])
    except Exception:
        parsed = []
    names = [item.get('name','') for item in parsed if isinstance(item, dict)]
    cats  = [item.get('category','') for item in parsed if isinstance(item, dict)]
    out['ing_top5']      = ' | '.join(names[:5])
    out['ing_top5_cats'] = ' | '.join(cats[:5])
    # ordered set of distinct categories
    seen = set(); ordered = []
    for c in cats:
        if c and c not in seen:
            seen.add(c); ordered.append(c)
    out['ing_categories'] = ' | '.join(ordered)
    # first per-category source
    for item in parsed:
        if not isinstance(item, dict): continue
        c = item.get('category',''); name = item.get('name','')
        if not name: continue
        nm = name.lower()
        if c == 'protein' and not out['protein_source']:
            out['protein_source'] = name
        if c == 'grain' and not out['grain_source']:
            out['grain_source'] = name
        if c == 'dairy' and not out['dairy_source']:
            out['dairy_source'] = name
        if c == 'sweetener' and not out['sweetener_source']:
            out['sweetener_source'] = name
        if c == 'oil_fat' and not out['oil_source']:
            out['oil_source'] = name
    text_low = (out['ing_full'] or '').lower()
    if 'batter' in text_low: out['has_batter'] = 'Y'
    if 'breading' in text_low or 'bread crumb' in text_low or 'panko' in text_low: out['has_breading'] = 'Y'
    if 'cocoa' in text_low or 'chocolate liquor' in text_low: out['has_cocoa'] = 'Y'
    if 'hot dog' in text_low or 'frankfurter' in text_low or 'wiener' in text_low or ' frank' in text_low.replace(',', ' ').replace(':', ' '):
        out['has_hot_dog'] = 'Y'
    return out

# ---- Walk parsed_titles, join, write ----
log("Joining ingredients into parsed_titles.csv...")
new_cols = ['ing_full','ing_top5','ing_top5_cats','ing_categories',
            'protein_source','grain_source','dairy_source','sweetener_source','oil_source',
            'has_batter','has_breading','has_cocoa','has_hot_dog','allergens']

n_rows = 0
n_with_ing = 0
cat_counter = Counter()

with open(PARSED, newline='') as src, open(OUT, 'w', newline='') as dst:
    reader = csv.DictReader(src)
    in_fields = reader.fieldnames[:]
    out_fields = in_fields + new_cols
    writer = csv.DictWriter(dst, fieldnames=out_fields)
    writer.writeheader()
    for r in reader:
        n_rows += 1
        gtin = (r.get('gtin_upc') or '').strip()
        fdc  = (r.get('fdc_id')  or '').strip()
        rec = ing_by_gtin.get(gtin) or ing_by_fdc.get(fdc)
        if rec:
            n_with_ing += 1
            extras = parse_ing(rec)
            for c in new_cols:
                r[c] = extras.get(c, '')
            for cat in (extras['ing_categories'] or '').split(' | '):
                if cat: cat_counter[cat] += 1
        else:
            for c in new_cols:
                r[c] = ''
        writer.writerow({k: r.get(k, '') for k in out_fields})
        if n_rows % 100000 == 0:
            log(f"  ...{n_rows:,}")

log("DONE")
log(f"  Rows: {n_rows:,}")
log(f"  With ingredients: {n_with_ing:,} ({100*n_with_ing/n_rows:.1f}%)")
log(f"  Output: {OUT}")
log("\nIngredient category coverage:")
for c, v in cat_counter.most_common(15):
    log(f"  {c:<22s} {v:>10,}")
