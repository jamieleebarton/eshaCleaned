"""Scoring configuration for meal planning optimization.

This module provides a parameterized scoring system that allows users to
choose between presets (budget, balanced, high_protein) or customize
individual scoring parameters.

Usage:
    from scoring_config import ScoringConfig, ScoringMode, SCORING_PRESETS

    # Use a preset
    config = ScoringConfig.budget()
    planner = SparseCascadePlanner(..., scoring_config=config)

    # Or use high protein
    config = ScoringConfig.high_protein(target_pct=35.0)
    planner = SparseCascadePlanner(..., scoring_config=config)

    # Or customize
    config = ScoringConfig(
        protein_pct_target=25.0,
        enable_produce_bonus=True,
        leftover_value=2.00,
    )

# =============================================================================
# IMPLEMENTATION STATUS (Updated Jan 12, 2026)
# =============================================================================
#
# This documents which config parameters are ACTUALLY READ by sparse_cascade.py
# vs which are DEAD CODE (defined but ignored).
#
# IMPLEMENTED - These 31 parameters WORK:
# -----------------------------------------------------------------------------
# LEFTOVER CONTROL:
#   - leftover_value             ✅ $/serving bonus for leftovers (line 1090)
#   - leftover_credit_rate       ✅ Credit % when consuming leftovers (line 933)
#   - leftover_target            ✅ 0-1 preference slider (line 519)
#   - leftover_meals_cap         ✅ Max meals of leftovers (lines 1087, 2854)
#   - side_leftover_value        ✅ $/serving for side leftovers (line 2856)
#   - leftover_pct_target        ✅ Target % meals from leftovers (line 577)
#
# SERVING SIZE CONTROL:
#   - serving_match_weight       ✅ Penalty for wrong batch size (lines 1106, 2869)
#   - enable_serving_filter      ✅ Enable batch size filtering (lines 1097, 2861)
#   - serving_tolerance_mult     ✅ Acceptable range multiplier (lines 1099, 2863)
#   - excess_serving_penalty     ✅ $/serving for oversized batches (lines 1225, 1403)
#
# PANTRY CONTROL:
#   - pantry_usage_value         ✅ $/gram discount for pantry use (lines 1037, 1134)
#   - enable_holding_cost        ✅ Enable pantry growth penalty (lines 1263, 1417)
#   - target_pantry_kg           ✅ Target pantry size (lines 1266, 1420)
#   - holding_cost_rate          ✅ $/kg penalty rate (lines 1267, 1421)
#   - perishable_urgency_value   ✅ $/gram for expiring items (lines 1198, 1385)
#
# PROTEIN DIVERSITY:
#   - enable_protein_diversity_boost ✅ Enable beef/pork/fish boosts (lines 1049, 1157)
#   - beef_boost                 ✅ $/1000cal boost for beef (lines 1053, 1161)
#   - fish_boost                 ✅ $/1000cal boost for fish (lines 1055, 1163)
#   - protein_diversity_boost    ✅ $/1000cal boost for pork (lines 1054, 1162)
#   - protein_target_distribution ✅ Progressive protein quota distribution (replaces cooldowns)
#
# CALORIE SHADOW PRICES:
#   - shadow_lambda_min          ✅ Base calorie penalty (line 602)
#   - shadow_lambda_max          ✅ Max calorie penalty (line 603)
#   - shadow_gamma               ✅ Urgency curve shape (line 604)
#   - shadow_tau                 ✅ Margin threshold (line 605)
#   - base_lambda_cal            ✅ Base multiplier (line 752)
#
# SECOND SIDE & BONUSES:
#   - enable_second_side         ✅ Add side when calories low (line 3039)
#   - side2_calorie_gap_threshold ✅ When to add side2 (line 3050)
#   - side2_prefer_produce       ✅ Prefer veggies for side2 (line 3068)
#   - template_match_bonus       ✅ Bonus for leftover matching template (lines 1249, 1414)
#   - frozen_pressure_base       ✅ Penalty for frozen accumulation (line 1257)
#   - enable_fruit_snacks        ✅ Auto-inject fruit snacks (line 525)
#
# DEAD CODE - These 20 parameters are IGNORED:
# -----------------------------------------------------------------------------
# PRODUCE (hardcoded):
#   - produce_value              ❌ HARDCODED as 0.002 (line 2841)
#   - enable_produce_bonus       ❌ Not implemented
#   - enable_main_produce_bonus  ❌ Not implemented
#   - main_produce_value         ❌ Not implemented
#
# PROTEIN DENSITY:
#   - protein_pct_target         ✅ Used in density bonus + band filter + auto-enable
#   - enable_protein_prefilter   ✅ Protein band filter in _cost_filter_candidates (auto-enabled)
#   - protein_filter_margin      ✅ Band half-width for protein prefilter (default 5pp)
#   - enable_protein_density_mult ❌ Not implemented
#   - enable_protein_density_bonus ✅ Bidirectional density bonus in scoring
#   - protein_density_value      ✅ $/serving bonus scaling
#   - auto_protein_targeting     ✅ Auto-enable protein mechanisms when target > 15%
#   - protein_band_widen_step    ✅ Adaptive widening increment for protein band
#   - protein_band_max_widen     ✅ Max widening cap for protein band
#   - side_protein_value         ❌ Not implemented
#
# PROTEIN COOLDOWN (uses hardcoded dict instead):
#   - protein_cooldown_penalty   ❌ Uses PROTEIN_SOURCE_COOLDOWN dict
#   - eggs_cooldown              ❌ Hardcoded as 3 in PROTEIN_SOURCE_COOLDOWN
#   - legumes_cooldown           ❌ Hardcoded as 3 in PROTEIN_SOURCE_COOLDOWN
#   - poultry_cooldown           ❌ Hardcoded as 2 in PROTEIN_SOURCE_COOLDOWN
#   - enable_protein_specialization ❌ Not implemented
#   - protein_specialization_bonus ❌ Not implemented
#
# MACRO PENALTIES:
#   - macro_tolerance_pct        ❌ Not implemented (hardcoded)
#   - macro_deviation_weight     ✅ Weight on macro % deviation penalty (line ~2180)
#   - low_servings_penalty       ❌ Not implemented
#
# LEGACY (replaced by holding cost):
#   - pantry_urgency_threshold   ❌ Legacy, use enable_holding_cost
#   - pantry_urgency_scale       ❌ Legacy
#   - pantry_urgency_max         ❌ Legacy
#
# FREEZER (constructor params, not config):
#   - enable_perishable_urgency  ❌ Not read from config
#   - enable_auto_freeze         ❌ Not read from config
#   - freezer_capacity_kg        ❌ Not read from config
#
# TODO: Wire up dead parameters or remove them from config.
# Priority for implementation:
#   1. produce_value (currently hardcoded, easy fix)
#   2. eggs_cooldown/legumes_cooldown/poultry_cooldown (use config instead of dict)
#   3. protein_pct_target (add to scoring)
#
# =============================================================================
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum
import json

if TYPE_CHECKING:
    from tier_injection import TierConfig


# =============================================================================
# PLANNER INVARIANTS - Non-negotiable constraints for system stability
# =============================================================================

@dataclass
class PlannerInvariants:
    """Hard constraints that must hold for the planner to be considered stable.

    These define success criteria - the system fails fast if any is violated.
    Used by comprehensive_50week_test.py to gate changes.

    Thresholds stored here, checking logic in comprehensive_50week_test.py
    to avoid circular imports with LongTermResult.
    """

    # Pantry growth rate (kg/week) - positive = growth, negative = depletion
    # Target: pantry can grow moderately; 60-70kg is acceptable
    max_pantry_slope_kg_per_week: float = 4.0  # Fail if growing faster than this

    # Minimum utilization = consumed / acquired (how much of what we buy do we use?)
    # 1.0 = using exactly what we buy (pantry flat)
    # 0.65 = using 65% of what we buy (pantry growing but acceptable)
    min_pantry_utilization: float = 0.65

    # Cost ceiling as multiple of budget mode baseline
    # Budget mode ~$70/week, so 3.0x = $210/week max for any mode
    max_weekly_cost_multiplier: float = 3.0

    # Mode-specific nutrition requirements
    # For HIGH_PROTEIN mode, require at least this protein %
    min_protein_pct_high_protein: float = 30.0

    # For BUDGET mode, minimum calorie compliance
    min_cal_compliance: float = 0.90


# Default invariants for different modes
DEFAULT_INVARIANTS = PlannerInvariants()
STRICT_INVARIANTS = PlannerInvariants(
    max_pantry_slope_kg_per_week=1.0,
    min_pantry_utilization=0.9,
    max_weekly_cost_multiplier=2.5,
)


class ScoringMode(Enum):
    """Scoring mode presets."""
    BUDGET = "budget"
    BALANCED = "balanced"
    HIGH_PROTEIN = "high_protein"
    CUSTOM = "custom"


@dataclass
class ScoringConfig:
    """Complete scoring configuration for meal planning.

    This centralizes all scoring parameters that were previously hardcoded
    throughout sparse_cascade.py. By using presets or custom configs, users
    can easily switch between budget-focused (~$66/week) and protein-focused
    (~$150-200/week) meal planning.

    Attributes:
        mode: The scoring mode (budget, balanced, high_protein, custom)

        # Cost/Leftover Parameters
        leftover_value: $/serving bonus for consuming leftovers
        leftover_credit_rate: Fraction of leftover value credited (0.0-1.0)
        leftover_target: User preference for leftovers (0.0-1.0)

        # Protein Parameters
        protein_pct_target: Target protein as % of calories (15-40)
        enable_protein_prefilter: Filter to high-protein recipes in cost pass
        protein_filter_margin: How far below target to filter (5 = target-5%)
        enable_protein_density_mult: Boost leftover value for protein-dense recipes
        side_protein_value: $/gram bonus for protein in side dishes

        # Produce Parameters
        enable_produce_bonus: Give bonus for veggie/fruit sides
        produce_value: $/gram for produce in sides

        # Pantry Parameters
        pantry_usage_value: $/gram discount for using pantry items

        # Penalty Parameters
        protein_cooldown_penalty: $/serving penalty for recent protein source
        low_servings_penalty: Penalty for recipes with insufficient servings

        # Tolerance Parameters
        macro_tolerance_pct: Tolerance band for macro deviation penalties
        macro_deviation_weight: Weight on macro deviations in scoring
    """

    mode: ScoringMode = ScoringMode.BALANCED

    # === COST/LEFTOVER PARAMETERS ===
    leftover_value: float = 1.50           # $/serving for main dish leftovers
    leftover_credit_rate: float = 0.70     # Credit % of leftover value
    leftover_target: float = 0.5           # 0.0-1.0 preference slider (DEPRECATED - use leftover_pct_target)
    leftover_meals_cap: float = 2.0        # Max meals worth of leftovers (DEPRECATED - use leftover_pct_target)
    side_leftover_value: float = 1.00      # $/serving for side dish leftovers (separate from mains)
    leftover_min_cal_per_serving: float = 50.0  # Min cal/srv to store as leftover (excludes condiments)
    never_used_bonus: float = 0.50         # $/recipe bonus for never-used recipes (exploration)

    # === NEW: LEFTOVER PERCENTAGE CONTROL ===
    # Customer-facing control: what % of meals should come from leftovers?
    # Formula: ideal_servings = family_size / (1 - leftover_pct_target)
    leftover_pct_target: float = 0.75      # 0.0-0.85: 0=fresh daily, 0.75=batch cook (default)
    side_leftover_pct_target: float = -1.0 # -1 = use leftover_pct_target; 0.0 = fresh sides daily
    serving_match_weight: float = 0.50     # $/serving penalty for deviation from ideal
    enable_serving_filter: bool = True     # Enable serving-size preference in scoring
    serving_tolerance_mult: float = 1.5    # Acceptable range: ideal_servings * this

    # === PROTEIN PARAMETERS ===
    protein_pct_target: float = 15.0       # Macro % target
    enable_protein_prefilter: bool = False # Filter low-protein recipes in cost pass
    protein_filter_margin: float = 5.0     # Filter to >= (target - margin)%
    enable_protein_density_mult: bool = False  # Boost leftover value for protein-dense
    side_protein_value: float = 0.02       # $/gram bonus for side protein

    # === PRODUCE PARAMETERS ===
    enable_produce_bonus: bool = True      # Bonus for veggie/fruit sides
    produce_value: float = 0.002           # $/gram for produce bonus (fallback)
    # Per-meal produce bonus: None = use produce_value for all meals
    # Breakfast: grains/bread are fine, no veggie push
    # Lunch: light nudge toward vegetables
    # Dinner: strong nudge toward vegetables
    produce_value_breakfast: float = 0.000  # No produce bonus at breakfast
    produce_value_lunch: float = 0.003      # Light veggie preference at lunch
    produce_value_dinner: float = 0.010     # Strong veggie preference at dinner

    # === PANTRY PARAMETERS ===
    pantry_usage_value: float = 0.01       # $/gram discount for pantry use (5x boost from 0.002)
    package_remainder_choice_penalty_per_kg: float = 1.0  # Avoid upsizing packages for tiny savings
    enable_package_spoilage_risk_cost: bool = True  # Penalize risky short-life package leftovers
    package_spoilage_risk_value: float = 0.25       # Max fraction of leftover package value charged
    package_spoilage_risk_window_days: float = 21.0 # Items below this shelf life carry remainder risk
    freezable_package_spoilage_risk_multiplier: float = 1.0   # "Can freeze" still consumes freezer/planning capacity
    pantry_urgency_threshold: float = 75.0 # kg threshold before urgency kicks in
    pantry_urgency_scale: float = 50.0     # kg per 1x urgency multiplier
    pantry_urgency_max: float = 2.0        # Max urgency multiplier (1+max)

    # === HOLDING COST CONTROLLER (Pantry Stability) ===
    # The controller: penalize recipes that GROW pantry, proportional to current size
    # This is the key knob for pantry stability - replaces ad-hoc penalties
    enable_holding_cost: bool = True       # Enable the holding cost controller
    target_pantry_kg: float = 30.0         # Target pantry size (equilibrium point)
    holding_cost_rate: float = 2.0         # $/kg of inventory growth when at 2x target
    frozen_pantry_usage_value: float = 0.004  # Extra $/gram bonus for consuming frozen pantry stock

    # === PERISHABLE URGENCY SCORING ===
    # Prioritize using expiring pantry items before they spoil
    # Items closer to expiration get higher "urgency" bonuses in scoring
    enable_perishable_urgency: bool = True   # Enable urgency-based scoring
    perishable_urgency_value: float = 0.05   # $/gram urgency point (urgency = 1/TTL)
    enable_auto_freeze: bool = True          # Auto-freeze expiring items if freezable
    freezer_capacity_kg: float = 20.0        # Max freezer capacity for pantry items

    # === PRODUCE BONUS FOR MAINS ===
    # Give bonus for vegetables/fruits in main dishes (not just sides)
    enable_main_produce_bonus: bool = True   # Bonus for produce in mains
    main_produce_value: float = 0.005        # $/gram for produce in mains (higher than sides)

    # === PROTEIN DENSITY BONUS (Joint Scoring) ===
    # When enabled, adds protein density as a direct cost bonus instead of pre-filtering
    # Bidirectional: pulls toward target from both sides (not just rewarding above)
    enable_protein_density_bonus: bool = False  # Add protein % as cost component
    protein_density_value: float = 2.0          # $/serving bonus at 100% of target protein

    # === AUTO PROTEIN TARGETING ===
    # When protein_pct_target > 15 and this is True, automatically enables:
    #   - enable_protein_prefilter (if dynamic servings on)
    #   - enable_protein_density_bonus
    #   - macro_deviation_weight >= 0.15
    # User just sets protein_pct_target=25 and everything activates.
    auto_protein_targeting: bool = True

    # === PROTEIN BAND FILTER (Adaptive) ===
    # Controls the protein prefilter band widening behavior
    # When the initial band (target ± protein_filter_margin) has too few recipes,
    # widen by protein_band_widen_step up to protein_band_max_widen total
    protein_band_widen_step: float = 5.0    # pp to widen each iteration
    protein_band_max_widen: float = 15.0    # Max total widening from initial margin

    # === PENALTY PARAMETERS ===
    protein_cooldown_penalty: float = 5.0  # $/serving for recent protein source
    low_servings_penalty: float = 200.0    # $/serving for insufficient servings

    # === CALORIE PENALTY (controls calorie compliance) ===
    # Higher values = stricter calorie control, potentially higher cost
    # Lower values = looser calorie control, potentially lower cost
    # Default 0.001 results in ~110% calorie compliance
    # Try 0.005-0.01 for tighter control (closer to 100%)
    base_lambda_cal: float = 0.001         # Base calorie penalty multiplier (UNUSED - see shadow_lambda)

    # === SHADOW PRICE PARAMETERS (ACTUALLY CONTROLS CALORIES!) ===
    # Shadow prices dynamically adjust penalties based on how far behind targets you are
    # shadow_lambda_min: base penalty when on-track
    # shadow_lambda_max: max penalty when falling behind (INCREASE THIS TO TIGHTEN CALORIES)
    shadow_lambda_min: float = 0.001       # Base penalty ($/cal when on track)
    shadow_lambda_max: float = 0.05        # Max penalty ($/cal when behind) - shared calorie lambda
    shadow_cal_over_lambda_min: float = 0.001  # Base over-calorie penalty ($/cal)
    shadow_cal_over_lambda_max: float = 0.03   # Max over-calorie penalty when current pace runs high
    shadow_prot_lambda_max: float = 0.15   # Max protein penalty ($/g when behind) - separate, stronger
    shadow_gamma: float = 2.0              # Urgency curve shape (2.0 = quadratic)
    shadow_tau: float = 0.3                # Margin threshold (0.3 = relax if 30% ahead)

    # === PHASE 3: DAILY SHADOW PRICING ===
    # Separate daily penalty that doesn't collapse when weekly target is met
    # Key insight: divide by meals_left_today (1-3), not remaining_slots (1-21)
    # This keeps pressure on even when weekly looks fine but today is behind
    enable_daily_shadow_pricing: bool = True   # Enable Phase 3 daily penalties
    enable_separate_shadow_prices: bool = True # Alias for sparse_cascade.py compatibility
    enable_switcheroo: bool = True             # Post-process to swap meals for better daily balance
    daily_shadow_lambda_min: float = 5.0       # Base daily penalty (was 0.05 - 100x increase!)
    daily_shadow_lambda_max: float = 20.0     # Max daily penalty (was 2.0 - 10x increase!)
    daily_cal_normalizer: float = 600.0        # Cal/meal for normalizing urgency (600 = typical meal)
    meal_shadow_multiplier: float = 1.0        # DEPRECATED: now using fixed 1+meal_idx scaling (1/2/3)
    daily_cal_penalty_weight: float = 0.15     # Fallback weight when separate shadow disabled

    # === BAND FILTER (Pre-filter by calorie range) ===
    # When enabled, filters recipes to a cal/srv band based on calorie debt
    # Disabling allows testing if band filter causes cost differences
    enable_band_filter: bool = True           # Apply calorie band filter in cost_filter_candidates

    # === PROGRESSIVE OVERSHOOT PENALTY (Phase 3 fix for hs1_cal1400) ===
    # Problem: Phase 3 penalizes deviation from pace, NOT projected overshoot
    # A 500 cal recipe at 467 cal pace is "on target" → tiny penalty
    # But for hs1, 500 cal recipe at dinner pushes day to 130%+ → BAD
    # Solution: Add PROJECTED overshoot penalty that kicks in before hitting 100%
    enable_progressive_overshoot: bool = True   # Enable projected overshoot penalty
    progressive_overshoot_mult: float = 100.0   # Penalty multiplier (quadratic: 10% over → $1, 20% over → $4)
    progressive_overshoot_floor: float = 1.0    # Start penalizing at 100% of daily target (1.0 = at target)

    # === PROGRESSIVE UNDERSHOOT PENALTY (Fix for underfed days) ===
    # Problem: Overshoot penalty alone is ASYMMETRIC - avoids big recipes but allows small ones
    # Result: Days end at 57-70% of target because small recipes are "safe"
    # Solution: Penalize recipes that would leave the day underfed, especially at dinner
    enable_progressive_undershoot: bool = True  # Enable projected undershoot penalty
    progressive_undershoot_mult: float = 100.0  # Penalty multiplier (quadratic: 10% under → $1, 20% under → $4)
    progressive_undershoot_ceiling: float = 0.90  # Start penalizing below 90% of daily target

    # === COORDINATED SHADOW PRICING (Daily Balance via Day-of-Week Scaling) ===
    # Problem: Early week over-consumes leftovers, leaving late week starving (56% worst case)
    # Solution: Use shadow prices as soft incentives that coordinate across leftovers and fresh cooking
    #
    # Two shadow price mechanisms:
    # 1. Leftover ceiling - controls how much we can consume from existing food
    # 2. Fresh urgency - controls how strictly we cook to hit daily targets
    #
    # Direction options:
    # - 'ascending' = LOW→HIGH (Mon relaxed, Sun strict) - saves leftovers for late week
    # - 'descending' = HIGH→LOW (Mon strict, Sun relaxed) - use leftovers early
    #
    # These work TOGETHER through day-of-week scaling to pace consumption evenly
    enable_coordinated_shadow_pricing: bool = True  # Enable day-of-week shadow pricing

    # Shadow pricing mode:
    # - 'fixed' = use leftover_shadow_direction and fresh_shadow_direction as-is
    # - 'alternating' = flip directions every other week (criss-cross pattern)
    #   Week 0,2,4...: leftover=ascending, fresh=descending
    #   Week 1,3,5...: leftover=descending, fresh=ascending
    shadow_pricing_mode: str = 'fixed'  # 'fixed' or 'alternating'

    # Leftover consumption shadow pricing (ceiling multiplier)
    leftover_shadow_direction: str = 'ascending'  # 'ascending' or 'descending'
    leftover_shadow_min: float = 0.80   # Mon ceiling multiplier (80% of daily target)
    leftover_shadow_max: float = 1.20   # Sun ceiling multiplier (120% of daily target)

    # Fresh cooking shadow pricing (urgency multiplier for daily penalties)
    fresh_shadow_direction: str = 'ascending'  # 'ascending' or 'descending'
    fresh_shadow_min: float = 0.50      # Mon urgency multiplier (relaxed)
    fresh_shadow_max: float = 1.50      # Sun urgency multiplier (strict)

    # === MAX FEED DAYS (Daily Balance Control) ===
    # Limits how many days a single recipe should feed the household
    # At 70% leftover target, we want recipes to last ~3-4 days, not 7 days
    # 0 = auto-compute from leftover_pct_target (recommended)
    # 1-7 = manual override (1 = cook fresh every meal, 7 = one cook per week)
    max_feed_days: int = 0                     # 0 = auto from leftover_pct_target

    # === EXPLORATION/TIER QUOTAS (HestiaGO) ===
    # These parameters control recipe exploration and tier-based selection
    # Set exploration = None to disable all exploration features
    exploration: object = None                  # ExplorationConfig object or None
    enable_exploration_bonus: bool = False      # Enable exploration bonus without tier quotas
    exploration_min_ingredients: int = 3        # Min ingredients for exploration quality gates
    exploration_min_mass_g: float = 100.0       # Min total mass for exploration quality gates

    # === FOOD PLAN TIER INJECTION ===
    # Controls post-processing injection of premium proteins (beef, fish)
    # Tiers: thrifty (0), low_cost (2/wk), moderate (4/wk), liberal (7/wk)
    # tier_config: Optional TierConfig from tier_injection.py
    # None = thrifty (no injection)
    tier_config: object = None                  # TierConfig object or None

    # === SERVING EFFICIENCY PENALTY (Waste Reduction) ===
    # Penalizes recipes with excess servings relative to household size
    # This is the key mechanism for reducing single-person household waste
    # Family of 4: no penalty (4-serving recipe = perfect match)
    # Single person: $0.75 penalty for 4-serving recipe (gentle nudge toward smaller batches)
    # Value tuned to be ~5-10% of typical recipe cost ($8-15 per recipe)
    excess_serving_penalty: float = 0.25   # $ penalty multiplier per excess serving

    # === BONUS PARAMETERS ===
    template_match_bonus: float = 3.0      # $/match for side leftovers matching main template
    frozen_pressure_base: float = 2.0      # Base penalty when frozen items accumulate

    # === TOLERANCE PARAMETERS ===
    macro_tolerance_pct: float = 3.0       # Tolerance band for macro penalties
    macro_deviation_weight: float = 0.1    # Weight on macro deviations

    # === PROGRESSIVE PROTEIN QUOTA ===
    # Replaces cooldowns + tier injection with a single distribution-tracking mechanism.
    # At each slot, quadratic overuse penalties and linear underuse bonuses steer toward
    # the target distribution. None = no quota enforcement (pure cost optimization).
    # Order: [beef, pork, poultry, fish, eggs, legumes] — sums to 1.0
    protein_target_distribution: list = None  # Target protein source distribution
    protein_quota_strictness: float = 3.0     # Enforcement strength (higher = stricter)

    # === PROTEIN SPECIALIZATION (for HIGH_PROTEIN pantry control) ===
    # When enabled, REWARD using the same protein source for consecutive meals
    # This maximizes ingredient overlap and reduces pantry bloat
    enable_protein_specialization: bool = False  # Reward same protein source?
    protein_specialization_bonus: float = 3.0    # $/serving bonus for same protein

    # === PROTEIN DIVERSITY BOOST (for pre-filter) ===
    # When enabled, gives beef/pork/fish a cost discount in the pre-filter
    # This helps them compete with cheap eggs/legumes recipes
    # The boost is $/1000cal discount
    enable_protein_diversity_boost: bool = False   # Enable diversity boost in pre-filter?
    protein_diversity_boost: float = 0.5           # $/1000cal boost for pork
    beef_boost: float = 0.5                        # $/1000cal boost for beef (needs more than pork)
    fish_boost: float = 0.5                        # $/1000cal boost for fish
    # Target protein mix (for balanced mode) - not enforced, just a guide
    # Keys: beef, pork, poultry, fish, eggs, legumes
    protein_mix: dict = None  # Will be set by presets

    # === SECOND SIDE DISH ===
    # When enabled, adds a second side dish when calorie gap is detected
    # This helps fill calorie targets with cheap produce instead of expensive mains
    enable_second_side: bool = False             # Enable second side dish?
    side2_calorie_gap_threshold: float = 0.75    # Trigger when < 75% of slot calorie target
    side2_prefer_produce: bool = True            # Prefer vegetables/fruits for side2?

    # === SNACK CONTROL ===
    # When enabled, auto-inject fruit snacks to fill calorie gaps
    # In budget mode, disable to avoid extra costs
    enable_fruit_snacks: bool = False      # Auto-inject fruit snacks? (wired up but disabled for now)
    snack_inject_floor: float = 0.85       # Inject snacks when below this % of weekly target
    snack_inject_ceiling: float = 0.95     # Stop injecting when above this % (fills 85-95% gap)

    # === CALORIE COMPLIANCE BOUNDS ===
    # Controls the acceptable range for weekly calorie targets
    # Tighter bounds = stricter compliance but potentially higher cost
    calorie_floor_pct: float = 0.95        # Min weekly calories (95% of target)
    calorie_ceiling_pct: float = 1.05      # Max weekly calories (105% of target)
    cal_over_ceiling_mult: float = 2.0     # Penalty multiplier for exceeding ceiling (2x worse than under)

    # === TERMINAL CALORIE SELECTION ===
    # The beam keeps multiple viable weekly plans alive, then the planner picks
    # a final frontier. Cost-only final selection can choose a cheap underfed
    # frontier even when a calorie-compliant one survived the beam.
    enable_terminal_calorie_selection: bool = True
    terminal_calorie_floor_pct: float = 0.95
    terminal_calorie_target_pct: float = 1.00
    terminal_calorie_ceiling_pct: float = 1.05
    terminal_calorie_under_weight: float = 0.04  # $ penalty per calorie below target
    terminal_calorie_over_weight: float = 0.08   # $ penalty per calorie above target
    terminal_calorie_hard_floor: bool = True     # Prefer compliant frontiers when any exist
    terminal_calorie_hard_ceiling: bool = True   # Prefer 95-105% frontiers when any exist

    # === BEAM DEDUPE ===
    # Some transitions can make different parent/candidate pairs collapse into
    # the same visible weekly plan. Oversample children, then keep unique meal
    # signatures so K=50 means 50 distinct candidate plans when available.
    enable_beam_signature_dedupe: bool = True
    beam_signature_dedupe_oversample_mult: int = 4

    # === LEFTOVER CALORIE SUPPLEMENT ===
    # Leftover servings can cover headcount while still leaving the week underfed
    # when the leftover recipe is low-calorie. Allow a partial fresh cook in
    # those cases so shadow pricing has an actual calorie-producing action.
    enable_leftover_calorie_supplement: bool = True
    leftover_supplement_floor_pct: float = 0.95
    leftover_supplement_min_gap_cal: float = 150.0
    leftover_supplement_max_extra_servings: float = 1.0

    # === FRESH RECIPE DAILY CALORIE CAP ===
    # Hard cap on fresh recipes based on today's remaining calorie headroom
    # Prevents big batch recipes from causing daily overfeed
    # The cap scales with meal position (dinner=tighter)
    # Target 90-110% daily → 125% ceiling gives breathing room for cost optimization
    fresh_recipe_daily_ceiling_pct: float = 1.25   # 125% daily ceiling (breathing room)
    fresh_recipe_cap_penalty: float = 1000.0       # Penalty for recipes exceeding cap
    fresh_recipe_cap_enabled: bool = True          # Enable/disable the fresh recipe cap

    # === FROZEN ITEM THRESHOLDS ===
    # Controls when frozen pressure penalty kicks in and skip-cooking logic
    frozen_count_threshold: int = 3        # Trigger frozen pressure when avg frozen items > this
    frozen_skip_threshold_hs1: int = 2     # Skip cooking threshold for single person
    frozen_skip_threshold_hs2: int = 3     # Skip cooking threshold for couples
    frozen_skip_threshold_hs4: int = 4     # Skip cooking threshold for families (4+)

    # === STORE-BOUGHT PRODUCT CONTROL ===
    # Controls how many store-bought products (frozen dinners, etc.) can be
    # selected per week. Products compete directly with recipes in the beam search.
    # 0 = all home-cooked (products excluded from search)
    # 7 = up to 1 store-bought meal per day (default)
    # 21 = fully store-bought (no cooking)
    max_product_meals_per_week: int = 7    # Max store-bought meals per week (0-21)

    # === INFLAMMATION SCORING (Ember Score) ===
    # When enabled, adds a penalty for recipes with low Ember Scores
    # Shortfall below target is penalized as: weight * (target - score) / 100
    enable_inflammation_scoring: bool = False
    inflammation_weight: float = 0.0        # $/point below target
    inflammation_target: float = 70.0       # Target Ember score (B grade)

    # === AIP FILTER (Autoimmune Protocol) ===
    # When enabled, restricts candidate pool to AIP-compliant or swappable recipes.
    # Uses pre-built boolean masks from data/tensor_cache/aip_masks.pt.
    # Pools: native (13K), confident (89K), extended (146K), maximum (289K)
    # Cost premium over baseline: confident +$35/wk, extended +$53/wk (family of 4)
    enable_aip_filter: bool = False
    aip_pool: str = "confident"  # "native", "confident", "extended", "maximum"

    # === VARIETY/COOLDOWN CONTROL ===
    # Controls recipe repetition and variety enforcement
    variety_penalty: float = 10000.0       # Cost penalty for using recipe in cooldown ring
    recipe_cooldown_weeks: int = 6         # Weeks before recipe can repeat (COOLDOWN_LEN = weeks * 42)
    product_fndds_cooldown_penalty: float = 10000.0  # Penalty for same FNDDS 6-digit group (e.g., all mac & cheese)

    # === SCORING PENALTIES ===
    # Controls penalties for trivial/non-food recipes
    complexity_weight: float = 0.3         # Weight for ingredient count in scoring (num_ing * this)
    min_cal_per_serving: float = 100.0     # Min calories/serving to be considered food
    # HARD GATE: a main candidate must be capable of delivering at least this
    # fraction of the slot's calorie demand (slot_servings * target_cal_per_srv).
    # Set to 0.0 to disable. 0.5 means recipes that physically can't feed half
    # the slot are dropped from main candidates. Required to fix hh4/hh6 cal
    # compliance — saturated soft penalties lose to pantry cost discounts.
    min_main_total_cal_pct: float = 0.85
    max_cal_per_serving: float = 0.0       # Max calories/serving (0 = disabled). Use 400-500 for fresh mode
    min_ingredients: int = 2               # Min ingredients to avoid trivial recipes
    low_cal_penalty: float = 5000.0        # Heavy penalty for recipes < min_cal_per_serving
    high_cal_penalty: float = 5000.0       # Heavy penalty for recipes > max_cal_per_serving
    low_ing_penalty: float = 1000.0        # Penalty for recipes < min_ingredients

    # === SERVING MATCH REFINEMENT ===
    # Fine-tunes how serving size preferences work in different modes
    fresh_mode_excess_mult: float = 2.0    # Extra penalty multiplier for oversized recipes in fresh mode
    batch_bonus_strength_mult: float = 2.0 # Bonus multiplier for large batches (leftover_pct * this)
    hard_serving_cap_mult: float = 2.0     # Hard exclude recipes > max_acceptable * this (e.g., 100-srv starters)

    # === LEFTOVER MANAGEMENT ===
    # Controls when excess leftover penalty triggers
    leftover_excess_threshold_mult: float = 8.0  # Penalty triggers at slot_servings * this (was 3.0, too low for 75% leftover)

    # === TTL/URGENCY ===
    # Controls expiration-based urgency bonuses
    ttl_urgency_window: int = 7            # Days before expiry to trigger urgency bonus
    auto_freeze_ttl_threshold: int = 1     # Auto-freeze items when TTL <= this

    # (Protein source cooldown fields removed — replaced by progressive quota above)

    # ==========================================================================
    # DYNAMIC SERVINGS CONFIGURATION
    # ==========================================================================
    # Dynamic servings allows the planner to compute optimal serving counts
    # based on calorie targets per meal slot rather than fixed recipe servings.
    #
    # Formula for servings:
    #   target_cal = daily_cal_target * meal_split[meal] * slot_ratio
    #   servings = target_cal / recipe_cal_per_serving
    #   servings = clamp(servings, min_dynamic_servings, max_dynamic_servings)
    #
    # Example (2000 cal/day, lunch main):
    #   target_cal = 2000 * 0.40 * 0.70 = 560 cal
    #   recipe has 280 cal/serving -> servings = 2.0
    #
    # ==========================================================================

    # === ENABLE FLAG ===
    enable_dynamic_servings: bool = True  # ON by default — cheaper and better cal compliance

    # === DAILY CALORIE TARGET ===
    # Base daily calories per person (scales with household size)
    # This is typically passed from household config, but can be overridden
    daily_cal_target: float = 2000.0       # Baseline: 2000 cal/day/person

    # === MEAL CALORIE SPLIT ===
    # How daily calories are distributed across meals (must sum to 1.0)
    # Default: 30% breakfast, 40% lunch, 30% dinner
    meal_cal_split_breakfast: float = 0.30  # Breakfast gets 30% of daily cal
    meal_cal_split_lunch: float = 0.40      # Lunch gets 40% of daily cal
    meal_cal_split_dinner: float = 0.30     # Dinner gets 30% of daily cal

    # === MAIN/SIDE RATIO ===
    # Within each meal, how calories split between main and side
    # 0.70 = main dish gets 70%, side dish gets 30%
    main_side_ratio: float = 0.70          # Main gets 70% of meal calories

    # === SERVING CONSTRAINTS ===
    # Hard limits on computed servings to ensure practical batch sizes
    min_dynamic_servings: float = 1.0      # Can't have fractional servings
    max_dynamic_servings: float = 12.0     # Reasonable batch size cap

    # === ROUNDING BEHAVIOR ===
    # How to handle fractional servings after computation
    # 'round' = standard rounding (1.5 -> 2, 1.4 -> 1)
    # 'ceil'  = always round up (1.1 -> 2) - ensures calorie targets met
    # 'floor' = always round down (1.9 -> 1) - avoids excess leftovers
    dynamic_serving_rounding: str = 'round'

    # === TOLERANCE FOR SERVING ADJUSTMENT ===
    # Only adjust servings if it would change by more than this fraction
    # Prevents micro-adjustments that add complexity without benefit
    # 0.25 = only adjust if computed servings differ by >25% from recipe default
    dynamic_serving_tolerance: float = 0.25

    # === EXPLICIT CALORIE TARGETS PER SLOT (Optional Override) ===
    # If set to non-zero, these override the formula-based computation
    # Useful for specific dietary requirements (e.g., lighter breakfast)
    # Set to 0.0 to use formula-based computation (default)
    breakfast_main_cal_target: float = 0.0   # 0 = use formula (420 cal at 2000/day)
    breakfast_side_cal_target: float = 0.0   # 0 = use formula (180 cal at 2000/day)
    lunch_main_cal_target: float = 0.0       # 0 = use formula (560 cal at 2000/day)
    lunch_side_cal_target: float = 0.0       # 0 = use formula (240 cal at 2000/day)
    dinner_main_cal_target: float = 0.0      # 0 = use formula (420 cal at 2000/day)
    dinner_side_cal_target: float = 0.0      # 0 = use formula (180 cal at 2000/day)

    # === HOUSEHOLD SCALING ===
    # When True, multiply target calories by household_size for batch cooking
    # When False, compute servings per person (useful for portion control)
    scale_servings_by_household: bool = True

    # === LEFTOVER INTEGRATION ===
    # When dynamic servings enabled, integrate with leftover_pct_target
    # Higher leftover targets -> larger batches -> more servings
    # 0.0 = no integration (ignore leftover target)
    # 1.0 = full integration (multiply servings by 1/(1-leftover_pct))
    dynamic_leftover_multiplier: float = 1.0

    def get_slot_cal_target(self, meal: str, slot: str) -> float:
        """Compute calorie target for a specific meal slot.

        Args:
            meal: 'breakfast', 'lunch', or 'dinner'
            slot: 'main' or 'side'

        Returns:
            Target calories for that slot (per person)

        Example:
            config.get_slot_cal_target('lunch', 'main')  # -> 560 cal
        """
        # Check for explicit override first
        override_key = f"{meal}_{slot}_cal_target"
        override_val = getattr(self, override_key, 0.0)
        if override_val > 0:
            return override_val

        # Formula-based computation
        meal_splits = {
            'breakfast': self.meal_cal_split_breakfast,
            'lunch': self.meal_cal_split_lunch,
            'dinner': self.meal_cal_split_dinner,
        }
        meal_pct = meal_splits.get(meal, 0.33)

        slot_ratio = self.main_side_ratio if slot == 'main' else (1.0 - self.main_side_ratio)

        return self.daily_cal_target * meal_pct * slot_ratio

    def compute_dynamic_servings(
        self,
        cal_per_serving: float,
        meal: str,
        slot: str,
        household_size: int = 1,
    ) -> float:
        """Compute optimal serving count for a recipe.

        Args:
            cal_per_serving: Calories per serving of the recipe
            meal: 'breakfast', 'lunch', or 'dinner'
            slot: 'main' or 'side'
            household_size: Number of people in household

        Returns:
            Optimal serving count (clamped and rounded per config)

        Example:
            # 280 cal/srv recipe for lunch main, household of 4
            config.compute_dynamic_servings(280, 'lunch', 'main', 4)  # -> 8.0
        """
        if not self.enable_dynamic_servings or cal_per_serving <= 0:
            return 0.0  # Signal: use recipe default

        # Get per-person target
        target_cal = self.get_slot_cal_target(meal, slot)

        # Scale by household if enabled
        if self.scale_servings_by_household:
            target_cal *= household_size

        # Integrate with leftover target if enabled
        # Use side_leftover_pct_target for sides if set (>= 0)
        lo_pct = self.leftover_pct_target
        if slot == 'side' and self.side_leftover_pct_target >= 0:
            lo_pct = self.side_leftover_pct_target

        if self.dynamic_leftover_multiplier > 0 and lo_pct < 1.0 and lo_pct > 0:
            leftover_mult = 1.0 / (1.0 - lo_pct)
            leftover_mult = 1.0 + (leftover_mult - 1.0) * self.dynamic_leftover_multiplier
            target_cal *= leftover_mult

        # Compute raw servings
        servings = target_cal / cal_per_serving

        # Apply rounding
        if self.dynamic_serving_rounding == 'ceil':
            import math
            servings = math.ceil(servings)
        elif self.dynamic_serving_rounding == 'floor':
            import math
            servings = math.floor(servings)
        else:  # 'round'
            servings = round(servings)

        # Clamp to constraints
        servings = max(self.min_dynamic_servings, min(self.max_dynamic_servings, servings))

        return float(servings)

    @classmethod
    def budget(cls, protein_diversity: bool = False) -> 'ScoringConfig':
        """Budget mode: ~$55-66/week, maximum batch cooking (75% leftovers).

        Leftover strategy: 75% leftovers = maximum batch cooking

        Disables ALL cost-increasing features:
        - Produce bonus (disabled)
        - Protein pre-filter (disabled)
        - Protein density multiplier (disabled)
        - Protein source cooldown (disabled - allows unlimited eggs/legumes)
        - Fruit snack injection (disabled - no extra snack costs)
        - Macro deviation penalty (disabled - allows cheap high-carb recipes)

        Args:
            protein_diversity: If True, enables protein variety boost (+$2-4 for beef/pork/fish)
                             If False, sticks to cheapest proteins (eggs/legumes/poultry)
        """
        config = cls(
            mode=ScoringMode.BUDGET,
            leftover_value=1.50,
            leftover_credit_rate=0.70,
            leftover_target=0.5,
            leftover_meals_cap=4.0,           # 4 meals worth of leftovers (16 srv for fam4 = 75% target)
            side_leftover_value=1.00,         # Side leftover bonus
            # NEW: Leftover percentage control
            leftover_pct_target=0.75,         # 75% leftovers = max savings (batch cooking)
            serving_match_weight=0.30,        # Moderate weight - encourage batch cooking
            enable_serving_filter=True,
            serving_tolerance_mult=1.5,
            protein_pct_target=15.0,
            enable_protein_prefilter=False,
            enable_protein_density_mult=False,
            side_protein_value=0.0,          # No side protein bonus
            enable_produce_bonus=False,       # Disabled: steers toward expensive produce sides
            produce_value=0.0,
            pantry_usage_value=0.002,        # Original baseline value
            frozen_pantry_usage_value=0.006, # Stronger push to burn frozen pantry before 60d spoilage
            protein_cooldown_penalty=5.0,
            low_servings_penalty=200.0,
            macro_deviation_weight=0.1,       # Light macro deviation penalty
            enable_fruit_snacks=False,        # Disabled - no extra snack costs
            perishable_urgency_value=0.01,   # CRITICAL: Match old hardcoded value
            enable_perishable_urgency=False,
            enable_auto_freeze=True,  # Prevents spoilage = saves money
            enable_main_produce_bonus=False,
            enable_holding_cost=True,        # Prevent pantry bloat in long-horizon budget runs
            target_pantry_kg=40.0,           # Budget mode can carry pantry, but not indefinitely
            holding_cost_rate=2.0,
            # PROTEIN DIVERSITY: Now a parameter, not hardcoded
            enable_protein_diversity_boost=protein_diversity,
            protein_diversity_boost=2.0 if protein_diversity else 0.0,
            beef_boost=4.0 if protein_diversity else 0.0,
            fish_boost=4.0 if protein_diversity else 0.0,
            # SECOND SIDE: Disabled for budget mode (adds extra cost)
            enable_second_side=False,
        )
        # Progressive quota: achievable targets based on pool composition
        # Order: [beef, pork, poultry, fish, eggs, legumes]
        config.protein_target_distribution = None  # Disabled: let cost optimizer choose freely
        config.protein_quota_strictness = 3.0
        return config

    @classmethod
    def balanced(cls, protein_diversity: bool = False) -> 'ScoringConfig':
        """Moderate leftovers (50%) - cook every other meal.

        Leftover strategy: 50% leftovers = moderate batch cooking

        Args:
            protein_diversity: If True, enables protein variety boost (+$2-4 for beef/pork/fish)
                             If False, sticks to cheapest proteins (eggs/legumes/poultry)
        """
        config = cls(
            mode=ScoringMode.BALANCED,
            leftover_value=1.50,
            leftover_credit_rate=0.70,
            leftover_target=0.5,
            leftover_meals_cap=2.0,           # 2 meals worth of leftovers
            side_leftover_value=1.00,         # Side leftover bonus
            # LEFTOVER STRATEGY: 50% leftovers = cook every other meal
            leftover_pct_target=0.50,
            serving_match_weight=0.30,        # Moderate enforcement
            enable_serving_filter=True,
            serving_tolerance_mult=1.5,
            protein_pct_target=15.0,
            enable_protein_prefilter=False,
            enable_protein_density_mult=False,
            side_protein_value=0.02,
            enable_produce_bonus=True,
            produce_value=0.002,
            pantry_usage_value=0.002,
            protein_cooldown_penalty=5.0,
            low_servings_penalty=200.0,
            perishable_urgency_value=0.01,
            enable_perishable_urgency=False,
            enable_auto_freeze=True,
            enable_main_produce_bonus=False,
            # PROTEIN DIVERSITY: Now a parameter, not hardcoded
            enable_protein_diversity_boost=protein_diversity,
            protein_diversity_boost=2.0 if protein_diversity else 0.0,
            beef_boost=4.0 if protein_diversity else 0.0,
            fish_boost=4.0 if protein_diversity else 0.0,
            # SECOND SIDE: Fill calorie gaps
            enable_second_side=True,
            side2_calorie_gap_threshold=0.75,
            side2_prefer_produce=True,
        )
        return config

    @classmethod
    def high_protein(cls, target_pct: float = 35.0) -> 'ScoringConfig':
        """High protein mode with Joint Scoring (~$150-200/week).

        Uses protein density bonus instead of pre-filtering. This allows
        recipes with good pantry overlap to compete even if slightly lower protein.

        Args:
            target_pct: Protein target as % of calories (default 35%)
        """
        return cls(
            mode=ScoringMode.HIGH_PROTEIN,
            protein_pct_target=target_pct,
            leftover_value=2.00,              # Higher leftover value for bulk
            leftover_credit_rate=0.0,         # DISABLED - was adding to pantry
            leftover_target=0.5,
            leftover_meals_cap=3.0,           # 3 meals worth (more for bulk cooking)
            side_leftover_value=1.50,         # Higher side leftover bonus for bulk
            # NEW: Leftover percentage control
            leftover_pct_target=0.75,         # 75% leftovers = max batch cooking
            serving_match_weight=0.20,        # Moderate weight
            enable_serving_filter=True,
            serving_tolerance_mult=1.5,
            # HYBRID: Pre-filter to high-protein, then pantry bonus selects among them
            enable_protein_prefilter=True,    # Filter to high-protein recipes first
            protein_filter_margin=5.0,
            enable_protein_density_mult=True, # Boosts leftover value for protein
            enable_protein_density_bonus=True, # Protein % as cost component
            protein_density_value=1.0,        # $/serving bonus at 100% target (reduced from 3.0)
            side_protein_value=0.04,          # 2x side protein bonus
            enable_produce_bonus=True,
            produce_value=0.002,
            # PANTRY: Use holding cost controller instead of ad-hoc urgency
            pantry_usage_value=0.01,          # Boosted 5x from 0.002
            pantry_urgency_threshold=50.0,    # 50kg threshold (legacy, being replaced)
            pantry_urgency_scale=25.0,        # 25kg per 1x (legacy)
            pantry_urgency_max=4.0,           # 5x max (legacy)
            # HOLDING COST CONTROLLER: The key knob for pantry stability
            enable_holding_cost=True,
            target_pantry_kg=60.0,            # Target ~60kg pantry (acceptable for family of 4)
            holding_cost_rate=2.0,            # $/kg when at 2x target
            protein_cooldown_penalty=5.0,
            low_servings_penalty=200.0,
            enable_protein_specialization=True,  # Reward sticking with same protein
            protein_specialization_bonus=5.0,
        )

    @classmethod
    def fresh_daily(cls, protein_diversity: bool = False) -> 'ScoringConfig':
        """Fresh mode: minimal leftovers (10%) - cook fresh each meal (~$65-90/week).

        Leftover strategy: 10% leftovers = fresh-cooked meals daily

        For customers who prefer fresh-cooked meals over leftovers.
        Strongly penalizes recipes with excess servings.

        UPDATED (Jan 2026): Side2 bug fixed!
        - Bug: main_cal was per-serving, not total calories
        - Fix: Now uses new_nutrition which has correct total
        - Side2 only triggers when genuinely needed (+0% overfeed)
        - Strong serving match penalty helps control calories

        Note: This is more expensive because:
        - More cooking events = more ingredient purchases
        - Less economies of scale
        - Higher variety (more recipe changes)

        Args:
            protein_diversity: If True, enables protein variety boost (+$2-4 for beef/pork/fish)
                             If False, sticks to cheapest proteins (eggs/legumes/poultry)
        """
        return cls(
            mode=ScoringMode.BALANCED,
            leftover_value=0.50,              # Low leftover value
            leftover_credit_rate=0.70,
            leftover_target=0.0,              # No leftover preference
            leftover_meals_cap=1.0,           # Cap at 1 meal of leftovers
            side_leftover_value=0.25,         # Low side leftover bonus
            # NEW: Strong penalty for excess servings
            leftover_pct_target=0.10,         # Only 10% leftovers target
            serving_match_weight=1.00,        # STRONG penalty for wrong sizes
            enable_serving_filter=True,
            serving_tolerance_mult=1.2,       # Tight tolerance
            protein_pct_target=15.0,
            enable_protein_prefilter=False,
            enable_protein_density_mult=False,
            side_protein_value=0.02,
            enable_produce_bonus=True,
            produce_value=0.002,
            pantry_usage_value=0.002,
            protein_cooldown_penalty=5.0,
            low_servings_penalty=200.0,
            macro_deviation_weight=0.0,
            enable_fruit_snacks=False,       # Wired up but disabled for now
            snack_inject_floor=0.50,         # Broader coverage: inject when < 95%
            snack_inject_ceiling=0.95,       # Stop at 95%
            perishable_urgency_value=0.01,
            enable_perishable_urgency=True,   # Important: use perishables before they spoil
            enable_auto_freeze=True,
            enable_main_produce_bonus=True,
            # PROTEIN DIVERSITY: Now a parameter, not hardcoded
            enable_protein_diversity_boost=protein_diversity,
            protein_diversity_boost=2.0 if protein_diversity else 0.0,
            beef_boost=4.0 if protein_diversity else 0.0,
            fish_boost=4.0 if protein_diversity else 0.0,
            # Side2: Fill calorie gaps when main+side1 is insufficient
            # Threshold 0.75 = trigger when delivered < 75% of target
            enable_second_side=True,
            side2_calorie_gap_threshold=0.75,
            # CALORIE CONTROL: Relaxed from 100%/20x now that Side2 bug is fixed
            calorie_ceiling_pct=1.05,         # 105% ceiling
            cal_over_ceiling_mult=2.0,        # Moderate penalty
        )

    # =========================================================================
    # FOOD PLAN TIER PRESETS
    # =========================================================================
    # These presets implement USDA-style food plan tiers using injection-based
    # approach. Tier = number of premium protein (beef/fish) dinners per week.
    #
    # The tier presets work ORTHOGONALLY to protein_pct_target:
    # - protein_pct (15%, 25%, 35%) controls macro ratio via density bonus
    # - tier (thrifty, low_cost, moderate, liberal) controls protein QUALITY
    #
    # Example combinations:
    # - thrifty + 15% protein = baseline (~$53/wk, eggs/legumes dominant)
    # - low_cost + 25% protein = moderate cost (~$65/wk), some beef/fish
    # - liberal + 35% protein = premium (~$115/wk), high protein beef/fish
    # =========================================================================

    @classmethod
    def thrifty(cls, protein_pct: float = 15.0) -> 'ScoringConfig':
        """Thrifty tier: baseline optimizer with progressive protein quota.

        Uses quota to steer toward cheap protein sources (eggs/legumes dominant)
        while allowing some pork/poultry for variety.

        Cost target: ~$53-57/week at 15% protein
        Distribution: eggs=60%, pork=15%, poultry=10%, legumes=11%, beef/fish=2%

        Args:
            protein_pct: Target protein as % of calories (15-40)
        """
        from .tier_injection import TIER_PRESETS
        config = cls.budget()
        config.protein_pct_target = protein_pct
        config.tier_config = TIER_PRESETS['thrifty']
        # Quota OFF: let cost optimizer choose freely. Protein source steering
        # is handled by tier_config injection counts, not in-beam penalties.
        config.protein_target_distribution = None
        config.protein_quota_strictness = 0.0
        config.enable_produce_bonus = True
        config.produce_value_breakfast = 0.000
        config.produce_value_lunch = 0.002
        config.produce_value_dinner = 0.005
        return config

    @classmethod
    def low_cost(cls, protein_pct: float = 15.0) -> 'ScoringConfig':
        """Low-cost tier: adds chicken and pork variety.

        Optimizer picks cheapest meals, then tier_config injects
        2 chicken + 1 pork dinners per week for variety.

        Args:
            protein_pct: Target protein as % of calories (15-40)
        """
        from .tier_injection import TIER_PRESETS
        config = cls.budget()
        config.protein_pct_target = protein_pct
        config.tier_config = TIER_PRESETS['low_cost']
        config.protein_target_distribution = None  # Quota OFF
        config.protein_quota_strictness = 0.0
        config.enable_produce_bonus = True
        config.produce_value_breakfast = 0.000
        config.produce_value_lunch = 0.002
        config.produce_value_dinner = 0.005
        return config

    @classmethod
    def moderate(cls, protein_pct: float = 15.0) -> 'ScoringConfig':
        """Moderate tier: balanced protein variety.

        Optimizer picks cheapest meals, then tier_config injects
        2 chicken + 1 pork + 2 beef dinners per week.

        Args:
            protein_pct: Target protein as % of calories (15-40)
        """
        from .tier_injection import TIER_PRESETS
        config = cls.budget()
        config.protein_pct_target = protein_pct
        config.tier_config = TIER_PRESETS['moderate']
        config.protein_target_distribution = None  # Quota OFF
        config.protein_quota_strictness = 0.0
        config.enable_produce_bonus = True
        config.produce_value_breakfast = 0.000
        config.produce_value_lunch = 0.003
        config.produce_value_dinner = 0.006
        return config

    @classmethod
    def liberal(cls, protein_pct: float = 15.0) -> 'ScoringConfig':
        """Liberal tier: premium protein quality.

        Optimizer picks cheapest meals, then tier_config injects
        1 chicken + 1 pork + 2 beef + 2 fish dinners per week.

        Args:
            protein_pct: Target protein as % of calories (15-40)
        """
        from .tier_injection import TIER_PRESETS
        config = cls.budget()
        config.protein_pct_target = protein_pct
        config.tier_config = TIER_PRESETS['liberal']
        config.protein_target_distribution = None  # Quota OFF
        config.protein_quota_strictness = 0.0
        config.enable_produce_bonus = True
        config.produce_value_breakfast = 0.000
        config.produce_value_lunch = 0.003
        config.produce_value_dinner = 0.008
        return config

    @classmethod
    def anti_inflammatory(cls) -> 'ScoringConfig':
        """Anti-inflammatory mode: optimizes for low-inflammation meals.

        Based on balanced() with inflammation scoring enabled.
        Favors whole foods, omega-3-rich fish, vegetables, legumes.
        Cost: ~$75-90/week (slightly higher than balanced due to quality preference)
        """
        config = cls.balanced(protein_diversity=True)
        config.enable_inflammation_scoring = True
        config.inflammation_weight = 0.5
        config.inflammation_target = 70.0
        return config

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for JSON serialization."""
        return {
            'mode': self.mode.value,
            'leftover_value': self.leftover_value,
            'leftover_credit_rate': self.leftover_credit_rate,
            'leftover_target': self.leftover_target,
            'protein_pct_target': self.protein_pct_target,
            'enable_protein_prefilter': self.enable_protein_prefilter,
            'protein_filter_margin': self.protein_filter_margin,
            'enable_protein_density_mult': self.enable_protein_density_mult,
            'enable_protein_density_bonus': self.enable_protein_density_bonus,
            'protein_density_value': self.protein_density_value,
            'side_protein_value': self.side_protein_value,
            'enable_produce_bonus': self.enable_produce_bonus,
            'produce_value': self.produce_value,
            'pantry_usage_value': self.pantry_usage_value,
            'package_remainder_choice_penalty_per_kg': self.package_remainder_choice_penalty_per_kg,
            'enable_package_spoilage_risk_cost': self.enable_package_spoilage_risk_cost,
            'package_spoilage_risk_value': self.package_spoilage_risk_value,
            'package_spoilage_risk_window_days': self.package_spoilage_risk_window_days,
            'freezable_package_spoilage_risk_multiplier': self.freezable_package_spoilage_risk_multiplier,
            'pantry_urgency_threshold': self.pantry_urgency_threshold,
            'pantry_urgency_scale': self.pantry_urgency_scale,
            'pantry_urgency_max': self.pantry_urgency_max,
            'enable_holding_cost': self.enable_holding_cost,
            'target_pantry_kg': self.target_pantry_kg,
            'holding_cost_rate': self.holding_cost_rate,
            'enable_perishable_urgency': self.enable_perishable_urgency,
            'perishable_urgency_value': self.perishable_urgency_value,
            'enable_auto_freeze': self.enable_auto_freeze,
            'freezer_capacity_kg': self.freezer_capacity_kg,
            'enable_main_produce_bonus': self.enable_main_produce_bonus,
            'main_produce_value': self.main_produce_value,
            'protein_cooldown_penalty': self.protein_cooldown_penalty,
            'low_servings_penalty': self.low_servings_penalty,
            'template_match_bonus': self.template_match_bonus,
            'frozen_pressure_base': self.frozen_pressure_base,
            'macro_tolerance_pct': self.macro_tolerance_pct,
            'macro_deviation_weight': self.macro_deviation_weight,
            'protein_target_distribution': self.protein_target_distribution,
            'protein_quota_strictness': self.protein_quota_strictness,
            'enable_fruit_snacks': self.enable_fruit_snacks,
            'enable_dynamic_servings': self.enable_dynamic_servings,
            'daily_cal_target': self.daily_cal_target,
            'meal_cal_split_breakfast': self.meal_cal_split_breakfast,
            'meal_cal_split_lunch': self.meal_cal_split_lunch,
            'meal_cal_split_dinner': self.meal_cal_split_dinner,
            'main_side_ratio': self.main_side_ratio,
            'min_dynamic_servings': self.min_dynamic_servings,
            'max_dynamic_servings': self.max_dynamic_servings,
            'dynamic_serving_rounding': self.dynamic_serving_rounding,
            'dynamic_serving_tolerance': self.dynamic_serving_tolerance,
            'breakfast_main_cal_target': self.breakfast_main_cal_target,
            'breakfast_side_cal_target': self.breakfast_side_cal_target,
            'lunch_main_cal_target': self.lunch_main_cal_target,
            'lunch_side_cal_target': self.lunch_side_cal_target,
            'dinner_main_cal_target': self.dinner_main_cal_target,
            'dinner_side_cal_target': self.dinner_side_cal_target,
            'scale_servings_by_household': self.scale_servings_by_household,
            'dynamic_leftover_multiplier': self.dynamic_leftover_multiplier,
            # Tier config (serialized as tier_name string, not full object)
            'tier_name': self.tier_config.tier_name if self.tier_config else None,
        }

    def to_json(self) -> str:
        """Serialize config to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScoringConfig':
        """Create config from dictionary."""
        data = data.copy()
        if 'mode' in data:
            data['mode'] = ScoringMode(data['mode'])
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> 'ScoringConfig':
        """Deserialize config from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def describe(self) -> str:
        """Return a human-readable description of this config."""
        features = []
        if self.enable_produce_bonus:
            features.append(f"produce bonus (${self.produce_value}/g)")
        if self.enable_protein_prefilter:
            features.append(f"protein pre-filter (>={self.protein_pct_target - self.protein_filter_margin}%)")
        if self.enable_protein_density_mult:
            features.append("protein density multiplier")
        if self.side_protein_value > 0:
            features.append(f"side protein bonus (${self.side_protein_value}/g)")
        if self.protein_target_distribution is not None:
            features.append("protein quota")
        if self.enable_fruit_snacks:
            features.append("fruit snacks")
        if self.macro_deviation_weight > 0:
            features.append(f"macro penalty ({self.macro_deviation_weight})")
        if self.enable_holding_cost:
            features.append(f"holding cost (target={self.target_pantry_kg}kg)")
        if self.enable_dynamic_servings:
            features.append(f"dynamic servings ({int(self.daily_cal_target)} cal/day, {int(self.meal_cal_split_breakfast*100)}/{int(self.meal_cal_split_lunch*100)}/{int(self.meal_cal_split_dinner*100)} B/L/D)")

        if not features:
            features.append("minimal (budget mode)")

        return (
            f"ScoringConfig({self.mode.value}):\n"
            f"  Protein target: {self.protein_pct_target}%\n"
            f"  Leftover value: ${self.leftover_value}/srv\n"
            f"  Features: {', '.join(features)}"
        )


