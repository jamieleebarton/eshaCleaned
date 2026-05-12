#!/usr/bin/env python3
"""Audit the actual plan output. For balanced 1p 2000:
  - Run plan
  - Pull each picked recipe
  - Trace each ingredient: HTC → resolved priced concept → SKU
  - Run calculator on each picked recipe; show line-by-line + macros + cost
  - Flag inconsistencies (cost mismatch, macro absurdity, wrong SKU form)
"""
from __future__ import annotations
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from htc_groups import protein_source as htc_protein_source
import json, os, sys, sqlite3, csv, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "recipe_pricing"))
os.environ["HESTIA_BASE_PATH"] = str(ROOT)
csv.field_size_limit(2**30)

import torch
from dataclasses import replace as dc_replace

import hestia.sparse_cascade as sc
import hestia.data_structures as ds
from htc_groups import patch_perishability_index as _patch_pi
_patch_pi(ds)
from hestia.scoring_config import ScoringConfig
from hestia.data_structures import PersonProfile, HouseholdConfig, AttendanceSchedule
import hestia.plate_builder as pb

DATA = ROOT / "data"
CI = json.loads((DATA / "concept_index.json").read_text())
RES = json.loads((DATA / "concept_resolution.json").read_text())

# Patches
PROT = {ck: _protein_from_path(c["canonical_path"]) for ck, c in CI.items()}
sc._classify_fndds_code = htc_protein_source

class CPI(ds.PackageIndex):
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
        self._gpu_tensors_built = False
        self._gpu_prices = self._gpu_sizes = self._gpu_option_prices = None

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
ds.PackageIndex = CPI

_OPB = pb.PlateBuilder
class CPB(_OPB):
    def __init__(self, *a, **kw):
        if "templates_dir" not in kw:
            kw["templates_dir"] = str(ROOT / "assets" / "plate_templates_v2")
        super().__init__(*a, **kw)
pb.PlateBuilder = CPB
sc.PlateBuilder = CPB
sc._tensor_cache_dir = lambda: DATA / "tensor_cache"

# Run plan
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
print(f"device={device}")
recipe_db = sc.SparseRecipeDatabase.from_cache(device)
package_index = ds.PackageIndex()
package_index.build_gpu_tensors(recipe_db.ingredient_index, device)

config = dc_replace(ScoringConfig.balanced(protein_diversity=True),
                     daily_cal_target=2000.0, protein_pct_target=20.0)
people = [PersonProfile("A", 2000.0, 75.0)]
schedule = AttendanceSchedule(HouseholdConfig(people=people))
planner = sc.SparseCascadePlanner(
    recipe_db=recipe_db, package_index=package_index, device=device,
    attendance_schedule=schedule, scoring_config=config,
    leftover_ttl=14, freezer_ttl=60, auto_freeze=True, K=50, verbose=False)
session = planner.start_session(initial_pantry=torch.zeros(planner.num_ingredients, device=device),
                                  initial_leftovers=None, historical_banned_ids=[])
print("planning...")
t0 = time.time()
result = session.plan_next_week()
print(f"  done in {time.time()-t0:.1f}s")

print(f"\n=== PLAN: ${result['total_cost']:.2f} ===")
print(f"protein={result['protein_pct']:.1f}%  veg={result['veg_compliance']:.2%}  fruit={result['fruit_compliance']:.2%}")

used_ids = result.get("used_recipe_ids", [])
try: ids = [int(x) for x in (used_ids.tolist() if hasattr(used_ids,'tolist') else list(used_ids)) if x]
except: ids = []
ids = list(dict.fromkeys(ids))[:8]  # unique, first 8

# Now run calculator on each picked recipe to inspect line-by-line
import calculate_recipe_cost_v7 as calc
print("\nloading calculator data…")
unified = calc.load_unified()
cls = calc.load_classifications()
bfl, overridden = calc.load_buy_form_lookup()
excluded_upcs = calc.load_excluded_upcs()
fndds_macros = calc.load_fndds_macros()
product_claims = calc.load_product_claims()
con = sqlite3.connect(str(calc.PRICED_DB))

print(f"\n=== AUDIT: {len(ids)} picked recipes ===")
issues = []
for rid in ids:
    r = calc.calculate(str(rid), unified, cls, bfl, con, [], excluded_upcs,
                        fndds_macros, product_claims, overridden)
    sv = 4
    kcal_s = r.total_kcal/sv
    prot_s = r.total_protein_g/sv
    fat_s = r.total_fat_g/sv
    sod_s = r.total_sodium_mg/sv
    print(f"\n--- rid={rid}  {r.recipe_title[:55]}")
    print(f"    {kcal_s:>5.0f} kcal/sv  {prot_s:>5.1f}g prot  {fat_s:>5.1f}g fat  {sod_s:>5.0f}mg Na")
    line_issues = []
    for ln in r.lines:
        sku = ln.sku_name or "(none)"
        if not ln.sku_name:
            line_issues.append(f"NO_SKU: {ln.canonical_buy_form}")
        # Sanity flags per line
        if ln.line_kcal > 4000:
            line_issues.append(f"KCAL_HIGH {ln.line_kcal:.0f}: {ln.canonical_buy_form} → {sku[:40]}")
        if ln.line_sodium_mg > 50000:
            line_issues.append(f"NA_HIGH {ln.line_sodium_mg:.0f}: {ln.canonical_buy_form} → {sku[:40]}")
        # Form mismatch detection
        bf = (ln.canonical_buy_form or "").lower()
        snl = sku.lower()
        if "whole milk" in bf and ("skim" in snl or "fat free" in snl):
            line_issues.append(f"FORM_MISMATCH: {ln.canonical_buy_form} → {sku[:40]}")
        if "extra firm" in bf and ("silken" in snl or "soft" in snl):
            line_issues.append(f"FORM_MISMATCH: {ln.canonical_buy_form} → {sku[:40]}")
        if "dijon" in bf and "honey" in snl:
            line_issues.append(f"FORM_MISMATCH: {ln.canonical_buy_form} → {sku[:40]}")
        if "unsalted" in bf and "salted" in snl and "unsalted" not in snl:
            line_issues.append(f"FORM_MISMATCH: {ln.canonical_buy_form} → {sku[:40]}")
        print(f"      {ln.canonical_buy_form[:30]:<30}  {sku[:50]:<50}  ${ln.line_cost_cents/100:.2f}")
    if line_issues:
        for li in line_issues:
            print(f"      ⚠ {li}")
            issues.append({"rid": rid, "issue": li})

print(f"\n=== AUDIT SUMMARY ===")
print(f"recipes audited: {len(ids)}")
print(f"issues found: {len(issues)}")
from collections import Counter
types = Counter(i["issue"].split(":")[0] for i in issues)
for t, n in types.most_common():
    print(f"  {n:>3}  {t}")

(DATA / "audit_results.json").write_text(json.dumps(
    {"plan_cost": result["total_cost"], "picked_ids": ids, "issues": issues}, indent=2))
print(f"\n→ {DATA/'audit_results.json'}")
