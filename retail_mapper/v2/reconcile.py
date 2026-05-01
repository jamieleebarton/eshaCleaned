#!/usr/bin/env python3
"""Stage C — reconcile multi-signal candidates into one retail_leaf per product.

Reads .cache/candidates.parquet (built by candidate_generator.py), runs a
weighted vote with identity guards, emits retail_leaf_v2.csv.

Signals (weights from PLAN.md):
  B1 title-parser leaf            2.0
  B6 embedding kNN top-1 ESHA     1.0  (uses agreement of top-3)
  B7 funnel sub_leaf (if !other)  0.8
  B8 ingredient FNDDS top-1       1.2
  B3 NER head-span match          1.5  (when NER spans contain a category-tsv head)
  B2 head-locked re-parse hint    2.0  (boost when head_phrase contains a category-tsv head)
  B4/B5 zero-shot                 1.5  (only if zs_super_score >= 0.4)

Identity guards:
  - BFC (branded_food_category) compatibility check vs leaf modal BFC (downweight 0.5x on mismatch)
  - low-confidence floor: rows where no leaf clears 1.5 weighted points → 'unmapped' (mintable)

Output: retail_leaf_v2.csv with columns
  fdc_id, gtin_upc, title, branded_food_category,
  current_esha, current_esha_desc,
  retail_leaf, confidence, sources_agreed,
  provenance, gap_flag, mint_candidate
"""
from __future__ import annotations
import argparse, csv, json, os, re, sys, time
from pathlib import Path
from collections import Counter, defaultdict

REPO = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
RM   = REPO / "retail_mapper"
V2   = RM / "v2"
CACHE = V2 / ".cache"
IN_PARQUET = CACHE / "candidates.parquet"
OUT_CSV    = V2 / "retail_leaf_v2.csv"

# Apple/grape varieties — these should NOT be treated as separate ingredients
# or combo components. They're cultivar tags on the parent food.
VARIETIES = {
    # apples
    "honey crisp": "Apple", "honeycrisp": "Apple", "pink lady": "Apple",
    "granny smith": "Apple", "ginger gold": "Apple", "fuji": "Apple",
    "gala": "Apple", "red delicious": "Apple", "golden delicious": "Apple",
    "braeburn": "Apple", "mcintosh": "Apple", "ambrosia": "Apple",
    "envy": "Apple", "jazz": "Apple", "cosmic crisp": "Apple",
    # grapes
    "concord": "Grape", "thompson seedless": "Grape", "red globe": "Grape",
    # cheeses (variety locks supercategory=Dairy>Cheese)
    # we leave most cheese types in flavor.tsv since they ARE the leaf
}

def has_variety(text: str) -> tuple[str, str]:
    t = (text or "").lower()
    for v, parent in VARIETIES.items():
        if v in t: return (v, parent)
    return ("", "")

_PACKAGING_TOKENS = {
    "oz","ml","ct","pk","kg","lb","lbs","g","l","fl",
    "pouch","pouches","case","jar","can","bag","box","tray",
    "carton","sleeve","container","cup","stick","bottle","tub","tube",
}

def _strip_packaging_tail(seg: str) -> str:
    """If the segment is mostly numbers + packaging unit, drop it."""
    s = seg.strip()
    sl = s.lower()
    if any(p == sl or sl.endswith(" "+p) or sl.startswith(p+" ") for p in _PACKAGING_TOKENS):
        return ""
    # numeric-with-unit like '32oz', '6/32oz', '1pk'
    import re as _re
    if _re.fullmatch(r"\d+(\.\d+)?\s*[/x×]?\s*\d*\.?\d*\s*[a-z]{1,5}", sl): return ""
    return s

def carry_b1_tail(target_leaf: str, b1_leaf: str) -> str:
    """When b1 had a wrong supercategory but a useful flavor/modifier tail
    (e.g. 'Produce > Fruit > Fig > Cake' or 'Snack > Candy > Fudge > Brownie'),
    append the distinctive tail tokens to the target_leaf so the flavor
    survives. Skip tokens that already appear in target_leaf."""
    if not target_leaf or not b1_leaf or " > " not in b1_leaf:
        return target_leaf
    target_segs = [s.strip() for s in target_leaf.split(" > ")]
    target_lc = {s.lower() for s in target_segs}
    b1_segs = [s.strip() for s in b1_leaf.split(" > ")]
    GENERIC = {"snack","produce","pantry","dairy","beverage","frozen","meal","meat","seafood",
               "fruit","vegetable","candy","combo","packs","dipper","composite","dishes",
               "composite dishes","combo packs","sub leaves","sub leaf",
               "nuts","seeds","cake","bread","spreads","spread","sweetener","sweeteners",
               "condiment","condiments","poultry","seafood","grain","legume","legumes"}
    extra = []
    for s in b1_segs:
        sl = s.lower()
        if sl in target_lc or sl in GENERIC: continue
        # skip multi-word combo tokens like "Cake Cupcakes + Frosting + Sprinkles"
        if "+" in s: continue
        # skip segments that start with "composite dishes" prefix
        if sl.startswith("composite dishes"): continue
        if sl.startswith("combo packs"):      continue
        extra.append(s)
    if not extra:
        return target_leaf
    # also: filter the FINAL appended tail for the same generic prefixes
    cleaned_extras = [e for e in extra[:2]
                      if not e.lower().startswith(("composite dishes", "combo packs"))]
    if not cleaned_extras: return target_leaf
    return target_leaf + " > " + " ".join(cleaned_extras)

def canonicalize_leaf(leaf: str, title_lc: str = "") -> str:
    """Final tidy-up applied to every retail_leaf:
       - strip raw refs (FNDDS:/ESHA:/FUNNEL:) — they shouldn't reach this far,
         but if they do, we replace with 'Other'.
       - resolve pipe-separated segments by picking the option whose tokens
         appear in `title_lc` (or the first option if context is empty).
       - drop adjacent duplicate segments.
       - drop trailing packaging tokens.
       - singularize rightmost segment for common plurals.
    """
    if not leaf: return leaf
    # strip stray internal-vote prefixes
    if leaf.startswith("B9:"):
        leaf = leaf[3:].strip()
    # raw-ref escape
    if leaf.startswith(("FNDDS:","ESHA:","FUNNEL:")):
        # try to grab the desc word: 'ESHA:14480|Almond Milk, plain' -> 'Almond Milk'
        ref = leaf.split("|", 1)[-1] if "|" in leaf else leaf
        return f"Other > Reference > {ref[:40]}"

    if " > " not in leaf:
        return leaf
    segs = [s.strip() for s in leaf.split(" > ") if s.strip()]

    # resolve pipes per segment using title context
    resolved = []
    for s in segs:
        if "|" in s:
            opts = [o.strip() for o in s.split("|") if o.strip()]
            if not opts: continue
            best, bs = opts[0], -1
            for opt in opts:
                sc = sum(1 for t in opt.lower().replace("-"," ").split() if t in title_lc)
                if sc > bs: best, bs = opt, sc
            resolved.append(best)
        else:
            resolved.append(s)

    # drop packaging tails
    while resolved:
        cleaned = _strip_packaging_tail(resolved[-1])
        if cleaned == resolved[-1]: break
        if cleaned: resolved[-1] = cleaned; break
        resolved.pop()

    # strip "Composite Dishes <X>" prefix that leaked from b1 carry-tail
    cleaned = []
    for s in resolved:
        sl = s.lower()
        if sl.startswith("composite dishes "):
            s = s[len("composite dishes "):].strip()
        if sl.startswith("combo packs "):
            s = s[len("combo packs "):].strip()
        if s: cleaned.append(s)
    resolved = cleaned

    # drop adjacent duplicates
    dedup = []
    for s in resolved:
        if dedup and dedup[-1].lower() == s.lower(): continue
        dedup.append(s)

    # singularize rightmost
    if dedup:
        last = dedup[-1]
        ll = last.lower()
        if ll.endswith("ies") and len(last) > 4:
            dedup[-1] = last[:-3] + "y"
        elif ll == "apples":
            dedup[-1] = "Apple"
        elif ll == "berries":
            dedup[-1] = "Berry"
        elif ll.endswith("s") and len(last) > 3 and not ll.endswith(("us","ss","ous","ess","ies")):
            dedup[-1] = last[:-1]

    # dedup AGAIN after singularize — singularization can create adjacent
    # duplicates ("Bakery > Muffin > Muffins" → "Bakery > Muffin > Muffin").
    final = []
    for s in dedup:
        if final and final[-1].lower() == s.lower(): continue
        final.append(s)

    return " > ".join(final)

