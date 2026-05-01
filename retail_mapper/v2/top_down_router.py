#!/usr/bin/env python3
"""Top-down hierarchical router prototype.

Reads:
  taxonomy_paths_cleaned.csv  — 43,887 canonical paths, the full leaf vocabulary
  retail_leaf_v2_enriched_v2.csv — per-product evidence (title, BFC, ESHA, ingredients,
                                   distinctive tokens, modifier guesses, brand, ...)

For each product:
  1. Build evidence_text = lowercased blob of every signal we have for the product
     (title, BFC, ESHA desc, top ingredients, distinctive tokens, modifier guesses,
     product_form_guess, role_candidates).
  2. Walk the taxonomy tree top-down.  At each node, score each child by how many
     of its segment tokens (singularized, lowercase) appear in evidence_text.
     Apply identity gates (sparkling -> requires carbonated, plant-based -> rules out
     dairy unless evidence says otherwise, etc.).
  3. Descend into the highest-scoring child whose score clears a threshold.
     Stop when no child clears it.
  4. Output retail_leaf_topdown alongside the existing retail_leaf so we can diff.

This is a PROTOTYPE — runs on a configurable --limit and writes top_down_test.csv.
"""
from __future__ import annotations
import csv, sys, json, re, argparse, collections
csv.field_size_limit(sys.maxsize)

REPO   = "/Users/jamiebarton/Desktop/esha_audit_bundle"
TAXO   = f"{REPO}/retail_mapper/v2/taxonomy_clean.csv"
ENRICH = f"{REPO}/retail_mapper/v2/retail_leaf_v2_enriched_v2.csv"
OUT    = f"{REPO}/retail_mapper/v2/top_down_test.csv"

# --- 1. load taxonomy ---------------------------------------------------
def load_paths(path):
    """Returns (paths_by_super, supers). paths_by_super maps each supercat
    to a list of (full_path, [seg, seg, ...], [seg_tokens_set, ...])."""
    paths_by_super = collections.defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            p = (r.get("retail_leaf") or "").strip()
            if not p: continue
            segs = [s.strip() for s in p.split(" > ")]
            if not segs: continue
            sup = segs[0]
            child_segs = segs[1:]
            seg_toks = [seg_tokens(s) for s in child_segs]
            paths_by_super[sup].append((p, child_segs, seg_toks))
    return paths_by_super

# --- 2. tokenization & alias map ---------------------------------------
WORD_RE = re.compile(r"[a-z0-9]+")
def toks(s: str) -> set[str]:
    return set(WORD_RE.findall((s or "").lower()))

# common typos / variants we want to bridge
ALIASES = {
    "graperfruit": "grapefruit",
    "almondmilk":  "almond milk",
    "soymilk":     "soy milk",
    "oatmilk":     "oat milk",
    "ricemilk":    "rice milk",
    "coconutmilk": "coconut milk",
    "cashewmilk":  "cashew milk",
    "espressos":   "espresso",
    "drk":         "dark",
    "choc":        "chocolate",
    "chocolat":    "chocolate",
    "vanille":     "vanilla",
    "natl":        "natural",
}
def expand_aliases(text: str) -> str:
    t = text.lower()
    for k,v in ALIASES.items():
        if k in t:
            t = t + " " + v
    return t

def singularize(w: str) -> str:
    if len(w) > 3 and w.endswith("ies"): return w[:-3] + "y"
    if len(w) > 3 and w.endswith("es") and w[-3] in "sxz": return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"): return w[:-1]
    return w

def seg_tokens(seg: str) -> set[str]:
    """Tokens that must (mostly) be matched in evidence to descend into this segment."""
    out = set()
    for t in WORD_RE.findall(seg.lower()):
        if len(t) <= 2: continue                     # skip "a", "&", etc.
        if t in {"and","with","the","of"}: continue
        out.add(t); out.add(singularize(t))
    return out

