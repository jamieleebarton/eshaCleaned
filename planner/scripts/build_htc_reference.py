#!/usr/bin/env python3
"""Build the HTC-native reference table the planner uses.

For every HTC code that appears in recipes_unified.csv (with its 8-char form),
emit one row containing:

  - macros per 100g       (kcal, protein_g, fat_g, carb_g, fiber_g, sodium_mg)
  - cheapest priced SKU   (cents_per_gram, cents, grams, sku_name, sku_upc)
  - food_group            (vegetables / fruits / dairy / grains / protein / fat / other)
  - protein_source        (beef / pork / poultry / fish / eggs / legumes / none)
  - perishability         (shelf_days, can_freeze, loss_rate_per_week)
  - allergens             (set of major allergens by canonical_path patterns)
  - sample_canonical_path (most common canonical_path at this HTC)

Resolution strategy per HTC:
  1. Exact 8-char HTC match in priced_products_v2.db
  2. Fall back to 4-char family prefix (positions 1–4) if exact has no SKUs
  3. Macros from priced_products' consensus_fndds → fndds_nutrient_lookup,
     averaged across SKUs that share the HTC. Crystallized into HTC-native
     macros — planner never reads FNDDS at runtime.

Output: planner/data/htc_reference.json
"""
from __future__ import annotations
import csv, json, sqlite3, sys, statistics
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
PRICED = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
UNIFIED = ROOT / "recipe_mapper" / "v1" / "output" / "recipes_unified.csv"
HTC_TAGGED = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_htc_tagged.csv"
FNDDS = ROOT / "data" / "fndds" / "fndds_nutrient_lookup.csv"
OUT = ROOT / "planner" / "data" / "htc_reference.json"


# --------- food group / protein source by canonical_path ---------
# canonical_path top-1 → food group label used by planner balance scoring
PATH_FOOD_GROUP = {
    "Produce": "produce",          # split below: fruit vs vegetable
    "Meat & Seafood": "protein",
    "Dairy": "dairy",
    "Bakery": "grains",
    "Pantry": "pantry",            # generic; refined below
    "Frozen": "frozen_other",
    "Snack": "other",
    "Beverage": "other",
    "Meal": "other",
    "Non-Food": "non_food",
    "Sports & Wellness": "non_food",
    "Baby & Toddler": "non_food",
    "Baby": "non_food",
    "Breakfast": "grains",
}

# Refinements based on path segments
def food_group_from_path(cp: str) -> str:
    if not cp: return "other"
    parts = [p.strip() for p in cp.split(" > ")]
    top = parts[0]
    g = PATH_FOOD_GROUP.get(top, "other")
    cp_low = cp.lower()
    if g == "produce":
        if "fruit" in cp_low: return "fruits"
        if "berr" in cp_low: return "fruits"
        if "herb" in cp_low: return "vegetables"  # planner counts herbs as veg
        return "vegetables"
    if g == "frozen_other":
        if "fruit" in cp_low: return "fruits"
        if "vegetable" in cp_low or "veggie" in cp_low: return "vegetables"
        if "meat" in cp_low or "poultry" in cp_low or "seafood" in cp_low: return "protein"
        if "dough" in cp_low or "bread" in cp_low or "pasta" in cp_low or "rice" in cp_low: return "grains"
        return "other"
    if g == "pantry":
        if "flour" in cp_low or "rice" in cp_low or "grain" in cp_low or "pasta" in cp_low or "cereal" in cp_low or "bread" in cp_low: return "grains"
        if "bean" in cp_low or "lentil" in cp_low or "legume" in cp_low: return "protein"
        if "nut" in cp_low or "seed" in cp_low: return "protein"
        if "oil" in cp_low or "shortening" in cp_low: return "fats"
        if "spice" in cp_low or "seasoning" in cp_low or "salt" in cp_low or "extract" in cp_low: return "seasoning"
        if "sweetener" in cp_low or "sugar" in cp_low or "syrup" in cp_low or "honey" in cp_low: return "sweets"
        if "vegetable" in cp_low or "tomato" in cp_low or "olive" in cp_low or "pickle" in cp_low or "chili" in cp_low or "pepper" in cp_low: return "vegetables"
        if "fruit" in cp_low: return "fruits"
        return "pantry_other"
    return g

