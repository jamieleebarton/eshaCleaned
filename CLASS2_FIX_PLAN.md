# Class-2 fix plan — re-tag golden files, re-encode, regression-test

**Premise:** the canonical_path taxonomy is correct, but consensus_full_corpus_audit.csv (and downstream consensus_htc_tagged.csv + priced_products_v2.db + food_slot_registry.csv) tag specific spices/sauces/butters at generic parent paths. That generates registry entries like `'spice blend nutmeg' @ gE/f6/slot=2B` instead of `'nutmeg' @ gE/f2/slot=2B`. Recipe encoder lookups for bare `"nutmeg"` then miss, food_slot collapses to `00`, and distinct foods (nutmeg/mace/cardamom/cloves) all get the same htc.

**Goal:** re-tag the master file → regenerate downstream → re-encode recipes + retail → run planner V5 → confirm no regressions vs V4 (95.37% calculable, $966/12wk).

---

## Phase A — Audit scope (no code changes)

For each Class-2 collision, compute exactly which FDC rows in `consensus_full_corpus_audit.csv` need re-tagging. Output: `audit_results/retag_plan.csv`.

**Collision classes to enumerate:**

| Class | Bad cp pattern | Re-tag to | Title-token guard |
|---|---|---|---|
| A1 — pure spices | `Pantry > Spices & Seasonings > Spice Blend` | `Pantry > Spices & Seasonings > Nutmeg` (etc.) | title contains exactly one of: nutmeg, cardamom, cloves, mace, anise, saffron, fenugreek, sumac, juniper |
| A2 — wines | `Beverage > Mixes > Slushie Mix` | `Beverage > Wine` (drinking) or `Pantry > Cooking Wines` (cooking) | title contains: red wine, white wine, sherry, port, marsala, madeira, burgundy, chardonnay, rioja, etc. |
| A3 — peanut/almond butters | `Snack > Bars > Protein Bars` | `Pantry > Nut Butters > Peanut Butter` (or > Almond Butter) | title contains: peanut butter, almond butter |
| A4 — orange marmalade | `Pantry > Spreads > Lime Curd` | `Pantry > Spreads > Marmalade` | title contains: marmalade |
| A5 — onion powder | `Pantry > Spices & Seasonings > Seasoning` (generic) | `Pantry > Spices & Seasonings > Onion Powder` | title contains: onion powder |
| A6 — extracts | `Pantry > Spices & Seasonings > Spice Blend` | `Pantry > Baking Extracts > Almond Extract` (etc.) | title contains: rum extract, maple extract, almond extract, etc. |

**Time:** 30 min. Output: rerag_plan.csv with `(fdc_id, current_cp, new_cp, scope_class, title)` ranked by impact.

**Gate:** review the rerag_plan.csv before Phase B mutates the master file.

---

## Phase B — Re-tag consensus_full_corpus_audit.csv

Apply the rerag_plan to the master file in-place (with backup). Only `canonical_path` and `retail_leaf_path` columns change.

**Backup:** `consensus_full_corpus_audit.csv.before_class2`

**Verification mid-phase:** spot-check 5 random FDCs from each class — confirm new cp.

**Time:** 10 min after rerag_plan is approved.

---

## Phase C — Regenerate consensus_htc_tagged.csv

Re-run `recipe_mapper/v1/tag_consensus_with_htc.py` on the new master. Outputs new htc_codes that match the new canonical_paths.

**Verification:** for each fixed FDC, confirm htc_code is now the spice-specific code (e.g. `E22B0001` for nutmeg, distinct from cloves/mace/cardamom).

**Time:** 5–10 min (script runs on 462k FDC rows).

---

## Phase D — Update priced_products_v2.db

The DB is already linked to FDC ids. Two paths:

**(D1)** Re-import from updated `consensus_full_corpus_audit.csv`. Cleanest if there's an importer.

**(D2)** Direct SQL `UPDATE`: `consensus_canonical = new_cp WHERE fdc_id IN (SELECT fdc_id FROM rerag_plan)` then re-derive `htc_code/htc_form_code/htc_full_code` from new cp via the encoder.

I'll inspect the existing importer (`build_priced_products_v2.py` mentioned earlier in repo) before choosing.

**Backup:** `priced_products_v2.db.before_class2`

**Verification:** spot-check `Great Value Nutmeg, 2 oz` SKU — `consensus_canonical` should be `Pantry > Spices & Seasonings > Nutmeg`, `htc_code` should be `E22B0001` (or whatever new pattern emerges).

**Time:** 15–30 min.

---

## Phase E — Rebuild food_slot_registry

Find and run the registry-build script (likely `recipe_mapper/v1/htc/build_food_slot_registry.py`). Verify new bare-spice entries appear:

- `(E, 2, 'nutmeg')` → slot 2B
- `(E, 2, 'cardamom')` → slot 5H  
- `(E, 2, 'cloves')` → slot 41
- `(E, 2, 'mace')` → slot ??
- `(F, A, 'orange marmalade')` → marmalade-specific slot
- `(A, 0, 'peanut butter')` → nut-butter-specific slot

**Verification:** `head food_slot_registry.csv | grep -E '(nutmeg|cardamom|cloves)'` shows bare entries at family 2.

**Time:** 5–10 min.

---

## Phase F — Re-encode recipe ingredients + re-stamp recipes_unified

```
python3 recipe_mapper/v1/tag_ingredients_with_htc.py
python3 planner/scripts/restamp_recipes_unified_htc.py
mv recipes_unified.csv recipes_unified.csv.before_class2
mv recipes_unified.htc_fixed.csv recipes_unified.csv
```

**Verification:** spot-test via test_encoder.py — assert nutmeg/cardamom/cloves now produce DISTINCT htc_codes.

**Time:** 5 min.

---

## Phase G — Rebuild downstream pipeline

```
python3 planner/scripts/build_recipe_concept_grams.py
python3 planner/scripts/build_concept_index.py
python3 planner/scripts/build_concept_resolution.py
cd planner && python3 build_concept_tensor_cache.py && cd ..
```

Compare to V4 baseline:
- exact-tier % at concept-key level (V4: 29.4%) — should rise (more recipe items hit specific FDC htcs)
- NO_MATCH count (V4: 667 keys) — should drop slightly
- recipe-level calculability (V4: 95.37%) — should hold or rise

**Time:** 10 min.

---

## Phase H — Planner V5 + audit + regression

```
HESTIA_BEAM_K=50 python3 planner/scripts/multi_week_ours.py \
    --weeks 12 --people 4 --cal 2000 --mode thrifty \
    --out audit_results/multi_week_ours_12w_v5.json
python3 recipe_pricing/picked_recipe_audit.py
python3 tests/test_encoder.py
```

**Acceptance criteria** (vs V4):
- ✓ encoder tests: 138/138 pass
- ✓ recipe-level calculability ≥ 95.37%
- ✓ exact-tier % in picks ≥ 90.6%
- ✓ cost in $80–100/wk band ($966 ± 5%)
- ✓ no new NO_RESOLUTION lines
- ✓ IMPOSTER_TOKEN ≤ V4's 5
- ✓ spot-check picks: nutmeg → exact-tier match to specific Nutmeg pool (not Spice Blend); peanut butter → exact match to Peanut Butter pool (not via override fallback); orange marmalade → exact to Marmalade

**Time:** 15 min.

**If regression:** restore backups, investigate which rerag rule overshot.

---

## Phase I — Prune redundant overrides + extend test set

After V5 succeeds, walk `htc_cp_overrides.csv` — drop overrides where the encoder now resolves natively. Estimated: 30+ rows can come out (peanut butter cluster, sherry/port/marsala wine, orange marmalade, nutmeg/cardamom/cloves, etc.).

Add ~10 new rows to `tests/encoder_truth.csv` covering the just-fixed items so future encoder/registry regressions are caught.

**Time:** 30 min.

---

## Total estimate: 2–4 hours

**Reversibility:** every phase mutates a single file with a `.before_class2` backup. Nothing destructive.

**Order of execution:**

```
A  → review rerag_plan.csv → approval
B → C → D → E (these mutate the golden files)
F (re-encode based on new registry)
G (rebuild pipeline tensors)
H (planner + audit + tests) ← acceptance gate
I (cleanup overrides + extend tests)
```

**What this kills:**
- The nutmeg/mace/cardamom/cloves htc collision (E2000009 collapse)
- The peanut butter → Snack Bars Protein Bars mistag
- The sherry/port/marsala wine → Slushie Mix mistag
- The orange marmalade → Lime Curd mistag
- The miso/sauerkraut/pimientos F900000C collision (need to verify miso path)
- The onion powder → generic Seasoning leaf

**What it does NOT touch:**
- True product-data gaps: lovage, sake, creme fraiche, fresh mint, fresh herbs (no priced SKUs to re-tag)
- The encoder's GROUP_RULES (already fixed in earlier phases)
- The variant-pruning in build_concept_index.py (Bug 5)

---

## What I want from you before starting

Phase A's output is `audit_results/retag_plan.csv`. I'll review it with you before mutating any golden file. You sign off on which classes to re-tag, then I execute B → I in sequence. Stop and roll back if Phase H acceptance fails.

Ready to start Phase A?
