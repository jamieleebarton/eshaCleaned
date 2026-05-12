"""
Plate: A complete meal consisting of main dish + optional sides.

A plate is NOT just one recipe - it's a combination:
- Main dish (matches template's main_categories)
- 0-3 sides (from template's side_pools, respecting constraints)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import numpy as np


@dataclass
class Recipe:
    """Single recipe with nutritional info and ingredient needs."""

    recipe_num: int
    recipe_name: str
    category_number: str

    # Cost
    base_cost: float

    # Nutrition per serving
    calories: float
    protein: float
    carbs: float
    fat: float
    fiber: float

    # Food groups (grams per serving)
    vegetables_g: float
    fruits_g: float
    grains_g: float
    dairy_g: float
    protein_foods_g: float
    fats_g: float
    other_g: float

    # Servings
    servings_produced: float

    # Ingredient needs: FPID -> grams per serving
    ingredient_needs: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict) -> "Recipe":
        """Create Recipe from recipe dictionary."""
        # Get servings FIRST - CSV has servings.min and servings.max
        servings_min = d.get("servings.min", None)
        servings_max = d.get("servings.max", None)

        if servings_min is not None and servings_max is not None:
            # Use average of min and max
            servings = (float(servings_min) + float(servings_max)) / 2
        elif servings_max is not None:
            servings = float(servings_max)
        elif servings_min is not None:
            servings = float(servings_min)
        else:
            servings = 4.0  # Last resort default

        # IMPORTANT: CSV values are TOTAL for recipe, not per serving
        # We need to divide by servings to get per-serving values
        servings_for_division = servings if servings > 0 else 1.0

        # Parse ingredient needs - ALSO divide by servings!
        ingredient_needs = {}
        if "fndds_grams_dict" in d:
            fndds = d["fndds_grams_dict"]
            if isinstance(fndds, str):
                try:
                    import ast
                    fndds = ast.literal_eval(fndds)
                except:
                    fndds = {}
            if isinstance(fndds, dict):
                # Divide by servings to get per-serving grams
                ingredient_needs = {
                    str(k): float(v) / servings_for_division
                    for k, v in fndds.items()
                }

        return cls(
            recipe_num=int(d.get("recipeNum", 0)),
            recipe_name=str(d.get("recipeName", "Unknown")),
            category_number=str(d.get("category_number", "")),
            base_cost=float(d.get("total_estimated_cost", 0) or 0) / servings_for_division,
            calories=float(d.get("calories_total_kcal", 0) or 0) / servings_for_division,
            protein=float(d.get("protein_total_g", 0) or 0) / servings_for_division,
            carbs=float(d.get("carbs_total_g", 0) or 0) / servings_for_division,
            fat=float(d.get("fat_total_g", 0) or 0) / servings_for_division,
            fiber=float(d.get("fiber_total_g", 0) or 0) / servings_for_division,
            vegetables_g=float(d.get("food_groups.vegetables_g", 0) or 0) / servings_for_division,
            fruits_g=float(d.get("food_groups.fruit_g", 0) or 0) / servings_for_division,
            grains_g=float(d.get("food_groups.grains_g", 0) or 0) / servings_for_division,
            dairy_g=float(d.get("food_groups.dairy_g", 0) or 0) / servings_for_division,
            protein_foods_g=float(d.get("food_groups.protein_g", 0) or 0) / servings_for_division,
            fats_g=float(d.get("food_groups.fats_g", d.get("fats_g", 0)) or 0) / servings_for_division,
            other_g=float(d.get("food_groups.other_g", d.get("other_g", 0)) or 0) / servings_for_division,
            servings_produced=float(servings),
            ingredient_needs=ingredient_needs,
        )

    def nutrition_vector(self) -> np.ndarray:
        """Nutrition as numpy array [10 values]."""
        return np.array([
            self.calories,
            self.protein,
            self.carbs,
            self.fat,
            self.fiber,
            self.vegetables_g,
            self.fruits_g,
            self.grains_g,
            self.dairy_g,
            self.protein_foods_g,
        ], dtype=np.float32)


@dataclass
class Plate:
    """
    A complete meal: main dish + optional sides.

    Constructed from a template that defines valid combinations.
    """

    template_name: str
    meal_type: str  # breakfast, lunch, dinner

    main_dish: Recipe
    sides: List[Recipe] = field(default_factory=list)

    # Is this a one-dish meal (soup, stew, casserole)?
    one_dish: bool = False

    def total_cost(self) -> float:
        """Total cost of plate (main + all sides)."""
        cost = self.main_dish.base_cost
        for side in self.sides:
            cost += side.base_cost
        return cost

    def total_nutrition(self, servings: float = 1.0) -> np.ndarray:
        """Total nutrition for given servings [10 values]."""
        nutrition = self.main_dish.nutrition_vector() * servings
        for side in self.sides:
            nutrition += side.nutrition_vector() * servings
        return nutrition

    def total_calories(self, servings: float = 1.0) -> float:
        """Total calories for given servings."""
        return self.total_nutrition(servings)[0]

    def total_protein(self, servings: float = 1.0) -> float:
        """Total protein for given servings."""
        return self.total_nutrition(servings)[1]

    def all_ingredient_needs(self) -> Dict[str, float]:
        """Combined ingredient needs from main + sides."""
        needs: Dict[str, float] = {}
        for fpid, grams in self.main_dish.ingredient_needs.items():
            needs[fpid] = needs.get(fpid, 0) + grams
        for side in self.sides:
            for fpid, grams in side.ingredient_needs.items():
                needs[fpid] = needs.get(fpid, 0) + grams
        return needs

    def pantry_overlap(self, pantry: Dict[str, float]) -> float:
        """
        Calculate what fraction of ingredients are in pantry.

        Returns: 0.0 (nothing in pantry) to 1.0 (everything in pantry)
        """
        needs = self.all_ingredient_needs()
        if not needs:
            return 0.0

        total_needed = 0.0
        total_available = 0.0

        for fpid, grams in needs.items():
            total_needed += grams
            available = pantry.get(fpid, 0.0)
            total_available += min(grams, available)

        return total_available / total_needed if total_needed > 0 else 0.0

    def cost_after_pantry(self, pantry: Dict[str, float]) -> float:
        """
        Estimated cost after pantry deductions.

        Simple model: cost * (1 - overlap * 0.7)
        """
        overlap = self.pantry_overlap(pantry)
        return self.total_cost() * (1 - overlap * 0.7)

    def max_servings(self) -> float:
        """Maximum servings this plate can produce (limited by main dish)."""
        return self.main_dish.servings_produced

    def recipe_nums(self) -> Set[int]:
        """All recipe numbers in this plate."""
        nums = {self.main_dish.recipe_num}
        for side in self.sides:
            nums.add(side.recipe_num)
        return nums

    def __repr__(self) -> str:
        sides_str = ", ".join(s.recipe_name for s in self.sides)
        return f"Plate({self.main_dish.recipe_name} + [{sides_str}])"


@dataclass
class Leftover:
    """Leftover food from a previous meal."""

    recipe_num: int
    recipe_name: str
    servings_remaining: float
    ttl: int  # Days until expiry (0 = expires today)

    # Nutrition per serving (for tracking)
    calories: float
    protein: float

    # Which meal type this came from
    meal_type: str
    template_name: str

    def is_expired(self) -> bool:
        return self.ttl < 0

    def is_expiring_soon(self) -> bool:
        return self.ttl <= 1

    def consume(self, servings: float) -> float:
        """Consume servings, return actual amount consumed."""
        consumed = min(servings, self.servings_remaining)
        self.servings_remaining -= consumed
        return consumed

    def decay(self) -> None:
        """Decrement TTL by one day."""
        self.ttl -= 1
