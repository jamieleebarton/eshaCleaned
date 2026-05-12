#!/usr/bin/env python3
"""Run the SparseCascadePlanner for a single week and print the meal plan
output. Sanity check that the tensors + planner work end-to-end."""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from dataclasses import replace as dc_replace

from concept_adapter import apply_concept_runtime

apply_concept_runtime()

from hestia.sparse_cascade import SparseRecipeDatabase, SparseCascadePlanner
from hestia.scoring_config import ScoringConfig
import hestia.data_structures as ds
from hestia.data_structures import PersonProfile, HouseholdConfig, AttendanceSchedule


def main():
    device = torch.device(
        "cuda" if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available()
        else "cpu"
    )
    print(f"device: {device}")

    print("loading recipe db from cache...")
    recipe_db = SparseRecipeDatabase.from_cache(device)
    print(f"  {recipe_db.num_recipes:,} recipes")

    # Use names from the recipe DB itself
    recipe_names = {}
    if hasattr(recipe_db, "names") and recipe_db.names:
        for i, n in enumerate(recipe_db.names):
            rid = int(recipe_db.recipe_ids[i].item())
            recipe_names[str(rid)] = n

    package_index = ds.PackageIndex()
    package_index.build_gpu_tensors(recipe_db.ingredient_index, device)

    config = ScoringConfig.thrifty()
    config = dc_replace(config, daily_cal_target=2000.0, protein_pct_target=15.0)

    people = [PersonProfile("Jamie", 2000.0, 75.0)]
    household = HouseholdConfig(people=people)
    schedule = AttendanceSchedule(household)

    planner = SparseCascadePlanner(
        recipe_db=recipe_db,
        package_index=package_index,
        device=device,
        attendance_schedule=schedule,
        scoring_config=config,
        leftover_ttl=14,
        freezer_ttl=60,
        auto_freeze=True,
        K=50,
        verbose=False,
    )

    pantry = torch.zeros(planner.num_ingredients, device=device)
    session = planner.start_session(
        initial_pantry=pantry,
        initial_leftovers=None,
        historical_banned_ids=[],
    )

    print("\nplanning week 1 ...")
    t0 = time.time()
    result = session.plan_next_week()
    elapsed = time.time() - t0
    print(f"  done in {elapsed:.1f}s")

    cost = result.get("total_cost", 0.0)
    print(f"\n=== WEEK 1 PLAN ===")
    print(f"total cost: ${cost:.2f}")
    print(f"keys in result: {list(result.keys())}")

    plan = result.get("plan") or result.get("schedule") or {}
    if plan:
        print(f"\nplan: {json.dumps(plan, default=str, indent=2)[:2000]}")

    # Try to dump the recipes/meals chosen
    if "meals" in result:
        print(f"\nmeals chosen ({len(result['meals'])}):")
        for m in result["meals"][:30]:
            print(f"  {m}")

    # Inspect the leftovers tensor
    final_lo = result.get("final_leftovers")
    if final_lo is not None:
        print(f"\nleftovers tensor shape: {final_lo.shape}")
        n = 0
        for i in range(final_lo.shape[0]):
            rid = int(final_lo[i, 0].item())
            if rid <= 0:
                continue
            sv = final_lo[i, 1].item()
            name = recipe_names.get(str(rid), f"Recipe {rid}")
            print(f"  recipe {rid:<8}  servings={sv:.1f}  {name}")
            n += 1
            if n >= 20:
                break

    # Tracking stats
    lo_stats = result.get("leftover_stats", {})
    if lo_stats:
        print(f"\nleftover_stats: {lo_stats}")


if __name__ == "__main__":
    main()
