"""
GPU-First Data Structures for Weekly Meal Planning.

ALL state lives on GPU tensors. No Python objects in hot paths.

Key design:
- GPUBeamState: Vectorized beam state with dense tensors
- GPUNutritionTargets: Weekly targets as GPU tensor
- Constants and indexing utilities

Tensor shapes:
- Pantry: [B, num_ingredients] - grams available
- Leftovers: [B, max_leftovers, LEFTOVER_FIELDS] - (recipe_id, servings, ttl, cal, prot, meal_type, is_frozen, dish_type, template_id, grams)
- Nutrition accumulated: [B, NUM_NUTRIENTS]
- Selections: [B, 21] - candidate index per slot
"""

import math
import re

import torch
import torch.nn.functional as F
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ============================================================================
# CONSTANTS
# ============================================================================

NUM_SLOTS = 21  # 7 days × 3 meals
NUM_NUTRIENTS = 10
MAX_LEFTOVERS = 128  # Max leftover items tracked per beam (doubled for single-person households)
MAX_RECENT_RECIPES = 84  # Track all recipe IDs (main + sides) for variety constraint
LEFTOVER_FIELDS = 10  # Fields: recipe_id, servings, ttl, cal, prot, meal_type, is_frozen, dish_type, template_id, grams

# Pantry TTL defaults (days)
DEFAULT_SHELF_DAYS = 90  # Default for unknown ingredients
FROZEN_SHELF_DAYS = 60   # Default frozen shelf life extension

NUTRIENT_NAMES = [
    "calories",      # 0
    "protein",       # 1
    "carbs",         # 2
    "fat",           # 3
    "fiber",         # 4
    "vegetables",    # 5
    "fruits",        # 6
    "grains",        # 7
    "dairy",         # 8
    "protein_foods", # 9
]

NUTRIENT_IDX = {name: i for i, name in enumerate(NUTRIENT_NAMES)}

# Meal types per slot (repeating pattern)
MEAL_TYPES = ["breakfast", "lunch", "dinner"] * 7
MEAL_TYPE_TO_IDX = {"breakfast": 0, "lunch": 1, "dinner": 2}


# ============================================================================
# GPU BEAM STATE
# ============================================================================

