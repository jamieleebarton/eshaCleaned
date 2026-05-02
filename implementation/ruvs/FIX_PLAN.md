# FIX_PLAN — Replace per-canonical filter chain with audit-driven accept

**Last edit:** 2026-05-02 (joining engineer)
**Anchor:** `GOAL.md` ACTIVE PLAN ("Replace the per-canonical filter chain with audit-driven accept").
**Investigation:** `INVESTIGATION_FILTER.md`.
**Hard constraints:** No LLM calls anywhere in this plan. No big-bang rewrite. Every step independently testable. Walmart/Kroger pricing untouched.

This plan ships in numbered steps. Each step is small, independently verifiable, and reversible. Numbers are dependency-ordered (1 → 2 → 3 → ...). Where a step has independent sub-steps, they are lettered (3a, 3b).

---

## Step 1 — Confirm baseline coverage on the four investigation samples

**Files touched:** none (read-only).
**Effort:** S. **Risk:** none (read-only). **Depends on:** nothing.

**Action:** Without changing any code, dump the per-rejection reasons for the four sample canonicals from a fresh calculator run. Today the calculator already records `accepted=N rejected=M` in the `path` field; expose the per-product `reason` string for the rejected products.

**How:** Re-run `api/scripts/run_universe_sweep.py` with a debug flag (or extend the dumper) to emit `rejected_products: [{description, brand, category, reason}]` for any line where `accepted=0`. Save to `api/data/universe_calc.debug.json`.

**Verification:** For canonical `macaroni` (1 1/2 lbs macaroni), the dump must show one of: `combo_or_prepared_product:pasta`, `missing_required_canonical_terms`, or `not_plain_dry_pasta:...`. For `tomato juice`, the dump must show `not_plain_tomato_juice:vegetable` or `tomato_juice_requires_juice_category` for V8/Sacramento/Campbell's. This is the empirical baseline against which Step 4 success is measured.

**Why it's first:** confirms the diagnosis in `INVESTIGATION_FILTER.md` against live data. If the reason strings don't match the analysis, stop and re-investigate before changing code.

---

## Step 2 — Build `canonical_audit_expectation` table from `full_corpus_audit.csv`

**File created:** `Hestia/api/data/canonical_audit_expectation.db`.
**Script created:** `Hestia/api/scripts/build_canonical_audit_expectation.py`.
**Effort:** M. **Risk:** low (additive; no production code reads it yet). **Depends on:** Step 1.

