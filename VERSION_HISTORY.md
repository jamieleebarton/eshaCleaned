# Recipe-pricing pipeline version history

Single source of truth for what's been changed and what each round did.
Update at the end of every round. Newest entries on top.

| Ver | Date | Calculability | Cost / 12wk | exact% in picks | What changed |
|---|---|---:|---:|---:|---|
| **V11** | 2026-05-10 | **91.30%** | **$1,345.81** | TBD | 30 component-substitution overrides for non-standalone-sold ingredients: graham cracker crumbs / chocolate cookie crumbs / cookie crumbs → cookies/grahams; egg yolks / egg whites → whole eggs; lemon/lime/orange zest+peel+rind → whole fruits. Cost rises sharply (+$351, +35%) because recipes needing "1 yolk" now require buying whole eggs. ✓ coverage detector PASS (within tolerance) |
| V10 | 2026-05-10 | 90.82% | $994.19 | 88.8% | 17 new htc_cp_overrides for safe parent-substitutions: extracts (Lemon/Peppermint/Mint/Almond/Maple/Rum/Coconut/Banana/Orange/Chocolate) → "Pantry > Baking Extracts" parent; tangerines/clementines → Oranges; bacon fat/duck fat/schmaltz → Pantry > Oil. ✓ coverage detector PASS, ✓ encoder 148/148 |
| V9 | 2026-05-10 | 90.43% | $928.70 | 88.8% | Coverage detector + version history. Baseline set. (Identical state to V8.) |
| V8 | 2026-05-10 | 90.43% | $928.70 | 88.8% | Migrated 2,194 portion rules from `implementation/reviewed_household_unit_gram_rules.csv` → `recipe_pricing/reviewed_household_portions.csv`. Reviewed-household now wins over SR28 in normalizer. Drift-prevention gate. |
| V7 | 2026-05-10 | 95.37% | $936.55 | 90.4% | Added 6 encoder GROUP_RULES guards (butter beans, garlic salt, onion soup mix, pimientos, mace, sauerkraut) + reordered FAMILY_RULES["E"] so f7 (specific spices) fires before f6 (generic seasoning) |
| V6 | 2026-05-10 | 95.37% | $936.55 | 90.6% | Updated `recipe_ingredient_taxonomy_v2.csv` for 17 spice items so restamp picks up new canonical_paths |
| V5 | 2026-05-09 | 95.37% | $1,004.85 | 90.4% | Class-2 architectural fix: re-tagged 42 spice FDCs at master (consensus_full_corpus_audit.csv), regen consensus_htc_tagged, rebuilt food_slot_registry, re-encoded recipes & priced. Distinct htc per spice (nutmeg/cardamom/cloves no longer collide at E2000009) |
| V4 | 2026-05-09 | 95.37% | $966.24 | 90.6% | 70 new htc_cp_overrides for audit-revealed routing bugs (beef roast, squash, cherry pie, pita, hamburger buns, miso, thyme/sage, ginger root, marmalade, peanut butter, sherry wine) |
| V3 | 2026-05-09 | 92.35% | $1,011.80 | 91.4% | 8 encoder precedence guards at top of GROUP_RULES (broth/stock, baking soda, extracts, chocolate chips, coconut flakes, cayenne, dried onion flakes, sauerkraut). Kills the `Plant Based Cheese > Spaghetti with Sauce` class. Test gate: 138 cases. |
| V2 | 2026-05-09 | 91.70% | $1,048.25 | 57.5% | 6 band-aid bugs: tomato-sauce overrides, min-count gate at htc_to_path lookup, leaf-pool promote in concept_index, recipe-cp overrides for misroutes, non-food filter |
| V1 | (inherited) | 74.30% | $1,035.38 | 58% | State at the start of this work — previous session's edits |
| V0 | (inherited) | 0.27% | — | — | `.before_full_audit` snapshot — broken |

## Files of record

| File | Purpose | Backed up |
|---|---|---|
| `retail_mapper/v2/consensus_full_corpus_audit.csv` | FNDDS master (462k rows). Source of canonical_path / fdc_id / htc per food | `.before_class2`, `.before_path_consolidation` |
| `recipe_mapper/v1/output/consensus_htc_tagged.csv` | derived from master via `tag_consensus_with_htc.py` | `.before_class2` |
| `recipe_mapper/v1/output/recipe_ingredient_taxonomy_v2.csv` | recipe ingredient → cp + product_identity_fixed | `.before_class2` |
| `recipe_mapper/v1/output/recipe_ingredient_htc_tagged.csv` | recipe item → htc_code (per `tag_ingredients_with_htc.py`) | `.before_phase2` |
| `recipe_mapper/v1/output/recipes_unified.csv` | 4.7M recipe ingredient lines with htc_code per line | `.before_v8`, `.before_class2_v2` |
| `recipe_mapper/v1/htc/encoder.py` | Group/family/form rules + encode() | `.before_categorical_fix` |
| `recipe_mapper/v1/htc/food_slots.py` + `food_slot_registry.csv` | (group, family, food_key) → food_slot lookup | `.before_class2` |
| `recipe_pricing/reviewed_household_portions.csv` | item × unit → grams (live normalizer reads this) | `.before_migration`, `.before_class2_phaseI` |
| `recipe_pricing/htc_cp_overrides.csv` | recipe item → canonical_path overrides | `.before_class2_phaseI` |
| `recipe_pricing/data/priced_products_v2.db` | 169k retail SKUs with htc + cp | `.before_class2` |
| `planner/data/concept_index.json` | priced concept_key → SKU pool | (rebuilt every change) |
| `planner/data/concept_resolution.json` | recipe concept_key → priced concept_key | (rebuilt) |
| `planner/data/recipe_concept_grams.json` | recipe_id → {concept_key: grams} | (rebuilt) |

