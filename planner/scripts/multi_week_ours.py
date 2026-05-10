#!/usr/bin/env python3
"""Run N consecutive weeks through our concept-keyed planner, carrying
leftovers + pantry forward. Dumps per-week metrics for comparison.

Usage:
  python3 planner/scripts/multi_week_ours.py [--weeks 4]
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
from dataclasses import replace as dc_replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HESTIA_BASE_PATH"] = str(ROOT)

from htc_groups import protein_source as htc_protein_source
import torch
import hestia.sparse_cascade as sc
import hestia.data_structures as ds
from htc_groups import patch_perishability_index as _patch_pi
_patch_pi(ds)
from hestia.scoring_config import ScoringConfig
from hestia.data_structures import PersonProfile, HouseholdConfig, AttendanceSchedule
import hestia.plate_builder as pb
from protein_floor import daily_protein_floor_g
from mode_config import build_scoring_config

DATA = ROOT / "data"
CI = json.loads((DATA / "concept_index.json").read_text())
HINTS = json.loads((DATA / "priced_to_recipe_leaf.json").read_text()) if (DATA / "priced_to_recipe_leaf.json").exists() else {}
PACKAGE_OPTIONS_BY_CK: dict[str, list[dict]] = {}
VARIANT_TOKENS = {
    "strawberry", "mango", "peach", "cinnamon", "banana", "berry",
    "blueberry", "cherry", "raspberry", "assorted", "variety",
    "flavored", "flavour",
}
PROTEIN_SOURCE_NAMES = ["beef", "pork", "poultry", "fish", "eggs", "legumes"]

# Whole-cart cost calculator (real shopping math, not amortized)
sys.path.insert(0, str(ROOT.parent / "recipe_pricing"))
import aggregate_shopping_list as _agg

# Patches (same shape as run_htc_battery)
sc._classify_fndds_code = htc_protein_source

class CPI(ds.PackageIndex):
    def __init__(self, *a, **kw):
        self.packages_by_fndds = {}; self.package_db_path = DATA/"concept_index.json"
        self.package_db_is_override = True
        for ck, c in CI.items():
            hints = HINTS.get(ck, [])
            tmp = []
            for pkg in c["packages"]:
                if pkg["cents"] < 0 or pkg["grams"] <= 0: continue
                name = pkg["name"]
                name_l = name.lower()
                tmp.append({
                    "price": pkg["cents"] / 100.0,
                    "cents": int(pkg["cents"]),
                    "grams": float(pkg["grams"]),
                    "display": pkg.get("size_display") or f"{pkg['grams']:.0f}g",
                    "name": name,
                    "name_l": name_l,
                    "upc": pkg.get("upc", ""),
                    "brand": pkg.get("brand", ""),
                })
            tmp.sort(key=lambda p: (
                -sum(1 for h in hints if h in p["name_l"]),
                sum(1 for t in VARIANT_TOKENS if t in p["name_l"]),
                p["price"] / p["grams"],
            ))
            if tmp:
                PACKAGE_OPTIONS_BY_CK[ck] = tmp
                self.packages_by_fndds[ck] = [
                    (p["price"], p["grams"], p["display"]) for p in tmp
                ]
        self._gpu_tensors_built = False
        self._gpu_prices = self._gpu_sizes = self._gpu_option_prices = None

    def build_gpu_tensors(self, ingredient_index, device):
        missing = [ck for ck in ingredient_index.fpid_to_idx if ck not in self.packages_by_fndds]
        if missing:
            sample = "\n  ".join(sorted(missing)[:20])
            raise RuntimeError(
                "ConceptPackageIndex refuses to use PackageIndex fallback pricing. "
                f"{len(missing)} concepts have no real package data:\n  {sample}"
            )
        n = ingredient_index.num_ingredients
        opt = self.MAX_PACKAGE_OPTIONS
        prices = torch.zeros(n, dtype=torch.float32, device=device)
        sizes  = torch.ones(n,  dtype=torch.float32, device=device)
        op = torch.zeros((n, opt), dtype=torch.float32, device=device)
        os_ = torch.ones((n, opt), dtype=torch.float32, device=device)
        for idx in range(n):
            ck = ingredient_index.idx_to_fpid[idx]
            pkgs = self.packages_by_fndds.get(ck)
            fp, fs, _ = pkgs[0]
            prices[idx] = float(fp); sizes[idx] = float(fs)
            op[idx, :] = float(fp); os_[idx, :] = float(fs)
            seen = set(); selected = []
            for pkg in pkgs:
                rs = round(float(pkg[1]), 3)
                if rs in seen: continue
                seen.add(rs); selected.append(pkg)
                if len(selected) >= opt: break
            for j, (price, grams, _) in enumerate(selected):
                op[idx, j] = float(price); os_[idx, j] = float(grams)
        self._gpu_prices = prices; self._gpu_sizes = sizes
        self._gpu_option_prices = op; self._gpu_option_sizes = os_
        self._gpu_tensors_built = True
        print(f"ConceptPackageIndex GPU ready: {n} ingredients")
ds.PackageIndex = CPI
sc._tensor_cache_dir = lambda: DATA / "tensor_cache"

_OPB = pb.PlateBuilder
class _PB(_OPB):
    def __init__(self, *a, **kw):
        if "templates_dir" not in kw:
            kw["templates_dir"] = str(ROOT / "assets" / "plate_templates_v2")
        super().__init__(*a, **kw)
pb.PlateBuilder = _PB; sc.PlateBuilder = _PB


def _package_option_menu(concept_key: str, option_count: int) -> list[dict]:
    """Return the same distinct-size package menu exposed to the planner."""
    selected: list[dict] = []
    seen: set[float] = set()
    for pkg in PACKAGE_OPTIONS_BY_CK.get(concept_key, []):
        rounded_size = round(float(pkg["grams"]), 3)
        if rounded_size in seen:
            continue
        seen.add(rounded_size)
        selected.append(pkg)
        if len(selected) >= option_count:
            break
    return selected


def _match_selected_package(concept_key: str, package_count: float,
                            acquired_grams: float, cost: float,
                            option_count: int) -> dict:
    if package_count <= 0:
        return {}
    selected_size = acquired_grams / package_count
    selected_price = cost / package_count
    options = _package_option_menu(concept_key, option_count)
    for pkg in options:
        if abs(float(pkg["grams"]) - selected_size) <= 0.01 and \
           abs(float(pkg["price"]) - selected_price) <= 0.01:
            return {**pkg, "_selected_packages": [{
                "n_packages": round(package_count, 3),
                "name": pkg.get("name", ""),
                "upc": pkg.get("upc", ""),
                "grams": round(float(pkg.get("grams", 0) or 0), 1),
                "cents": pkg.get("cents", 0),
                "display": pkg.get("display", ""),
            }]}
    bundle = _infer_package_bundle(
        options, package_count, acquired_grams, cost)
    if bundle:
        label_parts = []
        for entry in bundle:
            name = entry.get("name", "")
            label_parts.append(f"{entry['n_packages']:g}x {name[:48]}")
        first = bundle[0]
        return {
            **first,
            "name": "Mixed: " + " + ".join(label_parts),
            "upc": "",
            "grams": acquired_grams / package_count if package_count else 0,
            "cents": round((cost / package_count) * 100) if package_count else 0,
            "display": "mixed package sizes",
            "_selected_packages": bundle,
        }
    return {}


def _infer_package_bundle(options: list[dict], package_count: float,
                          acquired_grams: float, cost: float) -> list[dict]:
    """Recover mixed package choices from aggregate tensor totals.

    The planner can buy different package sizes for the same concept across
    multiple recipes in one week. The result tensors only store aggregate
    count/grams/cost, so exact single-SKU matching fails. For audit JSON,
    solve the small integer package menu and emit the actual bundle.
    """
    n_total = int(round(package_count))
    if n_total <= 0 or abs(package_count - n_total) > 0.01:
        return []
    target_cents = int(round(cost * 100))
    target_grams = float(acquired_grams)
    grams_tol = max(0.2, target_grams * 0.0005)
    cents_tol = 2

    best_counts: list[int] | None = None
    best_err = float("inf")
    counts = [0] * len(options)

    def search(i: int, remaining: int, grams_sum: float, cents_sum: int) -> None:
        nonlocal best_counts, best_err
        if i == len(options) - 1:
            counts[i] = remaining
            g = grams_sum + remaining * float(options[i]["grams"])
            c = cents_sum + remaining * int(options[i]["cents"])
            g_err = abs(g - target_grams)
            c_err = abs(c - target_cents)
            if g_err <= grams_tol and c_err <= cents_tol:
                err = g_err + c_err
                if err < best_err:
                    best_err = err
                    best_counts = counts.copy()
            counts[i] = 0
            return
        for n in range(remaining + 1):
            counts[i] = n
            search(
                i + 1,
                remaining - n,
                grams_sum + n * float(options[i]["grams"]),
                cents_sum + n * int(options[i]["cents"]),
            )
        counts[i] = 0

    if options:
        search(0, n_total, 0.0, 0)
    if not best_counts:
        return []
    bundle = []
    for n, pkg in zip(best_counts, options):
        if n <= 0:
            continue
        bundle.append({
            "n_packages": n,
            "name": pkg.get("name", ""),
            "upc": pkg.get("upc", ""),
            "grams": round(float(pkg.get("grams", 0) or 0), 1),
            "cents": pkg.get("cents", 0),
            "display": pkg.get("display", ""),
        })
    return bundle


def _purchase_audit_rows(result: dict, idx_to_ck: list[str], option_count: int) -> list[dict]:
    costs = result.get("ingredient_purchase_costs")
    grams = result.get("ingredient_purchase_grams")
    packages = result.get("ingredient_purchases")
    if costs is None or grams is None or packages is None:
        return []
    costs_l = costs.detach().cpu().tolist() if hasattr(costs, "detach") else list(costs)
    grams_l = grams.detach().cpu().tolist() if hasattr(grams, "detach") else list(grams)
    packages_l = packages.detach().cpu().tolist() if hasattr(packages, "detach") else list(packages)
    rows = []
    for idx, (n_pkg, acquired_g, cost) in enumerate(zip(packages_l, grams_l, costs_l)):
        n_pkg = float(n_pkg); acquired_g = float(acquired_g); cost = float(cost)
        if n_pkg <= 0 and acquired_g <= 0 and cost <= 0:
            continue
        ck = idx_to_ck[idx]
        pkg = _match_selected_package(ck, n_pkg, acquired_g, cost, option_count)
        rows.append({
            "concept_key": ck,
            "n_packages": round(n_pkg, 3),
            "purchased_grams": round(acquired_g, 1),
            "cost": round(cost, 2),
            "selected_sku": pkg.get("name", ""),
            "selected_upc": pkg.get("upc", ""),
            "selected_package_grams": round(float(pkg.get("grams", 0) or 0), 1),
            "selected_package_cents": pkg.get("cents", 0),
            "selected_package_display": pkg.get("display", ""),
            "selected_packages": pkg.get("_selected_packages", []),
        })
    return rows


def _protein_source_distribution(counts) -> dict:
    if counts is None:
        return {"counts": {}, "pct": {}}
    try:
        raw = counts.tolist() if hasattr(counts, "tolist") else list(counts)
    except TypeError:
        return {"counts": {}, "pct": {}}
    values = [float(v or 0.0) for v in raw[:len(PROTEIN_SOURCE_NAMES)]]
    counts_out = {
        name: round(value, 3)
        for name, value in zip(PROTEIN_SOURCE_NAMES, values)
        if value > 0
    }
    total = sum(values)
    pct_out = {
        name: round(value / total * 100.0, 1)
        for name, value in zip(PROTEIN_SOURCE_NAMES, values)
        if total > 0 and value > 0
    }
    return {"counts": counts_out, "pct": pct_out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=4)
    ap.add_argument(
        "--mode",
        default="balanced",
        choices=("balanced", "thrifty", "low_cost", "moderate", "liberal", "high_protein", "budget"),
    )
    ap.add_argument("--cal",  type=float, default=2000.0,
                     help="Per-person daily calories")
    ap.add_argument("--people", type=int, default=1,
                     help="Number of people in the household")
    ap.add_argument("--protein-pct", type=float, default=20.0)
    ap.add_argument("--protein-floor-mode", choices=("pct", "flat50"), default="flat50",
                     help="Synthetic household protein floor policy")
    ap.add_argument("--leftover-pct", type=float, default=None,
                     help="Override scoring config leftover_pct_target (0.0–0.85)")
    ap.add_argument("--planner-leftover-target", type=float, default=None,
                     help="Audit switch: pass legacy leftover_target bonus multiplier to SparseCascadePlanner")
    ap.add_argument("--disable-produce-bonus", action="store_true",
                     help="Audit switch: zero produce side bonuses")
    ap.add_argument("--disable-auto-protein-targeting", action="store_true",
                     help="Audit switch: prevent automatic protein density/prefilter overrides")
    ap.add_argument("--out", default=str(DATA / "multi_week_ours.json"))
    args = ap.parse_args()

    device = torch.device("cpu")
    print(f"loading recipe DB…", flush=True)
    recipe_db = sc.SparseRecipeDatabase.from_cache(device)
    package_index = ds.PackageIndex()
    package_index.build_gpu_tensors(recipe_db.ingredient_index, device)

    # Match the production batch builder: mode selects the preset, protein_pct
    # remains an orthogonal macro target.
    config = build_scoring_config(
        ScoringConfig,
        dc_replace,
        mode=args.mode,
        protein_pct=float(args.protein_pct),
        daily_cal=float(args.cal),
        leftover_pct=args.leftover_pct,
    )
    audit_overrides = {}
    if args.disable_produce_bonus:
        audit_overrides.update({
            "enable_produce_bonus": False,
            "produce_value": 0.0,
            "produce_value_breakfast": 0.0,
            "produce_value_lunch": 0.0,
            "produce_value_dinner": 0.0,
            "enable_main_produce_bonus": False,
            "main_produce_value": 0.0,
        })
    if args.disable_auto_protein_targeting:
        audit_overrides["auto_protein_targeting"] = False
    if audit_overrides:
        config = dc_replace(config, **audit_overrides)

    # Keep the hard protein gram floor independent from the macro target. The
    # macro target is handled by ScoringConfig; profile protein floors are
    # baseline adequacy constraints and should not turn 35% into 175g/person.
    daily_protein_g = daily_protein_floor_g(
        calories_per_person=float(args.cal),
        protein_pct=float(args.protein_pct),
        floor_mode=args.protein_floor_mode,
    )
    people = [PersonProfile(f"P{i+1}", args.cal, daily_protein_g) for i in range(args.people)]
    schedule = AttendanceSchedule(HouseholdConfig(people=people))
    # Current API-style runs only set leftover_pct_target on the config. The
    # older tier sweep also passed the same value as the constructor's
    # leftover_target bonus multiplier; keep it as an explicit audit switch.
    planner_kwargs = {}
    if args.planner_leftover_target is not None:
        planner_kwargs["leftover_target"] = float(args.planner_leftover_target)
    planner = sc.SparseCascadePlanner(
        recipe_db=recipe_db, package_index=package_index, device=device,
        attendance_schedule=schedule, scoring_config=config,
        leftover_ttl=14, freezer_ttl=60, auto_freeze=True, K=50, verbose=False,
        **planner_kwargs)

    pantry = torch.zeros(planner.num_ingredients, device=device)
    leftovers = None
    banned_ids: list[int] = []
    session = planner.start_session(initial_pantry=pantry, initial_leftovers=leftovers,
                                     historical_banned_ids=banned_ids)

    weeks_out = []
    print(f"\nrunning {args.weeks} weeks ({args.mode}, {args.cal} cal, {args.protein_pct}% prot)…")
    # Build idx → concept_key map once (used to translate pantry tensor → dict).
    idx_to_ck = recipe_db.ingredient_index.idx_to_fpid
    for w in range(args.weeks):
        # Capture pantry-at-start-of-week BEFORE plan_next_week modifies it.
        # Force a real copy via .clone().tolist() — numpy views into the
        # underlying tensor become invalid when _advance() replaces _state.pantry.
        start_pantry = (session.pantry.detach().cpu().clone().tolist()
                        if session.pantry is not None else None)
        start_pantry_total = sum(start_pantry) if start_pantry is not None else 0.0
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
        n_frozen = 0; n_fresh = 0
        if final_lo is not None and final_lo.numel() > 0:
            for i in range(final_lo.shape[0]):
                rid = int(final_lo[i, 0].item())
                if rid <= 0: continue
                if bool(final_lo[i, 6].item() > 0): n_frozen += 1
                else: n_fresh += 1

        # Whole-cart real shopping cost: the planner already computed
        # per-ingredient purchase cost AFTER pantry subtraction. Just sum it.
        # This is what Hestia uses; no separate aggregate needed.
        ipc = result.get("ingredient_purchase_costs")
        ipg = result.get("ingredient_purchase_grams")
        ipp = result.get("ingredient_purchases")
        if ipc is not None:
            whole_cart_cost = float(ipc.sum().item())
            n_packages = int(ipp.sum().item()) if ipp is not None else 0
            pantry_start_g = float(start_pantry_total) if start_pantry is not None else 0.0
            final_pantry = result.get("final_pantry")
            pantry_end_g = float(final_pantry.sum().item()) if final_pantry is not None else 0.0
        else:
            whole_cart_cost = 0.0
            n_packages = 0
            pantry_start_g = 0.0
            pantry_end_g = 0.0
        purchase_rows = _purchase_audit_rows(
            result, idx_to_ck, package_index.MAX_PACKAGE_OPTIONS)

        wk = {
            "week": w+1, "elapsed_s": round(elapsed, 1),
            "cost": result.get("total_cost", 0.0),
            "whole_cart_cost": whole_cart_cost,
            "n_packages": n_packages,
            "pantry_start_grams": pantry_start_g,
            "pantry_end_grams": pantry_end_g,
            "pantry_delta_grams": pantry_end_g - pantry_start_g,
            # Deprecated alias kept for older audit scripts. This is pantry at
            # the start of the week, not grams consumed during the week.
            "pantry_grams_used": pantry_start_g,
            "cal_compliance":   result.get("cal_compliance"),
            "protein_pct":      result.get("protein_pct"),
            "veg_compliance":   result.get("veg_compliance"),
            "fruit_compliance": result.get("fruit_compliance"),
            "fat_pct":          result.get("fat_pct"),
            "carbs_pct":        result.get("carbs_pct"),
            "protein_source_distribution": _protein_source_distribution(
                result.get("protein_quota_counts")
            ),
            "n_recipes": len(ids),
            "recipe_ids": ids,
            "recipe_names": names,
            "ingredient_purchases": purchase_rows,
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
        print(f"  W{w+1:>2}: amortized ${wk['cost']:>6.2f}  whole-cart ${wk['whole_cart_cost']:>6.2f} "
              f"({wk['n_packages']} pkgs, pantry_start={pantry_start_g:.0f}g)  "
              f"prot={wk['protein_pct']:.1f}%  veg={wk['veg_compliance']:.2f}  "
              f"recipes={wk['n_recipes']}  carry f/F={n_fresh}/{n_frozen}  "
              f"waste={wk['leftover_stats']['waste']}sv  ({elapsed:.1f}s)")

        # Carry forward is automatic — session._advance() (called inside
        # plan_next_week) already pulls final_pantry, final_leftovers,
        # final_pantry_ttl, final_pantry_frozen from the result and stores
        # them on self._state. The previous version of this code was
        # OVERWRITING the auto-advanced pantry with zeros, which destroyed
        # any pantry-buildup from prior weeks and made every week's cost
        # look like a cold start.

    # Aggregate
    total_cost = sum(w["cost"] for w in weeks_out)
    total_whole_cart = sum(w.get("whole_cart_cost", 0.0) for w in weeks_out)
    avg_veg = sum(w["veg_compliance"] for w in weeks_out) / len(weeks_out)
    avg_protein = sum(w["protein_pct"] for w in weeks_out) / len(weeks_out)
    all_recipes = [r for w in weeks_out for r in w["recipe_ids"]]
    unique_across = len(set(all_recipes))
    repeats = len(all_recipes) - unique_across

    summary = {
        "config": {
            "mode": args.mode,
            "weeks": args.weeks,
            "people": args.people,
            "cal": args.cal,
            "protein_pct": args.protein_pct,
            "effective_protein_pct_target": config.protein_pct_target,
            "effective_scoring": {
                "protein_pct_target": planner.config.protein_pct_target,
                "enable_protein_prefilter": planner.config.enable_protein_prefilter,
                "protein_filter_margin": planner.config.protein_filter_margin,
                "enable_protein_density_bonus": planner.config.enable_protein_density_bonus,
                "protein_density_value": planner.config.protein_density_value,
                "macro_deviation_weight": planner.config.macro_deviation_weight,
                "auto_protein_targeting": planner.config.auto_protein_targeting,
                "enable_produce_bonus": planner.config.enable_produce_bonus,
                "produce_value_breakfast": planner.config.produce_value_breakfast,
                "produce_value_lunch": planner.config.produce_value_lunch,
                "produce_value_dinner": planner.config.produce_value_dinner,
            },
            "leftover_pct": args.leftover_pct,
            "planner_leftover_target": args.planner_leftover_target,
            "daily_protein_floor_g_per_person": daily_protein_g,
            "daily_protein_g": daily_protein_g,
            "protein_floor_mode": args.protein_floor_mode,
            "audit_switches": {
                "disable_produce_bonus": args.disable_produce_bonus,
                "disable_auto_protein_targeting": args.disable_auto_protein_targeting,
                "planner_leftover_target": args.planner_leftover_target,
            },
        },
        "totals": {
            "total_cost": round(total_cost, 2),
            "total_whole_cart_cost": round(total_whole_cart, 2),
            "avg_weekly_cost": round(total_cost/args.weeks, 2),
            "avg_whole_cart_cost": round(total_whole_cart/args.weeks, 2),
            "avg_veg_compliance": round(avg_veg, 3),
            "avg_protein_pct": round(avg_protein, 1),
            "total_unique_recipes": unique_across,
            "repeat_picks": repeats,
        },
        "weeks": weeks_out,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2))

    print(f"\n=== {args.weeks}-week summary ===")
    print(f"  total amortized cost:    ${total_cost:.2f}")
    print(f"  total whole-cart cost:   ${total_whole_cart:.2f}  (real shopping)")
    print(f"  avg/week amortized:      ${total_cost/args.weeks:.2f}")
    print(f"  avg/week whole-cart:     ${total_whole_cart/args.weeks:.2f}")
    print(f"  avg veg compliance:   {avg_veg:.2%}")
    print(f"  avg protein:          {avg_protein:.1f}%")
    print(f"  unique recipes:       {unique_across}")
    print(f"  repeat picks (cumul): {repeats}")
    print(f"  → {args.out}")


if __name__ == "__main__":
    main()
