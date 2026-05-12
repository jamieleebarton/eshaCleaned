#!/usr/bin/env python3
"""Zero-shot classification sample run.

Picks a stratified 2,000-product sample (covering different BFCs) and
classifies each into:
  STAGE 1 — broad retail category  (one of ~80 labels)
  STAGE 2 — sub-leaf within that category (variant labels)

Outputs:
  retail_mapper/audit/zeroshot_sample.csv
"""
from __future__ import annotations
import os, sys, csv, sqlite3, time, random, warnings
from collections import Counter, defaultdict
warnings.filterwarnings('ignore')

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')
OUT  = os.path.join(RM, 'audit/zeroshot_sample.csv')

csv.field_size_limit(sys.maxsize)
t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

# Stage 1 candidate labels — broad retail categories
BROAD_LABELS = [
    # Beverages
    'plant-based milk', 'dairy milk', 'milk creamer', 'eggnog',
    'fruit juice', 'fruit drink', 'smoothie', 'soda', 'sparkling water',
    'still water', 'tea', 'coffee', 'energy drink', 'sport drink',
    'protein shake', 'kombucha',
    # Dairy
    'cheese', 'yogurt', 'cottage cheese', 'sour cream', 'butter',
    'cream', 'ice cream', 'frozen yogurt', 'sherbet sorbet', 'ice cream sandwich',
    # Bakery
    'bread', 'tortilla', 'bagel', 'muffin', 'cookie', 'cake', 'pie',
    'cracker', 'pretzel', 'donut',
    # Snacks
    'chocolate candy', 'gummy candy', 'hard candy', 'mints', 'gum',
    'potato chip', 'corn chip', 'tortilla chip', 'popcorn',
    'granola bar', 'protein bar', 'fruit snack',
    'mixed nuts', 'peanut butter', 'nut butter',
    # Frozen entrees
    'pizza', 'corn dog', 'hot dog', 'chicken nugget', 'fish stick',
    'frozen meal', 'frozen breakfast', 'frozen pasta', 'pot pie',
    'meatball', 'burger patty', 'sausage',
    # Pantry
    'pasta', 'rice', 'cereal', 'oatmeal', 'flour',
    'cooking oil', 'olive oil', 'vinegar',
    'sugar', 'honey', 'maple syrup', 'jam jelly',
    'salad dressing', 'mayonnaise', 'ketchup', 'mustard', 'salsa',
    'pasta sauce', 'cooking sauce', 'hot sauce', 'bbq sauce',
    'soup', 'broth stock', 'gravy',
    'spice seasoning', 'salt', 'baking mix',
    # Produce
    'fresh fruit', 'fresh vegetable', 'salad mix',
    'canned fruit', 'canned vegetable',
    'frozen fruit', 'frozen vegetable',
    'dried fruit',
    # Meat
    'fresh beef', 'fresh chicken', 'fresh pork', 'fresh fish', 'shrimp',
    'bacon', 'deli meat', 'jerky',
    # Combo/dish
    'hummus with chips', 'snack pack', 'lunchables',
    # Protein/supplement
    'protein powder', 'collagen powder', 'vitamin supplement',
    # Other
    'pickles', 'olives',
]

