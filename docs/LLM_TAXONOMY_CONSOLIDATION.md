# LLM Taxonomy Consolidation — Walmart/Kroger + Recipe Ingredients into the FDC Canonical Tree

## TL;DR

Sending 144,975 unclassified products and recipe ingredients through DeepSeek
gives us four things in one pass:

1. A canonical_path + facets per row (variant, flavor, form, processing,
   claims, modifier) — same shape as the curated FDC retail audit.
2. An HTC 8-char identity code per row that joins recipes ↔ retail ↔
   shoppable products by code equality.
3. A duplicate-detection dataset that exposes redundant canonical_paths in
   the existing FDC tree (different paths that should be one).
4. A new-concept queue — paths the LLM emits that don't exist in the tree
   yet but are real foods that should be added.

The expensive curation work has already been done on the FDC side
(`retail_mapper/v2/consensus_full_corpus_audit.csv` — 462,664 SKUs,
10,416 canonical_paths). Running the same prompt over the new corpora
extends that work to Walmart/Kroger and recipe ingredients without
rebuilding it.

Cost: ~$15 in DeepSeek calls. Time: ~5 hours wall clock at concurrency 30.

---

## What we're working with

### Input corpora

| Corpus | Rows | Source | Has taxonomy already? |
|---|---|---|---|
| FDC retail audit | 462,664 | USDA FoodData Central | ✓ (curated) |
| Walmart/Kroger API cache | 70,351 (deduped from 217,661) | Live retail APIs | ✗ |
| Recipe ingredients | 74,624 | Recipe corpus | ✗ |

The FDC retail audit is the source of truth. It has `canonical_path`,
`canonical_label`, `variant`, `flavor`, `form_texture_cut`,
`processing_storage`, `claims`, `modifier`, `retail_leaf_path`, FNDDS/SR28
cross-references, and review/override decisions.

### Output schema (what we emit per row)

Same 33 columns for every classified row (Walmart, Kroger, or recipe
ingredient):

```
fdc_id, source, corpus, title, retail_type,
canonical_path, canonical_label, product_identity_fixed,
variant, flavor, form_texture_cut, processing_storage,
claims, modifier, components_count, components,
htc_code, htc_sku_code,
htc_group, htc_family, htc_food,
htc_form, htc_processing, htc_ptype, htc_check,
llm_canonical_path, llm_confidence, llm_review_flags, llm_rationale,
match_method, match_confidence, htc_confidence, htc_source
```

The two HTC codes are the join layer:

- `htc_code` — identity-only, positions 5–7 zeroed. Recipe `cheese` joins to
  retail `American Cheese Slices` here. Used for "what food is this?"
- `htc_sku_code` — full code with form/processing/ptype populated. Used to
  identify the specific shoppable variant ("frozen sliced cheddar" vs
  "fresh sharp cheddar block").

The retail_path content (organic, gluten_free, kosher, every flavor and
variant) lives in the dedicated facet columns. Nothing is lost from the
LLM's response.

---

## Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. DeepSeek classification                                          │
│     run_full_csv_parallel.py at concurrency 30                       │
│     145k rows, ~$15, ~5h, 97% prompt-cache hit                       │
│     output: full_llm_run.live.jsonl                                  │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  2. Path normalization + HTC encoding                                │
│     cleanup_llm_output.py                                            │
│     - title-pattern overrides (curated rule list)                    │
│     - exact match against the 10,416 FDC canonical_paths             │
│     - token-set fuzzy match (handles "& Vinegars" vs "" naming)      │
│     - residual flagged for review                                    │
│     - derive HTC parts: group_from_canonical_path,                   │
│       family_from_identity, food_slot_registry.lookup                │
│     output: api_cache_taxonomy_v2.csv,                               │
│             recipe_ingredient_taxonomy_v2.csv,                       │
│             cleanup_review_queue.csv                                 │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  3. Dedup candidate analysis                                         │
│     find_path_duplicates.py                                          │
│     - same htc_code, distinct canonical_paths   (signal A)           │
│     - same canonical_label, distinct paths      (signal B)           │
│     - same LLM path, multiple FDC matches       (signal C)           │
│     output: canonical_path_dedup_candidates.csv                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  4. Human review + merge decisions                                   │
│     - eyeball top 100 highest-impact candidates                      │
│     - author merge rules: "consolidate path X into path Y"           │
│     - written into consensus_taxonomy_overrides.csv                  │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  5. Re-run cleanup + re-encode HTC                                   │
│     - applies the merge rules                                        │
│     - HTC codes update for affected products                         │
│     - canonical tree shrinks (10,416 → ~9,500–10,000 paths)          │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  6. Final tagged corpora + audit                                     │
│     - api_cache_taxonomy_v2.csv  (217k Walmart/Kroger via 70k unique)│
│     - recipe_ingredient_taxonomy_v2.csv                              │
│     - recipe_ingredient_join_audit.csv                               │
│     - consensus_full_corpus_audit.csv (FDC, post-merge)              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## How DeepSeek gives us deduplication signals