## Test gates (run before merging any change)

| Gate | What it checks | Run with |
|---|---|---|
| `tests/test_encoder.py` | 148 ground-truth (item, expected_group, expected_cp_contains) cases | `python3 tests/test_encoder.py` |
| `tests/test_portion_rules.py` | Drift between `implementation/reviewed_household_unit_gram_rules.csv` and `recipe_pricing/reviewed_household_portions.csv`; physical mass conversions; duplicates | `python3 tests/test_portion_rules.py` |
| `tests/test_planner_coverage.py` | Recipe-level calculability vs `tests/coverage_baseline.json` (V9 = 90.43%, ±1pp) | `python3 tests/test_planner_coverage.py` |

## Pipeline rebuild order

After ANY change to the master file, encoder, registry, taxonomy, or overrides:

```bash
# 1. Re-tag FDC corpus (master → consensus_htc_tagged)
python3 recipe_mapper/v1/tag_consensus_with_htc.py

# 2. Rebuild food_slot_registry from new master
python3 recipe_mapper/v1/htc/build_food_slot_registry.py

# 3. Re-tag recipe ingredient items
python3 recipe_mapper/v1/tag_ingredients_with_htc.py

# 4. Re-stamp recipes_unified.csv via taxonomy_v2 + encoder
mv recipe_mapper/v1/output/recipes_unified.csv recipe_mapper/v1/output/recipes_unified.csv.before_<round>
cp recipe_mapper/v1/output/recipes_unified.csv.<KNOWN_GOOD> recipe_mapper/v1/output/recipes_unified.csv
python3 planner/scripts/restamp_recipes_unified_htc.py
mv recipe_mapper/v1/output/recipes_unified.csv recipe_mapper/v1/output/recipes_unified.csv.input_<round>
mv recipe_mapper/v1/output/recipes_unified.htc_fixed.csv recipe_mapper/v1/output/recipes_unified.csv

# 5. (Optional) Re-normalize grams if portion rules changed
python3 recipe_pricing/normalize_grams_to_sr28.py

# 6. Rebuild downstream
python3 planner/scripts/build_recipe_concept_grams.py
python3 planner/scripts/build_concept_index.py
python3 planner/scripts/build_concept_resolution.py
cd planner && python3 build_concept_tensor_cache.py && cd ..

# 7. Run tests
python3 tests/test_encoder.py
python3 tests/test_portion_rules.py
python3 tests/test_planner_coverage.py

# 8. Run planner
HESTIA_BEAM_K=50 python3 planner/scripts/multi_week_ours.py \
    --weeks 12 --people 4 --cal 2000 --mode thrifty \
    --protein-pct 15 --leftover-pct 0.75 \
    --out audit_results/multi_week_ours_12w_v<n>.json

# 9. Audit picks
python3 recipe_pricing/picked_recipe_audit.py audit_results/multi_week_ours_12w_v<n>.json
```

## Why V7 → V8 coverage drop is NOT a regression to chase

V7's 95.37% calculable was inflated by **false-positive matching**:
- "lemon extract" → routed to generic Spice Blend pool (paid for ground cinnamon)
- "white pepper" → fell into Spice Blend (paid for whatever's cheapest there)
- "comfrey" → matched any random vegetable
- "lovage" → matched any herb

V8's 90.43% is honest:
- Lemon Extract is correctly NO_MATCH (priced data has no Lemon Extract specifically; nearest is generic Pantry > Baking Extracts)
- White Pepper is correctly NO_MATCH (priced data has no white pepper specifically)
- Comfrey is correctly NO_MATCH (no priced match, would substitute random vegetable)

Of the 24,170 "lost" recipes V7 → V8:
- ~15,000 are TRUE_GAPs — items Walmart/Kroger don't sell in the priced corpus
- ~7,000 are PARENT_HAS_POOL — recipe wants specific leaf, priced has parent only; substituting parent would buy wrong product
- ~2,000 are exotic items correctly rejected

**Future direction:** raise V8/V9 baseline only by adding priced SKUs (data) or by case-by-case approved overrides for items where parent substitution is acceptable. Do not chase V7's number.

## What broke and how it was fixed (lessons)

1. **Class-1 encoder collisions** (V3): GROUP_RULES regex order matters; first-match-wins. Specific noun patterns (broth, baking soda, extract, chocolate chips) must fire BEFORE broad patterns (chicken, beverage).

2. **Class-2 FDC mistags** (V5): the htc_to_path lookup builds from FDC tagging in `consensus_htc_tagged.csv`. If most FDCs at one htc were tagged at a generic path (Spice Blend / Slushie Mix / Protein Bars), the lookup returns that generic path even when the recipe really wants a specific food. Fix at master level by re-tagging FDCs.

3. **Variant pool contamination** (V2/V5): "Strawberry Applesauce" sat in the plain Applesauce pool because `htc_form_code` doesn't distinguish flavors. Pool-prune in `build_concept_index.py` drops flavored SKUs when plain exists. Same logic catches Mozzarella Blend, Smart Balance, etc.

4. **Two parallel rule files** (V8): `recipe_pricing/reviewed_household_portions.csv` and `implementation/reviewed_household_unit_gram_rules.csv` both held unit-gram rules. The live normalizer only read one. The lettuce-head fix lived in the OTHER file. Drift-prevention gate (`tests/test_portion_rules.py`) catches this.

5. **Coverage regression detector** (V9): chasing inflated coverage hides false-positives. The detector with V8 baseline catches future drops.
