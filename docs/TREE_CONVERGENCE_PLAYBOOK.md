# Tree Convergence Playbook — Reconciling LLM Output with the FDC Canonical Tree

Companion to [`LLM_TAXONOMY_CONSOLIDATION.md`](LLM_TAXONOMY_CONSOLIDATION.md).

This document is the operational playbook: what to do once the
DeepSeek run finishes and we have ~145k LLM-classified rows that
need to be reconciled with the existing 10,416 FDC canonical paths.

The goal is **three-way convergence**: every recipe ingredient,
Walmart/Kroger product, and FDC retail row that represents the same
food shares the same `htc_code`.

```
recipe ingredient   ──┐
                      ├── same htc_code  ──→  same shoppable products
walmart product     ──┤
                      │
kroger product      ──┤
                      │
FDC retail audit    ──┘
```

When recipe and walmart converge but FDC diverges (or vice versa),
that's a divergence we have to resolve. This playbook explains how.

---

## The three buckets

Every divergence between LLM output and FDC tree falls into one of
three categories. Each has a different fix.

### Bucket 1 — LLM is creative, FDC has the right leaf → write an OVERRIDE

The FDC tree already has the correct canonical_path for this kind of
food. The LLM is just routing creatively (saying "Spice Blend (Cumin)"
instead of "Cumin", "Meal Starter" instead of "Salad Kit").

**Symptom:** the LLM emits the same non-FDC path consistently for
products that the FDC tree has at a specific leaf.

**Fix:** title-pattern override that forces the LLM emission onto the
existing FDC leaf BEFORE the fuzzy matcher runs.

**File:** `recipe_pricing/walmart_kroger_overrides.csv`

```csv
pattern,canonical_path,canonical_label,product_identity_fixed,modifier,note
\bsalad kit\b,Meal > Salads > Salad Kit,Salad Kit,Salad Kit,,LLM tends to say Meal Starter
\bground (cumin|coriander|cardamom|cloves?|nutmeg|allspice|ginger)\b,Pantry > Spices & Seasonings > {capture:1},,,, ground spice → leaf
\binfant formula\b|baby formula\b,Baby & Toddler > Infant Formula,Infant Formula,Infant Formula,,LLM puts goat-milk infant formula at Dairy
\b(powder(ed)?|nonfat dry|instant) milk\b,Dairy > Milk > Powdered Milk,Powdered Milk,Powdered Milk,,LLM sometimes goes generic Milk leaf
\b100% juice\b|\b100 percent juice\b,Beverage > Juice,Juice,Juice,,LLM says Smoothie when title is 100% juice
```

`{capture:N}` is a substitution placeholder we extract from the regex
group — handles cases like "ground X" where X is the discriminator.

**Order of operations matters:** overrides apply BEFORE fuzzy matching.
Once an override fires, the LLM's emission is discarded and the
override-specified path is used.

**Targets:** ~30–50 override rules will catch the common systematic
LLM mistakes. They accumulate iteratively — every review session
generates a few more.

### Bucket 2 — FDC tree has duplicates → MERGE one path INTO another

The LLM consistently emits one canonical path, but FDC has two or
three near-equivalent paths for the same food. The LLM is voting for
consolidation.

**Symptoms** (from `find_path_duplicates.py`):

- **Signal A** — same `htc_code`, multiple distinct `canonical_paths`
  (the food slot derivation collapses them, so they're already
  identity-equivalent at the bucket level)
- **Signal B** — same `canonical_label`, multiple distinct paths
  (naming drift — same food name under different parents)
- **Signal C** — same LLM path → multiple FDC paths (LLM votes for
  one canonical home; FDC has multiple)

**Fix:** pick the canonical path, merge the others into it. Apply the
merge over the FDC retail audit (`consensus_full_corpus_audit.csv`)
so all 462k rows update to the merged path.

**File:** `retail_mapper/v2/consensus_taxonomy_merges.csv`

