# Portion Bridge Validation

This note records the current validation commands and the contract for calling
gram drift fixed.

## Required Checks

Run these from the repository root after changing recipe grams, household
portion rules, HTC routing, concept resolution, or planner package selection.

```bash
python3 recipe_pricing/repair_total_weight_range_grams.py
python3 recipe_pricing/normalize_grams_to_sr28.py
python3 recipe_pricing/normalize_grams_modal_deterministic.py --all-deterministic-drift
python3 recipe_pricing/audit_gram_determinism.py \
  --fail-on-drift \
  --max-drift-tuples 0 \
  --max-high-ratio-tuples 0
python3 recipe_pricing/audit_gram_drift_causes.py
python3 recipe_pricing/preflight_data_contract.py
python3 -m unittest implementation.tests.test_form_facet_audit -v
python3 -m unittest implementation.tests.test_household_free -v
python3 planner/scripts/audit_form_facet_intents.py \
  planner/data/config_runs/p4_2000_thrifty_l75_p15_pork_chorizo_fix.json
```

## Current State

- Deterministic gram drift gate: PASS, 0 drifted `(item, qty, unit)` tuples across 4,729,696 recipe lines.
- Separately audited non-deterministic rows: package/serving units 147,895 rows; density/form-state rows 847,764 rows; compound quantities 2,364 rows; repaired quantity rows 3,926 rows.
- Full data preflight: PASS. Recipe htc/full mismatches 0; product htc/full mismatches 0; full encoder mismatches 0 for 4,721,782 checked recipe rows and 161,935 checked product rows.
- Selected family plan form/facet audit: 0 findings across 2,268 selected-recipe lines.
- Family config check (`4 people`, `2000 cal`, `thrifty`, `15% protein`, `75% leftovers`, `12 weeks`): `$1,140.25` total, `$95.02/week`, `$3.39/person/day`, average protein `16.6%`.
- Household-free water tests: pass. Recipe-side tap water and ice are zero-cost; watermelon and water chestnuts are not treated as water.
- Head lettuce retail bridge: generic `lettuce,head` is 453.6g, matching a 1 ct retail lettuce head/package.
- Active reviewed portion authority: `recipe_pricing/reviewed_household_portions.csv`.
- Legacy compatibility file: `implementation/reviewed_household_unit_gram_rules.csv`; preflight requires every approved legacy rule to be represented in the active authority.

## What Changed

- `recipe_pricing/consolidate_reviewed_portions.py` migrated the remaining approved legacy household-unit rules into the active reviewed portion authority.
- `recipe_pricing/repair_total_weight_range_grams.py` restores rows like `about 1.5 to 2 pounds total` from `grams_blob` before SR28/modal normalization. This closes the bug where a displayed total package weight collapsed to one parsed lower-bound piece weight.
- `recipe_pricing/normalize_grams_modal_deterministic.py --all-deterministic-drift` now closes every deterministic drift bucket that the audit would fail. If an SR28 or reviewed-household value exists in a bucket, that anchor wins. Otherwise the row is marked `deterministic_modal_normalized` so generated consistency repairs are not confused with USDA authority.
- `recipe_pricing/normalize_grams_to_sr28.py` handles no-unit count lines when there is an exact reviewed count/each rule, e.g. `1 egg white`.
- `serving` and `servings` are no longer treated as deterministic household units. They are audited with variable package units because a serving has no universal gram value.

## Rule

Do not call gram drift solved until `audit_gram_determinism.py` is clean or
every remaining drift bucket is explicitly waived with a reviewed reason. A
single plan-level spot check is not enough.