# load axes vocab once
def load_axes():
    cat_heads = {}    # token -> (super, group)
    with open(RM / "axes" / "category.tsv") as f:
        for line in f:
            if line.startswith("#") or not line.strip(): continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                tok, sup, grp = parts[0].strip(), parts[1].strip(), parts[2].strip()
                cat_heads[tok] = (sup, grp)
    forms = set()
    with open(RM / "axes" / "form.tsv") as f:
        for line in f:
            if line.startswith("#") or not line.strip(): continue
            forms.add(line.split("\t")[0].strip())
    return cat_heads, forms

def _resolve_pipe(option_str: str, context: str) -> str:
    """Resolve a pipe-separated category.tsv field by picking the option whose
    tokens appear in the context. Falls back to the first option."""
    if "|" not in option_str: return option_str
    options = [o.strip() for o in option_str.split("|") if o.strip()]
    if not options: return option_str
    ctx = (context or "").lower()
    # Score each option by how many of its lowercased tokens appear in ctx
    best = options[0]; best_score = -1
    for opt in options:
        sc = sum(1 for t in opt.lower().replace("-"," ").split() if t in ctx)
        if sc > best_score:
            best_score = sc; best = opt
    return best

def category_for_phrase(phrase: str, cat_heads: dict, context: str = "") -> tuple[str, str, str]:
    """Find the rightmost token in `phrase` that matches a category-tsv head.
       Returns (token, super, group). When category.tsv uses | for context-
       dependent tokens (e.g. rice → Beverage|Pantry, Plant-based Milk|Grain),
       resolve super and group AS A PAIR (same index), so we don't get
       'Beverage > Grain' nonsense. Score each (super, group) pair by
       how many of its tokens appear in context."""
    if not phrase: return ("","","")
    if not context: context = phrase
    tokens = phrase.lower().split()
    for tok in reversed(tokens):
        if tok in cat_heads:
            sup_raw, grp_raw = cat_heads[tok]
            sup_opts = [s.strip() for s in sup_raw.split("|")] if "|" in sup_raw else [sup_raw]
            grp_opts = [s.strip() for s in grp_raw.split("|")] if "|" in grp_raw else [grp_raw]
            # pad shorter list to match
            while len(grp_opts) < len(sup_opts): grp_opts.append(grp_opts[-1])
            while len(sup_opts) < len(grp_opts): sup_opts.append(sup_opts[-1])
            ctx = context.lower()
            best_idx, best_score = 0, -1
            for i, (s, g) in enumerate(zip(sup_opts, grp_opts)):
                # score: sum of group tokens (which actually appear in titles)
                # plus a smaller bonus for super tokens
                grp_tokens = g.lower().replace("-", " ").split()
                sup_tokens = s.lower().split()
                sc = sum(1 for t in grp_tokens if t in ctx and len(t) >= 3)
                sc += 0.3 * sum(1 for t in sup_tokens if t in ctx and len(t) >= 3)
                if sc > best_score:
                    best_score = sc; best_idx = i
            return (tok, sup_opts[best_idx], grp_opts[best_idx])
    return ("","","")

