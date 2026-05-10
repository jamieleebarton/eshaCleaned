"""
Sparse Cascade Planner: Memory-efficient meal planning with sparse tensors.

Key insight: Recipes use ~12-20 of 3702 ingredients. Store sparsely.

Memory profile:
- Peak during scoring: ~900 MB (temporary)
- Sustained state: ~500 KB (pantries, selections)

Architecture:
1. SparseRecipeDatabase: All recipes stored once, sparsely
2. Two-phase scoring per meal: mains → filter → sides
3. Only top-K carried forward after each phase

# =============================================================================
# WARNING: DEAD CODE AND CONFIG GAPS (Dec 30, 2025)
# =============================================================================
#
# This file contains several features that are DEFINED but NEVER USED:
#
# 1. _compute_shadow_prices() - Lines ~1066-1129
#    - Full implementation of dynamic shadow pricing exists
#    - Method is NEVER CALLED anywhere
#    - Comments say "shadow price scoring" but code doesn't use it
#    - Working implementation exists in scoring.py (GPUBatchScorer)
#
# 2. ScoringConfig options - Only 6 of ~25 options are actually read
#    See scoring_config.py for the full list of dead options.
#
# 3. Side dish cost/pantry updates - Fixed but may need verification
#    Lines ~1997-2038 had bugs where sides were FREE (not added to cost,
#    not deducted from pantry). Fix exists in working tree.
#
# The net effect: The planner appears highly configurable but most "knobs"
# do nothing. Parameters like protein_density_value, pantry_usage_value,
# produce_value are hardcoded as constants instead of using config values.
#
# =============================================================================
"""

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import torch
import torch.nn.functional as F

import sys
BASE_PATH = "/workspace" if Path("/workspace/data/recipes.csv").exists() else str(Path(__file__).parent.parent)
sys.path.insert(0, BASE_PATH)
sys.path.insert(0, f"{BASE_PATH}/multi2")

from hestia.data_structures import (
    IngredientIndex, PackageIndex, NUM_SLOTS,
    HouseholdConfig, AttendanceSchedule, PerishabilityIndex, LEFTOVER_FIELDS,
    FROZEN_SHELF_DAYS, is_fresh_herb_fpid,
)
from hestia.plate_builder import PlateBuilder
from hestia.plate import Recipe
from hestia.scoring_config import ScoringConfig
from hestia.switcheroo.meal_repair import repair_plan, repair_with_leftover_substitution

# Constants
MAX_NNZ = 25  # Max ingredients per recipe (generous)
COOLDOWN_LEN = 256  # 6 weeks × 42 meals = 252, round up for variety enforcement
NUM_PROTEIN_SOURCES = 6  # beef=0, pork=1, poultry=2, fish=3, eggs=4, legumes=5

# Protein source codes (for tensor storage)
PROTEIN_SOURCE_CODES = {
    'beef': 0,
    'pork': 1,
    'poultry': 2,
    'fish': 3,
    'eggs': 4,
    'legumes': 5,
}
PROTEIN_SOURCE_NAMES = {v: k for k, v in PROTEIN_SOURCE_CODES.items()}


def _protein_targeting_overrides(config: ScoringConfig) -> Dict[str, Any]:
    """Return automatic scoring overrides for a requested protein percent."""
    prot_target = config.protein_pct_target
    if prot_target < 15 or not getattr(config, 'auto_protein_targeting', True):
        return {}

    overrides: Dict[str, Any] = {}
    if not config.enable_protein_density_bonus:
        overrides['enable_protein_density_bonus'] = True

    target_scale = max(0, (prot_target - 12.0) / 15.0)
    auto_density = max(config.protein_density_value, 3.0 + target_scale * 5.0)
    auto_macro_w = max(config.macro_deviation_weight, 0.15 + target_scale * 0.35)
    if config.protein_density_value < auto_density:
        overrides['protein_density_value'] = auto_density
    if config.macro_deviation_weight < auto_macro_w:
        overrides['macro_deviation_weight'] = auto_macro_w

    # Keep macro target separate from food-plan tier. A 35% weekly target should
    # not force every recipe through a hard protein floor; that collapses the
    # cheap egg/legume/pork pool before cost optimization can use it. Hard
    # filtering is reserved for configs that explicitly enable it, such as
    # high_protein mode.
    if prot_target >= 25 and config.macro_tolerance_pct > 3.0:
        overrides['macro_tolerance_pct'] = 3.0
    if config.enable_protein_prefilter:
        if prot_target >= 35 and config.protein_filter_margin < 8.0:
            overrides['protein_filter_margin'] = 8.0
        elif prot_target >= 25 and config.protein_filter_margin < 6.0:
            overrides['protein_filter_margin'] = 6.0
    return overrides


def _with_constructor_protein_target(
    config: ScoringConfig,
    protein_pct_target: float,
) -> ScoringConfig:
    """Apply legacy constructor protein target when config is still default."""
    if config.protein_pct_target == 15.0 and protein_pct_target != 15.0:
        return dc_replace(config, protein_pct_target=protein_pct_target)
    return config


def _classify_fndds_code(code: str) -> int:
    """Classify FNDDS food code to protein source. Returns int code (0-5) or -1.

    Derived directly from the FNDDS 2-digit food group prefix so the tensor
    cache never depends on an external protein_source_map.json file.

    beef=0, pork=1, poultry=2, fish=3, eggs=4, legumes=5
    """
    if len(code) < 2:
        return -1
    p2 = code[:2]
    if p2 in ('21', '23'):                      return 0  # beef / veal / lamb
    if p2 == '22':                              return 1  # pork
    if p2 == '24':                              return 2  # poultry (chicken, turkey)
    if p2 == '26':                              return 3  # fish / seafood
    if p2 in ('31', '32', '33', '34'):         return 4  # eggs
    if p2 == '41':                              # legumes / nuts / seeds subgroup
        p3 = code[:3] if len(code) >= 3 else ''
        p5 = code[:5] if len(code) >= 5 else ''
        if p3 in ('411', '412', '413'):         return 5  # beans / lentils / chickpeas
        if p5 in ('41416', '41421', '41440'):   return 5  # soy-based foods
        if p3 in ('418', '419'):                return 5  # peas (split, blackeyed)
    return -1


# ── Allergen → FNDDS prefix mapping ──────────────────────────────────────────
# Used to build per-request recipe masks so the planner never selects recipes
# containing ingredients the user is allergic to or excludes for religious/
# dietary reasons.  Prefixes match the USDA FNDDS 8-digit food code hierarchy.
ALLERGEN_FNDDS_PREFIXES: Dict[str, List[str]] = {
    # FDA Big-9 allergens
    "milk":       ["11", "12", "13", "14", "15"],     # Dairy (milk, cream, cheese, other, frozen desserts)
    "eggs":       ["31"],                              # Eggs and egg products
    "fish":       ["261", "262"],                      # Finfish (not shellfish)
    "shellfish":  ["263", "264"],                      # Crustaceans (shrimp, crab) + mollusks (clams, oysters, scallops)
    "tree_nuts":  ["4211", "4212", "4213", "4214",
                   "4215", "4216"],                    # Tree nuts (almond, cashew, walnut ...)
    "peanuts":    ["4210"],                            # Peanuts / peanut butter
    "wheat":      ["50", "51", "52", "53", "55"],     # Wheat (flour, breads, quick breads, cakes, pasta)
    "soy":        ["413"],                             # Soy products
    "soybeans":   ["413"],                             # Alias
    "sesame":     ["423"],                             # Sesame seeds
    # Meat exclusions (religious / cultural)
    "pork":       ["22"],                              # All pork
    "beef":       ["21"],                              # All beef
    "poultry":    ["24"],                              # All poultry (chicken, turkey ...)
    "red_meat":   ["21", "22", "23"],                  # Beef + pork + lamb
    # Aliases
    "dairy":      ["11", "12", "13", "14", "15"],     # Same as milk
    "gluten":     ["50", "51", "52", "53", "55"],     # Same as wheat
}

# Protein source cooldown configuration (meals before source can be used again)
# Higher = longer cooldown = less frequent selection
# Lower = shorter/no cooldown = encouraged for variety
PROTEIN_SOURCE_COOLDOWN = {
    'eggs': 3,      # Eggs in cooldown for 3 meals (common, cheap - limit it)
    'legumes': 3,   # Same for legumes
    'poultry': 2,   # Chicken OK every other meal
    'beef': 0,      # No cooldown - encourage beef!
    'pork': 0,      # No cooldown - encourage pork!
    'fish': 0,      # No cooldown - encourage fish!
}


def _env_path(name: str) -> Optional[Path]:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else None


def _coerce_recipe_id(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _tensor_cache_dir() -> Path:
    return _env_path("HESTIA_TENSOR_CACHE_DIR") or Path(BASE_PATH) / "data" / "tensor_cache"


def _recipes_csv_path() -> Path:
    return _env_path("HESTIA_RECIPES_CSV") or Path(BASE_PATH) / "data" / "recipes2.csv"


def _packages_db_path() -> Path:
    return _env_path("HESTIA_PACKAGES_DB") or Path(BASE_PATH) / "data" / "food_packages_final.db"


_INGREDIENT_META_CACHE: Optional[Dict[str, dict]] = None


def _ingredient_meta() -> Dict[str, dict]:
    global _INGREDIENT_META_CACHE
    if _INGREDIENT_META_CACHE is not None:
        return _INGREDIENT_META_CACHE

    path = _env_path("HESTIA_INGREDIENT_META_JSON")
    if not path or not path.exists():
        _INGREDIENT_META_CACHE = {}
        return _INGREDIENT_META_CACHE
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        _INGREDIENT_META_CACHE = loaded if isinstance(loaded, dict) else {}
    except Exception as exc:
        print(f"  [IngredientMeta] WARNING: could not load {path}: {exc}")
        _INGREDIENT_META_CACHE = {}
    return _INGREDIENT_META_CACHE


def _classify_ingredient_key(code: str) -> int:
    meta = _ingredient_meta().get(code) or {}
    source = str(meta.get("protein_source") or "").strip().lower()
    if source in PROTEIN_SOURCE_CODES:
        return PROTEIN_SOURCE_CODES[source]
    return _classify_fndds_code(code)


def _meta_allergen_key(allergen: str) -> str:
    aliases = {
        "dairy": "milk",
        "gluten": "wheat",
        "soybeans": "soy",
    }
    return aliases.get(allergen, allergen)

# Fruit snacks for automatic calorie gap filling
# fndds_code + fruit_g lets snacks flow into the shopping list
FRUIT_SNACKS = [
    {'name': 'Apple', 'calories': 95, 'fruit_g': 182, 'cost': 0.50, 'fndds_code': '63101000'},
    {'name': 'Orange juice (8oz)', 'calories': 110, 'fruit_g': 240, 'cost': 0.60, 'fndds_code': '61210000'},
    {'name': 'Banana', 'calories': 105, 'fruit_g': 118, 'cost': 0.25, 'fndds_code': '63107010'},
    {'name': 'Blueberries (1 cup)', 'calories': 85, 'fruit_g': 150, 'cost': 1.50, 'fndds_code': '63203010'},
    {'name': 'Orange', 'calories': 62, 'fruit_g': 131, 'cost': 0.40, 'fndds_code': '61119010'},
]

# =============================================================================
# DYNAMIC SERVINGS: Fixed-portion recipe detection
# =============================================================================
# These recipes are inherently single-serve or fixed-portion and should NOT
# have dynamic serving calculation applied. They keep their original servings.

FIXED_PORTION_KEYWORDS = frozenset([
    # Sandwiches/handheld items
    'sandwich', 'burger', 'hamburger', 'wrap', 'sub', 'hoagie', 'panini',
    'taco', 'burrito', 'quesadilla', 'enchilada', 'hot dog', 'hotdog',
    'calzone', 'stromboli', 'pita', 'gyro', 'falafel',
    # Individual baked items
    'cookie', 'cupcake', 'muffin', 'donut', 'doughnut', 'bagel',
    'roll', 'biscuit', 'scone', 'danish', 'croissant', 'bun', 'pretzel',
    # Dumplings/filled items
    'dumpling', 'wonton', 'pierogi', 'gyoza', 'potsticker',
    'samosa', 'empanada', 'egg roll', 'spring roll', 'ravioli',
    # Individual portions
    'wing', 'drumstick', 'slider', 'nugget', 'patty',
    'deviled egg',
    # Pancakes/waffles (individual items)
    'pancake', 'waffle', 'crepe', 'french toast',
    # Pizza (individual slices)
    'pizza',
    # Bars/brownies (pre-cut)
    'brownie', 'blondie', 'bar',
    # Candy/confections
    'truffle', 'bonbon', 'praline', 'candy', 'fudge',
    # Meat cuts (discrete portions)
    'steak', 'chop', 'breast', 'filet', 'fillet',
    'kabob', 'kebab', 'skewer', 'cutlet', 'thigh',
])


def is_fixed_portion_recipe(recipe_name: str) -> bool:
    """
    Check if a recipe is inherently fixed-portion (should not use dynamic servings).

    Fixed-portion recipes are things like sandwiches, cookies, tacos - where
    "1 serving = 1 item" makes sense and can't be arbitrarily divided.

    Args:
        recipe_name: The recipe name to check

    Returns:
        True if recipe should keep original servings, False if dynamic servings OK
    """
    return get_serving_unit(recipe_name) is not None


_SHORT_KW_RE = {}  # lazily compiled word-boundary patterns for short keywords

def get_serving_unit(recipe_name: str) -> 'Optional[str]':
    """Return the discrete serving unit if fixed-portion, else None.

    The returned keyword (e.g. "roll", "cookie", "steak") is the unit
    that the iOS app pluralizes for display ("2 rolls", "1 steak").
    Short keywords (<=3 chars) use word-boundary matching to avoid
    false positives like "bar" in "barley".
    """
    import re
    name_lower = recipe_name.lower()
    for keyword in FIXED_PORTION_KEYWORDS:
        if len(keyword) <= 3:
            # Word-boundary match for short keywords (also matches plural "bars")
            if keyword not in _SHORT_KW_RE:
                _SHORT_KW_RE[keyword] = re.compile(r'\b' + re.escape(keyword) + r's?\b')
            if _SHORT_KW_RE[keyword].search(name_lower):
                return keyword
        else:
            if keyword in name_lower:
                return keyword
    return None


@dataclass
class TemplateInfo:
    """Pre-computed template information."""
    template_id: int
    name: str
    meal_type: str  # breakfast, lunch, dinner
    is_one_dish: bool
    main_indices: torch.Tensor  # Indices into recipe database
    side_indices: torch.Tensor  # Indices into recipe database (empty if one_dish)


class SparseRecipeDatabase:
    """
    Stores all recipes in sparse format on GPU.

    Instead of [N, 3702] dense ingredient matrix,
    stores [N, MAX_NNZ] indices + [N, MAX_NNZ] amounts.

    Memory: ~26 MB for 300k recipes (vs 2.5 GB dense)

    PERFORMANCE: Uses prebuilt tensor cache if available to avoid 4.5GB memory spike
    when building from CSV. Cache is at data/tensor_cache/recipe_db_tensors.pt.

    For minimal memory usage when cache exists, use:
        recipe_db = SparseRecipeDatabase.from_cache(device)
    """

    @classmethod
    def from_cache(cls, device: torch.device, plate_builder=None) -> 'SparseRecipeDatabase':
        """
        Create SparseRecipeDatabase from cache without loading recipe CSV.

        This is the memory-efficient way to create the database when cache exists.
        Avoids the 4.5GB memory spike from CSV parsing and PlateBuilder indexing.

        Args:
            device: torch device
            plate_builder: optional pre-indexed PlateBuilder (needed for template rebuild)

        Returns:
            SparseRecipeDatabase instance

        Raises:
            FileNotFoundError: If cache doesn't exist
        """
        cache_dir = _tensor_cache_dir()
        cache_path = cache_dir / "recipe_db_tensors.pt"
        if not cache_path.exists():
            raise FileNotFoundError(
                f"Cache not found at {cache_path}. "
                f"Run: python multi2/build_tensor_cache.py"
            )

        ingredient_cache_path = cache_dir / "ingredient_index.pt"

        # === STALENESS CHECK ===
        # Hash source files and compare to cached hash. If stale, warn loudly.
        import hashlib
        def _hash_file(p):
            h = hashlib.sha256()
            with open(p, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    h.update(chunk)
            return h.hexdigest()[:16]

        source_files = {
            'recipes': _recipes_csv_path(),
            'packages_db': _packages_db_path(),
            'recipe_qa': Path(BASE_PATH) / "data" / "recipe_qa.db",
        }
        current_hashes = {}
        for name, path in source_files.items():
            if path.exists():
                current_hashes[name] = _hash_file(str(path))

        skip_staleness_check = os.environ.get("HESTIA_SKIP_TENSOR_STALENESS_CHECK", "").lower() in {
            "1",
            "true",
            "yes",
        }

        # Check cached hashes. Shadow/package A-B runs can opt out when the
        # checkout is intentionally read-only; normal startup keeps the guard.
        hash_path = cache_dir / "source_hashes.json"
        if skip_staleness_check:
            print("Skipping tensor source staleness check (HESTIA_SKIP_TENSOR_STALENESS_CHECK=1)")
        elif hash_path.exists():
            import json
            with open(hash_path) as f:
                cached_hashes = json.load(f)
            stale = []
            for name, current in current_hashes.items():
                cached = cached_hashes.get(name)
                if cached and cached != current:
                    stale.append(name)
            if stale:
                # Auto-rebuild what we can, error on what we can't
                can_auto = {'packages_db', 'recipe_qa'}
                needs_full = {'recipes'}
                auto_stale = [s for s in stale if s in can_auto]
                full_stale = [s for s in stale if s in needs_full]

                if full_stale:
                    raise RuntimeError(
                        f"\n{'!'*60}\n"
                        f"  TENSOR CACHE IS STALE!\n"
                        f"  Changed: {', '.join(full_stale)}\n"
                        f"  This requires a full tensor rebuild.\n"
                        f"  Run: python scripts/build_tensor_cache.py\n"
                        f"{'!'*60}"
                    )

                if auto_stale:
                    print(f"\n{'='*60}")
                    print(f"  Source data changed: {', '.join(auto_stale)}")
                    print(f"  Auto-rebuilding affected tensor caches...")
                    print(f"{'='*60}")

                    if 'packages_db' in auto_stale:
                        # Rebuild package_index.pt from the DB
                        from hestia.data_structures import PackageIndex as _PI
                        _pi = _PI()
                        _tmp_ing = IngredientIndex(torch.device('cpu'))
                        if ingredient_cache_path.exists():
                            _ci = torch.load(str(ingredient_cache_path), map_location='cpu', weights_only=False)
                            _tmp_ing.fpid_to_idx = _ci['fpid_to_idx']
                            _tmp_ing.idx_to_fpid = _ci['idx_to_fpid']
                            _tmp_ing.num_ingredients = _ci['num_ingredients']
                        _pi.build_gpu_tensors(_tmp_ing, torch.device('cpu'))
                        torch.save({
                            'prices': _pi._gpu_prices,
                            'sizes': _pi._gpu_sizes,
                            'option_prices': _pi._gpu_option_prices,
                            'option_sizes': _pi._gpu_option_sizes,
                            'package_shelf_life_days': _pi._gpu_package_shelf_life_days,
                            'package_starts_frozen': _pi._gpu_package_starts_frozen,
                            'option_shelf_life_days': _pi._gpu_option_shelf_life_days,
                            'option_starts_frozen': _pi._gpu_option_starts_frozen,
                        }, str(cache_dir / "package_index.pt"))
                        print(f"  Rebuilt package_index.pt from food_packages_final.db")

                    # Update hashes after rebuild
                    import json as _json
                    with open(hash_path, 'w') as f:
                        _json.dump(current_hashes, f, indent=2)
                    print(f"  Updated source hashes")
                    print(f"{'='*60}\n")
        else:
            # First run - save current hashes
            import json
            with open(hash_path, 'w') as f:
                json.dump(current_hashes, f, indent=2)
            print(f"Saved source hashes to {hash_path}")

        # Use provided PlateBuilder or create minimal one (just templates, no recipes)
        if plate_builder is None:
            plate_builder = PlateBuilder()  # Just reads template JSONs

        # Load IngredientIndex from cache
        ingredient_index = IngredientIndex(device)
        if ingredient_cache_path.exists():
            cached_ing = torch.load(ingredient_cache_path, map_location='cpu', weights_only=False)
            ingredient_index.fpid_to_idx = cached_ing['fpid_to_idx']
            ingredient_index.idx_to_fpid = cached_ing['idx_to_fpid']
            ingredient_index.num_ingredients = cached_ing['num_ingredients']
            print(f"Loaded IngredientIndex from cache: {ingredient_index.num_ingredients} ingredients")

        # Create instance with empty recipe_pool - cache will be used
        instance = cls([], ingredient_index, plate_builder, device,
                       use_cache=True)
        return instance

    def __init__(
        self,
        recipe_pool: List[Dict],
        ingredient_index: IngredientIndex,
        plate_builder: PlateBuilder,
        device: torch.device,
        use_cache: bool = True,  # Try to load from tensor cache
    ):
        self.device = device
        self.ingredient_index = ingredient_index
        self.plate_builder = plate_builder
        self.num_ingredients = ingredient_index.num_ingredients if ingredient_index else 0

        # Check for prebuilt tensor cache first
        cache_path = _tensor_cache_dir() / "recipe_db_tensors.pt"
        if use_cache and cache_path.exists():
            if self._load_from_cache(cache_path, plate_builder):
                return  # Successfully loaded from cache

        print("Building sparse recipe database...")

        # Get all unique recipes from plate builder
        all_recipes_raw = plate_builder.all_recipes
        if not all_recipes_raw:
            raise RuntimeError(
                "Cannot build recipe database: no recipes indexed. "
                "Cache load failed and plate_builder has no recipes. "
                "Ensure tensor cache is valid or provide recipes2.csv."
            )

        # === SANITY FILTERS ===
        # Exclude garbage recipes that would break the planner
        # These are typically data entry errors (e.g., 1.3 million grams of chickpeas)
        MAX_CALORIES = 20000       # No recipe should have 20k+ calories
        MAX_TOTAL_MASS_G = 20000   # No recipe should weigh 20+ kg
        MAX_CAL_PER_SERVING = 3000 # No serving should exceed 3000 cal
        MIN_CAL_PER_SERVING = 50   # No serving under 50 cal (excludes condiments/enhancers)
        MAX_SERVINGS = 50          # No recipe should make 50+ servings (excludes industrial batches)

        valid_recipes = []
        filtered_out = {'calories': 0, 'mass': 0, 'cal_per_serving': 0, 'low_cal': 0, 'high_servings': 0}

        for recipe in all_recipes_raw:
            total_cal = (recipe.calories or 0) * (recipe.servings_produced or 1)
            cal_per_srv = recipe.calories or 0
            servings = recipe.servings_produced or 1
            total_mass = sum(recipe.ingredient_needs.values()) * servings

            if total_cal > MAX_CALORIES:
                filtered_out['calories'] += 1
            elif total_mass > MAX_TOTAL_MASS_G:
                filtered_out['mass'] += 1
            elif cal_per_srv > MAX_CAL_PER_SERVING:
                filtered_out['cal_per_serving'] += 1
            elif cal_per_srv < MIN_CAL_PER_SERVING:
                filtered_out['low_cal'] += 1
            elif servings > MAX_SERVINGS:
                filtered_out['high_servings'] += 1
            else:
                valid_recipes.append(recipe)

        all_recipes = valid_recipes
        total_filtered = sum(filtered_out.values())
        if total_filtered > 0:
            print(f"  Filtered {total_filtered:,} garbage recipes:")
            print(f"    - {filtered_out['calories']} with >20k calories")
            print(f"    - {filtered_out['mass']} with >20kg mass")
            print(f"    - {filtered_out['cal_per_serving']} with >3k cal/serving")
            print(f"    - {filtered_out['low_cal']} with <50 cal/serving (condiments)")
            print(f"    - {filtered_out['high_servings']} with >50 servings (industrial)")

        self.num_recipes = len(all_recipes)
        print(f"  Total recipes: {self.num_recipes:,}")

        # Build recipe ID to index mapping
        self.recipe_id_to_idx: Dict[int, int] = {}
        for idx, recipe in enumerate(all_recipes):
            self.recipe_id_to_idx[recipe.recipe_num] = idx

        # Build on CPU first (MUCH faster than individual GPU writes)
        print("  Building CPU tensors...", flush=True)
        import numpy as np

        recipe_ids_np = np.zeros(self.num_recipes, dtype=np.int32)
        ingredient_indices_np = np.zeros((self.num_recipes, MAX_NNZ), dtype=np.int16)
        ingredient_amounts_np = np.zeros((self.num_recipes, MAX_NNZ), dtype=np.float16)
        nutrition_np = np.zeros((self.num_recipes, 4), dtype=np.float16)  # [cal, protein, carbs, fat]
        food_groups_np = np.zeros((self.num_recipes, 7), dtype=np.float16)  # [veg, fruit, grains, dairy, protein_foods, fats, other]
        servings_np = np.zeros(self.num_recipes, dtype=np.float16)
        nnz_np = np.zeros(self.num_recipes, dtype=np.int16)
        protein_source_np = np.full(self.num_recipes, -1, dtype=np.int8)  # -1 = no protein source
        self.names: List[str] = []

        # protein_source is derived from FNDDS ingredient codes (no external file needed)

        # Fill in recipe data on CPU
        for idx, recipe in enumerate(all_recipes):
            if idx % 100000 == 0:
                print(f"    {idx:,}/{self.num_recipes:,}...", flush=True)

            recipe_ids_np[idx] = recipe.recipe_num
            self.names.append(recipe.recipe_name)

            # Sparse ingredients
            ing_list = list(recipe.ingredient_needs.items())[:MAX_NNZ]
            for j, (fpid, grams) in enumerate(ing_list):
                ing_idx = ingredient_index.fpid_to_idx.get(fpid)
                if ing_idx is not None:
                    ingredient_indices_np[idx, j] = ing_idx
                    ingredient_amounts_np[idx, j] = grams
            nnz_np[idx] = len(ing_list)

            # Nutrition
            nutrition_np[idx, 0] = recipe.calories or 0
            nutrition_np[idx, 1] = recipe.protein or 0
            nutrition_np[idx, 2] = recipe.carbs or 0
            nutrition_np[idx, 3] = recipe.fat or 0

            # Food groups (grams per serving)
            food_groups_np[idx, 0] = recipe.vegetables_g or 0
            food_groups_np[idx, 1] = recipe.fruits_g or 0
            food_groups_np[idx, 2] = recipe.grains_g or 0
            food_groups_np[idx, 3] = recipe.dairy_g or 0
            food_groups_np[idx, 4] = recipe.protein_foods_g or 0
            food_groups_np[idx, 5] = recipe.fats_g or 0
            food_groups_np[idx, 6] = recipe.other_g or 0

            # Servings
            servings_np[idx] = recipe.servings_produced or 4

            # Protein source: classify from dominant ingredient by grams (no external file)
            best_protein_grams = 0.0
            best_protein_code = -1
            for fpid, grams in ing_list:
                src = _classify_ingredient_key(str(fpid))
                if src >= 0 and grams > best_protein_grams:
                    best_protein_grams = grams
                    best_protein_code = src
            protein_source_np[idx] = best_protein_code

        # Transfer to GPU in one shot
        print("  Transferring to GPU...", flush=True)
        self.recipe_ids = torch.from_numpy(recipe_ids_np).to(device)
        self.ingredient_indices = torch.from_numpy(ingredient_indices_np).to(device)
        self.ingredient_amounts = torch.from_numpy(ingredient_amounts_np).to(device)
        self.nutrition = torch.from_numpy(nutrition_np).to(device)
        self.food_groups = torch.from_numpy(food_groups_np).to(device)  # [veg, fruit, grains, dairy, protein_foods]
        self.servings = torch.from_numpy(servings_np).to(device)
        self.nnz = torch.from_numpy(nnz_np).to(device)
        self.protein_source = torch.from_numpy(protein_source_np).to(device)  # -1 = no protein

        # === CRITICAL: Build reverse mapping recipe_id -> db_idx for leftover consumption ===
        # gpu_side_compat is indexed by db_idx, but leftovers store recipe_ids
        # Without this mapping, category_match in leftover consumption would use wrong indices
        max_recipe_id = int(recipe_ids_np.max()) + 1
        gpu_recipe_id_to_idx_np = np.full(max_recipe_id, -1, dtype=np.int32)
        for idx in range(self.num_recipes):
            rid = int(recipe_ids_np[idx])
            gpu_recipe_id_to_idx_np[rid] = idx
        self.gpu_recipe_id_to_idx = torch.from_numpy(gpu_recipe_id_to_idx_np).to(device)
        print(f"  Built recipe_id -> db_idx mapping ({max_recipe_id:,} entries, {max_recipe_id * 4 / 1024 / 1024:.1f} MB)")

        # === PERFORMANCE: Pre-flatten indices for hot path ===
        # Avoids repeated .long().flatten() calls that allocate memory
        self.ingredient_indices_flat = self.ingredient_indices.long().flatten()  # [N * MAX_NNZ]

        # === DYNAMIC SERVINGS: Pre-compute total calories and fixed-portion mask ===
        # total_calories = cal_per_srv × servings (total recipe calories)
        # is_fixed_portion = True for recipes that shouldn't use dynamic servings
        self.total_calories = self.nutrition[:, 0] * self.servings.float()  # [N]

        # Build fixed-portion mask from recipe names
        is_fixed_np = np.zeros(self.num_recipes, dtype=np.bool_)
        for idx, name in enumerate(self.names):
            is_fixed_np[idx] = is_fixed_portion_recipe(name)
        self.is_fixed_portion = torch.from_numpy(is_fixed_np).to(device)
        fixed_count = is_fixed_np.sum()
        print(f"  Fixed-portion recipes: {fixed_count:,} ({fixed_count/self.num_recipes*100:.1f}%)")

        # === PERFORMANCE: Pack metadata for single gather ===
        # Combines servings, nutrition, food_groups into one tensor
        # Old: 5 separate gathers per recipe selection = 5 kernel launches
        # New: 1 gather + slice = 1 kernel launch
        # Layout: [servings(1), nutrition(4), food_groups(7)] = 12 columns
        self.packed_metadata = torch.cat([
            self.servings.unsqueeze(1),      # [N, 1]
            self.nutrition,                   # [N, 4] (cal, prot, carbs, fat)
            self.food_groups,                 # [N, 7] (veg, fruit, grains, dairy, protein, fats, other)
        ], dim=1).float()  # [N, 12]

        # Count protein source distribution
        source_counts = {k: (self.protein_source == v).sum().item() for k, v in PROTEIN_SOURCE_CODES.items()}
        classified = sum(source_counts.values())
        print(f"  Protein sources: {classified:,} classified ({source_counts})")

        # Initialize product tracking (no products until inject_products() called)
        self.is_product = torch.zeros(self.num_recipes, dtype=torch.bool, device=device)
        self.fndds_group = torch.zeros(self.num_recipes, dtype=torch.int32, device=device)
        self.product_metadata = []
        self.product_id_offset = 1_000_000

        # === SODIUM PER SERVING: Load from CSV and map by recipe_num ===
        sodium_per_serving_np = np.zeros(self.num_recipes, dtype=np.float32)
        try:
            import csv as csv_module
            csv_path = _recipes_csv_path()
            if csv_path.exists():
                sodium_by_id = {}
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv_module.DictReader(f)
                    for row in reader:
                        rid = int(row.get('recipeNum', 0) or 0)
                        na = float(row.get('sodium_total_mg', 0) or 0)
                        srv_min = float(row.get('servings.min', 1) or 1)
                        srv_max = float(row.get('servings.max', srv_min) or srv_min)
                        avg_srv = max((srv_min + srv_max) / 2, 1)
                        sodium_by_id[rid] = na / avg_srv
                for idx in range(self.num_recipes):
                    rid = int(recipe_ids_np[idx])
                    sodium_per_serving_np[idx] = sodium_by_id.get(rid, 0)
                n_with_sodium = sum(1 for x in sodium_per_serving_np if x > 0)
                print(f"  Sodium per serving: loaded for {n_with_sodium:,} recipes")
        except Exception as e:
            print(f"  WARNING: Could not load sodium data: {e}")
        self.sodium_per_serving = torch.from_numpy(sodium_per_serving_np).to(device)

        print(f"  Sparse storage: {self._memory_usage():.1f} MB")

        # Build template index (pure category-based pools)
        self._build_template_index()

        # Load verdicts + meal fitness (always — independent of pool strategy)
        verdicts, meal_ok = self._load_recipe_verdicts()
        if verdicts:
            self._build_verdict_penalties(verdicts)
            self._build_meal_fitness(meal_ok)
        else:
            self.gpu_verdict_penalty = torch.zeros(self.num_recipes, device=self.device)
            self.gpu_meal_ok = torch.ones(self.num_recipes, 3, dtype=torch.bool, device=self.device)

    def _load_from_cache(self, cache_path: Path, plate_builder: PlateBuilder) -> bool:
        """
        Load recipe database from prebuilt tensor cache.

        Returns True if successfully loaded, False to fall back to building from scratch.

        The cache saves ~4GB memory spike by avoiding:
        1. CSV parsing into DataFrame (~2GB)
        2. DataFrame.to_dict() conversion (~2GB)
        3. numpy array building (~500MB temporary)

        IMPORTANT: The cache should be built with the same filtering criteria
        (MIN_CAL_PER_SERVING=50, MAX_CAL_PER_SERVING=3000, etc.) to match
        the live build. If cache was built without filtering, this method
        still works but may include low-quality recipes.
        """
        try:
            print(f"Loading sparse recipe database from cache: {cache_path}")

            # Load cached tensors (directly to target device)
            cached = torch.load(cache_path, map_location=self.device, weights_only=False)

            # Required keys in cache
            required_keys = [
                'recipe_ids', 'ingredient_indices', 'ingredient_amounts',
                'nutrition', 'food_groups', 'servings', 'nnz', 'protein_source',
                'ingredient_indices_flat', 'packed_metadata', 'gpu_recipe_id_to_idx',
                'gpu_recipe_to_template', 'gpu_recipe_is_one_dish', 'gpu_side_compat',
            ]

            # Check all required keys exist
            for key in required_keys:
                if key not in cached:
                    print(f"  Cache missing key '{key}', falling back to build")
                    return False

            # Load core tensors
            self.recipe_ids = cached['recipe_ids'].to(self.device)
            self.ingredient_indices = cached['ingredient_indices'].to(self.device)
            self.ingredient_amounts = cached['ingredient_amounts'].to(self.device)
            self.nutrition = cached['nutrition'].to(self.device)
            self.food_groups = cached['food_groups'].to(self.device)
            self.servings = cached['servings'].to(self.device)
            self.nnz = cached['nnz'].to(self.device)
            self.protein_source = cached['protein_source'].to(self.device)
            self.ingredient_indices_flat = cached['ingredient_indices_flat'].to(self.device)
            self.packed_metadata = cached['packed_metadata'].to(self.device)
            self.gpu_recipe_id_to_idx = cached['gpu_recipe_id_to_idx'].to(self.device)

            # Template-related GPU tensors
            self.gpu_recipe_to_template = cached['gpu_recipe_to_template'].to(self.device)
            self.gpu_recipe_is_one_dish = cached['gpu_recipe_is_one_dish'].to(self.device)
            self.gpu_side_compat = cached['gpu_side_compat'].to(self.device)

            self.num_recipes = len(self.recipe_ids)

            # Build recipe_id_to_idx mapping (needed for leftover tracking etc.)
            # This is fast: just iterate recipe_ids tensor
            self.recipe_id_to_idx: Dict[int, int] = {}
            recipe_ids_cpu = self.recipe_ids.cpu().numpy()
            for idx, rid in enumerate(recipe_ids_cpu):
                self.recipe_id_to_idx[int(rid)] = idx

            # Load recipe names from cache if available
            if 'recipe_names' in cached:
                self.names: List[str] = cached['recipe_names']
            else:
                # Fallback to placeholders
                self.names: List[str] = [f"Recipe_{i}" for i in range(self.num_recipes)]

            print(f"  Loaded {self.num_recipes:,} recipes from cache")
            print(f"  Cache storage: {self._memory_usage():.1f} MB")

            # === DYNAMIC SERVINGS: Compute total_calories and is_fixed_portion ===
            # total_calories can be computed from cached tensors
            self.total_calories = self.nutrition[:, 0] * self.servings.float()  # [N]

            # is_fixed_portion: load from cache if available, else compute from names
            if 'is_fixed_portion' in cached:
                self.is_fixed_portion = cached['is_fixed_portion'].to(self.device)
                print(f"  Loaded is_fixed_portion from cache")
            else:
                # Cache doesn't have it - for now mark all as divisible (conservative)
                # In practice, should rebuild cache or load recipe names
                self.is_fixed_portion = torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)
                print(f"  WARNING: is_fixed_portion not in cache, marking all as divisible")

            # Load template structures from separate cache file
            # Use cache-only method that doesn't iterate plate_builder.all_recipes
            template_cache_path = cache_path.parent / "template_tensors.pt"
            if template_cache_path.exists():
                try:
                    self._load_template_cache_minimal(template_cache_path, plate_builder)
                except Exception as e:
                    print(f"  WARNING: template cache load failed: {e}")
                    print("  Falling back to rebuild template index")
                    self._build_template_index()
            else:
                # Fallback: build template index from plate_builder
                print("  WARNING: template cache not found, rebuilding template index")
                self._build_template_index()

            # === SODIUM PER SERVING: Load from cache or fall back to zeros ===
            if 'sodium_per_serving' in cached:
                self.sodium_per_serving = cached['sodium_per_serving'].to(self.device)
                n_with_sodium = (self.sodium_per_serving > 0).sum().item()
                print(f"  Loaded sodium_per_serving from cache ({n_with_sodium:,} recipes with data)")
            else:
                self.sodium_per_serving = torch.zeros(self.num_recipes, dtype=torch.float32, device=self.device)
                print(f"  WARNING: sodium_per_serving not in cache, using zeros (rebuild cache to enable sodium filtering)")

            # Initialize product tracking (no products until inject_products() called)
            self.is_product = torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)
            self.fndds_group = torch.zeros(self.num_recipes, dtype=torch.int32, device=self.device)
            self.product_metadata = []
            self.product_id_offset = 1_000_000

            return True

        except Exception as e:
            import traceback
            print(f"  Failed to load cache: {e}")
            traceback.print_exc()
            print(f"  Falling back to building from scratch")
            return False

    def _load_template_cache_minimal(self, template_cache_path: Path, plate_builder: PlateBuilder):
        """
        Load template structures from cache with minimal memory footprint.

        This method avoids iterating over plate_builder.all_recipes which would
        require 500k+ Recipe objects to be accessed, causing memory spikes.

        The template cache contains:
        - meal_main_indices: {meal_type: tensor} - union of main recipe indices per meal
        - meal_side_indices: {meal_type: tensor} - union of side recipe indices per meal
        - template_to_sides: {template_id: tensor} - side indices for each template
        - template_to_side_pool_ids: {template_id: tensor} - pool IDs for each side
        """
        print("  Loading template structures from cache...", flush=True)

        # Load to CPU first, then move to device (avoids potential GPU memory issues)
        cached = torch.load(template_cache_path, map_location='cpu', weights_only=False)

        # Load cached dict structures, moving tensors to device
        self.meal_main_indices = {
            k: v.to(self.device) for k, v in cached['meal_main_indices'].items()
        }
        self.meal_side_indices = {
            k: v.to(self.device) for k, v in cached['meal_side_indices'].items()
        }
        self.template_to_sides = {
            k: v.to(self.device) for k, v in cached['template_to_sides'].items()
        }
        self.template_to_side_pool_ids = {
            k: v.to(self.device) for k, v in cached['template_to_side_pool_ids'].items()
        }

        # Build template structures using only plate_builder.get_templates_for_meal()
        # This does NOT iterate all_recipes - it just reads template JSON
        self.template_is_one_dish: Dict[int, bool] = {}
        self.templates: Dict[str, List[TemplateInfo]] = {
            'breakfast': [], 'lunch': [], 'dinner': [],
        }

        template_id = 0
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            templates = plate_builder.get_templates_for_meal(meal_type)
            main_indices = self.meal_main_indices.get(meal_type, torch.tensor([], dtype=torch.int32, device=self.device))

            for template in templates:
                side_indices = self.template_to_sides.get(template_id, torch.tensor([], dtype=torch.int32, device=self.device))

                info = TemplateInfo(
                    template_id=template_id,
                    name=template.name,
                    meal_type=meal_type,
                    is_one_dish=template.one_dish,
                    main_indices=main_indices,
                    side_indices=side_indices,
                )
                self.templates[meal_type].append(info)
                self.template_is_one_dish[template_id] = template.one_dish
                template_id += 1

        # Build main_to_templates reverse mapping from meal_main_indices
        # This uses the cached meal_main_indices which are based on current templates
        self.main_to_templates: Dict[int, List[int]] = {}
        
        # Rebuild gpu_recipe_to_template from meal_main_indices
        # This ensures the mapping reflects the current templates, not stale cache
        self.gpu_recipe_to_template = torch.full(
            (self.num_recipes,), -1, dtype=torch.int32, device=self.device
        )
        
        template_id = 0
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            templates = plate_builder.get_templates_for_meal(meal_type)
            main_indices = self.meal_main_indices.get(meal_type, torch.tensor([], dtype=torch.int32, device=self.device))
            
            # Map each main recipe to all templates in this meal
            # (This is an approximation - recipes get all meal's templates)
            for idx in main_indices.cpu().numpy():
                idx = int(idx)
                if idx not in self.main_to_templates:
                    self.main_to_templates[idx] = []
                # Add all templates for this meal
                for tid in range(template_id, template_id + len(templates)):
                    if tid not in self.main_to_templates[idx]:
                        self.main_to_templates[idx].append(tid)
            
            template_id += len(templates)
        
        # Assign first template to each recipe for gpu_recipe_to_template
        if self.main_to_templates:
            recipe_indices = list(self.main_to_templates.keys())
            template_values = [tids[0] if tids else -1 for tids in self.main_to_templates.values()]
            self.gpu_recipe_to_template[recipe_indices] = torch.tensor(
                template_values, dtype=torch.int32, device=self.device
            )

        print(f"    Loaded template structures for {template_id} templates")

        # Load verdicts + meal fitness (always — these are independent of pool strategy)
        verdicts, meal_ok = self._load_recipe_verdicts()
        if verdicts:
            self._build_verdict_penalties(verdicts)
            self._build_meal_fitness(meal_ok)
        else:
            self.gpu_verdict_penalty = torch.zeros(self.num_recipes, device=self.device)
            self.gpu_meal_ok = torch.ones(self.num_recipes, 3, dtype=torch.bool, device=self.device)

    def _memory_usage(self) -> float:
        """Calculate memory usage in MB."""
        total = 0
        total += self.recipe_ids.numel() * 4  # int32
        total += self.ingredient_indices.numel() * 2  # int16
        total += self.ingredient_amounts.numel() * 2  # float16
        total += self.nutrition.numel() * 2  # float16
        total += self.food_groups.numel() * 2  # float16
        total += self.servings.numel() * 2  # float16
        total += self.nnz.numel() * 2  # int16
        total += self.protein_source.numel() * 1  # int8
        return total / 1e6

    def get_recipe_name(self, idx: int) -> str:
        """Get recipe name by index, with lazy loading support."""
        if not self.names:
            # Names not loaded - return placeholder
            return f"Recipe_{idx}"
        if idx < len(self.names):
            return self.names[idx] or f"Recipe_{idx}"
        return f"Recipe_{idx}"

    def populate_names_from_plate_builder(self):
        """Populate recipe names from plate_builder (call only if needed for debug output)."""
        if self.names and len(self.names) == self.num_recipes:
            return  # Already populated

        self.names = [''] * self.num_recipes
        if self.plate_builder and self.plate_builder.all_recipes:
            for recipe in self.plate_builder.all_recipes:
                idx = self.recipe_id_to_idx.get(recipe.recipe_num)
                if idx is not None and idx < self.num_recipes:
                    self.names[idx] = recipe.recipe_name

    def _load_recipe_verdicts(self):
        """Load LLM verdicts and meal fitness from recipe_qa.db.

        Returns:
            (verdicts, meal_ok) where:
            - verdicts: {recipe_id: "main"/"side"/"dessert"/...}
            - meal_ok: {recipe_id: (ok_breakfast, ok_lunch, ok_dinner)}
        """
        qa_path = Path(BASE_PATH) / "data" / "recipe_qa.db"
        if not qa_path.exists():
            print("    WARNING: recipe_qa.db not found — no verdict data", flush=True)
            return {}, {}

        conn = sqlite3.connect(str(qa_path))
        col_info = conn.execute("PRAGMA table_info(recipe_verdicts)").fetchall()
        col_names = {c[1] for c in col_info}
        has_meal_ok = 'ok_breakfast' in col_names

        if has_meal_ok:
            query = "SELECT recipe_id, verdict, ok_breakfast, ok_lunch, ok_dinner FROM recipe_verdicts"
        else:
            query = "SELECT recipe_id, verdict, 1, 1, 1 FROM recipe_verdicts"

        rows = conn.execute(query).fetchall()
        conn.close()

        verdicts = {}
        meal_ok = {}
        for r in rows:
            rid, verdict, ok_b, ok_l, ok_d = r
            verdicts[rid] = verdict
            meal_ok[rid] = (bool(ok_b), bool(ok_l), bool(ok_d))

        print(f"    Loaded {len(verdicts):,} verdicts from recipe_qa.db", flush=True)
        return verdicts, meal_ok

    def _build_template_index(self):
        """Build mapping from templates to recipe indices."""
        print("  Building template index...", flush=True)

        self.templates: Dict[str, List[TemplateInfo]] = {
            'breakfast': [],
            'lunch': [],
            'dinner': [],
        }
        # Temporary storage for pool IDs (will be converted to template_to_side_pool_ids later)
        self._temp_side_pool_ids: Dict[int, torch.Tensor] = {}

        # Use the pre-built category index (O(1) lookup) instead of searching all recipes
        recipes_by_cat = self.plate_builder.recipes_by_category

        # Dessert recipe IDs — blocked from both mains and sides
        dessert_ids = getattr(self.plate_builder, 'dessert_recipe_ids', set())
        desserts_blocked = 0
        desserts_blocked_sides = 0

        # For each template, look up recipe indices directly from category index
        template_id = 0
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            templates = self.plate_builder.get_templates_for_meal(meal_type)
            print(f"    Processing {len(templates)} {meal_type} templates...", flush=True)

            for ti, template in enumerate(templates):
                # Get main recipe indices from category index (fast!)
                # Exclude desserts — they can be sides but not mains
                main_indices_set = set()
                for cat in template.main_categories:
                    for recipe in recipes_by_cat.get(cat, []):
                        if recipe.recipe_num in dessert_ids:
                            desserts_blocked += 1
                            continue
                        idx = self.recipe_id_to_idx.get(recipe.recipe_num)
                        if idx is not None:
                            main_indices_set.add(idx)

                # Get side recipe indices from category index (fast!)
                # Track pool membership for each side (for pool diversity in side2 selection)
                # Block desserts from side slots (desserts aren't sides)
                side_indices_list = []
                side_pool_ids_list = []
                if not template.one_dish and template.side_pools:
                    for pool_idx, pool in enumerate(template.side_pools):
                        if not pool.category_ids:
                            continue  # Skip empty side pools
                        for cat in pool.category_ids:
                            for recipe in recipes_by_cat.get(cat, []):
                                if recipe.recipe_num in dessert_ids:
                                    desserts_blocked_sides += 1
                                    continue
                                idx = self.recipe_id_to_idx.get(recipe.recipe_num)
                                if idx is not None:
                                    side_indices_list.append(idx)
                                    side_pool_ids_list.append(pool_idx)

                # Deduplicate while preserving pool assignment (first pool wins)
                seen_indices = {}
                for idx, pool_id in zip(side_indices_list, side_pool_ids_list):
                    if idx not in seen_indices:
                        seen_indices[idx] = pool_id

                side_indices_sorted = sorted(seen_indices.keys())
                side_pool_ids_sorted = [seen_indices[idx] for idx in side_indices_sorted]

                info = TemplateInfo(
                    template_id=template_id,
                    name=template.name,
                    meal_type=meal_type,
                    is_one_dish=template.one_dish,
                    main_indices=torch.tensor(sorted(main_indices_set), dtype=torch.int32, device=self.device),
                    side_indices=torch.tensor(side_indices_sorted, dtype=torch.int32, device=self.device),
                )
                # Store pool IDs separately (same order as side_indices)
                self._temp_side_pool_ids[template_id] = torch.tensor(
                    side_pool_ids_sorted, dtype=torch.int32, device=self.device
                )
                self.templates[meal_type].append(info)
                template_id += 1

        if desserts_blocked > 0:
            print(f"    Blocked {desserts_blocked:,} dessert recipe-template entries from main slots")
            print(f"    Blocked {desserts_blocked_sides:,} dessert recipe-template entries from side slots")

        # Pre-compute union indices for each meal type
        print("    Computing meal type indices...", flush=True)
        self.meal_main_indices: Dict[str, torch.Tensor] = {}
        self.meal_side_indices: Dict[str, torch.Tensor] = {}

        for meal_type in ['breakfast', 'lunch', 'dinner']:
            # Union of all main indices for this meal type
            all_mains = set()
            all_sides = set()
            for t in self.templates[meal_type]:
                all_mains.update(t.main_indices.tolist())
                all_sides.update(t.side_indices.tolist())

            self.meal_main_indices[meal_type] = torch.tensor(
                sorted(all_mains), dtype=torch.int32, device=self.device
            )
            self.meal_side_indices[meal_type] = torch.tensor(
                sorted(all_sides), dtype=torch.int32, device=self.device
            )

            print(f"      {meal_type}: {len(all_mains):,} mains, {len(all_sides):,} sides", flush=True)

        # Build reverse mapping: recipe index -> which templates it belongs to (for mains)
        print("    Building reverse mapping...", flush=True)
        self.main_to_templates: Dict[int, List[int]] = {}
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            for t in self.templates[meal_type]:
                for idx in t.main_indices.tolist():
                    if idx not in self.main_to_templates:
                        self.main_to_templates[idx] = []
                    self.main_to_templates[idx].append(t.template_id)
        print(f"    Done! {len(self.main_to_templates):,} mains mapped to templates", flush=True)

        # Build template_id -> side_indices mapping for O(1) lookup
        print("    Building template_to_sides mapping...", flush=True)
        self.template_to_sides: Dict[int, torch.Tensor] = {}
        self.template_to_side_pool_ids: Dict[int, torch.Tensor] = {}  # Pool ID for each side
        self.template_is_one_dish: Dict[int, bool] = {}
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            for t in self.templates[meal_type]:
                self.template_to_sides[t.template_id] = t.side_indices
                self.template_to_side_pool_ids[t.template_id] = self._temp_side_pool_ids.get(
                    t.template_id, torch.tensor([], dtype=torch.int32, device=self.device)
                )
                self.template_is_one_dish[t.template_id] = t.is_one_dish
        # Clean up temporary storage
        del self._temp_side_pool_ids
        print(f"    Done! {len(self.template_to_sides):,} templates mapped", flush=True)

        # === GPU TENSORS FOR FAST LOOKUP ===
        # Build recipe_idx -> first_template_id tensor (GPU, O(1) lookup)
        # -1 means no template (shouldn't happen for indexed recipes)
        print(f"    Building GPU recipe->template tensor ({len(self.main_to_templates):,} entries)...", flush=True)
        self.gpu_recipe_to_template = torch.full(
            (self.num_recipes,), -1, dtype=torch.int32, device=self.device
        )
        # Vectorized: build lists then assign at once
        recipe_indices = list(self.main_to_templates.keys())
        template_values = [tids[0] if tids else -1 for tids in self.main_to_templates.values()]
        if recipe_indices:
            self.gpu_recipe_to_template[recipe_indices] = torch.tensor(template_values, dtype=torch.int32, device=self.device)
        print(f"    Done! gpu_recipe_to_template built", flush=True)

        # Build recipe_idx -> is_one_dish tensor (GPU, O(1) lookup)
        print(f"    Building is_one_dish tensor...", flush=True)
        self.gpu_recipe_is_one_dish = torch.zeros(
            self.num_recipes, dtype=torch.bool, device=self.device
        )
        # Vectorized: find all one-dish recipes
        one_dish_recipes = []
        for recipe_idx, template_ids in self.main_to_templates.items():
            for tid in template_ids:
                if self.template_is_one_dish.get(tid, False):
                    one_dish_recipes.append(recipe_idx)
                    break
        if one_dish_recipes:
            self.gpu_recipe_is_one_dish[one_dish_recipes] = True
        print(f"    Done! {len(one_dish_recipes):,} one-dish recipes", flush=True)

        # Build GPU side recipe -> template compatibility tensor
        # For cross-template leftover consumption: a green_salad from pasta template
        # should be consumable with steak template if both have green_salad in side_pools
        print("    Building side-template compatibility matrix...", flush=True)
        num_templates = max(self.template_to_sides.keys()) + 1 if self.template_to_sides else 0
        self.gpu_side_compat = torch.zeros(
            self.num_recipes, num_templates, dtype=torch.bool, device=self.device
        )
        for tid, side_indices in self.template_to_sides.items():
            if len(side_indices) > 0:
                self.gpu_side_compat[side_indices.long(), tid] = True
        print(f"    Done! {self.gpu_side_compat.sum().item():,} recipe-template pairs", flush=True)

        print(f"    Built GPU template tensors for {self.num_recipes:,} recipes")

    def _build_verdict_penalties(self, verdicts):
        """Build verdict hard exclusion mask.

        Hard-excluded (not_food, invalid) are blocked from both main AND side
        selection via gpu_verdict_excluded. Components and beverages are
        excluded at build time in PlateBuilder. All other verdicts (dessert,
        side, main) have NO penalty — the template system handles placement.
        """
        HARD_EXCLUDE = {"not_food", "invalid", "component", "beverage", "derived_fat_only"}
        # Recipes that should NEVER be selected as mains (only as sides)
        SIDE_ONLY = {"side", "dessert"}

        self.gpu_verdict_penalty = torch.zeros(self.num_recipes, device=self.device)
        self.gpu_verdict_excluded = torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)
        self.gpu_is_side_only = torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)
        excluded = 0
        side_only_count = 0
        for recipe_id, verdict in verdicts.items():
            idx = self.recipe_id_to_idx.get(recipe_id)
            if idx is None:
                continue
            if verdict in HARD_EXCLUDE:
                self.gpu_verdict_excluded[idx] = True
                self.gpu_verdict_penalty[idx] = 999.0
                excluded += 1
            elif verdict in SIDE_ONLY:
                self.gpu_is_side_only[idx] = True
                side_only_count += 1
        print(f"    Verdict: {excluded:,} hard-excluded (not_food/invalid)", flush=True)
        print(f"    Verdict: {side_only_count:,} side-only (blocked from main selection)", flush=True)

    def _build_meal_fitness(self, meal_ok):
        """Build per-meal-type boolean masks from LLM classifications.

        Uses ok_breakfast/ok_lunch/ok_dinner from recipe_qa.db to filter
        recipes into appropriate meal slots. Recipes without verdict data
        default to True (allowed everywhere).
        """
        self.gpu_meal_ok = torch.ones(self.num_recipes, 3, dtype=torch.bool, device=self.device)
        applied = 0
        for recipe_id, (ok_b, ok_l, ok_d) in meal_ok.items():
            idx = self.recipe_id_to_idx.get(recipe_id)
            if idx is None:
                continue
            self.gpu_meal_ok[idx, 0] = ok_b
            self.gpu_meal_ok[idx, 1] = ok_l
            self.gpu_meal_ok[idx, 2] = ok_d
            applied += 1
        b_count = self.gpu_meal_ok[:, 0].sum().item()
        l_count = self.gpu_meal_ok[:, 1].sum().item()
        d_count = self.gpu_meal_ok[:, 2].sum().item()
        print(f"    Meal fitness: {applied:,} recipes tagged (B:{int(b_count):,} L:{int(l_count):,} D:{int(d_count):,})", flush=True)

    def get_valid_sides_for_templates(self, template_ids: List[int]) -> torch.Tensor:
        """Get union of side indices for given templates."""
        all_sides = set()
        for tid in template_ids:
            for meal_type in ['breakfast', 'lunch', 'dinner']:
                for t in self.templates[meal_type]:
                    if t.template_id == tid:
                        all_sides.update(t.side_indices.tolist())
        return torch.tensor(sorted(all_sides), dtype=torch.int32, device=self.device)

    def inject_products(
        self,
        product_cache_path: str = None,
        package_index: Optional[PackageIndex] = None,
    ) -> int:
        """
        Inject store-bought products as pseudo-recipes into the database.

        Products compete directly with real recipes in the beam search.
        Each product becomes a single-ingredient "recipe" with a synthetic
        FNDDS code, so it has zero pantry overlap with real recipes.

        Args:
            product_cache_path: Path to product_recipes.pt (default: data/tensor_cache/product_recipes.pt)
            package_index: If provided, extends it with synthetic product pricing

        Returns:
            Number of products injected
        """
        import numpy as np

        if product_cache_path is None:
            product_cache_path = _tensor_cache_dir() / "product_recipes.pt"
        else:
            product_cache_path = Path(product_cache_path)

        if not product_cache_path.exists():
            print(f"  No product cache at {product_cache_path}, skipping product injection")
            return 0

        print(f"\n  Injecting store-bought products from {product_cache_path}...")
        pcache = torch.load(product_cache_path, map_location='cpu', weights_only=False)

        num_products = pcache["num_products"]
        if num_products == 0:
            print("  No products to inject")
            return 0

        old_num_recipes = self.num_recipes
        old_num_ingredients = self.ingredient_index.num_ingredients

        # === 1. Extend IngredientIndex with synthetic FNDDS codes ===
        synthetic_fndds_list = pcache["synthetic_fndds_list"][:num_products]
        for i, syn_fndds in enumerate(synthetic_fndds_list):
            new_idx = old_num_ingredients + i
            self.ingredient_index.fpid_to_idx[syn_fndds] = new_idx
            self.ingredient_index.idx_to_fpid[new_idx] = syn_fndds
        self.ingredient_index.num_ingredients = old_num_ingredients + num_products
        self.num_ingredients = self.ingredient_index.num_ingredients

        # === 2. Fix product ingredient indices (were placeholder 0, now real) ===
        prod_ingredient_indices = pcache["ingredient_indices"][:num_products].to(torch.int32).clone()
        prod_ingredient_indices[:, 0] = torch.arange(
            old_num_ingredients, old_num_ingredients + num_products, dtype=torch.int32
        )

        # === 3. Concatenate all tensors (sliced to num_products) ===
        self.recipe_ids = torch.cat([
            self.recipe_ids,
            pcache["recipe_ids"][:num_products].to(self.device),
        ])
        self.ingredient_indices = torch.cat([
            self.ingredient_indices,
            prod_ingredient_indices.to(self.device),
        ])
        self.ingredient_amounts = torch.cat([
            self.ingredient_amounts,
            pcache["ingredient_amounts"][:num_products].to(self.device),
        ])
        self.nutrition = torch.cat([
            self.nutrition,
            pcache["nutrition"][:num_products].to(self.device),
        ])
        self.food_groups = torch.cat([
            self.food_groups,
            pcache["food_groups"][:num_products].to(self.device),
        ])
        self.servings = torch.cat([
            self.servings,
            pcache["servings"][:num_products].to(self.device),
        ])
        self.nnz = torch.cat([
            self.nnz,
            pcache["nnz"][:num_products].to(self.device),
        ])
        self.protein_source = torch.cat([
            self.protein_source,
            pcache["protein_source"][:num_products].to(self.device),
        ])

        self.num_recipes = old_num_recipes + num_products

        # === 4. Build is_product mask ===
        self.is_product = torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)
        self.is_product[old_num_recipes:] = True

        self.product_metadata = pcache["product_metadata"][:num_products]
        self.product_id_offset = pcache["product_id_offset"]

        # === 4b. Build FNDDS 6-digit group tensor for product cooldown ===
        self.fndds_group = torch.zeros(self.num_recipes, dtype=torch.int32, device=self.device)
        for i in range(num_products):
            meta = self.product_metadata[i]
            fndds_code = meta.get("fndds_code", "")
            if len(fndds_code) >= 6:
                group = int(fndds_code[:6])
            elif fndds_code:
                group = int(fndds_code) * (10 ** (6 - len(fndds_code)))
            else:
                group = 0
            self.fndds_group[old_num_recipes + i] = group

        # === 5. Rebuild recipe_id_to_idx mapping ===
        prod_recipe_ids = pcache["recipe_ids"][:num_products].numpy()
        for i in range(num_products):
            rid = int(prod_recipe_ids[i])
            self.recipe_id_to_idx[rid] = old_num_recipes + i

        # === 6. Rebuild gpu_recipe_id_to_idx ===
        max_recipe_id = int(self.recipe_ids.max().item()) + 1
        new_gpu_map = torch.full((max_recipe_id,), -1, dtype=torch.int32)
        old_size = self.gpu_recipe_id_to_idx.shape[0]
        new_gpu_map[:old_size] = self.gpu_recipe_id_to_idx.cpu()
        prod_rid_tensor = torch.from_numpy(prod_recipe_ids).long()
        prod_idx_tensor = torch.arange(old_num_recipes, old_num_recipes + num_products, dtype=torch.int32)
        new_gpu_map[prod_rid_tensor] = prod_idx_tensor
        self.gpu_recipe_id_to_idx = new_gpu_map.to(self.device)

        # === 7. Rebuild derived tensors ===
        self.ingredient_indices_flat = self.ingredient_indices.long().flatten()
        self.total_calories = self.nutrition[:, 0] * self.servings.float()

        prod_fixed = pcache["is_fixed_portion"][:num_products].to(self.device)
        self.is_fixed_portion = torch.cat([self.is_fixed_portion, prod_fixed])

        self.packed_metadata = torch.cat([
            self.servings.unsqueeze(1),
            self.nutrition,
            self.food_groups,
        ], dim=1).float()

        for i in range(num_products):
            meta = self.product_metadata[i]
            brand = meta.get("brand", "")
            name = meta.get("name", f"Product_{i}")
            display = f"{brand} {name}".strip()[:60] if brand else name[:60]
            self.names.append(display)

        # === 8. Extend template GPU tensors ===
        old_rtt_cpu = self.gpu_recipe_to_template.cpu()
        new_rtt = torch.full((self.num_recipes,), -1, dtype=torch.int32)
        new_rtt[:old_num_recipes] = old_rtt_cpu

        old_rod_cpu = self.gpu_recipe_is_one_dish.cpu()
        new_rod = torch.zeros(self.num_recipes, dtype=torch.bool)
        new_rod[:old_num_recipes] = old_rod_cpu

        old_sc_cpu = self.gpu_side_compat.cpu()
        old_num_templates = old_sc_cpu.shape[1] if old_sc_cpu.dim() == 2 else 0
        num_templates = max(
            (t.template_id for meal in ['breakfast', 'lunch', 'dinner']
             for t in self.templates[meal]),
            default=-1
        ) + 1
        num_templates = max(num_templates, old_num_templates)
        new_sc = torch.zeros(self.num_recipes, num_templates, dtype=torch.bool)
        new_sc[:old_num_recipes, :old_num_templates] = old_sc_cpu

        main_cat_to_templates = {}
        side_cat_to_templates = {}
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            templates = self.plate_builder.get_templates_for_meal(meal_type)
            for t_info in self.templates[meal_type]:
                tid = t_info.template_id
                for pt in templates:
                    if pt.name == t_info.name:
                        for cat in pt.main_categories:
                            if cat not in main_cat_to_templates:
                                main_cat_to_templates[cat] = []
                            main_cat_to_templates[cat].append(tid)
                        if not pt.one_dish and pt.side_pools:
                            for pool in pt.side_pools:
                                for cat in pool.category_ids:
                                    if cat not in side_cat_to_templates:
                                        side_cat_to_templates[cat] = []
                                    side_cat_to_templates[cat].append(tid)
                        break

        def _match_cats(prod_cats, cat_map):
            matched = set()
            for pcat in prod_cats:
                if pcat in cat_map:
                    matched.update(cat_map[pcat])
                dot = pcat.rfind('.')
                if dot > 0:
                    parent = pcat[:dot]
                    if parent in cat_map:
                        matched.update(cat_map[parent])
                for tcat, tids in cat_map.items():
                    if pcat.startswith(tcat + '.'):
                        matched.update(tids)
            return matched

        tid_is_one_dish = {}
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            for t_info in self.templates[meal_type]:
                tid_is_one_dish[t_info.template_id] = t_info.is_one_dish

        products_as_main = 0
        products_as_side = 0
        main_additions = {}
        side_additions = {}

        for i in range(num_products):
            db_idx = old_num_recipes + i
            meta = self.product_metadata[i]
            prod_cats = meta.get("template_categories", [])

            matched_main_tids = _match_cats(prod_cats, main_cat_to_templates)
            matched_side_tids = _match_cats(prod_cats, side_cat_to_templates)

            if matched_main_tids:
                first_tid = min(matched_main_tids)
                new_rtt[db_idx] = first_tid
                new_rod[db_idx] = False
                self.main_to_templates[db_idx] = list(matched_main_tids)
                products_as_main += 1
                for tid in matched_main_tids:
                    if tid not in main_additions:
                        main_additions[tid] = []
                    main_additions[tid].append(db_idx)

            if matched_side_tids:
                products_as_side += 1
                for tid in matched_side_tids:
                    new_sc[db_idx, tid] = True
                    if tid not in side_additions:
                        side_additions[tid] = []
                    side_additions[tid].append(db_idx)
                if not matched_main_tids:
                    new_rtt[db_idx] = min(matched_side_tids)

        self.gpu_recipe_to_template = new_rtt.to(self.device)
        self.gpu_recipe_is_one_dish = new_rod.to(self.device)
        self.gpu_side_compat = new_sc.to(self.device)

        for meal_type in ['breakfast', 'lunch', 'dinner']:
            for t_info in self.templates[meal_type]:
                tid = t_info.template_id
                if tid in main_additions:
                    t_info.main_indices = torch.cat([
                        t_info.main_indices,
                        torch.tensor(main_additions[tid], dtype=torch.int32, device=self.device),
                    ])

        for meal_type in ['breakfast', 'lunch', 'dinner']:
            for t_info in self.templates[meal_type]:
                tid = t_info.template_id
                if tid in side_additions:
                    t_info.side_indices = torch.cat([
                        t_info.side_indices,
                        torch.tensor(side_additions[tid], dtype=torch.int32, device=self.device),
                    ])

        for meal_type in ['breakfast', 'lunch', 'dinner']:
            all_mains = set()
            all_sides = set()
            for t in self.templates[meal_type]:
                all_mains.update(t.main_indices.cpu().tolist())
                all_sides.update(t.side_indices.cpu().tolist())
                self.template_to_sides[t.template_id] = t.side_indices
            self.meal_main_indices[meal_type] = torch.tensor(
                sorted(all_mains), dtype=torch.int32, device=self.device
            )
            self.meal_side_indices[meal_type] = torch.tensor(
                sorted(all_sides), dtype=torch.int32, device=self.device
            )

        # === 9. Extend PackageIndex with synthetic product pricing ===
        if package_index is not None:
            all_synthetic = pcache["synthetic_packages"]
            synthetic_packages = {
                k: v for k, v in all_synthetic.items()
                if k in self.ingredient_index.fpid_to_idx
            }
            package_index.extend_with_synthetic(
                synthetic_packages, self.ingredient_index, self.device
            )

        print(f"  Injected {num_products:,} products ({products_as_main:,} as mains, {products_as_side:,} as sides)")
        print(f"  Total recipes: {self.num_recipes:,} ({old_num_recipes:,} recipes + {num_products:,} products)")
        print(f"  Total ingredients: {self.num_ingredients:,} ({old_num_ingredients:,} real + {num_products:,} synthetic)")

        return num_products


class SparseCascadePlanner:
    """
    Memory-efficient cascade planner using sparse recipe representation.

    Peak memory: ~900 MB (during scoring, immediately freed)
    Sustained memory: ~500 KB (cascade state)
    """

    def __init__(
        self,
        recipe_db: SparseRecipeDatabase,
        package_index: PackageIndex,
        device: torch.device,
        K: int = 200,  # Balanced beam width for two-pass scoring
        # NEW: Attendance schedule for variable family size and meal attendance
        attendance_schedule: Optional[AttendanceSchedule] = None,
        # NEW: Scoring configuration (controls cost/pantry/protein behavior)
        scoring_config: Optional[ScoringConfig] = None,
        # DEPRECATED: Old interface kept for backward compatibility
        servings_per_meal: Optional[float] = None,
        weekly_calories: Optional[float] = None,
        weekly_protein: Optional[float] = None,
        # Other settings
        leftover_ttl: int = 3,
        leftover_target: float = None,  # 0.0-1.0 slider: preference for high-leftover recipes (None = use config)
        # Macro percentage targets (must sum to 100)
        protein_pct_target: float = 15.0,
        carbs_pct_target: float = 50.0,
        fat_pct_target: float = 35.0,
        macro_tolerance_pct: float = 5.0,
        # Auto-inject fruit snacks when calories are 85-95%
        auto_inject_snacks: bool = True,
        # Freezer settings
        freezer_ttl: int = FROZEN_SHELF_DAYS,  # Freezer quality window; safety can be longer.
        freezer_capacity_kg: float = 30.0,  # Max frozen kg (0=unlimited)
        auto_freeze: bool = True,      # Auto-freeze when TTL hits 0
        verbose: bool = True,
        debug_trace: bool = False,     # Audit-only per-ingredient flow tracing
        score_noise: float = 0.0,      # Random noise added to scores (0=deterministic, 0.1=slight variation)
        # Allergen / ingredient exclusions
        allergen_exclusions: Optional[List[str]] = None,  # e.g. ["pork", "shellfish", "peanuts"]
        # Kosher meat+dairy separation
        kosher_mode: bool = False,
        # Sodium ceiling filter (per serving, mg)
        sodium_max_mg: Optional[float] = None,
    ):
        self.db = recipe_db
        self.package_index = package_index
        self.device = device
        self.K = K

        # === ALLERGEN FILTERING ===
        # Build a boolean mask [num_recipes] where True = safe, False = contains excluded ingredient
        self.allergen_safe_mask = self._build_allergen_recipe_mask(allergen_exclusions)

        # === KOSHER MEAT+DAIRY SEPARATION ===
        # Pre-compute per-recipe meat/dairy flags for O(1) lookup at side selection time
        self.kosher_mode = kosher_mode
        if kosher_mode:
            meat_prefixes = ["21", "22", "23", "24"]  # beef, pork, lamb, poultry
            dairy_prefixes = ["11", "12", "13", "14", "15"]  # all dairy
            # _build_ingredient_flag returns True for recipes that CONTAIN the ingredient
            self.recipe_has_meat = self._build_ingredient_flag(meat_prefixes)
            self.recipe_has_dairy = self._build_ingredient_flag(dairy_prefixes)
            n_meat = self.recipe_has_meat.sum().item()
            n_dairy = self.recipe_has_dairy.sum().item()
            n_both = (self.recipe_has_meat & self.recipe_has_dairy).sum().item()
            # Recipes that contain BOTH meat and dairy are never kosher - exclude them entirely
            if n_both > 0:
                kosher_safe = ~(self.recipe_has_meat & self.recipe_has_dairy)
                if self.allergen_safe_mask is not None:
                    self.allergen_safe_mask = self.allergen_safe_mask & kosher_safe
                else:
                    self.allergen_safe_mask = kosher_safe
            if verbose:
                print(f"  [Kosher] {n_meat:,} meat recipes, {n_dairy:,} dairy recipes, "
                      f"{n_both:,} with both (excluded), separation enforced at side selection")
        else:
            self.recipe_has_meat = None
            self.recipe_has_dairy = None

        # === QA EXCLUSION MASK ===
        # Merge LLM-verified exclusions (components, non-food) into allergen mask
        _qa_mask = getattr(recipe_db, 'qa_excluded_mask', None)
        if _qa_mask is not None:
            if self.allergen_safe_mask is not None:
                self.allergen_safe_mask = self.allergen_safe_mask & _qa_mask
            else:
                self.allergen_safe_mask = _qa_mask

        # === SODIUM CEILING FILTER ===
        if sodium_max_mg is not None and hasattr(recipe_db, 'sodium_per_serving'):
            sodium_safe = recipe_db.sodium_per_serving <= sodium_max_mg  # [num_recipes] bool
            n_excluded = (~sodium_safe).sum().item()
            if self.allergen_safe_mask is not None:
                self.allergen_safe_mask = self.allergen_safe_mask & sodium_safe
            else:
                self.allergen_safe_mask = sodium_safe
            if verbose:
                n_remaining = self.allergen_safe_mask.sum().item() if self.allergen_safe_mask is not None else self.db.num_recipes
                print(f"  [Sodium] Ceiling {sodium_max_mg:.0f}mg/serving: "
                      f"{n_excluded:,} recipes excluded, {n_remaining:,} remaining")

        title_ingredient_safe = self._build_title_ingredient_sanity_mask()
        if title_ingredient_safe is not None:
            if self.allergen_safe_mask is not None:
                self.allergen_safe_mask = self.allergen_safe_mask & title_ingredient_safe
            else:
                self.allergen_safe_mask = title_ingredient_safe

        # Store scoring config (defaults to balanced if not provided)
        self.config = scoring_config if scoring_config is not None else ScoringConfig.balanced()
        self.config = _with_constructor_protein_target(self.config, protein_pct_target)

        # === HOUSEHOLD SIZE ADJUSTMENTS ===
        # Singles/couples over-feed at 75% leftovers because batch sizes are too large.
        # Tighten calorie ceiling and lower leftover target for small households.
        _hh_size = len(attendance_schedule.household.people) if attendance_schedule else 4
        if _hh_size <= 1:
            _hh_overrides = {}
            # Tighter calorie ceiling: 102% instead of 105%
            if self.config.calorie_ceiling_pct > 1.02:
                _hh_overrides['calorie_ceiling_pct'] = 1.02
            # Much stronger over-ceiling penalty: 6x instead of 2x
            if self.config.cal_over_ceiling_mult < 6.0:
                _hh_overrides['cal_over_ceiling_mult'] = 6.0
            if _hh_overrides:
                self.config = dc_replace(self.config, **_hh_overrides)
        elif _hh_size == 2:
            _hh_overrides = {}
            if self.config.calorie_ceiling_pct > 1.03:
                _hh_overrides['calorie_ceiling_pct'] = 1.03
            if self.config.cal_over_ceiling_mult < 4.0:
                _hh_overrides['cal_over_ceiling_mult'] = 4.0
            if _hh_overrides:
                self.config = dc_replace(self.config, **_hh_overrides)

        # === TIERED AUTO PROTEIN TARGETING ===
        # At 15%: soft steering only (density bonus + macro weight, NO prefilter)
        #   - Keeps all cheap recipes in pool, gentle pull toward protein
        # At 25%+: add prefilter for harder steering.
        #   - Moderate 18% targets are still normal-family meal plans; the
        #     hard gate over-constrains the cuisine/recipe pool and raises
        #     whole-package spend without reliably hitting the target.
        #   - 25%+ is a genuinely high-protein plan where excluding low-protein
        #     recipes is worth the stronger steering.
        overrides = _protein_targeting_overrides(self.config)
        if overrides:
            self.config = dc_replace(self.config, **overrides)

        self.leftover_ttl = leftover_ttl
        # Use ScoringConfig's leftover_target if not explicitly provided
        self.leftover_target = leftover_target if leftover_target is not None else self.config.leftover_target
        self.protein_pct_target = self.config.protein_pct_target
        self.carbs_pct_target = carbs_pct_target
        self.fat_pct_target = fat_pct_target
        self.macro_tolerance_pct = (
            self.config.macro_tolerance_pct
            if self.config.protein_pct_target >= 25 and macro_tolerance_pct == 5.0
            else macro_tolerance_pct
        )
        # Use ScoringConfig for fruit snack control, fallback to constructor
        # param. Keep fruit top-ups to baseline protein plans; high-protein
        # plans need protein-dense calories, not carbohydrate snacks.
        _config_snacks = getattr(self.config, 'enable_fruit_snacks', auto_inject_snacks)
        self.auto_inject_snacks = bool(_config_snacks and self.config.protein_pct_target <= 15.0)
        self.freezer_ttl = freezer_ttl
        self.freezer_capacity_kg = freezer_capacity_kg
        self.auto_freeze = auto_freeze
        self.verbose = verbose
        self.debug_trace = debug_trace
        self.score_noise = score_noise
        self.num_ingredients = recipe_db.num_ingredients

        # === EMBER SCORES (inflammation scoring) ===
        self.ember_scores = None
        if self.config.enable_inflammation_scoring:
            ember_path = _tensor_cache_dir() / "ember_scores.pt"
            if ember_path.exists():
                cache = torch.load(ember_path, map_location=device, weights_only=False)
                self.ember_scores = cache["ember_scores"].to(device)
                if self.verbose:
                    print(f"Loaded Ember scores: {self.ember_scores.shape[0]:,} recipes, mean={self.ember_scores.mean():.1f}")
            else:
                if self.verbose:
                    print("WARNING: ember_scores.pt not found — inflammation scoring disabled")

        # === EMBER FILTER MASK (hard cutoff for candidate pool) ===
        self.ember_filter_mask = None
        if self.ember_scores is not None and self.config.enable_inflammation_scoring:
            threshold = self.config.inflammation_target  # 50.0 for C grade
            self.ember_filter_mask = self.ember_scores >= threshold
            if self.verbose:
                passing = self.ember_filter_mask.sum().item()
                print(f"  Ember filter: {passing:,}/{len(self.ember_scores):,} recipes pass (>={threshold})")

        # === AIP FILTER MASK (Autoimmune Protocol candidate pool) ===
        self.aip_filter_mask = None
        if getattr(self.config, 'enable_aip_filter', False):
            aip_path = _tensor_cache_dir() / "aip_masks.pt"
            if aip_path.exists():
                aip_masks = torch.load(aip_path, map_location=device, weights_only=False)
                pool_key = f"aip_{self.config.aip_pool}"
                if pool_key in aip_masks:
                    self.aip_filter_mask = aip_masks[pool_key].to(device)
                    if self.verbose:
                        passing = self.aip_filter_mask.sum().item()
                        print(f"  AIP filter: {passing:,} recipes in '{self.config.aip_pool}' pool")
                else:
                    if self.verbose:
                        print(f"  WARNING: AIP pool '{pool_key}' not found in aip_masks.pt")
            else:
                if self.verbose:
                    print("  WARNING: aip_masks.pt not found — AIP filter disabled")

        # === RECIPE-TO-PACKAGE MAPPING (store-bought alternatives) ===
        self.store_alternatives = {}
        store_alt_path = Path(__file__).parent / "recipe_to_package_map.json"
        if store_alt_path.exists():
            import json
            with open(store_alt_path) as f:
                data = json.load(f)
                self.store_alternatives = data.get('mappings', {})
            if self.verbose:
                print(f"Loaded {len(self.store_alternatives)} store-bought alternatives")

        # === PERISHABILITY INDEX (for pantry TTL/freezer) ===
        self.perishability = PerishabilityIndex(device=device)
        self.perishability.build_gpu_tensors(recipe_db.ingredient_index)

        # === ATTENDANCE SCHEDULE SETUP ===
        if attendance_schedule is not None:
            # New interface: use provided schedule
            self.attendance = attendance_schedule
        elif servings_per_meal is not None:
            # Backward compatibility: create schedule from old parameters
            # Build a household with the right number of people
            num_people = int(servings_per_meal)
            cal_per_person = (weekly_calories or 56000.0) / num_people / 7
            prot_per_person = (weekly_protein or 1400.0) / num_people / 7
            from hestia.data_structures import PersonProfile
            people = [
                PersonProfile(f"Person {i+1}", cal_per_person, prot_per_person)
                for i in range(num_people)
            ]
            household = HouseholdConfig(people=people)
            self.attendance = AttendanceSchedule(household)
        else:
            # Default: family of 4, everyone at every meal
            self.attendance = AttendanceSchedule(HouseholdConfig.family_of_four())

        # Pre-compute tensors for fast per-slot lookup
        self.servings_per_slot = self.attendance.servings_tensor(device)  # [NUM_SLOTS]
        self.cal_target_per_slot = self.attendance.calories_tensor(device)  # [NUM_SLOTS]
        self.prot_target_per_slot = self.attendance.protein_tensor(device)  # [NUM_SLOTS]

        # === NEW: LEFTOVER PERCENTAGE CONTROL ===
        # Compute ideal recipe servings based on leftover_pct_target
        #
        # FIXED: Old formula was WRONG (caused 7-day same-meal problem):
        #   ideal = slot_srv / (1 - leftover_pct_target)  # For 70%: 4/0.3 = 13.3 servings
        #   This allowed recipes that feed the whole week in one cook!
        #
        # NEW formula uses max_feed_days:
        #   At 70% leftover target, we want to cook ~30% of meals (fresh)
        #   So we cook every 1/0.30 = 3.3 days, meaning max_feed_days ≈ 3-4
        #   ideal = slot_srv * max_feed_days  # For 70%: 4 * 4 = 16 servings for 4 days
        #
        # The max_feed_days config allows tuning (default 4 = cook twice per week)
        self.leftover_pct_target = self.config.leftover_pct_target
        # Decoupled side leftover target (-1 = use main's value)
        self.side_leftover_pct_target = self.config.side_leftover_pct_target if self.config.side_leftover_pct_target >= 0 else self.leftover_pct_target
        self.ideal_servings_per_slot = torch.zeros(NUM_SLOTS, device=device)
        self.ideal_side_servings_per_slot = torch.zeros(NUM_SLOTS, device=device)

        # Compute max_feed_days: how many days a single recipe should feed
        # At 70% leftover: cook 30% of meals = every 3.3 days → max_feed_days ≈ 4
        # At 50% leftover: cook 50% of meals = every 2 days → max_feed_days ≈ 3
        # At 10% leftover: cook 90% of meals = every 1.1 days → max_feed_days ≈ 2
        # Config override allows user tuning; default computed from leftover_pct_target
        config_max_feed_days = getattr(self.config, 'max_feed_days', 0)
        if config_max_feed_days > 0:
            self.max_feed_days = config_max_feed_days
        elif self.leftover_pct_target > 0 and self.leftover_pct_target < 1.0:
            # Cooking frequency = 1 - leftover_pct_target (fraction of fresh meals)
            # max_feed_days = ceiling of cook interval, capped at 7
            cook_frequency = 1.0 - self.leftover_pct_target
            self.max_feed_days = min(7, int(1.0 / cook_frequency) + 1)
        else:
            self.max_feed_days = 1  # 0% leftovers = cook fresh every meal

        # Compute side max_feed_days separately
        if self.side_leftover_pct_target > 0 and self.side_leftover_pct_target < 1.0:
            side_cook_freq = 1.0 - self.side_leftover_pct_target
            self.side_max_feed_days = min(7, int(1.0 / side_cook_freq) + 1)
        else:
            self.side_max_feed_days = 1

        for slot in range(NUM_SLOTS):
            slot_srv = self.servings_per_slot[slot].item()
            if self.leftover_pct_target > 0 and self.leftover_pct_target < 1.0:
                # Ideal servings = enough to feed for max_feed_days worth of this slot
                self.ideal_servings_per_slot[slot] = slot_srv * self.max_feed_days
            else:
                self.ideal_servings_per_slot[slot] = slot_srv  # 0% leftovers = exact match
            # Side ideal servings use decoupled target
            if self.side_leftover_pct_target > 0 and self.side_leftover_pct_target < 1.0:
                self.ideal_side_servings_per_slot[slot] = slot_srv * self.side_max_feed_days
            else:
                self.ideal_side_servings_per_slot[slot] = slot_srv

        # Weekly totals (derived from schedule)
        self.weekly_calories = self.attendance.weekly_calories
        self.weekly_protein = self.attendance.weekly_protein

        # === FOOD GROUP TARGETS (grams per day, scaled by family size) ===
        # USDA MyPlate recommendations: 2.5 cups veg, 2 cups fruit per adult
        # ~200g per cup, so ~500g veg, ~400g fruit per person per day
        num_people = self.attendance.household.size
        self.weekly_vegetables_g = 500.0 * num_people * 7  # ~14kg/week for family of 4
        self.weekly_fruits_g = 400.0 * num_people * 7       # ~11kg/week for family of 4

        # Shadow price configuration (dollars per gram of shortfall)
        # λ_min: baseline value when constraint is comfortable
        # λ_max: panic value when constraint is urgent
        # γ: curvature exponent (>1 means gradual at first, steep at end)
        # Shadow price parameters from config (controls calorie/nutrition compliance)
        self.shadow_lambda_min = self.config.shadow_lambda_min  # Base penalty when on-track
        self.shadow_lambda_max = self.config.shadow_lambda_max  # Max penalty when behind - INCREASE to tighten calories
        self.shadow_gamma = self.config.shadow_gamma            # Urgency curve shape
        self.shadow_tau = self.config.shadow_tau                # Margin threshold

        # For backward compatibility - use first slot's servings as default
        # (used in functions that don't know current slot)
        self.servings_eaten = self.attendance.max_servings

        # Snack rotation counter (for variety in fruit snacks)
        self._snack_rotation_idx = 0

        # Build package tensors for cost calculation (only if not already built)
        if not package_index._gpu_tensors_built:
            package_index.build_gpu_tensors(recipe_db.ingredient_index, device)

        # === PERFORMANCE: Pooled cooldown mask ===
        # Pre-allocate once and reuse to avoid 1.7GB of allocations per week
        # Max recipe ID is typically ~200k, K up to 200
        max_recipe_id = int(recipe_db.recipe_ids.max().item()) + 1
        self._cooldown_mask_size = max_recipe_id
        self._cooldown_mask_pool = torch.zeros(
            K, max_recipe_id, dtype=torch.bool, device=device
        )

        # === PROGRESSIVE PROTEIN QUOTA ===
        # Replaces cooldowns + tier injection with distribution tracking.
        # Quadratic overuse penalties + linear underuse bonuses steer toward target.
        if self.config.protein_target_distribution is not None:
            self._protein_targets = torch.tensor(
                self.config.protein_target_distribution, dtype=torch.float32, device=device
            )  # [6] — order: beef, pork, poultry, fish, eggs, legumes
            self._protein_strictness = self.config.protein_quota_strictness
            if verbose:
                print(f"  Protein quota: targets={self.config.protein_target_distribution}, strictness={self._protein_strictness}")
        else:
            self._protein_targets = None

        # Static per-recipe tensors reused in hot scoring and transition paths.
        self._recipe_static_cache_key = None
        self._recipe_ing_idx_long = None
        self._recipe_full_amounts = None
        self._recipe_pkg_sizes = None
        self._recipe_pkg_prices = None
        self._recipe_pkg_option_sizes = None
        self._recipe_pkg_option_prices = None
        self._recipe_pkg_shelf_life_days = None
        self._recipe_pkg_starts_frozen = None
        self._recipe_pkg_option_shelf_life_days = None
        self._recipe_pkg_option_starts_frozen = None
        self._recipe_micro_herb_mask = None
        self._fresh_herb_ingredient_mask = None
        self._refresh_recipe_static_tensors()

    def _fresh_herb_mask_for_ingredients(self) -> torch.Tensor:
        """Return [num_ingredients] mask for fresh-herb FNDDS ingredients."""
        if (
            self._fresh_herb_ingredient_mask is not None
            and self._fresh_herb_ingredient_mask.shape[0] == self.db.num_ingredients
        ):
            return self._fresh_herb_ingredient_mask

        mask = torch.zeros(self.db.num_ingredients, dtype=torch.bool, device=self.device)
        for idx, fpid in self.db.ingredient_index.idx_to_fpid.items():
            if idx < self.db.num_ingredients and is_fresh_herb_fpid(fpid):
                mask[idx] = True
        self._fresh_herb_ingredient_mask = mask
        return mask

    def _micro_fresh_herb_package_mask(
        self,
        ing_idx_long: torch.Tensor,
        full_amounts: torch.Tensor,
    ) -> torch.Tensor:
        """Fresh-herb uses at this size behave like seasoning/garnish, not full bunches."""
        max_g = float(getattr(self.config, 'fresh_herb_micro_use_max_g', 0.0) or 0.0)
        if max_g <= 0:
            return torch.zeros_like(full_amounts, dtype=torch.bool)

        herb_mask = self._fresh_herb_mask_for_ingredients()
        herb_at_ing = herb_mask[ing_idx_long.clamp(min=0, max=herb_mask.shape[0] - 1)]
        return herb_at_ing & (full_amounts > 0) & (full_amounts <= max_g)

    def _fresh_ttl_for_recipe_positions(
        self,
        recipe_indices: torch.Tensor,
        ingredient_indices: torch.Tensor,
    ) -> torch.Tensor:
        """Return purchase TTLs, with micro fresh herbs treated as pantry seasonings."""
        fresh_ttl = self.perishability.shelf_life_tensor[ingredient_indices.long()]
        if self._recipe_micro_herb_mask is None:
            return fresh_ttl

        micro_mask = self._recipe_micro_herb_mask[recipe_indices]
        if not micro_mask.any():
            return fresh_ttl

        micro_ttl = torch.full_like(
            fresh_ttl,
            float(getattr(self.config, 'fresh_herb_micro_shelf_days', 365) or 365),
        )
        return torch.where(micro_mask, micro_ttl, fresh_ttl)

    def _purchase_ttl_for_recipe_positions(
        self,
        recipe_indices: torch.Tensor,
        ingredient_indices: torch.Tensor,
        package_option_idx: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Return TTL for newly purchased package remainders."""
        ttl = self._fresh_ttl_for_recipe_positions(recipe_indices, ingredient_indices)
        if package_option_idx is not None and self._recipe_pkg_option_shelf_life_days is not None:
            option_ttl = self._recipe_pkg_option_shelf_life_days[recipe_indices]
            option_idx = package_option_idx.long().clamp(min=0, max=option_ttl.shape[-1] - 1)
            package_ttl = option_ttl.gather(-1, option_idx.unsqueeze(-1)).squeeze(-1)
            if self._recipe_micro_herb_mask is not None:
                package_ttl = torch.where(
                    self._recipe_micro_herb_mask[recipe_indices],
                    torch.full_like(package_ttl, -1.0),
                    package_ttl,
                )
            return torch.where(package_ttl >= 0, package_ttl, ttl)

        if self._recipe_pkg_shelf_life_days is None:
            return ttl

        package_ttl = self._recipe_pkg_shelf_life_days[recipe_indices]
        if self._recipe_micro_herb_mask is not None:
            package_ttl = torch.where(
                self._recipe_micro_herb_mask[recipe_indices],
                torch.full_like(package_ttl, -1.0),
                package_ttl,
            )
        return torch.where(package_ttl >= 0, package_ttl, ttl)

    def _purchase_frozen_for_recipe_positions(
        self,
        recipe_indices: torch.Tensor,
        ingredient_indices: torch.Tensor,
        package_option_idx: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Return whether newly purchased package remainders start frozen."""
        if package_option_idx is not None and self._recipe_pkg_option_starts_frozen is not None:
            option_frozen = self._recipe_pkg_option_starts_frozen[recipe_indices]
            option_idx = package_option_idx.long().clamp(min=0, max=option_frozen.shape[-1] - 1)
            starts_frozen = option_frozen.gather(-1, option_idx.unsqueeze(-1)).squeeze(-1)
            if self._recipe_micro_herb_mask is not None:
                starts_frozen = torch.where(
                    self._recipe_micro_herb_mask[recipe_indices],
                    torch.zeros_like(starts_frozen),
                    starts_frozen,
                )
            return starts_frozen

        if self._recipe_pkg_starts_frozen is None:
            return torch.zeros_like(ingredient_indices, dtype=torch.bool)

        starts_frozen = self._recipe_pkg_starts_frozen[recipe_indices]
        if self._recipe_micro_herb_mask is not None:
            starts_frozen = torch.where(
                self._recipe_micro_herb_mask[recipe_indices],
                torch.zeros_like(starts_frozen),
                starts_frozen,
            )
        return starts_frozen

    def _refresh_recipe_static_tensors(self) -> None:
        """Build static per-recipe tensors reused in hot paths."""
        cache_key = (
            int(self.db.num_recipes),
            int(self.db.num_ingredients),
            int(self.package_index._gpu_prices.shape[0]) if self.package_index._gpu_prices is not None else -1,
            int(self.package_index._gpu_option_prices.shape[1]) if getattr(self.package_index, '_gpu_option_prices', None) is not None else -1,
            int(self.package_index._gpu_package_shelf_life_days.shape[0]) if getattr(self.package_index, '_gpu_package_shelf_life_days', None) is not None else -1,
            int(self.package_index._gpu_package_starts_frozen.shape[0]) if getattr(self.package_index, '_gpu_package_starts_frozen', None) is not None else -1,
            int(self.package_index._gpu_option_shelf_life_days.shape[1]) if getattr(self.package_index, '_gpu_option_shelf_life_days', None) is not None else -1,
            int(self.package_index._gpu_option_starts_frozen.shape[1]) if getattr(self.package_index, '_gpu_option_starts_frozen', None) is not None else -1,
            float(getattr(self.config, 'fresh_herb_micro_use_max_g', 0.0) or 0.0),
            float(getattr(self.config, 'fresh_herb_micro_package_g', 4.0) or 4.0),
            float(getattr(self.config, 'fresh_herb_micro_price_per_g', 0.10) or 0.10),
        )
        if self._recipe_static_cache_key == cache_key:
            return

        ing_idx_long = self.db.ingredient_indices.long()
        self._recipe_ing_idx_long = ing_idx_long
        self._recipe_full_amounts = self.db.ingredient_amounts.float() * self.db.servings.float().view(-1, 1)
        pkg_sizes = self.package_index._gpu_sizes[ing_idx_long]
        pkg_prices = self.package_index._gpu_prices[ing_idx_long]
        pkg_option_sizes_src = getattr(self.package_index, '_gpu_option_sizes', None)
        pkg_option_prices_src = getattr(self.package_index, '_gpu_option_prices', None)
        if pkg_option_sizes_src is not None and pkg_option_prices_src is not None:
            pkg_option_sizes = pkg_option_sizes_src[ing_idx_long]
            pkg_option_prices = pkg_option_prices_src[ing_idx_long]
        else:
            pkg_option_sizes = pkg_sizes.unsqueeze(-1)
            pkg_option_prices = pkg_prices.unsqueeze(-1)
        pkg_shelf_days_src = getattr(self.package_index, '_gpu_package_shelf_life_days', None)
        if pkg_shelf_days_src is not None:
            pkg_shelf_days = pkg_shelf_days_src[ing_idx_long]
        else:
            pkg_shelf_days = torch.full_like(pkg_sizes, -1.0)
        pkg_starts_frozen_src = getattr(self.package_index, '_gpu_package_starts_frozen', None)
        if pkg_starts_frozen_src is not None:
            pkg_starts_frozen = pkg_starts_frozen_src[ing_idx_long]
        else:
            pkg_starts_frozen = torch.zeros_like(pkg_sizes, dtype=torch.bool)
        pkg_option_shelf_days_src = getattr(self.package_index, '_gpu_option_shelf_life_days', None)
        if pkg_option_shelf_days_src is not None:
            pkg_option_shelf_days = pkg_option_shelf_days_src[ing_idx_long]
        else:
            pkg_option_shelf_days = torch.full_like(pkg_option_sizes, -1.0)
        pkg_option_starts_frozen_src = getattr(self.package_index, '_gpu_option_starts_frozen', None)
        if pkg_option_starts_frozen_src is not None:
            pkg_option_starts_frozen = pkg_option_starts_frozen_src[ing_idx_long]
        else:
            pkg_option_starts_frozen = torch.zeros_like(pkg_option_sizes, dtype=torch.bool)

        micro_herb_mask = self._micro_fresh_herb_package_mask(ing_idx_long, self._recipe_full_amounts)
        if micro_herb_mask.any():
            micro_package_g = max(
                1.0,
                float(getattr(self.config, 'fresh_herb_micro_package_g', 4.0) or 4.0),
            )
            micro_price_per_g = max(
                0.0,
                float(getattr(self.config, 'fresh_herb_micro_price_per_g', 0.10) or 0.10),
            )
            micro_size = torch.full_like(pkg_sizes, micro_package_g)
            micro_price = torch.full_like(pkg_prices, micro_package_g * micro_price_per_g)
            pkg_sizes = torch.where(micro_herb_mask, micro_size, pkg_sizes)
            pkg_prices = torch.where(micro_herb_mask, micro_price, pkg_prices)
            micro_option_mask = micro_herb_mask.unsqueeze(-1)
            pkg_option_sizes = torch.where(
                micro_option_mask,
                torch.full_like(pkg_option_sizes, micro_package_g),
                pkg_option_sizes,
            )
            pkg_option_prices = torch.where(
                micro_option_mask,
                torch.full_like(pkg_option_prices, micro_package_g * micro_price_per_g),
                pkg_option_prices,
            )
            pkg_shelf_days = torch.where(
                micro_herb_mask,
                torch.full_like(pkg_shelf_days, -1.0),
                pkg_shelf_days,
            )
            pkg_starts_frozen = torch.where(
                micro_herb_mask,
                torch.zeros_like(pkg_starts_frozen),
                pkg_starts_frozen,
            )
            pkg_option_shelf_days = torch.where(
                micro_option_mask,
                torch.full_like(pkg_option_shelf_days, -1.0),
                pkg_option_shelf_days,
            )
            pkg_option_starts_frozen = torch.where(
                micro_option_mask,
                torch.zeros_like(pkg_option_starts_frozen),
                pkg_option_starts_frozen,
            )

        self._recipe_pkg_sizes = pkg_sizes
        self._recipe_pkg_prices = pkg_prices
        self._recipe_pkg_option_sizes = pkg_option_sizes
        self._recipe_pkg_option_prices = pkg_option_prices
        self._recipe_pkg_shelf_life_days = pkg_shelf_days
        self._recipe_pkg_starts_frozen = pkg_starts_frozen
        self._recipe_pkg_option_shelf_life_days = pkg_option_shelf_days
        self._recipe_pkg_option_starts_frozen = pkg_option_starts_frozen
        self._recipe_micro_herb_mask = micro_herb_mask
        self._recipe_static_cache_key = cache_key

    def _per_person_daily_calories(self) -> float:
        """Return the configured daily calorie target per person."""
        household_size = max(1, len(self.attendance.household.people))
        return (self.weekly_calories / 7.0) / household_size

    def _debug_purchase_ingredients(
        self,
        ing_idx: torch.Tensor,
        full_amt: torch.Tensor,
        pantry_take: torch.Tensor,
        to_buy: torch.Tensor,
        num_pkg: torch.Tensor,
        pkg_sizes: torch.Tensor,
        pkg_prices: torch.Tensor,
    ) -> List[Dict[str, Any]]:
        """Audit-only purchase trace for one freshly cooked recipe event."""
        rows: List[Dict[str, Any]] = []
        ing_idx_cpu = ing_idx.detach().cpu().tolist()
        full_cpu = full_amt.detach().float().cpu().tolist()
        take_cpu = pantry_take.detach().float().cpu().tolist()
        buy_cpu = to_buy.detach().float().cpu().tolist()
        pkg_cpu = num_pkg.detach().float().cpu().tolist()
        size_cpu = pkg_sizes.detach().float().cpu().tolist()
        price_cpu = pkg_prices.detach().float().cpu().tolist()

        for pos, idx_val in enumerate(ing_idx_cpu):
            required_g = float(full_cpu[pos])
            pantry_used_g = float(take_cpu[pos])
            bought_packages = float(pkg_cpu[pos])
            if required_g <= 0 and pantry_used_g <= 0 and bought_packages <= 0:
                continue

            ingredient_idx = int(idx_val)
            fpid = str(self.db.ingredient_index.idx_to_fpid.get(ingredient_idx, ""))
            package_size_g = float(size_cpu[pos])
            bought_g = bought_packages * package_size_g
            package_price = float(price_cpu[pos])
            rows.append({
                "fpid": fpid,
                "ingredient_idx": ingredient_idx,
                "recipe_required_g": required_g,
                "pantry_used_g": pantry_used_g,
                "to_buy_g": float(buy_cpu[pos]),
                "packages_bought": bought_packages,
                "package_size_g": package_size_g,
                "package_price": package_price,
                "bought_g": bought_g,
                "remainder_g": bought_g - float(buy_cpu[pos]),
                "package_display": self.package_index.get_size_display(fpid, package_size_g),
            })

        return rows

    # =====================================================================
    # Deterministic ranking helpers
    # =====================================================================
    # CPU and GPU break ties differently in topk/argsort/argmin because
    # floating-point reductions (sum, matmul) accumulate in different
    # order, producing scores that differ by ~1e-6.  Quantizing to
    # fixed precision kills this noise; the index tiebreaker guarantees
    # identical ordering across devices when values are truly equal.

    @staticmethod
    def _stable_topk(
        scores: torch.Tensor, k: int, largest: bool = False, dim: int = -1
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """topk with deterministic tie-breaking across CPU/CUDA/MPS.

        On CPU/CUDA: float64 with 1e-12 tiebreaker.
        On MPS: float32 with 1e-7 tiebreaker (MPS lacks float64).
        """
        _f64 = scores.device.type != 'mps'
        q = scores.double() if _f64 else scores.float()
        n = q.shape[dim]
        _dt = torch.float64 if _f64 else torch.float32
        _eps = 1e-12 if _f64 else 1e-7
        tb = torch.arange(n, device=q.device, dtype=_dt) * _eps
        shape = [1] * q.ndim
        shape[dim] = n
        tb = tb.view(shape)
        if largest:
            q = q - tb
        else:
            q = q + tb
        vals, idx = torch.topk(q, k=k, largest=largest, dim=dim)
        return vals.float(), idx

    @staticmethod
    def _choose_package_options(
        to_buy: torch.Tensor,
        package_sizes: torch.Tensor,
        package_prices: torch.Tensor,
        remainder_penalty_per_kg: float = 0.0,
        return_indices: bool = False,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Choose the cheapest package option for the actual grams needed.

        `package_sizes` and `package_prices` have one extra trailing dimension:
        the package-option menu. Broadcasting handles the beam and recipe
        dimensions. This replaces the old shortcut that picked one global
        package per ingredient, which made a 36 fl oz ranch bottle look normal
        even when the recipe only needed a few tablespoons.
        """
        # Preserve real sub-gram spice packets (for example 0.5g saffron).
        # The old 1g clamp created fake package sizes and could underbuy tiny
        # packages while making purchase audit rows impossible to match to SKUs.
        safe_sizes = package_sizes.clamp(min=1e-6)
        needed = to_buy.unsqueeze(-1)
        ratio = needed / safe_sizes
        rounded = torch.round(ratio).clamp(min=1.0)
        close_to_whole_package = torch.abs(ratio - rounded) <= 0.005
        num_packages = torch.where(close_to_whole_package, rounded, torch.ceil(ratio))
        num_packages = num_packages * (needed > 0).float()

        option_cost = num_packages * package_prices
        option_purchased = num_packages * safe_sizes
        option_remainder = (option_purchased - needed).clamp(min=0)
        # Equal-cost ties should not grow pantry unnecessarily.
        ranking_cost = (
            option_cost
            + option_remainder * (float(remainder_penalty_per_kg) / 1000.0)
            + option_purchased * 1e-8
        )
        best_idx = ranking_cost.argmin(dim=-1)
        gather_idx = best_idx.unsqueeze(-1)

        expanded_sizes = safe_sizes
        expanded_prices = package_prices
        while expanded_sizes.dim() < option_cost.dim():
            expanded_sizes = expanded_sizes.unsqueeze(0)
            expanded_prices = expanded_prices.unsqueeze(0)
        expanded_sizes = expanded_sizes.expand_as(option_cost)
        expanded_prices = expanded_prices.expand_as(option_cost)
        selected_packages = num_packages.gather(-1, gather_idx).squeeze(-1)
        selected_sizes = expanded_sizes.gather(-1, gather_idx).squeeze(-1)
        selected_prices = expanded_prices.gather(-1, gather_idx).squeeze(-1)
        selected_purchased = option_purchased.gather(-1, gather_idx).squeeze(-1)
        selected_cost = option_cost.gather(-1, gather_idx).squeeze(-1)
        if return_indices:
            return selected_packages, selected_sizes, selected_prices, selected_purchased, selected_cost, best_idx
        return selected_packages, selected_sizes, selected_prices, selected_purchased, selected_cost

    @staticmethod
    def _stable_argsort(
        scores: torch.Tensor, descending: bool = False, dim: int = -1
    ) -> torch.Tensor:
        """argsort with deterministic tie-breaking across CPU/CUDA/MPS."""
        _f64 = scores.device.type != 'mps'
        q = scores.double() if _f64 else scores.float()
        n = q.shape[dim]
        _dt = torch.float64 if _f64 else torch.float32
        _eps = 1e-12 if _f64 else 1e-7
        tb = torch.arange(n, device=q.device, dtype=_dt) * _eps
        shape = [1] * q.ndim
        shape[dim] = n
        tb = tb.view(shape)
        if descending:
            q = q - tb
        else:
            q = q + tb
        return torch.argsort(q, dim=dim, descending=descending)

    @staticmethod
    def _stable_argmin(scores: torch.Tensor, dim: int = -1) -> torch.Tensor:
        """argmin with deterministic tie-breaking across CPU/CUDA/MPS."""
        _f64 = scores.device.type != 'mps'
        q = scores.double() if _f64 else scores.float()
        n = q.shape[dim]
        _dt = torch.float64 if _f64 else torch.float32
        _eps = 1e-12 if _f64 else 1e-7
        tb = torch.arange(n, device=q.device, dtype=_dt) * _eps
        shape = [1] * q.ndim
        shape[dim] = n
        tb = tb.view(shape)
        return (q + tb).argmin(dim=dim)

    @staticmethod
    def _deterministic_scatter_add(
        target: torch.Tensor, dim: int, index: torch.Tensor, src: torch.Tensor
    ) -> torch.Tensor:
        """scatter_add that is deterministic on CUDA.

        Falls back to index_put_ with accumulate=True which PyTorch
        guarantees to be deterministic when torch.use_deterministic_algorithms
        is enabled, but even without that flag, this formulation avoids the
        race-condition non-determinism of scatter_add_ on CUDA.
        """
        # For the 1-D pantry case (dim=0, flat tensors): use a for-loop
        # grouped by unique index to guarantee order-independent accumulation.
        if dim == 0 and index.ndim == 1:
            # Sort by index so identical keys are adjacent → deterministic sum
            sorted_idx = index.argsort()
            sorted_index = index[sorted_idx]
            sorted_src = src[sorted_idx]
            target.index_put_((sorted_index,), sorted_src, accumulate=True)
            return target
        # General fallback: use index_put_ with accumulate
        target.scatter_add_(dim, index, src)
        return target

    def _build_title_ingredient_sanity_mask(self) -> Optional[torch.Tensor]:
        """Exclude title/ingredient mismatches like 50g pork for pork chops.

        Recipe CSV ingredient grams are trusted for accounting, so rows whose
        title promises a meat/fish main while the full recipe contains only a
        garnish-sized amount should not be eligible planner candidates.
        """
        names = getattr(self.db, "names", None)
        if not names:
            return None

        rules = [
            (
                "pork",
                ("22", "25"),
                (
                    re.compile(r"\bpork\b"),
                    re.compile(r"\bham\b"),
                    re.compile(r"\bchops\b"),
                    re.compile(r"\bbacon\s+roast\b"),
                    re.compile(r"\broast\s+beast\b"),
                ),
                (re.compile(r"\blamb\b"), re.compile(r"\bveal\b")),
            ),
            (
                "beef",
                ("21",),
                (re.compile(r"\bbeef\b"), re.compile(r"\bsteaks?\b"), re.compile(r"\bbrisket\b")),
                (re.compile(r"\blamb\b"), re.compile(r"\bveal\b"), re.compile(r"\btuna\b")),
            ),
            (
                "poultry",
                ("24",),
                (re.compile(r"\bchicken\b"), re.compile(r"\bturkey\b")),
                (),
            ),
            (
                "seafood",
                ("26",),
                (
                    re.compile(r"\bfish\b"),
                    re.compile(r"\bsalmon\b"),
                    re.compile(r"\btuna\b"),
                    re.compile(r"\bshrimp\b"),
                    re.compile(r"\bcod\b"),
                    re.compile(r"\btilapia\b"),
                    re.compile(r"\bhalibut\b"),
                ),
                (),
            ),
        ]

        ing_idx = self.db.ingredient_indices.long()
        max_nnz = ing_idx.shape[1]
        positions = torch.arange(max_nnz, device=self.device).unsqueeze(0)
        valid_mask = positions < self.db.nnz.long().unsqueeze(1)
        full_amounts = self.db.ingredient_amounts.float() * self.db.servings.float().view(-1, 1)
        servings = self.db.servings.float().clamp(min=1.0)
        min_claimed_meat_g = torch.maximum(
            servings * 56.0,
            torch.full_like(servings, 150.0),
        )

        safe = torch.ones(self.db.num_recipes, dtype=torch.bool, device=self.device)
        idx_to_fpid = self.db.ingredient_index.idx_to_fpid
        total_excluded = 0

        normalized_names = [
            " " + re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip() + " "
            for name in names
        ]

        for label, prefixes, patterns, negative_patterns in rules:
            ingredient_match = torch.zeros(self.db.num_ingredients, dtype=torch.bool, device=self.device)
            for ingredient_idx, fpid in idx_to_fpid.items():
                fpid_str = str(fpid)
                if any(fpid_str.startswith(prefix) for prefix in prefixes):
                    ingredient_match[int(ingredient_idx)] = True

            if not ingredient_match.any():
                continue

            title_hit_cpu = [
                any(pattern.search(normalized) for pattern in patterns)
                and not any(pattern.search(normalized) for pattern in negative_patterns)
                for normalized in normalized_names
            ]
            title_hit = torch.tensor(title_hit_cpu, dtype=torch.bool, device=self.device)
            if not title_hit.any():
                continue

            group_grams = torch.where(
                ingredient_match[ing_idx] & valid_mask,
                full_amounts,
                torch.zeros_like(full_amounts),
            ).sum(dim=1)
            invalid = title_hit & (group_grams < min_claimed_meat_g)
            excluded = int(invalid.sum().item())
            if excluded:
                safe &= ~invalid
                total_excluded += excluded
                if getattr(self, 'verbose', False):
                    print(
                        f"  [DataQuality] Excluding {excluded:,} {label}-title recipes "
                        f"with garnish-sized {label} grams"
                    )

        if total_excluded == 0:
            return None

        if getattr(self, 'verbose', False):
            remaining = int(safe.sum().item())
            print(
                f"  [DataQuality] Excluding {total_excluded:,} title/ingredient mismatches, "
                f"{remaining:,} recipes remaining"
            )

        return safe

    def _build_allergen_recipe_mask(
        self, allergen_exclusions: Optional[List[str]]
    ) -> Optional[torch.Tensor]:
        """Build a boolean mask [num_recipes] where True = safe, False = contains excluded ingredient.

        Uses FNDDS code prefix matching: each allergen maps to one or more
        FNDDS prefixes (e.g. "pork" → "22", "dairy" → "11","12","13","14").
        A recipe is unsafe if ANY of its ingredients start with an excluded prefix.

        Returns None if no exclusions requested (skip filtering entirely).
        """
        if not allergen_exclusions:
            return None

        # Collect all FNDDS prefixes to exclude and calculator-native allergen
        # flags when HESTIA_INGREDIENT_META_JSON is present.
        excluded_prefixes: List[str] = []
        excluded_meta_allergens: Set[str] = set()
        unknown = []
        meta = _ingredient_meta()
        for allergen in allergen_exclusions:
            key = allergen.lower().strip()
            excluded_meta_allergens.add(_meta_allergen_key(key))
            if key in ALLERGEN_FNDDS_PREFIXES:
                excluded_prefixes.extend(ALLERGEN_FNDDS_PREFIXES[key])
            elif not meta:
                unknown.append(key)
        if unknown:
            print(f"  [Allergen] Unknown allergens (ignored): {unknown}")
        if not excluded_prefixes and not excluded_meta_allergens:
            return None

        excluded_prefixes = list(set(excluded_prefixes))  # deduplicate

        # Step 1: Find all ingredient dense indices that match excluded prefixes
        # or calculator-native allergen/protein metadata.
        idx_to_fpid = self.db.ingredient_index.idx_to_fpid
        excluded_ingredient_indices: Set[int] = set()
        for idx, fpid in idx_to_fpid.items():
            fpid_str = str(fpid)
            item_meta = meta.get(fpid_str) or {}
            item_allergens = set(item_meta.get("allergens") or [])
            protein_source = str(item_meta.get("protein_source") or "").lower()
            if item_allergens & excluded_meta_allergens:
                excluded_ingredient_indices.add(idx)
                continue
            if "beef" in excluded_meta_allergens and protein_source == "beef":
                excluded_ingredient_indices.add(idx)
                continue
            if "pork" in excluded_meta_allergens and protein_source == "pork":
                excluded_ingredient_indices.add(idx)
                continue
            if "poultry" in excluded_meta_allergens and protein_source == "poultry":
                excluded_ingredient_indices.add(idx)
                continue
            if "red_meat" in excluded_meta_allergens and protein_source in {"beef", "pork"}:
                excluded_ingredient_indices.add(idx)
                continue
            for prefix in excluded_prefixes:
                if fpid_str.startswith(prefix):
                    excluded_ingredient_indices.add(idx)
                    break

        if not excluded_ingredient_indices:
            print(f"  [Allergen] No matching ingredients for prefixes {excluded_prefixes}")
            return None

        # Step 2: Build recipe mask using vectorized GPU operations
        # Create a boolean tensor of excluded ingredient indices
        excluded_set = torch.zeros(self.db.num_ingredients, dtype=torch.bool, device=self.device)
        for idx in excluded_ingredient_indices:
            if idx < self.db.num_ingredients:
                excluded_set[idx] = True

        # ingredient_indices: [N, MAX_NNZ] — dense indices per recipe
        # nnz: [N] — number of actual ingredients per recipe
        ing_idx = self.db.ingredient_indices.long()  # [N, MAX_NNZ]
        # Look up which ingredients are excluded: [N, MAX_NNZ] bool
        is_excluded = excluded_set[ing_idx]

        # Mask out padding positions (beyond nnz) so they don't count
        max_nnz = ing_idx.shape[1]
        nnz_expanded = self.db.nnz.long().unsqueeze(1)  # [N, 1]
        positions = torch.arange(max_nnz, device=self.device).unsqueeze(0)  # [1, MAX_NNZ]
        valid_mask = positions < nnz_expanded  # [N, MAX_NNZ]
        is_excluded = is_excluded & valid_mask

        # Recipe is unsafe if ANY ingredient is excluded
        unsafe = is_excluded.any(dim=1)  # [N]
        safe_mask = ~unsafe  # [N] True = safe

        num_unsafe = unsafe.sum().item()
        num_safe = safe_mask.sum().item()
        print(f"  [Allergen] Excluding {allergen_exclusions}: "
              f"{len(excluded_ingredient_indices)} ingredients matched, "
              f"{num_unsafe:,} recipes excluded, {num_safe:,} recipes remaining")

        return safe_mask

    def _build_ingredient_flag(self, prefixes: List[str]) -> torch.Tensor:
        """Build a boolean mask [num_recipes] where True = recipe contains an ingredient
        matching any of the given FNDDS prefixes. Used for kosher meat/dairy detection."""
        idx_to_fpid = self.db.ingredient_index.idx_to_fpid
        matched_indices: Set[int] = set()
        prefix_set = set(prefixes)
        meta = _ingredient_meta()
        for idx, fpid in idx_to_fpid.items():
            fpid_str = str(fpid)
            item_meta = meta.get(fpid_str) or {}
            item_allergens = set(item_meta.get("allergens") or [])
            protein_source = str(item_meta.get("protein_source") or "").lower()
            if prefix_set & {"11", "12", "13", "14", "15"} and "milk" in item_allergens:
                matched_indices.add(idx)
                continue
            if prefix_set & {"21", "23"} and protein_source == "beef":
                matched_indices.add(idx)
                continue
            if "22" in prefix_set and protein_source == "pork":
                matched_indices.add(idx)
                continue
            if "24" in prefix_set and protein_source == "poultry":
                matched_indices.add(idx)
                continue
            for prefix in prefixes:
                if fpid_str.startswith(prefix):
                    matched_indices.add(idx)
                    break

        if not matched_indices:
            return torch.zeros(self.db.num_recipes, dtype=torch.bool, device=self.device)

        flag_set = torch.zeros(self.db.num_ingredients, dtype=torch.bool, device=self.device)
        for idx in matched_indices:
            if idx < self.db.num_ingredients:
                flag_set[idx] = True

        ing_idx = self.db.ingredient_indices.long()
        has_match = flag_set[ing_idx]  # [N, MAX_NNZ]

        max_nnz = ing_idx.shape[1]
        nnz_expanded = self.db.nnz.long().unsqueeze(1)
        positions = torch.arange(max_nnz, device=self.device).unsqueeze(0)
        valid_mask = positions < nnz_expanded
        has_match = has_match & valid_mask

        return has_match.any(dim=1)  # [N] True = contains matching ingredient

    def _sparse_score(
        self,
        recipe_indices: torch.Tensor,  # [N] indices into recipe database
        pantries: torch.Tensor,  # [K, I] current pantry states
        current_nutrition: torch.Tensor,  # [K, 2] cumulative nutrition
        slot: int,
        used_ids: torch.Tensor,  # [K, COOLDOWN_LEN] variety ring
        servings_to_cook: torch.Tensor,  # [K] servings needed
        is_side: bool = False,
    ) -> torch.Tensor:
        """
        Score recipes against pantries using SPARSE operations.

        Instead of [K, N, I] dense tensor (79 GB for dinner),
        we gather only the non-zero ingredients: [K, N, nnz] (~900 MB).

        Returns: [K, N] scores (lower = better)
        """
        K = pantries.shape[0]
        N = recipe_indices.shape[0]

        if N == 0:
            return torch.full((K, 0), float('inf'), device=self.device)

        # Gather recipe data for these indices
        indices = recipe_indices.long()

        # Sparse ingredients: [N, MAX_NNZ]
        ing_idx = self._recipe_ing_idx_long[indices]  # [N, MAX_NNZ] ingredient indices
        recipe_nnz = self.db.nnz[indices]  # [N] actual nnz per recipe

        # Recipe metadata
        recipe_nutr = self.db.nutrition[indices].float()  # [N, 2]
        recipe_ids = self.db.recipe_ids[indices]  # [N]

        # === SPARSE SCORING ===
        # For each recipe, gather pantry values at its ingredient indices
        # Key: avoid creating [K, N, I] tensor!

        # ing_idx: [N, MAX_NNZ] contains ingredient indices
        # pantries: [K, I] contains pantry values
        # We want pantry_gathered[k, n, j] = pantries[k, ing_idx[n, j]]

        # Flatten ing_idx for advanced indexing: [N * MAX_NNZ]
        ing_idx_flat = ing_idx.flatten()  # [N * MAX_NNZ]

        # Index pantries: [K, N * MAX_NNZ] then reshape
        # pantries[:, ing_idx_flat] gives [K, N * MAX_NNZ]
        pantry_gathered = pantries[:, ing_idx_flat].view(K, N, MAX_NNZ)  # [K, N, MAX_NNZ]

        # Full batch ingredient amounts are static per recipe.
        full_amounts = self._recipe_full_amounts[indices].unsqueeze(0)  # [1, N, MAX_NNZ]

        # Overlap = min(what pantry has, what recipe needs)
        overlap = torch.minimum(pantry_gathered, full_amounts)  # [K, N, MAX_NNZ]

        # Sum per recipe (for pantry bonus calculation)
        # Use float64 summation to eliminate CPU/CUDA accumulation-order divergence
        total_overlap = torch.round(overlap.float().sum(dim=2) * 100.0).float() / 100.0  # [K, N]
        total_needed = torch.round(full_amounts.float().sum(dim=2) * 100.0).float() / 100.0  # [K, N]

        # === PACKAGE-BASED COST CALCULATION ===
        # What we need to buy per ingredient: [K, N, MAX_NNZ]
        to_buy_per_ing = (full_amounts - overlap).clamp(min=0)  # [K, N, MAX_NNZ]

        # Choose package sizes/prices for the actual amount needed at each ingredient.
        pkg_sizes = self._recipe_pkg_option_sizes[indices]  # [N, MAX_NNZ, P]
        pkg_prices = self._recipe_pkg_option_prices[indices]  # [N, MAX_NNZ, P]
        num_packages, _, _, _, ingredient_cost = self._choose_package_options(
            to_buy_per_ing,
            pkg_sizes,
            pkg_prices,
            getattr(self.config, "package_remainder_choice_penalty_per_kg", 0.0),
        )

        # Total purchase cost per recipe: sum over ingredients
        # float64 sum + round to eliminate CPU/CUDA divergence
        purchase_cost = torch.round(ingredient_cost.float().sum(dim=2) * 100.0).float() / 100.0  # [K, N]

        # NOTE: No pantry_bonus - purchase_cost already excludes pantry items
        # NOTE: No leftover_bonus - leftovers are handled via consumption, not creation incentives
        # The cost is simply: what we need to buy (pantry items = $0)
        effective_cost = purchase_cost

        # === NUTRITION PENALTY ===
        # Target range: Calories 90-105%, Protein more flexible
        # User has snacks for minor calorie gaps, but don't overfeed
        remaining = max(NUM_SLOTS - slot, 1)
        current_cal = current_nutrition[:, 0]  # [K]
        current_prot = current_nutrition[:, 1]  # [K]

        # Calorie targets with bounds (now configurable)
        cal_target_remaining = self.weekly_calories - current_cal  # What we still need
        cal_min_remaining = self.weekly_calories * self.config.calorie_floor_pct - current_cal  # Floor
        cal_max_remaining = self.weekly_calories * self.config.calorie_ceiling_pct - current_cal  # Ceiling

        cal_pace_target = cal_target_remaining.clamp(min=0) / remaining
        cal_pace_min = cal_min_remaining / remaining  # Can be negative if already over 90%
        cal_pace_max = cal_max_remaining / remaining  # Upper bound per meal

        prot_debt = (self.weekly_protein - current_prot).clamp(min=0)
        prot_pace = prot_debt / remaining

        # Recipe nutrition for servings eaten (per-slot attendance)
        slot_servings = self.servings_per_slot[slot].item()
        if self.config.enable_dynamic_servings:
            # With dynamic servings, effective cal/srv = total_cal / dynamic_servings ≈ target
            # Using original cal/srv here adds noise that fights cost optimization
            dyn_srv, _ = self._compute_dynamic_servings(recipe_indices, slot, meal_type, 'main' if not is_side else 'side')
            effective_cal = self.db.total_calories[recipe_indices.long()] / dyn_srv.clamp(min=1)
            original_cal = recipe_nutr[:, 0].clamp(min=1.0)
            cal_ratio = effective_cal / original_cal
            recipe_cal = effective_cal * slot_servings  # [N]
            recipe_prot = recipe_nutr[:, 1] * cal_ratio * slot_servings  # [N] scale protein proportionally
        else:
            recipe_cal = recipe_nutr[:, 0] * slot_servings  # [N]
            recipe_prot = recipe_nutr[:, 1] * slot_servings  # [N]

        # Calorie penalties: under floor OR over ceiling
        cal_under_floor = (cal_pace_min.view(K, 1) - recipe_cal.view(1, N)).clamp(min=0)  # Too few cals
        cal_over_ceiling = (recipe_cal.view(1, N) - cal_pace_max.view(K, 1)).clamp(min=0)  # Too many cals

        prot_short = (prot_pace.view(K, 1) - recipe_prot.view(1, N)).clamp(min=0)

        # Calories: penalize being under floor OR over ceiling
        # Over ceiling is worse (can't un-eat food, but can add snacks)
        # cal_over_ceiling_mult controls how much worse (default 2.0)
        base_lambda_cal = self.config.base_lambda_cal * (0.3 if is_side else 1.0)
        base_lambda_prot = 0.02 * (0.3 if is_side else 1.0)

        cal_penalty = base_lambda_cal * cal_under_floor + base_lambda_cal * self.config.cal_over_ceiling_mult * cal_over_ceiling
        prot_penalty = base_lambda_prot * prot_short

        nutrition_penalty = cal_penalty + prot_penalty

        # === VARIETY PENALTY ===
        # Check if recipe is in cooldown ring (OPTIMIZED: scatter/gather)
        # Use pooled cooldown mask to avoid 200MB allocation per call
        max_recipe_id = max(recipe_ids.max().item(), used_ids.max().item()) + 1
        if K <= self._cooldown_mask_pool.shape[0] and max_recipe_id <= self._cooldown_mask_size:
            # Use pre-allocated pool (fast path)
            cooldown_mask = self._cooldown_mask_pool[:K, :max_recipe_id]
            cooldown_mask.zero_()  # Reset to False
        else:
            # Fallback: allocate new tensor if IDs exceed pool size (rare)
            cooldown_mask = torch.zeros(K, max_recipe_id, dtype=torch.bool, device=self.device)
        cooldown_mask.scatter_(1, used_ids, True)
        in_cooldown = cooldown_mask[:, recipe_ids]  # [K, N]
        # Don't delete - it's either a view of pool or will be GC'd

        # Count how many used_ids are non-zero (active in cooldown)
        active_cooldown = (used_ids > 0).sum(dim=1).float().mean().item()
        blocked_by_variety = in_cooldown.sum().item()

        variety_penalty = torch.where(
            in_cooldown,
            torch.tensor(self.config.variety_penalty, device=self.device),
            torch.tensor(0.0, device=self.device),
        )

        # Store stats for debug output
        self._last_variety_stats = {
            'active_cooldown': active_cooldown,
            'blocked_recipes': blocked_by_variety,
            'total_recipes': K * N,
        }

        # === COMPLEXITY PENALTY ===
        complexity = recipe_nnz.float().view(1, N) * self.config.complexity_weight  # [1, N]

        # === MINIMUM QUALITY REQUIREMENTS ===
        # Penalize recipes that aren't real food
        min_cal_per_serving = self.config.min_cal_per_serving
        max_cal_per_serving = self.config.max_cal_per_serving
        min_ingredients = self.config.min_ingredients

        recipe_cal_per_srv = recipe_nutr[:, 0]  # [N]
        low_cal_penalty = torch.where(
            recipe_cal_per_srv < min_cal_per_serving,
            torch.tensor(self.config.low_cal_penalty, device=self.device),  # Heavy penalty for non-food
            torch.tensor(0.0, device=self.device),
        ).view(1, N)

        # === MAX CALORIE PENALTY (for fresh mode or dynamic cap) ===
        # When max_cal_per_serving > 0, penalize calorie-dense recipes
        # This prevents overfeeding in fresh mode by excluding 600+ cal/srv casseroles
        #
        # DYNAMIC CAP: If max_cal_per_serving == 0, use 40% of daily target
        # This prevents absurd recipes like 2508 cal/srv for a 2000 cal/day person
        effective_max_cal = max_cal_per_serving
        if effective_max_cal == 0:
            # Dynamic cap: one serving should not exceed 40% of daily calories
            daily_cal = self._per_person_daily_calories()
            effective_max_cal = daily_cal * 0.40  # 800 cal/srv for 2000 cal/day

        high_cal_penalty = torch.zeros(1, N, device=self.device)
        if effective_max_cal > 0:
            high_cal_penalty = torch.where(
                recipe_cal_per_srv > effective_max_cal,
                torch.tensor(self.config.high_cal_penalty, device=self.device),  # Heavy penalty for calorie-dense
                torch.tensor(0.0, device=self.device),
            ).view(1, N)

        low_ing_penalty = torch.where(
            recipe_nnz < min_ingredients,
            torch.tensor(self.config.low_ing_penalty, device=self.device),  # Penalty for incomplete recipes
            torch.tensor(0.0, device=self.device),
        ).view(1, N)

        # === INFLAMMATION PENALTY (Ember Score) ===
        inflammation_penalty = torch.zeros(1, N, device=self.device)
        if self.config.enable_inflammation_scoring and self.ember_scores is not None:
            target = self.config.inflammation_target
            weight = self.config.inflammation_weight
            recipe_ember = self.ember_scores[indices]  # [N]
            shortfall = (target - recipe_ember).clamp(min=0)  # [N]
            inflammation_penalty = (weight * shortfall / 100.0).view(1, N)

        total_score = effective_cost + nutrition_penalty + variety_penalty + complexity + low_cal_penalty + high_cal_penalty + low_ing_penalty + inflammation_penalty

        # FREE intermediate tensors
        del ing_idx_flat, pantry_gathered, full_amounts, overlap
        del total_overlap, total_needed, to_buy_per_ing, pkg_sizes, pkg_prices, num_packages

        return total_score  # [K, N]

    def _sparse_score_batched(
        self,
        recipe_indices: torch.Tensor,
        pantries: torch.Tensor,
        current_nutrition: torch.Tensor,
        slot: int,
        used_ids: torch.Tensor,
        servings_to_cook: torch.Tensor,
        is_side: bool = False,
        batch_size: int = 100,
    ) -> torch.Tensor:
        """
        Batched version of _sparse_score for large K.
        Processes frontiers in batches to avoid OOM.
        """
        K = pantries.shape[0]

        if K <= batch_size:
            return self._sparse_score(
                recipe_indices, pantries, current_nutrition, slot,
                used_ids, servings_to_cook, is_side
            )

        # Process in batches
        all_scores = []
        for k_start in range(0, K, batch_size):
            k_end = min(k_start + batch_size, K)
            batch_scores = self._sparse_score(
                recipe_indices,
                pantries[k_start:k_end],
                current_nutrition[k_start:k_end],
                slot,
                used_ids[k_start:k_end],
                servings_to_cook[k_start:k_end],
                is_side,
            )
            all_scores.append(batch_scores)

        return torch.cat(all_scores, dim=0)

    def _compute_incremental_cost(
        self,
        pantries: torch.Tensor,         # [K, I]
        recipe_indices: torch.Tensor,   # [N] indices into recipe database
        slot_servings: float = 4.0,     # Servings needed for this slot (what we'll actually cook)
        return_pantry_usage: bool = False,  # If True, also return pantry usage for bonus
        return_inventory_delta: bool = False,  # If True, also return inventory delta for holding cost
    ) -> torch.Tensor:
        """
        Pass 1 helper: Compute pure incremental cost per recipe.
        Cost = ceil(grams_needed / pkg_size) * pkg_price for items not in pantry.
        Pantry items cost $0.

        IMPORTANT: Uses slot_servings (what we need), not recipe.servings_produced!
        This prevents over-pricing veggie-heavy recipes that have large batch sizes.

        Returns: [K, N] costs (or tuple of (costs, pantry_usage) if return_pantry_usage=True)
        """
        K = pantries.shape[0]
        N = recipe_indices.shape[0]

        if N == 0:
            empty = torch.full((K, 0), float('inf'), device=self.device)
            zeros = torch.zeros((K, 0), device=self.device)
            if return_pantry_usage and return_inventory_delta:
                return empty, zeros, zeros
            elif return_pantry_usage:
                return empty, zeros
            elif return_inventory_delta:
                return empty, zeros
            return empty

        indices = recipe_indices.long()

        # Sparse ingredients: [N, MAX_NNZ]
        ing_idx = self._recipe_ing_idx_long[indices]  # [N, MAX_NNZ]

        # COOK FULL BATCH: Use recipe_servings to calculate ingredient costs
        # We cook the full recipe and store leftovers, so cost is for full batch
        # Leftover bonus in scoring compensates for the extra servings
        full_amounts = self._recipe_full_amounts[indices].unsqueeze(0)  # [1, N, MAX_NNZ]

        # Gather pantry at ingredient positions
        ing_idx_flat = ing_idx.flatten()  # [N * MAX_NNZ]
        pantry_gathered = pantries[:, ing_idx_flat].view(K, N, MAX_NNZ)  # [K, N, MAX_NNZ]

        # Overlap = what we can use from pantry
        overlap = torch.minimum(pantry_gathered, full_amounts)  # [K, N, MAX_NNZ]

        # What we need to buy
        to_buy = (full_amounts - overlap).clamp(min=0)  # [K, N, MAX_NNZ]

        # Package-based cost
        pkg_sizes = self._recipe_pkg_option_sizes[indices]  # [N, MAX_NNZ, P]
        pkg_prices = self._recipe_pkg_option_prices[indices]  # [N, MAX_NNZ, P]
        num_packages, selected_sizes, selected_prices, purchased_grams, ingredient_cost = self._choose_package_options(
            to_buy,
            pkg_sizes,
            pkg_prices,
            getattr(self.config, "package_remainder_choice_penalty_per_kg", 0.0),
        )

        # Total cost per recipe (gross)
        # NOTE: .sum(dim=2) accumulates in different order on CPU vs CUDA,
        # producing float32 rounding differences of ~1e-6.  We sum in float64
        # then round to 0.001 (tenth-of-a-cent) so both devices agree exactly.
        _Q = lambda t: torch.round(t.float().sum(dim=2) * 100.0).float() / 100.0
        gross_cost = _Q(ingredient_cost)  # [K, N]

        # === BULK PACKAGE CREDIT ===
        # Credit the value of unused package contents (will go to pantry)
        # This makes buying large packages more attractive since leftovers have value
        # Example: Buy $6.99 chicken (2700g), use 400g → 2300g leftover worth ~$5.97
        leftover_grams = (purchased_grams - to_buy).clamp(min=0)  # [K, N, MAX_NNZ]

        # Value leftover grams at package price-per-gram (what they're worth)
        price_per_gram = selected_prices / selected_sizes.clamp(min=1.0)  # [K, N, MAX_NNZ]
        leftover_value = _Q(leftover_grams * price_per_gram)  # [K, N]

        # Discount factor: how much to credit (0.5 = credit 50% of leftover value)
        # Not 100% because: storage, expiry risk, might not use it all
        # NOTE: For high-protein mode, this is set to 0.0 to avoid incentivizing pantry growth
        leftover_credit_rate = self.config.leftover_credit_rate
        cost = gross_cost - leftover_value * leftover_credit_rate

        # Pantry usage = grams consumed from pantry for this recipe
        pantry_usage = _Q(overlap)  # [K, N]

        # Inventory delta = net change to pantry (positive = growth)
        # acquired (leftover from packages) - consumed (from pantry)
        inventory_delta = _Q(leftover_grams) - pantry_usage  # [K, N]

        if return_pantry_usage and return_inventory_delta:
            return cost, pantry_usage, inventory_delta
        elif return_pantry_usage:
            return cost, pantry_usage
        elif return_inventory_delta:
            return cost, inventory_delta

        return cost

    def _compute_at_risk_pantry_rescue_credit(
        self,
        pantries: torch.Tensor,              # [K, I]
        recipe_indices: torch.Tensor,        # [N]
        pantry_ttl: Optional[torch.Tensor],  # [K, I]
        pantry_frozen: Optional[torch.Tensor],  # [K, I]
    ) -> torch.Tensor:
        """
        Extra experiment credit for recipes that burn down pantry inventory close
        to expiry, net of new perishable package remainders they create.
        """
        K = pantries.shape[0]
        N = recipe_indices.shape[0]
        zeros = torch.zeros((K, N), device=self.device)
        if (
            not getattr(self.config, 'enable_at_risk_pantry_rescue', False)
            or pantry_ttl is None
            or N == 0
        ):
            return zeros

        ttl_window = float(getattr(self.config, 'at_risk_rescue_ttl_days', 0) or 0)
        if ttl_window <= 0:
            return zeros

        indices = recipe_indices.long()
        ing_idx = self._recipe_ing_idx_long[indices]  # [N, MAX_NNZ]
        full_amounts = self._recipe_full_amounts[indices]  # [N, MAX_NNZ]
        ing_idx_flat = ing_idx.flatten()

        pantry_gathered = pantries[:, ing_idx_flat].view(K, N, MAX_NNZ)
        overlap = torch.minimum(pantry_gathered, full_amounts.unsqueeze(0))
        ttl_gathered = pantry_ttl[:, ing_idx_flat].view(K, N, MAX_NNZ)
        at_risk = (pantry_gathered > 0) & (ttl_gathered >= 0) & (ttl_gathered <= ttl_window)
        if not at_risk.any():
            return zeros

        # TTL 0/1 should matter a lot; TTL near the window should still matter,
        # but less. Use inverse TTL so the signal is FEFO-shaped.
        urgency = torch.where(
            at_risk,
            1.0 / ttl_gathered.clamp(min=1.0),
            torch.zeros_like(ttl_gathered),
        )
        weighted_overlap = overlap * urgency

        if pantry_frozen is not None:
            frozen_gathered = pantry_frozen[:, ing_idx_flat].view(K, N, MAX_NNZ)
        else:
            frozen_gathered = torch.zeros_like(at_risk)

        fresh_overlap = weighted_overlap * (~frozen_gathered.bool()).float()
        frozen_overlap = weighted_overlap * frozen_gathered.float()
        fresh_value = float(getattr(self.config, 'at_risk_rescue_fresh_value_per_g', 0.0) or 0.0)
        frozen_value = float(getattr(self.config, 'at_risk_rescue_frozen_value_per_g', 0.0) or 0.0)
        rescue_credit = (
            fresh_overlap * fresh_value + frozen_overlap * frozen_value
        ).float().sum(dim=2)

        # Guardrail: do not call it rescue if the recipe creates a new pile of
        # short-shelf package remainder to save a smaller old remainder.
        new_penalty_per_g = float(
            getattr(self.config, 'at_risk_rescue_new_perishable_penalty_per_g', 0.0) or 0.0
        )
        if new_penalty_per_g > 0:
            to_buy = (full_amounts.unsqueeze(0) - overlap).clamp(min=0)
            pkg_sizes = self._recipe_pkg_sizes[indices].clamp(min=1.0).unsqueeze(0)
            num_packages = torch.ceil(to_buy / pkg_sizes) * (to_buy > 0).float()
            package_remainder = (num_packages * pkg_sizes - to_buy).clamp(min=0)
            purchase_ttl = self._purchase_ttl_for_recipe_positions(indices, ing_idx).unsqueeze(0)
            risk_ttl = float(
                getattr(self.config, 'at_risk_rescue_new_perishable_ttl_days', 14) or 14
            )
            new_risk_mask = purchase_ttl <= risk_ttl
            new_perishable_remainder = package_remainder * new_risk_mask.float()
            new_risk_penalty = new_perishable_remainder.float().sum(dim=2) * new_penalty_per_g
            rescue_credit = (rescue_credit - new_risk_penalty).clamp(min=0)

        max_credit = float(getattr(self.config, 'at_risk_rescue_max_bonus_per_recipe', 0.0) or 0.0)
        if max_credit > 0:
            rescue_credit = rescue_credit.clamp(max=max_credit)
        return torch.round(rescue_credit * 100.0).float() / 100.0

    def _cost_filter_candidates(
        self,
        pantries: torch.Tensor,         # [K, I]
        recipe_indices: torch.Tensor,   # [N] indices into recipe database
        used_ids: torch.Tensor,         # [K, COOLDOWN_LEN]
        slot: int,                      # Current slot (for per-slot servings)
        top_m: int = 100,
        batch_size: int = 100,          # Process frontiers in batches to save memory
        protein_counts: Optional[torch.Tensor] = None,  # [K, 6] protein source counts for quota
        leftovers: Optional[torch.Tensor] = None,  # [K, L, LEFTOVER_FIELDS] for template match bonus
        pantry_ttl: Optional[torch.Tensor] = None,  # [K, I] TTL for urgency bonus
        pantry_frozen: Optional[torch.Tensor] = None,  # [K, I] frozen-state bonus for pantry burn-down
        current_nutrition: Optional[torch.Tensor] = None,  # [K, 4] for calorie band filtering
        slot_idx: int = 0,  # Current slot index (for quota expected counts)
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Pass 1: Filter candidates by cost with pantry utilization bonus.
        Returns indices of top M cheapest recipes per frontier.

        NEW: If current_nutrition provided, filters to calorie band first.

        Key incentives:
        - Pantry items cost $0 (natural cheapness)
        - PANTRY UTILIZATION BONUS: Recipes that consume more pantry grams get a discount
          This makes complex recipes competitive if we already have their ingredients!
        - Leftover bonus: Multi-serving recipes get discounted

        Uses batching over frontiers to handle large K without OOM.
        """
        K = pantries.shape[0]
        N = recipe_indices.shape[0]

        if N == 0:
            return torch.zeros(K, 0, dtype=torch.long, device=self.device), \
                   torch.full((K, 0), float('inf'), device=self.device)

        # Get per-slot servings (variable attendance)
        slot_servings = self.servings_per_slot[slot].item()

        # === PRE-FILTER TO TOP 20K BY COST/CALORIE RATIO (8× speedup) ===
        # Skip full [K, N, MAX_NNZ] scoring on all 174k recipes
        # FIXED: Pure cost filter biased towards low-cal recipes (379 vs 510 cal/srv)
        PRE_FILTER_SIZE = 20000

        # Determine meal type from slot for dynamic servings
        meal_type = self._get_meal_type_from_slot(slot)

        if N > PRE_FILTER_SIZE:
            indices = recipe_indices.long()

            # === DYNAMIC SERVINGS: Compute servings based on target cal/srv ===
            if self.config.enable_dynamic_servings:
                # Use dynamic servings: total_cal / target_cal_per_srv
                recipe_servings_tmp, target_cal_per_srv = self._compute_dynamic_servings(
                    recipe_indices, slot, meal_type, 'main'
                )
                # With dynamic servings, cal/srv is normalized to target
                # So recipe_cals is effectively target_cal_per_srv for divisible recipes
                recipe_cals = self.db.total_calories[indices] / recipe_servings_tmp.clamp(min=1)
            else:
                # Original behavior: use author-defined servings
                recipe_cals = self.db.nutrition[indices, 0].float()  # [N] cal per serving
                recipe_servings_tmp = self.db.servings[indices].float()  # [N]

            # First: hard filter on servings and calories
            valid_servings = recipe_servings_tmp >= slot_servings  # Must have enough servings
            valid_cal = recipe_cals >= 100  # Must be real food (>100 cal/srv)

            if self.config.enable_dynamic_servings and self.config.enable_band_filter:
                band_high = self._dynamic_effective_cal_ceiling(
                    target_cal_per_srv,
                    slot_servings,
                )
                in_dynamic_band = recipe_cals <= band_high
                if in_dynamic_band.sum() >= top_m * 2:
                    valid_cal = valid_cal & in_dynamic_band

            # === CALORIE BAND FILTER ===
            # With DYNAMIC SERVINGS: Skip calorie band filter (cal/srv is already normalized)
            # Without: Filter to recipes that fit our calorie needs
            # Can be disabled via enable_band_filter=False for A/B testing
            if current_nutrition is not None and self.config.enable_band_filter and not self.config.enable_dynamic_servings:
                meals_remaining = max(21 - slot, 1)  # 21 slots per week
                cal_debt = (self.weekly_calories - current_nutrition[:, 0].float().mean()).clamp(min=0)
                target_cal_per_meal = cal_debt / meals_remaining
                target_cal_per_srv = target_cal_per_meal / max(slot_servings, 1)

                # Tighter band for small servings (small households need precise portions)
                # Wide band for large servings (batch cooking has more flexibility)
                if slot_servings <= 2:
                    # Tight: ±30% for small households
                    band_low = max(100, target_cal_per_srv * 0.70)
                    band_high = min(600, target_cal_per_srv * 1.30)
                else:
                    # Looser: ±50% for large households
                    band_low = max(150, target_cal_per_srv * 0.50)
                    band_high = max(800, target_cal_per_srv * 1.50)

                in_band = (recipe_cals >= band_low) & (recipe_cals <= band_high)
                # Only apply band if it leaves enough recipes
                if in_band.sum() >= top_m * 2:
                    valid_cal = valid_cal & in_band

            # === PROTEIN BAND FILTER ===
            # Filter recipes by protein density (protein_g * 4 / cal * 100).
            # Protein density is a recipe property, serving-size independent —
            # works with or without dynamic servings.
            # NOTE: Removed 'target > 15' check to enable targeting at any level
            if self.config.enable_protein_prefilter:
                recipe_prot_g = self.db.nutrition[indices, 1].float()  # [N] protein g/srv
                recipe_cal_srv = self.db.nutrition[indices, 0].float()  # [N] cal/srv
                recipe_prot_pct = (recipe_prot_g * 4) / recipe_cal_srv.clamp(min=1) * 100  # [N]

                margin = self.config.protein_filter_margin
                widen_step = getattr(self.config, 'protein_band_widen_step', 5.0)
                max_widen = getattr(self.config, 'protein_band_max_widen', 15.0)
                target = self.protein_pct_target

                # Apply protein floor filter (exclude below target - margin, allow above)
                prot_in_band = (recipe_prot_pct >= target - margin)
                # Combine with existing validity mask
                valid_cal = valid_cal & prot_in_band

            valid_mask = valid_servings & valid_cal

            valid_count = valid_mask.sum().item()
            # NOTE: Changed from > PRE_FILTER_SIZE to > 100
            # The old check skipped the filter when valid_count was small (e.g., 5K after tight protein filter)
            # We want to apply the filter as long as we have enough recipes for diversity
            if valid_count > 100:
                valid_idx = torch.nonzero(valid_mask, as_tuple=True)[0]
                recipe_indices = recipe_indices[valid_idx]
                indices = recipe_indices.long()
                N = len(recipe_indices)

                # Recompute servings for filtered set
                if self.config.enable_dynamic_servings:
                    recipe_servings_tmp, _ = self._compute_dynamic_servings(
                        recipe_indices, slot, meal_type, 'main'
                    )
                    recipe_cals = self.db.total_calories[indices] / recipe_servings_tmp.clamp(min=1)
                else:
                    recipe_cals = self.db.nutrition[indices, 0].float()
                    recipe_servings_tmp = self.db.servings[indices].float()
            # === PANTRY-AWARE INCREMENTAL COST (FIX: was using RAW cost, excluding beef/pork) ===
            # Use aggregate pantry across all frontiers for pre-filter efficiency
            # This lets recipes with pantry overlap compete fairly with "cheap" recipes
            aggregate_pantry = pantries.max(dim=0).values  # [I] - union across frontiers

            ing_idx = self._recipe_ing_idx_long[indices]  # [N, MAX_NNZ]
            full_amounts = self._recipe_full_amounts[indices]  # [N, MAX_NNZ]
            ing_idx_flat = ing_idx.flatten()

            # Get pantry at each ingredient position
            pantry_at_ing = aggregate_pantry[ing_idx_flat].view(N, MAX_NNZ)  # [N, MAX_NNZ]

            # Compute overlap with pantry - ingredients we DON'T need to buy
            overlap = torch.minimum(pantry_at_ing, full_amounts)  # [N, MAX_NNZ]
            to_buy = (full_amounts - overlap).clamp(min=0)  # [N, MAX_NNZ] - what we actually need

            pkg_prices = self._recipe_pkg_option_prices[indices]
            pkg_sizes = self._recipe_pkg_option_sizes[indices]

            # Package cost for what we need to BUY (not full recipe)
            _, _, _, _, ingredient_costs = self._choose_package_options(
                to_buy,
                pkg_sizes,
                pkg_prices,
                getattr(self.config, "package_remainder_choice_penalty_per_kg", 0.0),
            )
            # float64 sum + round to eliminate CPU/CUDA divergence
            incremental_costs = torch.round(ingredient_costs.float().sum(dim=1) * 100.0).float() / 100.0  # [N] - PANTRY-AWARE!

            # Pantry utilization bonus - reward recipes that use more pantry
            pantry_usage_grams = torch.round(overlap.float().sum(dim=1) * 100.0).float() / 100.0  # [N] grams consumed from pantry
            pantry_bonus = pantry_usage_grams * self.config.pantry_usage_value  # [N]

            # Effective cost = what we pay - pantry bonus
            effective_cost = (incremental_costs - pantry_bonus).clamp(min=0.01)  # [N]
            if getattr(self.config, 'enable_at_risk_pantry_rescue', False) and pantry_ttl is not None:
                large_ttl = torch.full_like(pantry_ttl, 1_000_000.0)
                present_ttl = torch.where(
                    (pantries > 0) & (pantry_ttl >= 0),
                    pantry_ttl,
                    large_ttl,
                )
                aggregate_ttl = present_ttl.min(dim=0).values
                aggregate_ttl = torch.where(
                    aggregate_ttl >= 999_999.0,
                    torch.full_like(aggregate_ttl, -1.0),
                    aggregate_ttl,
                )
                aggregate_frozen = None
                if pantry_frozen is not None:
                    aggregate_frozen = ((pantries > 0) & pantry_frozen.bool()).any(dim=0).unsqueeze(0)
                rescue_credit = self._compute_at_risk_pantry_rescue_credit(
                    aggregate_pantry.unsqueeze(0),
                    recipe_indices,
                    aggregate_ttl.unsqueeze(0),
                    aggregate_frozen,
                )[0]
                effective_cost = (effective_cost - rescue_credit).clamp(min=0.01)

            # Normalize by calories: $/1000cal instead of just $
            cal_per_batch = recipe_cals * recipe_servings_tmp
            cost_per_1000cal = effective_cost / (cal_per_batch / 1000).clamp(min=1.0)

            # === PROTEIN DIVERSITY BOOST (for balanced mode) ===
            # Give beef/pork/fish cost discounts to help them compete with eggs/legumes
            # Each protein type can have different boost based on how expensive it is
            if self.config.enable_protein_diversity_boost:
                recipe_protein_src = self.db.protein_source[indices]  # [N] int8
                # PROTEIN_SOURCE_CODES: beef=0, pork=1, poultry=2, fish=3, eggs=4, legumes=5
                diversity_boost = torch.zeros(N, device=self.device)
                diversity_boost[recipe_protein_src == 0] = self.config.beef_boost  # beef needs most help
                diversity_boost[recipe_protein_src == 1] = self.config.protein_diversity_boost  # pork
                diversity_boost[recipe_protein_src == 3] = self.config.fish_boost  # fish needs help too

                cost_per_1000cal = cost_per_1000cal - diversity_boost  # Lower = better

            # === PROTEIN TARGETING IN COST FILTER (492k → 20k gate) ===
            # Normal food-plan tiers use a soft discount so high-protein
            # candidates survive the cost filter. Only explicit hard-prefilter
            # configs push low-protein recipes to the bottom.
            if self.config.enable_protein_prefilter or self.config.enable_protein_density_bonus:
                recipe_nutr_pf = self.db.nutrition[indices].float()  # [N, 4]
                prot_cal_pf = recipe_nutr_pf[:, 1] * 4  # protein grams → calories
                total_cal_pf = recipe_nutr_pf[:, 0].clamp(min=1.0)  # cal/serving
                recipe_prot_pct_pf = (prot_cal_pf / total_cal_pf) * 100  # [N]

                if self.config.enable_protein_prefilter:
                    # FLOOR ONLY: exclude recipes below target - margin (never cap high protein)
                    min_prot_pct = self.protein_pct_target - self.config.protein_filter_margin
                    low_protein_mask = recipe_prot_pct_pf < min_prot_pct
                    cost_per_1000cal[low_protein_mask] += 1e6  # Effectively excluded

                # Graduated bonus: pull surviving recipes toward target
                # Recipes at target get max discount, further away get less
                prot_dist_pf = (recipe_prot_pct_pf - self.protein_pct_target).abs()
                prot_prox_pf = (1.0 - prot_dist_pf / 30.0).clamp(min=0)  # 0-1
                # Scale discount by target aggressiveness (use absolute distance from baseline)
                _baseline = 25.0  # Database natural baseline ~25-35%
                _pf_scale = max(1.0, abs(self.protein_pct_target - _baseline) / 10.0)
                prot_discount_pf = prot_prox_pf * 0.5 * _pf_scale  # $/1000cal discount
                cost_per_1000cal -= prot_discount_pf

            # === PROTEIN QUOTA PRE-FILTER ===
            # Shape the 20K candidate pool to reflect target distribution.
            # High-target sources get cost DISCOUNT (more in pool).
            # Low-target sources get NO penalty — the progressive quota
            # handles overuse enforcement during beam search.
            # Penalizing low-target sources here would exclude them from the
            # pool entirely, preventing the quota from ever selecting them.
            if self._protein_targets is not None:
                recipe_protein_src_pf = self.db.protein_source[indices]  # [N] int8
                median_target = self._protein_targets.median().item()
                # Only apply discounts (negative adjustments), clamp penalties to 0
                source_adj = torch.clamp(median_target - self._protein_targets, max=0.0) * 8.0  # [6]
                has_source = (recipe_protein_src_pf >= 0) & (recipe_protein_src_pf <= 5)
                adj = torch.zeros(N, device=self.device)
                adj[has_source] = source_adj[recipe_protein_src_pf[has_source].long()]
                cost_per_1000cal += adj

            # Take top 20k by cost efficiency (low $/1000cal)
            _, top_idx = self._stable_topk(-cost_per_1000cal, k=min(PRE_FILTER_SIZE, N), largest=True, dim=0)
            recipe_indices = recipe_indices[top_idx]
            N = len(recipe_indices)
            del ing_idx, full_amounts, pkg_prices, pkg_sizes, top_idx, cost_per_1000cal
            del pantry_at_ing, overlap, to_buy, incremental_costs, pantry_bonus, effective_cost

        # Pre-compute recipe metadata (shared across all frontiers)
        recipe_ids = self.db.recipe_ids[recipe_indices.long()]  # [N]
        recipe_nutr = self.db.nutrition[recipe_indices.long()].float()  # [N, 2]
        recipe_nnz = self.db.nnz[recipe_indices.long()]  # [N]
        recipe_protein_source = self.db.protein_source[recipe_indices.long()]  # [N] int8, -1=none

        # Quality penalty masks (shared)
        low_cal = recipe_nutr[:, 0] < 100  # [N]
        low_ing = recipe_nnz < 2  # [N]

        # CRITICAL: Recipe must produce enough servings for this slot's attendance!
        # With DYNAMIC SERVINGS: Use computed servings based on target cal/srv
        # NOTE: Must compute BEFORE high_cal check which uses recipe_servings
        if self.config.enable_dynamic_servings:
            recipe_servings, _ = self._compute_dynamic_servings(
                recipe_indices, slot, meal_type, 'main'
            )
        else:
            recipe_servings = self.db.servings[recipe_indices.long()].float()  # [N]
        low_servings = recipe_servings < slot_servings  # [N]

        # HIGH CALORIE CAP: Dynamic based on daily target
        # One serving should not exceed 40% of daily calories
        # For 2000 cal/day → max 1000 cal/srv
        # This prevents 2500+ cal/srv recipes from dominating small households
        # With DYNAMIC SERVINGS: Cal/srv is normalized to target, so this is less relevant
        daily_cal = self._per_person_daily_calories()
        effective_max_cal_per_srv = daily_cal * 0.40
        if self.config.enable_dynamic_servings:
            # Dynamic servings: compute effective cal/srv from total/servings
            recipe_servings, target_cal_per_srv = self._compute_dynamic_servings(
                recipe_indices, slot, meal_type, 'main'
            )
            effective_cal_per_srv = self.db.total_calories[recipe_indices.long()] / recipe_servings.clamp(min=1)
            dynamic_max = self._dynamic_effective_cal_ceiling(
                target_cal_per_srv,
                slot_servings,
            )
            effective_max_cal_per_srv = min(effective_max_cal_per_srv, dynamic_max)
            high_cal = effective_cal_per_srv > effective_max_cal_per_srv  # [N]
        else:
            high_cal = recipe_nutr[:, 0] > effective_max_cal_per_srv  # [N]

        # === LEFTOVER BONUS ===
        # Recipes with more servings = more leftovers = potentially cheaper per meal
        # Example: 12-serving lasagna eaten 3x is cheaper than 3 separate 4-serving meals
        raw_leftover_servings = (recipe_servings - slot_servings).clamp(min=0)  # [N] - raw, uncapped
        # Cap at N meals worth of leftovers (scales with family size via slot_servings)
        # Use MAX(8, relative) to preserve benefit for small households
        # hs1: max(8, 1*2) = 8, hs6: max(8, 6*2) = 12, hs8: max(8, 8*2) = 16
        max_leftover_servings = max(8.0, slot_servings * self.config.leftover_meals_cap)
        leftover_servings = raw_leftover_servings.clamp(max=max_leftover_servings)  # capped for bonus
        # Value each leftover serving based on config (was hardcoded $1.50)
        leftover_bonus = leftover_servings * self.config.leftover_value * self.leftover_target  # [N]

        # === NEW: SERVING-MATCH PENALTY ===
        # Penalize recipes that deviate from ideal serving size based on leftover_pct_target
        # Low leftover_pct (fresh daily): penalize recipes that are TOO BIG
        # High leftover_pct (batch cook): penalize recipes that are TOO SMALL
        serving_match_penalty = torch.zeros(N, device=self.device)
        if self.config.enable_serving_filter:
            ideal_srv = self.ideal_servings_per_slot[slot].item()
            min_acceptable = ideal_srv / self.config.serving_tolerance_mult
            max_acceptable = ideal_srv * self.config.serving_tolerance_mult

            if self.leftover_pct_target < 0.3:
                # FRESH DAILY MODE: Strongly penalize excess servings (too big)
                # Penalty = excess_servings × weight × fresh_mode_excess_mult
                excess = (recipe_servings - max_acceptable).clamp(min=0)
                serving_match_penalty = excess * self.config.serving_match_weight * self.config.fresh_mode_excess_mult
            elif self.leftover_pct_target >= 0.5:
                # BATCH COOK MODE: Give BONUS for larger batches (not just penalize small)
                # Recipes larger than slot_servings get a discount up to ideal_srv
                max_bonus_servings = ideal_srv - slot_servings  # e.g., 8 - 4 = 4 extra servings max
                extra_servings = (recipe_servings - slot_servings).clamp(min=0, max=max_bonus_servings)
                # Bonus = negative penalty, scales with leftover_pct_target
                bonus_strength = self.leftover_pct_target * self.config.batch_bonus_strength_mult
                serving_match_penalty = -extra_servings * self.config.serving_match_weight * bonus_strength
            # else: 30-50% target - moderate zone, use existing leftover_bonus only

            # === HARD SERVING CAP ===
            # Exclude recipes that are WAY over the acceptable range (2x max_acceptable)
            # This prevents 100-serving sourdough starter type recipes from being selected
            # For hs4 with 75% leftover target: ideal=16, max_acceptable=24, hard_cap=48
            # Soft penalty handles moderate excess; hard cap handles absurd excess
            hard_serving_cap = max_acceptable * self.config.hard_serving_cap_mult  # Default: 2.0
            way_over_mask = recipe_servings > hard_serving_cap
            serving_match_penalty = torch.where(
                way_over_mask,
                torch.full_like(serving_match_penalty, 1e4),  # Effectively exclude
                serving_match_penalty
            )

            # === MAX FEED-DAYS CONSTRAINT (DAILY BALANCE) ===
            # Prevents same recipe from feeding household for entire week
            # At 70% leftover target with max_feed_days=4:
            #   max_servings = 4 people * 4 days = 16 servings
            #   Any recipe > 16 servings gets penalized (not excluded, just discouraged)
            #
            # This is SEPARATE from hard_serving_cap which catches absurd recipes
            # This catches recipes that are "valid" but too big for daily balance
            max_servings_for_balance = slot_servings * self.max_feed_days
            excess_for_balance = (recipe_servings - max_servings_for_balance).clamp(min=0)
            # Penalty: $2 per excess serving beyond max_feed_days worth
            # Soft penalty - doesn't exclude, but makes large batches less attractive
            balance_excess_penalty = excess_for_balance * 2.0  # $2 per serving over limit
            serving_match_penalty = serving_match_penalty + balance_excess_penalty

            # TRACE: max_feed_days penalty
            if self.verbose and slot == 0:
                num_penalized = (excess_for_balance > 0).sum().item()
                max_excess = excess_for_balance.max().item()
                max_pen = balance_excess_penalty.max().item()
                print(f"\n    [MAX_FEED_DAYS TRACE slot={slot}]")
                print(f"      slot_servings: {slot_servings}, max_feed_days: {self.max_feed_days}")
                print(f"      max_servings_for_balance: {max_servings_for_balance}")
                print(f"      recipes penalized: {num_penalized}/{N}")
                print(f"      max_excess: {max_excess:.0f} servings, max_penalty: ${max_pen:.2f}")

        # === EXCESS SERVING PENALTY (Dynamic, Inventory-Aware) ===
        # Only penalize new leftovers when existing inventory is already high
        # This prevents leftover pile-up while allowing batch cooking when inventory is low
        #
        # Logic: If we already have >N meals worth of leftovers, discourage creating more
        # Threshold = slot_servings × leftover_excess_threshold_mult
        #
        # The penalty scales with how much we're OVER the threshold
        leftover_threshold = slot_servings * self.config.leftover_excess_threshold_mult

        # Count current leftover servings (will be computed per-frontier if leftovers available)
        # Default to 0 if no leftover state (penalty only activates when we have context)
        excess_serving_penalty = torch.zeros(N, device=self.device)  # [N] - will be adjusted per-K if needed

        # === PANTRY UTILIZATION BONUS ===
        # Reward recipes that consume MORE grams from pantry - makes complex recipes competitive!
        # Value based on config (~$2-10 per kg used depending on mode)
        PANTRY_USAGE_VALUE = self.config.pantry_usage_value  # Was hardcoded 0.002

        # === PER-SERVING COST NORMALIZATION ===
        # Compare costs fairly by dividing by servings produced
        # This prevents cheap small recipes from beating nutritious larger ones
        # Example: $7 chicken for 4 servings = $1.75/srv beats $3 eggs for 1 serving = $3/srv
        USE_PER_SERVING_COST = True

        actual_m = min(top_m, N)

        # If K is small enough, process all at once
        if K <= batch_size:
            costs, pantry_usage, inventory_delta = self._compute_incremental_cost(
                pantries, recipe_indices, slot_servings=slot_servings,
                return_pantry_usage=True, return_inventory_delta=True
            )  # [K, N], [K, N], [K, N]

            # Apply pantry utilization bonus (the more pantry you use, the cheaper!)
            pantry_bonus = pantry_usage * PANTRY_USAGE_VALUE  # [K, N]
            costs -= pantry_bonus

            # === PROTEIN DIVERSITY BOOST (scoring step - reduced to 50% to avoid double-counting) ===
            # Pre-filter gets beef/pork into top 20K, then scoring applies partial boost
            if self.config.enable_protein_diversity_boost:
                if self.config.enable_dynamic_servings:
                    cal_per_batch = self.db.total_calories[recipe_indices.long()]  # [N] use actual total cal
                else:
                    cal_per_batch = recipe_nutr[:, 0] * slot_servings  # [N] total calories
                diversity_boost = torch.zeros(N, device=self.device)
                # Apply 50% of configured boost to avoid over-boosting from pre-filter + scoring
                diversity_boost[recipe_protein_source == 0] = self.config.beef_boost * 0.5  # beef
                diversity_boost[recipe_protein_source == 1] = self.config.protein_diversity_boost * 0.5  # pork
                diversity_boost[recipe_protein_source == 3] = self.config.fish_boost * 0.5  # fish
                boost_amount = diversity_boost * (cal_per_batch / 1000.0)
                costs -= boost_amount.unsqueeze(0)

            # === PANTRY URGENCY BONUS ===
            # Prefer recipes using ingredients about to expire (FEFO: First Expired First Out)
            # PERF: Only compute if there are items expiring soon
            ttl_window = self.config.ttl_urgency_window  # configurable (default 7 days)
            if pantry_ttl is not None:
                # Quick check: any items expiring within the urgency window?
                has_expiring = ((pantry_ttl < ttl_window) & (pantries > 0)).any()
                if has_expiring:
                    # Get ingredient indices and amounts for these recipes
                    indices = recipe_indices.long()
                    ing_idx = self.db.ingredient_indices[indices]  # [N, MAX_NNZ]
                    ing_amt = self.db.ingredient_amounts[indices].float()  # [N, MAX_NNZ]
                    recipe_servings_exp = self.db.servings[indices].float().view(N, 1)
                    full_amounts = ing_amt * recipe_servings_exp  # [N, MAX_NNZ]

                    # Get TTL at ingredient positions: [K, N, MAX_NNZ]
                    ing_idx_flat = ing_idx.long().flatten()  # [N * MAX_NNZ]
                    ttl_gathered = pantry_ttl[:, ing_idx_flat].view(K, N, MAX_NNZ)  # [K, N, MAX_NNZ]

                    # Only give bonus for truly expiring items (TTL < window)
                    # Items with TTL >= window get urgency=0 (no bonus)
                    urgency = torch.where(
                        ttl_gathered < ttl_window,
                        1.0 / ttl_gathered.clamp(min=1.0),  # TTL=1->1.0, TTL=3->0.33
                        torch.zeros_like(ttl_gathered)  # No urgency for non-expiring
                    )

                    # Weight by overlap (how much we use from pantry)
                    pantry_gathered = pantries[:, ing_idx_flat].view(K, N, MAX_NNZ)  # [K, N, MAX_NNZ]
                    overlap = torch.minimum(pantry_gathered, full_amounts.unsqueeze(0))  # [K, N, MAX_NNZ]

                    # Urgency bonus based on config (was hardcoded $0.01/gram)
                    # float64 sum + round to eliminate CPU/CUDA divergence
                    urgency_bonus = torch.round((overlap * urgency * self.config.perishable_urgency_value).float().sum(dim=2) * 100.0).float() / 100.0  # [K, N]
                    costs -= urgency_bonus

                    if pantry_frozen is not None and self.config.frozen_pantry_usage_value > 0:
                        frozen_gathered = pantry_frozen[:, ing_idx_flat].view(K, N, MAX_NNZ)
                        frozen_overlap = overlap * frozen_gathered.float()
                        frozen_bonus = torch.round((frozen_overlap * self.config.frozen_pantry_usage_value).float().sum(dim=2) * 100.0).float() / 100.0  # [K, N]
                        costs -= frozen_bonus

            if (
                getattr(self.config, 'enable_at_risk_pantry_rescue', False)
                and not getattr(self.config, 'enable_perishable_urgency', True)
            ):
                # Main scoring already has FEFO urgency. Only apply the rescue
                # credit here if that older urgency scorer is disabled.
                rescue_credit = self._compute_at_risk_pantry_rescue_credit(
                    pantries,
                    recipe_indices,
                    pantry_ttl,
                    pantry_frozen,
                )
                costs -= rescue_credit

            # Apply leftover bonus BEFORE per-serving normalization (bonus is in total $)
            costs -= leftover_bonus.unsqueeze(0)  # [K, N] - [1, N]

            # Apply serving-match penalty (penalizes wrong-sized batches based on leftover_pct_target)
            costs += serving_match_penalty.unsqueeze(0)  # [K, N] - [1, N]

            # === DYNAMIC EXCESS SERVING PENALTY ===
            # Only apply when current leftover inventory exceeds threshold
            if leftovers is not None:
                # Count current leftover servings: sum of servings (col 1) where recipe_id (col 0) > 0
                current_lo_servings = torch.round(leftovers[:, :, 1].clamp(min=0).float().sum(dim=1) * 100.0).float() / 100.0  # [K]

                # How much OVER threshold are we? (0 if under threshold)
                over_threshold = (current_lo_servings - leftover_threshold).clamp(min=0)  # [K]

                # Scale penalty by how much we're over threshold
                # If at threshold: penalty = 0
                # If 3 servings over: penalty = 3 × $0.25 × leftover_servings = slight discourage
                inventory_penalty_mult = over_threshold / leftover_threshold  # [K] normalized 0-N
                inventory_penalty_mult = inventory_penalty_mult.clamp(max=2.0)  # Cap at 2x base penalty

                # Apply per-frontier penalty: penalty = mult × base_rate × excess_servings
                # Use raw_leftover_servings (not capped) so penalty scales with actual excess
                # [K, 1] × [1, N] → [K, N]
                dynamic_penalty = inventory_penalty_mult.unsqueeze(1) * self.config.excess_serving_penalty * raw_leftover_servings.unsqueeze(0)
                costs += dynamic_penalty  # [K, N]

            # === TEMPLATE MATCH BONUS ===
            # Reward mains whose templates match existing side leftovers
            # This encourages consuming leftover sides instead of letting them expire
            if leftovers is not None:
                # Extract side leftover templates: dish_type=2 (side) with servings > 0
                side_leftover_mask = (leftovers[:, :, 7] == 2) & (leftovers[:, :, 1] > 0)  # [K, L]
                side_templates = leftovers[:, :, 8].long()  # [K, L] template IDs

                # Get each recipe's template ID
                recipe_templates = self.db.gpu_recipe_to_template[recipe_indices.long()]  # [N]

                # Check if ANY frontier's side leftover template matches recipe template
                template_matches = (side_templates.unsqueeze(2) == recipe_templates.view(1, 1, -1))  # [K, L, N]

                # Mask out non-side leftovers (only count valid sides)
                template_matches = template_matches & side_leftover_mask.unsqueeze(2)  # [K, L, N]

                # Any template match across leftover slots -> [K, N]
                has_matching_leftover = template_matches.any(dim=1).float()  # [K, N]

                # Apply bonus from config (was hardcoded $3)
                costs -= has_matching_leftover * self.config.template_match_bonus

            # === FROZEN PRESSURE PENALTY ===
            # When frozen inventory is high, discourage cooking new (eat leftovers first!)
            # This prevents frozen items from accumulating until they expire
            frozen_count = (leftovers[:, :, 6] > 0).sum(dim=1).float()  # [K]
            frozen_over = (frozen_count - self.config.frozen_count_threshold).clamp(min=0)
            if frozen_over.any():
                # Per-frontier penalty. The old scalar mean made every beam pay
                # the same amount, so it did not actually prefer low-freezer
                # frontiers.
                frozen_pressure_penalty = self.config.frozen_pressure_base * (frozen_over / 8.0)
                costs += frozen_pressure_penalty.unsqueeze(1)

            # === HOLDING COST CONTROLLER ===
            # Penalize recipes that GROW pantry, proportional to how far above target we are
            # This is the key knob for pantry stability in high-protein mode
            if self.config.enable_holding_cost:
                # Current pantry size per frontier in kg
                current_pantry_kg = torch.round(pantries.float().sum(dim=1) * 100.0).float() / 100.0 / 1000.0  # [K]
                target_kg = max(self.config.target_pantry_kg, 1.0)  # Guard against div/0
                rate = self.config.holding_cost_rate

                # Excess ratio: how far above target we are (0 = at target, 1 = 2x target)
                excess_ratio = ((current_pantry_kg - target_kg) / target_kg).clamp(min=0)  # [K]

                # Holding rate scales with excess ($/kg of inventory growth)
                holding_rate = excess_ratio * rate  # [K]

                # Only penalize GROWTH (positive inventory_delta), not depletion
                positive_delta_kg = inventory_delta.clamp(min=0) / 1000.0  # [K, N] in kg

                # Add holding cost: delta_kg * rate_per_kg
                holding_cost = positive_delta_kg * holding_rate.unsqueeze(1)  # [K, N]
                costs += holding_cost

            # === PROTEIN PROXIMITY DISCOUNT (Cost Filter) ===
            # When protein targeting is active, give high-protein recipes a cost discount
            # so they survive the cost filter and reach the second pass scoring.
            # This is the KEY mechanism: without it, cost optimization eliminates
            # high-protein recipes before the density bonus can help them.
            # NOTE: Removed 'target > 15' check to enable targeting at any level
            if self.config.enable_protein_prefilter or self.config.enable_protein_density_bonus:
                recipe_prot_g_cf = self.db.nutrition[recipe_indices.long(), 1].float()  # [N]
                recipe_cal_cf = self.db.nutrition[recipe_indices.long(), 0].float()  # [N]
                recipe_prot_pct_cf = (recipe_prot_g_cf * 4) / recipe_cal_cf.clamp(min=1) * 100  # [N]
                prot_dist_cf = (recipe_prot_pct_cf - self.protein_pct_target).abs()  # [N]
                prot_prox_cf = (1.0 - prot_dist_cf / 25.0).clamp(min=0)  # [N] 0-1
                # Discount per recipe (not per serving) — applied to total cost
                prot_discount = prot_prox_cf * self.config.protein_density_value * slot_servings  # [N]
                costs -= prot_discount.unsqueeze(0)  # [K, N] broadcast

            # === PER-SERVING NORMALIZATION ===
            # Normalize costs by what we COOK (slot_servings), not what recipe makes!
            # With servings fix, we buy ingredients for slot_servings, so divide by that.
            # OLD BUG: Dividing $7 (for 4 servings) by 12 made large recipes look 3x cheaper
            if USE_PER_SERVING_COST:
                # Use slot_servings for fair comparison (what we actually cook)
                costs = costs / slot_servings  # Now in $/serving

            # Variety filter (OPTIMIZED: pooled scatter/gather)
            # Uses pre-allocated mask pool to avoid 1.7GB allocations/week
            if K <= self._cooldown_mask_pool.shape[0]:
                mask = self._cooldown_mask_pool[:K, :self._cooldown_mask_size]
                mask.zero_()
            else:
                mask = torch.zeros(K, self._cooldown_mask_size, dtype=torch.bool, device=self.device)
            mask.scatter_(1, used_ids, True)
            in_cooldown = mask[:, recipe_ids]  # [K, N]
            costs[in_cooldown] = float('inf')

            # Quality filters (penalties are in $/serving now, so they're very high)
            costs[:, low_cal] += 100.0  # $100/srv penalty for non-food
            costs[:, low_ing] += 20.0   # $20/srv penalty for trivial recipes
            costs[:, low_servings] += 200.0  # $200/srv penalty - must produce enough servings!
            costs[:, high_cal] += 1000.0  # $1000/srv penalty for calorie bombs (>40% of daily cal)

            # === PROGRESSIVE PROTEIN QUOTA (replaces cooldown) ===
            # Uses tagged meal count (not total slots) as denominator, since many
            # recipes have no protein source tag (-1) and shouldn't inflate expected counts
            if self._protein_targets is not None and protein_counts is not None:
                tagged_total = protein_counts.sum(dim=1, keepdim=True).clamp(min=1)  # [K, 1]
                expected = self._protein_targets.unsqueeze(0) * tagged_total  # [K, 6]
                deviation = protein_counts.float() - expected  # [K, 6]
                overuse_penalty = self._protein_strictness * torch.clamp(deviation, min=0) ** 2  # [K, 6]
                underuse_bonus = self._protein_strictness * 0.5 * torch.clamp(-deviation, min=0)  # [K, 6]
                net_adjustment = overuse_penalty - underuse_bonus  # [K, 6]
                # Apply per-recipe: gather adjustment for each recipe's protein source
                valid_src = (recipe_protein_source >= 0) & (recipe_protein_source <= 5)
                if valid_src.any():
                    # net_adjustment: [K, 6], recipe sources: [N]
                    src_adj = net_adjustment[:, recipe_protein_source[valid_src].long()]  # [K, num_valid]
                    costs[:, valid_src] += src_adj

            # Quantize final costs to eliminate CPU/CUDA float32 noise before ranking
            top_m_costs, top_m_pos = self._stable_topk(costs, k=actual_m, largest=False, dim=1)
            top_m_db_idx = recipe_indices[top_m_pos]
            return top_m_db_idx, top_m_costs

        # === BATCHED PROCESSING for large K ===
        all_top_m_idx = []
        all_top_m_costs = []

        for k_start in range(0, K, batch_size):
            k_end = min(k_start + batch_size, K)
            batch_pantries = pantries[k_start:k_end]
            batch_used_ids = used_ids[k_start:k_end]
            batch_K = k_end - k_start

            # Compute costs, pantry usage, and inventory delta for this batch
            costs, pantry_usage, inventory_delta = self._compute_incremental_cost(
                batch_pantries, recipe_indices, slot_servings=slot_servings,
                return_pantry_usage=True, return_inventory_delta=True
            )  # [batch_K, N], [batch_K, N], [batch_K, N]

            # Apply pantry utilization bonus
            pantry_bonus = pantry_usage * PANTRY_USAGE_VALUE
            costs -= pantry_bonus

            # === PROTEIN DIVERSITY BOOST (batched - 50% to avoid double-counting) ===
            if self.config.enable_protein_diversity_boost:
                if self.config.enable_dynamic_servings:
                    cal_per_batch = self.db.total_calories[recipe_indices.long()]
                else:
                    cal_per_batch = recipe_nutr[:, 0] * slot_servings
                diversity_boost = torch.zeros(N, device=self.device)
                diversity_boost[recipe_protein_source == 0] = self.config.beef_boost * 0.5
                diversity_boost[recipe_protein_source == 1] = self.config.protein_diversity_boost * 0.5
                diversity_boost[recipe_protein_source == 3] = self.config.fish_boost * 0.5
                boost_amount = diversity_boost * (cal_per_batch / 1000.0)
                costs -= boost_amount.unsqueeze(0)

            # === PANTRY URGENCY BONUS (batched) ===
            # PERF: Only compute if there are items expiring soon.
            ttl_window = self.config.ttl_urgency_window
            if pantry_ttl is not None:
                batch_ttl = pantry_ttl[k_start:k_end]  # [batch_K, I]
                has_expiring = ((batch_ttl < ttl_window) & (batch_pantries > 0)).any()
                if has_expiring:
                    indices = recipe_indices.long()
                    ing_idx = self.db.ingredient_indices[indices]  # [N, MAX_NNZ]
                    ing_amt = self.db.ingredient_amounts[indices].float()  # [N, MAX_NNZ]
                    recipe_servings_exp = self.db.servings[indices].float().view(N, 1)
                    full_amounts = ing_amt * recipe_servings_exp  # [N, MAX_NNZ]

                    ing_idx_flat = ing_idx.long().flatten()  # [N * MAX_NNZ]
                    ttl_gathered = batch_ttl[:, ing_idx_flat].view(batch_K, N, MAX_NNZ)  # [batch_K, N, MAX_NNZ]

                    # Only give bonus for truly expiring items.
                    urgency = torch.where(
                        ttl_gathered < ttl_window,
                        1.0 / ttl_gathered.clamp(min=1.0),
                        torch.zeros_like(ttl_gathered)
                    )

                    pantry_gathered = batch_pantries[:, ing_idx_flat].view(batch_K, N, MAX_NNZ)
                    overlap = torch.minimum(pantry_gathered, full_amounts.unsqueeze(0))
                    # Urgency bonus from config (was hardcoded 0.01)
                    # float64 sum + round to eliminate CPU/CUDA divergence
                    urgency_bonus = torch.round((overlap * urgency * self.config.perishable_urgency_value).float().sum(dim=2) * 100.0).float() / 100.0  # [batch_K, N]
                    costs -= urgency_bonus

                    if pantry_frozen is not None and self.config.frozen_pantry_usage_value > 0:
                        batch_frozen = pantry_frozen[k_start:k_end]
                        frozen_gathered = batch_frozen[:, ing_idx_flat].view(batch_K, N, MAX_NNZ)
                        frozen_overlap = overlap * frozen_gathered.float()
                        frozen_bonus = torch.round((frozen_overlap * self.config.frozen_pantry_usage_value).float().sum(dim=2) * 100.0).float() / 100.0  # [batch_K, N]
                        costs -= frozen_bonus

            if (
                getattr(self.config, 'enable_at_risk_pantry_rescue', False)
                and not getattr(self.config, 'enable_perishable_urgency', True)
            ):
                # Main scoring already has FEFO urgency. Only apply the rescue
                # credit here if that older urgency scorer is disabled.
                batch_ttl_for_rescue = pantry_ttl[k_start:k_end] if pantry_ttl is not None else None
                batch_frozen_for_rescue = pantry_frozen[k_start:k_end] if pantry_frozen is not None else None
                rescue_credit = self._compute_at_risk_pantry_rescue_credit(
                    batch_pantries,
                    recipe_indices,
                    batch_ttl_for_rescue,
                    batch_frozen_for_rescue,
                )
                costs -= rescue_credit

            # Apply leftover bonus BEFORE per-serving normalization (bonus is in total $)
            costs -= leftover_bonus.unsqueeze(0)  # [batch_K, N] - [1, N]

            # Apply serving-match penalty (penalizes wrong-sized batches based on leftover_pct_target)
            costs += serving_match_penalty.unsqueeze(0)  # [batch_K, N] - [1, N]

            # === DYNAMIC EXCESS SERVING PENALTY + TEMPLATE MATCH BONUS (batched) ===
            if leftovers is not None:
                batch_leftovers = leftovers[k_start:k_end]  # [batch_K, L, 9]

                # --- Dynamic penalty: only when leftover inventory exceeds threshold ---
                current_lo_servings = torch.round(batch_leftovers[:, :, 1].clamp(min=0).float().sum(dim=1) * 100.0).float() / 100.0  # [batch_K]
                over_threshold = (current_lo_servings - leftover_threshold).clamp(min=0)  # [batch_K]
                inventory_penalty_mult = (over_threshold / leftover_threshold).clamp(max=2.0)  # [batch_K]
                # Use raw_leftover_servings (not capped) so penalty scales with actual excess
                dynamic_penalty = inventory_penalty_mult.unsqueeze(1) * self.config.excess_serving_penalty * raw_leftover_servings.unsqueeze(0)
                costs += dynamic_penalty  # [batch_K, N]

                # --- Template match bonus ---
                side_leftover_mask = (batch_leftovers[:, :, 7] == 2) & (batch_leftovers[:, :, 1] > 0)  # [batch_K, L]
                side_templates = batch_leftovers[:, :, 8].long()  # [batch_K, L]
                recipe_templates = self.db.gpu_recipe_to_template[recipe_indices.long()]  # [N]
                template_matches = (side_templates.unsqueeze(2) == recipe_templates.view(1, 1, -1))  # [batch_K, L, N]
                template_matches = template_matches & side_leftover_mask.unsqueeze(2)  # [batch_K, L, N]
                has_matching_leftover = template_matches.any(dim=1).float()  # [batch_K, N]
                # Template match bonus from config (was hardcoded 3.0)
                costs -= has_matching_leftover * self.config.template_match_bonus

                frozen_count = (batch_leftovers[:, :, 6] > 0).sum(dim=1).float()
                frozen_over = (frozen_count - self.config.frozen_count_threshold).clamp(min=0)
                if frozen_over.any():
                    frozen_pressure_penalty = self.config.frozen_pressure_base * (frozen_over / 8.0)
                    costs += frozen_pressure_penalty.unsqueeze(1)

            # === HOLDING COST CONTROLLER (batched) ===
            if self.config.enable_holding_cost:
                # Current pantry size per frontier in kg
                current_pantry_kg = torch.round(batch_pantries.float().sum(dim=1) * 100.0).float() / 100.0 / 1000.0  # [batch_K]
                target_kg = max(self.config.target_pantry_kg, 1.0)  # Guard against div/0
                rate = self.config.holding_cost_rate

                # Excess ratio: how far above target we are
                excess_ratio = ((current_pantry_kg - target_kg) / target_kg).clamp(min=0)  # [batch_K]

                # Holding rate scales with excess
                holding_rate = excess_ratio * rate  # [batch_K]

                # Only penalize GROWTH (positive inventory_delta)
                positive_delta_kg = inventory_delta.clamp(min=0) / 1000.0  # [batch_K, N]

                # Add holding cost
                holding_cost = positive_delta_kg * holding_rate.unsqueeze(1)  # [batch_K, N]
                costs += holding_cost

            # === PER-SERVING NORMALIZATION (batched) ===
            # Use slot_servings for fair comparison (what we actually cook)
            if USE_PER_SERVING_COST:
                costs = costs / slot_servings  # Now in $/serving

            # Variety filter for batch (OPTIMIZED: pooled scatter/gather)
            if batch_K <= self._cooldown_mask_pool.shape[0]:
                mask = self._cooldown_mask_pool[:batch_K, :self._cooldown_mask_size]
                mask.zero_()
            else:
                mask = torch.zeros(batch_K, self._cooldown_mask_size, dtype=torch.bool, device=self.device)
            mask.scatter_(1, batch_used_ids, True)
            in_cooldown = mask[:, recipe_ids]  # [batch_K, N]
            costs[in_cooldown] = float('inf')

            # Quality filters (penalties are in $/serving now)
            costs[:, low_cal] += 100.0  # $100/srv penalty for non-food
            costs[:, low_ing] += 20.0   # $20/srv penalty for trivial recipes
            costs[:, low_servings] += 200.0  # $200/srv penalty - must produce enough servings!
            costs[:, high_cal] += 1000.0  # $1000/srv penalty for calorie bombs (>40% of daily cal)

            # === PROGRESSIVE PROTEIN QUOTA (batched) ===
            if self._protein_targets is not None and protein_counts is not None:
                batch_counts = protein_counts[k_start:k_end]  # [batch_K, 6]
                tagged_total = batch_counts.sum(dim=1, keepdim=True).clamp(min=1)  # [batch_K, 1]
                expected = self._protein_targets.unsqueeze(0) * tagged_total  # [batch_K, 6]
                deviation = batch_counts.float() - expected  # [batch_K, 6]
                overuse_penalty = self._protein_strictness * torch.clamp(deviation, min=0) ** 2
                underuse_bonus = self._protein_strictness * 0.5 * torch.clamp(-deviation, min=0)
                net_adjustment = overuse_penalty - underuse_bonus  # [batch_K, 6]
                valid_src = (recipe_protein_source >= 0) & (recipe_protein_source <= 5)
                if valid_src.any():
                    src_adj = net_adjustment[:, recipe_protein_source[valid_src].long()]
                    costs[:, valid_src] += src_adj

            # Quantize final costs to eliminate CPU/CUDA float32 noise before ranking
            # Top M for batch
            top_m_costs, top_m_pos = self._stable_topk(costs, k=actual_m, largest=False, dim=1)
            top_m_db_idx = recipe_indices[top_m_pos]

            all_top_m_idx.append(top_m_db_idx)
            all_top_m_costs.append(top_m_costs)

            # Free memory
            del costs, pantry_usage, inventory_delta

        return torch.cat(all_top_m_idx, dim=0), torch.cat(all_top_m_costs, dim=0)

    def _compute_remaining_debt(
        self,
        nutrition: torch.Tensor,  # [K, 2] current cumulative nutrition
        slot: int,
    ) -> torch.Tensor:
        """
        Compute remaining calorie/protein debt for the week.
        """
        meals_remaining = max(NUM_SLOTS - slot, 1)

        # Remaining targets
        remaining_cal_target = self.weekly_calories * (meals_remaining / NUM_SLOTS)
        remaining_prot_target = self.weekly_protein * (meals_remaining / NUM_SLOTS)

        # What we need per meal to stay on track
        cal_per_meal = remaining_cal_target / meals_remaining
        prot_per_meal = remaining_prot_target / meals_remaining

        return torch.tensor([[cal_per_meal, prot_per_meal]], device=self.device).expand(nutrition.shape[0], 2)

    def _compute_shadow_prices(
        self,
        current_achieved: Dict[str, torch.Tensor],  # {constraint_name: [K] achieved so far}
        weekly_targets: Dict[str, float],           # {constraint_name: weekly target}
        slot: int,
    ) -> Dict[str, torch.Tensor]:
        """
        ⚠️  DEAD CODE: This method is NEVER CALLED anywhere in the planner!

        A working implementation exists in scoring.py (GPUBatchScorer).
        This was added in commit 8cf28ca but never wired into the scoring loop.

        ---

        Compute shadow price λ for each constraint based on urgency.

        Shadow price formula:
            λ = λ_min + (λ_max - λ_min) * urgency^γ

        where urgency = clip(1 - margin/τ, 0, 1)
        and margin = max_achievable - debt (how much buffer we have)

        Returns dict of {constraint_name: [K] lambda values}
        """
        remaining_slots = max(NUM_SLOTS - slot, 1)
        K = next(iter(current_achieved.values())).shape[0]

        lambdas = {}
        for name, achieved in current_achieved.items():
            target = weekly_targets.get(name, 0)
            if target <= 0:
                lambdas[name] = torch.full((K,), self.shadow_lambda_min, device=self.device)
                continue

            # Debt = what we still need
            debt = (target - achieved).clamp(min=0)  # [K]

            # Pace needed per slot
            pace = debt / remaining_slots  # [K]

            # Estimate max achievable (rough: assume ~1000 cal/meal provides ~100g veg, ~50g fruit)
            # This is a heuristic - in practice we'd compute from available recipes
            if name == 'calories':
                max_per_slot = 2000.0  # Can get 2000 cal per meal max
            elif name == 'protein':
                max_per_slot = 100.0   # Can get 100g protein per meal max
            elif name == 'vegetables_g':
                max_per_slot = 300.0   # Can get 300g vegetables per meal
            elif name == 'fruits_g':
                max_per_slot = 200.0   # Can get 200g fruit per meal
            else:
                max_per_slot = 100.0

            max_achievable = max_per_slot * remaining_slots

            # Margin = how much buffer we have
            margin = max_achievable - debt  # [K]

            # Urgency: 0 = comfortable, 1 = critical
            # If margin > tau * target, we're relaxed (urgency near 0)
            # If margin < 0, we're in trouble (urgency = 1)
            tau_amount = self.shadow_tau * target
            urgency = (1.0 - margin / max(tau_amount, 1.0)).clamp(0, 1)  # [K]

            # Shadow price: rises with urgency
            # Protein uses separate lambda_max (protein is in grams ~20/meal,
            # calories are ~600/meal, so protein needs stronger lambda for equal weight)
            _lam_max = self.shadow_lambda_max
            if name == 'protein':
                _lam_max = getattr(self.config, 'shadow_prot_lambda_max', self.shadow_lambda_max)
            lam = self.shadow_lambda_min + \
                  (_lam_max - self.shadow_lambda_min) * (urgency ** self.shadow_gamma)

            lambdas[name] = lam

        return lambdas

    def _compute_calorie_over_lambda(
        self,
        *,
        current_calories: torch.Tensor,
        slot: int,
    ) -> torch.Tensor:
        """Price over-calorie candidates separately from deficit urgency."""
        lambda_min = getattr(self.config, 'shadow_cal_over_lambda_min', self.shadow_lambda_min)
        if slot <= 0:
            return torch.full_like(current_calories, lambda_min)

        expected_before_slot = max(float(self.weekly_calories) * (slot / NUM_SLOTS), 1.0)
        current_progress_pct = current_calories / expected_before_slot
        over_urgency = ((current_progress_pct - 1.0) / 0.25).clamp(0.0, 1.0)
        lambda_max = getattr(self.config, 'shadow_cal_over_lambda_max', self.shadow_lambda_max)
        return lambda_min + (lambda_max - lambda_min) * (over_urgency ** self.shadow_gamma)

    def _compute_dynamic_servings(
        self,
        recipe_indices: torch.Tensor,    # [N] indices into recipe database
        slot: int,
        meal_type: str = 'lunch',        # 'breakfast', 'lunch', 'dinner'
        slot_type: str = 'main',         # 'main', 'side'
    ) -> Tuple[torch.Tensor, float]:
        """
        Compute dynamic servings for recipes based on target calories per serving.

        DYNAMIC SERVINGS APPROACH:
        Instead of using author-defined servings (which vary wildly),
        compute servings based on: total_recipe_cal / target_cal_per_srv

        This normalizes all recipes to deliver consistent calorie portions.

        Args:
            recipe_indices: [N] indices into recipe database
            slot: Current slot number (0-20)
            meal_type: 'breakfast', 'lunch', or 'dinner'
            slot_type: 'main' or 'side'

        Returns:
            dynamic_servings: [N] computed serving counts
            target_cal_per_srv: the target cal/srv used
        """
        if not self.config.enable_dynamic_servings:
            # Dynamic servings disabled - return original servings
            indices = recipe_indices.long()
            return self.db.servings[indices].float(), 0.0

        indices = recipe_indices.long()
        N = len(indices)

        # Get total recipe calories (pre-computed in database)
        total_recipe_cal = self.db.total_calories[indices]  # [N]

        # Get fixed-portion mask
        is_fixed = self.db.is_fixed_portion[indices]  # [N] bool

        # Get target cal/srv from config
        target_cal_per_srv = self.config.get_slot_cal_target(meal_type, slot_type)

        # One-dish meals must cover BOTH main and side calories since no side is selected.
        # Without this, a one-dish soup targets only 70% of meal calories (the main share),
        # and the missing 30% (side share) is never delivered — causing daily calorie drops.
        if slot_type == 'main':
            is_one_dish = self.db.gpu_recipe_is_one_dish[indices]  # [N] bool
            if is_one_dish.any():
                side_cal = self.config.get_slot_cal_target(meal_type, 'side')
                full_meal_target = target_cal_per_srv + side_cal
                target_cal_tensor = torch.where(
                    is_one_dish,
                    torch.tensor(full_meal_target, device=self.device),
                    torch.tensor(target_cal_per_srv, device=self.device),
                )
            else:
                target_cal_tensor = None
        else:
            target_cal_tensor = None

        # Compute dynamic servings
        if target_cal_tensor is not None:
            dynamic_servings = total_recipe_cal / target_cal_tensor.clamp(min=100.0)
        else:
            dynamic_servings = total_recipe_cal / max(target_cal_per_srv, 100.0)  # [N]

        # Apply constraints
        min_srv = self.config.min_dynamic_servings
        max_srv = self.config.max_dynamic_servings

        # Scale max by household for larger families.
        # NOTE: Pre-7ed3c169 there was no min clamp — recipes were taken at their
        # natural dyn_srv. Adding `min_srv = max(min_srv, household_size)` was
        # the wrong fix for "family of 6 picks 1-serving recipe": it relabels
        # 2.67 standard servings as 4, which under-portions every plate
        # (1600 cal recipe / 4 fake servings * 4 people = 1600 cal slot
        #  delivered into a 2533-cal slot target). Verified hh4 compliance
        # collapses to 86% with the clamp; hh1/hh2 unaffected because their
        # min_srv is already <= native dyn_srv. If small-recipe-for-big-family
        # is a real concern, fix it as a SKIP filter on candidate selection,
        # not a relabel of the calorie math here.
        if self.config.scale_servings_by_household:
            household_size = len(self.attendance.household.people)
            max_srv = max_srv * max(1, household_size / 2)

        dynamic_servings = dynamic_servings.clamp(min=min_srv, max=max_srv)

        # Apply rounding
        if self.config.dynamic_serving_rounding == 'ceil':
            dynamic_servings = dynamic_servings.ceil()
        elif self.config.dynamic_serving_rounding == 'floor':
            dynamic_servings = dynamic_servings.floor()
        else:  # 'round'
            dynamic_servings = dynamic_servings.round()

        # For fixed-portion recipes, use original servings.
        # Products get multi-package scaling: buy enough packages to fill calorie needs.
        original_servings = self.db.servings[indices].float()
        is_product = self.db.is_product[indices] if hasattr(self.db, 'is_product') else torch.zeros(N, dtype=torch.bool, device=self.device)

        if is_product.any():
            prod_cal = self.db.nutrition[indices, 0].float().clamp(min=1.0)
            slot_srv = self.servings_per_slot[slot].item()
            srv_per_person = (target_cal_per_srv / prod_cal).ceil().clamp(min=1.0)
            total_mfr_needed = srv_per_person * slot_srv
            pkg_srv = original_servings.clamp(min=1.0)
            packages = (total_mfr_needed / pkg_srv).ceil()
            product_dynamic = (packages * pkg_srv).clamp(min=min_srv, max=max_srv)
            dynamic_servings = torch.where(is_product, product_dynamic, dynamic_servings)

        use_original = is_fixed  # products no longer forced to original
        dynamic_servings = torch.where(use_original, original_servings, dynamic_servings)

        return dynamic_servings, target_cal_per_srv

    def _dynamic_effective_cal_ceiling(
        self,
        target_cal_per_srv: float,
        slot_servings: float,
    ) -> float:
        """Cap effective dynamic calories relative to this slot's portion target.

        Dynamic servings normally normalizes full-recipe calories down to a
        target portion. When a huge batch hits max_dynamic_servings, that
        normalization fails and the effective serving can be far above the meal
        target. Small households are most sensitive because one oversized
        leftover can repeat for days.
        """
        if slot_servings <= 2:
            return max(float(target_cal_per_srv) * 1.6, 450.0)
        return max(float(target_cal_per_srv) * 2.2, 800.0)

    def _get_meal_type_from_slot(self, slot: int) -> str:
        """Convert slot number (0-20) to meal type."""
        # 21 slots per week: 7 days × 3 meals
        # Slot 0-6 = day 0-6 breakfast, slot 7-13 = lunch, slot 14-20 = dinner
        # Actually: slot % 3 == 0 → breakfast, 1 → lunch, 2 → dinner
        meal_idx = slot % 3
        if meal_idx == 0:
            return 'breakfast'
        elif meal_idx == 1:
            return 'lunch'
        else:
            return 'dinner'

    def _nutrition_select(
        self,
        top_m_db_idx: torch.Tensor,     # [K, M] database indices of cost-filtered candidates
        top_m_costs: torch.Tensor,      # [K, M] costs of filtered candidates
        servings_to_cook: torch.Tensor, # [K] servings needed
        nutrition_debt: torch.Tensor,   # [K, 2] (cal_per_meal, prot_per_meal)
        current_nutrition: torch.Tensor, # [K, 2] cumulative nutrition so far
        slot: int,
        top_k: int,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Pass 2: From cost-filtered pool, select by nutrition compliance.
        Enforces calorie bounds: 90-105% range.
        Returns indices and costs of top K nutritious recipes.
        """
        K, M = top_m_db_idx.shape

        if M == 0:
            return torch.zeros(K, 0, dtype=torch.long, device=self.device), \
                   torch.full((K, 0), float('inf'), device=self.device), \
                   torch.zeros(K, 0, device=self.device)

        # Gather nutrition for filtered candidates
        nutr = self.db.nutrition[top_m_db_idx.long()].float()  # [K, M, 4]
        scoring_servings = servings_to_cook.view(K, 1).expand(K, M)
        if self.config.enable_dynamic_servings:
            meal_type = self._get_meal_type_from_slot(slot)
            flat_db_idx = top_m_db_idx.reshape(-1).long()
            dynamic_servings, _ = self._compute_dynamic_servings(flat_db_idx, slot, meal_type, 'main')
            total_recipe_cal = self.db.total_calories[flat_db_idx].float()
            effective_cal_per_srv = total_recipe_cal / dynamic_servings.clamp(min=1.0)
            original_cal_per_srv = self.db.nutrition[flat_db_idx, 0].float().clamp(min=1.0)
            nutrition_scale = (effective_cal_per_srv / original_cal_per_srv).view(K, M, 1)
            nutr = nutr * nutrition_scale
            recipe_servings_for_cap = dynamic_servings.view(K, M)
        else:
            recipe_servings_for_cap = self.db.servings[top_m_db_idx.long()].float()

        # Compute nutrition contribution using the same cap as delivery.
        servings_exp = torch.minimum(scoring_servings, recipe_servings_for_cap)
        cal_contrib = nutr[:, :, 0] * servings_exp   # [K, M]
        prot_contrib = nutr[:, :, 1] * servings_exp  # [K, M]

        # === CALORIE BOUNDS: 90-105% ===
        meals_remaining = max(NUM_SLOTS - slot, 1)
        current_cal = current_nutrition[:, 0:1]  # [K, 1]

        # After eating this recipe, what would total calories be?
        projected_cal = current_cal + cal_contrib  # [K, M]

        # How much "room" do we have left (in remaining meals)?
        cal_after_this = projected_cal  # [K, M]
        remaining_after = meals_remaining - 1

        # Target bounds for END of week
        cal_floor = self.weekly_calories * self.config.calorie_floor_pct
        cal_ceiling = self.weekly_calories * self.config.calorie_ceiling_pct

        # If remaining_after > 0, check if we're on pace
        # Projected final = current + this_meal + (remaining_meals * avg_pace)
        # For now, simpler: penalize if this meal would push us over ceiling pace
        cal_ceiling_pace = (cal_ceiling - current_cal) / meals_remaining  # Max cals this meal [K, 1]
        cal_floor_pace = (cal_floor - current_cal) / meals_remaining  # Min cals this meal [K, 1]

        # Deviation from ideal
        cal_target = nutrition_debt[:, 0:1]  # [K, 1]
        prot_target = nutrition_debt[:, 1:2]  # [K, 1]

        # Penalize being under floor OR over ceiling (asymmetric: over is worse)
        cal_under = (cal_floor_pace - cal_contrib).clamp(min=0)  # [K, M] - too few cals
        cal_over = (cal_contrib - cal_ceiling_pace).clamp(min=0)  # [K, M] - too many cals

        # Protein: just deviation from target
        prot_dev = (prot_contrib - prot_target).abs()  # [K, M]

        # Combine penalties
        # Over ceiling penalty is configurable (can't un-eat, but can add snacks for under)
        nutrition_score = (cal_under + cal_over * self.config.cal_over_ceiling_mult + prot_dev) * 0.01

        combined_score = top_m_costs + nutrition_score
        # Select top K
        actual_k = min(top_k, M)
        _, top_k_in_m = self._stable_topk(combined_score, k=actual_k, largest=False, dim=1)

        # Map back to database indices
        top_k_db_idx = torch.gather(top_m_db_idx, 1, top_k_in_m)  # [K, actual_k]
        top_k_costs = torch.gather(top_m_costs, 1, top_k_in_m)    # [K, actual_k]
        top_k_scores = torch.gather(combined_score, 1, top_k_in_m)  # [K, actual_k]

        return top_k_db_idx, top_k_costs, top_k_scores

    def _two_pass_score(
        self,
        recipe_indices: torch.Tensor,    # [N] indices into recipe database
        pantries: torch.Tensor,          # [K, I] current pantry states
        pantry_frozen: Optional[torch.Tensor],  # [K, I] frozen-state for pantry burn-down bonus
        current_nutrition: torch.Tensor, # [K, 4] cumulative nutrition (cal, protein, carbs, fat)
        current_food_groups: torch.Tensor,  # [K, 2] cumulative food groups (veg_g, fruit_g) - tracked but NOT scored
        slot: int,
        used_ids: torch.Tensor,          # [K, COOLDOWN_LEN] variety ring
        servings_to_cook: torch.Tensor,  # [K] servings needed
        top_m: int = 200,                # Cost filter size
        protein_counts: Optional[torch.Tensor] = None,  # [K, 6] protein source counts for quota
        leftovers: Optional[torch.Tensor] = None,  # [K, L, LEFTOVER_FIELDS] for template match bonus
        pantry_ttl: Optional[torch.Tensor] = None,  # [K, I] TTL for urgency bonus
        daily_nutrition: Optional[torch.Tensor] = None,  # [K, 7, 4] Phase 3 daily tracking
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Two-pass scoring for MAINS: cost filter → calorie/protein scoring.

        MAINS are the protein/calorie engine. NO fruit/veg shadow prices here.
        Fruit/veg scoring is ONLY applied to sides (Stage B).

        Pass 1: Filter to top M cheapest candidates (pantry items = $0)
        Pass 2: Score by calorie/protein compliance, combine with cost

        Returns:
            - top_m_db_idx: [K, M] database indices of filtered candidates
            - top_m_costs: [K, M] purchase costs
            - combined_scores: [K, M] final scores for global selection
        """
        K = pantries.shape[0]

        # === PASS 1: COST FILTER (with calorie band) ===
        top_m_db_idx, top_m_costs = self._cost_filter_candidates(
            pantries=pantries,
            recipe_indices=recipe_indices,
            used_ids=used_ids,
            slot=slot,
            top_m=top_m,
            protein_counts=protein_counts,
            leftovers=leftovers,
            pantry_ttl=pantry_ttl,
            pantry_frozen=pantry_frozen,
            current_nutrition=current_nutrition,
            slot_idx=slot,
        )

        M = top_m_db_idx.shape[1]

        # === LEFTOVER COVERAGE CREDIT ===
        # Frontiers that don't need to cook (have enough leftovers) should have ZERO main cost
        # This is the key fix: leftovers are FREE - we already paid when we made them
        no_cook_mask = servings_to_cook == 0  # [K]
        if M > 0:
            top_m_costs = top_m_costs.clone()  # FIX: Always clone to prevent aliasing issues
            if no_cook_mask.any():
                top_m_costs[no_cook_mask] = 0.0  # Free main dish - eating leftovers
        if M == 0:
            return top_m_db_idx, top_m_costs, torch.full((K, 0), float('inf'), device=self.device)

        # === PASS 2: CALORIE/PROTEIN SCORING (no fruit/veg for mains) ===
        meals_remaining = max(NUM_SLOTS - slot, 1)

        # Gather nutrition for filtered candidates (NO food groups for mains)
        nutr = self.db.nutrition[top_m_db_idx.long()].float()  # [K, M, 4] = [cal, protein, carbs, fat]
        scoring_servings = servings_to_cook.view(K, 1).expand(K, M)  # [K, M]
        if self.config.enable_dynamic_servings:
            meal_type = self._get_meal_type_from_slot(slot)
            flat_db_idx = top_m_db_idx.reshape(-1).long()
            dynamic_servings, _ = self._compute_dynamic_servings(flat_db_idx, slot, meal_type, 'main')
            total_recipe_cal = self.db.total_calories[flat_db_idx].float()
            effective_cal_per_srv = total_recipe_cal / dynamic_servings.clamp(min=1.0)
            original_cal_per_srv = self.db.nutrition[flat_db_idx, 0].float().clamp(min=1.0)
            nutrition_scale = (effective_cal_per_srv / original_cal_per_srv).view(K, M, 1)
            nutr = nutr * nutrition_scale
            recipe_servings_for_cap = dynamic_servings.view(K, M)
        else:
            recipe_servings_for_cap = self.db.servings[top_m_db_idx.long()].float()

        # Match transition accounting: delivery caps consumed servings at the
        # recipe's dynamic/original production size, so scoring must not book
        # phantom nutrition above that cap.
        servings_exp = torch.minimum(scoring_servings, recipe_servings_for_cap)
        cal_contrib = nutr[:, :, 0] * servings_exp     # [K, M]
        prot_contrib = nutr[:, :, 1] * servings_exp    # [K, M]
        carbs_contrib = nutr[:, :, 2] * servings_exp   # [K, M]
        fat_contrib = nutr[:, :, 3] * servings_exp     # [K, M]

        # Compute pace (what we need per remaining slot)
        cal_debt = (self.weekly_calories - current_nutrition[:, 0]).clamp(min=0)
        prot_debt = (self.weekly_protein - current_nutrition[:, 1]).clamp(min=0)

        cal_pace = cal_debt / meals_remaining  # [K]
        prot_pace = prot_debt / meals_remaining

        # === SHADOW PRICING (urgency-aware weights) ===
        # Dynamic weights that increase when falling behind targets
        shadow_prices = self._compute_shadow_prices(
            current_achieved={'calories': current_nutrition[:, 0], 'protein': current_nutrition[:, 1]},
            weekly_targets={'calories': self.weekly_calories, 'protein': self.weekly_protein},
            slot=slot,
        )
        cal_lambda = shadow_prices['calories'].view(K, 1)  # [K, 1]
        prot_lambda = shadow_prices['protein'].view(K, 1)  # [K, 1]

        # Calorie bounds (configurable floor/ceiling)
        current_cal = current_nutrition[:, 0:1]  # [K, 1]
        cal_floor = self.weekly_calories * self.config.calorie_floor_pct
        cal_ceiling = self.weekly_calories * self.config.calorie_ceiling_pct
        cal_ceiling_pace = (cal_ceiling - current_cal) / meals_remaining  # [K, 1]
        cal_floor_pace = (cal_floor - current_cal) / meals_remaining  # [K, 1]

        # Penalize being under floor OR over ceiling. Use a separate over-calorie
        # lambda; the deficit shadow price intentionally drops when calories are
        # ahead, which otherwise makes surplus too cheap.
        cal_under = (cal_floor_pace - cal_contrib).clamp(min=0)  # [K, M]
        cal_over = (cal_contrib - cal_ceiling_pace).clamp(min=0)  # [K, M]
        cal_over_lambda = self._compute_calorie_over_lambda(
            current_calories=current_cal,
            slot=slot,
        )

        # Protein shortfall from pace (FLOOR ONLY - don't penalize excess protein)
        # Extra protein is nutritionally fine and cheap sources are the cost optimizer's
        # best tools. Only penalize falling BELOW target.
        prot_target = prot_pace.view(K, 1)
        prot_dev = (prot_target - prot_contrib).clamp(min=0)  # [K, M] shortfall only

        # === SHADOW PRICE SCORING (urgency-aware) ===
        # Weight deviations by shadow prices (higher when falling behind)
        # cal_lambda: 0.001 (on track) → 0.05 (falling behind)
        # prot_lambda: 0.001 (on track) → 0.05 (falling behind)
        # Over ceiling multiplier is configurable (default 2.0, can go up to 10.0)
        cal_penalty = (
            cal_under * cal_lambda
            + cal_over * self.config.cal_over_ceiling_mult * cal_over_lambda
        )  # [K, M]
        prot_penalty = prot_dev * prot_lambda  # [K, M]
        nutrition_score = cal_penalty + prot_penalty

        # === MACRO BALANCE PENALTY ===
        # Calculate what macro split would be after adding this recipe
        current_prot_g = current_nutrition[:, 1:2]  # [K, 1]
        current_carbs_g = current_nutrition[:, 2:3]  # [K, 1]
        current_fat_g = current_nutrition[:, 3:4]   # [K, 1]

        new_prot_g = current_prot_g + prot_contrib    # [K, M]
        new_carbs_g = current_carbs_g + carbs_contrib  # [K, M]
        new_fat_g = current_fat_g + fat_contrib        # [K, M]

        # Convert to calories: protein=4cal/g, carbs=4cal/g, fat=9cal/g
        new_prot_cal = new_prot_g * 4
        new_carbs_cal = new_carbs_g * 4
        new_fat_cal = new_fat_g * 9
        new_total_cal = new_prot_cal + new_carbs_cal + new_fat_cal

        # Calculate percentage deviation from targets (avoid div by zero)
        eps = 1e-6
        prot_pct = (new_prot_cal / (new_total_cal + eps)) * 100
        carbs_pct = (new_carbs_cal / (new_total_cal + eps)) * 100
        fat_pct = (new_fat_cal / (new_total_cal + eps)) * 100

        # Deviation from targets (only penalize if beyond tolerance)
        prot_dev_macro = (prot_pct - self.protein_pct_target).abs() - self.macro_tolerance_pct
        carbs_dev_macro = (carbs_pct - self.carbs_pct_target).abs() - self.macro_tolerance_pct
        fat_dev_macro = (fat_pct - self.fat_pct_target).abs() - self.macro_tolerance_pct

        # Penalty only for deviations beyond tolerance (weight from config)
        macro_penalty = (prot_dev_macro.clamp(min=0) + carbs_dev_macro.clamp(min=0) + fat_dev_macro.clamp(min=0)) * self.config.macro_deviation_weight

        # === PROTEIN DENSITY BONUS (Bidirectional) ===
        # Pull recipe selection toward protein target from BOTH sides.
        # A recipe at exactly the target gets full bonus. 10pp away gets 60%.
        # 25pp+ away gets nothing. This works for targets above AND below db average.
        density_bonus = torch.zeros(K, M, device=self.device)
        # NOTE: Removed 'target > 15' check to enable density bonus at any level
        if self.config.enable_protein_density_bonus:
            eps_pdb = 1e-6
            recipe_prot_pct = (prot_contrib * 4) / (cal_contrib + eps_pdb) * 100  # [K, M]
            prot_distance = (recipe_prot_pct - self.protein_pct_target).abs()  # [K, M] pp from target
            proximity = (1.0 - prot_distance / 25.0).clamp(min=0)  # [K, M] 0-1 score
            density_bonus = proximity * self.config.protein_density_value  # [K, M]

        # === PHASE 3: DAILY BALANCE PENALTY ===
        # This is the key fix for "skinny Sundays" - penalize when TODAY is behind/ahead
        # even if the WEEKLY target looks on track
        daily_penalty = torch.zeros(K, M, device=self.device)

        if daily_nutrition is not None and getattr(self.config, 'enable_separate_shadow_prices', False):
            day = slot // 3
            meal_idx = slot % 3
            meals_left_today = 3 - meal_idx  # 3=breakfast, 2=lunch, 1=dinner

            # Daily target = weekly / 7
            daily_cal_target = self.weekly_calories / 7.0  # [K] scalar broadcast

            # What we've achieved today so far (from daily_nutrition tracking)
            today_achieved = daily_nutrition[:, day, 0]  # [K]

            # What we still need today
            today_debt = (daily_cal_target - today_achieved).clamp(min=0)  # [K]

            # Pace per remaining meal today (NOT remaining slots in week!)
            # This is the key difference from weekly shadow pricing
            today_pace = today_debt / max(meals_left_today, 1)  # [K]

            # How far off is this recipe from today's pace?
            # cal_contrib is [K, M] - what we'd get from each recipe
            daily_deviation = (cal_contrib - today_pace.view(K, 1)).abs()  # [K, M]

            # Scale urgency by meal position: dinner has most pressure to balance
            # breakfast=1x, lunch=2x, dinner=3x (fixed scaling, not 1/3/5)
            meal_urgency = 1.0 + meal_idx  # 0→1, 1→2, 2→3

            # Dynamic lambda: higher when BEHIND or AHEAD of today's target
            # This is the key fix: penalize OVERSHOOTING too, not just undershooting
            progress_today = today_achieved / (daily_cal_target + 1e-6)  # [K]
            expected_progress = meal_idx / 3.0  # 0=breakfast, 0.33=lunch, 0.67=dinner

            # FIXED: Use absolute deviation, not just behind_factor
            # Behind = progress < expected → need bigger meals
            # Ahead = progress > expected → need smaller meals (OVERSHOOT penalty)
            deviation_factor = (expected_progress - progress_today).abs()  # [K]
            lambda_min = getattr(self.config, 'daily_shadow_lambda_min', 0.01)
            lambda_max = getattr(self.config, 'daily_shadow_lambda_max', 0.30)
            daily_lambda = lambda_min + deviation_factor * (lambda_max - lambda_min)  # [K]

            # === COORDINATED SHADOW PRICING: FRESH URGENCY MULTIPLIER ===
            # Scale the daily penalty by day-of-week to coordinate with leftover ceiling
            if getattr(self.config, 'enable_coordinated_shadow_pricing', True):
                fresh_min = getattr(self.config, 'fresh_shadow_min', 0.50)
                fresh_max = getattr(self.config, 'fresh_shadow_max', 1.50)
                fresh_direction = self._effective_fresh_direction  # Use computed direction (supports alternating)

                if fresh_direction == 'ascending':
                    # LOW→HIGH: relax early, strict late
                    fresh_mult = fresh_min + (day / 6.0) * (fresh_max - fresh_min)
                else:
                    # HIGH→LOW: strict early, relax late
                    fresh_mult = fresh_max - (day / 6.0) * (fresh_max - fresh_min)
            else:
                fresh_mult = 1.0  # No day-of-week scaling

            # Normalize by typical meal size so penalty is $ scale
            cal_normalizer = getattr(self.config, 'daily_cal_normalizer', 600.0)
            daily_penalty = (daily_deviation / cal_normalizer) * daily_lambda.view(K, 1) * meal_urgency * fresh_mult  # [K, M]

            # === PROGRESSIVE OVERSHOOT PENALTY (Phase 3 fix for small households) ===
            # Problem: The deviation penalty above favors 500 cal recipe at 467 cal pace
            # because 500 is CLOSER to pace than 300 cal! But for hs1_cal1400, that
            # 500 cal recipe pushes the day to 130%+ which is BAD.
            # Solution: Add PROJECTED overshoot penalty that activates before hitting 100%
            if getattr(self.config, 'enable_progressive_overshoot', True):
                # Projected daily total if we select this recipe
                projected_total = today_achieved.view(K, 1) + cal_contrib  # [K, M]
                projected_pct = projected_total / daily_cal_target  # [K, M]

                # Family size scaling: small households need tight control
                # Large households can tolerate more variance for batch cooking
                family_size = self.attendance.household.size
                base_floor = getattr(self.config, 'progressive_overshoot_floor', 1.0)
                if family_size <= 2:
                    effective_floor = base_floor  # 100% for small households
                else:
                    effective_floor = base_floor + 0.05  # 105% for families of 4+

                overshoot_pct = (projected_pct - effective_floor).clamp(min=0)  # [K, M]

                # Penalty scales quadratically: 110% = 0.01*mult, 120% = 0.04*mult, 130% = 0.09*mult
                # At mult=100: 110% = $1, 120% = $4, 130% = $9
                # Also scaled by fresh_mult for day-of-week coordination
                overshoot_mult = getattr(self.config, 'progressive_overshoot_mult', 100.0)
                progressive_overshoot_penalty = (overshoot_pct ** 2) * overshoot_mult * meal_urgency * fresh_mult  # [K, M]

                daily_penalty = daily_penalty + progressive_overshoot_penalty

            # === PROGRESSIVE UNDERSHOOT PENALTY (Fix for underfed days - SMALL HOUSEHOLDS ONLY) ===
            # Problem: Overshoot penalty alone creates asymmetry - algorithm avoids big recipes
            # but happily picks small ones, leaving days at 57-70% of target.
            # Solution: Penalize recipes that would leave the day significantly underfed.
            #
            # IMPORTANT: Only apply to small households (hs1/hs2)!
            # Large households NEED daily variance for batch cooking - a 50% day is fine
            # because they're eating leftovers from yesterday's 130% cook.
            family_size = self.attendance.household.size
            if getattr(self.config, 'enable_progressive_undershoot', True) and family_size <= 2:
                # Projected daily total if we select this recipe
                projected_total = today_achieved.view(K, 1) + cal_contrib  # [K, M]
                projected_pct = projected_total / daily_cal_target  # [K, M]

                # Undershoot threshold: below this, we're at risk of ending underfed
                base_ceiling = getattr(self.config, 'progressive_undershoot_ceiling', 0.90)

                # Only penalize when we're late in the day (meal_idx=2 is dinner)
                # At breakfast, being at 30% is fine. At dinner, 70% is a problem.
                # Scale penalty by how few meals remain
                meals_remaining_factor = max(0.0, 1.0 - meals_remaining / 3.0)  # 0 at breakfast, 0.67 at dinner

                undershoot_pct = (base_ceiling - projected_pct).clamp(min=0)  # [K, M]

                # Penalty scales quadratically, but only when late in day
                # Also scaled by fresh_mult for day-of-week coordination
                undershoot_mult = getattr(self.config, 'progressive_undershoot_mult', 100.0)
                progressive_undershoot_penalty = (undershoot_pct ** 2) * undershoot_mult * meal_urgency * meals_remaining_factor * fresh_mult  # [K, M]

                daily_penalty = daily_penalty + progressive_undershoot_penalty

            # TRACE: Show Phase 3 penalty computation (only slot 0 for brevity)
            if self.verbose and slot == 0:
                k = 0
                print(f"\n    [PHASE3 TRACE slot={slot}]")
                print(f"      daily_cal_target: {daily_cal_target:.0f}")
                print(f"      today_achieved[{k}]: {today_achieved[k].item():.0f} ({today_achieved[k].item()/daily_cal_target*100:.0f}%)")
                print(f"      today_debt[{k}]: {today_debt[k].item():.0f}")
                print(f"      today_pace: {today_pace[k].item():.0f} cal")
                print(f"      deviation_factor[{k}]: {deviation_factor[k].item():.3f}")
                print(f"      daily_lambda[{k}]: {daily_lambda[k].item():.4f}")
                print(f"      meal_urgency: {meal_urgency}")
                # Show top 5 recipes by cal_contrib - compare high vs low calorie
                top5_idx = cal_contrib[k].argsort(descending=True)[:3]  # Top 3 high-cal
                low3_idx = cal_contrib[k].argsort(descending=False)[:3]  # Top 3 low-cal
                print(f"      High-cal recipes (should have HIGH penalty if projecting >100%):")
                for i, idx in enumerate(top5_idx):
                    cal = cal_contrib[k, idx].item()
                    dev = daily_deviation[k, idx].item()
                    pen = daily_penalty[k, idx].item()
                    proj_pct = (today_achieved[k].item() + cal) / daily_cal_target * 100
                    print(f"        {cal:.0f} cal -> proj={proj_pct:.0f}%, penalty=${pen:.2f}")
                print(f"      Low-cal recipes (should have LOWER penalty):")
                for i, idx in enumerate(low3_idx):
                    cal = cal_contrib[k, idx].item()
                    if cal > 0:  # Skip zero-cal entries
                        dev = daily_deviation[k, idx].item()
                        pen = daily_penalty[k, idx].item()
                        proj_pct = (today_achieved[k].item() + cal) / daily_cal_target * 100
                        print(f"        {cal:.0f} cal -> proj={proj_pct:.0f}%, penalty=${pen:.2f}")

            # When AHEAD of target, penalize large recipes MORE (overshoot protection)
            # today_surplus > 0 means we've already exceeded daily target
            today_surplus = (today_achieved - daily_cal_target).clamp(min=0)  # [K]
            if today_surplus.sum() > 0:
                # Add extra penalty for recipes that make overshoot worse
                overshoot_penalty_rate = getattr(self.config, 'daily_overshoot_penalty_weight', 0.02)
                overshoot_contribution = (cal_contrib * overshoot_penalty_rate).clamp(min=0)  # [K, M]
                # Only apply to beams that are already overshooting
                overshoot_mask = (today_surplus > 0).float().view(K, 1)  # [K, 1]
                daily_penalty = daily_penalty + overshoot_contribution * overshoot_mask

        # === FRESH RECIPE DAILY CALORIE CAP ===
        # Hard cap to prevent fresh recipes from pushing today far over target.
        # This is a safety rail, not the daily pacing mechanism; daily shadow
        # prices and leftover ceilings do the fine-grained balancing.
        fresh_cap_penalty = torch.zeros(K, M, device=self.device)

        if daily_nutrition is not None and getattr(self.config, 'fresh_recipe_cap_enabled', True):
            day = slot // 3
            meal_idx = slot % 3
            daily_cal_target = self.weekly_calories / 7.0

            # Get what we've eaten today so far
            today_so_far = daily_nutrition[:, day, 0]  # [K]

            configured_ceiling_pct = getattr(
                self.config,
                'fresh_recipe_daily_ceiling_pct',
                1.25,
            )
            family_size = self.attendance.household.size
            if family_size >= 3:
                effective_ceiling_pct = configured_ceiling_pct
            else:
                day_ceiling = 0.95 + (day * 0.02)
                meal_adj = [1.02, 1.00, 0.98][meal_idx]
                effective_ceiling_pct = min(configured_ceiling_pct, day_ceiling * meal_adj)

            daily_ceiling = daily_cal_target * effective_ceiling_pct  # [scalar]

            # How much room is left today?
            remaining_headroom = (daily_ceiling - today_so_far).clamp(min=0)  # [K]

            # Recipes that exceed remaining headroom get penalized
            excess_over_cap = (cal_contrib - remaining_headroom.view(K, 1)).clamp(min=0)  # [K, M]

            # Apply heavy penalty for recipes exceeding cap
            cap_penalty_rate = getattr(self.config, 'fresh_recipe_cap_penalty', 1000.0)
            fresh_cap_penalty = (excess_over_cap > 0).float() * cap_penalty_rate  # [K, M] - binary penalty

            # TRACE: Fresh recipe cap
            if self.verbose and slot == 0:
                k = 0
                num_capped = (excess_over_cap[k] > 0).sum().item()
                print(f"\n    [FRESH CAP TRACE slot={slot}]")
                print(f"      meal_idx: {meal_idx}")
                print(f"      effective_ceiling_pct: {effective_ceiling_pct:.1%}")
                print(f"      daily_cal_target: {daily_cal_target:.0f}")
                print(f"      daily_ceiling: {daily_ceiling:.0f}")
                print(f"      today_so_far[{k}]: {today_so_far[k].item():.0f}")
                print(f"      remaining_headroom[{k}]: {remaining_headroom[k].item():.0f}")
                print(f"      recipes capped: {num_capped}/{M}")

        # === VERDICT PENALTY (soft filter for non-meal recipes) ===
        verdict_penalty = torch.zeros(K, M, device=self.device)
        if hasattr(self.db, 'gpu_verdict_penalty'):
            verdict_penalty = self.db.gpu_verdict_penalty[top_m_db_idx.long()]  # [K, M]

        combined_scores = top_m_costs + nutrition_score + macro_penalty + daily_penalty + fresh_cap_penalty + verdict_penalty - density_bonus

        # When a frontier is fully covered by leftovers, every main candidate is
        # the same real action: cook nothing and eat the selected leftover. If
        # we let all M placeholders compete, the global top-K can fill with
        # duplicate no-op branches from one parent and lose actual alternatives.
        if self.attendance.household.size >= 3 and no_cook_mask.any() and M > 1:
            combined_scores = combined_scores.clone()
            combined_scores[no_cook_mask, 1:] = combined_scores[no_cook_mask, 1:] + 1_000_000.0

        # === BEAM TRACE diagnostic ===
        # Set HESTIA_TRACE_SLOT=N + HESTIA_TRACE_PATH=<path> to dump per-(parent,
        # candidate) score breakdown at slot N to a CSV. Lets you see WHY a
        # specific recipe won/lost a slot. Found the day-ramp bug in 10 minutes.
        # See api/docs/PLANNER_PHASE2_PLAN.md for usage.
        import os as _os_trace
        _trace_slot = _os_trace.environ.get('HESTIA_TRACE_SLOT')
        if _trace_slot is not None and int(_trace_slot) == slot:
            if daily_nutrition is not None:
                _day = slot // 3
                print(f"  [TRACE] slot {slot} (day {_day}): "
                      f"daily_nutrition[parent=0, day={_day}, cal] = {daily_nutrition[0, _day, 0].item():.0f}")
                print(f"  [TRACE]   weekly_calories={self.weekly_calories:.0f}, "
                      f"daily_target={self.weekly_calories/7:.0f}")
            import csv as _csv_trace
            _trace_path = _os_trace.environ.get('HESTIA_TRACE_PATH', '/tmp/beam_trace.csv')
            with open(_trace_path, 'w', newline='') as _tf:
                _w = _csv_trace.writer(_tf)
                _w.writerow(['parent_idx', 'cand_idx', 'recipe_id', 'recipe_name',
                             'total_cal', 'cal_per_srv', 'cal_contrib', 'cal_under', 'cal_over',
                             'top_m_cost', 'nutrition_score', 'macro_penalty',
                             'daily_penalty', 'fresh_cap_penalty', 'verdict_penalty',
                             'density_bonus', 'combined_score'])
                _K_t, _M_t = top_m_db_idx.shape
                _scan_K = min(_K_t, 5)
                _scan_M = min(_M_t, 30)
                for _k in range(_scan_K):
                    for _m in range(_scan_M):
                        _db_idx = int(top_m_db_idx[_k, _m].item())
                        _rid = int(self.db.recipe_ids[_db_idx].item())
                        _name = self.db.names[_db_idx] if hasattr(self.db, 'names') else ''
                        _tc = float(self.db.total_calories[_db_idx].item())
                        _cps = float(self.db.nutrition[_db_idx, 0].item())
                        _w.writerow([_k, _m, _rid, _name,
                                     f"{_tc:.0f}", f"{_cps:.0f}",
                                     f"{cal_contrib[_k,_m].item():.0f}",
                                     f"{cal_under[_k,_m].item():.1f}",
                                     f"{cal_over[_k,_m].item():.1f}",
                                     f"{top_m_costs[_k,_m].item():.3f}",
                                     f"{nutrition_score[_k,_m].item():.3f}",
                                     f"{macro_penalty[_k,_m].item():.3f}",
                                     f"{daily_penalty[_k,_m].item():.3f}",
                                     f"{fresh_cap_penalty[_k,_m].item():.3f}",
                                     f"{verdict_penalty[_k,_m].item():.3f}",
                                     f"{density_bonus[_k,_m].item():.3f}",
                                     f"{combined_scores[_k,_m].item():.3f}"])
            print(f"  [TRACE] slot {slot}: dumped {_scan_K * _scan_M} rows to {_trace_path}")

        return top_m_db_idx, top_m_costs, combined_scores

    def _leftover_calorie_supplement_servings(
        self,
        *,
        slot: int,
        current_calories_after_leftovers: torch.Tensor,
        slot_servings: float,
        full_leftover_mask: torch.Tensor,
    ) -> torch.Tensor:
        """Extra fresh servings needed when leftovers cover servings but not calories."""
        if not getattr(self.config, 'enable_leftover_calorie_supplement', True):
            return torch.zeros_like(current_calories_after_leftovers)

        if slot + 1 < NUM_SLOTS:
            future_nominal_cal = self.cal_target_per_slot[slot + 1:].sum()
        else:
            future_nominal_cal = torch.tensor(0.0, device=self.device)

        floor_pct = getattr(
            self.config,
            'leftover_supplement_floor_pct',
            getattr(self.config, 'calorie_floor_pct', 0.95),
        )
        weekly_floor = self.weekly_calories * floor_pct
        floor_gap = (weekly_floor - (current_calories_after_leftovers + future_nominal_cal)).clamp(min=0)

        min_gap = getattr(self.config, 'leftover_supplement_min_gap_cal', 150.0)
        main_share = float(getattr(self.config, 'main_side_ratio', 0.7))
        main_cal_per_serving = (
            float(self.cal_target_per_slot[slot].item())
            / max(float(slot_servings), 1.0)
            * main_share
        )
        extra_servings = floor_gap / max(main_cal_per_serving, 1.0)
        max_extra = getattr(self.config, 'leftover_supplement_max_extra_servings', 1.0)
        extra_servings = extra_servings.clamp(max=max_extra)
        extra_servings = torch.where(
            (floor_gap >= min_gap) & full_leftover_mask,
            extra_servings,
            torch.zeros_like(extra_servings),
        )
        return extra_servings

    def _leftover_calorie_headroom(
        self,
        *,
        slot: int,
        current_day_cal: torch.Tensor,
        slot_start_day_cal: torch.Tensor,
        daily_ceiling: float,
        urgent: bool = False,
    ) -> torch.Tensor:
        """Return calorie headroom constrained by both the current meal and day."""
        if urgent:
            slot_ceiling_pct = getattr(self.config, 'urgent_leftover_slot_ceiling_pct', 1.10)
        else:
            slot_ceiling_pct = getattr(self.config, 'leftover_slot_ceiling_pct', 1.10)

        slot_ceiling = float(self.cal_target_per_slot[slot].item()) * slot_ceiling_pct
        slot_consumed = (current_day_cal - slot_start_day_cal).clamp(min=0)
        slot_headroom = (slot_ceiling - slot_consumed).clamp(min=0)
        daily_headroom = (daily_ceiling - current_day_cal).clamp(min=0)
        return torch.minimum(slot_headroom, daily_headroom)

    def _find_leftovers(
        self,
        leftovers: torch.Tensor,  # [K, L, 7]
        meal_type: int,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Find available leftover servings per frontier.

        Prioritizes fresh items (lowest TTL first), then frozen items.
        Returns total available servings and index of best leftover to consume.
        """
        K = leftovers.shape[0]

        recipe_ids = leftovers[:, :, 0]
        servings = leftovers[:, :, 1]
        ttl = leftovers[:, :, 2]
        meal_types = leftovers[:, :, 5]
        is_frozen = leftovers[:, :, 6] > 0  # [K, L] bool

        # Meal compatibility.
        # Breakfast: breakfast items only
        # Lunch/dinner: either lunch or dinner leftovers are valid.
        if meal_type == 0:  # breakfast
            compatible = (meal_types == 0)
        elif meal_type == 1:  # lunch
            compatible = (meal_types == 1) | (meal_types == 2)  # lunch OR dinner items
        else:  # dinner
            compatible = (meal_types == 1) | (meal_types == 2)

        valid = (recipe_ids > 0) & (servings > 0) & compatible

        # Separate fresh and frozen
        valid_fresh = valid & ~is_frozen
        valid_frozen = valid & is_frozen

        # Fresh servings and frozen servings
        fresh_servings = torch.where(valid_fresh, servings, torch.zeros_like(servings))
        frozen_servings = torch.where(valid_frozen, servings, torch.zeros_like(servings))

        # Total available
        available = fresh_servings.sum(dim=1) + frozen_servings.sum(dim=1)  # [K]

        fresh_priority = torch.where(valid_fresh, 100.0 - ttl, torch.full_like(ttl, -1000.0))
        frozen_priority = torch.where(valid_frozen, 50.0 - ttl, torch.full_like(ttl, -1000.0))

        # Combined priority: use maximum to pick best from either category
        # (Previously used torch.where which ignored frozen when fresh existed)
        priority = torch.maximum(fresh_priority, frozen_priority)

        # Get best index per frontier
        _, best_idx = priority.max(dim=1)

        return available, best_idx

    def _find_side_leftovers(
        self,
        leftovers: torch.Tensor,  # [K, L, LEFTOVER_FIELDS]
        meal_type: int,
        template_id: int,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Find available SIDE leftovers that match a specific template.

        For strict template matching: side leftovers can only be consumed
        when cooking a meal with the same template they came from.

        Args:
            leftovers: [K, L, LEFTOVER_FIELDS] tensor
            meal_type: 0=breakfast, 1=lunch, 2=dinner
            template_id: Template ID to match (from main dish)

        Returns:
            available: [K] total available servings (sides matching template)
            best_idx: [K] index of best side leftover to consume
        """
        K = leftovers.shape[0]

        recipe_ids = leftovers[:, :, 0]
        servings = leftovers[:, :, 1]
        ttl = leftovers[:, :, 2]
        meal_types = leftovers[:, :, 5]
        is_frozen = leftovers[:, :, 6] > 0
        dish_types = leftovers[:, :, 7]   # 0=uninitialized/any, 1=main, 2=side
        template_ids = leftovers[:, :, 8]  # template_id

        # Meal compatibility (same rules)
        if meal_type == 0:  # breakfast
            meal_compatible = (meal_types == 0)
        elif meal_type == 1:  # lunch
            meal_compatible = (meal_types == 1) | (meal_types == 2)
        else:  # dinner
            meal_compatible = (meal_types == 1) | (meal_types == 2)

        # Strict template matching for sides
        # Only match sides (dish_type=2) from the same template
        # dish_type: 0=uninitialized/any, 1=main, 2=side
        is_side = (dish_types == 2) | (dish_types == 0)  # Include legacy/uninitialized
        template_match = (template_ids == template_id)

        valid = (recipe_ids > 0) & (servings > 0) & meal_compatible & is_side & template_match

        # Separate fresh and frozen
        valid_fresh = valid & ~is_frozen
        valid_frozen = valid & is_frozen

        fresh_servings = torch.where(valid_fresh, servings, torch.zeros_like(servings))
        frozen_servings = torch.where(valid_frozen, servings, torch.zeros_like(servings))

        available = fresh_servings.sum(dim=1) + frozen_servings.sum(dim=1)  # [K]

        # Priority (same as _find_leftovers)
        fresh_priority = torch.where(valid_fresh, 100.0 - ttl, torch.full_like(ttl, -1000.0))
        frozen_priority = torch.where(valid_frozen, 50.0 - ttl, torch.full_like(ttl, -1000.0))
        priority = torch.maximum(fresh_priority, frozen_priority)

        _, best_idx = priority.max(dim=1)

        return available, best_idx

    def _decay_leftovers_with_freeze(
        self,
        leftovers: torch.Tensor,  # [K, L, LEFTOVER_FIELDS]
        reserved_frozen_kg: Optional[torch.Tensor] = None,  # [K] pantry kg already using freezer capacity
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Decay TTL for all leftovers, auto-freeze items about to expire.

        Called at end of each day (every 3 slots).

        Logic:
        1. Decrement TTL for all items
        2. Fresh items with TTL=0: freeze them (if auto_freeze enabled and capacity allows)
        3. Clear expired items (TTL < 0), track wasted servings

        Returns:
            Tuple of (leftovers tensor, waste_servings tensor [K])
        """
        K = leftovers.shape[0]
        if reserved_frozen_kg is None:
            reserved_frozen_kg = torch.zeros(K, device=leftovers.device)
        else:
            reserved_frozen_kg = reserved_frozen_kg.to(device=leftovers.device, dtype=leftovers.dtype)

        # Identify fresh vs frozen items
        is_frozen = leftovers[:, :, 6] > 0  # [K, L]
        has_item = leftovers[:, :, 0] > 0   # [K, L] - has valid recipe_id

        # Decrement TTL for all items
        leftovers[:, :, 2] -= 1

        # Find fresh items about to expire (TTL just hit 0)
        about_to_expire = ~is_frozen & has_item & (leftovers[:, :, 2] == 0)

        # Auto-freeze logic
        if self.auto_freeze and about_to_expire.any():
            if self.freezer_capacity_kg > 0:
                frozen_leftover_kg = torch.where(
                    is_frozen,
                    leftovers[:, :, 9],
                    torch.zeros_like(leftovers[:, :, 9]),
                ).sum(dim=1) / 1000.0  # [K]
                freeze_candidate_kg = torch.where(
                    about_to_expire,
                    leftovers[:, :, 9],
                    torch.zeros_like(leftovers[:, :, 9]),
                ) / 1000.0  # [K, L]
                capacity_remaining_kg = (
                    self.freezer_capacity_kg - reserved_frozen_kg - frozen_leftover_kg
                ).clamp(min=0).unsqueeze(1)
                cumulative_candidate_kg = freeze_candidate_kg.cumsum(dim=1)
                do_freeze = about_to_expire & (cumulative_candidate_kg <= capacity_remaining_kg)
            else:
                # Unlimited capacity
                do_freeze = about_to_expire

            # Apply freezing: set is_frozen=1, reset TTL to freezer_ttl
            leftovers[:, :, 6] = torch.where(do_freeze, torch.ones_like(leftovers[:, :, 6]), leftovers[:, :, 6])
            leftovers[:, :, 2] = torch.where(do_freeze, torch.full_like(leftovers[:, :, 2], float(self.freezer_ttl)), leftovers[:, :, 2])

        # Clear expired items (TTL < 0) and track waste
        expired = leftovers[:, :, 2] < 0
        waste_servings = (leftovers[:, :, 1] * expired.float()).sum(dim=1)  # [K] - servings that expired
        leftovers[:, :, 0] = torch.where(expired, torch.zeros_like(leftovers[:, :, 0]), leftovers[:, :, 0])
        leftovers[:, :, 1] = torch.where(expired, torch.zeros_like(leftovers[:, :, 1]), leftovers[:, :, 1])
        leftovers[:, :, 6] = torch.where(expired, torch.zeros_like(leftovers[:, :, 6]), leftovers[:, :, 6])
        leftovers[:, :, 9] = torch.where(expired, torch.zeros_like(leftovers[:, :, 9]), leftovers[:, :, 9])

        return leftovers, waste_servings

    def _inject_fruit_snacks(
        self,
        current_cal: float,
        target_cal: float,
        current_fruit_g: float,
    ) -> List[Dict]:
        """
        If calories are 85-95% of target, add fruit snacks to fill the gap.

        Returns list of snack OCCASIONS (not individual servings).
        Each full occasion = 1 snack per person in the household. Tiny floor
        gaps may use fractional servings instead of pushing calories above the
        configured snack ceiling.

        E.g., "1 Apple occasion" for family of 4 = 4 apples, 380 cal, $2.00
        """
        compliance = current_cal / target_cal if target_cal > 0 else 1.0

        # Only inject if we're in the configurable range (default 85-95%)
        if compliance >= self.config.snack_inject_ceiling or compliance < self.config.snack_inject_floor:
            return []

        target_fill_cal = target_cal * self.config.snack_inject_ceiling
        cal_gap = target_fill_cal - current_cal
        max_add = min(
            cal_gap,
            target_cal * self.config.calorie_ceiling_pct - current_cal,
        )  # Don't exceed snack or weekly calorie ceiling
        if max_add <= 0:
            return []

        # Get family size for scaling
        num_people = self.attendance.household.size

        snacks_to_add = []
        remaining_gap = min(cal_gap, max_add)

        # Rotate through snacks for variety (instead of always picking OJ first)
        # Use rotation counter to start from different snack each week
        num_snack_types = len(FRUIT_SNACKS)

        # Fill gap with rotating snacks
        attempts = 0
        max_attempts = 10  # Prevent infinite loop
        while remaining_gap >= 10 and attempts < max_attempts:
            # Pick snack based on rotation counter
            snack_idx = self._snack_rotation_idx % num_snack_types
            snack = FRUIT_SNACKS[snack_idx]

            # Calories per occasion = per-person calories × family size
            cal_per_occasion = snack['calories'] * num_people

            if cal_per_occasion > 0:
                serving_fraction = min(1.0, remaining_gap / cal_per_occasion)
            else:
                serving_fraction = 0.0

            if serving_fraction > 0:
                # Create occasion with scaled values
                occasion = {
                    'name': snack['name'],
                    'servings': num_people * serving_fraction,
                    'calories': cal_per_occasion * serving_fraction,
                    'fruit_g': snack['fruit_g'] * num_people * serving_fraction,
                    'cost': snack['cost'] * num_people * serving_fraction,
                }
                snacks_to_add.append(occasion)
                remaining_gap -= occasion['calories']
                self._snack_rotation_idx += 1  # Move to next snack type
            else:
                # Try next snack type if this one is too big
                self._snack_rotation_idx += 1
            attempts += 1

        return snacks_to_add

    def start_session(
        self,
        *,
        initial_pantry: Optional[torch.Tensor] = None,
        historical_banned_ids: Optional[List[int]] = None,
        initial_leftovers: Optional[torch.Tensor] = None,
        week_number: int = 0,
        initial_pantry_ttl: Optional[torch.Tensor] = None,
        initial_pantry_frozen: Optional[torch.Tensor] = None,
    ):
        from hestia.planning_session import SparseCascadePlanningSession

        return SparseCascadePlanningSession(
            self,
            initial_pantry=initial_pantry,
            historical_banned_ids=historical_banned_ids,
            initial_leftovers=initial_leftovers,
            week_number=week_number,
            initial_pantry_ttl=initial_pantry_ttl,
            initial_pantry_frozen=initial_pantry_frozen,
        )

    def plan(
        self,
        initial_pantry: Optional[torch.Tensor] = None,
    ) -> Dict:
        """Run a fresh one-week plan. Use start_session() for continuation weeks."""
        return self.start_session(initial_pantry=initial_pantry).plan_next_week()

    def _plan_with_carryover(
        self,
        initial_pantry: Optional[torch.Tensor] = None,
        historical_banned_ids: Optional[list] = None,  # MUST be list to preserve chronological order!
        initial_leftovers: Optional[torch.Tensor] = None,
        week_number: int = 0,  # Used for alternating shadow pricing mode
        initial_pantry_ttl: Optional[torch.Tensor] = None,
        initial_pantry_frozen: Optional[torch.Tensor] = None,
    ) -> Dict:
        """
        Run sparse cascade planning.

        Memory profile:
        - Peak: ~900 MB during scoring (freed immediately after)
        - Sustained: ~500 KB cascade state
        """
        start_time = time.time()
        self._refresh_recipe_static_tensors()

        # Keep as list to preserve chronological order (critical for cooldown!)
        historical_banned = list(historical_banned_ids) if historical_banned_ids else []

        # Initialize state
        K = 1  # Start with 1 frontier, grows to self.K
        L = 128  # Leftover slots (doubled for single-person households)

        if initial_pantry is not None:
            pantries = initial_pantry.unsqueeze(0).clone()
        else:
            pantries = torch.zeros(K, self.num_ingredients, device=self.device)

        # Pantry TTL and frozen status (for perishability tracking)
        # If carried over from previous week, use that state; otherwise fresh shelf life
        if initial_pantry_ttl is not None:
            # Carry over TTL from previous week - only for items actually in pantry
            pantry_ttl = initial_pantry_ttl.unsqueeze(0).clone()  # [1, I] -> [K, I]
            # For NEW items (in pantry but TTL was never set), use fresh shelf life.
            # TTL=-1 means "no data" (sentinel). TTL=0 means "expiring today" - do NOT reset.
            fresh_ttl = self.perishability.shelf_life_tensor
            has_pantry = (pantries[0] > 0)
            has_ttl = (pantry_ttl[0] >= 0)  # 0 is valid (about to expire), -1 is sentinel for "no TTL"
            needs_fresh = has_pantry & ~has_ttl
            pantry_ttl[0, needs_fresh] = fresh_ttl[needs_fresh]
        else:
            pantry_ttl = self.perishability.shelf_life_tensor.unsqueeze(0).expand(K, -1).clone()  # [K, I]

        if initial_pantry_frozen is not None:
            pantry_frozen = initial_pantry_frozen.unsqueeze(0).clone()  # [1, I] -> [K, I]
        else:
            pantry_frozen = torch.zeros(K, self.num_ingredients, dtype=torch.bool, device=self.device)  # [K, I]

        nutrition = torch.zeros(K, 4, device=self.device)  # [cal, protein, carbs, fat]
        food_groups = torch.zeros(K, 2, device=self.device)  # [vegetables_g, fruits_g]
        cost = torch.zeros(K, device=self.device)
        objective_cost = torch.zeros(K, device=self.device)
        # Initialize leftovers: use previous week's state if provided, else start fresh
        if initial_leftovers is not None:
            # Expand single leftover state to K frontiers
            # Handle legacy leftover formats by zero-filling missing fields.
            if initial_leftovers.shape[-1] < LEFTOVER_FIELDS:
                old_expanded = initial_leftovers.unsqueeze(0).expand(K, -1, -1).clone()
                leftovers = torch.zeros(K, L, LEFTOVER_FIELDS, device=self.device)
                leftovers[:, :, :initial_leftovers.shape[-1]] = old_expanded
            else:
                leftovers = initial_leftovers.unsqueeze(0).expand(K, -1, -1).clone()
        else:
            # Fields: recipe_id, servings, ttl, cal, prot, meal_type, is_frozen, dish_type, template_id, grams
            leftovers = torch.zeros(K, L, LEFTOVER_FIELDS, device=self.device)

        used_ids = torch.zeros(K, COOLDOWN_LEN, dtype=torch.long, device=self.device)
        used_ptr = torch.zeros(K, dtype=torch.long, device=self.device)

        # Progressive protein quota: track count of each source selected so far
        protein_counts = torch.zeros(K, NUM_PROTEIN_SOURCES, dtype=torch.float32, device=self.device)

        # Load historical bans - take LAST COOLDOWN_LEN entries (most recent)
        # Note: Cooldown ring holds COOLDOWN_LEN entries (~6 weeks of recipes)
        # After 6 weeks, older recipes naturally exit cooldown and can be reused
        # CRITICAL: historical_banned_ids MUST be a list (not set) to preserve order!
        if historical_banned:
            # Take the LAST COOLDOWN_LEN entries (most recent recipes)
            hist_list = historical_banned[-COOLDOWN_LEN:]
            for i, rid in enumerate(hist_list):
                used_ids[0, i] = rid
            used_ptr[0] = len(hist_list)

        selections = [[]]  # Track selections per frontier

        # === COMPUTE EFFECTIVE SHADOW DIRECTIONS ===
        # Based on shadow_pricing_mode and week_number
        shadow_mode = getattr(self.config, 'shadow_pricing_mode', 'fixed')
        if shadow_mode == 'alternating':
            # Criss-cross pattern: flip directions every other week
            if week_number % 2 == 0:
                # Even weeks: leftover=ascending, fresh=descending
                self._effective_lo_direction = 'ascending'
                self._effective_fresh_direction = 'descending'
            else:
                # Odd weeks: leftover=descending, fresh=ascending
                self._effective_lo_direction = 'descending'
                self._effective_fresh_direction = 'ascending'
        else:
            # Fixed mode: use config values as-is
            self._effective_lo_direction = getattr(self.config, 'leftover_shadow_direction', 'ascending')
            self._effective_fresh_direction = getattr(self.config, 'fresh_shadow_direction', 'ascending')

        # Track waste and pantry flow for sustainability metrics
        # Track per-frontier to report only best path at end (fixes inflation bug)
        waste_per_frontier = torch.zeros(K, device=self.device)  # [K] - leftover waste per frontier
        pantry_spoilage = torch.zeros(K, device=self.device)  # [K] - pantry spoilage per frontier (kg)
        pantry_frozen_grams = torch.zeros(K, device=self.device)  # [K] - pantry items auto-frozen (grams)
        pantry_frozen_spoilage = torch.zeros(K, device=self.device)  # [K] - frozen items that expired (kg)
        pantry_fresh_spoilage = torch.zeros(K, device=self.device)   # [K] - fresh items that expired (kg)
        pantry_frozen_consumed = torch.zeros(K, device=self.device)  # [K] - grams consumed from frozen items
        pantry_fresh_consumed = torch.zeros(K, device=self.device)   # [K] - grams consumed from fresh items
        max_freezer_slots = torch.zeros(K, device=self.device)       # [K] - max freezer utilization observed
        urgent_ingredients_used = torch.zeros(K, device=self.device) # [K] - count of near-expiry items used
        acquired_grams = torch.zeros(K, device=self.device)  # [K] - grows with beam
        consumed_grams = torch.zeros(K, device=self.device)  # [K] - grows with beam
        # Per-ingredient purchase tracking: [K, num_ingredients] packages bought
        ingredient_packages_bought = torch.zeros(K, self.num_ingredients, device=self.device)
        ingredient_purchase_costs = torch.zeros(K, self.num_ingredients, device=self.device)
        ingredient_acquired_grams = torch.zeros(K, self.num_ingredients, device=self.device)
        ingredient_consumed_grams = torch.zeros(K, self.num_ingredients, device=self.device)
        ingredient_recipe_used_grams = torch.zeros(K, self.num_ingredients, device=self.device)
        ingredient_frozen_spoilage_grams = torch.zeros(K, self.num_ingredients, device=self.device)
        ingredient_fresh_spoilage_grams = torch.zeros(K, self.num_ingredients, device=self.device)
        leftover_consumed = torch.zeros(K, device=self.device)  # [K] - per-frontier leftover tracking

        # === SAME-DAY LEFTOVER DEDUP ===
        # Track recipe IDs consumed at each meal slot within a day [K, 3]
        # Used to penalize eating the same leftover at both lunch and dinner
        daily_consumed_recipe_ids = torch.zeros(K, 3, dtype=torch.long, device=self.device)

        # === PHASE 3: DAILY NUTRITION TRACKING ===
        # Track per-day nutrition to enable daily balance penalties
        # Shape: [K, 7, 4] - calories, protein, carbs, fat for each day
        daily_nutrition = torch.zeros(K, 7, 4, device=self.device)

        meal_types = ['breakfast', 'lunch', 'dinner']

        if self.verbose:
            print("\n" + "=" * 60, flush=True)
            print("SPARSE CASCADE PLANNING", flush=True)
            print("=" * 60, flush=True)

        for slot in range(NUM_SLOTS):
            day = slot // 3
            meal_idx = slot % 3
            meal_type = meal_types[meal_idx]

            # Reset same-day tracking at start of each day
            if meal_idx == 0:
                daily_consumed_recipe_ids = torch.zeros(
                    pantries.shape[0], 3, dtype=torch.long, device=self.device
                )

            if self.verbose and meal_idx == 0:
                K = pantries.shape[0]
                # Use GPU min/max, only transfer scalars (avoids full tensor CPU transfer)
                cost_min = cost.min().item()
                cost_max = cost.max().item()
                cal_max = nutrition[:, 0].max().item()
                progress = slot / NUM_SLOTS
                expected = self.weekly_calories * progress
                print(f"\nDay {day}: {K} frontiers, ${cost_min:.2f}-${cost_max:.2f}, "
                      f"cals {cal_max:.0f}/{expected:.0f}", flush=True)

            # Check leftovers (use per-slot servings for variable attendance)
            slot_servings = self.servings_per_slot[slot].item()

            # === ZERO ATTENDANCE: Skip slot (eating out) ===
            if slot_servings == 0:
                att = self.attendance.get_slot(slot)
                if self.verbose:
                    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                    meal_names = ['breakfast', 'lunch', 'dinner']
                    # Calculate calories consumed today so far
                    today_slots = range(day * 3, slot)
                    today_cal = sum(self.cal_target_per_slot[s].item() for s in today_slots)
                    daily_target = self.attendance.household.daily_calories()
                    remaining = max(0, daily_target - today_cal)
                    print(f"  Slot {slot} ({day_names[day]} {meal_names[meal_idx]}): SKIPPED - {att.note or 'Eating out'}")
                    print(f"    Today's home meals: {today_cal:.0f} cal | Aim for ~{remaining:.0f} cal when out")

                # Add empty selection for this slot
                for i in range(len(selections)):
                    selections[i].append((0, 0, "SKIPPED", att.note or "Eating out", 0.0))

                # Still decay leftovers at end of day
                if (slot + 1) % 3 == 0:
                    reserved_frozen_kg = (pantries * pantry_frozen.float()).sum(dim=1) / 1000.0
                    leftovers, waste = self._decay_leftovers_with_freeze(
                        leftovers,
                        reserved_frozen_kg=reserved_frozen_kg,
                    )
                    waste_per_frontier += waste  # [K] += [K] - track per frontier
                    objective_cost += waste * self.config.leftover_waste_penalty
                continue

            avail_servings, _ = self._find_leftovers(leftovers, meal_idx)
            servings_to_cook = (slot_servings - avail_servings).clamp(min=0)
            full_leftover = (avail_servings >= slot_servings)

            # === EXPECTED LEFTOVER CALORIES (for main scoring) ===
            # Calculate how many calories we expect to consume from leftovers
            # so main scoring can account for them in calorie pacing
            K_lo = leftovers.shape[0]
            lo_cal_per_srv = leftovers[:, :, 3]  # [K, L] calories per serving
            lo_servings = leftovers[:, :, 1]      # [K, L]
            lo_meal_types = leftovers[:, :, 5]    # [K, L]
            lo_is_frozen = leftovers[:, :, 6] > 0 # [K, L]

            # Same compatibility check as _find_leftovers
            if meal_idx == 0:  # breakfast
                lo_compatible = (lo_meal_types == 0)
            elif meal_idx == 1:  # lunch
                lo_compatible = (lo_meal_types == 1) | (lo_meal_types == 2)
            else:  # dinner
                lo_compatible = (lo_meal_types == 1) | (lo_meal_types == 2)

            lo_valid = (leftovers[:, :, 0] > 0) & (lo_servings > 0) & lo_compatible
            # Estimate: we'll consume up to slot_servings from available leftovers.
            # Cap globally, not per leftover slot, so scoring sees the same maximum
            # serving count as the actual greedy consumption loop.
            lo_servings_to_eat = torch.minimum(
                avail_servings,
                torch.full_like(avail_servings, slot_servings),
            )

            # Expected calories from leftovers (weighted average cal/srv × servings to eat)
            lo_total_cal = (lo_cal_per_srv * lo_servings * lo_valid.float()).sum(dim=1)  # [K]
            lo_total_srv = (lo_servings * lo_valid.float()).sum(dim=1).clamp(min=1)  # [K]
            lo_avg_cal_per_srv = lo_total_cal / lo_total_srv  # [K]
            expected_leftover_cal = lo_avg_cal_per_srv * lo_servings_to_eat  # [K]

            # CRITICAL FIX: Cap expected leftover calories at shadow pricing ceiling headroom
            # Without this, the scoring function sees inflated calories (assuming full leftover
            # consumption), picks lower-calorie mains, but the ceiling then restricts actual
            # consumption → systematic underfeed, especially for large households.
            if getattr(self.config, 'enable_separate_shadow_prices', False):
                daily_target_est = self.weekly_calories / 7.0
                if getattr(self.config, 'enable_coordinated_shadow_pricing', True):
                    lo_min_est = getattr(self.config, 'leftover_shadow_min', 0.80)
                    lo_max_est = getattr(self.config, 'leftover_shadow_max', 1.20)
                    lo_dir_est = self._effective_lo_direction
                    if lo_dir_est == 'ascending':
                        lo_mult_est = lo_min_est + (day / 6.0) * (lo_max_est - lo_min_est)
                    else:
                        lo_mult_est = lo_max_est - (day / 6.0) * (lo_max_est - lo_min_est)
                    day_ceiling_est = lo_mult_est
                else:
                    day_ceiling_est = 0.95 + (day * 0.02)
                meal_adj_est = [1.02, 1.00, 0.98][meal_idx]
                ceiling_cal = daily_target_est * day_ceiling_est * meal_adj_est
                current_day_cal_est = daily_nutrition[:, day, 0]  # Today's cal so far
                headroom = self._leftover_calorie_headroom(
                    slot=slot,
                    current_day_cal=current_day_cal_est,
                    slot_start_day_cal=current_day_cal_est,
                    daily_ceiling=ceiling_cal,
                    urgent=False,
                )
                expected_leftover_cal = torch.minimum(expected_leftover_cal, headroom)

            # Adjust nutrition for scoring (add expected leftover calories AND protein)
            # This helps main scoring know we're already getting these calories/protein
            # Without protein, the planner over-compensates in fresh recipes.
            nutrition_for_scoring = nutrition.clone()
            nutrition_for_scoring[:, 0] += expected_leftover_cal

            # Expected protein from leftovers (same averaging as calories)
            lo_prot_per_srv = leftovers[:, :, 4]  # [K, L] protein g per serving
            lo_total_prot = (lo_prot_per_srv * lo_servings * lo_valid.float()).sum(dim=1)  # [K]
            lo_avg_prot_per_srv = lo_total_prot / lo_total_srv  # [K] (lo_total_srv already clamped)
            expected_leftover_prot = lo_avg_prot_per_srv * lo_servings_to_eat  # [K]
            nutrition_for_scoring[:, 1] += expected_leftover_prot

            supplement_servings = self._leftover_calorie_supplement_servings(
                slot=slot,
                current_calories_after_leftovers=nutrition_for_scoring[:, 0],
                slot_servings=slot_servings,
                full_leftover_mask=full_leftover,
            )
            servings_to_cook = torch.maximum(servings_to_cook, supplement_servings)

            # Get recipe indices for this meal type
            main_indices = self.db.meal_main_indices[meal_type]

            # === VERDICT EXCLUSION (mains) — hard-block not_food/invalid ===
            if hasattr(self.db, 'gpu_verdict_excluded'):
                not_excluded = ~self.db.gpu_verdict_excluded[main_indices.long()]
                ex_count = (~not_excluded).sum().item()
                if not_excluded.sum().item() >= 10:
                    main_indices = main_indices[not_excluded]
                elif self.verbose:
                    print(f"    WARNING: verdict exclusion would leave <10 mains, skipping")

            # === SIDE-ONLY EXCLUSION (mains) — block side/dessert from main slot ===
            if hasattr(self.db, 'gpu_is_side_only'):
                is_main_eligible = ~self.db.gpu_is_side_only[main_indices.long()]
                if is_main_eligible.sum().item() >= 10:
                    main_indices = main_indices[is_main_eligible]
                elif self.verbose:
                    print(f"    WARNING: side-only exclusion would leave <10 mains, skipping")

            # === ALLERGEN FILTERING (mains) ===
            if self.allergen_safe_mask is not None:
                safe = self.allergen_safe_mask[main_indices.long()]
                safe_count = safe.sum().item()
                main_indices = main_indices[safe]  # HARD GATE - always enforce, never bypass
                if safe_count < 10 and self.verbose:
                    print(f"    ALLERGEN: Low safe pool ({safe_count} mains) but enforcing filter")

            # === EMBER SCORE FILTERING (mains) ===
            if self.ember_filter_mask is not None:
                passing = self.ember_filter_mask[main_indices.long()]
                passing_count = passing.sum().item()
                if passing_count >= 10:
                    main_indices = main_indices[passing]
                elif self.verbose:
                    print(f"    WARNING: Only {passing_count} ember-passing mains, using all candidates")

            # === AIP FILTER (mains) ===
            if self.aip_filter_mask is not None:
                passing = self.aip_filter_mask[main_indices.long()]
                passing_count = passing.sum().item()
                if passing_count >= 10:
                    main_indices = main_indices[passing]
                elif self.verbose:
                    print(f"    WARNING: Only {passing_count} AIP-passing mains, using all candidates")

            # === MEAL FITNESS FILTERING (hard — same threshold as ember/allergen) ===
            if hasattr(self.db, 'gpu_meal_ok'):
                meal_col = {'breakfast': 0, 'lunch': 1, 'dinner': 2}[meal_type]
                fit = self.db.gpu_meal_ok[main_indices.long(), meal_col]
                fit_count = fit.sum().item()
                if fit_count >= 10:
                    main_indices = main_indices[fit]
                elif self.verbose:
                    print(f"    Meal fitness: only {int(fit_count)} fit, using all {len(main_indices):,}")

            # === MIN-TOTAL-CAL HARD GATE (mains) ===
            # Recipe must be physically capable of delivering at least
            # min_main_total_cal_pct of the slot's calorie demand.
            # Without this, the planner can pick recipes whose total_calories
            # are smaller than slot_servings * target_cal_per_srv. Such recipes
            # cap cook_stc at the recipe's natural servings (line ~5075), so
            # the slot is short by construction. Pantry-driven cost discounts
            # then beat the saturated calorie penalty and tiny recipes win.
            # Households 4-6 are the worst hit because the deficit isn't large
            # enough to overcome cost discounts via the soft penalty.
            min_main_total_cal_pct = float(getattr(self.config, 'min_main_total_cal_pct', 0.5))
            if min_main_total_cal_pct > 0 and hasattr(self.db, 'total_calories'):
                # Use the household-aware slot total target (cal_target_per_slot
                # is built from PersonProfile.meal_calories per attendee — it IS
                # the actual cal demand for this slot).
                #
                # Two thresholds — one_dish recipes are the entire meal (no side
                # is cooked), so they must deliver the FULL slot calorie target.
                # Non-one-dish mains cover only main_share; sides cover the rest.
                slot_total = float(self.cal_target_per_slot[slot].item())
                main_share = float(getattr(self.config, 'main_side_ratio', 0.7))
                cand_total_cal = self.db.total_calories[main_indices.long()].float()
                cand_is_one_dish = self.db.gpu_recipe_is_one_dish[main_indices.long()]
                # Per-candidate threshold: one_dish needs full slot, others need main share
                threshold_one_dish = slot_total * min_main_total_cal_pct
                threshold_partner  = slot_total * main_share * min_main_total_cal_pct
                threshold_per = torch.where(
                    cand_is_one_dish,
                    torch.tensor(threshold_one_dish, device=self.device),
                    torch.tensor(threshold_partner, device=self.device),
                )
                cal_ok = cand_total_cal >= threshold_per
                cal_ok_count = int(cal_ok.sum().item())
                if cal_ok_count >= 10:
                    if self.verbose:
                        dropped = int((~cal_ok).sum().item())
                        dropped_od = int(((~cal_ok) & cand_is_one_dish).sum().item())
                        dropped_partner = dropped - dropped_od
                        print(f"    min-total-cal gate: dropped {dropped} mains "
                              f"({dropped_od} one_dish < {threshold_one_dish:.0f} cal, "
                              f"{dropped_partner} partner-style < {threshold_partner:.0f} cal)")
                    main_indices = main_indices[cal_ok]
                elif self.verbose:
                    print(f"    min-total-cal gate would leave {cal_ok_count} mains, skipping")

            if self.verbose:
                print(f"  Slot {slot} ({meal_type}): two-pass scoring {len(main_indices):,} mains...", end=" ", flush=True)

            # === PHASE 1: TWO-PASS SCORING (cost filter → shadow price scoring) ===
            top_m = min(500, len(main_indices))  # Cost filter size (increased for variety)
            top_m_db_idx, top_m_costs, combined_scores = self._two_pass_score(
                recipe_indices=main_indices,
                pantries=pantries,
                pantry_frozen=pantry_frozen,
                current_nutrition=nutrition_for_scoring,  # Includes expected leftover calories
                current_food_groups=food_groups,
                slot=slot,
                used_ids=used_ids,
                servings_to_cook=servings_to_cook,
                top_m=top_m,
                protein_counts=protein_counts,
                leftovers=leftovers,  # For template match bonus
                pantry_ttl=pantry_ttl,  # For urgency bonus
                daily_nutrition=daily_nutrition,  # Phase 3: daily balance tracking
            )  # Returns [K, M] scores with shadow price penalties

            # Select top-K from filtered candidates (global selection)
            M = top_m_db_idx.shape[1]
            cumulative_scores = combined_scores + objective_cost.view(-1, 1)
            flat_scores = cumulative_scores.flatten()

            # Add noise for multistart diversity (score_noise > 0 enables different results per run)
            if self.score_noise > 0:
                noise = torch.randn_like(flat_scores) * self.score_noise
                flat_scores = flat_scores + noise

            dedupe_enabled = getattr(self.config, 'enable_beam_signature_dedupe', True)
            oversample_mult = int(getattr(self.config, 'beam_signature_dedupe_oversample_mult', 4)) if dedupe_enabled else 1
            oversample_mult = max(1, oversample_mult)
            num_to_select = min(self.K * oversample_mult, flat_scores.shape[0])
            _, top_flat_idx = self._stable_topk(-flat_scores, k=num_to_select, largest=True, dim=0)  # best = lowest score

            parent_idx = top_flat_idx // M
            filtered_choice_idx = top_flat_idx % M

            # Map through filtered indices to get database indices
            # top_m_db_idx[parent_idx, filtered_choice_idx] gives the actual db index
            selected_main_db_idx = top_m_db_idx[parent_idx, filtered_choice_idx]

            # FREE scoring tensors
            del combined_scores, cumulative_scores, flat_scores, top_flat_idx
            del top_m_db_idx, top_m_costs

            # Count unique cooldown entries for debug
            active_cooldown = (used_ids > 0).sum(dim=1).float().mean().item()

            if self.verbose:
                print(f"selected {num_to_select} from top-{M} (cooldown: {active_cooldown:.0f} recipes)")

            # === Expand state for new frontiers ===
            new_K = num_to_select
            new_pantries = pantries[parent_idx].clone()
            new_nutrition = nutrition[parent_idx].clone()
            new_food_groups = food_groups[parent_idx].clone()  # Track vegetables_g, fruits_g
            new_cost = cost[parent_idx].clone()
            new_objective_cost = objective_cost[parent_idx].clone()
            new_leftovers = leftovers[parent_idx].clone()
            new_used_ids = used_ids[parent_idx].clone()
            new_used_ptr = used_ptr[parent_idx].clone()
            new_protein_counts = protein_counts[parent_idx].clone()
            new_acquired_grams = acquired_grams[parent_idx].clone()  # Pantry flow tracking
            new_consumed_grams = consumed_grams[parent_idx].clone()  # Pantry flow tracking
            new_ingredient_packages = ingredient_packages_bought[parent_idx].clone()  # Per-ingredient purchase tracking
            new_ingredient_purchase_costs = ingredient_purchase_costs[parent_idx].clone()
            new_ingredient_acquired_grams = ingredient_acquired_grams[parent_idx].clone()
            new_ingredient_consumed_grams = ingredient_consumed_grams[parent_idx].clone()
            new_ingredient_recipe_used_grams = ingredient_recipe_used_grams[parent_idx].clone()
            new_ingredient_frozen_spoilage_grams = ingredient_frozen_spoilage_grams[parent_idx].clone()
            new_ingredient_fresh_spoilage_grams = ingredient_fresh_spoilage_grams[parent_idx].clone()
            new_leftover_consumed = leftover_consumed[parent_idx].clone()  # Leftover tracking
            new_waste_per_frontier = waste_per_frontier[parent_idx].clone()  # Leftover waste tracking
            new_pantry_spoilage = pantry_spoilage[parent_idx].clone()  # Pantry spoilage tracking
            new_pantry_frozen_grams = pantry_frozen_grams[parent_idx].clone()  # Pantry frozen grams tracking
            new_pantry_frozen_spoilage = pantry_frozen_spoilage[parent_idx].clone()  # Frozen spoilage tracking
            new_pantry_fresh_spoilage = pantry_fresh_spoilage[parent_idx].clone()  # Fresh spoilage tracking
            new_pantry_frozen_consumed = pantry_frozen_consumed[parent_idx].clone()  # Frozen consumption tracking
            new_pantry_fresh_consumed = pantry_fresh_consumed[parent_idx].clone()  # Fresh consumption tracking
            new_max_freezer_slots = max_freezer_slots[parent_idx].clone()  # Freezer utilization tracking
            new_urgent_ingredients_used = urgent_ingredients_used[parent_idx].clone()  # Urgency tracking
            new_pantry_ttl = pantry_ttl[parent_idx].clone()  # Pantry TTL tracking
            new_pantry_frozen = pantry_frozen[parent_idx].clone()  # Pantry frozen status
            new_daily_nutrition = daily_nutrition[parent_idx].clone()  # Phase 3: daily nutrition tracking
            new_daily_consumed = daily_consumed_recipe_ids[parent_idx].clone()  # Same-day dedup tracking

            # Track selected mains and their templates (OPTIMIZED: batch index extraction)
            selected_main_ids = self.db.recipe_ids[selected_main_db_idx]  # [new_K]
            main_db_idx_list = selected_main_db_idx.tolist()
            main_names = [self.db.names[idx] for idx in main_db_idx_list]

            # Record cooked main recipe for same-day leftover dedup
            new_daily_consumed[:, meal_idx] = selected_main_ids

            # Check which are one-dish using GPU tensor lookup (O(1), no Python loop)
            is_one_dish = self.db.gpu_recipe_is_one_dish[selected_main_db_idx.long()]  # [new_K]

            # Get template IDs - MUST match current meal type!
            # gpu_recipe_to_template only stores PRIMARY template, which may be wrong meal type
            # Fix: For each recipe, find a template that matches current meal_type
            primary_template_ids = self.db.gpu_recipe_to_template[selected_main_db_idx.long()].long()  # [new_K]

            # Get set of valid template IDs for current meal type
            valid_templates_for_meal = set()
            for t in self.db.templates[meal_type]:
                valid_templates_for_meal.add(t.template_id)

            # Check each recipe and fix template if needed
            template_ids = primary_template_ids.clone()
            fixed_count = 0
            for k, db_idx in enumerate(main_db_idx_list):
                primary_tid = primary_template_ids[k].item()
                if primary_tid not in valid_templates_for_meal:
                    # Primary template is wrong meal type - find alternative
                    all_tids = self.db.main_to_templates.get(db_idx, [])
                    for tid in all_tids:
                        if tid in valid_templates_for_meal:
                            template_ids[k] = tid
                            fixed_count += 1
                            if self.verbose:
                                print(f"      Fixed template for {self.db.names[db_idx][:30]}: {primary_tid} -> {tid}")
                            break
                    # If no match found, keep primary (shouldn't happen if recipe is valid for meal)
            if fixed_count > 0 and self.verbose:
                print(f"    Fixed {fixed_count} template assignments for {meal_type}")

            # === VECTORIZED MULTI-SLOT LEFTOVER CONSUMPTION ===
            # PERF FIX: Previous loop called _find_leftovers 8× per slot (67,200 calls/week!)
            # Now we compute priority ONCE and consume greedily from sorted slots
            K_lo, L = new_leftovers.shape[:2]

            # Extract all fields once
            lo_recipe_ids = new_leftovers[:, :, 0]  # [K, L]
            lo_servings = new_leftovers[:, :, 1]    # [K, L]
            lo_ttl = new_leftovers[:, :, 2]         # [K, L]
            lo_cal = new_leftovers[:, :, 3]         # [K, L]
            lo_prot = new_leftovers[:, :, 4]        # [K, L]
            lo_meal_types = new_leftovers[:, :, 5]  # [K, L]
            lo_is_frozen = new_leftovers[:, :, 6] > 0  # [K, L]
            lo_dish_types = new_leftovers[:, :, 7]  # [K, L] - 0=any/legacy, 1=main, 2=side
            lo_template_ids = new_leftovers[:, :, 8]  # [K, L] - template_id for matching

            # Meal compatibility (computed once, not in loop)
            if meal_idx == 0:  # breakfast
                compatible = (lo_meal_types == 0)
            elif meal_idx == 1:  # lunch
                compatible = (lo_meal_types == 1) | (lo_meal_types == 2)
            else:  # dinner
                compatible = (lo_meal_types == 1) | (lo_meal_types == 2)

            # CRITICAL: Main consumption should only use MAIN leftovers (dish_type=1 or 0=any/legacy)
            # Side dish leftovers (dish_type=2) should NOT satisfy main dish requirements
            is_main_or_any = (lo_dish_types == 1) | (lo_dish_types == 0)
            valid = (lo_recipe_ids > 0) & (lo_servings > 0) & compatible & is_main_or_any  # [K, L]

            fresh_priority = torch.where(valid & ~lo_is_frozen, 100.0 - lo_ttl, torch.full_like(lo_ttl, -1000.0))
            frozen_priority = torch.where(valid & lo_is_frozen, 50.0 - lo_ttl, torch.full_like(lo_ttl, -1000.0))
            priority = torch.maximum(fresh_priority, frozen_priority)  # [K, L]

            # === FROZEN EXPIRY URGENCY BOOST ===
            # Normal rotation starts early; inside the urgency window, frozen
            # leftovers must outrank fresh leftovers so they are eaten before
            # the freezer TTL runs out.
            #
            # IMPORTANT: Urgency window scales by family size!
            # - Single person consumes ~9 srv/week -> needs 14+ day warning for 20-srv item
            # - Family of 4 consumes ~60 srv/week -> needs only 3-day warning
            # Formula: urgency_days = max(3, 7 * (1 + 2/family_size))
            family_size = self.attendance.household.size
            urgency_days = max(3, int(7 * (1 + 2.0 / max(1, family_size))))  # hs1:21, hs4:11, hs8:9
            frozen_near_expiry = valid & lo_is_frozen & (lo_ttl <= urgency_days)
            expiry_urgency_boost = torch.where(
                frozen_near_expiry,
                120.0 * (1.0 - lo_ttl / urgency_days).clamp(min=0),  # +120 at TTL=0, +0 at urgency_days
                torch.zeros_like(lo_ttl)
            )
            priority = priority + expiry_urgency_boost
            # Once frozen leftovers enter the urgency window, force them above
            # ordinary fresh leftovers so freezer inventory gets drained before
            # it expires.
            priority = torch.where(
                frozen_near_expiry,
                torch.maximum(priority, 125.0 - lo_ttl),
                priority,
            )

            # === SERVING SIZE URGENCY BOOST ===
            # High-serving items represent more potential waste, so prioritize consuming them
            # Boost up to +15 for items with 20+ servings
            serving_boost = (lo_servings.clamp(max=20) / 20) * 15.0
            priority = priority + torch.where(valid, serving_boost, torch.zeros_like(serving_boost))

            # === TEMPLATE MATCH PRIORITY BOOST (OPTIMIZED) ===
            # Prefer mains that match existing SIDE leftovers, so we can consume sides too
            # This prevents side leftovers from expiring due to template mismatch
            side_leftover_mask = (lo_dish_types == 2) & (lo_servings > 0)  # [K, L] - valid side leftovers
            if side_leftover_mask.any():
                # Get unique side templates per frontier (flatten to set-like operation)
                side_templates = torch.where(side_leftover_mask, lo_template_ids, torch.zeros_like(lo_template_ids))
                main_templates = torch.where(valid, lo_template_ids, torch.zeros_like(lo_template_ids))

                # Efficient: check if main template exists in side templates (per frontier)
                # Use scatter to mark which templates have sides
                max_template = int(max(side_templates.max().item(), main_templates.max().item())) + 1
                if max_template > 0 and max_template < 500:  # Sanity check (increased from 200)
                    side_template_exists = torch.zeros(new_K, max_template, device=self.device)
                    side_template_exists.scatter_(1, side_templates.long().clamp(min=0), 1.0)

                    # Check if each main's template has a matching side
                    main_template_idx = main_templates.long().clamp(min=0, max=max_template-1)
                    has_matching_side = side_template_exists.gather(1, main_template_idx)  # [K, L]

                    # Boost priority for mains with matching sides (+30 = higher than fresh/frozen gap)
                    TEMPLATE_MATCH_PRIORITY_BOOST = 30.0
                    priority = priority + has_matching_side * TEMPLATE_MATCH_PRIORITY_BOOST

            # === SAME-DAY LEFTOVER DEDUP ===
            # Penalize leftovers whose recipe_id was already consumed earlier today
            # This prevents the same dish appearing at both lunch and dinner
            if meal_idx > 0:  # lunch or dinner — check previous meals today
                for prev_meal in range(meal_idx):
                    prev_ids = new_daily_consumed[:new_K, prev_meal].unsqueeze(1)  # [K, 1]
                    same_recipe = (lo_recipe_ids[:new_K] == prev_ids) & (prev_ids > 0)  # [K, L]
                    priority = priority - same_recipe.float() * 200.0  # Strong soft penalty

            # Sort slots by priority (descending) - highest priority first
            sorted_indices = self._stable_argsort(priority, descending=True, dim=1)  # [K, L]

            # Create indexing tensor for gather operations
            k_idx = torch.arange(new_K, device=self.device).unsqueeze(1).expand(new_K, L)  # [K, L]

            # Reorder by priority using advanced indexing
            sorted_servings = lo_servings[k_idx, sorted_indices]  # [K, L]
            sorted_cal = lo_cal[k_idx, sorted_indices]            # [K, L]
            sorted_prot = lo_prot[k_idx, sorted_indices]          # [K, L]
            sorted_valid = valid[k_idx, sorted_indices].float()   # [K, L]
            sorted_template_ids = lo_template_ids[k_idx, sorted_indices]  # [K, L] - for template matching
            sorted_recipe_ids = lo_recipe_ids[k_idx, sorted_indices]  # [K, L] - for display in selection tuple
            sorted_ttl = lo_ttl[k_idx, sorted_indices]
            sorted_is_frozen = lo_is_frozen[k_idx, sorted_indices]

            # Greedy consumption from highest-priority slots
            remaining = torch.full((new_K,), slot_servings, device=self.device)  # [K]
            total_lo_consumed = torch.zeros(new_K, device=self.device)
            # Use -1 as sentinel for "no template/recipe yet" (0 could be valid!)
            eaten_leftover_template = torch.full((new_K,), -1, dtype=torch.int64, device=self.device)
            eaten_leftover_recipe_id = torch.full((new_K,), -1, dtype=torch.long, device=self.device)
            slot_start_day_cal = new_daily_nutrition[:, day, 0].clone()
            # Track ALL consumed leftover sources: list of (recipe_id, servings) per frontier
            all_lo_sources = [[] for _ in range(new_K)]
            audit_events = [[] for _ in range(new_K)]

            # Small loop over slots (typically 1-3 needed), NOT calling _find_leftovers
            max_slots = min(L, 4)  # Usually 1-3 slots suffice
            # Daily calorie ceiling for leftover consumption (prevent overfeed)
            daily_target_for_mains = self.weekly_calories / 7.0

            # === SHADOW PRICING: DYNAMIC SOFT CEILING FOR LEFTOVER CONSUMPTION ===
            # When shadow pricing enabled, use tighter ceiling that scales with meal progress.
            # This ensures leftover consumption respects daily balance, not just TTL.
            #
            # CRITICAL FIX: Early days (Mon-Wed) were consuming ALL leftovers, leaving
            # late days (Sat-Sun) starving at 48-68%. Need tighter ceiling early in week.
            #
            # COORDINATED SHADOW PRICING: Day-of-week scaling coordinates leftover and fresh
            # cooking to pace consumption evenly across the week.
            if getattr(self.config, 'enable_separate_shadow_prices', False):
                family_size = self.attendance.household.size

                # === COORDINATED SHADOW PRICING: LEFTOVER CEILING ===
                # Get shadow multiplier based on direction config
                if getattr(self.config, 'enable_coordinated_shadow_pricing', True):
                    lo_min = getattr(self.config, 'leftover_shadow_min', 0.80)
                    lo_max = getattr(self.config, 'leftover_shadow_max', 1.20)
                    lo_direction = self._effective_lo_direction  # Use computed direction (supports alternating)

                    if lo_direction == 'ascending':
                        # LOW→HIGH: tight early, loose late (save leftovers for later)
                        lo_mult = lo_min + (day / 6.0) * (lo_max - lo_min)
                    else:
                        # HIGH→LOW: loose early, tight late (use leftovers now)
                        lo_mult = lo_max - (day / 6.0) * (lo_max - lo_min)

                    day_ceiling = 1.0 * lo_mult  # Apply shadow multiplier directly
                else:
                    # Legacy: hardcoded 95%-107% scaling
                    day_ceiling = 0.95 + (day * 0.02)

                # MEAL ADJUSTMENT: dinner slightly tighter (last chance to balance)
                meal_adj = [1.02, 1.00, 0.98][meal_idx]  # breakfast loose, dinner tight

                daily_ceiling_for_mains = daily_target_for_mains * day_ceiling * meal_adj
            else:
                daily_ceiling_for_mains = daily_target_for_mains * 1.50  # Fallback when day ceilings are disabled

            for l in range(max_slots):
                if remaining.sum() < 0.1:
                    break

                slot_avail = sorted_servings[:, l] * sorted_valid[:, l]  # [K]
                to_eat = torch.minimum(remaining, slot_avail)  # [K]

                # === SLOT/DAY CALORIE CHECK FOR MAIN LEFTOVER CONSUMPTION ===
                # Don't consume leftover mains past the current slot and daily calorie headroom.
                current_day_cal = new_daily_nutrition[:, day, 0]  # [new_K]
                slot_cal_per_srv = sorted_cal[:, l]  # [new_K] cal per serving for this slot
                urgent_rescue = (
                    (sorted_valid[:, l] > 0)
                    & (
                        ((~sorted_is_frozen[:, l]) & (sorted_ttl[:, l] <= 1))
                        | (sorted_is_frozen[:, l] & (sorted_ttl[:, l] <= urgency_days))
                    )
                )
                normal_headroom = self._leftover_calorie_headroom(
                    slot=slot,
                    current_day_cal=current_day_cal,
                    slot_start_day_cal=slot_start_day_cal,
                    daily_ceiling=daily_ceiling_for_mains,
                    urgent=False,
                )
                rescue_ceiling = daily_target_for_mains * getattr(
                    self.config,
                    'urgent_leftover_daily_ceiling_pct',
                    1.10,
                )
                rescue_headroom = self._leftover_calorie_headroom(
                    slot=slot,
                    current_day_cal=current_day_cal,
                    slot_start_day_cal=slot_start_day_cal,
                    daily_ceiling=rescue_ceiling,
                    urgent=True,
                )
                headroom = torch.where(urgent_rescue, rescue_headroom, normal_headroom)
                safe_to_eat = headroom / slot_cal_per_srv.clamp(min=1.0)
                to_eat = torch.minimum(to_eat, safe_to_eat.clamp(min=0))

                # Update nutrition (only for frontiers eating something)
                eating = to_eat > 0
                if eating.any():
                    cal_eaten = sorted_cal[eating, l] * to_eat[eating]
                    prot_eaten = sorted_prot[eating, l] * to_eat[eating]
                    new_nutrition[eating, 0] += cal_eaten
                    new_nutrition[eating, 1] += prot_eaten
                    # Phase 3: Update daily nutrition tracking
                    new_daily_nutrition[eating, day, 0] += cal_eaten
                    new_daily_nutrition[eating, day, 1] += prot_eaten

                    # Track template and recipe ID of eaten leftover (first slot consumed)
                    # This is used to update template_ids for side leftover matching
                    # and to display correct recipe name in selection tuple
                    # Check for -1 (sentinel) not 0 (valid template/recipe ID)
                    first_consume = (eaten_leftover_template == -1) & eating
                    if first_consume.any():
                        eaten_leftover_template[first_consume] = sorted_template_ids[first_consume, l].long()
                        eaten_leftover_recipe_id[first_consume] = sorted_recipe_ids[first_consume, l].long()

                    # Record ALL consumed leftover sources for multi-leftover display
                    # Servings represent whole people — always integers.
                    eating_indices = eating.nonzero(as_tuple=True)[0]
                    recipe_ids_at_l = sorted_recipe_ids[:, l]
                    for ki in eating_indices.tolist():
                        rid = int(recipe_ids_at_l[ki].item())
                        srv_float = float(to_eat[ki].item())
                        srv = int(round(srv_float))
                        if srv > 0 and rid > 0:
                            all_lo_sources[ki].append((rid, srv))
                        if srv_float > 0 and rid > 0:
                            audit_events[ki].append({
                                'role': 'main',
                                'source': 'leftover',
                                'recipe_id': rid,
                                'servings': srv_float,
                                'cal_per_serving': float(sorted_cal[ki, l].item()),
                                'protein_per_serving': float(sorted_prot[ki, l].item()),
                                'carbs_per_serving': 0.0,
                                'fat_per_serving': 0.0,
                            })

                # Update remaining and total
                remaining = remaining - to_eat
                total_lo_consumed = total_lo_consumed + to_eat

                # Decrement in original tensor (map back through sorted_indices)
                orig_slot = sorted_indices[:, l]  # [K] - original slot indices
                # Use pre-created k_idx for performance (avoid tensor allocation in loop)
                orig_servings = new_leftovers[k_idx[:, 0], orig_slot, 1]
                orig_grams = new_leftovers[k_idx[:, 0], orig_slot, 9]
                eat_fraction = torch.where(
                    orig_servings > 0,
                    to_eat / orig_servings.clamp(min=1e-6),
                    torch.zeros_like(to_eat),
                )
                new_leftovers[k_idx[:, 0], orig_slot, 9] = (orig_grams * (1.0 - eat_fraction)).clamp(min=0)
                new_leftovers[k_idx[:, 0], orig_slot, 1] -= to_eat

            # Clear empty slots (servings <= 0.1)
            empty_mask = new_leftovers[:, :, 1] <= 0.1
            new_leftovers[empty_mask] = 0

            # Track total leftover consumption per-frontier
            new_leftover_consumed += total_lo_consumed

            # servings_to_cook is what we still need after eating all available leftovers
            servings_to_cook_expanded = remaining.clamp(min=0)
            slot_cal_after_main_leftovers = (
                new_daily_nutrition[:, day, 0] - slot_start_day_cal
            ).clamp(min=0)
            slot_floor_after_leftovers = float(self.cal_target_per_slot[slot].item()) * getattr(
                self.config,
                'calorie_floor_pct',
                0.95,
            )
            daily_headroom_after_leftovers = (
                daily_ceiling_for_mains - new_daily_nutrition[:, day, 0]
            ).clamp(min=0)
            leftover_calories_satisfy_slot = (
                (total_lo_consumed > 0)
                & (
                    (slot_cal_after_main_leftovers >= slot_floor_after_leftovers)
                    | (daily_headroom_after_leftovers <= 1.0)
                )
            )
            servings_to_cook_expanded = torch.where(
                leftover_calories_satisfy_slot,
                torch.zeros_like(servings_to_cook_expanded),
                servings_to_cook_expanded,
            )
            actual_supplement_servings = self._leftover_calorie_supplement_servings(
                slot=slot,
                current_calories_after_leftovers=new_nutrition[:, 0],
                slot_servings=slot_servings,
                full_leftover_mask=total_lo_consumed >= slot_servings - 0.1,
            )
            servings_to_cook_expanded = torch.maximum(
                servings_to_cook_expanded,
                actual_supplement_servings,
            )

            if self.verbose and slot == 0 and total_lo_consumed.sum() > 0:
                print(f"    Consumed {total_lo_consumed.sum().item():.1f} leftover servings (vectorized)")

            # === UPDATE TEMPLATE_IDS FOR LEFTOVERS (CRITICAL FIX) ===
            # When eating leftover mains, we need to use THEIR template for side matching,
            # not the template of the selected-but-not-cooked recipe.
            # Without this fix, side leftovers never match and expire → WASTE
            #
            # NOTE: We track TWO different flags:
            # 1. ate_from_leftover: ANY leftover consumed (for template matching)
            # 2. meal_entirely_from_leftover: ENTIRE meal from leftover (for selection tuple)
            ate_from_leftover = total_lo_consumed > 0.5  # Any leftover consumed
            meal_entirely_from_leftover = (
                (total_lo_consumed >= slot_servings - 0.5)
                & ate_from_leftover
                & (servings_to_cook_expanded <= 0.1)
            )  # No cooking needed
            if ate_from_leftover.any():
                # Use template stored in leftover directly (no lookup needed)
                template_ids[ate_from_leftover] = eaten_leftover_template[ate_from_leftover]
                if self.verbose and slot == 0:
                    print(f"    Updated {ate_from_leftover.sum().item()} template IDs for leftover mains")

                # Track consumed recipe IDs for same-day dedup
                consumed_mask = ate_from_leftover & (eaten_leftover_recipe_id > 0)
                if consumed_mask.any():
                    new_daily_consumed[:, meal_idx][consumed_mask] = eaten_leftover_recipe_id[consumed_mask]


            # === LEFTOVERS FIRST: SKIP COOKING WHEN INVENTORY HIGH ===
            # When leftovers FULLY covered the slot AND inventory is high, don't cook new.
            # This forces the system to cycle through existing inventory instead of
            # accumulating until expiration (batch waste events).

            # CRITICAL FIX: Only skip cooking if leftovers FULLY covered the slot!
            # Old code used `total_lo_consumed > 0.5` which would skip cooking even when
            # the leftover ceiling restricted consumption, leaving remaining servings with
            # ZERO main dish calories. This caused 3-6% systematic underfeed for large households.
            fully_fed_from_leftovers = servings_to_cook_expanded <= 0.1

            # === CHECK 1: Frozen item pressure (original logic) ===
            frozen_count = (new_leftovers[:, :, 6] > 0).sum(dim=1).float()  # [K] frozen items per frontier
            if slot_servings <= 1.5:  # Single person
                frozen_threshold = self.config.frozen_skip_threshold_hs1
            elif slot_servings <= 2.5:  # Couple
                frozen_threshold = self.config.frozen_skip_threshold_hs2
            else:  # Family
                frozen_threshold = self.config.frozen_skip_threshold_hs4
            high_frozen = frozen_count > frozen_threshold
            skip_cooking_frozen = high_frozen & fully_fed_from_leftovers

            # === CHECK 2: Meal-type MAIN inventory (NEW - fixes fresh leftover blind spot) ===
            # Count MAIN dish leftovers (fresh + frozen) of the current meal type.
            # IMPORTANT: Only count MAINS (dish_type=1 or 0=any), not SIDES (dish_type=2)
            # because consumption only eats mains for main dish slots.
            # Example: 20 pancakes for 1 person = ~3 weeks of breakfast, don't cook more breakfast!
            lo_meal_types_check = new_leftovers[:, :, 5]  # [K, L]
            lo_servings_check = new_leftovers[:, :, 1]    # [K, L]
            lo_dish_types_check = new_leftovers[:, :, 7]  # [K, L] - 0=any, 1=main, 2=side
            valid_lo = lo_servings_check > 0.1
            is_main = (lo_dish_types_check == 1) | (lo_dish_types_check == 0)  # mains only, not sides

            # Sum MAIN servings for current meal type
            if meal_idx == 0:  # breakfast - only breakfast mains work
                meal_type_mask = (lo_meal_types_check == 0) & valid_lo & is_main
            elif meal_idx == 1:  # lunch - can eat lunch OR dinner mains
                meal_type_mask = ((lo_meal_types_check == 1) | (lo_meal_types_check == 2)) & valid_lo & is_main
            else:  # dinner - can eat lunch OR dinner mains
                meal_type_mask = ((lo_meal_types_check == 1) | (lo_meal_types_check == 2)) & valid_lo & is_main

            meal_type_inventory = (meal_type_mask.float() * lo_servings_check).sum(dim=1)  # [K]

            # Threshold: 1 week's worth of this meal type (7 meals × servings per meal)
            meal_type_threshold = slot_servings * 7
            skip_cooking_meal_type = (meal_type_inventory > meal_type_threshold) & fully_fed_from_leftovers

            # Combine: skip if frozen pressure OR meal-type inventory is high
            skip_cooking = skip_cooking_frozen | skip_cooking_meal_type

            # Force skip cooking for frontiers with high frozen inventory
            servings_to_cook_expanded = torch.where(
                skip_cooking,
                torch.zeros_like(servings_to_cook_expanded),
                servings_to_cook_expanded
            )

            if self.verbose:
                frozen_skip = skip_cooking_frozen.sum().item()
                meal_skip = skip_cooking_meal_type.sum().item()
                avg_inventory = meal_type_inventory.mean().item()
                lo_consumed = total_lo_consumed.mean().item()
                meal_names = ['B', 'L', 'D']
                if avg_inventory > 5 or skip_cooking.any():  # Only show interesting cases
                    print(f"      {meal_names[meal_idx]}: inv={avg_inventory:.0f}, thresh={meal_type_threshold:.0f}, consumed={lo_consumed:.1f}, skip={meal_skip}")

            # === VECTORIZED MAIN TRANSITION ===
            # Only cook if we need to (servings_to_cook_expanded > 0)
            needs_cooking = servings_to_cook_expanded > 0

            # Get all recipe data at once (OPTIMIZED: packed metadata = 1 gather instead of 5)
            main_ing_idx = self._recipe_ing_idx_long[selected_main_db_idx]  # [new_K, MAX_NNZ]
            main_metadata = self.db.packed_metadata[selected_main_db_idx]  # [new_K, 12] - single gather!
            # Unpack: [servings(1), nutrition(4), food_groups(7)]
            main_servings_original = main_metadata[:, 0]  # [new_K]
            main_nutr = main_metadata[:, 1:5].clone()    # [new_K, 4] - CLONE to allow modification
            main_food_grp = main_metadata[:, 5:12]  # [new_K, 7]

            # === DYNAMIC SERVINGS FIX ===
            # When dynamic servings is enabled, we need to:
            # 1. Use dynamic servings instead of original servings for cooking
            # 2. Recompute effective cal/srv = total_cal / dynamic_servings
            if self.config.enable_dynamic_servings:
                main_servings, _ = self._compute_dynamic_servings(
                    selected_main_db_idx, slot, meal_type, 'main'
                )
                # Compute effective cal/srv based on dynamic servings
                # total_cal is constant, but servings changed, so cal/srv changes
                main_total_cal = self.db.total_calories[selected_main_db_idx.long()]  # [new_K]
                effective_cal_per_srv = main_total_cal / main_servings.clamp(min=1.0)  # [new_K]
                # Update nutrition to use effective values
                # Scale all nutrition proportionally: new_nutr = original_nutr * (effective_cal / original_cal)
                original_cal_per_srv = main_nutr[:, 0].clamp(min=1.0)
                cal_ratio = effective_cal_per_srv / original_cal_per_srv
                main_nutr = main_nutr * cal_ratio.unsqueeze(1)  # Scale all nutrients proportionally
            else:
                main_servings = main_servings_original

            # Only process frontiers that need cooking
            if needs_cooking.any():
                k_cook = torch.arange(new_K, device=self.device)[needs_cooking]

                # Full amounts for full recipe (only for cooking frontiers)
                cook_ing_idx = main_ing_idx[needs_cooking]  # [num_cook, MAX_NNZ]
                cook_servings = main_servings[needs_cooking]
                cook_nutr = main_nutr[needs_cooking]
                cook_food_grp = main_food_grp[needs_cooking]  # [num_cook, 5]
                cook_stc = servings_to_cook_expanded[needs_cooking]  # servings to cook

                # === NUTRITION CAP FIX ===
                # Can't eat more dynamic servings than the recipe produces.
                # When dynamic_servings < household_size, cap consumed servings
                # at dynamic_servings. The remaining people get partial portions
                # (physically: the recipe is divided among everyone, so each person
                # gets total_cal / household_size, not effective_cal_per_dynamic_srv).
                # But we must not book phantom calories that don't exist.
                cook_stc = torch.minimum(cook_stc, cook_servings)

                # COOK FULL BATCH: Use ORIGINAL servings for ingredient amounts
                # The ingredient_amounts in DB are per-ORIGINAL-serving, not per-dynamic-serving
                # Dynamic servings is for calorie normalization, not for ingredient computation
                # FIX: Always use original servings for cooking to get correct ingredient amounts
                full_amt = self._recipe_full_amounts[selected_main_db_idx][needs_cooking]  # [num_cook, MAX_NNZ]

                # Gather current pantry at ingredient positions
                num_cook = k_cook.shape[0]
                idx_flat = cook_ing_idx.flatten()  # [num_cook * MAX_NNZ]
                k_indices = k_cook.repeat_interleave(MAX_NNZ)
                pantry_at_ing = new_pantries[k_indices, idx_flat].view(num_cook, MAX_NNZ)

                # What we take from pantry vs buy
                take = torch.minimum(pantry_at_ing, full_amt)
                to_buy = (full_amt - take).clamp(min=0)

                # Package purchasing
                pkg_sizes = self._recipe_pkg_option_sizes[selected_main_db_idx][needs_cooking]
                pkg_prices = self._recipe_pkg_option_prices[selected_main_db_idx][needs_cooking]
                num_pkg, selected_pkg_sizes, selected_pkg_prices, purchased_grams, ingredient_cost, selected_pkg_option_idx = self._choose_package_options(
                    to_buy,
                    pkg_sizes,
                    pkg_prices,
                    getattr(self.config, "package_remainder_choice_penalty_per_kg", 0.0),
                    return_indices=True,
                )

                num_ing = new_pantries.shape[1]
                k_expanded = k_cook.view(-1, 1).expand(-1, MAX_NNZ)  # [num_cook, MAX_NNZ]
                flat_idx = k_expanded * num_ing + cook_ing_idx  # [num_cook, MAX_NNZ]

                # Total cost per cooking frontier
                meal_cost = torch.round(ingredient_cost.float().sum(dim=1) * 100.0).float() / 100.0  # [num_cook]
                new_cost[k_cook] += meal_cost
                new_objective_cost[k_cook] += meal_cost

                # Track per-ingredient packages bought without a Python loop.
                flat_packages = new_ingredient_packages.view(-1)
                self._deterministic_scatter_add(flat_packages, 0, flat_idx.flatten(), num_pkg.flatten())
                self._deterministic_scatter_add(
                    new_ingredient_purchase_costs.view(-1),
                    0,
                    flat_idx.flatten(),
                    ingredient_cost.flatten(),
                )

                # Excess goes back to pantry
                excess = purchased_grams - to_buy
                pantry_delta = excess - take

                # Update pantry for cooking frontiers (VECTORIZED - no Python loop)
                # Flatten to 1D and use single scatter_add_
                num_cook = k_cook.shape[0]
                new_K = new_pantries.shape[0]

                # FIX: Assert k_cook indices are within bounds
                assert k_cook.max() < new_K, f"k_cook index {k_cook.max()} >= new_K {new_K}"

                # Flatten and scatter (deterministic across CPU/CUDA)
                flat_pantries = new_pantries.view(-1)  # [new_K * num_ing]
                self._deterministic_scatter_add(flat_pantries, 0, flat_idx.flatten(), pantry_delta.flatten())
                flat_ing_acquired = new_ingredient_acquired_grams.view(-1)
                flat_ing_consumed = new_ingredient_consumed_grams.view(-1)
                self._deterministic_scatter_add(
                    flat_ing_acquired,
                    0,
                    flat_idx.flatten(),
                    purchased_grams.flatten(),
                )
                self._deterministic_scatter_add(
                    flat_ing_consumed,
                    0,
                    flat_idx.flatten(),
                    take.flatten(),
                )
                flat_ing_recipe_used = new_ingredient_recipe_used_grams.view(-1)
                self._deterministic_scatter_add(
                    flat_ing_recipe_used,
                    0,
                    flat_idx.flatten(),
                    full_amt.flatten(),
                )

                # Reset TTL/storage for purchased ingredients from the selected package form.
                # Frozen retail packages start frozen; otherwise fall back to ingredient TTL.
                purchased_mask = num_pkg > 0  # [num_cook, MAX_NNZ]
                if purchased_mask.any():
                    purchase_ttl = self._purchase_ttl_for_recipe_positions(
                        selected_main_db_idx[needs_cooking],
                        cook_ing_idx,
                        selected_pkg_option_idx,
                    )  # [num_cook, MAX_NNZ]
                    purchase_frozen = self._purchase_frozen_for_recipe_positions(
                        selected_main_db_idx[needs_cooking],
                        cook_ing_idx,
                        selected_pkg_option_idx,
                    )  # [num_cook, MAX_NNZ]
                    # Use flat indexing for GPU-efficient update
                    flat_ttl = new_pantry_ttl.view(-1)
                    flat_frozen = new_pantry_frozen.view(-1)
                    update_mask = purchased_mask.flatten()  # [num_cook * MAX_NNZ]
                    update_idx = flat_idx.flatten()[update_mask]
                    flat_ttl.index_copy_(0, update_idx, purchase_ttl.flatten()[update_mask])
                    flat_frozen.index_copy_(0, update_idx, purchase_frozen.flatten()[update_mask])

                # Track pantry flow per-frontier for sustainability metrics
                # Sum across ingredients per cooking frontier: [num_cook, MAX_NNZ] -> [num_cook]
                consumed_per_cook = take.sum(dim=1)  # [num_cook]
                acquired_per_cook = purchased_grams.sum(dim=1)  # [num_cook]
                new_consumed_grams[k_cook] += consumed_per_cook
                new_acquired_grams[k_cook] += acquired_per_cook

                # Track frozen vs fresh consumption
                frozen_at_ing = new_pantry_frozen[k_indices, idx_flat].view(num_cook, MAX_NNZ)  # [num_cook, MAX_NNZ]
                frozen_consumed = (take * frozen_at_ing.float()).sum(dim=1)  # [num_cook]
                fresh_consumed = consumed_per_cook - frozen_consumed  # [num_cook]
                new_pantry_frozen_consumed[k_cook] += frozen_consumed
                new_pantry_fresh_consumed[k_cook] += fresh_consumed

                # Track urgency: count ingredients with TTL < 7 that were used
                ttl_at_ing = new_pantry_ttl[k_indices, idx_flat].view(num_cook, MAX_NNZ)  # [num_cook, MAX_NNZ]
                is_urgent = (ttl_at_ing < 7) & (take > 0)  # [num_cook, MAX_NNZ]
                urgent_count = is_urgent.sum(dim=1).float()  # [num_cook]
                new_urgent_ingredients_used[k_cook] += urgent_count

                # Add nutrition from cooking (only what we actually eat, not the full recipe)
                cal_from_cook = cook_nutr[:, 0] * cook_stc
                prot_from_cook = cook_nutr[:, 1] * cook_stc
                carbs_from_cook = cook_nutr[:, 2] * cook_stc
                fat_from_cook = cook_nutr[:, 3] * cook_stc
                new_nutrition[k_cook, 0] += cal_from_cook  # calories
                new_nutrition[k_cook, 1] += prot_from_cook  # protein
                new_nutrition[k_cook, 2] += carbs_from_cook  # carbs
                new_nutrition[k_cook, 3] += fat_from_cook  # fat
                # Phase 3: Update daily nutrition tracking
                new_daily_nutrition[k_cook, day, 0] += cal_from_cook
                new_daily_nutrition[k_cook, day, 1] += prot_from_cook
                new_daily_nutrition[k_cook, day, 2] += carbs_from_cook
                new_daily_nutrition[k_cook, day, 3] += fat_from_cook
                selected_main_ids_for_cook = selected_main_ids[needs_cooking]
                for event_i, k_local in enumerate(k_cook.tolist()):
                    servings_eaten = float(cook_stc[event_i].item())
                    if servings_eaten <= 0:
                        continue
                    event = {
                        'role': 'main',
                        'source': 'fresh',
                        'recipe_id': int(selected_main_ids_for_cook[event_i].item()),
                        'servings': servings_eaten,
                        'cal_per_serving': float(cook_nutr[event_i, 0].item()),
                        'protein_per_serving': float(cook_nutr[event_i, 1].item()),
                        'carbs_per_serving': float(cook_nutr[event_i, 2].item()),
                        'fat_per_serving': float(cook_nutr[event_i, 3].item()),
                    }
                    if self.debug_trace:
                        event['purchase_ingredients'] = self._debug_purchase_ingredients(
                            cook_ing_idx[event_i],
                            full_amt[event_i],
                            take[event_i],
                            to_buy[event_i],
                            num_pkg[event_i],
                            selected_pkg_sizes[event_i],
                            selected_pkg_prices[event_i],
                        )
                    audit_events[k_local].append(event)

                # Add food groups from cooking (vegetables_g=0, fruits_g=1)
                new_food_groups[k_cook, 0] += cook_food_grp[:, 0] * cook_stc  # vegetables
                new_food_groups[k_cook, 1] += cook_food_grp[:, 1] * cook_stc  # fruits

                # === LEFTOVER CREATION ===
                # We cook the full recipe batch, eat cook_stc, and store the rest
                # Leftovers = full batch - what we eat now
                full_batch_grams = full_amt.sum(dim=1)  # [num_cook]
                leftover_srv = (cook_servings - cook_stc).clamp(min=0)  # [num_cook]
                leftover_grams = full_batch_grams * (leftover_srv / cook_servings.clamp(min=1.0))
                has_leftover = leftover_srv > 0.5  # Has at least 1 serving leftover

                # Find first empty slot per cooking frontier
                cook_leftovers = new_leftovers[k_cook]  # [num_cook, L, LEFTOVER_FIELDS]
                empty_mask = cook_leftovers[:, :, 0] == 0
                has_empty = empty_mask.any(dim=1)
                first_empty = empty_mask.long().argmax(dim=1)

                # Only store if has leftover AND has empty slot
                can_store = has_leftover & has_empty
                if can_store.any():
                    store_k_local = torch.arange(num_cook, device=self.device)[can_store]
                    store_k_global = k_cook[can_store]
                    slot_idx = first_empty[can_store]
                    store_main_ids = selected_main_ids[needs_cooking][can_store]
                    store_template_ids = template_ids[needs_cooking][can_store]  # Template for these mains

                    new_leftovers[store_k_global, slot_idx, 0] = store_main_ids.float()
                    new_leftovers[store_k_global, slot_idx, 1] = leftover_srv[can_store]
                    new_leftovers[store_k_global, slot_idx, 2] = self.leftover_ttl
                    new_leftovers[store_k_global, slot_idx, 3] = cook_nutr[can_store, 0]
                    new_leftovers[store_k_global, slot_idx, 4] = cook_nutr[can_store, 1]
                    new_leftovers[store_k_global, slot_idx, 5] = meal_idx
                    new_leftovers[store_k_global, slot_idx, 6] = 0  # Fresh, not frozen
                    new_leftovers[store_k_global, slot_idx, 7] = 1  # dish_type: 1=main (0=uninitialized/any, 2=side)
                    new_leftovers[store_k_global, slot_idx, 8] = store_template_ids.float()  # template_id
                    new_leftovers[store_k_global, slot_idx, 9] = leftover_grams[can_store]

                # Update variety ring only for cooking frontiers
                ptr = new_used_ptr[k_cook] % COOLDOWN_LEN
                new_used_ids[k_cook, ptr] = selected_main_ids[needs_cooking].long()
                new_used_ptr[k_cook] += 1

                # Update protein quota counts for cooking frontiers
                # Weight by meals-worth of servings: a recipe producing 8 servings
                # for a 4-person household = 2 meals, not 1. This accounts for
                # leftover amplification so the quota matches what the user sees.
                cooking_db_idx = selected_main_db_idx[needs_cooking]
                cooking_protein_sources = self.db.protein_source[cooking_db_idx.long()]  # [num_cooking] int8
                valid_src = (cooking_protein_sources >= 0) & (cooking_protein_sources <= 5)
                if valid_src.any():
                    k_valid = k_cook[valid_src]
                    src_valid = cooking_protein_sources[valid_src].long()
                    # Weight by meals-worth: total servings / headcount, capped [1, 5]
                    meals_worth = (cook_servings[valid_src] / max(slot_servings, 1)).clamp(min=1.0, max=5.0)
                    new_protein_counts[k_valid, src_valid] += meals_worth

            # === PHASE 2: Score sides (filtered) ===
            side_ids = torch.zeros(new_K, dtype=torch.long, device=self.device)
            side_names = [""] * new_K
            side_from_leftover = torch.zeros(new_K, dtype=torch.bool, device=self.device)
            # Second side dish (for calorie gap filling)
            side2_ids = torch.zeros(new_K, dtype=torch.long, device=self.device)
            side2_names = [""] * new_K

            # === TEMPLATE-AWARE SIDE LEFTOVER CONSUMPTION ===
            # Strict template matching: side leftovers can only be consumed with
            # mains from the same template (garlic bread only with pasta mains)
            side_servings_needed = slot_servings  # Each person gets a serving
            K_side, L_side = new_leftovers.shape[:2]

            # Extract all leftover fields
            side_lo_recipe_ids = new_leftovers[:, :, 0]  # [K, L]
            side_lo_servings = new_leftovers[:, :, 1]    # [K, L]
            side_lo_ttl = new_leftovers[:, :, 2]         # [K, L]
            side_lo_cal = new_leftovers[:, :, 3]         # [K, L]
            side_lo_prot = new_leftovers[:, :, 4]        # [K, L]
            side_lo_meal_types = new_leftovers[:, :, 5]  # [K, L]
            side_lo_is_frozen = new_leftovers[:, :, 6] > 0  # [K, L]
            side_lo_dish_types = new_leftovers[:, :, 7]  # [K, L] - 0=uninitialized/any, 1=main, 2=side
            side_lo_template_ids = new_leftovers[:, :, 8]  # [K, L] - template_id

            # Meal compatibility
            if meal_idx == 0:
                side_compatible = (side_lo_meal_types == 0)
            elif meal_idx == 1:
                side_compatible = (side_lo_meal_types == 1) | (side_lo_meal_types == 2)
            else:
                side_compatible = (side_lo_meal_types == 1) | (side_lo_meal_types == 2)

            # TEMPLATE-AWARE side leftover consumption
            # Each frontier k has its own template_ids[k], so we do per-frontier matching
            # For backwards compatibility: dish_type=0 and template_id=0 are treated as "any"
            # (uninitialized leftovers from before this feature work like before)
            is_side_or_any = (side_lo_dish_types == 2) | (side_lo_dish_types == 0)  # 2=side, 0=any/legacy
            frontier_templates = template_ids.unsqueeze(1).expand(new_K, L_side)  # [K, L]

            # CATEGORY-BASED template matching (cross-template leftover consumption)
            # A green_salad leftover from dinner_pasta should be consumable with dinner_steak
            # because BOTH templates have green_salad in their side_pools.
            # We use gpu_side_compat[db_idx, template_id] to check if a side recipe
            # is valid for the target template's side_pools.
            # CRITICAL: Leftovers store recipe_ids, but gpu_side_compat is indexed by db_idx
            # Must convert recipe_id -> db_idx before lookup!
            side_recipe_ids_clamped = side_lo_recipe_ids.long().clamp(0, self.db.gpu_recipe_id_to_idx.shape[0] - 1)
            side_db_indices = self.db.gpu_recipe_id_to_idx[side_recipe_ids_clamped]  # [K, L] - convert to db_idx
            side_db_indices_valid = side_db_indices.clamp(0, self.db.num_recipes - 1)  # Clamp -1 (unmapped) to valid range
            frontier_templates_clamped = frontier_templates.long().clamp(0, self.db.gpu_side_compat.shape[1] - 1)  # [K, L]
            category_match = self.db.gpu_side_compat[side_db_indices_valid, frontier_templates_clamped]  # [K, L]
            category_match = category_match & (side_db_indices >= 0)  # Unmapped recipes (-1) should not match

            # Final match: category-compatible OR legacy (template_id=0) OR main has no template.
            # If a side is close to expiring, rescue it even when the template
            # is not perfect; throwing away cooked food is worse than a loose
            # pairing.
            # NOTE: Frozen items NO LONGER bypass template matching - they still need category match
            # This prevents breakfast sides from leaking into dinner via freezing
            # BUG FIX: When main has no template (template_id=-1), allow ANY meal-compatible side
            # This affects 57% of recipes that have no template assignment
            no_template_main = (frontier_templates == -1)  # [K, L] - main recipe has no template
            urgent_side_rescue = (
                ((~side_lo_is_frozen) & (side_lo_ttl <= 1))
                | (side_lo_is_frozen & (side_lo_ttl <= urgency_days))
            )
            template_match = (
                category_match
                | (side_lo_template_ids == 0)
                | no_template_main
                | urgent_side_rescue
            )  # [K, L]

            # Valid = has recipe + has servings + meal compatible + (side or legacy) + template matches
            side_valid = (side_lo_recipe_ids > 0) & (side_lo_servings > 0) & side_compatible & is_side_or_any & template_match

            # Priority: fresh first, then frozen.
            side_fresh_priority = torch.where(side_valid & ~side_lo_is_frozen, 100.0 - side_lo_ttl, torch.full_like(side_lo_ttl, -1000.0))
            side_frozen_priority = torch.where(side_valid & side_lo_is_frozen, 50.0 - side_lo_ttl, torch.full_like(side_lo_ttl, -1000.0))
            side_priority = torch.maximum(side_fresh_priority, side_frozen_priority)

            # === FROZEN EXPIRY URGENCY BOOST (for sides) ===
            # Same logic as main dishes: boost frozen sides near expiry so they compete with fresh
            # Uses same urgency_days scaling as main dishes (calculated above based on family_size)
            side_frozen_near_expiry = side_valid & side_lo_is_frozen & (side_lo_ttl <= urgency_days)
            side_expiry_boost = torch.where(
                side_frozen_near_expiry,
                120.0 * (1.0 - side_lo_ttl / urgency_days).clamp(min=0),
                torch.zeros_like(side_lo_ttl)
            )
            side_priority = side_priority + side_expiry_boost
            side_priority = torch.where(
                side_frozen_near_expiry,
                torch.maximum(side_priority, 125.0 - side_lo_ttl),
                side_priority,
            )

            # === SERVING SIZE URGENCY BOOST (for sides) ===
            side_serving_boost = (side_lo_servings.clamp(max=20) / 20) * 15.0
            side_priority = side_priority + torch.where(side_valid, side_serving_boost, torch.zeros_like(side_serving_boost))

            # Sort by priority
            side_sorted_indices = self._stable_argsort(side_priority, descending=True, dim=1)
            side_k_idx = torch.arange(new_K, device=self.device).unsqueeze(1).expand(new_K, L_side)

            # Reorder by priority
            side_sorted_servings = side_lo_servings[side_k_idx, side_sorted_indices]
            side_sorted_cal = side_lo_cal[side_k_idx, side_sorted_indices]
            side_sorted_prot = side_lo_prot[side_k_idx, side_sorted_indices]
            side_sorted_recipe_ids = side_lo_recipe_ids[side_k_idx, side_sorted_indices]
            side_sorted_valid = side_valid[side_k_idx, side_sorted_indices].float()
            side_sorted_ttl = side_lo_ttl[side_k_idx, side_sorted_indices]
            side_sorted_is_frozen = side_lo_is_frozen[side_k_idx, side_sorted_indices]

            # Greedy consumption
            side_remaining = torch.full((new_K,), side_servings_needed, device=self.device)
            side_total_consumed = torch.zeros(new_K, device=self.device)
            # Use -1 as sentinel for "no recipe yet" (0 could be a valid recipe ID)
            side_lo_recipe_id = torch.full((new_K,), -1, dtype=torch.long, device=self.device)

            max_side_slots = min(L_side, 4)
            # Daily calorie ceiling for leftover consumption (prevent overfeed)
            daily_target_for_sides = self.weekly_calories / 7.0

            # === SHADOW PRICING: DYNAMIC SOFT CEILING FOR SIDE LEFTOVER CONSUMPTION ===
            # Same coordinated shadow pricing logic as main dishes
            if getattr(self.config, 'enable_separate_shadow_prices', False):
                # === COORDINATED SHADOW PRICING: LEFTOVER CEILING (SIDES) ===
                if getattr(self.config, 'enable_coordinated_shadow_pricing', True):
                    lo_min = getattr(self.config, 'leftover_shadow_min', 0.80)
                    lo_max = getattr(self.config, 'leftover_shadow_max', 1.20)
                    lo_direction = self._effective_lo_direction  # Use computed direction (supports alternating)

                    if lo_direction == 'ascending':
                        # LOW→HIGH: tight early, loose late (save leftovers for later)
                        lo_mult = lo_min + (day / 6.0) * (lo_max - lo_min)
                    else:
                        # HIGH→LOW: loose early, tight late (use leftovers now)
                        lo_mult = lo_max - (day / 6.0) * (lo_max - lo_min)

                    day_ceiling = 1.0 * lo_mult
                else:
                    # Legacy: hardcoded 95%-107% scaling
                    day_ceiling = 0.95 + (day * 0.02)

                meal_adj = [1.02, 1.00, 0.98][meal_idx]

                daily_ceiling_for_sides = daily_target_for_sides * day_ceiling * meal_adj
            else:
                daily_ceiling_for_sides = daily_target_for_sides * 1.50  # Fallback when day ceilings are disabled

            for l in range(max_side_slots):
                if side_remaining.sum() < 0.1:
                    break

                slot_avail = side_sorted_servings[:, l] * side_sorted_valid[:, l]
                to_eat = torch.minimum(side_remaining, slot_avail)

                # === SLOT/DAY CALORIE CHECK FOR SIDE LEFTOVER CONSUMPTION ===
                # Don't consume leftover sides past the current slot and daily calorie headroom.
                current_day_cal = new_daily_nutrition[:, day, 0]  # [new_K]
                slot_cal_per_srv = side_sorted_cal[:, l]  # [new_K] cal per serving for this slot
                urgent_rescue = (
                    (side_sorted_valid[:, l] > 0)
                    & (
                        ((~side_sorted_is_frozen[:, l]) & (side_sorted_ttl[:, l] <= 1))
                        | (side_sorted_is_frozen[:, l] & (side_sorted_ttl[:, l] <= urgency_days))
                    )
                )
                normal_headroom = self._leftover_calorie_headroom(
                    slot=slot,
                    current_day_cal=current_day_cal,
                    slot_start_day_cal=slot_start_day_cal,
                    daily_ceiling=daily_ceiling_for_sides,
                    urgent=False,
                )
                rescue_ceiling = daily_target_for_sides * getattr(
                    self.config,
                    'urgent_leftover_daily_ceiling_pct',
                    1.10,
                )
                rescue_headroom = self._leftover_calorie_headroom(
                    slot=slot,
                    current_day_cal=current_day_cal,
                    slot_start_day_cal=slot_start_day_cal,
                    daily_ceiling=rescue_ceiling,
                    urgent=True,
                )
                headroom = torch.where(urgent_rescue, rescue_headroom, normal_headroom)
                safe_to_eat = headroom / slot_cal_per_srv.clamp(min=1.0)
                to_eat = torch.minimum(to_eat, safe_to_eat.clamp(min=0))

                eating = to_eat > 0
                if eating.any():
                    side_cal_eaten = side_sorted_cal[eating, l] * to_eat[eating]
                    side_prot_eaten = side_sorted_prot[eating, l] * to_eat[eating]
                    new_nutrition[eating, 0] += side_cal_eaten
                    new_nutrition[eating, 1] += side_prot_eaten
                    # Phase 3: Update daily nutrition tracking
                    new_daily_nutrition[eating, day, 0] += side_cal_eaten
                    new_daily_nutrition[eating, day, 1] += side_prot_eaten

                    # Track recipe ID from first slot consumed (for display)
                    # Check for -1 (sentinel) not 0 (could be valid recipe ID)
                    first_consume = (side_lo_recipe_id == -1) & eating
                    side_lo_recipe_id[first_consume] = side_sorted_recipe_ids[first_consume, l].long()
                    side_eating_indices = eating.nonzero(as_tuple=True)[0]
                    for ki in side_eating_indices.tolist():
                        srv_float = float(to_eat[ki].item())
                        rid = int(side_sorted_recipe_ids[ki, l].item())
                        if srv_float <= 0 or rid <= 0:
                            continue
                        audit_events[ki].append({
                            'role': 'side1',
                            'source': 'leftover',
                            'recipe_id': rid,
                            'servings': srv_float,
                            'cal_per_serving': float(side_sorted_cal[ki, l].item()),
                            'protein_per_serving': float(side_sorted_prot[ki, l].item()),
                            'carbs_per_serving': 0.0,
                            'fat_per_serving': 0.0,
                        })

                side_remaining = side_remaining - to_eat
                side_total_consumed = side_total_consumed + to_eat

                # Decrement in original tensor
                orig_slot = side_sorted_indices[:, l]
                orig_servings = new_leftovers[side_k_idx[:, 0], orig_slot, 1]
                orig_grams = new_leftovers[side_k_idx[:, 0], orig_slot, 9]
                eat_fraction = torch.where(
                    orig_servings > 0,
                    to_eat / orig_servings.clamp(min=1e-6),
                    torch.zeros_like(to_eat),
                )
                new_leftovers[side_k_idx[:, 0], orig_slot, 9] = (orig_grams * (1.0 - eat_fraction)).clamp(min=0)
                new_leftovers[side_k_idx[:, 0], orig_slot, 1] -= to_eat

            # Clear empty slots
            side_empty_mask = new_leftovers[:, :, 1] <= 0.1
            new_leftovers[side_empty_mask] = 0

            # Mark frontiers that got their full side from leftovers
            slot_cal_after_side_leftovers = (
                new_daily_nutrition[:, day, 0] - slot_start_day_cal
            ).clamp(min=0)
            slot_floor_after_side_leftovers = float(self.cal_target_per_slot[slot].item()) * getattr(
                self.config,
                'calorie_floor_pct',
                0.95,
            )
            daily_headroom_after_side_leftovers = (
                daily_ceiling_for_sides - new_daily_nutrition[:, day, 0]
            ).clamp(min=0)
            side_leftover_calories_satisfy_slot = (
                (side_total_consumed > 0)
                & (
                    (slot_cal_after_side_leftovers >= slot_floor_after_side_leftovers)
                    | (daily_headroom_after_side_leftovers <= 1.0)
                )
            )
            has_side_leftovers = (
                (side_total_consumed >= side_servings_needed - 0.1)
                | side_leftover_calories_satisfy_slot
            )
            side_from_leftover[has_side_leftovers] = True
            side_ids[has_side_leftovers] = side_lo_recipe_id[has_side_leftovers]

            # BUG FIX: Populate side_names for leftover sides (was missing)
            # Look up recipe name from leftover recipe ID
            for k in has_side_leftovers.nonzero(as_tuple=True)[0].tolist():
                lo_recipe_id = side_lo_recipe_id[k].item()
                if lo_recipe_id > 0:  # Valid recipe ID
                    db_idx = self.db.recipe_id_to_idx.get(lo_recipe_id)
                    if db_idx is not None:
                        side_names[k] = self.db.names[db_idx]

            # Track leftover consumption
            new_leftover_consumed += side_total_consumed

            if self.verbose and side_total_consumed.sum() > 0:
                print(f"    Side leftovers consumed: {side_total_consumed.sum().item():.1f} servings (vectorized)")

            # === OPTIMIZED SIDE SELECTION (GPU-accelerated) ===
            # Only for frontiers that DON'T have side leftovers
            # Instead of building per-frontier validity masks (O(K * num_sides) Python loop),
            # we pick the best side per TEMPLATE, then assign to frontiers.

            # Group frontiers by template using GPU tensors
            # template_ids is [new_K] tensor from GPU lookup
            # MODIFIED: Only frontiers without side leftovers need new sides
            # Sides are now ALSO eligible for one_dish recipes — soup/stew/smoothie
            # can pair with bread, salad, etc. when calorie demand justifies it.
            # Previously `~is_one_dish` hard-blocked sides for ~5% of templates,
            # but the recipe-to-template binding overrecruits ~18% of recipes
            # into those buckets, dropping the side ~40% of the time. Letting
            # the planner OPTIONALLY add a side restores main+side coverage on
            # those slots when calorie-target benefit > side cost. The
            # _compute_dynamic_servings code still gives one_dish recipes the
            # main+side calorie boost, so when no side is cooked they cover the
            # full slot solo; when a side IS cooked the side is bonus calories.
            needs_side = (template_ids >= 0) & ~side_from_leftover  # [new_K] bool tensor

            # === SIDE INVENTORY CHECK (same logic as main skip-cooking) ===
            # If we have enough side leftovers for this meal type, skip cooking new sides.
            # This prevents side inventory from exploding while mains are controlled.
            is_side_leftover = (side_lo_dish_types == 2)  # dish_type=2 is side
            if meal_idx == 0:  # breakfast
                side_inv_mask = (side_lo_meal_types == 0) & is_side_leftover & (side_lo_servings > 0.1)
            elif meal_idx == 1:  # lunch - can use lunch or dinner sides
                side_inv_mask = ((side_lo_meal_types == 1) | (side_lo_meal_types == 2)) & is_side_leftover & (side_lo_servings > 0.1)
            else:  # dinner
                side_inv_mask = ((side_lo_meal_types == 1) | (side_lo_meal_types == 2)) & is_side_leftover & (side_lo_servings > 0.1)
            side_inventory = (side_inv_mask.float() * side_lo_servings).sum(dim=1)  # [K]
            side_threshold = slot_servings * 7  # 1 week's worth of sides
            skip_side_cooking = side_inventory > side_threshold

            # Apply side inventory skip
            needs_side = needs_side & ~skip_side_cooking

            # Get unique templates that need sides
            unique_tids = template_ids[needs_side].unique()

            # Build template -> frontiers mapping (minimal Python loop over unique templates only)
            template_to_frontiers = {}
            for tid in unique_tids.tolist():
                # Find all frontiers with this template (GPU comparison)
                mask = (template_ids == tid) & needs_side
                frontier_indices = torch.nonzero(mask, as_tuple=True)[0].tolist()
                if frontier_indices:
                    template_to_frontiers[tid] = frontier_indices

            if template_to_frontiers:
                # For each template, score its sides and pick best
                # This is O(num_templates) instead of O(K * num_sides)

                all_side_indices_list = []
                all_side_pool_ids_list = []  # Track pool ID for pool diversity in side2
                template_side_ranges = {}  # tid -> (start, end) in concatenated tensor

                offset = 0
                for tid in template_to_frontiers.keys():
                    sides = self.db.template_to_sides.get(tid)
                    pool_ids = self.db.template_to_side_pool_ids.get(tid)
                    if sides is not None and len(sides) > 0:
                        # === ALLERGEN FILTERING (sides) ===
                        if self.allergen_safe_mask is not None:
                            safe = self.allergen_safe_mask[sides.long()]
                            if pool_ids is not None and len(pool_ids) == len(sides):
                                pool_ids = pool_ids[safe]
                            sides = sides[safe]  # HARD GATE - always enforce, never bypass
                        # === EMBER SCORE FILTERING (sides) ===
                        if self.ember_filter_mask is not None:
                            passing = self.ember_filter_mask[sides.long()]
                            if passing.sum().item() >= 3:
                                if pool_ids is not None and len(pool_ids) == len(sides):
                                    pool_ids = pool_ids[passing]
                                sides = sides[passing]
                        # === AIP FILTER (sides) ===
                        if self.aip_filter_mask is not None:
                            passing = self.aip_filter_mask[sides.long()]
                            if passing.sum().item() >= 3:
                                if pool_ids is not None and len(pool_ids) == len(sides):
                                    pool_ids = pool_ids[passing]
                                sides = sides[passing]
                        # === VERDICT EXCLUSION (sides) — hard-block not_food/invalid ===
                        if hasattr(self.db, 'gpu_verdict_excluded'):
                            not_excluded = ~self.db.gpu_verdict_excluded[sides.long()]
                            if not_excluded.sum().item() >= 3:
                                if pool_ids is not None and len(pool_ids) == len(sides):
                                    pool_ids = pool_ids[not_excluded]
                                sides = sides[not_excluded]
                        # === MEAL FITNESS FILTERING (sides) ===
                        if hasattr(self.db, 'gpu_meal_ok'):
                            meal_col = {'breakfast': 0, 'lunch': 1, 'dinner': 2}[meal_type]
                            fit = self.db.gpu_meal_ok[sides.long(), meal_col]
                            if fit.sum().item() >= 3:
                                if pool_ids is not None and len(pool_ids) == len(sides):
                                    pool_ids = pool_ids[fit]
                                sides = sides[fit]
                        template_side_ranges[tid] = (offset, offset + len(sides))
                        all_side_indices_list.append(sides)
                        if pool_ids is not None and len(pool_ids) > 0:
                            all_side_pool_ids_list.append(pool_ids)
                        else:
                            # Fallback: assign pool 0 if no pool IDs (shouldn't happen)
                            all_side_pool_ids_list.append(torch.zeros(len(sides), dtype=torch.int32, device=self.device))
                        offset += len(sides)

                if all_side_indices_list:
                    # Concatenate all unique sides for batch scoring
                    all_side_indices = torch.cat(all_side_indices_list)
                    all_side_pool_ids = torch.cat(all_side_pool_ids_list)

                    if self.verbose:
                        print(f"    Scoring {len(all_side_indices):,} sides for {len(template_to_frontiers)} templates...", end=" ", flush=True)

                    # Score all sides at once (using first frontier's state as representative)
                    # This is an approximation but much faster
                    first_k = next(iter(template_to_frontiers.values()))[0]
                    side_needed_for_score = float(
                        (torch.tensor(slot_servings, device=self.device) - side_total_consumed[first_k])
                        .clamp(min=0)
                        .item()
                    )
                    side_needed_tensor = torch.full(
                        (len(all_side_indices),),
                        side_needed_for_score,
                        device=self.device,
                    )

                    # Cost scoring for sides
                    side_costs = self._compute_incremental_cost(
                        new_pantries[first_k:first_k+1],
                        all_side_indices,
                        slot_servings=side_needed_for_score,
                    )  # [1, num_all_sides]
                    if getattr(self.config, 'enable_at_risk_pantry_rescue', False):
                        side_rescue_credit = self._compute_at_risk_pantry_rescue_credit(
                            new_pantries[first_k:first_k+1],
                            all_side_indices,
                            new_pantry_ttl[first_k:first_k+1],
                            new_pantry_frozen[first_k:first_k+1],
                        )
                        side_costs -= side_rescue_credit

                    # === SIDE1 CALORIE PENALTY (NEW) ===
                    # Penalize sides that would push us over the calorie ceiling
                    # Get current calories from main (already in new_nutrition)
                    main_cal_delivered = new_nutrition[first_k, 0].item()
                    slot_cal_target = self.cal_target_per_slot[slot].item()
                    calorie_ceiling = slot_cal_target * self.config.calorie_ceiling_pct

                    # Calculate calories each side would add
                    if self.config.enable_dynamic_servings:
                        _side_dyn_srv, _ = self._compute_dynamic_servings(
                            all_side_indices, slot, meal_type, 'side'
                        )
                        side_cal_per_srv = self.db.total_calories[all_side_indices.long()] / _side_dyn_srv.clamp(min=1)
                        side_servings_for_cal = torch.minimum(
                            _side_dyn_srv,
                            side_needed_tensor,
                        )
                    else:
                        side_cal_per_srv = self.db.nutrition[all_side_indices.long(), 0]  # [num_sides]
                        side_servings_for_cal = torch.minimum(
                            self.db.servings[all_side_indices.long()].float(),
                            side_needed_tensor,
                        )
                    side_cal_contribution = side_cal_per_srv * side_servings_for_cal  # [num_sides]

                    # Penalty for exceeding ceiling (same multiplier as mains)
                    total_with_side = main_cal_delivered + side_cal_contribution
                    cal_overshoot = (total_with_side - calorie_ceiling).clamp(min=0)
                    # Use same penalty rate as mains: base_lambda_cal * cal_over_ceiling_mult
                    side_cal_penalty = cal_overshoot * self.config.base_lambda_cal * self.config.cal_over_ceiling_mult
                    side_costs[0] = side_costs[0] + side_cal_penalty

                    # === SIDE DAILY OVERSHOOT PENALTY (PROGRESSIVE VERSION) ===
                    # The per-slot penalty above only checks this meal's ceiling
                    # This check ensures we don't exceed the DAILY ceiling either
                    # Critical for Phase 3 daily balance: sides were escaping daily penalty!
                    if getattr(self.config, 'enable_separate_shadow_prices', False):
                        day = slot // 3
                        meal_idx = slot % 3
                        daily_target = self.weekly_calories / 7.0
                        today_cal_so_far = new_daily_nutrition[first_k, day, 0].item()

                        # === PROGRESSIVE OVERSHOOT for sides (same family scaling as mains) ===
                        if getattr(self.config, 'enable_progressive_overshoot', True):
                            projected_total = today_cal_so_far + side_cal_contribution  # [num_sides]
                            projected_pct = projected_total / daily_target  # [num_sides]

                            # Family size scaling (same as mains)
                            family_size = self.attendance.household.size
                            base_floor = getattr(self.config, 'progressive_overshoot_floor', 1.0)
                            if family_size <= 2:
                                effective_floor = base_floor  # 100% for small households
                            else:
                                effective_floor = base_floor + 0.05  # 105% for families of 4+

                            overshoot_pct = (projected_pct - effective_floor).clamp(min=0)  # [num_sides]
                            overshoot_mult = getattr(self.config, 'progressive_overshoot_mult', 100.0)
                            meal_urgency = 1.0 + meal_idx  # 1=breakfast, 2=lunch, 3=dinner
                            side_progressive_penalty = (overshoot_pct ** 2) * overshoot_mult * meal_urgency
                            side_costs[0] = side_costs[0] + side_progressive_penalty

                        # === PROGRESSIVE UNDERSHOOT for sides (SMALL HOUSEHOLDS ONLY) ===
                        # Large households need variance for batch cooking - don't penalize undershoot
                        family_size = self.attendance.household.size
                        if getattr(self.config, 'enable_progressive_undershoot', True) and family_size <= 2:
                            projected_total = today_cal_so_far + side_cal_contribution  # [num_sides]
                            projected_pct = projected_total / daily_target  # [num_sides]

                            base_ceiling = getattr(self.config, 'progressive_undershoot_ceiling', 0.90)

                            # Only penalize when late in day (meal_idx 2 = dinner)
                            meals_remaining = 3 - meal_idx  # 3 at breakfast, 1 at dinner
                            meals_remaining_factor = max(0.0, 1.0 - meals_remaining / 3.0)

                            undershoot_pct = (base_ceiling - projected_pct).clamp(min=0)  # [num_sides]
                            undershoot_mult = getattr(self.config, 'progressive_undershoot_mult', 100.0)
                            meal_urgency = 1.0 + meal_idx  # 1=breakfast, 2=lunch, 3=dinner
                            side_undershoot_penalty = (undershoot_pct ** 2) * undershoot_mult * meal_urgency * meals_remaining_factor
                            side_costs[0] = side_costs[0] + side_undershoot_penalty

                        # Also keep the linear penalty for anything over ceiling
                        daily_ceiling_pct = getattr(self.config, 'daily_calorie_ceiling_pct', 1.15)
                        daily_ceiling = daily_target * daily_ceiling_pct
                        daily_overshoot = (today_cal_so_far + side_cal_contribution - daily_ceiling).clamp(min=0)
                        lambda_max = getattr(self.config, 'daily_shadow_lambda_max', 2.0)
                        side_daily_penalty = daily_overshoot * lambda_max / 1000.0  # Per 1000 cal
                        side_costs[0] = side_costs[0] + side_daily_penalty

                        # TRACE: Show side daily overshoot (only for slot 0)
                        if self.verbose and slot == 0:
                            max_overshoot = daily_overshoot.max().item()
                            max_penalty = side_daily_penalty.max().item()
                            num_penalized = (daily_overshoot > 0).sum().item()
                            print(f"\n    [SIDE DAILY TRACE slot={slot}]")
                            print(f"      daily_target: {daily_target:.0f}, ceiling: {daily_ceiling:.0f}")
                            print(f"      today_cal_so_far: {today_cal_so_far:.0f}")
                            print(f"      sides penalized: {num_penalized}/{len(all_side_indices)}")
                            print(f"      max_overshoot: {max_overshoot:.0f} cal, max_penalty: ${max_penalty:.2f}")

                    # === PRODUCE BONUS FOR SIDES ===
                    # Favor cheap fruit/veggie sides to hit nutritional targets
                    # BONUS (not penalty): rewards produce-heavy sides, doesn't hurt non-produce
                    side_food_groups = self.db.food_groups[all_side_indices.long()]  # [num_sides, 7]
                    side_veg_g = side_food_groups[:, 0].clamp(max=300)   # vegetables per serving (cap outliers)
                    side_fruit_g = side_food_groups[:, 1].clamp(max=300)  # fruits per serving (cap outliers)

                    # Scale by servings we'll actually eat (each person gets a serving)
                    if self.config.enable_dynamic_servings:
                        side_servings_raw = _side_dyn_srv  # reuse from calorie penalty above
                    else:
                        side_servings_raw = self.db.servings[all_side_indices.long()]
                    side_servings_eaten = torch.minimum(
                        side_servings_raw,
                        torch.full_like(side_servings_raw, side_needed_for_score)
                    )
                    side_veg_total = side_veg_g * side_servings_eaten
                    side_fruit_total = side_fruit_g * side_servings_eaten

                    # Compute urgency based on remaining meals and shortfall
                    meals_remaining = max(NUM_SLOTS - slot, 1)
                    # Use first frontier's food groups as representative
                    current_veg = new_food_groups[first_k, 0].item()
                    current_fruit = new_food_groups[first_k, 1].item()

                    veg_shortfall = max(0, self.weekly_vegetables_g - current_veg)
                    fruit_shortfall = max(0, self.weekly_fruits_g - current_fruit)

                    # Urgency multiplier: higher when behind schedule (1.0 to 2.0)
                    veg_urgency = min(2.0, 1.0 + veg_shortfall / (self.weekly_vegetables_g + 1))
                    fruit_urgency = min(2.0, 1.0 + fruit_shortfall / (self.weekly_fruits_g + 1))

                    # Produce bonus: per-meal $/gram bonus for vegetable/fruit sides
                    # Breakfast=0 (bread OK), lunch=light, dinner=strong
                    if self.config.enable_produce_bonus:
                        meal_produce = {
                            'breakfast': self.config.produce_value_breakfast,
                            'lunch': self.config.produce_value_lunch,
                            'dinner': self.config.produce_value_dinner,
                        }.get(meal_type, self.config.produce_value)
                        veg_bonus = side_veg_total * meal_produce * veg_urgency
                        fruit_bonus = side_fruit_total * meal_produce * fruit_urgency
                        side_costs[0] = side_costs[0] - veg_bonus - fruit_bonus

                    # === SIDE PROTEIN BONUS ===
                    # When protein targeting is active, prefer sides with higher protein density.
                    # Sides typically have ~10% protein density, which massively dilutes
                    # overall protein even when mains are high-protein. This bonus pulls
                    # side selection toward the protein target.
                    # NOTE: Removed 'target > 15' check to enable targeting at any level
                    if self.config.enable_protein_prefilter or self.config.enable_protein_density_bonus:
                        side_prot_g = self.db.nutrition[all_side_indices.long(), 1].float()  # [num_sides]
                        side_cal = self.db.nutrition[all_side_indices.long(), 0].float()  # [num_sides]
                        side_prot_pct = (side_prot_g * 4) / side_cal.clamp(min=1) * 100  # [num_sides]
                        side_prot_dist = (side_prot_pct - self.protein_pct_target).abs()  # [num_sides]
                        side_prot_prox = (1.0 - side_prot_dist / 30.0).clamp(min=0)  # [num_sides] 0-1
                        # Scale bonus with target distance: higher targets get stronger side pull
                        _side_prot_scale = max(1.0, (self.protein_pct_target - 15.0) / 10.0)
                        side_prot_bonus = side_prot_prox * self.config.protein_density_value * _side_prot_scale * side_needed_for_score
                        side_costs[0] = side_costs[0] - side_prot_bonus

                    # === SIDE PROTEIN DEBT COMPENSATION ===
                    # When side leftovers are decoupled (fresh sides), the side pool
                    # shifts toward low-protein vegetables. This bonus gently steers
                    # toward protein-containing sides (beans, eggs, cheese) when
                    # weekly protein is falling behind pace.
                    # Only activates when side_leftover_pct < main leftover_pct.
                    if self.side_leftover_pct_target < self.leftover_pct_target:
                        cumulative_cal = max(new_nutrition[first_k, 0].item(), 1.0)
                        cumulative_prot = new_nutrition[first_k, 1].item()
                        current_prot_pct = (cumulative_prot * 4) / cumulative_cal * 100
                        prot_debt_pct = max(0.0, self.protein_pct_target - current_prot_pct)

                        if prot_debt_pct > 0.5:
                            side_prot_g = self.db.nutrition[all_side_indices.long(), 1].float()
                            # Scale: $0.08/g protein * debt factor. At 5pp behind, factor=1.
                            # Gentle enough to not destroy cost optimization.
                            debt_factor = min(prot_debt_pct / 5.0, 2.0)
                            side_debt_bonus = side_prot_g * 0.20 * debt_factor
                            side_costs[0] = side_costs[0] - side_debt_bonus

                    # === SIDE LEFTOVER BONUS ===
                    # Prefer sides with more servings (creates leftovers for future meals)
                    # Uses separate side_leftover_value config (default $1.00/serving)
                    if self.config.enable_dynamic_servings:
                        side_recipe_servings = _side_dyn_srv  # reuse dynamic servings
                    else:
                        side_recipe_servings = self.db.servings[all_side_indices.long()]  # [num_sides]
                    side_leftover_servings = (side_recipe_servings - side_needed_for_score).clamp(min=0)
                    # Use same cap formula as mains: max(8, relative)
                    max_side_leftover = max(8.0, slot_servings * self.config.leftover_meals_cap)
                    side_leftover_servings = side_leftover_servings.clamp(max=max_side_leftover)
                    side_leftover_bonus = side_leftover_servings * self.config.side_leftover_value * self.leftover_target
                    side_costs[0] = side_costs[0] - side_leftover_bonus

                    # === SIDE SERVING-MATCH PENALTY ===
                    # Uses decoupled side_leftover_pct_target for independent side leftover control
                    if self.config.enable_serving_filter:
                        ideal_srv = self.ideal_side_servings_per_slot[slot].item()
                        min_acceptable = ideal_srv / self.config.serving_tolerance_mult
                        max_acceptable = ideal_srv * self.config.serving_tolerance_mult

                        if self.side_leftover_pct_target < 0.3:
                            # FRESH DAILY MODE: Strongly penalize excess servings for sides
                            side_excess = (side_recipe_servings - max_acceptable).clamp(min=0)
                            side_serving_penalty = side_excess * self.config.serving_match_weight * self.config.fresh_mode_excess_mult
                        elif self.side_leftover_pct_target >= 0.5:
                            # BATCH COOK MODE: Give BONUS for larger side batches
                            max_bonus_servings = ideal_srv - slot_servings
                            extra_servings = (side_recipe_servings - side_needed_for_score).clamp(min=0, max=max_bonus_servings)
                            bonus_strength = self.side_leftover_pct_target * self.config.batch_bonus_strength_mult
                            side_serving_penalty = -extra_servings * self.config.serving_match_weight * bonus_strength
                        else:
                            side_serving_penalty = torch.zeros_like(side_recipe_servings)

                        # === HARD SERVING CAP FOR SIDES ===
                        # Exclude sides that are WAY over the acceptable range (same as mains)
                        hard_serving_cap = max_acceptable * self.config.hard_serving_cap_mult
                        way_over_mask = side_recipe_servings > hard_serving_cap
                        side_serving_penalty = torch.where(
                            way_over_mask,
                            torch.full_like(side_serving_penalty, 1e4),  # Effectively exclude
                            side_serving_penalty
                        )

                        # === MAX FEED-DAYS CONSTRAINT FOR SIDES (DAILY BALANCE) ===
                        # Same logic as mains: prevent sides from feeding entire week
                        max_servings_for_balance = slot_servings * self.max_feed_days
                        side_excess_for_balance = (side_recipe_servings - max_servings_for_balance).clamp(min=0)
                        # Penalty: $2 per excess serving beyond max_feed_days worth
                        side_balance_penalty = side_excess_for_balance * 2.0
                        side_serving_penalty = side_serving_penalty + side_balance_penalty

                        side_costs[0] = side_costs[0] + side_serving_penalty

                    # === VARIETY FILTER FOR SIDES (OPTIMIZED: scatter/gather) ===
                    # Get recipe IDs for all sides
                    all_side_recipe_ids = self.db.recipe_ids[all_side_indices.long()]  # [num_sides]

                    # Check against ALL frontiers' cooldowns (blocked if in ANY frontier)
                    # Flatten all cooldown IDs across all frontiers, build global mask
                    all_cooldown_ids = new_used_ids.flatten().unique()  # All unique IDs in cooldown
                    # FIX: Filter out sentinel values (-1, 0) before using as indices
                    all_cooldown_ids = all_cooldown_ids[all_cooldown_ids > 0]
                    if all_cooldown_ids.numel() == 0:
                        # No valid cooldown IDs, all sides are available
                        max_id = int(all_side_recipe_ids.max().item()) + 1
                    else:
                        max_id = max(all_side_recipe_ids.max().item(), all_cooldown_ids.max().item()) + 1
                    cooldown_mask = torch.zeros(max_id, dtype=torch.bool, device=self.device)
                    if all_cooldown_ids.numel() > 0:
                        cooldown_mask[all_cooldown_ids] = True
                    in_cooldown = cooldown_mask[all_side_recipe_ids]  # [num_sides]
                    del cooldown_mask, all_cooldown_ids

                    # Apply variety penalty
                    side_costs[0, in_cooldown] = float('inf')

                    # === SERVINGS FILTER FOR SIDES ===
                    # Sides must produce enough servings for full attendance
                    # With DYNAMIC SERVINGS: Use computed servings based on target cal/srv
                    if self.config.enable_dynamic_servings:
                        all_side_servings, _ = self._compute_dynamic_servings(
                            all_side_indices, slot, meal_type, 'side'
                        )
                    else:
                        all_side_servings = self.db.servings[all_side_indices.long()].float()  # [num_sides]
                    low_side_servings = all_side_servings < side_needed_for_score  # [num_sides]
                    side_costs[0, low_side_servings] += 10000.0  # Penalize low-serving sides

                    # === HIGH CALORIE CAP FOR SIDES ===
                    # Sides should not exceed 40% of daily calories per serving
                    # For 2000 cal/day → max 800 cal/srv for sides
                    # With DYNAMIC SERVINGS: Cal/srv is normalized, so compute effective cal/srv
                    daily_cal_for_cap = self._per_person_daily_calories()
                    side_max_cal_per_srv = daily_cal_for_cap * 0.40
                    if self.config.enable_dynamic_servings:
                        all_side_cal_per_srv = self.db.total_calories[all_side_indices.long()] / all_side_servings.clamp(min=1)
                    else:
                        all_side_cal_per_srv = self.db.nutrition[all_side_indices.long(), 0]  # [num_sides]
                    high_cal_sides = all_side_cal_per_srv > side_max_cal_per_srv  # [num_sides]
                    # HARD EXCLUDE: Set to infinity so these are never selected
                    side_costs[0, high_cal_sides] = float('inf')

                    # === PROTEIN SOURCE DIVERSITY: avoid main+side same protein ===
                    # Pre-compute protein sources for all candidate sides
                    all_side_protein_src = self.db.protein_source[all_side_indices.long()]  # [num_sides]

                    # For each template, find cheapest VALID side
                    for tid, frontier_list in template_to_frontiers.items():
                        if tid not in template_side_ranges:
                            continue
                        start, end = template_side_ranges[tid]
                        template_costs = side_costs[0, start:end].clone()  # [num_template_sides]

                        # === KOSHER MEAT+DAIRY SEPARATION (sides) ===
                        # If any frontier's main has meat, exclude dairy sides (and vice versa)
                        if self.kosher_mode and self.recipe_has_meat is not None:
                            main_db_indices = selected_main_db_idx[frontier_list].long()
                            any_main_has_meat = self.recipe_has_meat[main_db_indices].any().item()
                            any_main_has_dairy = self.recipe_has_dairy[main_db_indices].any().item()
                            side_indices_in_range = all_side_indices[start:end]
                            if any_main_has_meat:
                                # Main has meat - exclude dairy sides
                                dairy_sides = self.recipe_has_dairy[side_indices_in_range.long()]
                                template_costs[dairy_sides] = float('inf')
                            if any_main_has_dairy:
                                # Main has dairy - exclude meat sides
                                meat_sides = self.recipe_has_meat[side_indices_in_range.long()]
                                template_costs[meat_sides] = float('inf')

                        # Penalize sides with same protein source as main
                        # Use majority protein source across this template's frontiers
                        main_sources = self.db.protein_source[selected_main_db_idx[frontier_list].long()]
                        valid_sources = main_sources[main_sources >= 0]
                        if len(valid_sources) > 0:
                            main_protein_src = valid_sources[0].item()  # Use first frontier's source
                            side_sources = all_side_protein_src[start:end]
                            same_source = (side_sources == main_protein_src)
                            # Heavy penalty: $50/srv pushes same-source sides way down
                            # but doesn't hard-exclude (inf), so it falls back if no alternative
                            template_costs[same_source] += 50.0

                        best_pos = self._stable_argmin(template_costs, dim=0)
                        best_side_db_idx = all_side_indices[start + best_pos]

                        # Assign to all frontiers with this template
                        for k in frontier_list:
                            side_ids[k] = self.db.recipe_ids[best_side_db_idx].long()
                            side_names[k] = self.db.names[best_side_db_idx.item()]

                        # Apply side nutrition for these frontiers (vectorized)
                        # Use actual servings eaten: min(recipe_servings, slot_servings)
                        k_tensor = torch.tensor(frontier_list, device=self.device)
                        side_nutr = self.db.nutrition[best_side_db_idx].float()

                        # With DYNAMIC SERVINGS: Use computed servings and adjusted cal/srv
                        if self.config.enable_dynamic_servings:
                            side_idx_tensor = best_side_db_idx.unsqueeze(0)
                            side_dyn_srv, _ = self._compute_dynamic_servings(side_idx_tensor, slot, meal_type, 'side')
                            side_recipe_servings = side_dyn_srv[0]
                            # Adjust nutrition per dynamic serving
                            total_side_cal = self.db.total_calories[best_side_db_idx]
                            dyn_cal_per_srv = total_side_cal / side_recipe_servings.clamp(min=1)
                            # Scale other nutrients proportionally
                            orig_cal_per_srv = side_nutr[0]
                            if orig_cal_per_srv > 0:
                                scale = dyn_cal_per_srv / orig_cal_per_srv
                                side_nutr = side_nutr * scale
                        else:
                            side_recipe_servings = self.db.servings[best_side_db_idx].float()

                        # Account for partial side leftover consumption: only eat what's still needed
                        # side_total_consumed[k] tells how many servings frontier k already ate from leftovers
                        side_already_eaten = side_total_consumed[k_tensor]  # [num_k]
                        side_still_needed = (slot_servings - side_already_eaten).clamp(min=0)  # [num_k]
                        side_servings_avail = side_recipe_servings.item()
                        side_servings_eaten_per_k = torch.minimum(
                            side_still_needed,
                            torch.full_like(side_still_needed, side_servings_avail)
                        )  # [num_k]

                        fresh_side_cal = side_nutr[0] * side_servings_eaten_per_k  # [num_k]
                        fresh_side_prot = side_nutr[1] * side_servings_eaten_per_k
                        fresh_side_carbs = side_nutr[2] * side_servings_eaten_per_k
                        fresh_side_fat = side_nutr[3] * side_servings_eaten_per_k
                        new_nutrition[k_tensor, 0] += fresh_side_cal  # calories
                        new_nutrition[k_tensor, 1] += fresh_side_prot  # protein
                        new_nutrition[k_tensor, 2] += fresh_side_carbs  # carbs
                        new_nutrition[k_tensor, 3] += fresh_side_fat  # fat
                        # Phase 3: Update daily nutrition tracking
                        new_daily_nutrition[k_tensor, day, 0] += fresh_side_cal
                        new_daily_nutrition[k_tensor, day, 1] += fresh_side_prot
                        new_daily_nutrition[k_tensor, day, 2] += fresh_side_carbs
                        new_daily_nutrition[k_tensor, day, 3] += fresh_side_fat
                        for event_i, k_local in enumerate(k_tensor.tolist()):
                            servings_eaten = float(side_servings_eaten_per_k[event_i].item())
                            if servings_eaten <= 0:
                                continue
                            event = {
                                'role': 'side1',
                                'source': 'fresh',
                                'recipe_id': int(side_ids[k_local].item()),
                                'servings': servings_eaten,
                                'cal_per_serving': float(side_nutr[0].item()),
                                'protein_per_serving': float(side_nutr[1].item()),
                                'carbs_per_serving': float(side_nutr[2].item()),
                                'fat_per_serving': float(side_nutr[3].item()),
                            }
                            audit_events[k_local].append(event)

                        # Use first frontier's servings for food group tracking (representative)
                        side_servings_eaten = side_servings_eaten_per_k[0].item()
                        # Apply side food groups (vegetables, fruits)
                        side_food_grp = self.db.food_groups[best_side_db_idx].float()  # [7]
                        new_food_groups[k_tensor, 0] += side_food_grp[0] * side_servings_eaten_per_k  # vegetables
                        new_food_groups[k_tensor, 1] += side_food_grp[1] * side_servings_eaten_per_k  # fruits

                        # Update variety ring
                        ptr = new_used_ptr[k_tensor] % COOLDOWN_LEN
                        new_used_ids[k_tensor, ptr] = side_ids[k_tensor]
                        new_used_ptr[k_tensor] += 1

                        # === APPLY SIDE DISH COST AND PANTRY (was missing!) ===
                        # Side dishes need to actually cost something and consume ingredients
                        # for every frontier that receives them. Side choice is still based on
                        # a representative frontier, but transition accounting must not make
                        # non-representative beams eat free sides.
                        side_ing_idx = self._recipe_ing_idx_long[best_side_db_idx]  # [MAX_NNZ]
                        # side_recipe_servings already computed above (original or dynamic)

                        # Calculate ingredients for side dish
                        # Use original servings for ingredient amounts (recipe total doesn't change)
                        side_full_amt = self._recipe_full_amounts[best_side_db_idx]  # Full batch

                        # Gather pantry at ingredient positions
                        side_ing_idx_long = side_ing_idx
                        side_ing_idx_expanded = side_ing_idx_long.unsqueeze(0).expand(k_tensor.shape[0], -1)
                        pantry_at_side_ing = new_pantries[
                            k_tensor.view(-1, 1),
                            side_ing_idx_expanded,
                        ]  # [num_k, MAX_NNZ]

                        # Compute take/buy for side dish
                        side_full_amt_expanded = side_full_amt.unsqueeze(0)
                        side_take = torch.minimum(pantry_at_side_ing, side_full_amt_expanded)
                        side_to_buy = (side_full_amt - side_take).clamp(min=0)

                        # Package purchasing for side
                        side_pkg_sizes = self._recipe_pkg_option_sizes[best_side_db_idx]  # [MAX_NNZ, P]
                        side_pkg_prices = self._recipe_pkg_option_prices[best_side_db_idx]  # [MAX_NNZ, P]
                        side_num_pkg, side_selected_sizes, side_selected_prices, side_purchased_grams, side_ingredient_cost, side_pkg_option_idx = self._choose_package_options(
                            side_to_buy,
                            side_pkg_sizes,
                            side_pkg_prices,
                            getattr(self.config, "package_remainder_choice_penalty_per_kg", 0.0),
                            return_indices=True,
                        )

                        if self.debug_trace:
                            for event_i, k_local in enumerate(k_tensor.tolist()):
                                purchase_ingredients = self._debug_purchase_ingredients(
                                    side_ing_idx_expanded[event_i],
                                    side_full_amt,
                                    side_take[event_i],
                                    side_to_buy[event_i],
                                    side_num_pkg[event_i],
                                    side_selected_sizes[event_i],
                                    side_selected_prices[event_i],
                                )
                                for event in reversed(audit_events[k_local]):
                                    if (
                                        event.get('role') == 'side1'
                                        and event.get('source') == 'fresh'
                                        and event.get('recipe_id') == int(side_ids[k_local].item())
                                        and 'purchase_ingredients' not in event
                                    ):
                                        event['purchase_ingredients'] = purchase_ingredients
                                        break

                        side_cost_actual = torch.round(
                            side_ingredient_cost.float().sum(dim=1) * 100.0
                        ).float() / 100.0
                        new_cost[k_tensor] += side_cost_actual
                        new_objective_cost[k_tensor] += side_cost_actual

                        # Pantry delta for side (excess - take)
                        side_excess = side_purchased_grams - side_to_buy
                        side_pantry_delta = side_excess - side_take  # [MAX_NNZ]

                        num_ing = new_pantries.shape[1]
                        side_flat_idx = k_tensor.view(-1, 1) * num_ing + side_ing_idx_expanded
                        self._deterministic_scatter_add(
                            new_pantries.view(-1),
                            0,
                            side_flat_idx.flatten(),
                            side_pantry_delta.flatten(),
                        )
                        acquired_per_k = side_purchased_grams.sum(dim=1)
                        consumed_per_k = side_take.sum(dim=1)
                        new_acquired_grams[k_tensor] += acquired_per_k
                        new_consumed_grams[k_tensor] += consumed_per_k
                        self._deterministic_scatter_add(
                            new_ingredient_acquired_grams.view(-1),
                            0,
                            side_flat_idx.flatten(),
                            side_purchased_grams.flatten(),
                        )
                        self._deterministic_scatter_add(
                            new_ingredient_purchase_costs.view(-1),
                            0,
                            side_flat_idx.flatten(),
                            side_ingredient_cost.flatten(),
                        )
                        self._deterministic_scatter_add(
                            new_ingredient_consumed_grams.view(-1),
                            0,
                            side_flat_idx.flatten(),
                            side_take.flatten(),
                        )
                        self._deterministic_scatter_add(
                            new_ingredient_recipe_used_grams.view(-1),
                            0,
                            side_flat_idx.flatten(),
                            side_full_amt_expanded.expand_as(side_take).flatten(),
                        )

                        # Track per-ingredient side dish packages
                        self._deterministic_scatter_add(
                            new_ingredient_packages.view(-1),
                            0,
                            side_flat_idx.flatten(),
                            side_num_pkg.flatten(),
                        )

                        # Track frozen vs fresh consumption for side dish
                        side_frozen_at_ing = new_pantry_frozen[
                            k_tensor.view(-1, 1),
                            side_ing_idx_expanded,
                        ]  # [num_k, MAX_NNZ]
                        side_frozen_consumed = (side_take * side_frozen_at_ing.float()).sum(dim=1)
                        side_fresh_consumed = consumed_per_k - side_frozen_consumed
                        new_pantry_frozen_consumed[k_tensor] += side_frozen_consumed
                        new_pantry_fresh_consumed[k_tensor] += side_fresh_consumed

                        # Track urgency for side dish
                        side_ttl_at_ing = new_pantry_ttl[
                            k_tensor.view(-1, 1),
                            side_ing_idx_expanded,
                        ]  # [num_k, MAX_NNZ]
                        side_is_urgent = (side_ttl_at_ing < 7) & (side_take > 0)  # [MAX_NNZ]
                        side_urgent_count = side_is_urgent.sum(dim=1).float()
                        new_urgent_ingredients_used[k_tensor] += side_urgent_count

                        # Reset TTL for purchased side ingredients
                        side_purchased = side_num_pkg > 0  # [MAX_NNZ]
                        if side_purchased.any():
                            side_recipe_indices = best_side_db_idx.expand(k_tensor.shape[0])
                            purchase_ttl = self._purchase_ttl_for_recipe_positions(
                                side_recipe_indices,
                                side_ing_idx_expanded,
                                side_pkg_option_idx,
                            )  # [num_k, MAX_NNZ]
                            purchase_frozen = self._purchase_frozen_for_recipe_positions(
                                side_recipe_indices,
                                side_ing_idx_expanded,
                                side_pkg_option_idx,
                            )  # [num_k, MAX_NNZ]
                            update_idx = side_flat_idx[side_purchased]
                            new_pantry_ttl.view(-1).index_copy_(0, update_idx, purchase_ttl[side_purchased])
                            new_pantry_frozen.view(-1).index_copy_(0, update_idx, purchase_frozen[side_purchased])

                        # === SIDE DISH LEFTOVER CREATION (VECTORIZED) ===
                        # We cook the full side recipe batch, eat side_servings_eaten, store the rest
                        side_leftover_srv = (side_recipe_servings - side_servings_eaten_per_k).clamp(min=0)
                        side_batch_grams = side_full_amt.sum()
                        side_leftover_grams = side_batch_grams * (
                            side_leftover_srv / side_recipe_servings.clamp(min=1.0)
                        )
                        has_leftover = side_leftover_srv > 0.5
                        if has_leftover.any():  # Has at least 1 serving leftover
                            # Batch process all frontiers in this template group
                            k_leftovers = new_leftovers[k_tensor]  # [num_k, L, LEFTOVER_FIELDS]
                            empty_mask = k_leftovers[:, :, 0] == 0  # [num_k, L]
                            has_empty = empty_mask.any(dim=1)  # [num_k]
                            store_mask = has_leftover & has_empty

                            if store_mask.any():
                                # Find first empty slot for each frontier
                                first_empty = empty_mask.long().argmax(dim=1)  # [num_k]
                                store_k = k_tensor[store_mask]
                                store_slots = first_empty[store_mask]
                                side_id = self.db.recipe_ids[best_side_db_idx].float()

                                # Batch update all leftover slots
                                new_leftovers[store_k, store_slots, 0] = side_id
                                new_leftovers[store_k, store_slots, 1] = side_leftover_srv[store_mask]
                                new_leftovers[store_k, store_slots, 2] = self.leftover_ttl
                                new_leftovers[store_k, store_slots, 3] = side_nutr[0]
                                new_leftovers[store_k, store_slots, 4] = side_nutr[1]
                                new_leftovers[store_k, store_slots, 5] = meal_idx
                                new_leftovers[store_k, store_slots, 6] = 0  # Fresh, not frozen
                                new_leftovers[store_k, store_slots, 7] = 2  # dish_type: 2=side (0=any, 1=main)
                                new_leftovers[store_k, store_slots, 8] = tid  # template_id
                                new_leftovers[store_k, store_slots, 9] = side_leftover_grams[store_mask]

                        # === SECOND SIDE DISH (calorie gap filling) ===
                        # If enabled, add a second side when main + side1 calories are low
                        if self.config.enable_second_side:
                            # Get current-slot calories from leftovers + main + side1 for the
                            # first frontier in this template group. `new_nutrition` is
                            # cumulative week nutrition, so compare against the parent's
                            # pre-slot daily total to avoid disabling side2 after breakfast.
                            first_k = frontier_list[0]
                            parent_for_first = parent_idx[first_k]
                            before_slot_cal = daily_nutrition[parent_for_first, day, 0].item()
                            delivered_cal = new_daily_nutrition[first_k, day, 0].item() - before_slot_cal

                            # Calculate calorie gap ratio
                            slot_cal_target = self.cal_target_per_slot[slot].item()  # From attendance schedule
                            gap_ratio = delivered_cal / max(slot_cal_target, 1.0)

                            if gap_ratio < self.config.side2_calorie_gap_threshold:
                                # Need a second side - select from remaining candidates
                                # Exclude the first side AND its entire pool for diversity
                                side2_mask = torch.ones(end - start, dtype=torch.bool, device=self.device)
                                side2_mask[best_pos] = False  # Exclude first side recipe

                                # Pool diversity: exclude all sides from the same pool as side1
                                side1_pool_id = all_side_pool_ids[start + best_pos]
                                template_pool_ids = all_side_pool_ids[start:end]
                                same_pool_mask = (template_pool_ids == side1_pool_id)
                                side2_mask = side2_mask & ~same_pool_mask  # Exclude same pool

                                # NEW: Calorie ceiling check - exclude sides that would exceed target
                                # Get calorie per serving for all candidate sides
                                side2_indices = all_side_indices[start:end]
                                if self.config.enable_dynamic_servings:
                                    _s2_dyn, _ = self._compute_dynamic_servings(side2_indices, slot, meal_type, 'side')
                                    side2_cal_per_srv = self.db.total_calories[side2_indices.long()] / _s2_dyn.clamp(min=1)
                                    side2_recipe_servings_all = _s2_dyn
                                else:
                                    side2_cal_per_srv = self.db.nutrition[side2_indices.long(), 0]  # [num_sides]
                                    side2_recipe_servings_all = self.db.servings[side2_indices.long()].float()
                                side2_servings_eaten_all = torch.minimum(side2_recipe_servings_all,
                                                                         torch.tensor(slot_servings, device=self.device))
                                side2_cal_contribution = side2_cal_per_srv * side2_servings_eaten_all

                                # Only allow sides that keep us under the calorie ceiling
                                calorie_ceiling = slot_cal_target * self.config.calorie_ceiling_pct
                                would_exceed = (delivered_cal + side2_cal_contribution) > calorie_ceiling
                                side2_mask = side2_mask & ~would_exceed

                                if side2_mask.sum() > 0:
                                    # FIX: Recalculate costs with UPDATED pantry (after main+side1)
                                    # Old bug: reused template_costs from before side1 was purchased
                                    side2_indices = all_side_indices[start:end]
                                    side2_fresh_costs = self._compute_incremental_cost(
                                        new_pantries[first_k:first_k+1], side2_indices, slot_servings=slot_servings
                                    )  # [1, num_template_sides]
                                    if getattr(self.config, 'enable_at_risk_pantry_rescue', False):
                                        side2_rescue_credit = self._compute_at_risk_pantry_rescue_credit(
                                            new_pantries[first_k:first_k+1],
                                            side2_indices,
                                            new_pantry_ttl[first_k:first_k+1],
                                            new_pantry_frozen[first_k:first_k+1],
                                        )
                                        side2_fresh_costs -= side2_rescue_credit
                                    side2_template_costs = side2_fresh_costs[0].clone()
                                    side2_template_costs[~side2_mask] = float('inf')

                                    # NEW: Calorie-fit penalty - prefer sides that fill gap precisely
                                    # Penalize sides that overshoot the calorie gap
                                    calorie_gap = slot_cal_target - delivered_cal  # What we actually need
                                    overshoot = (side2_cal_contribution[side2_mask] - calorie_gap).clamp(min=0)
                                    # Apply penalty: $0.005/cal overshoot (50 cal overshoot = $0.25 penalty)
                                    side2_template_costs[side2_mask] += overshoot * 0.005

                                    # If prefer produce, boost vegetable/fruit sides
                                    if self.config.side2_prefer_produce:
                                        side2_food_grp = self.db.food_groups[side2_indices.long()]  # [num_sides, 7]
                                        is_produce = (side2_food_grp[:, 0] > 0) | (side2_food_grp[:, 1] > 0)  # veg or fruit
                                        side2_template_costs = side2_template_costs - is_produce.float() * 2.0  # $2 bonus

                                    # Select best side2 (lowest cost after penalties)
                                    best_side2_pos = self._stable_argmin(side2_template_costs, dim=0)
                                    best_side2_db_idx = all_side_indices[start + best_side2_pos]

                                    # Assign side2 to all frontiers in this template group
                                    for k in frontier_list:
                                        side2_ids[k] = self.db.recipe_ids[best_side2_db_idx].long()
                                        side2_names[k] = self.db.names[best_side2_db_idx.item()]

                                    # Apply side2 nutrition
                                    side2_nutr = self.db.nutrition[best_side2_db_idx].float().clone()

                                    # With DYNAMIC SERVINGS: Use computed servings and adjusted cal/srv
                                    if self.config.enable_dynamic_servings:
                                        side2_idx_tensor = best_side2_db_idx.unsqueeze(0)
                                        side2_dyn_srv, _ = self._compute_dynamic_servings(side2_idx_tensor, slot, meal_type, 'side')
                                        side2_recipe_servings = side2_dyn_srv[0]
                                        # Adjust nutrition per dynamic serving
                                        total_side2_cal = self.db.total_calories[best_side2_db_idx]
                                        dyn_cal_per_srv = total_side2_cal / side2_recipe_servings.clamp(min=1)
                                        # Scale other nutrients proportionally
                                        orig_cal_per_srv = side2_nutr[0]
                                        if orig_cal_per_srv > 0:
                                            scale = dyn_cal_per_srv / orig_cal_per_srv
                                            side2_nutr = side2_nutr * scale
                                    else:
                                        side2_recipe_servings = self.db.servings[best_side2_db_idx].float()

                                    side2_servings_eaten = min(side2_recipe_servings.item(), slot_servings)
                                    k_tensor = torch.tensor(frontier_list, device=self.device)
                                    new_nutrition[k_tensor, 0] += side2_nutr[0] * side2_servings_eaten
                                    new_nutrition[k_tensor, 1] += side2_nutr[1] * side2_servings_eaten
                                    new_nutrition[k_tensor, 2] += side2_nutr[2] * side2_servings_eaten
                                    new_nutrition[k_tensor, 3] += side2_nutr[3] * side2_servings_eaten
                                    # Update daily nutrition tracking (was missing — caused daily totals to under-report)
                                    new_daily_nutrition[k_tensor, day, 0] += side2_nutr[0] * side2_servings_eaten
                                    new_daily_nutrition[k_tensor, day, 1] += side2_nutr[1] * side2_servings_eaten
                                    new_daily_nutrition[k_tensor, day, 2] += side2_nutr[2] * side2_servings_eaten
                                    new_daily_nutrition[k_tensor, day, 3] += side2_nutr[3] * side2_servings_eaten
                                    for event_i, k_local in enumerate(k_tensor.tolist()):
                                        if side2_servings_eaten <= 0:
                                            continue
                                        event = {
                                            'role': 'side2',
                                            'source': 'fresh',
                                            'recipe_id': int(side2_ids[k_local].item()),
                                            'servings': float(side2_servings_eaten),
                                            'cal_per_serving': float(side2_nutr[0].item()),
                                            'protein_per_serving': float(side2_nutr[1].item()),
                                            'carbs_per_serving': float(side2_nutr[2].item()),
                                            'fat_per_serving': float(side2_nutr[3].item()),
                                        }
                                        audit_events[k_local].append(event)

                                    # Apply side2 food groups
                                    side2_food_grp_single = self.db.food_groups[best_side2_db_idx].float()
                                    new_food_groups[k_tensor, 0] += side2_food_grp_single[0] * side2_servings_eaten
                                    new_food_groups[k_tensor, 1] += side2_food_grp_single[1] * side2_servings_eaten

                                    # Update variety ring for side2
                                    ptr2 = new_used_ptr[k_tensor] % COOLDOWN_LEN
                                    new_used_ids[k_tensor, ptr2] = side2_ids[k_tensor]
                                    new_used_ptr[k_tensor] += 1

                                    # Apply side2 cost and pantry (same pattern as side1)
                                    side2_ing_idx = self._recipe_ing_idx_long[best_side2_db_idx]
                                    side2_full_amt = self._recipe_full_amounts[best_side2_db_idx]

                                    side2_ing_idx_long = side2_ing_idx
                                    side2_ing_idx_expanded = side2_ing_idx_long.unsqueeze(0).expand(k_tensor.shape[0], -1)
                                    pantry_at_side2_ing = new_pantries[
                                        k_tensor.view(-1, 1),
                                        side2_ing_idx_expanded,
                                    ]
                                    side2_full_amt_expanded = side2_full_amt.unsqueeze(0)
                                    side2_take = torch.minimum(pantry_at_side2_ing, side2_full_amt_expanded)
                                    side2_to_buy = (side2_full_amt - side2_take).clamp(min=0)

                                    side2_pkg_sizes = self._recipe_pkg_option_sizes[best_side2_db_idx]
                                    side2_pkg_prices = self._recipe_pkg_option_prices[best_side2_db_idx]
                                    side2_num_pkg, side2_selected_sizes, side2_selected_prices, side2_purchased_grams, side2_ingredient_cost, side2_pkg_option_idx = self._choose_package_options(
                                        side2_to_buy,
                                        side2_pkg_sizes,
                                        side2_pkg_prices,
                                        getattr(self.config, "package_remainder_choice_penalty_per_kg", 0.0),
                                        return_indices=True,
                                    )

                                    if self.debug_trace:
                                        for event_i, k_local in enumerate(k_tensor.tolist()):
                                            purchase_ingredients = self._debug_purchase_ingredients(
                                                side2_ing_idx_expanded[event_i],
                                                side2_full_amt,
                                                side2_take[event_i],
                                                side2_to_buy[event_i],
                                                side2_num_pkg[event_i],
                                                side2_selected_sizes[event_i],
                                                side2_selected_prices[event_i],
                                            )
                                            for event in reversed(audit_events[k_local]):
                                                if (
                                                    event.get('role') == 'side2'
                                                    and event.get('source') == 'fresh'
                                                    and event.get('recipe_id') == int(side2_ids[k_local].item())
                                                    and 'purchase_ingredients' not in event
                                                ):
                                                    event['purchase_ingredients'] = purchase_ingredients
                                                    break

                                    side2_cost_actual = torch.round(
                                        side2_ingredient_cost.float().sum(dim=1) * 100.0
                                    ).float() / 100.0
                                    new_cost[k_tensor] += side2_cost_actual
                                    new_objective_cost[k_tensor] += side2_cost_actual

                                    # Track per-ingredient side2 packages
                                    num_ing = new_pantries.shape[1]
                                    side2_flat_idx = k_tensor.view(-1, 1) * num_ing + side2_ing_idx_expanded
                                    self._deterministic_scatter_add(
                                        new_ingredient_packages.view(-1),
                                        0,
                                        side2_flat_idx.flatten(),
                                        side2_num_pkg.flatten(),
                                    )
                                    self._deterministic_scatter_add(
                                        new_ingredient_acquired_grams.view(-1),
                                        0,
                                        side2_flat_idx.flatten(),
                                        side2_purchased_grams.flatten(),
                                    )
                                    self._deterministic_scatter_add(
                                        new_ingredient_purchase_costs.view(-1),
                                        0,
                                        side2_flat_idx.flatten(),
                                        side2_ingredient_cost.flatten(),
                                    )
                                    self._deterministic_scatter_add(
                                        new_ingredient_consumed_grams.view(-1),
                                        0,
                                        side2_flat_idx.flatten(),
                                        side2_take.flatten(),
                                    )
                                    self._deterministic_scatter_add(
                                        new_ingredient_recipe_used_grams.view(-1),
                                        0,
                                        side2_flat_idx.flatten(),
                                        side2_full_amt_expanded.expand_as(side2_take).flatten(),
                                    )
                                    new_acquired_grams[k_tensor] += side2_purchased_grams.sum(dim=1)
                                    new_consumed_grams[k_tensor] += side2_take.sum(dim=1)

                                    # Pantry delta for side2
                                    side2_excess = side2_purchased_grams - side2_to_buy
                                    side2_pantry_delta = side2_excess - side2_take
                                    self._deterministic_scatter_add(
                                        new_pantries.view(-1),
                                        0,
                                        side2_flat_idx.flatten(),
                                        side2_pantry_delta.flatten(),
                                    )

                                    side2_purchased = side2_num_pkg > 0
                                    if side2_purchased.any():
                                        side2_recipe_indices = best_side2_db_idx.expand(k_tensor.shape[0])
                                        purchase_ttl = self._purchase_ttl_for_recipe_positions(
                                            side2_recipe_indices,
                                            side2_ing_idx_expanded,
                                            side2_pkg_option_idx,
                                        )
                                        purchase_frozen = self._purchase_frozen_for_recipe_positions(
                                            side2_recipe_indices,
                                            side2_ing_idx_expanded,
                                            side2_pkg_option_idx,
                                        )
                                        update_idx = side2_flat_idx[side2_purchased]
                                        new_pantry_ttl.view(-1).index_copy_(
                                            0,
                                            update_idx,
                                            purchase_ttl[side2_purchased],
                                        )
                                        new_pantry_frozen.view(-1).index_copy_(
                                            0,
                                            update_idx,
                                            purchase_frozen[side2_purchased],
                                        )

                                    # Side2 leftover creation
                                    side2_leftover_srv = side2_recipe_servings.item() - side2_servings_eaten
                                    side2_batch_grams = side2_full_amt.sum().item()
                                    side2_leftover_grams = side2_batch_grams * (side2_leftover_srv / max(side2_recipe_servings.item(), 1.0))
                                    if side2_leftover_srv > 0.5:
                                        k_leftovers = new_leftovers[k_tensor]
                                        empty_mask2 = k_leftovers[:, :, 0] == 0
                                        has_empty2 = empty_mask2.any(dim=1)
                                        if has_empty2.any():
                                            first_empty2 = empty_mask2.long().argmax(dim=1)
                                            store_k2 = k_tensor[has_empty2]
                                            store_slots2 = first_empty2[has_empty2]
                                            side2_id = self.db.recipe_ids[best_side2_db_idx].float()
                                            new_leftovers[store_k2, store_slots2, 0] = side2_id
                                            new_leftovers[store_k2, store_slots2, 1] = side2_leftover_srv
                                            new_leftovers[store_k2, store_slots2, 2] = self.leftover_ttl
                                            new_leftovers[store_k2, store_slots2, 3] = side2_nutr[0]
                                            new_leftovers[store_k2, store_slots2, 4] = side2_nutr[1]
                                            new_leftovers[store_k2, store_slots2, 5] = meal_idx
                                            new_leftovers[store_k2, store_slots2, 6] = 0
                                            new_leftovers[store_k2, store_slots2, 7] = 2  # dish_type=side
                                            new_leftovers[store_k2, store_slots2, 8] = tid
                                            new_leftovers[store_k2, store_slots2, 9] = side2_leftover_grams

                    if self.verbose:
                        print("done", flush=True)

                    # FREE side scoring tensors
                    del all_side_indices, all_side_pool_ids, side_costs
                    del side_food_groups, side_veg_g, side_fruit_g, in_cooldown

            # BUG FIX: When meal is entirely from leftover, show the actual leftover recipe
            # (not the recipe that was selected for potential fresh cooking)
            # This fixes confusing output where "Paneer" appears as leftover but was never cooked
            if meal_entirely_from_leftover.any():
                for k in meal_entirely_from_leftover.nonzero(as_tuple=True)[0].tolist():
                    lo_recipe_id = eaten_leftover_recipe_id[k].item()
                    if lo_recipe_id > 0:
                        # Override the selected main with the actual leftover recipe
                        selected_main_ids[k] = lo_recipe_id
                        # Look up the name for this recipe
                        db_idx = self.db.recipe_id_to_idx.get(lo_recipe_id)
                        if db_idx is not None:
                            main_names[k] = self.db.names[db_idx]

            # Build selection records (OPTIMIZED: batch .tolist() once)
            parent_list = parent_idx.tolist()
            main_id_list = selected_main_ids.tolist()
            side_id_list = side_ids.tolist()
            side2_id_list = side2_ids.tolist()  # Second side dish
            new_cost_list = new_cost.tolist()
            # Leftover tracking flags
            # Use meal_entirely_from_leftover (not ate_from_leftover) for accurate tracking
            # This is TRUE only when the ENTIRE meal came from leftovers (no fresh cooking)
            main_leftover_list = meal_entirely_from_leftover.tolist()
            side_leftover_list = side_from_leftover.tolist()
            # Leftover source info for graduated leftover display
            eaten_lo_rid_list = eaten_leftover_recipe_id.tolist()
            total_lo_consumed_list = total_lo_consumed.tolist()
            side_lo_rid_list = side_lo_recipe_id.tolist()
            side_lo_consumed_list = side_total_consumed.tolist()

            # FREE intermediate tensors AFTER conversion to Python lists
            del parent_idx, filtered_choice_idx, selected_main_db_idx
            del selected_main_ids, is_one_dish, template_ids, side_ids, side2_ids
            cost_list = cost.tolist()

            new_selections = []
            for k in range(new_K):
                parent = parent_list[k]
                prev = list(selections[parent])
                main_id = main_id_list[k]
                side_id = side_id_list[k]
                side2_id = side2_id_list[k]  # Second side (0 if none)
                meal_cost = new_cost_list[k] - cost_list[parent]

                # Look up store-bought alternatives
                main_store_alt = self.store_alternatives.get(str(main_id))
                side_store_alt = self.store_alternatives.get(str(side_id)) if side_id else None
                side2_store_alt = self.store_alternatives.get(str(side2_id)) if side2_id else None

                # Extended tuple with second side + leftover flags + leftover source info:
                # indices 0-12: main_id, side_id, side2_id, main_name, side_name, side2_name, meal_cost,
                #               main_store_alt, side_store_alt, side2_store_alt, main_is_leftover, side_is_leftover, side2_is_leftover
                # indices 13-16: eaten_lo_recipe_id, total_lo_consumed, side_lo_recipe_id, side_lo_consumed
                # index 17: all_lo_sources — list of (recipe_id, servings) for every leftover consumed
                # index 18: audit_events — consumed fresh/leftover serving events for ledger audit
                parent_k = parent_list[k]
                # Remap all_lo_sources from child index to parent's frontier
                lo_sources_for_k = all_lo_sources[k] if k < len(all_lo_sources) else []
                audit_events_for_k = audit_events[k] if k < len(audit_events) else []
                prev.append((main_id, side_id, side2_id, main_names[k], side_names[k], side2_names[k],
                             meal_cost, main_store_alt, side_store_alt, side2_store_alt,
                             main_leftover_list[k], side_leftover_list[k], False,
                             eaten_lo_rid_list[k], total_lo_consumed_list[k],
                             side_lo_rid_list[k], side_lo_consumed_list[k],
                             lo_sources_for_k, audit_events_for_k))
                new_selections.append(prev)

            if dedupe_enabled and new_K > self.K:
                keep_indices = []
                seen_signatures = set()
                for idx, plan in enumerate(new_selections):
                    sig_parts = []
                    for sel in plan:
                        main = _coerce_recipe_id(sel[0]) if len(sel) > 0 else 0
                        side1 = _coerce_recipe_id(sel[1]) if len(sel) > 1 else 0
                        side2 = _coerce_recipe_id(sel[2]) if len(sel) > 2 else 0
                        sig_parts.append(f"{main}:{side1}:{side2}")
                    signature = "|".join(sig_parts)
                    if signature in seen_signatures:
                        continue
                    seen_signatures.add(signature)
                    keep_indices.append(idx)
                    if len(keep_indices) >= self.K:
                        break

                if len(keep_indices) < min(self.K, new_K):
                    kept = set(keep_indices)
                    for idx in range(new_K):
                        if idx in kept:
                            continue
                        keep_indices.append(idx)
                        if len(keep_indices) >= self.K:
                            break

                if len(keep_indices) < new_K:
                    keep_tensor = torch.tensor(keep_indices, dtype=torch.long, device=self.device)
                    new_pantries = new_pantries[keep_tensor]
                    new_nutrition = new_nutrition[keep_tensor]
                    new_food_groups = new_food_groups[keep_tensor]
                    new_cost = new_cost[keep_tensor]
                    new_objective_cost = new_objective_cost[keep_tensor]
                    new_leftovers = new_leftovers[keep_tensor]
                    new_used_ids = new_used_ids[keep_tensor]
                    new_used_ptr = new_used_ptr[keep_tensor]
                    new_protein_counts = new_protein_counts[keep_tensor]
                    new_acquired_grams = new_acquired_grams[keep_tensor]
                    new_consumed_grams = new_consumed_grams[keep_tensor]
                    new_ingredient_packages = new_ingredient_packages[keep_tensor]
                    new_ingredient_purchase_costs = new_ingredient_purchase_costs[keep_tensor]
                    new_ingredient_acquired_grams = new_ingredient_acquired_grams[keep_tensor]
                    new_ingredient_consumed_grams = new_ingredient_consumed_grams[keep_tensor]
                    new_ingredient_recipe_used_grams = new_ingredient_recipe_used_grams[keep_tensor]
                    new_ingredient_frozen_spoilage_grams = new_ingredient_frozen_spoilage_grams[keep_tensor]
                    new_ingredient_fresh_spoilage_grams = new_ingredient_fresh_spoilage_grams[keep_tensor]
                    new_leftover_consumed = new_leftover_consumed[keep_tensor]
                    new_waste_per_frontier = new_waste_per_frontier[keep_tensor]
                    new_pantry_spoilage = new_pantry_spoilage[keep_tensor]
                    new_pantry_frozen_grams = new_pantry_frozen_grams[keep_tensor]
                    new_pantry_frozen_spoilage = new_pantry_frozen_spoilage[keep_tensor]
                    new_pantry_fresh_spoilage = new_pantry_fresh_spoilage[keep_tensor]
                    new_pantry_frozen_consumed = new_pantry_frozen_consumed[keep_tensor]
                    new_pantry_fresh_consumed = new_pantry_fresh_consumed[keep_tensor]
                    new_max_freezer_slots = new_max_freezer_slots[keep_tensor]
                    new_urgent_ingredients_used = new_urgent_ingredients_used[keep_tensor]
                    new_pantry_ttl = new_pantry_ttl[keep_tensor]
                    new_pantry_frozen = new_pantry_frozen[keep_tensor]
                    new_daily_nutrition = new_daily_nutrition[keep_tensor]
                    new_daily_consumed = new_daily_consumed[keep_tensor]
                    new_selections = [new_selections[i] for i in keep_indices]
                    new_K = len(keep_indices)

            # Update state - FREE old tensors first to prevent GPU memory leak
            del pantries, nutrition, food_groups, cost, objective_cost, leftovers
            del used_ids, used_ptr, protein_counts
            del acquired_grams, consumed_grams, leftover_consumed, pantry_spoilage, pantry_frozen_grams, ingredient_packages_bought
            del ingredient_purchase_costs
            del ingredient_acquired_grams, ingredient_consumed_grams, ingredient_recipe_used_grams
            del ingredient_frozen_spoilage_grams, ingredient_fresh_spoilage_grams
            del pantry_frozen_spoilage, pantry_fresh_spoilage, pantry_frozen_consumed, pantry_fresh_consumed
            del max_freezer_slots, urgent_ingredients_used

            pantries = new_pantries
            nutrition = new_nutrition
            food_groups = new_food_groups
            cost = new_cost
            objective_cost = new_objective_cost
            leftovers = new_leftovers
            used_ids = new_used_ids
            used_ptr = new_used_ptr
            protein_counts = new_protein_counts
            acquired_grams = new_acquired_grams
            consumed_grams = new_consumed_grams
            ingredient_packages_bought = new_ingredient_packages
            ingredient_purchase_costs = new_ingredient_purchase_costs
            ingredient_acquired_grams = new_ingredient_acquired_grams
            ingredient_consumed_grams = new_ingredient_consumed_grams
            ingredient_recipe_used_grams = new_ingredient_recipe_used_grams
            ingredient_frozen_spoilage_grams = new_ingredient_frozen_spoilage_grams
            ingredient_fresh_spoilage_grams = new_ingredient_fresh_spoilage_grams
            leftover_consumed = new_leftover_consumed
            waste_per_frontier = new_waste_per_frontier
            pantry_spoilage = new_pantry_spoilage
            pantry_frozen_grams = new_pantry_frozen_grams
            pantry_frozen_spoilage = new_pantry_frozen_spoilage
            pantry_fresh_spoilage = new_pantry_fresh_spoilage
            pantry_frozen_consumed = new_pantry_frozen_consumed
            pantry_fresh_consumed = new_pantry_fresh_consumed
            max_freezer_slots = new_max_freezer_slots
            urgent_ingredients_used = new_urgent_ingredients_used
            pantry_ttl = new_pantry_ttl
            pantry_frozen = new_pantry_frozen
            daily_nutrition = new_daily_nutrition  # Phase 3: daily balance tracking
            daily_consumed_recipe_ids = new_daily_consumed  # Same-day leftover dedup
            selections = new_selections
            K = new_K

            # Decay leftovers at end of day
            if (slot + 1) % 3 == 0:
                reserved_frozen_kg = (pantries * pantry_frozen.float()).sum(dim=1) / 1000.0
                leftovers, waste = self._decay_leftovers_with_freeze(
                    leftovers,
                    reserved_frozen_kg=reserved_frozen_kg,
                )
                waste_per_frontier += waste  # [K] += [K] - track per frontier
                objective_cost += waste * self.config.leftover_waste_penalty

                # === PANTRY TTL DECAY AND AUTO-FREEZE ===
                # Decay TTL for all pantry items (both fresh and frozen expire)
                pantry_ttl = pantry_ttl - 1

                # Auto-freeze items about to expire (TTL <= threshold, has quantity, not already frozen, and freezable)
                has_quantity = pantries > 0  # [K, I]
                about_to_expire = (pantry_ttl <= self.config.auto_freeze_ttl_threshold) & has_quantity & (~pantry_frozen)
                freezable = about_to_expire & self.perishability.freezable_tensor.unsqueeze(0)  # [K, I]

                # === FREEZER CAPACITY CHECK (kg-based) ===
                # Calculate current frozen kg (pantry + leftovers share freezer capacity)
                pantry_frozen_kg = (pantries * pantry_frozen.float()).sum(dim=1) / 1000.0  # [K] kg
                leftover_frozen_kg = torch.where(
                    leftovers[:, :, 6] > 0,
                    leftovers[:, :, 9],
                    torch.zeros_like(leftovers[:, :, 9]),
                ).sum(dim=1) / 1000.0  # [K] kg
                total_frozen_kg = pantry_frozen_kg + leftover_frozen_kg  # [K]

                if self.freezer_capacity_kg > 0:
                    capacity_remaining_kg = (self.freezer_capacity_kg - total_frozen_kg).clamp(min=0).unsqueeze(1)
                    freezable_kg = torch.where(freezable, pantries, torch.zeros_like(pantries)) / 1000.0
                    cumulative_freezable_kg = freezable_kg.cumsum(dim=1)
                    can_freeze = freezable & (cumulative_freezable_kg <= capacity_remaining_kg)
                else:
                    # Unlimited capacity
                    can_freeze = freezable

                # Track how much is being frozen (before modifying state)
                frozen_this_day = (pantries * can_freeze.float()).sum(dim=1)  # [K] grams frozen today
                pantry_frozen_grams += frozen_this_day  # Cumulative frozen grams

                # Freeze eligible items: mark as frozen and reset TTL to freezer shelf life.
                pantry_frozen = pantry_frozen | can_freeze
                pantry_ttl = torch.where(can_freeze, torch.full_like(pantry_ttl, float(self.freezer_ttl)), pantry_ttl)

                # === TRACK FREEZER UTILIZATION ===
                # Update max freezer slots after any new freezing (count-based for legacy metrics)
                new_pantry_frozen_count = pantry_frozen.sum(dim=1)  # [K]
                leftover_frozen_count = (leftovers[:, :, 6] > 0).sum(dim=1)  # [K] count of frozen leftovers
                new_total_frozen = new_pantry_frozen_count + leftover_frozen_count  # [K]
                max_freezer_slots = torch.maximum(max_freezer_slots, new_total_frozen.float())

                # === TRACK SPOILAGE: FROZEN VS FRESH ===
                # Items with TTL < 0 and quantity > 0 have expired
                expired = (pantry_ttl < 0) & has_quantity
                frozen_expired = expired & pantry_frozen  # Frozen items past modeled quality TTL.
                fresh_expired = expired & ~pantry_frozen  # Fresh items that expired (before freeze)

                frozen_spoilage_grams = (pantries * frozen_expired.float()).sum(dim=1)  # [K]
                fresh_spoilage_grams = (pantries * fresh_expired.float()).sum(dim=1)    # [K]
                spoilage_grams = frozen_spoilage_grams + fresh_spoilage_grams  # Total
                new_ingredient_frozen_spoilage_grams += pantries * frozen_expired.float()
                new_ingredient_fresh_spoilage_grams += pantries * fresh_expired.float()

                pantry_frozen_spoilage += frozen_spoilage_grams / 1000.0  # kg
                pantry_fresh_spoilage += fresh_spoilage_grams / 1000.0    # kg
                pantry_spoilage += spoilage_grams / 1000.0  # Total (for backwards compat)
                objective_cost += (spoilage_grams / 1000.0) * self.config.pantry_spoilage_kg_penalty

                if self.freezer_capacity_kg > 0:
                    current_pantry_frozen_kg = (pantries * pantry_frozen.float()).sum(dim=1) / 1000.0
                    current_leftover_frozen_kg = torch.where(
                        leftovers[:, :, 6] > 0,
                        leftovers[:, :, 9],
                        torch.zeros_like(leftovers[:, :, 9]),
                    ).sum(dim=1) / 1000.0
                    freezer_over_kg = (
                        current_pantry_frozen_kg + current_leftover_frozen_kg - self.freezer_capacity_kg
                    ).clamp(min=0)
                    objective_cost += freezer_over_kg * self.config.freezer_over_capacity_kg_penalty

                # Remove expired items from pantry
                pantries = torch.where(expired, torch.zeros_like(pantries), pantries)
                pantry_frozen = torch.where(expired, torch.zeros_like(pantry_frozen), pantry_frozen)  # Clear frozen flag too
                pantry_ttl = torch.where(expired, self.perishability.shelf_life_tensor.unsqueeze(0).expand_as(pantry_ttl), pantry_ttl)

        # Clear CUDA cache ONCE per week (not per day!) to prevent memory fragmentation
        # Moving this outside the daily loop = 14x fewer cache clears = 75x faster
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Extract best frontier. `cost` is reported grocery spend; objective_cost
        # is grocery spend plus internal waste/freezer penalties.
        final_score = objective_cost
        if getattr(self.config, 'enable_terminal_calorie_selection', True):
            total_calories = nutrition[:, 0].float()
            weekly_target = float(self.weekly_calories)
            cal_pct = total_calories / max(weekly_target, 1.0)

            target_pct = getattr(self.config, 'terminal_calorie_target_pct', 1.0)
            floor_pct = getattr(self.config, 'terminal_calorie_floor_pct', 0.95)
            ceiling_pct = getattr(
                self.config,
                'terminal_calorie_ceiling_pct',
                getattr(self.config, 'calorie_ceiling_pct', 1.05),
            )
            ceiling_pct = min(ceiling_pct, getattr(self.config, 'calorie_ceiling_pct', ceiling_pct))
            under_weight = getattr(self.config, 'terminal_calorie_under_weight', 0.04)
            over_weight = getattr(self.config, 'terminal_calorie_over_weight', 0.02)

            under_gap_cal = (target_pct - cal_pct).clamp(min=0.0) * weekly_target
            over_gap_cal = (cal_pct - target_pct).clamp(min=0.0) * weekly_target
            final_score = objective_cost + under_gap_cal * under_weight + over_gap_cal * over_weight

            meets_floor = cal_pct >= floor_pct
            in_band = meets_floor & (cal_pct <= ceiling_pct)
            if getattr(self.config, 'terminal_calorie_hard_ceiling', True) and in_band.any():
                final_score = torch.where(
                    in_band,
                    final_score,
                    torch.full_like(final_score, float('inf')),
                )
            elif getattr(self.config, 'terminal_calorie_hard_floor', True):
                if meets_floor.any():
                    final_score = torch.where(
                        meets_floor,
                        final_score,
                        torch.full_like(final_score, float('inf')),
                    )

        best_idx = self._stable_argmin(final_score, dim=0).item()
        best_objective_cost = objective_cost[best_idx].item()
        trace_final_path = os.environ.get('HESTIA_TRACE_FINAL_PATH')
        if trace_final_path:
            import csv as _csv_trace
            import hashlib as _hashlib_trace

            weekly_target = float(self.weekly_calories)
            protein_target = float(self.weekly_protein)
            trace_calories = nutrition[:, 0].float()
            trace_protein = nutrition[:, 1].float()
            trace_cal_pct = trace_calories / max(weekly_target, 1.0)
            trace_prot_pct = trace_protein / max(protein_target, 1.0)
            floor_pct = getattr(self.config, 'terminal_calorie_floor_pct', 0.95)
            ceiling_pct = getattr(
                self.config,
                'terminal_calorie_ceiling_pct',
                getattr(self.config, 'calorie_ceiling_pct', 1.05),
            )
            ceiling_pct = min(ceiling_pct, getattr(self.config, 'calorie_ceiling_pct', ceiling_pct))
            trace_meets_floor = trace_cal_pct >= floor_pct
            trace_in_band = trace_meets_floor & (trace_cal_pct <= ceiling_pct)
            top_n = int(os.environ.get('HESTIA_TRACE_FINAL_TOP_N', '50'))
            top_n = max(1, min(top_n, final_score.numel()))
            trace_order = self._stable_argsort(final_score, descending=False, dim=0)[:top_n]
            trace_file = Path(trace_final_path)
            write_header = not trace_file.exists()
            with open(trace_file, 'a', newline='') as _f_trace:
                _w = _csv_trace.writer(_f_trace)
                if write_header:
                    _w.writerow([
                        'week_number', 'rank', 'frontier_idx', 'selected', 'cost',
                        'final_score', 'calories', 'cal_pct', 'protein', 'prot_pct',
                        'meets_floor', 'in_band', 'plan_hash', 'plan_signature',
                    ])
                for _rank, _idx_t in enumerate(trace_order.tolist(), start=1):
                    _sig_parts = []
                    for _sel in selections[_idx_t]:
                        _main = _coerce_recipe_id(_sel[0]) if len(_sel) > 0 else 0
                        _side1 = _coerce_recipe_id(_sel[1]) if len(_sel) > 1 else 0
                        _side2 = _coerce_recipe_id(_sel[2]) if len(_sel) > 2 else 0
                        _sig_parts.append(f"{_main}:{_side1}:{_side2}")
                    _signature = "|".join(_sig_parts)
                    _plan_hash = _hashlib_trace.sha1(_signature.encode('utf-8')).hexdigest()[:12]
                    _w.writerow([
                        week_number,
                        _rank,
                        _idx_t,
                        int(_idx_t == best_idx),
                        f"{cost[_idx_t].item():.2f}",
                        f"{final_score[_idx_t].item():.2f}",
                        f"{trace_calories[_idx_t].item():.0f}",
                        f"{trace_cal_pct[_idx_t].item():.4f}",
                        f"{trace_protein[_idx_t].item():.1f}",
                        f"{trace_prot_pct[_idx_t].item():.4f}",
                        int(trace_meets_floor[_idx_t].item()),
                        int(trace_in_band[_idx_t].item()),
                        _plan_hash,
                        _signature,
                    ])
        best_cost = cost[best_idx].item()
        best_nutrition = nutrition[best_idx]
        best_food_groups = food_groups[best_idx]
        best_selections = selections[best_idx]
        best_pantry = pantries[best_idx]
        best_pantry_ttl = pantry_ttl[best_idx]  # [I] - remaining TTL per ingredient
        best_pantry_frozen = pantry_frozen[best_idx]  # [I] - frozen status per ingredient
        best_protein_counts = protein_counts[best_idx].cpu().tolist() if protein_counts is not None else None

        # Collect all used recipe IDs for multi-week persistence
        # IMPORTANT: Use list (not set) to preserve insertion order for cooldown tracking
        used_recipe_ids = []
        seen_recipe_ids = set()  # For deduplication
        for selection in best_selections:
            if not selection:
                continue
            main_id = selection[0]
            side_id = selection[1] if len(selection) > 1 else 0
            if main_id > 0 and main_id not in seen_recipe_ids:
                used_recipe_ids.append(main_id)
                seen_recipe_ids.add(main_id)
            if side_id > 0 and side_id not in seen_recipe_ids:
                used_recipe_ids.append(side_id)
                seen_recipe_ids.add(side_id)

        elapsed = time.time() - start_time

        # Compute leftover stats from best frontier
        best_leftovers = leftovers[best_idx]  # [L, 7]
        has_item = best_leftovers[:, 0] > 0
        is_frozen = best_leftovers[:, 6] > 0
        fresh_mask = has_item & ~is_frozen
        frozen_mask = has_item & is_frozen

        leftover_stats = {
            'fresh_count': fresh_mask.sum().item(),
            'frozen_count': frozen_mask.sum().item(),
            'fresh_servings': best_leftovers[fresh_mask, 1].sum().item() if fresh_mask.any() else 0.0,
            'frozen_servings': best_leftovers[frozen_mask, 1].sum().item() if frozen_mask.any() else 0.0,
            'waste_servings': waste_per_frontier[best_idx].item(),  # Use best frontier only (fixes 100x inflation bug)
            'consumed_servings': leftover_consumed[best_idx].item(),  # Use best frontier only
        }

        # Pantry flow stats - use only best frontier's values (fixes inflation bug)
        best_acquired = acquired_grams[best_idx].item()
        best_consumed = consumed_grams[best_idx].item()
        best_spoilage = pantry_spoilage[best_idx].item()
        best_frozen = pantry_frozen_grams[best_idx].item()
        best_frozen_spoilage = pantry_frozen_spoilage[best_idx].item()
        best_fresh_spoilage = pantry_fresh_spoilage[best_idx].item()
        best_frozen_consumed = pantry_frozen_consumed[best_idx].item()
        best_fresh_consumed = pantry_fresh_consumed[best_idx].item()
        best_max_freezer_slots = max_freezer_slots[best_idx].item()
        best_urgent_used = urgent_ingredients_used[best_idx].item()

        # Current freezer utilization
        best_pantry_frozen_count = pantry_frozen[best_idx].sum().item()
        best_leftover_frozen_count = (leftovers[best_idx, :, 6] > 0).sum().item()
        best_freezer_slots = best_pantry_frozen_count + best_leftover_frozen_count
        best_pantry_freezer_kg = (pantries[best_idx] * pantry_frozen[best_idx].float()).sum().item() / 1000.0
        best_leftover_freezer_kg = torch.where(
            leftovers[best_idx, :, 6] > 0,
            leftovers[best_idx, :, 9],
            torch.zeros_like(leftovers[best_idx, :, 9]),
        ).sum().item() / 1000.0
        best_freezer_kg = best_pantry_freezer_kg + best_leftover_freezer_kg

        pantry_flow = {
            'acquired_grams': best_acquired,
            'consumed_grams': best_consumed,
            'net_grams': best_acquired - best_consumed,
            # Spoilage breakdown
            'spoilage_kg': best_spoilage,               # Total (backwards compat)
            'frozen_spoilage_kg': best_frozen_spoilage, # Frozen items past modeled quality TTL
            'fresh_spoilage_kg': best_fresh_spoilage,   # Fresh items that expired before freeze
            # Freezing stats
            'frozen_grams': best_frozen,                # Grams auto-frozen this week
            # Consumption breakdown
            'frozen_consumed_grams': best_frozen_consumed,  # Consumed from frozen pantry
            'fresh_consumed_grams': best_fresh_consumed,    # Consumed from fresh pantry
            # Freezer utilization
            'freezer_slots_used': best_freezer_slots,       # Current: pantry + leftover frozen count
            'max_freezer_slots': best_max_freezer_slots,    # Max observed during week
            'freezer_kg': best_freezer_kg,                  # Total kg currently in freezer
            'freezer_pantry_kg': best_pantry_freezer_kg,    # Pantry kg currently frozen
            'freezer_leftover_kg': best_leftover_freezer_kg,  # Leftover kg currently frozen
            'freezer_capacity_kg': self.freezer_capacity_kg,  # Capacity limit in kg
            # Urgency system
            'urgent_ingredients_used': best_urgent_used,    # Count of near-expiry items consumed
        }

        ingredient_trace = None
        if self.debug_trace:
            ingredient_trace = {
                'acquired_grams': ingredient_acquired_grams[best_idx].cpu(),
                'consumed_from_pantry_grams': ingredient_consumed_grams[best_idx].cpu(),
                'recipe_used_grams': ingredient_recipe_used_grams[best_idx].cpu(),
                'fresh_spoilage_grams': ingredient_fresh_spoilage_grams[best_idx].cpu(),
                'frozen_spoilage_grams': ingredient_frozen_spoilage_grams[best_idx].cpu(),
            }

        # Food group compliance
        veg_compliance = best_food_groups[0].item() / self.weekly_vegetables_g if self.weekly_vegetables_g > 0 else 0
        fruit_compliance = best_food_groups[1].item() / self.weekly_fruits_g if self.weekly_fruits_g > 0 else 0

        # Macro percentage calculations
        total_cal = best_nutrition[0].item()
        total_prot_g = best_nutrition[1].item()
        total_carbs_g = best_nutrition[2].item()
        total_fat_g = best_nutrition[3].item()

        # Calculate macro percentages using actual calories from database (not derived)
        # protein=4cal/g, carbs=4cal/g, fat=9cal/g
        if total_cal > 0:
            protein_pct = (total_prot_g * 4 / total_cal) * 100
            carbs_pct = (total_carbs_g * 4 / total_cal) * 100
            fat_pct = (total_fat_g * 9 / total_cal) * 100
        else:
            protein_pct = carbs_pct = fat_pct = 0.0

        # === FRUIT SNACK INJECTION ===
        snacks_added = []
        if self.auto_inject_snacks:
            snacks_added = self._inject_fruit_snacks(
                current_cal=total_cal,
                target_cal=self.weekly_calories,
                current_fruit_g=best_food_groups[1].item(),
            )
            # Update totals with snacks
            for snack in snacks_added:
                total_cal += snack['calories']
                best_food_groups[1] += snack['fruit_g']
                best_cost += snack['cost']
                best_objective_cost += snack['cost']
                # Update macros (fruit is mostly carbs)
                total_carbs_g += snack['calories'] / 4 * 0.95  # ~95% of fruit cals from carbs

            # Recalculate fruit compliance if snacks were added
            if snacks_added:
                fruit_compliance = best_food_groups[1].item() / self.weekly_fruits_g if self.weekly_fruits_g > 0 else 0

                # Recalculate macro percentages using actual calories (not derived)
                if total_cal > 0:
                    protein_pct = (total_prot_g * 4 / total_cal) * 100
                    carbs_pct = (total_carbs_g * 4 / total_cal) * 100
                    fat_pct = (total_fat_g * 9 / total_cal) * 100

        if self.verbose:
            print(f"\nUsed {len(used_recipe_ids)} unique recipes this week")
            print(f"Food groups: {best_food_groups[0].item()/1000:.1f}kg vegetables ({veg_compliance*100:.0f}%), "
                  f"{best_food_groups[1].item()/1000:.1f}kg fruits ({fruit_compliance*100:.0f}%)")
            if snacks_added:
                snack_cal = sum(s['calories'] for s in snacks_added)
                snack_names = [s['name'] for s in snacks_added]
                print(f"Snacks added: {snack_names} (+{snack_cal} cal, +${sum(s['cost'] for s in snacks_added):.2f})")
            print(f"Macros: {protein_pct:.1f}% protein, {carbs_pct:.1f}% carbs, {fat_pct:.1f}% fat")
            if leftover_stats['frozen_count'] > 0:
                print(f"Leftover stats: {leftover_stats['fresh_count']} fresh, {leftover_stats['frozen_count']} frozen")
            best_waste = waste_per_frontier[best_idx].item()
            if best_waste > 0:
                print(f"Waste: {best_waste:.1f} servings expired")

        # === SWITCHEROO: Post-processing to improve daily balance ===
        # Swap meals between days to reduce daily calorie variance
        # This is the STANDARD post-processing step for all plans
        daily_target = self.weekly_calories / 7.0
        daily_cals_before = daily_nutrition[best_idx, :, 0].cpu().tolist()

        # Build result dict first (needed by switcheroo)
        result = {
            'total_cost': best_cost,
            'selections': best_selections,
            'daily_nutrition': daily_nutrition[best_idx].cpu(),
        }

        # Apply switcheroo repairs
        if getattr(self.config, 'enable_switcheroo', True):  # ON by default
            try:
                result = repair_plan(
                    result=result,
                    daily_target=daily_target,
                    recipe_db=self.db,
                    servings_per_slot=self.servings_per_slot,
                    target_floor=0.90,
                    target_ceiling=1.10,
                    max_swaps=10,
                    verbose=self.verbose,
                )
                result = repair_with_leftover_substitution(
                    result=result,
                    daily_target=daily_target,
                    recipe_db=self.db,
                    servings_per_slot=self.servings_per_slot,
                    target_floor=0.90,
                    target_ceiling=1.10,
                    verbose=self.verbose,
                )
                daily_cals_after = result.get('daily_calories_repaired', daily_cals_before)

                if self.verbose:
                    before_range = max(daily_cals_before) - min(daily_cals_before)
                    after_range = max(daily_cals_after) - min(daily_cals_after)
                    if after_range < before_range:
                        print(f"Switcheroo: reduced daily range from {before_range:.0f} to {after_range:.0f} cal")
            except Exception as e:
                if self.verbose:
                    print(f"Switcheroo failed: {e}")
                daily_cals_after = daily_cals_before  # Fallback to original
        else:
            daily_cals_after = daily_cals_before  # Switcheroo disabled

        return {
            'total_cost': best_cost,
            'optimization_cost': best_objective_cost,
            'waste_penalty_cost': best_objective_cost - best_cost,
            'selections': best_selections,
            'cal_compliance': total_cal / self.weekly_calories,  # Uses updated total (with snacks)
            'prot_compliance': best_nutrition[1].item() / self.weekly_protein,
            'veg_compliance': veg_compliance,
            'fruit_compliance': fruit_compliance,
            'vegetables_g': best_food_groups[0].item(),
            'fruits_g': best_food_groups[1].item(),
            # Macro tracking
            'protein_g': total_prot_g,
            'carbs_g': total_carbs_g,
            'fat_g': total_fat_g,
            'protein_pct': protein_pct,
            'carbs_pct': carbs_pct,
            'fat_pct': fat_pct,
            # Snack tracking
            'snacks_added': snacks_added,
            'snacks_calories': sum(s['calories'] for s in snacks_added),
            'snacks_cost': sum(s['cost'] for s in snacks_added),
            'final_pantry': best_pantry,
            'final_pantry_ttl': best_pantry_ttl,  # [I] remaining days per ingredient
            'final_pantry_frozen': best_pantry_frozen,  # [I] frozen status per ingredient
            'final_leftovers': best_leftovers,  # For multi-week leftover persistence
            'elapsed_seconds': elapsed,
            'used_recipe_ids': used_recipe_ids,  # For multi-week variety tracking
            'leftover_stats': leftover_stats,
            'pantry_flow': pantry_flow,
            'daily_nutrition': daily_nutrition[best_idx].cpu(),  # Phase 3: [7, 4] daily cal/prot/carbs/fat
            'daily_calories_repaired': daily_cals_after,  # After switcheroo repair (list of 7 floats)
            'protein_quota_counts': best_protein_counts,  # Final protein source distribution
            'ingredient_purchases': ingredient_packages_bought[best_idx].cpu(),  # [num_ingredients] packages bought per ingredient
            'ingredient_purchase_grams': ingredient_acquired_grams[best_idx].cpu(),
            'ingredient_purchase_costs': ingredient_purchase_costs[best_idx].cpu(),
            'ingredient_trace': ingredient_trace,
        }


def run_sparse_cascade():
    """Run the sparse cascade planner."""
    # Use safe data loader to avoid pandas segfault on large DataFrames
    from hestia.data_loader import load_recipes

    print("=" * 70)
    print("SPARSE CASCADE PLANNER")
    print("Memory-efficient meal planning with sparse tensors")
    print("=" * 70)

    # Load recipes using safe method (avoids .to_dict('records') segfault)
    recipe_pool = load_recipes("recipes2.csv")
    print(f"\nLoaded {len(recipe_pool):,} recipes")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}")

    # Build infrastructure
    print("\nBuilding infrastructure...")
    ingredient_index = IngredientIndex(device)
    ingredient_index.build_from_recipes(recipe_pool)

    plate_builder = PlateBuilder()
    plate_builder.index_recipes(recipe_pool)

    package_index = PackageIndex()

    # Build sparse database
    print("Creating sparse database...", flush=True)
    recipe_db = SparseRecipeDatabase(
        recipe_pool, ingredient_index, plate_builder, device
    )
    print("Sparse database created!", flush=True)

    # Load pantry (or start empty for testing)
    USE_EMPTY_PANTRY = False  # Set True to test with empty pantry

    if USE_EMPTY_PANTRY:
        print("\n*** TESTING WITH EMPTY PANTRY ***")
        initial_pantry = torch.zeros(ingredient_index.num_ingredients, device=device)
    else:
        pantry_file = f'{BASE_PATH}/pantry_state.json'
        try:
            with open(pantry_file) as f:
                pantry_dict = json.load(f)
            print(f"\nLoaded pantry: {len(pantry_dict)} ingredients")
        except FileNotFoundError:
            pantry_dict = {}

        initial_pantry = torch.zeros(ingredient_index.num_ingredients, device=device)
        for fpid, grams in pantry_dict.items():
            idx = ingredient_index.fpid_to_idx.get(fpid)
            if idx is not None:
                initial_pantry[idx] = grams

    # Load history
    recent_file = f'{BASE_PATH}/recent_recipes.json'
    try:
        with open(recent_file) as f:
            historical = list(json.load(f))
    except FileNotFoundError:
        historical = []

    # Create planner
    print("\nCreating planner...", flush=True)
    planner = SparseCascadePlanner(
        recipe_db=recipe_db,
        package_index=package_index,
        device=device,
        K=200,  # Balanced beam search with two-pass scoring
        verbose=True,
    )
    print("Planner created!", flush=True)

    # Run planning
    print("\n" + "=" * 70)
    result = planner.start_session(
        initial_pantry=initial_pantry,
        historical_banned_ids=historical,
    ).plan_next_week()

    # Print results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"Total cost: ${result['total_cost']:.2f}")
    print(f"Calorie compliance: {result['cal_compliance']*100:.1f}%")
    print(f"Protein compliance: {result['prot_compliance']*100:.1f}%")
    print(f"Time: {result['elapsed_seconds']:.1f}s")

    # Print meal plan
    print("\n" + "-" * 70)
    print("WEEKLY MEAL PLAN")
    print("-" * 70)

    meal_types = ['Breakfast', 'Lunch', 'Dinner']
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    for i, selection in enumerate(result['selections']):
        # Unpack - supports old 7-tuple and new 10-tuple format with side2
        if len(selection) >= 10:
            # New format with side2: (main_id, side_id, side2_id, main_name, side_name, side2_name, meal_cost, ...)
            main_id, side_id, side2_id, main_name, side_name, side2_name, meal_cost = selection[:7]
            main_store_alt = selection[7] if len(selection) > 7 else None
            side_store_alt = selection[8] if len(selection) > 8 else None
            side2_store_alt = selection[9] if len(selection) > 9 else None
        else:
            # Old format: (main_id, side_id, main_name, side_name, meal_cost, ...)
            main_id, side_id, main_name, side_name, meal_cost = selection[:5]
            side2_id, side2_name = 0, ""
            main_store_alt = selection[5] if len(selection) > 5 else None
            side_store_alt = selection[6] if len(selection) > 6 else None
            side2_store_alt = None

        day_idx = i // 3
        meal_idx = i % 3

        if meal_idx == 0:
            print(f"\n{day_names[day_idx].upper()}")

        # Build dish list
        dishes = [main_name[:30]]
        if side_name:
            dishes.append(side_name[:20])
        if side2_name:
            dishes.append(side2_name[:20])

        dish_str = " + ".join(dishes)
        print(f"  {meal_types[meal_idx]:10} ${meal_cost:5.2f} | {dish_str}")

        # Show store-bought alternatives if available
        if main_store_alt:
            pkg_desc = main_store_alt['package_description']
            pkg_price = main_store_alt['median_price']
            print(f"      {'':10}        → OR buy: {pkg_desc} (${pkg_price:.2f})")
        if side_store_alt:
            pkg_desc = side_store_alt['package_description']
            pkg_price = side_store_alt['median_price']
            print(f"      {'':10}        → OR buy: {pkg_desc} (${pkg_price:.2f})")
        if side2_store_alt:
            pkg_desc = side2_store_alt['package_description']
            pkg_price = side2_store_alt['median_price']
            print(f"      {'':10}        → OR buy: {pkg_desc} (${pkg_price:.2f})")

    return result


if __name__ == "__main__":
    run_sparse_cascade()
