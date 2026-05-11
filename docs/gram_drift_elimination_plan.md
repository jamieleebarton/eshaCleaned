# Gram Drift Elimination Plan

## Goal

Recipe household portions must be deterministic. For any deterministic portion
key, the same food/form/unit/quantity must resolve to one gram value. If two
values appear, either the identity/form key is wrong or the SR28/FNDDS/reviewed
portion bridge is missing or wrong.

No blocklists or path-conditional reject lists are acceptable fixes for this
class of issue. Correct the food identity, HTC/form, canonical path, FDC bridge,
or reviewed household portion.

## Current Evidence

Latest deterministic audit:

```bash
python3 recipe_pricing/audit_gram_determinism.py
```

Result:

- 4,729,696 recipe lines scanned.
- 178,167 main deterministic `(ingredient_item, qty, unit)` keys.
- 11,846 drifted deterministic tuples.
- 96,069 recipe lines affected by drift.
- 3,727 high-ratio drift tuples at `ratio >= 1.5`, affecting 35,401 lines.
- 8,119 lower-ratio drift tuples below `1.5`, affecting 60,668 lines.
- 198 drift tuples already contain an SR28/reviewed source somewhere in the
  bucket, which means mixed source precedence still exists.

Latest cause replay for the top 300 high-ratio tuples:

```bash
python3 recipe_pricing/audit_gram_drift_causes.py --limit 300
```

Line-weighted causes:

- `no_matching_sr28_or_reviewed_portion`: 8,715 lines.
- `sr28_bridge_probably_wrong_food`: 2,955 lines.
- `no_sr28_bridge`: 1,615 lines.
- `sr28_food_has_no_portions`: 305 lines.
- `bridge_name_safety_skip`: 109 lines.
- `unit_not_supported_by_sr28_normalizer`: 28 lines.

Examples:

- `goat cheese, 0.5 cup`: no matching reviewed/SR28 portion.
- `fresh ground pepper, 0.5 tsp`: bridge points to raw banana pepper.
- `kalamata olives, 0.5 cup`: no matching reviewed/SR28 portion.
- `baby carrots, 2 cup`: no matching reviewed/SR28 portion.
- `onion flakes, 1 tbsp`: bridge points to taco seasoning mix.

Planner evidence after today's package fixes:

```bash
python3 planner/scripts/audit_plan_multipacks.py \
  planner/data/fix_try12_p4_2000_thrifty_l75_p35_12wk_multipackfix.json \
  --out implementation/output/fix_try12_thrifty_p35_multipack_audit.csv
```

Result:

- 54 selected count/multipack packages audited.
- 0 multipack package-gram flags.
- Form/facet audit: 0 findings across 2,774 selected-recipe lines.
- Bad SKU audit: 0 hits across 584 purchase rows.
- Reasonableness package flags: 0.

## Root Cause

`planner/scripts/build_recipe_concept_grams.py` aggregates
`grams_resolved` from `recipe_mapper/v1/output/recipes_unified.csv` into
planner concept grams without enforcing gram determinism first. That means
blob/parser gram values can still enter the planner when the SR28/FNDDS/reviewed
household portion bridge is absent, wrong, or not selected.

The planner is downstream. The fix belongs at the recipe portion bridge layer,
then the planner artifacts must be rebuilt.

## Fix Plan

1. Add a strict validation gate.

   Create a strict mode for the gram determinism audit or a new
   `recipe_pricing/validate_gram_determinism.py` wrapper that exits nonzero
   when main deterministic drift remains. It must report:

   - total drift tuples;
   - affected lines;
   - high-ratio drift tuples;
   - SR28/reviewed mixed-source tuples;
   - top causes from `audit_gram_drift_causes.py`.

   Package units, explicit state/form exceptions, compound quantities, and
   repaired parser rows stay in separate audit files. They are not allowed to
   hide main deterministic drift.

2. Fix identity bridges first.

   Correct wrong bridges in these files before adding new reviewed portions:

   - `recipe_pricing/ingredient_fdc_overrides.csv`
   - `recipe_pricing/htc_to_fdc.csv`
   - upstream HTC tagging if the bad FDC comes from the code rather than an
     item override.

   First target examples:

   - `fresh ground pepper` must bridge to pepper/spice, not raw banana pepper.
   - `red pepper` must distinguish spice/flake/powder from fresh pepper.
   - `onion flakes` must bridge to dried onion, not taco seasoning mix.
   - `ginger powder` must bridge to dry ground ginger, not raw ginger root.
   - `instant espresso powder` must bridge to coffee/espresso powder, not
     gravy.
   - `chicken bouillon` must bridge to bouillon, not raw ground chicken.

