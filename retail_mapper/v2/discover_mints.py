#!/usr/bin/env python3
"""Discover mint candidates from retail_leaf_v2_enriched_v2.csv.

Aggregates (form, modifier) tuples that have ≥3 evidence products and where
existing retail_leaf is scattered/generic. Outputs:

  _proposed_mints.csv         — proposal list for human review
  _retail_leaf_v2_lite.csv    — stripped-down version of the main output for review
"""
from __future__ import annotations
import csv, sys, collections, re, json
csv.field_size_limit(sys.maxsize)

REPO = "/Users/jamiebarton/Desktop/esha_audit_bundle"
RM   = f"{REPO}/retail_mapper/v2"
IN_CSV  = f"{RM}/retail_leaf_v2_enriched_v2.csv"
OUT_MINTS = f"{RM}/_proposed_mints.csv"
OUT_LITE  = f"{RM}/retail_leaf_v2_lite.csv"

# --- canonical form → path map (where in the tree this form belongs) ---
FORM_TO_PATH = {
    # dairy
    "milk":           ("Dairy", "Milk"),
    "yogurt":         ("Dairy", "Yogurt"),
    "cheese":         ("Dairy", "Cheese"),
    "butter":         ("Dairy", "Butter"),
    "cream":          ("Dairy", "Cream"),
    "creamer":        ("Dairy", "Cream", "Creamer"),
    "cottage cheese": ("Dairy", "Cheese", "Cottage"),
    "cream cheese":   ("Dairy", "Cream Cheese"),
    "sour cream":     ("Dairy", "Sour Cream"),
    "ice cream":      ("Frozen", "Ice Cream"),
    # plant-milk
    "almond milk":    ("Beverage", "Plant-based Milk", "Almond"),
    "oat milk":       ("Beverage", "Plant-based Milk", "Oat"),
    "soy milk":       ("Beverage", "Plant-based Milk", "Soy"),
    "coconut milk":   ("Beverage", "Plant-based Milk", "Coconut"),
    "almondmilk":     ("Beverage", "Plant-based Milk", "Almond"),
    "oatmilk":        ("Beverage", "Plant-based Milk", "Oat"),
    # snacks
    "cookie":         ("Snack", "Cookie"),
    "cracker":        ("Snack", "Cracker"),
    "chip":           ("Snack", "Chip"),
    "potato chip":    ("Snack", "Chip", "Potato"),
    "tortilla chip":  ("Snack", "Chip", "Tortilla"),
    "pretzel":        ("Snack", "Pretzel"),
    "popcorn":        ("Snack", "Popcorn"),
    "candy":          ("Snack", "Candy"),
    "chocolate":      ("Snack", "Chocolate"),
    "granola":        ("Snack", "Granola"),
    "bar":            ("Snack", "Bar"),
    "trail mix":      ("Snack", "Trail Mix"),
    "fruit snack":    ("Snack", "Fruit Snack"),
    # bakery
    "bread":          ("Pantry", "Bread"),
    "bun":            ("Pantry", "Bread", "Bun"),
    "roll":           ("Pantry", "Bread", "Roll"),
    "tortilla":       ("Pantry", "Bread", "Tortilla"),
    "muffin":         ("Bakery", "Muffin"),
    "english muffin": ("Bakery", "Muffin", "English"),
    "bagel":          ("Bakery", "Bagel"),
    "cake":           ("Bakery", "Cake"),
    "pie":            ("Bakery", "Pie"),
    "brownie":        ("Bakery", "Brownie"),
    "donut":          ("Bakery", "Donut"),
    "pastry":         ("Bakery", "Pastry"),
    "biscuit":        ("Bakery", "Biscuit"),
    # pantry/grocery
    "rice":           ("Pantry", "Rice"),
    "pasta":          ("Pantry", "Pasta"),
    "macaroni":       ("Pantry", "Pasta", "Macaroni"),
    "noodle":         ("Pantry", "Pasta", "Noodle"),
    "cereal":         ("Pantry", "Cereal"),
    "oatmeal":        ("Pantry", "Hot Cereal", "Oatmeal"),
    "flour":          ("Pantry", "Baking", "Flour"),
    "sugar":          ("Pantry", "Sweetener", "Sugar"),
    "honey":          ("Pantry", "Sweetener", "Honey"),
    "syrup":          ("Pantry", "Sweetener", "Syrup"),
    "salt":           ("Pantry", "Seasoning", "Salt"),
    "pepper":         ("Pantry", "Seasoning", "Pepper"),
    "spice":          ("Pantry", "Spice"),
    "seasoning":      ("Pantry", "Seasoning"),
    "oil":            ("Pantry", "Oil"),
    "olive oil":      ("Pantry", "Oil", "Olive"),
    "vinegar":        ("Pantry", "Vinegar"),
    # condiments / sauces
    "mayonnaise":     ("Pantry", "Condiment", "Mayonnaise"),
    "mayo":           ("Pantry", "Condiment", "Mayonnaise"),
    "aioli":          ("Pantry", "Condiment", "Aioli"),
    "ketchup":        ("Pantry", "Condiment", "Ketchup"),
    "mustard":        ("Pantry", "Condiment", "Mustard"),
    "bbq sauce":      ("Pantry", "Sauce", "BBQ"),
    "barbecue sauce": ("Pantry", "Sauce", "BBQ"),
    "hot sauce":      ("Pantry", "Sauce", "Hot Sauce"),
    "soy sauce":      ("Pantry", "Sauce", "Soy"),
    "sauce":          ("Pantry", "Sauce"),
    "salsa":          ("Pantry", "Salsa"),
    "hummus":         ("Pantry", "Hummus"),
    "dressing":       ("Pantry", "Salad Dressing"),
    "ranch dressing": ("Pantry", "Salad Dressing", "Ranch"),
    "spread":         ("Pantry", "Spread"),
    "jam":            ("Pantry", "Spread", "Jam"),
    "jelly":          ("Pantry", "Spread", "Jelly"),
    "peanut butter":  ("Pantry", "Spread", "Nut Butter", "Peanut"),
    "almond butter":  ("Pantry", "Spread", "Nut Butter", "Almond"),
    "nut butter":     ("Pantry", "Spread", "Nut Butter"),
    # canned/frozen/legumes
    "soup":           ("Pantry", "Soup"),
    "broth":          ("Pantry", "Broth"),
    "chili":          ("Pantry", "Chili"),
    "stew":           ("Pantry", "Stew"),
    "beans":          ("Pantry", "Legume", "Bean"),
    "bean":           ("Pantry", "Legume", "Bean"),
    "lentil":         ("Pantry", "Legume", "Lentil"),
    # beverages
    "juice":          ("Beverage", "Juice"),
    "soda":           ("Beverage", "Soda"),
    "cola":           ("Beverage", "Soda", "Cola"),
    "water":          ("Beverage", "Water"),
    "sparkling water":("Beverage", "Water", "Sparkling"),
    "tea":            ("Beverage", "Tea"),
    "coffee":         ("Beverage", "Coffee"),
    "smoothie":       ("Beverage", "Smoothie"),
    "shake":          ("Beverage", "Shake"),
    "protein powder": ("Beverage", "Protein Powder"),
    "hot cocoa":      ("Beverage", "Hot Cocoa"),
    "eggnog":         ("Beverage", "Eggnog"),
    "egg nog":        ("Beverage", "Eggnog"),
    "nog":            ("Beverage", "Eggnog"),
    # meat / seafood
    "beef":           ("Meat & Seafood", "Beef"),
    "pork":           ("Meat & Seafood", "Pork"),
    "chicken":        ("Meat & Seafood", "Chicken"),
    "turkey":         ("Meat & Seafood", "Turkey"),
    "ham":            ("Meat & Seafood", "Ham"),
    "bacon":          ("Meat & Seafood", "Bacon"),
    "sausage":        ("Meat & Seafood", "Sausage"),
    "hot dog":        ("Meat & Seafood", "Hot Dog"),
    "fish":           ("Meat & Seafood", "Fish"),
    "salmon":         ("Meat & Seafood", "Salmon"),
    "tuna":           ("Meat & Seafood", "Tuna"),
    "shrimp":         ("Meat & Seafood", "Shrimp"),
    "egg":            ("Dairy", "Egg"),
    # produce
    "apple":          ("Produce", "Fruit", "Apple"),
    "banana":         ("Produce", "Fruit", "Banana"),
    "berry":          ("Produce", "Fruit", "Berry"),
    "tomato":         ("Produce", "Vegetable", "Tomato"),
    "potato":         ("Produce", "Vegetable", "Potato"),
    "fruit":          ("Produce", "Fruit"),
    "vegetable":      ("Produce", "Vegetable"),
    # frozen
    "pizza":          ("Frozen", "Pizza"),
    "lasagna":        ("Frozen", "Lasagna"),
    "burrito":        ("Frozen", "Burrito"),
    "pot pie":        ("Frozen", "Pot Pie"),
    "casserole":      ("Frozen", "Casserole"),
    "egg roll":       ("Frozen", "Egg Roll"),
    "corn dog":       ("Frozen", "Corn Dog"),
    "chicken nugget": ("Frozen", "Chicken Nugget"),
    "fish stick":     ("Frozen", "Fish Stick"),
}

