#!/usr/bin/env python3
"""Build the concept-keyed tensor cache.

Architecture:
  IngredientIndex keyed by priced concept_key strings
  PackageIndex carries ALL packages per concept (multi-package model)
  Recipe ingredient lines re-mapped via concept_resolution.json

Replaces the broken HTC-only build.
"""
from __future__ import annotations
from htc_groups import protein_source as htc_protein_source
import json, os, sys, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ["HESTIA_BASE_PATH"] = str(ROOT)
csv.field_size_limit(2**30)

import torch
import hestia.sparse_cascade as sc
import hestia.data_structures as ds
from htc_groups import patch_perishability_index as _patch_pi
_patch_pi(ds)
from hestia.plate_builder import PlateBuilder
from hestia.sparse_cascade import SparseRecipeDatabase, IngredientIndex
from household_free import household_free_decision

DATA = ROOT / "data"
CACHE_DIR = DATA / "tensor_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CI_PATH    = DATA / "concept_index.json"
RCG_PATH   = DATA / "recipe_concept_grams.json"
RES_PATH   = DATA / "concept_resolution.json"
HOUSEHOLD_FREE_AUDIT_PATH = DATA / "household_free_lines.csv"
HOUSEHOLD_FREE_SUMMARY_PATH = DATA / "household_free_summary.json"

# ---------- Load concept artifacts ----------
print("loading concept_index…", flush=True)
CI = json.loads(CI_PATH.read_text())
print(f"  {len(CI):,} priced concepts")
print("loading recipe_concept_grams…", flush=True)
RCG = json.loads(RCG_PATH.read_text())
print(f"  {len(RCG['concept_grams']):,} recipes")
print("loading concept_resolution…", flush=True)
RES = json.loads(RES_PATH.read_text())
print(f"  {len(RES):,} resolutions")

# ---------- Apply resolution: rewrite recipe concept_keys ----------
# For each recipe ingredient line, replace the recipe-side concept_key with
# its resolved priced concept_key. Lines marked NO_MATCH are dropped (planner
# treats those recipes as having a gap; macros/cost not computed for them).
print("applying resolution to recipe concepts…", flush=True)
resolved_recipes: dict[str, dict[str, float]] = {}
household_free_rows: list[dict[str, str | float]] = []
n_drop_lines = 0; n_keep_lines = 0; n_household_free_lines = 0
n_excluded_partial = 0; n_excluded_all_unresolved = 0
for rid, concepts in RCG["concept_grams"].items():
    new_d: dict[str, float] = {}
    dropped_this_recipe = 0
    for rk, grams in concepts.items():
        r = RES.get(rk, {})
        pk = r.get("priced_key")
        free_decision = household_free_decision(rk, pk)
        if free_decision.is_free:
            n_household_free_lines += 1
            household_free_rows.append({
                "recipe_id": rid,
                "recipe_concept_key": rk,
                "priced_concept_key": pk or "",
                "resolution_tier": r.get("tier") or "UNRESOLVED",
                "grams": float(grams),
                "status": "household_free",
                "reason": free_decision.reason,
            })
            continue
        if pk:
            new_d[pk] = new_d.get(pk, 0.0) + grams
            n_keep_lines += 1
        else:
            n_drop_lines += 1
            dropped_this_recipe += 1
    if dropped_this_recipe:
        if new_d:
            n_excluded_partial += 1
        else:
            n_excluded_all_unresolved += 1
        continue
    if new_d:
        resolved_recipes[rid] = new_d
