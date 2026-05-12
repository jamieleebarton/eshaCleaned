# Hestia Recipe→Retail Bridge — Handoff

Last updated: 2026-05-09. Working dir: `/Users/jamiebarton/Desktop/esha_audit_bundle`.

This document is the operating manual for the recipe→retail-product matching system. It explains:
1. What the system does and what's broken
2. The core data files (the "golden files") and how they relate
3. Every script we use, what it does, and when to run it
4. The end-to-end pipeline to go from recipes → priced 12-week meal plan
5. Known bugs (with severity) and the workstreams that address each

This file supersedes prior HANDOFF.md content (which was the R5-era 85.7% audit notes).

---

## 1. What the system does

Given ~500K recipes and ~40K retail SKUs from Walmart/Kroger:
1. Parse each recipe ingredient line into `(item, qty, unit, grams_resolved, htc_code)`
2. Resolve each ingredient to a priced concept (a bucket of ranked SKUs)
3. The cascade planner picks recipes for 12 weeks for 4 people at 2000 cal/day, minimizing cost while hitting calorie/protein/veg targets and 0 waste

**Goal**: a real, public-ready, deterministic meal plan + shopping list. "1 tsp salt → 6g, buy Kroger Salt $0.79" — every time, same answer.

**What's been broken across rounds**: every audit surfaces bugs (mayo for olive oil, chorizo for andouille, Mrs Meyer's for basil, popcorn topping for oil, water priced like a beverage, "BLT" recipe with no bacon in cart). Architectural fixes catch one class of bug, surface another. The cost number drops each round but is partly artifact (silent NO_MATCH skipping).

---

## 2. The golden files

Per the user's memory: "same identity → same htc_code across all of them." Reality has been they drift apart.

| file | path | what it stores | keyed on |
|---|---|---|---|
| consensus_full_corpus_audit.csv | `retail_mapper/v2/` | 37-col corpus audit: fdc_id, canonical_path, canonical_label, fndds_code, sr28_code, esha_code, retail_leaf_path, identity, variant, claims, modifier | fdc_id |
| consensus_htc_tagged.csv | `recipe_mapper/v1/output/` | Encoder-authoritative htc_code → (canonical_path, htc_form, htc_full_code, group/family/food/form) | fdc_id |
| recipe_ingredient_htc_tagged.csv | `recipe_mapper/v1/output/` | Per-ingredient (item → htc, n_recipes, grams_total) | item |
| recipe_ingredient_taxonomy_v2.csv | `recipe_mapper/v1/output/` | Per-ingredient (title → canonical_path, modifier). **Has known leaf-loss bugs** — used as fallback only. | title |
| api_cache_taxonomy_v2 / api_cache_htc_tagged.csv | `recipe_pricing/output/` | Per-SKU (upc, canonical_path, htc_code, htc_full_code) | upc |
| **priced_products_v2.db** | `recipe_pricing/data/` | **The active priced DB** — every SKU we can buy with consensus_canonical, htc_code, htc_form_code, htc_full_code, cents, grams, cpg, brand | upc |
| recipes_unified.csv | `recipe_mapper/v1/output/` | 4.7M recipe-ingredient lines: recipe_id, ingredient_item, display, qty, unit, grams_blob, grams_resolved, grams_source, htc_code, htc_form, htc_confidence, normalized_canonical_text, htc_full_code | recipe_id+line |

