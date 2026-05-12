# Calculator Iteration Plan — Hestia as Blueprint

## Goal

Build a calculator + planner pipeline that:
1. Picks the right SKU per ingredient (whole vs sliced ham, Dijon vs honey mustard, etc.)
2. Computes correct macros from picked SKU's own FNDDS or SR28
3. Emits a sane shopping list with multi-package size matching to recipe grams
4. Holds up over multi-week plans (no leftover absurdities, no SKU drift, no compounding bridge errors)

We treat Hestia's existing pipeline as the **blueprint** — borrow the patterns that work, replace the parts that don't, iterate weekly.

---

## What Hestia has that we don't

### Multi-week test infrastructure (in `~/Desktop/Hestia/api/scripts/`)

| Script | What it does |
|---|---|
| `multi_week_test.py` | Runs N weeks back-to-back, checks for plan stability |
| `prove_leftovers_30w.py` | 30-week leftover ledger — every frozen item tracked in/out |
| `generate_24_weeks.py` | 24-week plan corpus dump for audit |
| `pantry_simulation.py` | Carries pantry state across weeks |
| `audit_shopping_list_scenarios.py` | Scenario-based shopping-list audit |
| `audit_plan.py` | Per-plan correctness audit |
| `audit_ab_compare.py` | A/B compare two plan configs |
| `fiber_weekly_audit.py` | Fiber compliance over many weeks |
| `run_tier_sweep.py` / `run_tier_sweep_full.py` | Sweep through household tiers |
| `run_universe_sweep.py` | Sweep entire scoring-config universe |

We have one (`run_htc_week.py`) — single week. **Gap.**

### Calculator-side services (in `~/Desktop/Hestia/api/app/`)

| File | What it does |
|---|---|
| `services/shopping_list.py` | Aggregates ingredients across recipes, deduplicates by FPID, sums grams, looks up packages |
| `services/fpid_purchase_matcher.py` | Matches user's purchase history → recipe ingredients (pantry tracking) |
| `services/receipt_product_matcher.py` | OCR'd receipt items → FPID resolution |
| `routers/cart.py` | Builds the actual cart from a plan |
| `routers/optimizer.py` | Cost optimization layer |
| `routers/shopping_list.py` | Shopping-list endpoint |
| `routers/preview.py` | Plan preview computation |
| `routers/plan.py` | Plan endpoint orchestration |
| `models/plan.py` | Plan data model |

We have `recipe_pricing/calculate_recipe_cost_v7.py` (single recipe) and `batch_calculate_all.py`. **No cart aggregation, no pantry carry-over, no multi-recipe shopping-list dedup.** Gaps.

---

## The plan — iterate weekly toward parity

### Phase 1 — Multi-week scaffolding for our planner

1. Port `multi_week_test.py` → `planner/scripts/multi_week_ours.py` (concept-keyed)
2. Run **4 consecutive weeks** through ours; capture per-week:
   - Total cost, recipes picked, recipe variety, leftover state
   - Shopping list (deduplicated by concept_key)
   - Macros aggregate (vs scoring config target)
3. Run same 4 weeks through Hestia (vanilla)
4. Diff: per-week recipe overlap, cost diff, veg compliance diff, recipe-name overlap

### Phase 2 — Aggregate shopping list (multi-recipe dedup)

Currently each recipe is calculated independently. Hestia aggregates:
- 5 recipes that all use butter → 1 line on shopping list with summed grams
- Pick package size that covers the total
- Track pantry leftovers (spent < bought = pantry surplus)

Build `recipe_pricing/aggregate_shopping_list.py`:
- Input: list of recipe_ids + servings each
- Output: [(concept_key, total_grams_needed, picked_sku, package_count, total_cents)]
- Use multi-package model: 380g butter need + 4-pack 113g sticks → 4 sticks, 452g, $X

### Phase 3 — Per-recipe Hestia calculator parity

Hestia's per-recipe cost computation lives in `app/services/shopping_list.py`. Read it, identify:
- How it picks a SKU per ingredient (which fields, what filter)
- How it accumulates cost (line vs package)
- How it handles pantry overlap

