"""Switcheroo Meal Repair - Redistributes meals to fix daily calorie variance.

Two repair strategies:
1. Day swaps: Move entire meals between days (same meal type)
2. Leftover substitution: Swap which leftover to eat at a slot (same template)

Key insight: If weekly calories are on target, swapping meals redistributes
without changing the total. Leftover substitution can also reduce waste.
"""
from typing import List, Dict, Tuple, Optional
import torch


def parse_selections(selections: List[tuple], recipe_db, servings_per_slot=None) -> List[Dict]:
    """Convert selection tuples to meal dicts with day/slot/calories info.

    Selection tuple format (from sparse_cascade.py):
    (main_id, side_id, side2_id, main_name, side_name, side2_name,
     meal_cost, main_store_alt, side_store_alt, side2_store_alt,
     main_is_leftover, side_is_leftover, side2_is_leftover)

    NOTE: main_id/side_id are recipe_nums, need recipe_db.recipe_id_to_idx mapping

    Args:
        selections: List of selection tuples from planner
        recipe_db: SparseRecipeDatabase for looking up calories
        servings_per_slot: Tensor of servings per slot (from planner)

    Returns:
        List of meal dicts with keys: slot, day, meal_type, recipe_idx,
        servings, is_leftover, calories
    """
    meals = []
    for slot_idx, sel in enumerate(selections):
        # Unpack the selection tuple
        main_id = sel[0]  # recipe_num
        side_id = sel[1]  # recipe_num
        side2_id = sel[2]  # recipe_num
        main_is_leftover = sel[10] if len(sel) > 10 else False
        side_is_leftover = sel[11] if len(sel) > 11 else False

        # Get servings for this slot
        if servings_per_slot is not None:
            slot_servings = servings_per_slot[slot_idx].item()
        else:
            slot_servings = 4.0  # Default

        # Calculate total calories for this meal
        total_cal = 0.0

        # Main dish calories - map recipe_num to db index
        if main_id > 0 and main_id in recipe_db.recipe_id_to_idx:
            db_idx = recipe_db.recipe_id_to_idx[main_id]
            cal_per_srv = recipe_db.nutrition[db_idx, 0].item()
            total_cal += cal_per_srv * slot_servings

        # Side dish calories
        if side_id > 0 and side_id in recipe_db.recipe_id_to_idx:
            db_idx = recipe_db.recipe_id_to_idx[side_id]
            cal_per_srv = recipe_db.nutrition[db_idx, 0].item()
            total_cal += cal_per_srv * slot_servings

        # Second side dish calories
        if side2_id > 0 and side2_id in recipe_db.recipe_id_to_idx:
            db_idx = recipe_db.recipe_id_to_idx[side2_id]
            cal_per_srv = recipe_db.nutrition[db_idx, 0].item()
            total_cal += cal_per_srv * slot_servings

        day = slot_idx // 3
        meal_type = slot_idx % 3  # 0=breakfast, 1=lunch, 2=dinner

        meals.append({
            'slot': slot_idx,
            'day': day,
            'meal_type': meal_type,
            'main_id': main_id,
            'side_id': side_id,
            'side2_id': side2_id,
            'recipe_idx': main_id,  # For backward compat
            'servings': slot_servings,
            'is_leftover': main_is_leftover,
            'side_is_leftover': side_is_leftover,
            'calories': total_cal,
        })

    return meals


def compute_daily_calories(meals: List[Dict], num_days: int = 7) -> List[float]:
    """Sum calories per day."""
    daily = [0.0] * num_days
    for m in meals:
        if m['day'] < num_days:
            daily[m['day']] += m['calories']
    return daily


def build_leftover_graph(meals: List[Dict]) -> Dict:
    """Track leftover dependencies.

    Returns: {recipe_idx: {'cooked_day': int, 'consumed': [(day, slot), ...]}}
    """
    graph = {}

    # First pass: find all fresh cooking
    for m in meals:
        if not m['is_leftover'] and m['recipe_idx'] >= 0:
            if m['recipe_idx'] not in graph:
                graph[m['recipe_idx']] = {'cooked_day': m['day'], 'consumed': []}
            else:
                # Multiple fresh cookings of same recipe - use earliest
                if m['day'] < graph[m['recipe_idx']]['cooked_day']:
                    graph[m['recipe_idx']]['cooked_day'] = m['day']

    # Second pass: find all leftover consumption
    for m in meals:
        if m['is_leftover'] and m['recipe_idx'] in graph:
            graph[m['recipe_idx']]['consumed'].append((m['day'], m['slot']))

    return graph