# --- 3a. BFC → supercategory hardcoded map ------------------------------
# The bfc_modal_super column is computed from reconcile output and inherits
# its biases (apple-sauce products voted Produce because reconcile sent them
# there).  This map encodes the *intended* supercategory for each known BFC
# value. Products whose BFC isn't in the map fall back to majority-vote.
BFC_SUPER = {
    # Pantry
    "Candy": "Pantry",
    "Chocolate": "Pantry",
    "Cookies & Biscuits": "Pantry",
    "Biscuits/Cookies": "Pantry",
    "Biscuits/Cookies (Shelf Stable)": "Pantry",
    "Cereal": "Pantry",
    "Processed Cereal Products": "Pantry",
    "Pasta by Shape & Type": "Pantry",
    "Pasta/Noodles": "Pantry",
    "All Noodles": "Pantry",
    "Pasta Dinners": "Pantry",
    "Pickles, Olives, Peppers & Relishes": "Pantry",
    "Ketchup, Mustard, BBQ & Cheese Sauce": "Pantry",
    "Salad Dressing & Mayonnaise": "Pantry",
    "Vegetable & Cooking Oils": "Pantry",
    "Canned Vegetables": "Pantry",
    "Canned Fruit": "Pantry",
    "Canned & Bottled Beans": "Pantry",
    "Canned Tuna": "Pantry",
    "Canned Seafood": "Pantry",
    "Canned Meat": "Pantry",
    "Canned Soup": "Pantry",
    "Canned Condensed Soup": "Pantry",
    "Other Soups": "Pantry",
    "Prepared Soups": "Pantry",
    "Baking Decorations & Dessert Toppings": "Pantry",
    "Prepared Pasta & Pizza Sauces": "Pantry",
    "Oriental, Mexican & Ethnic Sauces": "Pantry",
    "Other Cooking Sauces": "Pantry",
    "Sauces/Spreads/Dips/Condiments": "Pantry",
    "Other Condiments": "Pantry",
    "Cake, Cookie & Cupcake Mixes": "Pantry",
    "Bread & Muffin Mixes": "Pantry",
    "Pizza Mixes & Other Dry Dinners": "Pantry",
    "Baking/Cooking Mixes/Supplies": "Pantry",
    "Baking Additives & Extracts": "Pantry",
    "Jam, Jelly & Fruit Spreads": "Pantry",
    "Tomatoes": "Pantry",
    "Nut & Seed Butters": "Pantry",
    "Herbs & Spices": "Pantry",
    "Seasoning Mixes, Salts, Marinades & Tenderizers": "Pantry",
    "Syrups & Molasses": "Pantry",
    "Honey": "Pantry",
    "Rice": "Pantry",
    "Flavored Rice Dishes": "Pantry",
    "Granulated, Brown & Powdered Sugar": "Pantry",
    "Mexican Dinner Mixes": "Pantry",
    "Flours & Corn Meal": "Pantry",
    "Chili & Stew": "Pantry",
    "Confectionery Products": "Pantry",
    "Gelatin, Gels, Pectins & Desserts": "Pantry",
    "Gravy Mix": "Pantry",
    "Pastry Shells & Fillings": "Pantry",
    "Vegetable and Lentil Mixes": "Pantry",
    "Other Grains & Seeds": "Pantry",
    "Stuffing": "Pantry",
    "Vegetables - Prepared/Processed": "Pantry",
    "Vegetables  Prepared/Processed": "Pantry",
    "Cooked & Prepared": "Pantry",
    "Fruit  Prepared/Processed": "Pantry",
    "Fruit - Prepared/Processed": "Pantry",
    "Grains/Flour": "Pantry",
    "Specialty Formula Supplements": "Pantry",
    "Dips & Salsa": "Pantry",
    "Vegetable Based Products / Meals": "Meal",
    "Dough Based Products / Meals": "Meal",
    # Snack
    "Popcorn, Peanuts, Seeds & Related Snacks": "Snack",
    "Chips, Pretzels & Snacks": "Snack",
    "Snack, Energy & Granola Bars": "Snack",
    "Other Snacks": "Snack",
    "Wholesome Snacks": "Snack",
    "Crackers & Biscotti": "Snack",
    "Flavored Snack Crackers": "Snack",
    "Chewing Gum & Mints": "Snack",
    "Snacks": "Snack",
    "Lunch Snacks & Combinations": "Snack",
    "Pre-Packaged Fruit & Vegetables": "Snack",
    # Bakery
    "Breads & Buns": "Bakery",
    "Bread": "Bakery",
    "Cakes, Cupcakes, Snack Cakes": "Bakery",
    "Croissants, Sweet Rolls, Muffins & Other Pastries": "Bakery",
    "Crusts & Dough": "Bakery",
    "Sweet Bakery Products": "Bakery",
    "Savoury Bakery Products": "Bakery",
    "Frozen Bread & Dough": "Bakery",
    "Frozen Pancakes, Waffles, French Toast & Crepes": "Bakery",
    # Beverage
    "Fruit & Vegetable Juice, Nectars & Fruit Drinks": "Beverage",
    "Soda": "Beverage",
    "Other Drinks": "Beverage",
    "Powdered Drinks": "Beverage",
    "Iced & Bottle Tea": "Beverage",
    "Tea Bags": "Beverage",
    "Coffee": "Beverage",
    "Energy, Protein & Muscle Recovery Drinks": "Beverage",
    "Plant Based Water": "Beverage",
    "Liquid Water Enhancer": "Beverage",
    "Sport Drinks": "Beverage",
    "Non Alcoholic Beverages  Ready to Drink": "Beverage",
    "Non Alcoholic Beverages - Ready to Drink": "Beverage",
    "Non Alcoholic Beverages Ready to Drink": "Beverage",
    "Water": "Beverage",
    "Plant Based Milk": "Beverage",
    "Milk": "Beverage",
    "Milk Additives": "Beverage",
    "Frozen Fruit & Fruit Juice Concentrates": "Beverage",
    "Alcohol": "Beverage",
    # Dairy
    "Cheese": "Dairy",
    "Cheese/Cheese Substitutes": "Dairy",
    "Yogurt": "Dairy",
    "Yogurt/Yogurt Substitutes": "Dairy",
    "Cream": "Dairy",
    "Butter & Spread": "Dairy",
    "Eggs & Egg Substitutes": "Dairy",
    "Puddings & Custards": "Dairy",
    # Frozen
    "Ice Cream & Frozen Yogurt": "Frozen",
    "Frozen Dinners & Entrees": "Frozen",
    "Frozen Appetizers & Hors D'oeuvres": "Frozen",
    "Frozen Vegetables": "Frozen",
    "Frozen Fish & Seafood": "Frozen",
    "Other Frozen Desserts": "Frozen",
    "Frozen Patties and Burgers": "Frozen",
    "Frozen Bacon, Sausages & Ribs": "Frozen",
    "Frozen Sausages, Hotdogs & Brats": "Frozen",
    "Frozen Poultry, Chicken & Turkey": "Frozen",
    "Vegetarian Frozen Meats": "Frozen",
    "Other Frozen Meats": "Frozen",
    "Frozen Prepared Sides": "Frozen",
    "Frozen Breakfast Sandwiches, Biscuits & Meals": "Frozen",
    "French Fries, Potatoes & Onion Rings": "Frozen",
    "Pizza": "Frozen",
    # Meat & Seafood
    "Pepperoni, Salami & Cold Cuts": "Meat & Seafood",
    "Sausages, Hotdogs & Brats": "Meat & Seafood",
    "Bacon, Sausages & Ribs": "Meat & Seafood",
    "Other Meats": "Meat & Seafood",
    "Other Deli": "Meat & Seafood",
    "Meat/Poultry/Other Animals  Prepared/Processed": "Meat & Seafood",
    "Meat/Poultry/Other Animals - Prepared/Processed": "Meat & Seafood",
    "Meat/Poultry/Other Animals  Unprepared/Unprocessed": "Meat & Seafood",
    "Meat/Poultry/Other Animals Sausages  Prepared/Processed": "Meat & Seafood",
    "Poultry, Chicken & Turkey": "Meat & Seafood",
    "Fish & Seafood": "Meat & Seafood",
    "Fish  Unprepared/Unprocessed": "Meat & Seafood",
    "Shellfish Unprepared/Unprocessed": "Meat & Seafood",
    "Sushi": "Meat & Seafood",
    # Meal
    "Entrees, Sides & Small Meals": "Meal",
    "Prepared Subs & Sandwiches": "Meal",
    "Prepared Wraps and Burittos": "Meal",
    "Sandwiches/Filled Rolls/Wraps": "Meal",
    "Ready-Made Combination Meals": "Meal",
    "Breakfast Sandwiches, Biscuits & Meals": "Meal",
    "Deli Salads": "Meal",
    # Other
    "Desserts/Dessert Sauces/Toppings": "Pantry",
}

