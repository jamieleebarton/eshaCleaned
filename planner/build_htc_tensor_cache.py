#!/usr/bin/env python3
"""Build a fresh HTC-native tensor cache for the Hestia planner.

Replaces the FNDDS-based pipeline with our HTC data:
  - recipe pool loaded from `recipe_htc_grams.json` (HTC-keyed)
  - PackageIndex sourced from `htc_reference.json` (HTC → cheapest SKU price+grams)
  - _classify_fndds_code monkey-patched to consult htc_reference's protein_source

Outputs into planner/data/tensor_cache/ (parallel to Hestia's prod cache).
"""
from __future__ import annotations
import json, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Resolve module data paths via env so we don't break the prod Hestia install
os.environ["HESTIA_BASE_PATH"] = str(ROOT)

import torch

import hestia.sparse_cascade as sc
import hestia.data_structures as ds
from hestia.plate_builder import PlateBuilder
from hestia.sparse_cascade import (
    SparseRecipeDatabase, IngredientIndex,
)

DATA = ROOT / "data"
HTC_REF_PATH = DATA / "htc_reference.json"
HTC_GRAMS_PATH = DATA / "recipe_htc_grams.json"
CACHE_DIR = DATA / "tensor_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ---------- Load HTC reference ----------
print("loading HTC reference…", flush=True)
with HTC_REF_PATH.open() as f:
    HTC_REF = json.load(f)
print(f"  {len(HTC_REF):,} HTC entries")

# Map protein_source string → integer code that planner expects (0–5, -1)
PROTEIN_SOURCE_INT = {
    "beef":    0, "lamb":   0,         # planner groups beef/lamb/veal
    "pork":    1,
    "poultry": 2,
    "fish":    3,
    "eggs":    4,
    "legumes": 5, "nuts": 5,
    "none":   -1,
}


# ---------- Monkey-patch the protein-source classifier ----------
_orig_classify_fndds = sc._classify_fndds_code
def _classify_htc_code(code: str) -> int:
    """HTC → protein_source int (0=beef, 1=pork, 2=poultry, 3=fish, 4=eggs,
    5=legumes/nuts, -1=other)."""
    code = (code or "").lstrip("~")
    ref = HTC_REF.get(code)
    if not ref:
        # Try family-level fallback (4-char prefix)
        if len(code) >= 4:
            for k in HTC_REF:
                if k[:4] == code[:4]:
                    ref = HTC_REF[k]
                    break
    if not ref:
        return -1
    return PROTEIN_SOURCE_INT.get(ref.get("protein_source") or "none", -1)

sc._classify_fndds_code = _classify_htc_code


# ---------- Patch PackageIndex to source from htc_reference ----------
_OrigPackageIndex = ds.PackageIndex
class HTCPackageIndex(_OrigPackageIndex):
    """PackageIndex that loads price/grams from htc_reference.json
    instead of food_packages_final.db. Drop-in compatible — packages_by_fndds
    is keyed by HTC code strings here."""
    def __init__(self, packages_csv=None, packages_db=None):
        # bypass parent __init__ — we populate our own structure
        self.packages_by_fndds = {}
        self.package_db_path = HTC_REF_PATH
        self.package_db_is_override = True
        for h, ref in HTC_REF.items():
            p = ref.get("price")
            if not p: continue
            cents = p.get("cents", 0)
            grams = p.get("grams", 0)
            if cents <= 0 or grams <= 0: continue
            price = cents / 100.0
            size_display = f"{grams:.0f}g"
            self.packages_by_fndds.setdefault(h, []).append((price, grams, size_display))
        for h in self.packages_by_fndds:
            self.packages_by_fndds[h].sort(key=lambda x: x[0]/x[1])
        n = sum(len(v) for v in self.packages_by_fndds.values())
        print(f"HTCPackageIndex: {len(self.packages_by_fndds)} HTCs, {n} packages")
        # GPU tensor placeholders
        self._gpu_tensors_built = False
        self._gpu_prices = None
        self._gpu_sizes = None
        self._gpu_option_prices = None

ds.PackageIndex = HTCPackageIndex


# ---------- Build recipe pool ----------
print("loading recipe HTC grams…", flush=True)
with HTC_GRAMS_PATH.open() as f:
    htc_grams_data = json.load(f)
titles = htc_grams_data["titles"]
htc_grams = htc_grams_data["htc_grams"]
print(f"  {len(htc_grams):,} recipes")