def protein_source_from_path(cp: str) -> str:
    cp_low = (cp or "").lower()
    if "beef" in cp_low or "veal" in cp_low: return "beef"
    if "lamb" in cp_low or "mutton" in cp_low: return "lamb"
    if "pork" in cp_low or "ham" in cp_low or "bacon" in cp_low: return "pork"
    if "chicken" in cp_low or "turkey" in cp_low or "duck" in cp_low or "poultry" in cp_low or "goose" in cp_low: return "poultry"
    if "fish" in cp_low or "salmon" in cp_low or "tuna" in cp_low or "shellfish" in cp_low or "seafood" in cp_low or "shrimp" in cp_low or "crab" in cp_low or "lobster" in cp_low: return "fish"
    if "egg" in cp_low and "egg roll" not in cp_low: return "eggs"
    if "bean" in cp_low or "lentil" in cp_low or "tofu" in cp_low or "tempeh" in cp_low or "seitan" in cp_low or "legume" in cp_low: return "legumes"
    if "nut" in cp_low and "non-food" not in cp_low: return "nuts"
    return "none"

# Allergen patterns
ALLERGEN_RULES = [
    (("milk","dairy"),     ["dairy >", "milk", "cheese", "yogurt", "butter", "cream"]),
    (("egg","eggs"),       ["eggs", "egg "]),
    (("wheat","gluten"),   ["bakery >", "bread", "pasta", "flour", "wheat", "cracker", "cereal", "cookie", "biscuit"]),
    (("soy","soybeans"),   ["soy", "tofu", "edamame", "tempeh", "miso"]),
    (("peanut",),          ["peanut"]),
    (("treenut",),         ["almond","cashew","walnut","pecan","pistachio","macadamia","hazelnut","pine nut","brazil nut"]),
    (("fish",),            ["fish >", "salmon","tuna","cod","halibut","tilapia","trout","bass","mackerel","sardine"]),
    (("shellfish",),       ["shellfish","shrimp","crab","lobster","clam","mussel","oyster","scallop","prawn","crayfish"]),
    (("sesame",),          ["sesame", "tahini"]),
]
def allergens_from_path(cp: str) -> list[str]:
    cp_low = (cp or "").lower()
    out = set()
    for (canon, *aliases), patterns in ALLERGEN_RULES:
        for p in patterns:
            if p in cp_low:
                out.add(canon)
                break
    return sorted(out)

# Perishability heuristics keyed by canonical_path top + segments
def perishability_from_path(cp: str) -> dict:
    cp_low = (cp or "").lower()
    if not cp_low:
        return {"shelf_days": 90, "can_freeze": False, "loss_rate_per_week": 0.05}
    if cp_low.startswith("produce"):
        if "salad" in cp_low or "lettuce" in cp_low or "spinach" in cp_low or "herb" in cp_low or "watercress" in cp_low:
            return {"shelf_days": 7, "can_freeze": False, "loss_rate_per_week": 0.20}
        if "berr" in cp_low or "grape" in cp_low:
            return {"shelf_days": 7, "can_freeze": True, "loss_rate_per_week": 0.20}
        if "fruit" in cp_low:
            return {"shelf_days": 7, "can_freeze": True, "loss_rate_per_week": 0.15}
        return {"shelf_days": 14, "can_freeze": True, "loss_rate_per_week": 0.10}
    if cp_low.startswith("dairy"):
        if "cheese" in cp_low and "cream" not in cp_low:
            return {"shelf_days": 60, "can_freeze": True, "loss_rate_per_week": 0.05}
        if "butter" in cp_low:
            return {"shelf_days": 90, "can_freeze": True, "loss_rate_per_week": 0.03}
        if "yogurt" in cp_low:
            return {"shelf_days": 21, "can_freeze": False, "loss_rate_per_week": 0.05}
        return {"shelf_days": 14, "can_freeze": True, "loss_rate_per_week": 0.10}
    if cp_low.startswith("meat & seafood"):
        return {"shelf_days": 4, "can_freeze": True, "loss_rate_per_week": 0.35}
    if cp_low.startswith("frozen"):
        return {"shelf_days": 365, "can_freeze": True, "loss_rate_per_week": 0.01}
    if cp_low.startswith("bakery"):
        return {"shelf_days": 6, "can_freeze": True, "loss_rate_per_week": 0.18}
    if cp_low.startswith("pantry"):
        if "spice" in cp_low or "seasoning" in cp_low or "extract" in cp_low: return {"shelf_days": 730, "can_freeze": False, "loss_rate_per_week": 0.005}
        if "canned" in cp_low: return {"shelf_days": 730, "can_freeze": False, "loss_rate_per_week": 0.01}
        if "pickle" in cp_low: return {"shelf_days": 365, "can_freeze": False, "loss_rate_per_week": 0.01}
        if "oil" in cp_low: return {"shelf_days": 365, "can_freeze": False, "loss_rate_per_week": 0.01}
        return {"shelf_days": 365, "can_freeze": False, "loss_rate_per_week": 0.02}
    if cp_low.startswith("snack") or cp_low.startswith("beverage"):
        return {"shelf_days": 180, "can_freeze": False, "loss_rate_per_week": 0.02}
    return {"shelf_days": 90, "can_freeze": False, "loss_rate_per_week": 0.05}