**Action:** For each (`canonical_key`, `fndds_code`) pair the calculator currently knows about (extracted from `surface_lab_calculator.py`'s `SURFACE_*_OVERRIDES`, `_ALIAS` tables, and `canonical_to_esha.csv`), find the dominant `canonical_path` in `full_corpus_audit.csv` for that fndds_code. Populate `canonical_audit_expectation` with the schema in `GOAL.md`'s ACTIVE PLAN. Where multiple canonical_paths tie, pick the one whose `canonical_label` token-overlaps the canonical_key.

**Verification:**
- `canonical_audit_expectation` must contain rows for at least: `macaroni`, `chicken drumstick`, `green onion`, `tomato juice`, `creamed corn`, `butter`, `whole ham`, `pork butt`, plus the top 20 universe-sweep offenders.
- Spot-check: macaroni → `Pantry > Pasta > Macaroni > Plain`; chicken drumstick → `Meat & Seafood > Poultry > Plain > Chicken Drumsticks`; green onion → `Produce > Fresh Vegetables > Onions > Green Onions > Plain`; tomato juice → `Beverage > Juice > Tomato > Plain`.
- Dump count: rows per top-level canonical_path root (`Pantry`, `Produce`, `Meat & Seafood`, `Dairy`, `Beverage`, etc.). If any root is empty, one of the major canonicals is missing.

**Output artifact:** `Hestia/api/data/canonical_audit_expectation.report.md` — coverage stats and any canonicals that could not be auto-mapped.

---

## Step 3 — Add `accept_via_audit()` to `surface_lab_calculator.py`, fall through to legacy

**File touched:** `esha_audit_bundle/implementation/surface_lab_calculator.py`.
**Effort:** M. **Risk:** medium (changes the hot path; mitigated by fallthrough to legacy on miss). **Depends on:** Step 2.

**Action:**

1. Add a function `accept_via_audit(product, canonical) -> tuple[bool, str] | None`. Returns `None` when no audit classification exists for the product (so the legacy chain runs). Returns `(True, reason)` or `(False, reason)` when classification exists.
2. Wire it as the first check in `_product_acceptance_reason` (line 3797), BEFORE the existing `_accept_milk_product` cascade. If `accept_via_audit` returns non-None, return that. Otherwise, fall through to the legacy chain unchanged.
3. The function reads `canonical_audit_expectation` (built Step 2) and `product_audit_classification` (built tonight, commit a5e26b42). Cache both at module scope keyed on file mtime.

**Verification:**
- Re-run the universe sweep (Step 1's instrumented version) on a separate output path. For canonicals that have a `canonical_audit_expectation` row AND have audit-classified cached products, expect `accepted` count to rise.
- Spot-check the four samples:
  - `macaroni` (1 1/2 lbs) — coverage rises from 0 accepted to >5 accepted (Barilla, Great Value, Kroger plain elbow macaroni).
  - `chicken drumstick` (8–10 drumsticks) — rises from 0 accepted to >3 accepted (Tyson Fresh, Harvestland Fresh, Perdue Fresh).
  - `green onion` (recipe lines that resolve to plain green onion) — rises if the cache has plain bunches; if the only cached candidates are salad kits, accepted stays 0 because the audit's canonical_path for those is `Produce > Salad Kits > ...`, not `Produce > Fresh Vegetables > Onions > Green Onions > Plain`. That is the correct behavior.
  - `tomato juice` (1 19-oz can) — rises from 0 accepted to >2 (Sacramento, Campbell's plain). V8 stays rejected because its audit canonical_path is `Beverage > Juice > Vegetable Blend > V8`.
- Re-run for Tacos De Carnitas (recipe 189466). Coverage must rise from 13.7%; baseline measured in Step 1.
- For canonicals NOT yet in `canonical_audit_expectation` (`coot`, `oleo`, etc.), `accept_via_audit` returns `None` and the legacy chain runs unchanged. No regressions on these.

**Rollback:** Revert the single new function and one line in `_product_acceptance_reason`. Surgical.

---

## Step 4 — Migrate the four investigation samples explicitly

**Files touched:** `surface_lab_calculator.py` (delete or comment out four legacy branches), `canonical_audit_expectation.db` (data only).
**Effort:** S. **Risk:** low (legacy branches now unreachable for these canonicals). **Depends on:** Step 3.

**Action:** For each of `macaroni`, `chicken drumstick`, `green onion`, `tomato juice`, confirm the `accept_via_audit` path is the source of every accept/reject decision. Then delete:
- The `if canonical_key in {"scallion", "green onion"}` block (~lines 2445–2470).
- The `if canonical_key == "tomato juice"` block (~lines 2734–2742).
- The `if canonical_key == "chicken"` block IS NOT deleted yet (it covers the broader `chicken` canonical, not `chicken drumstick`); but verify it's no longer reached for `chicken drumstick` inputs.
- For `macaroni`, there was no per-canonical block to delete; just confirm `_reject_combo_product` is no longer reached for this canonical.

**Verification:** Re-run the universe sweep. Compare the per-rejection reason strings against Step 1's baseline. None of `not_plain_scallion`, `not_plain_tomato_juice`, `combo_or_prepared_product:pasta` should appear for these four canonicals anymore.

---

## Step 5 — Migrate the top-10 universe-sweep offenders

**Files touched:** `surface_lab_calculator.py`, `canonical_audit_expectation.db`.
**Effort:** M. **Risk:** low (one canonical at a time). **Depends on:** Step 4.

**Action:** For each canonical in the top-10 offenders from `universe_gaps.md` (`Pork Butt`, `creamed corn`, `butter`, `whole ham`, `mayonnaise`, `cheddar cheese`, `cream cheese`, `flour`, `sugar`, `olive oil`):

1. Confirm `canonical_audit_expectation` row exists with the right `expected_audit_path`.
2. Run the calculator on the recipes that surface this canonical (use `universe_gaps.jsonl` to find them).
3. Confirm `accept_via_audit` accepts the right products and rejects the wrong ones.
4. Delete the corresponding legacy `if canonical_key == ...` branch and any per-canonical rules in `price_product_filters.py`.

Recipes for verification (from session memory):
- Pork Butt → Tacos De Carnitas (189466). Sugardale Ham Shank must NOT be accepted.
- Butter → any baking recipe; Land O Lakes Butter with Olive Oil must NOT be accepted under plain Butter.
- Creamed corn → Kroger $1 Cream Style Golden Corn MUST be accepted (this was the historical false-negative).

**Verification per cohort:** average per-recipe coverage rises (target: 72.8% → 80%+ once the 46 shopping_gap + 51 wrong_form_likely lines are addressed). No new pricing regressions in the planner output A/B.

---

## Step 6 — Migrate the long tail and delete `_reject_combo_product`

**Files touched:** `surface_lab_calculator.py`, `price_product_filters.py`.
**Effort:** L. **Risk:** medium (fewer fallback safety nets remain). **Depends on:** Step 5.

**Action:** For every remaining canonical_key with a hand-tuned branch in `_product_acceptance_reason`, `is_retail_price_reject`, or `passes_retail_identity`:

1. Add (if missing) a `canonical_audit_expectation` row.
2. Confirm `accept_via_audit` covers it.
3. Delete the legacy branch.

When all per-canonical branches are deleted, delete `_reject_combo_product` entirely. The default tail collapses to:

```python
audit_decision = accept_via_audit(product, canonical)
if audit_decision is not None:
    return audit_decision
# Fallback for unclassified products (audit_title_bm25 below threshold or no UPC):
canonical_tokens = set(normalize_key(canonical).split()) - {"and","or","with","food","product"}
if canonical_tokens and canonical_tokens <= tokens:
    return True, "fallback_token_match"
return False, "missing_required_canonical_terms"
```

**Verification:** Universe sweep coverage ≥ 85%. `wrong_form_likely` and `shopping_gap` counts both ≤ 5 (down from 51 and 46). No drop in nutrition coverage.

---

## Step 7 — Delete ESHA-coupled artifacts

**Files touched / deleted:** `canonical_to_esha.csv`, `esha_nutrition.csv`, `esha_nutrition.py`, `SURFACE_ESHA_NUTRITION_PRIORITY` and `SURFACE_*_OVERRIDES` constants in `surface_lab_calculator.py`.
**Effort:** M. **Risk:** medium (must verify nutrition still resolves through fndds/sr28). **Depends on:** Step 6.

**Action:** GOAL.md says "We are not using ESHA going forward." Once `accept_via_audit` is the sole accept rule and nutrition flows through `fndds_code`/`sr28_code` (already verified for most canonicals), the ESHA-coupled tables become deletable. Do this last because it touches the nutrition path, not just the filter path.

**Verification:**
- `nutrition_unknown` count in the universe sweep does not rise.
- Sample 50 lines, compare nutrition before/after. Differences must be attributable to fndds vs ESHA discrepancies, not bugs.

---

## Step 8 — Retire the food_packages stopgap DBs

**Files touched / deleted:** `Hestia/api/data/food_packages_final.cleaned.db`, `Hestia/api/data/food_packages_audit_tagged.db`, the env var `HESTIA_PACKAGES_DB` consumer logic.
**Effort:** S. **Risk:** low (tagged DB was a stopgap; classification table is now the truth). **Depends on:** Step 7.

**Action:** Once the calculator and the planner both read `product_audit_classification.db` directly, the pre-filtered food_packages DBs are redundant. Switch the planner (`api/hestia/sparse_cascade.py` and `api/hestia/plate_builder.py`) to query `api_cache` × `product_audit_classification` instead of `food_packages_final.db`. Delete the build scripts (`clean_food_packages_via_audit.py`, `build_food_packages_from_audit_tagged.py`) and the resulting DBs.

**Verification:** Planner output for the default household=4 plan matches step-7 numbers within ±2%. No pricing regression.

---

## Step 9 — Address residual gap classes (recipe-text bugs)

**Files touched:** `surface_lab_calculator.py` portion_resolver hooks, `non_food_words.csv`, alias maps.
**Effort:** M. **Risk:** low (each is a small surgical fix). **Depends on:** none of the above (can run in parallel after Step 6).

**Action:**

- **`range_in_text` (21 lines):** parse "8–10 chicken drumsticks" as midpoint 9 in `portion_resolver`. Add unit test for "8–10" (en-dash), "8-10" (hyphen), "8 to 10" (word).
- **`or_option_in_text` (23 lines):** when recipe text has `"X, Y, or Z"`, surface as a structured array and let RUVS verify_line arbitrate (already wired in `run_ruvs_calculator_residual.py` after commits cd84424 / a41fcd5). No code change needed here other than confirming it triggers.
- **`no_canonical` non-food (10 lines):** add `ziploc bag`, `ziploc bags`, `toothpick`, `toothpicks`, `coot` to `non_food_words.csv`.
- **`no_canonical` food (6 lines):** add aliases for `oleo` → `margarine`, `corn niblet` → `corn`, `dry oatmeal` → `uncooked oatmeal` → `oats`, `very fine breadcrumbs` → `breadcrumbs`, `saltine cracker` → `saltine crackers`, `tofu yogurt` → `tofu` (or `yogurt, soy` if FNDDS has it).
- **`generic_term` (333 lines):** RUVS verify_line on the residual after Steps 6–8. The owner has paused LLM calls for this session; resume next session. The residual classifier was already hardened (commits cd84424, a41fcd5) to skip 1,597 clean lines and only send 143.

**Verification:** Universe sweep coverage rises another 5–10 points. No regressions in any earlier step's metric.

---

## Confirmation: regex `verify_ambiguous` is gone

Commit cd84424 in `esha_audit_bundle` confirms removal: `Old GENERIC_RE matched any parsed_item ending in {oil,flour,sugar,...}, which sent fully-resolved lines like '1 cup all-purpose flour' and '2 tbsp vegetable oil' to DeepSeek. The model then manufactured fictitious issues. New rule: line is sent only if (a) it has a real calculator gap, OR (b) recipe text has a numeric range, OR (c) recipe text has an or-option between two ingredient-noun-shaped tokens, OR (d) the canonical_name itself is in a small bare-generic set.` The wrong-shaped classifier is gone; this plan does not propose any work to revive or extend it.

---

## Dependency graph

```
Step 1 (baseline dump)
   |
   v
Step 2 (build canonical_audit_expectation)
   |
   v
Step 3 (add accept_via_audit, fallthrough to legacy)
   |
   v
Step 4 (migrate four samples; delete their branches)
   |
   v
Step 5 (migrate top-10 offenders; delete their branches)
   |
   v
Step 6 (migrate tail; delete _reject_combo_product)        Step 9 (recipe-text residuals)
   |                                                              ^
   v                                                              | (independent; can run after Step 6)
Step 7 (delete ESHA artifacts)                                    |
   |                                                              |
   v                                                              |
Step 8 (retire stopgap food_packages DBs)  ----------------------- 
```

---

## Effort & risk summary

| Step | Effort | Risk | Reversible? |
|---|---|---|---|
| 1 | S | none | n/a |
| 2 | M | low | yes (drop the table) |
| 3 | M | medium | yes (revert one function) |
| 4 | S | low | yes (uncomment branches) |
| 5 | M | low | yes (per-canonical revert) |
| 6 | L | medium | partial (legacy regex code is gone) |
| 7 | M | medium | partial (ESHA reads can be re-enabled) |
| 8 | S | low | partial (rebuild scripts archived but easy to revive) |
| 9 | M | low | yes (per-token / per-alias) |

---

## Anti-drift checklist (apply before each step)

- [ ] Did I read `INVESTIGATION_FILTER.md` and `GOAL.md` since the last code change?
- [ ] Am I about to add a regex / token list / category gate when the audit already classifies this case?
- [ ] Am I touching pricing data? (Don't.)
- [ ] Am I about to call DeepSeek? (Don't, this session — owner has revoked permission.)
- [ ] Did the previous step's verification pass before I started this one?
- [ ] Is the change small enough to revert in one git revert?
