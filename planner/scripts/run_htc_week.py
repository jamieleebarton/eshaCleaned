import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from htc_groups import protein_source as htc_protein_source
#!/usr/bin/env python3
"""Run a 1-week meal plan against our HTC-native tensor cache."""
import json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HESTIA_BASE_PATH"] = str(ROOT)

import torch

import hestia.sparse_cascade as sc
import hestia.data_structures as ds
from htc_groups import patch_perishability_index as _patch_pi
_patch_pi(ds)
from hestia.scoring_config import ScoringConfig
from hestia.data_structures import PersonProfile, HouseholdConfig, AttendanceSchedule
from dataclasses import replace as dc_replace

DATA = ROOT / "data"
CI = json.loads((DATA / "concept_index.json").read_text())

CONCEPT_PROTEIN = {}
def _classify_concept(c: str) -> int:
    return CONCEPT_PROTEIN.get(c, -1)
sc._classify_fndds_code = htc_protein_source


class ConceptPackageIndex(ds.PackageIndex):
    def __init__(self, packages_csv=None, packages_db=None):
        self.packages_by_fndds = {}
        self.package_db_path = DATA / "concept_index.json"
        self.package_db_is_override = True
        for ck, c in CI.items():
            for pkg in c["packages"]:
                if pkg["cents"] <= 0 or pkg["grams"] <= 0: continue
                self.packages_by_fndds.setdefault(ck, []).append(
                    (pkg["cents"]/100.0, float(pkg["grams"]),
                     pkg.get("size_display") or f'{pkg["grams"]:.0f}g'))
        for ck in self.packages_by_fndds:
            self.packages_by_fndds[ck].sort(key=lambda x: x[0]/x[1])
        n = sum(len(v) for v in self.packages_by_fndds.values())
        print(f"ConceptPackageIndex: {len(self.packages_by_fndds):,} concepts, {n:,} packages")
        self._gpu_tensors_built = False
        self._gpu_prices = None; self._gpu_sizes = None; self._gpu_option_prices = None

    def build_gpu_tensors(self, ingredient_index, device):
        missing = [
            concept_key
            for concept_key in ingredient_index.fpid_to_idx
            if concept_key not in self.packages_by_fndds
        ]
        if missing:
            sample = "\n  ".join(sorted(missing)[:20])
            raise RuntimeError(
                "ConceptPackageIndex refuses to use PackageIndex fallback pricing. "
                f"{len(missing):,} concept keys have no real package data:\n  {sample}"
            )

        option_count = self.MAX_PACKAGE_OPTIONS
        num_ingredients = ingredient_index.num_ingredients
        prices = torch.zeros(num_ingredients, dtype=torch.float32, device=device)
        sizes = torch.ones(num_ingredients, dtype=torch.float32, device=device)
        option_prices = torch.zeros((num_ingredients, option_count), dtype=torch.float32, device=device)
        option_sizes = torch.ones((num_ingredients, option_count), dtype=torch.float32, device=device)
        for idx in range(num_ingredients):
            concept_key = ingredient_index.idx_to_fpid[idx]
            packages = self.packages_by_fndds[concept_key]
            first_price, first_size, _first_display = packages[0]
            prices[idx] = float(first_price)
            sizes[idx] = float(first_size)
            option_prices[idx, :] = float(first_price)
            option_sizes[idx, :] = float(first_size)
            seen_sizes: set[float] = set()
            selected: list[tuple[float, float, str]] = []
            for package in packages:
                price, grams, display = package
                rounded_size = round(float(grams), 3)
                if rounded_size in seen_sizes:
                    continue
                seen_sizes.add(rounded_size)
                selected.append(package)
                if len(selected) >= option_count:
                    break
            for opt_idx, (price, grams, _display) in enumerate(selected):
                option_prices[idx, opt_idx] = float(price)
                option_sizes[idx, opt_idx] = float(grams)
        self._gpu_prices = prices
        self._gpu_sizes = sizes
        self._gpu_option_prices = option_prices
        self._gpu_option_sizes = option_sizes
        self._gpu_tensors_built = True
        print(
            f"ConceptPackageIndex: Built GPU tensors for {num_ingredients:,} "
            "ingredients using real package data only"
        )
ds.PackageIndex = ConceptPackageIndex