# multi-word base foods (longer first)
KNOWN_FORMS = sorted(FORM_TO_PATH.keys(), key=lambda x: -len(x))

# generic modifiers we deprioritize
GENERIC_MODIFIERS = {"original","plain","natural","premium","classic","real",
                     "regular","traditional","authentic","artisan","gourmet",
                     "fresh","new","best","quality","select","choice"}

# brand-noise tokens (already in axes/brand_noise.tsv but small set inline)
BRAND_TOKENS = {"silk","eggo","beyond","stouffer","callender","quaker","kellogg",
                "kraft","heinz","hormel","tyson","hidden","valley","kewpie","duke",
                "best","foods","bumble","star","kist"}

def clean_form(form_guess: str) -> str:
    """Pick the canonical base form from a noisy product_form_guess string."""
    f = (form_guess or '').lower().strip()
    if not f: return ''
    # try to find a known form (longest match) inside f
    for known in KNOWN_FORMS:
        if known in f.split() or known == f:
            return known
        if known in f:
            return known
    # fallback: take last word
    parts = f.split()
    return parts[-1] if parts else ''

def clean_modifier(mod: str, form: str) -> str:
    """Strip form-overlap, brand-tokens, packaging-noise from a modifier."""
    if not mod: return ''
    m = mod.lower().strip()
    # remove the form word from the modifier
    if form:
        m = re.sub(r"\b" + re.escape(form) + r"\b", "", m).strip()
        # also remove substrings of multi-word forms
        for w in form.split():
            m = re.sub(r"\b" + re.escape(w) + r"\b", "", m).strip()
    # drop brand tokens
    toks = [t for t in m.split() if t not in BRAND_TOKENS]
    # drop pure-numeric / packaging
    toks = [t for t in toks if not re.match(r'^\d+(\.\d+)?[a-z]*$', t)]
    return " ".join(toks).strip()

