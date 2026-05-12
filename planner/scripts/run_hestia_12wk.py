#!/usr/bin/env python3
"""Run Hestia's planner DIRECTLY (no overrides) for 12 weeks, 4 people,
thrifty, 2000 cal each, 75% leftovers. Compare to ours.

Uses Hestia's PackageIndex (FNDDS-keyed pooled prices), not our concept_index.
"""
import argparse, sys, os, json, time
sys.path.insert(0, '/Users/jamiebarton/Desktop/Hestia/api')
os.environ.setdefault('HESTIA_BASE_PATH', '/Users/jamiebarton/Desktop/Hestia/api')

import torch
from dataclasses import replace as dc_replace
from hestia.sparse_cascade import SparseRecipeDatabase, SparseCascadePlanner
from hestia.scoring_config import ScoringConfig
from hestia.data_structures import PackageIndex, PersonProfile, HouseholdConfig, AttendanceSchedule


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="planner/data/multi_week_hestia_12wk_config_matched.json")
    args = ap.parse_args()

    weeks = 12
    people = 4
    cal_per = 2000.0
    leftover_pct = 0.75

    device = torch.device('cpu')
    print(f"Loading Hestia recipe DB…")
    recipe_db = SparseRecipeDatabase.from_cache(device)
    print(f"  {recipe_db.num_recipes:,} recipes")

    pkg = PackageIndex()
    pkg.build_gpu_tensors(recipe_db.ingredient_index, device)

    # Match user's 15%-protein run config
    config = ScoringConfig.thrifty(protein_pct=15.0)
    config.daily_cal_target = float(cal_per)
    config = dc_replace(config, leftover_pct_target=leftover_pct)
    # Match Hestia's tier sweep semantics for synthetic households.
    daily_protein = cal_per * 0.15 / 4.0
    print(f"  thrifty, {cal_per} cal/person × {people} people, leftover_pct={leftover_pct}")

    persons = [PersonProfile(f"P{i+1}", cal_per, daily_protein) for i in range(people)]
    schedule = AttendanceSchedule(HouseholdConfig(people=persons))

    planner = SparseCascadePlanner(
        recipe_db=recipe_db, package_index=pkg, device=device,
        attendance_schedule=schedule, scoring_config=config,
        leftover_ttl=14, freezer_ttl=60, auto_freeze=True, K=50, verbose=False,
    )
    session = planner.start_session(
        initial_pantry=torch.zeros(planner.num_ingredients, device=device),
        initial_leftovers=None, historical_banned_ids=[],
    )

    total_cost = 0.0
    total_purchase = 0.0
    weeks_out = []
    union_recipe_ids = set()
    print(f"\n{'Wk':>3} {'total_cost':>10} {'purchase_sum':>12} {'pantry':>7} {'recipes':>7}")
    print("-" * 50)
    for w in range(weeks):
        t0 = time.time()
        result = session.plan_next_week()
        elapsed = time.time() - t0

        cost = float(result.get("total_cost", 0.0) or 0.0)
        ipc = result.get("ingredient_purchase_costs")
        purchase = float(ipc.sum().item()) if ipc is not None else 0.0
        used = result.get("used_recipe_ids", [])
        try: ids = [int(x) for x in (used.tolist() if hasattr(used,'tolist') else list(used)) if x]
        except: ids = []
        pantry_g = float(session.pantry.sum().item()) if session.pantry is not None else 0.0

        total_cost += cost
        total_purchase += purchase
        union_recipe_ids.update(ids)
        # Leftover stats
        ls = result.get("leftover_stats", {}) or {}
        consumed = ls.get("consumed_servings", 0) or 0
        waste = ls.get("waste_servings", 0) or 0
        fresh = ls.get("fresh_count", 0) or 0
        frozen = ls.get("frozen_count", 0) or 0
        print(f"{w+1:>3} ${cost:>8.2f}  pantry={pantry_g:>5.0f}g  rec={len(set(ids)):>3}  "
              f"fresh={fresh:>2}  frozen={frozen:>2}  consumed={consumed:>5.1f}sv  "
              f"waste={waste:>5.1f}sv  ({elapsed:.1f}s)")
        weeks_out.append({
            "week": w + 1,
            "elapsed_s": round(elapsed, 1),
            "cost": cost,
            "whole_cart_cost": purchase,
            "pantry_grams": pantry_g,
            "recipe_ids": ids,
            "n_recipes": len(set(ids)),
            "leftover_stats": {
                "fresh_count": fresh,
                "frozen_count": frozen,
                "consumed": consumed,
                "waste": waste,
            },
        })

    print("-" * 50)
    print(f"\n=== Hestia 12-week, 4 people, thrifty, 2000cal, 75% leftover ===")
    print(f"  total_cost (planner reports):       ${total_cost:.2f}")
    print(f"  ingredient_purchase_costs sum:      ${total_purchase:.2f}")
    print(f"  avg/week (planner total_cost):      ${total_cost/weeks:.2f}")
    print(f"  avg/week (purchase costs):          ${total_purchase/weeks:.2f}")
    print(f"  per-person/week:                    ${total_cost/weeks/people:.2f}")

    out = {
        "config": {
            "mode": "thrifty",
            "weeks": weeks,
            "people": people,
            "cal": cal_per,
            "protein_pct": 15.0,
            "daily_protein_g": daily_protein,
            "leftover_pct": leftover_pct,
        },
        "weeks": weeks_out,
        "summary": {
            "total_cost": total_cost,
            "total_purchase_cost": total_purchase,
            "avg_week_cost": total_cost / weeks,
            "avg_week_purchase_cost": total_purchase / weeks,
            "unique_recipes": len(union_recipe_ids),
            "repeat_picks": sum(len(w["recipe_ids"]) for w in weeks_out) - len(union_recipe_ids),
        },
        "union_recipe_ids": sorted(union_recipe_ids),
    }
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  → {out_path}")


if __name__ == "__main__":
    main()