**Invariant we want (often broken)**: same food identity → same htc_code AND same canonical_path across all files. Right now `consensus_htc_tagged` says "Cumin Seed", priced_products has "Cumin", recipe_ingredient_taxonomy_v2 said bare "Pantry" (we patched build_recipe_concept_grams to use htc-truth instead of taxonomy_v2's wrong cps).

`api_cache_htc_tagged.csv` is synced to `priced_products_v2.db` via `propagate_quarantine_to_golden.py` (UPC-keyed). FDC-level `consensus_htc_tagged.csv` is NOT touched by SKU-level moves (different abstraction).

---

## 3. Data flow (end-to-end)

```
recipes_unified.csv      (recipe-ingredient lines with htc_code)
        │
        ▼
build_recipe_concept_grams.py   (uses consensus_htc_tagged.csv → cp lookup as truth,
                                  falls back to recipe_ingredient_taxonomy_v2)
        │
        ▼
recipe_concept_grams.json       (recipe_id → {concept_key: grams})
                                 concept_key = "canonical_path|htc_form_code"
        │                       │
        │                       │
        │                       ▼
        │              build_concept_index.py   (priced_products_v2.db → grouped pools)
        │                                       (rejects non-food blocklist + path-conditional)
        │                                       (Beverage > Water → cents=0)
        │                       │
        │                       ▼
        │              concept_index.json       (priced concept_key → packages[])
        │                       │
        ▼                       ▼
build_concept_resolution.py   (recipe ck → priced ck via tiers)
                              (gates: singleton ≥3, top-cat invariant,
                               require_specific_sku w/ parent-leaf-subset accept,
                               alias map)
        │
        ▼
concept_resolution.json
        │
        ▼
build_concept_tensor_cache.py  (planner-side tensors)
        │
        ▼
multi_week_ours.py             (12wk plan via SparseCascadePlanner)
        │
        ▼
multi_week_ours_12w_round*.json
        │
        ▼
build_weekly_shopping_list.py  (per-week shopping cart with canonical names)
        │
        ▼
weekly_shopping_list.md / .csv
```

---

## 4. Scripts catalog

### 4.1 Bridge / index / resolution (the planner data)

| script | path | purpose |
|---|---|---|
| `build_recipe_concept_grams.py` | `planner/scripts/` | Per-recipe gram totals per concept_key. Uses htc-truth CP from consensus_htc_tagged. Falls back to taxonomy_v2. |
| `build_concept_index.py` | `planner/scripts/` | Priced concept pools. Filters non-food blocklist and path-conditional rejects. Marks `Beverage > Water` zero-cost via `FREE_PATHS`. |
| `build_concept_resolution.py` | `planner/scripts/` | Recipe→priced concept mapping with tiered fallback. Has singleton + top-cat + sku-pool gates with parent-leaf-subset accept. |
| `build_concept_tensor_cache.py` | `planner/` | Planner tensors from concept data. |
| `build_htc_to_fdc_bridge.py` | `recipe_pricing/` | htc_code → fdc_id bridge (for SR28 lookups). |
| `multi_week_ours.py` | `planner/scripts/` | The 12-week planner driver. |

### 4.2 SKU cleanup / reclassification

| script | path | purpose |
|---|---|---|
| `reclassify_canonical_paths.py` | `recipe_pricing/` | Move SKUs to correct paths via curated rules. Auto-runs reencode after. |
| `reencode_after_reclassify.py` | `recipe_pricing/` | Re-encode htc_code/htc_form_code/htc_full_code after path moves. |
| `quarantine_blocklisted_skus.py` | `recipe_pricing/` | Move non-food SKUs (Mrs Meyer's, Magic Man Chili, etc.) to "Non-Food > Misclassified". Auto-runs reencode. |
| `propagate_quarantine_to_golden.py` | `recipe_pricing/` | Sync canonical_path + htc updates from priced_products_v2.db to api_cache_htc_tagged.csv (UPC-keyed). |

### 4.3 Audits / validation gates

| script | path | purpose |
|---|---|---|
| `htc_coverage_audit.py` | `recipe_pricing/` | **The end-to-end audit**: per-concept_key, gram determinism + bridge ok + correct SKU. Verdict GREEN/YELLOW/RED. |
| `audit_full_bridge.py` | `recipe_pricing/` | Whole-corpus (not just picked) bridge bugs ranked by recipe-impact. |
| `audit_gram_determinism.py` | `recipe_pricing/` | Per-(item,qty,unit) drift: distinct gram values vs modal. |
| `audit_token_mismatch.py` | `recipe_pricing/` | Picked-recipe lines where SKU and ingredient share no tokens. |
| `picked_recipe_audit.py` | `recipe_pricing/` | Per-recipe end-to-end checklist (tier, SKU, n-recipes-impact). |
| `test_bridge_integrity.py` | `recipe_pricing/` | Fixture-based truth assertions (must_contain / must_not_contain / NO_MATCH FAILS unless allow_no_match). |
| `test_recurrence_detector.py` | `recipe_pricing/` | Fail CI when same SKU+target_path appears in ≥2 reclass rounds. |
| `freeze_canonical_paths.py` | `recipe_pricing/` | Snapshot/check upc→canonical_path freeze. |
| `verify.sh` | `recipe_pricing/` | Run all gates: freeze, recurrence, bridge integrity. |

### 4.4 Output

| script | path | purpose |
|---|---|---|
| `build_weekly_shopping_list.py` | `recipe_pricing/` | Per-week canonical-name shopping list from 12wk plan output. Reads `/tmp/multi_week_ours_12w_round10.json` by default. |
| `build_coverage_report.py` | `recipe_pricing/` | Recipe-level "what's calculable" coverage report. |

### 4.5 Gram normalization (deterministic SR28 truth)

| script | path | purpose |
|---|---|---|
| `normalize_grams_to_sr28.py` | `recipe_pricing/` | R7-era: normalize grams_resolved using SR28 portion truth. **Has SKIP_PATTERNS guard that's currently TOO restrictive — 30K+ tuples drift.** |
| `build_htc_to_fdc_bridge.py` | `recipe_pricing/` | Build htc_code → fdc_id mapping for SR28 join. |

### 4.6 Configuration files (the rules)

| file | purpose |
|---|---|
| `recipe_pricing/non_food_blocklist.txt` | Phrases that disqualify a SKU at any food path (cleaner, candle, bonnie plants, mrs meyer, etc.) |
| `recipe_pricing/canonical_path_aliases.csv` | Recipe-side cp → priced-side cp rewrites. **Pruned** in R12 to drop depth-losing aliases. |
| `recipe_pricing/canonical_path_freeze.csv` | Snapshot for drift detection. |
| `recipe_pricing/leaf_synonyms.csv` | Acceptable food synonyms (margarine ≡ vegetable oil spread). |
| `recipe_pricing/bridge_truth.csv` | Fixture: 193 truth rows with positive+negative assertions. |
| `recipe_pricing/ingredient_fdc_overrides.csv` | Manual htc→fdc bridge overrides. |
| `recipe_pricing/htc_cp_overrides.csv` | Manual item→cp overrides for upstream encoder mis-classifications (nutmeg/mace/cardamom/cloves filed under "Spice Blend" upstream → routed to correct leaf). |
| `recipe_pricing/priced_products_excluded.csv` | UPCs to skip. |
| `PATH_CONDITIONAL_REJECT` (inline in `build_concept_index.py` AND `quarantine_blocklisted_skus.py`) | Path-specific reject rules (oil rejects mayo/topping, broth rejects lunchmeat/jerky, sausage subtypes reject other subtypes). **Must be kept in sync between the two files.** |

---

## 5. End-to-end pipeline (run order)

To go from recipes/SKUs to a fresh 12-week plan:

```bash
cd /Users/jamiebarton/Desktop/esha_audit_bundle

# (Optional) Apply any pending reclassification or quarantine to the DB
python3 recipe_pricing/reclassify_canonical_paths.py     # (auto-reencodes)
python3 recipe_pricing/quarantine_blocklisted_skus.py    # (auto-reencodes)
python3 recipe_pricing/propagate_quarantine_to_golden.py # (sync to golden file)

# Build the bridge data
python3 recipe_pricing/build_htc_to_fdc_bridge.py
python3 planner/scripts/build_recipe_concept_grams.py
python3 planner/scripts/build_concept_index.py
python3 planner/scripts/build_concept_resolution.py
cd planner && python3 build_concept_tensor_cache.py && cd ..

# Verify the gates BEFORE running the plan
bash recipe_pricing/verify.sh

# Run the 12-week plan
HESTIA_BEAM_K=50 python3 planner/scripts/multi_week_ours.py \
    --weeks 12 --people 4 --cal 2000 --mode thrifty \
    --protein-pct 15 --leftover-pct 0.75 \
    --out /tmp/multi_week_ours_12w_round_X.json

# Audit it
python3 recipe_pricing/htc_coverage_audit.py
python3 recipe_pricing/picked_recipe_audit.py
python3 recipe_pricing/audit_token_mismatch.py

# Generate the shopping list
cp /tmp/multi_week_ours_12w_round_X.json /tmp/multi_week_ours_12w_round10.json
python3 recipe_pricing/build_weekly_shopping_list.py
# Output: recipe_pricing/weekly_shopping_list.md and .csv
```

---

## 6. Cost trajectory across rounds

What the headline number means and what was actually true:

| Round | $/wk avg | NO_MATCH% | What "real" status | Gotcha |
|---:|---:|---:|---|---|
| R7 | $85.39 | n/a | gram normalizer applied (1.39M lines) | SKIP_PATTERNS too restrictive |
| R8 | $87.23 | n/a | retag round | |
| R9 | $89.88 | n/a | path-form leaf-token guards | |
| R10 | $93.40 | n/a | reclass round, regression | |
| R11 | $90.17 | n/a | re-encode after reclassify (structural fix) | |
| R11b | $92.71 | n/a | post-reencode | |
| R12 | $68.78 | 26.4% | non-food blocklist, singleton + top-cat gates, alias prune | TEST FIXTURE INFLATED — NO_MATCH counted as PASS |
| R13 | $63.52 | 26.5% | gates on alias_exact + path_only, leaf-token gate, fixture fixed | Test pass rate dropped to honest 52.3% |
| R14 | $35.38 | 38.2% | htc-truth-cp + free water | **FAKE — htc→longest-cp picked random Meal-tier compound dishes (bacon→cheeseburger patties, black beans→rice with black beans). BLT had no bacon.** |
| R14b | $46.98 | 32.8% | parent-leaf-subset accept fix to gates | partial — recipe cps still wrong |
| **R14c** | **$66.76** | **31.7%** | **htc → most-frequent-cp + chicken-lunchmeat block + raw-top-cat preference** | **Honest. 99.9% cal, 56.9% veg, 0sv waste, 259 recipes.** Sample audit: 20/29 ingredients correct (69%), 8 NO_MATCH (haddock, leeks, wild rice — really not stocked + recipe-parser artifacts), 1 instant-rice-for-rice. |

**Lesson**: cost is misleading when NO_MATCH inflates. The audit (`htc_coverage_audit.py`) verdict GREEN/YELLOW/RED is the honest signal.

---

## 7. Known bugs (severity ranked)

### CRITICAL — affecting picks today

| bug | recipe-impact | root cause | workstream |
|---|---:|---|---|
| Gram drift | 51% of recipe-uses | `normalize_grams_to_sr28.py` SKIP_PATTERNS rejects "1 tsp salt + plus more"; modal grams cover 78-99% of lines but not 100% | Gram normalizer aggression — top-50 SR28 tuples force-pass |
| NO_MATCH inflation | 32.8% of concepts (R14b) | recipe-side cp specificity (Cumin Seed) doesn't match priced-side cp (Cumin); resolver gates over-strict | parent-leaf-subset fix in `passes_gates` (just shipped R14b) |
| Lemons/Red Onions/Mozzarella/Ginger NO_MATCH | ~100K | Fresh fruits filed at "Frozen > Frozen Fruit" by upstream LLM SKU classifier; top-cat invariant correctly refuses cross-cat bridge but root cause is upstream misclassification | Buyability classifier rerun (already noted in memory: $126/10h DeepSeek) |
| Bare-Pantry recipes | 31K (was 61K before R14) | `recipe_ingredient_taxonomy_v2.csv` had wrong cps for spices; `build_recipe_concept_grams` now uses htc-truth as primary, falls back to taxonomy_v2 only when htc has no entry | partly fixed in R14; remaining 31K are htc codes that genuinely have no leaf in consensus_htc_tagged |

### HIGH — visible in W1 carts

| bug | recipe-impact | root cause | fix |
|---|---:|---|---|
| Tap water purchased ($31.20/12wk) | global | `Beverage > Water` SKUs treated as priced ingredients | `FREE_PATHS` in `build_concept_index` sets cents=0 (R14) |
| Generic "Pantry > Spices > Spice Blend" → Badia Complete Seasoning | broad | Spice Blend path is generic; Badia is the cheapest at that path; path-conditional reject doesn't have rule for it | TBD: path-conditional reject for "Spice Blend" needing recipe-leaf-token match |
| Hot Pepper Sauce → "Blue Elephant Royal Thai Premium" $3.16 | small | premium SKU is cheapest per-gram at hot sauce path (large bottle) | TBD: prefer simpler-named SKUs (Tabasco) over imported gourmet |
| Margarine → Imperial Vegetable Oil Spread | acceptable | Modern margarine IS vegetable oil spread; semantically correct | not a bug, just terminology drift |

### MEDIUM — surfaced in audits, not in current picks

| bug | recipe-impact | root cause | fix |
|---|---:|---|---|
| Coriander seed → Cilantro produce | ~6K | alias_exact tier was bypassing gates (now gated R13.2) | should be fixed with R14b parent-subset accept |
| Aliases collapsing identity (Currants→Raisins, Liver→Beef Liver, Apricot Preserves→Preserves, Marinated Artichoke Hearts→Artichoke Hearts) | broad | Round-2-5 era depth-losing aliases | R12 pruned 14 of them; remaining ~24 still loss-of-depth, should convert to facet projections per canonical-recipe architecture (R13.6 deferred) |
| Dean's French Onion Dip absorbs 83 distinct dip recipes | 83 | dip path doesn't enforce modifier match (onion/bean/spinach/cheese/hummus) | path-conditional rule for `Pantry > Dips & Spreads > Dip` requiring modifier match |

### LOW — fixture polish

| bug | recipe-impact | fix |
|---|---:|---|
| Fixture has stale must_not_contain rules | ≤10 truth rows | re-curate `bridge_truth.csv` with sharper assertions |

---

## 8. Architectural decisions (for future you)

1. **htc_code is the food identity**, but it's a bucket — positions 3-4 are reserved 00 so garlic/onion/leek share family 65. canonical_path is the species-level discriminator.
2. **Cross-top-category resolution is forbidden** — recipe at Produce > X cannot resolve to Pantry > X via fallback tiers. Refuse rather than bridge wrong food. (`TOP_CAT_INVARIANT = True` in build_concept_resolution.)
3. **Singleton-bucket rejection** — any tier ≥ 2 needs ≥3 SKUs in the priced concept. Without this, contamination buckets (1 Mrs. Meyer's at Basil) would win. (`SINGLETON_FLOOR = 3`)
4. **Non-food blocklist + path-conditional rejects must run at concept_index ingest AND quarantine source-DB pass.** Two passes: filter-at-runtime AND clean-the-source. They drift apart easily — keep them in sync.
5. **NO_MATCH must FAIL tests** unless explicitly allowed. R12's 95.9% pass was inflated by NO_MATCH-counts-as-PASS. Always check.
6. **Reclassify_canonical_paths.py auto-runs reencode_after_reclassify.py** — never leave stale htc codes after a path move. Same applies to quarantine.
7. **Recurrence detector** (`test_recurrence_detector.py`): if the same SKU+path tuple appears in 2 different reclass rounds, fail CI. Don't whack-a-mole.
8. **Coverage audit (`htc_coverage_audit.py`) is the honest signal** — verdict GREEN per concept means: deterministic grams + bridge round-trip + correct SKU. Headline cost number is misleading.
9. **Parent-leaf-subset accept** (R14b): when recipe is more specific than priced (Cumin Seed → Cumin), resolver accepts. When candidate has its own distinctive tokens (Andouille → Chorizo), resolver requires SKU pool to prove the recipe-specific food is present.
10. **htc_code → canonical_path is the truth source** for recipe-side cp, BUT pick the **most-frequent** cp per htc, not the longest. An htc maps to a FAMILY of foods (many fdcs); longest-path picks rare compound dishes (bacon→cheeseburger patties via 3 fdcs vs 270 at correct path). Also disprefer `Meal > ...` cps when raw-ingredient cps are available (Pantry/Produce/Dairy/Meat & Seafood/Bakery/Frozen/Beverage). Implemented in `build_recipe_concept_grams.py` R14c.
11. **`recipe_ingredient_taxonomy_v2.csv` has known leaf-loss bugs** (cumin seeds → bare "Pantry"). Used only as fallback when htc has no cp.

---

## 9. Pending workstreams (not yet started)

1. **Gram normalizer aggression** — drop SKIP_PATTERNS, force SR28 truth on top-50 tuples (would unblock ~30% of RED).
2. **Buyability classifier** — DeepSeek pass per recipe-line, ~$126/10h (in memory). Would fix Fresh-Strawberries-at-Frozen-path and similar SKU misclassifications at the source.
3. **R13.6: aliases → facet projection** — Marinated Artichoke Hearts keeps marinade as runtime facet (canonical-recipe architecture in memory).
4. **R9b: macro reconstruction** — protein/fat/carbs/sodium/fiber from picked SKUs (per-package consensus_sr28).
5. **R9c: htc_full_code as match tier** — currently use htc_form (8-char) as the form code; htc_full_code carries variant + claims bits.
6. **Sibling tier in resolver** — formally add a `sibling_form` tier between path_form and parent_form: walk to parent, try every child path with same htc_form ranked by leaf-stem overlap. Currently this works via parent_form → leaf-token guard but is implicit.

---

## 10. Files to back up / never touch

- `recipe_pricing/data/priced_products_v2.db` — the active priced DB. Snapshot before any reclass/quarantine.
- `recipe_pricing/data/priced_products_v2.before_*.db` — historical snapshots (kept).
- `recipe_pricing/canonical_path_freeze.csv` — drift baseline.
- `recipe_pricing/canonical_path_aliases.csv.before_round*` — alias history (recurrence detector reads these).
- `recipe_pricing/reclassify_log.csv` — recurrence detector input. Snapshot per round (`reclassify_log_round12.csv`).

---

## 11. The "running it cold" sanity test

At any point: `python3 recipe_pricing/htc_coverage_audit.py` and look at:
- GREEN % by recipe-uses — should be > 50% for the system to be useful
- Top RED entries — should NOT have obvious wrong picks (mayo for oil, chorizo for andouille, etc.)
- Bottom 30 GREEN entries — should look like real food matches with sensible cents/g

If GREEN % drops between runs, something regressed.

Also: pick 5 recipes from the latest 12wk plan output, look up each ingredient's resolution in `concept_resolution.json`, check what SKU `concept_index.json` would buy, and verify the SKU is the right food. Don't trust the cost number alone.
