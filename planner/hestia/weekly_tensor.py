"""
GPU Weekly Tensor: Dense tensor representation of weekly candidates.

ALL data on GPU for maximum parallelism. No sparse matrices.

Key tensors:
- nutrition: [NUM_SLOTS, K, NUM_NUTRIENTS] - per-serving nutrition
- costs: [NUM_SLOTS, K] - per-serving cost
- servings: [NUM_SLOTS, K] - servings produced per recipe
- recipe_ids: [NUM_SLOTS, K] - recipe identifiers
- ingredients: [NUM_SLOTS, K, num_ingredients] - ingredient needs per serving

This is O(21 * K * D) storage, NOT O(K^21).
"""

import ast
import torch
from typing import Dict, List, Optional, Tuple
from .data_structures import NUM_SLOTS, NUM_NUTRIENTS, IngredientIndex


class GPUWeeklyTensor:
    """
    Dense GPU tensor representation of weekly meal candidates.

    Stores K candidates per slot, all pre-computed on GPU.
    Enables fully vectorized scoring and selection.
    """

    def __init__(
        self,
        K: int,
        num_ingredients: int,
        device: torch.device,
    ):
        """
        Initialize empty tensor storage.

        Args:
            K: Candidates per slot
            num_ingredients: Size of ingredient vocabulary
            device: GPU device
        """
        self.K = K
        self.num_ingredients = num_ingredients
        self.device = device

        # === CORE TENSORS ===

        # Nutrition per serving: [NUM_SLOTS, K, NUM_NUTRIENTS]
        self.nutrition = torch.zeros(
            NUM_SLOTS, K, NUM_NUTRIENTS,
            dtype=torch.float32, device=device
        )

        # Cost per serving: [NUM_SLOTS, K]
        self.costs = torch.zeros(
            NUM_SLOTS, K,
            dtype=torch.float32, device=device
        )

        # Servings produced by recipe: [NUM_SLOTS, K]
        self.servings = torch.zeros(
            NUM_SLOTS, K,
            dtype=torch.float32, device=device
        )

        # Recipe IDs for variety tracking: [NUM_SLOTS, K]
        # This stores MAIN dish ID only (for backward compatibility)
        self.recipe_ids = torch.zeros(
            NUM_SLOTS, K,
            dtype=torch.long, device=device
        )

        # ALL recipe IDs (main + sides): [NUM_SLOTS, K, MAX_RECIPES_PER_PLATE]
        # Stores main dish + up to 3 side dishes. 0 = empty slot.
        MAX_RECIPES_PER_PLATE = 4  # main + 3 sides max
        self.all_recipe_ids = torch.zeros(
            NUM_SLOTS, K, MAX_RECIPES_PER_PLATE,
            dtype=torch.long, device=device
        )

        # Ingredient needs per serving: [NUM_SLOTS, K, num_ingredients]
        # Dense tensor - trades memory for GPU parallelism
        self.ingredients = torch.zeros(
            NUM_SLOTS, K, num_ingredients,
            dtype=torch.float32, device=device
        )

        # Leftover TTL (days until expiry): [NUM_SLOTS, K]
        self.leftover_ttl = torch.full(
            (NUM_SLOTS, K), 3,
            dtype=torch.float32, device=device
        )

        # Recipe names for debugging (CPU, not used in hot path)
        self.recipe_names: List[List[str]] = [[] for _ in range(NUM_SLOTS)]

        # Template names for debugging (which plate template was used)
        self.template_names: List[List[str]] = [[] for _ in range(NUM_SLOTS)]

    def fill_slot(
        self,
        slot: int,
        candidates: List[Dict],
        ingredient_index: IngredientIndex,
    ) -> None:
        """
        Fill a slot with candidate data.

        Args:
            slot: Slot index (0-20)
            candidates: List of recipe dictionaries
            ingredient_index: Mapping from FPID to dense index
        """
        num_candidates = min(len(candidates), self.K)

        for k in range(num_candidates):
            recipe = candidates[k]
            self._fill_candidate(slot, k, recipe, ingredient_index)

        # Pad remaining slots with copies of last candidate
        if num_candidates < self.K and num_candidates > 0:
            for k in range(num_candidates, self.K):
                # Copy from last valid candidate
                self.nutrition[slot, k] = self.nutrition[slot, num_candidates - 1]
                self.costs[slot, k] = self.costs[slot, num_candidates - 1]
                self.servings[slot, k] = self.servings[slot, num_candidates - 1]
                self.recipe_ids[slot, k] = self.recipe_ids[slot, num_candidates - 1]
                self.all_recipe_ids[slot, k] = self.all_recipe_ids[slot, num_candidates - 1]  # MUST copy all IDs!
                self.ingredients[slot, k] = self.ingredients[slot, num_candidates - 1]
                self.leftover_ttl[slot, k] = self.leftover_ttl[slot, num_candidates - 1]

    def _fill_candidate(
        self,
        slot: int,
        k: int,
        recipe: Dict,
        ingredient_index: IngredientIndex,
    ) -> None:
        """Fill a single candidate slot."""
        # Determine servings
        servings_val = recipe.get("servings.standard_serving_size")
        if servings_val in (None, 0):
            srv_min = recipe.get("servings.min")
            srv_max = recipe.get("servings.max")
            if srv_min and srv_max:
                servings_val = (float(srv_min) + float(srv_max)) / 2
            elif srv_max:
                servings_val = float(srv_max)
            elif srv_min:
                servings_val = float(srv_min)
            else:
                servings_val = 4.0
        servings_val = max(float(servings_val or 4.0), 1.0)

        # Per-serving values
        def _per_serving(val):
            return float(val or 0) / servings_val

        # Nutrition (per serving)
        self.nutrition[slot, k, 0] = _per_serving(recipe.get("calories_total_kcal", 0))
        self.nutrition[slot, k, 1] = _per_serving(recipe.get("protein_total_g", 0))
        self.nutrition[slot, k, 2] = _per_serving(recipe.get("carbs_total_g", 0))
        self.nutrition[slot, k, 3] = _per_serving(recipe.get("fat_total_g", 0))
        self.nutrition[slot, k, 4] = _per_serving(recipe.get("fiber_total_g", 0))
        self.nutrition[slot, k, 5] = _per_serving(recipe.get("food_groups.vegetables_g", 0))
        self.nutrition[slot, k, 6] = _per_serving(recipe.get("food_groups.fruit_g", 0))
        self.nutrition[slot, k, 7] = _per_serving(recipe.get("food_groups.grains_g", 0))
        self.nutrition[slot, k, 8] = _per_serving(recipe.get("food_groups.dairy_g", 0))
        self.nutrition[slot, k, 9] = _per_serving(recipe.get("food_groups.protein_g", 0))

        # Cost (per serving)
        total_cost = float(recipe.get("total_estimated_cost", 0) or 0)
        self.costs[slot, k] = total_cost / servings_val

        # Servings
        self.servings[slot, k] = servings_val

        # Recipe ID
        recipe_id = int(recipe.get("recipeNum", 0))
        self.recipe_ids[slot, k] = recipe_id
        self.all_recipe_ids[slot, k, 0] = recipe_id  # Main dish only (no sides for raw recipes)

        # Recipe name (for debugging)
        self.recipe_names[slot].append(str(recipe.get("recipeName", "Unknown")))

        # Ingredients (per serving)
        fndds = recipe.get("fndds_grams_dict", {})
        if isinstance(fndds, str):
            try:
                fndds = ast.literal_eval(fndds)
            except:
                fndds = {}
        if isinstance(fndds, dict):
            for fpid, grams in fndds.items():
                fpid_str = str(fpid)
                if fpid_str in ingredient_index.fpid_to_idx:
                    idx = ingredient_index.fpid_to_idx[fpid_str]
                    self.ingredients[slot, k, idx] = float(grams) / servings_val

    def get_nutrition(self, slot: int) -> torch.Tensor:
        """Get nutrition tensor for slot: [K, NUM_NUTRIENTS]."""
        return self.nutrition[slot]

    def get_costs(self, slot: int) -> torch.Tensor:
        """Get cost tensor for slot: [K]."""
        return self.costs[slot]

    def get_servings(self, slot: int) -> torch.Tensor:
        """Get servings tensor for slot: [K]."""
        return self.servings[slot]

    def get_recipe_ids(self, slot: int) -> torch.Tensor:
        """Get recipe ID tensor for slot: [K]."""
        return self.recipe_ids[slot]

    def get_ingredients(self, slot: int) -> torch.Tensor:
        """Get ingredient needs tensor for slot: [K, num_ingredients]."""
        return self.ingredients[slot]

    def fill_slot_from_plates(
        self,
        slot: int,
        plates: List["Plate"],
        ingredient_index: IngredientIndex,
    ) -> None:
        """
        Fill a slot from Plate objects (template-compliant).

        Args:
            slot: Slot index (0-20)
            plates: List of Plate objects from PlateBuilder
            ingredient_index: Mapping from FPID to dense index
        """
        num_candidates = min(len(plates), self.K)

        for k in range(num_candidates):
            plate = plates[k]
            self._fill_candidate_from_plate(slot, k, plate, ingredient_index)

        # Pad remaining slots with copies of last candidate
        if num_candidates < self.K and num_candidates > 0:
            for k in range(num_candidates, self.K):
                self.nutrition[slot, k] = self.nutrition[slot, num_candidates - 1]
                self.costs[slot, k] = self.costs[slot, num_candidates - 1]
                self.servings[slot, k] = self.servings[slot, num_candidates - 1]
                self.recipe_ids[slot, k] = self.recipe_ids[slot, num_candidates - 1]
                self.all_recipe_ids[slot, k] = self.all_recipe_ids[slot, num_candidates - 1]  # MUST copy all IDs!
                self.ingredients[slot, k] = self.ingredients[slot, num_candidates - 1]
                self.leftover_ttl[slot, k] = self.leftover_ttl[slot, num_candidates - 1]

    def _fill_candidate_from_plate(
        self,
        slot: int,
        k: int,
        plate: "Plate",
        ingredient_index: IngredientIndex,
    ) -> None:
        """Fill a single candidate slot from a Plate object."""
        # Get main dish info (plates are based on main dish)
        main = plate.main_dish
        servings_val = main.servings_produced

        # Nutrition per serving (from main + sides combined)
        total_nutrition = plate.total_nutrition(1.0)  # per serving (numpy array)
        self.nutrition[slot, k, 0] = float(total_nutrition[0])  # calories
        self.nutrition[slot, k, 1] = float(total_nutrition[1])  # protein
        self.nutrition[slot, k, 2] = float(total_nutrition[2])  # carbs
        self.nutrition[slot, k, 3] = float(total_nutrition[3])  # fat
        self.nutrition[slot, k, 4] = float(total_nutrition[4])  # fiber
        self.nutrition[slot, k, 5] = float(total_nutrition[5])  # vegetables
        self.nutrition[slot, k, 6] = float(total_nutrition[6])  # fruits
        self.nutrition[slot, k, 7] = float(total_nutrition[7])  # grains
        self.nutrition[slot, k, 8] = float(total_nutrition[8])  # dairy
        self.nutrition[slot, k, 9] = float(total_nutrition[9])  # protein foods

        # Cost per serving (plate total cost)
        self.costs[slot, k] = plate.total_cost()

        # Servings (limited by main dish)
        self.servings[slot, k] = servings_val

        # Recipe ID (main dish ID) - for backward compatibility
        self.recipe_ids[slot, k] = main.recipe_num

        # ALL recipe IDs (main + sides) - for variety constraint
        self.all_recipe_ids[slot, k, 0] = main.recipe_num
        for i, side in enumerate(plate.sides[:3]):  # Max 3 sides
            self.all_recipe_ids[slot, k, i + 1] = side.recipe_num

        # Recipe name (main dish name, with template)
        main_name = main.recipe_name
        sides_str = " + ".join(s.recipe_name[:20] for s in plate.sides) if plate.sides else ""
        full_name = f"{main_name}" + (f" | {sides_str}" if sides_str else "")
        self.recipe_names[slot].append(full_name)

        # Template name
        self.template_names[slot].append(plate.template_name)

        # Ingredients per serving (combined from main + sides)
        all_needs = plate.all_ingredient_needs()  # Already per-serving
        for fpid, grams in all_needs.items():
            fpid_str = str(fpid)
            if fpid_str in ingredient_index.fpid_to_idx:
                idx = ingredient_index.fpid_to_idx[fpid_str]
                self.ingredients[slot, k, idx] = float(grams)

    def compute_pantry_overlap_batch(
        self,
        slot: int,
        pantry: torch.Tensor,  # [B, num_ingredients] or [num_ingredients]
        servings_scale: float = 1.0,
    ) -> torch.Tensor:
        """
        Compute pantry overlap for all candidates in a slot.

        Fully vectorized GPU operation.

        Args:
            slot: Slot index
            pantry: Pantry tensor [B, num_ingredients] or [num_ingredients]
            servings_scale: Scale ingredient needs by this factor

        Returns:
            [B, K] or [K] tensor of overlap ratios (0-1)
        """
        # Ingredient needs for this slot: [K, num_ingredients]
        needs = self.ingredients[slot] * servings_scale

        # Handle both batched and single pantry
        if pantry.dim() == 1:
            # Single pantry: [num_ingredients] -> compute [K] overlaps
            # Available is min of needs and pantry
            available = torch.minimum(needs, pantry.unsqueeze(0))  # [K, num_ingredients]
            total_needs = needs.sum(dim=1).clamp(min=1e-6)  # [K]
            total_available = available.sum(dim=1)  # [K]
            return total_available / total_needs  # [K]
        else:
            # Batched pantry: [B, num_ingredients] -> compute [B, K] overlaps
            B = pantry.shape[0]
            K = needs.shape[0]

            # Expand dimensions for broadcasting
            # needs: [K, num_ingredients] -> [1, K, num_ingredients]
            # pantry: [B, num_ingredients] -> [B, 1, num_ingredients]
            needs_exp = needs.unsqueeze(0)  # [1, K, num_ingredients]
            pantry_exp = pantry.unsqueeze(1)  # [B, 1, num_ingredients]

            # Available: [B, K, num_ingredients]
            available = torch.minimum(needs_exp.expand(B, -1, -1), pantry_exp.expand(-1, K, -1))

            total_needs = needs_exp.sum(dim=2).expand(B, K).clamp(min=1e-6)  # [B, K]
            total_available = available.sum(dim=2)  # [B, K]

            return total_available / total_needs  # [B, K]

    def memory_usage_mb(self) -> float:
        """Calculate GPU memory usage in MB."""
        total_bytes = (
            self.nutrition.numel() * 4 +
            self.costs.numel() * 4 +
            self.servings.numel() * 4 +
            self.recipe_ids.numel() * 8 +
            self.ingredients.numel() * 4 +
            self.leftover_ttl.numel() * 4
        )
        return total_bytes / (1024 * 1024)

    def summary(self) -> str:
        """Return summary statistics."""
        unique_recipes = len(set(
            self.recipe_ids.flatten().cpu().tolist()
        ))
        avg_cost = self.costs.mean().item()
        avg_calories = self.nutrition[:, :, 0].mean().item()

        return (
            f"GPUWeeklyTensor Summary:\n"
            f"  Device: {self.device}\n"
            f"  Slots: {NUM_SLOTS}\n"
            f"  Candidates per slot (K): {self.K}\n"
            f"  Ingredients: {self.num_ingredients}\n"
            f"  Unique recipes: {unique_recipes}\n"
            f"  Avg cost/serving: ${avg_cost:.2f}\n"
            f"  Avg calories/serving: {avg_calories:.0f}\n"
            f"  Memory usage: {self.memory_usage_mb():.1f} MB\n"
            f"  Tensor shapes:\n"
            f"    nutrition: {list(self.nutrition.shape)}\n"
            f"    ingredients: {list(self.ingredients.shape)}\n"
        )