```csv
old_canonical_path,new_canonical_path,note
Pantry > Oil > Olive Oil,Pantry > Oils & Vinegars > Olive Oil,naming drift
Pantry > Vinegars > Olive Oil,Pantry > Oils & Vinegars > Olive Oil,naming drift
Beverage > Juice > Juice Smoothie,Beverage > Smoothies > Smoothie,redundant smoothie
Beverage > Juice > Smoothie,Beverage > Smoothies > Smoothie,redundant smoothie
Dairy > Plant Based > Almond Milk,Beverage > Plant Milk > Almond Milk,plant milk lives in Beverage
Dairy > Plant Based > Soy Milk,Beverage > Plant Milk > Soy Milk,plant milk lives in Beverage
Frozen > Frozen Fruit > Frozen Fruit,Frozen > Fruit > Frozen Fruit Blend,specifying granularity
```

The merger pass:

1. Read `consensus_taxonomy_merges.csv`
2. For every row in the FDC audit whose `canonical_path` matches an
   `old_canonical_path`, rewrite it to `new_canonical_path`
3. Write a decisions log: `consensus_taxonomy_merges_applied.csv`
   showing every rewrite for traceability
4. Rebuild `food_slot_registry.csv` (slots reshuffle after merges,
   though usually only modestly — the food name is preserved)
5. Rebuild HTC codes for all affected products

**Decision criteria for whether to merge:**

- Are the products at both paths *really* the same kind of food?
- Does FDC have a strong reason for the split (different
  preparation, different storage, different nutritional profile)?
- Does the LLM consistently pick one or the other?

When in doubt: **trust the LLM's choice as the canonical name** and
merge the FDC duplicate into it. The LLM has seen 145k examples and
chose one phrasing; that's a stronger vote than the original FDC
curator who saw a fraction of that.

**Targets:** ~50–150 merge rules in the first round. Tree shrinks
from 10,416 → ~9,500–10,000 paths. Subsequent rounds taper off.

### Bucket 3 — LLM is right, FDC is missing → MINT a new canonical path

The LLM emits a canonical path that doesn't exist in the FDC tree at
all, AND it's a real food with multiple instances (so it's not just
a one-off creative emission).

**Symptom:** rows in `cleanup_review_queue.csv` whose
`llm_canonical_path` is novel and supported by ≥3 distinct products
sharing it.

**Fix:** append the new path to the canonical universe.

**File:** `retail_mapper/v2/canonical_paths_new.csv`

```csv
canonical_path,canonical_label,parent_path,seed_rationale
Beverage > Plant Milk > Pistachio Milk,Pistachio Milk,Beverage > Plant Milk,LLM tagged 47 products here; no existing FDC path
Pantry > Spices & Seasonings > Aleppo Pepper,Aleppo Pepper,Pantry > Spices & Seasonings,niche spice not in FDC tree
Beverage > Plant Milk > Hemp Milk,Hemp Milk,Beverage > Plant Milk,LLM tagged 14 products
Frozen > Smoothie Bowls > Acai Bowl,Acai Bowl,Frozen > Smoothie Bowls,LLM tagged 89 products
```

The minting pass:

1. Read `canonical_paths_new.csv`
2. Append each new path to the canonical universe
3. Mint a food slot in `food_slot_registry.csv` under the appropriate
   `(group, family)` bucket
4. Re-encode HTC codes for products that now match the new path

**Decision criteria for whether to mint:**

- ≥3 distinct products at the same novel path (single instance is
  probably an LLM hallucination)
- Path follows existing tree conventions (parent matches existing
  parent paths; leaf is a real food name)
- Doesn't duplicate an existing path (would be Bucket 2 instead)

**Targets:** ~20–50 new paths in the first round. Mostly niche / new
foods that the original FDC audit didn't see (regional ingredients,
new product categories like Smoothie Bowls).

---

## The iteration loop

