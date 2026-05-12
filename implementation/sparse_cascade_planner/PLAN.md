# Sparse Cascade Planner Bring-Up Plan

## Current Build Status

- Local sparse cascade artifacts are built under `implementation/output/sparse_cascade_planner/`.
- The recipe source is `data/recipe_qa.db`; the current recipe-native export has 472,371 rows from 509,509 source recipes.
- The package DB has 13,688 package rows across 1,292 calculator-native ingredient keys.
- The tensor cache has 393,305 planner-ready recipes and 4,201 ingredient keys.
- The one-week local smoke runner passes with budget preset output in `local_sparse_plan.smoke.json`.
- Product leak verification now allowlists banana nut muffin titles only for `ESHA:18966` and `FNDDS:58610005`; walnut/generic muffin leaks remain blocked.
- Full rebuild command: `python3 implementation/sparse_cascade_planner/rebuild_local_sparse_cascade.py`.
- Default-priced ingredients are disallowed. `build_recipe_qa_native_recipes.py` now excludes recipes with any ingredient key missing from the package DB unless explicitly run with `--allow-default-priced-ingredients`.

## Current Findings

- The existing audit runner at `implementation/run_sparse_cascade_purchase_audit.py` does not run a local planner. It imports the Hestia planner from `/Users/jamiebarton/Desktop/Hestia/api/hestia/sparse_cascade.py`, then uses this bundle's calculator and verification tools to audit the resulting recipes and cart lines.
- The Hestia planner is tensor-cache based. Its default sources are `recipes2.csv`, `food_packages_final.db`, and `data/tensor_cache/*.pt`. That tensor path is useful as a design reference, not the source of truth for this bundle.
- This bundle's stronger recipe source is `data/recipe_qa.db`: 509,509 cleaned recipes with gram-backed `ingredients_json`, plus 10,291 `recipe_item_overrides` rows for ambiguity cleanup.
- The local recipe funnel exists in the clean workspace as `/Users/jamiebarton/Desktop/clean/implementation/output/recipe_funnel.db`. This bundle has the scripts to rebuild it, but the DB is not currently present under `implementation/output/`.
- The local Walmart/Kroger price universe is `recipe_pricing/data/priced_products_tagged.db`: 63,670 tagged rows, sourced from a larger API cache of 217,661 rows in `/Users/jamiebarton/Desktop/clean/recipe_pricing/data/api_cache_products.csv`.
- `retail_mapper/v2/consensus_full_corpus_audit.csv` is not safe to trust raw for planner pricing or nutrition. Example: `BANANA NUT MUFFIN` has `fndds_desc=banana muffin mix`, while the ESHA row says `Muffin, banana nut`. The planner should only use consensus rows after restricting to the Walmart/Kroger cache subset and passing identity/form gates.

## Source Of Truth Decisions

1. Recipe source: `data/recipe_qa.db`.
2. Recipe normalization source: local funnel artifacts rebuilt from `recipe_qa.db`, not `recipes2`.
3. Nutrition/calculation source: this bundle's calculator path, especially `surface_lab_calculator.calculate_lab`.
4. Product source: Walmart/Kroger API cache and `recipe_pricing/data/priced_products_tagged.db`.
5. Consensus source: candidate enrichment only, filtered to products that appear in the Walmart/Kroger cache and rejected when title/form conflicts with the mapped FNDDS/ESHA identity.
6. Tensor design reference: Hestia `sparse_cascade.py` and its tensor cache shape, not its older `recipes2` data.

## Build Plan

### Phase 1: Inventory And Localize Inputs

- Create an inventory script that writes `implementation/output/sparse_cascade_planner/source_inventory.json`.
- Verify schemas and counts for:
  - `data/recipe_qa.db`
  - `implementation/output/recipe_funnel.db` or rebuilt equivalent
  - `recipe_pricing/data/priced_products_tagged.db`
  - Walmart/Kroger API cache
  - `retail_mapper/v2/consensus_full_corpus_audit.csv`
  - `data/fndds/*.csv`
- Copy or rebuild missing local artifacts instead of silently falling back to `/Users/jamiebarton/Desktop/clean`.

### Phase 2: Build Our Recipe Ingredient Corpus

- Read `recipe_cleaned.ingredients_json` from `data/recipe_qa.db`.
- Apply `recipe_item_overrides` before calculator resolution.
- Drop recipes with any resolved ingredient key that is not priced by the Walmart/Kroger package DB. The local planner must not buy `$3/kg` synthetic defaults.
- Emit one normalized recipe ingredient table with:
  - recipe id/title
  - original display text
  - overridden item/base product
  - grams
  - normalized shopping item
  - calculator nutrition anchor
  - calculator shopping canonical
  - non-food/no-purchase flags

### Phase 3: Build Our `fndds_dict`

- Use `data/fndds/MainFoodDesc16.csv`, `FNDDSSRLinks.csv`, `FNDDSIngred.csv`, and `fndds_nutrient_lookup.csv`.
- Populate per-recipe dictionaries from calculator-resolved recipe lines:
  - prefer ESHA keys when confidently available
  - keep SR28 fallback where calculator already accepts it
  - keep FNDDS keys only when the calculator or reviewed bridge supports it
- Store both native keys and an FNDDS-compatible projection so the sparse planner can still use FNDDS prefix rules for allergens/protein source.

### Phase 4: Build The Product/Price Universe

- Start from Walmart/Kroger cache only.
- Build a cache universe table keyed by `(source, upc, name, grams, cents, search_term)`.
- Build `product_identity_bridge.csv` from UPC/title-level product identities before package DB ingestion. This keeps repeated cache UPCs from inheriting whichever search term found them.
- Join to existing priced tags where available.
- Join to consensus by FDC/UPC only when possible; otherwise use consensus only through search-term/canonical matching, never as a direct truth source.
- Apply product gates:
  - calculator `_review_products`
  - `price_product_filters.is_retail_price_reject`
  - identity mismatch checks like muffin vs muffin mix
  - wrong-form checks for prepared/mix/snack/substitute products

### Phase 5: Tensor Cache

- Write tensors under `implementation/output/sparse_cascade_planner/tensor_cache/`.
- Target artifacts:
  - `ingredient_index.pt`
  - `recipe_db_tensors.pt`
  - `package_index.pt`
  - `source_hashes.json`
  - `ingredient_meta.json`
- Follow Hestia's sparse shape: recipe ids, ingredient indices, ingredient grams, nutrition, food groups, servings, nonzero counts, and protein-source classification.

### Phase 6: Local Planner Wrapper

- Add a local runner that points the Hestia sparse cascade classes at this bundle's generated tensor cache and package DB.
- Keep the first runner small: one-week, CPU/MPS-safe, deterministic config, and explicit output JSON.
- Do not let runtime planner calls perform string search. Product choice should come from the prebuilt Walmart/Kroger package universe.

### Phase 7: Verification Gates

- Reuse `implementation/plan_verification_suite.py` and `implementation/run_sparse_cascade_purchase_audit.py` classification logic.
- Add fixture blockers:
  - banana nut muffin must not map to banana muffin mix unless the recipe line actually says mix
  - cow milk must not pick plant milk
  - raw chicken breast must not pick deli/prepared chicken
  - potato must not pick chips/skins/snacks
  - butter must not pick fruit/nut/body butter
- Produce a summary with coverage, unresolved recipe grams, package coverage by store, and top rejected consensus/cache mappings.

## First Implementation Step

Build `source_inventory.py` in this folder and run it. The result should make missing local artifacts explicit before tensor work starts.
