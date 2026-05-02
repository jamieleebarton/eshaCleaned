# GOAL — anchor doc

**Last edit:** 2026-05-02 (post-universe-sweep, audit-tagging shipped)
**Read this every turn before proposing anything.**

## DONE — Tag the Walmart & Kroger cache to `full_corpus_audit.csv`

The previous ACTIVE PLAN ("Tag the Walmart & Kroger cache to full_corpus_audit.csv") shipped tonight in two Hestia commits and one esha_audit_bundle commit:

- **a5e26b42** (`Tag api_cache UPCs to full_corpus_audit (FDC + BM25)`) — `api/scripts/tag_api_cache_to_audit.py` populated `api/data/product_audit_classification.db` with 92,634 UPC-keyed classification rows: 17,837 `audit_fdc_match`, 52,303 `audit_title_bm25`, 22,494 `unclassified`. Walmart/Kroger pricing preserved.
- **a5e26b42** (same commit) — `api/scripts/build_food_packages_from_audit_tagged.py` produced `api/data/food_packages_audit_tagged.db` (drop-in via `HESTIA_PACKAGES_DB`). Sugardale Ham Shank now classifies to fndds 22708010 (sandwich), out of fndds 22010945 (Pork Butt).
- **03b72ee2** (`ruvs: universe sweep + gap aggregator + walmart weight extractor`) — `api/scripts/run_universe_sweep.py` and `api/scripts/aggregate_universe_gaps.py` produced 1,740 calculator lines across 259 recipes with full classification: 51 `wrong_form_likely`, 46 `shopping_gap`, 28 `nutrition_unknown`, 23 `or_option_in_text`, 21 `range_in_text`, 16 `no_canonical`, 333 `generic_term`. Average per-recipe coverage: 72.8%.
- **a41fcd5 / cd84424** (esha_audit_bundle) — RUVS residual classifier hardened: regex `verify_ambiguous` path dropped (was sending fully-resolved lines to DeepSeek and getting fictitious issue reports back). Replacement rule: send only when (a) calculator gap, (b) numeric range in recipe text, (c) or-option between ingredient-noun tokens, (d) canonical itself is bare-generic. Sweep before/after: 469 → 143 lines for DeepSeek.

The classification substrate is in place. The next move uses it.

## ACTIVE PLAN — Structured audit-driven product compatibility

**Read first: `STRUCTURED_MATCHER_SPEC.md` (committed `c1f0870`).** That document is the canonical spec, owner-authored. This section is a pointer.

The previous ACTIVE PLAN ("Replace the per-canonical filter chain with audit-driven accept") was on the right line but framed too narrowly. Step 3 (`accept_via_audit` as first check, commit `88af680`) shipped and is the foothold the spec extends. The new spec demands more than swapping per-canonical branches: it requires a **structured compatibility decision** across six dimensions (canonical path, nutrition codes, variant, form, flavor, combo/prepared) with explicit handling of:

- ESHA override must NOT short-circuit retail matching (Spec Part 4).
- A generated `canonical_retail_bridge` table — not hand-authored — that maps each canonical to expected audit path + allowed/forbidden facets (Spec Part 5).
- Demote `_reject_combo_product()` to unclassified-fallback only (Spec Part 3), do not delete blindly.
- A clear separation between Problem A (raw recipe → canonical fails) and Problem B (canonical resolved, retail match fails). Most current failures are B.

`/Users/jamiebarton/Desktop/esha_audit_bundle/implementation/surface_lab_calculator.py` is still the file that gates retail product selection. Today it has 60+ `if canonical_key == "..."` branches plus a default-tail combo blocklist (`pasta`, `bread`, `salad`, `mix`, `tortilla`, ...). The classification substrate (`product_audit_classification.db`) gives every cached product a deterministic `canonical_path` / `variant` / `form_texture_cut` / `processing_storage`. The matcher must use it as primary, not the legacy regex chain.

Execution order is in the spec (Parts 1 → 4 → 5 → 2 → 3 → 7/10). Win conditions (Part 8) are non-negotiable.