```
input:  full_llm_run.live.jsonl  (DeepSeek output, 145k rows)
        consensus_full_corpus_audit.csv  (FDC tree)

iteration:
  while dedup_candidates_above_threshold OR unmatched_above_threshold:

    1. Look at top 50 rows of cleanup_review_queue.csv
         -> classify into Bucket 1 (override), 2 (merge), or 3 (mint)
         -> add lines to:
            recipe_pricing/walmart_kroger_overrides.csv          (Bucket 1)
            retail_mapper/v2/consensus_taxonomy_merges.csv       (Bucket 2)
            retail_mapper/v2/canonical_paths_new.csv             (Bucket 3)

    2. Look at top 50 rows of canonical_path_dedup_candidates.csv
         -> Signal A and B almost always Bucket 2 (merge)
         -> Signal C often Bucket 2, sometimes Bucket 1
         -> append to consensus_taxonomy_merges.csv

    3. Apply merges over the FDC audit
         python3 retail_mapper/v2/apply_consensus_overrides.py \
             --merges retail_mapper/v2/consensus_taxonomy_merges.csv \
             --new-paths retail_mapper/v2/canonical_paths_new.csv

    4. Rebuild the food slot registry (slots reshuffle after merges)
         python3 recipe_mapper/v1/htc/build_food_slot_registry.py

    5. Re-run cleanup over the LLM output (with updated overrides + tree)
         python3 recipe_pricing/cleanup_llm_output.py

    6. Re-run dedup analysis
         python3 recipe_pricing/find_path_duplicates.py

    7. Compare candidate counts to previous round
         -> if dropped by ≥30%, continue another round
         -> if plateau, stop

output: recipe_pricing/output/api_cache_taxonomy_v2.csv
        recipe_mapper/v1/output/recipe_ingredient_taxonomy_v2.csv
        recipe_mapper/v1/output/recipe_ingredient_join_audit.csv
        retail_mapper/v2/consensus_full_corpus_audit.csv  (FDC, post-merge)
```

**Expected rounds:** 2–3 before convergence. Each round takes 10–20
minutes (no LLM calls — just rule application + re-encoding).

---

## Three-way convergence verification

After each iteration, run the assertion suite. The
`recipe_ingredient_join_audit.csv` already encodes the
three-way join status per ingredient — its `join_status` column is one
of:

- `both` — recipe ingredient has a matching code in BOTH FDC retail
  audit AND Walmart/Kroger cache
- `retail_only` — matches FDC retail but no Walmart/Kroger product
- `walmart_only` — matches Walmart/Kroger but FDC retail has no
  product at this code
- `unmatched` — code matches nothing else

**Target metrics:**

| metric | current (pre-LLM-run) | target |
|---|---|---|
| top 200 ingredients with `join_status = both` | 99% | ≥99% |
| top 500 ingredients with `join_status = both` | 94% | ≥97% |
| all 74,624 ingredients with `join_status ∈ {both, retail_only, walmart_only}` | 99.8% | ≥99.8% |
| `unmatched` count | 199 | ≤100 |
| `food=00` rate (recipe ingredients) | 8.3% | ≤5% |
| `food=00` rate (walmart/kroger) | 2.3% | ≤2% |
| canonical_path count (FDC tree) | 10,416 | ~9,500 (post-merge) |

The "both" rate at the top of the recipe-frequency distribution is
the most important — those are the ingredients that show up in the
most recipes, so getting them all to join means recipe pricing covers
the long tail of usage.

---

## Bucket triage decision tree

When classifying a divergence, use this tree:

```
                    LLM emits canonical_path X
                            │
                            ▼
              ┌─── Does X exist in FDC tree exactly?
              │
              │ YES                                           NO
              ▼                                               ▼
       JOIN WORKS — done                       Is X conceptually correct?
                                                    │
                                                    │ YES
                                                    ▼
                                       Is there an existing FDC path
                                       that means the same thing?
                                            │
                                            │ YES                NO
                                            ▼                    ▼
                                      Bucket 2: MERGE         Bucket 3: MINT
                                      (LLM's X into FDC's     (X is genuinely new,
                                      existing path, OR        add to canonical
                                      vice versa, by row       universe)
                                      count)
                                                    │ NO (X is wrong)
                                                    ▼
                                       Bucket 1: OVERRIDE
                                       (force LLM to use FDC's leaf)
```