def propose_leaf(form: str, modifier: str, modal_super: str) -> str:
    """Build the canonical leaf path."""
    base = FORM_TO_PATH.get(form)
    parts = list(base) if base else []
    if not parts:
        # use modal supercategory + form
        parts = [modal_super or "Other", form.title()]
    # append modifier (title-case)
    if modifier:
        parts.append(modifier.title())
    return " > ".join(p for p in parts if p)

def canonical_name(form: str, modifier: str) -> str:
    """Recipe-friendly name."""
    parts = []
    if modifier: parts.append(modifier.title())
    if form:     parts.append(form.title())
    return " ".join(parts).strip()

# -------- main --------
print("reading enriched data...")
import time; t0 = time.time()

# (form, modifier) → list of (fdc_id, title, retail_leaf, super)
groups = collections.defaultdict(list)
n_total = 0

# also build the lite version
LITE_COLS = ['fdc_id','gtin_upc','title','branded_food_category',
             'current_esha','current_esha_desc',
             'retail_leaf','confidence','gap_flag',
             'product_form_guess','modifier_guesses','ingredient_guesses',
             'ing_top5','brand_owner']
lite_out = open(OUT_LITE, 'w', newline='')
lite_w = csv.DictWriter(lite_out, fieldnames=LITE_COLS)
lite_w.writeheader()

