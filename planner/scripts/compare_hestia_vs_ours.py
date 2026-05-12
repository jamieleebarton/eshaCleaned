#!/usr/bin/env python3
"""Run BOTH Hestia's planner (unchanged) and our concept-keyed planner
with the same scoring config. Dump:

  - total cost (Hestia vs ours)
  - recipe-level macros
  - recipes picked: which they share, which each picked alone
  - per-side full ingredient list for picked recipes (for spot diffs)

Both run on CPU for determinism.
"""
from __future__ import annotations
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from htc_groups import protein_source as htc_protein_source
import json, os, sys, time
from pathlib import Path

OURS_ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle/planner")
HESTIA_ROOT = Path("/Users/jamiebarton/Desktop/Hestia/api")
OUT = OURS_ROOT / "data" / "compare_hestia_vs_ours.json"

CONFIG = {
    "name": "balanced 1p 2000",
    "daily_cal": 2000.0, "protein_pct": 20.0,
    "person_kg": 75.0,
}


def run_hestia():
    """Run vanilla Hestia planner in subprocess so its imports/data don't bleed."""
    import subprocess
    code = r'''
import sys, os, json, time
sys.path.insert(0, "/Users/jamiebarton/Desktop/Hestia/api")
os.chdir("/Users/jamiebarton/Desktop/Hestia/api")
import torch
from dataclasses import replace as dc_replace
from hestia.sparse_cascade import SparseRecipeDatabase, SparseCascadePlanner
from hestia.scoring_config import ScoringConfig
from hestia.data_structures import PackageIndex, PersonProfile, HouseholdConfig, AttendanceSchedule
device = torch.device("cpu")
recipe_db = SparseRecipeDatabase.from_cache(device)
package_index = PackageIndex(); package_index.build_gpu_tensors(recipe_db.ingredient_index, device)
config = dc_replace(ScoringConfig.balanced(protein_diversity=True),
                     daily_cal_target=2000.0, protein_pct_target=20.0)
planner = SparseCascadePlanner(
    recipe_db=recipe_db, package_index=package_index, device=device,
    attendance_schedule=AttendanceSchedule(HouseholdConfig(people=[PersonProfile("A",2000.0,75.0)])),
    scoring_config=config, leftover_ttl=14, freezer_ttl=60, auto_freeze=True, K=50, verbose=False)
session = planner.start_session(initial_pantry=torch.zeros(planner.num_ingredients,device=device),
                                 initial_leftovers=None, historical_banned_ids=[])
t0 = time.time()
result = session.plan_next_week()
elapsed = time.time() - t0
used = result.get("used_recipe_ids", [])
ids = []
try: ids = [int(x) for x in (used.tolist() if hasattr(used,"tolist") else list(used)) if x]
except: pass
out = {
    "elapsed": elapsed,
    "total_cost": result.get("total_cost", 0.0),
    "protein_pct": result.get("protein_pct"),
    "carbs_pct":   result.get("carbs_pct"),
    "fat_pct":     result.get("fat_pct"),
    "veg_compliance":   result.get("veg_compliance"),
    "fruit_compliance": result.get("fruit_compliance"),
    "ids": list(dict.fromkeys(ids)),
    "names": [recipe_db.get_recipe_name(int(recipe_db.gpu_recipe_id_to_idx[i].item())) if i in recipe_db.gpu_recipe_id_to_idx else f"r{i}"
              for i in dict.fromkeys(ids)],
}
print("HESTIA_RESULT:" + json.dumps(out, default=str))
'''
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        return {"error": p.stderr[-1500:]}
    for line in p.stdout.splitlines():
        if line.startswith("HESTIA_RESULT:"):
            return json.loads(line[len("HESTIA_RESULT:"):])
    return {"error": "no result line"}


