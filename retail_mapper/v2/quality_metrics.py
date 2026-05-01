#!/usr/bin/env python3
"""quality_metrics.py — baseline measurement of the retail mapping.

Reads:    retail_leaf_v2_enriched_v2.csv
Outputs:  _quality_report.txt          (one-page summary)
          _quality_offenders.csv       (rows that failed each metric)

Metrics:
  1. findability_rate           — does the leaf contain a distinctive title-token?
  2. specificity_loss_rate      — ≥2 distinctive tokens missing from leaf?
  3. same_fndds_super_scatter   — products sharing FNDDS landing in ≤3 supercats?
  4. leaf_cardinality           — products-per-leaf, by supercat
  5. ingredient_leaf_coherence  — first ingredient consistent with leaf supercat?
  6. audit_disagreement_rate    — leaf supercat differs from current_esha_desc head?
  7. recipe_resolution_rate     — top-50 recipe names → leaf match rate
  8. brand_in_leaf_rate         — leaves polluted with brand tokens
"""
from __future__ import annotations
import csv, sys, re, collections, json, time
csv.field_size_limit(sys.maxsize)

REPO = "/Users/jamiebarton/Desktop/esha_audit_bundle"
RM   = f"{REPO}/retail_mapper/v2"
IN_CSV  = f"{RM}/retail_leaf_v2_enriched_v2.csv"
REPORT  = f"{RM}/_quality_report.txt"
OFFENDERS = f"{RM}/_quality_offenders.csv"

# --- 1. ingredient → supercat coherence rules ---
ING_TO_SUPER = [
    # check substring of ing_top5 first-ingredient (lowercased)
    (r"^filtered water|^spring water|^purified water|^artesian water",
                       {"Beverage"}),
    (r"^carbonated water|^sparkling water|^seltzer",
                       {"Beverage"}),
    (r"^almondmilk|^almond milk|^oatmilk|^oat milk|^soymilk|^soy milk|^coconutmilk|^coconut milk",
                       {"Beverage"}),
    (r"^cultured (?:pasteurized )?(?:nonfat )?milk|^milk(?:,| is)|^pasteurized milk|^reduced fat milk|^whole milk",
                       {"Dairy", "Beverage"}),
    (r"^cream\b|^heavy cream|^half (?:and|&) half",
                       {"Dairy"}),
    (r"^yogurt|^cultured nonfat",
                       {"Dairy"}),
    (r"^(?:cheddar|mozzarella|parmesan|swiss|gouda|provolone|romano|cream cheese|cottage cheese|feta|brie|monterey)",
                       {"Dairy"}),
    (r"^butter\b|^unsalted butter|^salted butter|^sweet cream butter",
                       {"Dairy"}),
    (r"^eggs?\b|^liquid egg|^pasteurized egg",
                       {"Dairy"}),
    (r"^enriched (?:wheat )?flour|^whole wheat|^whole grain|^wheat flour|^semolina|^all purpose flour",
                       {"Pantry", "Bakery"}),
    (r"^oats\b|^rolled oats|^steel cut|^oatmeal",
                       {"Pantry"}),
    (r"^rice\b|^long grain|^jasmine rice|^basmati",
                       {"Pantry"}),
    (r"^pasta\b|^macaroni|^spaghetti|^semolina",
                       {"Pantry"}),
    (r"^tomato|^crushed tomato|^tomato pure",
                       {"Pantry", "Produce"}),
    (r"^(?:ground |raw )?beef|^chuck|^sirloin|^brisket",
                       {"Meat & Seafood"}),
    (r"^pork\b|^bacon|^ham\b|^pork loin|^pork shoulder",
                       {"Meat & Seafood"}),
    (r"^chicken\b|^chicken breast|^chicken thigh",
                       {"Meat & Seafood", "Frozen"}),
    (r"^turkey",       {"Meat & Seafood"}),
    (r"^salmon|^tuna|^cod|^tilapia|^shrimp|^crab|^lobster",
                       {"Meat & Seafood"}),
    (r"^honey\b",      {"Pantry"}),
    (r"^(?:cane )?sugar|^brown sugar|^powdered sugar|^maple syrup|^corn syrup",
                       {"Pantry"}),
    (r"^(?:olive|vegetable|canola|soybean|peanut|coconut|avocado|sesame|sunflower) oil|^extra virgin",
                       {"Pantry"}),
    (r"^vinegar|^balsamic|^apple cider vinegar",
                       {"Pantry"}),
    (r"^almonds?\b|^cashews?|^walnuts?|^pecans|^peanuts?\b|^pistachios|^macadamia",
                       {"Snack", "Pantry"}),
    (r"^(?:cocoa|cacao)\b|^chocolate liquor",
                       {"Snack"}),
    (r"^cane juice|^fruit juice|^orange juice|^apple juice|^grape juice",
                       {"Beverage"}),
    (r"^green beans?|^carrots?|^celery|^onion|^bell pepper|^lettuce|^spinach|^cucumber|^kale|^broccoli",
                       {"Produce", "Pantry"}),
    (r"^apples?|^bananas?|^berries|^strawberr|^blueberr|^raspberr|^blackberr|^cherries|^grapes|^pineapple",
                       {"Produce", "Snack"}),
]
def first_ingredient_super(ing_top5: str) -> set[str]:
    if not ing_top5: return set()
    first = ing_top5.split('|')[0].strip().lower()
    for pat, supers in ING_TO_SUPER:
        if re.match(pat, first):
            return supers
    return set()