# Title-level disqualifiers per supercategory.  If a candidate path's
# super is X but the title contains a disqualifier word, the path is
# rejected (it's a processed product, not raw produce, etc.).
SUPER_DISQUALIFY = {
    "Produce": ("sauce","applesauce","jelly","jam","juice","syrup","frozen",
                "freeze-dried","freeze dried","sweetened","dried","powder",
                "candied","crystallized","crispies","puff","puffs","chip",
                "chips","cracker","crackers","cookie","cookies","bar","bars",
                "snack","ice cream","yogurt","cheese","milk","beverage",
                "drink","soda","baked","fried","glazed","seasoned",
                "concentrate"),
}

# --- 3. identity gates --------------------------------------------------
GATES = {
    # segment_lc -> required_token_set (any-of), or callable(evidence_text) -> bool
    "sparkling":       lambda ev: any(w in ev for w in (" carbonate", " sparkl", " soda water"," seltzer")),
    "diet":            lambda ev: " diet" in ev or "zero sugar" in ev or "sugar free" in ev or "sugar-free" in ev,
    "plant-based milk": lambda ev: any(w in ev for w in (
        "plant", "almond", "soy", "oat", "rice", "coconut", "cashew", "hemp", "pea", "macadamia"
    )),
    "decaf":           lambda ev: "decaf" in ev,
    "non-dairy":       lambda ev: "non-dairy" in ev or "non dairy" in ev or "dairy free" in ev or "dairy-free" in ev or "plant" in ev,
    "organic":         lambda ev: "organic" in ev,
    "gluten free":     lambda ev: "gluten" in ev,
    "gluten-free":     lambda ev: "gluten" in ev,
    "kombucha":        lambda ev: "kombucha" in ev or "scoby" in ev or "fermented tea" in ev,
    "nog":             lambda ev: "nog" in ev or "eggnog" in ev,
    "kosher":          lambda ev: "kosher" in ev,
    "vegan":           lambda ev: "vegan" in ev,
    "smoked":          lambda ev: "smoke" in ev,
    "raw":             lambda ev: " raw " in ev or ev.startswith("raw"),
}
def gate_passes(seg_lc: str, ev: str) -> bool:
    g = GATES.get(seg_lc)
    if g is None: return True
    try: return bool(g(ev))
    except: return True