class GPUBeamState:
    """
    Fully GPU-resident beam state.

    ALL tensors stay on GPU. No Python loops over beams.
    Supports vectorized expansion, selection, and updates.
    """

    def __init__(
        self,
        B: int,
        num_ingredients: int,
        device: torch.device,
    ):
        """
        Initialize beam state tensors.

        Args:
            B: Number of beams
            num_ingredients: Size of ingredient vocabulary
            device: GPU device
        """
        self.B = B
        self.num_ingredients = num_ingredients
        self.device = device

        # === CORE STATE TENSORS ===

        # Nutrition accumulated: [B, NUM_NUTRIENTS]
        self.nutrition = torch.zeros(
            B, NUM_NUTRIENTS,
            dtype=torch.float32, device=device
        )

        # Total cost: [B]
        self.cost = torch.zeros(B, dtype=torch.float32, device=device)

        # Selections made: [B, NUM_SLOTS] - candidate index per slot
        self.selections = torch.zeros(
            B, NUM_SLOTS,
            dtype=torch.long, device=device
        )

        # Current slot (same for all beams): scalar
        self.current_slot = 0

        # Beam scores: [B]
        self.scores = torch.zeros(B, dtype=torch.float32, device=device)

        # === PANTRY STATE ===
        # Dense tensor: [B, num_ingredients] - grams available per ingredient
        self.pantry = torch.zeros(
            B, num_ingredients,
            dtype=torch.float32, device=device
        )

        # === PANTRY TTL TRACKING (for perishable urgency scoring) ===
        # Days until each ingredient expires: [B, num_ingredients]
        # Higher = fresher, 0 = expires today, negative = spoiled
        self.pantry_ttl = torch.full(
            (B, num_ingredients), DEFAULT_SHELF_DAYS,
            dtype=torch.float32, device=device
        )

        # Is each ingredient frozen: [B, num_ingredients]
        # Frozen items don't decay but have quality loss
        self.pantry_frozen = torch.zeros(
            B, num_ingredients,
            dtype=torch.bool, device=device
        )

        # === LEFTOVER STATE ===
        # Leftover tensor: [B, MAX_LEFTOVERS, 7]
        # Each leftover: (recipe_idx, servings, ttl, cal_per_srv, prot_per_srv, meal_type, is_frozen)
        # meal_type: 0=breakfast, 1=lunch, 2=dinner
        # is_frozen: 0=fresh (in fridge), 1=frozen (in freezer)
        self.leftovers = torch.zeros(
            B, MAX_LEFTOVERS, LEFTOVER_FIELDS,
            dtype=torch.float32, device=device
        )

        # Number of active leftovers per beam: [B]
        self.num_leftovers = torch.zeros(B, dtype=torch.long, device=device)

        # === VARIETY TRACKING ===
        # All used recipe IDs (main + sides): [B, MAX_RECENT_RECIPES]
        # 21 slots * 4 recipes per slot (main + 3 sides) = 84 max
        self.used_recipe_ids = torch.zeros(
            B, MAX_RECENT_RECIPES,
            dtype=torch.long, device=device
        )

        # Count of used recipes per beam: [B]
        self.used_count = torch.zeros(B, dtype=torch.long, device=device)

        # Legacy - keep for compatibility
        self.recent_recipes = self.used_recipe_ids
        self.recent_count = self.used_count

    def expand(self, K: int) -> "GPUBeamState":
        """
        Expand B beams to B×K beams (one for each candidate).

        Uses repeat_interleave for efficient GPU expansion.
        Each original beam is duplicated K times.

        Args:
            K: Number of candidates per slot

        Returns:
            New GPUBeamState with B×K beams
        """
        BK = self.B * K
        expanded = GPUBeamState(BK, self.num_ingredients, self.device)

        # Repeat each beam K times along dim 0
        expanded.nutrition = self.nutrition.repeat_interleave(K, dim=0)
        expanded.cost = self.cost.repeat_interleave(K, dim=0)
        expanded.selections = self.selections.repeat_interleave(K, dim=0)
        expanded.scores = self.scores.repeat_interleave(K, dim=0)
        expanded.pantry = self.pantry.repeat_interleave(K, dim=0)
        expanded.pantry_ttl = self.pantry_ttl.repeat_interleave(K, dim=0)
        expanded.pantry_frozen = self.pantry_frozen.repeat_interleave(K, dim=0)
        expanded.leftovers = self.leftovers.repeat_interleave(K, dim=0)
        expanded.num_leftovers = self.num_leftovers.repeat_interleave(K, dim=0)
        expanded.used_recipe_ids = self.used_recipe_ids.repeat_interleave(K, dim=0)
        expanded.used_count = self.used_count.repeat_interleave(K, dim=0)
        expanded.recent_recipes = expanded.used_recipe_ids  # Alias
        expanded.recent_count = expanded.used_count  # Alias
        expanded.current_slot = self.current_slot

        return expanded

    def select_topk(self, scores: torch.Tensor, k: int) -> "GPUBeamState":
        """
        Keep top-k beams by score using torch.topk.

        Args:
            scores: [B] tensor of beam scores
            k: Number of beams to keep

        Returns:
            New GPUBeamState with top-k beams
        """
        k = min(k, self.B)
        _, indices = torch.topk(scores, k)

        selected = GPUBeamState(k, self.num_ingredients, self.device)
        selected.nutrition = self.nutrition[indices]
        selected.cost = self.cost[indices]
        selected.selections = self.selections[indices]
        selected.scores = scores[indices]
        selected.pantry = self.pantry[indices]
        selected.pantry_ttl = self.pantry_ttl[indices]
        selected.pantry_frozen = self.pantry_frozen[indices]
        selected.leftovers = self.leftovers[indices]
        selected.num_leftovers = self.num_leftovers[indices]
        selected.used_recipe_ids = self.used_recipe_ids[indices]
        selected.used_count = self.used_count[indices]
        selected.recent_recipes = selected.used_recipe_ids  # Alias
        selected.recent_count = selected.used_count  # Alias
        selected.current_slot = self.current_slot

        return selected

    def clone(self) -> "GPUBeamState":
        """Create a deep copy of this state."""
        cloned = GPUBeamState(self.B, self.num_ingredients, self.device)
        cloned.nutrition = self.nutrition.clone()
        cloned.cost = self.cost.clone()
        cloned.selections = self.selections.clone()
        cloned.scores = self.scores.clone()
        cloned.pantry = self.pantry.clone()
        cloned.pantry_ttl = self.pantry_ttl.clone()
        cloned.pantry_frozen = self.pantry_frozen.clone()
        cloned.leftovers = self.leftovers.clone()
        cloned.num_leftovers = self.num_leftovers.clone()
        cloned.used_recipe_ids = self.used_recipe_ids.clone()
        cloned.used_count = self.used_count.clone()
        cloned.recent_recipes = cloned.used_recipe_ids  # Alias
        cloned.recent_count = cloned.used_count  # Alias
        cloned.current_slot = self.current_slot
        return cloned

    def decay_leftovers(self) -> torch.Tensor:
        """
        Decay TTL for all leftovers and remove expired ones.

        Called at end of each day (every 3 slots).

        Returns:
            [B] tensor of wasted servings per beam
        """
        # Decrement TTL: leftovers[:, :, 2] -= 1
        self.leftovers[:, :, 2] -= 1

        # Find expired (TTL < 0)
        expired_mask = self.leftovers[:, :, 2] < 0  # [B, MAX_LEFTOVERS]

        # Calculate waste (servings of expired leftovers)
        waste = (self.leftovers[:, :, 1] * expired_mask.float()).sum(dim=1)  # [B]

        # Zero out expired leftovers
        self.leftovers[:, :, 1] = torch.where(
            expired_mask,
            torch.zeros_like(self.leftovers[:, :, 1]),
            self.leftovers[:, :, 1]
        )

        return waste

    def decay_pantry_ttl(self, days: int = 1) -> torch.Tensor:
        """
        Decay TTL for all pantry items (fresh and frozen).

        Called at end of each day (every 3 slots).

        Args:
            days: Number of days to decay (default 1)

        Returns:
            [B] tensor of wasted grams per beam (from items that expired)
        """
        # Decay TTL for ALL pantry items (fresh and frozen both expire)
        # Fresh items: 4-14 day shelf life, Frozen items: 60 day shelf life
        self.pantry_ttl = self.pantry_ttl - days

        # Find expired items (TTL < 0 and has grams)
        expired_mask = (self.pantry_ttl < 0) & (self.pantry > 0)  # [B, num_ingredients]

        # Calculate waste (grams of expired items)
        waste = (self.pantry * expired_mask.float()).sum(dim=1)  # [B]

        # Zero out expired pantry items
        self.pantry = torch.where(
            expired_mask,
            torch.zeros_like(self.pantry),
            self.pantry
        )

        return waste

    def auto_freeze_expiring(
        self,
        freezable: torch.Tensor,  # [num_ingredients] bool
        freezer_capacity_kg: float = 20.0,
    ) -> torch.Tensor:
        """
        Auto-freeze items about to expire (TTL <= 1) if freezable.

        GPU-optimized: processes all beams in parallel.

        Args:
            freezable: [num_ingredients] bool tensor - which ingredients can be frozen
            freezer_capacity_kg: Maximum freezer capacity in kg

        Returns:
            [B] tensor of grams frozen per beam
        """
        # Find items about to expire (TTL <= 1) that can be frozen and aren't already frozen
        about_to_expire = (self.pantry_ttl <= 1) & (self.pantry > 0)  # [B, I]
        can_freeze = about_to_expire & freezable.unsqueeze(0) & (~self.pantry_frozen)  # [B, I]

        # Calculate current freezer usage: sum of frozen grams per beam
        freezer_used = (self.pantry * self.pantry_frozen.float()).sum(dim=1, keepdim=True)  # [B, 1]
        freezer_capacity_g = freezer_capacity_kg * 1000  # Convert to grams

        # How much space left in freezer
        freezer_space = (freezer_capacity_g - freezer_used).clamp(min=0)  # [B, 1]

        # Only freeze if there's space
        # For simplicity, freeze everything that fits (could prioritize by urgency)
        grams_to_freeze = self.pantry * can_freeze.float()  # [B, I]

        # Check capacity - for now, just freeze up to capacity per beam
        # Cumulative sum to track space used as we freeze each ingredient
        # This is a simplified approach - freeze in order until capacity is hit
        cumsum_grams = grams_to_freeze.cumsum(dim=1)  # [B, I]
        under_capacity = cumsum_grams <= freezer_space  # [B, I]

        # Final mask: can freeze AND under capacity
        freeze_mask = can_freeze & under_capacity  # [B, I]

        # Mark as frozen
        self.pantry_frozen = self.pantry_frozen | freeze_mask

        # Reset TTL for frozen items
        self.pantry_ttl = torch.where(
            freeze_mask,
            torch.full_like(self.pantry_ttl, FROZEN_SHELF_DAYS),
            self.pantry_ttl
        )

        # Track how much was frozen
        grams_frozen = (self.pantry * freeze_mask.float()).sum(dim=1)  # [B]

        return grams_frozen

    def get_urgency_weights(self) -> torch.Tensor:
        """
        Get urgency weights for pantry items based on TTL.

        Items closer to expiration get higher urgency (used for scoring).

        Returns:
            [B, num_ingredients] urgency weights (higher = more urgent)
        """
        # Urgency = 1 / max(ttl, 1) for ALL items (fresh and frozen)
        # Frozen items naturally have longer TTL (60 days) so lower urgency
        # But as they age, urgency increases - they WILL be used before expiring
        ttl_clamped = self.pantry_ttl.clamp(min=1)
        urgency = 1.0 / ttl_clamped

        # Frozen items still have slightly lower priority than same-TTL fresh items
        # (prefer fresh for quality), but urgency scales with TTL so they get used
        frozen_factor = torch.where(
            self.pantry_frozen,
            torch.full_like(urgency, 0.5),  # 50% of fresh urgency (not 10%!)
            torch.ones_like(urgency)
        )

        return urgency * frozen_factor


# ============================================================================
# PERISHABILITY INDEX (for TTL classification by FNDDS prefix)
# ============================================================================