# --------- main ---------

def main():
    print("loading FNDDS macros…", file=sys.stderr)
    fndds_macros = {}
    with FNDDS.open() as f:
        for row in csv.DictReader(f):
            fndds_macros[(row.get("fndds_code") or "").strip()] = {
                "kcal":      float(row.get("energy_kcal") or 0),
                "protein_g": float(row.get("protein_g") or 0),
                "fat_g":     float(row.get("fat_g") or 0),
                "carb_g":    float(row.get("carbs_g") or 0),
                "fiber_g":   float(row.get("fiber_g") or 0),
                "sodium_mg": float(row.get("sodium_mg") or 0),
            }
    print(f"  {len(fndds_macros):,} fndds codes", file=sys.stderr)

    print("loading excluded UPCs…", file=sys.stderr)
    excl_upcs = set()
    excl_path = ROOT / "recipe_pricing" / "priced_products_excluded.csv"
    if excl_path.exists():
        with excl_path.open() as f:
            for row in csv.DictReader(f):
                u = (row.get("upc") or "").strip()
                if u: excl_upcs.add(u)
    print(f"  {len(excl_upcs):,} excluded upcs", file=sys.stderr)

    print("collecting recipe HTCs…", file=sys.stderr)
    recipe_htcs = set()
    with UNIFIED.open() as f:
        for row in csv.DictReader(f):
            h = (row.get("htc_code") or "").strip().lstrip("~")
            if h: recipe_htcs.add(h)
    print(f"  {len(recipe_htcs):,} distinct recipe htc_codes", file=sys.stderr)

    # Build htc → dominant canonical_path mapping by FRESH-encoding each
    # ingredient title in v2 taxonomy with its canonical_path. This guarantees
    # the bridge is consistent with the encoder's current behavior.
    print("building htc → recipe canonical_path bridge from v2 taxonomy…", file=sys.stderr)
    sys.path.insert(0, str(ROOT))
    from recipe_mapper.v1.htc.encoder import encode as _encode
    V2 = ROOT / "recipe_mapper" / "v1" / "output" / "recipe_ingredient_taxonomy_v2.csv"
    htc_path_counts: defaultdict = defaultdict(Counter)
    with V2.open() as f:
        for row in csv.DictReader(f):
            title = (row.get("title") or "").strip().lower()
            cp = (row.get("canonical_path") or "").strip()
            pif = (row.get("product_identity_fixed") or "").strip()
            if not title or not cp: continue
            h = _encode("", description=title, food_name=pif,
                          canonical_path=cp, identity_mode=False).code
            htc_path_counts[h][cp] += 1
    htc_to_recipe_path: dict[str, str] = {h: c.most_common(1)[0][0] for h, c in htc_path_counts.items()}
    print(f"  {len(htc_to_recipe_path):,} HTC → canonical_path mappings", file=sys.stderr)

    print("indexing priced_products by htc & family…", file=sys.stderr)
    con = sqlite3.connect(str(PRICED))
    cur = con.cursor()
    # Match against htc_form_code (encoded with identity_mode=False so positions
    # 5-7 carry form/processing/ptype). Whole vs sliced ham, ground vs whole
    # cinnamon, etc. all resolve to distinct codes.
    cur.execute("""
        SELECT REPLACE(htc_form_code,'~','') AS htc,
               cents, grams,
               consensus_fndds, consensus_canonical, name, upc
        FROM priced_products
        WHERE htc_form_code != '' AND grams > 0 AND cents > 0 AND available = 1
          AND consensus_canonical NOT LIKE 'Non-Food%'
    """)
    # Hard-coded keyword filters for clearly-wrong SKUs that slip through
    # priced_products' classification.
    BAD_NAME_PATTERNS = [
        "livestock", "poultry feed", "chicken feed", "feeding livestock",
        "for feeding", "bird seed", "wild bird", "deer feed", "horse feed",
        "fish food", "cat food", "dog food", "pet food", "supplement powder for pet",
        "candle", "fragrance", "soap", "shampoo", "detergent", "ice melt",
    ]
    by_htc: dict[str, list] = defaultdict(list)
    by_family: dict[str, list] = defaultdict(list)
    by_path: dict[str, list] = defaultdict(list)
    for htc, cents, grams, fndds, cp, name, upc in cur.fetchall():
        if upc in excl_upcs: continue
        nl = (name or "").lower()
        if any(b in nl for b in BAD_NAME_PATTERNS): continue
        rec = (cents, grams, cents/grams, fndds or "", cp or "", name or "", upc)
        if htc:
            by_htc[htc].append(rec)
            if len(htc) >= 4:
                by_family[htc[:4]].append(rec)
        if cp:
            by_path[cp].append(rec)
    print(f"  {len(by_htc):,} priced HTCs, {len(by_family):,} priced families, "
          f"{len(by_path):,} canonical_paths", file=sys.stderr)

    print("building HTC reference for each recipe HTC…", file=sys.stderr)
    out: dict[str, dict] = {}
    n_path = 0; n_exact = 0; n_family = 0; n_unmatched = 0
    for h in recipe_htcs:
        # Tier 1: form-aware HTC exact match (so whole ham vs sliced ham
        # actually resolve to different SKUs). Requires sufficient SKUs (>=2)
        # so single-SKU HTCs that may be miscategorized don't dominate.
        rows = by_htc.get(h)
        match_level = "htc_exact" if (rows and len(rows) >= 2) else None
        if not match_level: rows = None

        # Tier 2: recipe canonical_path fallback (broader pool)
        if not rows:
            recipe_path = htc_to_recipe_path.get(h, "")
            rows = by_path.get(recipe_path) if recipe_path else None
            if rows: match_level = "recipe_path"

        # Tier 3: family-level (4-char prefix)
        if not rows and len(h) >= 4:
            rows = by_family.get(h[:4])
            if rows: match_level = "htc_family"

        if not rows:
            n_unmatched += 1
            out[h] = {"match": "none", "macros": None, "price": None,
                      "food_group": "other", "protein_source": "none",
                      "perishability": {"shelf_days": 90, "can_freeze": False, "loss_rate_per_week": 0.05},
                      "allergens": [], "sample_canonical_path": recipe_path}
            continue

        # Median cents/g (more robust than cheapest, which often picks bridge errors).
        # Pick the SKU closest to median cents/g for representative pricing.
        sorted_rows = sorted(rows, key=lambda r: r[2])
        cheapest = sorted_rows[len(sorted_rows)//2]
        # Macros: pick the most common (cents-weighted) consensus_fndds in rows
        fndds_counter: Counter = Counter()
        path_counter: Counter = Counter()
        for cents, grams, cpg, fndds, cp, name, upc in rows:
            if fndds in fndds_macros:
                fndds_counter[fndds] += 1
            if cp: path_counter[cp] += 1
        macros = None
        if fndds_counter:
            best_fndds = fndds_counter.most_common(1)[0][0]
            macros = dict(fndds_macros[best_fndds])
            macros["sourced_via_fndds"] = best_fndds
        sample_path = path_counter.most_common(1)[0][0] if path_counter else (cheapest[4] or "")
        out[h] = {
            "match": match_level,
            "n_skus": len(rows),
            "macros": macros,           # kcal/protein/fat/carb/fiber/sodium per 100g
            "price": {
                "cents": cheapest[0], "grams": cheapest[1],
                "cents_per_gram": cheapest[2],
                "sku_name": cheapest[5], "sku_upc": cheapest[6],
            },
            "food_group": food_group_from_path(sample_path),
            "protein_source": protein_source_from_path(sample_path),
            "perishability": perishability_from_path(sample_path),
            "allergens": allergens_from_path(sample_path),
            "sample_canonical_path": sample_path,
        }
        if   match_level == "recipe_path": n_path += 1
        elif match_level == "htc_exact":   n_exact += 1
        else:                              n_family += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        json.dump(out, f)
    print(f"\n  recipe-path matches:  {n_path:,}", file=sys.stderr)
    print(f"  htc-exact matches:    {n_exact:,}", file=sys.stderr)
    print(f"  htc-family fallbacks: {n_family:,}", file=sys.stderr)
    print(f"  unmatched:            {n_unmatched:,}", file=sys.stderr)
    print(f"  → {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
