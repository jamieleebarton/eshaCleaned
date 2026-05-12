# Plan: fix the recipe-side HTC encoder upstream (kill the band-aids)

**Premise:** the recipe encoder in `recipe_mapper/v1/htc/encoder.py` (and related) is producing wrong `htc_code` / `canonical_path` for many ingredient-line strings ("plantains" → Frozen Fruit, "chickpeas" → Snack > Chips, "tomato sauce" → Plant Based Cheese, etc.). Every override row in `htc_cp_overrides.csv` is a band-aid covering one misfire of that encoder. The 161+ overrides only cover items the 12-week thrifty plan happened to surface; the other ~99.95% of the recipe corpus has the same encoder running, producing the same kinds of wrong codes, never inspected.

**Goal:** fix the encoder at source. Reduce override CSV to 0 rows. Re-encode all 4.7M recipe lines. Confirm calculability stays ≥ 90% AND picks stay correct. Add ground-truth tests so this doesn't regress.

**Non-goals:** no further band-aids; no resolution-tier edits; no priced-side work.

---

## Phase 0 — Measure the scope of encoder misfires (no code changes)

Want to know HOW broken the encoder is across the full corpus, not just within the 233 picked recipes.

**Steps**
1. Scan `recipe_mapper/v1/output/recipes_unified.csv` (4.7M lines). For each unique `(ingredient_item, htc_code, derived_cp_via_consensus_htc_tagged)` tuple, count occurrences.
2. For each row, classify whether the derived `canonical_path` is plausible given the `ingredient_item` text. Use a heuristic: leaf-token overlap between `ingredient_item` and `canonical_path.split(" > ")[-1]`. No overlap → suspected misfire.
3. Output a CSV: `encoder_misfire_leverage.csv` with columns `ingredient_item, htc_code, current_cp, recipe_line_count, suspected_misfire_reason`. Sort by `recipe_line_count DESC`. Cap at top 500 (covers ~95% of suspected misfires by volume).
4. Cross-check: for each suspected misfire row, query `priced_products_v2.db` to find what canonical_path real SKUs with that ingredient name actually have. Append `priced_cp_top_3` column. Now we know: this item is mis-encoded, AND here's where the right cp lives in priced.

**Output:** `recipe_pricing/encoder_misfire_leverage.csv` (~500 rows). Estimated ~50–80% of misfire volume comes from <100 distinct items.

**Time:** ~30 min.

**Decision point:** if the leverage table shows a few dozen items concentrate >70% of misfires, the encoder likely has a small number of broken rules — Phase 2 is bounded. If misfires are diffuse across thousands of items, the encoder has structural problems and Phase 3 might need a wider rewrite.

---

## Phase 1 — Read the encoder, document how it works (no code changes)

I haven't read `recipe_mapper/v1/htc/encoder.py` yet. Until I do, I'm guessing about its structure. So before proposing a fix:

**Steps**
1. Read `recipe_mapper/v1/htc/encoder.py` end to end.
2. Read `recipe_mapper/v1/tag_ingredients_with_htc.py` and `recipe_mapper/v1/tag_consensus_with_htc.py` (these were in the modified files at session start).
3. Read `recipe_mapper/v1/output/consensus_htc_tagged.csv`'s schema and how the encoder consults it.
4. Identify:
   - The encoder's input: just `ingredient_item` text, or also `display`, `qty`, `unit`, modifier facets?
   - The encoder's lookup mechanism: rule table? decision tree? FNDDS lookup? LLM call?
   - The data sources it trusts: which CSVs / tables provide the (text → htc) mapping?
   - Where each htc-code component (group/family/food/form/processing/ptype) gets its value.
5. Write `ENCODER_ARCHITECTURE.md` — a one-pager that explains the pipeline so future sessions don't have to re-discover it.

**Output:** `recipe_mapper/v1/htc/ENCODER_ARCHITECTURE.md`.

**Time:** ~45 min.

---

## Phase 2 — Diagnose specific broken rules (no code changes)

Cross-reference Phase 0's leverage table with Phase 1's encoder map. For each high-volume misfire, identify the SPECIFIC rule (or absent rule) responsible.

Examples we already know:
- **F800000X (tomato sauce / pesto / broth → "Plant Based Cheese > Spaghetti with Sauce")** — root cause is `consensus_htc_tagged.csv` has exactly one FDC entry for that htc_code and that one is mistagged. Encoder consults the file and inherits the mistag. Fix has two parts: (a) add a min-count gate at consult-time (already done in `build_recipe_concept_grams.py:56-74`), (b) fix the underlying FDC tagging in `consensus_htc_tagged.csv` or the upstream `tag_consensus_with_htc.py`.
- **chickpeas → Snack > Chips** — encoder's text-classification rule probably matched "chip" substring or similar. Should classify "chickpeas" / "garbanzo" to `Pantry > Beans > Garbanzo Beans`.
- **plantains → Frozen > Frozen Fruit** — encoder's category routing for fruits-vs-vegetables miscategorizes plantains.
- **avocado → Frozen > Frozen Fruit** — same class as plantains.
- **applesauce → Snack > Dried Fruit** — encoder mis-routes applesauce.

**Steps**
1. For each top-30 leverage row, point to the specific encoder code path that produces it. If the rule is in a lookup CSV, point to the row. If it's in a decision-tree, point to the branch.
2. Write the corrected expected output for each.
3. Group fixes into categories: "lookup table edit", "rule logic change", "FNDDS upstream re-tag", "needs LLM pass".

