#!/usr/bin/env python3
"""Fast label classification by embedding cosine similarity.

Loads:
  implementation/.embed_cache/prod_emb.npy       (462,646 × 384)  product embeddings
  implementation/.embed_cache/prod_ids.npy       (462,646,)       product fdc_ids
  retail_mapper/discovery/retail_labels.json     hierarchical label set

Embeds the labels with all-MiniLM-L6-v2 (the same model used for prod_emb),
computes cosine similarity, picks top-1 + top-3 per product.

Two-stage:
  STAGE 1 (broad)  — every product against ~80 broad category labels
  STAGE 2 (sub-leaf) — within the top-1 broad category, every product against that
                       category's variant labels

Output:
  retail_mapper/audit/embed_classify.csv
    gtin_upc, fdc_id, description, branded_food_category,
    broad_label, broad_score, broad_top3,
    sub_label, sub_score, sub_top3,
    final_leaf
"""
from __future__ import annotations
import os, sys, csv, json, sqlite3, time, pickle, warnings
from collections import Counter, defaultdict
import numpy as np
warnings.filterwarnings('ignore')

ROOT = '/Users/jamiebarton/Desktop/esha_audit_bundle'
RM   = os.path.join(ROOT, 'retail_mapper')
DB   = os.path.join(ROOT, 'data/master_products.db')
EMB  = os.path.join(ROOT, 'implementation/.embed_cache')
OUT  = os.path.join(RM, 'audit/embed_classify.csv')

t0 = time.time()
log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

# Broad category labels — same as in zeroshot_sample.py
BROAD_LABELS = [
    'plant-based milk','dairy milk','milk creamer','eggnog',
    'fruit juice','fruit drink','smoothie','soda','sparkling water',
    'still water','tea','coffee','energy drink','sport drink','protein shake','kombucha',
    'cheese','yogurt','cottage cheese','sour cream','butter','cream',
    'ice cream','frozen yogurt','sherbet sorbet','ice cream sandwich','popsicle',
    'bread','tortilla','bagel','muffin','cookie','cake','pie','pastry','donut',
    'cracker','pretzel',
    'chocolate candy','gummy candy','hard candy','mints','gum',
    'potato chip','corn chip','tortilla chip','popcorn',
    'granola bar','protein bar','fruit snack','fruit roll-up',
    'mixed nuts','peanut butter','almond butter','nut butter',
    'pizza','corn dog','hot dog','chicken nugget','fish stick',
    'frozen meal','frozen breakfast','frozen pasta','pot pie','meatball','burger patty','plant-based burger',
    'sausage','pepperoni','salami','deli meat','bacon','jerky',
    'pasta','rice','cereal','oatmeal','flour','baking mix',
    'cooking oil','olive oil','coconut oil','vegetable oil',
    'sugar','honey','maple syrup','jam jelly',
    'salad dressing','mayonnaise','ketchup','mustard','salsa','hummus','dip',
    'pasta sauce','cooking sauce','hot sauce','bbq sauce','soy sauce',
    'soup','broth stock','gravy','spice seasoning','salt','pepper',
    'fresh fruit','fresh vegetable','salad mix',
    'canned fruit','canned vegetable','frozen fruit','frozen vegetable','dried fruit',
    'fresh beef','fresh chicken','fresh pork','fresh fish','shrimp','seafood',
    'pickles','olives',
    'protein powder','collagen powder','vitamin supplement','energy bar',
    'baby food','infant formula',
    'hummus with pita chips combo','vegetables with dip combo',
    'apple slices with peanut butter combo','cheese and cracker combo',
    'casserole or baked dish','meal kit',
]