def build_weekly_tensor(
    recipe_pool: List[Dict],
    ingredient_index: IngredientIndex,
    K: int = 128,
    device: torch.device = None,
    template_registry: "GPUTemplateRegistry" = None,
    seed: int = 42,
    initial_pantry: Dict[str, float] = None,  # FPID -> grams
    use_plate_templates: bool = True,  # NEW: Use plate templates for meal structure
) -> GPUWeeklyTensor:
    """
    Build GPUWeeklyTensor from recipe pool.

    Uses PlateBuilder to generate template-compliant candidates for each slot.
    Each meal slot gets plates that match the appropriate meal type template
    (breakfast templates for breakfast slots, etc.)

    Args:
        recipe_pool: List of recipe dictionaries
        ingredient_index: Pre-built ingredient index
        K: Candidates per slot
        device: GPU device
        template_registry: Optional template registry for filtering (deprecated)
        seed: Random seed
        initial_pantry: Starting pantry state (FPID -> grams)
        use_plate_templates: If True, use PlateBuilder for template-compliant plates

    Returns:
        Filled GPUWeeklyTensor
    """
    import random
    random.seed(seed)
    torch.manual_seed(seed)

    if device is None:
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")

    tensor = GPUWeeklyTensor(K, ingredient_index.num_ingredients, device)

    # Default empty pantry if not provided
    if initial_pantry is None:
        initial_pantry = {}

    # === USE PLATE TEMPLATES ===
    if use_plate_templates:
        try:
            from hestia.plate_builder import PlateBuilder

            print("Using PlateBuilder with plate templates...")
            builder = PlateBuilder()
            builder.index_recipes(recipe_pool)

            # === BUILD BEST-OF-EACH-TEMPLATE POOLS ===
            # For each meal type, get top N plates from EVERY template
            # This ensures diversity - we don't just pick cheapest template
            plates_per_template = max(2, K // 20)  # ~3-6 plates per template

            best_plates_by_meal = {"breakfast": [], "lunch": [], "dinner": []}
            template_stats = {"breakfast": {}, "lunch": {}, "dinner": {}}

            for meal_type in ["breakfast", "lunch", "dinner"]:
                templates = builder.get_templates_for_meal(meal_type)
                print(f"  {meal_type}: evaluating {len(templates)} templates...")

                for template in templates:
                    # Build plates for this specific template
                    plates = builder.build_plates_for_template(
                        template,
                        max_plates=plates_per_template * 3,  # Build extra, keep best
                        max_sides=2,
                    )

                    if not plates:
                        continue

                    # Score by cost + pantry if available
                    if initial_pantry:
                        scored = builder.score_plates_combined(
                            plates,
                            pantry=initial_pantry,
                            cost_weight=0.6,
                            pantry_weight=0.3,
                            batch_size_weight=0.1,
                        )
                        best = [p for p, _ in scored[:plates_per_template]]
                    else:
                        plates.sort(key=lambda p: p.total_cost())
                        best = plates[:plates_per_template]

                    # Keep track of what we got from each template
                    template_stats[meal_type][template.name] = len(best)
                    best_plates_by_meal[meal_type].extend(best)

            # Summary of what we collected
            for meal_type in ["breakfast", "lunch", "dinner"]:
                total = len(best_plates_by_meal[meal_type])
                templates_with_plates = sum(1 for v in template_stats[meal_type].values() if v > 0)
                print(f"  {meal_type}: {total} plates from {templates_with_plates} templates")

            meal_types = ["breakfast", "lunch", "dinner"] * 7
            templates_used = {"breakfast": set(), "lunch": set(), "dinner": set()}

            for slot in range(NUM_SLOTS):
                meal_type = meal_types[slot]

                # Get all best plates for this meal type
                all_plates = best_plates_by_meal[meal_type].copy()

                if not all_plates:
                    print(f"  Warning: No plates found for {meal_type} slot {slot}, using fallback")
                    tensor.fill_slot(slot, recipe_pool[:K], ingredient_index)
                    continue

                # Final scoring to pick top K for this slot
                if initial_pantry:
                    scored = builder.score_plates_combined(
                        all_plates,
                        pantry=initial_pantry,
                        cost_weight=0.5,
                        pantry_weight=0.4,
                        batch_size_weight=0.1,
                    )
                    plates = [p for p, _ in scored[:K]]
                else:
                    all_plates.sort(key=lambda p: p.total_cost())
                    plates = all_plates[:K]

                # Track which templates are being used
                for plate in plates:
                    templates_used[meal_type].add(plate.template_name)

                # Fill slot from plates
                tensor.fill_slot_from_plates(slot, plates, ingredient_index)

            # Summary
            print(f"Templates in final candidate pools:")
            for meal, templates in templates_used.items():
                total_templates = len(builder.get_templates_for_meal(meal))
                print(f"  {meal}: {len(templates)}/{total_templates} templates represented")

            return tensor

        except ImportError as e:
            print(f"PlateBuilder not available ({e}), falling back to recipe-based selection")

    # === FALLBACK: ORIGINAL RECIPE-BASED APPROACH ===
    print("Using recipe-based candidate selection (no plate templates)")

    # Filter keywords for non-food items
    EXCLUDE_KEYWORDS = ['dog', 'cat', 'pet', 'bath', 'soap', 'lotion']

    def get_ingredients(recipe):
        fndds = recipe.get('fndds_grams_dict', {})
        if isinstance(fndds, str):
            try:
                fndds = ast.literal_eval(fndds)
            except:
                fndds = {}
        return {str(k): float(v) for k, v in fndds.items()} if isinstance(fndds, dict) else {}

    def calc_pantry_coverage(recipe, pantry):
        ingredients = get_ingredients(recipe)
        if not ingredients:
            return 0.0, float(recipe.get("total_estimated_cost", 0) or 0)

        base_cost = float(recipe.get("total_estimated_cost", 0) or 0)
        total_grams = sum(ingredients.values())

        covered_grams = 0
        for fpid, grams_needed in ingredients.items():
            available = pantry.get(fpid, 0)
            covered = min(available, grams_needed)
            covered_grams += covered

        coverage = covered_grams / max(total_grams, 1)
        cost_after_pantry = base_cost * (1 - coverage)

        return coverage, cost_after_pantry

    # Score recipes
    scored_recipes = []
    for recipe in recipe_pool:
        recipe_name = str(recipe.get("recipeName", "")).lower()
        if any(kw in recipe_name for kw in EXCLUDE_KEYWORDS):
            continue

        cost = float(recipe.get("total_estimated_cost", 999) or 999)
        cals = float(recipe.get("calories_total_kcal", 0) or 0)

        srv = recipe.get("servings.max") or recipe.get("servings.min") or 4.0
        srv = max(float(srv), 1.0)

        if cost < 0.5 or cals < 200:
            continue

        coverage, cost_after_pantry = calc_pantry_coverage(recipe, initial_pantry)
        score = -cost_after_pantry if initial_pantry else -cost

        scored_recipes.append((score, recipe, coverage))

    scored_recipes.sort(key=lambda x: x[0], reverse=True)
    core_recipes = [r[1] for r in scored_recipes[:K]]

    print(f"Built core pool of {len(core_recipes)} recipes")

    meal_types = ["breakfast", "lunch", "dinner"] * 7
    for slot in range(NUM_SLOTS):
        tensor.fill_slot(slot, core_recipes, ingredient_index)

    return tensor


class SmartCandidateGenerator:
    """
    GPU-accelerated smart candidate generation.

    Generates diverse candidate sets per slot using multiple strategies:
    1. Cost-efficient (lowest cost)
    2. Pantry-heavy (best pantry overlap)
    3. Nutrition-targeted (fills remaining debt)
    4. Random exploration

    All operations vectorized on GPU.
    """

    def __init__(
        self,
        recipe_pool: List[Dict],
        ingredient_index: IngredientIndex,
        template_registry: "GPUTemplateRegistry",
        device: torch.device,
    ):
        self.device = device
        self.recipe_pool = recipe_pool
        self.ingredient_index = ingredient_index
        self.template_registry = template_registry

        # Pre-index all recipes on GPU
        self._build_recipe_tensors()

    def _build_recipe_tensors(self) -> None:
        """Pre-compute recipe data on GPU."""
        N = len(self.recipe_pool)

        # Nutrition: [N, NUM_NUTRIENTS]
        self.all_nutrition = torch.zeros(N, NUM_NUTRIENTS, dtype=torch.float32, device=self.device)

        # Costs: [N]
        self.all_costs = torch.zeros(N, dtype=torch.float32, device=self.device)

        # Servings: [N]
        self.all_servings = torch.zeros(N, dtype=torch.float32, device=self.device)

        # Recipe IDs: [N]
        self.all_recipe_ids = torch.zeros(N, dtype=torch.long, device=self.device)

        # Ingredients: [N, num_ingredients]
        self.all_ingredients = torch.zeros(
            N, self.ingredient_index.num_ingredients,
            dtype=torch.float32, device=self.device
        )

        for i, recipe in enumerate(self.recipe_pool):
            # Servings
            srv = recipe.get("servings.standard_serving_size")
            if srv in (None, 0):
                srv_min = recipe.get("servings.min")
                srv_max = recipe.get("servings.max")
                if srv_min and srv_max:
                    srv = (float(srv_min) + float(srv_max)) / 2
                elif srv_max:
                    srv = float(srv_max)
                elif srv_min:
                    srv = float(srv_min)
                else:
                    srv = 4.0
            srv = max(float(srv or 4.0), 1.0)
            self.all_servings[i] = srv

            # Per-serving nutrition
            def _ps(val):
                return float(val or 0) / srv

            self.all_nutrition[i, 0] = _ps(recipe.get("calories_total_kcal", 0))
            self.all_nutrition[i, 1] = _ps(recipe.get("protein_total_g", 0))
            self.all_nutrition[i, 2] = _ps(recipe.get("carbs_total_g", 0))
            self.all_nutrition[i, 3] = _ps(recipe.get("fat_total_g", 0))
            self.all_nutrition[i, 4] = _ps(recipe.get("fiber_total_g", 0))
            self.all_nutrition[i, 5] = _ps(recipe.get("food_groups.vegetables_g", 0))
            self.all_nutrition[i, 6] = _ps(recipe.get("food_groups.fruit_g", 0))
            self.all_nutrition[i, 7] = _ps(recipe.get("food_groups.grains_g", 0))
            self.all_nutrition[i, 8] = _ps(recipe.get("food_groups.dairy_g", 0))
            self.all_nutrition[i, 9] = _ps(recipe.get("food_groups.protein_g", 0))

            # Cost
            total_cost = float(recipe.get("total_estimated_cost", 0) or 0)
            self.all_costs[i] = total_cost / srv

            # Recipe ID
            self.all_recipe_ids[i] = int(recipe.get("recipeNum", 0))

            # Ingredients
            fndds = recipe.get("fndds_grams_dict", {})
            if isinstance(fndds, str):
                try:
                    fndds = ast.literal_eval(fndds)
                except:
                    fndds = {}
            if isinstance(fndds, dict):
                for fpid, grams in fndds.items():
                    fpid_str = str(fpid)
                    if fpid_str in self.ingredient_index.fpid_to_idx:
                        idx = self.ingredient_index.fpid_to_idx[fpid_str]
                        self.all_ingredients[i, idx] = float(grams) / srv

    def generate_candidates(
        self,
        slot: int,
        K: int,
        pantry: torch.Tensor,  # [num_ingredients]
        nutrition_debt: torch.Tensor,  # [NUM_NUTRIENTS]
        excluded_recipes: torch.Tensor,  # [N] bool mask
        servings_per_meal: float = 4.0,
    ) -> Tuple[torch.Tensor, List[int]]:
        """
        Generate K diverse candidates for a slot.

        Mixes multiple strategies for good coverage.

        Args:
            slot: Slot index
            K: Number of candidates to generate
            pantry: Current pantry state
            nutrition_debt: Remaining nutrition targets
            excluded_recipes: Mask of recipes to exclude
            servings_per_meal: Expected servings

        Returns:
            (indices, recipe_indices) - GPU tensor and list
        """
        meal_type = ["breakfast", "lunch", "dinner"][slot % 3]

        # Get valid recipes for this meal type
        meal_mask = self.template_registry.get_combined_main_mask_for_meal(meal_type)
        valid_mask = meal_mask & ~excluded_recipes

        valid_indices = torch.where(valid_mask)[0]
        N_valid = len(valid_indices)

        if N_valid == 0:
            # Fallback to any recipe
            valid_indices = torch.where(~excluded_recipes)[0]
            N_valid = len(valid_indices)

        if N_valid == 0:
            # No valid recipes - return zeros
            return torch.zeros(K, dtype=torch.long, device=self.device), []

        # Allocate result
        selected = torch.zeros(K, dtype=torch.long, device=self.device)
        selected_set = set()

        # Strategy allocation
        k_cost = K // 4  # 25% lowest cost
        k_pantry = K // 4  # 25% best pantry overlap
        k_nutrition = K // 4  # 25% nutrition-targeted
        k_random = K - k_cost - k_pantry - k_nutrition  # Rest random

        idx = 0

        # 1. COST-EFFICIENT: Lowest cost per serving
        if k_cost > 0:
            costs = self.all_costs[valid_indices]
            _, cost_order = torch.sort(costs)
            for i in range(min(k_cost, N_valid)):
                recipe_idx = valid_indices[cost_order[i]].item()
                if recipe_idx not in selected_set:
                    selected[idx] = recipe_idx
                    selected_set.add(recipe_idx)
                    idx += 1
                    if idx >= K:
                        break

        # 2. PANTRY-HEAVY: Best pantry overlap
        if k_pantry > 0 and idx < K:
            needs = self.all_ingredients[valid_indices] * servings_per_meal  # [N_valid, num_ing]
            available = torch.minimum(needs, pantry.unsqueeze(0))
            total_needs = needs.sum(dim=1).clamp(min=1e-6)
            total_available = available.sum(dim=1)
            overlap = total_available / total_needs

            _, overlap_order = torch.sort(overlap, descending=True)
            for i in range(min(k_pantry, N_valid)):
                recipe_idx = valid_indices[overlap_order[i]].item()
                if recipe_idx not in selected_set:
                    selected[idx] = recipe_idx
                    selected_set.add(recipe_idx)
                    idx += 1
                    if idx >= K:
                        break

        # 3. NUTRITION-TARGETED: Best fills debt
        if k_nutrition > 0 and idx < K:
            nutrition = self.all_nutrition[valid_indices] * servings_per_meal
            # Compute how well each candidate fills the debt
            # Higher is better when nutrition fills positive debt
            debt_fill = torch.minimum(nutrition, nutrition_debt.unsqueeze(0).clamp(min=0))
            fill_score = debt_fill.sum(dim=1)

            _, fill_order = torch.sort(fill_score, descending=True)
            for i in range(min(k_nutrition, N_valid)):
                recipe_idx = valid_indices[fill_order[i]].item()
                if recipe_idx not in selected_set:
                    selected[idx] = recipe_idx
                    selected_set.add(recipe_idx)
                    idx += 1
                    if idx >= K:
                        break

        # 4. RANDOM: Exploration
        if idx < K:
            remaining = K - idx
            available_for_random = [i.item() for i in valid_indices if i.item() not in selected_set]
            if available_for_random:
                import random
                random.shuffle(available_for_random)
                for recipe_idx in available_for_random[:remaining]:
                    selected[idx] = recipe_idx
                    idx += 1
                    if idx >= K:
                        break

        # Pad if needed
        if idx < K and idx > 0:
            for i in range(idx, K):
                selected[i] = selected[idx - 1]

        return selected, list(selected_set)
