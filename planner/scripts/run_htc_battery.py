import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from htc_groups import protein_source as htc_protein_source
#!/usr/bin/env python3
"""Run multiple planner configurations through our HTC tensor cache.

Configs:
  - thrifty 1 person 2000 cal
  - balanced 1 person 2000 cal
  - high_protein 1 person 2200 cal (35% protein)
  - budget 1 person 1800 cal
  - balanced 2 people 4000 cal
  - balanced 4 people (family) 7000 cal
  - balanced 1 person 1500 cal (cut)
  - balanced 1 person 2500 cal (bulk)

Reports cost, macros, veg/fruit compliance, recipe diversity.
"""
import json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HESTIA_BASE_PATH"] = str(ROOT)

import torch
from dataclasses import replace as dc_replace

import hestia.sparse_cascade as sc
import hestia.data_structures as ds
from htc_groups import patch_perishability_index as _patch_pi
_patch_pi(ds)
from hestia.scoring_config import ScoringConfig
from hestia.data_structures import PersonProfile, HouseholdConfig, AttendanceSchedule

DATA = ROOT / "data"
CI = json.loads((DATA / "concept_index.json").read_text())


CONCEPT_PROTEIN = {}
def _classify_concept(c): return CONCEPT_PROTEIN.get(c, -1)
sc._classify_fndds_code = htc_protein_source


class ConceptPackageIndex(ds.PackageIndex):
    def __init__(self, *a, **kw):
        self.packages_by_fndds = {}; self.package_db_path = DATA/"concept_index.json"
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

def _our_cache_dir(): return DATA / "tensor_cache"
sc._tensor_cache_dir = _our_cache_dir

import hestia.plate_builder as pb
_O = pb.PlateBuilder
class HTCPB(_O):
    def __init__(self, *a, **kw):
        if "templates_dir" not in kw:
            kw["templates_dir"] = str(ROOT / "assets" / "plate_templates_v2")
        super().__init__(*a, **kw)
pb.PlateBuilder = HTCPB
sc.PlateBuilder = HTCPB


def run(config_name: str, config, people: list, cal_target_total: float, verbose=False):
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    recipe_db = sc.SparseRecipeDatabase.from_cache(device)
    package_index = ds.PackageIndex()
    package_index.build_gpu_tensors(recipe_db.ingredient_index, device)

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
    session = planner.start_session(initial_pantry=pantry, initial_leftovers=None,
                                     historical_banned_ids=[])
    t0 = time.time()
    result = session.plan_next_week()
    elapsed = time.time() - t0

    used = result.get("used_recipe_ids", [])
    try:
        ids = [int(x) for x in (used.tolist() if hasattr(used,'tolist') else list(used)) if x]
    except: ids = []
    rid_idx = recipe_db.gpu_recipe_id_to_idx
    names = []
    for rid in ids[:20]:
        try:
            idx = int(rid_idx[rid].item())
            names.append(recipe_db.get_recipe_name(idx))
        except: names.append(f"r{rid}")

    return {
        "name": config_name,
        "cost": result.get("total_cost", 0.0),
        "elapsed": elapsed,
        "cal_compliance": result.get("cal_compliance"),
        "protein_pct": result.get("protein_pct"),
        "carbs_pct": result.get("carbs_pct"),
        "fat_pct": result.get("fat_pct"),
        "veg_compliance": result.get("veg_compliance"),
        "fruit_compliance": result.get("fruit_compliance"),
        "n_unique_recipes": len(set(ids)),
        "sample_recipes": names[:12],
    }


CONFIGS = [
    ("thrifty 1p 2000",
     dc_replace(ScoringConfig.thrifty(), daily_cal_target=2000.0, protein_pct_target=15.0),
     [PersonProfile("A", 2000.0, 75.0)],
     2000.0),
    ("balanced 1p 2000",
     dc_replace(ScoringConfig.balanced(protein_diversity=True),
                 daily_cal_target=2000.0, protein_pct_target=20.0),
     [PersonProfile("A", 2000.0, 75.0)],
     2000.0),
    ("high_protein 1p 2200",
     dc_replace(ScoringConfig.high_protein(target_pct=35.0),
                 daily_cal_target=2200.0, protein_pct_target=35.0),
     [PersonProfile("A", 2200.0, 75.0)],
     2200.0),
    ("budget 1p 1800",
     dc_replace(ScoringConfig.budget(protein_diversity=True),
                 daily_cal_target=1800.0, protein_pct_target=18.0),
     [PersonProfile("A", 1800.0, 75.0)],
     1800.0),
    ("balanced 2p 4000",
     dc_replace(ScoringConfig.balanced(protein_diversity=True),
                 daily_cal_target=4000.0, protein_pct_target=20.0),
     [PersonProfile("A", 2000.0, 75.0), PersonProfile("B", 2000.0, 65.0)],
     4000.0),
    ("balanced family 4p 7000",
     dc_replace(ScoringConfig.balanced(protein_diversity=True),
                 daily_cal_target=7000.0, protein_pct_target=20.0),
     [PersonProfile("A", 2000.0, 75.0), PersonProfile("B", 2000.0, 65.0),
      PersonProfile("C", 1500.0, 50.0), PersonProfile("D", 1500.0, 50.0)],
     7000.0),
    ("balanced 1p 1500 (cut)",
     dc_replace(ScoringConfig.balanced(protein_diversity=True),
                 daily_cal_target=1500.0, protein_pct_target=25.0),
     [PersonProfile("A", 1500.0, 65.0)],
     1500.0),
    ("balanced 1p 2500 (bulk)",
     dc_replace(ScoringConfig.balanced(protein_diversity=True),
                 daily_cal_target=2500.0, protein_pct_target=20.0),
     [PersonProfile("A", 2500.0, 85.0)],
     2500.0),
]

def main():
    rows = []
    for cname, cfg, ppl, cal in CONFIGS:
        print(f"\n=== {cname} ===", flush=True)
        try:
            r = run(cname, cfg, ppl, cal)
            rows.append(r)
            print(f"  cost ${r['cost']:.2f}  ({r['elapsed']:.1f}s)  unique recipes={r['n_unique_recipes']}")
            print(f"  cal_compliance={r['cal_compliance']:.2f}  protein={r['protein_pct']:.1f}%  carbs={r['carbs_pct']:.1f}%  fat={r['fat_pct']:.1f}%")
            print(f"  veg_compliance={r['veg_compliance']:.2f}  fruit_compliance={r['fruit_compliance']:.3f}")
            print(f"  sample: {r['sample_recipes'][:6]}")
        except Exception as e:
            print(f"  FAILED: {e!r}")
            rows.append({"name": cname, "error": str(e)})

    print("\n\n========================================")
    print("SUMMARY (all configs)")
    print("========================================")
    print(f"{'config':<28}  {'cost':>8}  {'protein':>8}  {'veg':>6}  {'recipes':>8}")
    for r in rows:
        if "error" in r:
            print(f"{r['name']:<28}  ERROR: {r['error']}")
        else:
            print(f"{r['name']:<28}  ${r['cost']:>7.2f}  {r['protein_pct']:>7.1f}%  {r['veg_compliance']:>5.1%}  {r['n_unique_recipes']:>8}")

    out = ROOT / "data" / "battery_results.json"
    out.write_text(json.dumps(rows, default=str, indent=2))
    print(f"\nfull results → {out}")


if __name__ == "__main__":
    main()