**Quick heuristics:**

- **High-volume LLM emission (>50 rows) at a path that's not in FDC** →
  almost certainly Bucket 2 (merge with an existing FDC variant) or
  Bucket 3 (genuine new concept)
- **LLM consistently emits "Spice Blend (X)" or "Sauce (Y)" or
  similar generic-with-modifier** → Bucket 1 (override to specific leaf)
- **Two FDC paths look like minor naming variants of each other** →
  Bucket 2 (merge)
- **Single LLM emission at a novel path** → ignore (probably noise),
  or just include it in the unmatched residual

---

## File reference

### Input files (read by the convergence loop)

- `recipe_pricing/data/full_llm_run.live.jsonl` — DeepSeek raw output
- `recipe_pricing/data/full_llm_input.csv` — input rows (title + source)
- `retail_mapper/v2/consensus_full_corpus_audit.csv` — FDC canonical tree

### Curated rule files (the convergence loop appends to these)

- `recipe_pricing/walmart_kroger_overrides.csv` — Bucket 1 rules
- `retail_mapper/v2/consensus_taxonomy_merges.csv` — Bucket 2 rules
- `retail_mapper/v2/canonical_paths_new.csv` — Bucket 3 mints

### Pipeline scripts

- `recipe_pricing/cleanup_llm_output.py` — normalize + HTC encode
- `recipe_pricing/find_path_duplicates.py` — dedup candidate finder
- `retail_mapper/v2/apply_consensus_overrides.py` — apply merges + new paths
- `recipe_mapper/v1/htc/build_food_slot_registry.py` — rebuild registry

### Output files (regenerated each round)

- `recipe_pricing/output/api_cache_taxonomy_v2.csv` — Walmart/Kroger tagged
- `recipe_mapper/v1/output/recipe_ingredient_taxonomy_v2.csv` — recipes tagged
- `recipe_mapper/v1/output/recipe_ingredient_join_audit.csv` — three-way audit
- `recipe_pricing/output/cleanup_review_queue.csv` — residual unmatched
- `recipe_pricing/output/canonical_path_dedup_candidates.csv` — dedup signals
- `retail_mapper/v2/consensus_full_corpus_audit.csv` — FDC tree (in place)
- `recipe_mapper/v1/htc/food_slot_registry.csv` — registry (in place)

---

## What "done" looks like

After 2–3 convergence rounds:

1. **Recipe ingredients tagged** — every recipe ingredient has an
   `htc_code` and a `canonical_path` that exists in the FDC tree.
2. **Walmart/Kroger products tagged** — same.
3. **FDC tree consolidated** — duplicate paths merged, redundant
   leaves collapsed. Path count down from 10,416 to ~9,500.
4. **Food slot registry stable** — every food in the tree has a
   minted slot; new ingredients/products map onto existing slots
   rather than minting duplicates.
5. **Three-way join works** — top 500 recipe ingredients all
   resolve to FDC and Walmart/Kroger products via code equality.
6. **Override + merge + mint files** archived under version control —
   reusable for future iterations as new corpora come in (other
   retailers, additional recipe sources, etc.).

The convergence is a one-time effort to reconcile the LLM's voice
with the FDC tree's voice. Once it's done, every new corpus we run
through the same cleanup pipeline inherits the consolidated tree
without further work — the rules are stable.

---

## Implementation status

**Done:**
- LLM run script (`run_full_csv_parallel.py`)
- Walmart/Kroger adapter (`build_walmart_kroger_for_llm.py`)
- Combined input builder (`build_full_llm_input.py`)
- Cleanup orchestrator (`cleanup_llm_output.py`) — already preserves
  all facets, emits both join + SKU HTC codes
- Dedup candidate finder (`find_path_duplicates.py`)

**Running:**
- Full 145k DeepSeek classification (~5h ETA, ~$15 spend)

**Pending the run completing:**
- First-round override + merge + mint authoring (manual review of
  top candidates after first cleanup pass)
- Iterate the convergence loop until candidates plateau
- Final three-way audit regeneration