# BFC → supercategory hint (rough, additive). Hand-curated rough mapping —
# we use it to upweight any leaf whose first segment matches.
BFC_HINTS = {
    # SANDWICHES / DELI / PIZZA / FROZEN MEALS
    "prepared subs & sandwiches":      ("Meal > Sandwich", 1.7),
    "subs & sandwiches":               ("Meal > Sandwich", 1.7),
    "sandwiches & wraps":              ("Meal > Sandwich", 1.6),
    "wraps":                           ("Meal > Sandwich > Wrap", 1.6),
    "burritos & enchiladas":           ("Meal > Burrito", 1.6),
    "tacos":                           ("Meal > Taco", 1.6),
    "pizza":                           ("Meal > Pizza", 1.6),
    "frozen pizza":                    ("Frozen > Pizza", 1.7),
    "frozen dinners & entrees":        ("Frozen > Entree", 1.5),
    "frozen entrees":                  ("Frozen > Entree", 1.5),
    "frozen appetizers & hors d'oeuvres": ("Frozen > Appetizer", 1.5),
    "frozen breakfast":                ("Frozen > Breakfast", 1.5),
    "tv dinners":                      ("Frozen > Entree > TV Dinner", 1.5),
    "pepperoni, salami & cold cuts":   ("Meat & Seafood > Deli > Cold Cut", 1.5),
    "other deli":                      ("Meat & Seafood > Deli", 1.3),
    "sausages, hotdogs & brats":       ("Meat & Seafood > Sausage", 1.5),
    "bacon":                           ("Meat & Seafood > Bacon", 1.7),
    "fresh meat":                      ("Meat & Seafood > Meat", 1.4),
    "fresh seafood":                   ("Meat & Seafood > Seafood", 1.5),
    # SNACKS / SWEETS / BAKED GOODS
    "popcorn, peanuts, seeds & related snacks": ("Snack", 1.3),
    "snack, energy & granola bars":    ("Snack > Bar", 1.5),
    "energy, protein & muscle recovery drinks": ("Beverage > Functional", 1.5),
    "energy, protein bars & cookies":  ("Snack > Bar", 1.4),
    "other snacks":                    ("Snack", 1.0),
    "wholesome snacks":                ("Snack", 1.0),
    "cakes, cupcakes, snack cakes":    ("Bakery > Cake", 1.5),
    "croissants, sweet rolls, muffins & other pastries": ("Bakery > Pastry", 1.5),
    "biscuits/cookies":                ("Snack > Cookie", 1.5),
    "biscuits & cookies":              ("Snack > Cookie", 1.5),
    "cake, cookie & cupcake mixes":    ("Pantry > Baking > Mix", 1.5),
    "baking decorations & dessert toppings": ("Pantry > Baking > Topping", 1.4),
    # CONDIMENTS / SAUCES / DIPS
    "pickles, olives, peppers & relishes": ("Pantry > Pickled", 1.4),
    "dips & salsa":                    ("Pantry > Dip", 1.5),
    "prepared pasta & pizza sauces":   ("Pantry > Pasta Sauce", 1.5),
    "oriental, mexican & ethnic sauces": ("Pantry > Sauce", 1.4),
    "other cooking sauces":            ("Pantry > Sauce", 1.3),
    "marinades":                       ("Pantry > Marinade", 1.5),
    # Multi-condiment USDA shelf labels — must be present so they outrank the
    # bare "cheese" / "mustard" single-word fallbacks below
    "ketchup, mustard, bbq & cheese sauce": ("Pantry > Condiment", 1.6),
    "ketchup":                         ("Pantry > Condiment > Ketchup", 1.5),
    "mustard":                         ("Pantry > Condiment > Mustard", 1.5),
    "bbq sauce":                       ("Pantry > Condiment > BBQ Sauce", 1.5),
    "barbecue sauce":                  ("Pantry > Condiment > BBQ Sauce", 1.5),
    "hot sauce":                       ("Pantry > Condiment > Hot Sauce", 1.5),
    "soy sauce":                       ("Pantry > Sauce > Soy Sauce", 1.5),
    "teriyaki sauce":                  ("Pantry > Sauce > Teriyaki", 1.5),
    "salsa":                           ("Pantry > Salsa", 1.5),
    "guacamole":                       ("Produce > Vegetable > Avocado > Guacamole", 1.5),
    "hummus":                          ("Pantry > Hummus", 1.6),
    "peanut sauce":                    ("Pantry > Sauce > Peanut", 1.6),
    "peanut butter":                   ("Pantry > Spreads > Nut Butter > Peanut", 1.6),
    "vinegar":                         ("Pantry > Vinegar", 1.5),
    "vegetable & cooking oils":        ("Pantry > Oil", 1.6),
    "olive oils":                      ("Pantry > Oil > Olive", 1.6),
    "nut & seed butters":              ("Pantry > Spreads > Nut Butter", 1.6),
    "butter & spread":                 ("Dairy > Butter", 1.5),
    "jams, jellies & fruit spreads":   ("Pantry > Spreads > Jam", 1.5),
    "gelatin, gels, pectins & desserts": ("Pantry > Baking > Gelatin & Pectin", 1.5),
    "pectins":                         ("Pantry > Baking > Pectin", 1.5),
    "pectin":                          ("Pantry > Baking > Pectin", 1.5),
    "gelatin":                         ("Pantry > Baking > Gelatin", 1.5),
    # PANTRY / GROCERY
    "canned & bottled beans":          ("Pantry > Legumes", 1.5),
    "vegetable and lentil mixes":      ("Pantry > Legumes", 1.4),
    "tomatoes":                        ("Produce > Vegetable > Tomato", 1.4),
    "canned tomatoes":                 ("Pantry > Canned > Tomato", 1.5),
    "canned vegetables":               ("Pantry > Canned > Vegetable", 1.5),
    "canned fruit":                    ("Pantry > Canned > Fruit", 1.5),
    "dried fruit":                     ("Snack > Dried Fruit", 1.5),
    "herbs & spices":                  ("Pantry > Spice", 1.5),
    "salt, pepper, salt substitutes":  ("Pantry > Seasoning", 1.5),
    "granulated, brown & powdered sugar": ("Pantry > Sweetener > Sugar", 1.5),
    "flour":                           ("Pantry > Baking > Flour", 1.5),
    "baking products":                 ("Pantry > Baking", 1.3),
    "rice & grains":                   ("Pantry > Rice", 1.4),
    "pasta":                           ("Pantry > Pasta", 1.5),
    # BEVERAGES
    "water":                           ("Beverage > Water", 1.5),
    "sparkling waters":                ("Beverage > Water > Sparkling", 1.5),
    "flavored waters":                 ("Beverage > Water > Flavored", 1.5),
    "sports drinks":                   ("Beverage > Sports", 1.5),
    "iced tea":                        ("Beverage > Tea > Iced", 1.5),
    "tea bags":                        ("Beverage > Tea", 1.5),
    "ground coffee":                   ("Beverage > Coffee", 1.5),
    "coffee pods":                     ("Beverage > Coffee > Pod", 1.5),
    "ready-to-drink coffee":           ("Beverage > Coffee > RTD", 1.5),
    # BREAKFAST
    "ready-to-eat cereals":            ("Pantry > Breakfast Cereal", 1.5),
    "hot cereals":                     ("Pantry > Hot Cereal", 1.5),
    "oatmeal":                         ("Pantry > Hot Cereal > Oatmeal", 1.5),
    # MISC
    "plant based milk":               ("Beverage > Plant-based Milk", 1.5),
    "milk":                            ("Dairy > Milk", 1.2),
    "yogurt":                          ("Dairy > Yogurt", 1.5),
    "cheese":                          ("Dairy > Cheese", 1.5),
    "ice cream":                       ("Frozen > Ice Cream", 1.5),
    "frozen desserts":                 ("Frozen > Ice Cream", 1.2),
    "salad dressing & mayonnaise":     ("Pantry > Condiment", 1.4),
    "dressings & toppings":            ("Pantry > Condiment", 1.2),
    "honey":                           ("Pantry > Sweetener > Honey", 1.5),
    "syrups & molasses":               ("Pantry > Sweetener > Syrup", 1.5),
    "syrup":                           ("Pantry > Sweetener > Syrup", 1.5),
    "molasses":                        ("Pantry > Sweetener > Molasses", 1.5),
    "vegetables  prepared/processed":  ("Pantry", 1.2),    # baked beans, etc.
    "vegetables - prepared/processed": ("Pantry", 1.2),
    "beans, peas & lentils":           ("Pantry > Legumes", 1.5),
    "non alcoholic beverages":         ("Beverage", 1.2),
    "non alcoholic beverages - ready to drink": ("Beverage", 1.2),
    "other drinks":                    ("Beverage", 0.8),
    "candy":                           ("Snack > Candy", 1.4),
    "chocolate":                       ("Snack > Candy > Chocolate", 1.5),
    "cookies & biscuits":              ("Snack > Cookies", 1.5),
    "crackers & biscotti":             ("Snack > Crackers", 1.5),
    "chips, pretzels & snacks":        ("Snack", 1.2),
    "pre-packaged fruit & vegetables": ("Produce", 1.3),
    "fruit":                           ("Produce > Fruit", 1.5),
    "vegetables":                      ("Produce > Vegetable", 1.5),
    "meats":                           ("Meat & Seafood", 1.3),
    "seafood":                         ("Meat & Seafood > Seafood", 1.4),
    "poultry":                         ("Meat & Seafood > Poultry", 1.4),
    "frozen entrees":                  ("Frozen > Entree", 1.2),
    "frozen pizza":                    ("Frozen > Pizza", 1.5),
    "soup":                            ("Pantry > Soup", 1.5),
    "soups":                           ("Pantry > Soup", 1.5),
    "pasta by shape & type":           ("Pantry > Pasta", 1.5),
    "rice":                            ("Pantry > Rice", 1.5),
    "bread":                           ("Pantry > Bread", 1.5),
    "cereal":                          ("Pantry > Breakfast Cereal", 1.5),
    "cereals":                         ("Pantry > Breakfast Cereal", 1.5),
    "spices, seasonings, sauces":      ("Pantry > Spice", 1.2),
    "seasoning mixes, salts, marina":  ("Pantry > Seasoning", 1.3),
    "powdered drinks":                 ("Beverage > Mix", 1.2),
    "soda":                            ("Beverage > Soda", 1.5),
    "coffee":                          ("Beverage > Coffee", 1.5),
    "tea":                             ("Beverage > Tea", 1.5),
    "fruit & vegetable juice":         ("Beverage > Juice", 1.4),
    "energy, sports & nutritional drinks": ("Beverage > Functional", 1.3),
    "wine":                            ("Beverage > Alcoholic > Wine", 1.5),
    "beer":                            ("Beverage > Alcoholic > Beer", 1.5),
    "spirits / liquor":                ("Beverage > Alcoholic", 1.4),
}