def check_swap_conflict(m1: Dict, m2: Dict, lo_graph: Dict) -> Tuple[bool, str]:
    """Check if swapping m1 and m2 would break leftover causality.

    Returns (has_conflict, reason).
    """
    # If both are fresh, no conflict
    if not m1['is_leftover'] and not m2['is_leftover']:
        return False, "both_fresh"

    # If either is a leftover, check causality
    r1, r2 = m1['recipe_idx'], m2['recipe_idx']
    d1, d2 = m1['day'], m2['day']

    # Swapping means m1 goes to d2, m2 goes to d1

    if m1['is_leftover']:
        # m1 is leftover, moving to d2
        if r1 in lo_graph:
            cooked = lo_graph[r1]['cooked_day']
            if d2 < cooked:
                return True, f"leftover would be eaten before cooking (day {d2} < cook day {cooked})"

    if m2['is_leftover']:
        # m2 is leftover, moving to d1
        if r2 in lo_graph:
            cooked = lo_graph[r2]['cooked_day']
            if d1 < cooked:
                return True, f"leftover would be eaten before cooking (day {d1} < cook day {cooked})"

    # Check if moving fresh cooking would strand leftovers
    if not m1['is_leftover'] and r1 in lo_graph:
        # m1 is fresh cooking moving to d2
        # All leftover consumers must still be >= d2
        for (consume_day, _) in lo_graph[r1]['consumed']:
            if consume_day < d2:
                return True, f"fresh cooking would move past its leftover consumer (day {consume_day})"

    if not m2['is_leftover'] and r2 in lo_graph:
        # m2 is fresh cooking moving to d1
        for (consume_day, _) in lo_graph[r2]['consumed']:
            if consume_day < d1:
                return True, f"fresh cooking would move past its leftover consumer (day {consume_day})"

    return False, "safe"


def dist_from_target(cal: float, daily_target: float, floor_pct: float = 0.90, ceiling_pct: float = 1.10) -> float:
    """Calculate penalty for being outside target range."""
    pct = cal / daily_target
    if pct < floor_pct:
        return (floor_pct - pct) * 100  # Penalty for being under floor
    elif pct > ceiling_pct:
        return (pct - ceiling_pct) * 100  # Penalty for being over ceiling
    return 0


def find_swap_candidates(meals: List[Dict], daily_cals: List[float],
                         daily_target: float, lo_graph: Dict,
                         floor_pct: float = 0.90, ceiling_pct: float = 1.10) -> List[Dict]:
    """Find all potential swaps sorted by improvement.

    Only considers swaps between same meal types (breakfast<->breakfast, etc).
    """
    candidates = []

    for i, m1 in enumerate(meals):
        for j, m2 in enumerate(meals):
            if i >= j:
                continue

            # Must be same meal type
            if m1['meal_type'] != m2['meal_type']:
                continue

            # Must be different days
            if m1['day'] == m2['day']:
                continue

            # Check for leftover conflicts
            has_conflict, reason = check_swap_conflict(m1, m2, lo_graph)

            # Calculate improvement
            d1, d2 = m1['day'], m2['day']
            cal1, cal2 = daily_cals[d1], daily_cals[d2]

            # After swap: m1's calories go to d2, m2's calories go to d1
            cal1_after = cal1 - m1['calories'] + m2['calories']
            cal2_after = cal2 - m2['calories'] + m1['calories']

            before_penalty = dist_from_target(cal1, daily_target, floor_pct, ceiling_pct) + \
                           dist_from_target(cal2, daily_target, floor_pct, ceiling_pct)
            after_penalty = dist_from_target(cal1_after, daily_target, floor_pct, ceiling_pct) + \
                          dist_from_target(cal2_after, daily_target, floor_pct, ceiling_pct)

            improvement = before_penalty - after_penalty

            if improvement > 0:  # Only consider beneficial swaps
                candidates.append({
                    'meal1_slot': m1['slot'],
                    'meal2_slot': m2['slot'],
                    'day1': d1,
                    'day2': d2,
                    'cal1_before': cal1,
                    'cal2_before': cal2,
                    'cal1_after': cal1_after,
                    'cal2_after': cal2_after,
                    'improvement': improvement,
                    'has_conflict': has_conflict,
                    'conflict_reason': reason,
                    'm1_calories': m1['calories'],
                    'm2_calories': m2['calories'],
                })

    # Sort by improvement (highest first)
    candidates.sort(key=lambda x: x['improvement'], reverse=True)
    return candidates


