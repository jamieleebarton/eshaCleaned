# Consensus Full Corpus Audit

Rows: `462,664`
Unique FDC ids: `462,664`
Duplicate extra rows: `0`
Path defect rows: `0`

## Adopted From Codex

- `take_codex:restore_sauces_salsas_parent`: `21,279`
- `take_codex:restore_spices_seasonings_parent`: `9,126`
- `take_codex:restore_dips_spreads_parent`: `2,434`
- `take_codex:restore_broth_stock_parent`: `1,693`
- `take_codex:title_level_salad_over_dirty_pickle_bfc`: `969`
- `take_codex:actual_churro_product_not_cookie`: `2`

## Consensus Normalizations

- `consensus_normalize:frozen_fruit_to_frozen`: `2,050`
- `consensus_normalize:canned_vegetables_to_pantry`: `259`
- `consensus_normalize:pasta_dinners_to_meal_pasta`: `169`
- `consensus_normalize:frozen_vegetables_to_frozen`: `3`

## Explicitly Kept From Full

- `keep_full:frozen_vegetables_storage_department`: `4,302`
- `keep_full:pasta_dinners_are_meal_pasta_dishes`: `1,494`
- `keep_full:canned_vegetables_stay_pantry`: `524`
- `keep_full:nut_seed_butters_not_dairy_butter`: `463`
- `keep_full:frozen_fruit_storage_department`: `201`
- `keep_full:true_cookies_stay_bakery`: `185`

## Quality Metrics

- `full`: duplicate extra `0`, type echo `420`, BFC-name leaf `659`, path defects `0`
- `codex_first_occurrence`: duplicate extra `0`, type echo `1106`, BFC-name leaf `671`, path defects `0`
- `consensus`: duplicate extra `0`, type echo `428`, BFC-name leaf `662`, path defects `0`