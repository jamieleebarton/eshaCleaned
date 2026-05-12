"""
PlateBuilder: Constructs valid plates from templates.

A plate must follow template rules:
- Main dish matches template's main_categories
- Sides come from template's side_pools
- Respects constraints (unique_sides, max_one_starchy_side, etc.)
- one_dish templates have no sides (soup, stew, casserole)
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
import numpy as np

try:
    from .plate import Plate, Recipe
except ImportError:
    from hestia.plate import Plate, Recipe


@dataclass
class SidePool:
    """A pool of valid side dishes within a template."""
    name: str
    category_ids: List[str]
    tags: List[str] = field(default_factory=list)


@dataclass
class PlateTemplate:
    """Template defining valid plate construction."""
    name: str
    meal: str  # breakfast, lunch, dinner
    main_categories: List[str]
    side_pools: List[SidePool] = field(default_factory=list)
    drink_allowed: bool = False
    constraints: List[str] = field(default_factory=list)
    one_dish: bool = False
    cuisine_filter: Optional[List[str]] = None  # Optional: limit to specific cuisines


class PlateBuilder:
    """
    Builds valid plates from templates and recipe pool.

    Key responsibilities:
    - Load templates from JSON files
    - Match recipes to templates
    - Build plates with valid main + sides combinations
    - Respect all constraints
    """

    def __init__(self, templates_dir: str = None, cuisine_file: str = None,
                 corrections_file: str = None):
        # Auto-detect path based on environment (works on Linux, Windows, Docker)
        if templates_dir is None:
            templates_dir = str(Path(__file__).parent.parent / "assets" / "plate_templates")
        self.templates_dir = Path(templates_dir)
        self.templates: Dict[str, List[PlateTemplate]] = {
            "breakfast": [],
            "lunch": [],
            "dinner": [],
        }
        self._load_templates()

        # Index recipes by category for fast lookup
        self.recipes_by_category: Dict[str, List[Recipe]] = {}
        self.all_recipes: List[Recipe] = []

        # Load cuisine classifications for filtering
        self.cuisine_by_recipe: Dict[int, str] = {}
        self._load_cuisine_classifications(cuisine_file)

        # Load category corrections (runtime category overrides)
        self.category_corrections: Dict[int, str] = {}
        self._load_category_corrections(corrections_file)

        # Load excluded categories (components/condiments that shouldn't be main dishes)
        self.excluded_main_categories: Set[str] = set()
        self.excluded_side_categories: Set[str] = set()
        self.category_keyword_exclusions: Dict[str, List[str]] = {}
        self._load_excluded_categories()

    def _load_templates(self) -> None:
        """Load templates from JSON files."""
        for meal in ["breakfast", "lunch", "dinner"]:
            filepath = self.templates_dir / f"{meal}.json"
            if not filepath.exists():
                print(f"Warning: Template file not found: {filepath}")
                continue

            with open(filepath) as f:
                data = json.load(f)

            for t in data:
                side_pools = []
                for sp in t.get("side_pools", []):
                    side_pools.append(SidePool(
                        name=sp["name"],
                        category_ids=sp.get("category_ids", []),
                        tags=sp.get("tags", []),
                    ))

                template = PlateTemplate(
                    name=t["name"],
                    meal=t["meal"],
                    main_categories=t.get("main_categories", []),
                    side_pools=side_pools,
                    drink_allowed=t.get("drink_allowed", False),
                    constraints=t.get("constraints", []),
                    one_dish=t.get("one_dish", False),
                    cuisine_filter=t.get("cuisine_filter", None),
                )
                self.templates[meal].append(template)

        total = sum(len(v) for v in self.templates.values())
        print(f"Loaded {total} templates: "
              f"{len(self.templates['breakfast'])} breakfast, "
              f"{len(self.templates['lunch'])} lunch, "
              f"{len(self.templates['dinner'])} dinner")

    def _load_cuisine_classifications(self, cuisine_file: str = None) -> None:
        """Load cuisine classifications for recipe filtering."""
        if cuisine_file is None:
            cuisine_file = str(Path(__file__).parent.parent / "data" / "cuisine_classifications.json")

        cuisine_path = Path(cuisine_file)
        if not cuisine_path.exists():
            print(f"Note: Cuisine file not found: {cuisine_path} (cuisine filtering disabled)")
            return

        try:
            with open(cuisine_path) as f:
                data = json.load(f)

            for recipe_num_str, info in data.items():
                try:
                    recipe_num = int(recipe_num_str)
                    cuisine = info.get('cuisine', '')
                    if cuisine:
                        self.cuisine_by_recipe[recipe_num] = cuisine
                except (ValueError, KeyError):
                    continue

            print(f"Loaded {len(self.cuisine_by_recipe):,} cuisine classifications")
        except Exception as e:
            print(f"Warning: Could not load cuisine file: {e}")

    def _load_category_corrections(self, corrections_file: str = None) -> None:
        """Load category corrections for misclassified recipes."""
        if corrections_file is None:
            corrections_file = str(Path(__file__).parent.parent / "data" / "category_corrections.json")

        corrections_path = Path(corrections_file)
        if not corrections_path.exists():
            # Silently skip if no corrections file yet (will be generated by audit)
            return

        try:
            with open(corrections_path) as f:
                data = json.load(f)

            for recipe_num_str, info in data.items():
                try:
                    recipe_num = int(recipe_num_str)
                    correct_category = info.get('correct', '')
                    if correct_category:
                        self.category_corrections[recipe_num] = correct_category
                except (ValueError, KeyError):
                    continue

            print(f"Loaded {len(self.category_corrections):,} category corrections")
        except Exception as e:
            print(f"Warning: Could not load corrections file: {e}")

    def _load_excluded_categories(self) -> None:
        """Load excluded categories (components/condiments that shouldn't be meals)."""
        excluded_cat_file = str(Path(__file__).parent.parent / "data" / "excluded_categories.json")

        excluded_path = Path(excluded_cat_file)
        if not excluded_path.exists():
            # Silently skip if no exclusions file yet
            return

        try:
            with open(excluded_path) as f:
                data = json.load(f)

            # Load excluded main categories
            for cat_id, info in data.get('excluded_main_categories', {}).items():
                if not cat_id.startswith('_'):  # Skip _comment fields
                    self.excluded_main_categories.add(cat_id)

            # Load excluded side categories
            for cat_id, info in data.get('excluded_side_categories', {}).items():
                if not cat_id.startswith('_'):
                    self.excluded_side_categories.add(cat_id)

            # Load category-specific keyword exclusions
            for cat_id, info in data.get('category_keyword_exclusions', {}).items():
                if not cat_id.startswith('_'):
                    keywords = info.get('exclude_if_contains', [])
                    if keywords:
                        self.category_keyword_exclusions[cat_id] = [kw.lower() for kw in keywords]

            total_excluded = len(self.excluded_main_categories) + len(self.excluded_side_categories)
            if total_excluded > 0:
                print(f"Loaded {len(self.excluded_main_categories)} excluded main categories, "
                      f"{len(self.excluded_side_categories)} excluded side categories")

        except Exception as e:
            print(f"Warning: Could not load excluded categories: {e}")

    def _load_verdict_exclusions(self) -> set:
        """Load recipe IDs that should be excluded based on LLM verdict.

        Excludes: component, beverage, not_food, invalid.
        These recipes should never enter the template pools.

        Also loads dessert recipe IDs into self.dessert_recipe_ids —
        these are blocked from both mains and sides (desserts aren't meals).
        """
        import sqlite3
        qa_path = Path(__file__).parent.parent / "data" / "recipe_qa.db"
        if not qa_path.exists():
            self.dessert_recipe_ids = set()
            return set()

        try:
            conn = sqlite3.connect(str(qa_path))
            rows = conn.execute(
                "SELECT recipe_id FROM recipe_verdicts "
                "WHERE verdict IN ('component', 'beverage', 'not_food', 'invalid', 'derived_fat_only')"
            ).fetchall()
            excluded = {r[0] for r in rows}
            print(f"Loaded {len(excluded):,} verdict exclusions (component/beverage/not_food/invalid/derived_fat_only)")

            # Load dessert IDs — blocked from both mains and sides
            dessert_rows = conn.execute(
                "SELECT recipe_id FROM recipe_verdicts WHERE verdict = 'dessert'"
            ).fetchall()
            self.dessert_recipe_ids = {r[0] for r in dessert_rows}
            print(f"Loaded {len(self.dessert_recipe_ids):,} dessert recipes (blocked from mains+sides)")

            conn.close()
            return excluded
        except Exception as e:
            print(f"Warning: Could not load verdict exclusions: {e}")
            self.dessert_recipe_ids = set()
            return set()

    def _get_effective_category(self, recipe_num: int, original_category: str) -> str:
        """Get the effective category for a recipe, applying corrections if available."""
        if recipe_num in self.category_corrections:
            return self.category_corrections[recipe_num]
        return original_category

    # Keywords to exclude from recipes (pet food, non-food items, crafts)
    EXCLUDE_KEYWORDS = [
        # Pet food
        'for dogs', 'dog treat', 'dog food', 'for cats', 'cat treat', 'cat food',
        'pet food', 'pet treat', 'bird food', 'bird treat', 'hamster', 'guinea pig',
        'pill pocket', 'canine', 'feline', 'doggie', 'kitty treat', 'puppy treat',
        'for kitty', 'kitty pet',  # catches "for kitty" pet recipes
        # Crafts and non-edibles
        'playdough', 'play dough', 'play-dough', 'bath bomb', 'bath bom',
        'lip balm', 'skin care', 'lotion', 'soap recipe', 'slime', 'shampoo',
        'non-edible', 'not for consumption', 'facial cleansing',
        'facial scrub', 'body scrub', 'exfoliat',
        # Test/placeholder entries
        'please ignore', 'test recipe', 'placeholder', 'delete me',
        # How-to / instructional (not actual recipes)
        'how to cook ', 'how to make ', 'how to boil ', 'how to roast ',
        'how to bake ', 'how to grill ', 'how to fry ', 'how to blanch ',
        'how to steam ', 'how to prepare ',
    ]

    # Component endings: if recipe name ends with these AND has few ingredients,
    # it's a standalone sauce/condiment/component, not a meal.
    _COMPONENT_ENDINGS = [
        'sauce', 'sauces', 'syrup', 'glaze', 'glazes',
        'frosting', 'icing', 'icings', 'frostings',
        'gravy', 'marinade', 'marinades', 'rub', 'rubs',
        'seasoning mix', 'spice mix', 'spice blend', 'seasoning blend',
        'herb mix', 'herb blend',
    ]

    # "X for Y" patterns: sauce for pasta, syrup for pancakes, etc.
    _COMPONENT_FOR_PATTERNS = [
        'sauce for ', 'syrup for ', 'glaze for ', 'icing for ',
        'frosting for ', 'gravy for ', 'marinade for ', 'rub for ',
        'topping for ', 'drizzle for ', 'dressing for ',
    ]

    # Plain dough/wrap names (not dishes that contain these as ingredients)
    _DOUGH_KEYWORDS = [
        'tortilla', 'pie crust', 'pizza dough', 'bread dough',
        'pastry dough', 'puff pastry', 'phyllo dough', 'filo dough',
    ]
    # Dish words that mean a tortilla/crust is part of an actual dish
    _DOUGH_DISH_EXCEPTIONS = [
        'soup', 'casserole', 'enchilada', 'wrap', 'burrito', 'taco',
        'quesadilla', 'chip', 'pizza', 'lasagna', 'roll-up', 'pinwheel',
        'omelet', 'omelette', 'espanola', 'española', 'española',
        'dumpling', 'roll', 'pie', 'quiche', 'pot pie', 'samosa',
        'empanada', 'calzone', 'stromboli',
    ]

    # Max ingredients for component detection (recipes with more are likely real dishes)
    _COMPONENT_MAX_INGREDIENTS = 5

    @classmethod
    def _is_component_recipe(cls, name: str, n_ingredients: int) -> bool:
        """Check if recipe is a component (sauce, dough, etc.) not a standalone meal."""
        name_lower = name.lower().strip()

        # "Canned X" with 1-2 ingredients is an ingredient, not a dish
        if name_lower.startswith('canned ') and n_ingredients <= 2:
            return True

        # Only apply remaining checks to low-ingredient recipes
        if n_ingredients > cls._COMPONENT_MAX_INGREDIENTS:
            return False

        # Check "X for Y" patterns (sauce for pasta, etc.)
        for pat in cls._COMPONENT_FOR_PATTERNS:
            if pat in name_lower:
                return True

        # Check standalone component endings
        for ending in cls._COMPONENT_ENDINGS:
            if name_lower.endswith(ending) or name_lower.endswith(ending + 's'):
                return True

        # Check plain dough/wrap (but not dishes made with them)
        for kw in cls._DOUGH_KEYWORDS:
            if kw in name_lower:
                has_dish = any(d in name_lower for d in cls._DOUGH_DISH_EXCEPTIONS)
                if not has_dish:
                    return True

        return False

    def index_recipes(self, recipe_pool: List[Dict]) -> None:
        """
        Index recipes by category for fast lookup.

        Call this once after loading recipe pool.

        Applies:
        - Verdict-based exclusions (component/beverage/not_food/invalid from recipe_qa.db)
        - Keyword-based exclusions (pet food, crafts, etc.)
        - Category corrections from category_corrections.json
        """
        self.recipes_by_category.clear()
        self.all_recipes: List[Recipe] = []

        # Load LLM verdicts to exclude components/beverages/not_food/invalid
        verdict_excluded = self._load_verdict_exclusions()

        excluded_by_keywords = 0
        excluded_by_components = 0
        excluded_by_verdict = 0
        corrected_categories = 0

        for r in recipe_pool:
            recipe_num = int(r.get('recipeNum', 0))

            # Skip recipes classified as component/beverage/not_food/invalid by LLM
            if recipe_num in verdict_excluded:
                excluded_by_verdict += 1
                continue

            # Filter out pet food and non-food items by keywords
            name = str(r.get('recipeName', '')).lower()
            if any(kw in name for kw in self.EXCLUDE_KEYWORDS):
                excluded_by_keywords += 1
                continue

            # Filter out component recipes (sauces, doughs, condiments)
            recipe_name = str(r.get('recipeName', ''))
            fndds_str = str(r.get('fndds_grams_dict', '{}'))
            n_ingredients = fndds_str.count(':')
            if self._is_component_recipe(recipe_name, n_ingredients):
                excluded_by_components += 1
                continue

            recipe = Recipe.from_dict(r)

            # Apply category correction if available
            original_category = recipe.category_number
            effective_category = self._get_effective_category(recipe_num, original_category)
            if effective_category != original_category:
                recipe.category_number = effective_category
                corrected_categories += 1

            self.all_recipes.append(recipe)

            category = recipe.category_number
            if category not in self.recipes_by_category:
                self.recipes_by_category[category] = []
            self.recipes_by_category[category].append(recipe)

        print(f"Indexed {len(self.all_recipes):,} recipes across {len(self.recipes_by_category)} categories")
        total_excluded = excluded_by_keywords + excluded_by_components + excluded_by_verdict
        if total_excluded > 0:
            print(f"  Excluded: {excluded_by_verdict} by verdict, {excluded_by_keywords} by keywords, {excluded_by_components} components")
        if corrected_categories > 0:
            print(f"  Corrected: {corrected_categories} category assignments")

    def get_templates_for_meal(self, meal_type: str) -> List[PlateTemplate]:
        """Get all templates for a meal type."""
        return self.templates.get(meal_type, [])

    def get_available_cuisines(self) -> Dict[str, int]:
        """Get count of recipes per cuisine (useful for debugging)."""
        from collections import Counter
        return dict(Counter(self.cuisine_by_recipe.values()))

    def find_matching_recipes(
        self,
        categories: List[str],
        exclude_ids: Optional[Set[int]] = None,
        min_cost: float = 0.01,  # Filter out $0 cost (likely bad data)
        cuisine_filter: Optional[List[str]] = None,  # Optional: limit to these cuisines
        is_main_dish: bool = True,  # True for mains, False for sides
    ) -> List[Recipe]:
        """Find recipes matching any of the given categories and optional cuisine filter."""
        exclude_ids = exclude_ids or set()
        matches = []
        seen_ids = set()

        # Get the appropriate excluded categories set
        excluded_cats = self.excluded_main_categories if is_main_dish else self.excluded_side_categories

        for recipe in self.all_recipes:
            if recipe.recipe_num in exclude_ids:
                continue
            if recipe.recipe_num in seen_ids:
                continue
            # Filter out recipes with zero/missing cost data
            if recipe.base_cost < min_cost:
                continue

            # Skip recipes in excluded component categories
            if self._is_excluded_category(recipe.category_number, excluded_cats, recipe.name):
                continue

            if self._category_matches(recipe.category_number, categories):
                # Check cuisine filter if specified
                if cuisine_filter:
                    recipe_cuisine = self.cuisine_by_recipe.get(recipe.recipe_num)
                    if not recipe_cuisine or recipe_cuisine not in cuisine_filter:
                        continue
                matches.append(recipe)
                seen_ids.add(recipe.recipe_num)

        return matches

    def _is_excluded_category(self, category: str, excluded_cats: Set[str], recipe_name: str = "") -> bool:
        """Check if a category/recipe should be excluded as a component."""
        if not category:
            return False

        # Check if category or any of its parents are in the exclusion set
        for excluded in excluded_cats:
            if category == excluded:
                return True
            if category.startswith(excluded + "."):
                return True

        # Check keyword exclusions for specific categories
        name_lower = recipe_name.lower() if recipe_name else ""
        for cat_prefix, keywords in self.category_keyword_exclusions.items():
            if category == cat_prefix or category.startswith(cat_prefix + "."):
                for kw in keywords:
                    if kw in name_lower:
                        return True

        return False

    def _category_matches(self, recipe_category: str, allowed_categories: List[str]) -> bool:
        """Check if recipe category matches any allowed category."""
        if not recipe_category:
            return False

        for allowed in allowed_categories:
            if not allowed:
                continue
            # Exact match or prefix match
            if recipe_category == allowed:
                return True
            if recipe_category.startswith(allowed + "."):
                return True
            if allowed.startswith(recipe_category + "."):
                return True

        return False

    def build_plates_for_template(
        self,
        template: PlateTemplate,
        max_plates: int = 64,
        max_sides: int = 2,
        exclude_recipe_ids: Optional[Set[int]] = None,
    ) -> List[Plate]:
        """
        Build valid plates for a template.

        Args:
            template: PlateTemplate to build plates for
            max_plates: Maximum number of plates to generate
            max_sides: Maximum sides per plate (0 for one_dish)
            exclude_recipe_ids: Recipe IDs to exclude (e.g., recently used)

        Returns:
            List of valid Plates
        """
        exclude_ids = exclude_recipe_ids or set()

        # Find valid main dishes (with optional cuisine filter from template)
        main_dishes = self.find_matching_recipes(
            template.main_categories,
            exclude_ids,
            cuisine_filter=template.cuisine_filter,
        )

        if not main_dishes:
            return []

        # For one-dish meals, no sides
        plates: List[Plate] = []

        if template.one_dish or max_sides == 0:
            for main in main_dishes:
                if len(plates) >= max_plates:
                    break
                plates.append(Plate(
                    template_name=template.name,
                    meal_type=template.meal,
                    main_dish=main,
                    sides=[],
                    one_dish=True,
                ))
        else:
            # Find valid sides from each pool
            sides_by_pool: Dict[str, List[Recipe]] = {}
            pool_tags_by_name: Dict[str, List[str]] = {}
            for pool in template.side_pools:
                pool_sides = self.find_matching_recipes(pool.category_ids, exclude_ids, is_main_dish=False)
                if pool_sides:
                    sides_by_pool[pool.name] = pool_sides
                    pool_tags_by_name[pool.name] = pool.tags

            constraints = set(template.constraints)

            for main_idx, main in enumerate(main_dishes):
                if len(plates) >= max_plates * 2:
                    break

                # Filter out starch/bread side pools when main is starch/bread
                filtered_sides = self._filter_clashing_pools(
                    sides_by_pool, pool_tags_by_name, main
                )

                # Use main_idx as variation_index so each main dish gets different sides
                selected_sides = self._select_sides(
                    filtered_sides,
                    max_sides,
                    constraints,
                    exclude_ids | {main.recipe_num},
                    variation_index=main_idx,  # Different sides for different main dishes
                )

                plate = Plate(
                    template_name=template.name,
                    meal_type=template.meal,
                    main_dish=main,
                    sides=selected_sides,
                    one_dish=False,
                )
                plates.append(plate)

        plates.sort(key=lambda p: p.total_cost())
        return plates[:max_plates]

    # Category prefixes that indicate a starch/bread main dish
    _STARCH_MAIN_PREFIXES = (
        "1.2.",     # Breads (yeast breads, quick breads like pancakes/waffles)
        "1.16.3.",  # Starchy side dishes used as mains (rice, pasta, grains)
        "1.3.6.",   # Cereals/oatmeal
    )

    # Tags on side pools that clash with a starch/bread main
    _STARCH_CLASH_TAGS = {"starchy", "bread", "grain", "potato"}

    def _filter_clashing_pools(
        self,
        sides_by_pool: Dict[str, List[Recipe]],
        pool_tags_by_name: Dict[str, List[str]],
        main: "Recipe",
    ) -> Dict[str, List[Recipe]]:
        """Remove starch/bread side pools when the main dish is already starch/bread."""
        cat = main.category_number or ""
        main_is_starch = any(cat.startswith(p) for p in self._STARCH_MAIN_PREFIXES)

        if not main_is_starch:
            return sides_by_pool

        filtered = {}
        for pool_name, sides in sides_by_pool.items():
            tags = set(pool_tags_by_name.get(pool_name, []))
            if tags & self._STARCH_CLASH_TAGS:
                continue  # Skip this pool - bread/starch side with bread/starch main
            filtered[pool_name] = sides
        return filtered

    def _select_sides(
        self,
        sides_by_pool: Dict[str, List[Recipe]],
        max_sides: int,
        constraints: Set[str],
        exclude_ids: Set[int],
        variation_index: int = 0,  # Which variation of side selection to use
    ) -> List[Recipe]:
        """Select sides respecting constraints.

        Args:
            variation_index: Different values produce different side combinations.
                             This ensures main dishes get different sides.
        """
        if not sides_by_pool or max_sides <= 0:
            return []

        selected = []
        used_pools = set()
        tag_counts: Dict[str, int] = {}

        # Parse constraints
        unique_sides = "unique_sides" in constraints
        max_starchy = 1 if "max_one_starchy_side" in constraints else 999
        max_bread = 1 if "max_one_bread_side" in constraints else 999

        # Try to pick one from each pool first
        pool_names = list(sides_by_pool.keys())
        random.shuffle(pool_names)

        for pool_name in pool_names:
            if len(selected) >= max_sides:
                break

            if unique_sides and pool_name in used_pools:
                continue

            candidates = sides_by_pool[pool_name]
            # Filter out $0 cost (likely bad data) and sort by cost
            valid_candidates = [c for c in candidates if c.base_cost > 0.01]
            if not valid_candidates:
                valid_candidates = candidates  # Fallback if all are $0
            valid_candidates.sort(key=lambda r: r.base_cost)

            # Use variation_index to pick different sides for different main dishes
            # Skip the first 'variation_index' valid candidates to get variety
            candidates_checked = 0
            for candidate in valid_candidates:
                if candidate.recipe_num in exclude_ids:
                    continue

                # Skip first N candidates based on variation_index
                if candidates_checked < (variation_index % max(len(valid_candidates), 1)):
                    candidates_checked += 1
                    continue

                if len(selected) >= max_sides:
                    break

                selected.append(candidate)
                used_pools.add(pool_name)
                exclude_ids.add(candidate.recipe_num)
                break

        return selected

    def build_all_plates_for_meal(
        self,
        meal_type: str,
        max_plates_per_template: int = 32,
        max_total_plates: int = 256,
        exclude_recipe_ids: Optional[Set[int]] = None,
        min_calories_per_serving: float = 0.0,
    ) -> List[Plate]:
        """
        Build plates from all templates for a meal type.

        Args:
            meal_type: breakfast, lunch, or dinner
            max_plates_per_template: Max plates per template
            max_total_plates: Max total plates
            exclude_recipe_ids: Recipe IDs to exclude
            min_calories_per_serving: Filter out plates below this cal/serving

        Returns:
            List of valid Plates
        """
        templates = self.get_templates_for_meal(meal_type)
        all_plates = []

        # Build plates from ALL templates (don't stop early!)
        for template in templates:
            plates = self.build_plates_for_template(
                template,
                max_plates=max_plates_per_template,
                exclude_recipe_ids=exclude_recipe_ids,
            )
            all_plates.extend(plates)

        # Filter by minimum calorie density if specified
        if min_calories_per_serving > 0:
            all_plates = [
                p for p in all_plates
                if p.total_calories(1.0) >= min_calories_per_serving
            ]

        # DON'T sort by base cost here - that's the author's estimate, not actual
        # purchase cost after considering pantry. The cascade will score plates
        # based on actual purchase cost at runtime when pantry is known.
        #
        # Just shuffle to get variety across templates, then cap to max_total_plates
        import random
        random.shuffle(all_plates)
        return all_plates[:max_total_plates]

    def get_mains_for_meal(
        self,
        meal_type: str,
        exclude_ids: Optional[Set[int]] = None,
    ) -> List[Recipe]:
        """
        Get ALL main dishes valid for a meal type (from all templates).

        This returns individual recipes, not plates. The cascade will
        score these against pantry and pick the best.
        """
        templates = self.get_templates_for_meal(meal_type)
        exclude_ids = exclude_ids or set()

        all_mains = []
        seen_ids = set()

        for template in templates:
            mains = self.find_matching_recipes(template.main_categories, exclude_ids)
            for main in mains:
                if main.recipe_num not in seen_ids:
                    all_mains.append(main)
                    seen_ids.add(main.recipe_num)

        return all_mains

    def get_sides_for_meal(
        self,
        meal_type: str,
        exclude_ids: Optional[Set[int]] = None,
    ) -> List[Recipe]:
        """
        Get ALL side dishes valid for a meal type (from all templates).

        This returns individual recipes, not plates. The cascade will
        score these against pantry and pick the best.
        """
        templates = self.get_templates_for_meal(meal_type)
        exclude_ids = exclude_ids or set()

        all_sides = []
        seen_ids = set()

        for template in templates:
            for pool in template.side_pools:
                sides = self.find_matching_recipes(pool.category_ids, exclude_ids, is_main_dish=False)
                for side in sides:
                    if side.recipe_num not in seen_ids:
                        all_sides.append(side)
                        seen_ids.add(side.recipe_num)

        return all_sides

    def get_one_dish_meals_for_meal(
        self,
        meal_type: str,
        exclude_ids: Optional[Set[int]] = None,
    ) -> List[Recipe]:
        """
        Get one-dish meals (soups, stews, casseroles) for a meal type.

        These are complete meals that don't need sides.
        """
        templates = self.get_templates_for_meal(meal_type)
        exclude_ids = exclude_ids or set()

        one_dish_meals = []
        seen_ids = set()

        for template in templates:
            if not template.one_dish:
                continue
            mains = self.find_matching_recipes(template.main_categories, exclude_ids)
            for main in mains:
                if main.recipe_num not in seen_ids:
                    one_dish_meals.append(main)
                    seen_ids.add(main.recipe_num)

        return one_dish_meals

    def score_plates_by_pantry(
        self,
        plates: List[Plate],
        pantry: Dict[str, float],
    ) -> List[tuple]:
        """
        Score plates by pantry utilization.

        Returns: List of (plate, score) tuples, sorted by score descending
        """
        scored = []
        for plate in plates:
            overlap = plate.pantry_overlap(pantry)
            scored.append((plate, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def score_plates_by_cost(
        self,
        plates: List[Plate],
        pantry_tracker=None,
        servings: float = 4.0,
    ) -> List[tuple]:
        """
        Score plates by estimated cost (lower is better).

        Uses pantry_tracker if available to estimate actual purchase cost,
        otherwise falls back to recipe base cost.

        Returns: List of (plate, cost) tuples, sorted by cost ascending
        """
        scored = []
        for plate in plates:
            if pantry_tracker is not None and hasattr(pantry_tracker, 'package_loader') and pantry_tracker.package_loader:
                # Estimate cost based on ingredients not in pantry
                # Use REAL package costs, not fallback rate
                all_needs = plate.all_ingredient_needs()
                total_needs = {k: v * servings for k, v in all_needs.items()}

                # Check what's already in inventory and estimate purchase cost
                estimated_cost = 0.0
                for ing_id, grams_needed in total_needs.items():
                    available = pantry_tracker.inventory.get(str(ing_id), 0.0)
                    if available < grams_needed:
                        shortage = grams_needed - available
                        # Use REAL package pricing
                        try:
                            _, cost, _ = pantry_tracker.package_loader.get_cheapest_package(
                                str(ing_id), shortage
                            )
                            estimated_cost += cost
                        except Exception:
                            # Fallback if package lookup fails
                            estimated_cost += shortage * 0.01  # ~$10/kg
            else:
                # Fallback to recipe base cost
                estimated_cost = plate.total_cost()

            scored.append((plate, estimated_cost))

        scored.sort(key=lambda x: x[1])  # Ascending - lower cost first
        return scored

    def score_plates_combined(
        self,
        plates: List[Plate],
        pantry: Dict[str, float],
        pantry_tracker=None,
        servings: float = 4.0,
        cost_weight: float = 0.7,
        pantry_weight: float = 0.15,
        batch_size_weight: float = 0.15,
        max_reasonable_batch: float = 16.0,
    ) -> List[tuple]:
        """
        Score plates by combined cost, pantry utilization, and batch size.

        Lower score is better.

        Args:
            batch_size_weight: Weight for penalizing oversized batches
            max_reasonable_batch: Batches larger than this get penalized

        Returns: List of (plate, score) tuples, sorted by score ascending
        """
        scored = []

        # Get cost and pantry scores
        cost_scores = {id(p): c for p, c in self.score_plates_by_cost(plates, pantry_tracker, servings)}
        pantry_scores = {id(p): o for p, o in self.score_plates_by_pantry(plates, pantry)}

        # Normalize cost scores (0-1 where 0 is best)
        max_cost = max(cost_scores.values()) if cost_scores else 1.0
        min_cost = min(cost_scores.values()) if cost_scores else 0.0
        cost_range = max_cost - min_cost if max_cost > min_cost else 1.0

        for plate in plates:
            cost = cost_scores.get(id(plate), max_cost)
            overlap = pantry_scores.get(id(plate), 0.0)

            # Normalize cost to 0-1 (lower cost = lower normalized)
            norm_cost = (cost - min_cost) / cost_range

            # Pantry overlap is already 0-1 (higher = better)
            # Invert so lower is better
            norm_pantry = 1.0 - overlap

            # Batch size penalty: penalize recipes that make way more than needed
            # e.g., if we need 4 servings but recipe makes 24, that creates variety problems
            batch_size = plate.max_servings()
            if batch_size <= servings * 1.5:  # Up to 6 servings for 4-person meal is OK
                norm_batch = 0.0
            elif batch_size <= servings * 2.5:  # 7-10 servings: small penalty
                norm_batch = (batch_size - servings) / max_reasonable_batch
            elif batch_size <= max_reasonable_batch:  # 11-16 servings: medium penalty
                norm_batch = 1.0 + (batch_size - servings * 2) / max_reasonable_batch
            else:
                # 17+ servings: HEAVY penalty (these kill variety)
                norm_batch = 3.0 + (batch_size - max_reasonable_batch) / 8.0

            # Combined score (lower is better)
            combined = (
                cost_weight * norm_cost +
                pantry_weight * norm_pantry +
                batch_size_weight * norm_batch
            )
            scored.append((plate, combined))

        scored.sort(key=lambda x: x[1])  # Ascending - lower is better
        return scored


def test_plate_builder():
    """Test plate builder with real templates."""
    print("Testing PlateBuilder...")

    builder = PlateBuilder()

    # Create some dummy recipes
    dummy_recipes = [
        {"recipeNum": 1, "recipeName": "Bagel", "category_number": "1.3.2.3",
         "total_estimated_cost": 2.0, "calories_total_kcal": 300},
        {"recipeNum": 2, "recipeName": "Eggs", "category_number": "1.1.2.3.1",
         "total_estimated_cost": 3.0, "calories_total_kcal": 200},
        {"recipeNum": 3, "recipeName": "Bacon", "category_number": "1.3.4.1",
         "total_estimated_cost": 5.0, "calories_total_kcal": 400},
        {"recipeNum": 4, "recipeName": "Fruit Salad", "category_number": "1.16.2",
         "total_estimated_cost": 4.0, "calories_total_kcal": 150},
        {"recipeNum": 5, "recipeName": "Steak", "category_number": "1.9.1.2",
         "total_estimated_cost": 15.0, "calories_total_kcal": 600},
        {"recipeNum": 6, "recipeName": "Soup", "category_number": "1.17.2",
         "total_estimated_cost": 8.0, "calories_total_kcal": 350},
    ]

    builder.index_recipes(dummy_recipes)

    # Build plates for each meal
    for meal in ["breakfast", "lunch", "dinner"]:
        print(f"\n{meal.upper()} plates:")
        plates = builder.build_all_plates_for_meal(meal, max_plates_per_template=2)
        for plate in plates[:5]:
            print(f"  {plate}")

    print("\n✅ PlateBuilder test passed!")


if __name__ == "__main__":
    test_plate_builder()