# Presets dictionary for easy access
# Note: Leftover strategy (budget/balanced/fresh) is separate from protein_diversity
# - budget: 75% leftovers, max batch cooking
# - balanced: 50% leftovers, cook every other meal
# - fresh_daily: 10% leftovers, fresh cooked meals
# - All default to protein_diversity=False (cheapest proteins: eggs/legumes/poultry)
# - Use .budget(protein_diversity=True) etc. to enable beef/pork/fish variety boosts
SCORING_PRESETS = {
    'budget': ScoringConfig.budget(),
    'balanced': ScoringConfig.balanced(),
    'fresh_daily': ScoringConfig.fresh_daily(),
    'high_protein': ScoringConfig.high_protein(35.0),
    'bodybuilder': ScoringConfig.high_protein(40.0),
    # With protein diversity enabled (more variety, higher cost)
    'budget_diverse': ScoringConfig.budget(protein_diversity=True),
    'balanced_diverse': ScoringConfig.balanced(protein_diversity=True),
    'fresh_diverse': ScoringConfig.fresh_daily(protein_diversity=True),
}

# Food plan tier presets (USDA-style tiers via injection)
# These are separate from SCORING_PRESETS to avoid import issues
# Use ScoringConfig.thrifty(), .low_cost(), .moderate(), .liberal() directly


def get_preset(name: str) -> ScoringConfig:
    """Get a scoring config preset by name.

    Args:
        name: Preset name ('budget', 'balanced', 'high_protein', 'bodybuilder')

    Returns:
        ScoringConfig instance

    Raises:
        ValueError: If preset name is not recognized
    """
    if name not in SCORING_PRESETS:
        available = ', '.join(SCORING_PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")
    return SCORING_PRESETS[name]