def bfc_hint(bfc: str) -> tuple[str, float]:
    if not bfc: return ("", 0.0)
    b = bfc.lower().strip()
    if b in BFC_HINTS: return BFC_HINTS[b]
    # partial: longest substring match
    best = ("", 0.0); best_len = 0
    for key, val in BFC_HINTS.items():
        if key in b and len(key) > best_len:
            best = val; best_len = len(key)
    return best

def vote(c: dict, cat_heads: dict, forms: set) -> dict:
    """Run weighted vote on one product's candidates."""
    votes: dict[str, float] = defaultdict(float)
    provenance: dict[str, dict] = {}

    title = (c["title"] or "").lower()
    bfc   = (c.get("branded_food_category") or "").lower()

    # B-1 — current_esha_desc anchor.
    # The audit already curated an ESHA description per fdc_id (e.g.
    # "Applesauce", "Almond Milk, plain", "Eggnog, regular"). When the
    # description contains a category-tsv head, treat that as a strong
    # anchor — it forces consistency across all retail products that share
    # the same ESHA code.
    cur_desc = (c.get("current_esha_desc") or "").lower()
    cur_anchor_leaf = ""
    if cur_desc:
        cur_tok = cur_super = cur_grp = ""
        ctx = title + " " + cur_desc
        # ESHA descriptions follow "HEAD, modifier, modifier" — so prefer a
        # cat_heads match in the FIRST comma-segment of cur_desc.  Only fall
        # back to the broader scan when no head is in segment 1.
        first_seg = cur_desc.split(",")[0].strip()
        # Use category_for_phrase (which does paired pipe-resolution) to
        # ensure super and group come from the same index, not independent.
        if first_seg:
            t, s, g = category_for_phrase(first_seg, cat_heads, context=ctx)
            if t and len(t) > len(cur_tok):
                cur_tok, cur_super, cur_grp = t, s, g
        if not cur_super:
            t, s, g = category_for_phrase(cur_desc, cat_heads, context=ctx)
            if t:
                cur_tok, cur_super, cur_grp = t, s, g
        # also check for compound terms in cur_desc — iterate the FULL
        # compound_anchors keys so additions to the dict actually take effect.
        compound_anchors = {
                    "applesauce":     ("Produce", "Fruit > Apple > Apple Sauce"),
                    "peanut butter":  ("Pantry",  "Spreads > Nut Butter > Peanut"),
                    "almond butter":  ("Pantry",  "Spreads > Nut Butter > Almond"),
                    "ice cream":      ("Frozen",  "Ice Cream"),
                    "sour cream":     ("Dairy",   "Sour Cream"),
                    "cream cheese":   ("Dairy",   "Cream Cheese"),
                    "hot dog":        ("Meat & Seafood", "Hot Dog"),
                    "corn dog":       ("Frozen",  "Corn Dog"),
                    "egg nog":        ("Beverage","Eggnog"),
                    "eggnog":         ("Beverage","Eggnog"),
                    "hot cocoa":      ("Beverage","Hot Cocoa"),
                    "hot chocolate":  ("Beverage","Hot Cocoa"),
                    "iced tea":       ("Beverage","Tea > Iced"),
                    "cold brew":      ("Beverage","Coffee > Cold Brew"),
                    "frozen yogurt":  ("Frozen",  "Frozen Yogurt"),
                    "trail mix":      ("Snack",   "Trail Mix"),
                    "granola bar":    ("Snack",   "Bar > Granola"),
                    "protein bar":    ("Snack",   "Bar > Protein"),
                    "protein powder": ("Beverage","Protein Powder"),
                    "fruit snack":    ("Snack",   "Fruit Snack"),
                    "rice cake":      ("Snack",   "Rice Cake"),
                    "tortilla chip":  ("Snack",   "Chip > Tortilla"),
                    "potato chip":    ("Snack",   "Chip > Potato"),
                    "macaroni and cheese": ("Pantry","Pasta > Macaroni And Cheese"),
                    "macaroni & cheese":   ("Pantry","Pasta > Macaroni And Cheese"),
                    "mac and cheese":      ("Pantry","Pasta > Macaroni And Cheese"),
                    "chicken nugget":      ("Frozen","Chicken Nugget"),
                    "chicken tender":      ("Frozen","Chicken Tender"),
                    "fish stick":          ("Frozen","Fish Stick"),
                    "egg roll":            ("Frozen","Egg Roll"),
                    "spring roll":         ("Frozen","Spring Roll"),
                    "pop tart":            ("Bakery","Pastry > Toaster"),
                    "toaster pastry":      ("Bakery","Pastry > Toaster"),
                }
        cur_desc_norm = cur_desc.replace(" ", "")
        # iterate longest-first so multi-word compounds beat shorter prefixes
        for combo in sorted(compound_anchors.keys(), key=lambda x: -len(x)):
            if combo.replace(" ", "") in cur_desc_norm:
                s, g = compound_anchors[combo]
                cur_super = s; cur_grp = g; cur_tok = combo
                break
        if cur_super:
            # Build anchor leaf: super > grp > head_token (when head adds
            # specificity beyond grp).  E.g. cat_heads["bacon"]=(Meat&Seafood,
            # Meat) → leaf becomes "Meat & Seafood > Bacon" not
            # "Meat & Seafood > Meat".
            parts = [cur_super]
            if cur_grp and cur_grp.lower() != cur_super.lower():
                parts.append(cur_grp)
            head_title = (cur_tok or "").title()
            if head_title and head_title.lower() not in (p.lower() for p in parts):
                # only append if more specific than the existing tail; e.g. don't
                # append "Apple" if grp is already "Apple"
                if not parts or head_title.lower() != parts[-1].lower():
                    # if grp is the literal generic "Meat", "Vegetable", "Fruit",
                    # replace it with the head token; otherwise append
                    GENERIC_GROUPS = {"meat","vegetable","fruit","seafood","poultry","cereal"}
                    if parts and parts[-1].lower() in GENERIC_GROUPS:
                        parts[-1] = head_title
                    else:
                        parts.append(head_title)
            cur_anchor_leaf = " > ".join(parts)

            # Defer to BFC when they disagree at supercategory level — the
            # audit's current_esha can be wrong (e.g. tagging a rice dish as
            # "avocado pulp"). BFC is the USDA shelf category and is more
            # reliable for the supercategory signal.
            tmp_bfc_path, _ = bfc_hint(bfc) if bfc else ("", 0)
            anchor_w = 2.5
            if tmp_bfc_path:
                bfc_super_first = tmp_bfc_path.split(" > ")[0].lower()
                anchor_super_first = cur_super.lower()
                if bfc_super_first and bfc_super_first != anchor_super_first:
                    anchor_w = 1.0     # weakened — likely audit error
                    provenance.setdefault("guards", {})["b_neg1_bfc_disagree"] = True
            # SANITY CHECK: if the head_token from current_esha_desc doesn't
            # appear in the product title at all, the audit is probably wrong
            # (e.g. shrimp fajita tagged as "Pastry, toaster, apple" — title
            # contains neither "pastry" nor "toaster").  Drop weight to 0.4.
            if cur_tok and cur_tok.lower() not in title.lower():
                # also check: any of the leaf segment tokens in title?
                leaf_tokens = set(re.split(r'[^a-z]+', cur_anchor_leaf.lower()))
                title_tokens = set(re.split(r'[^a-z]+', title.lower()))
                if not (leaf_tokens & title_tokens & {cur_tok.lower(), cur_grp.lower(), cur_super.lower()}):
                    anchor_w = min(anchor_w, 0.4)
                    provenance.setdefault("guards", {})["b_neg1_audit_token_missing_in_title"] = True
            votes[cur_anchor_leaf] += anchor_w
            provenance["b_neg1_esha_anchor"] = {"esha_desc": cur_desc, "anchor_leaf": cur_anchor_leaf, "head_token": cur_tok, "score": anchor_w}

    # B0 — branded_food_category hint (boost matching leaves, NOT a vote key)
    bfc_path, bfc_w = bfc_hint(bfc)
    if bfc_path:
        provenance["b0_bfc"] = {"hint": bfc_path, "weight": bfc_w}

    # B1 — title parser leaf
    b1 = c.get("b1_leaf") or ""
    b1_cf = float(c.get("b1_confidence") or 0)
    if b1 and b1_cf >= 0.55 and "Other > Unclassified" not in b1:
        votes[b1] += 2.0 * b1_cf
        provenance["b1_parser"] = {"leaf": b1, "score": round(2.0 * b1_cf, 3)}

    # B6 — embed kNN top-3 vote.
    # Resolve the FNDDS/ESHA description to a canonical category leaf using
    # cat_heads, so multiple signals naming the same category combine instead
    # of competing as separate keys.
    if c.get("b6_top_codes"):
        codes  = (c["b6_top_codes"] or "").split("|")[:3]
        scores = [float(s) for s in (c["b6_top_scores"] or "").split("|")[:3]] or [0]
        descs  = (c["b6_top_descs"] or "").split("||")[:3]
        if codes and codes[0]:
            avg = sum(scores)/max(1,len(scores))
            top_desc = (descs[0] if descs else "").lower()
            # try to canonicalize via cat_heads
            ctok, csup, cgrp = category_for_phrase(top_desc, cat_heads, context=title + " " + top_desc)
            if csup:
                canon = f"{csup} > {cgrp}" if cgrp and cgrp.lower() != csup.lower() else csup
                # add specificity if head differs from grp
                if ctok and ctok.title().lower() not in canon.lower():
                    GENERIC_GROUPS = {"meat","vegetable","fruit","seafood","poultry","cereal"}
                    if cgrp.lower() in GENERIC_GROUPS:
                        canon = f"{csup} > {ctok.title()}"
                    else:
                        canon = f"{canon} > {ctok.title()}"
                votes[canon] += 1.0 * avg
                provenance["b6_embed_knn"] = {"resolved_leaf": canon, "head_token": ctok, "score": round(1.0 * avg, 3)}
            else:
                # fall back to raw ESHA reference vote
                esha_leaf = f"ESHA:{codes[0]}|{descs[0] if descs else ''}"
                votes[esha_leaf] += 1.0 * avg
                provenance["b6_embed_knn"] = {"leaf": esha_leaf, "score": round(1.0 * avg, 3)}

    # B7 — funnel sub_leaf. Same resolution as B6: canonicalize via cat_heads.
    if not c.get("b7_other"):
        sl = c.get("b7_sub_leaf_label") or ""
        if sl and sl.lower() not in ("", "other"):
            ftok, fsup, fgrp = category_for_phrase(sl.lower(), cat_heads, context=title + " " + sl.lower())
            if fsup:
                fcanon = f"{fsup} > {fgrp}" if fgrp and fgrp.lower() != fsup.lower() else fsup
                if ftok and ftok.title().lower() not in fcanon.lower():
                    GENERIC_GROUPS = {"meat","vegetable","fruit","seafood","poultry","cereal"}
                    if fgrp.lower() in GENERIC_GROUPS:
                        fcanon = f"{fsup} > {ftok.title()}"
                    else:
                        fcanon = f"{fcanon} > {ftok.title()}"
                votes[fcanon] += 0.8
                provenance["b7_funnel"] = {"resolved_leaf": fcanon, "head_token": ftok, "score": 0.8}
            else:
                funnel_leaf = f"FUNNEL:{sl}"
                votes[funnel_leaf] += 0.8
                provenance["b7_funnel"] = {"leaf": funnel_leaf, "score": 0.8}

    # B8 — ingredient FNDDS.
    # When the ingredient-cosine FNDDS DESCRIPTION shares a content token with
    # b1's leaf, this is corroboration — boost b1 instead of voting for a
    # parallel FNDDS-prefixed leaf. Only fall back to a competing FNDDS leaf
    # vote when b1 has no leaf at all.
    b8_code = c.get("b8_top_fndds_code") or ""
    b8_desc = (c.get("b8_top_fndds_desc") or "").lower()
    b8_score = float(c.get("b8_top_score") or 0)
    if b8_code and b8_score >= 0.5:
        # extract content tokens from b8_desc (drop short/common words)
        b8_tokens = {t for t in re.split(r"[^a-z]+", b8_desc) if len(t) >= 4}
        b1_tokens = set(re.split(r"[^a-z]+", (b1 or "").lower()))
        overlap = b8_tokens & b1_tokens
        # also corroborate by shared "applesauce" -> "apple"+"sauce"
        if not overlap and b8_desc:
            for combo in ("applesauce","peanut butter","ice cream","sour cream","cream cheese","hot dog","corn dog"):
                if combo.replace(" ","") in b8_desc.replace(" ",""):
                    parts = combo.split()
                    if all(p in b1_tokens for p in parts):
                        overlap = set(parts); break
        if overlap and b1:
            # corroborate b1
            votes[b1] += 1.5 * b8_score
            provenance["b8_corroborates_b1"] = {"shared_tokens": sorted(overlap), "boost": round(1.5 * b8_score, 3)}
        else:
            # b1 absent OR no token overlap — canonicalize B8 via cat_heads
            # so it joins the consensus pool rather than living as a separate
            # FNDDS:* key.
            b8_w = (1.2 * b8_score) if (not b1 or b1_cf < 0.55) else (0.8 * b8_score)
            btok, bsup, bgrp = category_for_phrase(b8_desc, cat_heads, context=title + " " + b8_desc)
            if bsup:
                bcanon = f"{bsup} > {bgrp}" if bgrp and bgrp.lower() != bsup.lower() else bsup
                if btok and btok.title().lower() not in bcanon.lower():
                    GENERIC_GROUPS = {"meat","vegetable","fruit","seafood","poultry","cereal"}
                    if bgrp.lower() in GENERIC_GROUPS:
                        bcanon = f"{bsup} > {btok.title()}"
                    else:
                        bcanon = f"{bcanon} > {btok.title()}"
                votes[bcanon] += b8_w
                provenance["b8_ingredient_fndds"] = {"resolved_leaf": bcanon, "head_token": btok, "score": round(b8_w, 3)}
            else:
                b8_leaf = f"FNDDS:{b8_code}|{b8_desc}"
                votes[b8_leaf] += b8_w
                provenance["b8_ingredient_fndds"] = {"leaf": b8_leaf, "score": round(b8_w, 3)}

    # B2 — head-phrase based category routing.
    # We use the syntactic head two ways:
    #   (a) BOOST b1 when b1 already agrees with head's supercategory
    #   (b) PROVIDE a fallback leaf when b1 is missing/low-confidence
    #   (c) OVERRIDE b1 when b1 confidently chose a DIFFERENT supercategory
    #       AND b1's path doesn't share any tokens with the head_phrase
    head = c.get("head_phrase") or ""
    if head:
        tok, sup, grp = category_for_phrase(head, cat_heads, context=title + " " + head)
        if tok and sup:
            head_leaf = f"{sup} > {grp}" if grp and grp != sup else sup
            head_super = sup.lower()
            b1_super = (b1.split(" > ")[0].lower()) if b1 and " > " in b1 else (b1.lower() if b1 else "")
            bfc_super = (bfc_path.split(" > ")[0].lower()) if bfc_path else ""
            head_in_b1  = bool(b1) and head_super == b1_super
            head_in_bfc = bool(bfc_super) and head_super == bfc_super
            b1_bfc_agree = bool(b1_super) and bool(bfc_super) and b1_super == bfc_super

            if head_in_b1:
                # b1 agrees with head's supercategory.  But the parser may have
                # picked a SIBLING type segment (e.g. b1='Pantry > Pasta >
                # Macaroni' when title says PENNE).  If head_token isn't already
                # represented in b1, recover specificity instead of just boosting.
                head_leaf_pref = f"{sup} > {grp}" if grp and grp != sup else sup
                b1_lower = b1.lower()
                tok_lc = tok.lower()
                if tok_lc not in b1_lower:
                    if b1_lower.startswith(head_leaf_pref.lower() + " > "):
                        # b1 extends head_leaf with a sibling-type segment.
                        # Replace that one segment with head_token; keep any
                        # downstream flavor tail intact.
                        b1_segs = [s.strip() for s in b1.split(" > ")]
                        head_segs = [s.strip() for s in head_leaf_pref.split(" > ")]
                        rest = b1_segs[len(head_segs)+1:]
                        more_specific = " > ".join(head_segs + [tok.title()] + rest)
                        votes[more_specific] += 2.0
                        votes[b1] *= 0.6
                        provenance["b2_head_specificity"] = {
                            "head_token": tok, "more_specific": more_specific,
                            "replaced_b1_tail": b1_segs[len(head_segs)] if len(b1_segs) > len(head_segs) else "",
                        }
                    else:
                        # b1 == head_leaf (or shorter) — head_token adds depth.
                        more_specific = f"{b1} > {tok.title()}"
                        votes[more_specific] += 1.5
                        votes[b1] += 0.3
                        provenance["b2_head_append"] = {
                            "head_token": tok, "appended_to": b1, "result": more_specific,
                        }
                else:
                    # head_token already represented in b1 — pure boost
                    votes[b1] += 1.0
                    provenance["b2_head_agree"] = {"head_token": tok, "boost": 1.0}
            elif (not b1) or b1_cf < 0.7 or "Other > Unclassified" in (b1 or ""):
                # b1 missing/low-confidence — head provides the fallback
                votes[head_leaf] += 1.5
                provenance["b2_head_fallback"] = {"leaf": head_leaf, "head_token": tok, "score": 1.5}
            elif b1_bfc_agree and not head_in_bfc:
                # b1 AND BFC agree on supercategory but head disagrees.
                # Don't override the majority — head's category-tsv match is
                # likely an ingredient that appears in the title rather than
                # the product head (e.g. acai in an acai-flavored beverage).
                pass
            elif bfc_super and bfc_w >= 1.4 and not head_in_bfc:
                # BFC has a strong hint but head_phrase says something else
                # (e.g. sandwich w/ "blue cheese" head). BFC wins, head silent.
                # Just downweight b1 so BFC fallback can win.
                votes[b1] *= 0.6
                provenance["b2_head_silenced_by_bfc"] = {
                    "head_token": tok, "bfc_super": bfc_super,
                    "head_super": sup,
                }
            else:
                # b1 high cf, BFC absent or weak, head says something different
                # → head wins.  Compose a richer head leaf: super > group >
                # head_token > [compound modifier from compound_prefix].
                head_parts = [sup]
                if grp and grp.lower() != sup.lower():
                    head_parts.append(grp)
                head_title = tok.title()
                if head_title and head_title.lower() not in (p.lower() for p in head_parts):
                    GENERIC = {"meat","vegetable","fruit","seafood","poultry","cereal","spreads"}
                    if head_parts and head_parts[-1].lower() in GENERIC:
                        head_parts[-1] = head_title
                    else:
                        head_parts.append(head_title)
                # add compound prefix modifier (e.g. "lemon beet" for hummus)
                cp = (c.get("compound_prefix") or "").strip()
                if cp:
                    cp_words = [w for w in cp.split() if w.lower() != tok.lower() and len(w) > 2]
                    if cp_words:
                        head_parts.append(" ".join(w.title() for w in cp_words[:3]))
                head_leaf_specific = " > ".join(head_parts)
                # carry b1's distinctive flavor tail (e.g. "Blueberry" from
                # b1="Produce > Fruit > Blueberry > Pie") into the new leaf
                head_leaf_specific = carry_b1_tail(head_leaf_specific, b1)
                votes[head_leaf_specific] += 2.0
                votes[b1] *= 0.6
                provenance["b2_head_override"] = {
                    "leaf": head_leaf_specific, "head_token": tok,
                    "head_super": sup, "b1_super": b1_super,
                    "downweighted_b1": b1,
                }

    # B3 — NER head-span match against category-tsv.
    # Boost ALL leaves currently in the vote whose supercategory matches the
    # NER token's supercategory (capped at one boost per leaf, regardless of
    # how many NER spans match — otherwise multi-modifier titles like
    # "maple brown sugar cereal" stack 3-4 boosts on b1 and bury the anchor).
    ner = c.get("ner_spans") or ""
    if ner:
        ner_supers = set()
        ner_tokens_matched = []
        ner_tok_super = []   # (tok, sup, grp)
        for span in ner.split("|"):
            ntok, nsup, ngrp = category_for_phrase(span, cat_heads, context=title)
            if ntok and nsup:
                ner_supers.add(nsup.lower())
                ner_tokens_matched.append(ntok)
                ner_tok_super.append((ntok, nsup, ngrp))
        if ner_supers:
            for leaf in list(votes.keys()):
                ll_super = leaf.split(" > ")[0].lower() if " > " in leaf else leaf.lower()
                if ll_super in ner_supers:
                    votes[leaf] += 0.5     # capped, one boost per matching leaf
            if ner_tokens_matched:
                provenance["b3_ner_match"] = {"matches": ner_tokens_matched, "applied": "all_leaves_in_super"}

            # SPECIFICITY: if NER token is a category-tsv head AND it's missing
            # from the current top vote (and from b1), append it.  Captures
            # cases where head_phrase missed but NER caught (e.g. 'gouda',
            # 'penne' as a non-head modifier, 'truffle' as a flavor-form).
            if votes:
                top_leaf, top_score = max(votes.items(), key=lambda kv: kv[1])
                top_super = top_leaf.split(" > ")[0].lower() if " > " in top_leaf else top_leaf.lower()
                top_lc = top_leaf.lower()
                title_lc_full = title.lower()
                appended_ner = []
                top_segs_lc = [s.strip().lower() for s in top_leaf.split(" > ")]
                for ntok, nsup, ngrp in ner_tok_super:
                    if nsup.lower() != top_super:        continue
                    if ntok.lower() in top_lc:           continue
                    if ntok.lower() not in title_lc_full: continue
                    # Skip NER tokens whose resolved (sup, grp) is a prefix of
                    # top_leaf — those are PARENT category words, not deeper
                    # specificity (e.g. NER 'macaroni' resolves to Pantry>Pasta
                    # for a leaf already at 'Pantry > Pasta > Penne').
                    ngrp_segs = [s.strip().lower() for s in (ngrp or "").split(" > ") if s.strip()]
                    parent_prefix = [nsup.lower()] + ngrp_segs
                    if len(top_segs_lc) > len(parent_prefix) and top_segs_lc[:len(parent_prefix)] == parent_prefix:
                        continue
                    appended_ner.append(ntok)
                if appended_ner:
                    extras = " ".join(t.title() for t in appended_ner[:2])
                    more_specific = f"{top_leaf} > {extras}"
                    votes[more_specific] += top_score + 0.3   # narrowly beat top
                    provenance["b3_ner_specificity"] = {
                        "appended": appended_ner[:2], "from_leaf": top_leaf,
                        "result": more_specific,
                    }

    # B9 — ingredient-signature boost.
    # Boost any existing vote whose leaf matches the signature pattern, instead
    # of introducing a new prefixed key. Also gate on title-content: don't fire
    # nog-boost unless title actually mentions nog/eggnog; don't fire
    # baked-beans-boost unless title mentions beans/baked.
    ing_sig = c.get("b9_ing_sig") or ""
    if ing_sig:
        title_lc_chk = title.lower()
        for kv in ing_sig.split(";"):
            if not kv: continue
            cat, _, score = kv.partition(":")
            try: sc = float(score)
            except: sc = 0.0
            if cat == "nog":
                if not ("nog" in title_lc_chk or "eggnog" in title_lc_chk):
                    continue
                for leaf_key in list(votes.keys()):
                    if "nog" in leaf_key.lower():
                        votes[leaf_key] += sc
                provenance.setdefault("b9_ing_sig", []).append({"cat": "nog", "score": sc, "applied": "boost-existing"})
            elif cat == "baked beans":
                if not ("baked bean" in title_lc_chk or ("beans" in title_lc_chk and "baked" in title_lc_chk)):
                    continue
                for leaf_key in list(votes.keys()):
                    ll = leaf_key.lower()
                    if "bean" in ll or "legume" in ll:
                        votes[leaf_key] += sc
                provenance.setdefault("b9_ing_sig", []).append({"cat": "baked beans", "score": sc, "applied": "boost-existing"})

    # B-axis plant-milk compose — flavor must come from TITLE-only tokens.
    # Pulling from ingredients leaks emulsifier/lecithin tokens (sunflower,
    # gellan, lecithin) into the flavor slot.
    plant_words = ("almondmilk","almond milk","oatmilk","oat milk","soymilk","soy milk",
                   "coconut milk","cashew milk","rice milk","plant based","plant-based",
                   "non-dairy","non dairy","dairy free","dairy-free")
    title_lc = title.lower()
    if any(p in title_lc for p in plant_words):
        plant = ""
        for p in ("almond","oat","soy","coconut","cashew","rice"):
            if p in title_lc: plant = p; break
        # flavor: scan only TITLE for known flavor tokens
        title_flavors_known = (
            "vanilla","chocolate","strawberry","banana","mango","blueberry","raspberry",
            "chipotle","sriracha","wasabi","horseradish","garlic","lime","lemon","mint",
            "honey","maple","caramel","cinnamon","pumpkin spice","matcha","mocha",
            "salted caramel","cookies and cream","cookie dough",
            "original","plain","unflavored",
            "unsweetened","sweetened","light","reduced sugar",
            "double chocolate","dark chocolate","milk chocolate","white chocolate",
        )
        flav = ""
        # prefer multi-word matches (longest first) and rightmost
        for f in sorted(title_flavors_known, key=lambda x: -len(x)):
            if f in title_lc:
                flav = f.title()
                break
        if plant and flav:
            leaf = f"Beverage > Plant-based Milk > {plant.title()} Milk > {flav}"
            votes[leaf] += 1.5
            provenance["b_axis_plant_milk"] = {"leaf": leaf, "plant": plant, "flavor": flav}

    # ---- BFC compatibility downweight (rough heuristic) ----
    # We don't have a leaf→modal-BFC table here; the funnel sub_leaf already
    # incorporates BFC coherence in its construction, so we apply it lightly:
    # if the title parser and funnel disagree AND the funnel is not 'other',
    # require the parser's leaf to share at least one token with bfc to keep
    # full weight; otherwise downweight by 0.5x.
    if b1 and bfc and "FUNNEL:" + (c.get("b7_sub_leaf_label") or "") in votes:
        b1_tokens = set((b1 or "").lower().split())
        bfc_tokens = set(bfc.split())
        if not (b1_tokens & bfc_tokens):
            votes[b1] *= 0.5
            provenance.setdefault("guards", {})["bfc_mismatch_downweight"] = 0.5

    # ---- BFC boost AFTER all primary votes are in:
    #      add bfc_w to every leaf whose prefix overlaps with the hint;
    #      AND if NO leaf shares BFC's supercategory, BFC gets a full vote and
    #      the dissenting b1 leaf is downweighted (audit-disagreement signal).
    if bfc_path:
        bfc_prefix = bfc_path.lower()
        bfc_first  = bfc_prefix.split(" > ")[0]
        any_match = False
        for leaf in list(votes.keys()):
            ll = leaf.lower()
            ll_first = ll.split(" > ")[0] if " > " in ll else ll
            if bfc_prefix in ll or ll.startswith(bfc_prefix):
                votes[leaf] += bfc_w
                any_match = True
            elif ll_first == bfc_first or bfc_first in ll_first:
                votes[leaf] += 0.5 * bfc_w
                any_match = True
        if not any_match:
            # No vote agrees with BFC's supercategory.  BFC stands as a
            # full-weight competing vote (not a half-weight fallback)
            votes[bfc_path] += bfc_w
            provenance.setdefault("b0_bfc", {})["fallback_leaf"] = bfc_path

        # Downweight b1 when its leaf disagrees with BFC.
        #   - SUPER mismatch (Pantry vs Snack) → strong downweight (0.4×)
        #   - SUPER matches but GROUP mismatch (Pantry > Sweeteners vs
        #     Pantry > Breakfast Cereal) → moderate downweight (0.6×)
        if b1 and b1 in votes:
            b1_segs = [s.lower() for s in b1.split(" > ")]
            bfc_segs = [s.lower() for s in bfc_path.split(" > ")]
            if b1_segs and bfc_segs:
                if b1_segs[0] != bfc_segs[0]:
                    votes[b1] *= 0.4
                    provenance.setdefault("guards", {})["b1_bfc_super_disagree"] = True
                elif (len(b1_segs) >= 2 and len(bfc_segs) >= 2
                      and b1_segs[1] != bfc_segs[1]):
                    votes[b1] *= 0.6
                    provenance.setdefault("guards", {})["b1_bfc_group_disagree"] = True

    # ---- pick top ----
    if not votes:
        return {
            "retail_leaf":     "",
            "confidence":      0.0,
            "sources_agreed":  0,
            "provenance":      json.dumps({}),
            "gap_flag":        True,
            "mint_candidate":  json.dumps({"head_phrase": head, "compound_prefix": c.get("compound_prefix",""), "ner": ner}),
        }
    # Plant-milk safety net: if the title clearly says almondmilk/oatmilk/etc.,
    # FORCE the leaf to start with Beverage > Plant-based Milk regardless of
    # what other signals voted. Many products have BFC=Milk/Milk Substitutes
    # which can pull them into Dairy.
    plant_force = ""
    for p in ("almondmilk","almond milk","oatmilk","oat milk","soymilk","soy milk",
              "coconut milk","cashew milk","rice milk","hemp milk","pea milk"):
        if p in title:
            base = p.replace("milk","").replace(" ","").strip().title() or "Almond"
            plant_force = f"Beverage > Plant-based Milk > {base} Milk"
            break
    if plant_force:
        # add a strong vote so any Dairy-routed candidate is overpowered
        votes[plant_force] += 3.0
        provenance["plant_milk_safety_net"] = {"forced": plant_force}

    ranked = sorted(votes.items(), key=lambda x: -x[1])
    top_leaf, top_score = ranked[0]

    # Convert raw ESHA: / FNDDS: leaves to real paths using the SUPER vocab.
    # When B6 (embed kNN) or B8 (ingredient FNDDS) won uncorroborated, the
    # winning "leaf" is just a reference like 'ESHA:14480|Almond Milk, ...'.
    # Map the description into a real Pantry/Beverage/Snack path.
    if top_leaf.startswith(("ESHA:","FNDDS:")):
        # parse desc out
        ref_desc = top_leaf.split("|", 1)[-1] if "|" in top_leaf else top_leaf
        ref_lc = ref_desc.lower()
        # find rightmost matching token in cat_heads
        matched_super = matched_grp = matched_tok = ""
        for tok, (sup, grp) in cat_heads.items():
            if tok in ref_lc:
                if len(tok) > len(matched_tok):
                    matched_tok = tok; matched_super = sup; matched_grp = grp
        if matched_super:
            real_leaf = f"{matched_super} > {matched_grp}" if matched_grp and matched_grp != matched_super else matched_super
            # carry the ESHA ref as a tail label
            top_leaf = real_leaf
            provenance["leaf_promoted_from_ref"] = {
                "original": ranked[0][0], "promoted_to": real_leaf, "head_token": matched_tok,
            }
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    sources_agreed = sum(1 for v in provenance.values() if isinstance(v, dict) and v.get("leaf") == top_leaf)
    margin = top_score - second
    # confidence: scale top_score so a single strong signal (b1 score 2.0) ≈ 0.65
    # and corroborated leaves (≥2 signals agree, score ≥3.0) reach ≥0.85.
    base = min(1.0, top_score / 3.5)
    margin_bonus = 0.10 if (margin > 0.5) else 0.0
    agree_bonus  = 0.10 * max(0, sources_agreed - 1)
    conf = max(0.0, min(1.0, base + margin_bonus + agree_bonus))
    # gap = "low-confidence enough that we should consider minting / human review"
    # b1 cf=0.55 -> score 1.1, that's still a real leaf. Only flag when NO signal
    # contributed materially.
    gap = top_score < 1.0

    # Multi-word compound foods that should always be preserved as the leaf
    # tail when present in the title.  Otherwise the parser splits them
    # ("egg roll" -> Egg > Roll) and the canonicalizer can't reassemble them.
    COMPOUND_FOODS = (
        "egg roll", "spring roll", "summer roll", "lobster roll",
        "corn dog", "hot dog", "ice cream sandwich", "ice cream cone",
        "ice cream bar", "fish stick", "chicken nugget", "chicken tender",
        "chicken finger", "chicken patty", "chicken wing",
        "pop tart", "toaster pastry", "fruit snack", "fruit cup",
        "trail mix", "granola bar", "protein bar", "protein powder",
        "potato chip", "tortilla chip", "pita chip", "rice cake",
        "macaroni and cheese", "macaroni & cheese", "mac and cheese",
        "peanut butter", "almond butter", "nut butter",
        "ice tea", "iced tea", "iced coffee", "cold brew",
        "fish stick", "fish stix",
    )
    title_lc_full = title.lower()
    compound_in_title = ""
    for cf in sorted(COMPOUND_FOODS, key=lambda x: -len(x)):
        if cf in title_lc_full:
            compound_in_title = cf
            break

    # Canonicalize the leaf (singularize rightmost, dedupe adjacent, etc.)
    top_leaf_canonical = canonicalize_leaf(top_leaf, title_lc=title)
    # Append compound food if it's not already represented in the leaf
    if compound_in_title:
        leaf_lc_check = top_leaf_canonical.lower()
        compound_words = compound_in_title.split()
        if not all(w in leaf_lc_check for w in compound_words if len(w) > 2):
            top_leaf_canonical = top_leaf_canonical + " > " + compound_in_title.title()

    # Append meaningful compound_prefix tokens that aren't already in the leaf
    # (e.g. "English" for ENGLISH MUFFINS, "Whole Wheat" for WHOLE WHEAT BREAD).
    # Skip generic prefixes already covered by other axes.
    PRESERVED = {
        "english","french","italian","greek","spanish","mexican","asian",
        "whole wheat","whole grain","multi grain","sourdough","rye","pumpernickel",
        "gluten free","gluten-free","keto","paleo","vegan","organic",
        "low fat","fat free","reduced fat","light","unsweetened","sweetened",
    }
    cp = (c.get("compound_prefix") or "").lower()
    leaf_lc = top_leaf_canonical.lower()
    add_prefix = []
    for p in sorted(PRESERVED, key=lambda x: -len(x)):
        if p in cp and p not in leaf_lc and p not in title.lower()[:0]:
            # only add if literally in the title (not a token from ingredients)
            if p in title.lower():
                add_prefix.append(p.title())
                if len(add_prefix) >= 2: break
    if add_prefix and " > " in top_leaf_canonical:
        # insert prefix tokens before the last segment so the leaf reads
        # "Bakery > Muffin > English" not "Bakery > English > Muffin"
        segs = top_leaf_canonical.split(" > ")
        top_leaf_canonical = " > ".join(segs + add_prefix)

    return {
        "retail_leaf":    top_leaf_canonical,
        "confidence":     round(conf, 3),
        "top_score":      round(top_score, 3),
        "second_score":   round(second, 3),
        "sources_agreed": sources_agreed,
        "provenance":     json.dumps(provenance),
        "gap_flag":       gap,
        "mint_candidate": json.dumps({"head_phrase": head, "compound_prefix": c.get("compound_prefix",""), "ner": ner}) if gap else "",
    }

