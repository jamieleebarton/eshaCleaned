# Hestia bridge — Fix Plan, Round 2

After running Hestia's vanilla planner side-by-side with ours, then doing per-recipe diffs against `recipes2.csv` ground truth, here are the remaining defects and the plan.

## What we now know is broken

### 1. IngredientIndex contains concept_keys that have no packages (hard-fail)
The new ConceptPackageIndex.build_gpu_tensors raises `RuntimeError` if any concept_key in `ingredient_index.fpid_to_idx` is missing from `packages_by_fndds`. Concepts arrive in IngredientIndex through recipe-pool ingredient lists; lines that resolved via `parent_path_only`, `form_only`, or `path_only` may end up keyed on priced concepts that DO have packages — so this should be safe — but anything that slipped through (e.g. recipe used a concept with no priced match) will crash the build.

### 2. Recipe total_mass under-counts when ingredient lines drop
When a recipe ingredient line resolves to NO_MATCH, its grams are dropped from the recipe's mass. The recipe pool's `total_mass_g` is then less than the actual recipe. Hestia uses the recipe-side authoritative total mass; ours can lose 30–50% of the mass on recipes where multiple ingredients are unresolved.

### 3. Form-leakage still imperfect
- `whole milk → 1% Lowfat` (was Skim, improved with recipe-leaf hints, still not exactly Whole)
- `whole ham → Spiral Sliced Half Ham` (close enough — actually correct family, but the leaf "sliced" in name confuses some tests)
- `Mexican cheese → American cheese singles` (cheese family substitution)

### 4. Per-recipe macro outliers (16 cases out of 200)
- Honey-Mango bridge error in priced_products `consensus_fndds` (mango SKU tagged with honey FNDDS)
- Some SKUs have valid FNDDS codes that don't exist in our local `fndds_nutrient_lookup.csv` (cooked ham 22311010, honey 41436000) — partially fixed by SR28 fallback (closes 16/16 from 200-recipe verify)

### 5. Recipe-pool food_groups now correct
After `recipes2.csv` overlay: `food_groups.vegetables_g` etc. read directly from FNDDS-derived totals. Veg compliance jumped 0.4% → 38.1% on balanced 1p 2000.

### 6. Fishing lures, baby food, charcoal — quarantined
After NAME_BLOCKLIST in concept_index build + clean_priced_products HARD_RULES, these no longer leak into food picks.

## Fix Phases

### Phase A — Drop unmatched concepts from IngredientIndex (no more crash risk)

When building the recipe pool in `build_concept_tensor_cache.py`, skip lines whose resolved priced_key has no entry in `concept_index.json` (this should be impossible by construction now, but enforce it):

```python
# in build_concept_tensor_cache.py:
priced_keys_with_packages = {ck for ck, c in CI.items() if c["packages"]}
for rid, concepts in RCG["concept_grams"].items():
    new_d = {}
    for rk, grams in concepts.items():
        pk = RES.get(rk, {}).get("priced_key")
        if pk and pk in priced_keys_with_packages:
            new_d[pk] = new_d.get(pk, 0.0) + grams
    if new_d: resolved_recipes[rid] = new_d
```

### Phase B — Use recipes2.csv `total_mass_g` as authoritative recipe mass

Already done in the overlay. Verify by spot-check: Kittencal's Potato Kugel mass = 4596g per recipes2.csv (was 1882g in our pool before overlay).

### Phase C — Per-recipe Hestia parity verification

Run `diff_per_recipe.py` on 1,000 recipes. Stratify by:
- Recipes where ours and Hestia agree on food groups within 5% mass (should be ~100% after overlay)
- Recipes where we agree on cost within 20% (calculator-level)
- Recipes where macros match within 10% per-serving (calculator + SR28 fallback)

### Phase D — Run Hestia + ours side by side for 4 weeks of plans

The 1-week comparison was lopsided. Run Hestia's plan_next_week 4× consecutively, ditto ours, and compute:

| Metric | Hestia avg | Ours avg | Diff |
|---|---|---|---|
| Cost ($/week) | | | |
| Veg compliance | | | |
| Recipe variety (unique recipes) | | | |
| Pizza/grilled-cheese frequency | | | |
| Real protein recipes (chicken/fish/beef) per week | | | |

### Phase E — Form-leakage final pass

The recipe-leaf hint approach helped Dijon→Dijon, whole→whole-ish, but is averaging across recipes mapping to same concept. To get pure per-recipe-line filtering inside the planner, pass `recipe_leaf_tokens` through to package picker at planner-runtime. Requires a small extension to `IngredientIndex` to carry per-recipe-line filter hints.

### Phase F — SKU macro audit on priced_products

The Honey-Mangos / cooked-ham-FNDDS-missing patterns suggest priced_products has consensus_fndds errors. Run a SKU-level audit:

For each (sku.consensus_fndds, sku.consensus_canonical) pair, check if FNDDS code's food group matches the canonical_path's expected food group (vegetables-coded FNDDS at `Produce > Vegetables`, etc.). Flag mismatches.

### Phase G — Calculator-side macro test gate (recipe → kcal sanity)

Run calculator on 1,000 recipes. Per-serving:
- 50 ≤ kcal ≤ 1200 (any outliers dumped with their picked SKUs)
- 1 ≤ protein ≤ 80
- 0 ≤ sodium ≤ 4000

Already implemented (`macro_sanity_test.py`); raise sample to 1,000.

### Phase H — Battery comparison Hestia vs Ours, all 8 configs

Run `compare_hestia_vs_ours.py` for thrifty, balanced, high-protein, budget, 2-person, family, cut, bulk. Report side-by-side: cost, protein%, veg%, recipe types per config. This becomes the actual scorecard.

## Definition of done

1. All 8 battery configs run without crashes
2. Veg compliance per config matches Hestia within ±5 percentage points (we may exceed; should not be *below*)
3. Cost per 1000 kcal ∈ [$1.50, $4.00] for all configs (currently $3–$6, need package-options optimizer to fully kick in)
4. Staples test: 16/16 pass
5. Macro sanity test on 1,000 recipes: ≥95% pass
6. Per-recipe Hestia-diff: ≥95% recipes have food_groups within 5% mass
7. No fishing lures / baby food / charcoal in any picked recipe across battery
8. Side-by-side battery report shows ours doesn't fall behind Hestia on any compliance dimension

## What stays as-is

- Concept-index keying on (canonical_path | modifier | htc_form)
- Multi-package model in ConceptPackageIndex
- Recipe-leaf hint ranking
- recipes2.csv overlay for food_groups + per-recipe macros
- FNDDS first / SR28 fallback in calculator
- 00000000 quarantine + NAME_BLOCKLIST in concept_index build
- Anti-modifier filter in calculator (gluten-free/skim/etc.)

## What gets reverted/dropped

- `htc_reference.broken.json` (kept as archive only; never read)
- `tensor_cache.htc_only.bak/` (kept as archive)
- The canonical_path heuristic for food_groups (replaced by recipes2.csv overlay)

## File deliverables

- `planner/scripts/diff_per_recipe.py` — extend to 1000 sample, dump CSV
- `planner/scripts/macro_sanity_test.py` — bump sample to 1000
- `planner/scripts/audit_skus_macros.py` — NEW: priced_products consensus_fndds vs canonical_path consistency check
- `planner/scripts/four_week_comparison.py` — NEW: 4-week side-by-side
- `planner/scripts/compare_hestia_vs_ours.py` — already in place; extend to all 8 configs
- `planner/data/round2_scorecard.json` — final definition-of-done report