# --- 2. recipe-name probe set (50 common ingredients) ---
RECIPE_NAMES = [
    # (name, expected substring patterns in leaf)
    ("olive oil",         [r"olive", r"oil"]),
    ("extra virgin olive oil", [r"olive", r"virgin"]),
    ("truffle oil",       [r"truffle", r"oil"]),
    ("butter",            [r"butter"]),
    ("salted butter",     [r"butter"]),
    ("unsalted butter",   [r"butter"]),
    ("milk",              [r"milk"]),
    ("whole milk",        [r"whole", r"milk"]),
    ("almond milk",       [r"almond", r"milk"]),
    ("greek yogurt",      [r"greek", r"yogurt"]),
    ("blueberry yogurt",  [r"yogurt"]),  # blueberry is ideal but yogurt-only acceptable
    ("cream cheese",      [r"cream", r"cheese"]),
    ("cheddar cheese",    [r"cheddar"]),
    ("mozzarella",        [r"mozzarella"]),
    ("parmesan",          [r"parmesan"]),
    ("ground beef",       [r"beef"]),
    ("chicken breast",    [r"chicken"]),
    ("bacon",             [r"bacon"]),
    ("deli ham",          [r"ham"]),
    ("eggs",              [r"egg"]),
    ("flour",             [r"flour"]),
    ("all-purpose flour", [r"flour"]),
    ("sugar",             [r"sugar"]),
    ("brown sugar",       [r"brown", r"sugar"]),
    ("honey",             [r"honey"]),
    ("maple syrup",       [r"maple", r"syrup"]),
    ("salt",              [r"salt"]),
    ("black pepper",      [r"pepper"]),
    ("cinnamon",          [r"cinnamon"]),
    ("vanilla extract",   [r"vanilla"]),
    ("baking powder",     [r"baking"]),
    ("baking soda",       [r"baking"]),
    ("oats",              [r"oat"]),
    ("rice",              [r"rice"]),
    ("pasta",             [r"pasta"]),
    ("spaghetti",         [r"spaghetti|pasta"]),
    ("yellow cake mix",   [r"cake", r"mix"]),
    ("ketchup",           [r"ketchup"]),
    ("mustard",           [r"mustard"]),
    ("mayonnaise",        [r"mayonnaise|mayo"]),
    ("hot sauce",         [r"hot", r"sauce"]),
    ("soy sauce",         [r"soy", r"sauce"]),
    ("worcestershire",    [r"worcestershire|sauce"]),
    ("tomato sauce",      [r"tomato|sauce"]),
    ("tomato paste",      [r"tomato"]),
    ("celery",            [r"celery|vegetable"]),
    ("garlic",            [r"garlic"]),
    ("onion",             [r"onion"]),
    ("lemon juice",       [r"lemon|juice"]),
    ("orange juice",      [r"orange", r"juice"]),
    ("blueberry pie filling", [r"pie|blueberry"]),
]

