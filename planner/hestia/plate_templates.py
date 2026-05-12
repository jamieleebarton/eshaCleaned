"""
GPU-Accelerated Plate Template System.

First-class template support with pre-computed GPU category masks.
ALL category matching is GPU-vectorized - no Python loops over recipes.

Key optimizations:
- Recipe categories encoded as integers on GPU
- Template allowed categories as sets of integer codes
- Prefix matching via pre-computed ancestry tensors
- Batch mask building with torch operations
"""

import json
import torch
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import time


@dataclass
class SidePool:
    """Definition of a side dish pool."""
    name: str
    category_ids: List[str]
    tags: List[str] = field(default_factory=list)


@dataclass
class PlateTemplate:
    """
    Definition of a plate structure.

    Specifies what components exist and which categories are valid.
    """
    name: str
    meal: str  # breakfast, lunch, dinner
    main_categories: List[str]
    side_pools: List[SidePool] = field(default_factory=list)
    drink_allowed: bool = True
    constraints: List[str] = field(default_factory=list)
    one_dish: bool = False

    @classmethod
    def from_dict(cls, data: Dict) -> "PlateTemplate":
        """Create template from dictionary (JSON format)."""
        side_pools = []
        for pool_data in data.get("side_pools", []):
            side_pools.append(SidePool(
                name=pool_data.get("name", ""),
                category_ids=pool_data.get("category_ids", []),
                tags=pool_data.get("tags", []),
            ))

        return cls(
            name=data.get("name", "unknown"),
            meal=data.get("meal", "dinner"),
            main_categories=data.get("main_categories", []),
            side_pools=side_pools,
            drink_allowed=data.get("drink_allowed", True),
            constraints=data.get("constraints", []),
            one_dish=data.get("one_dish", False),
        )