# Sub-leaf candidates per broad
def stage2_labels_for(broad: str) -> list[str]:
    if broad == 'plant-based milk':
        return ['almond milk plain','almond milk chocolate','almond milk vanilla',
                'almond milk pumpkin spice','almond milk unsweetened','almond milk sweetened',
                'oat milk plain','oat milk chocolate','oat milk vanilla',
                'soy milk plain','soy milk chocolate','soy milk vanilla',
                'coconut milk plain','coconut milk vanilla','coconut milk chocolate',
                'cashew milk','rice milk','pea milk','hemp milk','flax milk']
    if broad == 'dairy milk':
        return ['whole milk','two percent milk','one percent milk','skim milk',
                'chocolate milk','strawberry milk','lactose-free milk','flavored milk other','organic whole milk']
    if broad == 'eggnog': return ['dairy eggnog','almond nog','soy nog','coconut nog','oat nog']
    if broad == 'corn dog': return ['beef corn dog','chicken corn dog','turkey corn dog','mini corn dog','jumbo corn dog']
    if broad == 'hot dog': return ['beef hot dog','chicken hot dog','turkey hot dog','pork hot dog','uncured hot dog','plant-based hot dog']
    if broad == 'chicken nugget': return ['breaded chicken nugget','grilled chicken nugget','plant-based chicken nugget','organic chicken nugget','popcorn chicken']
    if broad == 'mayonnaise':
        return ['regular mayonnaise','olive oil mayonnaise','avocado oil mayonnaise',
                'chipotle mayo','sriracha mayo','garlic mayo','lemon mayo','lime mayo','vegan mayo','reduced fat mayo']
    if broad == 'cheese':
        return ['cheddar cheese','mozzarella cheese','parmesan cheese','swiss cheese','gouda cheese',
                'provolone cheese','feta cheese','goat cheese','cream cheese','american cheese',
                'pepper jack','colby cheese','blue cheese','brie cheese','ricotta','cottage cheese',
                'string cheese','shredded cheese']
    if broad == 'yogurt':
        return ['greek yogurt vanilla','greek yogurt strawberry','greek yogurt blueberry','greek yogurt plain',
                'regular yogurt vanilla','regular yogurt strawberry','regular yogurt plain',
                'low-fat yogurt','non-fat yogurt','dairy-free yogurt','drinkable yogurt']
    if broad == 'ice cream':
        return ['vanilla ice cream','chocolate ice cream','strawberry ice cream','cookies and cream',
                'mint chocolate chip','rocky road','chunky monkey banana ice cream','butter pecan','neapolitan',
                'salted caramel','dairy-free ice cream','cherry garcia ice cream','phish food']
    if broad in ('chocolate candy',):
        return ['milk chocolate bar','dark chocolate bar','white chocolate bar','chocolate truffles',
                'chocolate-covered nuts','chocolate-covered fruit','chocolate chips','peanut butter cup',
                'chocolate-covered raisins']
    if broad == 'peanut butter':
        return ['creamy peanut butter','crunchy peanut butter','natural peanut butter',
                'reduced-fat peanut butter','peanut butter with chocolate','no-stir peanut butter']
    if broad in ('potato chip','tortilla chip','corn chip'):
        return ['original chip','salt and vinegar chip','sour cream and onion chip','barbecue chip','jalapeno chip',
                'cheddar chip','dill pickle chip','spicy chip','baked chip','kettle cooked chip']
    if broad == 'salad dressing':
        return ['ranch dressing','italian dressing','caesar dressing','blue cheese dressing',
                'balsamic vinaigrette','french dressing','thousand island dressing','honey mustard dressing',
                'olive oil vinaigrette','poppy seed dressing','greek dressing']
    if broad == 'salsa':
        return ['mild salsa','medium salsa','hot salsa','restaurant style salsa','black bean salsa',
                'mango salsa','peach salsa','salsa verde','chunky salsa','pico de gallo']
    if broad == 'pizza':
        return ['cheese pizza','pepperoni pizza','sausage pizza','meat lovers pizza','vegetable pizza',
                'thin crust pizza','deep dish pizza','french bread pizza','flatbread pizza','cauliflower crust pizza',
                'gluten-free pizza','frozen breakfast pizza']
    if broad == 'soda':
        return ['cola','diet cola','lemon-lime soda','orange soda','root beer','ginger ale',
                'cream soda','grape soda','dr pepper-style','black cherry soda','energy soda']
    if broad == 'cooking oil':
        return ['olive oil','extra virgin olive oil','vegetable oil','canola oil','sunflower oil',
                'avocado oil','grapeseed oil','peanut oil','sesame oil']
    if broad == 'plant-based burger':
        return ['plant-based beef-style burger','plant-based chicken-style patty',
                'black bean burger','soy burger','seitan patty','mushroom burger']
    return []