The classification substrate that just shipped (`product_audit_classification.db`) gives every cached product a deterministic `canonical_path` / `variant` / `form_texture_cut` / `processing_storage`. The filter chain just needs to use it.

### Why this is the right move

1. **Kills filter-rule brittleness for real this time.** The audit-tagging work shipped the data; the rules are still ignoring it. No more `_reject_combo_product` blocking elbow macaroni because "pasta" is in the blocklist. The accept rule becomes one comparison: `audit.canonical_path startswith expected_path AND audit.variant matches AND audit.processing_storage matches`.
2. **Handles retailer-private SKUs uniformly.** Already proven by the BM25 step in commit a5e26b42; 52K Kroger/Walmart-private SKUs got their canonical_path. The filter chain is what consumes that work.
3. **Single source of truth across the stack.** Calculator, planner runtime store (food_packages_audit_tagged.db), RUVS residual all read the same `product_audit_classification` table. Cross-stack drift becomes structurally impossible.
4. **Decouples from ESHA.** Nutrition was already routed through `esha_nutrition.csv`. The audit anchors to FNDDS+SR28 (USDA public). With the filter accepting via canonical_path, `canonical_to_esha.csv` and the `surface_*_NUTRITION_OVERRIDES` tables in `surface_lab_calculator.py` become deletable. We are not using ESHA going forward.
5. **Tonight's `food_packages_final.cleaned.db` and `food_packages_audit_tagged.db` are now redundant once the filter accepts via audit.** The cleaner stages drop / demote rows up-front, but the rules-driven filter then rejects again at calc time. With audit-driven accept, the planner's pre-filtered DB and the calculator's accept rule agree by construction.
6. **Shrinks RUVS residual to true ambiguity.** With shopping_gap + wrong_form_likely fixed deterministically, the only RUVS work is the 333 `generic_term` lines (recipe-text problem) and the 44 `or_option`/`range` lines (recipe-text problem). All filter-time rejection cases drop out.
7. **Fixes the calculator's gap on retailer-private products without per-canonical maintenance.** Kroger's $1 Cream Style Golden Corn already has its audit canonical_path written (BM25 step). The filter just needs to read it.
8. **The 60+ hand-tuned `canonical_key` branches in `surface_lab_calculator.py` become deletable**, along with the entire `_reject_combo_product` function and the per-canonical gates in `price_product_filters.py`. Every one was a workaround for missing classification. The audit IS the classification.

### What we are building

A single accept function in `surface_lab_calculator.py` with this shape:

```python
def accept_via_audit(
    product: LabProduct,
    canonical: str,
    expected_audit_path: str,
    required_variant: set[str] | None = None,
    required_form: set[str] | None = None,
    required_processing: set[str] | None = None,
    forbidden_modifiers: set[str] | None = None,
) -> tuple[bool, str]:
    """Single deterministic accept rule.
    Looks up product_audit_classification by product.gtin_upc.
    Accepts iff:
      - classification exists AND audit_confidence >= MIN_CONFIDENCE, AND
      - audit.canonical_path startswith expected_audit_path, AND
      - required_variant is None OR audit.variant in required_variant, AND
      - required_form is None OR audit.form_texture_cut in required_form, AND
      - required_processing is None OR audit.processing_storage in required_processing, AND
      - forbidden_modifiers is None OR no overlap with audit's variant/flavor/claims.
    Falls back to the legacy per-canonical rules ONLY for unclassified products
    (audit_title_bm25 below threshold or no UPC), shrinking the legacy surface
    to ~22K rows instead of all 92K.
    """
```

A new sidecar table mapping each canonical the calculator knows about → its expected audit path + required facets:

```
CREATE TABLE canonical_audit_expectation (
    canonical_key        TEXT PRIMARY KEY,        -- e.g. 'macaroni'
    expected_audit_path  TEXT NOT NULL,           -- e.g. 'Pantry > Pasta > Macaroni > Plain'
    required_variant     TEXT,                    -- JSON array, nullable
    required_form        TEXT,                    -- JSON array, nullable
    required_processing  TEXT,                    -- JSON array, nullable
    forbidden_modifiers  TEXT,                    -- JSON array, nullable
    notes                TEXT
);
```

