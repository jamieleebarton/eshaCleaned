# Hestia HTC Bridge — Fix Plan

## Problem statement

The bridge between recipe encoding, priced_products, and the SparseCascadePlanner was built with these errors:

1. **One HTC code treated as universal identity** — collapses different foods (whole milk vs skim milk, dijon vs honey mustard, extra firm vs silken tofu) into the same lookup row.
2. **Facts pooled across unrelated SKUs** — `htc_reference.json` picks median price from one SKU and most-common FNDDS from another at the same HTC. Macros come from a different food than the price.
3. **Package model gutted** — `HTCPackageIndex` puts exactly one package per HTC. The sparse planner expects multiple package options so it can pick the size that matches recipe grams. Without this, cost arithmetic uses package-list price instead of per-recipe-gram cost.
4. **HTC `00000000` is a Non-Food junk drawer** — leaks Pine Cleaner, Charcoal, Fishing Line, Perfume into the food index. Currently mapped to "Pav Bhaji Masala" with gluten-free pretzel macros.
5. **`(canonical_path, modifier)` matcher was abandoned** — the working matcher from the prior handoff used canonical_path + modifier with htc_form as a routing feature. Current code uses raw HTC as primary key.
6. **No verification gate** — no staple-test ever ran to confirm "Dijon mustard → Dijon mustard SKU".

## Correct architecture

```
concept_key  = (canonical_path, modifier, htc_form)
                ↑                ↑          ↑
                identity tier    claim      form-aware HTC

For each concept_key:
    packages[]   = list of {upc, name, cents, grams, package_size}
                   sparse planner picks size based on actual recipe grams
    sample_skus  = up to 5 SKU evidence rows kept verbatim
                   (no pooling)

For each line in a recipe plan:
    1. resolve concept_key via (recipe.canonical_path, recipe.modifier, recipe.htc_form)
    2. matcher picks one SKU from packages[] using sparse planner's existing logic
    3. nutrition = picked_sku.consensus_fndds → FNDDS lookup (or sr28 fallback)
                   never pool across unrelated SKUs
```

## Phases

