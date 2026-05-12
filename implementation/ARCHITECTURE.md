# Category-First Routing — Architecture

**Status:** v1, deterministic, no LLM, no embedding cosine as primary signal.
**Scope:** Re-route products in `product_to_best_esha_full_map.vIdentity.csv` whose current ESHA assignment violates a hard category constraint.
**Author:** Claude (joining stuck pipeline 2026-04-27).

## The core principle

`branded_food_category` is a **HARD GATE**, not a preference. If a product's
branded category is "Pickles, Olives, Peppers & Relishes" and the assigned
ESHA code's cohort majority is "Bread", that routing is wrong by definition.
We do not soften this with embedding similarity. We do not let the language
model "judge". We re-route to a code whose cohort majority is *in the same
category cluster* as the product, or — if no such code exists — we record a
**new-leaf proposal** instead of force-fitting.

## Inputs

1. `product_to_best_esha_full_map.vIdentity.csv` — canonical map (462,646 rows).
   Edited in place. Audit trail goes in changelogs.
2. `product_to_best_esha_full_map.vIdentity.baseline.csv` — pre-pipeline state.
   We use this to compute **untainted** cohort majorities. Subsequent passes
   moved products around, which biases cohort majorities if computed from the
   current file. Always compute cohort statistics from baseline.
3. `esha_cleaned_canonical.csv` — 39,691 ESHA codes with descriptions.
4. `implementation/.embed_cache/` — cached MiniLM embeddings (used only as
   tiebreak, not as the primary signal).

## Pipeline

### Pre-step: cohort fingerprints (one-shot)

For every ESHA code that has any baseline-assigned products, compute
`majority_category`, `majority_share`, `cohort_size`. Codes with `cohort_size <= 3`
are **considered unobserved** — their majority is unreliable, so we treat them
as "category-flexible" (compatible with any category) for source-side checks
but cannot be used as re-route targets without a strong textual match.

### Step 1: category fitness check (hard gate)

For each product `p` with current ESHA code `c`:

- If `c` has an observed cohort and `cohort_majority(c)` is in the same
  **category cluster** as `p.branded_food_category`, the routing is
  **CATEGORY-OK** → leave it alone.
- Else → **NEEDS_REROUTE**.

The category cluster is a curated mapping — see
`category_cluster_map.json` (built into the script). It groups
synonyms ("Bread" ≈ "Breads & Buns" ≈ "Bread/Bakery Products Variety Packs"),
and clusters together obvious siblings ("Cookies & Biscuits" ≈ "Cake, Cookie
& Cupcake Mixes" ≈ "Biscuits/Cookies"). Clusters are deliberately **narrow**:
a Cracker is NOT in the same cluster as a Bread; Croutons are NOT in the
same cluster as Crackers. When in doubt, we err on the side of NOT clustering,
because false positives in the gate cause exactly the bugs we are fixing.

### Step 2: candidate search (within-cluster only)

For each NEEDS_REROUTE product, the candidate pool is:

```
Pool = { code | cohort_majority(code) is in cluster(product.category)
              AND cohort_size(code) >= 1 }
```

Strictly **within-cluster**. No fallback to "open pool".

### Step 3: candidate scoring (textual first, embedding tiebreak)

For each candidate code in the pool, score:

1. **+50** if `rft_fndds_desc` exact-tokenized-substring matches the candidate's
   tree Description. (rft_fndds is the existing FNDDS cross-walk; when both
   sides agree on a word string, this is a very strong signal.)
2. **+30** if `rft_sr28_desc` exact match.
3. **+10 per noun token** in product description that appears in the candidate
   description. Tokens are lowercased alpha-only, length ≥ 4 (to skip "the",
   "and", "with"). Domain stop-words (`flavor`, `style`, `original`, `variety`)
   are removed.
4. **+5 per noun token** in `rft_canonical_name` that appears in candidate.
5. **+ embedding_cosine × 5** as a tiebreaker only.

The winner must beat the runner-up by ≥ 3 points to count as confident.

### Step 4: apply or flag

- If best candidate's score ≥ 15 AND beats runner-up by ≥ 3 →
  apply re-route, write changelog row.
- Else → record `(fdc_id, product, current_code, top3_candidates_with_scores)`
  in `category_first_new_leaves.csv`. A separate human or downstream task
  decides whether to expand the tree.

### Step 5: protected rows

We do **not** touch a product whose `rft_verdict` is `EXACT` AND whose current
ESHA code is category-OK — that's already a strong match. We **DO** touch
`EXACT` rows whose category is contradicted (e.g. an "exact" textual match
against a Bread code for a Pickle product is still wrong — the FNDDS exact
match was on shared word "spread" or similar).

## Audit trail

- `category_first_changelog.csv` — every row we changed, with
  `fdc_id, product_description, branded_food_category, old_code, old_desc,
   new_code, new_desc, score, runner_up_score, signals_fired, reason`.
- `category_first_new_leaves.csv` — every product with no good in-cluster
  candidate, with top-3 attempted candidates so the human reviewer sees what
  the tree is missing.

We update the canonical CSV **in place**. We bump
`assignment_source = "category_first_route"` and
`best_esha_change_reason = "category_first_route"`.
`best_esha_original_code` is preserved if already set; otherwise we set it to
the current (pre-edit) code so we never lose the original audit trail.

## Decisions called out

- **Why baseline for cohort majorities?** Because the prior
  `primary_identity_fix` pass moved 183k products with soft-category logic.
  Using current assignments to compute cohort majorities would launder those
  prior moves into the truth set and we'd lose detection power.
- **Why no embedding-only routing?** Embeddings hallucinate. "Bread & butter
  pickles" looks textually like bread. The hard category gate is the only
  thing that prevents this.
- **Why narrow clusters?** False-positive clusters re-introduce the bug.
- **Why don't we revert primary_identity_fix wholesale?** Because the user
  said an auditor agent is concurrently checking it. We treat the current
  state as the input and compute cohort statistics from baseline. This means
  if `primary_identity_fix` produced a category-incompatible assignment,
  this pass will detect it (because the cohort stats see the original
  population) and re-route.
- **What we do NOT do:** open-pool fallback, LLM tiebreak, fuzzy stemming.
  The deal is "narrow and honest" rather than "wide and confident".

## Limits / known weaknesses

- Cohort statistics for codes with < 4 baseline products are unreliable. We
  flag those products into new-leaves rather than re-routing within them.
- The category-cluster map is hand-curated; it is incomplete. Categories not
  listed are treated as their own singleton cluster. False-negatives here
  (good routing flagged as needs-reroute) are recoverable; false-positives
  (bad routing accepted) are not.
- "Other Snacks" / "Other Drinks" / "Wholesome Snacks" are deliberately
  isolated singletons — they are too generic to safely cluster.