# Tell sparse_cascade where to find our cache
def _our_cache_dir(): return DATA / "tensor_cache"
sc._tensor_cache_dir = _our_cache_dir

# Tell PlateBuilder where templates live
import hestia.plate_builder as pb
_OrigPlateBuilder = pb.PlateBuilder
class HTCPlateBuilder(_OrigPlateBuilder):
    def __init__(self, *a, **kw):
        if "templates_dir" not in kw:
            kw["templates_dir"] = str(ROOT / "assets" / "plate_templates_v2")
        super().__init__(*a, **kw)
pb.PlateBuilder = HTCPlateBuilder
sc.PlateBuilder = HTCPlateBuilder


def main():
    device = torch.device(
        "cuda" if torch.cuda.is_available() else
        "mps" if torch.backends.mps.is_available() else "cpu"
    )
    print(f"device: {device}")

    print("loading recipe db from HTC cache…")
    recipe_db = sc.SparseRecipeDatabase.from_cache(device)
    print(f"  {recipe_db.num_recipes:,} recipes")

    package_index = ds.PackageIndex()
    package_index.build_gpu_tensors(recipe_db.ingredient_index, device)

    config = ScoringConfig.balanced(protein_diversity=True)
    config = dc_replace(config, daily_cal_target=2000.0, protein_pct_target=20.0)

    people = [PersonProfile("Jamie", 2000.0, 75.0)]
    household = HouseholdConfig(people=people)
    schedule = AttendanceSchedule(household)

    planner = sc.SparseCascadePlanner(
        recipe_db=recipe_db,
        package_index=package_index,
        device=device,
        attendance_schedule=schedule,
        scoring_config=config,
        leftover_ttl=14, freezer_ttl=60, auto_freeze=True, K=50, verbose=False,
    )

    pantry = torch.zeros(planner.num_ingredients, device=device)
    session = planner.start_session(initial_pantry=pantry,
                                      initial_leftovers=None,
                                      historical_banned_ids=[])

    print("\nplanning week 1 …")
    t0 = time.time()
    result = session.plan_next_week()
    elapsed = time.time() - t0
    print(f"  done in {elapsed:.1f}s")

    cost = result.get("total_cost", 0.0)
    print(f"\n=== WEEK 1 PLAN ===")
    print(f"total cost: ${cost:.2f}")

    # Macro compliance
    print(f"\nDaily nutrition (avg per day):")
    print(f"  cal compliance:      {result.get('cal_compliance')}")
    print(f"  protein pct: {result.get('protein_pct'):.1f}% (target {config.protein_pct_target}%)")
    print(f"  carbs pct:   {result.get('carbs_pct'):.1f}%")
    print(f"  fat pct:     {result.get('fat_pct'):.1f}%")
    print(f"  veg compliance:      {result.get('veg_compliance')}")
    print(f"  fruit compliance:    {result.get('fruit_compliance')}")

    # Recipe selections
    sel = result.get("selections")
    if sel is not None:
        # selections is typically [num_meals, ...] tensor
        try:
            print(f"\nselections shape: {sel.shape if hasattr(sel,'shape') else 'list'}")
        except: pass

    # Recipe IDs used
    used_ids = result.get("used_recipe_ids", [])
    if used_ids is not None:
        try:
            ids_list = used_ids.tolist() if hasattr(used_ids, 'tolist') else list(used_ids)
        except:
            ids_list = []
        ids_list = [i for i in ids_list if i]
        print(f"\nused recipe IDs: {len(ids_list)} total")
        for rid in ids_list[:21]:  # show first 21 (3 meals × 7 days)
            name = recipe_db.get_recipe_name(recipe_db.gpu_recipe_id_to_idx[rid].item()) if rid in recipe_db.gpu_recipe_id_to_idx else f"r{rid}"
            print(f"  {rid:<8} {name}")

    # Inspect final leftovers
    final_lo = result.get("final_leftovers")
    if final_lo is not None and final_lo.numel() > 0:
        print(f"\nleftover tensor shape: {tuple(final_lo.shape)}")

    lo_stats = result.get("leftover_stats", {})
    if lo_stats:
        print(f"\nleftover_stats: {lo_stats}")


if __name__ == "__main__":
    main()