3. Fill missing household portions from SR28/FNDDS or reviewed evidence.

   Add reviewed rows to `recipe_pricing/reviewed_household_portions.csv` only
   when SR28/FNDDS lacks a usable household modifier or when a derived adjacent
   portion is needed. Each row needs evidence and reason.

   First targets:

   - goat cheese cup/tbsp, with crumbled/soft/hard state separated where needed;
   - kalamata olives cup;
   - potato chips cup, with crushed state explicit;
   - baby carrots cup;
   - nutritional yeast cup/tbsp;
   - powdered/dry milk tbsp;
   - blue cheese tbsp, with crumbled state explicit;
   - dill tsp, fresh versus dried separated;
   - vital wheat gluten tbsp;
   - gelatin tbsp, unflavored dry versus dessert mix separated.

4. Make portion state part of the deterministic key.

   If the display says `crumbled`, `crushed`, `packed`, `powdered`, `whole`,
   `kosher`, `table`, `fresh`, `dried`, `shredded`, or similar, the normalizer
   must either preserve that state in the item/form key or route it to an
   explicit reviewed portion. Do not let `goat cheese` silently mix block,
   soft, hard, and crumbled grams.

5. Re-normalize recipe grams.

   Run the SR28/FNDDS/reviewed normalizer after bridge corrections:

   ```bash
   python3 recipe_pricing/normalize_grams_to_sr28.py
   python3 recipe_pricing/audit_gram_determinism.py
   python3 recipe_pricing/audit_gram_drift_causes.py --limit 300
   ```

   Repeat until:

   - high-ratio deterministic drift is 0;
   - mixed SR28/reviewed versus blob/parser buckets are 0;
   - lower-ratio deterministic drift is 0 or moved into an explicit reviewed
     state/package/compound exception bucket.

6. Rebuild downstream planner artifacts only after gram drift is clean.

   ```bash
   python3 planner/scripts/build_recipe_concept_grams.py
   python3 planner/scripts/build_concept_index.py
   python3 planner/scripts/build_concept_resolution.py
   python3 planner/build_concept_tensor_cache.py
   python3 planner/scripts/multi_week_ours.py \
     --weeks 12 --mode thrifty --cal 2000 --people 4 \
     --protein-pct 35 --protein-floor-mode flat50 \
     --leftover-pct 0.75 \
     --out planner/data/gramfix_p4_2000_thrifty_l75_p35_12wk.json
   ```

7. Validate the rebuilt plan.

   Required checks:

   ```bash
   python3 planner/scripts/audit_plan_multipacks.py \
     planner/data/gramfix_p4_2000_thrifty_l75_p35_12wk.json
   python3 planner/scripts/audit_plan_reasonableness.py \
     planner/data/gramfix_p4_2000_thrifty_l75_p35_12wk.json
   python3 recipe_pricing/verify_plan_bad_skus.py \
     planner/data/gramfix_p4_2000_thrifty_l75_p35_12wk.json
   python3 planner/scripts/audit_form_facet_intents.py \
     planner/data/gramfix_p4_2000_thrifty_l75_p35_12wk.json
   ```

   Spot checks must include:

   - `1 tsp salt` resolves to one default gram value unless the line explicitly
     says kosher/table/sea and that state is encoded.
   - `1 head lettuce` resolves near a whole head/package, not 100 g, and buys
     whole lettuce rather than shredded lettuce.
   - `0.5 cup goat cheese` has one reviewed form-specific value.
   - `0.5 tsp fresh ground pepper` uses a spice/pepper bridge, not fresh pepper.
   - `0.5 cup kalamata olives` has one reviewed value.
   - `2 cup baby carrots` has one reviewed value.

## Acceptance Criteria

- Main deterministic gram drift: 0 tuples.
- High-ratio deterministic gram drift: 0 tuples.
- SR28/reviewed mixed with blob/parser for the same deterministic key: 0 tuples.
- No selected plan multipack/package gram flags.
- No selected plan bad SKU hits.
- No selected plan form/facet findings.
- The family-of-4 12-week plan can be explained from line grams to package
  purchases without hidden free food, wrong package size, or wrong food form.