**Output:** `recipe_mapper/v1/htc/ENCODER_FIX_LIST.md` — a table of (item, current_wrong_output, expected_output, where_to_fix, fix_type).

**Time:** ~60 min, depends on Phase 1 findings.

---

## Phase 3 — Fix the encoder, re-encode the corpus

**Steps**
1. Apply the rule corrections from Phase 2's fix list.
2. Re-run whatever script produces `recipes_unified.csv` (or `restamp_recipes_unified_htc.py` per the modified files list — that name suggests it re-stamps htc codes onto recipes_unified). Confirm.
3. Run a before/after diff: how many recipe lines changed `htc_code` / derived `canonical_path`? How many of the Phase 0 leverage table rows are now correct?
4. If the diff is bigger than expected, sanity-check a sample of newly-changed lines manually.

**Output:** updated `recipes_unified.csv`, encoder before/after diff report.

**Time:** ~2–4 hours, depends on encoder structure and how many rule changes are needed.

---

## Phase 4 — Rebuild pipeline, re-run planner, re-audit

Standard rebuild order:
```
python3 planner/scripts/build_recipe_concept_grams.py
python3 planner/scripts/build_concept_index.py
python3 planner/scripts/build_concept_resolution.py
cd planner && python3 build_concept_tensor_cache.py && cd ..
HESTIA_BEAM_K=50 python3 planner/scripts/multi_week_ours.py \
    --weeks 12 --people 4 --cal 2000 --mode thrifty \
    --protein-pct 15 --leftover-pct 0.75 \
    --out audit_results/multi_week_ours_12w_v3.json
python3 recipe_pricing/picked_recipe_audit.py audit_results/multi_week_ours_12w_v3.json
```

**Acceptance criteria** (compare against V2):
- Recipe-level calculability ≥ 91.7% (current). Should ideally improve as encoder fixes recover recipes that previously had NO_MATCH lines.
- NO_RESOLUTION lines in picked recipes = 0 (V2 already met this).
- IMPOSTER_TOKEN flags ≤ 1.
- Resolution tier mix: `exact` share grows (was 57.5%); `path_only` share shrinks (was 39.9%) — because correct htc_codes now match exactly instead of falling through.
- Cost stays in same neighborhood ($85–$95/wk). If it spikes, encoder change disrupted something — investigate.

**Output:** `audit_results/12WEEK_AUDIT_REPORT_V3.md`.

**Time:** ~1 hour.

---

## Phase 5 — Delete redundant overrides

For each row in `htc_cp_overrides.csv`, check whether the encoder now produces the right cp on its own. If yes, delete the override row. If no, keep it (the encoder still misfires for that item).

**Goal:** override CSV row count goes from ~160 → ideally <20 (the residual non-fixable items: facet-based overrides, deliberate substitutes for true gaps, etc.).

**Time:** ~30 min.

---

## Phase 6 — Ground-truth tests (CI gate)

User memory `feedback_durable_fixes_not_whackamole`: "fix architecture (resolver tiers + SKU sanity gate + ground-truth tests), not more reclass rules." This is the test set the encoder doesn't have today.

**Steps**
1. Build `tests/encoder_truth.csv` — ~50–100 rows of `(ingredient_item, expected_canonical_path, expected_htc_family)`. Cover: produce (avocado, plantains, bell peppers, onions); proteins (chicken breast, ground beef, salmon, hot dogs); pantry (tomato sauce, pasta sauce, applesauce, broth, oil); dairy (milk, mozzarella, sour cream); spices; flours; common substitutes.
2. Write a runner: `tests/test_encoder.py` — loads test CSV, runs each `ingredient_item` through the encoder, asserts cp and htc family match expected.
3. Wire into pre-commit / pre-build hook so any encoder change must pass.

**Output:** `tests/encoder_truth.csv`, `tests/test_encoder.py`. Pre-build gate.

**Time:** ~1 hour.

---

## Order, dependencies, total estimate

```
Phase 0 (measure) → Phase 1 (read) → Phase 2 (diagnose) → Phase 3 (fix encoder)
                                                         ↓
                                                   Phase 4 (rebuild + audit)
                                                         ↓
                                            Phase 5 (delete overrides) → Phase 6 (tests)
```

**Total wall time:** ~6–9 hours of focused work, depending on encoder complexity.

**Reversibility:** Every phase is reversible. Phase 3 mutates `recipes_unified.csv` — back it up first. The current `htc_cp_overrides.csv` is in git; can restore.

---

## What this plan deliberately does NOT do

- Does not touch `build_concept_resolution.py` tier ladder.
- Does not propose new resolution tiers.
- Does not move SKUs in the priced database (priced side is mostly correct; the bugs we found there — flavored-pool contamination — are handled by Bug 5's structural pool-prune in `build_concept_index.py`).
- Does not run an LLM-classification pass over every item (only if Phase 2 reveals the rule logic is too complex to fix manually for some category).
- Does not chase any further per-item override.

## Decision needed before starting

Phase 0 (measure) is no-risk. Want me to start there? If the leverage table shows the misfires are concentrated in a small number of broken rules, Phases 2–5 are tractable. If they're diffuse, we may need a different approach (encoder rewrite, or LLM-assisted re-classification per memory `Use DeepSeek; don't ask`).

Before Phase 3, I'll come back with the concrete fix list (Phase 2 output) for your sign-off — so you see exactly what rules are changing before the corpus is re-encoded.
