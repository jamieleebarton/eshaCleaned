# Recipe to Retail Bridge Official Plan

Date: 2026-05-10

## Goal

Produce a deterministic 12-week meal plan and shopping list where every picked
recipe ingredient has:

- a resolved gram amount,
- a recipe-side concept key,
- a priced retail concept key,
- an actual purchased SKU,
- whole-package cost math,
- and an audit trail that proves the SKU is the right food.

Target household configuration:

- 12 weeks
- 4 people
- 2000 calories per person per day
- thrifty mode
- 75% leftovers
- 15% protein target

Current release-candidate after Codex audit pass:

- Plan JSON: `/tmp/multi_week_ours_12w_codex_final.json`
- Total cost: `$936.55`
- Average weekly cost: `$78.05`
- Per person per day: `$2.79`
- Unique recipes: `248`
- Repeat picks: `41`
- Actual cart purchase rows logged: `433`
- Picked ingredient audit lines: `1,875`
- `NO_RESOLUTION`: `0`
- Bad-SKU gate: `0` hits

The remaining release risk is not known junk in the actual cart. It is
household-unit gram drift, lossy `path_only` resolution debt, and one planner
metadata issue: tensor-cache rebuild still reports `Protein sources: 0
classified`, even though weekly protein percentages are calculated.

## Non-Negotiable Invariants

1. `NO_MATCH` is never free. A recipe with any unresolved required ingredient
   is excluded from the planner pool until the bridge is fixed.
2. Quarantine is only for actual non-food. Food in the wrong aisle must be
   moved to the correct canonical path and re-encoded.
3. The final plan must log actual `ingredient_purchases`, including SKU,
   UPC, package grams, package cents, purchased grams, package count, and cost.
4. Water can be zero-cost only by explicit free-path policy, never by fallback.
5. No fallback `$3/kg` package pricing is allowed.
6. Hestia comparisons are valid only when run with the same target config.
   Any one-person/balanced/single-week compare is diagnostic only.
7. A headline cost is not evidence. Coverage, gram determinism, picked-SKU
   audit, and bad-SKU scans are the evidence.

## Workstreams

### 1. Source Classification and Reclassification

Purpose: make the retail database carry the correct food identity before the
planner sees it.

Files:

- `recipe_pricing/reclassify_canonical_paths.py`
- `recipe_pricing/quarantine_blocklisted_skus.py`
- `recipe_pricing/non_food_blocklist.txt`
- `recipe_pricing/htc_cp_overrides.csv`
- `recipe_pricing/canonical_path_aliases.csv`
- `recipe_pricing/concept_resolution_overrides.csv`

Rules:

- Move food misroutes to the correct food path.
- Move actual non-food to `Non-Food > ...`.
- Re-encode after every path move.
- Do not solve food-form problems by hiding SKUs in quarantine.

Current known repaired classes:

- canned chicken no longer prices raw chicken breast,
- mozzarella blend no longer prices plain mozzarella,
- Smart Balance cooking-oil blend moved to margarine,
- fresh jalapenos price as fresh jalapenos, not jarred sliced jalapenos,
- vegetable suet prices as shortening, not bird-feed suet,
- fresh cilantro prices through the produce cilantro pool, not pantry spices,
- Comet cleaning powder is `Non-Food > Household` with HTC `N0000009`, not a
  seasoning concept,
- cooking wine prices as cooking wine, not drink/slush mix,
- fresh tomatoes moved out of canned tomato pools,
- canned/instant potatoes moved out of fresh potatoes,
- Burpee seed packets and kitchenware moved out of food paths,
- frozen hash browns route to hash browns, not grain blend,
- red licorice routes to licorice candy, not grain blend,
- sweet red bean paste no longer buys fruit preserves,
- red wine routes to cooking wine, not slush/drink mix,
- goat treats moved out of licorice candy.

Verification:

```bash
python3 recipe_pricing/reclassify_canonical_paths.py --dry-run
python3 recipe_pricing/quarantine_blocklisted_skus.py --dry-run
```

Acceptance:

- Reclassify dry-run is `0` unless intentionally applying a reviewed batch.
- Quarantine dry-run is `0`.
- Any proposed quarantine row must be actual non-food, not misplaced food.