Seeded from `full_corpus_audit.csv` by extracting the dominant `canonical_path` per `fndds_code`, joined to the calculator's existing canonical → fndds_code map.

### How (sequence, no code yet — see FIX_PLAN.md for the executable steps)

See `FIX_PLAN.md` for the ordered, small, testable changes. The shape is:

1. Build `canonical_audit_expectation` from the audit (deterministic; no LLM).
2. Add `accept_via_audit()` to `surface_lab_calculator.py`. Fall through to legacy on unclassified products.
3. Migrate canonicals one at a time, starting with the four investigation samples (macaroni, chicken drumstick, green onion, tomato juice) and the top universe-sweep offenders (creamed corn, butter, ham). Verify recipe coverage rises before moving on.
4. Once all migrated, delete the per-canonical branches and `_reject_combo_product`.
5. Delete `canonical_to_esha.csv`, `surface_*_NUTRITION_OVERRIDES`, `esha_nutrition.csv` reads (nutrition already flows through fndds/sr28).

### What we are NOT going to do (drift guardrails for this plan)

- **Do not keep tuning the regex / per-canonical rules.** They are deletable. Every minute spent adding a token to the combo list or a phrase to a per-canonical reject set is a minute that should have been spent moving canonicals onto `accept_via_audit`.
- **Do not run the LLM at all in this work.** The owner has revoked LLM-call permission for this session. The expectation table is built from the existing audit CSV deterministically; verification reads existing dumps (`/tmp/calc_plan13.json`, `universe_calc.json`) and re-runs the calculator/planner locally.
- **Walmart/Kroger pricing preserved at every step.** The accept function consumes existing classification rows; it never writes to `product_meta`, `api_cache`, or pricing tables.
- **Classification flows from the audit, NOT from new manual rules.** When a canonical has no clean audit path (e.g., `coot`, `oleo`, `corn niblet`), do not invent one — leave it on the legacy fallback and add it to a residual queue.
- **No big-bang switch.** Per-canonical migration with A/B coverage check after each cohort. The legacy chain stays live as fallback until every canonical-with-an-expected-audit-path is migrated.
- **Tonight's `food_packages_final.cleaned.db` and `food_packages_audit_tagged.db` stay in place as A/B baselines** until the new filter is live and verified, then both become redundant and can be retired.

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

## State of work right now (2026-05-02 post-universe-sweep)

### Shipped tonight (in order)

- **Step 1–4 (`food_packages_final.cleaned.db` cleaner)** — DONE in commit 252fb832 on Hestia. `Hestia/api/scripts/clean_food_packages_via_audit.py`. Outputs 13,789 kept / 2,136 demoted / 1,647 dropped from 15,058 inputs. Verification: Sugardale Ham Shank in fndds 22010945 (Pork Butt) = 0 rows.
- **Audit-tagged classification table** — DONE in commit a5e26b42 on Hestia. `Hestia/api/scripts/tag_api_cache_to_audit.py` produced `Hestia/api/data/product_audit_classification.db`: 17,837 `audit_fdc_match` + 52,303 `audit_title_bm25` + 22,494 `unclassified` = 92,634 rows.
- **Audit-tagged food_packages DB** — DONE in commit a5e26b42 on Hestia. `Hestia/api/scripts/build_food_packages_from_audit_tagged.py` produced `Hestia/api/data/food_packages_audit_tagged.db` (drop-in via `HESTIA_PACKAGES_DB`). Walmart/Kroger pricing preserved.
- **Universe sweep + gap aggregator + walmart weight extractor** — DONE in commit 03b72ee2 on Hestia. 259 recipes / 1,740 lines analyzed. `universe_calc.json`, `universe_gaps.md`, `universe_gaps.jsonl`, `universe_sweep.summary.json`. Average per-recipe coverage: 72.8%. 35 recipes have full coverage (no gap on any line).
- **RUVS residual classifier hardened** — DONE in esha_audit_bundle commits cd84424 (require canonical itself to be bare-generic) and a41fcd5 (drop regex ambiguity detection). Universe sweep before/after: 469 → 143 lines selected for DeepSeek (1,597 clean lines now correctly skipped). The wrong-shaped `verify_ambiguous` regex classifier is gone.