def apply_swap(meals: List[Dict], daily_cals: List[float], swap: Dict) -> Tuple[List[Dict], List[float]]:
    """Apply a swap and update daily calories."""
    s1, s2 = swap['meal1_slot'], swap['meal2_slot']

    # Swap the meals
    meals[s1], meals[s2] = meals[s2], meals[s1]

    # Fix the slot/day references
    meals[s1]['slot'] = s1
    meals[s1]['day'] = s1 // 3
    meals[s2]['slot'] = s2
    meals[s2]['day'] = s2 // 3

    # Update daily calories
    daily_cals[swap['day1']] = swap['cal1_after']
    daily_cals[swap['day2']] = swap['cal2_after']

    return meals, daily_cals


def repair_plan(result: Dict, daily_target: float,
                recipe_db=None, servings_per_slot=None,
                target_floor: float = 0.90, target_ceiling: float = 1.10,
                max_swaps: int = 10, verbose: bool = True) -> Dict:
    """Main entry point. Takes planner result, applies safe swaps, returns repaired result.

    Args:
        result: Planner result dict with 'selections' key
        daily_target: Target calories per day (family_size * cal_per_person)
        recipe_db: SparseRecipeDatabase for looking up calories
        servings_per_slot: Tensor of servings per slot (from planner.servings_per_slot)
        target_floor: Minimum acceptable daily % (default 0.90 = 90%)
        target_ceiling: Maximum acceptable daily % (default 1.10 = 110%)
        max_swaps: Maximum number of swaps to attempt
        verbose: Print progress

    Returns:
        Modified result dict with repaired meal plan
    """
    if 'selections' not in result:
        if verbose:
            print("No selections in result, skipping repair")
        return result

    # Parse selections into meal list
    meals = parse_selections(result['selections'], recipe_db, servings_per_slot)

    # Compute initial daily calories
    daily_cals = compute_daily_calories(meals)

    # Build leftover dependency graph
    lo_graph = build_leftover_graph(meals)

    if verbose:
        print(f"\nSwitcheroo Repair")
        print(f"  Target: {daily_target:.0f} cal/day ({target_floor*100:.0f}%-{target_ceiling*100:.0f}%)")
        print(f"  Before: ", end="")
        for d, cal in enumerate(daily_cals):
            pct = cal / daily_target * 100
            print(f"D{d}:{pct:.0f}% ", end="")
        print()

    swaps_applied = []

    for iteration in range(max_swaps):
        # Find all swap candidates
        candidates = find_swap_candidates(meals, daily_cals, daily_target, lo_graph,
                                         target_floor, target_ceiling)

        # Filter to safe swaps only
        safe_swaps = [c for c in candidates if not c['has_conflict']]

        if not safe_swaps:
            if verbose:
                print(f"  No safe swaps available")
            break

        # Take best safe swap
        best = safe_swaps[0]

        if best['improvement'] < 1:
            if verbose:
                print(f"  Best improvement too small ({best['improvement']:.1f})")
                # Show why we can't improve more
                print(f"  Remaining problem days:")
                for d, cal in enumerate(daily_cals):
                    pct = cal / daily_target * 100
                    if pct < target_floor * 100 or pct > target_ceiling * 100:
                        print(f"    Day {d}: {pct:.1f}%")
                # Show blocked swaps
                all_candidates = find_swap_candidates(meals, daily_cals, daily_target, lo_graph,
                                                     target_floor, target_ceiling)
                conflicts = [c for c in all_candidates if c['has_conflict']]
                if conflicts:
                    print(f"  Blocked by leftover conflicts: {len(conflicts)} swaps")
                    for c in conflicts[:3]:
                        print(f"    D{c['day1']}<->D{c['day2']}: {c['conflict_reason']}")
            break

        # Apply it
        meals, daily_cals = apply_swap(meals, daily_cals, best)
        swaps_applied.append(best)

        if verbose:
            meal_names = ['breakfast', 'lunch', 'dinner']
            slot1, slot2 = best['meal1_slot'], best['meal2_slot']
            meal_type = meal_names[slot1 % 3]
            print(f"  Swap {iteration+1}: D{best['day1']}<->D{best['day2']} ({meal_type}) "
                  f"({best['cal1_before']:.0f}->{best['cal1_after']:.0f}, "
                  f"{best['cal2_before']:.0f}->{best['cal2_after']:.0f}) "
                  f"improvement={best['improvement']:.1f}")

    if verbose:
        print(f"  After:  ", end="")
        for d, cal in enumerate(daily_cals):
            pct = cal / daily_target * 100
            print(f"D{d}:{pct:.0f}% ", end="")
        print()
        print(f"  Applied {len(swaps_applied)} swaps")

    # Update result
    result['daily_calories_repaired'] = daily_cals
    result['repair_swaps_applied'] = len(swaps_applied)
    result['repair_swaps'] = swaps_applied

    # Count days in range
    days_ok_before = sum(1 for cal in compute_daily_calories(parse_selections(result['selections'], recipe_db, servings_per_slot))
                        if target_floor <= cal/daily_target <= target_ceiling)
    days_ok_after = sum(1 for cal in daily_cals
                       if target_floor <= cal/daily_target <= target_ceiling)
    result['days_in_range_before'] = days_ok_before
    result['days_in_range_after'] = days_ok_after

    return result