# --- 4. evidence builder ------------------------------------------------
PACKAGING = {"oz","ml","fl","ct","pk","pack","count","lb","g","kg","gal","gallon","quart"}
def build_evidence(row: dict) -> str:
    parts = [
        row.get("title",""),
        row.get("branded_food_category",""),
        row.get("current_esha_desc",""),
        row.get("ing_top5",""),
        row.get("distinctive_tokens","").replace("|"," "),
        row.get("distinctive_bigrams","").replace("|"," ").replace("_"," "),
        row.get("modifier_guesses","").replace("|"," "),
        row.get("product_form_guess",""),
        row.get("ing_categories","").replace("|"," "),
    ]
    return expand_aliases(" ".join(parts))

def extract_heads(row: dict) -> set[str]:
    """Pool of plausible head-noun tokens for the product.  Used as a
    GATE: a candidate path must contain at least one of these in some
    segment, otherwise it's the wrong sub-tree.

    Sources (most-trusted first):
      1. last token of product_form_guess (form parser's deduced noun)
      2. last non-packaging token of title (BEFORE first comma)
      3. last token of current_esha_desc minus comma-tail modifiers
    """
    out = set()
    pfg = (row.get("product_form_guess") or "").strip().lower()
    if pfg:
        words = [w for w in WORD_RE.findall(pfg) if w not in PACKAGING and not w.isdigit()]
        if words:
            out.add(singularize(words[-1]))
            out.add(words[-1])
    title = (row.get("title") or "").lower().split(",")[0]
    twords = [w for w in WORD_RE.findall(title) if w not in PACKAGING and not w.isdigit() and len(w) > 2]
    if twords:
        out.add(singularize(twords[-1]))
        out.add(twords[-1])
    esha = (row.get("current_esha_desc") or "").lower().split(",")[0]
    ewords = [w for w in WORD_RE.findall(esha) if w not in PACKAGING and not w.isdigit() and len(w) > 2]
    if ewords:
        out.add(singularize(ewords[-1]))
        out.add(ewords[-1])
    return {h for h in out if h}