with open(IN_CSV) as f:
    for r in csv.DictReader(f):
        n_total += 1
        # write lite row
        lite_w.writerow({k: r.get(k, '') for k in LITE_COLS})
        # bucket for mint discovery
        form_raw = r.get('product_form_guess', '').strip().lower()
        mods_raw = r.get('modifier_guesses', '') or ''
        if not form_raw or not mods_raw: continue
        form = clean_form(form_raw)
        if not form: continue
        leaf = r.get('retail_leaf', '')
        sup = leaf.split(' > ')[0] if ' > ' in leaf else leaf
        for m in [x.strip() for x in mods_raw.split('|') if x.strip()][:5]:
            mod = clean_modifier(m, form)
            if not mod or mod == form: continue
            # filter: skip pure generics if there are other modifiers; keep them otherwise
            key = (form, mod)
            groups[key].append((r['fdc_id'], r['title'][:60], leaf, sup))

lite_out.close()
print(f"  {n_total:,} products  ({time.time()-t0:.1f}s)")

# build proposals
print("\nbuilding proposals...")
proposals = []
for (form, mod), evidence in groups.items():
    if len(evidence) < 3: continue
    # modal supercategory
    supers = collections.Counter(e[3] for e in evidence)
    modal_super = supers.most_common(1)[0][0] if supers else ''
    # existing leaf scatter
    existing = collections.Counter(e[2] for e in evidence)
    proposed = propose_leaf(form, mod, modal_super)
    # is the proposed leaf already represented?
    already_there = (proposed in existing) and existing[proposed] >= len(evidence) * 0.8
    if already_there: continue
    # skip pure-generic modifier when it'd produce a tail like ">Original" with no other modifiers
    if mod in GENERIC_MODIFIERS:
        # only keep if there's strong evidence and existing leaves are scattered
        if len(existing) < 3: continue
    proposals.append({
        "proposed_leaf":       proposed,
        "canonical_name":      canonical_name(form, mod),
        "form":                form,
        "modifier":            mod,
        "modal_super":         modal_super,
        "evidence_count":      len(evidence),
        "unique_existing_leaves": len(existing),
        "top_existing_leaves": " ;; ".join(f"{k} (n={c})" for k, c in existing.most_common(3)),
        "sample_titles":       " ;; ".join(t[:55] for _, t, _, _ in evidence[:5]),
        "review_status":       "",
    })

# rank by evidence count
proposals.sort(key=lambda p: -p['evidence_count'])
print(f"  {len(proposals):,} mint candidates after de-junking")

with open(OUT_MINTS, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(proposals[0].keys()))
    w.writeheader()
    w.writerows(proposals)
print(f"  wrote {OUT_MINTS}")

# print top 30 to terminal
print("\n=== TOP 30 MINT CANDIDATES (by evidence count) ===\n")
for p in proposals[:30]:
    print(f"  [{p['evidence_count']:>4}]  {p['proposed_leaf']}")
    print(f"          form={p['form']!r}  modifier={p['modifier']!r}  modal_super={p['modal_super']!r}")
    print(f"          unique_existing_leaves={p['unique_existing_leaves']}  top: {p['top_existing_leaves'][:90]}")
    print(f"          sample: {p['sample_titles'][:90]}")
    print()

print(f"\nfile sizes:")
import os
for path in [OUT_LITE, OUT_MINTS]:
    sz = os.path.getsize(path)
    print(f"  {path}  {sz/1e6:.1f} MB")
