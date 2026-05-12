"""Tier Injection Module: Post-processing injection of premium protein dinners.

This module implements food plan tiers (Thrifty, Low-Cost, Moderate, Liberal) by
injecting premium protein dinners (beef, fish) AFTER the baseline optimizer runs.

Key insight: Don't fight the optimizer. Let it pick cheapest proteins (eggs, legumes),
then POST-PROCESS to inject premium proteins. Tier = number of injected meals/week.

This mirrors USDA food plan philosophy where tiers differ by protein QUALITY,
not by fighting cost optimization.

Usage:
    from tier_injection import TierConfig, TIER_PRESETS, inject_premium_proteins

    # Use preset
    tier_config = TIER_PRESETS['moderate']  # 2 beef, 2 fish per week

    # Inject after planning
    result = inject_premium_proteins(
        result=planner_result,
        tier_config=tier_config,
        recipe_db=db,
        protein_pct_target=25.0,
    )
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set
import math


# Protein source codes (must match sparse_cascade.py)
PROTEIN_SOURCE_CODES = {
    'beef': 0,
    'pork': 1,
    'poultry': 2,
    'fish': 3,
    'eggs': 4,
    'legumes': 5,
}


@dataclass
class TierConfig:
    """Controls premium protein injection for food plan tiers.

    Attributes:
        tier_name: Human-readable tier name
        chicken_per_week: Number of poultry dinners to inject per week
        pork_per_week: Number of pork dinners to inject per week
        beef_per_week: Number of beef dinners to inject per week
        fish_per_week: Number of fish/seafood dinners to inject per week
        prefer_high_protein: When True, filter to high-protein recipes
            when protein_pct_target > 15%

    Protein value ranking (protein per $):
        1. Chicken: 33.7g/$  (BEST value)
        2. Eggs:    32.5g/$  (baseline picks these)
        3. Pork:    25.0g/$
        4. Beef:    17.7g/$
        5. Fish:    16.9g/$  (most expensive)
    """
    tier_name: str = 'thrifty'
    chicken_per_week: int = 0   # poultry, protein_source=2
    pork_per_week: int = 0      # pork, protein_source=1
    beef_per_week: int = 0      # beef, protein_source=0
    fish_per_week: int = 0      # fish/seafood, protein_source=3
    prefer_high_protein: bool = True

    # Legacy compatibility
    @property
    def beef_dinners_per_week(self) -> int:
        return self.beef_per_week

    @property
    def fish_dinners_per_week(self) -> int:
        return self.fish_per_week


# Tier presets based on protein/$ value ranking:
# - Thrifty: baseline only (eggs, legumes from optimizer)
# - Low-cost: add chicken (best protein/$)
# - Moderate: add chicken + pork
# - Liberal: add chicken + pork + beef + fish
TIER_PRESETS = {
    'thrifty': TierConfig(
        tier_name='thrifty',
        chicken_per_week=0,
        pork_per_week=0,
        beef_per_week=0,
        fish_per_week=0,
    ),
    'low_cost': TierConfig(
        tier_name='low_cost',
        chicken_per_week=2,  # best value protein
        pork_per_week=1,
        beef_per_week=0,
        fish_per_week=0,
    ),
    'moderate': TierConfig(
        tier_name='moderate',
        chicken_per_week=2,
        pork_per_week=1,
        beef_per_week=2,     # add beef
        fish_per_week=0,
    ),
    'liberal': TierConfig(
        tier_name='liberal',
        chicken_per_week=1,
        pork_per_week=1,
        beef_per_week=2,
        fish_per_week=2,     # add fish (most expensive)
    ),
}


def _get_dinner_slots() -> List[int]:
    """Return slot indices for dinners (slot 2, 5, 8, 11, 14, 17, 20).

    In a week with 21 slots (7 days × 3 meals):
    - slot % 3 == 0: breakfast
    - slot % 3 == 1: lunch
    - slot % 3 == 2: dinner
    """
    return [i for i in range(21) if i % 3 == 2]


def _evenly_space_indices(count: int, available: List[int]) -> List[int]:
    """Select `count` indices from `available` with even spacing.

    Args:
        count: Number of indices to select
        available: List of available indices

    Returns:
        List of selected indices (subset of available)
    """
    if count <= 0 or not available:
        return []
    if count >= len(available):
        return available

    # Use even spacing
    step = len(available) / count
    selected = []
    for i in range(count):
        idx = int(i * step)
        selected.append(available[idx])
    return selected


def _find_eligible_dinner_slots(
    selections: List[tuple],
) -> List[Tuple[int, int, float]]:
    """Find dinner slots eligible for premium protein injection.

    Eligibility criteria:
    - Must be a dinner slot (slot % 3 == 2)
    - Must be fresh-cooked (not leftover consumption)

    Args:
        selections: List of selection tuples from planner

    Returns:
        List of (slot_idx, recipe_id, cal_per_serving) tuples
    """
    dinner_slots = _get_dinner_slots()
    eligible = []

    for slot_idx in dinner_slots:
        if slot_idx >= len(selections):
            continue

        sel = selections[slot_idx]
        main_id = sel[0]  # recipe_id
        main_is_leftover = sel[10] if len(sel) > 10 else False

        # Skip leftover slots
        if main_is_leftover:
            continue

        # Skip empty slots
        if main_id <= 0:
            continue

        eligible.append((slot_idx, main_id, 0.0))  # cal_per_serving computed later

    return eligible


def _find_replacement_recipe(
    original_recipe_id: int,
    target_protein_source: int,  # 0=beef, 3=fish
    recipe_db,
    protein_pct_target: float = 15.0,
    prefer_high_protein: bool = True,
    slot_servings: float = 4.0,
    calorie_tolerance: float = 0.30,  # 30% calorie match tolerance
    exclude_recipe_ids: Optional[Set[int]] = None,
) -> Optional[Dict]:
    """Find a replacement recipe with the target protein source.

    Args:
        original_recipe_id: The recipe being replaced
        target_protein_source: Protein source code (0=beef, 3=fish)
        recipe_db: SparseRecipeDatabase instance
        protein_pct_target: Target protein % (for filtering high-protein recipes)
        prefer_high_protein: Filter to high-protein recipes when target > 15%
        slot_servings: Servings needed per slot
        calorie_tolerance: How close calories must match (0.30 = within 30%)
        exclude_recipe_ids: Recipe IDs to exclude (already injected this week)

    Returns:
        Dict with replacement info or None if no suitable replacement found
    """
    if exclude_recipe_ids is None:
        exclude_recipe_ids = set()

    # Get original recipe info
    if original_recipe_id not in recipe_db.recipe_id_to_idx:
        return None

    orig_idx = recipe_db.recipe_id_to_idx[original_recipe_id]
    orig_cal_per_srv = recipe_db.nutrition[orig_idx, 0].item()
    orig_total_cal = orig_cal_per_srv * slot_servings

    # Find all recipes with target protein source
    protein_mask = recipe_db.protein_source == target_protein_source
    candidate_indices = protein_mask.nonzero().squeeze(-1)

    if candidate_indices.dim() == 0:
        candidate_indices = candidate_indices.unsqueeze(0)

    if len(candidate_indices) == 0:
        return None

    # Filter by protein % if requested
    if prefer_high_protein and protein_pct_target > 15.0:
        min_protein_pct = protein_pct_target - 5.0  # Allow 5pp below target
        nutrition = recipe_db.nutrition[candidate_indices]  # [N, 4]
        cal_per_srv = nutrition[:, 0]
        prot_per_srv = nutrition[:, 1]
        # protein_pct = (protein_g * 4 / calories) * 100
        safe_cal = cal_per_srv.clamp(min=1.0)
        protein_pct = (prot_per_srv * 4 / safe_cal) * 100
        high_protein_mask = protein_pct >= min_protein_pct
        candidate_indices = candidate_indices[high_protein_mask]

        if len(candidate_indices) == 0:
            # Fall back to all recipes with this protein source
            candidate_indices = protein_mask.nonzero().squeeze(-1)
            if candidate_indices.dim() == 0:
                candidate_indices = candidate_indices.unsqueeze(0)

    # Get calories for candidates
    candidate_cal = recipe_db.nutrition[candidate_indices, 0]  # [N]

    # Filter by calorie match
    min_cal = orig_cal_per_srv * (1 - calorie_tolerance)
    max_cal = orig_cal_per_srv * (1 + calorie_tolerance)
    cal_mask = (candidate_cal >= min_cal) & (candidate_cal <= max_cal)
    candidate_indices = candidate_indices[cal_mask]
    candidate_cal = candidate_cal[cal_mask]

    if len(candidate_indices) == 0:
        return None

    # Get recipe IDs and filter out excluded ones
    candidate_recipe_ids = recipe_db.recipe_ids[candidate_indices]
    valid_mask = []
    for i, rid in enumerate(candidate_recipe_ids.tolist()):
        valid_mask.append(int(rid) not in exclude_recipe_ids)

    import torch
    valid_mask = torch.tensor(valid_mask, dtype=torch.bool, device=candidate_indices.device)

    if not valid_mask.any():
        return None

    candidate_indices = candidate_indices[valid_mask]
    candidate_cal = candidate_cal[valid_mask]
    candidate_recipe_ids = candidate_recipe_ids[valid_mask]

    # Score candidates by calorie match (closest to original)
    cal_diff = (candidate_cal - orig_cal_per_srv).abs()
    best_idx = cal_diff.argmin().item()

    # Get recipe info
    db_idx = candidate_indices[best_idx].item()
    new_recipe_id = int(candidate_recipe_ids[best_idx].item())
    new_cal_per_srv = candidate_cal[best_idx].item()

    # Get recipe name if available
    try:
        new_name = recipe_db.names[db_idx]
    except (IndexError, AttributeError):
        new_name = f"Recipe_{new_recipe_id}"

    return {
        'recipe_id': new_recipe_id,
        'db_idx': db_idx,
        'cal_per_srv': new_cal_per_srv,
        'name': new_name,
        'protein_source': target_protein_source,
    }


# Estimated incremental cost per injection (based on typical price differences)
# These are FLAT estimates since we can't compute actual incremental cost
# without pantry state. Real costs depend on pantry overlap.
#
# Based on protein/$ value ranking:
#   Chicken: 33.7g/$ - nearly same as eggs, minimal cost uplift
#   Pork:    25.0g/$ - moderate uplift
#   Beef:    17.7g/$ - significant uplift
#   Fish:    16.9g/$ - highest uplift (most expensive protein per $)
#
# With leftovers, one dinner feeds ~2-3 meals, so per-injection uplift is lower
ESTIMATED_CHICKEN_INJECTION_COST = 1.00  # $ per chicken dinner injection
ESTIMATED_PORK_INJECTION_COST = 2.00     # $ per pork dinner injection
ESTIMATED_BEEF_INJECTION_COST = 4.00     # $ per beef dinner injection
ESTIMATED_FISH_INJECTION_COST = 5.00     # $ per fish dinner injection


def inject_premium_proteins(
    result: Dict,
    tier_config: TierConfig,
    recipe_db,
    protein_pct_target: float = 15.0,
    servings_per_slot=None,
    package_index=None,
    verbose: bool = False,
) -> Dict:
    """DEPRECATED: Post-process planner result to inject protein dinners by type.

    NOTE: This function is DEPRECATED. Tier injection now happens IN-LOOP via
    candidate filtering in SparseCascadePlanner._compute_tier_slot_requirements().
    The in-loop approach provides full accounting (pantry, leftovers, nutrition, cost)
    whereas this post-processing approach was cosmetic only.

    Algorithm:
    1. Find dinner slots that are fresh-cooked (not leftovers) - these are swap candidates
    2. Allocate slots for each protein type in order: chicken, pork, beef, fish
       (from best value to most expensive)
    3. For each slot, find best replacement recipe:
       - Same protein source
       - If protein_pct_target > 15%, must be high-protein (>= target - 5%)
       - Calorie match within 30% of original
    4. Update selections, recalculate cost
    5. Return modified result

    Args:
        result: Planner result dict with 'selections' key
        tier_config: TierConfig specifying how many of each protein to inject
        recipe_db: SparseRecipeDatabase instance
        protein_pct_target: Target protein % (for filtering high-protein recipes)
        servings_per_slot: Optional tensor of servings per slot
        package_index: Optional PackageIndex for cost calculation
        verbose: Print progress

    Returns:
        Modified result dict with injected proteins
    """
    # Check if any injections needed
    total_injections = (
        tier_config.chicken_per_week +
        tier_config.pork_per_week +
        tier_config.beef_per_week +
        tier_config.fish_per_week
    )

    if total_injections == 0:
        if verbose:
            print("Tier injection: no injections configured")
        result['tier_injections'] = []
        return result

    if 'selections' not in result:
        if verbose:
            print("Tier injection: no selections in result")
        result['tier_injections'] = []
        return result

    selections = list(result['selections'])  # Make mutable copy

    # Step 1: Find eligible dinner slots (fresh-cooked, not leftovers)
    eligible = _find_eligible_dinner_slots(selections)

    if verbose:
        print(f"\nTier Injection ({tier_config.tier_name})")
        print(f"  Target: {tier_config.chicken_per_week} chicken, {tier_config.pork_per_week} pork, "
              f"{tier_config.beef_per_week} beef, {tier_config.fish_per_week} fish")
        print(f"  Eligible dinner slots: {len(eligible)}")

    if len(eligible) == 0:
        if verbose:
            print("  No eligible slots for injection")
        result['tier_injections'] = []
        return result

    # Step 2: Allocate slots for each protein type (best value first)
    slot_indices = [s[0] for s in eligible]
    remaining_slots = slot_indices.copy()

    # Allocation order: chicken (best value) -> pork -> beef -> fish (most expensive)
    protein_allocations = [
        ('poultry', tier_config.chicken_per_week, PROTEIN_SOURCE_CODES['poultry'], ESTIMATED_CHICKEN_INJECTION_COST),
        ('pork', tier_config.pork_per_week, PROTEIN_SOURCE_CODES['pork'], ESTIMATED_PORK_INJECTION_COST),
        ('beef', tier_config.beef_per_week, PROTEIN_SOURCE_CODES['beef'], ESTIMATED_BEEF_INJECTION_COST),
        ('fish', tier_config.fish_per_week, PROTEIN_SOURCE_CODES['fish'], ESTIMATED_FISH_INJECTION_COST),
    ]

    slot_assignments = {}  # slot_idx -> (protein_name, protein_code, cost_estimate)
    for protein_name, count, protein_code, cost_estimate in protein_allocations:
        if count > 0 and remaining_slots:
            assigned = _evenly_space_indices(count, remaining_slots)
            for slot_idx in assigned:
                slot_assignments[slot_idx] = (protein_name, protein_code, cost_estimate)
            remaining_slots = [s for s in remaining_slots if s not in assigned]

    if verbose:
        for pname, count, _, _ in protein_allocations:
            slots = [s for s, (n, _, _) in slot_assignments.items() if n == pname]
            if slots:
                print(f"  {pname.capitalize()} slots: {slots}")

    # Get default servings per slot
    default_servings = 4.0
    if servings_per_slot is not None:
        try:
            default_servings = servings_per_slot[0].item()
        except (IndexError, AttributeError):
            pass

    # Track injections
    injections = []
    injected_recipe_ids: Set[int] = set()  # Avoid repeating same recipe
    cost_delta = 0.0

    # Step 3: Find replacements for each assigned slot
    for slot_idx, (protein_name, protein_code, cost_estimate) in sorted(slot_assignments.items()):
        sel = selections[slot_idx]
        original_id = sel[0]

        slot_servings = default_servings
        if servings_per_slot is not None:
            try:
                slot_servings = servings_per_slot[slot_idx].item()
            except (IndexError, AttributeError):
                pass

        replacement = _find_replacement_recipe(
            original_recipe_id=original_id,
            target_protein_source=protein_code,
            recipe_db=recipe_db,
            protein_pct_target=protein_pct_target,
            prefer_high_protein=tier_config.prefer_high_protein,
            slot_servings=slot_servings,
            exclude_recipe_ids=injected_recipe_ids,
        )

        if replacement is None:
            if verbose:
                print(f"  Slot {slot_idx}: no {protein_name} replacement found")
            continue

        # Get original recipe info for logging
        if original_id in recipe_db.recipe_id_to_idx:
            orig_idx = recipe_db.recipe_id_to_idx[original_id]
            try:
                orig_name = recipe_db.names[orig_idx]
            except (IndexError, AttributeError):
                orig_name = f"Recipe_{original_id}"
            orig_cal = recipe_db.nutrition[orig_idx, 0].item()
        else:
            orig_name = f"Recipe_{original_id}"
            orig_cal = 0.0

        # Update selection tuple (keep sides, change main)
        new_sel = list(sel)
        new_sel[0] = replacement['recipe_id']
        new_sel[3] = replacement['name']  # main_name
        selections[slot_idx] = tuple(new_sel)

        injected_recipe_ids.add(replacement['recipe_id'])
        cost_delta += cost_estimate

        injection = {
            'slot': slot_idx,
            'day': slot_idx // 3,
            'protein_type': protein_name,
            'original_recipe_id': original_id,
            'original_name': orig_name,
            'original_cal': orig_cal,
            'new_recipe_id': replacement['recipe_id'],
            'new_name': replacement['name'],
            'new_cal': replacement['cal_per_srv'],
            'cost_delta': cost_estimate,
        }
        injections.append(injection)

        if verbose:
            print(f"  Slot {slot_idx} (day {slot_idx // 3}): {orig_name} -> {replacement['name']} ({protein_name})")

    # Step 4: Update result
    result['selections'] = selections
    result['tier_injections'] = injections
    result['tier_cost_delta'] = cost_delta

    # Update total cost if available
    if 'total_cost' in result:
        result['total_cost'] = result['total_cost'] + cost_delta

    if verbose:
        counts = {}
        for inj in injections:
            ptype = inj['protein_type']
            counts[ptype] = counts.get(ptype, 0) + 1
        count_str = ', '.join(f"{c} {p}" for p, c in counts.items())
        print(f"  Injected: {count_str}")
        print(f"  Estimated cost delta: ${cost_delta:.2f}")

    return result