Diff against our `calculate_recipe_cost_v7.calculate()`. For each algorithm difference, decide: keep ours, copy Hestia's, or hybrid.

### Phase 4 — Pantry carry-over

After a week's plan, we have:
- "Pantry surplus" (bought 1 lb butter, used 113g; 340g left over)
- "Frozen leftovers" (cooked extra; stored)

Next week's plan should:
- Subtract pantry surplus from new ingredient needs
- Score recipes that use existing frozen leftovers higher

Hestia does this via `pantry_simulation.py` + `prove_leftovers_30w.py`. Port the state-carrying logic to our planner.

### Phase 5 — Drift detection

Run 12 weeks back-to-back with same scoring config. Track:
- Mean weekly cost (should be stable)
- Variance in recipe variety (shouldn't repeat same 4 recipes for 12 weeks)
- Cumulative bridge errors (any baby-food/lure pick = compounding)
- Shopping list dedup effectiveness (are we double-buying butter every week?)

Report: drift score per week.

### Phase 6 — Calculator A/B harness

Stand up `compare_calculators.py` that:
- Takes a recipe_id
- Runs Hestia's per-recipe calc
- Runs ours
- Diffs: cost, macros, picked SKU, shopping list
- Buckets by where they diverge (SKU pick, macro source, package selection)

Run on 1000 recipes; surface top 50 divergence patterns.

### Phase 7 — Apply fixes one at a time

For each divergence pattern (in priority order):
1. Decide which side is right (Hestia / ours / synthesis)
2. Apply the targeted fix
3. Re-run multi-week + A/B harness; verify no regression
4. Document the decision (why we chose what we chose)

### Phase 8 — Convergence target

By N iterations, get:
- 4-week ours-vs-Hestia recipe overlap > 40% on shared scoring configs (currently ~8%)
- Cost diff < 15% per config (currently 20-30%)
- Veg/protein/fruit compliance within ±3pp of Hestia
- Shopping list cents-per-gram weighted-mean diff < 10%
- Zero non-food picks over 12-week sweep (already true)
- Stable plan output across 12 weeks (no >2x recipe-repeat compared to Hestia)

---

## Iteration loop

Each cycle (~ once per session):
1. Pick one Hestia-vs-ours divergence pattern
2. Build minimal repro
3. Identify root cause (data / encoder / scoring / calc-algo)
4. Fix, with regression test
5. Re-run multi-week + battery
6. Update this doc with what changed

This becomes our discipline — every commit moves a metric, no random patches.

---

## Files this plan creates

- `planner/scripts/multi_week_ours.py` — N-week run with state carry
- `planner/scripts/compare_multi_week.py` — Hestia vs ours, per week
- `recipe_pricing/aggregate_shopping_list.py` — multi-recipe dedup + multi-package
- `planner/scripts/compare_calculators.py` — per-recipe calc A/B
- `planner/data/multi_week_results.json` — per-week dump
- `planner/data/calc_divergence_report.json` — top divergences

## What stays — already working

- HTC encoder + form-aware encoding
- Concept_index + concept_resolution + multi-package model
- recipes2.csv overlay for per-recipe macros + food_groups
- FNDDS first / SR28 fallback in calculator
- 00000000 / Non-Food / baby food / lure quarantine
- Anti-modifier filter (gluten-free / skim / etc.)
- Recipe-leaf token re-ranking inside priced concepts
- Staples test gate (16/17 staples)
- Macro sanity gate (200 recipes / 1858 lines / 0 math errors)

## Convention going forward

- No new regex on canonical_path (HTC positions are the truth)
- No new heuristic-derived food_groups (recipes2.csv overlay is authoritative)
- No SKU pick without recipe-leaf-token filter
- No NO_MATCH that survives without a parent_path or form_only fallback
- All new tests get a regression entry in `planner/scripts/staples_test.py` or `macro_sanity_test.py`

---

This is the plan. Each phase is a session's work; phases 6-8 are the iteration loop forever.