# --- 5. router ----------------------------------------------------------
def pick_supercategory(supers: set[str], ev: str, row: dict) -> str | None:
    """Pick supercategory with this priority:
       1. BFC text → hardcoded super (most authoritative).
       2. Majority vote among (current pipeline, bfc_modal, fndds_modal).
       3. Current pipeline's choice."""
    bfc_text = (row.get("branded_food_category") or "").strip()
    if bfc_text in BFC_SUPER:
        s = BFC_SUPER[bfc_text]
        if s in supers: return s
    cur = (row.get("retail_leaf") or "").split(" > ")[0]
    bfc = (row.get("bfc_modal_super") or "").strip()
    fnd = (row.get("fndds_modal_super") or "").strip()
    votes = [v for v in (cur, bfc, fnd) if v in supers]
    if not votes: return None
    counts = collections.Counter(votes)
    top = counts.most_common(1)[0]
    if top[1] >= 2:
        return top[0]
    return cur if cur in supers else votes[0]

def super_passes_title_gate(super_name: str, title_lc: str) -> bool:
    bad = SUPER_DISQUALIFY.get(super_name)
    if not bad: return True
    return not any(w in title_lc for w in bad)

def score_path(child_segs: list[str], seg_toks: list[set[str]], ev_words: set[str], ev_text: str, heads: set[str]):
    """Score a single taxonomy path. Rejects if:
       - any segment fails its identity gate, OR
       - any segment has zero token-evidence, OR
       - HEAD-NOUN gate: heads is non-empty but NO path segment contains
         any of them (meaning the path is in the wrong sub-tree)."""
    total_hits = 0
    matched = 0
    head_seen = not heads     # if no heads available, gate auto-passes
    for seg, toks_ in zip(child_segs, seg_toks):
        if not gate_passes(seg.lower(), ev_text):
            return None
        if not toks_:
            return None
        h = sum(1 for t in toks_ if t in ev_words)
        if h == 0:
            return None
        if heads and (toks_ & heads):
            head_seen = True
        total_hits += h
        matched += 1
    if not head_seen:
        return None
    total_seg_toks = sum(len(t) for t in seg_toks)
    coverage = total_hits / max(1, total_seg_toks)
    score = total_hits + 0.5 * matched + 0.5 * coverage
    return (score, matched, coverage)

def route(paths_by_super, supers: set[str], ev_text: str, ev_words: set[str], row: dict):
    sup = pick_supercategory(supers, ev_text, row)
    if not sup: return "", []
    title_lc = (row.get("title") or "").lower()
    if not super_passes_title_gate(sup, title_lc):
        # fall back to current pipeline's super if it's different and gate-clean
        cur = (row.get("retail_leaf") or "").split(" > ")[0]
        if cur and cur != sup and cur in supers and super_passes_title_gate(cur, title_lc):
            sup = cur
    heads = extract_heads(row)
    # First pass: with head-noun gate.  If nothing passes, retry without.
    for use_heads in (heads, set()):
        candidates = []
        for full, child_segs, seg_toks in paths_by_super.get(sup, []):
            if not child_segs:
                candidates.append((0.0, 0, 0.0, len(full), full))
                continue
            s = score_path(child_segs, seg_toks, ev_words, ev_text, use_heads)
            if s is None: continue
            score, matched, coverage = s
            candidates.append((score, matched, coverage, len(full), full))
        if candidates:
            candidates.sort(key=lambda x: (-x[0], -x[1], -x[2], x[3]))
            best = candidates[0][4]
            return best, [(best, candidates[0][0])]
        if not heads:           # don't retry with empty heads if heads was empty
            break
    return sup, [(sup,"super-only")]