class GPUTemplateRegistry:
    """
    GPU-accelerated template registry.

    Pre-computes category masks using pure GPU tensor operations.
    No Python loops over recipes in the hot path.
    """

    def __init__(self, device: torch.device):
        self.device = device

        # Template storage
        self.templates: List[PlateTemplate] = []
        self.template_names: List[str] = []

        # Indices by meal type
        self.breakfast_indices: List[int] = []
        self.lunch_indices: List[int] = []
        self.dinner_indices: List[int] = []

        # Category encoding
        self.category_to_idx: Dict[str, int] = {}
        self.idx_to_category: Dict[int, str] = {}
        self.num_categories: int = 0

        # Recipe category codes: [num_recipes]
        self.recipe_categories: torch.Tensor = None
        self.num_recipes: int = 0

        # Pre-computed masks: [num_templates, num_recipes]
        self.main_masks: torch.Tensor = None

        # Side pool masks: List[List[Tensor]]
        self.side_pool_masks: List[List[torch.Tensor]] = []

        # One-dish flags: [num_templates]
        self.is_one_dish: torch.Tensor = None

        # Ancestry tensor for prefix matching: [num_categories, max_ancestors]
        # Each category knows its ancestors (prefixes)
        self.category_ancestors: torch.Tensor = None
        self.max_ancestors: int = 10

    def load_templates(self, templates_dir: str) -> None:
        """Load templates from JSON files."""
        templates_path = Path(templates_dir)

        for meal in ["breakfast", "lunch", "dinner"]:
            filepath = templates_path / f"{meal}.json"
            if not filepath.exists():
                print(f"Warning: {filepath} not found")
                continue

            with open(filepath) as f:
                template_list = json.load(f)

            for template_data in template_list:
                template_data["meal"] = meal
                template = PlateTemplate.from_dict(template_data)
                idx = len(self.templates)
                self.templates.append(template)
                self.template_names.append(template.name)

                if meal == "breakfast":
                    self.breakfast_indices.append(idx)
                elif meal == "lunch":
                    self.lunch_indices.append(idx)
                else:
                    self.dinner_indices.append(idx)

        print(f"Loaded {len(self.templates)} templates:")
        print(f"  Breakfast: {len(self.breakfast_indices)}")
        print(f"  Lunch: {len(self.lunch_indices)}")
        print(f"  Dinner: {len(self.dinner_indices)}")

    def build_category_index(self, recipe_pool: List[Dict]) -> None:
        """
        Build category index from recipes - CPU preprocessing.

        This is O(N) in recipes but just builds a dictionary.
        """
        start = time.time()

        # Collect all unique categories
        all_categories: Set[str] = set()

        for recipe in recipe_pool:
            cat = str(recipe.get("category_number", "") or "")
            if cat:
                all_categories.add(cat)

        # Add template categories
        for template in self.templates:
            for cat in template.main_categories:
                if cat:
                    all_categories.add(cat)
            for pool in template.side_pools:
                for cat in pool.category_ids:
                    if cat:
                        all_categories.add(cat)

        # Also add all prefixes (ancestors)
        prefixes = set()
        for cat in all_categories:
            parts = cat.split(".")
            for i in range(1, len(parts)):
                prefixes.add(".".join(parts[:i]))
        all_categories.update(prefixes)

        # Sort and index
        sorted_cats = sorted(all_categories)
        self.category_to_idx = {cat: i + 1 for i, cat in enumerate(sorted_cats)}
        self.idx_to_category = {i + 1: cat for i, cat in enumerate(sorted_cats)}
        self.num_categories = len(sorted_cats) + 1  # 0 = unknown

        print(f"Built category index: {self.num_categories} categories ({time.time()-start:.2f}s)")

    def _build_ancestry_tensor(self) -> None:
        """
        Build tensor mapping each category to its ancestors (prefixes).

        This enables GPU-based prefix matching.
        """
        # ancestry[cat_idx] = [ancestor1_idx, ancestor2_idx, ..., 0, 0, ...]
        ancestry = torch.zeros(
            self.num_categories, self.max_ancestors,
            dtype=torch.long, device=self.device
        )

        for cat, idx in self.category_to_idx.items():
            parts = cat.split(".")
            ancestors = []
            # Add self
            ancestors.append(idx)
            # Add all prefixes
            for i in range(1, len(parts)):
                prefix = ".".join(parts[:i])
                if prefix in self.category_to_idx:
                    ancestors.append(self.category_to_idx[prefix])

            # Fill tensor (up to max_ancestors)
            for i, anc_idx in enumerate(ancestors[:self.max_ancestors]):
                ancestry[idx, i] = anc_idx

        self.category_ancestors = ancestry

    def index_recipes(self, recipe_pool: List[Dict]) -> None:
        """
        Index recipes using GPU-accelerated operations.
        """
        start = time.time()
        self.num_recipes = len(recipe_pool)

        # Build ancestry tensor first
        self._build_ancestry_tensor()

        # Build recipe category tensor (single pass through recipes)
        recipe_categories = torch.zeros(self.num_recipes, dtype=torch.long, device='cpu')
        for i, recipe in enumerate(recipe_pool):
            cat = str(recipe.get("category_number", "") or "")
            recipe_categories[i] = self.category_to_idx.get(cat, 0)

        self.recipe_categories = recipe_categories.to(self.device)
        print(f"  Recipe categories indexed ({time.time()-start:.2f}s)")

        # Build masks using GPU operations
        start = time.time()
        num_templates = len(self.templates)
        self.main_masks = torch.zeros(
            num_templates, self.num_recipes,
            dtype=torch.bool, device=self.device
        )
        self.side_pool_masks = []
        self.is_one_dish = torch.zeros(num_templates, dtype=torch.bool, device=self.device)

        for t_idx, template in enumerate(self.templates):
            # Main dish mask - GPU vectorized
            self.main_masks[t_idx] = self._build_category_mask_gpu(template.main_categories)

            # Side pool masks
            pool_masks = []
            for pool in template.side_pools:
                mask = self._build_category_mask_gpu(pool.category_ids)
                pool_masks.append(mask)
            self.side_pool_masks.append(pool_masks)

            # One-dish flag
            self.is_one_dish[t_idx] = template.one_dish

        print(f"  Template masks built ({time.time()-start:.2f}s)")
        print(f"Indexed {self.num_recipes} recipes against {num_templates} templates")

    def _build_category_mask_gpu(self, allowed_categories: List[str]) -> torch.Tensor:
        """
        Build boolean mask using pure GPU tensor operations.

        A recipe matches if its category OR any of its ancestors
        is in the allowed set.
        """
        if not allowed_categories:
            return torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)

        # Convert allowed categories to index set
        allowed_indices = set()
        for cat in allowed_categories:
            if cat and cat in self.category_to_idx:
                allowed_indices.add(self.category_to_idx[cat])

        if not allowed_indices:
            return torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)

        # Create allowed tensor [num_allowed]
        allowed_tensor = torch.tensor(
            list(allowed_indices), dtype=torch.long, device=self.device
        )

        # Get recipe category indices [N]
        recipe_cats = self.recipe_categories  # [N]

        # Get ancestors for each recipe's category [N, max_ancestors]
        recipe_ancestors = self.category_ancestors[recipe_cats]  # [N, max_ancestors]

        # Check if ANY ancestor is in allowed set
        # Expand for broadcasting: [N, max_ancestors, 1] vs [1, 1, num_allowed]
        ancestors_exp = recipe_ancestors.unsqueeze(2)  # [N, max_ancestors, 1]
        allowed_exp = allowed_tensor.unsqueeze(0).unsqueeze(0)  # [1, 1, num_allowed]

        # Match: [N, max_ancestors, num_allowed]
        matches = ancestors_exp == allowed_exp

        # Any match across ancestors and allowed categories
        mask = matches.any(dim=2).any(dim=1)  # [N]

        return mask

    def get_templates_for_meal(self, meal_type: str) -> List[int]:
        """Get template indices for a meal type."""
        if meal_type == "breakfast":
            return self.breakfast_indices
        elif meal_type == "lunch":
            return self.lunch_indices
        else:
            return self.dinner_indices

    def get_main_mask(self, template_idx: int) -> torch.Tensor:
        """Get main dish mask for a template: [num_recipes] boolean."""
        return self.main_masks[template_idx]

    def get_combined_main_mask_for_meal(self, meal_type: str) -> torch.Tensor:
        """
        Get combined main dish mask for all templates of a meal type.

        Returns mask where recipe is valid for ANY template of this meal.
        """
        template_indices = self.get_templates_for_meal(meal_type)
        if not template_indices:
            return torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)

        combined = torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)
        for t_idx in template_indices:
            combined |= self.main_masks[t_idx]

        return combined

    def get_side_pool_mask(self, template_idx: int, pool_idx: int) -> torch.Tensor:
        """Get mask for a specific side pool: [num_recipes] boolean."""
        pools = self.side_pool_masks[template_idx]
        if pool_idx < len(pools):
            return pools[pool_idx]
        return torch.zeros(self.num_recipes, dtype=torch.bool, device=self.device)

    def get_template_by_name(self, name: str) -> Optional[PlateTemplate]:
        """Look up template by name."""
        for template in self.templates:
            if template.name == name:
                return template
        return None

    def sample_template_for_slot(self, slot: int, generator: torch.Generator = None) -> int:
        """Sample a random template index for a slot."""
        meal_type = ["breakfast", "lunch", "dinner"][slot % 3]
        indices = self.get_templates_for_meal(meal_type)

        if not indices:
            return 0

        if generator is not None:
            rand_idx = torch.randint(len(indices), (1,), generator=generator).item()
        else:
            rand_idx = torch.randint(len(indices), (1,)).item()

        return indices[rand_idx]


def load_template_registry(
    templates_dir: str,
    recipe_pool: List[Dict],
    device: torch.device,
) -> GPUTemplateRegistry:
    """
    Convenience function to load and initialize template registry.

    Args:
        templates_dir: Path to plate_templates directory
        recipe_pool: List of recipe dictionaries
        device: GPU device

    Returns:
        Fully initialized GPUTemplateRegistry
    """
    registry = GPUTemplateRegistry(device)
    registry.load_templates(templates_dir)
    registry.build_category_index(recipe_pool)
    registry.index_recipes(recipe_pool)
    return registry