### Coverage / quality numbers

- Recipes analysed: 259
- Lines total: 1,740
- Lines with at least one gap class: 469 (27.0%)
- Recipes with full coverage: 35 (13.5%)
- Average per-recipe coverage: 72.8%
- Worst-coverage recipe in the sweep: Tacos De Carnitas at 13.7% (single-line resolution failures dominate)
- Top unresolved canonicals (no_canonical or shopping_gap): tomato juice (4), green onion (4), chicken drumstick (3), macaroni (2), uncooked oatmeal (2), bourbon (2), then a long tail
- Top fndds_codes with wrong-form picks: 74406010 (9), 28345140 (6), 11113000 (5), 75109600 (4)

### Open gap classes (next session)

| Class | Count | Lever |
|---|---|---|
| `generic_term` | 333 | RUVS verify_line on bare-generic canonicals. Already wired (run_ruvs_calculator_residual.py). Owner has paused LLM calls; will resume next session. |
| **`wrong_form_likely`** | **51** | **`accept_via_audit` (this plan's ACTIVE PLAN). Audit `processing_storage` / `variant` / `form_texture_cut` rules out wrong forms deterministically.** |
| **`shopping_gap`** | **46** | **`accept_via_audit` (this plan's ACTIVE PLAN). Audit `canonical_path` accepts cached products that the regex/category rule rejects.** |
| `nutrition_unknown` | 28 | Resolver-side; separate sweep |
| `or_option_in_text` | 23 | RUVS verify_line — recipe-text problem |
| `range_in_text` | 21 | portion_resolver fix; not filter-related |
| `no_canonical` | 16 | 6 are food terms missing alias mapping (oleo, corn niblet, dry oatmeal, very fine breadcrumbs, saltine cracker, tofu yogurt). 10 are non-food (ziploc bag, toothpick, toothpicks, coot) escaping `non_food_words.csv`. |

## Cleanup Script Inventory (Step 1 result, 2026-05-02)

All scripts read or write `product_to_best_esha_full_map.vIdentity*.csv` (462K rows: product → ESHA code map). The cohort key is `current_esha_code`. The product text is `product_description + brand_name`. The category check is `branded_food_category`. To repurpose for `food_packages_final.db`, the cohort key becomes `fndds_code`, doc text becomes `product_meta.name + product_meta.ingredient_statement`, anchor becomes `food_description`. The scoring math is unchanged.

### Outlier-scoring engines (produce flag lists)

| Script | Signal | Threshold | Inputs | Outputs |
|---|---|---|---|---|
| `cohort_outlier_scan.py` | TF-IDF ingredient distance z-score + category mismatch + fndds mismatch + weak verdict | composite > 1.5 | vIdentity.fixed_v2.csv + master_products.db | `cohort_outliers_per_code.csv`, summary md |
| `embed_outlier_scan.py` | MiniLM `description+brand` embedding, 1−cos(emb, cohort_centroid), z-score within cohort | z ≥ 1.5 | vIdentity.fixed_v2.csv + esha_cleaned_canonical.csv | `embed_outliers.csv`, cache at `.embed_cache/prod_emb.npy`, summary md |

### Reroute engines (move outliers to a better cohort)

| Script | Signal | Apply rule | Inputs | Outputs |
|---|---|---|---|---|
| `cohort_reroute.py` | TF-IDF cosine to alt cohort centroid, filtered by branded_food_category majority | alt_sim ≥ 0.25, margin ≥ 0.10, alt_majority ≥ 0.4, alt_size ≥ 5 | vIdentity.fixed_v2.csv + cohort_outliers_per_code.csv | `cohort_reroute_applied.csv`, review queue, vIdentity.fixed_v3.csv |
| `embed_reroute.py` | MiniLM embedding cosine to alt cohort centroid, filtered by majority category | alt_sim ≥ 0.50, margin ≥ 0.10, alt_majority ≥ 0.4, alt_size ≥ 5 | vIdentity.fixed_v2.csv + outliers_filtered.csv + .embed_cache/* | `embed_reroute_applied.csv`, review, vIdentity.fixed_v3_embed.csv |

### Tightening / filtering (post-reroute confidence)

| Script | Action | Inputs | Outputs |
|---|---|---|---|
| `apply_embed_v3.py` | Tighten embed_reroute_applied.csv: keep only if alt_sim ≥ 0.75, OR (alt_sim ≥ 0.65 AND margin ≥ 0.15) | embed_reroute_applied.csv + vIdentity.fixed_v2.csv | `embed_v3_applied.csv`, review queue, vIdentity.fixed_v3.csv |
| `filter_and_cluster_outliers.py` | Drop outliers whose sim_to_tree_description ≥ 0.5 (false-positive guard); cluster survivors by (esha_code, category) for bulk fix | embed_outliers.csv | `outliers_filtered.csv`, `outlier_clusters.csv`, summary |

### BM25 utilities (alternative scoring, ingredient-list driven)

| Script | What it indexes | Use |
|---|---|---|
| `fixy_done/_bm25_match.py` | Token bag per FNDDS CSV file | ingredient list → best `fndds_code` |
| `fixy_done/_bm25_esha_v3.py` | ESHA-code docs with field weighting (title 5x, ingredients 1x, bigrams) | product/audit text → best `esha_code` with top1/top2 margin as confidence |
| `fixy_done/_bm25_fast.py` | Sparse-matrix variant of v3 (batch scoring) | full-corpus scoring against ESHA |

### Cleanup orchestration

| Script | What it does |
|---|---|
| `embed_cluster_pipeline.py` | Full pipeline: load → MiniLM embed → FAISS kNN graph → Leiden cluster → centroid kNN against SR28/FNDDS/ESHA → report. Two modes: `products_only` (default) and `joint` (with reference items). |
| `build_esha_cleanup_matrix.py` | Assembles MD-pack product rows + cross-reference + matcher into `esha_cleanup_matrix.csv` |
| `build_esha_category_outlier_workbench.py` | Per-category outlier triage workbench, uses `self_heal_common` for category lane / form / role / target heads |

### The chain that produced the working v3 reroute

```
embed_outlier_scan.py        →  embed_outliers.csv
filter_and_cluster_outliers  →  outliers_filtered.csv     (drop sim_to_tree ≥ 0.5)
embed_reroute.py             →  embed_reroute_applied.csv (alt_sim ≥ 0.50, margin ≥ 0.10)
apply_embed_v3.py            →  vIdentity.fixed_v3.csv    (tighten to alt_sim ≥ 0.75 OR ≥0.65+margin≥0.15)
```

### Adaptation surface for food_packages_final.db

To clean the planner's runtime store using this same chain, only the data-loading layer changes:

- **INPUT** rows: `food_packages_final.db.packages` (15,009 rows). Key = `(fndds_code, package_weight_grams)`. Per row: `food_description`, `product_meta` JSON (`name`, `brand`, `ingredient_statement`, `categories`).
- **Cohort key**: `fndds_code` (was `current_esha_code`).
- **Doc text per row**: `product_meta.name + " " + product_meta.ingredient_statement`.
- **Anchor (analog of esha_cleaned_canonical row)**: `food_description`.
- **Category analog**: `product_meta.categories[0]` (kroger) — used for the majority-category filter in reroute.
- **Output**: a flag list (`food_packages_outliers.csv`) of (fndds_code, package_weight_grams, name, score, reason). Optionally a sidecar `food_packages_demote.csv` indicating which rows to drop or demote in confidence_tier.
- The scoring math, thresholds, embedding model, cache layout — all reused.

## Anti-drift checklist (run before every reply)

- [ ] Did I look at the actual file/script/data before saying anything?
- [ ] Am I proposing new infrastructure when existing infrastructure does this job?
- [ ] Am I trusting `recipes2.csv` for grams? (Don't.)
- [ ] Am I throwing out walmart/kroger pricing? (Don't.)
- [ ] Am I about to call DeepSeek before deterministic cleanup ran? (Don't.)
- [ ] Does this turn move us forward in the action sequence above, or am I bouncing to a new direction?