# brand-pollution detection (small set of common brand tokens)
BRAND_TOKENS = {"silk","eggo","beyond","stouffer","callender","quaker","kellogg",
                "kraft","heinz","tyson","hidden","valley","kewpie","duke","bumble",
                "simply","welch","tropicana","dole","chiquita","nestle","sweet baby",
                "hellmann","duke","heinz","mccormick","betty crocker","pillsbury",
                "lipton","starbucks","oreo","nabisco","keebler","general mills",
                "nature valley","bai","la croix","sparkling ice","bubly","hint",
                "vitamin water","whole foods","trader joe","wegman","kroger","aldi"}

# --- main ---
def main():
    print("loading enriched corpus...")
    t0 = time.time()
    rows = []
    leaves_by_super = collections.defaultdict(set)
    products_by_super = collections.Counter()
    leaves_by_fndds = collections.defaultdict(set)
    products_by_fndds = collections.Counter()
    super_by_fndds = collections.defaultdict(set)
    all_leaves = set()
    with open(IN_CSV) as f:
        for r in csv.DictReader(f):
            leaf = (r.get('retail_leaf') or '').strip()
            sup = leaf.split(' > ')[0] if ' > ' in leaf else (leaf if leaf else '')
            if leaf:
                all_leaves.add(leaf)
                if sup:
                    leaves_by_super[sup].add(leaf)
                    products_by_super[sup] += 1
            if r.get('current_esha'):
                e = r['current_esha']
                products_by_fndds[e] += 1
                if leaf: leaves_by_fndds[e].add(leaf)
                if sup:  super_by_fndds[e].add(sup)
            rows.append(r)
    n = len(rows)
    print(f"  {n:,} products, {len(all_leaves):,} unique leaves  ({time.time()-t0:.1f}s)")

    # ---- per-row metrics ----
    print("\ncomputing per-row metrics...")
    t0 = time.time()
    findable = 0
    specificity_loss_rows = 0
    coherence_match = coherence_check_n = 0
    audit_disagree = 0
    audit_check_n = 0
    brand_in_leaf = 0

    findability_offenders = []
    specificity_offenders = []
    coherence_offenders = []
    brand_offenders = []

    for r in rows:
        title = r.get('title','') or ''
        leaf  = (r.get('retail_leaf') or '').strip()
        leaf_lc = leaf.lower()
        leaf_super = leaf.split(' > ')[0] if ' > ' in leaf else leaf
        distinctive = (r.get('distinctive_tokens','') or '').lower()
        dt_list = [t.strip() for t in distinctive.split('|') if t.strip()]
        ing5 = r.get('ing_top5','') or ''
        cur_d = (r.get('current_esha_desc','') or '').lower()

        # 1. findability — is at least one distinctive token in the leaf?
        if dt_list:
            in_leaf = sum(1 for t in dt_list if t in leaf_lc)
            if in_leaf >= 1:
                findable += 1
            else:
                if len(findability_offenders) < 200:
                    findability_offenders.append({
                        "fdc_id": r['fdc_id'], "title": title[:60],
                        "leaf": leaf, "distinctive": distinctive,
                    })
            # 2. specificity loss — ≥2 distinctive tokens missing
            missing = [t for t in dt_list[:5] if t not in leaf_lc]
            if len(missing) >= 2 and dt_list:
                specificity_loss_rows += 1
                if len(specificity_offenders) < 200:
                    specificity_offenders.append({
                        "fdc_id": r['fdc_id'], "title": title[:60], "leaf": leaf,
                        "missing": " | ".join(missing[:3]),
                    })

        # 6. ingredient-leaf coherence
        expected_supers = first_ingredient_super(ing5)
        if expected_supers and leaf_super:
            coherence_check_n += 1
            if leaf_super in expected_supers:
                coherence_match += 1
            else:
                if len(coherence_offenders) < 200:
                    coherence_offenders.append({
                        "fdc_id": r['fdc_id'], "title": title[:60], "leaf": leaf,
                        "first_ing": ing5.split('|')[0].strip()[:40],
                        "expected_supers": "/".join(sorted(expected_supers)),
                    })

        # 7. audit disagreement at supercat — we just count, can't tell which side is right without spot-check
        if cur_d:
            audit_check_n += 1
            # audit head segment first comma-segment
            audit_head = cur_d.split(',')[0].strip()
            # very rough: is audit head in leaf?
            if audit_head and audit_head not in leaf_lc and leaf_super:
                audit_disagree += 1

        # 8. brand-in-leaf
        for bt in BRAND_TOKENS:
            if bt in leaf_lc:
                brand_in_leaf += 1
                if len(brand_offenders) < 100:
                    brand_offenders.append({
                        "fdc_id": r['fdc_id'], "title": title[:60], "leaf": leaf,
                        "brand_token": bt,
                    })
                break

    print(f"  per-row done  ({time.time()-t0:.1f}s)")

    # 3. same FNDDS supercat scatter
    fndds_scatter = []
    for code, prods in products_by_fndds.items():
        if prods >= 5:
            fndds_scatter.append((code, prods, len(super_by_fndds[code]), len(leaves_by_fndds[code])))
    fndds_scatter.sort(key=lambda x: -x[2])  # sort by # supercats desc
    fndds_scatter_avg = sum(s[2] for s in fndds_scatter)/max(1,len(fndds_scatter))

    # 4. leaf cardinality per supercat
    cardinality = {sup: (products_by_super[sup], len(leaves_by_super[sup]),
                          products_by_super[sup]/max(1,len(leaves_by_super[sup])))
                   for sup in products_by_super}

    # 7. recipe resolution
    leaves_lc = list(all_leaves)
    leaves_lc_lower = [l.lower() for l in leaves_lc]
    resolved = 0
    unresolved = []
    for name, patterns in RECIPE_NAMES:
        # check if any leaf matches all patterns
        matches = []
        for ll, leaf_orig in zip(leaves_lc_lower, leaves_lc):
            if all(re.search(p, ll) for p in patterns):
                matches.append(leaf_orig)
                if len(matches) >= 3: break
        if matches:
            resolved += 1
        else:
            unresolved.append(name)

    # ---- write report ----
    lines = []
    P = lines.append
    P("=" * 70)
    P("  RETAIL MAPPING — QUALITY BASELINE")
    P("=" * 70)
    P(f"corpus:       {n:,} products / {len(all_leaves):,} unique leaves")
    P("")
    P("METRIC                                    score    target   status")
    P("-" * 70)
    def fmt(name, val, tgt, op="≥"):
        ok = (val >= tgt) if op == "≥" else (val <= tgt)
        return f"  {name:<38s}  {val*100:>5.1f}%   {op}{tgt*100:.0f}%    {'PASS' if ok else 'FAIL'}"
    P(fmt("1. findability_rate",         findable/n, 0.90))
    P(fmt("2. specificity_loss_rate",    specificity_loss_rows/n, 0.10, op="≤"))
    P(f"  3. same_fndds_super_scatter_avg          {fndds_scatter_avg:>5.2f}    ≤3.00    "
      f"{'PASS' if fndds_scatter_avg <= 3.0 else 'FAIL'}")
    P(fmt("5. ingredient_leaf_coherence",
          coherence_match/max(1,coherence_check_n), 0.90))
    P(f"  6. audit_disagreement_rate              {audit_disagree/max(1,audit_check_n)*100:>5.1f}%   "
      f"(informational — manual spot-check needed)")
    P(fmt("7. recipe_resolution_rate (50 names)",
          resolved/len(RECIPE_NAMES), 0.95))
    P(fmt("8. brand_in_leaf_rate",       brand_in_leaf/n, 0.01, op="≤"))
    P("")
    P("LEAF CARDINALITY  (products / unique leaves per supercat)")
    P("-" * 70)
    for sup, (np_, nl_, ratio) in sorted(cardinality.items(), key=lambda x: -x[1][0]):
        flag = "OK" if ratio >= 30 else ("THIN" if ratio < 10 else "ok")
        P(f"  {sup:<25s}  {np_:>7,} products / {nl_:>5,} leaves  =  {ratio:>6.1f} prods/leaf  {flag}")
    P("")
    P("WORST FNDDS SUPER-SCATTER  (same audit-FNDDS landing in many supercats)")
    P("-" * 70)
    for code, n_prod, n_super, n_leaf in fndds_scatter[:15]:
        P(f"  esha={code:>6}  {n_prod:>5} products  in {n_super} supercats / {n_leaf} leaves")
    P("")
    P(f"RECIPE RESOLUTION — unresolved ({len(unresolved)}/{len(RECIPE_NAMES)}):")
    P("-" * 70)
    for u in unresolved:
        P(f"  -  {u}")
    P("")
    P(f"TOP 10 FINDABILITY OFFENDERS  (distinctive tokens missing from leaf):")
    P("-" * 70)
    for o in findability_offenders[:10]:
        P(f"  {o['title']:<55s}")
        P(f"     leaf:        {o['leaf']!r}")
        P(f"     distinctive: {o['distinctive']!r}")
    P("")
    P(f"TOP 10 INGREDIENT-LEAF COHERENCE OFFENDERS:")
    P("-" * 70)
    for o in coherence_offenders[:10]:
        P(f"  {o['title']:<55s}")
        P(f"     leaf:        {o['leaf']!r}")
        P(f"     1st ing:     {o['first_ing']!r}")
        P(f"     expected:    {o['expected_supers']}")
    P("")
    P(f"TOP 10 BRAND-IN-LEAF OFFENDERS:")
    P("-" * 70)
    for o in brand_offenders[:10]:
        P(f"  {o['title']:<55s}")
        P(f"     leaf: {o['leaf']!r}    (brand token: {o['brand_token']!r})")
    P("")
    P("=" * 70)
    text = "\n".join(lines)
    with open(REPORT, 'w') as f: f.write(text)
    print(text)
    print(f"\nfull report -> {REPORT}")

    # write offenders csv
    with open(OFFENDERS, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(["metric","fdc_id","title","retail_leaf","extra"])
        for o in findability_offenders:
            w.writerow(["findability", o['fdc_id'], o['title'], o['leaf'], "missing distinctive: "+o['distinctive']])
        for o in specificity_offenders:
            w.writerow(["specificity_loss", o['fdc_id'], o['title'], o['leaf'], "missing tokens: "+o['missing']])
        for o in coherence_offenders:
            w.writerow(["ingredient_coherence", o['fdc_id'], o['title'], o['leaf'],
                        f"first_ing={o['first_ing']} expected_supers={o['expected_supers']}"])
        for o in brand_offenders:
            w.writerow(["brand_in_leaf", o['fdc_id'], o['title'], o['leaf'], "brand: "+o['brand_token']])
    print(f"offenders -> {OFFENDERS}")

if __name__ == "__main__":
    main()
