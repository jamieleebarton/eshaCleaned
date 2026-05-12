# Current Status

As of `2026-04-25`, the current whole-corpus assignment artifact is:

- [product_to_best_esha_full_map.csv](/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/product_to_best_esha_full_map.csv:1)
- [product_to_best_esha_full_map_summary.json](/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/product_to_best_esha_full_map_summary.json:1)

Fixy overlay cleanup was added after this baseline. The operator notes, output map recommendations, and rerun commands are documented in:

- [FIXY_DONE_CLEANUP.md](/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/FIXY_DONE_CLEANUP.md:1)

Current recommendation: evaluate `implementation/output/product_to_best_esha_full_map.vFixyFlagged.csv` as the conservative next candidate. It keeps coverage intact, applies high-confidence Fixy recoveries/remaps, and marks suspicious assignments with `fixy_cleanup_*` columns instead of blanking them.

## Where We Are

The whole-corpus matcher was patched to stop forcing matches on generic category/family overlap alone.

The new invariant is:

> If the product has a recognizable identity token, a candidate with a different recognizable identity token must be rejected, even if category/family overlap is strong.

That change is implemented in:

- [build_product_to_best_esha_full_map.py](/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/build_product_to_best_esha_full_map.py:21)
- [build_esha_code_query_packs.py](/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/build_esha_code_query_packs.py:743)

Current counts from the refreshed summary:

- `462,646` total products
- `156,418` legacy assignments kept after validation
- `255,667` fallback assignments
- `50,561` unassigned products

This is intentionally stricter than the earlier forced-coverage run. The old forced map covered everything but was lying. The current map leaves uncertain rows unassigned instead of shoving them onto nonsense ESHA codes.

## What Was Fixed

These exact failure classes were fixed in the scorer:

- `MUSHROOM PIECES & STEMS` no longer lands on `7867 Artichoke, hearts, canned, pieces`
- `BABY ARUGULA` no longer lands on `5443 Squash, zucchini, baby, fresh`
- `HABANERO PEPPER JELLY` no longer lands on `46801 Applesauce, original`
- `FAT FREE MILK` no longer gets forced onto `7 Buttermilk, low fat, cultured`

Current refreshed-file behavior:

- `MUSHROOM PIECES & STEMS` -> `6276 Mushrooms, pieces & stems, canned`
- `BABY ARUGULA` -> `6032 Greens, arugula, leaf, fresh`
- `BABY KALE` -> `5208 Cabbage, kale, fresh, chopped`
- `EVAPORATED MILK` -> `20952 Milk, evaporated`
- `FAT FREE MILK` -> no assignment
- `HABANERO PEPPER JELLY` -> no applesauce leak; currently routes to jelly-family code `90883`

Code-level collapse checks:

- `7867 Artichoke, hearts, canned, pieces`: `0`
- `46801 Applesauce, original`: `0`
- `7 Buttermilk, low fat, cultured`: `16`
  - current survivors are actual buttermilk-family rows
- `5443 Squash, zucchini, baby, fresh`: `3`
  - current survivors are actual baby zucchini/squash rows

## What Changed Technically

The fallback matcher now:

- uses canonical surfaces from [canonical_surface_normalized_with_product_proxies.csv](/Users/jamiebarton/Desktop/esha_audit_bundle/canonical_surface_normalized_with_product_proxies.csv:1) to recover identity anchors
- strips weak tokens like `pieces`, `stems`, `baby`, `original`, `naturally`, `fat`, `whole`, `fresh`, `canned` from identity scoring
- requires meaningful identity overlap before a fallback candidate is accepted
- revalidates legacy `product_to_best_esha_map.csv` rows instead of trusting them blindly
- penalizes explicit state mismatches like `cooked`, `frozen`, `dried`, `evaporated`, `condensed`

The applesauce family was also persisted into the card builder:

- `46797 Applesauce, naturally sweetened`
- `46799 Applesauce, cinnamon`
- `46801 Applesauce, original`
- `46806 Applesauce, natural, no sugar added, org`

Those codes now query/guard on `applesauce` instead of generic poison terms like `original`, `naturally`, or `cinnamon` by themselves.

## What Still Needs To Be Done

The file is safer, but it is not final truth yet.

Highest-priority remaining work:

1. Milk subtype routing
   - `filled milk`
   - `goat milk`
   - `condensed milk`
   - `buttermilk` variant cleanup
   - plant milk / creamer / shake separation

2. Produce leaf specificity
   - kale vs salad kits
   - baby produce vs mixed greens
   - produce blends vs single-ingredient produce

3. Jelly / preserve / spread routing
   - pepper jelly
   - jalapeno / habanero jelly
   - fruit preserves vs applesauce

4. Category-singularity cleanup
   - keep driving fixes off:
     - [esha_code_category_aggregation.csv](/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/esha_code_category_aggregation.csv:1)
     - [esha_single_category_fix_queue.csv](/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/output/esha_single_category_fix_queue.csv:1)

5. Unassigned reduction
   - there are still `50,561` unassigned products
   - the correct next step is targeted routers, not another forced-coverage fallback

## What Not To Do

- Do not trust raw category/family overlap without identity overlap.
- Do not trust legacy best-map rows without revalidation.
- Do not use generic modifiers like `pieces`, `baby`, `original`, `naturally`, `fat`, `fresh`, `whole`, `canned` as assignment anchors.
- Do not rerun a forced-coverage full map that assigns every product no matter what.

## Verification

Regression coverage for the new invariant is in:

- [test_build_product_to_best_esha_full_map.py](/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/tests/test_build_product_to_best_esha_full_map.py:1)
- [test_build_esha_code_query_packs_retail_cleanup.py](/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/tests/test_build_esha_code_query_packs_retail_cleanup.py:1)

Current focused regression result:

- `34` tests passed for the whole-map and card-builder coverage touched in this pass.
