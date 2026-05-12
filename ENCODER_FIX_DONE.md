# Encoder fix complete (Phases 0–6)

**Started:** with `htc_cp_overrides.csv` band-aiding 280+ items per-string.
**Done:** 8 architectural rules in the encoder + 138-test pre-build gate.

## Phase results, end to end

| Phase | What | Outcome |
|---|---|---|
| 0 | Measure scope across 4.7M-line corpus | 38 high-confidence REAL_BUGs identified, 6 true gaps confirmed |
| 1 | Read encoder (`recipe_mapper/v1/htc/encoder.py` 739 lines) and document architecture | `ENCODER_ARCHITECTURE.md` produced |
| 2 | Code-level fix list | 8 precedence-guard rules drafted |
| 3 | Apply fixes, re-stamp 4.7M lines | 23,857 unique items changed group; 2,319,244 recipe lines re-stamped |
| 4 | Run planner V3, audit | exact-tier 58% → **91.4%** in picks; cost $1,048 → $1,012; coverage 91.7% → 92.35% |
| 5 | Delete redundant overrides | `htc_cp_overrides.csv`: 292 → 236 (56 dropped, encoder now native) |
| 6 | Ground-truth test set + runner | `tests/test_encoder.py` + `tests/encoder_truth.csv` (138 rows, all pass) |

## What was changed in this work session

- `recipe_mapper/v1/htc/encoder.py` — 8 new precedence-guard rules at top of GROUP_RULES (broth/stock, baking soda, extracts, chocolate chips, coconut flakes, cayenne, dried onion flakes, sauerkraut)
- `recipe_mapper/v1/output/recipe_ingredient_htc_tagged.csv` — regenerated (74,624 items)
- `recipe_mapper/v1/output/recipes_unified.csv` — re-stamped (4,729,696 lines, 49% changed htc_code)
- `planner/data/recipe_concept_grams.json` — rebuilt
- `planner/data/concept_index.json` — rebuilt (with Bug 5 variant pruning still active)
- `planner/data/concept_resolution.json` — rebuilt
- `planner/data/tensor_cache/recipe_db_tensors.pt` — rebuilt
- `recipe_pricing/htc_cp_overrides.csv` — pruned 292 → 236
- `tests/encoder_truth.csv` — new (138 ground-truth rows)
- `tests/test_encoder.py` — new (CI gate runner)
- `audit_results/multi_week_ours_12w_v3.json` — new 12-week plan
- `audit_results/12WEEK_AUDIT_REPORT_V3.md` — new audit report

## What remains

**Class-2 mistagged FDC entries** — encoder produces correct htc but `consensus_htc_tagged.csv` has wrong cp for that htc:

- peanut butter / creamy peanut butter / almond butter (htc A0FZ000Q / A001000P → Snack > Bars > Protein Bars)
- sherry wine / port wine / marsala wine variants (htc D8000007 → Beverage > Mixes > Slushie Mix)
- onion powder (generic Seasoning leaf)
- nutmeg / mace / cardamom / cloves / fenugreek / star anise (generic Spice Blend leaf — 11 keep-for-now overrides do this work)
- rum extract / maple extract (generic Spice Blend instead of Baking Extracts specific leaf)

**Fix path for Class-2:** either (a) re-tag the offending FDC rows in `consensus_htc_tagged.csv`, or (b) build an `(htc_code → cp)` override layer that runs before `htc_to_path` lookup in `build_recipe_concept_grams.py`. Either is a separate workstream.

**True product-data gaps** (no priced SKU exists):
- lovage, lime curd, sake, creme fraiche, vegetable spread, haddock — confirmed earlier
- frozen ginger (7.7k recipe lines), candied fruit (5.9k), fresh herbs (mint, lovage), miso, frozen squash

These need SKU additions to `priced_products_v2.db`, not encoder fixes.

## How to run the test gate

```
python3 tests/test_encoder.py
```

Returns 0 if all 138 pass, non-zero on any failure. Run after ANY change to:
- `recipe_mapper/v1/htc/encoder.py`
- `recipe_mapper/v1/htc/food_slots.py` / `food_slot_registry.csv`
- `recipe_pricing/htc_cp_overrides.csv`
- `recipe_mapper/v1/output/consensus_htc_tagged.csv`

## Trajectory

| State | Calculable | Cost / 12wk | Exact-tier in picks |
|---|---:|---:|---:|
| `.before_full_audit` snapshot (broken) | 0.27% | — | — |
| After previous-AI's edit | 74.30% | $1,035 | 58% |
| After my Bugs 1–6 (band-aid round) | 91.70% | $1,048 | 57.5% |
| **After encoder fix (this round)** | **92.35%** | **$1,012** | **91.4%** |