def run_ours():
    import subprocess
    code = r'''
import sys, os, json, time
sys.path.insert(0, "/Users/jamiebarton/Desktop/esha_audit_bundle/planner")
os.chdir("/Users/jamiebarton/Desktop/esha_audit_bundle/planner")
os.environ["HESTIA_BASE_PATH"] = "/Users/jamiebarton/Desktop/esha_audit_bundle/planner"
import torch
from dataclasses import replace as dc_replace
import hestia.sparse_cascade as sc
import hestia.data_structures as ds
from htc_groups import (
    patch_perishability_index as _patch_pi,
    protein_source as htc_protein_source,
)
_patch_pi(ds)
from hestia.scoring_config import ScoringConfig
from hestia.data_structures import PersonProfile, HouseholdConfig, AttendanceSchedule
import hestia.plate_builder as pb
DATA = __import__("pathlib").Path("/Users/jamiebarton/Desktop/esha_audit_bundle/planner/data")
CI = json.loads((DATA/"concept_index.json").read_text())
HINTS = json.loads((DATA/"priced_to_recipe_leaf.json").read_text())
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
                tmp.append((pkg["cents"]/100.0, float(pkg["grams"]),
                            pkg.get("size_display") or f"{pkg['grams']:.0f}g",
                            pkg["name"].lower()))
            tmp.sort(key=lambda p: (-sum(1 for h in hints if h in p[3]), p[0]/p[1]))
            self.packages_by_fndds[ck] = [(p[0],p[1],p[2]) for p in tmp]
        self._gpu_tensors_built = False
        self._gpu_prices = self._gpu_sizes = self._gpu_option_prices = None
    def build_gpu_tensors(self, ingredient_index, device):
        missing = [ck for ck in ingredient_index.fpid_to_idx if ck not in self.packages_by_fndds]
        if missing:
            raise RuntimeError("Concept planner refuses fallback pricing: " + ", ".join(sorted(missing)[:20]))
        n = ingredient_index.num_ingredients
        p = self.MAX_PACKAGE_OPTIONS
        prices = torch.zeros(n, dtype=torch.float32, device=device)
        sizes = torch.ones(n, dtype=torch.float32, device=device)
        option_prices = torch.zeros((n, p), dtype=torch.float32, device=device)
        option_sizes = torch.ones((n, p), dtype=torch.float32, device=device)
        for idx in range(n):
            ck = ingredient_index.idx_to_fpid[idx]
            pkgs = self.packages_by_fndds[ck]
            first_price, first_size, _ = pkgs[0]
            prices[idx] = float(first_price); sizes[idx] = float(first_size)
            option_prices[idx, :] = float(first_price); option_sizes[idx, :] = float(first_size)
            seen = set(); selected = []
            for pkg in pkgs:
                rounded = round(float(pkg[1]), 3)
                if rounded in seen: continue
                seen.add(rounded); selected.append(pkg)
                if len(selected) >= p: break
            for j, (price, grams, _) in enumerate(selected):
                option_prices[idx, j] = float(price); option_sizes[idx, j] = float(grams)
        self._gpu_prices = prices; self._gpu_sizes = sizes
        self._gpu_option_prices = option_prices; self._gpu_option_sizes = option_sizes
        self._gpu_tensors_built = True
        print(f"ConceptPackageIndex: Built GPU tensors for {n:,} ingredients using real package data only")
ds.PackageIndex = CPI
sc._tensor_cache_dir = lambda: DATA/"tensor_cache"
_OPB = pb.PlateBuilder
class _PB(_OPB):
    def __init__(self, *a, **kw):
        if "templates_dir" not in kw: kw["templates_dir"] = "/Users/jamiebarton/Desktop/esha_audit_bundle/planner/assets/plate_templates_v2"
        super().__init__(*a, **kw)
pb.PlateBuilder = _PB; sc.PlateBuilder = _PB
device = torch.device("cpu")
recipe_db = sc.SparseRecipeDatabase.from_cache(device)
package_index = ds.PackageIndex(); package_index.build_gpu_tensors(recipe_db.ingredient_index, device)
config = dc_replace(ScoringConfig.balanced(protein_diversity=True),
                     daily_cal_target=2000.0, protein_pct_target=20.0)
planner = sc.SparseCascadePlanner(
    recipe_db=recipe_db, package_index=package_index, device=device,
    attendance_schedule=AttendanceSchedule(HouseholdConfig(people=[PersonProfile("A",2000.0,75.0)])),
    scoring_config=config, leftover_ttl=14, freezer_ttl=60, auto_freeze=True, K=50, verbose=False)
session = planner.start_session(initial_pantry=torch.zeros(planner.num_ingredients,device=device),
                                 initial_leftovers=None, historical_banned_ids=[])
t0 = time.time()
result = session.plan_next_week()
elapsed = time.time() - t0
used = result.get("used_recipe_ids", [])
ids = []
try: ids = [int(x) for x in (used.tolist() if hasattr(used,"tolist") else list(used)) if x]
except: pass
out = {"elapsed": elapsed,
       "total_cost": result.get("total_cost", 0.0),
       "protein_pct": result.get("protein_pct"),
       "carbs_pct":   result.get("carbs_pct"),
       "fat_pct":     result.get("fat_pct"),
       "veg_compliance":   result.get("veg_compliance"),
       "fruit_compliance": result.get("fruit_compliance"),
       "ids": list(dict.fromkeys(ids)),
       "names": [recipe_db.get_recipe_name(int(recipe_db.gpu_recipe_id_to_idx[i].item())) if i in recipe_db.gpu_recipe_id_to_idx else f"r{i}"
                 for i in dict.fromkeys(ids)]}
print("OURS_RESULT:" + json.dumps(out, default=str))
'''
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        return {"error": p.stderr[-1500:]}
    for line in p.stdout.splitlines():
        if line.startswith("OURS_RESULT:"):
            return json.loads(line[len("OURS_RESULT:"):])
    return {"error": "no result line"}


def main():
    print("=== Running Hestia planner (unchanged)…", flush=True)
    h = run_hestia()
    print(f"  cost ${h.get('total_cost',0):.2f}  protein={h.get('protein_pct')}%  veg={h.get('veg_compliance')}  ({h.get('elapsed')}s)")
    print(f"  recipes: {len(h.get('ids', []))}")

    print("\n=== Running OUR concept-keyed planner…", flush=True)
    o = run_ours()
    print(f"  cost ${o.get('total_cost',0):.2f}  protein={o.get('protein_pct')}%  veg={o.get('veg_compliance')}  ({o.get('elapsed')}s)")
    print(f"  recipes: {len(o.get('ids', []))}")

    h_ids = set(h.get("ids", []))
    o_ids = set(o.get("ids", []))
    print(f"\n=== Recipe overlap ===")
    print(f"  shared:        {len(h_ids & o_ids)}")
    print(f"  Hestia-only:   {len(h_ids - o_ids)}")
    print(f"  Ours-only:     {len(o_ids - h_ids)}")

    h_names = dict(zip(h.get("ids", []), h.get("names", [])))
    o_names = dict(zip(o.get("ids", []), o.get("names", [])))
    print(f"\n=== Hestia picks ===")
    for i in h.get("ids", [])[:25]: print(f"  {i:<8} {h_names.get(i,'?')}")
    print(f"\n=== Our picks ===")
    for i in o.get("ids", [])[:25]: print(f"  {i:<8} {o_names.get(i,'?')}")

    OUT.write_text(json.dumps({"hestia": h, "ours": o}, indent=2, default=str))
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
