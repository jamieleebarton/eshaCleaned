# GOAL — anchor doc

**Last edit:** 2026-05-02
**Read this every turn before proposing anything.**

## The single goal

**Make Hestia's planner pick correct products for the recipes it actually uses, using the calculator + the cleanup infrastructure that already exists in `esha_audit_bundle/`.**

That's it. Anything not in service of this goal is drift.

## What "correct" means (operational)

A recipe line is correct when ALL of these hold:

1. The canonical (fndds/sr28/esha) maps to the food the recipe actually wants. Pork butt → pork shoulder products, NOT Sugardale Ham Shank.
2. The form is right. Plain "butter" → butter sticks, NOT Land-O-Lakes-with-olive-oil-spread.
3. The granularity is right. Plain "mayonnaise" → plain mayo, NOT chipotle/lime mayo.
4. The grams come from running the calculator on the RAW recipe text (recipe_qa.db), NOT from `recipes2.csv`'s pre-baked `fndds_grams_dict`.
5. Walmart/Kroger pricing is preserved — we cannot throw out the cache, we need the prices.

## Confirmed facts (with evidence, not guesses)

- The planner reads `Hestia/api/data/food_packages_final.db` at startup. That's where its picks come from.
- That DB has ~4,500 rows (of 15,009) with zero token overlap between `food_description` and `product_meta.name`. Some are tokenizer false positives (`Soy Milk` vs `Soymilk`); a substantial portion are real misroutes (Sugardale Ham Shank → Pork Butt; Tzatziki → Milk; Guacamole → Sour Cream).
- The calculator's product matcher (via `esha_audit_bundle/data/master_products.db.product_code_tags`) is CLEAN for the same fndds_codes that are dirty in `food_packages_final.db`. Verified for fndds 22010945 (Pork Butt): 70 candidates returned, ALL pork shoulder/butt products.
- `recipes2.csv.fndds_grams_dict` is broken for at least Tacos De Carnitas (recipe 189466): says 85g pork butt, 2g salsa, 2g cilantro, 10080 kcal total. The calculator on raw text from `recipe_qa.db` produces 2041g pork, 100g salsa, 20g cilantro — those are correct.
- The planner picks 13 recipes for a default household=4 plan ($105.51/wk). Of those 13, the calculator's `recipe_qa.db` corpus has 10. 3 are missing: `Blueberry Muffins (32228)`, `Homemade Instant Oatmeal With Variations (136842)`, `Pork (Or Beef) on a Bun (156460)`.
- `full_corpus_audit.csv` (May 1 23:16, 462,712 rows) has rich classification columns (canonical_path, variant, flavor, form_texture_cut, processing_storage, claims) but is keyed on FDC IDs. Most Kroger/Walmart private-label products in `food_packages_final.db` are NOT in FDC, so they cannot be re-tagged from the audit directly.
- Existing cleanup scripts in `esha_audit_bundle/implementation/` that work on the same kind of problem (centroid/embedding/BM25 outlier detection per code-cohort): `apply_embed_v3.py`, `cohort_reroute.py`, `embed_cluster_pipeline.py`, `filter_and_cluster_outliers.py`, `build_esha_cleanup_matrix.py`, `build_esha_category_outlier_workbench.py`, `fixy_done/_bm25_match.py`, `fixy_done/_bm25_esha_v3.py`. These were built for ESHA-mapping cleanup (462K-row product_to_best_esha map). The pattern (centroid per code, score outliers, drop or demote) transfers to `food_packages_final.db` cohorts (per fndds_code).
- An esha-shadow DB already exists at `Hestia/api/data/food_packages_esha_shadow.db` (Apr 28, 22,717 rows, 5,685 fndds_codes — more coverage than `food_packages_final.db`'s 15,058 / 5,606). The current branch is `codex/esha-package-shadow`; `Hestia/api/scripts/build_esha_package_shadow.py` is the builder. The shadow has the same Sugardale-Ham-Shank-in-Pork-Butt and Butter-with-Olive-Oil-in-Butter bugs, because it was built before the latest `full_corpus_audit.csv` pass and its bridge filtering does not use audit columns like `form_texture_cut`.

## What we will NOT do (drift guardrails)

- Build parallel infrastructure. Use `apply_embed_v3.py` / `cohort_reroute.py` / BM25 / etc. as the cleanup engine. Adapt, do not reinvent.
- Throw out walmart/kroger cache or live API. Pricing comes from there.
- Trust `recipes2.csv.fndds_grams_dict`. Always run the calculator on raw `recipe_qa.db` text.
- Send DeepSeek to "search for products". Products are in our local data. DeepSeek's job (if used at all) is to verify or to arbitrate residual ambiguity after deterministic cleanup.
- Patch `food_packages_final.db` row-by-row in place. Generate a clean shadow DB and A/B-swap.
- Spec or plan more before we have a clean cleanup pass over `food_packages_final.db`.

## Action sequence (this is the path; do not rewrite without saying so)

1. **Inventory the cleanup scripts.** Document exactly what each `apply_embed_v3.py` / `cohort_reroute.py` / `_bm25_match.py` / etc. consumes and produces, with sample input/output.
2. **Adapt one of them to operate on `food_packages_final.db.packages` cohorts.** Cohort key = `fndds_code`. Doc text = `product_meta.name` + `product_meta.ingredient_statement`. Anchor = `food_description`.
3. **Run the cleanup.** Produce an outlier report with `centroid_zscore` per row (same shape as `embed_v3_applied.csv`).
4. **A/B compare.** Build a shadow DB (`food_packages_final.db.cleaned`) by dropping/demoting outliers from above a chosen `centroid_zscore` threshold. Re-run sparse_cascade with `HESTIA_PACKAGES_DB=...cleaned`. Compare picks side-by-side. Sugardale Ham Shank should disappear from Pork Butt picks; butter blends should drop from plain Butter picks.
5. **Run the calculator on the planner's recipe IDs.** Confirm calculator-derived grams are sane (verified for Tacos De Carnitas already). Resolve the 3 recipes the calculator's corpus is missing.
6. **Only THEN** layer DeepSeek on the residual cases that the deterministic pipeline cannot decide.

## State of work right now (2026-05-02)

- Step 1: NOT DONE. Need to read each cleanup script's I/O contract and write a one-line summary per script.
- Step 2: NOT STARTED.
- Step 3: NOT STARTED.
- Step 4: NOT STARTED. (Existing shadow DB from Apr 28 has the same bugs; shadow build chain doesn't use audit columns.)
- Step 5: PARTIAL. Calculator dump for 10/13 recipes at `/tmp/calc_plan13.json`. Plan dump at `implementation/output/ruvs/real_plan/plan.json`.
- Step 6: NOT STARTED.

## Anti-drift checklist (run before every reply)

- [ ] Did I look at the actual file/script/data before saying anything?
- [ ] Am I proposing new infrastructure when existing infrastructure does this job?
- [ ] Am I trusting `recipes2.csv` for grams? (Don't.)
- [ ] Am I throwing out walmart/kroger pricing? (Don't.)
- [ ] Am I about to call DeepSeek before deterministic cleanup ran? (Don't.)
- [ ] Does this turn move us forward in the action sequence above, or am I bouncing to a new direction?