# Compute per-recipe macros + cost from the HTC reference
def per_recipe_totals(htc_dict: dict) -> dict:
    """Aggregate macros + cost across an htc_grams_dict using HTC_REF lookups."""
    kcal = protein = fat = carb = fiber = sodium = 0.0
    cost_cents = 0.0
    veg_g = fruit_g = dairy_g = grain_g = protein_g_food = 0.0
    total_mass = 0.0
    for htc, grams in htc_dict.items():
        ref = HTC_REF.get(htc)
        if not ref:
            # Family fallback
            if len(htc) >= 4:
                for k in HTC_REF:
                    if k[:4] == htc[:4]:
                        ref = HTC_REF[k]; break
        if not ref: continue
        m = ref.get("macros")
        if m:
            scale = grams / 100.0
            kcal    += m["kcal"]      * scale
            protein += m["protein_g"] * scale
            fat     += m["fat_g"]     * scale
            carb    += m["carb_g"]    * scale
            fiber   += m["fiber_g"]   * scale
            sodium  += m["sodium_mg"] * scale
        p = ref.get("price")
        if p and p.get("cents", 0) > 0 and p.get("grams", 0) > 0:
            cents_per_gram = p["cents"] / p["grams"]
            cost_cents += grams * cents_per_gram
        fg = ref.get("food_group", "")
        if fg == "vegetables": veg_g += grams
        elif fg == "fruits":   fruit_g += grams
        elif fg == "dairy":    dairy_g += grams
        elif fg == "grains":   grain_g += grams
        elif fg == "protein":  protein_g_food += grams
        total_mass += grams
    return dict(
        kcal=kcal, protein=protein, fat=fat, carb=carb, fiber=fiber, sodium=sodium,
        cost_cents=cost_cents,
        veg_g=veg_g, fruit_g=fruit_g, dairy_g=dairy_g, grain_g=grain_g,
        protein_food_g=protein_g_food, total_mass=total_mass,
    )

# Pull real category_number / serving counts from Hestia's recipes2.csv so
# template assignment produces breakfast/lunch/dinner distribution.
print("loading category_number map from Hestia recipes2.csv…", flush=True)
import csv as _csv
_csv.field_size_limit(2**30)
RECIPES2 = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")
cat_map: dict[int, str] = {}
serv_map: dict[int, int] = {}
with RECIPES2.open(encoding="utf-8", errors="replace") as f:
    for row in _csv.DictReader(f):
        try:
            rid = int(row.get("recipeNum") or 0)
        except: continue
        if rid == 0: continue
        cn = (row.get("category_number") or "").strip()
        if cn: cat_map[rid] = cn
        try:
            sv = int(float(row.get("servings.max") or 4))
        except: sv = 4
        serv_map[rid] = max(1, sv)
print(f"  {len(cat_map):,} category_numbers, {len(serv_map):,} serving counts")

# Recipe pool needs the same shape as Hestia's load_recipes returns
# (list of dicts with specific keys).
print("building recipe pool…", flush=True)
recipe_pool = []
for rid_str, htc_dict in htc_grams.items():
    rid = int(rid_str)
    totals = per_recipe_totals(htc_dict)
    if totals["total_mass"] <= 0: continue
    pool_row = {
        "recipeNum": rid,
        "recipeName": titles.get(rid_str) or f"Recipe {rid}",
        "fndds_grams_dict": htc_dict,    # planner reads this key; we feed HTC keys
        "total_mass_g": totals["total_mass"],
        "calories_total_kcal": totals["kcal"],
        "protein_total_g": totals["protein"],
        "carbs_total_g": totals["carb"],
        "fat_total_g": totals["fat"],
        "saturatedFat": 0.0, "fiber": totals["fiber"],
        "sodium": totals["sodium"], "cost": round(totals["cost_cents"]/100.0, 2),
        "totalMass": totals["total_mass"], "ndb_id": 0, "price": 0.0, "grams": totals["total_mass"],
        "cookingMinutes": 0, "prepMinutes": 0,
        "food_groups.vegetables_g": totals["veg_g"],
        "food_groups.fruit_g": totals["fruit_g"],
        "food_groups.dairy_g": totals["dairy_g"],
        "food_groups.grains_g": totals["grain_g"],
        "food_groups.protein_g": totals["protein_food_g"],
        "food_groups.fats_g": 0.0, "food_groups.other_g": 0.0,
        "vegetables_g": totals["veg_g"], "fruits_g": totals["fruit_g"],
        "grains_g": totals["grain_g"], "dairy_g": totals["dairy_g"],
        "protein_foods_g": totals["protein_food_g"],
        "fats_g": 0.0, "other_g": 0.0,
        "servings.max": serv_map.get(rid, 4), "servings.min": serv_map.get(rid, 4),
        "servings": serv_map.get(rid, 4),
        "calories_per_serving.max": int(totals["kcal"] / max(1, serv_map.get(rid, 4))) if totals["kcal"] else 0,
        "calories_per_serving.min": int(totals["kcal"] / max(1, serv_map.get(rid, 4))) if totals["kcal"] else 0,
        "category_number": cat_map.get(rid, ""),  # real FOODEX2 prefix from Hestia recipes2.csv
        "cuisine": [], "dietary_tags": [],
        "flavor_intensity": 3, "flavor_profile.bitter": 1, "flavor_profile.salty": 1,
        "flavor_profile.sour": 1, "flavor_profile.sweet": 1, "flavor_profile.umami": 1,
        "on_sale_items": {}, "non_sale_items": {}, "on_hand_items": [],
        "total_estimated_cost": round(totals["cost_cents"]/100.0, 2),
        "estimated_cost_sales_only": 0.0, "total_savings": 0.0, "saving_per": 0.0,
        "energy_density_kcal_per_100g": (totals["kcal"]/totals["total_mass"]*100) if totals["total_mass"] else 0.0,
        "kcal_est": totals["kcal"], "hedonic_score_heuristic": 30, "satiety_score_heuristic": 60,
        "gi_est": 50.0, "gi_confidence": 0.5, "gl_per_100g": 5.0, "gl_per_recipe": 50.0,
        "nutriscore_points": 0, "nutriscore_grade": "B",
        "sodium_total_mg": totals["sodium"], "potassium_total_mg": 0.0,
        "food_groups.vegetables_pct": (totals["veg_g"]/totals["total_mass"]*100) if totals["total_mass"] else 0,
        "food_groups.fruit_pct": (totals["fruit_g"]/totals["total_mass"]*100) if totals["total_mass"] else 0,
        "food_groups.dairy_pct": (totals["dairy_g"]/totals["total_mass"]*100) if totals["total_mass"] else 0,
        "food_groups.grains_pct": (totals["grain_g"]/totals["total_mass"]*100) if totals["total_mass"] else 0,
        "food_groups.protein_pct": (totals["protein_food_g"]/totals["total_mass"]*100) if totals["total_mass"] else 0,
        "food_groups.fats_pct": 0.0, "food_groups.other_pct": 0.0,
    }
    recipe_pool.append(pool_row)

