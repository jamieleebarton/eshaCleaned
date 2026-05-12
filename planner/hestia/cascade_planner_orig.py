"""
TensorCascadePlanner: Beam search with TRUE lookahead via rollout.

The key insight: score each candidate by its TOTAL WEEK COST (via inner beam rollout),
not just immediate cost. This allows "investment" choices (buy expensive now, save later)
to survive pruning.

Algorithm:
  For slot t with M beams and K candidates:
    1. EXPAND: M → M×K (each beam tries each candidate)
    2. UPDATE: Apply candidate to state (exact pantry, leftovers, cost)
    3. ROLLOUT: For each M×K state, run inner beam search for slots t+1 to 20
    4. SCORE: total_cost = cost_so_far + rollout_cost
    5. PRUNE: Keep top M by lowest total_cost
    6. Repeat for next slot

All rollouts run in parallel on GPU. No Python loops over candidates or beams.
"""

import time
import torch
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple

from .data_structures import (
    NUM_SLOTS, NUM_NUTRIENTS, GPUBeamState, GPUPlanResult,
    NutritionTargets, IngredientIndex, PackageIndex, MAX_LEFTOVERS
)
from .weekly_tensor import GPUWeeklyTensor


class TensorCascadePlanner:
    """
    Cascade planner with true lookahead via batched beam rollouts.

    Key difference from GPUBeamSearchPlanner:
    - GPUBeamSearchPlanner scores by IMMEDIATE impact only
    - TensorCascadePlanner scores by TOTAL WEEK COST via rollout

    This means "buy pork at slot 0" can survive because we SEE
    its future savings during the rollout.
    """

    def __init__(
        self,
        weekly_tensor: GPUWeeklyTensor,
        weekly_targets: torch.Tensor,
        device: torch.device,
        ingredient_index: IngredientIndex = None,
        package_index: PackageIndex = None,
        # Beam parameters
        beam_width: int = 64,           # M: outer beams to keep
        rollout_beam_width: int = 8,    # Inner beam width for rollout
        # Meal parameters
        servings_per_meal: float = 4.0,
        leftover_ttl: int = 3,
        # Shadow price parameters (for nutrition scoring)
        min_lambda_cal: float = 0.003,
        base_lambda_cal: float = 0.005,
        min_lambda_prot: float = 0.02,
        base_lambda_prot: float = 0.05,
        # Rollout depth limit (None = full rollout to end)
        max_rollout_depth: int = None,
        verbose: bool = False,
    ):
        """
        Initialize cascade planner.

        Args:
            weekly_tensor: Pre-built GPU tensor with candidates
            weekly_targets: Weekly nutrition targets [NUM_NUTRIENTS]
            device: GPU device
            beam_width: Number of outer beams to maintain (M)
            rollout_beam_width: Beam width for inner rollout
            servings_per_meal: Servings consumed per meal
            leftover_ttl: Days until leftovers expire
            max_rollout_depth: Limit rollout to this many slots ahead (None = all)
            verbose: Print progress
        """
        self.wt = weekly_tensor
        self.weekly_targets = weekly_targets
        self.device = device
        self.ingredient_index = ingredient_index
        self.package_index = package_index

        self.M = beam_width
        self.K = weekly_tensor.K
        self.rollout_B = rollout_beam_width
        self.servings = servings_per_meal
        self.leftover_ttl = leftover_ttl
        self.max_rollout_depth = max_rollout_depth
        self.verbose = verbose

        # Shadow prices for nutrition scoring
        self.min_lambda_cal = min_lambda_cal
        self.base_lambda_cal = base_lambda_cal
        self.min_lambda_prot = min_lambda_prot
        self.base_lambda_prot = base_lambda_prot

        # Pre-compute max nutrition per meal for panic detection
        all_cals = weekly_tensor.nutrition[:, :, 0]
        all_prot = weekly_tensor.nutrition[:, :, 1]
        self.max_cal_per_meal = all_cals.max().item() * servings_per_meal
        self.max_prot_per_meal = all_prot.max().item() * servings_per_meal

        if verbose:
            print(f"TensorCascadePlanner initialized:")
            print(f"  Outer beam width (M): {self.M}")
            print(f"  Rollout beam width: {self.rollout_B}")
            print(f"  Candidates per slot (K): {self.K}")
            print(f"  Max rollout depth: {self.max_rollout_depth or 'full'}")

    def plan(self, initial_pantry: Optional[torch.Tensor] = None) -> GPUPlanResult:
        """
        Run cascade planning with rollout-based lookahead.

        LEFTOVERS-FIRST DESIGN:
        - Leftovers are a SEPARATE pool, not part of candidates
        - At each slot, FIRST consume any available leftovers
        - Only cook fresh from candidates if no leftovers available

        Args:
            initial_pantry: Optional [num_ingredients] tensor of starting pantry

        Returns:
            GPUPlanResult with best plan found
        """
        start_time = time.time()

        # Initialize with single beam
        num_ingredients = self.wt.num_ingredients
        state = GPUBeamState(1, num_ingredients, self.device)

        if initial_pantry is not None:
            state.pantry[0] = initial_pantry

        beams_explored = 0
        total_waste = 0.0
        leftover_meals_eaten = 0

        for slot in range(NUM_SLOTS):
            M_current = state.B
            K = self.K

            if self.verbose and slot % 3 == 0:
                day = slot // 3 + 1
                leftover_srv = (state.leftovers[:, :, 1] > 0.5).sum().item()
                print(f"  Day {day}: {M_current} beams, cost ${state.cost.min():.2f}-${state.cost.max():.2f}, leftovers: {leftover_srv}")

            # === STEP 1: CHECK FOR LEFTOVERS ===
            # Leftovers are consumed FIRST, before any candidate selection
            leftovers_consumed = self._consume_leftovers_first(state, slot)

            if leftovers_consumed:
                # All beams ate from leftovers - no candidate selection needed
                leftover_meals_eaten += state.B
                beams_explored += state.B

                # Still need to decay at end of day
                if (slot + 1) % 3 == 0:
                    waste = state.decay_leftovers()
                    total_waste += waste.sum().item()
                continue

            # === STEP 2: NO LEFTOVERS - Cook fresh from candidates ===

            # === EXPAND: M → M×K ===
            expanded = state.expand(K)
            cand_indices = torch.arange(K, device=self.device).repeat(M_current)

            # === UPDATE STATE FOR ALL M×K ===
            self._update_state_batch(expanded, slot, cand_indices)
            beams_explored += expanded.B

            # === COMPUTE EFFECTIVE COST FOR CURRENT CANDIDATES ===
            # This includes nutrition and variety penalties
            effective_current = self._compute_effective_cost_at_slot(expanded, slot, cand_indices)

            # === LOOKAHEAD: Score by total week cost ===
            if slot < NUM_SLOTS - 1:
                # Determine rollout end slot
                if self.max_rollout_depth is not None:
                    end_slot = min(slot + 1 + self.max_rollout_depth, NUM_SLOTS)
                else:
                    end_slot = NUM_SLOTS

                # Run beam rollout for remaining slots
                rollout_costs = self._batched_beam_rollout(
                    expanded,
                    start_slot=slot + 1,
                    end_slot=end_slot,
                )

                # Total cost = effective current + rollout future
                total_costs = effective_current + rollout_costs
            else:
                # Last slot - no rollout needed
                total_costs = effective_current

            # === PRUNE TO TOP M BY LOWEST TOTAL COST ===
            # Use negative because select_topk picks highest
            scores = -total_costs
            target_beams = min(self.M, expanded.B)
            state = expanded.select_topk(scores, target_beams)

            # === ADD RECIPE IDs TO USED LIST (after pruning) ===
            # Now that we've selected the best beams, add their recipe IDs
            self._add_recipe_ids_after_pruning(state, slot)

            # === DECAY LEFTOVERS AT END OF DAY ===
            if (slot + 1) % 3 == 0:
                waste = state.decay_leftovers()
                total_waste += waste.sum().item()

        # Build result from best beam
        elapsed_ms = (time.time() - start_time) * 1000

        best_idx = state.cost.argmin()
        best_cost = state.cost[best_idx].item()
        best_selections = state.selections[best_idx]
        best_nutrition = state.nutrition[best_idx]
        best_pantry = state.pantry[best_idx]

        if self.verbose:
            print(f"  Leftover meals eaten: {leftover_meals_eaten}")

        # Compute compliance
        compliance = {}
        for i, name in enumerate(['calories', 'protein', 'carbs', 'fat', 'fiber']):
            if self.weekly_targets[i] > 0:
                compliance[name] = (best_nutrition[i] / self.weekly_targets[i]).item()

        return GPUPlanResult(
            selections=best_selections,
            nutrition_totals=best_nutrition,
            total_cost=best_cost,
            compliance=compliance,
            beams_explored=beams_explored,
            beams_pruned=beams_explored - self.M,
            runtime_ms=elapsed_ms,
            leftover_waste=total_waste,
            final_pantry=best_pantry,
        )

    def _consume_leftovers_first(
        self,
        state: GPUBeamState,
        slot: int,
    ) -> bool:
        """
        Check if leftovers are available and consume them.

        This is called BEFORE candidate selection. Only consume from leftovers
        if we have ENOUGH for a full meal AND the meal type matches.
        - Breakfast leftovers can only be eaten at breakfast
        - Lunch leftovers can only be eaten at lunch
        - Dinner leftovers can only be eaten at dinner

        Args:
            state: Current beam state (modified in-place)
            slot: Current slot

        Returns:
            True if leftovers were consumed, False if need to cook fresh
        """
        B = state.B
        current_meal_type = slot % 3  # 0=breakfast, 1=lunch, 2=dinner

        # Check leftover servings for MATCHING meal type only
        leftover_servings = state.leftovers[:, :, 1]  # [B, MAX_LEFTOVERS]
        leftover_meal_types = state.leftovers[:, :, 5]  # [B, MAX_LEFTOVERS]

        # Mask for matching meal type
        matching_type = (leftover_meal_types == current_meal_type)  # [B, MAX_LEFTOVERS]

        # Only count servings from matching leftovers
        matching_servings = leftover_servings * matching_type.float()  # [B, MAX_LEFTOVERS]
        total_matching = matching_servings.sum(dim=1)  # [B]

        # Only consume if we have ENOUGH matching leftovers for a full meal
        has_enough = total_matching >= self.servings  # [B]

        # CRITICAL: Only consume if ALL beams have enough leftovers
        # If not all have enough, return False and let ALL beams cook fresh
        # This prevents the bug where some beams eat leftovers AND cook
        if not has_enough.all():
            return False

        # === ALL BEAMS HAVE ENOUGH - CONSUME LEFTOVERS ===
        for beam_idx in range(B):
            beam_leftovers = state.leftovers[beam_idx]  # [MAX_LEFTOVERS, 6]
            # Format: (recipe_id, servings, ttl, cal_per_srv, prot_per_srv, meal_type)

            # Find matching leftover with most servings
            servings = beam_leftovers[:, 1]
            meal_types = beam_leftovers[:, 5]
            matching = (meal_types == current_meal_type) & (servings > 0.5)

            # Get matching servings (set non-matching to 0)
            masked_servings = servings.clone()
            masked_servings[~matching] = 0

            best_idx = masked_servings.argmax()
            best_servings = servings[best_idx].item()

            # Consume up to servings_per_meal from this leftover
            consume = min(self.servings, best_servings)

            # Get nutrition from leftover (stored per-serving)
            cal_per_srv = beam_leftovers[best_idx, 3].item()
            prot_per_srv = beam_leftovers[best_idx, 4].item()

            # Update nutrition (calories and protein from leftover)
            state.nutrition[beam_idx, 0] += cal_per_srv * consume
            state.nutrition[beam_idx, 1] += prot_per_srv * consume

            # Reduce leftover servings
            state.leftovers[beam_idx, best_idx, 1] -= consume

            # If fully consumed, clear the slot
            if state.leftovers[beam_idx, best_idx, 1] < 0.5:
                state.leftovers[beam_idx, best_idx, :] = 0

            # Record selection as -1 to indicate leftover
            state.selections[beam_idx, slot] = -1

        # All beams consumed leftovers
        return True

    def _batched_beam_rollout(
        self,
        state: GPUBeamState,
        start_slot: int,
        end_slot: int,
    ) -> torch.Tensor:
        """
        Run GREEDY rollout for all B states in parallel.

        LEFTOVERS-FIRST: At each slot, first check if leftovers exist.
        If yes, consume them (cost=0). Only cook fresh if no leftovers.

        Args:
            state: Current state with B beams
            start_slot: First slot to simulate
            end_slot: Last slot (exclusive) to simulate

        Returns:
            [B] tensor of rollout costs (cost from start_slot to end_slot)
        """
        B = state.B

        if start_slot >= end_slot:
            return torch.zeros(B, device=self.device)

        # Clone state for simulation (don't modify original)
        sim = state.clone()

        # Track starting cost to compute rollout delta
        start_cost = sim.cost.clone()

        for slot in range(start_slot, end_slot):
            # === STEP 1: CHECK FOR LEFTOVERS ===
            leftovers_consumed = self._consume_leftovers_rollout(sim)

            if leftovers_consumed:
                # Leftovers consumed - no cooking needed, cost stays same
                if (slot + 1) % 3 == 0:
                    sim.decay_leftovers()
                continue

            # === STEP 2: NO LEFTOVERS - Cook fresh ===
            K = self.K

            # Score all K candidates for all B beams
            costs_2d = self._compute_candidate_costs_batch(sim, slot)  # [B, K]

            # GREEDY: Pick best candidate for each beam
            best_costs, best_indices = costs_2d.min(dim=1)  # [B]

            # Update state with greedy choices (approximate cost for speed)
            self._update_state_batch(sim, slot, best_indices, use_approximate_cost=True)

            # Decay leftovers at end of day
            if (slot + 1) % 3 == 0:
                sim.decay_leftovers()

        # Rollout cost is total cost minus starting cost
        rollout_costs = sim.cost - start_cost
        return rollout_costs

    def _consume_leftovers_rollout(self, state: GPUBeamState) -> bool:
        """
        Fast leftover consumption for rollout simulation.

        Vectorized version - consumes from biggest leftover for each beam.
        Only consumes if we have ENOUGH for a full meal.

        Args:
            state: Simulation state (modified in-place)

        Returns:
            True if ALL beams had enough leftovers, False otherwise
        """
        B = state.B

        # Check total leftover servings per beam
        leftover_servings = state.leftovers[:, :, 1]  # [B, MAX_LEFTOVERS]
        total_per_beam = leftover_servings.sum(dim=1)  # [B]

        # Only consume if we have ENOUGH for a full meal
        has_enough = total_per_beam >= self.servings  # [B]

        # If ANY beam doesn't have enough, we need to cook fresh
        if not has_enough.all():
            return False

        # All beams have leftovers - consume from biggest
        # Find index of max servings per beam
        max_servings, max_idx = leftover_servings.max(dim=1)  # [B], [B]

        # Get nutrition values
        batch_idx = torch.arange(B, device=self.device)
        cal_per_srv = state.leftovers[batch_idx, max_idx, 3]  # [B]
        prot_per_srv = state.leftovers[batch_idx, max_idx, 4]  # [B]

        # Consume up to servings_per_meal
        consume = torch.minimum(
            max_servings,
            torch.full((B,), self.servings, device=self.device)
        )

        # Update nutrition
        state.nutrition[:, 0] += cal_per_srv * consume
        state.nutrition[:, 1] += prot_per_srv * consume

        # Reduce leftover servings
        state.leftovers[batch_idx, max_idx, 1] -= consume

        # Clear fully consumed leftovers
        fully_consumed = state.leftovers[batch_idx, max_idx, 1] < 0.5
        state.leftovers[batch_idx[fully_consumed], max_idx[fully_consumed], :] = 0

        return True

    def _compute_candidate_costs_batch(
        self,
        state: GPUBeamState,
        slot: int,
    ) -> torch.Tensor:
        """
        Compute effective cost for all K candidates across all B beams.

        NOTE: This is only called when NO leftovers are available.
        Leftovers are consumed separately via _consume_leftovers_first().

        Returns:
            [B, K] tensor of effective costs (lower = better)
        """
        B = state.B
        K = self.K

        # Get candidate data for this slot
        cand_nutrition = self.wt.nutrition[slot]  # [K, NUM_NUTRIENTS]
        cand_costs = self.wt.costs[slot]  # [K]
        cand_servings = self.wt.servings[slot]  # [K]
        cand_recipe_ids = self.wt.recipe_ids[slot]  # [K]
        cand_ingredients = self.wt.ingredients[slot]  # [K, num_ing]

        # === CALCULATE COOKING COST WITH PANTRY ===
        # Full recipe ingredients: [K, num_ing] * [K, 1] = [K, num_ing]
        full_recipe_ingredients = cand_ingredients * cand_servings.unsqueeze(1)  # [K, num_ing]

        # Expand for batch: [1, K, num_ing]
        full_recipe_ing_exp = full_recipe_ingredients.unsqueeze(0)  # [1, K, num_ing]

        # Expand pantry: [B, 1, num_ing]
        pantry_exp = state.pantry.unsqueeze(1)  # [B, 1, num_ing]

        # Available from pantry: [B, K, num_ing]
        available_from_pantry = torch.minimum(full_recipe_ing_exp, pantry_exp)

        # Ingredients to buy: [B, K, num_ing]
        ingredients_to_buy = (full_recipe_ing_exp - available_from_pantry).clamp(min=0)

        # Buy ratio: [B, K]
        total_recipe_grams = full_recipe_ingredients.sum(dim=1).clamp(min=1e-6)  # [K]
        total_to_buy_grams = ingredients_to_buy.sum(dim=2)  # [B, K]
        buy_ratio = total_to_buy_grams / total_recipe_grams.unsqueeze(0)  # [B, K]

        # Full recipe cost: [K]
        full_recipe_cost = cand_costs * cand_servings  # [K]

        # Actual cooking cost: [B, K]
        actual_cost = full_recipe_cost.unsqueeze(0) * buy_ratio  # [B, K]

        # === ADD NUTRITION PENALTY ===
        remaining_slots = max(NUM_SLOTS - slot - 1, 1)

        debt = self.weekly_targets - state.nutrition  # [B, NUM_NUTRIENTS]
        debt_cal = debt[:, 0:1]  # [B, 1]
        debt_prot = debt[:, 1:2]  # [B, 1]

        # Required pace - what we NEED per meal to meet targets
        pace_cal = debt_cal / remaining_slots  # [B, 1]
        pace_prot = debt_prot / remaining_slots  # [B, 1]

        # Nutrition this meal would provide: [K, NUM_NUTRIENTS] * servings
        meal_nutrition = cand_nutrition * self.servings  # [K, NUM_NUTRIENTS]
        meal_cal = meal_nutrition[:, 0:1].T  # [1, K]
        meal_prot = meal_nutrition[:, 1:2].T  # [1, K]

        # Shortfall if we pick this meal: [B, K]
        cal_shortfall = F.relu(pace_cal - meal_cal)  # [B, K]
        prot_shortfall = F.relu(pace_prot - meal_prot)  # [B, K]

        # Urgency-scaled penalty (more urgent as week progresses)
        urgency = 1.0 + 9.0 * (slot / NUM_SLOTS)
        nutrition_penalty = urgency * (
            self.base_lambda_cal * cal_shortfall +
            self.base_lambda_prot * prot_shortfall
        )

        # === RECIPE REUSE CONSTRAINT ===
        # HARD CONSTRAINT: Cannot reuse ANY recipe (main OR side) within the week
        # Check ALL recipe IDs for each candidate against used_recipe_ids

        # Get all recipe IDs for candidates: [K, 4] (main + 3 sides)
        all_cand_ids = self.wt.all_recipe_ids[slot]  # [K, 4]

        # Used recipe IDs: [B, MAX_RECENT_RECIPES]
        used_ids = state.used_recipe_ids  # [B, num_used]

        # For each beam-candidate pair, check if ANY of the candidate's IDs match used IDs
        # all_cand_ids: [K, 4] -> [1, K, 4]
        # used_ids: [B, num_used] -> [B, 1, num_used]
        all_cand_exp = all_cand_ids.unsqueeze(0)  # [1, K, 4]
        used_exp = used_ids.unsqueeze(1).unsqueeze(3)  # [B, 1, num_used, 1]
        all_cand_exp2 = all_cand_exp.unsqueeze(2)  # [1, K, 1, 4]

        # Check matches: [B, K, num_used, 4]
        matches = (used_exp == all_cand_exp2) & (used_exp > 0) & (all_cand_exp2 > 0)

        # Count how many IDs overlap for each candidate
        # matches: [B, K, num_used, 4] -> sum over num_used and recipe slots
        num_overlaps = matches.any(dim=2).sum(dim=2).float()  # [B, K] - count of overlapping IDs (0-4)
        has_any_overlap = num_overlaps > 0  # [B, K]

        # Check if ANY candidate has zero overlaps
        any_unblocked = (~has_any_overlap).any(dim=1, keepdim=True)  # [B, 1]

        # SMART VARIETY PENALTY:
        # - If unblocked candidates exist: HARD block overlapping ones ($1000)
        # - If ALL candidates overlap: small penalty per overlap ($10) so we pick best pantry match
        variety_penalty = torch.where(
            any_unblocked.expand_as(has_any_overlap),
            # Unblocked candidates exist - strongly prefer them
            torch.where(has_any_overlap, torch.full_like(actual_cost, 1000.0), torch.zeros_like(actual_cost)),
            # ALL blocked - just prefer fewer overlaps, but let pantry savings dominate
            num_overlaps * 10.0
        )

        # Effective cost = actual cost + nutrition penalty + variety penalty
        return actual_cost + nutrition_penalty + variety_penalty

    def _compute_effective_cost_at_slot(
        self,
        state: GPUBeamState,
        slot: int,
        cand_indices: torch.Tensor,
    ) -> torch.Tensor:
        """
        Compute effective cost for expanded beams at current slot.

        NOTE: This is only called when cooking fresh (no leftovers).
        Leftovers are handled separately.

        Args:
            state: Expanded GPUBeamState with B beams
            slot: Current slot
            cand_indices: [B] candidate indices that were applied

        Returns:
            [B] tensor of effective costs
        """
        B = state.B

        # Raw accumulated cost
        raw_cost = state.cost  # [B]

        # === NUTRITION PENALTY ===
        remaining_slots = max(NUM_SLOTS - slot - 1, 1)

        debt = self.weekly_targets - state.nutrition  # [B, NUM_NUTRIENTS]
        debt_cal = debt[:, 0]  # [B]
        debt_prot = debt[:, 1]  # [B]

        # Required pace
        pace_cal = debt_cal / remaining_slots
        pace_prot = debt_prot / remaining_slots

        # Expected pace if on track
        expected_cal_rate = self.weekly_targets[0] / NUM_SLOTS
        expected_prot_rate = self.weekly_targets[1] / NUM_SLOTS

        # Shortfall vs expected
        cal_shortfall = F.relu(pace_cal - expected_cal_rate)
        prot_shortfall = F.relu(pace_prot - expected_prot_rate)

        # Urgency-scaled penalty
        urgency = 1.0 + 9.0 * (slot / NUM_SLOTS)
        nutrition_penalty = urgency * (
            self.base_lambda_cal * cal_shortfall +
            self.base_lambda_prot * prot_shortfall
        )

        # === RECIPE REUSE CONSTRAINT ===
        # Check ALL recipe IDs (main + sides) against used_recipe_ids
        # This is critical for preventing ANY recipe from repeating

        # Get ALL recipe IDs for the selected candidates: [B, 4]
        all_cand_ids = self.wt.all_recipe_ids[slot][cand_indices]  # [B, 4]

        # Get used IDs: [B, MAX_RECENT]
        used_ids = state.used_recipe_ids  # [B, 84]

        # For each beam, check if ANY of its candidate's IDs match ANY used ID
        # all_cand_ids: [B, 4] -> [B, 1, 4]
        # used_ids: [B, 84] -> [B, 84, 1]
        all_cand_exp = all_cand_ids.unsqueeze(1)  # [B, 1, 4]
        used_exp = used_ids.unsqueeze(2)  # [B, 84, 1]

        # Check matches: [B, 84, 4]
        matches = (used_exp == all_cand_exp) & (used_exp > 0) & (all_cand_exp > 0)

        # Count how many IDs overlap (0-4)
        num_overlaps = matches.any(dim=1).sum(dim=1).float()  # [B]
        has_overlap = num_overlaps > 0  # [B]

        # HARD BLOCK for overlapping recipes - variety is mandatory
        # Check if ANY candidate has zero overlaps (is unblocked)
        any_unblocked = (~has_overlap).any()  # scalar bool

        # If unblocked candidates exist: HARD block overlapping ones ($1000)
        # If ALL candidates overlap: small penalty so we pick best pantry match
        variety_penalty = torch.where(
            has_overlap,
            torch.where(
                torch.tensor(any_unblocked, device=self.device),
                torch.full_like(raw_cost, 1000.0),  # Hard block
                num_overlaps * 10.0  # Soft penalty when all blocked
            ),
            torch.zeros_like(raw_cost)
        )

        # Total effective cost
        return raw_cost + nutrition_penalty + variety_penalty

    def _compute_effective_cost_for_pruning(
        self,
        state: GPUBeamState,
        slot: int,
    ) -> torch.Tensor:
        """
        Compute effective cost (including nutrition penalty) for pruning decisions.

        This is used during rollout to decide which candidates to keep.

        Returns:
            [B] tensor of effective costs (lower = better)
        """
        B = state.B
        remaining_slots = max(NUM_SLOTS - slot - 1, 1)

        # Compute nutrition debt and shadow prices
        debt = self.weekly_targets - state.nutrition
        debt_cal = debt[:, 0]
        debt_prot = debt[:, 1]

        # Required pace
        pace_cal = debt_cal / remaining_slots
        pace_prot = debt_prot / remaining_slots

        # Shortage detection
        slots_done = slot + 1
        expected_cal = (slots_done / NUM_SLOTS) * self.weekly_targets[0]
        expected_prot = (slots_done / NUM_SLOTS) * self.weekly_targets[1]

        behind_cal = F.relu(expected_cal - state.nutrition[:, 0])
        behind_prot = F.relu(expected_prot - state.nutrition[:, 1])

        shortage_cal = behind_cal / (self.weekly_targets[0] + 1e-6)
        shortage_prot = behind_prot / (self.weekly_targets[1] + 1e-6)

        # Shadow prices
        lambda_cal = self.min_lambda_cal + self.base_lambda_cal * shortage_cal
        lambda_prot = self.min_lambda_prot + self.base_lambda_prot * shortage_prot

        # Nutrition penalty based on pace
        # Estimate shortfall from pace using average nutrition
        avg_cal_per_meal = self.max_cal_per_meal * 0.5  # Rough estimate
        cal_shortfall = F.relu(pace_cal - avg_cal_per_meal)
        prot_shortfall = F.relu(pace_prot - self.max_prot_per_meal * 0.5)

        nutrition_penalty = lambda_cal * cal_shortfall + lambda_prot * prot_shortfall

        # Effective cost = raw cost + nutrition penalty
        return state.cost + nutrition_penalty

    def _buy_packages_batch(
        self,
        ingredients_to_buy: torch.Tensor,  # [B, num_ingredients]
        needs_cooking: torch.Tensor,  # [B] bool
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Buy whole packages for all beams that need cooking.

        Args:
            ingredients_to_buy: [B, num_ingredients] grams needed per ingredient
            needs_cooking: [B] bool mask for which beams need cooking

        Returns:
            (costs [B], package_extras [B, num_ingredients])
            - costs: total cost for each beam
            - package_extras: grams purchased beyond what was needed (for pantry)
        """
        B = ingredients_to_buy.shape[0]
        num_ing = ingredients_to_buy.shape[1]

        costs = torch.zeros(B, dtype=torch.float32, device=self.device)
        package_extras = torch.zeros(B, num_ing, dtype=torch.float32, device=self.device)

        # Convert to numpy for iteration (package index isn't GPU-accelerated)
        needs_np = ingredients_to_buy.cpu().numpy()
        cooking_np = needs_cooking.cpu().numpy()

        for beam_idx in range(B):
            if not cooking_np[beam_idx]:
                continue

            beam_cost = 0.0
            for ing_idx in range(num_ing):
                grams_needed = needs_np[beam_idx, ing_idx]
                if grams_needed <= 0:
                    continue

                # Get FNDDS code for this ingredient
                fndds = self.ingredient_index.idx_to_fpid.get(ing_idx, "")

                # Buy whole package(s)
                cost, grams_bought = self.package_index.buy_ingredient(fndds, grams_needed)
                beam_cost += cost

                # Package extras go to pantry
                extras = grams_bought - grams_needed
                if extras > 0:
                    package_extras[beam_idx, ing_idx] = float(extras)

            costs[beam_idx] = float(beam_cost)

        return costs, package_extras

    def _update_state_batch(
        self,
        state: GPUBeamState,
        slot: int,
        cand_indices: torch.Tensor,
        use_approximate_cost: bool = False,
    ) -> None:
        """
        Update state for all beams with their chosen candidates.

        NOTE: This is only called when cooking fresh (no leftovers).
        Leftovers are consumed via _consume_leftovers_first().

        Handles:
        - Pantry-based ingredient coverage
        - Cooking cost calculation
        - Nutrition update
        - New leftover creation
        - Recent recipes update

        Args:
            state: GPUBeamState with B beams (modified in-place)
            slot: Current slot
            cand_indices: [B] candidate indices for each beam
            use_approximate_cost: If True, use fast approximate cost (for rollout)
        """
        B = state.B

        # Gather candidate data
        cand_nutrition = self.wt.nutrition[slot][cand_indices]  # [B, NUM_NUTRIENTS]
        cand_costs = self.wt.costs[slot][cand_indices]  # [B]
        cand_servings = self.wt.servings[slot][cand_indices]  # [B]
        cand_recipe_ids = self.wt.recipe_ids[slot][cand_indices]  # [B]
        cand_ingredients = self.wt.ingredients[slot][cand_indices]  # [B, num_ing]

        # === UPDATE NUTRITION ===
        # We eat servings_per_meal worth of nutrition
        state.nutrition += cand_nutrition * self.servings

        # === CALCULATE COOKING COST ===
        # Full recipe ingredient needs (for entire recipe, not just what we eat)
        full_recipe_ingredients = cand_ingredients * cand_servings.unsqueeze(1)

        # Check pantry coverage
        available_from_pantry = torch.minimum(full_recipe_ingredients, state.pantry)
        ingredients_to_buy = (full_recipe_ingredients - available_from_pantry).clamp(min=0)

        # Buy ingredients using WHOLE PACKAGES (or approximate for speed)
        use_packages = (
            self.package_index is not None
            and self.ingredient_index is not None
            and not use_approximate_cost
        )

        # All beams are cooking (no leftover consumption here)
        needs_cooking = torch.ones(B, dtype=torch.bool, device=self.device)

        if use_packages:
            # Use package-based purchasing (accurate but slower)
            cooking_cost, package_extras = self._buy_packages_batch(
                ingredients_to_buy, needs_cooking
            )
        else:
            # Fallback: use recipe cost proportionally (APPROXIMATE but fast)
            full_recipe_cost = cand_costs * cand_servings
            total_recipe_grams = full_recipe_ingredients.sum(dim=1).clamp(min=1e-6)
            cost_per_gram = full_recipe_cost / total_recipe_grams
            grams_to_buy = ingredients_to_buy.sum(dim=1)
            cooking_cost = grams_to_buy * cost_per_gram
            package_extras = torch.zeros_like(ingredients_to_buy)

        # Add cooking cost
        state.cost += cooking_cost

        # === UPDATE PANTRY ===
        # Consume from pantry
        state.pantry = (state.pantry - available_from_pantry).clamp(min=0)

        # Add package extras to pantry (bought more than needed)
        state.pantry = state.pantry + package_extras

        # === CREATE NEW LEFTOVERS ===
        # We eat servings_per_meal, leftover is the rest
        leftover_servings_new = (cand_servings - self.servings).clamp(min=0)
        has_leftover = leftover_servings_new > 0.5

        leftover_idx = slot % MAX_LEFTOVERS
        meal_type = float(slot % 3)  # 0=breakfast, 1=lunch, 2=dinner

        state.leftovers[:, leftover_idx, 0] = torch.where(
            has_leftover, cand_recipe_ids.float(),
            state.leftovers[:, leftover_idx, 0]
        )
        state.leftovers[:, leftover_idx, 1] = torch.where(
            has_leftover, leftover_servings_new,
            state.leftovers[:, leftover_idx, 1]
        )
        state.leftovers[:, leftover_idx, 2] = torch.where(
            has_leftover, torch.full_like(leftover_servings_new, self.leftover_ttl),
            state.leftovers[:, leftover_idx, 2]
        )
        state.leftovers[:, leftover_idx, 3] = torch.where(
            has_leftover, cand_nutrition[:, 0],
            state.leftovers[:, leftover_idx, 3]
        )
        state.leftovers[:, leftover_idx, 4] = torch.where(
            has_leftover, cand_nutrition[:, 1],
            state.leftovers[:, leftover_idx, 4]
        )
        # Store meal type (index 5)
        state.leftovers[:, leftover_idx, 5] = torch.where(
            has_leftover, torch.full_like(leftover_servings_new, meal_type),
            state.leftovers[:, leftover_idx, 5]
        )

        # === UPDATE SELECTIONS ===
        state.selections[:, slot] = cand_indices

        # NOTE: Recipe IDs are added to used_recipe_ids AFTER pruning,
        # not here. This ensures the variety check in _compute_effective_cost_at_slot
        # only sees IDs from PREVIOUS slots, not the current slot's candidates.

    def _add_recipe_ids_after_pruning(
        self,
        state: GPUBeamState,
        slot: int,
    ) -> None:
        """
        Add recipe IDs to used_recipe_ids AFTER pruning.

        This is called after select_topk() so we only track the IDs of
        candidates that actually survived into the beam.

        Args:
            state: The pruned GPUBeamState
            slot: Current slot
        """
        B = state.B

        # Get the candidate indices that were selected at this slot
        cand_indices = state.selections[:, slot]  # [B]

        # Get ALL recipe IDs for the selected candidates: [B, 4]
        all_ids = self.wt.all_recipe_ids[slot][cand_indices]  # [B, 4]

        # Add each recipe ID to used_recipe_ids
        for i in range(all_ids.shape[1]):
            recipe_id = all_ids[:, i]  # [B]
            valid = recipe_id > 0  # Skip zeros (empty slots)

            # Find next available slot in used_recipe_ids
            for b in range(B):
                if valid[b]:
                    count = state.used_count[b].item()
                    if count < state.used_recipe_ids.shape[1]:
                        state.used_recipe_ids[b, int(count)] = recipe_id[b]
                        state.used_count[b] += 1


# Add select_by_indices method to GPUBeamState
def _select_by_indices(self, indices: torch.Tensor) -> "GPUBeamState":
    """Select beams by flat indices."""
    k = indices.shape[0]
    selected = GPUBeamState(k, self.num_ingredients, self.device)
    selected.nutrition = self.nutrition[indices]
    selected.cost = self.cost[indices]
    selected.selections = self.selections[indices]
    selected.scores = self.scores[indices]
    selected.pantry = self.pantry[indices]
    selected.leftovers = self.leftovers[indices]
    selected.num_leftovers = self.num_leftovers[indices]
    selected.recent_recipes = self.recent_recipes[indices]
    selected.recent_count = self.recent_count[indices]
    selected.current_slot = self.current_slot
    return selected

# Monkey-patch the method onto GPUBeamState
GPUBeamState.select_by_indices = _select_by_indices


def plan_week_cascade(
    recipe_pool: List[Dict],
    device: torch.device = None,
    beam_width: int = 64,
    rollout_beam_width: int = 8,
    candidates_per_slot: int = 64,
    max_rollout_depth: int = 10,
    servings_per_meal: float = 4.0,
    initial_pantry: Optional[Dict[str, float]] = None,
    seed: int = 42,
    verbose: bool = True,
) -> GPUPlanResult:
    """
    Convenience function to run cascade planning.

    Args:
        recipe_pool: List of recipe dictionaries
        device: GPU device (default: auto-detect)
        beam_width: Outer beam width (M)
        rollout_beam_width: Inner rollout beam width
        candidates_per_slot: Candidates per slot (K)
        max_rollout_depth: Max slots to look ahead (None = full)
        servings_per_meal: Servings per meal
        initial_pantry: Starting pantry (FPID -> grams)
        seed: Random seed
        verbose: Print progress

    Returns:
        GPUPlanResult
    """
    import torch
    from .weekly_tensor import build_weekly_tensor

    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    torch.manual_seed(seed)

    # Build ingredient index
    ingredient_index = IngredientIndex(device)
    ingredient_index.build_from_recipes(recipe_pool)

    # Build package index
    package_index = PackageIndex()

    # Build weekly tensor
    weekly_tensor = build_weekly_tensor(
        recipe_pool=recipe_pool,
        ingredient_index=ingredient_index,
        K=candidates_per_slot,
        device=device,
        seed=seed,
        initial_pantry=initial_pantry,
    )

    # Build targets
    targets = NutritionTargets().to_weekly_tensor(device)

    # Create planner
    planner = TensorCascadePlanner(
        weekly_tensor=weekly_tensor,
        weekly_targets=targets,
        device=device,
        ingredient_index=ingredient_index,
        package_index=package_index,
        beam_width=beam_width,
        rollout_beam_width=rollout_beam_width,
        servings_per_meal=servings_per_meal,
        max_rollout_depth=max_rollout_depth,
        verbose=verbose,
    )

    # Convert pantry if provided
    pantry_tensor = None
    if initial_pantry:
        pantry_tensor = ingredient_index.pantry_dict_to_tensor(initial_pantry)

    return planner.plan(initial_pantry=pantry_tensor)