def run(limit: int | None = None):
    import pyarrow.parquet as pq
    cat_heads, forms = load_axes()
    print(f"axes: {len(cat_heads)} category heads, {len(forms)} forms")

    if not IN_PARQUET.exists():
        print(f"{IN_PARQUET} not found — run candidate_generator.py first")
        sys.exit(1)
    print(f"reading {IN_PARQUET}")
    tbl = pq.read_table(IN_PARQUET).to_pylist()
    if limit: tbl = tbl[:limit]
    print(f"  {len(tbl)} candidates")

    cols = ["fdc_id","gtin_upc","title","branded_food_category",
            "current_esha","current_esha_desc",
            "retail_leaf","confidence","top_score","second_score","sources_agreed",
            "provenance","gap_flag","mint_candidate"]
    written = 0
    high_conf = 0
    gap_count = 0
    t0 = time.time()
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in tbl:
            v = vote(c, cat_heads, forms)
            row = {
                "fdc_id":                c.get("fdc_id",""),
                "gtin_upc":              c.get("gtin_upc",""),
                "title":                 c.get("title",""),
                "branded_food_category": c.get("branded_food_category",""),
                "current_esha":          c.get("current_esha",""),
                "current_esha_desc":     c.get("current_esha_desc",""),
                **v,
            }
            w.writerow(row)
            written += 1
            if v["confidence"] >= 0.5: high_conf += 1
            if v["gap_flag"]:          gap_count += 1
            if written % 50000 == 0:
                print(f"  {written:>7}  high_conf={high_conf}  gaps={gap_count}  ({(time.time()-t0)/60:.1f}m)")
    print(f"\nwrote {OUT_CSV}  ({written} rows, {(time.time()-t0)/60:.1f}m)")
    print(f"  high_conf (≥0.5): {high_conf:,}  ({100*high_conf/written:.1f}%)")
    print(f"  gap candidates:   {gap_count:,}  ({100*gap_count/written:.1f}%)")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args()
    if a.run: run(a.limit)
    else: p.print_help()

if __name__ == "__main__":
    main()