### 2. Bridge Rebuild

Purpose: rebuild recipe concepts, priced concepts, and resolution from source.

Commands:

```bash
python3 planner/scripts/build_recipe_concept_grams.py
python3 planner/scripts/build_concept_index.py
python3 planner/scripts/build_concept_resolution.py
rm -f planner/data/tensor_cache/ingredient_index.pt \
      planner/data/tensor_cache/template_tensors.pt \
      planner/data/tensor_cache/source_hashes.json \
      planner/data/tensor_cache/recipe_db_tensors.pt
cd planner && python3 build_concept_tensor_cache.py
```

Verification:

- `build_concept_tensor_cache.py` must report excluded partial-unresolved
  recipes.
- It must not silently drop unresolved ingredient lines while keeping the
  recipe.
- `concept_index.json` must contain no known non-food contamination terms in
  active food concepts.

Current expected cache behavior:

- partial unresolved recipes excluded: about `26k`
- no-resolved recipes excluded: about `9`
- final planner recipe pool: about `379k`
- known warning to investigate: `Protein sources: 0 classified`

### 3. Gram Determinism

Purpose: stop equivalent recipe quantities from drifting across the corpus.

Primary audit:

```bash
python3 recipe_pricing/audit_gram_determinism.py
```

Cause audit:

```bash
python3 recipe_pricing/audit_gram_drift_causes.py --limit 300
```

Current baseline:

- normalizer dry-run changes: `0`
- temperature quantity repairs: `0`
- drifted main `(item, qty, unit)` tuples: `12,095`
- affected lines from main drift: `107,523`
- package-unit rows audited separately: `147,366`
- density-state rows audited separately: `744,252`
- compound-quantity rows audited separately: `2,126`
- quantity-repair rows audited separately: `3,791`
- `1 tsp salt` and `0.5 tsp salt` are deterministic.
- temperature parser artifacts such as `1 cup water (70-80°F)` are restored
  from `grams_blob`.
- Top-300 drift root causes are now written to
  `recipe_pricing/audit_gram_drift_causes.csv` and
  `recipe_pricing/audit_gram_drift_cause_examples.csv`.
- Current top-300 cause totals by affected lines:
  - no matching SR28 or reviewed household portion: `9,004`
  - SR28 bridge probably points to wrong food: `3,008`
  - no SR28 bridge: `1,453`
  - SR28 food has no portions: `396`
  - reviewed household portion already applied: `215`
  - already equal to SR28 expected: `175`
  - unit unsupported by SR28 normalizer: `137`
  - already equal to reviewed expected: `85`
  - bridge name safety skip: `28`

Fix direction:

- Repair `recipe_pricing/normalize_grams_to_sr28.py`.
- Run `recipe_pricing/normalize_grams_modal_deterministic.py`.
- Run `recipe_pricing/repair_temperature_quantity_grams.py` after modal
  normalization.
- Repair high-volume ingredient-to-SR28 bridge errors before normalizing:
  examples include `chili powder -> Chili, no beans, canned entree`,
  `cayenne pepper -> Pepper, banana, raw`, `bacon -> Bacon, meatless`,
  `orange juice -> apple/grape juice blend`, and
  `cinnamon stick -> ground cinnamon`.
- Fix the SR28 name-safety check so singular/plural and safe compound matches
  like `carrot -> Carrots, raw`, `green onion -> spring onions/scallions`,
  and `breadcrumbs -> Bread, crumbs` do not get skipped.
- Add reviewed derived household portions when SR28 has adjacent evidence but
  not the exact unit, e.g. garlic tbsp from SR28 tsp/clove, brown sugar tbsp
  from SR28 tsp/cup, cornstarch tsp/tbsp from SR28 cup, and margarine cup/tbsp
  from SR28 tsp/stick.
- Stop over-broad skip patterns from bypassing deterministic household-unit
  rules.
- Prefer reviewed SR28/household-unit rules for common units.
- Preserve explicit package-weight and recipe-specific gram evidence.

Release gate:

- `1 tsp salt == 6g` everywhere unless the line is explicitly not consumed.
- `0.5 tsp salt == 3g` everywhere unless explicitly not consumed.
- Top 100 SR28-present drift tuples must be fixed or reviewed with a
  documented cause in `audit_gram_drift_causes.csv`.
- Picked-plan huge-gram flags must be explainable cooking/process liquid, not
  parser blow-outs.

### 4. Target Plan Run

Command:

```bash
HESTIA_BEAM_K=50 python3 planner/scripts/multi_week_ours.py \
  --weeks 12 \
  --people 4 \
  --cal 2000 \
  --mode thrifty \
  --protein-pct 15 \
  --leftover-pct 0.75 \
  --out /tmp/multi_week_ours_12w_release_candidate.json
```

Verification:

```bash
python3 recipe_pricing/picked_recipe_audit.py \
  /tmp/multi_week_ours_12w_release_candidate.json

python3 recipe_pricing/verify_plan_bad_skus.py \
  /tmp/multi_week_ours_12w_release_candidate.json

python3 recipe_pricing/htc_coverage_audit.py
python3 recipe_pricing/audit_gram_determinism.py
```

Acceptance:

- Plan config in JSON exactly matches the target household config.
- `ingredient_purchases` exists for every week.
- `NO_RESOLUTION == 0` in picked recipe audit.
- Bad-SKU scan returns `0`.
- No known junk SKU class appears in actual purchases.
- Whole-cart cost is reported and equals the shopping-list cost basis.

Bad-SKU scan terms must include at minimum:

- `mozzarella blend`
- `smart balance`
- `strawberry applesauce`
- `fat-free mozzarella`
- `revlon`
- `lip oil`
- `vitamin e oil`
- `canned chicken`
- `starkist`
- `breyers`
- `nature's song`
- `bird`
- `burpee`
- `ceramic`
- `mug`
- `sauce pan`
- `drink pouch`
- `icee slush`

### 5. Picked-SKU Audit Review

Primary output:

- `recipe_pricing/picked_recipe_audit_lines.csv`
- `recipe_pricing/picked_recipe_audit_recipes.csv`
- `recipe_pricing/picked_recipe_audit_flags.csv`

Current final baseline:

- `1,875` picked ingredient audit lines
- `168` `RESOLVED_LOSSY`
- `83` `TINY_POOL`
- `47` `SKU_NAME_OFF`
- `7` `IMPOSTER_TOKEN`
- `0` `NO_RESOLUTION`

Interpretation:

- `RESOLVED_LOSSY` is mostly `path_only`; it is not automatically wrong, but
  it is still technical debt.
- `SKU_NAME_OFF` contains false positives such as `Breadcrumbs` vs `Bread
  Crumbs`, but every row must be reviewed.
- `IMPOSTER_TOKEN` is acceptable only when the recipe itself asks for that
  identity, such as imitation crab.
- `HUGE_GRAMS` is acceptable only for explicit cooking/process water or a
  reviewed recipe-scale line.

Current disposition:

- Bad-SKU scan over actual purchases returns `0`.
- `SKU_NAME_OFF` and `IMPOSTER_TOKEN` remain review queues, not release proof.
- No known high-severity mismatch is present in the actual cart after fixing
  cilantro routing and moving Comet cleaning powder to non-food household.

Release gate:

- No high-severity picked-SKU mismatch.
- Every remaining `SKU_NAME_OFF`, `HUGE_GRAMS`, and `IMPOSTER_TOKEN` has a
  reviewed disposition.

### 6. Coverage Audit

Primary output:

- `recipe_pricing/htc_coverage_audit.csv`
- `recipe_pricing/htc_coverage_summary.txt`

Current final baseline:

- recipe-side concepts: `7,687`
- recipe-use volume: `4,489,952`
- GREEN: `755` concepts, `46.7%` of recipe-use volume
- YELLOW: `4,383` concepts, `30.0%` of recipe-use volume
- RED: `2,549` concepts, `23.2%` of recipe-use volume

Most remaining RED volume is household-unit/form variability and missing SR28
bridge evidence. The previous Comet non-food RED row is gone; the same
seasoning concept now picks onion powder.

Release gate:

