# Data Authority Contract

This repo now has an explicit contract for planner/pricing data inputs.

## File Roles

The machine-readable file list is:

```bash
recipe_pricing/data_authority_manifest.csv
```

Roles:

- `SOURCE`: external/raw authority such as USDA SR28/FNDDS files.
- `REVIEWED_OVERRIDE`: human-reviewed corrections or intent overrides.
- `GENERATED`: derived artifacts. These may be rebuilt, but scripts must not treat stale derived columns as source truth when they can recompute them.

The active household portion authority is:

```bash
recipe_pricing/reviewed_household_portions.csv
```

`implementation/reviewed_household_unit_gram_rules.csv` is legacy compatibility only. `recipe_pricing/preflight_data_contract.py` fails if an approved legacy rule is missing from the active authority.

## Enforcement

Run:

```bash
python3 recipe_pricing/preflight_data_contract.py
```

It fails on:

- `recipes_unified.htc_code` disagreeing with `recipes_unified.htc_full_code`.
- `recipes_unified.htc_code` disagreeing with the current encoder.
- `priced_products.htc_code` disagreeing with `priced_products.htc_full_code`.
- coded product `htc_code` / `htc_form_code` disagreeing with the current encoder.
- missing active reviewed portion authority rows.
- missing active manifest paths or invalid file roles.

Current verified result:

```text
PASS: data authority preflight
recipe htc/full prefix mismatches: 0
recipe encoder mismatches: 0 across 4,721,782 checked rows
product htc/full prefix mismatches: 0
product encoder mismatches: 0 across 161,935 checked rows
legacy portion rules missing from active authority: 0
active reviewed portion keys: 2,689
```

## Rebuild Order

Use the ordered runner:

```bash
python3 planner/scripts/rebuild_pricing_pipeline.py
```

To inspect the order without running it:

```bash
python3 planner/scripts/rebuild_pricing_pipeline.py --dry-run
```

Required order:

1. Consolidate reviewed portions.
2. Reclassify product canonical paths.
3. Re-encode product HTC identity/form/full codes.
4. Re-tag recipe `htc_code` / `htc_full_code`.
5. Restore display total-weight range grams from `grams_blob`.
6. Apply SR28/reviewed gram normalization.
7. Apply deterministic gram drift normalization.
8. Fail if deterministic gram drift remains.
9. Run data preflight.
10. Rebuild concept index.
11. Rebuild recipe concept grams with form-aware recipe HTC.
12. Rebuild concept resolution.
13. Audit concept package classes.
14. Rebuild tensor cache.
15. Run data preflight again.

Do not run `normalize_htc_at_path.py` in this contract path; it mutates product form codes away from the current encoder output and would fail preflight.