Three signals we can mine from the cleanup output:

### Signal A — same `htc_code`, multiple `canonical_paths`

The `htc_code` is derived from `(group, family, food_slot)` which is
keyed on `product_identity_fixed`. If two distinct canonical_paths in
the FDC tree both resolve to the same htc_code, they're the same identity
in different parents.

Example:

```
htc_code = B0010001  (Group B oils, family 0, food slot 01 = Olive Oil)

  canonical_path                              count
  Pantry > Oil > Olive Oil                    2,020
  Pantry > Oils & Vinegars > Olive Oil          243
```

Both are "Olive Oil" — different parent naming. The LLM sometimes
emits one, sometimes the other; the htc_code is identical. Merge target.

### Signal B — same `canonical_label`, multiple `canonical_paths`

Same human-readable food name showing up under different parents. The
canonical_label embeds the facets, so when two paths both end up with
identical labels, it's almost always naming drift.

Example:

```
canonical_label = "Almond Milk (Unsweetened, Original)"

  canonical_path                              count
  Beverage > Plant Milk > Almond Milk           640
  Dairy > Plant Based > Almond Milk             127
```

The LLM thinks both are the same product, but FDC's tree has them at
two different parents. One should be the canonical home.

### Signal C — same `llm_canonical_path`, multiple FDC matches

The LLM consistently emits one path; our fuzzy matcher places it at
different FDC paths because they're all near-equivalent. Strong vote
that those FDC paths are duplicates.

Example:

```
llm_canonical_path = "Beverage > Smoothies > Smoothie"

  fuzzy-matched FDC path                      count
  Beverage > Smoothies > Smoothie               412
  Beverage > Juice > Juice Smoothie             138
  Beverage > Smoothies                           94
  Beverage > Juice > Smoothie                    27
```

The LLM thinks all of these are the same thing. The FDC tree has four
near-equivalent paths. Pick the canonical one and merge the others.

---

## Why this works

1. **Single model, consistent voice.** DeepSeek classifies all 145k rows
   with the same prompt and the same examples, so its preferred phrasing
   is consistent. When it emits one canonical_path for products that the
   FDC audit had at multiple paths, the divergence is on the FDC side.

2. **High match rate to existing tree.** Smoke-test cleanup showed 92% of
   LLM outputs match an existing FDC canonical_path (38% exact, 54%
   fuzzy). Only 8% are unmatched — those go to a human-review queue.

3. **Volume + consistency.** A single LLM emission isn't evidence of
   FDC redundancy. But when 412 distinct products from Walmart/Kroger
   all classify to the same LLM path, and that path fuzzy-matches to
   four different FDC paths in proportion, that's a strong vote.

4. **Already-curated identities.** The LLM doesn't need to invent the
   tree — it works with the existing 10,416 canonical_paths as priors,
   and we let it propose new ones only when nothing fits.

---

## Override layer (the curated rule list)

Some LLM mistakes are systematic and predictable. We catch them with a
small handcrafted override CSV (`walmart_kroger_overrides.csv`) that
matches title patterns and forces the canonical_path:

| pattern | canonical_path | notes |
|---|---|---|
| `\bsalad kit\b` | `Meal > Salads > Salad Kit` | LLM tends to say "Meal Starter" |
| `\binfant formula\b\|baby formula\b` | `Baby & Toddler > Infant Formula > {modifier}` | LLM puts goat-milk infant formula at Dairy > Goat Milk |
| `\bspice blend\b.*\b(cumin\|paprika\|cinnamon)\b` | `Pantry > Spices & Seasonings > {Cumin|Paprika|Cinnamon}` | LLM keeps the generic Spice Blend |
| `100% juice\|juice from concentrate` (without "smoothie") | `Beverage > Juice` | LLM sometimes says "Smoothie" for juice |
| `\bpowder(ed)? milk\b` | `Dairy > Milk > Powdered Milk` | LLM sometimes uses generic Milk leaf |

This list grows iteratively. Every dedup-review session generates new
override rules. They're applied during cleanup before the fuzzy matcher
sees the LLM path, so the override always wins.

---

## What this gives us at the end

### Per-row outputs

Every Walmart/Kroger product and every recipe ingredient gets:

- A canonical_path that exists in the consolidated FDC tree
- A canonical_label with the parenthesized facets
- All retail-path content as separate facet columns
- Two HTC codes:
  - `htc_code` (8-char identity-only join key)
  - `htc_sku_code` (full code with form/processing/ptype)

### Cross-corpus joins

```
recipe ingredient   "garlic"            -> 6503000D
retail audit        "Spice World Garlic" -> 6503000D
walmart product     "Christopher Ranch Whole Garlic, 8 oz Mesh Bag" -> 6503000D
kroger product      "Simple Truth Organic Garlic" -> 6503000D
```

All four sources join on the same code. A recipe asking for garlic
returns priced products from both retailers.

For the variant case:

```
recipe              "whole milk"        -> htc_code=1001000$, variant=whole
retail              "Horizon Organic Whole Milk" -> htc_code=1001000$, variant=whole
walmart             "Great Value Whole Milk Half Gallon" -> htc_code=1001000$, variant=whole
recipe              "skim milk"         -> htc_code=1001000$, variant=skim
```

`htc_code` is shared (so "milk" recipes match all milks), but variant
is preserved so a "whole milk" recipe specifically can filter to
whole-milk products.

### Tree consolidation

Each iteration produces a list of dedup candidates. We review the top
N by impact (rows affected × distinct paths involved). Approved merges
get written into `consensus_taxonomy_overrides.csv` (the same file used
to maintain the original FDC audit). Rerunning the cleanup applies
them.

Expected reduction: 10,416 → roughly 9,500–10,000 canonical_paths in
the first round. Further rounds taper off as the tree converges.

### New concept queue

Paths the LLM emits that don't match anything in the FDC tree go to
`cleanup_review_queue.csv`. Review them: most are LLM creativity
(reroute to existing path via override), some are genuine new foods
that should join the tree (mint a new canonical_path + food slot).

---

## Why this is the right architecture

The alternative was the regex-based encoder
(`recipe_mapper/v1/htc/encoder.py` GROUP_RULES / FAMILY_RULES). It
worked but:

- Every edge case required another regex patch (rice vinegar matched
  "rice" before "vinegar"; kielbasa hit `\bbasa\b` for fish; meat-and-
  seafood prefix routed all meat to fish; tomato + onion modifier
  beat tomato pid).
- Two parallel inference paths existed (one for FDC retail via
  canonical_tree, one for new corpora via regex), and they
  disagreed.
- Adding a new food required writing new rules instead of letting
  the curated tree absorb it.

The LLM approach unifies it. One prompt produces canonical_path +
facets. Same prompt that produced the original 462k FDC retail run.
HTC codes are deterministically derived from canonical_path. The tree
itself is the source of truth; the regex encoder shrinks to a fallback
for the residual <5%.

---

## File index

### Inputs

- `recipe_pricing/data/api_cache_products.csv` — raw Walmart/Kroger cache (217,661 rows)
- `recipe_pricing/data/walmart_kroger_for_llm.csv` — deduped to 70,351 unique products
- `recipe_mapper/v1/output/recipe_ingredient_items.csv` — 74,624 unique recipe ingredients
- `recipe_pricing/data/full_llm_input.csv` — combined 144,975-row LLM input
- `retail_mapper/v2/consensus_full_corpus_audit.csv` — FDC canonical tree (source of truth)

### Pipeline scripts

- `recipe_pricing/build_walmart_kroger_for_llm.py` — adapter, dedupes API cache
- `recipe_pricing/build_full_llm_input.py` — merges Walmart/Kroger + recipe ingredients
- `retail_mapper/v2/run_full_csv_parallel.py` — DeepSeek driver (api.deepseek.com)
- `recipe_pricing/cleanup_llm_output.py` — normalize → HTC encode
- `recipe_pricing/find_path_duplicates.py` — dedup candidate analysis
- `retail_mapper/v2/apply_consensus_overrides.py` — apply merge rules

### Outputs

- `recipe_pricing/data/full_llm_run.live.jsonl` — DeepSeek raw output
- `recipe_pricing/output/api_cache_taxonomy_v2.csv` — Walmart/Kroger tagged
- `recipe_mapper/v1/output/recipe_ingredient_taxonomy_v2.csv` — recipe ingredients tagged
- `recipe_pricing/output/cleanup_review_queue.csv` — unmatched, needs human eyes
- `recipe_pricing/output/canonical_path_dedup_candidates.csv` — merge candidates
- `recipe_pricing/output/cleanup_summary.json` — match-method stats

### Reference / supporting

- `recipe_mapper/v1/htc/encoder.py` — deterministic group/family resolver
- `recipe_mapper/v1/htc/food_slots.py` — registry + lookup helpers
- `recipe_mapper/v1/htc/food_slot_registry.csv` — minted food slots
- `recipe_mapper/v1/HTC_SPEC.md` — 8-char code spec

---

## Status

The DeepSeek classification job is currently running over all 144,975
rows at concurrency 30. Output streams to
`recipe_pricing/data/full_llm_run.live.jsonl`. Resumable: ctrl-C and
re-run skips already-completed fdc_ids.

Once it finishes:

1. Run `cleanup_llm_output.py` for normalization + HTC encoding.
2. Run `find_path_duplicates.py` for the dedup analysis.
3. Review the top dedup candidates, write merge rules.
4. Re-run cleanup with the override CSV populated.
5. Final pass: re-encode HTC, regenerate
   `recipe_ingredient_join_audit.csv`.

The canonical tree shrinks toward a single consistent shape across
recipes, FDC retail, Walmart, and Kroger. HTC codes become stable
join keys across all sources. Recipe ↔ shoppable matching becomes
deterministic.