print(f"  resolved line candidates: {n_keep_lines:,}")
print(f"  household-free lines ignored: {n_household_free_lines:,}")
print(f"  dropped lines: {n_drop_lines:,}")
print(f"  excluded recipes with partial unresolved concepts: {n_excluded_partial:,}")
print(f"  excluded recipes with no resolved concepts:        {n_excluded_all_unresolved:,}")
print(f"  recipes with all concepts resolved: {len(resolved_recipes):,}")
if household_free_rows:
    with HOUSEHOLD_FREE_AUDIT_PATH.open("w", newline="") as f:
        fieldnames = [
            "recipe_id",
            "recipe_concept_key",
            "priced_concept_key",
            "resolution_tier",
            "grams",
            "status",
            "reason",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(household_free_rows)
    HOUSEHOLD_FREE_SUMMARY_PATH.write_text(json.dumps({
        "status": "household_free_not_purchased",
        "rows": len(household_free_rows),
        "total_grams": round(sum(float(r["grams"]) for r in household_free_rows), 3),
        "audit_csv": str(HOUSEHOLD_FREE_AUDIT_PATH.relative_to(ROOT)),
    }, indent=2))
    print(f"  household-free audit: {HOUSEHOLD_FREE_AUDIT_PATH.relative_to(ROOT)}", flush=True)
titles = RCG["titles"]


# ---------- Patch protein-source classifier ----------
# Use the priced concept's canonical_path → protein bucket
CONCEPT_PROTEIN = {}
sc._classify_fndds_code = htc_protein_source



# ---------- ConceptPackageIndex: multiple packages per concept ----------
# Load recipe-leaf hints — these tell the adapter "for this priced concept,
# the recipes that map to it want SKUs whose names contain THESE tokens"
# (e.g. priced 'Dairy > Milk' might receive recipes asking for whole/skim/2%
# milk; the recipe-leaf tokens then guide which package ranks first).
_HINT_PATH = DATA / "priced_to_recipe_leaf.json"
HINTS: dict[str, list[str]] = {}
if _HINT_PATH.exists():
    HINTS = json.loads(_HINT_PATH.read_text())
print(f"loaded {len(HINTS):,} priced→recipe-leaf hints")

class ConceptPackageIndex(ds.PackageIndex):
    def __init__(self, packages_csv=None, packages_db=None):
        # Override parent — we own packages_by_fndds (keyed by concept_key)
        self.packages_by_fndds: dict[str, list[tuple[float, float, str]]] = {}
        self.package_db_path = CI_PATH
        self.package_db_is_override = True
        for ck, c in CI.items():
            hint_tokens = HINTS.get(ck, [])
            for pkg in c["packages"]:
                if pkg["cents"] >= 0 and pkg["grams"] > 0:
                    self.packages_by_fndds.setdefault(ck, []).append(
                        (pkg["cents"]/100.0, float(pkg["grams"]),
                         pkg.get("size_display") or f'{pkg["grams"]:.0f}g',
                         pkg["name"].lower()))
        # Rank: more recipe-leaf-token matches first, then cpg ASC.
        # When recipes ask for whole milk, "Whole Milk" SKUs surface above
        # "Skim Milk" SKUs at the same priced concept.
        for ck in self.packages_by_fndds:
            hints = HINTS.get(ck, [])
            def rank(p):
                nl = p[3]
                n_match = sum(1 for h in hints if h in nl) if hints else 0
                return (-n_match, p[0]/p[1])
            self.packages_by_fndds[ck].sort(key=rank)
            # Strip the temporary 4th field — parent expects 3-tuples
            self.packages_by_fndds[ck] = [
                (p[0], p[1], p[2]) for p in self.packages_by_fndds[ck]]
        n = sum(len(v) for v in self.packages_by_fndds.values())
        print(f"ConceptPackageIndex: {len(self.packages_by_fndds):,} concepts, {n:,} packages")
        self._gpu_tensors_built = False
        self._gpu_prices = None
        self._gpu_sizes = None
        self._gpu_option_prices = None

    def build_gpu_tensors(self, ingredient_index, device):
        import torch

        missing = [
            concept_key
            for concept_key in ingredient_index.fpid_to_idx
            if concept_key not in self.packages_by_fndds
        ]
        if missing:
            sample = "\n  ".join(sorted(missing)[:20])
            raise RuntimeError(
                "ConceptPackageIndex refuses to use PackageIndex fallback pricing. "
                f"{len(missing):,} concept keys have no real package data:\n  {sample}"
            )
        num_ingredients = ingredient_index.num_ingredients
        option_count = self.MAX_PACKAGE_OPTIONS
        prices = torch.zeros(num_ingredients, dtype=torch.float32, device=device)
        sizes = torch.ones(num_ingredients, dtype=torch.float32, device=device)
        option_prices = torch.zeros((num_ingredients, option_count), dtype=torch.float32, device=device)
        option_sizes = torch.ones((num_ingredients, option_count), dtype=torch.float32, device=device)

        for idx in range(num_ingredients):
            concept_key = ingredient_index.idx_to_fpid[idx]
            packages = self.packages_by_fndds[concept_key]
            first_price, first_size, _first_display = packages[0]
            prices[idx] = float(first_price)
            sizes[idx] = float(first_size)
            option_prices[idx, :] = float(first_price)
            option_sizes[idx, :] = float(first_size)

            seen_sizes: set[float] = set()
            selected: list[tuple[float, float, str]] = []
            for package in packages:
                price, grams, display = package
                rounded_size = round(float(grams), 3)
                if rounded_size in seen_sizes:
                    continue
                seen_sizes.add(rounded_size)
                selected.append(package)
                if len(selected) >= option_count:
                    break

            for opt_idx, (price, grams, _display) in enumerate(selected):
                option_prices[idx, opt_idx] = float(price)
                option_sizes[idx, opt_idx] = float(grams)

        self._gpu_prices = prices
        self._gpu_sizes = sizes
        self._gpu_option_prices = option_prices
        self._gpu_option_sizes = option_sizes
        self._gpu_tensors_built = True
        print(
            f"ConceptPackageIndex: Built GPU tensors for {num_ingredients:,} "
            "ingredients using real package data only"
        )
ds.PackageIndex = ConceptPackageIndex


# ---------- Build recipe pool with concept_keys as fpids ----------
print("loading recipes2.csv (categories, servings, food_groups, macros)…", flush=True)
RECIPES2 = Path("/Users/jamiebarton/Desktop/Hestia/api/data/recipes2.csv")

# Pass through these fields verbatim — Hestia's planner expects them, and they
# carry per-recipe FNDDS-derived nutrition the planner uses for compliance scoring.
RECIPES2_FIELDS = [
    "category_number",
    "servings.max", "servings.min",
    "calories_total_kcal", "protein_total_g", "carbs_total_g", "fat_total_g",
    "fiber", "sodium", "sodium_total_mg", "potassium_total_mg",
    "food_groups.vegetables_g", "food_groups.fruit_g",
    "food_groups.dairy_g",     "food_groups.grains_g",
    "food_groups.protein_g",   "food_groups.fats_g",
    "food_groups.other_g",
    "food_groups.vegetables_pct", "food_groups.fruit_pct",
    "food_groups.dairy_pct",     "food_groups.grains_pct",
    "food_groups.protein_pct",   "food_groups.fats_pct",
    "food_groups.other_pct",
    "vegetables_g", "fruits_g", "grains_g", "dairy_g", "protein_foods_g",
    "fats_g", "other_g",
    "energy_density_kcal_per_100g", "kcal_est",
    "hedonic_score_heuristic", "satiety_score_heuristic",
    "gi_est", "gi_confidence", "gl_per_100g", "gl_per_recipe",
    "nutriscore_points", "nutriscore_grade",
    "calories_per_serving.max", "calories_per_serving.min",
    "cuisine", "dietary_tags", "flavor_intensity",
    "flavor_profile.bitter", "flavor_profile.salty", "flavor_profile.sour",
    "flavor_profile.sweet", "flavor_profile.umami",
    "total_mass_g", "totalMass",
]
cat_map: dict[int, str] = {}
serv_map: dict[int, int] = {}
recipes2_fields_map: dict[int, dict] = {}
with RECIPES2.open(encoding="utf-8", errors="replace") as f:
    for row in csv.DictReader(f):
        try: rid = int(row.get("recipeNum") or 0)
        except: continue
        if rid == 0: continue
        cn = (row.get("category_number") or "").strip()
        if cn: cat_map[rid] = cn
        try: sv = int(float(row.get("servings.max") or 4))
        except: sv = 4
        serv_map[rid] = max(1, sv)
        # Stash the full passthrough payload
        rec_fields = {}
        for k in RECIPES2_FIELDS:
            v = row.get(k, "")
            if v in (None, ""): continue
            rec_fields[k] = v
        recipes2_fields_map[rid] = rec_fields
print(f"  {len(cat_map):,} category_numbers, {len(recipes2_fields_map):,} food_group payloads")


# Compute per-recipe macros from the picked SKU's own consensus_fndds.
# Load FNDDS lookup once.
print("loading FNDDS lookup…", flush=True)
FNDDS = ROOT.parent / "data" / "fndds" / "fndds_nutrient_lookup.csv"
fndds_macros = {}
with FNDDS.open() as f:
    for row in csv.DictReader(f):
        c = (row.get("fndds_code") or "").strip()
        if not c: continue
        fndds_macros[c] = {
            "kcal": float(row.get("energy_kcal") or 0),
            "protein": float(row.get("protein_g") or 0),
            "fat":     float(row.get("fat_g")     or 0),
            "carb":    float(row.get("carbs_g")   or 0),
            "fiber":   float(row.get("fiber_g")   or 0),
            "sodium":  float(row.get("sodium_mg") or 0),
        }
print(f"  {len(fndds_macros):,} fndds codes")


def per_recipe_totals(concept_dict: dict[str, float]) -> dict:
    """For each concept, use the cheapest package's consensus_fndds for macros.
    Sum scaled by recipe grams. NEVER pool macros across SKUs at one concept."""
    kcal = protein = fat = carb = fiber = sodium = 0.0
    cost_cents = 0.0
    veg_g = fruit_g = dairy_g = grain_g = protein_g_food = 0.0
    total_mass = 0.0
    for ck, grams in concept_dict.items():
        c = CI.get(ck)
        if not c or not c["packages"]: continue
        pkg = c["packages"][0]  # cheapest
        cpg = pkg["cents"] / pkg["grams"]
        cost_cents += grams * cpg
        # Macros from THIS SKU's fndds
        fndds = pkg.get("consensus_fndds")
        m = fndds_macros.get(fndds)
        if m:
            scale = grams / 100.0
            kcal    += m["kcal"]    * scale
            protein += m["protein"] * scale
            fat     += m["fat"]     * scale
            carb    += m["carb"]    * scale
            fiber   += m["fiber"]   * scale
            sodium  += m["sodium"]  * scale
        # HTC-positional food group classification — no path regex.
        # `c["htc_form"]` 8-char HTC; group code at position 0 maps to one of
        # vegetables/fruits/dairy/grains/protein/etc. See planner/htc_groups.py
        # The recipes2.csv overlay later supersedes these values for the pool;
        # this fallback fires only if recipes2.csv lacks a row for the recipe.
        from htc_groups import foodgroup as _fg
        fg = _fg(c.get("htc_form", ""))
        if   fg == "vegetables": veg_g += grams
        elif fg == "fruits":     fruit_g += grams
        elif fg == "dairy":      dairy_g += grams
        elif fg == "grains":     grain_g += grams
        elif fg == "protein":    protein_g_food += grams
        total_mass += grams
    return dict(
        kcal=kcal, protein=protein, fat=fat, carb=carb, fiber=fiber, sodium=sodium,
        cost_cents=cost_cents,
        veg_g=veg_g, fruit_g=fruit_g, dairy_g=dairy_g, grain_g=grain_g,
        protein_food_g=protein_g_food, total_mass=total_mass,
    )


print("building recipe pool…", flush=True)
recipe_pool = []
for rid_str, concepts in resolved_recipes.items():
    rid = int(rid_str)
    t = per_recipe_totals(concepts)
    if t["total_mass"] <= 0: continue
    sv = serv_map.get(rid, 4)
    pool_row = {
        "recipeNum": rid,
        "recipeName": titles.get(rid_str) or f"Recipe {rid}",
        "fndds_grams_dict": concepts,    # planner reads this — concept_keys here
        "total_mass_g": t["total_mass"],
        "calories_total_kcal": t["kcal"],
        "protein_total_g": t["protein"],
        "carbs_total_g": t["carb"], "fat_total_g": t["fat"],
        "fiber": t["fiber"], "sodium": t["sodium"],
        "cost": round(t["cost_cents"]/100.0, 2),
        "totalMass": t["total_mass"], "ndb_id": 0, "price": 0.0, "grams": t["total_mass"],
        "cookingMinutes": 0, "prepMinutes": 0, "saturatedFat": 0.0,
        "food_groups.vegetables_g": t["veg_g"],
        "food_groups.fruit_g": t["fruit_g"],
        "food_groups.dairy_g": t["dairy_g"],
        "food_groups.grains_g": t["grain_g"],
        "food_groups.protein_g": t["protein_food_g"],
        "food_groups.fats_g": 0.0, "food_groups.other_g": 0.0,
        "vegetables_g": t["veg_g"], "fruits_g": t["fruit_g"],
        "grains_g": t["grain_g"], "dairy_g": t["dairy_g"],
        "protein_foods_g": t["protein_food_g"], "fats_g": 0.0, "other_g": 0.0,
        "servings.max": sv, "servings.min": sv, "servings": sv,
        "calories_per_serving.max": int(t["kcal"]/max(1,sv)),
        "calories_per_serving.min": int(t["kcal"]/max(1,sv)),
        "category_number": cat_map.get(rid, ""),
        "cuisine": [], "dietary_tags": [],
        "flavor_intensity": 3,
        "flavor_profile.bitter": 1, "flavor_profile.salty": 1,
        "flavor_profile.sour": 1, "flavor_profile.sweet": 1, "flavor_profile.umami": 1,
        "on_sale_items": {}, "non_sale_items": {}, "on_hand_items": [],
        "total_estimated_cost": round(t["cost_cents"]/100.0, 2),
        "estimated_cost_sales_only": 0.0, "total_savings": 0.0, "saving_per": 0.0,
        "energy_density_kcal_per_100g": (t["kcal"]/t["total_mass"]*100) if t["total_mass"] else 0.0,
        "kcal_est": t["kcal"], "hedonic_score_heuristic": 30, "satiety_score_heuristic": 60,
        "gi_est": 50.0, "gi_confidence": 0.5, "gl_per_100g": 5.0, "gl_per_recipe": 50.0,
        "nutriscore_points": 0, "nutriscore_grade": "B",
        "sodium_total_mg": t["sodium"], "potassium_total_mg": 0.0,
        "food_groups.vegetables_pct": (t["veg_g"]/t["total_mass"]*100) if t["total_mass"] else 0,
        "food_groups.fruit_pct": (t["fruit_g"]/t["total_mass"]*100) if t["total_mass"] else 0,
        "food_groups.dairy_pct": (t["dairy_g"]/t["total_mass"]*100) if t["total_mass"] else 0,
        "food_groups.grains_pct": (t["grain_g"]/t["total_mass"]*100) if t["total_mass"] else 0,
        "food_groups.protein_pct": (t["protein_food_g"]/t["total_mass"]*100) if t["total_mass"] else 0,
        "food_groups.fats_pct": 0.0, "food_groups.other_pct": 0.0,
    }
    # Overlay recipes2.csv passthrough fields. Hestia's per-recipe nutrition +
    # food_groups come from FNDDS-derived totals there; trust them. We only
    # OVERRIDE cost (using our SKU pricing) and total_mass_g (already correct).
    r2 = recipes2_fields_map.get(rid)
    if r2:
        for k, v in r2.items():
            # numeric fields → float coerce; everything else passthrough
            if k in ("cuisine", "dietary_tags", "nutriscore_grade", "category_number"):
                pool_row[k] = v
                continue
            try: pool_row[k] = float(v)
            except (ValueError, TypeError): pool_row[k] = v
    recipe_pool.append(pool_row)
print(f"  {len(recipe_pool):,} recipes in pool")


# ---------- Build tensors ----------
device = torch.device("cpu")
print("\nIndexing recipes through PlateBuilder…", flush=True)
plate_builder = PlateBuilder(templates_dir=str(ROOT / "assets" / "plate_templates_v2"))
plate_builder.index_recipes(recipe_pool)

print("\nBuilding IngredientIndex…", flush=True)
ingredient_index = IngredientIndex(device)
ingredient_index.build_from_recipes(recipe_pool)
print(f"  {ingredient_index.num_ingredients:,} unique concept_keys")

print("\nBuilding SparseRecipeDatabase…", flush=True)
recipe_db = SparseRecipeDatabase(
    recipe_pool, ingredient_index, plate_builder, device, use_cache=False)
print(f"  {recipe_db.num_recipes:,} recipes")

# ---------- Save ----------
recipe_cache_path = CACHE_DIR / "recipe_db_tensors.pt"
torch.save({
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
}, recipe_cache_path)
print(f"saved {recipe_cache_path}")

torch.save({
    'fpid_to_idx': ingredient_index.fpid_to_idx,
    'idx_to_fpid': ingredient_index.idx_to_fpid,
    'num_ingredients': ingredient_index.num_ingredients,
}, CACHE_DIR / "ingredient_index.pt")

torch.save({
    'meal_main_indices': {k: v.cpu() for k, v in recipe_db.meal_main_indices.items()},
    'meal_side_indices': {k: v.cpu() for k, v in recipe_db.meal_side_indices.items()},
    'template_to_sides': {k: v.cpu() for k, v in recipe_db.template_to_sides.items()},
    'template_to_side_pool_ids': {k: v.cpu() for k, v in recipe_db.template_to_side_pool_ids.items()},
}, CACHE_DIR / "template_tensors.pt")

print("\nDONE")