def stage2_labels_for(broad: str) -> list[str]:
    """Return sub-leaf candidate labels for a given broad category."""
    if 'plant-based milk' in broad or 'almond' in broad or 'oat' in broad or 'soy' in broad:
        return ['almond milk plain','almond milk chocolate','almond milk vanilla',
                'almond milk pumpkin spice','almond milk unsweetened','almond milk sweetened',
                'oat milk plain','oat milk chocolate','oat milk vanilla',
                'soy milk plain','soy milk chocolate','soy milk vanilla',
                'coconut milk plain','coconut milk vanilla','coconut milk chocolate',
                'cashew milk','rice milk','pea milk','hemp milk']
    if broad == 'dairy milk':
        return ['whole milk','2% milk','1% milk','skim milk','chocolate milk',
                'strawberry milk','lactose-free milk','flavored milk other']
    if broad == 'eggnog':
        return ['dairy eggnog','almond nog','soy nog','coconut nog']
    if broad == 'corn dog':
        return ['beef corn dog','chicken corn dog','turkey corn dog','mini corn dog','jumbo corn dog']
    if broad == 'hot dog':
        return ['beef hot dog','chicken hot dog','turkey hot dog','pork hot dog','uncured hot dog','plant-based hot dog']
    if broad == 'chicken nugget':
        return ['breaded chicken nugget','grilled chicken nugget','plant-based chicken nugget','organic chicken nugget']
    if broad == 'mayonnaise':
        return ['regular mayonnaise','olive oil mayonnaise','avocado oil mayonnaise',
                'chipotle mayo','sriracha mayo','garlic mayo','lemon mayo','lime mayo','vegan mayo']
    if broad == 'cheese':
        return ['cheddar cheese','mozzarella cheese','parmesan cheese','swiss cheese','gouda cheese',
                'provolone cheese','feta cheese','goat cheese','cream cheese','american cheese',
                'pepper jack','colby cheese','blue cheese','brie cheese']
    if broad == 'yogurt':
        return ['greek yogurt vanilla','greek yogurt strawberry','greek yogurt blueberry','greek yogurt plain',
                'regular yogurt vanilla','regular yogurt strawberry','regular yogurt plain',
                'low-fat yogurt','non-fat yogurt','dairy-free yogurt','drinkable yogurt']
    if broad == 'ice cream':
        return ['vanilla ice cream','chocolate ice cream','strawberry ice cream','cookies and cream',
                'mint chocolate chip','rocky road','chunky monkey banana','butter pecan','neapolitan',
                'salted caramel','dairy-free ice cream']
    if broad in ('chocolate candy','milk chocolate'):
        return ['milk chocolate bar','dark chocolate bar','white chocolate bar','chocolate truffles',
                'chocolate-covered nuts','chocolate-covered fruit','chocolate chips','peanut butter cup']
    if broad == 'peanut butter':
        return ['creamy peanut butter','crunchy peanut butter','natural peanut butter',
                'reduced-fat peanut butter','peanut butter with chocolate','no-stir peanut butter']
    if broad in ('potato chip','tortilla chip','corn chip'):
        return ['original chip','salt and vinegar','sour cream and onion','barbecue chip','jalapeno chip',
                'cheddar chip','dill pickle','spicy chip','baked chip','kettle cooked']
    if broad == 'salad dressing':
        return ['ranch dressing','italian dressing','caesar dressing','blue cheese dressing',
                'balsamic vinaigrette','french dressing','thousand island','honey mustard',
                'olive oil vinaigrette','poppy seed dressing']
    if broad == 'salsa':
        return ['mild salsa','medium salsa','hot salsa','restaurant style salsa','black bean salsa',
                'mango salsa','peach salsa','verde salsa','chunky salsa']
    if broad == 'hummus with chips':
        return ['hummus with pita chips','hummus with crackers','hummus with vegetables','hummus with pretzels']
    if broad == 'pizza':
        return ['cheese pizza','pepperoni pizza','sausage pizza','meat lovers','vegetable pizza',
                'thin crust','deep dish','french bread pizza','flatbread pizza','cauliflower crust']
    return ['plain','flavored','original']  # fallback

