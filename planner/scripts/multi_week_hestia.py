#!/usr/bin/env python3
"""Run N consecutive weeks through HESTIA's vanilla planner with the same
config we use for ours, carrying leftovers forward. Dumps per-week metrics
in the same JSON format as multi_week_ours.py for easy diffing.
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
from dataclasses import replace as dc_replace

HESTIA = Path("/Users/jamiebarton/Desktop/Hestia/api")
BUNDLE_PLANNER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HESTIA))
sys.path.insert(1, str(BUNDLE_PLANNER))

import torch
import hestia.sparse_cascade as sc
from hestia.scoring_config import ScoringConfig
from hestia.data_structures import (
    PackageIndex, PersonProfile, HouseholdConfig, AttendanceSchedule,
)
from mode_config import build_scoring_config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=4)
    ap.add_argument(
        "--mode",
        default="balanced",
        choices=("balanced", "thrifty", "low_cost", "moderate", "liberal", "high_protein", "budget"),
    )
    ap.add_argument("--cal",  type=float, default=2000.0)
    ap.add_argument("--people", type=int, default=1)
    ap.add_argument("--protein-pct", type=float, default=20.0)
    ap.add_argument("--leftover-pct", type=float, default=None)
    ap.add_argument("--out", default="/Users/jamiebarton/Desktop/esha_audit_bundle/planner/data/multi_week_hestia.json")
    args = ap.parse_args()
    out_path = Path(args.out).expanduser().resolve()
    os.chdir(str(HESTIA))

    device = torch.device("cpu")
    print(f"loading Hestia recipe DB…", flush=True)
    recipe_db = sc.SparseRecipeDatabase.from_cache(device)
    package_index = PackageIndex()
    package_index.build_gpu_tensors(recipe_db.ingredient_index, device)

    config = build_scoring_config(
        ScoringConfig,
        dc_replace,
        mode=args.mode,
        protein_pct=float(args.protein_pct),
        daily_cal=float(args.cal),
        leftover_pct=args.leftover_pct,
    )

    daily_protein_g = float(args.cal) * (float(args.protein_pct) / 100.0) / 4.0
    people = [PersonProfile(f"P{i+1}", args.cal, daily_protein_g) for i in range(args.people)]
    schedule = AttendanceSchedule(HouseholdConfig(people=people))
    planner = sc.SparseCascadePlanner(
        recipe_db=recipe_db, package_index=package_index, device=device,
        attendance_schedule=schedule, scoring_config=config,
        leftover_ttl=14, freezer_ttl=60, auto_freeze=True, K=50, verbose=False)

    pantry = torch.zeros(planner.num_ingredients, device=device)
    leftovers = None
    session = planner.start_session(initial_pantry=pantry, initial_leftovers=leftovers,
                                     historical_banned_ids=[])

    weeks_out = []
    print(f"\nrunning {args.weeks} weeks ({args.mode}, {args.cal} cal)…")
    for w in range(args.weeks):
        t0 = time.time()
        result = session.plan_next_week()
        elapsed = time.time() - t0

        used = result.get("used_recipe_ids", [])
        try: ids = [int(x) for x in (used.tolist() if hasattr(used,'tolist') else list(used)) if x]
        except: ids = []
        ids = list(dict.fromkeys(ids))
        names = []
        for rid in ids[:25]:
            try:
                idx = int(recipe_db.gpu_recipe_id_to_idx[rid].item())
                names.append(recipe_db.get_recipe_name(idx))
            except: names.append(f"r{rid}")

        lo_stats = result.get("leftover_stats", {}) or {}
        final_lo = result.get("final_leftovers")
        n_frozen = n_fresh = 0
        if final_lo is not None and final_lo.numel() > 0:
            for i in range(final_lo.shape[0]):
                rid = int(final_lo[i, 0].item())
                if rid <= 0: continue
                if bool(final_lo[i, 6].item() > 0): n_frozen += 1
                else: n_fresh += 1

        wk = {
            "week": w+1, "elapsed_s": round(elapsed, 1),
            "cost": result.get("total_cost", 0.0),
            "cal_compliance":   result.get("cal_compliance"),
            "protein_pct":      result.get("protein_pct"),
            "veg_compliance":   result.get("veg_compliance"),
            "fruit_compliance": result.get("fruit_compliance"),
            "fat_pct":          result.get("fat_pct"),
            "carbs_pct":        result.get("carbs_pct"),
            "n_recipes": len(ids),
            "recipe_ids": ids,
            "recipe_names": names,
            "leftover_stats": {
                "fresh_count":      lo_stats.get("fresh_count", 0),
                "frozen_count":     lo_stats.get("frozen_count", 0),
                "fresh_servings":   round(float(lo_stats.get("fresh_servings", 0) or 0), 1),
                "frozen_servings":  round(float(lo_stats.get("frozen_servings", 0) or 0), 1),
                "consumed":         round(float(lo_stats.get("consumed_servings", 0) or 0), 1),
                "waste":            round(float(lo_stats.get("waste_servings", 0) or 0), 1),
                "carryover_fresh":  n_fresh,
                "carryover_frozen": n_frozen,
            },
        }
        weeks_out.append(wk)
        print(f"  W{w+1:>2}: ${wk['cost']:>6.2f}  prot={wk['protein_pct']:.1f}%  "
              f"veg={wk['veg_compliance']:.2f}  fruit={wk['fruit_compliance']:.2f}  "
              f"recipes={wk['n_recipes']}  carry frozen/fresh={n_frozen}/{n_fresh}  "
              f"waste={wk['leftover_stats']['waste']}sv  ({elapsed:.1f}s)")

        # Session advances pantry/leftovers/cooldown internally. Do not zero
        # pantry here; that turns every Hestia week into a cold start.

    total_cost = sum(w["cost"] for w in weeks_out)
    avg_veg = sum(w["veg_compliance"] for w in weeks_out) / len(weeks_out)
    avg_protein = sum(w["protein_pct"] for w in weeks_out) / len(weeks_out)
    all_recipes = [r for w in weeks_out for r in w["recipe_ids"]]

    summary = {
        "config": {
            "mode": args.mode,
            "weeks": args.weeks,
            "people": args.people,
            "cal": args.cal,
            "protein_pct": args.protein_pct,
            "leftover_pct": args.leftover_pct,
            "daily_protein_g": daily_protein_g,
        },
        "totals": {
            "total_cost": round(total_cost, 2),
            "avg_weekly_cost": round(total_cost/args.weeks, 2),
            "avg_veg_compliance": round(avg_veg, 3),
            "avg_protein_pct": round(avg_protein, 1),
            "total_unique_recipes": len(set(all_recipes)),
            "repeat_picks": len(all_recipes) - len(set(all_recipes)),
        },
        "weeks": weeks_out,
    }
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n=== Hestia {args.weeks}-week summary ===")
    print(f"  total cost: ${total_cost:.2f}  avg/week ${total_cost/args.weeks:.2f}")
    print(f"  avg veg {avg_veg:.2%}  avg prot {avg_protein:.1f}%")
    print(f"  → {out_path}")


if __name__ == "__main__":
    main()