- Coverage summary must be regenerated after every bridge or gram change.
- Top RED rows by recipe-use volume must be reviewed in order.
- RED rows caused by gram drift cannot be waived until the gram determinism
  workstream is complete.

### 7. Hestia A/B Comparison

Purpose: catch behavioral differences against the existing Hestia planner.

Config-matched outputs:

- Native Hestia JSON:
  `planner/data/multi_week_hestia_12wk_config_matched.json`
- Native Hestia total: `$1,354.96`
- Native Hestia average week: `$112.91`
- Native Hestia unique recipes: `246`
- Our final total: `$936.55`
- Our final average week: `$78.05`
- Per-recipe comparison:
  `planner/data/planner_pick_compare_config_matched.md`
- Per-recipe aggregate over our final picked recipes:
  ours `$3,037.73`, Hestia `$4,948.52`, delta `-$1,910.79`

Verification commands:

```bash
python3 planner/scripts/run_hestia_12wk.py \
  --out planner/data/multi_week_hestia_12wk_config_matched.json
python3 planner/scripts/compare_planner_picks.py \
  --plan-ours /tmp/multi_week_ours_12w_codex_final.json \
  --plan-hes planner/data/multi_week_hestia_12wk_config_matched.json \
  --top 20 \
  --out planner/data/planner_pick_compare_config_matched.md
```

Acceptance:

- Same household and scoring config on both sides.
- Whole-cart costs compared, not only line-attributed costs.
- Top divergences reviewed for grams, package math, and SKU identity.

## Release Candidate Checklist

Run this checklist in order:

```bash
python3 recipe_pricing/reclassify_canonical_paths.py --dry-run
python3 recipe_pricing/quarantine_blocklisted_skus.py --dry-run
python3 planner/scripts/build_recipe_concept_grams.py
python3 planner/scripts/build_concept_index.py
python3 planner/scripts/build_concept_resolution.py
rm -f planner/data/tensor_cache/ingredient_index.pt \
      planner/data/tensor_cache/template_tensors.pt \
      planner/data/tensor_cache/source_hashes.json \
      planner/data/tensor_cache/recipe_db_tensors.pt
cd planner && python3 build_concept_tensor_cache.py && cd ..
HESTIA_BEAM_K=50 python3 planner/scripts/multi_week_ours.py \
  --weeks 12 --people 4 --cal 2000 --mode thrifty \
  --protein-pct 15 --leftover-pct 0.75 \
  --out /tmp/multi_week_ours_12w_release_candidate.json
python3 recipe_pricing/picked_recipe_audit.py \
  /tmp/multi_week_ours_12w_release_candidate.json
python3 recipe_pricing/verify_plan_bad_skus.py \
  /tmp/multi_week_ours_12w_release_candidate.json
python3 recipe_pricing/htc_coverage_audit.py
python3 recipe_pricing/audit_gram_determinism.py
```

The release candidate is blocked if any of these are true:

- quarantine dry-run proposes food rows,
- reclassify dry-run has unexpected rows,
- tensor cache keeps recipes with partial unresolved required concepts,
- target plan JSON lacks actual SKU purchases,
- picked audit has `NO_RESOLUTION`,
- bad-SKU scan finds known junk,
- gram determinism audit still shows unreviewed high-volume drift,
- Hestia comparison is run on a different config but presented as proof.

## Immediate Next Tasks

1. Investigate why tensor-cache rebuild reports `Protein sources: 0
   classified`.
2. Continue gram determinism on remaining explained drift buckets such as
   bouillon granules, bacon bits, paprika cup, potato chips cup, flax seed,
   goat cheese, baby carrots, powdered milk, and blue cheese.
3. Improve audit token matching for known false positives and real precision
   gaps: onion powder at generic seasoning, breadcrumbs, cucumbers, apples,
   cornmeal, oatmeal, jalapenos, tuna forms, and margarine/spread.
4. Reduce picked `path_only` rows by adding source corrections or precise
   aliases only where the SKU pool proves the same food identity.
5. Keep `verify_plan_bad_skus.py`, config-matched Hestia comparison, and the
   actual-purchase audit in the release checklist.