### Phase 0 — Snapshot + freeze the broken bridge
- Move `planner/data/htc_reference.json` → `htc_reference.broken.json` (don't delete; reference for diffs)
- Move `planner/data/tensor_cache/` → `tensor_cache.htc_only.bak/`
- Tag git: `htc-bridge-broken-2026-05-07`

### Phase 1 — Build concept_index.json (replaces htc_reference.json)

Source: `priced_products_v2.db`. For each row:
- Skip if `htc_form_code IN ('', '00000000', NULL)`
- Skip if `consensus_canonical LIKE 'Non-Food%'`
- Skip if UPC in `priced_products_excluded.csv`
- Compute `modifier` = `consensus_modifier` (default 'Plain' if blank)
- Compute `concept_key = f"{canonical_path}|{modifier}|{htc_form_code}"`

Group SKUs by concept_key. Per group:
- `packages[]` = up to 20 cheapest distinct UPCs at this concept_key, each with `{upc, name, cents, grams, cpg, consensus_fndds, consensus_sr28}`
- `n_skus`, `path`, `modifier`, `htc_form` for diagnostics
- **No pooled macros, no median price, no consensus FNDDS at concept_key level**

Output: `planner/data/concept_index.json`

### Phase 2 — Build per-recipe concept_grams.json

For each row in `recipes_unified.csv`:
- Resolve recipe-side `(canonical_path, modifier, htc_form)` via:
  - canonical_path from `recipe_ingredient_taxonomy_v2.csv`
  - modifier from `recipe_ingredient_taxonomy_v2.csv`
  - htc_form from current `recipes_unified.csv` (already form-aware after the re-stamp)
- Aggregate grams per recipe per concept_key

Output: `planner/data/recipe_concept_grams.json`

### Phase 3 — Adapt SparseCascadePlanner

- New `ConceptPackageIndex` class extending `PackageIndex`:
  - `packages_by_fndds` re-keyed by concept_key string
  - For each concept_key, populate ALL SKUs from `packages[]` so the planner can pick package size to match recipe grams
- Override `_classify_fndds_code` to accept concept_key and dispatch to protein-source classifier from canonical_path (not from HTC)
- Recipe-line FNDDS is resolved per-pick at planner runtime, not crystallized

### Phase 4 — Rebuild tensor cache

- `IngredientIndex` keyed by concept_key strings
- `recipe_db_tensors.pt` ingredient indices reflect concept_keys
- Save under fresh path so old broken cache doesn't leak

### Phase 5 — Calculator (`calculate_recipe_cost_v7`) consumes concept_index too

- `find_cheapest` becomes `find_best_package(concept_key, recipe_grams, user_facets)`:
  - Filter packages[] by user_facets (organic/etc) via SKU name + claims
  - Pick package whose `grams` is closest to recipe_grams, breaking ties on cpg
  - Return picked SKU's own consensus_fndds for macros
- Remove `htc_reference.json` import; calculator uses `concept_index.json`

### Phase 6 — Staples test (build gate)

`planner/scripts/staples_test.py` runs after Phase 4 + Phase 5 builds. For each test case, resolve a recipe ingredient and assert:

```
test cases:
  ('Dijon mustard',          'Pantry > Condiments > Mustard > Dijon')
                             must NOT contain 'honey'
  ('whole ham',              'Meat & Seafood > Ham')
                             name must contain 'whole' or 'spiral' or 'shank'
                             must NOT match deli/sandwich/lunch
  ('sliced ham',             'Meat & Seafood > Ham')
                             name must contain 'sliced' or 'lunch' or 'deli'
  ('unsalted butter',        'Dairy > Butter')
                             name must contain 'unsalted' or 'sweet cream'
  ('whole milk',             'Dairy > Milk > Whole Milk')
                             name must contain 'whole milk'
                             must NOT match 'fat free' or 'skim' or 'lowfat'
  ('skim milk',              'Dairy > Milk > Fat Free Milk')
                             name must contain 'fat free' or 'skim'
  ('extra firm tofu',        'Pantry > ... > Tofu')
                             name must contain 'firm' (and not 'silken' or 'soft')
  ('tuna in water',          'Pantry > Canned Seafood > Tuna')
                             name must contain 'tuna' (not 'crab boil' or 'mayo')
  ('trout fillet',           'Meat & Seafood > Fish > Trout')
                             name must contain 'trout' or 'steelhead'
  ('ground cinnamon',        'Pantry > Spices & Seasonings > Cinnamon')
                             name must contain 'cinnamon'
                             must NOT match 'bacon' or 'meat'
  ('cinnamon stick',         'Pantry > Spices & Seasonings > Cinnamon')
                             name must contain 'cinnamon stick'
  ('eggs',                   'Dairy > Eggs')
                             name must contain 'egg'
  ('extra virgin olive oil', 'Pantry > Oil > Olive Oil')
                             name must contain 'olive'
                             must NOT match 'mayo' or 'dressing'
  ('whole chicken',          'Meat & Seafood > Poultry > Whole Chicken')
                             name must contain 'whole chicken'
  ('boneless chicken breast','Meat & Seafood > Poultry > Chicken Breast')
                             name must contain 'chicken breast'
                             must NOT match 'rotisserie diced' or 'deli'
  ('ground beef',            'Meat & Seafood > Beef > Ground Beef')
                             name must contain 'ground beef'

A concept_index that fails any case is rejected; build refuses to proceed.
```

### Phase 7 — Per-recipe macro sanity test

After Phase 5, run calculator on 50 known-clean recipes. Compute per-serving kcal/protein/fat. Assert:
- 50 ≤ kcal/serving ≤ 1500
- 1 ≤ protein/serving ≤ 100
- 0 ≤ fat/serving ≤ 100
- 0 ≤ sodium/serving ≤ 5000

Any recipe outside bounds is dumped with its picked SKUs for inspection.

### Phase 8 — Run battery + verify against Hestia behavior

- Run `run_htc_battery.py` (rename to `run_concept_battery.py`)
- Compare cost-per-1000kcal: if any config still > $4/1000kcal, package-options model is still wrong, debug
- Compare protein% to target: should hit within ±2% (was -3 to -5%)

## What stays the same

- `recipe_mapper/v1/htc/encoder.py` — encoder is correct, no changes
- `recipes_unified.csv` re-stamp with form-aware HTC — already done, keep
- `priced_products_v2.db.htc_form_code` column — already populated, keep
- `SparseCascadePlanner` core — keep, just feed it the new index
- `planner/hestia/*` Hestia ports — keep, just patch the adapter layer

## What gets deleted/replaced

- `planner/data/htc_reference.json` → archived as `htc_reference.broken.json`
- `planner/build_htc_tensor_cache.py` HTCPackageIndex class → replaced with ConceptPackageIndex
- `planner/scripts/build_htc_reference.py` → replaced with `build_concept_index.py`
- `planner/scripts/run_htc_battery.py` HTCPI class → replaced with ConceptPackageIndex import

## Rollback plan

If Phase 4 tensor rebuild produces fewer than 350k recipes (vs 392k currently), the concept resolver is dropping too many recipes. Revert by symlinking the `.htc_only.bak/` cache back. No production impact since this is local-dev.

## Definition of done

- All 17 staples tests pass
- 50/50 recipe macro sanity tests pass
- All 8 battery configs run with cost-per-1000kcal between $1.50 and $4.00
- Protein hits within ±2 percentage points of target
- `htc_reference.json` no longer referenced anywhere in `planner/` or `recipe_pricing/`
- No SKU at `htc_form_code = '00000000'` ever appears in a calculated recipe shopping list