print(f"  {len(recipe_pool):,} recipe pool entries built")

# ---------- Build tensors ----------
device = torch.device("cpu")
print("\nIndexing recipes through PlateBuilder…", flush=True)
plate_builder = PlateBuilder(
    templates_dir=str(ROOT / "assets" / "plate_templates_v2"),
)
plate_builder.index_recipes(recipe_pool)

print("\nBuilding IngredientIndex…", flush=True)
ingredient_index = IngredientIndex(device)
ingredient_index.build_from_recipes(recipe_pool)
print(f"  {ingredient_index.num_ingredients:,} unique HTC ingredients")

print("\nBuilding SparseRecipeDatabase from scratch…", flush=True)
recipe_db = SparseRecipeDatabase(
    recipe_pool, ingredient_index, plate_builder, device,
    use_cache=False,
)
print(f"  {recipe_db.num_recipes:,} recipes")

# ---------- Save cache ----------
recipe_cache_path = CACHE_DIR / "recipe_db_tensors.pt"
print(f"\nSaving recipe tensors → {recipe_cache_path}")
cache_data = {
    'recipe_ids': recipe_db.recipe_ids.cpu(),
    'ingredient_indices': recipe_db.ingredient_indices.cpu(),
    'ingredient_amounts': recipe_db.ingredient_amounts.cpu(),
    'nutrition': recipe_db.nutrition.cpu(),
    'food_groups': recipe_db.food_groups.cpu(),
    'servings': recipe_db.servings.cpu(),
    'nnz': recipe_db.nnz.cpu(),
    'protein_source': recipe_db.protein_source.cpu(),
    'ingredient_indices_flat': recipe_db.ingredient_indices_flat.cpu(),
    'packed_metadata': recipe_db.packed_metadata.cpu(),
    'gpu_recipe_id_to_idx': recipe_db.gpu_recipe_id_to_idx.cpu(),
    'gpu_recipe_to_template': recipe_db.gpu_recipe_to_template.cpu(),
    'gpu_recipe_is_one_dish': recipe_db.gpu_recipe_is_one_dish.cpu(),
    'gpu_side_compat': recipe_db.gpu_side_compat.cpu(),
    'is_fixed_portion': recipe_db.is_fixed_portion.cpu(),
    'sodium_per_serving': recipe_db.sodium_per_serving.cpu(),
    'recipe_names': recipe_db.names,
}
torch.save(cache_data, recipe_cache_path)
print(f"  {recipe_cache_path.stat().st_size/1024/1024:.1f} MB")

ing_cache_path = CACHE_DIR / "ingredient_index.pt"
torch.save({
    'fpid_to_idx': ingredient_index.fpid_to_idx,
    'idx_to_fpid': ingredient_index.idx_to_fpid,
    'num_ingredients': ingredient_index.num_ingredients,
}, ing_cache_path)
print(f"saved ingredient_index → {ing_cache_path}")

template_cache_path = CACHE_DIR / "template_tensors.pt"
try:
    torch.save({
        'meal_main_indices': {k: v.cpu() for k, v in recipe_db.meal_main_indices.items()},
        'meal_side_indices': {k: v.cpu() for k, v in recipe_db.meal_side_indices.items()},
        'template_to_sides': {k: v.cpu() for k, v in recipe_db.template_to_sides.items()},
        'template_to_side_pool_ids': {k: v.cpu() for k, v in recipe_db.template_to_side_pool_ids.items()},
    }, template_cache_path)
    print(f"saved template_tensors → {template_cache_path}")
except Exception as e:
    print(f"  WARNING: template save failed: {e}")

print("\nDONE")