def main():
    log("Loading product embeddings...")
    prod_ids = np.load(os.path.join(EMB, 'prod_ids.npy'), allow_pickle=True)
    prod_emb = np.load(os.path.join(EMB, 'prod_emb.npy'), allow_pickle=True).astype(np.float32)
    log(f"  prod_emb: {prod_emb.shape}")

    # L2-normalize products (cosine = dot)
    pn = np.linalg.norm(prod_emb, axis=1, keepdims=True); pn[pn==0]=1; prod_emb /= pn

    log("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2', device='mps')

    log(f"Embedding {len(BROAD_LABELS)} broad labels...")
    broad_emb = model.encode(BROAD_LABELS, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
    log(f"  broad_emb: {broad_emb.shape}")

    log("Computing broad cosine similarities (matrix multiply)...")
    sim = prod_emb @ broad_emb.T  # (462646, ~110)
    log(f"  sim: {sim.shape}")

    log("Picking top-1 + top-3 broad labels per product...")
    top_idx = np.argsort(-sim, axis=1)[:, :3]  # top-3 indices per product
    top_scores = np.take_along_axis(sim, top_idx, axis=1)
    log(f"  done")

    # Group products by their top-1 broad label so we can do stage-2 in batches
    log("Grouping products by top-1 broad...")
    groups: dict[int, list[int]] = defaultdict(list)
    for i, idx in enumerate(top_idx[:, 0]):
        groups[int(idx)].append(i)

    # Stage 2: for each broad with sub-labels, do another matrix multiply on JUST that group
    log("Stage 2: sub-leaf classification per broad group...")
    sub_top = np.full(len(prod_ids), -1, dtype=np.int32)
    sub_score = np.zeros(len(prod_ids), dtype=np.float32)
    sub_label_str = ['' for _ in range(len(prod_ids))]

    for broad_i, idxs in groups.items():
        broad_label = BROAD_LABELS[broad_i]
        sub_labels = stage2_labels_for(broad_label)
        if not sub_labels:
            continue
        sub_emb = model.encode(sub_labels, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
        sub_sim = prod_emb[idxs] @ sub_emb.T
        sub_top_idx = np.argmax(sub_sim, axis=1)
        sub_top_score = np.max(sub_sim, axis=1)
        for k, gi in enumerate(idxs):
            sub_label_str[gi] = sub_labels[int(sub_top_idx[k])]
            sub_score[gi] = float(sub_top_score[k])
        log(f"  broad '{broad_label}' ({len(idxs):,} products) → {len(sub_labels)} sub-labels")

    # Load metadata for the output
    log("Loading product metadata...")
    con = sqlite3.connect(DB)
    by_fdc = {}; by_gtin = {}
    for r in con.execute("""
        SELECT gtin_upc, fdc_id, description, branded_food_category
        FROM products
    """):
        rec = {'gtin_upc': r[0] or '', 'fdc_id': str(r[1]) if r[1] else '',
               'description': r[2] or '', 'branded_food_category': r[3] or ''}
        if rec['fdc_id']:  by_fdc[rec['fdc_id']] = rec
        if rec['gtin_upc']: by_gtin[rec['gtin_upc']] = rec

    # Write output
    log("Writing audit/embed_classify.csv...")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['gtin_upc','fdc_id','product_description','branded_food_category',
                    'broad_label','broad_score','broad_top3',
                    'sub_label','sub_score','final_leaf'])
        for i, pid in enumerate(prod_ids):
            ps = str(pid)
            r = by_fdc.get(ps) or by_gtin.get(ps) or {}
            broad_label = BROAD_LABELS[int(top_idx[i,0])]
            broad_top3 = ' | '.join(f"{BROAD_LABELS[int(top_idx[i,k])]}:{top_scores[i,k]:.2f}" for k in range(3))
            sub = sub_label_str[i]
            sub_s = float(sub_score[i])
            final = f"{broad_label} > {sub}" if sub else broad_label
            w.writerow([r.get('gtin_upc',''), r.get('fdc_id',''),
                        r.get('description',''), r.get('branded_food_category',''),
                        broad_label, round(float(top_scores[i,0]),3), broad_top3,
                        sub, round(sub_s,3), final])

    log(f"DONE — {OUT}")

    # Summary
    cnt = Counter(BROAD_LABELS[int(i)] for i in top_idx[:,0])
    log("\n=== Broad-label distribution ===")
    for c, n in cnt.most_common(25):
        log(f"  {n:>8,}  {c}")

if __name__ == '__main__':
    main()