class PerishabilityIndex:
    """
    Maps ingredient FNDDS codes to perishability categories.

    Provides:
    - Shelf life (days) per ingredient
    - Freezability (can it be frozen?)
    - GPU tensors for efficient scoring
    """

    def __init__(self, perishability_map_path: str = None, device: torch.device = None):
        """
        Load perishability data from JSON config.

        Args:
            perishability_map_path: Path to perishability_map.json
            device: GPU device for tensors
        """
        import json
        from pathlib import Path

        if perishability_map_path is None:
            perishability_map_path = Path(__file__).parent / "perishability_map.json"

        if device:
            self.device = device
        elif torch.cuda.is_available():
            self.device = torch.device('cuda')
        elif torch.backends.mps.is_available():
            self.device = torch.device('mps')
        else:
            self.device = torch.device('cpu')

        # Load perishability map
        with open(perishability_map_path) as f:
            self.map = json.load(f)

        self.categories = self.map.get("categories", {})
        self.default = self.map.get("default", {"shelf_days": 90, "can_freeze": False})
        self.frozen_shelf_days = self.map.get("frozen_shelf_days", 60)
        self.freezer_capacity_kg = self.map.get("freezer_capacity_kg", 20.0)
        self._card_overrides: Dict[str, Tuple[str, Dict]] = {}
        self._build_card_overrides(Path(perishability_map_path).parent.parent / "data" / "fndds_cards_v2.json")

        # Build prefix -> category lookup
        self._prefix_to_category = {}
        for category, info in self.categories.items():
            for prefix in info.get("prefixes", []):
                self._prefix_to_category[prefix] = (category, info)

        # GPU tensors (built lazily when ingredient index is provided)
        self._shelf_life: Optional[torch.Tensor] = None  # [num_ingredients]
        self._freezable: Optional[torch.Tensor] = None   # [num_ingredients]
        self._loss_rate: Optional[torch.Tensor] = None   # [num_ingredients]

    def _build_card_overrides(self, cards_path) -> None:
        """Build exact FPID shelf-life overrides from canonical FNDDS cards."""
        if not cards_path.exists():
            return

        import json

        shelf_stable_forms = {"canned", "dry", "liquid", "powder"}
        shelf_stable_info = {
            "prefixes": [],
            "shelf_days": 365,
            "loss_rate_per_week": 0.01,
            "can_freeze": False,
            "examples": ["canonical card: ambient shelf-stable form"],
        }
        frozen_info = {
            "prefixes": [],
            "shelf_days": 365,
            "loss_rate_per_week": 0.01,
            "can_freeze": False,
            "examples": ["canonical card: frozen product"],
        }
        try:
            cards = json.loads(cards_path.read_text())
        except Exception:
            return

        for fpid, card in cards.items():
            temperature = str(card.get("temperature") or "").lower()
            form = str(card.get("form") or "").lower()
            if temperature == "frozen":
                self._card_overrides[str(fpid)] = ("frozen_card", frozen_info)
            elif temperature == "ambient" and form in shelf_stable_forms:
                self._card_overrides[str(fpid)] = ("shelf_stable_card", shelf_stable_info)

    def classify_fpid(self, fpid: str) -> Tuple[str, Dict]:
        """
        Classify an ingredient by its FNDDS code.

        Args:
            fpid: FNDDS code (e.g., "11020100")

        Returns:
            (category_name, category_info) tuple
        """
        exact = self._card_overrides.get(str(fpid))
        if exact is not None:
            return exact

        # Try longest match first (full FPID down to 1 char) so specific
        # overrides (e.g. 8-char "75217520" for Hominy) beat broad prefixes.
        for prefix_len in range(len(fpid), 0, -1):
            prefix = fpid[:prefix_len]
            if prefix in self._prefix_to_category:
                return self._prefix_to_category[prefix]

        return "unknown", self.default

    def build_gpu_tensors(self, ingredient_index: "IngredientIndex") -> None:
        """
        Pre-build GPU tensors for efficient perishability lookups.

        Args:
            ingredient_index: Maps dense indices to FNDDS codes
        """
        num_ing = ingredient_index.num_ingredients

        # Initialize with defaults
        shelf_life = torch.full((num_ing,), float(self.default["shelf_days"]),
                               dtype=torch.float32, device=self.device)
        freezable = torch.zeros((num_ing,), dtype=torch.bool, device=self.device)
        loss_rate = torch.full((num_ing,), self.default.get("loss_rate_per_week", 0.05),
                              dtype=torch.float32, device=self.device)

        # Classify each ingredient
        for idx in range(num_ing):
            fpid = ingredient_index.idx_to_fpid.get(idx, "")
            category, info = self.classify_fpid(fpid)

            shelf_life[idx] = float(info.get("shelf_days", 90))
            freezable[idx] = bool(info.get("can_freeze", False))
            loss_rate[idx] = float(info.get("loss_rate_per_week", 0.05))

        self._shelf_life = shelf_life
        self._freezable = freezable
        self._loss_rate = loss_rate

        print(f"PerishabilityIndex: Built GPU tensors for {num_ing} ingredients")
        print(f"  Freezable: {freezable.sum().item()}/{num_ing} ingredients")
        perishable = (shelf_life < 14).sum().item()
        print(f"  Highly perishable (<14 days): {perishable}/{num_ing} ingredients")

    @property
    def shelf_life_tensor(self) -> torch.Tensor:
        """[num_ingredients] tensor of shelf life in days."""
        if self._shelf_life is None:
            raise RuntimeError("Call build_gpu_tensors() first!")
        return self._shelf_life

    @property
    def freezable_tensor(self) -> torch.Tensor:
        """[num_ingredients] bool tensor - which ingredients can be frozen."""
        if self._freezable is None:
            raise RuntimeError("Call build_gpu_tensors() first!")
        return self._freezable

    @property
    def loss_rate_tensor(self) -> torch.Tensor:
        """[num_ingredients] tensor of weekly loss rate (fraction)."""
        if self._loss_rate is None:
            raise RuntimeError("Call build_gpu_tensors() first!")
        return self._loss_rate

    def initialize_pantry_ttl(
        self,
        ingredient_index: "IngredientIndex",
        pantry: torch.Tensor,  # [num_ingredients] grams
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Initialize TTL and frozen status for pantry items.

        Newly purchased items start with full shelf life.

        Args:
            ingredient_index: Maps dense indices to FNDDS codes
            pantry: [num_ingredients] tensor of grams

        Returns:
            (ttl [num_ingredients], frozen [num_ingredients])
        """
        if self._shelf_life is None:
            self.build_gpu_tensors(ingredient_index)

        # All items start fresh with full shelf life
        ttl = self._shelf_life.clone()

        # All items start not frozen
        frozen = torch.zeros_like(pantry, dtype=torch.bool)

        return ttl, frozen


# ============================================================================
# NUTRITION TARGETS
# ============================================================================

@dataclass
class NutritionTargets:
    """
    Weekly nutrition targets.

    Converts per-person daily goals to weekly totals.
    Provides GPU tensor for vectorized scoring.
    """

    # Per-person daily targets
    calories_per_day: float = 2000.0
    protein_per_day: float = 50.0  # grams
    carbs_per_day: float = 250.0
    fat_per_day: float = 65.0
    fiber_per_day: float = 25.0

    # Macro percentage targets (must sum to 100)
    # USDA ranges: protein 10-35%, carbs 45-65%, fat 20-35%
    protein_pct_target: float = 15.0
    carbs_pct_target: float = 50.0
    fat_pct_target: float = 35.0

    # Tolerance band: how far off-target before penalty
    macro_tolerance_pct: float = 5.0

    # Food group targets (grams per day per person)
    vegetables_per_day: float = 300.0
    fruits_per_day: float = 200.0
    grains_per_day: float = 170.0
    dairy_per_day: float = 300.0
    protein_foods_per_day: float = 155.0

    # Household size
    num_people: int = 4
    num_days: int = 7

    def to_weekly_tensor(self, device: torch.device) -> torch.Tensor:
        """
        Convert to weekly totals as GPU tensor.

        Returns:
            [NUM_NUTRIENTS] tensor of weekly targets
        """
        daily = torch.tensor([
            self.calories_per_day,
            self.protein_per_day,
            self.carbs_per_day,
            self.fat_per_day,
            self.fiber_per_day,
            self.vegetables_per_day,
            self.fruits_per_day,
            self.grains_per_day,
            self.dairy_per_day,
            self.protein_foods_per_day,
        ], dtype=torch.float32, device=device)

        return daily * self.num_people * self.num_days

    def to_per_meal_tensor(self, device: torch.device) -> torch.Tensor:
        """
        Convert to per-meal targets as GPU tensor.

        Assumes 3 meals per day, equal distribution.

        Returns:
            [NUM_NUTRIENTS] tensor of per-meal targets (for all people)
        """
        return self.to_weekly_tensor(device) / NUM_SLOTS


# ============================================================================
# PLAN RESULT
# ============================================================================

@dataclass
class GPUPlanResult:
    """
    Result from GPU beam search planning.

    Contains both GPU tensors (for further processing) and
    Python-friendly summaries (for display).
    """

    # GPU tensors
    selections: torch.Tensor  # [NUM_SLOTS] - candidate indices
    nutrition_totals: torch.Tensor  # [NUM_NUTRIENTS]

    # Python values
    total_cost: float
    compliance: Dict[str, float]  # nutrient name -> ratio achieved

    # Planning stats
    beams_explored: int
    beams_pruned: int
    runtime_ms: float

    # Optional: detailed per-slot info
    slot_costs: Optional[torch.Tensor] = None  # [NUM_SLOTS]
    slot_nutrition: Optional[torch.Tensor] = None  # [NUM_SLOTS, NUM_NUTRIENTS]
    leftover_waste: float = 0.0

    # Final state for multi-week planning
    final_pantry: Optional[torch.Tensor] = None  # [num_ingredients]

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            "=" * 60,
            "GPU WEEKLY PLANNER RESULT",
            "=" * 60,
            f"Total Cost: ${self.total_cost:.2f}",
            f"Leftover Waste: {self.leftover_waste:.1f} servings",
            "",
            "Nutrition Compliance:",
        ]

        for name, ratio in self.compliance.items():
            pct = ratio * 100
            status = "✓" if pct >= 90 else "✗"
            lines.append(f"  {status} {name}: {pct:.0f}%")

        avg_compliance = sum(self.compliance.values()) / len(self.compliance)
        lines.extend([
            "",
            f"Overall Compliance: {avg_compliance * 100:.1f}%",
            f"Beams Explored: {self.beams_explored:,}",
            f"Beams Pruned: {self.beams_pruned:,}",
            f"Runtime: {self.runtime_ms:.1f}ms",
            "=" * 60,
        ])

        return "\n".join(lines)


# ============================================================================
# FEASIBILITY BOUNDS (GPU)
# ============================================================================

class GPUFeasibilityBounds:
    """
    GPU-resident feasibility bounds for beam pruning.

    Pre-computes min/max achievable nutrition for remaining slots.
    Used to prune beams that cannot possibly satisfy constraints.
    """

    def __init__(
        self,
        nutrition_min: torch.Tensor,  # [NUM_SLOTS, NUM_NUTRIENTS]
        nutrition_max: torch.Tensor,  # [NUM_SLOTS, NUM_NUTRIENTS]
        cost_min: torch.Tensor,  # [NUM_SLOTS]
        cost_max: torch.Tensor,  # [NUM_SLOTS]
        device: torch.device,
    ):
        self.device = device

        # Cumulative bounds from slot t to end
        # cumsum from end to compute remaining achievable
        self.nutrition_min_remaining = torch.flip(
            torch.flip(nutrition_min, [0]).cumsum(dim=0), [0]
        )
        self.nutrition_max_remaining = torch.flip(
            torch.flip(nutrition_max, [0]).cumsum(dim=0), [0]
        )
        self.cost_min_remaining = torch.flip(
            torch.flip(cost_min, [0]).cumsum(dim=0), [0]
        )
        self.cost_max_remaining = torch.flip(
            torch.flip(cost_max, [0]).cumsum(dim=0), [0]
        )

    def can_satisfy_batch(
        self,
        slot: int,
        remaining_debt: torch.Tensor,  # [B, NUM_NUTRIENTS]
        tolerance: float = 0.1,
    ) -> torch.Tensor:
        """
        Check which beams can possibly satisfy remaining targets.

        Vectorized over all B beams.

        Args:
            slot: Current slot (0-20)
            remaining_debt: [B, NUM_NUTRIENTS] what each beam still needs
            tolerance: Allow this fraction below target

        Returns:
            [B] boolean tensor - True if beam is feasible
        """
        if slot >= NUM_SLOTS - 1:
            # Last slot - always feasible (no future to consider)
            return torch.ones(remaining_debt.shape[0], dtype=torch.bool, device=self.device)

        # Max achievable nutrition from slot+1 to end
        max_remaining = self.nutrition_max_remaining[slot + 1]  # [NUM_NUTRIENTS]

        # Beam is infeasible if it needs MORE than max achievable
        # Check only calories (index 0) - most critical
        infeasible = remaining_debt[:, 0] > max_remaining[0] * (1 + tolerance)

        return ~infeasible

    @classmethod
    def from_weekly_tensor(
        cls,
        weekly_tensor: "GPUWeeklyTensor",
        servings_per_meal: float = 4.0,
    ) -> "GPUFeasibilityBounds":
        """
        Compute bounds from weekly tensor candidate statistics.

        Args:
            weekly_tensor: GPU tensor with all candidates
            servings_per_meal: Expected servings consumed per meal
        """
        device = weekly_tensor.device
        K = weekly_tensor.K

        # Get min/max nutrition per slot
        # nutrition shape: [NUM_SLOTS, K, NUM_NUTRIENTS]
        scaled_nutrition = weekly_tensor.nutrition * servings_per_meal

        nutrition_min = scaled_nutrition.min(dim=1).values  # [NUM_SLOTS, NUM_NUTRIENTS]
        nutrition_max = scaled_nutrition.max(dim=1).values  # [NUM_SLOTS, NUM_NUTRIENTS]

        # Get min/max cost per slot
        # costs shape: [NUM_SLOTS, K]
        scaled_costs = weekly_tensor.costs * servings_per_meal

        cost_min = scaled_costs.min(dim=1).values  # [NUM_SLOTS]
        cost_max = scaled_costs.max(dim=1).values  # [NUM_SLOTS]

        return cls(nutrition_min, nutrition_max, cost_min, cost_max, device)


# ============================================================================
# INGREDIENT INDEX
# ============================================================================

class IngredientIndex:
    """
    Maps ingredient FPIDs to dense tensor indices.

    Enables efficient GPU pantry operations with dense tensors
    rather than sparse dictionaries.
    """

    def __init__(self, device: torch.device):
        self.device = device
        self.fpid_to_idx: Dict[str, int] = {}
        self.idx_to_fpid: Dict[int, str] = {}
        self.num_ingredients = 0

    def build_from_recipes(self, recipe_pool: List[Dict]) -> None:
        """
        Build index from recipe pool.

        Scans all recipes to collect unique FPIDs.
        """
        import ast

        all_fpids = set()
        for recipe in recipe_pool:
            fndds = recipe.get("fndds_grams_dict", {})
            if isinstance(fndds, str):
                try:
                    fndds = ast.literal_eval(fndds)
                except:
                    fndds = {}
            if isinstance(fndds, dict):
                # Explicit loop instead of generator (avoids Python 3.11 bug)
                for fpid_key in fndds.keys():
                    all_fpids.add(str(fpid_key))

        # Sort for deterministic ordering
        sorted_fpids = sorted(all_fpids)
        self.fpid_to_idx = {fpid: i for i, fpid in enumerate(sorted_fpids)}
        self.idx_to_fpid = {i: fpid for fpid, i in self.fpid_to_idx.items()}
        self.num_ingredients = len(sorted_fpids)

    def pantry_dict_to_tensor(self, pantry: Dict[str, float]) -> torch.Tensor:
        """
        Convert pantry dictionary to dense GPU tensor.

        Args:
            pantry: Dict mapping FPID -> grams available

        Returns:
            [num_ingredients] tensor
        """
        tensor = torch.zeros(self.num_ingredients, dtype=torch.float32, device=self.device)
        for fpid, grams in pantry.items():
            if fpid in self.fpid_to_idx:
                tensor[self.fpid_to_idx[fpid]] = float(grams)  # Explicit float conversion
        return tensor

    def tensor_to_pantry_dict(self, tensor: torch.Tensor) -> Dict[str, float]:
        """
        Convert dense GPU tensor back to pantry dictionary.

        Only includes non-zero entries.
        """
        pantry = {}
        values = tensor.cpu().numpy()
        for i, grams in enumerate(values):
            if grams > 0:
                pantry[self.idx_to_fpid[i]] = float(grams)
        return pantry


# ============================================================================
# PACKAGE INDEX (for whole-package purchasing)
# ============================================================================

class PackageIndex:
    """
    Index of grocery packages for whole-package purchasing.

    NO PARTIAL PACKAGES - you buy the whole thing.
    Unused portions go to pantry.
    """

    # Typical weekly usage (grams) by FNDDS category prefix.
    # Used to select the package that minimizes actual purchase cost
    # (ceil(ref/size) * price) instead of cheapest-per-gram.
    REFERENCE_GRAMS_BY_PREFIX = {
        "02": 50,     # spices/seasonings
        "11": 2000,   # dairy/milk
        "12": 500,    # cream/sour cream
        "13": 500,    # ice cream/frozen desserts
        "14": 300,    # cheese
        "21": 1000,   # beef
        "22": 500,    # pork
        "23": 500,    # game meat
        "24": 1000,   # poultry
        "25": 500,    # luncheon meats
        "26": 500,    # seafood
        "31": 681,    # eggs (12 ct carton = 680.4g)
        "41": 500,    # legumes
        "42": 300,    # nuts
        "51": 500,    # bread/grains
        "53": 300,    # cakes/pastries
        "56": 500,    # rice/cereal
        "61": 500,    # vegetables canned
        "63": 500,    # fruit
        "71": 500,    # potatoes
        "72": 500,    # dark green vegetables
        "73": 500,    # red/orange vegetables
        "74": 500,    # other vegetables
        "75": 300,    # tomato products/sauces
        "81": 500,    # fats/oils
        "91": 300,    # condiments/sauces
        "92": 1000,   # beverages
        "93": 100,    # sweeteners
        "94": 100,    # seasonings
    }
    MAX_PACKAGE_OPTIONS = 8

    @staticmethod
    def _parse_simple_display_grams(display: str) -> Optional[float]:
        """Parse simple package displays like '1 lb' or '16 oz'."""
        if not display:
            return None
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(lb|lbs|oz|g|kg)\s*", display.lower())
        if not match:
            return None
        qty = float(match.group(1))
        unit = match.group(2)
        factors = {
            "lb": 453.592,
            "lbs": 453.592,
            "oz": 28.3495,
            "g": 1.0,
            "kg": 1000.0,
        }
        return qty * factors[unit]

    @classmethod
    def _normalize_retail_price(
        cls,
        price: float,
        grams: float,
        display: str,
        source: str,
        used_kroger_price: bool,
    ) -> Tuple[float, bool]:
        """Convert Kroger variable-weight per-pound prices to package totals."""
        if not used_kroger_price:
            return price, False
        if not str(source or "").startswith("kroger"):
            return price, False
        display_grams = cls._parse_simple_display_grams(display)
        if display_grams is None or "lb" not in str(display or "").lower():
            return price, False
        if display_grams <= 0 or grams <= 0:
            return price, False
        ratio = grams / display_grams
        if 0.85 <= ratio <= 1.15:
            return price, False
        return price * ratio, True

    def __init__(self, packages_csv: str = None, packages_db: str = None):
        """
        Load package data from food_packages_final.db (preferred) or legacy CSV.
        """
        import os
        import sqlite3
        from pathlib import Path

        self.packages_by_fndds: Dict[str, List[Tuple[float, float, str]]] = {}  # fndds -> [(price, grams, size_display), ...]
        self.package_db_path: Optional[Path] = None
        self.package_db_is_override = False

        # Prefer the ground-truth validated SQLite DB. For shadow pricing runs,
        # HESTIA_PACKAGES_DB can point at a compatible packages table without
        # mutating the production DB.
        default_db_path = Path(__file__).parent.parent / "data" / "food_packages_final.db"
        override_db = packages_db or os.environ.get("HESTIA_PACKAGES_DB")
        db_path = Path(override_db).expanduser() if override_db else default_db_path
        self.package_db_is_override = bool(override_db)
        if db_path.exists():
            self.package_db_path = db_path
            conn = sqlite3.connect(str(db_path))
            normalized_variable_weight = 0
            for row in conn.execute(
                "SELECT fndds_code, package_weight_grams, kroger_price_cents, walmart_price_cents, package_size_display, source FROM packages"
            ).fetchall():
                code, grams, kr, wm, size_display, source = row
                price_cents = kr or wm or 0
                if price_cents <= 0 or grams <= 0:
                    continue
                price = price_cents / 100.0
                price, normalized = self._normalize_retail_price(
                    price,
                    float(grams),
                    size_display or "",
                    source or "",
                    used_kroger_price=bool(kr),
                )
                normalized_variable_weight += int(normalized)
                if code not in self.packages_by_fndds:
                    self.packages_by_fndds[code] = []
                self.packages_by_fndds[code].append((price, grams, size_display or ""))
            conn.close()
            marker = " override" if self.package_db_is_override else ""
            print(f"PackageIndex: Loaded from{marker} {db_path}")
            if normalized_variable_weight:
                print(f"PackageIndex: Normalized {normalized_variable_weight} Kroger variable-weight prices")
        else:
            # Legacy CSV fallback
            import pandas as pd
            if packages_csv is None:
                combined_path = Path(__file__).parent.parent / "data" / "FoodPackages_combined.csv"
                if combined_path.exists():
                    packages_csv = combined_path
                else:
                    packages_csv = Path(__file__).parent.parent / "data" / "FoodPackages.csv"

            if Path(packages_csv).exists():
                df = pd.read_csv(packages_csv)
                for _, row in df.iterrows():
                    try:
                        fndds = str(int(row['fndds']))
                        price = float(row['price'])
                        grams = float(row['item_weight'])
                        if grams > 0 and price >= 0:
                            if fndds not in self.packages_by_fndds:
                                self.packages_by_fndds[fndds] = []
                            self.packages_by_fndds[fndds].append((price, grams, ""))
                    except:
                        continue
                print(f"PackageIndex: Loaded from {packages_csv}")

        # Sort by price/gram (best value first) for each ingredient
        for fndds in self.packages_by_fndds:
            self.packages_by_fndds[fndds].sort(key=lambda x: x[0] / x[1])


        total_packages = sum(len(v) for v in self.packages_by_fndds.values())
        print(f"PackageIndex: Loaded {len(self.packages_by_fndds)} ingredients, {total_packages} packages")

        # GPU tensors (built lazily when needed)
        self._gpu_tensors_built = False
        self._gpu_prices: Optional[torch.Tensor] = None  # [num_ingredients]
        self._gpu_sizes: Optional[torch.Tensor] = None   # [num_ingredients]
        self._gpu_option_prices: Optional[torch.Tensor] = None  # [num_ingredients, MAX_PACKAGE_OPTIONS]
        self._gpu_option_sizes: Optional[torch.Tensor] = None   # [num_ingredients, MAX_PACKAGE_OPTIONS]

    @staticmethod
    def _hash_source_file(path: str) -> str:
        """Compute SHA256 hash of a source data file."""
        import hashlib
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()[:16]  # 16 chars is enough for staleness detection

    def build_gpu_tensors(
        self,
        ingredient_index: "IngredientIndex",
        device: torch.device,
    ) -> None:
        """
        Pre-build GPU tensors for fast vectorized purchasing.

        Maps each ingredient index to its best-value package (price, size).
        Stores a hash of the source DB so staleness can be detected on load.
        """
        num_ing = ingredient_index.num_ingredients

        # Default: $0.003/gram fallback for unknown ingredients
        # This is $3/kg which is conservative but not as aggressive as $10/kg
        default_price_per_gram = 0.003
        default_size = 1000.0  # 1kg packages
        default_price = default_price_per_gram * default_size  # $3 per 1kg

        prices = torch.full((num_ing,), default_price, dtype=torch.float32, device=device)
        sizes = torch.full((num_ing,), default_size, dtype=torch.float32, device=device)
        option_prices = torch.full(
            (num_ing, self.MAX_PACKAGE_OPTIONS),
            default_price,
            dtype=torch.float32,
            device=device,
        )
        option_sizes = torch.full(
            (num_ing, self.MAX_PACKAGE_OPTIONS),
            default_size,
            dtype=torch.float32,
            device=device,
        )

        priced = 0
        defaulted = 0
        for idx in range(num_ing):
            fndds = ingredient_index.idx_to_fpid.get(idx, "")
            if fndds in self.packages_by_fndds:
                pkgs = self.packages_by_fndds[fndds]
                ref = self.REFERENCE_GRAMS_BY_PREFIX.get(fndds[:2], 500)
                # Select package minimizing actual purchase cost for reference quantity
                pkg = min(pkgs, key=lambda p: math.ceil(ref / p[1]) * p[0])
                prices[idx] = pkg[0]
                sizes[idx] = pkg[1]
                option_prices[idx, :] = pkg[0]
                option_sizes[idx, :] = pkg[1]
                # Keep a small menu of package sizes so the planner can price
                # the actual grams needed. A single global package choice is
                # wrong for ingredients like ranch dressing, where 8 oz is
                # right for a 60g recipe ask but 36 fl oz is right for 500g.
                deduped: List[Tuple[float, float, str]] = []
                seen_sizes = set()

                def add_option(package: Tuple[float, float, str]) -> bool:
                    price, grams, display = package
                    rounded_size = round(float(grams), 3)
                    if rounded_size in seen_sizes:
                        return False
                    seen_sizes.add(rounded_size)
                    deduped.append((price, grams, display))
                    return len(deduped) >= self.MAX_PACKAGE_OPTIONS

                # Always keep the economic package selected by the legacy
                # reference-quantity rule and the best unit-price package.
                # Then fill the menu with smaller packages for small recipe
                # asks. This keeps gallons/large bags available without
                # forcing them onto tablespoon-sized purchases.
                add_option(pkg)
                add_option(min(pkgs, key=lambda p: p[0] / p[1]))
                for package in sorted(pkgs, key=lambda p: (p[1], p[0])):
                    if add_option(package):
                        break
                for opt_idx, (price, grams, _display) in enumerate(deduped):
                    option_prices[idx, opt_idx] = price
                    option_sizes[idx, opt_idx] = grams
                priced += 1
            else:
                defaulted += 1

        self._gpu_prices = prices
        self._gpu_sizes = sizes
        self._gpu_option_prices = option_prices
        self._gpu_option_sizes = option_sizes
        self._gpu_tensors_built = True

        # Update source hashes for staleness detection
        from pathlib import Path
        import json
        db_path = self.package_db_path or Path(__file__).parent.parent / "data" / "food_packages_final.db"
        hash_path = Path(__file__).parent.parent / "data" / "tensor_cache" / "source_hashes.json"
        if db_path.exists() and hash_path.parent.exists() and not self.package_db_is_override:
            db_hash = self._hash_source_file(str(db_path))
            hashes = {}
            if hash_path.exists():
                with open(hash_path) as f:
                    hashes = json.load(f)
            hashes['packages_db'] = db_hash
            with open(hash_path, 'w') as f:
                json.dump(hashes, f, indent=2)

        print(f"PackageIndex: Built GPU tensors for {num_ing} ingredients "
              f"({priced} with store data, {defaulted} at $3/kg default)")

    def extend_with_synthetic(
        self,
        synthetic_packages: Dict[str, Tuple[float, float]],
        ingredient_index: "IngredientIndex",
        device: torch.device,
    ) -> None:
        """
        Extend GPU price/size tensors with synthetic product ingredients.

        Called after inject_products() adds synthetic FNDDS codes to the
        ingredient index. Each synthetic ingredient has a fixed price and
        size (typically price=product_cost, size=1g).

        Also adds synthetic packages to packages_by_fndds for CPU fallback.
        """
        if not self._gpu_tensors_built:
            raise RuntimeError("Call build_gpu_tensors() before extend_with_synthetic()")

        # Add to CPU dict
        for syn_fndds, (price, size) in synthetic_packages.items():
            self.packages_by_fndds[syn_fndds] = [(price, size, "")]

        # Extend GPU tensors to new ingredient count
        new_num_ing = ingredient_index.num_ingredients
        old_num_ing = self._gpu_prices.shape[0]

        if new_num_ing <= old_num_ing:
            return  # Nothing to extend

        num_new = new_num_ing - old_num_ing

        # Build on CPU to avoid per-element MPS kernel launches
        default_price = 0.003 * 1000.0  # $3/kg
        default_size = 1000.0

        new_prices = torch.full((num_new,), default_price, dtype=torch.float32)
        new_sizes = torch.full((num_new,), default_size, dtype=torch.float32)
        new_option_prices = torch.full(
            (num_new, self.MAX_PACKAGE_OPTIONS),
            default_price,
            dtype=torch.float32,
        )
        new_option_sizes = torch.full(
            (num_new, self.MAX_PACKAGE_OPTIONS),
            default_size,
            dtype=torch.float32,
        )

        for idx in range(old_num_ing, new_num_ing):
            fndds = ingredient_index.idx_to_fpid.get(idx, "")
            if fndds in synthetic_packages:
                price, size = synthetic_packages[fndds]
                new_prices[idx - old_num_ing] = price
                new_sizes[idx - old_num_ing] = size
                new_option_prices[idx - old_num_ing, :] = price
                new_option_sizes[idx - old_num_ing, :] = size

        self._gpu_prices = torch.cat([self._gpu_prices, new_prices.to(device)])
        self._gpu_sizes = torch.cat([self._gpu_sizes, new_sizes.to(device)])
        self._gpu_option_prices = torch.cat([self._gpu_option_prices, new_option_prices.to(device)])
        self._gpu_option_sizes = torch.cat([self._gpu_option_sizes, new_option_sizes.to(device)])

        print(f"PackageIndex: Extended GPU tensors with {num_new} synthetic ingredients "
              f"(total: {new_num_ing})")

    def buy_ingredients_gpu(
        self,
        to_buy: torch.Tensor,  # [num_ingredients] grams needed
    ) -> Tuple[float, torch.Tensor]:
        """
        GPU-native vectorized package purchasing.

        For each ingredient where to_buy > 0, buy enough packages to cover.

        Returns:
            (total_cost, purchased_grams [num_ingredients])
        """
        if not self._gpu_tensors_built:
            raise RuntimeError("Call build_gpu_tensors() first!")

        # Number of packages needed (ceiling division)
        # Avoid division by zero
        safe_sizes = self._gpu_sizes.clamp(min=1.0)
        num_packages = torch.ceil(to_buy / safe_sizes)

        # Zero out where we don't need anything
        num_packages = num_packages * (to_buy > 0).float()

        # Total cost = sum of (num_packages * price_per_package)
        total_cost = (num_packages * self._gpu_prices).sum().item()

        # Total purchased grams
        purchased = num_packages * self._gpu_sizes

        return total_cost, purchased

    def buy_ingredient(self, fndds: str, grams_needed: float) -> Tuple[float, float]:
        """
        Buy whole package(s) to cover grams_needed.

        Returns:
            (total_cost, total_grams_purchased)

        The caller should add (total_grams - grams_needed) to pantry.
        """
        if grams_needed <= 0:
            return 0.0, 0.0

        if fndds not in self.packages_by_fndds:
            # No package data - assume $0 (recipe cost already accounts for this)
            # We still "buy" the exact amount needed
            return 0.0, grams_needed

        packages = self.packages_by_fndds[fndds]

        # Find cheapest way to get at least grams_needed
        # Strategy: try each package size, pick cheapest that covers need
        # If no single package covers, buy multiples of best-value package

        best_cost = float('inf')
        best_grams = 0.0

        for price, pkg_grams, *_ in packages:
            if pkg_grams >= grams_needed:
                # Single package covers it
                if price < best_cost:
                    best_cost = price
                    best_grams = pkg_grams

        if best_cost < float('inf'):
            return best_cost, best_grams

        # No single package covers need - buy multiples of best-value package
        best_value_price, best_value_grams = packages[0][0], packages[0][1]  # Already sorted by value
        num_packages = int((grams_needed + best_value_grams - 1) / best_value_grams)  # Ceiling
        return best_value_price * num_packages, best_value_grams * num_packages

    def get_size_display(self, fndds: str, pkg_grams: float) -> str:
        """Return customer-facing size display for a package matching the given grams."""
        packages = self.packages_by_fndds.get(fndds, [])
        # Find the package whose grams match (within 1g tolerance)
        for price, grams, display in packages:
            if abs(grams - pkg_grams) < 1.0 and display:
                return display
        # Fallback: return first package with a display string
        for price, grams, display in packages:
            if display:
                return display
        return ""

    def buy_ingredients_batch(
        self,
        ingredient_index: "IngredientIndex",
        needs: torch.Tensor,  # [num_ingredients] grams needed
    ) -> Tuple[float, torch.Tensor]:
        """
        Buy all needed ingredients using whole packages.

        Args:
            ingredient_index: Maps dense indices to FNDDS codes
            needs: [num_ingredients] tensor of grams needed per ingredient

        Returns:
            (total_cost, purchased_grams [num_ingredients])
        """
        device = needs.device
        purchased = torch.zeros_like(needs)
        total_cost = 0.0

        needs_np = needs.cpu().numpy()
        purchased_np = purchased.cpu().numpy()
        for idx, grams_needed in enumerate(needs_np):
            if grams_needed > 0:
                fndds = ingredient_index.idx_to_fpid.get(idx, "")
                cost, grams_bought = self.buy_ingredient(fndds, grams_needed)
                total_cost += cost
                purchased_np[idx] = grams_bought

        # Copy back to GPU tensor
        purchased = torch.from_numpy(purchased_np).to(device)
        return total_cost, purchased


# ============================================================================
# ATTENDANCE & HOUSEHOLD CONFIGURATION
# ============================================================================

@dataclass
class PersonProfile:
    """
    Nutritional profile for one person in the household.

    Supports different calorie needs (1400-3000 cal/day range) and
    meal distribution preferences.
    """
    name: str = "Adult"
    daily_calories: float = 2000.0
    daily_protein: float = 50.0  # grams

    # Meal distribution ratios (must sum to 1.0)
    breakfast_ratio: float = 0.25  # 25% of daily calories at breakfast
    lunch_ratio: float = 0.35     # 35% at lunch
    dinner_ratio: float = 0.40    # 40% at dinner

    def meal_calories(self, meal_idx: int) -> float:
        """Get calorie target for a specific meal (0=breakfast, 1=lunch, 2=dinner)."""
        ratios = [self.breakfast_ratio, self.lunch_ratio, self.dinner_ratio]
        return self.daily_calories * ratios[meal_idx]

    def meal_protein(self, meal_idx: int) -> float:
        """Get protein target for a specific meal."""
        ratios = [self.breakfast_ratio, self.lunch_ratio, self.dinner_ratio]
        return self.daily_protein * ratios[meal_idx]


@dataclass
class HouseholdConfig:
    """
    Configuration for a household with one or more people.

    Supports families of 1-8 with different calorie/protein needs per person.
    """
    people: List[PersonProfile]

    @property
    def size(self) -> int:
        """Number of people in household."""
        return len(self.people)

    def daily_calories(self) -> float:
        """Total daily calories for entire household."""
        return sum(p.daily_calories for p in self.people)

    def daily_protein(self) -> float:
        """Total daily protein for entire household."""
        return sum(p.daily_protein for p in self.people)

    def meal_calories(self, meal_idx: int) -> float:
        """Total calories for a specific meal type across all people."""
        return sum(p.meal_calories(meal_idx) for p in self.people)

    def meal_protein(self, meal_idx: int) -> float:
        """Total protein for a specific meal type across all people."""
        return sum(p.meal_protein(meal_idx) for p in self.people)

    @classmethod
    def family_of_four(cls) -> "HouseholdConfig":
        """Default: 2 adults @ 2000 cal, 2 children @ 1800 cal."""
        return cls(people=[
            PersonProfile("Adult 1", 2000, 50),
            PersonProfile("Adult 2", 2000, 50),
            PersonProfile("Child 1", 1800, 40),
            PersonProfile("Child 2", 1800, 40),
        ])

    @classmethod
    def single_person(cls, calories: float = 2000, protein: float = 50) -> "HouseholdConfig":
        """Single person household."""
        return cls(people=[PersonProfile("Adult", calories, protein)])

    @classmethod
    def couple(cls, cal1: float = 2200, cal2: float = 1800) -> "HouseholdConfig":
        """Two adults with different calorie needs."""
        return cls(people=[
            PersonProfile("Adult 1", cal1, cal1 / 40),  # ~55g protein
            PersonProfile("Adult 2", cal2, cal2 / 40),  # ~45g protein
        ])

    @classmethod
    def large_family(cls, num_adults: int = 2, num_children: int = 4) -> "HouseholdConfig":
        """Large family with configurable composition."""
        people = []
        for i in range(num_adults):
            people.append(PersonProfile(f"Adult {i+1}", 2000, 50))
        for i in range(num_children):
            people.append(PersonProfile(f"Child {i+1}", 1600, 35))
        return cls(people=people)


@dataclass
class SlotAttendance:
    """
    Attendance configuration for a single meal slot.

    Specifies how many people are eating and their nutrition targets.
    """
    slot: int                     # 0-20 (slot in the week)
    headcount: int                # Number of people eating this meal
    calories_target: float        # Total calories for this slot
    protein_target: float         # Total protein for this slot
    servings_needed: float        # How many recipe servings to satisfy meal
    people_present: Optional[List[str]] = None  # Names of who's eating (optional)
    note: str = ""                # Optional note (e.g., "Friday dinner out")


class AttendanceSchedule:
    """
    Per-slot attendance and nutrition targets for a week.

    Supports:
    - Constant attendance (everyone eats every meal) - default
    - Variable attendance (some meals skipped or reduced)
    - Zero attendance slots (eating out - provides guidance)

    Example usage:
        # Default family of 4, everyone at every meal
        schedule = AttendanceSchedule(HouseholdConfig.family_of_four())

        # Single person
        schedule = AttendanceSchedule(HouseholdConfig.single_person(2000))

        # Custom with Friday dinner skipped
        schedule = AttendanceSchedule.from_json("my_schedule.json")
    """

    def __init__(
        self,
        household: HouseholdConfig,
        slot_overrides: Optional[Dict[int, Dict]] = None,
    ):
        """
        Initialize attendance schedule.

        Args:
            household: Household configuration with people profiles
            slot_overrides: Optional dict mapping slot -> override config
                           e.g., {5: {"headcount": 0, "note": "Friday dinner out"}}
        """
        self.household = household
        self._slots: Dict[int, SlotAttendance] = {}

        # Build default schedule where everyone attends every meal
        self._build_default_schedule()

        # Apply any overrides
        if slot_overrides:
            self._apply_overrides(slot_overrides)

    def _build_default_schedule(self):
        """Build default schedule where everyone attends every meal."""
        for slot in range(NUM_SLOTS):
            day = slot // 3
            meal_idx = slot % 3

            self._slots[slot] = SlotAttendance(
                slot=slot,
                headcount=self.household.size,
                calories_target=self.household.meal_calories(meal_idx),
                protein_target=self.household.meal_protein(meal_idx),
                servings_needed=float(self.household.size),
                people_present=[p.name for p in self.household.people],
            )

    def _apply_overrides(self, overrides: Dict[int, Dict]):
        """Apply slot-specific overrides."""
        for slot, override in overrides.items():
            if slot < 0 or slot >= NUM_SLOTS:
                continue

            existing = self._slots[slot]
            meal_idx = slot % 3

            # Get new headcount (default to existing if not specified)
            headcount = override.get("headcount", existing.headcount)

            # Get specific people if provided
            people_present = override.get("people", None)
            if people_present:
                # Calculate targets based on specific people
                cal_target = 0.0
                prot_target = 0.0
                for person in self.household.people:
                    if person.name in people_present:
                        cal_target += person.meal_calories(meal_idx)
                        prot_target += person.meal_protein(meal_idx)
                headcount = len(people_present)
            else:
                # Scale by headcount ratio
                if headcount == 0:
                    cal_target = 0.0
                    prot_target = 0.0
                else:
                    ratio = headcount / self.household.size
                    cal_target = self.household.meal_calories(meal_idx) * ratio
                    prot_target = self.household.meal_protein(meal_idx) * ratio

            self._slots[slot] = SlotAttendance(
                slot=slot,
                headcount=headcount,
                calories_target=cal_target,
                protein_target=prot_target,
                servings_needed=float(headcount),
                people_present=people_present or existing.people_present,
                note=override.get("note", ""),
            )

    def get_slot(self, slot: int) -> SlotAttendance:
        """Get attendance for a specific slot."""
        return self._slots[slot]

    def servings_tensor(self, device: torch.device) -> torch.Tensor:
        """Get [NUM_SLOTS] tensor of servings needed per slot."""
        servings = torch.zeros(NUM_SLOTS, dtype=torch.float32, device=device)
        for slot in range(NUM_SLOTS):
            servings[slot] = self._slots[slot].servings_needed
        return servings

    def calories_tensor(self, device: torch.device) -> torch.Tensor:
        """Get [NUM_SLOTS] tensor of calorie targets per slot."""
        cals = torch.zeros(NUM_SLOTS, dtype=torch.float32, device=device)
        for slot in range(NUM_SLOTS):
            cals[slot] = self._slots[slot].calories_target
        return cals

    def protein_tensor(self, device: torch.device) -> torch.Tensor:
        """Get [NUM_SLOTS] tensor of protein targets per slot."""
        prot = torch.zeros(NUM_SLOTS, dtype=torch.float32, device=device)
        for slot in range(NUM_SLOTS):
            prot[slot] = self._slots[slot].protein_target
        return prot

    @property
    def weekly_calories(self) -> float:
        """Total weekly calorie target."""
        return sum(s.calories_target for s in self._slots.values())

    @property
    def weekly_protein(self) -> float:
        """Total weekly protein target."""
        return sum(s.protein_target for s in self._slots.values())

    @property
    def max_servings(self) -> float:
        """Maximum servings needed in any single slot."""
        return max(s.servings_needed for s in self._slots.values())

    def skip_slots(self) -> List[int]:
        """Get list of slot indices that are skipped (headcount=0)."""
        return [slot for slot, att in self._slots.items() if att.headcount == 0]

    def eating_out_guidance(self, slot: int, calories_consumed_today: float) -> str:
        """
        Generate guidance for eating out when a slot is skipped.

        Args:
            slot: The skipped slot
            calories_consumed_today: Calories already consumed today

        Returns:
            Guidance string like "Aim for ~800 cal at dinner"
        """
        att = self._slots[slot]
        if att.headcount > 0:
            return ""  # Not skipped

        day = slot // 3
        meal_idx = slot % 3
        meal_names = ["breakfast", "lunch", "dinner"]

        # Calculate what they should aim for
        daily_target = self.household.daily_calories()
        remaining = max(0, daily_target - calories_consumed_today)

        return (
            f"Slot {slot} ({['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][day]} "
            f"{meal_names[meal_idx]}): SKIPPED - {att.note or 'Eating out'}\n"
            f"  Today's home meals: {calories_consumed_today:.0f} cal consumed\n"
            f"  Suggested restaurant target: ~{remaining:.0f} cal"
        )

    @classmethod
    def from_json(cls, path: str) -> "AttendanceSchedule":
        """
        Load schedule from JSON file.

        JSON format:
        {
          "household": {
            "people": [
              {"name": "Parent1", "daily_calories": 2200, "daily_protein": 55},
              {"name": "Parent2", "daily_calories": 1800, "daily_protein": 45}
            ]
          },
          "schedule": {
            "0": {"headcount": 1, "people": ["Parent1"]},
            "5": {"headcount": 0, "note": "Friday dinner out"}
          }
        }
        """
        import json

        with open(path, 'r') as f:
            data = json.load(f)

        # Parse household
        people = []
        for p in data.get("household", {}).get("people", []):
            people.append(PersonProfile(
                name=p.get("name", "Person"),
                daily_calories=p.get("daily_calories", 2000),
                daily_protein=p.get("daily_protein", 50),
                breakfast_ratio=p.get("breakfast_ratio", 0.25),
                lunch_ratio=p.get("lunch_ratio", 0.35),
                dinner_ratio=p.get("dinner_ratio", 0.40),
            ))

        if not people:
            # Default to family of 4 if no people specified
            household = HouseholdConfig.family_of_four()
        else:
            household = HouseholdConfig(people=people)

        # Parse schedule overrides
        schedule_data = data.get("schedule", {})
        overrides = {}
        for slot_str, override in schedule_data.items():
            if slot_str.startswith("_"):
                continue  # Skip meta keys like "_default"
            try:
                slot = int(slot_str)
                overrides[slot] = override
            except ValueError:
                continue

        return cls(household=household, slot_overrides=overrides)

    def to_json(self, path: str) -> None:
        """Save schedule to JSON file."""
        import json

        data = {
            "household": {
                "people": [
                    {
                        "name": p.name,
                        "daily_calories": p.daily_calories,
                        "daily_protein": p.daily_protein,
                        "breakfast_ratio": p.breakfast_ratio,
                        "lunch_ratio": p.lunch_ratio,
                        "dinner_ratio": p.dinner_ratio,
                    }
                    for p in self.household.people
                ]
            },
            "schedule": {}
        }

        # Only save non-default slots
        default_headcount = self.household.size
        for slot, att in self._slots.items():
            if att.headcount != default_headcount or att.note:
                slot_data = {"headcount": att.headcount}
                if att.people_present:
                    slot_data["people"] = att.people_present
                if att.note:
                    slot_data["note"] = att.note
                data["schedule"][str(slot)] = slot_data

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