def find_leftover_substitutions(
    selections: List[tuple],
    final_leftovers: torch.Tensor,
    recipe_db,
    servings_per_slot: torch.Tensor,
    daily_target: float,
    daily_cals: List[float],
    target_floor: float = 0.90,
    target_ceiling: float = 1.10,
) -> List[Dict]:
    """Find opportunities to substitute remaining leftovers into meals.

    Looks at leftovers remaining at end of week (which might waste next week)
    and checks if any meal could have used them instead of what was selected.

    Constraints:
    - Same meal_type (breakfast/lunch/dinner)
    - Improves or maintains calorie balance

    Args:
        selections: Original meal selections
        final_leftovers: [L, 9] tensor of remaining leftovers
        recipe_db: For looking up recipe info
        servings_per_slot: Servings per slot
        daily_target: Target calories per day
        daily_cals: Current daily calorie totals
        target_floor/ceiling: Acceptable range

    Returns:
        List of substitution opportunities
    """
    # Leftover fields: [recipe_id, servings, ttl, cal, prot, meal_type, is_frozen, dish_type, template_id]
    substitutions = []

    # Find active leftovers (servings > 0)
    active_mask = final_leftovers[:, 1] > 0
    if not active_mask.any():
        return substitutions

    active_indices = active_mask.nonzero().squeeze(-1)
    if active_indices.dim() == 0:
        active_indices = active_indices.unsqueeze(0)

    for lo_idx in active_indices:
        lo = final_leftovers[lo_idx]
        lo_recipe_id = int(lo[0].item())
        lo_servings = lo[1].item()
        lo_ttl = int(lo[2].item())
        lo_cal_per_srv = lo[3].item()
        lo_meal_type = int(lo[5].item())  # 0=breakfast, 1=lunch, 2=dinner
        lo_dish_type = int(lo[7].item())  # 0=main, 1=side
        lo_template_id = int(lo[8].item())

        # Look for meals that could use this leftover
        for slot_idx, sel in enumerate(selections):
            meal_type = slot_idx % 3
            day = slot_idx // 3

            # Must match meal type
            if meal_type != lo_meal_type:
                continue

            # Check if this slot used a fresh meal (not leftover)
            main_is_leftover = sel[10] if len(sel) > 10 else False
            side_is_leftover = sel[11] if len(sel) > 11 else False

            # Get the recipe that was used
            if lo_dish_type == 0:  # main dish
                if main_is_leftover:
                    continue  # Already using leftover
                used_recipe_id = sel[0]
            else:  # side dish
                if side_is_leftover:
                    continue
                used_recipe_id = sel[1]

            if used_recipe_id <= 0:
                continue

            # Calculate calorie difference
            slot_servings = servings_per_slot[slot_idx].item()

            if used_recipe_id in recipe_db.recipe_id_to_idx:
                db_idx = recipe_db.recipe_id_to_idx[used_recipe_id]
                used_cal_per_srv = recipe_db.nutrition[db_idx, 0].item()
            else:
                continue

            used_cal = used_cal_per_srv * slot_servings
            lo_cal = lo_cal_per_srv * min(slot_servings, lo_servings)
            cal_diff = lo_cal - used_cal

            # Would this improve the day's calories?
            current_pct = daily_cals[day] / daily_target
            new_pct = (daily_cals[day] + cal_diff) / daily_target

            # Calculate improvement
            def dist_from_target(pct):
                if pct < target_floor:
                    return target_floor - pct
                elif pct > target_ceiling:
                    return pct - target_ceiling
                return 0

            before_dist = dist_from_target(current_pct)
            after_dist = dist_from_target(new_pct)
            improvement = before_dist - after_dist

            if improvement > 0:
                substitutions.append({
                    'slot': slot_idx,
                    'day': day,
                    'meal_type': ['breakfast', 'lunch', 'dinner'][meal_type],
                    'dish_type': 'main' if lo_dish_type == 0 else 'side',
                    'old_recipe_id': used_recipe_id,
                    'new_recipe_id': lo_recipe_id,
                    'old_cal': used_cal,
                    'new_cal': lo_cal,
                    'cal_diff': cal_diff,
                    'improvement': improvement * 100,
                    'lo_servings_available': lo_servings,
                    'lo_ttl': lo_ttl,
                })

    # Sort by improvement
    substitutions.sort(key=lambda x: x['improvement'], reverse=True)
    return substitutions