# --- 6. main ------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--filter-fdcs", default="")     # comma-sep
    ap.add_argument("--full", action="store_true",
                    help="route all rows and overwrite retail_leaf_v2.csv (router takes over)")
    a = ap.parse_args()

    print(f"loading taxonomy {TAXO}")
    paths_by_super = load_paths(TAXO)
    supers = set(paths_by_super.keys())
    total_paths = sum(len(v) for v in paths_by_super.values())
    print(f"  {total_paths:,} paths,  {len(supers):,} supercategories")

    if a.full:
        # Replace retail_leaf in retail_leaf_v2.csv with the router's pick.
        # This lets the existing enrich_output / enrich_v2 / quality_metrics
        # chain run unchanged for an apples-to-apples comparison.
        in_csv  = f"{REPO}/retail_mapper/v2/retail_leaf_v2.csv"
        out_csv = f"{REPO}/retail_mapper/v2/retail_leaf_v2.csv"   # overwrite in place
        bak     = f"{REPO}/retail_mapper/v2/retail_leaf_v2.reconcile.csv"
        # backup once if not already
        import os, shutil
        if not os.path.exists(bak):
            shutil.copy(in_csv, bak)
            print(f"  backed up reconcile output -> {bak}")
        # We need the enriched columns (BFC, modal supers, modifier_guesses).
        # Walk both files in parallel keyed by fdc_id.
        print(f"loading enriched signals from {ENRICH}")
        sig = {}
        with open(ENRICH) as f:
            for r in csv.DictReader(f):
                sig[r["fdc_id"]] = r
        print(f"  {len(sig):,} signal rows")
        print(f"reading {bak}")
        n_total = n_changed = n_super_changed = 0
        rows_out = []
        with open(bak) as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames
            for r in reader:
                signals = sig.get(r["fdc_id"]) or r
                ev = build_evidence(signals)
                ev_words = set(WORD_RE.findall(ev))
                ev_words |= {singularize(w) for w in ev_words}
                new_leaf, trace = route(paths_by_super, supers, ev, ev_words, signals)
                old_leaf = r.get("retail_leaf","")
                if not new_leaf:
                    new_leaf = old_leaf       # don't blank-out — fall back
                old_super = old_leaf.split(" > ")[0] if old_leaf else ""
                new_super = new_leaf.split(" > ")[0] if new_leaf else ""
                if new_leaf != old_leaf: n_changed += 1
                if old_super != new_super and old_super and new_super: n_super_changed += 1
                r["retail_leaf"] = new_leaf
                # rewrite confidence as nominal (router doesn't compute one yet)
                r["confidence"]  = "1.0" if new_leaf else "0.0"
                rows_out.append(r)
                n_total += 1
                if n_total % 50000 == 0:
                    print(f"  {n_total:>7}  changed={n_changed}  super_changed={n_super_changed}")
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows_out)
        print(f"\nwrote {out_csv}  ({n_total} rows)")
        print(f"  changed:        {n_changed:,}  ({100*n_changed/n_total:.1f}%)")
        print(f"  super-changed:  {n_super_changed:,}  ({100*n_super_changed/n_total:.1f}%)")
        return

    print(f"reading {ENRICH}")
    keep_fdcs = set([x.strip() for x in a.filter_fdcs.split(",") if x.strip()])
    rows_done = 0
    agree = 0
    deeper = 0     # router went deeper than current
    shallower = 0
    diff_super = 0
    out_rows = []
    with open(ENRICH) as f:
        for r in csv.DictReader(f):
            if keep_fdcs and r["fdc_id"] not in keep_fdcs: continue
            ev = build_evidence(r)
            ev_words = set(WORD_RE.findall(ev))
            # Add singular forms so plural-vs-singular matches.
            ev_words |= {singularize(w) for w in ev_words}
            new_leaf, trace = route(paths_by_super, supers, ev, ev_words, r)
            old_leaf = r.get("retail_leaf","")
            old_depth = old_leaf.count(" > ")+1 if old_leaf else 0
            new_depth = new_leaf.count(" > ")+1 if new_leaf else 0
            old_super = old_leaf.split(" > ")[0] if old_leaf else ""
            new_super = new_leaf.split(" > ")[0] if new_leaf else ""
            if old_leaf == new_leaf: agree += 1
            elif old_super != new_super: diff_super += 1
            elif new_depth > old_depth: deeper += 1
            else: shallower += 1
            out_rows.append({
                "fdc_id": r["fdc_id"],
                "title":  r["title"][:80],
                "old_leaf": old_leaf,
                "new_leaf": new_leaf,
                "trace":   " | ".join(f"{n}({s})" for n,s in trace),
                "ev_first": ev[:160],
            })
            rows_done += 1
            if rows_done >= a.limit and not keep_fdcs: break

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fdc_id","title","old_leaf","new_leaf","trace","ev_first"])
        w.writeheader()
        w.writerows(out_rows)

    total = len(out_rows) or 1
    print(f"\nrouted {total} products")
    print(f"  exact agree:  {agree:>6}  ({100*agree/total:.1f}%)")
    print(f"  router deeper: {deeper:>6}  ({100*deeper/total:.1f}%)")
    print(f"  router shallower: {shallower:>6}  ({100*shallower/total:.1f}%)")
    print(f"  different supercat: {diff_super:>6}  ({100*diff_super/total:.1f}%)")
    print(f"\nwrote {OUT}")

if __name__ == "__main__":
    main()