def main():
    log("Loading sample from master_products.db...")
    con = sqlite3.connect(DB)
    rows = []
    for r in con.execute("""
        SELECT gtin_upc, fdc_id, description, brand_name, branded_food_category, ingredients_clean
        FROM products
        WHERE description IS NOT NULL
    """):
        rows.append({
            'gtin_upc': r[0] or '', 'fdc_id': str(r[1]) if r[1] else '',
            'description': r[2] or '', 'brand_name': r[3] or '',
            'branded_food_category': r[4] or '', 'ingredients_clean': (r[5] or '')[:200],
        })
    log(f"  total: {len(rows):,}")

    # Stratified sample by BFC: ~25 from each top BFC
    by_bfc = defaultdict(list)
    for r in rows:
        by_bfc[r['branded_food_category']].append(r)
    bfc_sorted = sorted(by_bfc.items(), key=lambda kv: -len(kv[1]))

    random.seed(42)
    sample = []
    target = 2000
    per_bfc = max(2, target // 100)  # take ~per_bfc from each of top 100 BFCs
    for bfc, lst in bfc_sorted[:120]:
        random.shuffle(lst)
        sample.extend(lst[:per_bfc])
        if len(sample) >= target: break

    # Force-include user pain examples
    must_include_phrases = ['CORN DOG','CHICKEN NUGGET','ALMONDMILK','EGG NOG','HUMMUS','MAYO',
                            'CHOCOLATE MILK','MILK CHOCOLATE','GREEK YOGURT','PUMPKIN SPICE',
                            'CHUNKY MONKEY','LIME','CHIPOTLE','APPLE NOODLE KUGEL','APPLE SLICE',
                            'PEANUT BUTTER','ICE CREAM SANDWICH','FRIED APPLE']
    for r in rows:
        if any(p in r['description'].upper() for p in must_include_phrases):
            sample.append(r)
        if len(sample) >= target + 200: break

    sample = sample[:target+200]
    log(f"  sample: {len(sample):,}")

    log("Loading zero-shot classifier (DeBERTa-v3-base)...")
    from transformers import pipeline
    clf = pipeline('zero-shot-classification',
                   model='MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli',
                   device='mps')
    log("  ready")

    log("Stage 1: classify into broad categories...")
    out_rows = []
    for i, r in enumerate(sample):
        text = r['description'].lower()
        if r['branded_food_category']:
            text += ' (category: ' + r['branded_food_category'].lower() + ')'
        try:
            res = clf(text, BROAD_LABELS, multi_label=False)
            broad = res['labels'][0]; broad_score = res['scores'][0]
            broad_top3 = ' | '.join(f"{l}:{s:.2f}" for l, s in zip(res['labels'][:3], res['scores'][:3]))
            # Stage 2: sub-leaf
            sub_labels = stage2_labels_for(broad)
            sub_res = clf(text, sub_labels, multi_label=False) if len(sub_labels) > 1 else None
            sub = sub_res['labels'][0] if sub_res else (sub_labels[0] if sub_labels else '')
            sub_score = sub_res['scores'][0] if sub_res else 0.0
        except Exception as e:
            broad = 'ERROR'; broad_score = 0; broad_top3 = str(e)[:120]; sub = ''; sub_score = 0
        out_rows.append({
            'gtin_upc': r['gtin_upc'], 'fdc_id': r['fdc_id'],
            'product_description': r['description'], 'brand_name': r['brand_name'],
            'branded_food_category': r['branded_food_category'],
            'ingredients_clean_top200': r['ingredients_clean'],
            'broad_category': broad, 'broad_score': round(broad_score, 3),
            'broad_top3': broad_top3,
            'sub_leaf': sub, 'sub_score': round(sub_score, 3),
            'final_leaf': f"{broad} > {sub}" if sub else broad,
        })
        if (i+1) % 100 == 0:
            log(f"  {i+1}/{len(sample)}  ({(i+1)/(time.time()-t0):.1f}/sec)")

    log("Writing output...")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', newline='') as fh:
        if not out_rows: return 0
        cols = list(out_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in out_rows: w.writerow(r)

    # Summary
    broad_dist = Counter(r['broad_category'] for r in out_rows)
    log("\n=== Broad category distribution ===")
    for c, n in broad_dist.most_common(20):
        log(f"  {n:>4}  {c}")
    log(f"\n=== Output: {OUT}")

if __name__ == '__main__':
    main()