def repair_with_leftover_substitution(
    result: Dict,
    daily_target: float,
    recipe_db,
    servings_per_slot: torch.Tensor,
    target_floor: float = 0.90,
    target_ceiling: float = 1.10,
    verbose: bool = True,
) -> Dict:
    """Second repair pass: substitute remaining leftovers into meals.

    This can help reduce future waste by using leftovers that would otherwise
    carry over and potentially expire.
    """
    if 'final_leftovers' not in result:
        return result

    final_leftovers = result['final_leftovers']
    selections = result['selections']

    # Get current daily calories (use repaired if available)
    if 'daily_calories_repaired' in result:
        daily_cals = result['daily_calories_repaired']
    else:
        meals = parse_selections(selections, recipe_db, servings_per_slot)
        daily_cals = compute_daily_calories(meals)

    # Find substitution opportunities
    subs = find_leftover_substitutions(
        selections=selections,
        final_leftovers=final_leftovers,
        recipe_db=recipe_db,
        servings_per_slot=servings_per_slot,
        daily_target=daily_target,
        daily_cals=daily_cals,
        target_floor=target_floor,
        target_ceiling=target_ceiling,
    )

    if verbose:
        print(f"\nLeftover Substitution Analysis:")
        active_lo = (final_leftovers[:, 1] > 0).sum().item()
        print(f"  Remaining leftovers: {active_lo:.0f}")
        print(f"  Substitution opportunities: {len(subs)}")
        for s in subs[:5]:
            print(f"    D{s['day']} {s['meal_type']} {s['dish_type']}: "
                  f"{s['old_cal']:.0f} -> {s['new_cal']:.0f} cal "
                  f"(+{s['improvement']:.1f}% improvement, ttl={s['lo_ttl']})")

    result['leftover_substitutions'] = subs
    result['leftover_sub_count'] = len(subs)

    return result
